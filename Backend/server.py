from dotenv import load_dotenv
from flask import Flask, jsonify, request, Response
from flask_cors import CORS
import time
import logging
import atexit
import os
import requests

from supabase import create_client, Client  # NEW

from proxmox_client import (
    list_nodes,
    list_vms,
    get_vm_status,
    start_vm,
    stop_vm,
    delete_vm,
    create_vm_from_template,
)

from auth import require_auth, get_current_user
from logging_config import setup_logging, log_api_request
from alerts_api import alerts_bp
from alert_engine import start_alert_engine, stop_alert_engine
from influx_queries import get_historical_metrics

load_dotenv()

logger = setup_logging()

# ------- SUPABASE HELPERS (Users.Role, Users.Proxmox) -------

_supabase_client: Client | None = None


def get_supabase() -> Client:
    global _supabase_client
    if _supabase_client is None:
        url = os.getenv("SUPABASE_URL")
        key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
        if not url or not key:
            raise RuntimeError(
                "SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set"
            )
        _supabase_client = create_client(url, key)
    return _supabase_client


def get_user_info(user_id: str) -> dict:
    """
    Returns e.g. {"Role": 1 or 2, "Proxmox": "101"} or {} if not found.
    """
    supabase = get_supabase()
    res = (
        supabase.table("Users")
        .select("Role, Proxmox")
        .eq("id", user_id)
        .maybe_single()
        .execute()
    )
    return res.data or {}


def set_user_proxmox(user_id: str, vmid: int | None) -> None:
    """
    Update Users.Proxmox for this user (string VMID or NULL).
    """
    supabase = get_supabase()
    value = str(vmid) if vmid is not None else None
    supabase.table("Users").update({"Proxmox": value}).eq("id", user_id).execute()


def get_vm_ip_address(proxmox, node: str, vmid: int, vm_type: str) -> str:
    try:
        if vm_type == 'qemu':
            agent_info = proxmox.nodes(node).qemu(vmid).agent('network-get-interfaces').get()

            if 'result' in agent_info:
                for interface in agent_info['result']:
                    if 'ip-addresses' in interface:
                        for ip_info in interface['ip-addresses']:
                            if ip_info.get('ip-address-type') == 'ipv4':
                                addr = ip_info.get('ip-address', '')
                                if addr and not addr.startswith('127.'):
                                    return addr
        elif vm_type == 'lxc':
            config = proxmox.nodes(node).lxc(vmid).config.get()
            return "N/A"

    except Exception as e:
        # VM might be stopped, agent not running, or other issues
        logger.debug(f"Could not get IP for VM {vmid}: {e}")
        pass

    return "N/A"


def generate_csv_response(infrastructure_data):
    from proxmox_client import get_proxmox

    output = StringIO()

    headers = [
        "node", "vmid", "name", "type", "status", "ip_address",
        "cpus", "maxcpus",
        "mem_mb", "maxmem_mb", "mem_usage_percent",
        "disk_gb", "maxdisk_gb", "disk_usage_percent",
        "uptime_hours", "cpu_percent"
    ]

    writer = csv.DictWriter(output, fieldnames=headers)
    writer.writeheader()

    try:
        proxmox = get_proxmox()
    except:
        proxmox = None

    for vm in infrastructure_data:
        mem_mb = vm.get("mem", 0) / (1024 * 1024)
        maxmem_mb = vm.get("maxmem", 0) / (1024 * 1024)
        mem_percent = (mem_mb / maxmem_mb * 100) if maxmem_mb > 0 else 0

        disk_gb = vm.get("disk", 0) / (1024 * 1024 * 1024)
        maxdisk_gb = vm.get("maxdisk", 0) / (1024 * 1024 * 1024)
        disk_percent = (disk_gb / maxdisk_gb * 100) if maxdisk_gb > 0 else 0

        uptime_hours = vm.get("uptime", 0) / 3600
        cpu_percent = vm.get("cpu", 0) * 100

        ip_address = "N/A"
        if proxmox:
            ip_address = get_vm_ip_address(
                proxmox,
                vm.get("node", ""),
                vm.get("vmid", 0),
                vm.get("type", "qemu")
            )

        writer.writerow({
            "node": vm.get("node", ""),
            "vmid": vm.get("vmid", ""),
            "name": vm.get("name", ""),
            "type": vm.get("type", ""),
            "status": vm.get("status", ""),
            "ip_address": ip_address,
            "cpus": vm.get("cpus", 0),
            "maxcpus": vm.get("maxcpus", 0),
            "mem_mb": f"{mem_mb:.2f}",
            "maxmem_mb": f"{maxmem_mb:.2f}",
            "mem_usage_percent": f"{mem_percent:.2f}",
            "disk_gb": f"{disk_gb:.2f}",
            "maxdisk_gb": f"{maxdisk_gb:.2f}",
            "disk_usage_percent": f"{disk_percent:.2f}",
            "uptime_hours": f"{uptime_hours:.2f}",
            "cpu_percent": f"{cpu_percent:.2f}"
        })

    csv_content = output.getvalue()
    timestamp = time.strftime("%Y%m%d_%H%M%S")

    return Response(
        csv_content,
        mimetype="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename=infrastructure_export_{timestamp}.csv"
        }
    )


