import os as _os

from fastapi import APIRouter, HTTPException

from backend import osquery_engine
from backend.core.config import DB_PATH, logger
from backend.db import (
    _load_env,
    _psycopg2_available,
    get_active_engine,
    get_db,
    init_db,
    migrate_sqlite_to_postgres,
    write_db_config,
)
from backend.models.osquery import AuditEngineRequest, DbEngineRequest

router = APIRouter()


@router.get("/api/settings/engine")
def get_audit_engine():
    with get_db(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM portal_settings WHERE key='audit_engine'")
        row = cursor.fetchone()
        engine = row[0] if row else "native"

    return {
        "audit_engine": engine,
        "osquery_available": osquery_engine.is_osquery_available(),
        "osquery_version": osquery_engine.get_osquery_version(),
        "osquery_path": osquery_engine.get_osquery_path() or "Not Found"
    }


@router.post("/api/settings/engine")
def set_audit_engine(data: AuditEngineRequest):
    mode = data.audit_engine.lower().strip()
    if mode not in ["native", "osquery"]:
        raise HTTPException(status_code=400, detail="Invalid engine. Must be 'native' or 'osquery'.")

    with get_db(DB_PATH) as conn:
        conn.execute("INSERT OR REPLACE INTO portal_settings (key, value) VALUES ('audit_engine', ?)", (mode,))
        conn.commit()

    return {"status": "success", "audit_engine": mode}


@router.get("/api/settings/database")
def get_db_engine():
    """Get current database engine and available options. Reloads .env on every call."""
    _load_env()
    pg_host     = _os.getenv("PG_HOST", "")
    pg_database = _os.getenv("PG_DATABASE", "")
    active      = get_active_engine()
    env_override = bool(_os.getenv("DB_ENGINE", ""))
    pg_configured = bool(pg_host and pg_database)
    return {
        "active_engine":      active,
        "env_override":       env_override,
        "pg_configured":      pg_configured,
        "psycopg2_available": _psycopg2_available,
        "pg_host":            pg_host or None,
        "pg_database":        pg_database or None,
    }


@router.post("/api/settings/database")
def set_db_engine(data: DbEngineRequest):
    """Switch database engine at runtime (saved to db_config.json). Reloads .env first."""
    _load_env()
    pg_host     = _os.getenv("PG_HOST", "")
    pg_database = _os.getenv("PG_DATABASE", "")
    mode = data.engine.lower().strip()
    if mode not in ["sqlite", "postgres"]:
        raise HTTPException(status_code=400, detail="Invalid engine. Must be 'sqlite' or 'postgres'.")
    if mode == "postgres" and not _psycopg2_available:
        raise HTTPException(status_code=400, detail="psycopg2 is not installed on this server.")
    if mode == "postgres" and not (pg_host and pg_database):
        raise HTTPException(status_code=400, detail="PostgreSQL credentials not found in .env file. Add PG_HOST and PG_DATABASE.")
    env_override = bool(_os.getenv("DB_ENGINE", ""))
    if env_override:
        raise HTTPException(status_code=400, detail="DB_ENGINE env var is set — remove it to allow UI switching.")
    write_db_config(mode)
    try:
        init_db(DB_PATH)
    except Exception as e:
        logger.warning(f"Engine switched to {mode}, but init_db failed: {e}")
    return {"status": "success", "active_engine": mode}


@router.post("/api/settings/migrate-db")
def trigger_db_migration():
    """Migrate all data from local SQLite database (audits.db) into active PostgreSQL instance."""
    res = migrate_sqlite_to_postgres(DB_PATH)
    if res.get("status") == "error":
        raise HTTPException(status_code=400, detail=res.get("message"))
    return res


@router.get("/api/osquery/status")
def osquery_status():
    return {
        "available": osquery_engine.is_osquery_available(),
        "version": osquery_engine.get_osquery_version(),
        "path": osquery_engine.get_osquery_path() or "Not Installed"
    }
