from fastapi import APIRouter, HTTPException

from backend import auth_db

router = APIRouter()


@router.get("/api/inventory/status")
def inventory_status():
    return auth_db.test_connection()


@router.get("/api/inventory/users")
def get_inventory_users():
    try:
        return {"users": auth_db.list_users()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/inventory/users/{user_id}")
def get_inventory_user(user_id: str):
    try:
        user = auth_db.get_user_by_id(user_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    if not user:
        raise HTTPException(status_code=404, detail=f"No user found with id '{user_id}'.")
    return user


@router.get("/api/inventory/users/{user_id}/roles")
def get_inventory_user_roles(user_id: str):
    try:
        return {"roles": auth_db.get_roles_for_user(user_id)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/inventory/roles")
def get_inventory_roles():
    try:
        return {"roles": auth_db.list_roles()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/inventory/user-roles")
def get_inventory_user_role_assignments():
    try:
        return {"assignments": auth_db.list_user_roles()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
