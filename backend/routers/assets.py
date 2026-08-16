from datetime import datetime

from fastapi import APIRouter, HTTPException

from backend import legacy_db
from backend.core.config import logger
from backend.models.assets import AssetMetadata
from backend.services.common import model_to_dict

router = APIRouter()


@router.post("/asset-metadata")
def save_asset_metadata(metadata: AssetMetadata):
    metadata.last_updated = datetime.now().isoformat()
    try:
        fields = model_to_dict(metadata)
        legacy_db.save_asset_metadata(metadata.device_id, fields)
        logger.info(f"Asset metadata saved: {metadata.device_id}")
        return {"status": "saved", "device_id": metadata.device_id}
    except Exception as e:
        logger.error(f"Failed to save asset metadata: {e}")
        raise HTTPException(status_code=500, detail="Failed to save metadata.")


@router.get("/asset-metadata/{device_id}")
def get_asset_metadata(device_id: str):
    row = legacy_db.get_asset_metadata(device_id)
    if not row:
        raise HTTPException(status_code=404, detail="Asset not found.")
    return row


@router.put("/asset-metadata/{device_id}")
def update_asset_metadata(device_id: str, metadata: AssetMetadata):
    metadata.device_id = device_id
    metadata.last_updated = datetime.now().isoformat()
    fields = model_to_dict(metadata)
    legacy_db.save_asset_metadata(device_id, fields)
    return {"status": "updated", "device_id": device_id}


@router.delete("/asset-metadata/{device_id}")
def delete_asset_metadata(device_id: str):
    if not legacy_db.delete_asset_metadata(device_id):
        raise HTTPException(status_code=404, detail="Asset not found.")
    return {"status": "deleted", "device_id": device_id}


@router.get("/assets")
def list_assets():
    assets = legacy_db.list_asset_metadata()
    return {"assets": assets, "total": len(assets)}
