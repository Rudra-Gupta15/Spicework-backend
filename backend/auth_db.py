"""
Connector for the external "sw inventory" PostgreSQL database
(users / roles / platform_user_roles / organizations / sites).

Kept fully separate from db.py — different env var prefix (INVENTORY_PG_*),
own connection helper — so the audit DB's sqlite<->postgres engine toggle can
never accidentally point at this database.
"""
import os
from contextlib import contextmanager

import bcrypt
import psycopg2
import psycopg2.errors
import psycopg2.extras


def _load_env():
    try:
        from dotenv import load_dotenv
        base_dir = os.path.dirname(os.path.abspath(__file__))
        root_dir = os.path.abspath(os.path.join(base_dir, ".."))
        load_dotenv(os.path.join(root_dir, ".env"), override=True)
        load_dotenv(os.path.join(base_dir, ".env"), override=True)
        load_dotenv(override=True)
    except ImportError:
        pass


def get_inventory_pg_creds() -> dict:
    """Fetch inventory-DB PostgreSQL credentials dynamically."""
    _load_env()
    return {
        "host": os.getenv("INVENTORY_PG_HOST", ""),
        "port": int(os.getenv("INVENTORY_PG_PORT", "5432")),
        "user": os.getenv("INVENTORY_PG_USER", "postgres"),
        "password": os.getenv("INVENTORY_PG_PASSWORD", ""),
        "dbname": os.getenv("INVENTORY_PG_DATABASE", ""),
    }


@contextmanager
def get_inventory_db():
    """Context manager yielding a raw psycopg2 connection to the inventory DB."""
    creds = get_inventory_pg_creds()
    conn = psycopg2.connect(
        host=creds["host"],
        port=creds["port"],
        user=creds["user"],
        password=creds["password"],
        dbname=creds["dbname"],
        connect_timeout=8,
    )
    try:
        yield conn
    finally:
        conn.close()


def _dict_cursor(conn):
    return conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)


def test_connection() -> dict:
    """Quick health check for a settings/status endpoint."""
    try:
        with get_inventory_db() as conn:
            cur = conn.cursor()
            cur.execute("SELECT 1")
            cur.fetchone()
        return {"status": "success", "connected": True}
    except Exception as e:
        return {"status": "error", "connected": False, "message": str(e)}


def get_org_dashboard_stats() -> dict:
    """Sites/users/cities across every organization — the Dashboard page's stat tiles."""
    with get_inventory_db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM sites")
        sites = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM users")
        users = cur.fetchone()[0]
        cur.execute("SELECT COUNT(DISTINCT city) FROM sites WHERE city IS NOT NULL AND city <> ''")
        cities = cur.fetchone()[0]
        return {"sites": sites, "users": users, "cities": cities}


_USER_COLUMNS = """
    id, email, first_name, last_name, user_type,
    is_active, email_verified, last_login_at,
    organization_id, site_id, created_at, updated_at
"""


def list_users() -> list:
    """All users, newest first. Never returns password_hash."""
    with get_inventory_db() as conn:
        cur = _dict_cursor(conn)
        cur.execute(f"""
            SELECT {_USER_COLUMNS}
            FROM users
            ORDER BY created_at DESC
        """)
        return [dict(r) for r in cur.fetchall()]


def get_user_by_id(user_id: str):
    with get_inventory_db() as conn:
        cur = _dict_cursor(conn)
        cur.execute(f"""
            SELECT {_USER_COLUMNS}
            FROM users WHERE id = %s
        """, (user_id,))
        row = cur.fetchone()
        return dict(row) if row else None


def get_user_by_email(email: str):
    with get_inventory_db() as conn:
        cur = _dict_cursor(conn)
        cur.execute(f"""
            SELECT {_USER_COLUMNS}
            FROM users WHERE email = %s
        """, (email,))
        row = cur.fetchone()
        return dict(row) if row else None


def authenticate_user(email: str, password: str):
    """
    Verify credentials for login. Returns the user (never including password_hash)
    plus their assigned role names on success, or None if the email doesn't exist,
    has no password set, is inactive, or the password doesn't match.
    """
    with get_inventory_db() as conn:
        cur = _dict_cursor(conn)
        cur.execute(f"""
            SELECT {_USER_COLUMNS}, password_hash
            FROM users WHERE email = %s
        """, (email,))
        row = cur.fetchone()
        if not row:
            return None
        row = dict(row)
        password_hash = row.pop("password_hash")
        if not row["is_active"]:
            return None
        if not password_hash or not verify_password(password, password_hash):
            return None

        cur.execute("""
            SELECT r.name FROM platform_user_roles pur
            JOIN roles r ON r.id = pur.role_id
            WHERE pur.user_id = %s
            ORDER BY r.name
        """, (row["id"],))
        row["roles"] = [r["name"] for r in cur.fetchall()]
        return row


