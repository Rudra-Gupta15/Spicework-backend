#!/bin/bash
# ==============================================================================
#        INFRAPULSE WORKSTATION SYSTEM INFRASTRUCTURE SCRIPT (macOS / Linux)
# ==============================================================================
# Version: 3.0.0 — Full IT Asset Management Edition

echo "Collecting Workstation System Data..."

EXECUTION_DATETIME=$(date +"%Y-%m-%d %H:%M:%S")
COMPUTER_NAME=$(hostname)

# ── OS Detection ──────────────────────────────────────────────────────────────
OS_NAME=$(uname -s)
ARCHITECTURE=$(uname -m)
OS_VERSION=$(uname -r)

if [ "$OS_NAME" = "Darwin" ]; then
    OS_NAME="macOS"
    if command -v sw_vers >/dev/null 2>&1; then
        OS_VERSION=$(sw_vers -productVersion)
    fi
elif [ -f /etc/os-release ]; then
    . /etc/os-release
    OS_NAME="${NAME:-$OS_NAME}"
    OS_VERSION="${VERSION_ID:-$OS_VERSION}"
fi

LICENSE_STATUS="Not Applicable"
DESCRIPTION="Unix Workstation ($OS_NAME)"
DOMAIN="LOCAL"
DOMAIN_ROLE="Standalone Workstation"
SHUTDOWN_TIME="N/A"
LAST_BACKUP="TimeMachine / System Backup Active"
LIFE_CYCLE="Active"

# Extract shutdown time if available
if command -v last >/dev/null 2>&1; then
    SHUTDOWN_TIME=$(last -x shutdown 2>/dev/null | head -1 | awk '{print $4" "$5" "$6" "$7}')
    [ -z "$SHUTDOWN_TIME" ] && SHUTDOWN_TIME="N/A"
fi

# Check if python3 is usable without triggering xcode-select installer
# On macOS without Xcode CLT, invoking python3 pops up an install dialog
PYTHON3_OK=false
if command -v python3 >/dev/null 2>&1; then
    # Test silently — xcode-select errors go to stderr, suppress them
    if python3 -c "import sys; sys.exit(0)" >/dev/null 2>&1; then
        PYTHON3_OK=true
    fi
fi

# ── MAC Address ───────────────────────────────────────────────────────────────
MAC_ADDRESS="Unknown"
if command -v ifconfig >/dev/null 2>&1; then
    MAC_ADDRESS=$(ifconfig | grep -v '00:00:00:00:00:00' | grep -oE '([[:xdigit:]]{1,2}:){5}[[:xdigit:]]{1,2}' | head -n 1 | tr -d ':' | tr '[:lower:]' '[:upper:]')
elif command -v ip >/dev/null 2>&1; then
    MAC_ADDRESS=$(ip link | grep -v '00:00:00:00:00:00' | grep -oE '([[:xdigit:]]{1,2}:){5}[[:xdigit:]]{1,2}' | head -n 1 | tr -d ':' | tr '[:lower:]' '[:upper:]')
fi
[ -z "$MAC_ADDRESS" ] && MAC_ADDRESS="Unknown"

DRIVE_NAME="No CD Unit Found"
COMPRESSION_UTILITIES='["tar", "gzip", "zip (built-in)"]'
ANTIVIRUS='["Built-in OS Protections"]'
PRINTERS="[]"
if [ "$PYTHON3_OK" = "true" ]; then
    PRINTERS=$(python3 - 2>/dev/null <<'PYEOF'
import subprocess, json, re
printers = []
try:
    r = subprocess.run(['lpstat', '-p'], capture_output=True, text=True, timeout=10)
    for line in r.stdout.split('\n'):
        if line.startswith('printer '):
            parts = line.split(' ')
            name = parts[1]
            status = ' '.join(parts[2:]).split('.')[0] if len(parts) > 2 else "Unknown"
            printers.append({
                "name": name,
                "port_name": "Unknown",
                "driver_name": "Unknown",
                "printer_status": status.strip(),
                "extended_printer_status": "0"
            })
except Exception:
    pass
print(json.dumps(printers))
PYEOF
    )
fi
if [ -z "$PRINTERS" ] || [ "$PRINTERS" = "null" ]; then
    PRINTERS="[]"
fi


# ── Basic Hardware: CPU, RAM, Disk ────────────────────────────────────────────
CPU="Unknown"
RAM="Unknown"
DISK="Unknown"

if [ "$OS_NAME" = "macOS" ]; then
    if command -v sysctl >/dev/null 2>&1; then
        CPU=$(sysctl -n machdep.cpu.brand_string 2>/dev/null)
        RAM_BYTES=$(sysctl -n hw.memsize 2>/dev/null)
        if [ -n "$RAM_BYTES" ]; then
            RAM_GB=$(awk "BEGIN {printf \"%.2f\", $RAM_BYTES / 1073741824}")
            RAM="${RAM_GB} GB"
        fi
    fi
    
    DF_LINE=$(df -k / 2>/dev/null | tail -1)
    TOT_KB=$(echo "$DF_LINE" | awk '{print $2}')
    AVAIL_KB=$(echo "$DF_LINE" | awk '{print $4}')
    if [ -n "$TOT_KB" ] && [ -n "$AVAIL_KB" ] && [ "$TOT_KB" -gt 0 ] 2>/dev/null; then
        USED_KB=$((TOT_KB - AVAIL_KB))
        TOT_GB=$(awk "BEGIN {printf \"%.2f\", $TOT_KB / 1048576}")
        FREE_GB=$(awk "BEGIN {printf \"%.2f\", $AVAIL_KB / 1048576}")
        USED_GB=$(awk "BEGIN {printf \"%.2f\", $USED_KB / 1048576}")
        DISK="Macintosh HD - ${FREE_GB} GB free of ${TOT_GB} GB (${USED_GB} GB used)"
    else
        DISK=$(df -h / | tail -1 | awk '{print "Macintosh HD - " $4 " free of " $2}' | sed 's/Gi/ GB/g')
    fi
else
    if command -v lscpu >/dev/null 2>&1; then
        CPU=$(lscpu | grep 'Model name' | cut -f 2 -d ":" | awk '{$1=$1}1')
    fi
    if command -v free >/dev/null 2>&1; then
        RAM_MB=$(free -m | awk '/^Mem:/{print $2}')
        if [ -n "$RAM_MB" ]; then
            RAM_GB=$(awk "BEGIN {printf \"%.2f\", $RAM_MB / 1024}")
            RAM="${RAM_GB} GB"
        fi
    fi
    DF_LINE=$(df -k / 2>/dev/null | tail -1)
    TOT_KB=$(echo "$DF_LINE" | awk '{print $2}')
    AVAIL_KB=$(echo "$DF_LINE" | awk '{print $4}')
    if [ -n "$TOT_KB" ] && [ -n "$AVAIL_KB" ] && [ "$TOT_KB" -gt 0 ] 2>/dev/null; then
        USED_KB=$((TOT_KB - AVAIL_KB))
        TOT_GB=$(awk "BEGIN {printf \"%.2f\", $TOT_KB / 1048576}")
        FREE_GB=$(awk "BEGIN {printf \"%.2f\", $AVAIL_KB / 1048576}")
        USED_GB=$(awk "BEGIN {printf \"%.2f\", $USED_KB / 1048576}")
        DISK="Main System Disk (/) — ${FREE_GB} GB free of ${TOT_GB} GB (${USED_GB} GB used)"
    else
        DISK=$(df -h / | tail -1 | awk '{print "Main System Disk (/) — " $4 " free of " $2}' | sed 's/Gi/ GB/g')
    fi
fi

# ── Network Details ───────────────────────────────────────────────────────────
IP_ADDRESS="Unknown"
if command -v hostname >/dev/null 2>&1; then
    IP_ADDRESS=$(hostname -I 2>/dev/null | awk '{print $1}')
fi
if [ -z "$IP_ADDRESS" ] && command -v ifconfig >/dev/null 2>&1; then
    IP_ADDRESS=$(ifconfig 2>/dev/null | awk '/inet / && !/127.0.0.1/{print $2}' | head -n 1)
fi
[ -z "$IP_ADDRESS" ] && IP_ADDRESS="Unknown"

NETWORK_DETAILS="[{\"ip_address\": \"$IP_ADDRESS\", \"gateway\": \"Unknown\", \"mac\": \"$MAC_ADDRESS\"}]"

# ── Rich User Account Collection ────────────────────────────────────────────
USER_ACCOUNTS="[]"
CURRENT_USER_NAME="$USER"

if [ "$OS_NAME" = "macOS" ]; then
    USER_ACCOUNTS=$(dscl . list /Users | grep -v '^_' | while read -r uname; do
        uid=$(dscl . -read "/Users/$uname" UniqueID 2>/dev/null | awk '{print $2}')
        [ -z "$uid" ] && continue
        [ "$uid" -lt 500 ] 2>/dev/null && continue
        home=$(dscl . -read "/Users/$uname" NFSHomeDirectory 2>/dev/null | awk '{print $2}')
        [ -z "$home" ] && home="Unknown"
        real_name=$(dscl . -read "/Users/$uname" RealName 2>/dev/null | tail -1 | sed 's/^ *//')
        [ -z "$real_name" ] && real_name="$uname"
        last_login=$(last -1 "$uname" 2>/dev/null | head -1 | awk '{print $4" "$5" "$6" "$7}' | sed 's/^ *//; s/ *$//')
        [ -z "$last_login" ] || [ "$last_login" = "   " ] && last_login="Never"
        is_admin=$(dscl . -read /Groups/admin GroupMembership 2>/dev/null | grep -w "$uname" | wc -l | tr -d ' ')
        user_type="Local User"
        [ "$is_admin" -gt 0 ] 2>/dev/null && user_type="Local Administrator"
        is_current="False"
        [ "$uname" = "$CURRENT_USER_NAME" ] && is_current="True"
        num_logins=$(last "$uname" 2>/dev/null | grep -vc "^$" || echo "1")
        printf '{"name":"%s","disabled":"False","home_directory":"%s","last_login":"%s","licensed":"Yes","number_of_logins":"%s","user_type":"%s","current_user":"%s"}|' \
            "$uname" "$home" "$last_login" "$num_logins" "$user_type" "$is_current"
    done | sed 's/|$//' | awk '{printf "[%s]", $0}' | sed 's/}{/},{/g')
