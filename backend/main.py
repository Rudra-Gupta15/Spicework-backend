#         INFRAPULSE WORKSTATION COMPLIANCE AUDIT BACKEND (FASTAPI)
# Version: 3.0.0 — Full IT Asset Management Edition

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend.core.config import FRONTEND_DIR
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
    saved_searches,
    scripts,
    view_preferences,
    wifi,
)

app = FastAPI(title="InfraPulse IT Asset Management Portal", version="3.0.0")

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
app.include_router(view_preferences.router, tags=["View Preferences"])
app.include_router(saved_searches.router, tags=["Saved Searches"])
app.include_router(dashboard.router, tags=["Dashboard"])

# Catch-all static mount for the frontend SPA — must stay last so it never
# shadows the explicit routes registered by the routers above.
if os.path.exists(FRONTEND_DIR):
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
