from datetime import datetime
from enum import Enum
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel


class RoleScope(str, Enum):
    PLATFORM = "PLATFORM"
    ORGANIZATION = "ORGANIZATION"


class UserType(str, Enum):
    PLATFORM_USER = "PLATFORM_USER"
    TENANT_USER = "TENANT_USER"


class Role(BaseModel):
    id: UUID
    name: str
    description: Optional[str] = None
    scope: RoleScope
    created_at: datetime


class User(BaseModel):
    id: UUID
    email: str
    first_name: str
    last_name: Optional[str] = None
    user_type: UserType = UserType.TENANT_USER
    is_active: bool = True
    email_verified: bool = False
    last_login_at: Optional[datetime] = None
    organization_id: Optional[UUID] = None
    site_id: Optional[UUID] = None
    created_at: datetime
    updated_at: datetime


class LoginRequest(BaseModel):
    email: str
    password: str


class LoginResponse(User):
    """A logged-in user plus their assigned role names."""
    roles: List[str] = []


class PlatformUserRole(BaseModel):
    user_id: UUID
    role_id: UUID
    created_at: datetime


class Organization(BaseModel):
    id: UUID
    name: str
    is_active: bool = True
    created_by: Optional[UUID] = None
    created_at: datetime
    updated_at: datetime


class Site(BaseModel):
    id: UUID
    organization_id: UUID
    name: str
    address_line: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = None
    postal_code: Optional[str] = None
    is_active: bool = True
    created_at: datetime
    updated_at: datetime


class UserWithRoles(User):
    """A user (typically an org employee) with their assigned role names attached."""
    roles: List[str] = []


class CreateOrganizationRequest(BaseModel):
    """Creates the organization plus its first user, the Organization Admin, together."""
    name: str
    admin_email: str
    admin_password: str
    admin_first_name: str
    admin_last_name: Optional[str] = None
    created_by: Optional[UUID] = None


class CreateSiteRequest(BaseModel):
    name: str
    address_line: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = None
    postal_code: Optional[str] = None


class CreateEmployeeRequest(BaseModel):
    email: str
    password: str
    first_name: str
    last_name: Optional[str] = None
    role_name: str
    site_id: Optional[UUID] = None


class SiteWithEmployees(Site):
    employees: List[UserWithRoles] = []


class OrganizationDetail(Organization):
    """Full nested view of an organization: its sites (each with their employees) and
    the org's employees who aren't tied to any specific site."""
    sites: List[SiteWithEmployees] = []
    unassigned_employees: List[UserWithRoles] = []


class WifiNetwork(BaseModel):
    """A network an organization (optionally one of its sites) has seen or connected to.
    Never carries the password — use WifiNetworkWithPassword for that."""
    id: UUID
    organization_id: UUID
    site_id: Optional[UUID] = None
    ssid: str
    authentication: Optional[str] = None
    encryption: Optional[str] = None
    signal: Optional[str] = None
    is_connected: bool = False
    last_connected_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class WifiNetworkWithPassword(WifiNetwork):
    """Internal/server-side use only (e.g. reconnect flows) — never return this from an API response."""
    password: Optional[str] = None


class ScanDevice(BaseModel):
    """One device found during a network scan — a flat snapshot, not tracked across scans."""
    id: UUID
    scan_id: UUID
    ip_address: Optional[str] = None
    hostname: Optional[str] = None
    mac_address: Optional[str] = None
    username: Optional[str] = None
    operating_system: Optional[str] = None
    device_type: Optional[str] = None
    open_ports: List[str] = []
    audit_status: Optional[str] = None  # "audited" | "unaudited"
    status: Optional[str] = None        # "online" | "offline"
    discovered_at: datetime


class NetworkScan(BaseModel):
    """One 'Connect & Scan' action."""
    id: UUID
    organization_id: UUID
    site_id: Optional[UUID] = None
    performed_by: UUID
    wifi_network_id: Optional[UUID] = None
    ssid: Optional[str] = None
    ip_address: Optional[str] = None
    subnet: Optional[str] = None
    status: str = "completed"
    device_count: int = 0
    started_at: datetime
    completed_at: Optional[datetime] = None


class NetworkScanDetail(NetworkScan):
    """A scan plus the devices it found — the shape for the 'Connected Devices' table."""
    devices: List[ScanDevice] = []


class StoreWifiNetworksRequest(BaseModel):
    """The 'Available WiFi Networks' list fetched on login, to be persisted."""
    site_id: Optional[UUID] = None
    networks: List[dict] = []  # each: {ssid, authentication?, encryption?, signal?}


class ConnectWifiNetworkRequest(BaseModel):
    """Selecting a network and entering its password."""
    ssid: str
    password: str
    site_id: Optional[UUID] = None


class RecordNetworkScanRequest(BaseModel):
    performed_by: UUID
    ssid: str
    devices: List[dict] = []
    site_id: Optional[UUID] = None
    wifi_network_id: Optional[UUID] = None
    ip_address: Optional[str] = None
    subnet: Optional[str] = None
