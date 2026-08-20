# API Reference — Spicework Backend

For frontend developers connecting to the FastAPI backend ([backend/main.py](main.py)).

## Base setup

- **Base URL:** `http://<host>:8000` (uvicorn default; no global `/api` prefix — some routes have `/api/...`, many legacy ones don't).
- **CORS:** open (`allow_origins=["*"]`) unless the server sets `CORS_ALLOWED_ORIGINS` (comma-separated list) in `.env`, in which case only those origins are allowed and credentials are enabled.
- **Auth:** JWT bearer tokens. `POST /api/auth/login` and `POST /api/auth/register` verify against the `users` table in Postgres (bcrypt) and return `{ access_token, token_type, expires_in, user }`. **Every `/api/...` endpoint requires `Authorization: Bearer <access_token>`** except the public allowlist in [core/security.py](core/security.py) — the two auth endpoints, plus the agent/collector endpoints that unattended scripts call with no user session (`/api/upload-audit`, `/api/check-status`, `/api/server-info`, `/api/sys-agent*`, `/api/sys-win`, `/api/get-audit-script`, `/api/install-daemon`, `/api/download-*-launcher`). Paths that do **not** start with `/api/` are public — that covers the SPA's static files and the agent scripts the collectors fetch by plain URL. Enforcement is a single middleware in [main.py](main.py), so a newly added endpoint is protected by default. Tokens are signed with `JWT_SECRET` and expire after `JWT_EXPIRE_MINUTES` (default 720); they are stateless, so there is no server-side revoke — rotate `JWT_SECRET` to invalidate everything outstanding.
- **Static frontend:** the built frontend (`FRONTEND_DIR`) is mounted at `/` as a catch-all SPA host — it's registered *last*, so it never shadows the API routes above.
- **IDs:** the inventory/org/device/wifi APIs (Postgres-backed) use UUID strings. The legacy audit APIs (SQLite-backed) key off `mac_address` or `computer_name` strings instead.

> ⚠️ **`osquery_settings.py` and `osquery_telemetry.py` routers exist in the codebase but are not imported/mounted in `main.py`.** Every endpoint listed under those two files below is currently **not reachable** on the running server. If you need them, someone has to add them to the `include_router` list in [main.py](main.py) first.

---

## 1. Auth — [inventory_auth.py](routers/inventory_auth.py)

| Method | Path | Body | Returns |
|---|---|---|---|
| POST | `/api/auth/login` | `{ email, password }` | `{ access_token, token_type, expires_in, user }`. `user` carries `roles: string[]` and `organization_name`. `401` if the credentials don't match or the account is inactive — deliberately the same message either way, so the endpoint can't be used to enumerate registered addresses. |
| POST | `/api/auth/register` | `{ organization_name, email, password, first_name, last_name? }` | `201` with the same shape as login — signing up logs you straight in. Creates the organization **and** its first user (`TENANT_USER`, role `ORGANIZATION_ADMIN`) in one transaction. `400` on a malformed field or a password under 6 characters, `409` if the email is taken. |
| GET | `/api/auth/me` | — | The bearer token's account, read fresh from Postgres so a deactivated user stops resolving immediately rather than when the token expires. `401` if the token is missing/invalid/expired or the account is inactive. |

## 2. Inventory reads (Postgres) — [inventory.py](routers/inventory.py)

Read-only views into the `sw inventory` Postgres DB.

| Method | Path | Returns |
|---|---|---|
| GET | `/api/inventory/status` | `{status, connected}` — health check |
| GET | `/api/inventory/users` | `{ users: [] }` (never includes password) |
| GET | `/api/inventory/users/{user_id}` | one user, `404` if missing |
| GET | `/api/inventory/users/{user_id}/roles` | `{ roles: [] }` |
| GET | `/api/inventory/roles` | `{ roles: [] }` — all platform roles |
| GET | `/api/inventory/user-roles` | `{ assignments: [] }` — all user↔role assignments joined |

## 3. Organizations, Sites, Employees — [inventory_organizations.py](routers/inventory_organizations.py)

| Method | Path | Body | Notes |
|---|---|---|---|
| POST | `/api/organizations` | `CreateOrganizationRequest {name, admin_email, admin_password, admin_first_name, admin_last_name?, created_by?}` | Creates org + its ORGANIZATION_ADMIN user in one transaction |
| GET | `/api/organizations` | — | `{ organizations: [] }` |
| GET | `/api/organizations/{organization_id}` | — | `404` if missing |
| GET | `/api/organizations/{organization_id}/detail` | — | Full nested view: sites (each with employees) + unassigned employees |
| POST | `/api/organizations/{organization_id}/sites` | `CreateSiteRequest {name, address_line?, city?, state?, country?, postal_code?}` | |
| GET | `/api/organizations/{organization_id}/sites` | — | `{ sites: [] }` |
| GET | `/api/sites/{site_id}` | — | `404` if missing |
| POST | `/api/organizations/{organization_id}/employees` | `CreateEmployeeRequest {email, password, first_name, last_name?, role_name, site_id?}` | `role_name` must be one of `IT_MANAGER`, `IT_PROFESSIONAL`, `IT_TECHNICIAN`, `ORGANIZATION_ADMIN` |
| GET | `/api/organizations/{organization_id}/employees?site_id=` | — | `{ employees: [] }`, `site_id` query param optional filter |

## 4. Devices & Deployments (Postgres, multi-tenant) — [inventory_devices.py](routers/inventory_devices.py)

| Method | Path | Body / Params | Notes |
|---|---|---|---|
| POST | `/api/organizations/{organization_id}/deployments` | `AgentDeploymentRequest {requested_by, launcher_type, deployment_mode?, site_id?, server_ip?, server_port?}` | Creates a tracking row before the launcher file is even generated |
| GET | `/api/organizations/{organization_id}/deployments?site_id=` | — | `{ deployments: [] }` |
| GET | `/api/deployments/{client_id}` | — | `404` if missing |
| POST | `/api/organizations/{organization_id}/devices/audit` | `DeviceAuditRequest {device_name, site_id?, deployment_id?, scanned_by?, device, software[], users[], login_history[], gpus[], network_adapters[], storage[], peripherals[], printers[], connected_devices[]}` | What a downloaded launcher script POSTs back after scanning a machine |
| GET | `/api/organizations/{organization_id}/devices?site_id=` | — | `{ devices: [] }` — hardware summary rows |
| GET | `/api/devices/{device_id}` | — | Full `DeviceDetail`: hardware + software + users + login history + gpus + adapters + storage + peripherals + printers + connected devices |
| GET | `/api/organizations/{organization_id}/stats/hardware` | — | `HardwareStats` — Hardware page summary cards |
| GET | `/api/organizations/{organization_id}/stats/software` | — | `SoftwareStats` — Software page summary cards |

## 5. WiFi & Network Scans (Postgres, multi-tenant) — [inventory_wifi.py](routers/inventory_wifi.py)

| Method | Path | Body / Params | Notes |
|---|---|---|---|
| POST | `/api/organizations/{organization_id}/wifi-networks` | `StoreWifiNetworksRequest {site_id?, networks: [{ssid, authentication?, encryption?, signal?}]}` | Bulk-persist the "Available WiFi Networks" list, no password |
| POST | `/api/organizations/{organization_id}/wifi-networks/connect` | `ConnectWifiNetworkRequest {ssid, password, site_id?}` | Stores password on that row, marks connected |
| GET | `/api/organizations/{organization_id}/wifi-networks?site_id=` | — | `{ networks: [] }` — never includes password |
| POST | `/api/organizations/{organization_id}/network-scans` | `RecordNetworkScanRequest {performed_by, ssid, devices[], site_id?, wifi_network_id?, ip_address?, subnet?}` | Persists one "Connect & Scan" action + all devices found, in one transaction |
| GET | `/api/organizations/{organization_id}/network-scans?site_id=` | — | `{ scans: [] }` — no nested devices |
| GET | `/api/network-scans/{scan_id}` | — | One scan + all its devices, `404` if missing |

---

## 6. Legacy Audit Ingestion & Reports (SQLite `audits.db`) — [audits.py](routers/audits.py)

| Method | Path | Body / Params | Notes |
|---|---|---|---|
| POST | `/upload-audit?client_id=` | `AuditData` (large flat audit payload — see `models/audit.py`) | What the legacy native audit script (exe/vbs/script) uploads. Stores row in `device_audits`, generates a PDF + XML compliance report on disk. |
| GET | `/download-report?client_id=&format=pdf&action=download\|view` | — | Downloads/streams the PDF for a session; falls back to regenerating from DB if no cached session |
| GET | `/api/download-device-pdf/{device_id}?action=download\|view` | — | Same, keyed directly by device_id (mac/name) instead of session client_id |

## 7. Devices & Software reads (SQLite `audits.db`) — [devices.py](routers/devices.py)

| Method | Path | Notes |
|---|---|---|
| GET | `/devices` or `/api/devices` | `{ devices: [], total }` — deduplicated list of audited machines (by name+OS family), with best-effort model name cleanup |
| GET | `/api/software/{device_id}` | Full latest-audit snapshot for one device (software, hardware, network, users, hotfixes, etc.), matched by mac or computer name |
| GET | `/api/device-diff/{device_id}` | Diffs the two most recent scans for a device: newly installed/removed software + hardware/OS field changes |

## 8. Asset Metadata (flat JSON files) — [assets.py](routers/assets.py)

Stored as one JSON file per device under `user_info/assets/`, not in a DB table.

| Method | Path | Body | Notes |
|---|---|---|---|
| POST | `/asset-metadata` | `AssetMetadata {device_id, asset_tag?, owner?, department?, location?, purchase_date?, purchase_price?, warranty_expiry?, life_cycle_stage?, vendor?, notes?}` | |
| GET | `/asset-metadata/{device_id}` | — | `404` if missing |
| PUT | `/asset-metadata/{device_id}` | `AssetMetadata` | |
| DELETE | `/asset-metadata/{device_id}` | — | `404` if missing |
| GET | `/assets` | — | `{ assets: [], total }` — all saved asset metadata files |

## 9. Asset Lifecycle & Tickets (SQLite `audits.db`) — [lifecycle.py](routers/lifecycle.py)

| Method | Path | Body | Notes |
|---|---|---|---|
| GET | `/api/lifecycle/{identifier}` | — | Lookup by mac_address or computer_name; `{}` if not found |
| POST | `/api/lifecycle` or `/api/lifecycle/{identifier}` | `LifecycleData {mac_address, computer_name?, owner?, location?, vendor?, status?, warranty_start?, warranty_end?, warranty_notes?, warranty_provider?, purchase_price?, purchase_date?, supplier?, po_number?}` | Upsert keyed on mac_address |
| GET | `/api/tickets/{mac_address}` | — | List of tickets for that device |
| POST | `/api/tickets` | `TicketData {mac_address, computer_name?, ticket_number?, summary?, status?, assigned?, priority?, mtbf?}` | |
| PUT | `/api/tickets/{ticket_id}` | `TicketData` | |
| DELETE | `/api/tickets/{ticket_id}` | — | |

## 10. Network Discovery — [discovery.py](routers/discovery.py)

| Method | Path | Body | Notes |
|---|---|---|---|
| POST | `/discover/network-scan` | `NetworkScanRequest {ip_range: "192.168.1.0/24" or "start-end", timeout_ms}` | Ping sweep + port scan (max 512 hosts) + ARP fallback for firewalled/mobile devices; returns `{discovered: [], total, scanned, ip_range, start_ip, end_ip, ip_subnet_range}` enriched with prior audit data |
| POST | `/discover/network-scan-stream` | `NetworkScanRequest` (same shape) | Same scan, but as **SSE** (`text/event-stream`): emits `data: {"type":"device","device":{...}}` per discovered host, then `{"type":"complete","total","scanned"}` at the end. Use `EventSource` on the frontend. |

## 11. WiFi (local Windows host only) — [wifi.py](routers/wifi.py)

Most of this only works when the backend itself runs on a Windows machine with WiFi hardware (uses `netsh`). On Linux/cloud it degrades gracefully (returns empty lists / `is_cloud_server: true`).

| Method | Path | Body / Params | Notes |
|---|---|---|---|
| GET | `/wifi/networks` or `/api/wifi/networks` | — | Nearby SSIDs via `netsh wlan show networks`, deduped by strongest signal, flagged `has_saved_password` |
| GET | `/wifi/current`, `/wifi-status`, `/api/wifi-status`, `/api/wifi/current` | — | Current connection: ssid, signal, rssi, band, channel, ip, subnet, estimated `distance_str` to AP |
| GET | `/wifi/credentials` | — | `{ credentials: {ssid: {ssid, password, updated_at}} }` — **returns raw stored passwords** |
| POST | `/wifi/save-credential` | `WifiSaveCredentialRequest {ssid, password}` | Upsert into `wifi_credentials` table only (no actual connect) |
| POST | `/wifi/connect` or `/api/wifi/connect` | `WifiConnectRequest {ssid, password}` | Saves credential, then creates a WPA2-PSK profile and connects via `netsh`; polls up to 12s for an IP |
| GET | `/wifi/scan-devices?subnet=` | — | Runs the network-scan against the given (or current) subnet, enriched with audit data |
| POST | `/audit/send-notification` | `NotificationRequest {ip_address, username, password, method: "auto"\|"winrm"\|"psexec"}` | Remote-executes a PowerShell toast + triggers a pull-based audit on the target via WinRM/PsExec. **Note: `winrm`/`PsExecClient` are hardcoded to `None` in this file — this endpoint currently always 500s.** |
| POST | `/api/trigger-scan/{device_id}` | — | Marks a pending scan-trigger flag for polling agents |
| GET | `/api/check-trigger?device_name=` | — | Polled by agent daemons; returns `{trigger: bool}` and clears the flag |

## 12. Agent Scripts & Launcher Downloads — [scripts.py](routers/scripts.py)

Serves PowerShell/VBS/shell launcher scripts and installers that get deployed to end-user machines. Mostly `GET`, `PlainTextResponse`/file downloads — not typically called from frontend app logic directly, but linked to from the UI as download buttons (e.g. "Download Windows Agent").

Key ones a frontend might link to: `/download-exe`, `/download-vbs`, `/download-mac`, `/download-linux`, `/api/get-audit-script`, `/s/{client_id}` (per-client script variant), `/check-status`.

---

## ⚠️ Not currently mounted (exist in code, but unreachable)

### [osquery_settings.py](routers/osquery_settings.py)
`GET/POST /api/settings/engine`, `GET/POST /api/settings/database`, `POST /api/settings/migrate-db`, `GET /api/osquery/status` — audit-engine toggle (native vs osquery) and the SQLite↔Postgres runtime switch/migration for the audit DB.

### [osquery_telemetry.py](routers/osquery_telemetry.py) — *(the file you have open)*
`GET/POST /api/osquery/device-data`, `/disk-data`, `/partition-data`, `/network-data`, `/peripheral-data`, `/user-data`, `/login-history`, `/software-inventory` (each runs a canned SQL query through the local `osqueryi` binary), plus `GET /api/osquery/collector.ps1` (downloads a remote-collector script), `POST /api/osquery/submit-remote-audit`, `GET /api/osquery/remote-devices`, `POST /api/osquery/query` (ad-hoc SELECT-only SQL against osquery), `POST /api/osquery/scan`.

**To activate either router:** add the import and `app.include_router(...)` call in [main.py](main.py) (pattern matches the other routers already there).
