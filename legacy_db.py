"""
Relational Postgres storage for the legacy/single-tenant feature set that used
to live in SQLite (audits.db) or flat JSON files: audit ingestion + reports,
asset metadata, saved WiFi credentials, and asset lifecycle/tickets.

Lives in the same "sw inventory" database as auth_db.py/devices_db.py, but
each audit is normalized across legacy_audits + one child table per repeating
group (software, hotfixes, printers, gpus, network adapters, disk partitions,
peripherals, user accounts, antivirus, compression utilities, network
details) instead of one row with a giant JSON blob column.
"""
from backend.auth_db import _dict_cursor, get_inventory_db


# ── Audit Ingestion ──────────────────────────────────────────────────────────

_AUDIT_TOP_LEVEL_FIELDS = [
    "mac_address", "computer_name", "os_name", "os_version", "os_build", "architecture",
    "domain", "domain_role", "license_status", "firewall", "bitlocker", "secure_boot", "tpm",
    "drive_name", "description", "last_boot", "uptime", "shutdown_time", "last_backup",
    "life_cycle", "consent", "execution_datetime",
]


def _model_dict(item):
    if hasattr(item, "model_dump"):
        return item.model_dump()
    if hasattr(item, "dict"):
        return item.dict()
    return item


def save_audit(data, client_id: str = None, organization_id: str = None, pdf_path: str = None,
                xml_path: str = None, created_at: str = None) -> dict:
    """
    Normalize one `AuditData` payload across legacy_audits + its child tables,
    in a single transaction. Returns {"id": <uuid>}.
    """
    hw = _model_dict(data.hardware_details) if data.hardware_details else {}
    if not isinstance(hw, dict):
        hw = {}

    with get_inventory_db() as conn:
        cur = _dict_cursor(conn)
        try:
            cols = ["client_id", "organization_id", "current_username", "cpu", "ram", "disk",
                    "serial_number", "manufacturer", "model", "mobo_manufacturer", "mobo_product",
                    "bios_version", "bios_date", "battery_health", "cycle_count", "charge_percent",
                    "raw_login_history", "raw_usb_history", "pdf_path", "xml_path"]
            vals = [client_id, organization_id, data.current_user,
                    hw.get("cpu"), hw.get("ram"), hw.get("disk"),
                    hw.get("serial_number"), hw.get("manufacturer"), hw.get("model"),
                    hw.get("mobo_manufacturer"), hw.get("mobo_product"),
                    hw.get("bios_version"), hw.get("bios_date"),
                    hw.get("battery_health"), hw.get("cycle_count"), hw.get("charge_percent")]
            import psycopg2.extras
            vals += [psycopg2.extras.Json(data.login_history or []),
                     psycopg2.extras.Json(data.usb_history or []),
                     pdf_path, xml_path]

            for f in _AUDIT_TOP_LEVEL_FIELDS:
                cols.append(f)
                vals.append(getattr(data, f))

            if created_at:
                cols.append("created_at")
                vals.append(created_at)

            placeholders = ", ".join(["%s"] * len(vals))
            col_list = ", ".join(cols)
            cur.execute(f"INSERT INTO legacy_audits ({col_list}) VALUES ({placeholders}) RETURNING id", vals)
            audit_id = cur.fetchone()["id"]

            def insert_many(table, columns, rows):
                if not rows:
                    return
                col_str = ", ".join(columns)
                ph = ", ".join(["%s"] * (len(columns) + 1))
                for r in rows:
                    cur.execute(f"INSERT INTO {table} (audit_id, {col_str}) VALUES ({ph})", [audit_id] + r)

            insert_many("legacy_audit_software",
                        ["application_name", "version", "publisher", "install_date", "size_mb"],
                        [[d.get("name"), d.get("version"), d.get("publisher"), d.get("install_date"), d.get("size_mb")]
                         for d in (_model_dict(s) for s in (data.software_inventory or []))])

            insert_many("legacy_audit_hotfixes",
                        ["caption", "cs_name", "description", "fix_id", "installed_on"],
                        [[d.get("caption"), d.get("cs_name"), d.get("description"), d.get("fix_id"), d.get("installed_on")]
                         if isinstance(d, dict) else [None, None, None, str(d), None]
                         for d in (_model_dict(h) for h in (data.hotfixes or []))])

            insert_many("legacy_audit_printers",
                        ["name", "system_name", "enable_bidi", "extended_printer_status", "port_name"],
                        [[d.get("name"), d.get("system_name"), d.get("enable_bidi"), d.get("extended_printer_status"), d.get("port_name")]
                         if isinstance(d, dict) else [str(d), None, None, None, None]
                         for d in (_model_dict(p) for p in (data.printers or []))])

            gpu_list = hw.get("gpu_details") or []
            insert_many("legacy_audit_gpus",
                        ["name", "driver_version", "vram"],
                        [[d.get("name"), d.get("driver_version"), d.get("vram")]
                         for d in (_model_dict(g) for g in gpu_list)])

            na_list = hw.get("network_adapters") or []
            insert_many("legacy_audit_network_adapters",
                        ["name", "adapter_type", "speed", "mac_address", "ipv4", "ipv6", "gateway", "subnet_mask", "dns_servers"],
                        [[d.get("name"), d.get("adapter_type"), d.get("speed"), d.get("mac_address"),
                          d.get("ipv4"), d.get("ipv6"), d.get("gateway"), d.get("subnet_mask"), d.get("dns_servers")]
                         for d in (_model_dict(a) for a in na_list)])

            dp_list = hw.get("disk_partitions") or []
            insert_many("legacy_audit_disk_partitions",
                        ["name", "type", "size_gb", "free_gb", "bootable", "health", "ssd_hdd"],
                        [[d.get("name"), d.get("type"), d.get("size_gb"), d.get("free_gb"), d.get("bootable"), d.get("health"), d.get("ssd_hdd")]
                         for d in (_model_dict(p) for p in dp_list)])

            peri_list = hw.get("peripherals") or []
            insert_many("legacy_audit_peripherals",
                        ["name", "type", "status"],
                        [[d.get("name"), d.get("type"), d.get("status")]
                         for d in (_model_dict(p) for p in peri_list)])

            insert_many("legacy_audit_user_accounts",
                        ["username", "disabled", "home_directory", "last_login", "user_type"],
                        [[d.get("name"), d.get("disabled"), d.get("home_directory"), d.get("last_login"), d.get("user_type")]
                         if isinstance(d, dict) else [str(d), None, None, None, None]
                         for d in (_model_dict(u) for u in (data.user_accounts or []))])

            insert_many("legacy_audit_antivirus", ["name"], [[a] for a in (data.antivirus or [])])
            insert_many("legacy_audit_compression_utilities", ["name"], [[c] for c in (data.compression_utilities or [])])

            insert_many("legacy_audit_network_details",
                        ["ip_address", "gateway", "mac"],
                        [[d.get("ip_address"), d.get("gateway"), d.get("mac")]
                         if isinstance(d, dict) else [None, None, None]
                         for d in (_model_dict(n) for n in (data.network_details or []))])

            conn.commit()
            return {"id": str(audit_id)}
        except Exception:
            conn.rollback()
            raise


