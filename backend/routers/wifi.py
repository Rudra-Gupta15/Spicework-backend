import base64
import os
import re
import socket
import tempfile
import time
import uuid
from datetime import datetime

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse

from backend import legacy_db
from backend.core.config import logger
from backend.models.discovery import NetworkScanRequest
from backend.models.wifi import NotificationRequest, WifiConnectRequest, WifiSaveCredentialRequest
from backend.routers.discovery import network_scan
from backend.services.network_utils import _is_windows, _run_cmd, calculate_wifi_distance, enrich_scan_results

router = APIRouter()


@router.get("/wifi/networks")
@router.get("/api/wifi/networks")
def get_wifi_networks():
    """List nearby WiFi networks via netsh (Windows only)."""
    if not _is_windows():
        return {
            "networks": [],
            "total": 0,
            "is_cloud_server": True,
            "message": "WiFi Hardware Unavailable (Running on Cloud Linux Server). Local WiFi scanning requires hosting on a local Windows machine."
        }

    stdout, _ = _run_cmd("netsh wlan show networks mode=bssid")

    networks = []
    current: dict = {}

    for line in stdout.splitlines():
        line = line.strip()
        if re.match(r'^SSID\s+\d+\s*:', line) and "BSSID" not in line:
            if current.get("ssid"):
                networks.append(current)
            ssid_val = line.split(":", 1)[1].strip()
            current = {"ssid": ssid_val, "authentication": "", "encryption": "", "signal": ""}
        elif line.startswith("Authentication") and ":" in line:
            current["authentication"] = line.split(":", 1)[1].strip()
        elif line.startswith("Encryption") and ":" in line:
            current["encryption"] = line.split(":", 1)[1].strip()
        elif line.startswith("Signal") and ":" in line:
            current["signal"] = line.split(":", 1)[1].strip()

    if current.get("ssid"):
        networks.append(current)

    # Query saved Windows WiFi profiles
    saved_profiles = set()
    try:
        p_stdout, _ = _run_cmd("netsh wlan show profiles")
        for line in p_stdout.splitlines():
            if ":" in line and ("All User Profile" in line or "User Profile" in line):
                pname = line.split(":", 1)[1].strip()
                if pname:
                    saved_profiles.add(pname)
    except Exception:
        pass

    # Query DB saved wifi credentials
    try:
        for ssid in legacy_db.list_wifi_ssids():
            if ssid:
                saved_profiles.add(ssid)
    except Exception:
        pass

    # Deduplicate: keep highest signal per SSID
    seen: dict = {}
    for n in networks:
        ssid = n["ssid"]
        raw  = n.get("signal", "0%").replace("%", "")
        sig  = int(raw) if raw.isdigit() else 0
        if ssid not in seen or sig > seen[ssid]["_sig"]:
            seen[ssid] = {**n, "_sig": sig, "has_saved_password": (ssid in saved_profiles)}

    result = [{k: v for k, v in net.items() if k != "_sig"} for net in seen.values()]
    result.sort(
        key=lambda x: int(x.get("signal", "0%").replace("%", "")) if x.get("signal", "0%").replace("%", "").isdigit() else 0,
        reverse=True,
    )
    return {"networks": result, "total": len(result)}


@router.get("/wifi/current")
@router.get("/wifi-status")
@router.get("/api/wifi-status")
@router.get("/api/wifi/current")
def get_current_wifi():
    """Return the current WiFi connection info including derived /24 subnet and router distance."""
    if not _is_windows():
        return {"connected": False, "ssid": None, "ip": None, "subnet": None, "distance_str": "Unknown"}

    stdout, _ = _run_cmd("netsh wlan show interfaces")

    ssid         = None
    state        = "disconnected"
    adapter_name = None
    signal       = "0%"
    rssi_val     = None
    band         = None
    channel      = None

    for line in stdout.splitlines():
        line = line.strip()
        if line.startswith("Name") and ":" in line and "Network" not in line and "Description" not in line:
            adapter_name = line.split(":", 1)[1].strip()
        elif line.startswith("State") and ":" in line:
            state = line.split(":", 1)[1].strip().lower()
        elif re.match(r'^SSID\s*:', line) and "BSSID" not in line:
            ssid = line.split(":", 1)[1].strip()
        elif line.startswith("Signal") and ":" in line:
            signal = line.split(":", 1)[1].strip()
        elif line.startswith("Rssi") and ":" in line:
            raw_r = line.split(":", 1)[1].strip()
            if raw_r.replace("-", "").isdigit():
                rssi_val = int(raw_r)
        elif line.startswith("Band") and ":" in line:
            band = line.split(":", 1)[1].strip()
        elif line.startswith("Channel") and ":" in line:
            channel = line.split(":", 1)[1].strip()

    connected  = (state == "connected" and bool(ssid))
    ip_address = None
    subnet     = None

    if connected and adapter_name:
        ip_out, _ = _run_cmd(f'netsh interface ip show addresses "{adapter_name}"')
        for ln in ip_out.splitlines():
            ln = ln.strip()
            if ln.startswith("IP Address") and ":" in ln:
                ip_address = ln.split(":", 1)[1].strip()
                break

        if ip_address:
            parts = ip_address.split(".")
            if len(parts) == 4:
                subnet = f"{parts[0]}.{parts[1]}.{parts[2]}.0/24"

    sig_num = int(signal.replace("%", "")) if signal.replace("%", "").isdigit() else 0
    dist_info = calculate_wifi_distance(signal_percent=sig_num, rssi_dbm=rssi_val)

    return {
        "connected":    connected,
        "ssid":         ssid,
        "state":        state,
        "adapter":      adapter_name,
        "signal":       signal,
        "rssi":         dist_info["rssi_dbm"],
        "band":         band,
        "channel":      channel,
        "distance_m":   dist_info["distance_m"],
        "distance_str": dist_info["distance_str"],
        "ip":           ip_address,
        "subnet":       subnet,
    }