def generate_json_response(infrastructure_data):
    from proxmox_client import get_proxmox

    formatted_data = []

    try:
        proxmox = get_proxmox()
    except:
        proxmox = None

    for vm in infrastructure_data:
        mem_mb = vm.get("mem", 0) / (1024 * 1024)
        maxmem_mb = vm.get("maxmem", 0) / (1024 * 1024)
        mem_percent = (mem_mb / maxmem_mb * 100) if maxmem_mb > 0 else 0

        disk_gb = vm.get("disk", 0) / (1024 * 1024 * 1024)
        maxdisk_gb = vm.get("maxdisk", 0) / (1024 * 1024 * 1024)
        disk_percent = (disk_gb / maxdisk_gb * 100) if maxdisk_gb > 0 else 0

        uptime_hours = vm.get("uptime", 0) / 3600
        cpu_percent = vm.get("cpu", 0) * 100

        ip_address = "N/A"
        if proxmox:
            ip_address = get_vm_ip_address(
                proxmox,
                vm.get("node", ""),
                vm.get("vmid", 0),
                vm.get("type", "qemu")
            )

        formatted_data.append({
            "node": vm.get("node", ""),
            "vmid": vm.get("vmid", ""),
            "name": vm.get("name", ""),
            "type": vm.get("type", ""),
            "status": vm.get("status", ""),
            "ip_address": ip_address,
            "resources": {
                "cpu": {
                    "current": vm.get("cpus", 0),
                    "max": vm.get("maxcpus", 0),
                    "usage_percent": round(cpu_percent, 2)
                },
                "memory": {
                    "current_mb": round(mem_mb, 2),
                    "max_mb": round(maxmem_mb, 2),
                    "usage_percent": round(mem_percent, 2)
                },
                "disk": {
                    "current_gb": round(disk_gb, 2),
                    "max_gb": round(maxdisk_gb, 2),
                    "usage_percent": round(disk_percent, 2)
                }
            },
            "uptime_hours": round(uptime_hours, 2)
        })

    timestamp = time.strftime("%Y%m%d_%H%M%S")

    return Response(
        json.dumps(formatted_data, indent=2),
        mimetype="application/json",
        headers={
            "Content-Disposition": f"attachment; filename=infrastructure_export_{timestamp}.json"
        }
    )


def generate_metrics_csv_response(metrics_data):
    output = StringIO()

    # CPU metrics
    cpu_headers = ["timestamp", "host", "metric_type", "value_percent"]
    writer = csv.DictWriter(output, fieldnames=cpu_headers)
    writer.writeheader()

    for point in metrics_data.get('cpu', []):
        writer.writerow({
            "timestamp": point.get('time', ''),
            "host": point.get('host', ''),
            "metric_type": "cpu",
            "value_percent": f"{point.get('value', 0):.2f}"
        })

    for point in metrics_data.get('memory', []):
        writer.writerow({
            "timestamp": point.get('time', ''),
            "host": point.get('host', ''),
            "metric_type": "memory",
            "value_percent": f"{point.get('value', 0):.2f}"
        })

    for point in metrics_data.get('storage', []):
        writer.writerow({
            "timestamp": point.get('time', ''),
            "host": point.get('host', ''),
            "metric_type": f"storage_{point.get('path', '/')}",
            "value_percent": f"{point.get('value', 0):.2f}"
        })

    csv_content = output.getvalue()
    timestamp = time.strftime("%Y%m%d_%H%M%S")

    return Response(
        csv_content,
        mimetype="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename=metrics_export_{timestamp}.csv"
        }
    )