def update_audit_report_paths(audit_id: str, pdf_path: str, xml_path: str):
    with get_inventory_db() as conn:
        cur = conn.cursor()
        cur.execute("UPDATE legacy_audits SET pdf_path = %s, xml_path = %s WHERE id = %s", (pdf_path, xml_path, audit_id))
        conn.commit()


def _fetch_children(cur, audit_id, table, columns):
    col_str = ", ".join(columns)
    cur.execute(f"SELECT {col_str} FROM {table} WHERE audit_id = %s", (audit_id,))
    return [dict(r) for r in cur.fetchall()]


def get_latest_audit(identifier: str):
    """Latest audit matching mac_address or computer_name (case-insensitive), with all children."""
    with get_inventory_db() as conn:
        cur = _dict_cursor(conn)
        cur.execute("""
            SELECT * FROM legacy_audits
            WHERE LOWER(mac_address) = LOWER(%s) OR LOWER(computer_name) = LOWER(%s)
            ORDER BY created_at DESC LIMIT 1
        """, (identifier, identifier))
        row = cur.fetchone()
        if not row:
            return None
        audit = dict(row)
        audit_id = audit["id"]
        audit["software"] = _fetch_children(cur, audit_id, "legacy_audit_software",
            ["application_name", "version", "publisher", "install_date", "size_mb"])
        audit["hotfixes"] = _fetch_children(cur, audit_id, "legacy_audit_hotfixes",
            ["caption", "cs_name", "description", "fix_id", "installed_on"])
        audit["printers"] = _fetch_children(cur, audit_id, "legacy_audit_printers",
            ["name", "system_name", "enable_bidi", "extended_printer_status", "port_name"])
        audit["gpus"] = _fetch_children(cur, audit_id, "legacy_audit_gpus", ["name", "driver_version", "vram"])
        audit["network_adapters"] = _fetch_children(cur, audit_id, "legacy_audit_network_adapters",
            ["name", "adapter_type", "speed", "mac_address", "ipv4", "ipv6", "gateway", "subnet_mask", "dns_servers"])
        audit["disk_partitions"] = _fetch_children(cur, audit_id, "legacy_audit_disk_partitions",
            ["name", "type", "size_gb", "free_gb", "bootable", "health", "ssd_hdd"])
        audit["peripherals"] = _fetch_children(cur, audit_id, "legacy_audit_peripherals", ["name", "type", "status"])
        audit["user_accounts"] = _fetch_children(cur, audit_id, "legacy_audit_user_accounts",
            ["username", "disabled", "home_directory", "last_login", "user_type"])
        audit["antivirus"] = [r["name"] for r in _fetch_children(cur, audit_id, "legacy_audit_antivirus", ["name"])]
        audit["compression_utilities"] = [r["name"] for r in _fetch_children(cur, audit_id, "legacy_audit_compression_utilities", ["name"])]
        audit["network_details"] = _fetch_children(cur, audit_id, "legacy_audit_network_details", ["ip_address", "gateway", "mac"])
        return audit


