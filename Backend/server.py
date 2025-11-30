from dotenv import load_dotenv
from flask import Flask, jsonify, request, g
from flask_cors import CORS
import time
import logging

from proxmox_client import (
    list_nodes,
    list_vms,
    get_vm_status,
    start_vm,
    stop_vm,
    create_vm_from_template,
)

from auth import require_auth, get_current_user
from logging_config import setup_logging, log_api_request

load_dotenv()

logger = setup_logging()

app = Flask(__name__)
CORS(app, resources={r"/api/*": {"origins": "*"}})  # dev only


@app.before_request
def before_request():
    g.start_time = time.time()


@app.after_request
def after_request(response):
    if request.path.startswith("/api/") and request.method != "OPTIONS":
        duration_ms = int((time.time() - g.start_time) * 1000)
        user = get_current_user()

        metadata = {}
        if request.method in ["POST", "PUT", "PATCH"]:
            metadata["request_body"] = request.get_json(silent=True) or {}
        if request.args:
            metadata["query_params"] = dict(request.args)

        log_api_request(
            logger,
            user_id=user["id"] if user else None,
            user_email=user["email"] if user else None,
            endpoint=request.path,
            http_method=request.method,
            status_code=response.status_code,
            duration_ms=duration_ms,
            metadata=metadata,
        )

    return response


@app.get("/api/health")
def health():
    return {"ok": True}


@app.get("/api/proxmox/nodes")
@require_auth
def api_nodes():
    try:
        nodes = list_nodes()
        logger.info("Listed Proxmox nodes", extra={
            "extra_fields": {
                "category": "vm_operation",
                "action": "list_nodes",
                "user_id": g.current_user["id"],
                "user_email": g.current_user["email"],
                "metadata": {"node_count": len(nodes)},
            }
        })
        return jsonify(nodes)
    except Exception as e:
        logger.error(f"Error listing nodes: {e}", exc_info=True, extra={
            "extra_fields": {
                "category": "system_error",
                "action": "list_nodes",
                "user_id": g.current_user["id"],
                "user_email": g.current_user["email"],
            }
        })
        return {"error": "Failed to list nodes"}, 500


@app.get("/api/proxmox/vms")
@require_auth
def api_vms():
    node = request.args.get("node")
    if not node:
        return {"error": "node query parameter is required"}, 400

    try:
        vms = list_vms(node)
        logger.info(f"Listed VMs on node {node}", extra={
            "extra_fields": {
                "category": "vm_operation",
                "action": "list_vms",
                "user_id": g.current_user["id"],
                "user_email": g.current_user["email"],
                "metadata": {"node": node, "vm_count": len(vms)},
            }
        })
        return jsonify(vms)
    except Exception as e:
        logger.error(f"Error listing VMs on node {node}: {e}", exc_info=True, extra={
            "extra_fields": {
                "category": "system_error",
                "action": "list_vms",
                "user_id": g.current_user["id"],
                "user_email": g.current_user["email"],
                "metadata": {"node": node},
            }
        })
        return {"error": "Failed to list VMs"}, 500


@app.get("/api/proxmox/vms/<node>/<int:vmid>/status")
@require_auth
def api_vm_status(node, vmid):
    try:
        status = get_vm_status(node, vmid)
        logger.info(f"Fetched status for VM {vmid}", extra={
            "extra_fields": {
                "category": "vm_operation",
                "action": "get_vm_status",
                "user_id": g.current_user["id"],
                "user_email": g.current_user["email"],
                "metadata": {"node": node, "vmid": vmid, "status": status.get("status")},
            }
        })
        return jsonify(status)
    except Exception as e:
        logger.error(f"Error getting VM status for {vmid}: {e}", exc_info=True, extra={
            "extra_fields": {
                "category": "system_error",
                "action": "get_vm_status",
                "user_id": g.current_user["id"],
                "user_email": g.current_user["email"],
                "metadata": {"node": node, "vmid": vmid},
            }
        })
        return {"error": "Failed to get VM status"}, 500


@app.post("/api/proxmox/vms/<node>/<int:vmid>/start")
@require_auth
def api_vm_start(node, vmid):
    try:
        upid = start_vm(node, vmid)
        logger.info(f"Started VM {vmid} on node {node}", extra={
            "extra_fields": {
                "category": "vm_operation",
                "action": "vm_start",
                "user_id": g.current_user["id"],
                "user_email": g.current_user["email"],
                "metadata": {"node": node, "vmid": vmid, "upid": upid},
            }
        })
        return jsonify({"upid": upid})
    except Exception as e:
        logger.error(f"Error starting VM {vmid}: {e}", exc_info=True, extra={
            "extra_fields": {
                "category": "system_error",
                "action": "vm_start",
                "user_id": g.current_user["id"],
                "user_email": g.current_user["email"],
                "metadata": {"node": node, "vmid": vmid},
            }
        })
        return {"error": "Failed to start VM"}, 500


@app.post("/api/proxmox/vms/<node>/<int:vmid>/stop")
@require_auth
def api_vm_stop(node, vmid):
    try:
        upid = stop_vm(node, vmid)
        logger.info(f"Stopped VM {vmid} on node {node}", extra={
            "extra_fields": {
                "category": "vm_operation",
                "action": "vm_stop",
                "user_id": g.current_user["id"],
                "user_email": g.current_user["email"],
                "metadata": {"node": node, "vmid": vmid, "upid": upid},
            }
        })
        return jsonify({"upid": upid})
    except Exception as e:
        logger.error(f"Error stopping VM {vmid}: {e}", exc_info=True, extra={
            "extra_fields": {
                "category": "system_error",
                "action": "vm_stop",
                "user_id": g.current_user["id"],
                "user_email": g.current_user["email"],
                "metadata": {"node": node, "vmid": vmid},
            }
        })
        return {"error": "Failed to stop VM"}, 500


@app.post("/api/proxmox/vms/create")
@require_auth
def api_vm_create():
    data = request.get_json() or {}

    node = data.get("node")
    template_vmid = data.get("template_vmid")
    name = data.get("name")
    cores = data.get("cores", 2)
    memory = data.get("memory", 2048)
    storage = data.get("storage", "local")

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

        logger.info(f"Created VM {name} (vmid={vmid}) from template {template_vmid}", extra={
            "extra_fields": {
                "category": "vm_operation",
                "action": "vm_create",
                "user_id": g.current_user["id"],
                "user_email": g.current_user["email"],
                "metadata": {
                    "node": node,
                    "vmid": vmid,
                    "vm_name": name,
                    "template_vmid": template_vmid,
                    "cores": cores,
                    "memory": memory,
                    "upid": upid,
                },
            }
        })

        return jsonify({
            "vmid": vmid,
            "upid": upid,
            "status": "ok",
            "message": f"VM '{name}' creation started on node {node}",
        }), 201

    except Exception as e:
        # Rare cases where something in Python blows up.
        logger.warning(f"VM creation request sent but backend error occurred: {e}", exc_info=True, extra={
            "extra_fields": {
                "category": "vm_operation",
                "action": "vm_create",
                "user_id": g.current_user["id"],
                "user_email": g.current_user["email"],
                "metadata": {
                    "node": node,
                    "vmid": vmid,
                    "vm_name": name,
                    "template_vmid": template_vmid,
                    "upid": upid,
                },
            }
        })
        return jsonify({
            "vmid": vmid,
            "upid": upid,
            "status": "unknown",
            "message": "VM creation request sent, but backend timed out or hit an error talking to Proxmox. Check the Proxmox UI.",
            "error": str(e),
        }), 202


if __name__ == "__main__":
    app.run(debug=True)