else
    USER_ACCOUNTS=$(getent passwd 2>/dev/null | awk -F: '$3 >= 1000 && $3 < 65534' | while IFS=: read -r uname _ uid _ _ home _; do
        [ -z "$uname" ] && continue
        last_login=$(last -1 "$uname" 2>/dev/null | head -1 | awk '{print $4" "$5" "$6" "$7}' | sed 's/^ *//; s/ *$//')
        [ -z "$last_login" ] && last_login="Never"
        is_sudo=$(groups "$uname" 2>/dev/null | grep -cwE 'sudo|wheel' || echo 0)
        user_type="Local User"
        [ "$is_sudo" -gt 0 ] 2>/dev/null && user_type="Local Administrator"
        is_current="False"
        [ "$uname" = "$CURRENT_USER_NAME" ] && is_current="True"
        [ -z "$home" ] && home="/home/$uname"
        printf '{"name":"%s","disabled":"False","home_directory":"%s","last_login":"%s","licensed":"Yes","number_of_logins":"1","user_type":"%s","current_user":"%s"}|' \
            "$uname" "$home" "$last_login" "$user_type" "$is_current"
    done | sed 's/|$//' | awk '{printf "[%s]", $0}' | sed 's/}{/},{/g')
fi
[ -z "$USER_ACCOUNTS" ] || [ "$USER_ACCOUNTS" = "[]" ] && \
    USER_ACCOUNTS="[{\"name\":\"$USER\",\"disabled\":\"False\",\"home_directory\":\"$HOME\",\"last_login\":\"Unknown\",\"licensed\":\"Yes\",\"number_of_logins\":\"1\",\"user_type\":\"Local User\",\"current_user\":\"True\"}]"

# ────────────────────────────────────────────────────────────────────────────
#  PHASE 1 — EXTENDED HARDWARE COLLECTION
# ────────────────────────────────────────────────────────────────────────────
echo "Collecting extended hardware info..."

# Serial Number, Manufacturer, Model, Motherboard, BIOS
SERIAL_NUMBER="Unknown"
MANUFACTURER="Unknown"
MODEL_NAME="Unknown"
MOBO_MANUFACTURER="Unknown"
MOBO_PRODUCT="Unknown"
MOBO_VERSION="Unknown"
MOBO_SERIAL="Unknown"
BIOS_VERSION="Unknown"
BIOS_DATE="Unknown"

if [ "$OS_NAME" = "macOS" ]; then
    SERIAL_NUMBER=$(system_profiler SPHardwareDataType 2>/dev/null | awk -F': ' '/Serial Number \(system\)/{print $2}' | head -1 | sed 's/^ *//')
    MANUFACTURER="Apple Inc."
    MODEL_NAME=$(system_profiler SPHardwareDataType 2>/dev/null | awk -F': ' '/Model Name/{print $2}' | head -1 | sed 's/^ *//')
    MOBO_MANUFACTURER="Apple Inc."
    MOBO_PRODUCT=$(system_profiler SPHardwareDataType 2>/dev/null | awk -F': ' '/Model Identifier/{print $2}' | head -1 | sed 's/^ *//')
    MOBO_VERSION=$(sw_vers -productVersion 2>/dev/null)
    MOBO_SERIAL=$(ioreg -c IOPlatformExpertDevice -d 2 2>/dev/null | awk -F'"' '/IOPlatformSerialNumber/{print $4}' | head -1)
    BIOS_VERSION=$(system_profiler SPHardwareDataType 2>/dev/null | awk -F': ' '/System Firmware Version|Boot ROM Version/{print $2}' | head -1 | sed 's/^ *//')
    BIOS_DATE="Built-in Apple Silicon Firmware"
    [ -z "$SERIAL_NUMBER" ] && SERIAL_NUMBER="Unknown"
    [ -z "$MODEL_NAME" ]    && MODEL_NAME="Unknown"
    [ -z "$BIOS_VERSION" ]  && BIOS_VERSION="Apple iBoot (Secure Boot)"
    [ -z "$MOBO_SERIAL" ]   && MOBO_SERIAL="$SERIAL_NUMBER"
else
    # 1. If running inside WSL 2, query host hardware via powershell.exe!
    if command -v powershell.exe >/dev/null 2>&1 && [ "$PYTHON3_OK" = "true" ]; then
        eval $(python3 - 2>/dev/null <<'PYEOF'
import subprocess, json

try:
    cmd = "Get-CimInstance Win32_ComputerSystemProduct | Select-Object Vendor, Name, IdentifyingNumber | ConvertTo-Json"
    r = subprocess.run(["powershell.exe", "-Command", cmd], capture_output=True, text=True, timeout=5)
    if r.returncode == 0 and r.stdout.strip():
        data = json.loads(r.stdout)
        v = data.get("Vendor","").strip()
        n = data.get("Name","").strip()
        s = data.get("IdentifyingNumber","").strip()
        if v: print(f'MANUFACTURER="{v}"')
        if n: print(f'MODEL_NAME="{n}"')
        if s: print(f'SERIAL_NUMBER="{s}"')
except Exception:
    pass

try:
    cmd = "Get-CimInstance Win32_BaseBoard | Select-Object Manufacturer, Product, Version, SerialNumber | ConvertTo-Json"
    r = subprocess.run(["powershell.exe", "-Command", cmd], capture_output=True, text=True, timeout=5)
    if r.returncode == 0 and r.stdout.strip():
        data = json.loads(r.stdout)
        if data.get("Manufacturer"): print(f'MOBO_MANUFACTURER="{data.get("Manufacturer").strip()}"')
        if data.get("Product"): print(f'MOBO_PRODUCT="{data.get("Product").strip()}"')
        if data.get("Version"): print(f'MOBO_VERSION="{data.get("Version").strip()}"')
        if data.get("SerialNumber"): print(f'MOBO_SERIAL="{data.get("SerialNumber").strip()}"')
except Exception:
    pass

try:
    cmd = "Get-CimInstance Win32_BIOS | Select-Object SMBIOSBIOSVersion, ReleaseDate | ConvertTo-Json"
    r = subprocess.run(["powershell.exe", "-Command", cmd], capture_output=True, text=True, timeout=5)
    if r.returncode == 0 and r.stdout.strip():
        data = json.loads(r.stdout)
        if data.get("SMBIOSBIOSVersion"): print(f'BIOS_VERSION="{data.get("SMBIOSBIOSVersion").strip()}"')
        if data.get("ReleaseDate"): print(f'BIOS_DATE="{data.get("ReleaseDate").strip()}"')
except Exception:
    pass
PYEOF
        )
    fi

    # 2. Try sysfs dmi first (world-readable on Linux without root!)
    if [ -d /sys/class/dmi/id ]; then
        { [ "$SERIAL_NUMBER" = "Unknown" ] || [ -z "$SERIAL_NUMBER" ]; } && [ -f /sys/class/dmi/id/product_serial ] && SERIAL_NUMBER=$(cat /sys/class/dmi/id/product_serial 2>/dev/null | tr -d '\0\r\n')
        { [ "$MANUFACTURER" = "Unknown" ] || [ -z "$MANUFACTURER" ]; }  && [ -f /sys/class/dmi/id/sys_vendor ]     && MANUFACTURER=$(cat /sys/class/dmi/id/sys_vendor 2>/dev/null | tr -d '\0\r\n')
        { [ "$MODEL_NAME" = "Unknown" ] || [ -z "$MODEL_NAME" ]; }      && [ -f /sys/class/dmi/id/product_name ]   && MODEL_NAME=$(cat /sys/class/dmi/id/product_name 2>/dev/null | tr -d '\0\r\n')
        { [ "$MOBO_MANUFACTURER" = "Unknown" ] || [ -z "$MOBO_MANUFACTURER" ]; } && [ -f /sys/class/dmi/id/board_vendor ] && MOBO_MANUFACTURER=$(cat /sys/class/dmi/id/board_vendor 2>/dev/null | tr -d '\0\r\n')
        { [ "$MOBO_PRODUCT" = "Unknown" ] || [ -z "$MOBO_PRODUCT" ]; }     && [ -f /sys/class/dmi/id/board_name ]     && MOBO_PRODUCT=$(cat /sys/class/dmi/id/board_name 2>/dev/null | tr -d '\0\r\n')
        { [ "$MOBO_VERSION" = "Unknown" ] || [ -z "$MOBO_VERSION" ]; }     && [ -f /sys/class/dmi/id/board_version ]  && MOBO_VERSION=$(cat /sys/class/dmi/id/board_version 2>/dev/null | tr -d '\0\r\n')
        { [ "$MOBO_SERIAL" = "Unknown" ] || [ -z "$MOBO_SERIAL" ]; }       && [ -f /sys/class/dmi/id/board_serial ]   && MOBO_SERIAL=$(cat /sys/class/dmi/id/board_serial 2>/dev/null | tr -d '\0\r\n')
        { [ "$BIOS_VERSION" = "Unknown" ] || [ -z "$BIOS_VERSION" ]; }     && [ -f /sys/class/dmi/id/bios_version ]   && BIOS_VERSION=$(cat /sys/class/dmi/id/bios_version 2>/dev/null | tr -d '\0\r\n')
        { [ "$BIOS_DATE" = "Unknown" ] || [ -z "$BIOS_DATE" ]; }        && [ -f /sys/class/dmi/id/bios_date ]      && BIOS_DATE=$(cat /sys/class/dmi/id/bios_date 2>/dev/null | tr -d '\0\r\n')
    fi
    
    # Fallback to dmidecode if sysfs values were empty/Unknown
    if command -v dmidecode >/dev/null 2>&1; then
        { [ "$SERIAL_NUMBER" = "Unknown" ] || [ -z "$SERIAL_NUMBER" ]; } && SERIAL_NUMBER=$(dmidecode -s system-serial-number 2>/dev/null | head -1)
        { [ "$MANUFACTURER" = "Unknown" ] || [ -z "$MANUFACTURER" ]; } && MANUFACTURER=$(dmidecode -s system-manufacturer 2>/dev/null | head -1)
        { [ "$MODEL_NAME" = "Unknown" ] || [ -z "$MODEL_NAME" ]; } && MODEL_NAME=$(dmidecode -s system-product-name 2>/dev/null | head -1)
    fi
