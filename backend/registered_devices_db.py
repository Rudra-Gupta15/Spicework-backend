"""
The registered device estate: units an organization owns and hands out, and
the trail of who has held each one.

Backed by the same inventory PostgreSQL database as auth_db, and reusing its
connection helper so there is one place credentials come from. Every read and
write here is scoped to an organization_id — the caller's, taken from their
token, never from the request body.

Distinct from hardware_devices/device_inventory_current, which are machines an
agent audited. A unit here exists because someone bought it and typed it in; it
may never run an agent at all.

See migrations/001_registered_devices.sql for the schema.
"""
import psycopg2.errors

from backend.auth_db import _dict_cursor, get_inventory_db

CATEGORIES = ("Laptop", "Printer", "Projector", "Desktop")

# A unit's current holder is whoever has an assignment still open. Derived on
# read rather than denormalized onto the device, so the row and its history can
# never disagree about who is holding it.
_CURRENT_USER_SQL = """
    COALESCE((
        SELECT a.user_name FROM device_assignments a
        WHERE a.device_id = d.id AND a.returned_on IS NULL
        ORDER BY a.assigned_on DESC
        LIMIT 1
    ), '') AS current_user_name
"""

_DEVICE_COLUMNS = f"""
    d.id, d.organization_id, d.site_id, d.category, d.name,
    d.serial_number, d.buy_date, d.created_at, d.updated_at,
    {_CURRENT_USER_SQL}
"""


class DeviceError(ValueError):
    """A failure the caller can fix — a duplicate serial, an unknown category."""


def list_devices(organization_id: str, category: str = None) -> list:
    """
    Every unit the organization has registered, newest first — the same order
    the screen adds them in, so a unit just registered is at the top.
    """
    clauses = ["d.organization_id = %s"]
    params = [organization_id]

    if category:
        clauses.append("d.category = %s")
        params.append(category)

    with get_inventory_db() as conn:
        cur = _dict_cursor(conn)
        cur.execute(f"""
            SELECT {_DEVICE_COLUMNS}
            FROM registered_devices d
            WHERE {" AND ".join(clauses)}
            ORDER BY d.created_at DESC, d.name
        """, params)
        return [dict(r) for r in cur.fetchall()]


def get_device(organization_id: str, device_id: str):
    """
    Scoped by organization on purpose: a device id belonging to another tenant
    reads as missing rather than as forbidden, which avoids confirming that the
    id exists at all.
    """
    with get_inventory_db() as conn:
        cur = _dict_cursor(conn)
        cur.execute(f"""
            SELECT {_DEVICE_COLUMNS}
            FROM registered_devices d
            WHERE d.id = %s AND d.organization_id = %s
        """, (device_id, organization_id))
        row = cur.fetchone()
        return dict(row) if row else None


def create_device(
    organization_id: str,
    category: str,
    name: str,
    serial_number: str,
    buy_date: str = None,
    current_user: str = None,
    site_id: str = None,
) -> dict:
    """
    Register a unit. Naming a holder opens their assignment in the same
    transaction, so the unit is never briefly registered-but-unassigned in a
    way another request could observe.
    """
    if category not in CATEGORIES:
        raise DeviceError(
            f"Unknown device type '{category}'. Expected one of: {', '.join(CATEGORIES)}."
        )

    with get_inventory_db() as conn:
        cur = _dict_cursor(conn)
        try:
            cur.execute("""
                INSERT INTO registered_devices
                    (organization_id, site_id, category, name, serial_number, buy_date)
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING id
            """, (organization_id, site_id, category, name, serial_number, buy_date or None))
            device_id = cur.fetchone()["id"]

            if current_user:
                cur.execute("""
                    INSERT INTO device_assignments (device_id, user_name, assigned_on, note)
                    VALUES (%s, %s, COALESCE(%s, CURRENT_DATE), %s)
                """, (
                    device_id,
                    current_user,
                    buy_date or None,
                    "Issued when the device was registered",
                ))

            conn.commit()
        except psycopg2.errors.UniqueViolation:
            conn.rollback()
            raise DeviceError(f"Serial '{serial_number}' is already registered.")
        except Exception:
            conn.rollback()
            raise

    return get_device(organization_id, device_id)


