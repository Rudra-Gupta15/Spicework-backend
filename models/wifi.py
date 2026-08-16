from pydantic import BaseModel


class WifiConnectRequest(BaseModel):
    ssid: str
    password: str


class WifiSaveCredentialRequest(BaseModel):
    ssid: str
    password: str


class NotificationRequest(BaseModel):
    ip_address: str
    username: str
    password: str
    method: str = "auto"
