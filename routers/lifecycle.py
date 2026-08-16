from fastapi import APIRouter, HTTPException

from backend import legacy_db
from backend.models.lifecycle import LifecycleData, TicketData

router = APIRouter()


@router.get("/api/lifecycle/{identifier}")
def get_lifecycle(identifier: str):
    return legacy_db.get_lifecycle(identifier)


@router.post("/api/lifecycle")
@router.post("/api/lifecycle/{identifier}")
def save_lifecycle(data: LifecycleData, identifier: str = ""):
    # If mac_address is not set in body but identifier is in URL, use it as computer_name key
    mac = data.mac_address or identifier or data.computer_name
    cname = data.computer_name or identifier
    fields = {
        "owner": data.owner, "location": data.location, "vendor": data.vendor, "status": data.status,
        "warranty_start": data.warranty_start, "warranty_end": data.warranty_end,
        "warranty_notes": data.warranty_notes, "warranty_provider": data.warranty_provider,
        "purchase_price": data.purchase_price, "purchase_date": data.purchase_date,
        "supplier": data.supplier, "po_number": data.po_number,
    }
    legacy_db.save_lifecycle(mac, cname, fields)
    return {"status": "saved"}


@router.get("/api/tickets/{mac_address}")
def get_tickets(mac_address: str):
    return legacy_db.list_tickets(mac_address)


@router.post("/api/tickets")
def create_ticket(data: TicketData):
    legacy_db.create_ticket(data.mac_address, data.computer_name, {
        "ticket_number": data.ticket_number, "summary": data.summary, "status": data.status,
        "assigned": data.assigned, "priority": data.priority, "mtbf": data.mtbf,
    })
    return {"status": "created"}


@router.put("/api/tickets/{ticket_id}")
def update_ticket(ticket_id: str, data: TicketData):
    row = legacy_db.update_ticket(ticket_id, {
        "summary": data.summary, "status": data.status, "assigned": data.assigned,
        "priority": data.priority, "mtbf": data.mtbf,
    })
    if not row:
        raise HTTPException(status_code=404, detail=f"No ticket found with id '{ticket_id}'.")
    return {"status": "updated"}


@router.delete("/api/tickets/{ticket_id}")
def delete_ticket(ticket_id: str):
    legacy_db.delete_ticket(ticket_id)
    return {"status": "deleted"}
