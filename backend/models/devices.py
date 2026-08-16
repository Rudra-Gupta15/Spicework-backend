from datetime import date, datetime
from enum import Enum
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel


class LauncherType(str, Enum):
    EXE = "exe"
    VBS = "vbs"
    MAC_COMMAND = "mac_command"
    LINUX_SH = "linux_sh"


class DeploymentMode(str, Enum):
    SELF = "self"
    REMOTE = "remote"
    DAEMON = "daemon"


class DeploymentStatus(str, Enum):
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"


class HardwareDeviceStatus(str, Enum):
    ONLINE = "online"
    OFFLINE = "offline"
    MAINTENANCE = "maintenance"


class AgentDeploymentRequest(BaseModel):
    requested_by: UUID
    launcher_type: LauncherType
    deployment_mode: DeploymentMode = DeploymentMode.SELF
    site_id: Optional[UUID] = None
    server_ip: Optional[str] = None
    server_port: Optional[int] = None


class DeviceAuditRequest(BaseModel):
    """What a launcher script POSTs back after scanning a machine. The nested
    lists stay as loosely-typed dicts (not strict sub-models) since the source
    data's keys vary by collector script (e.g. 'name' vs 'application_name') --
    record_device_audit() already tolerates both."""
    device_name: str
    site_id: Optional[UUID] = None
    deployment_id: Optional[UUID] = None
    scanned_by: Optional[UUID] = None
    device: dict = {}
    software: List[dict] = []
    users: List[dict] = []
    login_history: List[dict] = []
    gpus: List[dict] = []
    network_adapters: List[dict] = []
    storage: List[dict] = []
    peripherals: List[dict] = []
    printers: List[dict] = []
    connected_devices: List[dict] = []


class HardwareStorageKind(str, Enum):
    DISK = "disk"
    PARTITION = "partition"


class AgentDeployment(BaseModel):
    """Tracks a 'download launcher' click, created before the file is even generated,
    so an audit uploaded later with the same client_id can be attributed correctly."""
    id: UUID
    organization_id: UUID
    site_id: Optional[UUID] = None
    requested_by: UUID
    client_id: str
    launcher_type: LauncherType
    deployment_mode: DeploymentMode = DeploymentMode.SELF
    server_ip: Optional[str] = None
    server_port: Optional[int] = None
    status: DeploymentStatus = DeploymentStatus.PENDING
    created_at: datetime
    completed_at: Optional[datetime] = None


class HardwareDevice(BaseModel):
    """One physical device's hardware record, current-state only (each rescan
    overwrites this row). Table: hardware_devices."""
    id: UUID
    organization_id: UUID
    site_id: Optional[UUID] = None
    deployment_id: Optional[UUID] = None

    device_name: str
    device_type: Optional[str] = None
    mac_address: Optional[str] = None
    serial_number: Optional[str] = None
    asset_tag: Optional[str] = None
    manufacturer: Optional[str] = None
    model: Optional[str] = None
    description: Optional[str] = None

    os_name: Optional[str] = None
    os_version: Optional[str] = None
    os_build: Optional[str] = None
    domain: Optional[str] = None
    domain_role: Optional[str] = None

    location: Optional[str] = None
    public_ip: Optional[str] = None

    scanner_name: Optional[str] = None
    status: HardwareDeviceStatus = HardwareDeviceStatus.ONLINE
    uptime: Optional[str] = None
    last_boot_time: Optional[datetime] = None
    last_shutdown_time: Optional[datetime] = None
    last_backup: Optional[str] = None

    license_status: Optional[str] = None
    firewall: Optional[str] = None
    bitlocker: Optional[str] = None
    secure_boot: Optional[str] = None
    tpm: Optional[str] = None
    antivirus: Optional[str] = None

    last_login_user: Optional[str] = None
    last_login_at: Optional[datetime] = None
    warranty_expiry: Optional[date] = None

    last_scanned_by: Optional[UUID] = None
    last_scan_at: datetime
    created_at: datetime
    updated_at: datetime


