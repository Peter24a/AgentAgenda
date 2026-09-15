from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field


class JobCreateRequest(BaseModel):
    job_type: str = Field(..., description="Tipo de trabajo: document_extraction, generate_reminders, cleanup_temp_uploads, etc.")
    payload: Dict[str, Any] = Field(default_factory=dict, description="Parámetros del trabajo")
    scheduled_at: Optional[datetime] = Field(None, description="Fecha programada para ejecución diferida")
    max_attempts: int = Field(3, ge=1, le=10)


class JobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    job_type: str
    payload_json: Dict[str, Any]
    status: str # pending, processing, completed, failed, cancelled
    attempts: int
    max_attempts: int
    error_message: Optional[str] = None
    scheduled_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class JobBatchProcessResponse(BaseModel):
    processed_count: int
    succeeded_count: int
    failed_count: int
    jobs: List[JobResponse]


class ReminderDetail(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str
    event_id: Optional[str] = None
    task_id: Optional[str] = None
    remind_at: datetime
    offset_minutes: int
    status: str # pending, sent, cancelled, dismissed
    channel: str # local_alarm, push, silent
    title: Optional[str] = None
    created_at: datetime
