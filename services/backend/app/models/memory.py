from datetime import datetime, timezone
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


class MemoryCreateRequest(BaseModel):
    memory_type: str = Field("semantic", description="Tipo de memoria: semantic, episodic, procedural, prospective")
    subject_id: Optional[str] = Field(None, description="Identificador del sujeto (o entidad relacionada)")
    predicate: str = Field(..., min_length=1, description="Predicado o clave fáctica (ej. alergia_medicamentos, direccion_casa)")
    value: str = Field(..., min_length=1, description="Valor del hecho o recuerdo en lenguaje natural")
    context_text: Optional[str] = Field(None, description="Contexto adicional que aclara el origen del hecho")
    source_kind: str = Field("chat", description="Origen: chat, document, phone, import, manual")
    source_id: Optional[str] = Field(None, description="ID del origen (ej. turn_id, doc_id)")
    valid_from: Optional[datetime] = None
    valid_to: Optional[datetime] = None

    @field_validator("valid_from", "valid_to")
    @classmethod
    def normalize_instant(cls, value):
        # The canonical DateTime columns store UTC without an offset.
        return value.astimezone(timezone.utc).replace(tzinfo=None) if value and value.tzinfo else value


class MemorySourceDetail(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    source_kind: str
    source_id: str
    created_at: datetime


class MemoryDetail(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str
    memory_type: str
    subject_id: Optional[str] = None
    predicate: str
    value: str
    context_text: Optional[str] = None
    source_kind: str
    status: str
    valid_from: Optional[datetime] = None
    valid_to: Optional[datetime] = None
    version: int
    supersedes_id: Optional[str] = None
    sources: List[MemorySourceDetail] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class MemorySearchRequest(BaseModel):
    query: Optional[str] = Field(None, description="Texto de búsqueda en predicado, valor o contexto")
    memory_type: Optional[str] = Field(None, description="Filtro por tipo: semantic, episodic, etc.")
    predicate: Optional[str] = Field(None, description="Filtro por predicado exacto")
    status: str = Field("active", description="Estado a consultar (active, superseded, revoked, all)")
    as_of: Optional[datetime] = Field(None, description="Fecha de vigencia consultada")
    limit: int = Field(50, ge=1, le=200)
    offset: int = Field(0, ge=0)


class MemorySearchResponse(BaseModel):
    total: int
    memories: List[MemoryDetail]


class MemoryCorrectRequest(BaseModel):
    memory_id: str = Field(..., description="ID de la memoria activa a corregir")
    new_value: str = Field(..., min_length=1, description="Nuevo valor correcto del hecho")
    reason: Optional[str] = Field(None, description="Motivo de la corrección")
    source_kind: str = Field("chat", description="Origen de la corrección")
    source_id: Optional[str] = Field(None, description="ID del origen")


class MemoryForgetRequest(BaseModel):
    memory_id: str = Field(..., description="ID de la memoria a olvidar/revocar")
    reason: Optional[str] = Field(None, description="Motivo de revocación")


class ContextAssembleRequest(BaseModel):
    purpose: str = Field("general_chat", description="Propósito del contexto (general_chat, agenda_planning, document_preparation)")
    as_of: Optional[datetime] = Field(None, description="Fecha de referencia para evaluar hechos y eventos de la agenda")
    token_budget: int = Field(6144, ge=256, le=24576, description="Presupuesto máximo estimado de tokens")
    include_agenda: bool = Field(True, description="Incluir actividades y tareas del día")
    include_memories: bool = Field(True, description="Incluir hechos y preferencias relevantes")
    timezone: Optional[str] = None

    @field_validator("timezone")
    @classmethod
    def valid_timezone(cls, value):
        if value:
            try:
                ZoneInfo(value)
            except (ZoneInfoNotFoundError, ValueError):
                raise ValueError("Zona horaria IANA inválida")
        return value


class ContextAssembleResponse(BaseModel):
    purpose: str
    as_of: datetime
    token_budget: int
    estimated_tokens: int
    items_included_count: int
    memories_count: int
    events_count: int
    tasks_count: int
    assembled_context: str
