from fastapi import APIRouter, HTTPException

from backend import devices_db
from backend.models.devices import AgentDeploymentRequest, DeviceAuditRequest

router = APIRouter()


# ── Agent Deployments (the "Agent" page's launcher downloads) ───────────────

@router.post("/api/organizations/{organization_id}/deployments")
def create_agent_deployment(organization_id: str, data: AgentDeploymentRequest):
    try:
        return devices_db.create_agent_deployment(
            organization_id=organization_id,
            requested_by=str(data.requested_by),
            launcher_type=data.launcher_type.value,
            deployment_mode=data.deployment_mode.value,
            site_id=str(data.site_id) if data.site_id else None,
            server_ip=data.server_ip,
            server_port=data.server_port,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/api/organizations/{organization_id}/deployments")
def list_deployments(organization_id: str, site_id: str = None):
    return {"deployments": devices_db.list_deployments(organization_id, site_id=site_id)}


@router.get("/api/deployments/{client_id}")
def get_deployment(client_id: str):
    dep = devices_db.get_deployment_by_client_id(client_id)
    if not dep:
        raise HTTPException(status_code=404, detail=f"No deployment found with client_id '{client_id}'.")
    return dep


# ── Device audit upload — what a downloaded launcher POSTs back ────────────

@router.post("/api/organizations/{organization_id}/devices/audit")
def submit_device_audit(organization_id: str, data: DeviceAuditRequest):
    try:
        return devices_db.record_device_audit(
            organization_id=organization_id,
            device_name=data.device_name,
            site_id=str(data.site_id) if data.site_id else None,
            deployment_id=str(data.deployment_id) if data.deployment_id else None,
            scanned_by=str(data.scanned_by) if data.scanned_by else None,
            device=data.device,
            software=data.software,
            users=data.users,
            login_history=data.login_history,
            gpus=data.gpus,
            network_adapters=data.network_adapters,
            storage=data.storage,
            peripherals=data.peripherals,
            printers=data.printers,
            connected_devices=data.connected_devices,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ── Hardware / Software reads ───────────────────────────────────────────────

@router.get("/api/organizations/{organization_id}/devices")
def list_hardware_devices(organization_id: str, site_id: str = None):
    return {"devices": devices_db.list_hardware_devices(organization_id, site_id=site_id)}


@router.get("/api/devices/{device_id}")
def get_device_detail(device_id: str):
    device = devices_db.get_device_detail(device_id)
    if not device:
        raise HTTPException(status_code=404, detail=f"No device found with id '{device_id}'.")
    return device


@router.get("/api/organizations/{organization_id}/stats/hardware")
def get_hardware_stats(organization_id: str):
    return devices_db.get_hardware_stats(organization_id)


@router.get("/api/organizations/{organization_id}/stats/software")
def get_software_stats(organization_id: str):
    return devices_db.get_software_stats(organization_id)
