#          SPICEWORK WORKSTATION COMPLIANCE AUDIT BACKEND (FASTAPI)
# Version: 3.0.0 — Full IT Asset Management Edition

import os

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from backend.core.config import FRONTEND_DIR
from backend.core.security import bearer_token, decode_access_token, is_public_path
from backend.routers import (
    assets,
    audits,
    dashboard,
    devices,
    discovery,
    inventory,
    inventory_auth,
    inventory_devices,
    inventory_organizations,
    inventory_wifi,
    lifecycle,
    registered_devices,
    report_pins,
    row_overrides,
    saved_searches,
    scripts,
    view_preferences,
    wifi,
)

app = FastAPI(title="Spicework IT Asset Management Portal", version="3.0.0")


@app.middleware("http")
async def require_authentication(request: Request, call_next):
    """
    Gate on the way in: every /api/ route needs a valid bearer token unless it
    is on the public allowlist in core.security (auth itself, plus the agent
    and audit-ingestion endpoints the unattended collectors call).

    Enforcing it here rather than per-router means a newly added endpoint is
    protected the moment it exists — the failure mode is a locked door, not an
    open one. Registered before the CORS middleware below so CORS stays
    outermost: a 401 from here still carries the headers the browser needs to
    read it as a 401 instead of a generic network error.
    """
    if request.method == "OPTIONS" or is_public_path(request.url.path):
        return await call_next(request)

    token = bearer_token(request)
    if not token:
        return JSONResponse(
            status_code=401,
            content={"detail": "Not authenticated."},
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        # Claims are stashed for the request so handlers can read them through
        # the get_current_user dependency without decoding a second time.
        request.state.user = decode_access_token(token)
    except HTTPException as e:
        return JSONResponse(
            status_code=e.status_code,
            content={"detail": e.detail},
            headers=e.headers or {},
        )

    return await call_next(request)


cors_origins_env = os.getenv("CORS_ALLOWED_ORIGINS", "")
if cors_origins_env:
    origins = [o.strip() for o in cors_origins_env.split(",") if o.strip()]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
else:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

app.include_router(scripts.router, tags=["Scripts & Agent Launchers"])
app.include_router(audits.router, tags=["Audit Ingestion & Reports"])
app.include_router(assets.router, tags=["Asset Metadata"])
app.include_router(devices.router, tags=["Devices & Software (Audit DB)"])
app.include_router(discovery.router, tags=["Network Discovery"])
app.include_router(wifi.router, tags=["WiFi (Local Host)"])
app.include_router(lifecycle.router, tags=["Asset Lifecycle & Tickets"])
app.include_router(inventory.router, tags=["Inventory: Users & Roles"])
app.include_router(inventory_auth.router, tags=["Inventory: Auth"])
app.include_router(inventory_organizations.router, tags=["Inventory: Organizations & Sites"])
app.include_router(inventory_devices.router, tags=["Inventory: Devices & Deployments"])
app.include_router(inventory_wifi.router, tags=["Inventory: WiFi & Network Scans"])
app.include_router(registered_devices.router, tags=["Inventory: Registered Devices"])
app.include_router(view_preferences.router, tags=["View Preferences"])
app.include_router(saved_searches.router, tags=["Saved Searches"])
app.include_router(report_pins.router, tags=["Report Pins"])
app.include_router(row_overrides.router, tags=["Row Field Overrides"])
app.include_router(dashboard.router, tags=["Dashboard"])

# Catch-all static mount for the frontend SPA — must stay last so it never
# shadows the explicit routes registered by the routers above.
if os.path.exists(FRONTEND_DIR):
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
