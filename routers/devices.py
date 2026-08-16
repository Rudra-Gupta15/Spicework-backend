from fastapi import APIRouter, HTTPException

from backend import legacy_db

router = APIRouter()


@router.get("/api/software-inventory")
def list_software_inventory():
    """Estate-wide software list: one row per (application, version), aggregated across devices."""
    items = legacy_db.list_software_inventory()
    return {"software": items, "total": len(items)}


@router.get("/devices")
@router.get("/api/devices")
def list_audited_devices():
    devices = {}
    for row in legacy_db.list_audit_index():
        name = (row['computer_name'] or "Unknown").strip()
        os_name = (row['os_name'] or "Unknown").strip()

        # Categorize OS family to pair same OS versions (e.g. Windows 10 vs 11 or macOS vs macOS)
        os_lower = os_name.lower()
        if "windows" in os_lower:
            os_family = "windows"
        elif "mac" in os_lower:
            os_family = "mac"
        elif "ubuntu" in os_lower or "linux" in os_lower:
            os_family = "linux"
        else:
            os_family = os_lower

        key = (name.lower(), os_family)
        if key not in devices:
            user = row.get('current_username') or "Unknown"
            model_name = ""
            mfr = (row.get('manufacturer') or "").strip()
            mdl = (row.get('model') or "").strip()
            if mfr and mdl and mdl != "Unknown" and mdl != "N/A":
                if "ASUSTeK" in mfr or "ASUS" in mfr:
                    mfr = "ASUS"
                elif "Hewlett" in mfr or "HP" in mfr:
                    mfr = "HP"
                elif "Lenovo" in mfr:
                    mfr = "Lenovo"
                elif "Dell" in mfr:
                    mfr = "Dell"
                elif "Apple" in mfr:
                    mfr = "Apple"
                mdl_clean = mdl.split('_')[0].strip()
                # Reject disk/SSD model strings masquerading as laptop model names
                mdl_lower = mdl_clean.lower()
                is_disk_model = any(x in mdl_lower for x in [
                    'gb', 'tb', 'nvme', 'ssd', 'hdd', 'nand', 'sata', 'mzvl', 'kioxia',
                    'kingston', 'om8pcp', 'om8', 'samsung', 'wd', 'wdc', 'seagate',
                    'toshiba', 'micron', 'crucial', 'sandisk', 'evmnv', 'pm9', 'pm98',
                    'hynix', 'sk hynix', 'lexar', 'transcend', 'adata', 'sn5000', 'sn750', 'sn850',
                    '512', '256', '128', '1tb', '2tb', 'disk', 'drive', 'storage'
                ])
                if is_disk_model:
                    pass  # skip — leave model_name empty, fallback to computer_name
                elif mdl_clean.lower().startswith(mfr.lower()):
                    model_name = mdl_clean
                else:
                    model_name = f"{mfr} {mdl_clean}".strip()

            mac = row.get('mac_address')
            uid = mac if mac and mac != "Unknown" else name
            devices[key] = {
                "id": uid,
                "computer_name": name,
                "model_name": model_name or name,
                "os_name": os_name,
                "username": user,
                "last_seen": row.get('execution_datetime')
            }

    device_list = list(devices.values())
    device_list.sort(key=lambda x: x.get("last_seen") or "", reverse=True)
    return {"devices": device_list, "total": len(device_list)}


