# ==============================================================================
#  db.py  —  PostgreSQL / SQLite with dynamic runtime hot-switch & migration
#  DB engine is controlled dynamically by:
#    1. DB_ENGINE env var ("sqlite" | "postgres")  — checked dynamically
#    2. db_config.json file                        — runtime toggle from Settings UI
#    3. Auto: if PG_HOST + PG_DATABASE are set → postgres, else sqlite
# ==============================================================================
import os
import sqlite3
import logging
import json
import re
from contextlib import contextmanager

logger = logging.getLogger("AuditBackend.DB")

# ── Environment & Config Helper ───────────────────────────────────────────────
def _load_env():
    try:
        from dotenv import load_dotenv
        base_dir = os.path.dirname(os.path.abspath(__file__))
        root_dir = os.path.abspath(os.path.join(base_dir, ".."))
        load_dotenv(os.path.join(root_dir, ".env"), override=True)
        load_dotenv(os.path.join(base_dir, ".env"), override=True)
        load_dotenv(override=True)
    except ImportError:
        pass

def get_pg_creds() -> dict:
    """Fetch PostgreSQL credentials dynamically."""
    _load_env()
    return {
        "host": os.getenv("PG_HOST", ""),
        "port": int(os.getenv("PG_PORT", "5432")),
        "user": os.getenv("PG_USER", "postgres"),
        "password": os.getenv("PG_PASSWORD", ""),
        "dbname": os.getenv("PG_DATABASE", ""),
    }

# ── Runtime config file (written by Settings UI toggle) ───────────────────────
DB_CONFIG_FILE = "db_config.json"

def _read_db_config() -> dict:
    """Read the runtime db config file. Returns defaults if not found."""
    try:
        if os.path.exists(DB_CONFIG_FILE):
            with open(DB_CONFIG_FILE, "r") as f:
                return json.load(f)
    except Exception:
        pass
    return {"engine": "auto"}

def write_db_config(engine: str):
    """Write the DB engine choice to config file. engine = 'sqlite' | 'postgres' | 'auto'"""
    with open(DB_CONFIG_FILE, "w") as f:
        json.dump({"engine": engine}, f)
    logger.info(f"DB engine switched to: {engine}")

def get_active_engine() -> str:
    """
    Determine active DB engine dynamically on demand. Priority:
    1. DB_ENGINE env var (set 'postgres' on AWS deployment, overrides everything)
    2. db_config.json (set by Settings UI toggle)
    3. Auto-detect: if PG creds in environment → postgres, else sqlite
    Returns: 'postgres' or 'sqlite'
    """
    _load_env()
    env_engine = os.getenv("DB_ENGINE", "").lower()
    if env_engine in ("postgres", "postgresql", "pg"):
        return "postgres"
    if env_engine == "sqlite":
        return "sqlite"

    # Check runtime config file
    cfg = _read_db_config()
    cfg_engine = cfg.get("engine", "auto").lower()
    if cfg_engine == "postgres":
        return "postgres"
    if cfg_engine == "sqlite":
        return "sqlite"

    # Auto-detect from environment credentials
    creds = get_pg_creds()
    if creds["host"] and creds["dbname"]:
        return "postgres"
    return "sqlite"

# Try to import psycopg2 (needed for postgres mode)
_psycopg2_available = False
try:
    import psycopg2
    import psycopg2.extras
    _psycopg2_available = True
except ImportError:
    logger.warning("psycopg2 not installed — PostgreSQL mode will not be available")

def is_postgres_active() -> bool:
    """Returns True if PostgreSQL is selected AND psycopg2 driver is available."""
    return (get_active_engine() == "postgres") and _psycopg2_available

# Standard module attributes for backward compatibility
USE_POSTGRES = is_postgres_active()
PG_HOST = os.getenv("PG_HOST", "")
PG_DATABASE = os.getenv("PG_DATABASE", "")


# ── Compatibility cursor wrapper ───────────────────────────────────────────────
class _DictRow(dict):
    """A dict subclass that also supports column-index access like sqlite3.Row."""
    def __getitem__(self, key):
        if isinstance(key, int):
            return list(self.values())[key]
        return super().__getitem__(key)


