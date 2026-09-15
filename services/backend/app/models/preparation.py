from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field


class CreateRequirementRequest(BaseModel):
    title: str = Field(..., min_length=1, description="Título del requisito (ej. Identificación Oficial Vigente)")
    description: Optional[str] = Field(None, description="Instrucciones o especificaciones (ej. Original y 2 copias)")
    rule_source: str = Field("user", description="Origen de la regla (user, agent_inference, template)")
    task_id: Optional[str] = Field(None, description="ID opcional de tarea asociada")


class LinkDocumentRequest(BaseModel):
    document_id: str = Field(..., description="ID del documento canónico a vincular")
    revision_id: Optional[str] = Field(None, description="ID de revisión específica (o última por defecto)")
    status: str = Field("candidate", description="Estado inicial del vínculo: candidate o verified")


class VerifyRequirementRequest(BaseModel):
    link_id: Optional[str] = Field(None, description="ID del enlace a verificar (si se omite, verifica el último candidato)")
    status: str = Field("verified", description="Nuevo estado: verified, rejected o candidate")
    verified_by: str = Field("user", description="Identidad que valida el requisito: user o agent")


class DocumentLinkDetail(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    requirement_id: str
    document_id: str
    document_title: str
    revision_id: Optional[str] = None
    version: Optional[int] = None
    status: str
    mime_type: Optional[str] = None
    sha256_hash: Optional[str] = None
    is_expired: bool = False
    expiry_date: Optional[datetime] = None
    verified_at: Optional[datetime] = None
    verified_by: Optional[str] = None
    created_at: datetime


class RequirementDetail(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    event_id: Optional[str] = None
    task_id: Optional[str] = None
    title: str
    description: Optional[str] = None
    rule_source: Optional[str] = None
    status: str # missing, candidate, verified, expired, unknown
    links: List[DocumentLinkDetail] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class EventPreparationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    event_id: str
    event_title: str
    event_start_time: datetime
    readiness_status: str # ready, in_progress, attention_required
    total_requirements: int
    verified_count: int
    candidate_count: int
    missing_count: int
    expired_count: int
    requirements: List[RequirementDetail] = Field(default_factory=list)
    missing_requirements: List[RequirementDetail] = Field(default_factory=list)
    verified_requirements: List[RequirementDetail] = Field(default_factory=list)
    attention_required: List[RequirementDetail] = Field(default_factory=list)