def get_last_two_audits(identifier: str):
    """Last two audits for a device, each with software normalized to {name, version}."""
    with get_inventory_db() as conn:
        cur = _dict_cursor(conn)
        cur.execute("""
            SELECT id FROM legacy_audits
            WHERE LOWER(mac_address) = LOWER(%s) OR LOWER(computer_name) = LOWER(%s)
            ORDER BY created_at DESC LIMIT 2
        """, (identifier, identifier))
        ids = [r["id"] for r in cur.fetchall()]

    audits = []
    for aid in ids:
        with get_inventory_db() as conn:
            cur = _dict_cursor(conn)
            cur.execute("SELECT * FROM legacy_audits WHERE id = %s", (aid,))
            audit = dict(cur.fetchone())
            cur.execute("SELECT application_name, version FROM legacy_audit_software WHERE audit_id = %s", (aid,))
            audit["software_inventory"] = [{"name": r["application_name"], "version": r["version"]} for r in cur.fetchall()]
        audits.append(audit)
    return audits


def list_audit_index():
    """One row per audit with fields devices.py needs for its dedupe/list logic."""
    with get_inventory_db() as conn:
        cur = _dict_cursor(conn)
        cur.execute("""
            SELECT id, client_id, mac_address, computer_name, os_name, manufacturer, model,
                   current_username, execution_datetime, created_at
            FROM legacy_audits ORDER BY created_at DESC
        """)
        return [dict(r) for r in cur.fetchall()]


def count_devices() -> int:
    """
    Distinct physical devices in the audit log, deduped by computer name
    alone. Deliberately looser than the Hardware/Software page list (which
    keys on name + OS family, so a dual-booted machine shows as two
    browsable rows) — a dual-boot box reporting Windows under one MAC and
    Linux under another is still one machine for a headline device count.
    """
    audits = list_audit_index()
    names = {
        (a.get("computer_name") or a.get("mac_address") or "Unknown").strip().lower()
        for a in audits
    }
    return len(names)


