from dotenv import load_dotenv
from flask import Flask, jsonify, request
from flask_cors import CORS

from proxmox_client import (
    list_nodes,
    list_vms,
    get_vm_status,
    start_vm,
    stop_vm,
    create_vm_from_template,
)

# ------- ENV -------
load_dotenv()

# ------- FLASK APP & ROUTES -------

app = Flask(__name__)
CORS(app, resources={r"/api/*": {"origins": "*"}})  # dev only


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
def api_vm_start(node, vmid):
    """
    Start a VM.
    """
    try:
        upid = start_vm(node, vmid)
        return jsonify({"upid": upid})
    except Exception as e:
        print("Error starting VM:", e)
        return {"error": "Failed to start VM"}, 500


@app.post("/api/proxmox/vms/<node>/<int:vmid>/stop")
def api_vm_stop(node, vmid):
    """
    Stop (shutdown) a VM.
    """
    try:
        upid = stop_vm(node, vmid)
        return jsonify({"upid": upid})
    except Exception as e:
        print("Error stopping VM:", e)
        return {"error": "Failed to stop VM"}, 500


@app.post("/api/proxmox/vms/create")
def api_vm_create():
    """
    Create a new VM by cloning a template/base VM.

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