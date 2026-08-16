import json

from fastapi import APIRouter
from pydantic import BaseModel

from backend.core.config import DB_PATH
from backend.db import get_db

router = APIRouter()


class ViewColumnsRequest(BaseModel):
    columns: list[str]


def _key(view_name: str) -> str:
    return f"view_columns_{view_name}"


@router.get("/api/view-preferences/{view_name}")
def get_view_columns(view_name: str):
    """App-wide (not per-user) saved column selection for a table view, e.g. 'hardware' or 'software'."""
    with get_db(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM portal_settings WHERE key = ?", (_key(view_name),))
        row = cursor.fetchone()
    if not row:
        return {"view_name": view_name, "columns": None}
    return {"view_name": view_name, "columns": json.loads(row[0])}


@router.post("/api/view-preferences/{view_name}")
def save_view_columns(view_name: str, data: ViewColumnsRequest):
    with get_db(DB_PATH) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO portal_settings (key, value) VALUES (?, ?)",
            (_key(view_name), json.dumps(data.columns)),
        )
        conn.commit()
    return {"status": "saved", "view_name": view_name, "columns": data.columns}