def list_roles() -> list:
    with get_inventory_db() as conn:
        cur = _dict_cursor(conn)
        cur.execute("""
            SELECT id, name, description, scope, created_at
            FROM roles
            ORDER BY name
        """)
        return [dict(r) for r in cur.fetchall()]


def list_user_roles() -> list:
    """Role assignments joined against users/roles for a readable view."""
    with get_inventory_db() as conn:
        cur = _dict_cursor(conn)
        cur.execute("""
            SELECT pur.user_id, u.email, u.first_name, u.last_name,
                   pur.role_id, r.name AS role_name, r.scope AS role_scope,
                   pur.created_at AS assigned_at
            FROM platform_user_roles pur
            JOIN users u ON u.id = pur.user_id
            JOIN roles r ON r.id = pur.role_id
            ORDER BY pur.created_at DESC
        """)
        return [dict(r) for r in cur.fetchall()]


def get_roles_for_user(user_id: str) -> list:
    with get_inventory_db() as conn:
        cur = _dict_cursor(conn)
        cur.execute("""
            SELECT r.id, r.name, r.description, r.scope, pur.created_at AS assigned_at
            FROM platform_user_roles pur
            JOIN roles r ON r.id = pur.role_id
            WHERE pur.user_id = %s
            ORDER BY r.name
        """, (user_id,))
        return [dict(r) for r in cur.fetchall()]


# ── Passwords ─────────────────────────────────────────────────────────────────

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    if not password_hash:
        return False
    return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))


# ── Organizations ────────────────────────────────────────────────────────────

def create_organization(
    name: str,
    admin_email: str,
    admin_password: str,
    admin_first_name: str,
    admin_last_name: str = None,
    created_by: str = None,
) -> dict:
    """
    Create an Organization together with its first user — the Organization Admin
    (TENANT_USER, role ORGANIZATION_ADMIN). Both rows are created in one transaction:
    either the whole thing succeeds, or nothing is created.
    """
    with get_inventory_db() as conn:
        cur = _dict_cursor(conn)
        try:
            cur.execute("""
                INSERT INTO organizations (name, created_by)
                VALUES (%s, %s)
                RETURNING id, name, is_active, created_by, created_at, updated_at
            """, (name, created_by))
            org = dict(cur.fetchone())

            cur.execute("SELECT id FROM roles WHERE name = 'ORGANIZATION_ADMIN'")
            role_row = cur.fetchone()
            if not role_row:
                raise ValueError("ORGANIZATION_ADMIN role not found — was the schema migration run?")
            org_admin_role_id = role_row["id"]

            password_hash = hash_password(admin_password)
            cur.execute(f"""
                INSERT INTO users (email, first_name, last_name, password_hash, user_type, organization_id)
                VALUES (%s, %s, %s, %s, 'TENANT_USER', %s)
                RETURNING {_USER_COLUMNS}
            """, (admin_email, admin_first_name, admin_last_name, password_hash, org["id"]))
            admin_user = dict(cur.fetchone())

            cur.execute("""
                INSERT INTO platform_user_roles (user_id, role_id)
                VALUES (%s, %s)
            """, (admin_user["id"], org_admin_role_id))

            conn.commit()
        except psycopg2.errors.UniqueViolation:
            conn.rollback()
            raise ValueError(f"A user with email '{admin_email}' already exists.")
        except Exception:
            conn.rollback()
            raise

        return {"organization": org, "admin_user": admin_user}


def list_organizations() -> list:
    with get_inventory_db() as conn:
        cur = _dict_cursor(conn)
        cur.execute("""
            SELECT id, name, is_active, created_by, created_at, updated_at
            FROM organizations
            ORDER BY created_at DESC
        """)
        return [dict(r) for r in cur.fetchall()]


def get_organization(organization_id: str):
    with get_inventory_db() as conn:
        cur = _dict_cursor(conn)
        cur.execute("""
            SELECT id, name, is_active, created_by, created_at, updated_at
            FROM organizations WHERE id = %s
        """, (organization_id,))
        row = cur.fetchone()
        return dict(row) if row else None


# ── Sites ────────────────────────────────────────────────────────────────────

