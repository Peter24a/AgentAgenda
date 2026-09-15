from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field


class UploadInitRequest(BaseModel):
    filename: str = Field(..., min_length=1, description="Nombre original del archivo (ej. constancia_fiscal.pdf)")
    mime_type: str = Field(..., description="Tipo MIME del archivo (ej. application/pdf, image/jpeg)")
    expected_size_bytes: int = Field(..., gt=0, description="Tamaño total esperado en bytes")
    expected_sha256: Optional[str] = Field(None, min_length=64, max_length=64, description="Hash SHA-256 esperado para validación de integridad")
    title: Optional[str] = Field(None, description="Título descriptivo de la ficha documental")
    alias: Optional[str] = Field(None, description="Alias o identificador secundario")
    doc_type: str = Field("generic", description="Categoría documental (ej. constancia, identificacion, factura, medico, tramite)")
    issuer: Optional[str] = Field(None, description="Entidad emisora (ej. SAT, IMSS, Banco)")
    holder: Optional[str] = Field(None, description="Titular del documento")
    document_id: Optional[str] = Field(None, description="ID del documento si se está subiendo una nueva versión histórica")


class UploadSessionResponse(BaseModel):
    upload_id: str
    status: str
    uploaded_bytes: int
    expected_size_bytes: int
    created_at: datetime


class DocumentRevisionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    document_id: str
    version: int
    original_filename: str
    mime_type: str
    file_size_bytes: int
    sha256_hash: str
    extraction_status: str
    extracted_text: Optional[str] = None
    created_at: datetime


class DocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str
    title: str
    alias: Optional[str] = None
    doc_type: str
    issuer: Optional[str] = None
    holder: Optional[str] = None
    issue_date: Optional[datetime] = None
    expiry_date: Optional[datetime] = None
    revisions: List[DocumentRevisionResponse] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class DocumentUpdateRequest(BaseModel):
    title: Optional[str] = None
    alias: Optional[str] = None
    doc_type: Optional[str] = None
    issuer: Optional[str] = None
    holder: Optional[str] = None
    issue_date: Optional[datetime] = None
    expiry_date: Optional[datetime] = None


class DocumentListResponse(BaseModel):
    total: int
    documents: List[DocumentResponse]
