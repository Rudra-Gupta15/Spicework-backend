# InfraPulse

**IT Asset Management & Workstation Compliance Audit Platform**  
*Engineered by Prevoyance IT Solutions* — Version 3.0.0

---

## Contents

- [Running the project](#running-the-project)

1. [About the project](#1-about-the-project)
2. [Workflow](#2-workflow)
3. [Technology stack](#3-technology-stack)
4. [OS-level data extraction](#4-os-level-data-extraction)
5. [Functional scope and quality attributes](#5-functional-scope-and-quality-attributes)
6. [Endpoint agent design](#6-endpoint-agent-design)
7. [Related documents](#related-documents)

---

## Running the project

The backend is a package rooted at this repository, so it must be launched as
`backend.main:app` with the repository root as the working directory. Paths for
`audits.db`, `logs/` and `user_info/` are resolved relative to that directory.

```bash
# Backend — from the repository root
pip install -r backend/requirements.txt
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

`--host 0.0.0.0` is required whenever an agent on another machine has to reach
this server. Uvicorn binds to `127.0.0.1` by default, which is invisible to the
network — the deployment commands on the Agent page will fail with *"Unable to
connect to the remote server"* even though the same URL works locally.

```bash
# Frontend — from the Spicework-frontend repository
npm install
npm run dev            # http://localhost:5173, calls the backend on :8000
```

Interactive API docs are served at `/docs`.

### Configuration

`.env` is read from both the repository root and `backend/`. Copy
`backend/.env.example` and fill in the PostgreSQL credentials. `.env` is
git-ignored and must never be committed.

### Production build

```bash
VITE_API_BASE_URL= npm run build
```

The variable **must** be empty for production. Vite loads a plain `.env` in every
mode, so a leftover `VITE_API_BASE_URL=http://localhost:8000` gets compiled into
the bundle and every request goes to the visitor's own machine. Verify with
`grep -c localhost dist/assets/*.js` — it must print `0`.

Deploy the backend before the frontend: backend changes are additive, so the
running UI keeps working in between, whereas a frontend built against endpoints
that do not exist yet fails immediately.

---

## 1. About the project

InfraPulse collects hardware, software, network and user inventory from Windows, macOS and Linux workstations across branch offices, and turns each collection into a **regulatory compliance report** — a formatted PDF and a schema-conformant XML.

It is built around a single deliverable: **a prescribed audit document**. That distinguishes it from general device-management platforms, which produce live dashboards rather than documents.

### What makes it different

| Feature | Description |
|---|---|
| **Agentless option** | A workstation can be audited once, by running a launcher, with nothing left installed |
| **Scheduled option** | Or an installer registers a recurring audit via Task Scheduler / systemd / launchd |
| **Fixed-format output** | PDF + XML in the exact layout the audit mandate specifies |
| **Asset lifecycle** | Warranty, purchase order, supplier and vendor data that no endpoint agent can read |
| **File-storage fallback** | Report PDFs and XML are written to disk regardless of database state, so a DB outage degrades rather than fails |

### Scale of the codebase

| Component | File | Lines |
|---|---|---|
| App entrypoint (router wiring) | `backend/main.py` | 69 |
| API surface | `backend/routers/` (16 modules) | — |
| Audit data access | `backend/legacy_db.py` | 668 |
| Device / inventory data access | `backend/devices_db.py` | 690 |
| Auth & inventory Postgres | `backend/auth_db.py` | 665 |
| macOS / Linux collector | `scripts/audit.sh` | 1,352 |
| Windows collector | `scripts/audit.ps1` | 1,111 |
| Service installers | `scripts/install_service.*` | ~180 |

> The single-file `main.py` described in earlier revisions has been split into
> `routers/`, `services/` and `models/`; the React SPA now lives in its own
> repository rather than as a single `index.html`.

### Data captured

**67 required fields** across seven groups — Device Data (25), Disk Information (10), Partitions (5), Network Adaptors (12), Peripherals (4), Video Controllers (4), Users (7) — plus full software inventory, hotfix history, login history, antivirus state, and a 17-field asset lifecycle record.

---

## 2. Workflow

### End-to-end flow

```mermaid
flowchart TD
    Operator["Operator"] --> OpenPortal["Open portal / enter branch details"]
    OpenPortal --> GenSession["Generate client_id & create session"]
    
    GenSession --> ServeLauncher["Serve launcher (.vbs / .command / .sh)"]
    ServeLauncher --> TargetWorkstation["Target Workstation (Launcher runs)"]
    
    TargetWorkstation --> ExecMemory["Collector executes in memory"]
    ExecMemory --> QueryOS["Query OS APIs & Validate JSON"]
    QueryOS --> UploadAudit["POST /api/upload-audit"]
    
    UploadAudit --> ValidateAudit["Validate Pydantic AuditData"]
    
    ValidateAudit --> GenPDF["Generate PDF (ReportLab)"]
    ValidateAudit --> GenXML["Generate XML (ElementTree)"]
    
    GenPDF --> PersistDB["Persist PostgreSQL + files"]
    GenXML --> PersistDB
    
    PersistDB --> Dashboards["Dashboards (5 tabs)"]
```

### Collector internal sequence

```mermaid
flowchart TD
    Start["Start"] --> PreSeed["Pre-seed all fields = Unknown"]
    PreSeed --> OSIdentity["OS / device identity"]
    OSIdentity --> Hardware["Hardware (CPU, RAM, disk, GPU)"]
    Hardware --> NetAdapters["Network adapters"]
    NetAdapters --> Peripherals["Peripherals (connected & USB history)"]
    Peripherals --> SwInventory["Software inventory"]
    SwInventory --> UsersLogins["Users + login history"]
    UsersLogins --> AssembleJSON["Assemble JSON"]
    
    AssembleJSON --> CheckValid{"Valid JSON?"}
    CheckValid -- "Yes" --> CheckReachable{"Server reachable?"}
    CheckValid -- "No" --> Abort["Abort"]
    
    CheckReachable -- "Yes" --> Upload["Upload"]
    CheckReachable -- "No" --> SaveReview["Save payload for review"]
    
    Upload --> ExitDiag["Print diagnostics & exit"]
```

### Report generation

```mermaid
flowchart TD
    RawJSON["raw JSON"] --> Validate["AuditData validation"]
    
    Validate -- "ok" --> TypedModel["typed model"]
    Validate -- "fails" --> Bypass["model_construct bypass"]
    
    TypedModel --> WriteJSON["Write audit_*.json"]
    WriteJSON --> PDFXMLBuilder["PDF Builder & XML Builder"]
    Bypass --> PDFXMLBuilder
    
    PDFXMLBuilder --> CheckOnDisk{"Both files on disk?"}
    
    CheckOnDisk -- "Yes" --> SessionCompleted["session = completed"]
    CheckOnDisk -- "No" --> SessionFailed["session = failed (HTTP 500)"]
```

---

## 3. Technology stack

### Backend

| Layer | Technology | Role |
|---|---|---|
| **Web framework** | FastAPI | Async HTTP API, automatic OpenAPI docs |
| **ASGI server** | Uvicorn | Production server |
| **Validation** | Pydantic v2 | `ConfigDict`, `field_validator`, typed payload models |
| **Database** | PostgreSQL | `psycopg2-binary`, JSONB columns, `RealDictCursor` |
| **PDF generation** | ReportLab | `SimpleDocTemplate`, `Table`, `Paragraph`, `KeepTogether` |
| **XML generation** | `xml.etree.ElementTree` | Standard library |
| **Config** | python-dotenv | `.env` loading |
| **Concurrency** | `concurrent.futures` | Thread pools for network scanning |
| **Remote execution** | `pywinrm`, `pypsexec`, `paramiko`, `smbprotocol` | Optional, lazily imported |

### Frontend

Lives in its own repository (`Spicework-frontend`).

| Layer | Technology | Role |
|---|---|---|
| **Framework** | React 19 + TypeScript | Component-based SPA |
| **Build** | Vite | Dev server and production bundle |
| **Routing** | React Router | Client-side routes |
| **Styling** | Tailwind CSS v4 | Utility-first design system |
| **Icons** | lucide-react | — |

In development Vite serves the UI on `:5173` and calls the backend directly via
`VITE_API_BASE_URL`. In production the variable is left unset so the app issues
relative requests, which the reverse proxy forwards to FastAPI.

> **Every backend call must use an `/api/` prefix.** nginx proxies `/api/*` to
> FastAPI and serves the built SPA for everything else, so an un-prefixed path
> returns `index.html` and fails JSON parsing in the browser.

### Endpoint collectors

| Platform | Language | Runtime requirement |
|---|---|---|
| **Windows** | PowerShell 5.1+ | Built into Windows |
| **macOS / Linux** | Bash + embedded Python 3 | Both present by default on target systems |

### Scheduling

| Platform | Mechanism |
|---|---|
| **Windows** | `schtasks` — hourly trigger + `ONSTART` |
| **Linux** | `systemd timer`, `cron` fallback |
| **macOS** | `launchd` LaunchDaemon with `StartInterval` |

---

## 4. OS-level data extraction

How each platform is actually queried. **No kernel drivers, no privileged hooks** — every value comes from a documented operating-system interface.

### 4.1 Windows

| Area | API / library | Notes |
|---|---|---|
| **OS identity** | `Get-CimInstance Win32_OperatingSystem` | Caption, version, architecture, `CSDVersion` for service pack |
| **OS build name** | Registry `HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion` | `DisplayVersion` + `CurrentBuild` + `UBR` → 25H2 (Build 26200.8894). WMI returns only kernel version |
| **Device type** | `Win32_SystemEnclosure.ChassisTypes` | DMI code mapped via switch; falls back to `Win32_ComputerSystem.PCSystemType`; VM detected by model regex |
| **Licence status** | `SoftwareLicensingProduct` | Filtered by Windows `ApplicationID`; `LicenseStatus` 0–6 mapped to names |
| **Hotfixes** | `Get-HotFix` | Caption, HotFixID, description, install date |
| **System identity** | `Win32_ComputerSystem` | Manufacturer, model, domain, domain role, total RAM |
| **CPU** | `Win32_Processor` | Name, core count, processor type |
| **Memory slots** | `Win32_PhysicalMemory` | Per-module capacity, slot count, max supported |
| **BIOS** | `Win32_BIOS` | Version and release date |
| **Physical disks** | `Win32_DiskDrive` | Model, serial, firmware, size, interface |
| **SSD vs HDD** | `MSFT_PhysicalDisk` in `root\Microsoft\Windows\Storage` | **Authoritative** — `MediaType` 3=HDD, 4=SSD, 5=SCM. Model-name regex used only as fallback |
| **Disk → volume link** | `Get-CimAssociatedInstance` | Walks `DiskDrive` → `DiskPartition` → `LogicalDisk` for file system and free space |
| **Partitions** | `Win32_LogicalDisk` | Device ID, file system, size, free space, boot flag |
| **Optical drive** | `Win32_CDROMDrive` | Absence reported explicitly, not assumed |
| **GPU** | `Win32_VideoController` | Name, driver version, `AdapterRAM` for VRAM |
| **Network adapters** | `Win32_NetworkAdapter` + `Win32_NetworkAdapterConfiguration` | MAC, speed, IPv4/IPv6, gateway, DNS, DHCP server, MTU |
| **Primary MAC** | `Get-NetAdapter` | First adapter with `Status -eq "Up"` |
| **Printers** | `Win32_Printer` | Name, system name, BIDI flag, port, extended status |
| **Peripherals / devices** | `Get-PnpDevice`, `Win32_PnPEntity` | Every plug-and-play device across USB, MTP/WPD mobile phones, PCI, Bluetooth, serial, display |
| **Antivirus** | `AntiVirusProduct` in `root\SecurityCenter2` | The only reliable enumeration of third-party AV |
| **Software inventory** | Registry — 3 `Uninstall` hives | `HKLM`, `HKLM\WOW6432Node`, `HKCU`. Omitting `WOW6432Node` hides all 32-bit apps |
| **Software last-used** | `%SystemRoot%\Prefetch\*.pf` | `LastWriteTime` of the prefetch file ≈ last run. Fuzzy name match; falls back to install-dir mtime |
| **User accounts** | `Get-LocalUser` | Name, enabled state, home directory, last logon |
| **Login history** | `Get-WinEvent` — Security log, Event ID 4624 | **Requires Administrator**. Parsed as XML; `LogonType` filtered to 2/7/10/11; machine accounts excluded |
| **Uptime** | `Win32_OperatingSystem.LastBootUpTime` | Converted to seconds + human display |
| **Geolocation** | HTTP → `ip-api.com/json/` | Public IP, city, region, country. The only outbound call |

### 4.2 Linux

| Area | API / library | Notes |
|---|---|---|
| **OS identity** | `/etc/os-release`, `uname -s -r -m` | `NAME`, `VERSION_ID`, `PRETTY_NAME`, kernel release |
| **Hardware identity** | `/sys/class/dmi/id/*` | **SMBIOS via sysfs** — vendor, product name, serial, chassis type, BIOS version/date. Same firmware tables WMI reads |
| **Device type** | `/sys/class/dmi/id/chassis_type` | **Identical numbering to Windows** `ChassisTypes` — the switch table is shared |
| **Container detection** | `/.dockerenv`, `/proc/1/cgroup` | Matches `docker|lxc|kubepods` |
| **VM detection** | `systemd-detect-virt` | Reports the specific hypervisor |
| **CPU** | `/proc/cpuinfo`, `lscpu` | Model name, core and socket counts |
| **Memory** | `/proc/meminfo`, `dmidecode` | Total memory; DMI for slot count and max capacity |
| **Uptime** | `/proc/uptime` | Seconds since boot |
| **Block devices** | `/sys/block/*` | `sr[0-9]*` entries are optical drives |
| **SSD vs HDD** | `/sys/block/*/queue/rotational` | **Kernel's own flag** — 0 = SSD, 1 = HDD. Not an inference |
| **Disks / partitions** | `lsblk`, `df` | Size, mount point, file system, free space |
| **GPU** | `lspci -k` | `-k` reports the kernel driver **actually bound**, not merely installed |
| **USB devices** | `lsusb` | Vendor, product, bus and device number |
| **PCI devices** | `lspci` | Class, vendor, device |
| **Network interfaces** | `ip addr`, `ip link`, `ifconfig` | MAC, IPv4/IPv6, MTU, state |
| **Network connection** | `nmcli -t -f ...` | Active connection, SSID. Terse mode escapes colons as `\:` |
| **Routing / gateway** | `ip route` | Default gateway |
| **DNS** | `/etc/resolv.conf` | Nameservers, search domain |
| **Software inventory** | `dpkg-query -W`, `rpm -qa` | Debian first; `rpm` runs only if `dpkg` returned nothing |
| **Software last-used** | `shutil.which()` + `os.path.getatime()` | Access time of the resolved binary. Unreliable under `noatime`/`relatime` |
| **Users** | `getent passwd`, `/etc/shadow` | Name, home directory, shell, account state |
| **Login history** | `last`, `lastlog` | Login and shutdown records |
| **Printers** | `lpstat`, CUPS | Name, state, queues |

### 4.3 macOS

| Area | API / library | Notes |
|---|---|---|
| **OS identity** | `sw_vers -productVersion`, `-buildVersion` | Product version and build |
| **Hardware model** | `sysctl -n hw.model` | Model identifier, e.g. `MacBookPro18,3` |
| **Device type** | `hw.model` string match | `*Book*` → Laptop, `*iMac*` → All-in-One, `*mini*` → Desktop |
| **CPU / RAM** | `sysctl -n hw.ncpu`, `hw.memsize` | Core count, physical memory bytes |
| **System identity** | `system_profiler SPHardwareDataType` | Serial number, model name, chip, memory |
| **Software inventory** | `system_profiler SPApplicationsDataType -json` | **Native JSON output** — parsed directly, no text scraping |
| **Software last-used** | `os.path.getatime()` on the `.app` bundle | Falls back to `lastModified` from `system_profiler` |
| **GPU** | `system_profiler SPDisplaysDataType` | Chipset, VRAM, resolution |
| **Storage** | `system_profiler SPStorageDataType`, `diskutil` | Volumes, size, free space, file system |
| **USB devices** | `system_profiler SPUSBDataType` | Device tree with vendor and product |
| **Optical drive** | `system_profiler SPDiscBurningDataType`, `drutil status` | Two sources tried in order |
| **Device tree** | `ioreg` | IORegistry for low-level device data |
| **Network interfaces** | `ifconfig`, `networksetup` | MAC, addresses, hardware ports |
| **Wi-Fi / IP** | `ipconfig getifaddr en0` then `en1` | Adapter name varies by model |
| **Users** | `dscl . -list /Users`, `dscacheutil` | Directory Services |
| **Login history** | `last` | Login and reboot history |
| **Printers** | `lpstat -p`, CUPS | CUPS printer state |

### 4.4 Extraction design notes

* **Why `system_profiler -json` matters**: macOS is the only platform with a native structured inventory. Its collectors hand output straight to `json.loads()`, making the macOS branches consistently shorter and less fragile than the Linux equivalents, which parse text.
* **Why Linux and Windows share a chassis table**: Both ultimately read the same SMBIOS/DMI tables published by system firmware — Windows through `Win32_SystemEnclosure`, Linux through `/sys/class/dmi/id/`. The numeric codes are identical, so one switch statement serves both.
* **Authoritative source before heuristic**: Wherever the OS knows an answer, that source is queried first and inference is the fallback — `MSFT_PhysicalDisk.MediaType` and `queue/rotational` over model-name matching; `ChassisTypes` over guessing; Security event log over `LastLogon`.

---

## 5. Functional scope and quality attributes

### 5.1 Functional scope

| # | Capability | Description | Status |
|---|---|---|---|
| F1 | **Compliance audit** | Launcher distribution, collection, PDF + XML generation, status polling, download | Complete |
| F2 | **Asset registry** | CRUD over 17 lifecycle fields — owner, warranty, PO, supplier, vendor, status | Complete |
| F3 | **Device audits** | Per-device hardware specs, software inventory, incremental change tagging | Complete |
| F4 | **Change reporting** | Diff of the two most recent audits — hardware deltas, installed/removed software | Complete |
| F5 | **Network discovery** | TCP port scan over a CIDR, ARP fallback, SNMP check (Port 161), four-source name enrichment | Complete — LAN bound |
| F6 | **Wi-Fi dashboard** | Scan networks, connect, RSSI distance estimation, enumerate subnet devices | Windows-centric |
| F7 | **Scheduled re-audit** | Recurring collection via native OS schedulers | Complete |
| F8 | **Remote audit trigger** | WinRM / PsExec / SSH initiation | Partial — stub |
| F9 | **Authentication** | — | Not implemented |
| F10 | **Vulnerability management** | — | Not in scope |

### 5.2 Quality attributes

| Attribute | Design approach | Current state |
|---|---|---|
| **Reliability** | Pre-seeded fallbacks + `try/except` on every collector; a failed field never aborts the audit. PDF and XML generated independently | **Strong.** The collector cannot crash on a collection failure |
| **Data integrity** | Five validation layers: pre-seed → normalise → authoritative source → structural JSON validation → server-side Pydantic | **Strong on structure.** No cross-source reconciliation or attestation |
| **Availability** | PostgreSQL with a complete file-storage fallback for reports; DB outage degrades rather than fails | **Strong** |
| **Portability** | Three collectors covering Windows, macOS, Linux; shared DMI code table; tool-availability guards before every external command | **Strong** |
| **Usability** | Single-page UI, no build step; double-click launchers; self-elevating installers; four numbered diagnostics on connection failure | **Strong** |
| **Performance** | Wide thread pools (up to 512 workers) for scanning; reverse DNS capped at 3s; /24 scan completes in seconds | **Good** for LAN scale |
| **Scalability** | — | **Weak.** In-memory `sessions` dict forces `--workers 1`; `audit_results` grows unbounded; fallback paths do O(n) directory scans. Practical ceiling ~200–500 hosts |
| **Security** | — | **Weak.** No authentication on any endpoint; HTTP by default; Wi-Fi passwords stored in plaintext; `curl \| bash` install channel |
| **Maintainability** | Section-banner organisation; extensive bug post-mortem comments | **Mixed.** ~14,266 lines with duplicated endpoints and repeated report-table blocks |
| **Observability** | Dual logging to file and stdout; per-step console output during collection | **Adequate.** 19 of 54 exception handlers are silent `pass` |
| **Extensibility** | `extra="allow"` on every Pydantic model — new fields accepted without schema changes or breaking installed agents | **Strong** |
| **Auditability** | Every audit persisted as raw JSON alongside the generated PDF and XML | **Strong** for retention, **weak** for provenance |

### 5.3 Known constraints

1. **F5 and F6 require the server on the target LAN** — they inspect the network the server is attached to, which blocks central cloud deployment of those two features.
2. **Software inventory is truncated to 150 entries on macOS and Linux**; Windows is uncapped.
3. **Login history requires Administrator** on Windows; otherwise a weaker fallback is used silently.
4. **"Unknown" is ambiguous** — it means both "absent" and "collection failed".

---

## 6. Endpoint agent design

InfraPulse supports **two deployment modes** from the same collector code.

### Mode 1 — One-shot

```mermaid
flowchart LR
    A["Operator downloads launcher from portal"] --> B["Double-click"] --> C["Fetch collector over HTTP"] --> D["Execute in memory"] --> E["Upload + exit"] --> F["Nothing installed"]
```

### Mode 2 — Scheduled

```mermaid
flowchart LR
    A["Run installer as admin/root"] --> B["Write config + device.id"] --> C["Install runner script"] --> D["Register with OS scheduler"] --> E["Runs every N hours + at boot"]
```

### 6.1 Launcher artefacts

| Platform | Artefact | Served by | Mechanism |
|---|---|---|---|
| **Windows** | `verify_system_<id>.vbs` / `.exe` | `/download-vbs` / `/download-exe` | `WScript.Shell` / C# wrapper runs PowerShell hidden: `Invoke-RestMethod ... \| Invoke-Expression` |
| **macOS** | `verify_system_<id>.command` | `/download-mac` | `curl -s "..." \| bash` — `.command` is double-clickable in Finder |
| **Linux** | `verify_system_<id>.sh` | `/download-linux` | `curl -s "..." \| bash` |

There is no pre-built standalone `.exe` required (though C# compiled launcher is supported). The Windows path uses a `.vbs` wrapper — chosen because double-clicking it runs PowerShell with no visible console window (`objShell.Run command, 0, False`). The installer entry point is `Install-Audit.bat`, which self-elevates:

```cmd
net session >nul 2>&1
if %errorlevel%==0 goto RUN
powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
```

### 6.2 Key design property — the collector never touches disk

In one-shot mode the collector is fetched and executed entirely in memory:

```mermaid
flowchart LR
    A[".vbs"] --> B["powershell -ExecutionPolicy Bypass -WindowStyle Hidden"] --> C["Invoke-RestMethod 'SERVER_URL/download-script?client_id=CLIENT_ID'"] --> D["Invoke-Expression"]
```

The server substitutes `base_url` and `CLIENT_ID_PLACEHOLDER` into the script text at serve time, so the collector always calls back on the host the client actually used. Nothing is written to the workstation, nothing needs uninstalling.

### 6.3 Scheduled mode

The installers (`scripts/install_service.*`) read a shared configuration:

| Setting | Purpose |
|---|---|
| `SERVER_URL` | Server address — must be the network IP or Cloudflare tunnel, not localhost |
| `INTERVAL_HOURS` | Audit frequency |
| `INTERVAL_MINUTES` | Testing override |
| `JITTER_SECONDS` | Random pre-run delay so a branch does not hit the server simultaneously |

Each installer:
1. **Verifies elevation** — Administrator / root / sudo, and refuses otherwise
2. **Checks prerequisites** — curl, python3 / PowerShell
3. **Tests reachability** — `curl -s -f -m 10 "$SERVER_URL/api/devices"`
4. **Generates a stable `device.id`** — reused across runs so audits correlate to one machine
5. **Writes a small runner script** — deliberately minimal; it only fetches and executes the current collector, so server-side collector updates apply without revisiting the PC
6. **Registers the schedule**

| Platform | Registration | Boot trigger |
|---|---|---|
| **Windows** | `schtasks /SC HOURLY /MO <n> /RU SYSTEM /RL HIGHEST` | `/SC ONSTART /DELAY 0005:00` |
| **Linux** | `systemd timer`, `cron` fallback to `/etc/cron.d/` | `@reboot sleep 300` |
| **macOS** | `LaunchDaemon .plist` with `StartInterval` | `RunAtLoad` |

Jitter is applied before each scheduled run:
```bash
WAIT=$(( $(od -An -N2 -tu2 < /dev/urandom | tr -d ' ') % JITTER ))
sleep "$WAIT"
```
Without it, every PC in a branch uploads at the same second after a power restoration.

### 6.4 Agent execution contract

| Property | Behaviour |
|---|---|
| **Privileges** | Elevation required to *install* a schedule. One-shot mode runs unelevated, but login history then falls back to a weaker source |
| **Failure mode** | Degrade, never abort — a failed collector yields `"Unknown"` for its fields only |
| **Pre-upload validation** | `audit.sh` validates each JSON fragment and the whole payload; refuses to upload if invalid and saves it to `/tmp/audit_payload_invalid.json`. `audit.ps1` relies on `ConvertTo-Json -Depth 8` |
| **Connectivity check** | `audit.sh` tests TCP reachability via `nc` or bash `/dev/tcp` before uploading, printing four numbered diagnostics on failure |
| **Upload** | `audit.sh`: `curl` (60s cap) → `wget` fallback. `audit.ps1`: `Invoke-RestMethod` (300s) → `System.Net.WebClient` fallback |
| **Idempotency** | Every run produces a new audit record; the backend computes diffs against the previous one |
| **Uninstall** | `uninstall-audit.{ps1,sh,command}` removes the schedule, runner and config |

### 6.5 Known agent-side gaps

1. **No TLS 1.2 enforcement in older `audit.ps1`**. Windows PowerShell 5.1 defaults to TLS 1.0 on some legacy builds.
2. `curl | bash` and `Invoke-RestMethod | Invoke-Expression` are the install channel — acceptable on a trusted LAN, a remote-code-execution path on a public URL.
3. **No payload signing or machine attestation** — `computer_name` is self-reported and `client_id` is a query-string parameter.
4. `audit.ps1` performs no pre-upload validation, unlike `audit.sh`.

---

---

## 7. Swagger / OpenAPI Endpoint Audit & Test Report

**Execution Date**: 2026-08-15  
**Target Server**: `http://127.0.0.1:8000`  
**OpenAPI Specification**: 80 Unique Paths, 90 API Operations across 12 Tag Categories.

### 7.1 Test Summary Overview

| Category / Tag | Total Endpoints | 200 OK | 422 (Schema Validation) | 404 (Resource Missing) | 500 (Server Error / Missing File) |
|---|---|---|---|---|---|
| **Scripts & Agent Launchers** | 22 | 8 | 0 | 1 | 13 |
| **Audit Ingestion & Reports** | 3 | 0 | 1 | 2 | 0 |
| **Asset Metadata** | 4 | 0 | 2 | 2 | 0 |
| **Devices & Software (Audit DB)** | 4 | 3 | 0 | 1 | 0 |
| **Network Discovery** | 2 | 0 | 2 | 0 | 0 |
| **WiFi (Local Host)** | 10 | 7 | 3 | 0 | 0 |
| **Asset Lifecycle & Tickets** | 8 | 4 | 4 | 0 | 0 |
| **Inventory: Users & Roles** | 5 | 3 | 0 | 0 | 2 |
| **Inventory: Auth** | 1 | 0 | 1 | 0 | 0 |
| **Inventory: Organizations & Sites** | 10 | 1 | 4 | 0 | 5 |
| **Inventory: Devices & Deployments** | 6 | 0 | 2 | 1 | 3 |
| **Inventory: WiFi & Network Scans** | 5 | 0 | 3 | 0 | 2 |
| **Total** | **90** | **26** | **22** | **7** | **25** |

---

### 7.2 Detailed Category Breakdown

#### 1. Scripts & Agent Launchers (22 Operations)
- **Status**: 8 OK (`/download-exe`, `/download-vbs`, `/download-mac-launcher`, `/download-linux-launcher`, `/check-status`, etc.).
- **Notes**: Launchers served dynamically. Script generation routes (e.g. `/download-script`, `/sys-win`) return 500 when `scripts/audit.ps1` or `scripts/audit.sh` collector scripts are absent on host.

#### 2. Audit Ingestion & Reports (3 Operations)
- **Status**: POST `/api/upload-audit` returns 422 Unprocessable Entity when raw payload is missing (Pydantic validation active). GET `/api/download-report` returns 404 for invalid client ID.

#### 3. Devices & Software / Asset Metadata (8 Operations)
- **Status**: GET `/api/assets`, GET `/api/devices`, GET `/api/device-diff/{device_id}` return 200 OK.
- **Notes**: Resource lookups return 404 for nonexistent `device_id`.

#### 4. WiFi & Network Scans (10 Operations)
- **Status**: GET `/api/wifi/networks`, `/api/wifi/current`, `/api/wifi-status`, `/wifi/credentials` return 200 OK. POST routes enforce 422 schema validation.

#### 5. Asset Lifecycle & Tickets (8 Operations)
- **Status**: GET `/api/lifecycle/{identifier}`, GET `/api/tickets/{mac_address}`, DELETE `/api/tickets/{ticket_id}` return 200 OK.

#### 6. Inventory, Users, Roles & Organizations (27 Operations)
- **Status**: GET `/api/inventory/users`, `/api/inventory/roles`, `/api/inventory/user-roles`, `/api/organizations` return 200 OK.
- **Notes**: Organization sub-resource detail lookups require active PostgreSQL database credentials (`.env`).

---

## Related documents

| Document | Contents |
|---|---|
| `CODEBASE_EXPLANATION.md` | Line-by-line walkthrough of the backend, both collectors, and the verification design |
| `tools-comp.md` | InfraPulse vs osquery + Fleet — cost, security, scale, maintenance |
| `data-fields-comparison.md` | All 67 required fields mapped to the osquery schema; hybrid migration plan |
| `WORKFLOW.md` | Operational workflow |
| `README.md` | Setup, running, and architecture specification document |

