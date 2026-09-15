from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field


class ChallengeResponse(BaseModel):
    pairing_code: str = Field(..., description="Código de emparejamiento de un solo uso")
    expires_at: datetime = Field(..., description="Fecha y hora de expiración UTC")
    ttl_minutes: int = Field(..., description="Minutos de validez restantes")


class PairRequest(BaseModel):
    pairing_code: str = Field(..., description="Desafío o código de emparejamiento temporal")
    device_name: str = Field(..., min_length=1, max_length=128, description="Nombre descriptivo del dispositivo (ej. Pixel 9 Pro)")
    platform: str = Field(default="android", max_length=32, description="Plataforma: android, ios, web, cli")
    capabilities: Optional[List[str]] = Field(default_factory=list, description="Capacidades soportadas (ej. location, calendar)")
    client_device_id: Optional[str] = Field(None, max_length=64, description="Identificador persistente del cliente si ya existe")


class PairResponse(BaseModel):
    device_id: str
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = Field(..., description="Segundos de validez del access_token")
    scopes: List[str]


class RefreshTokenRequest(BaseModel):
    refresh_token: str = Field(..., description="Token de refresco activo emitido previamente")


class RefreshTokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    scopes: List[str]


class RevokeRequest(BaseModel):
    token: Optional[str] = Field(None, description="Token específico a revocar")
    device_id: Optional[str] = Field(None, description="ID del dispositivo a desvincular y revocar por completo")


class RevokeResponse(BaseModel):
    success: bool
    message: str


class AuthContext(BaseModel):
    user_id: str
    device_id: Optional[str]
    token_id: str
    scopes: List[str]
    device_name: Optional[str] = None
    platform: Optional[str] = None


class DeviceResponse(BaseModel):
    id: str
    user_id: str
    device_name: str
    platform: str
    capabilities: Optional[List[str]] = None
    is_active: bool
    created_at: datetime
    last_seen_at: datetime
