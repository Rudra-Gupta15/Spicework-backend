import concurrent.futures
import platform
import socket
import subprocess

from backend.core.config import logger


def _is_windows() -> bool:
    return platform.system() == "Windows"


def _run_cmd(cmd: str):
    """Run a shell command and return (stdout, returncode)."""
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=20, shell=True)
        return r.stdout, r.returncode
    except Exception as e:
        return str(e), -1


def _run_cmd_args(args: list):
    """Run a command using an argument list without shell=True for security."""
    try:
        r = subprocess.run(args, capture_output=True, text=True, timeout=20, shell=False)
        return r.stdout, r.returncode
    except Exception as e:
        return str(e), -1


def calculate_wifi_distance(signal_percent: int = 0, rssi_dbm: int = None) -> dict:
    """Calculate estimated router distance in meters using RSSI log-distance path loss model."""
    if rssi_dbm is None:
        if signal_percent <= 0:
            return {"distance_m": None, "distance_str": "Unknown"}
        rssi_dbm = int((signal_percent / 2.0) - 100.0)

    # Reference power at 1m: -40 dBm, Path loss exponent n = 2.8 (indoor)
    tx_power_1m = -40.0
    n = 2.8
    exp = (tx_power_1m - float(rssi_dbm)) / (10.0 * n)
    distance_m = round(10.0 ** exp, 1)

    if distance_m < 0.3:
        distance_m = 0.3

    return {
        "rssi_dbm": int(rssi_dbm),
        "distance_m": distance_m,
        "distance_str": f"~{distance_m} meters" if distance_m < 10 else f"~{int(distance_m)} meters"
    }


def resolve_hostname_netbios(ip_str: str) -> str:
    """Attempt Reverse DNS or NetBIOS nbtstat to find real hostname."""
    try:
        name, _, _ = socket.gethostbyaddr(ip_str)
        if name and name != ip_str and not name.startswith("192."):
            return name.split(".")[0].upper()
    except Exception:
        pass

    if _is_windows():
        try:
            out, rc = _run_cmd(f"nbtstat -A {ip_str}")
            if rc == 0 and out:
                for line in out.splitlines():
                    if "<00>" in line and "UNIQUE" in line:
                        nb_name = line.split()[0].strip()
                        if nb_name and not nb_name.startswith("__"):
                            return nb_name.upper()
        except Exception:
            pass

    return None


def enrich_scan_results(scan_result: dict) -> dict:
    from backend import legacy_db

    try:
        audit_index, audit_mac_index = legacy_db.get_audit_enrichment_indexes()
    except Exception as db_e:
        logger.warning(f"Could not load audits from DB for scan enrichment: {db_e}")
        audit_index, audit_mac_index = {}, {}

    # 2. Enrich discovered devices (Parallel NetBIOS/DNS resolution for fast 2-second completion)
    unaudited_devices = []
    for device in scan_result.get("discovered", []):
        ip = device.get("ip", "")

        scan_mac = None
        for p in device.get("port_labels", []):
            p_str = str(p)
            if p_str.startswith("MAC: "):
                scan_mac = p_str[5:].replace(":", "").replace("-", "").strip().upper()
                break

        a = audit_mac_index.get(scan_mac) if scan_mac else None
        if not a:
            a = audit_index.get(ip)

        if a:
            device["id"]            = a["id"]
            device["computer_name"] = a["computer_name"]
            device["os_name"]       = a["os_name"]
            device["username"]      = a["username"]
            device["last_audit"]    = a["last_audit"]
            device["audit_status"]  = "audited"
        else:
            unaudited_devices.append(device)

    def _resolve_device_name(device):
        ip = device.get("ip", "")
        raw_h = device.get("hostname")
        if not raw_h or raw_h in ("N/A", ip):
            nb_h = resolve_hostname_netbios(ip)
            if nb_h:
                device["computer_name"] = nb_h
            else:
                dev_t = device.get("device_type", "Network Device")
                clean_t = dev_t.replace(" Device", "").replace(" (Firewalled)", "").replace(" Workstation/Server", "").strip()
                last_octet = ip.split(".")[-1] if "." in ip else "Device"
                device["computer_name"] = f"{clean_t} ({last_octet})" if clean_t and clean_t != "Unknown" else f"Host-{last_octet}"
        else:
            device["computer_name"] = raw_h

        device["os_name"]       = device.get("device_type", "Network Target")
        device["username"]      = "Unaudited Target"
        device["last_audit"]    = "—"
        device["audit_status"]  = "unaudited"

    if unaudited_devices:
        with concurrent.futures.ThreadPoolExecutor(max_workers=32) as executor:
            list(executor.map(_resolve_device_name, unaudited_devices))

    return scan_result