def create_site(
    organization_id: str,
    name: str,
    address_line: str = None,
    city: str = None,
    state: str = None,
    country: str = None,
    postal_code: str = None,
) -> dict:
    with get_inventory_db() as conn:
        cur = _dict_cursor(conn)
        try:
            cur.execute("""
                INSERT INTO sites (organization_id, name, address_line, city, state, country, postal_code)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                RETURNING id, organization_id, name, address_line, city, state, country,
                          postal_code, is_active, created_at, updated_at
            """, (organization_id, name, address_line, city, state, country, postal_code))
            site = dict(cur.fetchone())
            conn.commit()
            return site
        except psycopg2.errors.ForeignKeyViolation:
            conn.rollback()
            raise ValueError(f"No organization found with id '{organization_id}'.")
        except Exception:
            conn.rollback()
            raise


def list_sites(organization_id: str) -> list:
    with get_inventory_db() as conn:
        cur = _dict_cursor(conn)
        cur.execute("""
            SELECT id, organization_id, name, address_line, city, state, country,
                   postal_code, is_active, created_at, updated_at
            FROM sites
            WHERE organization_id = %s
            ORDER BY name
        """, (organization_id,))
        return [dict(r) for r in cur.fetchall()]


def get_site(site_id: str):
    with get_inventory_db() as conn:
        cur = _dict_cursor(conn)
        cur.execute("""
            SELECT id, organization_id, name, address_line, city, state, country,
                   postal_code, is_active, created_at, updated_at
            FROM sites WHERE id = %s
        """, (site_id,))
        row = cur.fetchone()
        return dict(row) if row else None


# ── Employees ────────────────────────────────────────────────────────────────

_ORG_EMPLOYEE_ROLES = {"IT_MANAGER", "IT_PROFESSIONAL", "IT_TECHNICIAN", "ORGANIZATION_ADMIN"}


def create_employee(
    organization_id: str,
    email: str,
    password: str,
    first_name: str,
    last_name: str,
    role_name: str,
    site_id: str = None,
) -> dict:
    """
    Create an employee (TENANT_USER) for an organization, optionally tied to one
    of that same organization's sites, with one org-scoped role assigned.
    """
    if role_name not in _ORG_EMPLOYEE_ROLES:
        raise ValueError(f"'{role_name}' is not a valid organization employee role. Must be one of: {sorted(_ORG_EMPLOYEE_ROLES)}")

    with get_inventory_db() as conn:
        cur = _dict_cursor(conn)
        try:
            # A site must belong to the same organization as the employee being added.
            if site_id:
                cur.execute("SELECT organization_id FROM sites WHERE id = %s", (site_id,))
                site_row = cur.fetchone()
                if not site_row:
                    raise ValueError(f"No site found with id '{site_id}'.")
                if str(site_row["organization_id"]) != str(organization_id):
                    raise ValueError("That site belongs to a different organization.")

            cur.execute("SELECT id FROM roles WHERE name = %s AND scope = 'ORGANIZATION'", (role_name,))
            role_row = cur.fetchone()
            if not role_row:
                raise ValueError(f"Role '{role_name}' not found.")

            password_hash = hash_password(password)
            cur.execute(f"""
                INSERT INTO users (email, first_name, last_name, password_hash, user_type, organization_id, site_id)
                VALUES (%s, %s, %s, %s, 'TENANT_USER', %s, %s)
                RETURNING {_USER_COLUMNS}
            """, (email, first_name, last_name, password_hash, organization_id, site_id))
            employee = dict(cur.fetchone())

            cur.execute("""
                INSERT INTO platform_user_roles (user_id, role_id)
                VALUES (%s, %s)
            """, (employee["id"], role_row["id"]))

            conn.commit()
            return employee
        except psycopg2.errors.UniqueViolation:
            conn.rollback()
            raise ValueError(f"A user with email '{email}' already exists.")
        except psycopg2.errors.ForeignKeyViolation:
            conn.rollback()
            raise ValueError(f"No organization found with id '{organization_id}'.")
        except Exception:
            conn.rollback()
            raise


_USER_COLUMNS_QUALIFIED = """
    u.id, u.email, u.first_name, u.last_name, u.user_type,
    u.is_active, u.email_verified, u.last_login_at,
    u.organization_id, u.site_id, u.created_at, u.updated_at
"""