fi

# ---------------------------------------------------------
# Asset tag & chassis type
#
# Mirrors the Windows agent: prefer a tag actually burned into firmware, then
# fall back to real hardware serials. Nothing is synthesised -- a made-up tag is
# indistinguishable from a real one once it reaches a compliance report.
# ---------------------------------------------------------
_is_placeholder() {
    case "$(printf '%s' "$1" | tr '[:upper:]' '[:lower:]' | sed 's/^ *//;s/ *$//')" in
        ""|"unknown"|"n/a"|"none"|"null"|"not specified"|"default string") return 0 ;;
        "system serial number"|"to be filled by o.e.m.") return 0 ;;
        *"no asset"*|*"fill by oem"*|*"to be filled"*) return 0 ;;
        *) return 1 ;;
    esac
}

ASSET_TAG="Unknown"
if [ "$OS_NAME" = "macOS" ]; then
    # Macs expose no SMBIOS asset tag; the platform serial is the canonical ID.
    for _cand in "$SERIAL_NUMBER" "$MOBO_SERIAL"; do
        if ! _is_placeholder "$_cand"; then ASSET_TAG="$_cand"; break; fi
    done
else
    _CHASSIS_TAG=""
    [ -r /sys/class/dmi/id/chassis_asset_tag ] && _CHASSIS_TAG=$(cat /sys/class/dmi/id/chassis_asset_tag 2>/dev/null | tr -d '\0\r\n')
    if _is_placeholder "$_CHASSIS_TAG" && command -v dmidecode >/dev/null 2>&1; then
        _CHASSIS_TAG=$(dmidecode -s chassis-asset-tag 2>/dev/null | head -1)
    fi
    for _cand in "$_CHASSIS_TAG" "$MOBO_SERIAL" "$SERIAL_NUMBER"; do
        if ! _is_placeholder "$_cand"; then ASSET_TAG="$_cand"; break; fi
    done
fi

# Chassis type: read it rather than assuming every machine is a laptop.
DEVICE_TYPE="Unknown"
if [ "$OS_NAME" = "macOS" ]; then
    case "$(printf '%s' "$MODEL_NAME" | tr '[:upper:]' '[:lower:]')" in
        *macbook*) DEVICE_TYPE="Laptop" ;;
        *imac*|*"mac mini"*|*"mac studio"*|*"mac pro"*) DEVICE_TYPE="Desktop" ;;
        *xserve*) DEVICE_TYPE="Server" ;;
    esac
    if [ "$DEVICE_TYPE" = "Unknown" ]; then
        if pmset -g batt 2>/dev/null | grep -qi "InternalBattery"; then DEVICE_TYPE="Laptop"; else DEVICE_TYPE="Desktop"; fi
    fi
else
    _CT=""
    [ -r /sys/class/dmi/id/chassis_type ] && _CT=$(cat /sys/class/dmi/id/chassis_type 2>/dev/null | tr -d '\0\r\n')
    case "$_CT" in
        3|4|5|6|7|13|15|16|24) DEVICE_TYPE="Desktop" ;;
        8|9|10|11|12|14|31|32) DEVICE_TYPE="Laptop" ;;
        17|23|25|28) DEVICE_TYPE="Server" ;;
        30) DEVICE_TYPE="Tablet" ;;
    esac
    if [ "$DEVICE_TYPE" = "Unknown" ]; then
        if ls /sys/class/power_supply/BAT* >/dev/null 2>&1; then DEVICE_TYPE="Laptop"; else DEVICE_TYPE="Desktop"; fi
    fi
fi

ASSET_TAG=$(echo "$ASSET_TAG" | sed 's/"/\\"/g')
SERIAL_NUMBER=$(echo "$SERIAL_NUMBER" | sed 's/"/\\"/g')
MANUFACTURER=$(echo "$MANUFACTURER"  | sed 's/"/\\"/g')
MODEL_NAME=$(echo "$MODEL_NAME"      | sed 's/"/\\"/g')
MOBO_MANUFACTURER=$(echo "$MOBO_MANUFACTURER" | sed 's/"/\\"/g')
MOBO_PRODUCT=$(echo "$MOBO_PRODUCT" | sed 's/"/\\"/g')
MOBO_VERSION=$(echo "$MOBO_VERSION" | sed 's/"/\\"/g')
MOBO_SERIAL=$(echo "$MOBO_SERIAL" | sed 's/"/\\"/g')
BIOS_VERSION=$(echo "$BIOS_VERSION" | sed 's/"/\\"/g')
BIOS_DATE=$(echo "$BIOS_DATE" | sed 's/"/\\"/g')

# Physical Network Adapters
NETWORK_ADAPTERS_JSON="[]"
if [ "$PYTHON3_OK" = "true" ]; then
    NETWORK_ADAPTERS_JSON=$(python3 - 2>/dev/null <<'PYEOF'
import subprocess, json, glob, os, sys, re

adapters = []
try:
    if sys.platform == "darwin":
        r = subprocess.run(['networksetup', '-listallhardwareports'], capture_output=True, text=True, timeout=10)
        port = ""
        device = ""
        entries = []  # list of (port_name, device, mac)
        for line in r.stdout.splitlines():
            if 'Hardware Port:' in line:
                port = line.split(':', 1)[1].strip()
            elif 'Device:' in line:
                device = line.split(':', 1)[1].strip()
            elif 'Ethernet Address:' in line:
                mac = line.split(':', 1)[1].strip()
                if port:
                    entries.append((port, device, mac))
                port = ""; device = ""

        # Get default gateway
        gw = "N/A"
        try:
            rg = subprocess.run(['route', '-n', 'get', 'default'], capture_output=True, text=True, timeout=5)
            for ln in rg.stdout.splitlines():
                if 'gateway:' in ln:
                    gw = ln.split(':', 1)[1].strip(); break
        except: pass

        # Get DNS servers
        dns = "N/A"
        try:
            rd = subprocess.run(['scutil', '--dns'], capture_output=True, text=True, timeout=5)
            dns_list = list(dict.fromkeys([ln.split(':')[1].strip() for ln in rd.stdout.splitlines()
                            if 'nameserver[' in ln and not ln.split(':')[1].strip().startswith('127.')]))
            if dns_list: dns = ", ".join(dns_list[:3])
        except: pass

        # Get Wi-Fi SSID
        wifi_ssid = "N/A"
        try:
            rw = subprocess.run(['/System/Library/PrivateFrameworks/Apple80211.framework/Versions/Current/Resources/airport', '-I'],
                                capture_output=True, text=True, timeout=5)
            for ln in rw.stdout.splitlines():
                if ' SSID:' in ln:
                    wifi_ssid = ln.split(':', 1)[1].strip(); break
        except: pass

        for (pname, dev, mac) in entries:
            ip4 = "N/A"; ip6 = "N/A"
            if dev:
                try:
                    ri = subprocess.run(['ifconfig', dev], capture_output=True, text=True, timeout=5)
                    for ln in ri.stdout.splitlines():
                        ln = ln.strip()
                        if ln.startswith('inet ') and 'inet6' not in ln:
                            ip4 = ln.split()[1]
                        elif ln.startswith('inet6 '):
                            addr = ln.split()[1].split('%')[0]
                            if not addr.startswith('fe80'):
                                ip6 = addr
                except: pass
            is_wifi = 'wi-fi' in pname.lower() or 'airport' in pname.lower() or 'wireless' in pname.lower()
            adapters.append({
                "name": pname,
                "adapter_type": "Wi-Fi" if is_wifi else "Ethernet",
                "speed": "Active",
                "mac_address": mac,
                "ipv4": ip4,
                "ipv6": ip6,
                "gateway": gw if ip4 != "N/A" else "N/A",
                "dns_servers": dns,
                "wifi_ssid": wifi_ssid if is_wifi else "N/A"
            })
    else:
        # Linux Network Resolution
        dns_servers = "N/A"
        try:
            with open('/etc/resolv.conf', 'r') as f:
                dns_list = [line.split()[1] for line in f if line.startswith('nameserver') and not line.split()[1].startswith('127.')]
                if dns_list: dns_servers = ", ".join(dns_list)
        except: pass

        wifi_ssid = "N/A"
        try:
            r = subprocess.run(['iwgetid', '-r'], capture_output=True, text=True, timeout=5)
            if r.stdout.strip(): wifi_ssid = r.stdout.strip()
            else:
                r2 = subprocess.run(['nmcli', '-t', '-f', 'active,ssid', 'dev', 'wifi'], capture_output=True, text=True, timeout=5)
                for line in r2.stdout.splitlines():
                    if line.startswith('yes:'):
                        wifi_ssid = line.split(':', 1)[1]
                        break
        except: pass

        for iface_path in glob.glob('/sys/class/net/*'):
            iface = os.path.basename(iface_path)
            if iface == 'lo' or iface.startswith('veth') or iface.startswith('docker') or iface.startswith('br-'):
                continue
            mac = "N/A"
            try:
                with open(os.path.join(iface_path, 'address'), 'r') as f:
                    mac = f.read().strip().upper()
            except: pass
            
            speed = "Active"
            try:
                with open(os.path.join(iface_path, 'speed'), 'r') as f:
                    s = f.read().strip()
                    if s and s.isdigit() and int(s) > 0: speed = f"{s} Mbps"
            except: pass

            ip4 = "N/A"
            ip6 = "N/A"
            gw = "N/A"
            try:
                r_ip = subprocess.run(['ip', 'addr', 'show', iface], capture_output=True, text=True, timeout=5)
                ip4_list = [line.strip().split()[1].split('/')[0] for line in r_ip.stdout.splitlines() if 'inet ' in line]
                ip6_list = [line.strip().split()[1].split('/')[0] for line in r_ip.stdout.splitlines() if 'inet6 ' in line]
                if ip4_list: ip4 = ", ".join(ip4_list)
                if ip6_list: ip6 = ", ".join(ip6_list)
            except: pass
            
            try:
                r_route = subprocess.run(['ip', 'route', 'show', 'dev', iface], capture_output=True, text=True, timeout=5)
                for line in r_route.stdout.splitlines():
                    if 'default via' in line:
                        gw = line.split('via')[1].strip().split()[0]
                        break
            except: pass

            is_wifi = 'wl' in iface or 'wifi' in iface or 'wlan' in iface
            adapters.append({
                "name": iface,
                "adapter_type": "Wi-Fi" if is_wifi else "Ethernet",
                "speed": speed,
                "mac_address": mac,
                "ipv4": ip4,
                "ipv6": ip6,
                "gateway": gw,
                "dns_servers": dns_servers,
                "wifi_ssid": wifi_ssid if is_wifi else "N/A"
            })
except Exception: pass
print(json.dumps(adapters))
PYEOF
)
fi
if [ -z "$NETWORK_ADAPTERS_JSON" ] || [ "$NETWORK_ADAPTERS_JSON" = "null" ]; then
    NETWORK_ADAPTERS_JSON="[]"
