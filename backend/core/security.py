"""
JWT issuing and verification for the portal's login/register flow.

The token is stateless on purpose: there is no session table, so nothing here
touches the database on a normal request. That trade means a token stays valid
until it expires — there is no server-side revoke. Keep JWT_EXPIRE_MINUTES
short enough that this is acceptable, and rotate JWT_SECRET to invalidate every
outstanding token at once.
"""
import os
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import HTTPException, Request, status


def _load_env():
    """Mirrors auth_db's loader so the secret can live in the same .env file."""
    try:
        from dotenv import load_dotenv
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        root_dir = os.path.abspath(os.path.join(base_dir, ".."))
        load_dotenv(os.path.join(root_dir, ".env"), override=True)
        load_dotenv(os.path.join(base_dir, ".env"), override=True)
        load_dotenv(override=True)
    except ImportError:
        pass


ALGORITHM = "HS256"

# Requests that must work without a token. Everything outside /api/ is already
# public (the SPA's static files, and the agent script downloads the collectors
# fetch by plain URL), so only the /api/ exceptions need listing here.
#
# The collector scripts run unattended on workstations with no user session, so
# the endpoints they call are open by necessity — they are write-only ingestion
# or public script text, not portal data.
PUBLIC_API_PATHS = frozenset({
    "/api/auth/login",
    "/api/auth/register",
    "/api/upload-audit",
    "/api/check-status",
    "/api/server-info",
    "/api/sys-agent",
    "/api/sys-win",
    "/api/sys-agent-mac",
    "/api/get-audit-script",
    "/api/install-daemon",
    "/api/download-exe-launcher",
    "/api/download-vbs-launcher",
    "/api/download-mac-launcher",
    "/api/download-linux-launcher",
})


def get_jwt_secret() -> str:
    _load_env()
    return os.getenv("JWT_SECRET", "")


def get_expire_minutes() -> int:
    _load_env()
    try:
        return int(os.getenv("JWT_EXPIRE_MINUTES", "720"))
    except ValueError:
        return 720


def create_access_token(user: dict) -> str:
    """Sign a token for an authenticated user. `sub` is the user's UUID."""
    secret = get_jwt_secret()
    if not secret:
        raise RuntimeError(
            "JWT_SECRET is not set — refusing to sign tokens with an empty key. "
            "Add JWT_SECRET to .env."
        )

    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user["id"]),
        "email": user.get("email"),
        "user_type": user.get("user_type"),
        "organization_id": str(user["organization_id"]) if user.get("organization_id") else None,
        "roles": user.get("roles", []),
        "iat": now,
        "exp": now + timedelta(minutes=get_expire_minutes()),
    }
    return jwt.encode(payload, secret, algorithm=ALGORITHM)


def decode_access_token(token: str) -> dict:
    """Verify signature + expiry. Raises 401 on anything that doesn't check out."""
    secret = get_jwt_secret()
    if not secret:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Server auth is misconfigured (JWT_SECRET missing).",
        )
    try:
        return jwt.decode(token, secret, algorithms=[ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session expired. Please log in again.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token.",
            headers={"WWW-Authenticate": "Bearer"},
        )


def is_public_path(path: str) -> bool:
    """Public unless it's an /api/ route outside the allowlist."""
    if not path.startswith("/api/"):
        return True
    return path.rstrip("/") in PUBLIC_API_PATHS


def bearer_token(request: Request) -> str | None:
    header = request.headers.get("authorization") or ""
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        return None
    return token.strip()


def get_current_user(request: Request) -> dict:
    """
    Dependency for handlers that need to know who is calling. The auth
    middleware has already verified the token and stashed the claims, so this
    is just a typed read of that — no second decode.
    """
    claims = getattr(request.state, "user", None)
    if not claims:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return claims
