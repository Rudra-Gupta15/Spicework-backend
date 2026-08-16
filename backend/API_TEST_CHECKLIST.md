# API Test Checklist

Manual test checklist for every endpoint actually mounted in [main.py](main.py). Assumes the server is running locally:

```
uvicorn backend.main:app --reload --port 8000
```

Base URL below is `http://localhost:8000`. Endpoints from `osquery_settings.py` / `osquery_telemetry.py` are **not included** — they aren't mounted in `main.py`, so they won't respond regardless.

**Risk legend:** 🟢 safe read · 🟡 write (test data, easy to clean up) · 🟠 write with real-world side effect (touches disk/DB permanently unless manually cleaned) · 🔴 hardware/network side effect (changes actual WiFi connection, scans your live LAN, attempts remote exec) — confirm intent before running.

Where a path needs a real ID (`{organization_id}`, `{device_id}`, etc.), fetch one first via the matching `GET /api/organizations` or `GET /devices` call and substitute it in.

---

## 1. Auth

- [ ] 🟡 `POST /api/auth/login`
  ```
  curl -X POST http://localhost:8000/api/auth/login \
    -H "Content-Type: application/json" \
    -d '{"email":"someone@example.com","password":"wrong"}'
  ```
  Expected: `401 {"detail":"Invalid email or password."}` with a bad password; `200` + user object + `roles[]` with a real account.

## 2. Inventory reads (Postgres)

- [ ] 🟢 `GET /api/inventory/status` → `{"status":"success","connected":true}`
- [ ] 🟢 `GET /api/inventory/users` → `{"users":[...]}`
- [ ] 🟢 `GET /api/inventory/users/{user_id}` → user object, `404` on bad id
- [ ] 🟢 `GET /api/inventory/users/{user_id}/roles` → `{"roles":[...]}`
- [ ] 🟢 `GET /api/inventory/roles` → `{"roles":[...]}` (7 rows expected)
- [ ] 🟢 `GET /api/inventory/user-roles` → `{"assignments":[...]}`

## 3. Organizations, Sites, Employees

- [ ] 🟡 `POST /api/organizations`
  ```
  curl -X POST http://localhost:8000/api/organizations \
    -H "Content-Type: application/json" \
    -d '{"name":"__TEST_ORG__","admin_email":"test_admin@example.invalid","admin_password":"TestPass123!","admin_first_name":"Test"}'
  ```
  Save the returned `organization.id` for the next steps. Clean up afterward (see note at bottom).
- [ ] 🟢 `GET /api/organizations` → `{"organizations":[...]}`
- [ ] 🟢 `GET /api/organizations/{organization_id}` → org object, `404` on bad id
- [ ] 🟢 `GET /api/organizations/{organization_id}/detail` → org + nested `sites[]` + `unassigned_employees[]`
- [ ] 🟡 `POST /api/organizations/{organization_id}/sites`
  ```
  curl -X POST http://localhost:8000/api/organizations/{organization_id}/sites \
    -H "Content-Type: application/json" \
    -d '{"name":"__TEST_SITE__","city":"TestCity"}'
  ```
- [ ] 🟢 `GET /api/organizations/{organization_id}/sites` → `{"sites":[...]}`
- [ ] 🟢 `GET /api/sites/{site_id}` → site object, `404` on bad id
- [ ] 🟡 `POST /api/organizations/{organization_id}/employees`
  ```
  curl -X POST http://localhost:8000/api/organizations/{organization_id}/employees \
    -H "Content-Type: application/json" \
    -d '{"email":"test_emp@example.invalid","password":"TestPass123!","first_name":"Emp","role_name":"IT_TECHNICIAN"}'
  ```
- [ ] 🟢 `GET /api/organizations/{organization_id}/employees` → `{"employees":[...]}`

## 4. Devices & Deployments (Postgres, multi-tenant)

- [ ] 🟡 `POST /api/organizations/{organization_id}/deployments`
  ```
  curl -X POST http://localhost:8000/api/organizations/{organization_id}/deployments \
    -H "Content-Type: application/json" \
    -d '{"requested_by":"{user_id}","launcher_type":"exe"}'
  ```
