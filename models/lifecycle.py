from pydantic import BaseModel


class LifecycleData(BaseModel):
    mac_address: str
    computer_name: str = ""
    owner: str = ""
    location: str = ""
    vendor: str = ""
    status: str = "Active"
    warranty_start: str = ""
    warranty_end: str = ""
    warranty_notes: str = ""
    warranty_provider: str = ""
    purchase_price: str = ""
    purchase_date: str = ""
    supplier: str = ""
    po_number: str = ""


class TicketData(BaseModel):
    mac_address: str
    computer_name: str = ""
    ticket_number: str = ""
    summary: str = ""
    status: str = "Open"
    assigned: str = ""
    priority: str = "Medium"
    mtbf: str = ""
