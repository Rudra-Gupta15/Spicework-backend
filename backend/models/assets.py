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
