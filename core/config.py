import logging
import os
import time
from pathlib import Path

from backend.db import init_db

# ── Filesystem locations ─────────────────────────────────────────────────────
# CWD-relative: the app is launched from the repo root (uvicorn backend.main:app),
# so these resolve the same way they always have.
DB_PATH = "audits.db"  # used only for SQLite fallback path
LOGS_DIR = "logs"
USER_INFO_DIR = "user_info"
ASSET_METADATA_DIR = "user_info/assets"

# __file__-relative: computed once here so it's correct no matter which
# router/service module ends up needing it.
BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = BACKEND_DIR.parent
FRONTEND_DIR = str(REPO_ROOT / "frontend")
SCRIPTS_DIR = str(REPO_ROOT / "scripts")
REMOTE_AUDITS_FILE = str(BACKEND_DIR / "remote_audits_db.json")

init_db(DB_PATH)

for d in [LOGS_DIR, USER_INFO_DIR, ASSET_METADATA_DIR]:
    os.makedirs(d, exist_ok=True)


def _cleanup_old_temp_files():
    """Clean up orphaned temporary files in scratch/ and temp folders."""
    try:
        scratch_dir = os.path.join(os.getcwd(), "scratch")
        if os.path.exists(scratch_dir):
            now = time.time()
            for f in os.listdir(scratch_dir):
                fp = os.path.join(scratch_dir, f)
                if os.path.isfile(fp) and (f.endswith((".cs", ".exe", ".vbs", ".xml")) or f.startswith("launcher_")):
                    if now - os.path.getmtime(fp) > 7200:
                        try:
                            os.remove(fp)
                        except Exception:
                            pass
    except Exception:
        pass


_cleanup_old_temp_files()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(f"{LOGS_DIR}/audit_backend.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("AuditBackend")