def generate_metrics_json_response(metrics_data):
    timestamp = time.strftime("%Y%m%d_%H%M%S")

    return Response(
        json.dumps(metrics_data, indent=2),
        mimetype="application/json",
        headers={
            "Content-Disposition": f"attachment; filename=metrics_export_{timestamp}.json"
        }
    )


def generate_metrics_lineprotocol_response(metrics_data):
    output = StringIO()

    for point in metrics_data.get('cpu', []):
        timestamp_ns = int(time.mktime(time.strptime(point['time'][:19], "%Y-%m-%dT%H:%M:%S")) * 1e9)
        host = point['host'].replace(' ', '\\ ').replace(',', '\\,')
        value = point['value'] / 100.0  # Convert back to fraction for InfluxDB
        output.write(f"cpustat,host={host} cpu={value} {timestamp_ns}\n")

    for point in metrics_data.get('memory', []):
        timestamp_ns = int(time.mktime(time.strptime(point['time'][:19], "%Y-%m-%dT%H:%M:%S")) * 1e9)
        host = point['host'].replace(' ', '\\ ').replace(',', '\\,')
        value = point['value']
        # For line protocol, we'll store the percentage directly
        output.write(f"memory,host={host} usage_percent={value} {timestamp_ns}\n")

    for point in metrics_data.get('storage', []):
        timestamp_ns = int(time.mktime(time.strptime(point['time'][:19], "%Y-%m-%dT%H:%M:%S")) * 1e9)
        host = point['host'].replace(' ', '\\ ').replace(',', '\\,')
        path = point.get('path', '/').replace(' ', '\\ ').replace(',', '\\,')
        value = point['value']
        output.write(f"blockstat,host={host},path={path} per={value} {timestamp_ns}\n")

    line_protocol_content = output.getvalue()
    timestamp = time.strftime("%Y%m%d_%H%M%S")

    return Response(
        line_protocol_content,
        mimetype="text/plain",
        headers={
            "Content-Disposition": f"attachment; filename=metrics_export_{timestamp}.txt"
        }
    )


# ------- FLASK APP & ROUTES -------

app = Flask(__name__)
CORS(app, resources={r"/api/*": {"origins": "*"}})  # dev only

# Register alerts blueprint
app.register_blueprint(alerts_bp)

# Start alert engine on startup
try:
    start_alert_engine()
    logger.info("Alert engine started successfully")
except Exception as e:
    logger.error(f"Failed to start alert engine: {str(e)}")

# Register shutdown handler
atexit.register(stop_alert_engine)


@app.get("/api/health")
def health():
    return {"ok": True}


# ---- Proxmox routes ----

@app.get("/api/proxmox/nodes")
def api_nodes():
    """
    List Proxmox nodes.
    """
    try:
        nodes = list_nodes()
        return jsonify(nodes)
    except Exception as e:
        print("Error listing nodes:", e)
        return {"error": "Failed to list nodes"}, 500


@app.get("/api/proxmox/vms")
def api_vms():
    """
    List VMs on a given node.
    Usage: GET /api/proxmox/vms?node=proxmox-node-b
    """
    node = request.args.get("node")
    if not node:
        return {"error": "node query parameter is required"}, 400

    try:
        vms = list_vms(node)
        return jsonify(vms)
    except Exception as e:
        print("Error listing VMs:", e)
        return {"error": "Failed to list VMs"}, 500


@app.get("/api/proxmox/vms/<node>/<int:vmid>/status")
def api_vm_status(node, vmid):
    """
    Get current status of a VM.
    """
    try:
        status = get_vm_status(node, vmid)
        return jsonify(status)
    except Exception as e:
        print("Error getting VM status:", e)
        return {"error": "Failed to get VM status"}, 500


@app.post("/api/proxmox/vms/<node>/<int:vmid>/start")
@require_auth
def api_vm_start(node, vmid):
    """
    Start a VM.

    Students (Role=1): may only start their own VM, defined by Users.Proxmox.
    Staff/Admin (Role=2): can start any VM.
    """
    user = get_current_user()
    user_id = user["id"] if user else None

    info = get_user_info(user_id) if user_id else {}
    role = info.get("Role")
    prox = info.get("Proxmox")

    if role == 1:
        # Student: enforce ownership
        if not prox:
            return jsonify({"error": "You do not have a VM assigned"}), 403
        try:
            if int(prox) != int(vmid):
                return jsonify(
                    {"error": "You are not allowed to control this VM"}
                ), 403
        except (TypeError, ValueError):
            return jsonify({"error": "Invalid Proxmox VM assignment"}), 403

    try:
        upid = start_vm(node, vmid)
        return jsonify({"upid": upid})
    except Exception as e:
        print("Error starting VM:", e)
        return {"error": "Failed to start VM"}, 500