- [ ] 🟢 `GET /api/organizations/{organization_id}/deployments` → `{"deployments":[...]}`
- [ ] 🟢 `GET /api/deployments/{client_id}` → deployment object, `404` on bad id
- [ ] 🟡 `POST /api/organizations/{organization_id}/devices/audit`
  ```
  curl -X POST http://localhost:8000/api/organizations/{organization_id}/devices/audit \
    -H "Content-Type: application/json" \
    -d '{"device_name":"__TEST_DEVICE__","device":{"os_name":"TestOS"},"software":[{"name":"TestApp","version":"1.0"}]}'
  ```
  Upserts a `hardware_devices` row + replaces its child tables — safe to re-run, but leaves a permanent row unless deleted manually from Postgres afterward.
- [ ] 🟢 `GET /api/organizations/{organization_id}/devices` → `{"devices":[...]}`
- [ ] 🟢 `GET /api/devices/{device_id}` → full `DeviceDetail` with all child arrays
- [ ] 🟢 `GET /api/organizations/{organization_id}/stats/hardware` → `{total_devices, online, offline, warranty_expiring}`
- [ ] 🟢 `GET /api/organizations/{organization_id}/stats/software` → `{total_software, total_license, subscription_count, publisher_count}`

## 5. WiFi & Network Scans (Postgres, multi-tenant — DB records only, no hardware)

- [ ] 🟡 `POST /api/organizations/{organization_id}/wifi-networks`
  ```
  curl -X POST http://localhost:8000/api/organizations/{organization_id}/wifi-networks \
    -H "Content-Type: application/json" \
    -d '{"networks":[{"ssid":"__TEST_SSID__","authentication":"WPA2","signal":"80%"}]}'
  ```
- [ ] 🟡 `POST /api/organizations/{organization_id}/wifi-networks/connect` — **writes a real password into the DB row**; use a dummy SSID/password, not a real network's credentials.
- [ ] 🟢 `GET /api/organizations/{organization_id}/wifi-networks` → `{"networks":[...]}` (no password field)
- [ ] 🟡 `POST /api/organizations/{organization_id}/network-scans`
  ```
  curl -X POST http://localhost:8000/api/organizations/{organization_id}/network-scans \
    -H "Content-Type: application/json" \
    -d '{"performed_by":"{user_id}","ssid":"__TEST_SSID__","devices":[{"ip_address":"10.0.0.99","hostname":"test-host"}]}'
  ```
- [ ] 🟢 `GET /api/organizations/{organization_id}/network-scans` → `{"scans":[...]}`
- [ ] 🟢 `GET /api/network-scans/{scan_id}` → scan + `devices[]`, `404` on bad id

## 6. Legacy Audit Ingestion & Reports (SQLite `audits.db`)

- [ ] 🟠 `POST /upload-audit?client_id=test123` — body is a full `AuditData` object (see `models/audit.py`); minimal valid example:
  ```
  curl -X POST "http://localhost:8000/upload-audit?client_id=test123" \
    -H "Content-Type: application/json" \
    -d '{"computer_name":"__TEST_DEVICE__","os_name":"TestOS","mac_address":"AA:BB:CC:DD:EE:00"}'
  ```
  Writes a permanent row to `device_audits` and generates a PDF+XML on disk under `user_info/`. Clean up the DB row manually if you don't want it kept.
- [ ] 🟢 `GET /download-report?client_id=test123` → PDF file stream (only works right after an upload in the same session, or falls back to DB lookup)
- [ ] 🟢 `GET /api/download-device-pdf/__TEST_DEVICE__` → PDF file stream, `404` if no audit exists for that device

## 7. Devices & Software reads (SQLite `audits.db`)

- [ ] 🟢 `GET /devices` or `GET /api/devices` → `{"devices":[...], "total"}`
- [ ] 🟢 `GET /api/software/{device_id}` → full latest snapshot, `404` if no audit found
- [ ] 🟢 `GET /api/device-diff/{device_id}` → `{"has_diff": false, ...}` if <2 scans exist, else a diff object

## 8. Asset Metadata (flat JSON files, not DB)

- [ ] 🟡 `POST /asset-metadata`
  ```
  curl -X POST http://localhost:8000/asset-metadata \
    -H "Content-Type: application/json" \
    -d '{"device_id":"__TEST_DEVICE__","owner":"Tester"}'
  ```
  Creates `user_info/assets/__TEST_DEVICE__.json`.
- [ ] 🟢 `GET /asset-metadata/{device_id}` → the saved object, `404` if missing
- [ ] 🟡 `PUT /asset-metadata/{device_id}` → same body shape, overwrites
- [ ] 🟡 `DELETE /asset-metadata/{device_id}` → deletes the file, use this to clean up the test above
- [ ] 🟢 `GET /assets` → `{"assets":[...], "total"}`

## 9. Asset Lifecycle & Tickets (SQLite `audits.db`)

