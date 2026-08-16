from fastapi import APIRouter
from pydantic import BaseModel

from backend import view_preferences_db

router = APIRouter()


class ViewColumnsRequest(BaseModel):
    columns: list[str]


@router.get("/api/view-preferences/{view_name}")
def get_view_columns(view_name: str):
    """App-wide (not per-user) saved column selection for a table view, e.g. 'hardware' or 'software'."""
    columns = view_preferences_db.get_view_columns(view_name)
    return {"view_name": view_name, "columns": columns}


@router.post("/api/view-preferences/{view_name}")
def save_view_columns(view_name: str, data: ViewColumnsRequest):
    view_preferences_db.save_view_columns(view_name, data.columns)
    return {"status": "saved", "view_name": view_name, "columns": data.columns}
