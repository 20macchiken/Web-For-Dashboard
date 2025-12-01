from dotenv import load_dotenv
from flask import Flask, jsonify, request
from flask_cors import CORS
import time
import logging
import atexit
import os  # NEW

from supabase import create_client, Client  # NEW

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
from alerts_api import alerts_bp
from alert_engine import start_alert_engine, stop_alert_engine

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


if __name__ == "__main__":
    app.run(debug=True)