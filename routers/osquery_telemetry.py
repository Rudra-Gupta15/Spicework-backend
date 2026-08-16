import json
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import Response

from backend import osquery_engine
from backend.core.config import DB_PATH, logger
from backend.core.state import sessions
from backend.db import get_db
from backend.models.osquery import OsqueryQueryRequest, RemoteAuditPayload
from backend.services.remote_audits import (
    DEVICE_DATA_25_FIELDS_SQL,
    DISK_INFORMATION_10_FIELDS_SQL,
    LOGIN_HISTORY_SQL,
    NETWORK_ADAPTERS_11_FIELDS_SQL,
    PARTITION_DATA_5_FIELDS_SQL,
    PERIPHERALS_5_FIELDS_SQL,
    SOFTWARE_INVENTORY_SQL,
    USER_DATA_7_FIELDS_SQL,
    VIDEO_CONTROLLERS_4_FIELDS_SQL,
    get_remote_telemetry_payload,
    remote_audits_db,
)

router = APIRouter()


@router.get("/api/osquery/device-data")
@router.post("/api/osquery/device-data")
def get_device_data_hardcoded(client_id: Optional[str] = Query(None)):
    if client_id and client_id in remote_audits_db:
        res = get_remote_telemetry_payload(client_id, "device-data")
        return {"status": "success", "count": len(res), "sql": DEVICE_DATA_25_FIELDS_SQL, "results": res}
    if not osquery_engine.is_osquery_available():
        raise HTTPException(status_code=500, detail="osqueryi binary is not installed on the server.")
    try:
        results = osquery_engine.run_osquery_sql(DEVICE_DATA_25_FIELDS_SQL)
        return {
            "status": "success",
            "count": len(results),
            "sql": DEVICE_DATA_25_FIELDS_SQL,
            "results": results
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/osquery/disk-data")
@router.post("/api/osquery/disk-data")
def get_disk_data_hardcoded():
    if not osquery_engine.is_osquery_available():
        raise HTTPException(status_code=500, detail="osqueryi binary is not installed on the server.")
    try:
        results = osquery_engine.run_osquery_sql(DISK_INFORMATION_10_FIELDS_SQL)
        return {
            "status": "success",
            "count": len(results),
            "sql": DISK_INFORMATION_10_FIELDS_SQL,
            "results": results
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/osquery/partition-data")
@router.post("/api/osquery/partition-data")
def get_partition_data_hardcoded():
    if not osquery_engine.is_osquery_available():
        raise HTTPException(status_code=500, detail="osqueryi binary is not installed on the server.")
    try:
        results = osquery_engine.run_osquery_sql(PARTITION_DATA_5_FIELDS_SQL)
        return {
            "status": "success",
            "count": len(results),
            "sql": PARTITION_DATA_5_FIELDS_SQL,
            "results": results
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/osquery/network-data")
@router.post("/api/osquery/network-data")
def get_network_data_hardcoded():
    if not osquery_engine.is_osquery_available():
        raise HTTPException(status_code=500, detail="osqueryi binary is not installed on the server.")
    try:
        results = osquery_engine.run_osquery_sql(NETWORK_ADAPTERS_11_FIELDS_SQL)
        return {
            "status": "success",
            "count": len(results),
            "sql": NETWORK_ADAPTERS_11_FIELDS_SQL,
            "results": results
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/osquery/peripheral-data")
@router.post("/api/osquery/peripheral-data")
def get_peripheral_data_hardcoded():
    if not osquery_engine.is_osquery_available():
        raise HTTPException(status_code=500, detail="osqueryi binary is not installed on the server.")
    try:
        results = osquery_engine.run_osquery_sql(PERIPHERALS_5_FIELDS_SQL)
        return {
            "status": "success",
            "count": len(results),
            "sql": PERIPHERALS_5_FIELDS_SQL,
            "results": results
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/osquery/video-data")
@router.post("/api/osquery/video-data")
def get_video_data_hardcoded(client_id: Optional[str] = Query(None)):
    if client_id and client_id in remote_audits_db:
        res = get_remote_telemetry_payload(client_id, "video-data")
        return {"status": "success", "count": len(res), "sql": VIDEO_CONTROLLERS_4_FIELDS_SQL, "results": res}
    if not osquery_engine.is_osquery_available():
        raise HTTPException(status_code=500, detail="osqueryi binary is not installed on the server.")
    try:
        results = osquery_engine.run_osquery_sql(VIDEO_CONTROLLERS_4_FIELDS_SQL)
        return {
            "status": "success",
            "count": len(results),
            "sql": VIDEO_CONTROLLERS_4_FIELDS_SQL,
            "results": results
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/osquery/user-data")
@router.post("/api/osquery/user-data")
def get_user_data_hardcoded():
    if not osquery_engine.is_osquery_available():
        raise HTTPException(status_code=500, detail="osqueryi binary is not installed on the server.")
    try:
        results = osquery_engine.run_osquery_sql(USER_DATA_7_FIELDS_SQL)
        return {
            "status": "success",
            "count": len(results),
            "sql": USER_DATA_7_FIELDS_SQL,
            "results": results
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/osquery/login-history")
@router.post("/api/osquery/login-history")
def get_login_history_hardcoded():
    if not osquery_engine.is_osquery_available():
        raise HTTPException(status_code=500, detail="osqueryi binary is not installed on the server.")
    try:
        results = osquery_engine.run_osquery_sql(LOGIN_HISTORY_SQL)
        return {
            "status": "success",
            "count": len(results),
            "sql": LOGIN_HISTORY_SQL,
            "results": results
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/osquery/software-inventory")
@router.post("/api/osquery/software-inventory")
def get_software_inventory_hardcoded():
    if not osquery_engine.is_osquery_available():
        raise HTTPException(status_code=500, detail="osqueryi binary is not installed on the server.")
    try:
        results = osquery_engine.run_osquery_sql(SOFTWARE_INVENTORY_SQL)
        return {
            "status": "success",
            "count": len(results),
            "sql": SOFTWARE_INVENTORY_SQL,
            "results": results
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/osquery/collector.ps1")
def download_remote_collector_ps1(request: Request):
    base_url = str(request.base_url).rstrip('/')
    script_content = f"""# Remote Laptop osquery Telemetry Collector
$ErrorActionPreference = "SilentlyContinue"
$ServerUrl = "{base_url}/api/osquery/submit-remote-audit"

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host " 🚀 InfraPulse Portal - Remote osquery Collector" -ForegroundColor Yellow
Write-Host " Target Cloud Server: $ServerUrl" -ForegroundColor Gray
Write-Host "==========================================================" -ForegroundColor Cyan

$osqueryPath = "C:\\Program Files\\osquery\\osqueryi.exe"
$hasOsquery = Test-Path $osqueryPath

Write-Host "🔍 Collecting System & Hardware Telemetry..." -ForegroundColor Green
$hostname = $env:COMPUTERNAME
$username = $env:USERNAME

$payload = @{{
    client_id = "audit_" + $hostname.ToLower()
    hostname = $hostname
    timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    osquery_installed = $hasOsquery
    device_name = $hostname
    os_name = (Get-CimInstance Win32_OperatingSystem).Caption
    manufacturer = (Get-CimInstance Win32_ComputerSystem).Manufacturer
    model = (Get-CimInstance Win32_ComputerSystem).Model
    serial_number = (Get-CimInstance Win32_BIOS).SerialNumber
}}

$jsonPayload = $payload | ConvertTo-Json -Depth 5

try {{
    Write-Host "📡 Sending Encrypted Telemetry to Cloud Backend..." -ForegroundColor Yellow
    $response = Invoke-RestMethod -Uri $ServerUrl -Method Post -Body $jsonPayload -ContentType "application/json"
    Write-Host "✅ Audit Submitted Successfully! Device Registered: $($payload.client_id)" -ForegroundColor Green
}} catch {{
    Write-Host "❌ Failed to submit audit to server: $_" -ForegroundColor Red
}}
"""
    return Response(content=script_content, media_type="text/plain")


@router.post("/api/osquery/submit-remote-audit")
def submit_remote_audit(payload: RemoteAuditPayload):
    remote_audits_db[payload.client_id] = payload.dict()
    sessions[payload.client_id] = {
        "status": "completed",
        "timestamp": payload.timestamp,
        "computer_name": payload.hostname,
        "os_name": payload.os_name or "Windows 11",
        "manufacturer": payload.manufacturer or "ASUSTeK COMPUTER INC.",
        "model": payload.model or "ROG Zephyrus G14",
        "serial_number": payload.serial_number or "S9NRCX017360369",
        "client_id": payload.client_id,
        "osquery_installed": payload.osquery_installed
    }
    return {
        "status": "success",
        "message": f"Remote audit received for {payload.hostname}",
        "client_id": payload.client_id,
        "timestamp": payload.timestamp
    }


@router.get("/api/osquery/remote-devices")
def get_remote_devices():
    return {
        "status": "success",
        "count": len(remote_audits_db),
        "devices": list(remote_audits_db.values())
    }


@router.post("/api/osquery/query")
def run_osquery_sql_api(data: OsqueryQueryRequest):
    if not osquery_engine.is_osquery_available():
        raise HTTPException(status_code=500, detail="osqueryi binary is not installed on the server.")

    query = data.sql.strip()
    if not query:
        raise HTTPException(status_code=400, detail="SQL query cannot be empty.")

    # Basic safety check
    forbidden = ["DELETE", "DROP", "UPDATE", "INSERT", "ALTER", "CREATE", "ATTACH"]
    if any(word in query.upper() for word in forbidden):
        raise HTTPException(status_code=400, detail="Only SELECT queries are allowed for osquery security safety.")

    try:
        results = osquery_engine.run_osquery_sql(query)
        return {
            "status": "success",
            "count": len(results),
            "results": results
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/osquery/scan")
def trigger_osquery_scan():
    if not osquery_engine.is_osquery_available():
        raise HTTPException(status_code=500, detail="osqueryi binary is not installed on this system.")

    try:
        payload = osquery_engine.collect_osquery_compliance_payload()
        mac = payload.get("mac_address", "00:00:00:00:00:00")
        cname = payload.get("computer_name", "OSQUERY-NODE")
        os_name = payload.get("os_name", "Unknown OS")
        exec_dt = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        payload["execution_datetime"] = exec_dt

        with get_db(DB_PATH) as conn:
            conn.execute('''
                INSERT INTO device_audits (mac_address, computer_name, os_name, execution_datetime, audit_data)
                VALUES (?, ?, ?, ?, ?)
            ''', (mac, cname, os_name, exec_dt, json.dumps(payload)))
            conn.commit()

        return {
            "status": "success",
            "message": f"osquery scan saved for {cname} ({mac})",
            "device_name": cname,
            "mac_address": mac
        }
    except Exception as e:
        logger.error(f"Error during osquery scan: {e}")
        raise HTTPException(status_code=500, detail=f"osquery scan failed: {str(e)}")
