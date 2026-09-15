import hashlib
import json
from datetime import datetime
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field


def compute_canonical_hash(
    operation_id: str,
    operation_epoch: str,
    entity_type: str,
    entity_id: str,
    base_version: int,
    action: str,
    payload: Dict[str, Any],
) -> str:
    """Calcula un hash SHA-256 canónico y determinista del comando."""
    data = {
        "operation_id": operation_id,
        "operation_epoch": operation_epoch,
        "entity_type": entity_type,
        "entity_id": entity_id,
        "base_version": base_version,
        "action": action,
        "payload": payload,
    }
    encoded = json.dumps(data, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class SyncOperation(BaseModel):
    operation_id: str = Field(..., description="Identificador único global del comando generado por el cliente")
    operation_epoch: str = Field(..., description="Época de comandos asignada al dispositivo")
    entity_type: Literal["event", "task", "proposal", "document", "memory"] = Field(..., description="Tipo canónico de entidad")
    entity_id: str = Field(..., description="Identificador único de la entidad")
    base_version: int = Field(0, ge=0, description="0 para creación; versión exacta esperada para edición/borrado")
    action: Literal["create", "update", "delete", "set_status"] = Field(..., description="Acción deseada")
    payload: Dict[str, Any] = Field(default_factory=dict, description="Datos de la mutación")
    client_created_at: Optional[datetime] = Field(None, description="Fecha y hora de origen en el dispositivo")

    def get_canonical_hash(self) -> str:
        return compute_canonical_hash(
            self.operation_id,
            self.operation_epoch,
            self.entity_type,
            self.entity_id,
            self.base_version,
            self.action,
            self.payload,
        )


class SyncPushRequest(BaseModel):
    sync_schema_version: int = Field(1, description="Versión del protocolo de sincronización (1)")
    device_id: Optional[str] = Field(None, description="ID del dispositivo emisor")
    operations: List[SyncOperation] = Field(..., min_length=1, description="Lote atómico o secuencial de operaciones")


class OperationResult(BaseModel):
    operation_id: str
    entity_id: str
    entity_type: str
    status: Literal["applied", "duplicate", "conflict", "rejected"]
    new_version: Optional[int] = None
    error_message: Optional[str] = None
    current_server_state: Optional[Dict[str, Any]] = None


class SyncPushResponse(BaseModel):
    sync_schema_version: int = 1
    commit_seq: int = Field(..., description="Último commit_seq alcanzado tras aplicar el lote")
    results: List[OperationResult]


class ChangeItem(BaseModel):
    id: str
    commit_seq: int
    entity_type: str
    entity_id: str
    change_type: str
    entity_version: int
    payload: Dict[str, Any]
    created_at: datetime


class SyncPullResponse(BaseModel):
    sync_schema_version: int = 1
    current_seq: int = Field(..., description="Marca de agua (watermark) máxima actual del servidor")
    has_more: bool = Field(False, description="Indica si existen más cambios pendientes de paginar")
    changes: List[ChangeItem]


class SyncBootstrapResponse(BaseModel):
    sync_schema_version: int = 1
    watermark_seq: int = Field(..., description="Cursor inicial para subsecuentes consultas pull")
    events: List[Dict[str, Any]] = Field(default_factory=list)
    tasks: List[Dict[str, Any]] = Field(default_factory=list)
    proposals: List[Dict[str, Any]] = Field(default_factory=list)
    memories: List[Dict[str, Any]] = Field(default_factory=list)
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class SyncAckRequest(BaseModel):
    device_id: str = Field(..., description="ID del dispositivo que confirma")
    last_applied_seq: int = Field(..., ge=0, description="Último commit_seq integrado en local")


class SyncAckResponse(BaseModel):
    success: bool
    acknowledged_seq: int


class OperationReceiptResponse(BaseModel):
    operation_id: str
    user_id: str
    device_id: Optional[str]
    operation_epoch: str
    canonical_hash: str
    status: str
    result: Optional[Dict[str, Any]]
    created_at: datetime