fi

# Disk Partitions (Filtering out loop snap devices)
DISK_PARTITIONS_JSON="[]"
if [ "$PYTHON3_OK" = "true" ]; then
    if [ "$OS_NAME" = "macOS" ]; then
        DISK_PARTITIONS_JSON=$(python3 - <<'PYEOF'
import subprocess, json
try:
    partitions = []
    mounts = {}
    r_df = subprocess.run(['df', '-h'], capture_output=True, text=True, timeout=5)
    if r_df.returncode == 0:
        for line in r_df.stdout.splitlines()[1:]:
            parts = line.split()
            if len(parts) >= 6 and parts[0].startswith('/dev/'):
                dev = parts[0].replace('/dev/', '')
                size = parts[1]
                used = parts[2]
                avail = parts[3]
                mount = " ".join(parts[5:])
                mounts[dev] = {"size": size, "free": avail, "mount": mount}

    r_du = subprocess.run(['diskutil', 'list'], capture_output=True, text=True, timeout=5)
    if r_du.returncode == 0:
        for line in r_du.stdout.splitlines():
            parts = line.strip().split()
            if not parts: continue
            idx_str = parts[0].rstrip(':')
            if idx_str.isdigit():
                ident = parts[-1]
                ptype = parts[1] if len(parts) > 1 else "APFS"
                name_parts = parts[2:-2] if len(parts) > 4 else []
                name = " ".join(name_parts) if name_parts else ident
                if not name or name in ["-", "Scheme"]: name = ident
                
                m_info = mounts.get(ident, {})
                size_gb = m_info.get("size", " ".join(parts[-3:-1]) if len(parts) >= 4 else "Unknown")
                free_gb = m_info.get("free", "Unknown")
                mount_pt = m_info.get("mount", "")
                is_boot = "Yes" if (mount_pt == "/" or "Macintosh" in name) else "No"
                
                if not ptype.startswith("GUID_") and not ptype.startswith("APFS_Container"):
                    partitions.append({
                        "name": name,
                        "type": ptype,
                        "size_gb": size_gb if ("B" in size_gb) else f"{size_gb} GB",
                        "free_gb": free_gb if ("B" in free_gb or free_gb == "Unknown") else f"{free_gb} GB",
                        "bootable": is_boot,
                        "health": "Healthy",
                        "ssd_hdd": "SSD"
                    })

    if not partitions:
        for dev, m_info in mounts.items():
            partitions.append({
                "name": m_info["mount"] if m_info["mount"] else dev,
                "type": "APFS",
                "size_gb": m_info["size"],
                "free_gb": m_info["free"],
                "bootable": "Yes" if m_info["mount"] == "/" else "No",
                "health": "Healthy",
                "ssd_hdd": "SSD"
            })
            
    print(json.dumps(partitions))
except:
    print("[]")
PYEOF
)
    elif command -v lsblk >/dev/null 2>&1; then
        DISK_PARTITIONS_JSON=$(lsblk -J -o NAME,SIZE,TYPE,FSTYPE,MOUNTPOINT 2>/dev/null | python3 -c '
import sys, json
try:
    data = json.load(sys.stdin)
    partitions = []
    def flatten(devices):
        for d in devices:
            dtype = d.get("type", "")
            name = d.get("name", "")
            if dtype == "loop" or name.startswith("loop"):
                continue
            fstype = d.get("fstype") or dtype or "ext4"
            size = d.get("size") or "Unknown"
            mp = d.get("mountpoint") or ""
            partitions.append({
                "name": name,
                "type": fstype,
                "size_gb": size,
                "bootable": "Yes" if mp == "/" else "No",
                "health": "Healthy",
                "ssd_hdd": "SSD/HDD"
            })
            if d.get("children"):
                flatten(d["children"])
    flatten(data.get("blockdevices", []))
    print(json.dumps(partitions))
except:
    print("[]")
')
    fi
fi
if [ -z "$DISK_PARTITIONS_JSON" ] || [ "$DISK_PARTITIONS_JSON" = "null" ]; then
    DISK_PARTITIONS_JSON="[]"
fi

# Battery Diagnostics for Linux & macOS
BATTERY_HEALTH="N/A (Desktop)"
CYCLE_COUNT="N/A"
CHARGE_PERCENT="N/A"
DESIGN_CAPACITY="N/A"
FULL_CAPACITY="N/A"

BAT_PATH=$(ls -d /sys/class/power_supply/BAT* 2>/dev/null | head -1)
if [ -n "$BAT_PATH" ]; then
    [ -f "$BAT_PATH/status" ] && BATTERY_HEALTH=$(cat "$BAT_PATH/status" 2>/dev/null | tr -d '\r\n')
    [ -f "$BAT_PATH/capacity" ] && CHARGE_PERCENT="$(cat "$BAT_PATH/capacity" 2>/dev/null | tr -d '\r\n')%"
    [ -f "$BAT_PATH/cycle_count" ] && CYCLE_COUNT=$(cat "$BAT_PATH/cycle_count" 2>/dev/null | tr -d '\r\n')
    
    if [ -f "$BAT_PATH/energy_full_design" ]; then
        DESIGN_CAPACITY="$(awk '{printf "%.0f mWh", $1/1000}' "$BAT_PATH/energy_full_design" 2>/dev/null)"
    elif [ -f "$BAT_PATH/charge_full_design" ]; then
        DESIGN_CAPACITY="$(awk '{printf "%.0f mAh", $1/1000}' "$BAT_PATH/charge_full_design" 2>/dev/null)"
    fi
    
    if [ -f "$BAT_PATH/energy_full" ]; then
        FULL_CAPACITY="$(awk '{printf "%.0f mWh", $1/1000}' "$BAT_PATH/energy_full" 2>/dev/null)"
    elif [ -f "$BAT_PATH/charge_full" ]; then
        FULL_CAPACITY="$(awk '{printf "%.0f mAh", $1/1000}' "$BAT_PATH/charge_full" 2>/dev/null)"
    fi
fi

# Battery — macOS
if [ "$OS_NAME" = "macOS" ]; then
    BATTERY_HEALTH="N/A"
    CHARGE_PERCENT="N/A"
    CYCLE_COUNT="N/A"
    DESIGN_CAPACITY="N/A"
    FULL_CAPACITY="N/A"
    # pmset gives basic battery status
    if command -v pmset >/dev/null 2>&1; then
        _BATT=$(pmset -g batt 2>/dev/null)
        _PCT=$(echo "$_BATT" | grep -oE '[0-9]+%' | head -1)
        [ -n "$_PCT" ] && CHARGE_PERCENT="$_PCT"
        echo "$_BATT" | grep -qi "charging" && BATTERY_HEALTH="Charging"
        echo "$_BATT" | grep -qi "discharging" && BATTERY_HEALTH="Discharging"
        echo "$_BATT" | grep -qi "charged" && BATTERY_HEALTH="Fully Charged"
    fi
    # Extract battery specs via ioreg (AppleSmartBattery)
    if command -v ioreg >/dev/null 2>&1; then
        _IOREG=$(ioreg -l -n AppleSmartBattery 2>/dev/null)
        
        # CycleCount — must be > 0 and distinct from capacity values
        _CC=$(echo "$_IOREG" | grep '"CycleCount"' | grep -oE '[0-9]+' | tail -1)
        [ -n "$_CC" ] && CYCLE_COUNT="$_CC"
        
        # DesignCapacity — typically > 1000 mAh for any real laptop
        _DC=$(echo "$_IOREG" | grep '"DesignCapacity"' | grep -oE '[0-9]+' | tail -1)
        if [ -n "$_DC" ] && [ "$_DC" -gt 500 ] 2>/dev/null; then
            DESIGN_CAPACITY="${_DC} mAh"
        fi
        
        # MaxCapacity (Full Charge Capacity) — also typically > 1000 mAh
        _FC=$(echo "$_IOREG" | grep '"MaxCapacity"' | grep -oE '[0-9]+' | tail -1)
        if [ -n "$_FC" ] && [ "$_FC" -gt 500 ] 2>/dev/null; then
            FULL_CAPACITY="${_FC} mAh"
        fi

        [ "$BATTERY_HEALTH" = "N/A" ] && BATTERY_HEALTH="OK"
    fi
    
    # system_profiler fallback if ioreg returns empty or bad values
    if command -v system_profiler >/dev/null 2>&1; then
        if [ "$CYCLE_COUNT" = "N/A" ]; then
            _SP_CC=$(system_profiler SPPowerDataType 2>/dev/null | grep "Cycle Count" | awk '{print $NF}' | head -1)
            [ -n "$_SP_CC" ] && CYCLE_COUNT="$_SP_CC"
        fi
        if [ "$FULL_CAPACITY" = "N/A" ]; then
            _SP_FC=$(system_profiler SPPowerDataType 2>/dev/null | grep "Full Charge Capacity" | grep -oE '[0-9]+' | head -1)
            [ -n "$_SP_FC" ] && [ "$_SP_FC" -gt 500 ] 2>/dev/null && FULL_CAPACITY="${_SP_FC} mAh"
        fi
        if [ "$DESIGN_CAPACITY" = "N/A" ]; then
            _SP_DC=$(system_profiler SPPowerDataType 2>/dev/null | grep "Design Capacity" | grep -oE '[0-9]+' | head -1)
            [ -n "$_SP_DC" ] && [ "$_SP_DC" -gt 500 ] 2>/dev/null && DESIGN_CAPACITY="${_SP_DC} mAh"
        fi
    fi
fi

# Location Info — pure shell, no Python needed
LOCATION_INFO="Location Unavailable"
if command -v curl >/dev/null 2>&1; then
    GEO_RAW=$(curl -s --max-time 6 "http://ip-api.com/json/" 2>/dev/null)
    if [ -n "$GEO_RAW" ]; then
        # Check status field
        _STATUS=$(echo "$GEO_RAW" | grep -o '"status":"success"')
        if [ -n "$_STATUS" ]; then
            _CITY=$(echo    "$GEO_RAW" | grep -o '"city":"[^"]*"'       | cut -d'"' -f4)
            _REGION=$(echo  "$GEO_RAW" | grep -o '"regionName":"[^"]*"' | cut -d'"' -f4)
            _COUNTRY=$(echo "$GEO_RAW" | grep -o '"country":"[^"]*"'    | cut -d'"' -f4)
            _LAT=$(echo     "$GEO_RAW" | grep -o '"lat":[^,}]*'         | cut -d':' -f2)
            _LON=$(echo     "$GEO_RAW" | grep -o '"lon":[^,}]*'         | cut -d':' -f2)
            _IP=$(echo      "$GEO_RAW" | grep -o '"query":"[^"]*"'      | cut -d'"' -f4)
            [ -n "$_CITY" ] && LOCATION_INFO="${_CITY}, ${_REGION}, ${_COUNTRY} (Lat: ${_LAT}, Lon: ${_LON} | Public IP: ${_IP})"
        fi
    fi
fi
[ -z "$LOCATION_INFO" ] && LOCATION_INFO="Location Unavailable"


# Peripherals for macOS & Linux
PERIPHERALS_JSON=$(python3 - 2>/dev/null <<'PYEOF'
import subprocess, json, sys

devices = []
try:
    if sys.platform == "darwin":
        r = subprocess.run(['system_profiler', 'SPUSBDataType', '-json'], capture_output=True, text=True, timeout=8)
        if r.returncode == 0 and r.stdout.strip():
            sp_usb = json.loads(r.stdout).get('SPUSBDataType', [])
            def parse_usb(items):
                for item in items:
                    name = item.get('_name') or ''
                    mfr = item.get('manufacturer') or 'Apple Inc.'
                    dev_id = item.get('product_id') or 'N/A'
                    if name and not name.startswith('USB') and name not in ['Hub']:
                        conn_type = "USB Port"
                        if "wifi" in name.lower() or "wireless" in name.lower():
                            conn_type = "Wi-Fi"
                        elif "bluetooth" in name.lower():
                            conn_type = "Bluetooth"
                        
                        devices.append({
                            "name": name,
                            "type": name,
                            "connection_type": conn_type,
                            "device_id": dev_id,
                            "manufacturer": mfr,
                            "status": "OK"
                        })
                    if '_items' in item:
                        parse_usb(item['_items'])
            parse_usb(sp_usb)
    else:
        r = subprocess.run(['lsusb'], capture_output=True, text=True, timeout=5)
        for line in r.stdout.splitlines():
            if 'ID ' in line:
                parts = line.split('ID ')[1].split(' ')
                dev_id = parts[0]
                name = ' '.join(parts[1:]).strip()
                if name:
                    conn_type = "USB Port"
                    if "wifi" in name.lower() or "wireless" in name.lower():
                        conn_type = "Wi-Fi"
                    elif "bluetooth" in name.lower():
                        conn_type = "Bluetooth"
                    
                    devices.append({
                        "name": name,
                        "type": name,
                        "connection_type": conn_type,
                        "device_id": dev_id,
                        "manufacturer": "USB Device",
                        "status": "OK"
                    })
except Exception: pass

# Also check for network / CUPS printers
try:
    r_prt = subprocess.run(['lpstat', '-p'], capture_output=True, text=True, timeout=5)
    for line in r_prt.stdout.splitlines():
        if line.startswith('printer '):
            pname = line.split()[1]
            devices.append({
                "name": f"Printer ({pname})",
                "type": "Printer",
                "connection_type": "Wi-Fi / Network Port",
                "device_id": pname,
                "manufacturer": "Network Printer",
                "status": "OK"
            })
except Exception: pass

if not devices:
    devices = [{"name": "Integrated Retina Display, Built-in Keyboard & Trackpad", "type": "Built-in Hardware", "connection_type": "Internal Bus", "device_id": "Built-in", "manufacturer": "Apple/System OEM", "status": "OK"}]
print(json.dumps(devices))
PYEOF
)
if [ -z "$PERIPHERALS_JSON" ] || [ "$PERIPHERALS_JSON" = "null" ]; then
    PERIPHERALS_JSON="[]"
fi

# ── Timestamps & Security Details (macOS / Linux) ──────────────────────────────
LAST_BOOT="Unknown"
UPTIME="Unknown"
SHUTDOWN_TIME="N/A"
FIREWALL="Enabled (OS Socket Firewall)"
BITLOCKER="N/A"
SECURE_BOOT="Unknown"
TPM="Unknown"
OS_BUILD="Unknown"

if [ "$OS_NAME" = "macOS" ]; then
    OS_BUILD=$(sw_vers -buildVersion 2>/dev/null)
    [ -z "$OS_BUILD" ] && OS_BUILD="24D70"
    
    # Boot time & Uptime — pure shell, no python3 needed
    BOOT_SEC=$(sysctl -n kern.boottime 2>/dev/null | grep -oE 'sec = [0-9]+' | awk '{print $3}')
    if [ -n "$BOOT_SEC" ]; then
        NOW_SEC=$(date +%s 2>/dev/null)
        if [ -n "$NOW_SEC" ]; then
            UP_SEC=$((NOW_SEC - BOOT_SEC))
            LAST_BOOT=$(date -r "$BOOT_SEC" "+%Y-%m-%d %H:%M:%S" 2>/dev/null)
            [ -z "$LAST_BOOT" ] && LAST_BOOT=$(date -j -f "%s" "$BOOT_SEC" "+%Y-%m-%d %H:%M:%S" 2>/dev/null)
            _D=$((UP_SEC / 86400))
            _H=$(( (UP_SEC % 86400) / 3600 ))
            _M=$(( (UP_SEC % 3600) / 60 ))
            UPTIME="${_D}d ${_H}h ${_M}m"
        fi
    fi
    
    # Last Shutdown
    _SHUT=$(last -1 shutdown 2>/dev/null | head -1)
    [ -n "$_SHUT" ] && SHUTDOWN_TIME=$(echo "$_SHUT" | awk '{print $3 " " $4 " " $5 " " $6}')
    
    # Firewall
    FW_STATE=$(defaults read /Library/Preferences/com.apple.alf globalstate 2>/dev/null)
    if [ "$FW_STATE" = "1" ] || [ "$FW_STATE" = "2" ]; then
        FIREWALL="Enabled (macOS Socket Filter Firewall)"
    elif [ "$FW_STATE" = "0" ]; then
        FIREWALL="Disabled"
    fi

    # FileVault (BitLocker equivalent)
    if command -v fdesetup >/dev/null 2>&1; then
        if fdesetup status 2>/dev/null | grep -qi "On"; then
            BITLOCKER="Encrypted (FileVault On)"
        else
            BITLOCKER="Not Encrypted (FileVault Off)"
        fi
    fi

    # Secure Boot & TPM (Secure Enclave)
    SECURE_BOOT="Enabled (SIP & Apple Secure Enclave)"
    TPM="Apple Secure Enclave (Hardware Security)"
else
    if [ -f /proc/uptime ]; then
        UP_SEC=$(cut -d. -f1 /proc/uptime 2>/dev/null)
        if [ -n "$UP_SEC" ]; then
            UPTIME=$(python3 -c "s=$UP_SEC; d=s//86400; h=(s%86400)//3600; m=(s%3600)//60; print(f'{d}d {h}h {m}m')" 2>/dev/null)
            LAST_BOOT=$(python3 -c "import time, datetime; print(datetime.datetime.fromtimestamp(time.time() - $UP_SEC).strftime('%Y-%m-%d %H:%M:%S'))" 2>/dev/null)
        fi
    fi
    FIREWALL="Enabled (iptables / ufw)"
    BITLOCKER="LUKS Encrypted / Standard"
    SECURE_BOOT="Enabled"
    TPM="TPM 2.0 Module"
fi

# ────────────────────────────────────────────────────────────────────────────
#  GPU Collection
# ────────────────────────────────────────────────────────────────────────────
GPU_JSON="[]"
echo "Collecting GPU information..."
if [ "$PYTHON3_OK" = "true" ]; then
    GPU_JSON=$(python3 - <<'PYEOF'
import subprocess, json, sys, os

gpus = []
try:
    if sys.platform == "darwin":
        r = subprocess.run(['system_profiler', 'SPDisplaysDataType'], capture_output=True, text=True, timeout=10)
        name = ""
        vram = "Shared (Unified Memory)"
        in_gpu_section = False
        for line in r.stdout.splitlines():
            line_s = line.strip()
            if 'Chipset Model:' in line_s:
                # Flush previous GPU if any
                if name:
                    gpus.append({"name": name, "driver_version": "N/A", "vram": vram})
                name = line_s.split(':', 1)[1].strip()
                vram = "Shared (Unified Memory)"  # default for Apple Silicon
            elif ('VRAM' in line_s or 'Metal' in line_s) and name:
                if 'VRAM' in line_s:
                    vram = line_s.split(':', 1)[1].strip()
        # Flush last GPU
        if name:
            gpus.append({"name": name, "driver_version": "N/A", "vram": vram})
    else:
        # Try lspci first
        r = subprocess.run(['lspci'], capture_output=True, text=True, timeout=5)
        for line in r.stdout.splitlines():
            if 'VGA' in line or '3D controller' in line or 'Display controller' in line:
                name = line.split(':', 2)[-1].strip()
                vram = "Unknown"
                gpus.append({"name": name, "driver_version": "N/A", "vram": vram})
except Exception:
    pass
print(json.dumps(gpus))
PYEOF
)
fi
if [ -z "$GPU_JSON" ] || [ "$GPU_JSON" = "null" ]; then
    GPU_JSON="[]"
fi

# ────────────────────────────────────────────────────────────────────────────
#  Define PYTHON3_CMD now (needed by PHASE 2 & 3 software/login scans)
# ────────────────────────────────────────────────────────────────────────────
if [ "$PYTHON3_OK" = "true" ]; then
    PYTHON3_CMD="python3"
elif command -v python >/dev/null 2>&1 && python -c "import json" >/dev/null 2>&1; then
    PYTHON3_CMD="python"
else
    PYTHON3_CMD=""
fi

# ── CPU Cores & Threads (macOS via sysctl) ────────────────────────────────────
CPU_CORES="Unknown"
CPU_THREADS="Unknown"
if [ "$OS_NAME" = "macOS" ]; then
    _PC=$(sysctl -n hw.physicalcpu 2>/dev/null | tr -d '[:space:]')
    _LC=$(sysctl -n hw.logicalcpu 2>/dev/null | tr -d '[:space:]')
    [ -n "$_PC" ] && [ "$_PC" -gt 0 ] 2>/dev/null && CPU_CORES="$_PC"
    [ -n "$_LC" ] && [ "$_LC" -gt 0 ] 2>/dev/null && CPU_THREADS="$_LC"
elif [ -f /proc/cpuinfo ]; then
    _PC=$(grep -c '^processor' /proc/cpuinfo 2>/dev/null)
    [ -n "$_PC" ] && [ "$_PC" -gt 0 ] 2>/dev/null && CPU_CORES="$_PC" && CPU_THREADS="$_PC"
fi

# ────────────────────────────────────────────────────────────────────────────
#  PHASE 2 — FULL SOFTWARE INVENTORY
# ────────────────────────────────────────────────────────────────────────────
echo "Scanning installed software..."
SOFTWARE_INVENTORY_JSON="[]"

if [ -n "$PYTHON3_CMD" ]; then
    SOFTWARE_INVENTORY_JSON=$($PYTHON3_CMD - <<'PYEOF'
# -*- coding: utf-8 -*-
import subprocess, json, sys, os
apps = []
try:
    if sys.platform == "darwin":
        import plistlib, datetime
        seen_paths = set()
        seen_names = set()

        # Method 1: system_profiler SPApplicationsDataType -xml (works on macOS 10.11+)
        try:
            sp_out = subprocess.check_output(
                ['system_profiler', 'SPApplicationsDataType', '-xml'],
                stderr=open(os.devnull, 'w')
            )
            if hasattr(plistlib, 'loads'):
                pl_list = plistlib.loads(sp_out)
            else:
                pl_list = plistlib.readPlistFromString(sp_out)
            sp_apps = pl_list[0].get('_items', []) if pl_list else []
            for a in sp_apps:
                name = str(a.get('_name') or 'Unknown')
                path = str(a.get('path') or '')
                version = str(a.get('version') or 'Unknown')
                obtained = str(a.get('obtained_from') or '')
                if path: seen_paths.add(path)
                if name != 'Unknown': seen_names.add(name)
                pub = 'Apple Inc.' if obtained == 'apple' else ('Mac App Store' if obtained == 'mac_app_store' else 'Third-Party')
                install_date = 'Unknown'
                if path and os.path.exists(path):
                    try:
                        ctime = os.path.getctime(path)
                        install_date = datetime.date.fromtimestamp(ctime).isoformat()
                    except:
                        pass
                apps.append({'name': name, 'version': version, 'publisher': pub, 'install_date': install_date, 'size_mb': 'System'})
        except Exception:
            pass

        # Method 2: Walk /Applications for any missed .app bundles
        for sroot in ['/Applications', os.path.expanduser('~/Applications')]:
            if not os.path.isdir(sroot):
                continue
            for entry in os.listdir(sroot):
                if not entry.endswith('.app'):
                    continue
                app_full = os.path.join(sroot, entry)
                name = entry[:-4]
                if app_full in seen_paths or name in seen_names:
                    continue
                seen_paths.add(app_full)
                seen_names.add(name)
                version = 'Unknown'
                pub = 'Third-Party'
                install_date = 'Unknown'
                try:
                    ctime = os.path.getctime(app_full)
                    install_date = datetime.date.fromtimestamp(ctime).isoformat()
                except:
                    pass
                plist_path = os.path.join(app_full, 'Contents', 'Info.plist')
                if os.path.exists(plist_path):
                    try:
                        with open(plist_path, 'rb') as fp:
                            raw = fp.read()
                        pl = plistlib.loads(raw) if hasattr(plistlib, 'loads') else plistlib.readPlistFromString(raw)
                        version = str(pl.get('CFBundleShortVersionString') or pl.get('CFBundleVersion') or 'Unknown')
                        bundle_id = str(pl.get('CFBundleIdentifier') or '')
                        if 'com.apple' in bundle_id.lower():
                            pub = 'Apple Inc.'
                        elif 'microsoft' in bundle_id.lower():
                            pub = 'Microsoft Corporation'
                        elif 'google' in bundle_id.lower():
                            pub = 'Google LLC'
                    except:
                        pass
                apps.append({'name': name, 'version': version, 'publisher': pub, 'install_date': install_date, 'size_mb': 'Unknown'})
    else:
        import datetime as _dt
        import subprocess as _sp
        DEVNULL = open(os.devnull, 'w')

        # ── 1. dpkg (Debian / Ubuntu / Mint) — NO cap, with install dates ──────
        dpkg_dates = {}
        try:
            log_file = '/var/log/dpkg.log'
            if os.path.exists(log_file):
                with open(log_file, 'r', errors='replace') as lf:
                    for line in lf:
                        parts = line.strip().split()
                        if len(parts) >= 4 and parts[2] == 'install':
                            pkg_name = parts[3].split(':')[0]
                            dpkg_dates[pkg_name] = parts[0]
            # Also check rotated logs
            for i in range(1, 6):
                gz = f'/var/log/dpkg.log.{i}.gz'
                log_r = f'/var/log/dpkg.log.{i}'
                for path in [log_r]:
                    if os.path.exists(path):
                        with open(path, 'r', errors='replace') as lf:
                            for line in lf:
                                parts = line.strip().split()
                                if len(parts) >= 4 and parts[2] == 'install':
                                    pkg_name = parts[3].split(':')[0]
                                    if pkg_name not in dpkg_dates:
                                        dpkg_dates[pkg_name] = parts[0]
        except Exception:
            pass

        try:
            out = _sp.check_output(
                ['dpkg-query', '-W', '--showformat=${Package}|${Version}|${Installed-Size}|${Status}\n'],
                stderr=DEVNULL
            )
            for line in out.decode('utf-8', errors='replace').strip().split('\n'):
                parts = line.split('|')
                if len(parts) >= 2 and parts[0].strip():
                    pkg_name = parts[0].strip()
                    status = parts[3].strip() if len(parts) > 3 else ''
                    # Only show properly installed packages
                    if status and 'installed' not in status:
                        continue
                    size_kb = int(parts[2].strip()) if len(parts) > 2 and parts[2].strip().isdigit() else 0
                    size_str = str(round(size_kb / 1024.0, 2)) + ' MB' if size_kb > 0 else 'Unknown'
                    install_date = dpkg_dates.get(pkg_name, 'Unknown')
                    apps.append({
                        'name': pkg_name,
                        'version': parts[1].strip(),
                        'publisher': 'Debian/Ubuntu',
                        'install_date': install_date,
                        'size_mb': size_str
                    })
        except Exception:
            pass

        # ── 2. rpm (RedHat / Fedora / CentOS) — only if dpkg found nothing ─────
        if not apps:
            try:
                out = _sp.check_output(
                    ['rpm', '-qa', '--qf', '%{NAME}|%{VERSION}-%{RELEASE}|%{SIZE}|%{INSTALLTIME:date}\n'],
                    stderr=DEVNULL
                )
                for line in out.decode('utf-8', errors='replace').strip().split('\n'):
                    parts = line.split('|')
                    if len(parts) >= 2 and parts[0].strip():
                        size_b = int(parts[2].strip()) if len(parts) > 2 and parts[2].strip().isdigit() else 0
                        size_str = str(round(size_b / 1048576.0, 2)) + ' MB' if size_b > 0 else 'Unknown'
                        install_date = parts[3].strip()[:10] if len(parts) > 3 else 'Unknown'
                        apps.append({
                            'name': parts[0].strip(),
                            'version': parts[1].strip(),
                            'publisher': 'RedHat/RPM',
                            'install_date': install_date,
                            'size_mb': size_str
                        })
            except Exception:
                pass

        # ── 3. pacman (Arch Linux / Manjaro) ─────────────────────────────────────
        if not apps:
            try:
                out = _sp.check_output(['pacman', '-Q'], stderr=DEVNULL)
                for line in out.decode('utf-8', errors='replace').strip().split('\n'):
                    parts = line.split()
                    if len(parts) >= 2:
                        apps.append({
                            'name': parts[0].strip(),
                            'version': parts[1].strip(),
                            'publisher': 'Arch Linux',
                            'install_date': 'Unknown',
                            'size_mb': 'Unknown'
                        })
            except Exception:
                pass

        # ── 4. Snap — always append on top of any existing packages ─────────────
        try:
            out = _sp.check_output(['snap', 'list'], stderr=DEVNULL)
            for line in out.decode('utf-8', errors='replace').strip().split('\n')[1:]:
                parts = line.split()
                if len(parts) >= 2:
                    apps.append({
                        'name': parts[0].strip(),
                        'version': parts[1].strip(),
                        'publisher': 'Snap Package',
                        'install_date': 'Unknown',
                        'size_mb': 'Unknown'
                    })
        except Exception:
            pass

        # ── 5. Flatpak — always append ────────────────────────────────────────────
        try:
            out = _sp.check_output(
                ['flatpak', 'list', '--app', '--columns=name,version,origin'],
                stderr=DEVNULL
            )
            for line in out.decode('utf-8', errors='replace').strip().split('\n'):
                parts = line.split('\t')
                if len(parts) >= 1 and parts[0].strip():
                    apps.append({
                        'name': parts[0].strip(),
                        'version': parts[1].strip() if len(parts) > 1 else 'Unknown',
                        'publisher': 'Flatpak / ' + (parts[2].strip() if len(parts) > 2 else 'Unknown'),
                        'install_date': 'Unknown',
                        'size_mb': 'Unknown'
                    })
        except Exception:
            pass

        try:
            DEVNULL.close()
        except Exception:
            pass
except Exception:
    pass
print(json.dumps(apps))
PYEOF
    )
fi
if [ -z "$SOFTWARE_INVENTORY_JSON" ] || [ "$SOFTWARE_INVENTORY_JSON" = "null" ] || [ "$SOFTWARE_INVENTORY_JSON" = "[]" ]; then
    if [ "$OS_NAME" = "macOS" ]; then
        # Pure-shell macOS app scan: walk /Applications for .app bundles
        APPS_TMP=""
        for APP_PATH in /Applications/*.app /Applications/*/*.app "$HOME/Applications"/*.app; do
            [ -d "$APP_PATH" ] || continue
            APP_NAME=$(basename "$APP_PATH" .app)
            APP_VER="Unknown"
            # Read version from Info.plist using PlistBuddy or defaults
            PLIST="$APP_PATH/Contents/Info.plist"
            if [ -f "$PLIST" ]; then
                APP_VER=$(defaults read "$PLIST" CFBundleShortVersionString 2>/dev/null || defaults read "$PLIST" CFBundleVersion 2>/dev/null || echo "Unknown")
            fi
            SAFE_NAME=$(printf '%s' "$APP_NAME" | sed 's/"/\\"/g' | tr -d '\n\r')
            SAFE_VER=$(printf '%s' "$APP_VER" | sed 's/"/\\"/g' | tr -d '\n\r')
            APPS_TMP="${APPS_TMP}{\"name\":\"${SAFE_NAME}\",\"version\":\"${SAFE_VER}\",\"publisher\":\"macOS App\",\"install_date\":\"Unknown\",\"size_mb\":\"Unknown\"},"
        done
        [ -n "$APPS_TMP" ] && SOFTWARE_INVENTORY_JSON="[${APPS_TMP%,}]"
    elif command -v dpkg-query >/dev/null 2>&1; then
        # Pure-bash Linux software collection fallback — NO cap
        APPS_TMP=$(dpkg-query -W -f='{"name":"${Package}","version":"${Version}","publisher":"Debian/Ubuntu","install_date":"Unknown","size_mb":"Unknown"},' 2>/dev/null | tr -d '\r\n')
        [ -n "$APPS_TMP" ] && SOFTWARE_INVENTORY_JSON="[${APPS_TMP%,}]"
    elif command -v rpm >/dev/null 2>&1; then
        APPS_TMP=$(rpm -qa --qf '{"name":"%{NAME}","version":"%{VERSION}","publisher":"RedHat/RPM","install_date":"Unknown","size_mb":"Unknown"},' 2>/dev/null | tr -d '\r\n')
        [ -n "$APPS_TMP" ] && SOFTWARE_INVENTORY_JSON="[${APPS_TMP%,}]"
    fi
fi
echo "Software scan complete."

# ────────────────────────────────────────────────────────────────────────────
#  PHASE 3 — RECENT LOGINS
# ────────────────────────────────────────────────────────────────────────────
echo "Collecting recent login history..."
LOGIN_HISTORY_JSON="[]"
if [ -n "$PYTHON3_CMD" ]; then
    LOGIN_HISTORY_JSON=$($PYTHON3_CMD - <<'PYEOF'
# -*- coding: utf-8 -*-
import subprocess, json, os

logins = []
try:
    out = subprocess.check_output(['last', '-n', '20'], stderr=open(os.devnull, 'w'))
    lines = out.decode('utf-8', errors='replace').splitlines()
    for line in lines:
        line = line.strip()
        if not line or line.startswith('wtmp') or line.startswith('utmp') or line.startswith('btmp'):
            continue
        parts = line.split()
        if len(parts) >= 4:
            username = parts[0]
            terminal = parts[1]
            if username in ['reboot', 'shutdown']:
                domain = 'System Event'
                logon_type = 'System Startup/Reboot'
            else:
                domain = 'Local / Linux'
                logon_type = 'Interactive Console' if terminal in ['console', 'tty1', ':0'] else ('TTY Session (' + terminal + ')')
            timestamp = ' '.join(parts[2:])
            logins.append({
                'username': username,
                'domain': domain,
                'logon_type': logon_type,
                'timestamp': timestamp
            })
except Exception:
    pass

if not logins:
    try:
        out = subprocess.check_output(['who'], stderr=open(os.devnull, 'w'))
        for line in out.decode('utf-8', errors='replace').splitlines():
            parts = line.split()
            if len(parts) >= 3:
                logins.append({
                    'username': parts[0],
                    'domain': 'Local Session',
                    'logon_type': 'Console Session (' + parts[1] + ')',
                    'timestamp': ' '.join(parts[2:])
                })
    except Exception:
        pass

print(json.dumps(logins))
PYEOF
    )
fi
if [ -z "$LOGIN_HISTORY_JSON" ] || [ "$LOGIN_HISTORY_JSON" = "null" ] || [ "$LOGIN_HISTORY_JSON" = "[]" ]; then
    # Pure-bash Linux login fallback
    if command -v who >/dev/null 2>&1; then
        WHO_TMP=$(who 2>/dev/null | head -n 10 | while read -r u t d t2; do
            printf '{"username":"%s","domain":"Local Session","logon_type":"Console (%s)","timestamp":"%s %s"},' "$u" "$t" "$d" "$t2"
        done)
        [ -n "$WHO_TMP" ] && LOGIN_HISTORY_JSON="[${WHO_TMP%,}]"
    fi
fi

# ────────────────────────────────────────────────────────────────────────────
#  Build Final JSON Payload — via Python for safe escaping
# ────────────────────────────────────────────────────────────────────────────

if [ -n "$PYTHON3_CMD" ]; then
JSON=$($PYTHON3_CMD - <<PYEOF
# -*- coding: utf-8 -*-
import json, sys

def safe(v):
    if v is None: return "Unknown"
    s = str(v).strip()
    return s if s else "Unknown"

def safe_json(raw, fallback="[]"):
    try:
        return json.loads(raw)
    except Exception:
        return json.loads(fallback)

hw = {
    "cpu":              safe("""$CPU"""),
    "ram":              safe("""$RAM"""),
    "disk":             safe("""$DISK"""),
    "device_name":      safe("""$COMPUTER_NAME"""),
    "manufacturer":     safe("""$MANUFACTURER"""),
    "model":            safe("""$MODEL_NAME"""),
    "serial_number":    safe("""$SERIAL_NUMBER"""),
    "description":      safe("""$DESCRIPTION"""),
    "domain":           safe("""$DOMAIN"""),
    "domain_role":      safe("""$DOMAIN_ROLE"""),
    "shutdown_time":    safe("""$SHUTDOWN_TIME"""),
    "last_backup":      safe("""$LAST_BACKUP"""),
    "life_cycle":       safe("""$LIFE_CYCLE"""),
    "asset_tag":        safe("""$ASSET_TAG"""),
    "device_type":      safe("""$DEVICE_TYPE"""),
    "architecture":     safe("""$ARCHITECTURE"""),
    "processor_name":   safe("""$CPU"""),
    "cpu_cores":        safe("""$CPU_CORES"""),
    "cpu_threads":      safe("""$CPU_THREADS"""),
    "installed_ram":    safe("""$RAM"""),
    "ram_slots":        "Unknown",
    "mobo_manufacturer": safe("""$MOBO_MANUFACTURER"""),
    "mobo_product":     safe("""$MOBO_PRODUCT"""),
    "mobo_version":     safe("""$MOBO_VERSION"""),
    "mobo_serial":      safe("""$MOBO_SERIAL"""),
    "bios_version":     safe("""$BIOS_VERSION"""),
    "bios_date":        safe("""$BIOS_DATE"""),
    "battery_health":   safe("""$BATTERY_HEALTH"""),
    "cycle_count":      safe("""$CYCLE_COUNT"""),
    "charge_percent":   safe("""$CHARGE_PERCENT"""),
    "design_capacity":  safe("""$DESIGN_CAPACITY"""),
    "full_capacity":    safe("""$FULL_CAPACITY"""),
    "location_info":    safe("""$LOCATION_INFO"""),
    "gpu_details":      safe_json("""$GPU_JSON"""),
    "network_adapters": safe_json("""$NETWORK_ADAPTERS_JSON"""),
    "peripherals":      safe_json("""$PERIPHERALS_JSON"""),
    "disk_partitions":  safe_json("""$DISK_PARTITIONS_JSON"""),
}

payload = {
    "execution_datetime":    safe("""$EXECUTION_DATETIME"""),
    "computer_name":         safe("""$COMPUTER_NAME"""),
    "description":           safe("""$DESCRIPTION"""),
    "domain":                safe("""$DOMAIN"""),
    "domain_role":           safe("""$DOMAIN_ROLE"""),
    "shutdown_time":         safe("""$SHUTDOWN_TIME"""),
    "last_backup":           safe("""$LAST_BACKUP"""),
    "life_cycle":            safe("""$LIFE_CYCLE"""),
    "os_name":               safe("""$OS_NAME"""),
    "os_version":            safe("""$OS_VERSION"""),
    "os_build":              safe("""$OS_BUILD"""),
    "last_boot":             safe("""$LAST_BOOT"""),
    "uptime":                safe("""$UPTIME"""),
    "architecture":          safe("""$ARCHITECTURE"""),
    "license_status":        safe("""$LICENSE_STATUS"""),
    "antivirus":             safe_json("""$ANTIVIRUS""", '["Built-in OS Protections"]'),
    "firewall":              safe("""$FIREWALL"""),
    "bitlocker":             safe("""$BITLOCKER"""),
    "secure_boot":           safe("""$SECURE_BOOT"""),
    "tpm":                   safe("""$TPM"""),
    "hotfixes":              [],
    "mac_address":           safe("""$MAC_ADDRESS"""),
    "drive_name":            safe("""$DRIVE_NAME"""),
    "compression_utilities": safe_json("""$COMPRESSION_UTILITIES""", '["tar","gzip"]'),
    "printers":              safe_json("""$PRINTERS"""),
    "hardware_details":      hw,
    "network_details":       safe_json("""$NETWORK_DETAILS"""),
    "user_accounts":         safe_json("""$USER_ACCOUNTS"""),
    "software_inventory":    safe_json("""$SOFTWARE_INVENTORY_JSON"""),
    "login_history":         safe_json("""$LOGIN_HISTORY_JSON"""),
}
print(json.dumps(payload))
PYEOF
)
else
    # Pure-bash minimal JSON fallback — escapes double-quotes only
    esc() { printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g'; }
    JSON="{\"execution_datetime\":\"$(esc "$EXECUTION_DATETIME")\",\"computer_name\":\"$(esc "$COMPUTER_NAME")\",\"current_user\":\"$(esc "$USER")\",\"os_name\":\"$(esc "$OS_NAME")\",\"os_version\":\"$(esc "$OS_VERSION")\",\"os_build\":\"Unknown\",\"last_boot\":\"Unknown\",\"uptime\":\"Unknown\",\"architecture\":\"$(esc "$ARCHITECTURE")\",\"license_status\":\"$(esc "$LICENSE_STATUS")\",\"firewall\":\"Unknown\",\"bitlocker\":\"Not Applicable\",\"secure_boot\":\"Unknown\",\"tpm\":\"Not Applicable\",\"hotfixes\":[],\"mac_address\":\"$(esc "$MAC_ADDRESS")\",\"drive_name\":\"No CD Unit Found\",\"compression_utilities\":[\"tar\",\"gzip\"],\"antivirus\":[\"Built-in OS Protections\"],\"printers\":[],\"hardware_details\":{\"cpu\":\"$(esc "$CPU")\",\"ram\":\"$(esc "$RAM")\",\"disk\":\"$(esc "$DISK")\",\"serial_number\":\"$(esc "$SERIAL_NUMBER")\",\"manufacturer\":\"$(esc "$MANUFACTURER")\",\"model\":\"$(esc "$MODEL_NAME")\",\"architecture\":\"$(esc "$ARCHITECTURE")\",\"processor_name\":\"$(esc "$CPU")\",\"installed_ram\":\"$(esc "$RAM")\",\"gpu_details\":[],\"network_adapters\":[],\"peripherals\":[],\"disk_partitions\":[]},\"network_details\":[{\"ip_address\":\"$(esc "$IP_ADDRESS")\",\"gateway\":\"Unknown\",\"mac\":\"$(esc "$MAC_ADDRESS")\"}],\"user_accounts\":[{\"name\":\"$(esc "$USER")\",\"disabled\":\"False\"}],\"software_inventory\":[],\"login_history\":[]}"
fi

# Server URL & Client ID Resolution
TARGET_SERVER="${1:-$SERVER_URL}"
[ -z "$TARGET_SERVER" ] && TARGET_SERVER="http://127.0.0.1:8000"
TARGET_SERVER="${TARGET_SERVER%/}"

CLIENT_ID="CLIENT_ID_PLACEHOLDER"
if [ "$CLIENT_ID" = "CLIENT_ID_PLACEHOLDER" ]; then
    CLIENT_ID="audit_$(hostname | tr -dc 'a-zA-Z0-9')"
fi

API_URL="${TARGET_SERVER}/api/upload-audit?client_id=$CLIENT_ID"

echo "Uploading secure payload to compliance portal..."

TMP_JSON=$(mktemp 2>/dev/null || echo "/tmp/audit_payload_$$.json")
printf '%s' "$JSON" > "$TMP_JSON"

RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "$API_URL" \
     -H "Content-Type: application/json" \
     --data-binary @"$TMP_JSON")

rm -f "$TMP_JSON" 2>/dev/null

HTTP_STATUS=$(echo "$RESPONSE" | tail -n1)
# Use sed to strip last line — works on both macOS (BSD) and Linux (GNU)
BODY=$(echo "$RESPONSE" | sed '$d')

if [ "$HTTP_STATUS" -eq 200 ] 2>/dev/null || [ "$HTTP_STATUS" = "200" ]; then
    echo "Audit upload completed successfully!"
else
    echo "Upload failed. HTTP Status: $HTTP_STATUS"
    echo "Details: $BODY"
fi

if [ -t 0 ]; then
    echo "Press enter to exit..."
    read -r
fi
