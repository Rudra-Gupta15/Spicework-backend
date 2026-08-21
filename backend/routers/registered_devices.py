"""
The registered device estate behind /inventory/device.

Every route is scoped to the caller's own organization, read from their token
rather than taken from the path or body. That is deliberate: an organization id
in the URL would let anyone with a valid login enumerate another tenant's
estate just by changing it.
"""
from fastapi import APIRouter, Depends, HTTPException, Query, status

from backend import registered_devices_db as devices_db
from backend.core.security import get_current_user
from backend.models.registered_devices import (
    AssignDeviceRequest,
    AssignmentListResponse,
    CreateDeviceRequest,
    DeviceListResponse,
    RegisteredDevice,
    ReturnDeviceRequest,
    UpdateDeviceRequest,
)

router = APIRouter()


def _organization_id(claims: dict) -> str:
    """
    The caller's tenant. A user with no organization has no estate to look at —
    that is a real state for a platform-level account, so it is reported as a
    clear 403 rather than silently returning someone else's rows or an
    empty list that looks like "nothing registered yet".
    """
    organization_id = claims.get("organization_id")
    if not organization_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your account is not attached to an organization.",
        )
    return organization_id


@router.get("/api/registered-devices", response_model=DeviceListResponse)
def list_registered_devices(
    category: str = Query(None, description="Laptop | Printer | Projector | Desktop"),
    claims: dict = Depends(get_current_user),
):
    """
    The organization's units, newest first. The assignment filter the screen
    offers is applied client-side: the whole estate is already in hand for the
    tab counts, so filtering it again over the wire would only cost a round
    trip.
    """
    if category and category not in devices_db.CATEGORIES:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown device type '{category}'.",
        )

    return {"devices": devices_db.list_devices(_organization_id(claims), category)}


@router.post(
    "/api/registered-devices",
    response_model=RegisteredDevice,
    status_code=status.HTTP_201_CREATED,
)
def create_registered_device(
    data: CreateDeviceRequest,
    claims: dict = Depends(get_current_user),
):
    try:
        return devices_db.create_device(
            organization_id=_organization_id(claims),
            category=data.category.value,
            name=data.name.strip(),
            serial_number=data.serial_number.strip(),
            buy_date=data.buy_date,
            current_user=(data.current_user or "").strip() or None,
            site_id=str(data.site_id) if data.site_id else None,
        )
    except devices_db.DeviceError as e:
        # A duplicate serial is the one failure the person filling in the form
        # can actually resolve, so it comes back as a 409 they can act on.
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))


@router.get("/api/registered-devices/{device_id}", response_model=RegisteredDevice)
def get_registered_device(device_id: str, claims: dict = Depends(get_current_user)):
    device = devices_db.get_device(_organization_id(claims), device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found.")
    return device


@router.patch("/api/registered-devices/{device_id}", response_model=RegisteredDevice)
def update_registered_device(
    device_id: str,
    data: UpdateDeviceRequest,
    claims: dict = Depends(get_current_user),
):
    """Rename, re-serial, re-categorize or re-date an already-registered unit."""
    try:
        return devices_db.update_device(
            organization_id=_organization_id(claims),
            device_id=device_id,
            category=data.category.value,
            name=data.name.strip(),
            serial_number=data.serial_number.strip(),
            buy_date=data.buy_date,
        )
    except devices_db.DeviceError as e:
        status_code = (
            status.HTTP_404_NOT_FOUND
            if "not registered to your organization" in str(e)
            else status.HTTP_409_CONFLICT
        )
        raise HTTPException(status_code=status_code, detail=str(e))


@router.get(
    "/api/registered-devices/{device_id}/assignments",
    response_model=AssignmentListResponse,
)
def list_device_assignments(device_id: str, claims: dict = Depends(get_current_user)):
    """
    The hand-off trail. A device that has never been issued has an empty trail,
    which is a different thing from a device that does not exist — so the
    device is checked first and a missing one 404s.
    """
    organization_id = _organization_id(claims)
    if not devices_db.get_device(organization_id, device_id):
        raise HTTPException(status_code=404, detail="Device not found.")

    return {"assignments": devices_db.list_assignments(organization_id, device_id)}


@router.post(
    "/api/registered-devices/{device_id}/assignments",
    response_model=AssignmentListResponse,
)
def assign_registered_device(
    device_id: str,
    data: AssignDeviceRequest,
    claims: dict = Depends(get_current_user),
):
    """Hand the unit to someone, closing whoever holds it now."""
    try:
        assignments = devices_db.assign_device(
            organization_id=_organization_id(claims),
            device_id=device_id,
            user_name=data.user_name.strip(),
            assigned_on=data.assigned_on,
            note=(data.note or "").strip() or None,
        )
    except devices_db.DeviceError as e:
        raise HTTPException(status_code=404, detail=str(e))

    return {"assignments": assignments}


@router.post(
    "/api/registered-devices/{device_id}/return",
    response_model=AssignmentListResponse,
)
def return_registered_device(
    device_id: str,
    data: ReturnDeviceRequest,
    claims: dict = Depends(get_current_user),
):
    """Take the unit back into the store."""
    organization_id = _organization_id(claims)
    if not devices_db.get_device(organization_id, device_id):
        raise HTTPException(status_code=404, detail="Device not found.")

    return {
        "assignments": devices_db.return_device(
            organization_id=organization_id,
            device_id=device_id,
            returned_on=data.returned_on,
            note=(data.note or "").strip() or None,
        )
    }


@router.delete("/api/registered-devices/{device_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_registered_device(device_id: str, claims: dict = Depends(get_current_user)):
    if not devices_db.delete_device(_organization_id(claims), device_id):
        raise HTTPException(status_code=404, detail="Device not found.")