class CompatCursor:
    """
    Wraps a psycopg2 RealDictCursor to behave like sqlite3's Row-factory cursor.
    Preserves fetched rows so lastrowid extraction does not swallow application rows.
    """
    def __init__(self, cur):
        self._cur = cur
        self.lastrowid = None
        self._buffered_row = None

    def execute(self, sql, params=()):
        pg_sql = _to_pg(sql)
        self._cur.execute(pg_sql, params)
        self.lastrowid = None
        self._buffered_row = None

        # Attempt to grab lastrowid if INSERT … RETURNING id was used
        if re.match(r"^\s*INSERT", pg_sql, re.IGNORECASE) and "RETURNING" in pg_sql.upper():
            try:
                row = self._cur.fetchone()
                if row:
                    if "id" in row:
                        self.lastrowid = row["id"]
                    self._buffered_row = row
            except Exception:
                pass
        return self

    def fetchone(self):
        if self._buffered_row is not None:
            row = self._buffered_row
            self._buffered_row = None
            return _DictRow(dict(row)) if isinstance(row, dict) else row
        row = self._cur.fetchone()
        if row is None:
            return None
        return _DictRow(dict(row)) if isinstance(row, dict) else row

    def fetchall(self):
        rows = []
        if self._buffered_row is not None:
            rows.append(self._buffered_row)
            self._buffered_row = None
        try:
            more = self._cur.fetchall()
            if more:
                rows.extend(more)
        except Exception:
            pass
        return [_DictRow(dict(r)) if isinstance(r, dict) else r for r in rows]

    def __iter__(self):
        if self._buffered_row is not None:
            row = self._buffered_row
            self._buffered_row = None
            yield _DictRow(dict(row)) if isinstance(row, dict) else row
        for row in self._cur:
            yield _DictRow(dict(row)) if isinstance(row, dict) else row


class CompatConn:
    """
    Wraps a psycopg2 connection to look like sqlite3's context-manager connection.
    Idempotent close/commit/rollback to prevent errors on double exit.
    """
    def __init__(self, pg_conn):
        self._conn = pg_conn
        self.row_factory = None  # accepted but ignored
        self.lastrowid = None
        self._closed = False

    def cursor(self):
        raw = self._conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        return CompatCursor(raw)

    def execute(self, sql, params=()):
        cur = self.cursor()
        cur.execute(sql, params)
        self.lastrowid = cur.lastrowid
        return cur

    def commit(self):
        if not self._closed and self._conn and not self._conn.closed:
            try:
                self._conn.commit()
            except Exception:
                pass

    def rollback(self):
        if not self._closed and self._conn and not self._conn.closed:
            try:
                self._conn.rollback()
            except Exception:
                pass

    def close(self):
        if not self._closed:
            self._closed = True
            try:
                if self._conn and not self._conn.closed:
                    self._conn.close()
            except Exception:
                pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type:
            self.rollback()
        else:
            self.commit()
        self.close()
        return False


# ── Public API ─────────────────────────────────────────────────────────────────
@contextmanager
def get_db(sqlite_path: str = "audits.db"):
    """
    Context manager — drop-in replacement for `with sqlite3.connect(DB_PATH) as conn:`
    Engine is determined dynamically on every call. Fallback to SQLite if PostgreSQL fails.
    """
    if is_postgres_active():
        creds = get_pg_creds()
        pg_conn = None
        try:
            pg_conn = psycopg2.connect(
                host=creds["host"],
                port=creds["port"],
                user=creds["user"],
                password=creds["password"],
                dbname=creds["dbname"],
                connect_timeout=5
            )
        except Exception as e:
            logger.error(f"PostgreSQL connection failed: {e}. Falling back to SQLite ({sqlite_path}).")
            pg_conn = None

        if pg_conn is not None:
            wrapper = CompatConn(pg_conn)
            try:
                yield wrapper
            except Exception:
                wrapper.rollback()
                raise
            finally:
                wrapper.commit()
                wrapper.close()
            return

    with sqlite3.connect(sqlite_path) as conn:
        yield conn


def _guess_pk(table: str) -> str:
    """Return the primary key column name for known tables."""
    pks = {
        "portal_settings": "key",
        "wifi_credentials": "ssid",
        "asset_lifecycle": "mac_address",
    }
    return pks.get(table.lower(), "id")