def list_employees(organization_id: str, site_id: str = None) -> list:
    """Employees of an organization (optionally filtered to one site), each with their role names."""
    with get_inventory_db() as conn:
        cur = _dict_cursor(conn)
        query = f"""
            SELECT {_USER_COLUMNS_QUALIFIED},
                   COALESCE(
                       ARRAY_AGG(r.name) FILTER (WHERE r.name IS NOT NULL),
                       ARRAY[]::varchar[]
                   ) AS roles
            FROM users u
            LEFT JOIN platform_user_roles pur ON pur.user_id = u.id
            LEFT JOIN roles r ON r.id = pur.role_id
            WHERE u.organization_id = %s
        """
        params = [organization_id]
        if site_id:
            query += " AND u.site_id = %s"
            params.append(site_id)
        query += " GROUP BY u.id ORDER BY u.created_at DESC"
        cur.execute(query, params)
        return [dict(r) for r in cur.fetchall()]


# ── Full nested view ─────────────────────────────────────────────────────────

def get_organization_detail(organization_id: str):
    """
    Everything about one organization in a single call: the org itself, each of
    its sites with that site's employees nested inside, and any employees not
    tied to a specific site.
    """
    org = get_organization(organization_id)
    if not org:
        return None

    employees = list_employees(organization_id)
    sites = list_sites(organization_id)

    sites_by_id = {str(s["id"]): {**s, "employees": []} for s in sites}
    unassigned = []
    for emp in employees:
        sid = str(emp["site_id"]) if emp.get("site_id") else None
        if sid and sid in sites_by_id:
            sites_by_id[sid]["employees"].append(emp)
        else:
            unassigned.append(emp)

    org["sites"] = list(sites_by_id.values())
    org["unassigned_employees"] = unassigned
    return org


# ── WiFi Networks ────────────────────────────────────────────────────────────

_WIFI_NETWORK_COLUMNS = """
    id, organization_id, site_id, ssid, authentication, encryption, signal,
    is_connected, last_connected_at, created_at, updated_at
"""


def upsert_wifi_network(
    organization_id: str,
    ssid: str,
    site_id: str = None,
    authentication: str = None,
    encryption: str = None,
    signal: str = None,
    password: str = None,
    mark_connected: bool = False,
) -> dict:
    """
    Insert or refresh a network's catalog entry for an organization (+ site).
    Called both when just listing available networks (no password) and when
    connecting (password + mark_connected=True updates the same row).
    Never returns the password.
    """
    with get_inventory_db() as conn:
        cur = _dict_cursor(conn)
        try:
            cur.execute(f"""
                INSERT INTO wifi_networks
                    (organization_id, site_id, ssid, authentication, encryption, signal,
                     password, is_connected, last_connected_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s,
                        CASE WHEN %s THEN CURRENT_TIMESTAMP ELSE NULL END, CURRENT_TIMESTAMP)
                ON CONFLICT (organization_id, site_id, ssid) DO UPDATE SET
                    authentication     = COALESCE(EXCLUDED.authentication, wifi_networks.authentication),
                    encryption         = COALESCE(EXCLUDED.encryption, wifi_networks.encryption),
                    signal             = COALESCE(EXCLUDED.signal, wifi_networks.signal),
                    password           = COALESCE(EXCLUDED.password, wifi_networks.password),
                    is_connected       = wifi_networks.is_connected OR EXCLUDED.is_connected,
                    last_connected_at  = COALESCE(EXCLUDED.last_connected_at, wifi_networks.last_connected_at),
                    updated_at         = CURRENT_TIMESTAMP
                RETURNING {_WIFI_NETWORK_COLUMNS}
            """, (organization_id, site_id, ssid, authentication, encryption, signal,
                  password, mark_connected, mark_connected))
            row = dict(cur.fetchone())
            conn.commit()
            return row
        except psycopg2.errors.ForeignKeyViolation:
            conn.rollback()
            raise ValueError(f"No organization found with id '{organization_id}'.")
        except Exception:
            conn.rollback()
            raise


def upsert_wifi_networks_bulk(organization_id: str, networks: list, site_id: str = None) -> list:
    """Convenience wrapper for storing a whole 'Available WiFi Networks' scan result at once."""
    return [
        upsert_wifi_network(
            organization_id=organization_id,
            ssid=n["ssid"],
            site_id=site_id,
            authentication=n.get("authentication"),
            encryption=n.get("encryption"),
            signal=n.get("signal"),
        )
        for n in networks
    ]


