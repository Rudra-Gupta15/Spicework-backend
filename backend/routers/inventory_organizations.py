from fastapi import APIRouter, HTTPException

from backend import auth_db
from backend.models.auth import CreateEmployeeRequest, CreateOrganizationRequest, CreateSiteRequest

router = APIRouter()


# ── Organizations ────────────────────────────────────────────────────────────

@router.post("/api/organizations")
def create_organization(data: CreateOrganizationRequest):
    try:
        return auth_db.create_organization(
            name=data.name,
            admin_email=data.admin_email,
            admin_password=data.admin_password,
            admin_first_name=data.admin_first_name,
            admin_last_name=data.admin_last_name,
            created_by=str(data.created_by) if data.created_by else None,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/api/organizations")
def list_organizations():
    return {"organizations": auth_db.list_organizations()}


@router.get("/api/organizations/{organization_id}")
def get_organization(organization_id: str):
    org = auth_db.get_organization(organization_id)
    if not org:
        raise HTTPException(status_code=404, detail=f"No organization found with id '{organization_id}'.")
    return org


@router.get("/api/organizations/{organization_id}/detail")
def get_organization_detail(organization_id: str):
    detail = auth_db.get_organization_detail(organization_id)
    if not detail:
        raise HTTPException(status_code=404, detail=f"No organization found with id '{organization_id}'.")
    return detail


# ── Sites ────────────────────────────────────────────────────────────────────

@router.post("/api/organizations/{organization_id}/sites")
def create_site(organization_id: str, data: CreateSiteRequest):
    try:
        return auth_db.create_site(
            organization_id=organization_id,
            name=data.name,
            address_line=data.address_line,
            city=data.city,
            state=data.state,
            country=data.country,
            postal_code=data.postal_code,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/api/organizations/{organization_id}/sites")
def list_sites(organization_id: str):
    return {"sites": auth_db.list_sites(organization_id)}


@router.get("/api/sites/{site_id}")
def get_site(site_id: str):
    site = auth_db.get_site(site_id)
    if not site:
        raise HTTPException(status_code=404, detail=f"No site found with id '{site_id}'.")
    return site


# ── Employees ────────────────────────────────────────────────────────────────

@router.post("/api/organizations/{organization_id}/employees")
def create_employee(organization_id: str, data: CreateEmployeeRequest):
    try:
        return auth_db.create_employee(
            organization_id=organization_id,
            email=data.email,
            password=data.password,
            first_name=data.first_name,
            last_name=data.last_name,
            role_name=data.role_name,
            site_id=str(data.site_id) if data.site_id else None,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/api/organizations/{organization_id}/employees")
def list_employees(organization_id: str, site_id: str = None):
    return {"employees": auth_db.list_employees(organization_id, site_id=site_id)}
