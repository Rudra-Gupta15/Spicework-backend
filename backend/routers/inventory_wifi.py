from fastapi import APIRouter, HTTPException

from backend import auth_db
from backend.models.auth import ConnectWifiNetworkRequest, RecordNetworkScanRequest, StoreWifiNetworksRequest

router = APIRouter()


# ── WiFi Networks ────────────────────────────────────────────────────────────

@router.post("/api/organizations/{organization_id}/wifi-networks")
def store_wifi_networks(organization_id: str, data: StoreWifiNetworksRequest):
    """Persist the 'Available WiFi Networks' list fetched on login. No password here."""
    try:
        networks = auth_db.upsert_wifi_networks_bulk(
            organization_id, data.networks, site_id=str(data.site_id) if data.site_id else None,
        )
        return {"networks": networks}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/api/organizations/{organization_id}/wifi-networks/connect")
def connect_wifi_network(organization_id: str, data: ConnectWifiNetworkRequest):
    """Select a network, enter its password, connect — password is stored on that row."""
    try:
        return auth_db.upsert_wifi_network(
            organization_id, data.ssid,
            site_id=str(data.site_id) if data.site_id else None,
            password=data.password,
            mark_connected=True,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/api/organizations/{organization_id}/wifi-networks")
def list_wifi_networks(organization_id: str, site_id: str = None):
    return {"networks": auth_db.list_wifi_networks(organization_id, site_id=site_id)}


# ── Network Scans ("Connect & Scan" -> Connected Devices table) ────────────

@router.post("/api/organizations/{organization_id}/network-scans")
def record_network_scan(organization_id: str, data: RecordNetworkScanRequest):
    try:
        return auth_db.record_network_scan(
            organization_id=organization_id,
            performed_by=str(data.performed_by),
            ssid=data.ssid,
            devices=data.devices,
            site_id=str(data.site_id) if data.site_id else None,
            wifi_network_id=str(data.wifi_network_id) if data.wifi_network_id else None,
            ip_address=data.ip_address,
            subnet=data.subnet,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/api/organizations/{organization_id}/network-scans")
def list_network_scans(organization_id: str, site_id: str = None):
    return {"scans": auth_db.list_scans(organization_id, site_id=site_id)}


@router.get("/api/network-scans/{scan_id}")
def get_network_scan(scan_id: str):
    scan = auth_db.get_scan(scan_id)
    if not scan:
        raise HTTPException(status_code=404, detail=f"No scan found with id '{scan_id}'.")
    return scan
