"""
Per-view column selection for Customize View (Hardware/Software tables).

Lives in the "sw inventory" Postgres database alongside the rest of the
newer app data — see auth_db.py for the shared connection helper.
"""
import psycopg2.extras

from backend.auth_db import _dict_cursor, get_inventory_db


def get_view_columns(view_name: str) -> list | None:
    with get_inventory_db() as conn:
        cur = _dict_cursor(conn)
        cur.execute("SELECT columns FROM view_preferences WHERE view_name = %s", (view_name,))
        row = cur.fetchone()
        return row["columns"] if row else None


def save_view_columns(view_name: str, columns: list) -> None:
    with get_inventory_db() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO view_preferences (view_name, columns, updated_at)
            VALUES (%s, %s, now())
            ON CONFLICT (view_name) DO UPDATE SET columns = EXCLUDED.columns, updated_at = EXCLUDED.updated_at
            """,
            (view_name, psycopg2.extras.Json(columns)),
        )
        conn.commit()
