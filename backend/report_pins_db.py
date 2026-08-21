"""
Pinned systems on the Reports list — "show this one above everyone else",
the same way a favorite works.

App-wide rather than per-user, the same choice `view_preferences` makes:
there is no per-user account model on this side of the app yet, so a shared
list is what "pin" can mean today.
"""
from backend.auth_db import _dict_cursor, get_inventory_db


def list_pinned(category: str) -> list[str]:
    with get_inventory_db() as conn:
        cur = _dict_cursor(conn)
        cur.execute(
            "SELECT system_id FROM report_pins WHERE category = %s ORDER BY pinned_at",
            (category,),
        )
        return [row["system_id"] for row in cur.fetchall()]


def set_pinned(category: str, system_id: str, pinned: bool) -> None:
    with get_inventory_db() as conn:
        cur = conn.cursor()
        if pinned:
            cur.execute(
                """
                INSERT INTO report_pins (category, system_id)
                VALUES (%s, %s)
                ON CONFLICT (category, system_id) DO NOTHING
                """,
                (category, system_id),
            )
        else:
            cur.execute(
                "DELETE FROM report_pins WHERE category = %s AND system_id = %s",
                (category, system_id),
            )
        conn.commit()
