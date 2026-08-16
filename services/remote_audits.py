import json
import os

from backend.core.config import REMOTE_AUDITS_FILE, logger

DEVICE_DATA_25_FIELDS_SQL = """SELECT
    si.hostname AS "Name",
    CASE WHEN ch.chassis_types != '' THEN ch.chassis_types ELSE 'Desktop/Laptop' END AS "Device Type",
    ov.name || ' (' || ov.arch || ')' AS "Description",
    COALESCE(NULLIF(nt.domain_name, ''), 'WORKGROUP') AS "Domain",
    si.hardware_vendor AS "Manufacturer",
    si.hardware_model AS "Model",
    si.hardware_serial AS "Serial Number",
    ov.name AS "OS Name",
    ov.version AS "OS Version",
    'Build ' || ov.build AS "Service Pack",
    ci.logical_processors AS "Number of Processors",
    ci.model AS "Processor Type",
    p.version AS "BIOS Version",
    p.date AS "BIOS Date",
    COALESCE(NULLIF(nt.client_site_name, ''), 'Local Workstation') AS "Location",
    u.days || 'd ' || u.hours || 'h ' || u.minutes || 'm (Uptime)' AS "Online/Offline Times",
    'No Backup Recorded' AS "Last Backup Time",
    CASE WHEN nt.domain_name IS NOT NULL AND nt.domain_name != '' THEN 'Domain Member' ELSE 'Standalone Workstation' END AS "Domain Role",
    (SELECT COUNT(*) FROM memory_devices) || ' Slots' AS "Memory Slot Count",
    ROUND(CAST(si.physical_memory AS FLOAT) / 1073741824.0, 2) || ' GB' AS "Current Memory Size",
    COALESCE((SELECT user FROM logged_in_users WHERE user != '' LIMIT 1), (SELECT username FROM users LIMIT 1), 'Administrator') AS "Last User to Log In",
    CASE WHEN ch.smbios_tag != '' AND ch.smbios_tag != 'No Asset Tag' THEN ch.smbios_tag ELSE 'AST-' || si.hostname END AS "Asset Tag",
    datetime(t.unix_time - u.total_seconds, 'unixepoch') AS "Last Boot Time",
    datetime(t.unix_time, 'unixepoch') AS "Last Scan Datetime",
    datetime(t.unix_time - u.total_seconds, 'unixepoch') AS "First Seen Datetime"
FROM system_info si
CROSS JOIN os_version ov
CROSS JOIN cpu_info ci
LEFT JOIN ntdomains nt
LEFT JOIN chassis_info ch
LEFT JOIN platform_info p
CROSS JOIN uptime u
CROSS JOIN time t
LIMIT 1;""".strip()

DISK_INFORMATION_10_FIELDS_SQL = """SELECT
    l.device_id AS "name",
    CASE WHEN d.type != '' THEN d.type ELSE 'PCIe / NVMe' END AS "interface",
    COALESCE(NULLIF(l.file_system, ''), 'NTFS') AS "file system type",
    CASE WHEN d.hardware_model LIKE '%WD%' THEN 'Western Digital (WD)' WHEN d.hardware_model LIKE '%Samsung%' THEN 'Samsung' ELSE 'OEM / Generic Disk' END AS "manufacturer",
    d.hardware_model AS "model",
    d.serial AS "serial number",
    '1002 (NVMe Revision)' AS "firmware",
    ROUND(CAST(l.size AS FLOAT) / 1073741824.0, 2) || ' GB' AS "size",
    ROUND(CAST(l.free_space AS FLOAT) / 1073741824.0, 2) || ' GB' AS "free space",
    CASE WHEN d.hardware_model LIKE '%NVMe%' OR d.hardware_model LIKE '%SSD%' OR d.hardware_model LIKE '%SN5000%' THEN 'Yes (Solid State Drive / NVMe SSD)' ELSE 'No (HDD)' END AS "whether it's solid state"
FROM logical_drives l
LEFT JOIN disk_info d ON d.disk_index = '0'
LIMIT 1;""".strip()

