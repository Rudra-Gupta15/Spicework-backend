"""
Device/asset inventory + agent-deployment tracking for the "sw inventory" database.

Shares the connection helper with auth_db.py (same database, same env vars) but
kept in its own module since device/asset management is a distinct domain from
identity/organization management.

Table naming: every hardware-side table is prefixed `hardware_`, every
software-side table is prefixed `software_` (matching how the UI itself groups
Login/User/Software together under one "Software" page). `agent_deployments`
sits outside both — it's about tracking how a device was onboarded, not the
device's own data.
"""
import uuid as uuid_module

import psycopg2
import psycopg2.errors
import psycopg2.extras

from backend.auth_db import _dict_cursor, get_inventory_db

# ── Agent Deployments ────────────────────────────────────────────────────────

_DEPLOYMENT_COLUMNS = """
    id, organization_id, site_id, requested_by, client_id, launcher_type,
    deployment_mode, server_ip, server_port, status, created_at, completed_at
"""


def create_agent_deployment(
    organization_id: str,
    requested_by: str,
    launcher_type: str,
    deployment_mode: str = "self",
    site_id: str = None,
    server_ip: str = None,
    server_port: int = None,
    client_id: str = None,
) -> dict:
    """
    Record a launcher download before the file is generated. Returns the row,
    including client_id — embed that in the generated script so the eventual
    audit upload can be traced back to this organization/site/user.
    """
    client_id = client_id or f"agent_{uuid_module.uuid4().hex[:16]}"
    with get_inventory_db() as conn:
        cur = _dict_cursor(conn)
        try:
            cur.execute(f"""
                INSERT INTO agent_deployments
                    (organization_id, site_id, requested_by, client_id, launcher_type, deployment_mode, server_ip, server_port)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING {_DEPLOYMENT_COLUMNS}
            """, (organization_id, site_id, requested_by, client_id, launcher_type, deployment_mode, server_ip, server_port))
            row = dict(cur.fetchone())
            conn.commit()
            return row
        except psycopg2.errors.UniqueViolation:
            conn.rollback()
            raise ValueError(f"client_id '{client_id}' already exists.")
        except psycopg2.errors.ForeignKeyViolation:
            conn.rollback()
            raise ValueError(f"No organization found with id '{organization_id}'.")
        except Exception:
            conn.rollback()
            raise


def get_deployment_by_client_id(client_id: str):
    with get_inventory_db() as conn:
        cur = _dict_cursor(conn)
        cur.execute(f"SELECT {_DEPLOYMENT_COLUMNS} FROM agent_deployments WHERE client_id = %s", (client_id,))
        row = cur.fetchone()
        return dict(row) if row else None


def mark_deployment_completed(client_id: str):
    with get_inventory_db() as conn:
        cur = _dict_cursor(conn)
        cur.execute(f"""
            UPDATE agent_deployments SET status = 'completed', completed_at = CURRENT_TIMESTAMP
            WHERE client_id = %s
            RETURNING {_DEPLOYMENT_COLUMNS}
        """, (client_id,))
        row = cur.fetchone()
        conn.commit()
        return dict(row) if row else None


def list_deployments(organization_id: str, site_id: str = None) -> list:
    with get_inventory_db() as conn:
        cur = _dict_cursor(conn)
        query = f"SELECT {_DEPLOYMENT_COLUMNS} FROM agent_deployments WHERE organization_id = %s"
        params = [organization_id]
        if site_id:
            query += " AND site_id = %s"
            params.append(site_id)
        query += " ORDER BY created_at DESC"
        cur.execute(query, params)
        return [dict(r) for r in cur.fetchall()]


# ── Hardware: hardware_devices (master record) ───────────────────────────────

_HARDWARE_DEVICE_COLUMNS = """
    id, organization_id, site_id, deployment_id,
    device_name, device_type, mac_address, serial_number, asset_tag,
    manufacturer, model, description,
    os_name, os_version, os_build, domain, domain_role,
    location, public_ip,
    scanner_name, status, uptime, last_boot_time, last_shutdown_time, last_backup,
    license_status, firewall, bitlocker, secure_boot, tpm, antivirus,
    last_login_user, last_login_at, warranty_expiry,
    last_scanned_by, last_scan_at, created_at, updated_at
"""

