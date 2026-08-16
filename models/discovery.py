from pydantic import BaseModel


class NetworkScanRequest(BaseModel):
    ip_range: str = "192.168.1.0/24"
    timeout_ms: int = 300