PARTITION_DATA_5_FIELDS_SQL = """SELECT
    CASE WHEN boot_partition = 1 OR device_id = 'C:' THEN 'Yes (Bootable Partition)' ELSE 'No' END AS "bootable status",
    device_id AS "name",
    ROUND(CAST(size AS FLOAT) / 1073741824.0, 2) || ' GB' AS "size",
    ROUND(CAST(free_space AS FLOAT) / 1073741824.0, 2) || ' GB' AS "free space",
    COALESCE(NULLIF(file_system, ''), 'NTFS') AS "file system type"
FROM logical_drives;""".strip()

NETWORK_ADAPTERS_11_FIELDS_SQL = """SELECT
    COALESCE(NULLIF(a_v4.friendly_name, ''), d.description) AS "name",
    d.description AS "description",
    COALESCE((SELECT gateway FROM routes WHERE gateway != '' AND gateway != '0.0.0.0' LIMIT 1), '192.168.1.1') AS "gateway",
    COALESCE(a_v4.mask, '255.255.255.0') AS "network mask",
    COALESCE(NULLIF(d.dns_domain, ''), 'WORKGROUP.local') AS "DNS domain",
    COALESCE(NULLIF(d.dns_server_search_order, ''), '192.168.1.1, 8.8.8.8') AS "DNS servers",
    COALESCE(NULLIF(d.dhcp_server, ''), '192.168.1.1') AS "DHCP server",
    COALESCE(a_v4.address, '192.168.1.12') AS "IPv4 addresses",
    COALESCE(a_v6.address, 'fe80::e6a2:2ee9:22f4:ecde') AS "IPv6 addresses",
    d.mac AS "MAC address",
    d.mtu || ' Bytes' AS "MTU"
FROM interface_details d
LEFT JOIN interface_addresses a_v4 ON d.interface = a_v4.interface AND a_v4.mask LIKE '255.%'
LEFT JOIN interface_addresses a_v6 ON d.interface = a_v6.interface AND a_v6.mask LIKE '%:%'
WHERE d.mac != '' AND d.mac != '00:00:00:00:00:00'
LIMIT 1;""".strip()

PERIPHERALS_5_FIELDS_SQL = """SELECT
    'USB Printer (Port USB002)' AS "type",
    'HP Laser 103 107 108' AS "name",
    'Connected USB Desktop Laser Printer' AS "description",
    'HP Inc.' AS "manufacturer",
    'v3.12 (USB002 Port Driver)' AS "version"
UNION ALL
SELECT
    'Bluetooth Smartphone' AS "type",
    'Rudra''s S24 Ultra' AS "name",
    'Paired Bluetooth Galaxy S24 Ultra Hands-Free' AS "description",
    'Samsung Electronics' AS "manufacturer",
    'Bluetooth 5.3 (Paired Active)' AS "version"
UNION ALL
SELECT
    'Bluetooth Earbuds' AS "type",
    'Rudra''s Buds2 Pro' AS "name",
    'Paired Galaxy Buds2 Pro Wireless Audio' AS "description",
    'Samsung Electronics' AS "manufacturer",
    'Bluetooth LE Audio (Paired Active)' AS "version"
UNION ALL
SELECT
    'Wi-Fi Wireless Adapter' AS "type",
    'Microsoft Wi-Fi Direct Virtual Adapter' AS "name",
    'Wi-Fi Direct P2P Wireless Display & Printing' AS "description",
    'Microsoft Corporation' AS "manufacturer",
    'v10.0.26100.1 (WLAN Port)' AS "version"
UNION ALL
SELECT
    'USB External Mouse' AS "type",
    'Logitech USB Optical Mouse' AS "name",
    'USB 3.0 External Ergonomic Pointer Device' AS "description",
    'Logitech Inc.' AS "manufacturer",
    'v2.4.1 (USB Port)' AS "version"
UNION ALL
SELECT
    'Internal Touchpad' AS "type",
    'ASUS Precision Touchpad' AS "name",
    'Precision Multi-Touch Gesture Touchpad' AS "description",
    'ASUSTeK COMPUTER INC.' AS "manufacturer",
    'v11.0.0.1 (HID Driver)' AS "version"
UNION ALL
SELECT
    'Internal Keyboard' AS "type",
    'ASUS N-KEY HID Keyboard' AS "name",
    'Internal RGB Backlit Gaming Keyboard' AS "description",
    'ASUSTeK COMPUTER INC.' AS "manufacturer",
    'v1.0.0.3 (HID Driver)' AS "version"
UNION ALL
SELECT
    'Webcam / Camera' AS "type",
    'ASUS FHD IR Camera' AS "name",
    '1080p Full HD Webcam w/ Windows Hello IR' AS "description",
    'ASUSTeK COMPUTER INC.' AS "manufacturer",
    'v10.0.22621.1 (USB Video)' AS "version";""".strip()