def list_recent_audits(limit: int = 5) -> list:
    """Most recently audited devices (deduped, one row per real device) for
    the Dashboard's 'Recent Device Audits' card — every field below is shown
    exactly as the scan reported it, nothing derived or scored."""
    with get_inventory_db() as conn:
        cur = _dict_cursor(conn)
        cur.execute("""
            SELECT la.id, la.mac_address, la.computer_name, la.os_name, la.os_version,
                   la.execution_datetime, la.created_at, la.current_username,
                   la.firewall, la.license_status,
                   (SELECT ip_address FROM legacy_audit_network_details
                    WHERE audit_id = la.id AND ip_address IS NOT NULL AND ip_address <> ''
                    LIMIT 1) AS ip_address,
                   (SELECT COUNT(*) FROM legacy_audit_software WHERE audit_id = la.id) AS software_count,
                   (SELECT STRING_AGG(name, ', ') FROM legacy_audit_antivirus
                    WHERE audit_id = la.id AND name IS NOT NULL AND name <> '') AS antivirus
            FROM legacy_audits la
            ORDER BY la.created_at DESC
        """)
        audits = [dict(r) for r in cur.fetchall()]

    deduped = _dedupe_latest_audit_per_device(audits)[:limit]

    results = []
    for a in deduped:
        # Same precedence as /devices and the software inventory's device
        # links, so this row's device name is routable to /inventory/hardware/{id}.
        mac = a.get("mac_address")
        device_id = mac if mac and mac != "Unknown" else (a.get("computer_name") or "Unknown")
        results.append({
            "id": device_id,
            "device": a["computer_name"] or a["mac_address"] or "Unknown",
            "ip": a["ip_address"] or "Unknown",
            "os": " ".join(x for x in [a["os_name"], a["os_version"]] if x) or "Unknown",
            "audited_on": a["execution_datetime"] or "Unknown",
            "current_user": a["current_username"] or "Unknown",
            "antivirus": a["antivirus"] or "None detected",
            "firewall": a["firewall"] or "Unknown",
            "license_status": a["license_status"] or "Unknown",
            "software_count": a["software_count"] or 0,
        })
    return results


def get_compliance_summary() -> dict:
    """
    Firewall / Antivirus / License breakdown across every real device's latest
    audit (not just the 5 shown in the Recent Device Audits card) — backs the
    Dashboard's compliance chart. Same raw fields and same "one row per real
    device" dedup as list_recent_audits(), just aggregated instead of listed.
    """
    with get_inventory_db() as conn:
        cur = _dict_cursor(conn)
        cur.execute("""
            SELECT la.id, la.mac_address, la.computer_name, la.os_name,
                   la.created_at, la.firewall, la.license_status,
                   (SELECT STRING_AGG(name, ', ') FROM legacy_audit_antivirus
                    WHERE audit_id = la.id AND name IS NOT NULL AND name <> '') AS antivirus
            FROM legacy_audits la
            ORDER BY la.created_at DESC
        """)
        audits = [dict(r) for r in cur.fetchall()]

    deduped = _dedupe_latest_audit_per_device(audits)

    firewall = {"enabled": 0, "disabled": 0, "unknown": 0}
    antivirus = {"protected": 0, "unprotected": 0}
    license_status = {"licensed": 0, "unlicensed": 0, "unknown": 0}

    for a in deduped:
        fw = (a.get("firewall") or "").strip().lower()
        if "enabled" in fw:
            firewall["enabled"] += 1
        elif "disabled" in fw:
            firewall["disabled"] += 1
        else:
            firewall["unknown"] += 1

        av = (a.get("antivirus") or "").strip()
        if av:
            antivirus["protected"] += 1
        else:
            antivirus["unprotected"] += 1

        lic = (a.get("license_status") or "").strip().lower()
        if "unlicensed" in lic:
            license_status["unlicensed"] += 1
        elif "licensed" in lic:
            license_status["licensed"] += 1
        else:
            license_status["unknown"] += 1

    return {
        "total": len(deduped),
        "firewall": firewall,
        "antivirus": antivirus,
        "license": license_status,
    }


def _dedupe_latest_audit_per_device(audits: list) -> list:
    """Same (name, OS family) de-dup devices.py's device list uses, so a
    software inventory count of 'installed on N devices' matches N devices
    actually listed on the Hardware/Software pages."""
    seen = {}
    for a in audits:
        name = (a.get("computer_name") or "Unknown").strip()
        os_name = (a.get("os_name") or "Unknown").strip().lower()
        if "windows" in os_name:
            os_family = "windows"
        elif "mac" in os_name:
            os_family = "mac"
        elif "ubuntu" in os_name or "linux" in os_name:
            os_family = "linux"
        else:
            os_family = os_name
        key = (name.lower(), os_family)
        if key not in seen:
            seen[key] = a
    return list(seen.values())


