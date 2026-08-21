"""
Per-row corrections for the list sections of a device's Hardware Report and
Hardware Detail tabs — Disk Partitions, Network Adapters, Peripherals,
Printers, Video Controllers, User Accounts.

Distinct from `asset_metadata`'s hardware-spec overrides: those are six fixed
fields on one record. These are arbitrary rows the agent regenerates on every
scan, so a correction is stored generically — device, section, the row's own
natural identity (a MAC, a drive letter, a username), and a small bag of
field: value corrections for that row. Which fields exist, and what they
mean, is entirely the frontend's business; nothing here assumes a schema.
"""
import psycopg2.extras

from backend.auth_db import _dict_cursor, get_inventory_db


def get_overrides(device_id: str) -> dict:
    """Nested `{section: {row_key: {field: value}}}` for one device."""
    with get_inventory_db() as conn:
        cur = _dict_cursor(conn)
        cur.execute(
            "SELECT section, row_key, fields FROM row_field_overrides WHERE device_id = %s",
            (device_id,),
        )
        result: dict = {}
        for row in cur.fetchall():
            result.setdefault(row["section"], {})[row["row_key"]] = row["fields"]
        return result


def set_override(device_id: str, section: str, row_key: str, fields: dict) -> None:
    """
    Replaces one row's correction bag. An empty `fields` deletes it outright —
    that is how a correction is withdrawn, rather than leaving a row_key
    pointing at nothing for a field left blank.
    """
    with get_inventory_db() as conn:
        cur = conn.cursor()
        if fields:
            cur.execute(
                """
                INSERT INTO row_field_overrides (device_id, section, row_key, fields, updated_at)
                VALUES (%s, %s, %s, %s, now())
                ON CONFLICT (device_id, section, row_key)
                    DO UPDATE SET fields = EXCLUDED.fields, updated_at = now()
                """,
                (device_id, section, row_key, psycopg2.extras.Json(fields)),
            )
        else:
            cur.execute(
                "DELETE FROM row_field_overrides WHERE device_id = %s AND section = %s AND row_key = %s",
                (device_id, section, row_key),
            )
        conn.commit()
