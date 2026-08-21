from fastapi import APIRouter, HTTPException

from backend import legacy_db
from backend.services.common import execution_day, is_disk_model, is_identifiable_audit, resolve_machine_model

router = APIRouter()


@router.get("/api/software-inventory")
def list_software_inventory():
    """Estate-wide software list: one row per (application, version), aggregated across devices."""
    items = legacy_db.list_software_inventory()
    return {"software": items, "total": len(items)}


@router.get("/devices")
@router.get("/api/devices")
def list_audited_devices():
    # Keyed by the same id (mac, or computer name) the list below assigns as
    # "id" — one query up front rather than one per device, since the table
    # is small and every device is about to be looped over anyway.
    overrides_by_id = {row["device_id"]: row for row in legacy_db.list_asset_metadata()}
    devices = {}
    # Every day each device was ever audited, not just the day of its most
    # recent one. `list_audit_index()` returns one row per audit across all of
    # history, newest first, and the loop below only keeps the first (i.e.
    # latest) row per device for the fields that make sense as a single
    # snapshot — this collects the rest so a machine rescanned since a given
    # day does not erase that it was ever scanned on it.
    scan_days: dict = {}
    for row in legacy_db.list_audit_index():
        # Drop records with nothing identifying in them (empty probe/test posts),
        # which would otherwise render as a phantom "Unknown / Unknown" asset row.
        if not is_identifiable_audit(row):
            continue

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

        day = execution_day(row.get('execution_datetime'))
        if day:
            scan_days.setdefault(key, set()).add(day)

        if key not in devices:
            user = row.get('current_username') or "Unknown"

            # Computed early (normally built after the manufacturer/model
            # block below) because a correction, if one exists, has to reach
            # that block before it runs rather than patch its output — the
            # model-name logic needs the corrected manufacturer to decide
            # things like whether the model string already starts with it.
            mac = row.get('mac_address')
            uid = mac if mac and mac != "Unknown" else name
            overrides = overrides_by_id.get(uid) or {}

            def _corrected(raw_value, column):
                override = (overrides.get(column) or "").strip()
                return override or raw_value

            model_name = ""
            mfr = _corrected((row.get('manufacturer') or "").strip(), "manufacturer_override")
            mdl = _corrected((row.get('model') or "").strip(), "device_model_override")
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
                # Reject disk/SSD model strings masquerading as laptop model names.
                # When the reported model is a disk, the motherboard product is
                # the real machine model on OEM laptops (e.g. GA403UV), so prefer
                # that over falling all the way back to the computer name.
                if is_disk_model(mdl_clean):
                    board = (row.get('mobo_product') or "").strip()
                    mdl_clean = board if board and not is_disk_model(board) else ""
                if not mdl_clean:
                    pass  # leave model_name empty, fallback to computer_name
                elif mdl_clean.lower().startswith(mfr.lower()):
                    model_name = mdl_clean
                else:
                    model_name = f"{mfr} {mdl_clean}".strip()

            def _real(value, fallback=""):
                text = (value or "").strip()
                return fallback if text.lower() in ("", "unknown", "n/a") else text

            devices[key] = {
                "id": uid,
                "computer_name": name,
                "model_name": model_name or name,
                "os_name": os_name,
                "username": user,
                "last_seen": row.get('execution_datetime'),
                # The audit log does track these — the inventory table used to
                # hardcode them as "Unknown" simply because they were never sent.
                "serial_number": _real(_corrected(row.get('serial_number'), "serial_number_override")),
                "ip_address": _real(row.get('ip_address')),
                "device_type": _real(row.get('device_type')),
                "location": _real(row.get('location_info')),
            }

    for key, device in devices.items():
        device["scan_days"] = sorted(scan_days.get(key, ()), reverse=True)

    device_list = list(devices.values())
    device_list.sort(key=lambda x: x.get("last_seen") or "", reverse=True)
    return {"devices": device_list, "total": len(device_list)}


@router.get("/api/devices/{identifier}/scans")
def list_device_scan_history(identifier: str, limit: int = 50):
    """
    When this particular machine was scanned — one entry per audit it has
    filed, newest first.

    The device list collapses a machine's audits into one row per (name, OS
    family), so a dual-booted box shows twice and every earlier scan is hidden
    behind whichever was latest. This is the trail behind that row.

    `identifier` is the computer name or MAC address. `total` is the full count
    even when the returned page is capped — a machine that has reported for
    months has hundreds.
    """
    limit = max(1, min(limit, 200))
    result = legacy_db.list_device_scans(identifier, limit)

    if result["total"] == 0:
        raise HTTPException(status_code=404, detail=f"No scans recorded for '{identifier}'.")

    return {
        "device": identifier,
        "total": result["total"],
        "returned": len(result["scans"]),
        "scans": result["scans"],
    }


# A field left blank here means "nothing to correct" — the scanned value
# stands. Maps a Hardware Specification field to the asset_metadata column
# holding its correction, so both places that build hardware_details
# (this endpoint and the device list below) apply it identically.
_HARDWARE_OVERRIDE_COLUMNS = {
    "cpu": "cpu_override",
    "ram": "ram_override",
    "disk": "disk_override",
    "serial_number": "serial_number_override",
    "manufacturer": "manufacturer_override",
    "model": "device_model_override",
}


def _with_hardware_overrides(hardware_details: dict, device_id: str) -> dict:
    """
    A human correction of a Hardware Specification field, laid over what the
    agent read — the same precedence `asset_tag`/`location_info` already use
    against `asset_metadata`, extended to the fields Hardware Specification
    shows. Applied here rather than in the frontend so every reader of this
    data (the web app today, anything else tomorrow) sees the same corrected
    value with no merging logic of its own.
    """
    metadata = legacy_db.get_asset_metadata(device_id)
    if not metadata:
        return hardware_details

    corrected = dict(hardware_details)
    for field, column in _HARDWARE_OVERRIDE_COLUMNS.items():
        override = (metadata.get(column) or "").strip()
        if override:
            corrected[field] = override
    return corrected


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
        "hardware_details":   _with_hardware_overrides({
            **{k: latest_data.get(k) for k in
               ("cpu", "ram", "disk", "serial_number", "manufacturer")},
            # Audits collected before the agent's $model clobber was fixed stored a
            # disk product name here; repair it on read so historical rows render.
            "model": resolve_machine_model(latest_data.get("model"),
                                           latest_data.get("mobo_product"),
                                           latest_data.get("computer_name")),
        }, device_id),
        "asset_tag":          latest_data.get("asset_tag") or "",
        "location_info":      latest_data.get("location_info") or "",
        "device_type":        latest_data.get("device_type") or "",
        "life_cycle":         latest_data.get("life_cycle") or "",
        "domain":             latest_data.get("domain") or "",
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
