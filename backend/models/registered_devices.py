from datetime import date, datetime
from enum import Enum
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class DeviceCategory(str, Enum):
    LAPTOP = "Laptop"
    PRINTER = "Printer"
    PROJECTOR = "Projector"
    DESKTOP = "Desktop"


class DeviceAssignment(BaseModel):
    """One spell of ownership. The one with no returned_on is the current holder."""
    id: UUID
    user_name: str
    assigned_on: date
    returned_on: Optional[date] = None
    note: Optional[str] = None
    created_at: datetime


class RegisteredDevice(BaseModel):
    id: UUID
    organization_id: UUID
    site_id: Optional[UUID] = None
    category: DeviceCategory
    name: str
    serial_number: str
    buy_date: Optional[date] = None
    # Empty string while the unit sits in the store — the screen reads that as
    # "Unassigned". Derived from the open assignment, never stored on the row.
    current_user_name: str = ""
    created_at: datetime
    updated_at: datetime


class CreateDeviceRequest(BaseModel):
    category: DeviceCategory
    name: str = Field(min_length=1)
    serial_number: str = Field(min_length=1)
    buy_date: Optional[date] = None
    # Naming someone here opens their assignment as the unit is registered.
    current_user: Optional[str] = None
    site_id: Optional[UUID] = None


class UpdateDeviceRequest(BaseModel):
    category: DeviceCategory
    name: str = Field(min_length=1)
    serial_number: str = Field(min_length=1)
    buy_date: Optional[date] = None


class AssignDeviceRequest(BaseModel):
    user_name: str = Field(min_length=1)
    assigned_on: Optional[date] = None
    note: Optional[str] = None


class ReturnDeviceRequest(BaseModel):
    returned_on: Optional[date] = None
    note: Optional[str] = None


class DeviceListResponse(BaseModel):
    devices: List[RegisteredDevice] = []


class AssignmentListResponse(BaseModel):
    assignments: List[DeviceAssignment] = []
