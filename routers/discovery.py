import concurrent.futures
import ipaddress
import json
import platform
import socket
import subprocess

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from backend.core.config import logger
from backend.models.discovery import NetworkScanRequest
from backend.services.audit_queries import get_audit_indexes
from backend.services.mac_vendor import mac_vendor_dict
from backend.services.network_utils import _run_cmd, enrich_scan_results, resolve_hostname_netbios

router = APIRouter()


@router.post("/discover/network-scan")
def network_scan(request: NetworkScanRequest):
    try:
        raw_range = request.ip_range.strip()
        hosts = []
        if '-' in raw_range:
            parts = [p.strip() for p in raw_range.split('-')]
            start_ip = ipaddress.IPv4Address(parts[0])
            if '.' in parts[1]:
                end_ip = ipaddress.IPv4Address(parts[1])
            else:
                prefix = str(parts[0]).rsplit('.', 1)[0]
                end_ip = ipaddress.IPv4Address(f"{prefix}.{parts[1]}")

            start_int = int(start_ip)
            end_int = int(end_ip)
            if end_int < start_int:
                start_int, end_int = end_int, start_int
            if (end_int - start_int + 1) > 512:
                raise HTTPException(status_code=400, detail="IP range too large. Maximum 512 hosts permitted.")
            hosts = [ipaddress.IPv4Address(ip) for ip in range(start_int, end_int + 1)]
            network = ipaddress.ip_network(f"{start_ip}/24", strict=False)
        else:
            network = ipaddress.ip_network(raw_range, strict=False)
            hosts = list(network.hosts())
            if not hosts:
                hosts = [network.network_address]
            if len(hosts) > 512:
                raise HTTPException(status_code=400, detail="IP range too large. Use /23 or smaller.")

        start_host = str(hosts[0])
        end_host = str(hosts[-1])
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid IP range: {e}")

    common_ports  = [22, 23, 80, 135, 161, 443, 445, 3389, 8080, 8443, 9100]
    timeout_secs  = max(0.1, min(request.timeout_ms / 1000, 2.0))

    PORT_LABELS = {
        22: "SSH", 23: "Telnet (SNMP)", 80: "HTTP", 135: "RPC",
        161: "SNMP (UDP/Network)",
        443: "HTTPS", 445: "SMB", 3389: "RDP",
        8080: "HTTP-Alt", 8443: "HTTPS-Alt", 9100: "Printer/RAW"
    }

    def check_snmp(ip_str):
        pkt = b'\x30\x29\x02\x01\x00\x04\x06public\xa0\x1c\x02\x04\x00\x00\x00\x01\x02\x01\x00\x02\x01\x00\x30\x0e\x30\x0c\x06\x08\x2b\x06\x01\x02\x01\x01\x01\x00\x05\x00'
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.settimeout(min(timeout_secs, 0.8))
            s.sendto(pkt, (ip_str, 161))
            data, _ = s.recvfrom(1024)
            s.close()
            return bool(data)
        except Exception:
            return False

    def guess_device_type(open_ports):
        if 3389 in open_ports and 445 in open_ports:
            return "Windows Workstation/Server"
        if 445 in open_ports and 135 in open_ports:
            return "Windows Host"
        if 22 in open_ports and 80 not in open_ports and 443 not in open_ports:
            return "Linux/Unix Server"
        if 9100 in open_ports:
            return "Network Printer (SNMP)"
        if 23 in open_ports or 161 in open_ports:
            return "Network Device / Switch / Router (SNMP)"
        if 80 in open_ports or 443 in open_ports:
            return "Web Service / Network Device"
        return "Unknown Device"

    def scan_host(ip):
        ip_str     = str(ip)
        open_ports = []
        hostname   = ip_str

        try:
            hostname = socket.getfqdn(ip_str)
        except Exception:
            pass

        for port in common_ports:
            if port == 161:
                if check_snmp(ip_str):
                    open_ports.append(161)
                continue
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(timeout_secs)
                if sock.connect_ex((ip_str, port)) == 0:
                    open_ports.append(port)
                sock.close()
            except Exception:
                pass

        if open_ports:
            port_labels = [f"{p} ({PORT_LABELS.get(p, 'Unknown')})" for p in open_ports]
            return {
                "ip":          ip_str,
                "hostname":    hostname if hostname != ip_str else "N/A",
                "open_ports":  open_ports,
                "port_labels": port_labels,
                "device_type": guess_device_type(open_ports),
                "status":      "online",
            }
        return None

    logger.info(f"Starting network scan: {request.ip_range}")

    # ─────────────────────────────────────────────────────────────────────────
    # Step 1: Fast ICMP Ping Sweep — populates ARP cache for ALL live devices
    # including mobiles and firewalled laptops that block TCP ports.
    # ─────────────────────────────────────────────────────────────────────────
    def ping_host(ip_str: str):
        try:
            subprocess.run(
                ["ping", "-n", "1", "-w", "500", str(ip_str)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=1
            )
        except Exception:
            pass

    logger.info("Running ping sweep to populate ARP cache...")
    with concurrent.futures.ThreadPoolExecutor(max_workers=128) as executor:
        executor.map(ping_host, [str(h) for h in hosts])

    # ─────────────────────────────────────────────────────────────────────────
    # Step 2: Port Scan — identifies Windows/Linux/printer devices by open ports
    # ─────────────────────────────────────────────────────────────────────────
    with concurrent.futures.ThreadPoolExecutor(max_workers=64) as executor:
        results = list(executor.map(scan_host, hosts))

    discovered_dict = {r["ip"]: r for r in results if r is not None}


    # ────────────────────────────────────────────────────────────────────────────
    # ARP Fallback: Discover mobile phones and firewalled devices
    # ────────────────────────────────────────────────────────────────────────────
    try:
        broadcast_ip  = str(network.broadcast_address)
        network_ip    = str(network.network_address)
        BROADCAST_MACS = {"ff-ff-ff-ff-ff-ff", "ff:ff:ff:ff:ff:ff", "00-00-00-00-00-00"}

        arp_out, _ = _run_cmd("arp -a")
        for line in arp_out.splitlines():
            line = line.strip()
            if not line:
                continue
            parts = line.split()
            if len(parts) < 3:
                continue
            entry_type = parts[2].lower() if len(parts) >= 3 else ""
            if entry_type not in ("dynamic", "static"):
                continue
            ip_str  = parts[0]
            mac_str = parts[1].lower()

            # Skip broadcast, network, and invalid MACs
            if ip_str in (broadcast_ip, network_ip):
                continue
            if mac_str in BROADCAST_MACS:
                continue

            try:
                if ipaddress.IPv4Address(ip_str) not in network:
                    continue
                if ip_str in discovered_dict:
                    continue

                hostname = ip_str
                try:
                    resolved = socket.getfqdn(ip_str)
                    if resolved != ip_str:
                        hostname = resolved
                except Exception:
                    pass

                # Guess device type by hostname pattern
                h_lower = hostname.lower()
                if any(x in h_lower for x in ["desktop", "laptop", "pc", "workstation", "win"]):
                    dev_type = "Windows Host (Firewalled)"
                elif any(x in h_lower for x in ["android", "iphone", "ipad", "samsung", "pixel"]):
                    dev_type = "Mobile Device"
                else:
                    try:
                        prefix = mac_str.replace(":", "").replace("-", "").upper()[:6]
                        if prefix in mac_vendor_dict:
                            vendor = mac_vendor_dict[prefix]
                            vendor = vendor.replace(" Inc.", "").replace(" Ltd.", "").replace(" Co.", "").replace(", Inc.", "").replace(" Corporation", "")
                            if len(vendor) > 20:
                                vendor = vendor[:20].strip() + "..."
                            dev_type = f"{vendor} Device"
                        else:
                            dev_type = "Unknown Device (Firewalled)"
                    except Exception:
                        dev_type = "Unknown Device (Firewalled)"

                discovered_dict[ip_str] = {
                    "ip":          ip_str,
                    "hostname":    hostname if hostname != ip_str else "N/A",
                    "open_ports":  [],
                    "port_labels": [f"MAC: {mac_str}"],
                    "device_type": dev_type,
                    "status":      "online"
                }
            except Exception:
                pass
    except Exception as e:
        logger.error(f"ARP scan fallback failed: {e}")


    discovered = list(discovered_dict.values())
    logger.info(f"Scan complete: {len(discovered)} hosts found of {len(hosts)} scanned")
    return enrich_scan_results({
        "discovered":       discovered,
        "total":            len(discovered),
        "scanned":          len(hosts),
        "ip_range":         request.ip_range,
        "start_ip":         start_host,
        "end_ip":           end_host,
        "ip_subnet_range":  f"{start_host} – {end_host}"
    })


@router.post("/discover/network-scan-stream")
def network_scan_stream(request: NetworkScanRequest):
    """Real-time streaming network scanner — yields discovered devices immediately as SSE events."""
    # Deferred import: routers.wifi imports network_scan from this module at
    # top level, so this stays a lazy import here to avoid a circular import.
    from backend.routers.wifi import get_current_wifi

    def event_generator():
        try:
            raw_range = request.ip_range.strip()
            if '-' in raw_range:
                parts = [p.strip() for p in raw_range.split('-')]
                start_ip = ipaddress.IPv4Address(parts[0])
                end_ip = ipaddress.IPv4Address(parts[1] if '.' in parts[1] else f"{str(parts[0]).rsplit('.', 1)[0]}.{parts[1]}")
                start_int, end_int = int(start_ip), int(end_ip)
                if end_int < start_int: start_int, end_int = end_int, start_int
                hosts = [ipaddress.IPv4Address(ip) for ip in range(start_int, end_int + 1)]
                network = ipaddress.ip_network(f"{start_ip}/24", strict=False)
            else:
                network = ipaddress.ip_network(raw_range, strict=False)
                hosts = list(network.hosts()) or [network.network_address]
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'detail': str(e)})}\n\n"
            return

        common_ports  = [22, 23, 80, 135, 161, 443, 445, 3389, 8080, 8443, 9100]
        timeout_secs  = max(0.1, min(request.timeout_ms / 1000, 2.0))

        PORT_LABELS = {
            22: "SSH", 23: "Telnet (SNMP)", 80: "HTTP", 135: "RPC",
            161: "SNMP (UDP/Network)",
            443: "HTTPS", 445: "SMB", 3389: "RDP",
            8080: "HTTP-Alt", 8443: "HTTPS-Alt", 9100: "Printer/RAW"
        }

        def check_snmp_stream(ip_str):
            pkt = b'\x30\x29\x02\x01\x00\x04\x06public\xa0\x1c\x02\x04\x00\x00\x00\x01\x02\x01\x00\x02\x01\x00\x30\x0e\x30\x0c\x06\x08\x2b\x06\x01\x02\x01\x01\x01\x00\x05\x00'
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                s.settimeout(min(timeout_secs, 0.8))
                s.sendto(pkt, (ip_str, 161))
                data, _ = s.recvfrom(1024)
                s.close()
                return bool(data)
            except Exception:
                return False

        def guess_device_type(open_ports):
            if 3389 in open_ports and 445 in open_ports: return "Windows Workstation/Server"
            if 445 in open_ports and 135 in open_ports: return "Windows Host"
            if 22 in open_ports and 80 not in open_ports and 443 not in open_ports: return "Linux/Unix Server"
            if 9100 in open_ports: return "Network Printer (SNMP)"
            if 23 in open_ports or 161 in open_ports: return "Network Device / Switch / Router (SNMP)"
            if 80 in open_ports or 443 in open_ports: return "Web Service / Network Device"
            return "Unknown Device"

        audit_index, audit_mac_index = get_audit_indexes()
        curr_wifi = get_current_wifi()
        base_dist_m = curr_wifi.get("distance_m") or 6.1

        def calculate_device_distance(ip_str: str) -> str:
            if not ip_str:
                return "~5.0 meters"
            parts = ip_str.split(".")
            last_num = int(parts[-1]) if len(parts) == 4 and parts[-1].isdigit() else 10

            if last_num in (1, 254):
                return f"~{base_dist_m} meters (Wi-Fi AP)"

            if curr_wifi.get("ip") and ip_str == curr_wifi.get("ip"):
                return f"~{base_dist_m} meters"

            offset = round(((last_num % 7) * 0.7) - 0.8, 1)
            d = round(base_dist_m + offset, 1)
            if d < 0.5:
                d = 0.5
            return f"~{d} meters"

        def enrich_dev(device):
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
                device["id"]                 = a["id"]
                device["computer_name"]      = a["computer_name"]
                device["os_name"]            = a["os_name"]
                device["username"]           = a["username"]
                device["last_audit"]         = a["last_audit"]
                device["audit_status"]       = "audited"
                device["estimated_distance"] = calculate_device_distance(ip)
            else:
                nb_h = resolve_hostname_netbios(ip)
                if nb_h:
                    device["computer_name"] = nb_h
                else:
                    dev_t = device.get("device_type", "Network Device")
                    clean_t = dev_t.replace(" Device", "").replace(" (Firewalled)", "").replace(" Workstation/Server", "").strip()
                    last_octet = ip.split(".")[-1] if "." in ip else "Device"
                    device["computer_name"] = f"{clean_t} ({last_octet})" if clean_t and clean_t != "Unknown" else f"Host-{last_octet}"
                device["os_name"]            = device.get("device_type", "Network Target")
                device["username"]           = "Unaudited Target"
                device["last_audit"]         = "—"
                device["audit_status"]       = "unaudited"
                device["estimated_distance"] = calculate_device_distance(ip)
            return device

        discovered_set = set()

        # Step 1: Fast ICMP Ping Sweep (Cross-Platform)
        def ping_host(ip_str: str):
            try:
                if platform.system() == "Windows":
                    cmd = ["ping", "-n", "1", "-w", "300", ip_str]
                else:
                    cmd = ["ping", "-c", "1", "-W", "1", ip_str]
                subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=1.0, shell=False)
            except Exception:
                pass

        with concurrent.futures.ThreadPoolExecutor(max_workers=32) as executor:
            executor.map(ping_host, [str(h) for h in hosts])

        # Step 2: Parallel Port Scan & Stream Discovered Devices as they Pop Up!
        def scan_and_yield(ip):
            ip_str = str(ip)
            open_ports = []
            for port in common_ports:
                if port == 161:
                    if check_snmp_stream(ip_str):
                        open_ports.append(161)
                    continue
                try:
                    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    sock.settimeout(timeout_secs)
                    if sock.connect_ex((ip_str, port)) == 0:
                        open_ports.append(port)
                    sock.close()
                except Exception:
                    pass
            if open_ports:
                dev = {
                    "ip":          ip_str,
                    "hostname":    "N/A",
                    "open_ports":  open_ports,
                    "port_labels": [f"{p} ({PORT_LABELS.get(p, 'Unknown')})" for p in open_ports],
                    "device_type": guess_device_type(open_ports),
                    "status":      "online",
                }
                return enrich_dev(dev)
            return None

        with concurrent.futures.ThreadPoolExecutor(max_workers=16) as executor:
            futures = {executor.submit(scan_and_yield, h): h for h in hosts}
            for future in concurrent.futures.as_completed(futures):
                res = future.result()
                if res and res["ip"] not in discovered_set:
                    discovered_set.add(res["ip"])
                    yield f"data: {json.dumps({'type': 'device', 'device': res})}\n\n"

        # Step 3: ARP Fallback for mobile / firewalled devices & Stream them!
        try:
            broadcast_ip  = str(network.broadcast_address)
            network_ip    = str(network.network_address)
            BROADCAST_MACS = {"ff-ff-ff-ff-ff-ff", "ff:ff:ff:ff:ff:ff", "00-00-00-00-00-00"}
            arp_out, _ = _run_cmd("arp -a")
            for line in arp_out.splitlines():
                parts = line.strip().split()
                if len(parts) >= 3 and parts[2].lower() in ("dynamic", "static"):
                    ip_str, mac_str = parts[0], parts[1].lower()
                    if ip_str not in (broadcast_ip, network_ip) and mac_str not in BROADCAST_MACS:
                        try:
                            if ipaddress.IPv4Address(ip_str) in network and ip_str not in discovered_set:
                                discovered_set.add(ip_str)
                                prefix = mac_str.replace(":", "").replace("-", "").upper()[:6]
                                vendor = mac_vendor_dict.get(prefix, "")
                                dev_type = f"{vendor} Device" if vendor else "Network Device (Firewalled)"
                                dev = {
                                    "ip":          ip_str,
                                    "hostname":    "N/A",
                                    "open_ports":  [],
                                    "port_labels": [f"MAC: {mac_str}"],
                                    "device_type": dev_type,
                                    "status":      "online"
                                }
                                yield f"data: {json.dumps({'type': 'device', 'device': enrich_dev(dev)})}\n\n"
                        except Exception:
                            pass
        except Exception:
            pass

        yield f"data: {json.dumps({'type': 'complete', 'total': len(discovered_set), 'scanned': len(hosts)})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")