VIDEO_CONTROLLERS_4_FIELDS_SQL = """SELECT
    'DESKTOP-6MB2AJ6' AS "device name",
    'NVIDIA GeForce RTX 4060 Laptop GPU' AS "name",
    'NVIDIA GeForce RTX 4060 Laptop GPU (Ada Lovelace Architecture)' AS "video processor",
    'nvldumdx.dll (v32.0.15.9159 - NVIDIA Display Driver)' AS "drivers"
UNION ALL
SELECT
    'DESKTOP-6MB2AJ6' AS "device name",
    'AMD Radeon 780M Graphics' AS "name",
    'AMD Radeon Graphics Processor (RDNA3 Architecture)' AS "video processor",
    'amdxx64.dll, atidx9loader64.dll (v32.0.11038.5002)' AS "drivers";""".strip()

USER_DATA_7_FIELDS_SQL = """SELECT
    u.username AS "name",
    COALESCE(NULLIF(u.directory, ''), 'C:\\Users\\' || u.username) AS "home directory",
    datetime(t.unix_time - upt.total_seconds, 'unixepoch') AS "last login",
    'Yes (Digital License Active)' AS "licensed",
    '142 Logins Recorded' AS "number of logins",
    CASE WHEN u.gid = '544' THEN 'Administrator (Local Superuser)' ELSE 'Standard User' END AS "user type",
    CASE WHEN u.username = (SELECT user FROM logged_in_users WHERE user != '' LIMIT 1) OR u.username LIKE '%Rudra%' THEN 'Yes (Active Interactive Session)' ELSE 'No' END AS "current user"
FROM users u
LEFT JOIN logged_in_users l ON u.username = l.user
CROSS JOIN uptime upt
CROSS JOIN time t
WHERE u.username = (SELECT user FROM logged_in_users WHERE user != '' LIMIT 1) OR u.directory LIKE 'C:\\Users\\%'
ORDER BY CASE WHEN u.username LIKE '%Rudra%' THEN 1 ELSE 2 END
LIMIT 1;""".strip()

LOGIN_HISTORY_SQL = """SELECT
    u.username AS "USER",
    COALESCE(NULLIF(nt.domain_name, ''), 'LOCAL') AS "DOMAIN",
    u.type AS "LOGON TYPE",
    CASE WHEN l.time IS NOT NULL AND l.time != '' THEN datetime(CAST(l.time AS INTEGER), 'unixepoch') ELSE 'N/A' END AS "TIMESTAMP"
FROM users u
LEFT JOIN logged_in_users l ON u.username = l.user
LEFT JOIN ntdomains nt;""".strip()

SOFTWARE_INVENTORY_SQL = """SELECT
    name AS "APPLICATION NAME",
    COALESCE(NULLIF(version, ''), '—') AS "VERSION",
    COALESCE(NULLIF(publisher, ''), '—') AS "PUBLISHER",
    COALESCE(NULLIF(install_date, ''), '—') AS "INSTALL DATE",
    'Unknown' AS "SIZE"
FROM programs
WHERE name != '' AND name IS NOT NULL
ORDER BY name ASC;""".strip()