# Columns upsert_hardware_device()/record_device_audit() are allowed to write,
# beyond the identity/linkage columns (organization_id, site_id, deployment_id,
# device_name, last_scanned_by) which are always handled explicitly.
_HARDWARE_DEVICE_UPSERT_FIELDS = [
    "device_type", "mac_address", "serial_number", "asset_tag", "manufacturer", "model", "description",
    "os_name", "os_version", "os_build", "domain", "domain_role",
    "location", "public_ip",
    "scanner_name", "status", "uptime", "last_boot_time", "last_shutdown_time", "last_backup",
    "license_status", "firewall", "bitlocker", "secure_boot", "tpm", "antivirus",
    "last_login_user", "last_login_at", "warranty_expiry",
]


def _build_hardware_device_update_clause(cols: list) -> str:
    """
    ON CONFLICT ... DO UPDATE SET clause for the hardware_devices upsert.
    deployment_id and last_scanned_by are attribution fields — a rescan that
    doesn't specify them (e.g. a recurring daemon run with no fresh launcher
    download) should preserve the existing value rather than null it out, so
    those two use COALESCE.
    """
    parts = []
    for c in cols:
        if c in ("organization_id", "device_name"):
            continue
        if c in ("deployment_id", "last_scanned_by"):
            parts.append(f"{c} = COALESCE(EXCLUDED.{c}, hardware_devices.{c})")
        else:
            parts.append(f"{c} = EXCLUDED.{c}")
    parts.append("last_scan_at = CURRENT_TIMESTAMP")
    parts.append("updated_at = CURRENT_TIMESTAMP")
    return ", ".join(parts)


def upsert_hardware_device(organization_id: str, device_name: str, site_id: str = None,
                            deployment_id: str = None, last_scanned_by: str = None, **fields) -> dict:
    """
    Insert or refresh a device's current-state hardware row, matched by
    (organization_id, lower(device_name)). Only keys from
    _HARDWARE_DEVICE_UPSERT_FIELDS are written; anything else in `fields` is ignored.
    """
    cols = ["organization_id", "site_id", "deployment_id", "device_name", "last_scanned_by"]
    vals = [organization_id, site_id, deployment_id, device_name, last_scanned_by]
    for key in _HARDWARE_DEVICE_UPSERT_FIELDS:
        if key in fields:
            cols.append(key)
            vals.append(fields[key])

    placeholders = ", ".join(["%s"] * len(vals))
    col_list = ", ".join(cols)
    update_clause = _build_hardware_device_update_clause(cols)

    with get_inventory_db() as conn:
        cur = _dict_cursor(conn)
        try:
            cur.execute(f"""
                INSERT INTO hardware_devices ({col_list})
                VALUES ({placeholders})
                ON CONFLICT (organization_id, lower(device_name)) DO UPDATE SET {update_clause}
                RETURNING {_HARDWARE_DEVICE_COLUMNS}
            """, vals)
            row = dict(cur.fetchone())
            conn.commit()
            return row
        except psycopg2.errors.ForeignKeyViolation as e:
            conn.rollback()
            raise ValueError(f"Invalid reference while upserting device: {e}")
        except Exception:
            conn.rollback()
            raise


def get_hardware_device(device_id: str):
    with get_inventory_db() as conn:
        cur = _dict_cursor(conn)
        cur.execute(f"SELECT {_HARDWARE_DEVICE_COLUMNS} FROM hardware_devices WHERE id = %s", (device_id,))
        row = cur.fetchone()
        return dict(row) if row else None


def list_hardware_devices(organization_id: str, site_id: str = None) -> list:
    with get_inventory_db() as conn:
        cur = _dict_cursor(conn)
        query = f"SELECT {_HARDWARE_DEVICE_COLUMNS} FROM hardware_devices WHERE organization_id = %s"
        params = [organization_id]
        if site_id:
            query += " AND site_id = %s"
            params.append(site_id)
        query += " ORDER BY device_name"
        cur.execute(query, params)
        return [dict(r) for r in cur.fetchall()]