@app.post("/api/proxmox/vms/<node>/<int:vmid>/stop")
@require_auth
def api_vm_stop(node, vmid):
    """
    Stop (shutdown) a VM.

    Students (Role=1): may only stop their own VM.
    Staff/Admin: no restriction.
    """
    user = get_current_user()
    user_id = user["id"] if user else None

    info = get_user_info(user_id) if user_id else {}
    role = info.get("Role")
    prox = info.get("Proxmox")

    if role == 1:
        if not prox:
            return jsonify({"error": "You do not have a VM assigned"}), 403
        try:
            if int(prox) != int(vmid):
                return jsonify(
                    {"error": "You are not allowed to control this VM"}
                ), 403
        except (TypeError, ValueError):
            return jsonify({"error": "Invalid Proxmox VM assignment"}), 403

    try:
        upid = stop_vm(node, vmid)
        return jsonify({"upid": upid})
    except Exception as e:
        print("Error stopping VM:", e)
        return {"error": "Failed to stop VM"}, 500

@app.post("/api/proxmox/vms/<node>/<int:vmid>/delete")
@require_auth
def api_vm_delete(node, vmid):
    """
    Delete a VM.

    Students (Role=1): may only delete their own VM (Users.Proxmox).
    Staff/Admin (Role=2): may delete any VM.

    If the VM is still running, we try to stop it first.
    For students we also clear Users.Proxmox after successful delete.
    """
    user = get_current_user()
    user_id = user["id"] if user else None

    info = get_user_info(user_id) if user_id else {}
    role = info.get("Role")
    prox = info.get("Proxmox")

    # ---- Student ownership check ----
    if role == 1:
        if not prox:
            return jsonify({"error": "You do not have a VM assigned"}), 403
        try:
            if int(prox) != int(vmid):
                return jsonify(
                    {"error": "You are not allowed to delete this VM"}
                ), 403
        except (TypeError, ValueError):
            return jsonify({"error": "Invalid Proxmox VM assignment"}), 403

    try:
        # ---- Make sure VM is stopped before delete ----
        try:
            status = get_vm_status(node, vmid)
            if status.get("status") == "running":
                # hard stop (quick)
                try:
                    stop_vm(node, vmid)
                except Exception as e_stop:
                    print(f"Warning: failed to stop VM {vmid} before delete: {e_stop}")
        except Exception as e_status:
            # If we fail to read status, just log and continue; delete might still work
            print(f"Warning: failed to read status for VM {vmid}: {e_status}")

        # ---- Delete in Proxmox ----
        result = delete_vm(node, vmid)

        # ---- Clear student's Proxmox mapping if needed ----
        if role == 1 and user_id:
            try:
                set_user_proxmox(user_id, None)
            except Exception as e_set:
                print("Failed to clear Proxmox VMID for user:", e_set)

        return jsonify(
            {
                "status": "ok",
                "message": f"VM {vmid} deleted on node {node}",
                "result": result,
            }
        )
    except Exception as e:
        # Return the actual error text so you can see it in the browser
        print(f"Error deleting VM {vmid} on node {node}:", e)
        return (
            jsonify(
                {
                    "error": f"Delete failed: {str(e)}",
                }
            ),
            500,
        )

