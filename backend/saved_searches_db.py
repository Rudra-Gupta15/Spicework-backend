"""
Saved search queries, saved from the filter bar on the Hardware/Software/
Cloud Assets/Network pages and re-listed on the Saved Search page.

Lives in the "sw inventory" Postgres database alongside the rest of the
newer app data — see auth_db.py for the shared connection helper.
"""
import psycopg2.extras

from backend.auth_db import _dict_cursor, get_inventory_db

_COLUMNS = "id, category, name, scope, applied_filters, results_count, created_by, created_at"


def create_saved_search(
    category: str,
    name: str,
    scope: str,
    applied_filters: list,
    results_count: int,
    created_by: str,
) -> dict:
    with get_inventory_db() as conn:
        cur = _dict_cursor(conn)
        cur.execute(f"""
            INSERT INTO saved_searches (category, name, scope, applied_filters, results_count, created_by)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING {_COLUMNS}
        """, (category, name, scope, psycopg2.extras.Json(applied_filters), results_count, created_by))
        row = dict(cur.fetchone())
        conn.commit()
        return row


def list_saved_searches(category: str = None) -> list:
    with get_inventory_db() as conn:
        cur = _dict_cursor(conn)
        if category:
            cur.execute(f"SELECT {_COLUMNS} FROM saved_searches WHERE category = %s ORDER BY created_at DESC", (category,))
        else:
            cur.execute(f"SELECT {_COLUMNS} FROM saved_searches ORDER BY created_at DESC")
        return [dict(r) for r in cur.fetchall()]


def get_saved_search(search_id: str):
    with get_inventory_db() as conn:
        cur = _dict_cursor(conn)
        cur.execute(f"SELECT {_COLUMNS} FROM saved_searches WHERE id = %s", (search_id,))
        row = cur.fetchone()
        return dict(row) if row else None


def delete_saved_search(search_id: str) -> bool:
    with get_inventory_db() as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM saved_searches WHERE id = %s", (search_id,))
        deleted = cur.rowcount > 0
        conn.commit()
        return deleted
