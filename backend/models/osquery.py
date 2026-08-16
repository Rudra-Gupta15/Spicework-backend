from typing import Optional

from pydantic import BaseModel


class AuditEngineRequest(BaseModel):
    audit_engine: str  # "native" or "osquery"


class OsqueryQueryRequest(BaseModel):
    sql: str


class DbEngineRequest(BaseModel):
    engine: str  # "sqlite" or "postgres"


class RemoteAuditPayload(BaseModel):
    client_id: str
    hostname: str
    timestamp: str
    osquery_installed: bool = False
    device_name: Optional[str] = None
    os_name: Optional[str] = None
    manufacturer: Optional[str] = None
    model: Optional[str] = None
    serial_number: Optional[str] = None
