import os
import requests
from proxmoxer import ProxmoxAPI


def _str_to_bool(value: str) -> bool:
    return str(value).lower() in ("1", "true", "yes", "on")


def get_proxmox():
    """
    Create and return a proxmoxer client using env variables.
    Uses API token auth.
    """
    host = os.getenv("PROXMOX_HOST")
    user = os.getenv("PROXMOX_USER")
    token_name = os.getenv("PROXMOX_TOKEN_NAME")
    token_value = os.getenv("PROXMOX_TOKEN_VALUE")
    verify_ssl = _str_to_bool(os.getenv("PROXMOX_VERIFY_SSL", "false"))

    if not all([host, user, token_name, token_value]):
        raise RuntimeError("Proxmox env variables are not fully set")

    proxmox = ProxmoxAPI(
        host,
        user=user,
        token_name=token_name,
        token_value=token_value,
        verify_ssl=verify_ssl,
        timeout=30,  # bump timeout so clone doesn’t instantly time out
    )
    return proxmox


def list_nodes():
    """
    Return all nodes in the cluster.
    """
    proxmox = get_proxmox()
    return proxmox.nodes.get()


def list_vms(node: str):
    """
    List all VMs/containers on a node (QEMU + LXC)
    using the cluster.resources API.
    """
    proxmox = get_proxmox()
    resources = proxmox.cluster.resources.get(type="vm")  # qemu + lxc

    # Debug log so you can see what Proxmox returns in the server console
    print("cluster.resources(type='vm') =", resources)

    # Filter by node name
    return [vm for vm in resources if vm.get("node") == node]


def get_vm_status(node: str, vmid: int):
    proxmox = get_proxmox()
    return proxmox.nodes(node).qemu(vmid).status.current.get()


def start_vm(node: str, vmid: int):
    proxmox = get_proxmox()
    return proxmox.nodes(node).qemu(vmid).status.start.post()


def stop_vm(node: str, vmid: int, force: bool = True):
    """
    Stop a VM on Proxmox.

    By default we use a *hard stop* (power off) so it does not wait
    for the guest OS to shutdown gracefully.

    If you ever want a slow graceful shutdown instead, call with: force=False
    """
    proxmox = get_proxmox_client()

    if force:
        # Hard power-off, returns immediately and does not wait for guest
        return proxmox.nodes(node).qemu(vmid).status().stop.post()
    else:
        # Graceful shutdown (can timeout if guest doesn't respond)
        return proxmox.nodes(node).qemu(vmid).status().shutdown.post()
    
def delete_vm(node: str, vmid: int):
    """
    Permanently delete a VM from Proxmox.
    """
    proxmox = get_proxmox()     # <<< same helper as list_nodes / start_vm / stop_vm
    return proxmox.nodes(node).qemu(vmid).delete()






def create_vm_from_template(
    node: str,
    template_vmid: int,
    name: str,
    cores: int,
    memory: int,
    storage: str,
):
    """
    Create a new VM by cloning from an existing template/base VM.

    - node: Proxmox node name (e.g. 'proxmox-node-b')
    - template_vmid: VMID of the VM to clone (e.g. 101)
    - name: name for the new VM
    - cores: number of vCPUs
    - memory: RAM in MB (e.g. 2048 = 2GB)
    - storage: target storage (e.g. 'local')
    """
    proxmox = get_proxmox()

    # 1) Get next free VMID
    vmid = int(proxmox.cluster.nextid.get())

    # 2) Clone the template VM (async task)
    try:
        upid = proxmox.nodes(node).qemu(template_vmid).clone.post(
            newid=vmid,
            name=name,
            full=1,
            target=node,
            storage=storage,
        )
    except requests.exceptions.ReadTimeout as e:
        # Proxmox is slow to answer; clone may still be running on the node
        print(f"Clone request timed out for VMID {vmid}, task may still be running:", e)
        upid = None

    # 3) Try to configure CPU + RAM, but don't fail the whole request
    try:
        proxmox.nodes(node).qemu(vmid).config.post(
            cores=cores,
            memory=memory,
        )
    except Exception as e:
        print(f"Warning: failed to set config for VM {vmid}:", e)

    return vmid, upid