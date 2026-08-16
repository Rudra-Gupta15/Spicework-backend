from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend import saved_searches_db

router = APIRouter()


class CreateSavedSearchRequest(BaseModel):
    category: str
    name: str
    scope: str = "Private"
    applied_filters: list[str] = []
    results_count: int = 0
    created_by: str = "Unknown"


@router.get("/api/saved-searches")
def list_saved_searches(category: Optional[str] = None):
    return {"searches": saved_searches_db.list_saved_searches(category)}


@router.post("/api/saved-searches")
def create_saved_search(data: CreateSavedSearchRequest):
    return saved_searches_db.create_saved_search(
        category=data.category,
        name=data.name,
        scope=data.scope,
        applied_filters=data.applied_filters,
        results_count=data.results_count,
        created_by=data.created_by,
    )


@router.get("/api/saved-searches/{search_id}")
def get_saved_search(search_id: str):
    search = saved_searches_db.get_saved_search(search_id)
    if not search:
        raise HTTPException(status_code=404, detail=f"No saved search found with id '{search_id}'.")
    return search


@router.delete("/api/saved-searches/{search_id}")
def delete_saved_search(search_id: str):
    if not saved_searches_db.delete_saved_search(search_id):
        raise HTTPException(status_code=404, detail=f"No saved search found with id '{search_id}'.")
    return {"status": "deleted"}