def update_device(
    organization_id: str,
    device_id: str,
    category: str,
    name: str,
    serial_number: str,
    buy_date: str = None,
) -> dict:
    """
    Rename, re-serial, re-categorize or re-date an already-registered unit.

    Assignment is deliberately not a parameter here: who holds the device is
    derived from `device_assignments`, and changing it belongs to
    `assign_device`/`return_device` so the hand-off trail stays a real history
    rather than a field a form can silently overwrite.
    """
    if category not in CATEGORIES:
        raise DeviceError(
            f"Unknown device type '{category}'. Expected one of: {', '.join(CATEGORIES)}."
        )

    with get_inventory_db() as conn:
        cur = _dict_cursor(conn)
        try:
            cur.execute("""
                UPDATE registered_devices
                SET category = %s, name = %s, serial_number = %s,
                    buy_date = %s, updated_at = now()
                WHERE id = %s AND organization_id = %s
                RETURNING id
            """, (category, name, serial_number, buy_date or None, device_id, organization_id))
            row = cur.fetchone()
            if not row:
                conn.rollback()
                raise DeviceError("That device is not registered to your organization.")
            conn.commit()
        except psycopg2.errors.UniqueViolation:
            conn.rollback()
            raise DeviceError(f"Serial '{serial_number}' is already registered.")
        except DeviceError:
            raise
        except Exception:
            conn.rollback()
            raise

    return get_device(organization_id, device_id)


def list_assignments(organization_id: str, device_id: str) -> list:
    """
    Who has held the unit, newest spell first. Returns [] both for a device
    that has never been issued and for one that isn't the caller's — callers
    that need to tell those apart check the device itself.
    """
    with get_inventory_db() as conn:
        cur = _dict_cursor(conn)
        cur.execute("""
            SELECT a.id, a.user_name, a.assigned_on, a.returned_on, a.note, a.created_at
            FROM device_assignments a
            JOIN registered_devices d ON d.id = a.device_id
            WHERE a.device_id = %s AND d.organization_id = %s
            ORDER BY a.assigned_on DESC, a.created_at DESC
        """, (device_id, organization_id))
        return [dict(r) for r in cur.fetchall()]


def assign_device(
    organization_id: str,
    device_id: str,
    user_name: str,
    assigned_on: str = None,
    note: str = None,
) -> list:
    """
    Hand the unit to someone. Any open spell is closed as the new one starts,
    so the history reads as a continuous chain rather than as two overlapping
    holders. Returns the device's full history.
    """
    with get_inventory_db() as conn:
        cur = _dict_cursor(conn)
        try:
            cur.execute(
                "SELECT 1 FROM registered_devices WHERE id = %s AND organization_id = %s",
                (device_id, organization_id),
            )
            if not cur.fetchone():
                raise DeviceError("That device is not registered to your organization.")

            # GREATEST keeps the closing date from landing before the spell
            # started, which the table's own CHECK would reject anyway.
            cur.execute("""
                UPDATE device_assignments
                SET returned_on = GREATEST(assigned_on, COALESCE(%s, CURRENT_DATE))
                WHERE device_id = %s AND returned_on IS NULL
            """, (assigned_on or None, device_id))

            cur.execute("""
                INSERT INTO device_assignments (device_id, user_name, assigned_on, note)
                VALUES (%s, %s, COALESCE(%s, CURRENT_DATE), %s)
            """, (device_id, user_name, assigned_on or None, note))

            conn.commit()
        except psycopg2.errors.UniqueViolation:
            conn.rollback()
            raise DeviceError("That device is already out with someone.")
        except Exception:
            conn.rollback()
            raise

    return list_assignments(organization_id, device_id)


def return_device(
    organization_id: str,
    device_id: str,
    returned_on: str = None,
    note: str = None,
) -> list:
    """Take the unit back into the store, closing whoever's spell is open."""
    with get_inventory_db() as conn:
        cur = _dict_cursor(conn)
        try:
            cur.execute("""
                UPDATE device_assignments a
                SET returned_on = GREATEST(a.assigned_on, COALESCE(%s, CURRENT_DATE)),
                    note = COALESCE(%s, a.note)
                FROM registered_devices d
                WHERE d.id = a.device_id
                  AND a.device_id = %s
                  AND d.organization_id = %s
                  AND a.returned_on IS NULL
            """, (returned_on or None, note, device_id, organization_id))
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    return list_assignments(organization_id, device_id)


def delete_device(organization_id: str, device_id: str) -> bool:
    """Remove the unit and its history (assignments cascade). True if it existed."""
    with get_inventory_db() as conn:
        cur = conn.cursor()
        cur.execute(
            "DELETE FROM registered_devices WHERE id = %s AND organization_id = %s",
            (device_id, organization_id),
        )
        deleted = cur.rowcount > 0
        conn.commit()
        return deleted