def _to_pg(sql: str) -> str:
    """Convert SQLite-dialect SQL to PostgreSQL-compatible SQL safely."""
    if not sql or not isinstance(sql, str):
        return sql

    # 1. Replace ? placeholders with %s
    sql = sql.replace("?", "%s")

    # 2. INTEGER PRIMARY KEY AUTOINCREMENT → SERIAL PRIMARY KEY
    sql = re.sub(
        r"INTEGER\s+PRIMARY\s+KEY\s+AUTOINCREMENT",
        "SERIAL PRIMARY KEY",
        sql, flags=re.IGNORECASE
    )

    # 3. INSERT OR IGNORE → INSERT INTO ... ON CONFLICT DO NOTHING
    had_or_ignore = bool(re.search(r"INSERT\s+OR\s+IGNORE", sql, re.IGNORECASE))
    sql = re.sub(r"INSERT\s+OR\s+IGNORE\s+INTO", "INSERT INTO", sql, flags=re.IGNORECASE)

    # 4. INSERT OR REPLACE → INSERT … ON CONFLICT DO UPDATE / DO NOTHING
    def _replace_handler(m):
        table = m.group(1)
        cols_str = m.group(2)
        vals_str = m.group(3)
        pk = _guess_pk(table)
        
        cols = [c.strip() for c in cols_str.split(",") if c.strip()]
        non_pk_cols = [c for c in cols if c.lower() != pk.lower()]

        if not non_pk_cols:
            # If inserted columns only contain PK, DO UPDATE SET is invalid syntax in PG
            return f"INSERT INTO {table} ({cols_str}) VALUES ({vals_str}) ON CONFLICT ({pk}) DO NOTHING"

        set_clause = ", ".join(f"{c} = EXCLUDED.{c}" for c in non_pk_cols)
        return (
            f"INSERT INTO {table} ({cols_str}) VALUES ({vals_str}) "
            f"ON CONFLICT ({pk}) DO UPDATE SET {set_clause}"
        )

    sql = re.sub(
        r"INSERT\s+OR\s+REPLACE\s+INTO\s+(\w+)\s*\(([^)]+)\)\s*VALUES\s*\(([^)]+)\)",
        _replace_handler,
        sql, flags=re.IGNORECASE
    )

    # 5. Add RETURNING id to INSERT (so lastrowid works)
    TEXT_PK_TABLES = {"portal_settings", "wifi_credentials", "asset_lifecycle"}

    def _should_add_returning(sql_str):
        m = re.match(r"^\s*INSERT\s+INTO\s+(\w+)", sql_str, re.IGNORECASE)
        if not m:
            return False
        table = m.group(1).lower()
        return table not in TEXT_PK_TABLES

    if re.match(r"^\s*INSERT\s+INTO", sql, re.IGNORECASE):
        if "RETURNING" not in sql.upper() and _should_add_returning(sql):
            sql = sql.rstrip().rstrip(";") + " RETURNING id"

    # 6. Add ON CONFLICT DO NOTHING for converted INSERT OR IGNORE if not present
    if had_or_ignore and "ON CONFLICT" not in sql.upper():
        if "RETURNING id" in sql:
            sql = sql.replace(" RETURNING id", "") + " ON CONFLICT DO NOTHING RETURNING id"
        else:
            sql = sql.rstrip().rstrip(";") + " ON CONFLICT DO NOTHING"

    # 7. Remove SQLite-specific COLLATE NOCASE
    sql = re.sub(r"\s+COLLATE\s+NOCASE", "", sql, flags=re.IGNORECASE)

    return sql


