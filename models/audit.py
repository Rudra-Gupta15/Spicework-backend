from typing import List, Optional, Union

from pydantic import BaseModel, validator

from backend.services.common import clean_string


class GpuInfo(BaseModel):
    name: str = "Unknown"
    driver_version: str = "Unknown"
    vram: str = "Unknown"

    @validator("*", pre=True, allow_reuse=True)
    def normalize(cls, v):
        return clean_string(v, "Unknown")


class NetworkAdapter(BaseModel):
    name: str = "Unknown"
    adapter_type: str = "Unknown"
    speed: str = "Unknown"
    mac_address: str = "Unknown"
    ipv4: str = "Unknown"
    ipv6: str = "Unknown"
    gateway: str = "Unknown"
    subnet_mask: str = "255.255.255.0"
    mtu: str = "1500 (Standard)"
    dns_servers: str = "N/A"
    wifi_ssid: str = "N/A"

    @validator("*", pre=True, allow_reuse=True)
    def normalize(cls, v):
        return clean_string(v, "Unknown")


class Peripheral(BaseModel):
    name: str = "Unknown"
    type: str = "Unknown"
    status: str = "Unknown"

    @validator("*", pre=True, allow_reuse=True)
    def normalize(cls, v):
        return clean_string(v, "Unknown")


class DiskPartition(BaseModel):
    name: str = "Unknown"
    type: str = "Unknown"
    size_gb: str = "Unknown"
    free_gb: str = "Unknown"
    bootable: str = "Unknown"
    health: str = "Healthy"
    ssd_hdd: str = "SSD/HDD"
    file_system_type: str = "Unknown"

    @validator("*", pre=True, allow_reuse=True)
    def normalize(cls, v):
        return clean_string(v, "Unknown")


class HardwareDetails(BaseModel):
    # Basic
    cpu: str = "Unknown"
    ram: str = "Unknown"
    disk: str = "Unknown"
    description: str = "N/A"
    domain: str = "WORKGROUP"
    domain_role: str = "Standalone Workstation"
    shutdown_time: str = "N/A"
    last_backup: str = "No Backup Recorded"
    life_cycle: str = "Active"
    # Extended System & CPU/RAM
    processor_name: str = "Unknown"
    cpu_cores: str = "Unknown"
    cpu_threads: str = "Unknown"
    installed_ram: str = "Unknown"
    ram_slots: str = "Unknown"
    serial_number: str = "Unknown"
    asset_tag: str = "N/A"
    device_type: str = "Unknown"
    manufacturer: str = "Unknown"
    model: str = "Unknown"
    architecture: str = "Unknown"
    # Motherboard & BIOS
    mobo_manufacturer: str = "Unknown"
    mobo_product: str = "Unknown"
    mobo_version: str = "Unknown"
    mobo_serial: str = "Unknown"
    bios_version: str = "Unknown"
    bios_date: str = "Unknown"
    # Battery Diagnostics
    battery_health: str = "N/A"
    cycle_count: str = "N/A"
    charge_percent: str = "N/A"
    design_capacity: str = "N/A"
    full_capacity: str = "N/A"
    # Location Info
    location_info: str = "Unknown"
    # Lists
    gpu_details: List[Union[GpuInfo, dict]] = []
    network_adapters: List[Union[NetworkAdapter, dict]] = []
    peripherals: List[Union[Peripheral, dict]] = []
    disk_partitions: List[Union[DiskPartition, dict]] = []
    usb_history: List[dict] = []

    @validator("cpu", "ram", "disk", "serial_number", "manufacturer", "model", "processor_name", "installed_ram", pre=True, always=True, allow_reuse=True)
    def normalize_str(cls, v):
        return clean_string(v, "Unknown")

    @validator("gpu_details", "network_adapters", "peripherals", "disk_partitions", pre=True, always=True, allow_reuse=True)
    def coerce_list(cls, v):
        if v is None:
            return []
        if isinstance(v, list):
            return v
        return [v]


class NetworkDetails(BaseModel):
    ip_address: str = "Unknown"
    gateway: str = "Unknown"
    mac: str = "Unknown"

    @validator("*", pre=True, allow_reuse=True)
    def normalize(cls, v):
        return clean_string(v, "Unknown")


class UserAccount(BaseModel):
    name: str = "Unknown"
    disabled: str = "Unknown"
    home_directory: str = "Unknown"
    last_login: str = "Unknown"
    licensed: str = "Yes"
    number_of_logins: str = "1"
    user_type: str = "Local"
    current_user: str = "False"

    @validator("*", pre=True, allow_reuse=True)
    def normalize(cls, v):
        return clean_string(v, "Unknown")


class HotfixData(BaseModel):
    caption: str = ""
    cs_name: str = ""
    description: str = ""
    fix_id: str = ""
    installed_on: str = ""

    @validator("*", pre=True, allow_reuse=True)
    def normalize(cls, v):
        return clean_string(v, "")


class PrinterData(BaseModel):
    name: str = ""
    system_name: str = ""
    enable_bidi: str = ""
    extended_printer_status: str = ""
    port_name: str = ""

    @validator("*", pre=True, allow_reuse=True)
    def normalize(cls, v):
        return clean_string(v, "")


class SoftwareEntry(BaseModel):
    name: str = ""
    version: str = "Unknown"
    publisher: str = "Unknown"
    install_date: str = "Unknown"
    size_mb: str = "Unknown"

    @validator("*", pre=True, allow_reuse=True)
    def normalize(cls, v):
        return clean_string(v, "Unknown")


class AuditData(BaseModel):
    execution_datetime: str = ""
    consent: Optional[str] = ""
    computer_name: str = "Unknown"
    current_user: str = "Unknown"
    description: str = "N/A"
    domain: str = "WORKGROUP"
    domain_role: str = "Standalone Workstation"
    shutdown_time: str = "N/A"
    last_backup: str = "No Backup Recorded"
    life_cycle: str = "Active"
    os_name: str = "Unknown"
    os_version: str = "Unknown"
    os_build: str = "Unknown"
    last_boot: str = "Unknown"
    uptime: str = "Unknown"
    architecture: str = "Unknown"
    license_status: str = "Unknown"
    firewall: str = "Unknown"
    bitlocker: str = "Unknown"
    secure_boot: str = "Unknown"
    tpm: str = "Unknown"
    hotfixes: List[Union[HotfixData, str]] = []
    mac_address: str = "Unknown"
    drive_name: str = "No CD Unit Found"
    compression_utilities: List[str] = []
    antivirus: List[str] = []
    printers: List[Union[PrinterData, str]] = []
    hardware_details: Union[HardwareDetails, dict, str] = {}
    network_details: List[Union[NetworkDetails, dict, str]] = []
    user_accounts: List[Union[UserAccount, dict, str]] = []
    software_inventory: List[Union[SoftwareEntry, dict]] = []
    login_history: List[dict] = []
    usb_history: List[dict] = []

    @validator(
        "execution_datetime", "consent", "computer_name", "os_name",
        "os_version", "architecture", "license_status", "mac_address",
        pre=True, always=True, allow_reuse=True,
    )
    def normalize_required(cls, v):
        return clean_string(v, "Unknown")

    @validator("drive_name", pre=True, always=True, allow_reuse=True)
    def normalize_drive(cls, v):
        return clean_string(v, "No CD Unit Found")

    @validator(
        "antivirus", "compression_utilities", "hotfixes",
        "printers", "network_details", "user_accounts", "software_inventory",
        pre=True, always=True, allow_reuse=True,
    )
    def coerce_list(cls, v):
        if v is None:
            return []
        if isinstance(v, list):
            return v
        return [v]