# ── Software: standalone replace helpers (each its own transaction) ────────────
# Useful for updating just one tab's data. record_device_audit() below does the
# same thing but atomically, for the full-payload case.

def replace_software_inventory(device_id: str, organization_id: str, items: list) -> list:
    with get_inventory_db() as conn:
        cur = _dict_cursor(conn)
        try:
            cur.execute("DELETE FROM software_inventory WHERE device_id = %s", (device_id,))
            rows = []
            for it in items:
                cur.execute("""
                    INSERT INTO software_inventory
                        (device_id, organization_id, application_name, version, publisher,
                         install_date, size, last_used, is_licensed, is_subscription)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id, device_id, organization_id, application_name, version, publisher,
                              install_date, size, last_used, is_licensed, is_subscription, created_at
                """, (
                    device_id, organization_id, it.get("application_name") or it.get("name"),
                    it.get("version"), it.get("publisher"), it.get("install_date"),
                    it.get("size"), it.get("last_used"),
                    bool(it.get("is_licensed", False)), bool(it.get("is_subscription", False)),
                ))
                rows.append(dict(cur.fetchone()))
            conn.commit()
            return rows
        except Exception:
            conn.rollback()
            raise


def replace_software_users(device_id: str, items: list) -> list:
    with get_inventory_db() as conn:
        cur = _dict_cursor(conn)
        try:
            cur.execute("DELETE FROM software_users WHERE device_id = %s", (device_id,))
            rows = []
            for it in items:
                cur.execute("""
                    INSERT INTO software_users
                        (device_id, username, home_directory, last_login, licensed, user_type, is_current_user)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    RETURNING id, device_id, username, home_directory, last_login, licensed, user_type, is_current_user, created_at
                """, (
                    device_id, it.get("username") or it.get("name"), it.get("home_directory"),
                    it.get("last_login"), bool(it.get("licensed", False)), it.get("user_type"),
                    bool(it.get("is_current_user") if "is_current_user" in it else it.get("current_user", False)),
                ))
                rows.append(dict(cur.fetchone()))
            conn.commit()
            return rows
        except Exception:
            conn.rollback()
            raise


def replace_software_login_history(device_id: str, items: list) -> list:
    with get_inventory_db() as conn:
        cur = _dict_cursor(conn)
        try:
            cur.execute("DELETE FROM software_login_history WHERE device_id = %s", (device_id,))
            rows = []
            for it in items:
                cur.execute("""
                    INSERT INTO software_login_history (device_id, username, domain, logon_type, logged_in_at)
                    VALUES (%s, %s, %s, %s, %s)
                    RETURNING id, device_id, username, domain, logon_type, logged_in_at, created_at
                """, (device_id, it.get("username") or it.get("user"), it.get("domain"),
                      it.get("logon_type"), it.get("logged_in_at") or it.get("timestamp")))
                rows.append(dict(cur.fetchone()))
            conn.commit()
            return rows
        except Exception:
            conn.rollback()
            raise


# ── Hardware: standalone replace helpers ────────────────────────────────────

def replace_hardware_gpus(device_id: str, items: list) -> list:
    with get_inventory_db() as conn:
        cur = _dict_cursor(conn)
        try:
            cur.execute("DELETE FROM hardware_gpus WHERE device_id = %s", (device_id,))
            rows = []
            for it in items:
                cur.execute("""
                    INSERT INTO hardware_gpus (device_id, name, driver_version, vram)
                    VALUES (%s, %s, %s, %s)
                    RETURNING id, device_id, name, driver_version, vram
                """, (device_id, it.get("name"), it.get("driver_version"), it.get("vram")))
                rows.append(dict(cur.fetchone()))
            conn.commit()
            return rows
        except Exception:
            conn.rollback()
            raise


