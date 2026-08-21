from typing import List

from pydantic import BaseModel


class RowUpdate(BaseModel):
    row_key: str
    """A blank dict clears this row's correction rather than setting one."""
    fields: dict[str, str] = {}


class RowOverridesRequest(BaseModel):
    """One or several rows of one section, saved together."""
    updates: List[RowUpdate]