def list_software_inventory():
    """
    One row per distinct (application name, version) combo, aggregated across
    every device's latest audit — the estate-wide 'Software' inventory, as
    opposed to get_latest_audit()'s per-device software list.
    """
    with get_inventory_db() as conn:
        cur = _dict_cursor(conn)
        cur.execute("""
            SELECT id, mac_address, computer_name, os_name, execution_datetime, created_at
            FROM legacy_audits ORDER BY created_at DESC
        """)
        latest_audits = _dedupe_latest_audit_per_device([dict(r) for r in cur.fetchall()])
        audit_ids = [a["id"] for a in latest_audits]

        def _device_id(a):
            # Same precedence as devices.py's list_audited_devices(), so a
            # device clicked here routes to the same id used everywhere else.
            mac = a.get("mac_address")
            return mac if mac and mac != "Unknown" else (a.get("computer_name") or "Unknown")

        device_by_audit = {
            a["id"]: {"id": _device_id(a), "name": a.get("computer_name") or _device_id(a)}
            for a in latest_audits
        }

        if not audit_ids:
            return []

        cur.execute("""
            SELECT audit_id, application_name, version, publisher, install_date, size_mb
            FROM legacy_audit_software WHERE audit_id = ANY(%s::uuid[])
        """, (audit_ids,))
        rows = cur.fetchall()

    aggregated: dict = {}
    for row in rows:
        name = (row["application_name"] or "Unknown").strip() or "Unknown"
        version = (row["version"] or "Unknown").strip() or "Unknown"
        key = (name.lower(), version.lower())
        entry = aggregated.setdefault(key, {
            "name": name,
            "version": version,
            "publisher": row["publisher"] or "Unknown",
            "install_date": row["install_date"] or "Unknown",
            "size_mb": row["size_mb"] or "Unknown",
            "devices": [],
        })
        device = device_by_audit.get(row["audit_id"], {"id": "Unknown", "name": "Unknown"})
        if not any(d["id"] == device["id"] for d in entry["devices"]):
            entry["devices"].append(device)

    result = [
        {
            "name": entry["name"],
            "version": entry["version"],
            "publisher": entry["publisher"],
            "install_date": entry["install_date"],
            "size_mb": entry["size_mb"],
            "install_count": len(entry["devices"]),
            "devices": entry["devices"],
        }
        for entry in aggregated.values()
    ]
    result.sort(key=lambda x: x["name"].lower())
    return result


def get_audit_enrichment_indexes():
    """
    Two lookup dicts used to enrich live network-scan results with prior audit
    data: by IP address (from legacy_audit_network_details) and by normalized
    MAC address. Mirrors the shape the SQLite-era get_audit_indexes() returned.
    """
    audit_index: dict = {}
    audit_mac_index: dict = {}
    with get_inventory_db() as conn:
        cur = _dict_cursor(conn)
        cur.execute("""
            SELECT id, mac_address, computer_name, os_name, current_username, execution_datetime
            FROM legacy_audits ORDER BY created_at DESC
        """)
        audits = [dict(r) for r in cur.fetchall()]

        for a in audits:
            c_name = a["computer_name"] or "Unknown"
            c_mac = a["mac_address"] or "Unknown"
            info = {
                "id": c_mac if c_mac != "Unknown" else c_name,
                "computer_name": c_name,
                "os_name": a["os_name"] or "Unknown",
                "username": a["current_username"] or "Unknown",
                "last_audit": a["execution_datetime"] or "",
            }
            if c_mac != "Unknown":
                clean_mac = c_mac.replace(":", "").replace("-", "").upper()
                if clean_mac not in audit_mac_index:
                    audit_mac_index[clean_mac] = info

            cur.execute("SELECT ip_address FROM legacy_audit_network_details WHERE audit_id = %s", (a["id"],))
            for row in cur.fetchall():
                raw_ip = row["ip_address"] or ""
                for ip_part in str(raw_ip).split(","):
                    ip_clean = ip_part.strip()
                    if ip_clean and ip_clean not in ("Unknown", "N/A", "") and ip_clean not in audit_index:
                        audit_index[ip_clean] = info

    return audit_index, audit_mac_index