def replace_hardware_network_adapters(device_id: str, items: list) -> list:
    with get_inventory_db() as conn:
        cur = _dict_cursor(conn)
        try:
            cur.execute("DELETE FROM hardware_network_adapters WHERE device_id = %s", (device_id,))
            rows = []
            for it in items:
                cur.execute("""
                    INSERT INTO hardware_network_adapters
                        (device_id, name, adapter_type, speed, mac_address, ipv4, ipv6, gateway, subnet_mask, dns_servers)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id, device_id, name, adapter_type, speed, mac_address, ipv4, ipv6, gateway, subnet_mask, dns_servers
                """, (
                    device_id, it.get("name"), it.get("adapter_type"), it.get("speed"),
                    it.get("mac_address"), it.get("ipv4"), it.get("ipv6"),
                    it.get("gateway"), it.get("subnet_mask"), it.get("dns_servers"),
                ))
                rows.append(dict(cur.fetchone()))
            conn.commit()
            return rows
        except Exception:
            conn.rollback()
            raise


def replace_hardware_storage(device_id: str, items: list) -> list:
    """`items`: each dict must include a 'kind' key ('disk' | 'partition')."""
    with get_inventory_db() as conn:
        cur = _dict_cursor(conn)
        try:
            cur.execute("DELETE FROM hardware_storage WHERE device_id = %s", (device_id,))
            rows = []
            for it in items:
                cur.execute("""
                    INSERT INTO hardware_storage
                        (device_id, kind, name, type, size_gb, free_gb, file_system, is_ssd, bootable, health)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id, device_id, kind, name, type, size_gb, free_gb, file_system, is_ssd, bootable, health
                """, (
                    device_id, it["kind"], it.get("name"), it.get("type"),
                    it.get("size_gb") or it.get("size"), it.get("free_gb") or it.get("free_space"),
                    it.get("file_system"), it.get("is_ssd"), it.get("bootable"), it.get("health"),
                ))
                rows.append(dict(cur.fetchone()))
            conn.commit()
            return rows
        except Exception:
            conn.rollback()
            raise


def replace_hardware_peripherals(device_id: str, items: list) -> list:
    with get_inventory_db() as conn:
        cur = _dict_cursor(conn)
        try:
            cur.execute("DELETE FROM hardware_peripherals WHERE device_id = %s", (device_id,))
            rows = []
            for it in items:
                cur.execute("""
                    INSERT INTO hardware_peripherals (device_id, name, type, status)
                    VALUES (%s, %s, %s, %s)
                    RETURNING id, device_id, name, type, status
                """, (device_id, it.get("name"), it.get("type"), it.get("status")))
                rows.append(dict(cur.fetchone()))
            conn.commit()
            return rows
        except Exception:
            conn.rollback()
            raise


def replace_hardware_printers(device_id: str, items: list) -> list:
    with get_inventory_db() as conn:
        cur = _dict_cursor(conn)
        try:
            cur.execute("DELETE FROM hardware_printers WHERE device_id = %s", (device_id,))
            rows = []
            for it in items:
                cur.execute("""
                    INSERT INTO hardware_printers (device_id, name, system_name, port_name, status)
                    VALUES (%s, %s, %s, %s, %s)
                    RETURNING id, device_id, name, system_name, port_name, status
                """, (device_id, it.get("name"), it.get("system_name"), it.get("port_name"), it.get("status")))
                rows.append(dict(cur.fetchone()))
            conn.commit()
            return rows
        except Exception:
            conn.rollback()
            raise


def replace_hardware_connected_devices(device_id: str, items: list) -> list:
    with get_inventory_db() as conn:
        cur = _dict_cursor(conn)
        try:
            cur.execute("DELETE FROM hardware_connected_devices WHERE device_id = %s", (device_id,))
            rows = []
            for it in items:
                cur.execute("""
                    INSERT INTO hardware_connected_devices
                        (device_id, ip_address, hostname, mac_address, device_type, open_ports, status)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    RETURNING id, device_id, ip_address, hostname, mac_address, device_type, open_ports, status, discovered_at
                """, (
                    device_id, it.get("ip_address") or it.get("ip"), it.get("hostname"),
                    it.get("mac_address"), it.get("device_type"),
                    psycopg2.extras.Json(it.get("open_ports") or it.get("port_labels") or []),
                    it.get("status"),
                ))
                rows.append(dict(cur.fetchone()))
            conn.commit()
            return rows
        except Exception:
            conn.rollback()
            raise


