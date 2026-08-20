"""
Login, signup and session identity.

Credentials are checked against the `users` table in the inventory PostgreSQL
database (bcrypt hashes, via auth_db) — this is the only place the portal turns
a password into a session. On success the caller gets a signed JWT; every
protected endpoint then expects it as `Authorization: Bearer <token>`.
"""
from fastapi import APIRouter, Depends, HTTPException, status

from backend import auth_db
from backend.core.security import (
    create_access_token,
    get_current_user,
    get_expire_minutes,
)
from backend.models.auth import AuthResponse, LoginRequest, RegisterRequest

router = APIRouter()

MIN_PASSWORD_LENGTH = 6


def _auth_response(user: dict) -> dict:
    return {
        "access_token": create_access_token(user),
        "token_type": "bearer",
        "expires_in": get_expire_minutes() * 60,
        "user": user,
    }


@router.post("/api/auth/login", response_model=AuthResponse)
def login(data: LoginRequest):
    user = auth_db.authenticate_user(data.email.strip(), data.password)
    if not user:
        # Deliberately identical for "no such email" and "wrong password" —
        # a distinct message would let anyone enumerate registered addresses.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
        )

    auth_db.touch_last_login(user["id"])
    return _auth_response(user)


@router.post("/api/auth/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
def register(data: RegisterRequest):
    """Creates the organization and its Organization Admin, then logs them straight in."""
    email = data.email.strip()
    organization_name = data.organization_name.strip()
    first_name = data.first_name.strip()

    if not organization_name:
        raise HTTPException(status_code=400, detail="Organization name is required.")
    if not first_name:
        raise HTTPException(status_code=400, detail="First name is required.")
    if "@" not in email or "." not in email.split("@")[-1]:
        raise HTTPException(status_code=400, detail="Enter a valid email address.")
    if len(data.password) < MIN_PASSWORD_LENGTH:
        raise HTTPException(
            status_code=400,
            detail=f"Password must be at least {MIN_PASSWORD_LENGTH} characters.",
        )

    try:
        user = auth_db.register_account(
            organization_name=organization_name,
            email=email,
            password=data.password,
            first_name=first_name,
            last_name=(data.last_name or "").strip() or None,
        )
    except ValueError as e:
        # Raised for a duplicate email — the one signup failure the caller can fix.
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))

    return _auth_response(user)


@router.get("/api/auth/me")
def me(claims: dict = Depends(get_current_user)):
    """
    Who the bearer token belongs to, read fresh from the database rather than
    from the token — so a deactivated or deleted account stops resolving
    immediately instead of when the token happens to expire.
    """
    user = auth_db.get_user_by_id(claims["sub"])
    if not user or not user["is_active"]:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Account is no longer active.",
        )
    user["roles"] = [r["name"] for r in auth_db.get_roles_for_user(user["id"])]
    return user