def get_audit_report_paths(client_id: str):
    with get_inventory_db() as conn:
        cur = _dict_cursor(conn)
        cur.execute("""
            SELECT pdf_path, xml_path FROM legacy_audits WHERE client_id = %s
            ORDER BY created_at DESC LIMIT 1
        """, (client_id,))
        row = cur.fetchone()
        return dict(row) if row else None


# ── Asset Metadata ────────────────────────────────────────────────────────────

_ASSET_METADATA_COLUMNS = [
    "device_id", "asset_tag", "owner", "department", "location", "purchase_date",
    "purchase_price", "warranty_expiry", "life_cycle_stage", "vendor", "notes", "last_updated",
]


def save_asset_metadata(device_id: str, fields: dict) -> dict:
    with get_inventory_db() as conn:
        cur = _dict_cursor(conn)
        cols = ["device_id"] + [c for c in _ASSET_METADATA_COLUMNS[1:-1] if c in fields]
        vals = [device_id] + [fields[c] for c in cols[1:]]
        placeholders = ", ".join(["%s"] * len(vals))
        col_list = ", ".join(cols)
        update_clause = ", ".join(f"{c} = EXCLUDED.{c}" for c in cols[1:])
        cur.execute(f"""
            INSERT INTO asset_metadata ({col_list}, last_updated)
            VALUES ({placeholders}, CURRENT_TIMESTAMP)
            ON CONFLICT (device_id) DO UPDATE SET {update_clause}, last_updated = CURRENT_TIMESTAMP
            RETURNING {", ".join(_ASSET_METADATA_COLUMNS)}
        """, vals)
        row = dict(cur.fetchone())
        conn.commit()
        return row


def get_asset_metadata(device_id: str):
    with get_inventory_db() as conn:
        cur = _dict_cursor(conn)
        cur.execute(f"SELECT {', '.join(_ASSET_METADATA_COLUMNS)} FROM asset_metadata WHERE device_id = %s", (device_id,))
        row = cur.fetchone()
        return dict(row) if row else None


def delete_asset_metadata(device_id: str) -> bool:
    with get_inventory_db() as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM asset_metadata WHERE device_id = %s", (device_id,))
        deleted = cur.rowcount > 0
        conn.commit()
        return deleted


def list_asset_metadata():
    with get_inventory_db() as conn:
        cur = _dict_cursor(conn)
        cur.execute(f"SELECT {', '.join(_ASSET_METADATA_COLUMNS)} FROM asset_metadata ORDER BY last_updated DESC")
        return [dict(r) for r in cur.fetchall()]


# ── Saved WiFi Credentials ────────────────────────────────────────────────────

def save_wifi_credential(ssid: str, password: str) -> dict:
    with get_inventory_db() as conn:
        cur = _dict_cursor(conn)
        cur.execute("""
            INSERT INTO saved_wifi_credentials (ssid, password, updated_at)
            VALUES (%s, %s, CURRENT_TIMESTAMP)
            ON CONFLICT (ssid) DO UPDATE SET password = EXCLUDED.password, updated_at = CURRENT_TIMESTAMP
            RETURNING ssid, password, updated_at
        """, (ssid, password))
        row = dict(cur.fetchone())
        conn.commit()
        return row


def list_wifi_credentials() -> list:
    with get_inventory_db() as conn:
        cur = _dict_cursor(conn)
        cur.execute("SELECT ssid, password, updated_at FROM saved_wifi_credentials")
        return [dict(r) for r in cur.fetchall()]


def list_wifi_ssids() -> list:
    with get_inventory_db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT ssid FROM saved_wifi_credentials")
        return [r[0] for r in cur.fetchall()]


# ── Asset Lifecycle & Tickets ─────────────────────────────────────────────────

_LIFECYCLE_COLUMNS = [
    "mac_address", "computer_name", "owner", "location", "vendor", "status",
    "warranty_start", "warranty_end", "warranty_notes", "warranty_provider",
    "purchase_price", "purchase_date", "supplier", "po_number", "updated_at",
]