@app.post("/api/proxmox/vms/create")
@require_auth
def api_vm_create():
    """
    Create a new VM by cloning a template/base VM.

    Students (Role=1): can only have one VM in total (tracked in Users.Proxmox).
    Staff/Admin (Role=2): no limit.

    Expected JSON body:
    {
        "node": "proxmox-node-b",
        "template_vmid": 101,
        "name": "test-vm-01",
        "cores": 2,
        "memory": 2048,
        "storage": "local"
    }
    """
    data = request.get_json() or {}

    # ---- Role & existing VM check ----
    user = get_current_user()
    user_id = user["id"] if user else None

    info = get_user_info(user_id) if user_id else {}
    role = info.get("Role")
    prox = info.get("Proxmox")

    # 1 VM per student
    if role == 1 and prox not in (None, "", "null"):
        return (
            jsonify(
                {
                    "error": "You already have a VM assigned. Please contact staff if you need more.",
                }
            ),
            403,
        )

    node = data.get("node")
    template_vmid = data.get("template_vmid")
    name = data.get("name")
    cores = data.get("cores", 2)
    memory = data.get("memory", 2048)
    storage = data.get("storage", "local")

    # Basic validation
    if not node or not template_vmid or not name:
        return {
            "error": "node, template_vmid, and name are required"
        }, 400

    try:
        template_vmid = int(template_vmid)
        cores = int(cores)
        memory = int(memory)
    except ValueError:
        return {"error": "template_vmid, cores, and memory must be integers"}, 400

    vmid = None
    upid = None
    try:
        vmid, upid = create_vm_from_template(
            node=node,
            template_vmid=template_vmid,
            name=name,
            cores=cores,
            memory=memory,
            storage=storage,
        )

        # If this is a student, remember their VMID in Users.Proxmox
        if role == 1 and user_id:
            try:
                set_user_proxmox(user_id, vmid)
            except Exception as e_set:
                print("Failed to update Proxmox for user:", e_set)

        return jsonify({
            "vmid": vmid,
            "upid": upid,
            "status": "ok",
            "message": f"VM '{name}' creation started on node {node}",
        }), 201

    except Exception as e:
        # This covers rare cases where something in Python blows up.
        # Clone may still have started on Proxmox.
        print("Error creating VM (clone may have started):", e)
        return jsonify({
            "vmid": vmid,
            "upid": upid,
            "status": "unknown",
            "message": "VM creation request sent, but backend timed out or hit an error talking to Proxmox. Check the Proxmox UI.",
            "error": str(e),
        }), 202


@app.get("/api/proxmox/infrastructure/export")
@require_auth
def api_infrastructure_export():
    format_type = request.args.get("format", "json").lower()

    if format_type not in ["csv", "json"]:
        return jsonify({"error": "Invalid format. Use 'csv' or 'json'"}), 400

    # Get current user and role
    user = get_current_user()
    user_id = user["id"] if user else None
    info = get_user_info(user_id) if user_id else {}
    role = info.get("Role")
    user_proxmox_vmid = info.get("Proxmox")

    try:
        nodes = list_nodes()
        all_infrastructure = []

        for node in nodes:
            node_name = node.get("node") or node.get("id", "").split("/")[-1]
            try:
                vms = list_vms(node_name)
                all_infrastructure.extend(vms)
            except Exception as e:
                logger.warning(f"Failed to fetch VMs from node {node_name}: {e}")
                continue

        if role == 1:  # Student
            if user_proxmox_vmid:
                all_infrastructure = [
                    vm for vm in all_infrastructure
                    if str(vm.get("vmid")) == str(user_proxmox_vmid)
                ]
            else:
                all_infrastructure = []

        if format_type == "csv":
            return generate_csv_response(all_infrastructure)
        else:
            return generate_json_response(all_infrastructure)

    except Exception as e:
        logger.error(f"Export failed: {e}")
        return jsonify({"error": "Failed to export infrastructure data"}), 500


