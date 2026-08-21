from fastapi import APIRouter

from backend import row_overrides_db
from backend.models.row_overrides import RowOverridesRequest

router = APIRouter()


@router.get("/api/devices/{device_id}/row-overrides")
def get_row_overrides(device_id: str):
    """Every saved correction for this device, nested by section then row."""
    return row_overrides_db.get_overrides(device_id)


@router.put("/api/devices/{device_id}/row-overrides/{section}")
def save_row_overrides(device_id: str, section: str, data: RowOverridesRequest):
    """
    Saves one or several rows' corrections in one call — the row's own
    identity travels in the body rather than the URL so a MAC address or a
    printer name with odd characters never has to survive path-encoding.
    """
    for update in data.updates:
        row_overrides_db.set_override(device_id, section, update.row_key, update.fields)
    return {"status": "saved", "count": len(data.updates)}
