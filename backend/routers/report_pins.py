from fastapi import APIRouter

from backend import report_pins_db

router = APIRouter()


@router.get("/api/report-pins/{category}")
def get_pinned_systems(category: str):
    """Every system id pinned in this Reports category, oldest pin first."""
    return {"category": category, "system_ids": report_pins_db.list_pinned(category)}


@router.put("/api/report-pins/{category}/{system_id}")
def pin_system(category: str, system_id: str):
    report_pins_db.set_pinned(category, system_id, pinned=True)
    return {"category": category, "system_id": system_id, "pinned": True}


@router.delete("/api/report-pins/{category}/{system_id}")
def unpin_system(category: str, system_id: str):
    report_pins_db.set_pinned(category, system_id, pinned=False)
    return {"category": category, "system_id": system_id, "pinned": False}