def list_wifi_networks(organization_id: str, site_id: str = None) -> list:
    """Networks known for an org (+ site), most recently updated first. Never includes password."""
    with get_inventory_db() as conn:
        cur = _dict_cursor(conn)
        query = f"SELECT {_WIFI_NETWORK_COLUMNS} FROM wifi_networks WHERE organization_id = %s"
        params = [organization_id]
        if site_id:
            query += " AND site_id = %s"
            params.append(site_id)
        query += " ORDER BY updated_at DESC"
        cur.execute(query, params)
        return [dict(r) for r in cur.fetchall()]


def get_wifi_network_with_password(wifi_network_id: str):
    """Internal use only (e.g. reconnect flows) — includes the stored password.
    Never expose this response directly from an API endpoint."""
    with get_inventory_db() as conn:
        cur = _dict_cursor(conn)
        cur.execute(f"""
            SELECT {_WIFI_NETWORK_COLUMNS}, password
            FROM wifi_networks WHERE id = %s
        """, (wifi_network_id,))
        row = cur.fetchone()
        return dict(row) if row else None


# ── Network Scans ────────────────────────────────────────────────────────────

_SCAN_COLUMNS = """
    id, organization_id, site_id, performed_by, wifi_network_id, ssid,
    ip_address, subnet, status, device_count, started_at, completed_at
"""

_SCAN_DEVICE_COLUMNS = """
    id, scan_id, ip_address, hostname, mac_address, username,
    operating_system, device_type, open_ports, audit_status, status, discovered_at
"""


def record_network_scan(
    organization_id: str,
    performed_by: str,
    ssid: str,
    devices: list,
    site_id: str = None,
    wifi_network_id: str = None,
    ip_address: str = None,
    subnet: str = None,
) -> dict:
    """
    Persist one 'Connect & Scan' action: the scan row plus every device it found,
    in a single transaction. `devices` is a list of dicts, each optionally containing:
    ip_address, hostname, mac_address, username, operating_system, device_type,
    open_ports (list[str]), audit_status, status.
    """
    with get_inventory_db() as conn:
        cur = _dict_cursor(conn)
        try:
            cur.execute(f"""
                INSERT INTO network_scans
                    (organization_id, site_id, performed_by, wifi_network_id, ssid,
                     ip_address, subnet, status, device_count, completed_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, 'completed', %s, CURRENT_TIMESTAMP)
                RETURNING {_SCAN_COLUMNS}
            """, (organization_id, site_id, performed_by, wifi_network_id, ssid,
                  ip_address, subnet, len(devices)))
            scan = dict(cur.fetchone())

            device_rows = []
            for d in devices:
                cur.execute(f"""
                    INSERT INTO scan_devices
                        (scan_id, ip_address, hostname, mac_address, username,
                         operating_system, device_type, open_ports, audit_status, status)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING {_SCAN_DEVICE_COLUMNS}
                """, (
                    scan["id"], d.get("ip_address") or d.get("ip"), d.get("hostname"), d.get("mac_address"),
                    d.get("username"), d.get("operating_system"), d.get("device_type"),
                    psycopg2.extras.Json(d.get("open_ports") or d.get("port_labels") or []),
                    d.get("audit_status"), d.get("status"),
                ))
                device_rows.append(dict(cur.fetchone()))

            conn.commit()
            scan["devices"] = device_rows
            return scan
        except psycopg2.errors.ForeignKeyViolation as e:
            conn.rollback()
            raise ValueError(f"Invalid reference while recording scan: {e}")
        except Exception:
            conn.rollback()
            raise


def get_scan(scan_id: str):
    """One scan plus every device it found."""
    with get_inventory_db() as conn:
        cur = _dict_cursor(conn)
        cur.execute(f"SELECT {_SCAN_COLUMNS} FROM network_scans WHERE id = %s", (scan_id,))
        row = cur.fetchone()
        if not row:
            return None
        scan = dict(row)
        cur.execute(f"""
            SELECT {_SCAN_DEVICE_COLUMNS} FROM scan_devices
            WHERE scan_id = %s ORDER BY discovered_at
        """, (scan_id,))
        scan["devices"] = [dict(r) for r in cur.fetchall()]
        return scan


def list_scans(organization_id: str, site_id: str = None) -> list:
    """Scan history for an org (+ site), most recent first. No nested devices — use get_scan() for that."""
    with get_inventory_db() as conn:
        cur = _dict_cursor(conn)
        query = f"SELECT {_SCAN_COLUMNS} FROM network_scans WHERE organization_id = %s"
        params = [organization_id]
        if site_id:
            query += " AND site_id = %s"
            params.append(site_id)
        query += " ORDER BY started_at DESC"
        cur.execute(query, params)
        return [dict(r) for r in cur.fetchall()]