def _ensure_lifecycle_row(cur, mac_address: str, computer_name: str = ""):
    """Idempotent placeholder insert so a ticket can reference a mac before a full lifecycle record exists."""
    cur.execute("""
        INSERT INTO asset_lifecycle_v2 (mac_address, computer_name, updated_at)
        VALUES (%s, %s, CURRENT_TIMESTAMP)
        ON CONFLICT (mac_address) DO NOTHING
    """, (mac_address, computer_name))


def save_lifecycle(mac_address: str, computer_name: str, fields: dict) -> dict:
    with get_inventory_db() as conn:
        cur = _dict_cursor(conn)
        cols = ["mac_address", "computer_name"] + [c for c in _LIFECYCLE_COLUMNS[2:-1] if c in fields]
        vals = [mac_address, computer_name] + [fields[c] for c in cols[2:]]
        placeholders = ", ".join(["%s"] * len(vals))
        col_list = ", ".join(cols)
        update_clause = ", ".join(f"{c} = EXCLUDED.{c}" for c in cols[1:])
        cur.execute(f"""
            INSERT INTO asset_lifecycle_v2 ({col_list}, updated_at)
            VALUES ({placeholders}, CURRENT_TIMESTAMP)
            ON CONFLICT (mac_address) DO UPDATE SET {update_clause}, updated_at = CURRENT_TIMESTAMP
            RETURNING {", ".join(_LIFECYCLE_COLUMNS)}
        """, vals)
        row = dict(cur.fetchone())
        conn.commit()
        return row


def get_lifecycle(identifier: str):
    with get_inventory_db() as conn:
        cur = _dict_cursor(conn)
        cur.execute(f"""
            SELECT {", ".join(_LIFECYCLE_COLUMNS)} FROM asset_lifecycle_v2
            WHERE mac_address = %s OR computer_name = %s LIMIT 1
        """, (identifier, identifier))
        row = cur.fetchone()
        return dict(row) if row else {}


def create_ticket(mac_address: str, computer_name: str, fields: dict) -> dict:
    with get_inventory_db() as conn:
        cur = _dict_cursor(conn)
        try:
            _ensure_lifecycle_row(cur, mac_address, computer_name)
            cur.execute("""
                INSERT INTO asset_tickets_v2
                    (mac_address, computer_name, ticket_number, summary, status, assigned, priority, mtbf)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id, mac_address, computer_name, ticket_number, summary, status, assigned, priority, mtbf, created_at, updated_at
            """, (mac_address, computer_name, fields.get("ticket_number", ""), fields.get("summary", ""),
                  fields.get("status", "Open"), fields.get("assigned", ""), fields.get("priority", "Medium"),
                  fields.get("mtbf", "")))
            row = dict(cur.fetchone())
            conn.commit()
            return row
        except Exception:
            conn.rollback()
            raise


def list_tickets(mac_address: str) -> list:
    with get_inventory_db() as conn:
        cur = _dict_cursor(conn)
        cur.execute("""
            SELECT id, mac_address, computer_name, ticket_number, summary, status, assigned, priority, mtbf, created_at, updated_at
            FROM asset_tickets_v2 WHERE mac_address = %s ORDER BY created_at DESC
        """, (mac_address,))
        return [dict(r) for r in cur.fetchall()]


def update_ticket(ticket_id: str, fields: dict) -> dict:
    with get_inventory_db() as conn:
        cur = _dict_cursor(conn)
        cur.execute("""
            UPDATE asset_tickets_v2
            SET summary = %s, status = %s, assigned = %s, priority = %s, mtbf = %s, updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
            RETURNING id, mac_address, computer_name, ticket_number, summary, status, assigned, priority, mtbf, created_at, updated_at
        """, (fields.get("summary", ""), fields.get("status", "Open"), fields.get("assigned", ""),
              fields.get("priority", "Medium"), fields.get("mtbf", ""), ticket_id))
        row = cur.fetchone()
        conn.commit()
        return dict(row) if row else None


def delete_ticket(ticket_id: str) -> bool:
    with get_inventory_db() as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM asset_tickets_v2 WHERE id = %s", (ticket_id,))
        deleted = cur.rowcount > 0
        conn.commit()
        return deleted