def init_db(sqlite_path: str = "audits.db"):
    """Create all tables on the active database engine (PostgreSQL or SQLite)."""
    with get_db(sqlite_path) as conn:
        if is_postgres_active():
            conn.execute('''
                CREATE TABLE IF NOT EXISTS device_audits (
                    id SERIAL PRIMARY KEY,
                    mac_address TEXT,
                    computer_name TEXT,
                    os_name TEXT,
                    execution_datetime TEXT,
                    audit_data TEXT
                )
            ''')
            conn.execute('''
                CREATE TABLE IF NOT EXISTS wifi_credentials (
                    ssid TEXT PRIMARY KEY,
                    password TEXT NOT NULL,
                    updated_at TEXT
                )
            ''')
            conn.execute('''
                CREATE TABLE IF NOT EXISTS asset_lifecycle (
                    mac_address TEXT PRIMARY KEY,
                    computer_name TEXT,
                    owner TEXT DEFAULT '',
                    location TEXT DEFAULT '',
                    vendor TEXT DEFAULT '',
                    status TEXT DEFAULT 'Active',
                    warranty_start TEXT DEFAULT '',
                    warranty_end TEXT DEFAULT '',
                    warranty_notes TEXT DEFAULT '',
                    warranty_provider TEXT DEFAULT '',
                    purchase_price TEXT DEFAULT '',
                    purchase_date TEXT DEFAULT '',
                    supplier TEXT DEFAULT '',
                    po_number TEXT DEFAULT '',
                    updated_at TEXT
                )
            ''')
            try:
                conn.execute("ALTER TABLE asset_lifecycle ADD COLUMN IF NOT EXISTS location TEXT DEFAULT ''")
            except Exception:
                pass
            conn.execute('''
                CREATE TABLE IF NOT EXISTS asset_tickets (
                    id SERIAL PRIMARY KEY,
                    mac_address TEXT,
                    computer_name TEXT,
                    ticket_number TEXT,
                    summary TEXT,
                    status TEXT DEFAULT 'Open',
                    assigned TEXT DEFAULT '',
                    priority TEXT DEFAULT 'Medium',
                    mtbf TEXT DEFAULT '',
                    created_at TEXT,
                    updated_at TEXT
                )
            ''')
            conn.execute('''
                CREATE TABLE IF NOT EXISTS portal_settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
            ''')
            conn.execute(
                "INSERT INTO portal_settings (key, value) VALUES ('audit_engine', 'native') "
                "ON CONFLICT (key) DO NOTHING"
            )
        else:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS device_audits (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    mac_address TEXT,
                    computer_name TEXT,
                    os_name TEXT,
                    execution_datetime TEXT,
                    audit_data TEXT
                )
            ''')
            conn.execute('''
                CREATE TABLE IF NOT EXISTS wifi_credentials (
                    ssid TEXT PRIMARY KEY,
                    password TEXT NOT NULL,
                    updated_at TEXT
                )
            ''')
            conn.execute('''
                CREATE TABLE IF NOT EXISTS asset_lifecycle (
                    mac_address TEXT PRIMARY KEY,
                    computer_name TEXT,
                    owner TEXT DEFAULT '',
                    location TEXT DEFAULT '',
                    vendor TEXT DEFAULT '',
                    status TEXT DEFAULT 'Active',
                    warranty_start TEXT DEFAULT '',
                    warranty_end TEXT DEFAULT '',
                    warranty_notes TEXT DEFAULT '',
                    warranty_provider TEXT DEFAULT '',
                    purchase_price TEXT DEFAULT '',
                    purchase_date TEXT DEFAULT '',
                    supplier TEXT DEFAULT '',
                    po_number TEXT DEFAULT '',
                    updated_at TEXT
                )
            ''')
            try:
                conn.execute("ALTER TABLE asset_lifecycle ADD COLUMN location TEXT DEFAULT ''")
            except Exception:
                pass
            conn.execute('''
                CREATE TABLE IF NOT EXISTS asset_tickets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    mac_address TEXT,
                    computer_name TEXT,
                    ticket_number TEXT,
                    summary TEXT,
                    status TEXT DEFAULT 'Open',
                    assigned TEXT DEFAULT '',
                    priority TEXT DEFAULT 'Medium',
                    mtbf TEXT DEFAULT '',
                    created_at TEXT,
                    updated_at TEXT
                )
            ''')
            conn.execute('''
                CREATE TABLE IF NOT EXISTS portal_settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
            ''')
            conn.execute("INSERT OR IGNORE INTO portal_settings (key, value) VALUES ('audit_engine', 'native')")
            conn.commit()


def migrate_sqlite_to_postgres(sqlite_path: str = "audits.db") -> dict:
    """
    Migrates all records from local SQLite audits.db into active PostgreSQL database.
    Returns summary dict of migrated rows count per table.
    """
    if not os.path.exists(sqlite_path):
        return {"status": "error", "message": f"SQLite database file {sqlite_path} not found"}

    if not is_postgres_active():
        return {"status": "error", "message": "PostgreSQL is not currently active"}

    # Ensure PostgreSQL tables exist
    init_db(sqlite_path)

    stats = {}
    with sqlite3.connect(sqlite_path) as sq_conn:
        sq_conn.row_factory = sqlite3.Row

        # 1. Device Audits
        audits = sq_conn.execute("SELECT mac_address, computer_name, os_name, execution_datetime, audit_data FROM device_audits").fetchall()
        audits_count = 0
        with get_db(sqlite_path) as pg_conn:
            for row in audits:
                pg_conn.execute(
                    "INSERT INTO device_audits (mac_address, computer_name, os_name, execution_datetime, audit_data) "
                    "VALUES (%s, %s, %s, %s, %s)",
                    (row["mac_address"], row["computer_name"], row["os_name"], row["execution_datetime"], row["audit_data"])
                )
                audits_count += 1
        stats["device_audits"] = audits_count

        # 2. Wifi Credentials
        wifi = sq_conn.execute("SELECT ssid, password, updated_at FROM wifi_credentials").fetchall()
        wifi_count = 0
        with get_db(sqlite_path) as pg_conn:
            for row in wifi:
                pg_conn.execute(
                    "INSERT INTO wifi_credentials (ssid, password, updated_at) VALUES (%s, %s, %s) "
                    "ON CONFLICT (ssid) DO UPDATE SET password = EXCLUDED.password, updated_at = EXCLUDED.updated_at",
                    (row["ssid"], row["password"], row["updated_at"])
                )
                wifi_count += 1
        stats["wifi_credentials"] = wifi_count

        # 3. Asset Lifecycle
        assets = sq_conn.execute("SELECT * FROM asset_lifecycle").fetchall()
        asset_count = 0
        with get_db(sqlite_path) as pg_conn:
            for row in assets:
                d = dict(row)
                cols = list(d.keys())
                vals = [d[c] for c in cols]
                cols_str = ", ".join(cols)
                placeholders = ", ".join(["%s"] * len(cols))
                update_str = ", ".join([f"{c} = EXCLUDED.{c}" for c in cols if c != "mac_address"])
                pg_conn.execute(
                    f"INSERT INTO asset_lifecycle ({cols_str}) VALUES ({placeholders}) "
                    f"ON CONFLICT (mac_address) DO UPDATE SET {update_str}",
                    vals
                )
                asset_count += 1
        stats["asset_lifecycle"] = asset_count

        # 4. Asset Tickets
        tickets = sq_conn.execute("SELECT mac_address, computer_name, ticket_number, summary, status, assigned, priority, mtbf, created_at, updated_at FROM asset_tickets").fetchall()
        ticket_count = 0
        with get_db(sqlite_path) as pg_conn:
            for row in tickets:
                pg_conn.execute(
                    "INSERT INTO asset_tickets (mac_address, computer_name, ticket_number, summary, status, assigned, priority, mtbf, created_at, updated_at) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                    (row["mac_address"], row["computer_name"], row["ticket_number"], row["summary"], row["status"], row["assigned"], row["priority"], row["mtbf"], row["created_at"], row["updated_at"])
                )
                ticket_count += 1
        stats["asset_tickets"] = ticket_count

        # 5. Portal Settings
        settings = sq_conn.execute("SELECT key, value FROM portal_settings").fetchall()
        settings_count = 0
        with get_db(sqlite_path) as pg_conn:
            for row in settings:
                pg_conn.execute(
                    "INSERT INTO portal_settings (key, value) VALUES (%s, %s) "
                    "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value",
                    (row["key"], row["value"])
                )
                settings_count += 1
        stats["portal_settings"] = settings_count

    return {"status": "success", "migrated_rows": stats}


# Module level fallback getter for dynamic properties
def __getattr__(name):
    if name == "USE_POSTGRES":
        return is_postgres_active()
    if name == "PG_HOST":
        return get_pg_creds()["host"]
    if name == "PG_DATABASE":
        return get_pg_creds()["dbname"]
    if name == "PG_PORT":
        return get_pg_creds()["port"]
    if name == "PG_USER":
        return get_pg_creds()["user"]
    if name == "PG_PASSWORD":
        return get_pg_creds()["password"]
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")