@app.get("/api/export/unified")
@require_auth
def api_unified_export():
    format_type = request.args.get("format", "json").lower()
    include_infra = request.args.get("include_infrastructure", "true").lower() == "true"
    include_metrics = request.args.get("include_metrics", "false").lower() == "true"
    multi_format = request.args.get("multi_format", "false").lower() == "true"
    start_time = request.args.get("start_time")
    end_time = request.args.get("end_time")

    if format_type not in ["csv", "json", "lineprotocol"]:
        return jsonify({"error": "Invalid format. Use 'csv', 'json', or 'lineprotocol'"}), 400

    if not include_infra and not include_metrics:
        return jsonify({"error": "Must include at least infrastructure or metrics"}), 400

    if include_metrics and (not start_time or not end_time):
        return jsonify({"error": "start_time and end_time required when including metrics"}), 400

    if format_type == "lineprotocol" and include_infra:
        return jsonify({"error": "Line Protocol format only supports metrics data"}), 400

    if multi_format and not include_metrics:
        return jsonify({"error": "Multi-format export requires metrics to be included"}), 400

    try:
        user = get_current_user()
        user_id = user["id"] if user else None
        info = get_user_info(user_id) if user_id else {}
        role = info.get("Role")
        user_proxmox_vmid = info.get("Proxmox")

        infrastructure_data = []
        metrics_data = {'cpu': [], 'memory': [], 'storage': []}

        if include_infra:
            nodes = list_nodes()
            for node in nodes:
                node_name = node.get("node") or node.get("id", "").split("/")[-1]
                try:
                    vms = list_vms(node_name)
                    infrastructure_data.extend(vms)
                except Exception as e:
                    logger.warning(f"Failed to fetch VMs from node {node_name}: {e}")

            if role == 1:  # Student
                if user_proxmox_vmid:
                    infrastructure_data = [
                        vm for vm in infrastructure_data
                        if str(vm.get("vmid")) == str(user_proxmox_vmid)
                    ]
                else:
                    infrastructure_data = []

        if include_metrics:
            metrics_data = get_historical_metrics(start_time, end_time)

        if multi_format and include_metrics:
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            zip_buffer = BytesIO()

            with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
                if format_type == "csv":
                    csv_output = StringIO()
                    csv_writer = csv.writer(csv_output)
                    csv_writer.writerow(["timestamp", "host", "metric_type", "value_percent"])

                    for point in metrics_data.get('cpu', []):
                        csv_writer.writerow([point.get('time', ''), point.get('host', ''), "cpu", f"{point.get('value', 0):.2f}"])
                    for point in metrics_data.get('memory', []):
                        csv_writer.writerow([point.get('time', ''), point.get('host', ''), "memory", f"{point.get('value', 0):.2f}"])
                    for point in metrics_data.get('storage', []):
                        csv_writer.writerow([point.get('time', ''), point.get('host', ''), f"storage_{point.get('path', '/')}", f"{point.get('value', 0):.2f}"])

                    zip_file.writestr(f"metrics_{timestamp}.csv", csv_output.getvalue())

                elif format_type == "json":
                    zip_file.writestr(f"metrics_{timestamp}.json", json.dumps(metrics_data, indent=2))

                lineprotocol_output = StringIO()

                for point in metrics_data.get('cpu', []):
                    timestamp_ns = int(time.mktime(time.strptime(point['time'][:19], "%Y-%m-%dT%H:%M:%S")) * 1e9)
                    host = point['host'].replace(' ', '\\ ').replace(',', '\\,')
                    value = point['value'] / 100.0
                    lineprotocol_output.write(f"cpustat,host={host} cpu={value} {timestamp_ns}\n")

                for point in metrics_data.get('memory', []):
                    timestamp_ns = int(time.mktime(time.strptime(point['time'][:19], "%Y-%m-%dT%H:%M:%S")) * 1e9)
                    host = point['host'].replace(' ', '\\ ').replace(',', '\\,')
                    value = point['value']
                    lineprotocol_output.write(f"memory,host={host} usage_percent={value} {timestamp_ns}\n")

                for point in metrics_data.get('storage', []):
                    timestamp_ns = int(time.mktime(time.strptime(point['time'][:19], "%Y-%m-%dT%H:%M:%S")) * 1e9)
                    host = point['host'].replace(' ', '\\ ').replace(',', '\\,')
                    path = point.get('path', '/').replace(' ', '\\ ').replace(',', '\\,')
                    value = point['value']
                    lineprotocol_output.write(f"blockstat,host={host},path={path} per={value} {timestamp_ns}\n")

                zip_file.writestr(f"metrics_{timestamp}.txt", lineprotocol_output.getvalue())

            zip_buffer.seek(0)
            return Response(
                zip_buffer.getvalue(),
                mimetype="application/zip",
                headers={"Content-Disposition": f"attachment; filename=metrics_export_{timestamp}.zip"}
            )

        if format_type == "csv":
            # Combine both datasets into one CSV
            output = StringIO()
            writer = csv.writer(output)

            if include_infra:
                writer.writerow(["=== INFRASTRUCTURE DATA ==="])
                writer.writerow([
                    "node", "vmid", "name", "type", "status", "ip_address",
                    "cpus", "maxcpus", "mem_mb", "maxmem_mb", "mem_usage_percent",
                    "disk_gb", "maxdisk_gb", "disk_usage_percent",
                    "uptime_hours", "cpu_percent"
                ])

                from proxmox_client import get_proxmox
                try:
                    proxmox = get_proxmox()
                except:
                    proxmox = None

                for vm in infrastructure_data:
                    mem_mb = vm.get("mem", 0) / (1024 * 1024)
                    maxmem_mb = vm.get("maxmem", 0) / (1024 * 1024)
                    mem_percent = (mem_mb / maxmem_mb * 100) if maxmem_mb > 0 else 0
                    disk_gb = vm.get("disk", 0) / (1024 * 1024 * 1024)
                    maxdisk_gb = vm.get("maxdisk", 0) / (1024 * 1024 * 1024)
                    disk_percent = (disk_gb / maxdisk_gb * 100) if maxdisk_gb > 0 else 0
                    uptime_hours = vm.get("uptime", 0) / 3600
                    cpu_percent = vm.get("cpu", 0) * 100

                    ip_address = "N/A"
                    if proxmox:
                        ip_address = get_vm_ip_address(proxmox, vm.get("node", ""), vm.get("vmid", 0), vm.get("type", "qemu"))

                    writer.writerow([
                        vm.get("node", ""), vm.get("vmid", ""), vm.get("name", ""),
                        vm.get("type", ""), vm.get("status", ""), ip_address,
                        vm.get("cpus", 0), vm.get("maxcpus", 0),
                        f"{mem_mb:.2f}", f"{maxmem_mb:.2f}", f"{mem_percent:.2f}",
                        f"{disk_gb:.2f}", f"{maxdisk_gb:.2f}", f"{disk_percent:.2f}",
                        f"{uptime_hours:.2f}", f"{cpu_percent:.2f}"
                    ])

            if include_metrics:
                writer.writerow([])
                writer.writerow(["=== METRICS DATA ==="])
                writer.writerow(["timestamp", "host", "metric_type", "value_percent"])

                for point in metrics_data.get('cpu', []):
                    writer.writerow([point.get('time', ''), point.get('host', ''), "cpu", f"{point.get('value', 0):.2f}"])
                for point in metrics_data.get('memory', []):
                    writer.writerow([point.get('time', ''), point.get('host', ''), "memory", f"{point.get('value', 0):.2f}"])
                for point in metrics_data.get('storage', []):
                    writer.writerow([point.get('time', ''), point.get('host', ''), f"storage_{point.get('path', '/')}", f"{point.get('value', 0):.2f}"])

            timestamp = time.strftime("%Y%m%d_%H%M%S")
            return Response(
                output.getvalue(),
                mimetype="text/csv",
                headers={"Content-Disposition": f"attachment; filename=export_combined_{timestamp}.csv"}
            )

        elif format_type == "lineprotocol":
            return generate_metrics_lineprotocol_response(metrics_data)

        else:
            combined_data = {}
            if include_infra:
                combined_data['infrastructure'] = infrastructure_data
            if include_metrics:
                combined_data['metrics'] = metrics_data

            timestamp = time.strftime("%Y%m%d_%H%M%S")
            return Response(
                json.dumps(combined_data, indent=2),
                mimetype="application/json",
                headers={"Content-Disposition": f"attachment; filename=export_combined_{timestamp}.json"}
            )

    except Exception as e:
        logger.error(f"Unified export failed: {e}")
        return jsonify({"error": f"Failed to export data: {str(e)}"}), 500