- [ ] 🟢 `GET /api/lifecycle/{identifier}` → `{}` if not found (currently 0 rows in this table)
- [ ] 🟡 `POST /api/lifecycle` — body `{"mac_address":"AA:BB:CC:DD:EE:00","owner":"Tester"}`
- [ ] 🟢 `GET /api/tickets/{mac_address}` → `[]` if none
- [ ] 🟡 `POST /api/tickets` — body `{"mac_address":"AA:BB:CC:DD:EE:00","summary":"test ticket"}`
- [ ] 🟡 `PUT /api/tickets/{ticket_id}` — needs the numeric id returned/visible from the create/list above
- [ ] 🟡 `DELETE /api/tickets/{ticket_id}`

## 10. Network Discovery 🔴

- [ ] 🔴 `POST /discover/network-scan` — actively pings/port-scans the given IP range (your real LAN if you point it at your own subnet). Confirm before running against anything other than a range you own.
- [ ] 🔴 `POST /discover/network-scan-stream` — same scan, streamed via SSE.

## 11. WiFi (local Windows host only) 🔴

Only meaningfully testable if the backend runs on Windows with WiFi hardware — on Linux/cloud these degrade gracefully (empty results / `is_cloud_server: true`), which is itself worth confirming.

- [ ] 🟢 `GET /wifi/networks` → nearby SSIDs or the cloud-server fallback message
- [ ] 🟢 `GET /wifi/current` → current connection info or `connected:false`
- [ ] 🟢 `GET /wifi/credentials` → **returns raw stored WiFi passwords** — confirm this response isn't exposed to end users in the frontend
- [ ] 🟡 `POST /wifi/save-credential` — stores a credential row only, no actual connect attempt; safe to test with a dummy SSID
- [ ] 🔴 `POST /wifi/connect` — **will actually reconfigure and connect this machine's WiFi adapter** if run on Windows. Do not run against a real SSID/password unless you intend to change this machine's network.
- [ ] 🔴 `GET /wifi/scan-devices` — triggers a live subnet scan (same caveat as Discovery above)
- [ ] 🔴 `POST /audit/send-notification` — attempts WinRM/PsExec remote command execution against the given `ip_address`. **Currently hardcoded to always fail** (`winrm`/`PsExecClient` are `None` in the code) — expect a `500` regardless of input; flagged here so you know it's a known dead endpoint, not a bug in your test.
- [ ] 🟢 `POST /api/trigger-scan/{device_id}` → sets an in-memory flag, no side effects beyond process memory
- [ ] 🟢 `GET /api/check-trigger?device_name=x` → reads/clears that flag

## 12. Agent Scripts & Launcher Downloads

Mostly linked from UI download buttons rather than called by app logic. Each just streams a script/file — safe to `GET`, but note some (`/download-exe`, `/download-mac-launcher`, etc.) write temporary generator artifacts to `scratch/` on the server.

- [ ] 🟢 `GET /check-status`
- [ ] 🟢 `GET /download-exe`, `/download-vbs`, `/download-mac`, `/download-linux`
- [ ] 🟢 `GET /api/get-audit-script?client_id=test123`
- [ ] 🟢 `GET /s/{client_id}` — per-client script variant

---

## Cleanup after a full pass

Anything created under sections 3–9 with a `__TEST_*` name is safe to leave (clearly marked) or remove with:

```sql
-- Postgres (sw inventory)
DELETE FROM platform_user_roles WHERE user_id IN (SELECT id FROM users WHERE email LIKE '%@example.invalid');
DELETE FROM users WHERE email LIKE '%@example.invalid';
DELETE FROM sites WHERE name = '__TEST_SITE__';
DELETE FROM organizations WHERE name = '__TEST_ORG__';
DELETE FROM hardware_devices WHERE device_name = '__TEST_DEVICE__';  -- cascades child tables if FKs are ON DELETE CASCADE, otherwise clear those first
DELETE FROM wifi_networks WHERE ssid = '__TEST_SSID__';
```

```sql
-- SQLite (audits.db)
DELETE FROM device_audits WHERE computer_name = '__TEST_DEVICE__';
DELETE FROM asset_lifecycle WHERE mac_address = 'AA:BB:CC:DD:EE:00';
DELETE FROM asset_tickets WHERE mac_address = 'AA:BB:CC:DD:EE:00';
```

Plus: `rm user_info/assets/__TEST_DEVICE__.json` and any `user_info/audit_test123_*` PDF/XML/JSON files.