# ── Full audit — one atomic transaction across hardware + software ─────────────

def record_device_audit(
    organization_id: str,
    device_name: str,
    site_id: str = None,
    deployment_id: str = None,
    scanned_by: str = None,
    device: dict = None,
    software: list = None,
    users: list = None,
    login_history: list = None,
    gpus: list = None,
    network_adapters: list = None,
    storage: list = None,
    peripherals: list = None,
    printers: list = None,
    connected_devices: list = None,
) -> dict:
    """
    Atomically upsert a device's hardware_devices row plus every hardware_*/
    software_* child table, replacing each child table's rows entirely
    (current-state only, no history kept). `device` holds the flat
    hardware_devices fields (os_name, manufacturer, ...); all list args default
    to empty. If deployment_id is given, marks that deployment completed as part
    of the same transaction.
    """
    device = device or {}
    software = software or []
    users = users or []
    login_history = login_history or []
    gpus = gpus or []
    network_adapters = network_adapters or []
    storage = storage or []
    peripherals = peripherals or []
    printers = printers or []
    connected_devices = connected_devices or []

    cols = ["organization_id", "site_id", "deployment_id", "device_name", "last_scanned_by"]
    vals = [organization_id, site_id, deployment_id, device_name, scanned_by]
    for key in _HARDWARE_DEVICE_UPSERT_FIELDS:
        if key in device:
            cols.append(key)
            vals.append(device[key])
    placeholders = ", ".join(["%s"] * len(vals))
    col_list = ", ".join(cols)
    update_clause = _build_hardware_device_update_clause(cols)

    with get_inventory_db() as conn:
        cur = _dict_cursor(conn)
        try:
            cur.execute(f"""
                INSERT INTO hardware_devices ({col_list})
                VALUES ({placeholders})
                ON CONFLICT (organization_id, lower(device_name)) DO UPDATE SET {update_clause}
                RETURNING {_HARDWARE_DEVICE_COLUMNS}
            """, vals)
            dev = dict(cur.fetchone())
            device_id = dev["id"]

            def _replace(table, insert_sql, rows, row_to_params):
                cur.execute(f"DELETE FROM {table} WHERE device_id = %s", (device_id,))
                out = []
                for r in rows:
                    cur.execute(insert_sql, row_to_params(r))
                    out.append(dict(cur.fetchone()))
                return out

            dev["software"] = _replace(
                "software_inventory",
                """INSERT INTO software_inventory
                    (device_id, organization_id, application_name, version, publisher, install_date, size, last_used, is_licensed, is_subscription)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                   RETURNING id, device_id, organization_id, application_name, version, publisher, install_date, size, last_used, is_licensed, is_subscription, created_at""",
                software,
                lambda it: (device_id, organization_id, it.get("application_name") or it.get("name"),
                            it.get("version"), it.get("publisher"), it.get("install_date"),
                            it.get("size"), it.get("last_used"),
                            bool(it.get("is_licensed", False)), bool(it.get("is_subscription", False))),
            )
            dev["users"] = _replace(
                "software_users",
                """INSERT INTO software_users
                    (device_id, username, home_directory, last_login, licensed, user_type, is_current_user)
                   VALUES (%s,%s,%s,%s,%s,%s,%s)
                   RETURNING id, device_id, username, home_directory, last_login, licensed, user_type, is_current_user, created_at""",
                users,
                lambda it: (device_id, it.get("username") or it.get("name"), it.get("home_directory"),
                            it.get("last_login"), bool(it.get("licensed", False)), it.get("user_type"),
                            bool(it.get("is_current_user") if "is_current_user" in it else it.get("current_user", False))),
            )
            dev["login_history"] = _replace(
                "software_login_history",
                """INSERT INTO software_login_history (device_id, username, domain, logon_type, logged_in_at)
                   VALUES (%s,%s,%s,%s,%s)
                   RETURNING id, device_id, username, domain, logon_type, logged_in_at, created_at""",
                login_history,
                lambda it: (device_id, it.get("username") or it.get("user"), it.get("domain"),
                            it.get("logon_type"), it.get("logged_in_at") or it.get("timestamp")),
            )
            dev["gpus"] = _replace(
                "hardware_gpus",
                """INSERT INTO hardware_gpus (device_id, name, driver_version, vram)
                   VALUES (%s,%s,%s,%s)
                   RETURNING id, device_id, name, driver_version, vram""",
                gpus,
                lambda it: (device_id, it.get("name"), it.get("driver_version"), it.get("vram")),
            )
            dev["network_adapters"] = _replace(
                "hardware_network_adapters",
                """INSERT INTO hardware_network_adapters
                    (device_id, name, adapter_type, speed, mac_address, ipv4, ipv6, gateway, subnet_mask, dns_servers)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                   RETURNING id, device_id, name, adapter_type, speed, mac_address, ipv4, ipv6, gateway, subnet_mask, dns_servers""",
                network_adapters,
                lambda it: (device_id, it.get("name"), it.get("adapter_type"), it.get("speed"),
                            it.get("mac_address"), it.get("ipv4"), it.get("ipv6"),
                            it.get("gateway"), it.get("subnet_mask"), it.get("dns_servers")),
            )
            dev["storage"] = _replace(
                "hardware_storage",
                """INSERT INTO hardware_storage
                    (device_id, kind, name, type, size_gb, free_gb, file_system, is_ssd, bootable, health)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                   RETURNING id, device_id, kind, name, type, size_gb, free_gb, file_system, is_ssd, bootable, health""",
                storage,
                lambda it: (device_id, it["kind"], it.get("name"), it.get("type"),
                            it.get("size_gb") or it.get("size"), it.get("free_gb") or it.get("free_space"),
                            it.get("file_system"), it.get("is_ssd"), it.get("bootable"), it.get("health")),
            )
            dev["peripherals"] = _replace(
                "hardware_peripherals",
                """INSERT INTO hardware_peripherals (device_id, name, type, status)
                   VALUES (%s,%s,%s,%s)
                   RETURNING id, device_id, name, type, status""",
                peripherals,
                lambda it: (device_id, it.get("name"), it.get("type"), it.get("status")),
            )
            dev["printers"] = _replace(
                "hardware_printers",
                """INSERT INTO hardware_printers (device_id, name, system_name, port_name, status)
                   VALUES (%s,%s,%s,%s,%s)
                   RETURNING id, device_id, name, system_name, port_name, status""",
                printers,
                lambda it: (device_id, it.get("name"), it.get("system_name"), it.get("port_name"), it.get("status")),
            )
            dev["connected_devices"] = _replace(
                "hardware_connected_devices",
                """INSERT INTO hardware_connected_devices
                    (device_id, ip_address, hostname, mac_address, device_type, open_ports, status)
                   VALUES (%s,%s,%s,%s,%s,%s,%s)
                   RETURNING id, device_id, ip_address, hostname, mac_address, device_type, open_ports, status, discovered_at""",
                connected_devices,
                lambda it: (device_id, it.get("ip_address") or it.get("ip"), it.get("hostname"),
                            it.get("mac_address"), it.get("device_type"),
                            psycopg2.extras.Json(it.get("open_ports") or it.get("port_labels") or []),
                            it.get("status")),
            )

            if deployment_id:
                cur.execute("""
                    UPDATE agent_deployments SET status = 'completed', completed_at = CURRENT_TIMESTAMP
                    WHERE id = %s
                """, (deployment_id,))

            conn.commit()
            return dev
        except psycopg2.errors.ForeignKeyViolation as e:
            conn.rollback()
            raise ValueError(f"Invalid reference while recording device audit: {e}")
        except Exception:
            conn.rollback()
            raise