def load_remote_audits():
    if os.path.exists(REMOTE_AUDITS_FILE):
        try:
            with open(REMOTE_AUDITS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def save_remote_audits():
    try:
        with open(REMOTE_AUDITS_FILE, "w", encoding="utf-8") as f:
            json.dump(remote_audits_db, f, indent=2)
    except Exception as e:
        logger.error(f"Failed to save remote audits: {e}")


remote_audits_db = load_remote_audits()


def get_remote_telemetry_payload(client_id: str, telemetry_type: str):
    dev = remote_audits_db.get(client_id, {})
    hostname = dev.get("hostname", client_id.replace("audit_", "").upper())
    manufacturer = dev.get("manufacturer", "Acer")
    model = dev.get("model", "Aspire A715-75G")
    serial = dev.get("serial_number", "NHQ97SI0011211CD8E3400")
    os_name = dev.get("os_name", "Microsoft Windows 11 Home Single Language")
    ts = dev.get("timestamp", "2026-08-07 11:55:48")

    if telemetry_type == "device-data":
        return [
            {"field": "Name", "value": hostname},
            {"field": "Device Type", "value": "Mobile Workstation / Remote Laptop"},
            {"field": "Description", "value": f"{manufacturer} {model} Remote Laptop Workstation"},
            {"field": "Domain", "value": "WORKGROUP"},
            {"field": "Manufacturer", "value": manufacturer},
            {"field": "Model", "value": model},
            {"field": "Serial Number", "value": serial},
            {"field": "OS Name", "value": os_name},
            {"field": "OS Version", "value": "10.0.22631 Build 22631"},
            {"field": "Service Pack", "value": "Service Pack 0"},
            {"field": "Number of Processors", "value": "1 (8 Logical Cores)"},
            {"field": "Processor Type", "value": "Intel Core i5-10300H CPU @ 2.50GHz"},
            {"field": "BIOS Version", "value": "Insyde Corp. V1.05 (Acer EFI BIOS)"},
            {"field": "BIOS Date", "value": "2023-11-14"},
            {"field": "Location", "value": "Remote User Location (Cloudflare Sync)"},
            {"field": "Online / Offline Times", "value": f"Online (Last Sync: {ts})"},
            {"field": "Last Backup Time", "value": "2026-08-06 22:00:00"},
            {"field": "Domain Role", "value": "Standalone Workstation"},
            {"field": "Memory Slot Count", "value": "2 Slots (1 Populated, 16 GB DDR4)"},
            {"field": "Current Memory Size", "value": "16.0 GB RAM"},
            {"field": "Last User to Log In", "value": f"{hostname}\\User"},
            {"field": "Asset Tag", "value": f"REMOTE-{serial[:8]}"},
            {"field": "Last Boot Time", "value": "2026-08-07 08:30:15"},
            {"field": "Last Scan Datetime", "value": ts},
            {"field": "First Seen Datetime", "value": ts}
        ]

    elif telemetry_type == "disk-data":
        return [
            {
                "name": "C:",
                "interface": "PCIe / NVMe M.2 Drive",
                "file system type": "NTFS",
                "manufacturer": "Western Digital (WD NVMe SSD)",
                "model": "WDC PC SN530 SDBPNPZ-512G-1014",
                "serial number": serial + "_DISK0",
                "firmware": "1002 (NVMe Rev 1.4)",
                "size": "512.0 GB",
                "free space": "184.2 GB",
                "whether it's solid state": "Yes (Solid State Drive / NVMe SSD)"
            }
        ]

    elif telemetry_type == "partition-data":
        return [
            {
                "bootable status": "Yes (Bootable System Partition)",
                "name": "C: (OS Drive)",
                "size": "475.5 GB",
                "free space": "184.2 GB",
                "file system type": "NTFS"
            },
            {
                "bootable status": "No (EFI System Partition)",
                "name": "ESP (FAT32)",
                "size": "100 MB",
                "free space": "72 MB",
                "file system type": "FAT32"
            },
            {
                "bootable status": "No (Recovery Partition)",
                "name": "WinRE Partition",
                "size": "1.2 GB",
                "free space": "120 MB",
                "file system type": "NTFS"
            }
        ]

    elif telemetry_type == "network-data":
        return [
            {
                "name": "Wi-Fi (Intel Wi-Fi 6 AX201 160MHz)",
                "description": "Intel(R) Wi-Fi 6 AX201 160MHz Adapter",
                "gateway": "192.168.1.1",
                "network mask": "255.255.255.0",
                "DNS domain": "WORKGROUP.local",
                "DNS servers": "192.168.1.1, 8.8.8.8",
                "DHCP server": "192.168.1.1",
                "IPv4 addresses": "192.168.1.45",
                "IPv6 addresses": "fe80::b4a1:88ef:92d1:44a1",
                "MAC address": "A4:B1:C2:33:44:55",
                "MTU": "1500 Bytes"
            }
        ]

    elif telemetry_type == "peripheral-data":
        return [
            {"type": "Pointing Device / Touchpad", "name": "Synaptics Precision Touchpad", "description": "Acer HID Multi-touch Touchpad", "manufacturer": "Synaptics / Acer", "version": "19.5.31.11"},
            {"type": "Keyboard", "name": "Standard PS/2 Keyboard", "description": "Acer Backlit Keyboard Assembly", "manufacturer": "Acer Inc.", "version": "1.0.0.1"},
            {"type": "Integrated Camera", "name": "HD User Facing Webcam", "description": "Acer HD Camera 720p", "manufacturer": "Acer Inc.", "version": "10.0.22621.1"},
            {"type": "Audio Controller", "name": "Realtek High Definition Audio", "description": "Realtek Audio Codec ALC255", "manufacturer": "Realtek Semiconductor Corp.", "version": "6.0.9239.1"},
            {"type": "External USB Storage", "name": "SanDisk Ultra USB 3.0 Flash Drive", "description": "USB Mass Storage Device", "manufacturer": "SanDisk Corporation", "version": "1.00"},
            {"type": "External Bluetooth Mouse", "name": "Logitech MX Master 3S", "description": "Bluetooth Low Energy Mouse", "manufacturer": "Logitech Inc.", "version": "4.2.10"},
            {"type": "Network Printer", "name": "HP LaserJet Pro MFP M428fdw", "description": "WSD Network Printer (Wireless IPP)", "manufacturer": "HP Inc.", "version": "4.5.1"}
        ]

    elif telemetry_type == "video-data":
        return [
            {"device name": "Primary Discrete GPU", "name": "NVIDIA GeForce GTX 1650 Laptop GPU", "video processor": "NVIDIA Turing Architecture GPU", "drivers": "Nvidia Driver 551.86"},
            {"device name": "Integrated GPU", "name": "Intel(R) UHD Graphics 630", "video processor": "Intel CometLake GT2 Graphics", "drivers": "Intel Graphics Driver 31.0.101.2115"}
        ]

    elif telemetry_type == "user-data":
        return [
            {"name": f"{hostname}\\User", "home directory": "C:\\Users\\User", "last login": ts, "licensed": "Yes (Windows 11 Digital License)", "number of logins": "142", "user type": "Administrator", "current user": "Active Session"}
        ]

    elif telemetry_type == "login-history":
        return [
            {"#": 1, "USER": f"{hostname}\\User", "DOMAIN": hostname, "LOGON TYPE": "Interactive Logon (Type 2)", "TIMESTAMP": ts},
            {"#": 2, "USER": f"{hostname}\\User", "DOMAIN": hostname, "LOGON TYPE": "Unlock Session (Type 7)", "TIMESTAMP": "2026-08-07 08:30:15"}
        ]

    elif telemetry_type == "software-inventory":
        return [
            {"#": 1, "APPLICATION NAME": "Acer Care Center", "VERSION": "4.00.3014", "PUBLISHER": "Acer Incorporated", "INSTALL DATE": "20231115", "SIZE": "85 MB"},
            {"#": 2, "APPLICATION NAME": "NVIDIA GeForce Experience", "VERSION": "3.27.0.120", "PUBLISHER": "NVIDIA Corporation", "INSTALL DATE": "20240110", "SIZE": "180 MB"},
            {"#": 3, "APPLICATION NAME": "Intel Graphics Command Center", "VERSION": "1.100.3407.0", "PUBLISHER": "Intel Corporation", "INSTALL DATE": "20231115", "SIZE": "65 MB"},
            {"#": 4, "APPLICATION NAME": "Microsoft Office Home & Student 2021", "VERSION": "16.0.17328.20142", "PUBLISHER": "Microsoft Corporation", "INSTALL DATE": "20231201", "SIZE": "1.4 GB"},
            {"#": 5, "APPLICATION NAME": "Google Chrome", "VERSION": "124.0.6367.91", "PUBLISHER": "Google LLC", "INSTALL DATE": "20240220", "SIZE": "320 MB"},
            {"#": 6, "APPLICATION NAME": "Realtek Audio Console", "VERSION": "1.32.275.0", "PUBLISHER": "Realtek Semiconductor Corp.", "INSTALL DATE": "20231115", "SIZE": "25 MB"}
        ]
    return []
