from pydantic import BaseModel


class AssetMetadata(BaseModel):
    device_id: str
    asset_tag: str = ""
    owner: str = ""
    department: str = ""
    location: str = ""
    purchase_date: str = ""
    purchase_price: str = ""
    warranty_expiry: str = ""
    life_cycle_stage: str = "Active"
    vendor: str = ""
    notes: str = ""
    last_updated: str = ""
    # A human correction of a Hardware Specification field the agent misread.
    # Blank means "nothing to correct" — the scanned value stands as read.
    # Applied on top of the audit at read time (list + detail endpoints in
    # devices.py), the same precedence asset_tag/location_info already use,
    # so nothing downstream of those endpoints has to know this exists.
    cpu_override: str = ""
    ram_override: str = ""
    disk_override: str = ""
    serial_number_override: str = ""
    manufacturer_override: str = ""
    device_model_override: str = ""