@router.get("/api/software/{device_id}")
def get_software_for_device(device_id: str):
    latest_data = legacy_db.get_latest_audit(device_id)

    if not latest_data:
        raise HTTPException(status_code=404, detail=f"No audit found for device: {device_id}")

    software_inventory = [
        {"name": s.get("application_name"), "version": s.get("version"),
         "publisher": s.get("publisher"), "install_date": s.get("install_date"), "size_mb": s.get("size_mb")}
        for s in latest_data.get("software", [])
    ]

    return {
        "id":                 device_id,
        "computer_name":      latest_data.get("computer_name") or "Unknown",
        "current_user":       latest_data.get("current_username") or "Unknown",
        "last_audit":         latest_data.get("execution_datetime"),
        "software_inventory": software_inventory,
        "total":              len(software_inventory),
        "os_name":            latest_data.get("os_name") or "",
        "os_version":         latest_data.get("os_version") or "",
        "os_build":           latest_data.get("os_build") or "",
        "last_boot":          latest_data.get("last_boot") or "",
        "uptime":             latest_data.get("uptime") or "",
        "architecture":       latest_data.get("architecture") or "",
        "license_status":     latest_data.get("license_status") or "",
        "firewall":           latest_data.get("firewall") or "Unknown",
        "bitlocker":          latest_data.get("bitlocker") or "Unknown",
        "secure_boot":        latest_data.get("secure_boot") or "Unknown",
        "tpm":                latest_data.get("tpm") or "Unknown",
        "hardware_details":   {k: latest_data.get(k) for k in
                                ("cpu", "ram", "disk", "serial_number", "manufacturer", "model")},
        "network_details":    latest_data.get("network_details", []),
        "user_accounts":      latest_data.get("user_accounts", []),
        "login_history":      latest_data.get("raw_login_history") or [],
        "hotfixes":           latest_data.get("hotfixes", []),
        "antivirus":          latest_data.get("antivirus", []),
        "gpus":               latest_data.get("gpus", []),
        "disk_partitions":    latest_data.get("disk_partitions", []),
        "peripherals":        latest_data.get("peripherals", []),
        "printers":           latest_data.get("printers", []),
        "network_adapters":   latest_data.get("network_adapters", []),
    }


@router.get("/api/device-diff/{device_id}")
def get_device_diff(device_id: str):
    """
    Compare the two most recent audit scans for a device.
    Returns: newly installed apps, removed apps, hardware changes.
    """
    scans_raw = legacy_db.get_last_two_audits(device_id)
    scans = [(a.get("execution_datetime") or a["created_at"].isoformat(), a) for a in scans_raw]

    if len(scans) < 2:
        return {
            "has_diff": False,
            "message": "Need at least 2 scans to generate a change report.",
            "scan_count": len(scans),
        }

    # Sort by datetime string ascending — latest last
    scans.sort(key=lambda x: x[0])
    prev_ts,  prev  = scans[-2]
    curr_ts,  curr  = scans[-1]

    # ── Software diff ─────────────────────────────────────────────────────────
    def sw_key(entry):
        """Unique key: lowercase name + version."""
        if isinstance(entry, dict):
            return f"{(entry.get('name') or '').strip().lower()}||{(entry.get('version') or '').strip()}"
        return ""

    prev_sw = {sw_key(s): s for s in prev.get("software_inventory", []) if sw_key(s)}
    curr_sw = {sw_key(s): s for s in curr.get("software_inventory", []) if sw_key(s)}

    installed_keys = set(curr_sw) - set(prev_sw)
    removed_keys   = set(prev_sw) - set(curr_sw)

    newly_installed = [curr_sw[k] for k in sorted(installed_keys)]
    newly_removed   = [prev_sw[k] for k in sorted(removed_keys)]

    # ── Hardware diff ─────────────────────────────────────────────────────────
    hw_changes = []
    hw_fields  = [
        ("cpu",           "Processor (CPU)"),
        ("ram",           "Memory (RAM)"),
        ("disk",          "Storage"),
        ("serial_number", "Serial Number"),
        ("manufacturer",  "Manufacturer"),
        ("model",         "Model"),
    ]

    for field, label in hw_fields:
        pv = str(prev.get(field) or "Unknown").strip()
        cv = str(curr.get(field) or "Unknown").strip()
        if pv != cv:
            hw_changes.append({"field": label, "previous": pv, "current": cv})

    # OS changes
    for field, label in [("os_name", "OS Name"), ("os_version", "OS Version"), ("architecture", "Architecture")]:
        pv = str(prev.get(field) or "Unknown").strip()
        cv = str(curr.get(field) or "Unknown").strip()
        if pv != cv:
            hw_changes.append({"field": label, "previous": pv, "current": cv})

    return {
        "has_diff":        True,
        "scan_count":      len(scans),
        "previous_scan":   prev_ts,
        "current_scan":    curr_ts,
        "newly_installed": newly_installed,
        "newly_removed":   newly_removed,
        "hw_changes":      hw_changes,
        "summary": {
            "installed_count": len(newly_installed),
            "removed_count":   len(newly_removed),
            "hw_change_count": len(hw_changes),
        }
    }
