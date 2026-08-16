from fastapi import APIRouter, HTTPException

from backend import auth_db
from backend.models.auth import LoginRequest

router = APIRouter()


@router.post("/api/auth/login")
def login(data: LoginRequest):
    user = auth_db.authenticate_user(data.email, data.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid email or password.")
    return user
