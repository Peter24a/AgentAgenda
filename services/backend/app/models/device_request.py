from datetime import datetime
from typing import Any, Dict, Optional
from pydantic import BaseModel, ConfigDict, Field


class CreateDeviceRequest(BaseModel):
    device_id: Optional[str] = Field(None, description="ID del dispositivo destino (o por defecto el del cliente)")
    capability: str = Field(..., description="Capacidad solicitada: timezone, location, calendar_snapshot, battery")
    purpose: str = Field(..., min_length=3, description="Propósito o justificación de la solicitud")
    ttl_seconds: int = Field(300, ge=10, le=86400, description="Tiempo de vida en segundos")


class DeviceRequestResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str
    device_id: str
    capability: str
    purpose: str
    ttl_seconds: int
    status: str # pending, completed, denied, expired, unavailable
    created_at: datetime
    expires_at: datetime


class DeviceObservationPayload(BaseModel):
    status: str = Field("completed", description="Estado de respuesta: completed, denied, unavailable")
    payload: Dict[str, Any] = Field(default_factory=dict, description="Datos de la observación (ej. coordenadas, zona horaria)")
    observed_at: Optional[datetime] = Field(None, description="Momento exacto de captura en el sensor del teléfono")


class DeviceObservationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    request_id: Optional[str] = None
    capability: str
    payload_json: Dict[str, Any]
    observed_at: datetime
    received_at: datetime