@app.get("/api/influxdb/metrics/export")
@require_auth
def api_metrics_export():
    format_type = request.args.get("format", "json").lower()
    start_time = request.args.get("start_time")
    end_time = request.args.get("end_time")

    if format_type not in ["csv", "json", "lineprotocol"]:
        return jsonify({"error": "Invalid format. Use 'csv', 'json', or 'lineprotocol'"}), 400

    if not start_time or not end_time:
        return jsonify({"error": "start_time and end_time are required"}), 400

    try:
        metrics_data = get_historical_metrics(start_time, end_time)

        total_points = (
            len(metrics_data.get('cpu', [])) +
            len(metrics_data.get('memory', [])) +
            len(metrics_data.get('storage', []))
        )

        if total_points == 0:
            logger.warning(f"No metrics data found for time range {start_time} to {end_time}")

        if format_type == "csv":
            return generate_metrics_csv_response(metrics_data)
        elif format_type == "lineprotocol":
            return generate_metrics_lineprotocol_response(metrics_data)
        else:
            return generate_metrics_json_response(metrics_data)

    except Exception as e:
        logger.error(f"Metrics export failed: {e}")
        return jsonify({"error": f"Failed to export metrics data: {str(e)}"}), 500


if __name__ == "__main__":
    app.run(debug=True)