class SoftwareInventoryItem(BaseModel):
    """Table: software_inventory."""
    id: UUID
    device_id: UUID
    organization_id: UUID
    application_name: str
    version: Optional[str] = None
    publisher: Optional[str] = None
    install_date: Optional[str] = None
    size: Optional[str] = None
    last_used: Optional[str] = None
    is_licensed: bool = False
    is_subscription: bool = False
    created_at: datetime


class SoftwareUser(BaseModel):
    """A local user account on the device. Table: software_users."""
    id: UUID
    device_id: UUID
    username: Optional[str] = None
    home_directory: Optional[str] = None
    last_login: Optional[str] = None
    licensed: bool = False
    user_type: Optional[str] = None
    is_current_user: bool = False
    created_at: datetime


class SoftwareLoginHistory(BaseModel):
    """Table: software_login_history."""
    id: UUID
    device_id: UUID
    username: Optional[str] = None
    domain: Optional[str] = None
    logon_type: Optional[str] = None
    logged_in_at: Optional[datetime] = None
    created_at: datetime


class HardwareGpu(BaseModel):
    """Table: hardware_gpus."""
    id: UUID
    device_id: UUID
    name: Optional[str] = None
    driver_version: Optional[str] = None
    vram: Optional[str] = None


class HardwareNetworkAdapter(BaseModel):
    """Table: hardware_network_adapters."""
    id: UUID
    device_id: UUID
    name: Optional[str] = None
    adapter_type: Optional[str] = None
    speed: Optional[str] = None
    mac_address: Optional[str] = None
    ipv4: Optional[str] = None
    ipv6: Optional[str] = None
    gateway: Optional[str] = None
    subnet_mask: Optional[str] = None
    dns_servers: Optional[str] = None


class HardwareStorage(BaseModel):
    """A disk or a partition. Table: hardware_storage."""
    id: UUID
    device_id: UUID
    kind: HardwareStorageKind
    name: Optional[str] = None
    type: Optional[str] = None
    size_gb: Optional[str] = None
    free_gb: Optional[str] = None
    file_system: Optional[str] = None
    is_ssd: Optional[bool] = None
    bootable: Optional[bool] = None
    health: Optional[str] = None


class HardwarePeripheral(BaseModel):
    """Table: hardware_peripherals."""
    id: UUID
    device_id: UUID
    name: Optional[str] = None
    type: Optional[str] = None
    status: Optional[str] = None


class HardwarePrinter(BaseModel):
    """Table: hardware_printers."""
    id: UUID
    device_id: UUID
    name: Optional[str] = None
    system_name: Optional[str] = None
    port_name: Optional[str] = None
    status: Optional[str] = None


class HardwareConnectedDevice(BaseModel):
    """Another device seen on this device's own network during its audit run.
    Same shape/pattern as the WiFi-flow's ScanDevice, but a separate table scoped
    to device_id rather than scan_id. Table: hardware_connected_devices."""
    id: UUID
    device_id: UUID
    ip_address: Optional[str] = None
    hostname: Optional[str] = None
    mac_address: Optional[str] = None
    device_type: Optional[str] = None
    open_ports: List[str] = []
    status: Optional[str] = None
    discovered_at: datetime


class DeviceDetail(HardwareDevice):
    """Full nested view for the 'Hardware Assets' detail page: one tab's worth of
    data per list, pulled from both the hardware_* and software_* tables."""
    software: List[SoftwareInventoryItem] = []
    users: List[SoftwareUser] = []
    login_history: List[SoftwareLoginHistory] = []
    gpus: List[HardwareGpu] = []
    network_adapters: List[HardwareNetworkAdapter] = []
    storage: List[HardwareStorage] = []
    peripherals: List[HardwarePeripheral] = []
    printers: List[HardwarePrinter] = []
    connected_devices: List[HardwareConnectedDevice] = []


class HardwareStats(BaseModel):
    """The Hardware page's summary cards."""
    total_devices: int = 0
    online: int = 0
    offline: int = 0
    warranty_expiring: int = 0


class SoftwareStats(BaseModel):
    """The Software page's summary cards."""
    total_software: int = 0
    total_license: int = 0
    subscription_count: int = 0
    publisher_count: int = 0