@router.get("/wifi/credentials")
def get_saved_wifi_credentials():
    credentials = {}
    for row in legacy_db.list_wifi_credentials():
        credentials[row['ssid']] = {
            "ssid": row['ssid'],
            "password": row['password'],
            "updated_at": row['updated_at']
        }
    return {"credentials": credentials}


@router.post("/wifi/save-credential")
def save_wifi_credential(req: WifiSaveCredentialRequest):
    if not req.ssid or not req.password:
        raise HTTPException(status_code=400, detail="SSID and password cannot be empty.")
    legacy_db.save_wifi_credential(req.ssid.strip(), req.password)
    return {"status": "saved", "ssid": req.ssid.strip()}


@router.post("/wifi/connect")
@router.post("/api/wifi/connect")
def connect_wifi(req: WifiConnectRequest):
    """Create a WPA2-Personal profile and connect to the given SSID."""
    ssid     = req.ssid
    password = req.password

    if not ssid:
        return JSONResponse(status_code=400, content={"status": "error", "message": "SSID cannot be empty."})
    if len(password) < 8:
        return JSONResponse(status_code=400, content={"status": "error", "message": "WiFi password must be at least 8 characters."})

    # Save credential permanently to DB
    try:
        legacy_db.save_wifi_credential(ssid.strip(), password)
    except Exception as db_err:
        logger.warning(f"Could not save WiFi credential to DB: {db_err}")

    if not _is_windows():
        return JSONResponse(status_code=400, content={"status": "error", "message": "WiFi connection is supported when hosted on local Windows machine."})

    def _xml_esc(s: str) -> str:
        return (s.replace("&", "&amp;")
                 .replace("<", "&lt;").replace(">", "&gt;")
                 .replace('"', "&quot;").replace("'", "&apos;"))

    profile_xml = (
        '<?xml version="1.0"?>\n'
        '<WLANProfile xmlns="http://www.microsoft.com/networking/WLAN/profile/v1">\n'
        f'    <name>{_xml_esc(ssid)}</name>\n'
        '    <SSIDConfig>\n'
        '        <SSID>\n'
        f'            <name>{_xml_esc(ssid)}</name>\n'
        '        </SSID>\n'
        '    </SSIDConfig>\n'
        '    <connectionType>ESS</connectionType>\n'
        '    <connectionMode>auto</connectionMode>\n'
        '    <MSM>\n'
        '        <security>\n'
        '            <authEncryption>\n'
        '                <authentication>WPA2PSK</authentication>\n'
        '                <encryption>AES</encryption>\n'
        '                <useOneX>false</useOneX>\n'
        '            </authEncryption>\n'
        '            <sharedKey>\n'
        '                <keyType>passPhrase</keyType>\n'
        '                <protected>false</protected>\n'
        f'                <keyMaterial>{_xml_esc(password)}</keyMaterial>\n'
        '            </sharedKey>\n'
        '        </security>\n'
        '    </MSM>\n'
        '</WLANProfile>'
    )

    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".xml", delete=False, encoding="utf-8") as tmp:
            tmp.write(profile_xml)
            tmp_path = tmp.name

        add_out, _ = _run_cmd(f'netsh wlan add profile filename="{tmp_path}" user=current')
        logger.info(f"WiFi add profile: {add_out.strip()}")

        conn_out, conn_rc = _run_cmd(f'netsh wlan connect name="{ssid}"')
        logger.info(f"WiFi connect: {conn_out.strip()}")

        if conn_rc != 0 and "successfully" not in conn_out.lower():
            return {"status": "error", "message": f"Connection command failed: {conn_out.strip()}"}

        # Poll for IP assignment (up to 12 s)
        for _ in range(12):
            time.sleep(1)
            cur = get_current_wifi()
            if cur.get("connected") and cur.get("ssid") == ssid and cur.get("ip"):
                return {
                    "status": "connected",
                    "ssid":   ssid,
                    "ip":     cur["ip"],
                    "subnet": cur["subnet"],
                }

        return {
            "status":  "connecting",
            "ssid":    ssid,
            "message": "Connection initiated. Waiting for IP — check status again in a moment.",
        }

    except Exception as e:
        logger.error(f"WiFi connect error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except Exception:
                pass


@router.get("/wifi/scan-devices")
def wifi_scan_devices(subnet: str = Query(None)):
    """Scan the WiFi subnet and enrich results with stored audit data."""
    if not subnet:
        cur    = get_current_wifi()
        subnet = cur.get("subnet")

    if not subnet:
        raise HTTPException(
            status_code=400,
            detail="No subnet provided and no active WiFi connection detected.",
        )

    # Run port scan
    scan_req = NetworkScanRequest(ip_range=subnet, timeout_ms=400)
    return enrich_scan_results(network_scan(scan_req))


@router.post("/audit/send-notification")
def send_notification(req: NotificationRequest):
    winrm = None
    PsExecClient = None
    if not winrm or not PsExecClient:
        raise HTTPException(status_code=500, detail="Missing winrm or pypsexec libraries.")

    server_url = f"http://{socket.gethostbyname(socket.gethostname())}:8000"
    client_id = f"audit_{uuid.uuid4().hex[:12]}"

    ps_payload = f"""
$User = (Get-WmiObject -Class Win32_ComputerSystem).UserName
if (-not $User) {{ exit 1 }}
$xml = @"
<Toast>
    <visual>
        <binding template="ToastText02">
            <text id="1">IT Security Audit Required</text>
            <text id="2">Please leave this window open. IT is running a mandatory compliance scan.</text>
        </binding>
    </visual>
</Toast>
"@
$null = [Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime]
$xmlDoc = New-Object Windows.Data.Xml.Dom.XmlDocument
$xmlDoc.LoadXml($xml)
$toast = [Windows.UI.Notifications.ToastNotification]::new($xmlDoc)
$notifier = [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier("IT Department")
$notifier.Show($toast)

Write-Host "==============================================" -ForegroundColor Cyan
Write-Host "    INFRAPULSE IT COMPLIANCE & SECURITY AUDIT   " -ForegroundColor Cyan
Write-Host "==============================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "A mandatory IT security audit has been initiated."
Write-Host "Please press ENTER to allow the scan to proceed..." -ForegroundColor Yellow
Read-Host

curl.exe -s "{server_url}/api/get-audit-script?client_id={client_id}" -o "$env:TEMP\\audit.ps1"; powershell -ExecutionPolicy Bypass -File "$env:TEMP\\audit.ps1"
"""

    encoded_cmd = base64.b64encode(ps_payload.encode('utf-16le')).decode('utf-8')
    cmd = f'powershell.exe -NoProfile -EncodedCommand {encoded_cmd}'

    results = {}
    methods_to_try = ["winrm", "psexec"] if req.method == "auto" else [req.method]

    for method in methods_to_try:
        try:
            logger.info(f"Sending notification to {req.ip_address} using {method}")
            if method == "winrm":
                s = winrm.Session(f'http://{req.ip_address}:5985/wsman', auth=(req.username, req.password), transport='ntlm')
                r = s.run_cmd(cmd)
                if r.status_code == 0:
                    return {"status": "success", "method": method, "message": "Notification sent successfully."}
                else:
                    results[method] = r.std_err.decode('utf-8', errors='ignore')
            elif method == "psexec":
                client = PsExecClient(req.ip_address, username=req.username, password=req.password)
                client.connect()
                try:
                    client.create_service()
                    stdout, stderr, rc = client.run_executable("powershell.exe", arguments=f"-WindowStyle Normal -NoProfile -EncodedCommand {encoded_cmd}", interactive=True)
                    if rc == 0:
                        return {"status": "success", "method": method, "message": "Notification sent successfully."}
                    else:
                        results[method] = stderr.decode('utf-8', errors='ignore') if stderr else f"Exit code {rc}"
                finally:
                    try:
                        client.remove_service()
                    except Exception:
                        pass
                    client.disconnect()
        except Exception as e:
            logger.error(f"Failed to send notification via {method} on {req.ip_address}: {e}")
            results[method] = str(e)

    raise HTTPException(status_code=500, detail={"message": "All attempted remote execution methods failed.", "errors": results})


pending_scan_triggers = set()


@router.post("/api/trigger-scan/{device_id}")
def trigger_immediate_scan(device_id: str):
    logger.info(f"Manual force-scan requested for device: {device_id}")
    clean_id = device_id.strip().lower()
    pending_scan_triggers.add(clean_id)
    pending_scan_triggers.add("ALL")
    return {
        "status": "triggered",
        "device_id": device_id,
        "message": f"Scan signal initiated for {device_id}. Target agent will execute scan immediately."
    }


@router.get("/api/check-trigger")
def check_trigger(device_name: str = Query(...)):
    triggered = False
    if pending_scan_triggers:
        triggered = True
        pending_scan_triggers.clear()
        logger.info(f"Trigger delivered to checking daemon: {device_name}")
    return {"trigger": triggered}