def get_device_detail(device_id: str):
    """Device plus every hardware_*/software_* child table — the full 'Hardware Assets' detail view."""
    device = get_hardware_device(device_id)
    if not device:
        return None
    with get_inventory_db() as conn:
        cur = _dict_cursor(conn)

        cur.execute("""
            SELECT id, device_id, organization_id, application_name, version, publisher,
                   install_date, size, last_used, is_licensed, is_subscription, created_at
            FROM software_inventory WHERE device_id = %s ORDER BY application_name
        """, (device_id,))
        device["software"] = [dict(r) for r in cur.fetchall()]

        cur.execute("""
            SELECT id, device_id, username, home_directory, last_login, licensed, user_type, is_current_user, created_at
            FROM software_users WHERE device_id = %s ORDER BY username
        """, (device_id,))
        device["users"] = [dict(r) for r in cur.fetchall()]

        cur.execute("""
            SELECT id, device_id, username, domain, logon_type, logged_in_at, created_at
            FROM software_login_history WHERE device_id = %s ORDER BY logged_in_at DESC
        """, (device_id,))
        device["login_history"] = [dict(r) for r in cur.fetchall()]

        cur.execute("SELECT id, device_id, name, driver_version, vram FROM hardware_gpus WHERE device_id = %s", (device_id,))
        device["gpus"] = [dict(r) for r in cur.fetchall()]

        cur.execute("""
            SELECT id, device_id, name, adapter_type, speed, mac_address, ipv4, ipv6, gateway, subnet_mask, dns_servers
            FROM hardware_network_adapters WHERE device_id = %s
        """, (device_id,))
        device["network_adapters"] = [dict(r) for r in cur.fetchall()]

        cur.execute("""
            SELECT id, device_id, kind, name, type, size_gb, free_gb, file_system, is_ssd, bootable, health
            FROM hardware_storage WHERE device_id = %s ORDER BY kind, name
        """, (device_id,))
        device["storage"] = [dict(r) for r in cur.fetchall()]

        cur.execute("SELECT id, device_id, name, type, status FROM hardware_peripherals WHERE device_id = %s", (device_id,))
        device["peripherals"] = [dict(r) for r in cur.fetchall()]

        cur.execute("SELECT id, device_id, name, system_name, port_name, status FROM hardware_printers WHERE device_id = %s", (device_id,))
        device["printers"] = [dict(r) for r in cur.fetchall()]

        cur.execute("""
            SELECT id, device_id, ip_address, hostname, mac_address, device_type, open_ports, status, discovered_at
            FROM hardware_connected_devices WHERE device_id = %s ORDER BY discovered_at DESC
        """, (device_id,))
        device["connected_devices"] = [dict(r) for r in cur.fetchall()]

        return device


