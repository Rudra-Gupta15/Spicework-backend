from fastapi import APIRouter, Query

from backend import auth_db, legacy_db

router = APIRouter()


@router.get("/api/dashboard/stats")
def get_dashboard_stats():
    """Sites/Users/Cities (sw inventory, Postgres) + Devices (legacy audit log) — the 4 stat tiles."""
    org_stats = auth_db.get_org_dashboard_stats()
    return {**org_stats, "devices": legacy_db.count_devices()}


@router.get("/api/dashboard/recent-audits")
def get_recent_audits(limit: int = Query(5, ge=1, le=50)):
    return {"audits": legacy_db.list_recent_audits(limit)}


@router.get("/api/dashboard/compliance-summary")
def get_compliance_summary():
    """Firewall/Antivirus/License breakdown across every real device, for the compliance chart."""
    return legacy_db.get_compliance_summary()