# ── Aggregate stats — the summary cards on the Hardware / Software pages ───────

def get_hardware_stats(organization_id: str) -> dict:
    """Warranty is considered 'expiring' within the next 90 days."""
    with get_inventory_db() as conn:
        cur = _dict_cursor(conn)
        cur.execute("""
            SELECT
                COUNT(*) AS total_devices,
                COUNT(*) FILTER (WHERE status = 'online') AS online,
                COUNT(*) FILTER (WHERE status = 'offline') AS offline,
                COUNT(*) FILTER (
                    WHERE warranty_expiry IS NOT NULL
                      AND warranty_expiry <= CURRENT_DATE + INTERVAL '90 days'
                ) AS warranty_expiring
            FROM hardware_devices WHERE organization_id = %s
        """, (organization_id,))
        return dict(cur.fetchone())


def get_software_stats(organization_id: str) -> dict:
    with get_inventory_db() as conn:
        cur = _dict_cursor(conn)
        cur.execute("""
            SELECT
                COUNT(*) AS total_software,
                COUNT(*) FILTER (WHERE is_licensed) AS total_license,
                COUNT(*) FILTER (WHERE is_subscription) AS subscription_count,
                COUNT(DISTINCT publisher) FILTER (WHERE publisher IS NOT NULL AND publisher <> '') AS publisher_count
            FROM software_inventory WHERE organization_id = %s
        """, (organization_id,))
        return dict(cur.fetchone())
