from datetime import datetime
from typing import Optional, Any
from sqlalchemy import (
    Column, String, Integer, Boolean, DateTime, Text, JSON, ForeignKey, Index
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()

class SyncHead(Base):
    __tablename__ = "sync_head"
    user_id = Column(String(64), primary_key=True, default="default_user")
    current_seq = Column(Integer, nullable=False, default=0)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class Device(Base):
    __tablename__ = "devices"
    id = Column(String(64), primary_key=True)
    user_id = Column(String(64), nullable=False, default="default_user")
    device_name = Column(String(128), nullable=False)
    platform = Column(String(32), nullable=False, default="android") # android, ios, web, cli
    capabilities = Column(JSON, nullable=True) # list of supported capabilities
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_seen_at = Column(DateTime, default=datetime.utcnow)

class AuthToken(Base):
    __tablename__ = "auth_tokens"
    id = Column(String(64), primary_key=True)
    device_id = Column(String(64), ForeignKey("devices.id"), nullable=True)
    user_id = Column(String(64), nullable=False, default="default_user")
    token_hash = Column(String(128), nullable=False, index=True)
    scopes = Column(JSON, nullable=False, default=list) # e.g. ["agenda:read", "agenda:write"]
    expires_at = Column(DateTime, nullable=False)
    revoked_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

class AccessGrant(Base):
    __tablename__ = "access_grants"
    id = Column(String(64), primary_key=True)
    user_id = Column(String(64), nullable=False, default="default_user")
    client_name = Column(String(64), nullable=False) # e.g. "Codex", "ChatGPT"
    scopes = Column(JSON, nullable=False, default=list)
    purpose = Column(String(256), nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    expires_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

class Event(Base):
    __tablename__ = "events"
    id = Column(String(64), primary_key=True)
    user_id = Column(String(64), nullable=False, default="default_user", index=True)
    title = Column(String(256), nullable=False)
    description = Column(Text, nullable=True)
    start_time = Column(DateTime, nullable=False, index=True)
    end_time = Column(DateTime, nullable=True)
    timezone = Column(String(64), nullable=False, default="America/Mexico_City")
    category = Column(String(32), nullable=False, default="general")
    is_completed = Column(Boolean, nullable=False, default=False)
    version = Column(Integer, nullable=False, default=1)
    is_deleted = Column(Boolean, nullable=False, default=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class Task(Base):
    __tablename__ = "tasks"
    id = Column(String(64), primary_key=True)
    user_id = Column(String(64), nullable=False, default="default_user", index=True)
    title = Column(String(256), nullable=False)
    description = Column(Text, nullable=True)
    status = Column(String(32), nullable=False, default="pending") # pending, in_progress, completed, cancelled
    priority = Column(String(16), nullable=False, default="medium") # low, medium, high, urgent
    due_date = Column(DateTime, nullable=True, index=True)
    version = Column(Integer, nullable=False, default=1)
    is_deleted = Column(Boolean, nullable=False, default=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class Reminder(Base):
    __tablename__ = "reminders"
    id = Column(String(64), primary_key=True)
    user_id = Column(String(64), nullable=False, default="default_user", index=True)
    event_id = Column(String(64), ForeignKey("events.id"), nullable=True)
    task_id = Column(String(64), ForeignKey("tasks.id"), nullable=True)
    remind_at = Column(DateTime, nullable=False, index=True)
    offset_minutes = Column(Integer, nullable=False, default=60)
    status = Column(String(32), nullable=False, default="pending") # pending, sent, cancelled, dismissed
    channel = Column(String(32), nullable=False, default="local_alarm") # local_alarm, push, silent
    created_at = Column(DateTime, default=datetime.utcnow)

class Proposal(Base):
    __tablename__ = "proposals"
    id = Column(String(64), primary_key=True)
    user_id = Column(String(64), nullable=False, default="default_user")
    summary = Column(String(256), nullable=False)
    reason = Column(Text, nullable=False)
    resulting_items = Column(JSON, nullable=False) # list of dicts with items
    status = Column(String(32), nullable=False, default="pending") # pending, accepted, rejected
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class ChatTurn(Base):
    __tablename__ = "chat_turns"
    id = Column(String(64), primary_key=True)
    user_id = Column(String(64), nullable=False, default="default_user")
    device_id = Column(String(64), nullable=True)
    client_message_id = Column(String(128), nullable=True, index=True)
    status = Column(String(32), nullable=False, default="queued") # queued, running, completed, failed, cancelled
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)

    messages = relationship("ChatMessage", back_populates="turn", cascade="all, delete-orphan", lazy="selectin")

class ChatMessage(Base):
    __tablename__ = "chat_messages"
    id = Column(String(64), primary_key=True)
    turn_id = Column(String(64), ForeignKey("chat_turns.id"), nullable=True, index=True)
    user_id = Column(String(64), nullable=False, default="default_user", index=True)
    role = Column(String(16), nullable=False) # user, assistant, system
    content = Column(Text, nullable=False)
    client_created_at = Column(DateTime, nullable=True)
    received_at = Column(DateTime, default=datetime.utcnow)
    created_at = Column(DateTime, default=datetime.utcnow)

    turn = relationship("ChatTurn", back_populates="messages")

class Document(Base):
    __tablename__ = "documents"
    id = Column(String(64), primary_key=True)
    user_id = Column(String(64), nullable=False, default="default_user", index=True)
    title = Column(String(256), nullable=False)
    alias = Column(String(256), nullable=True)
    doc_type = Column(String(64), nullable=False, default="generic")
    issuer = Column(String(128), nullable=True)
    holder = Column(String(128), nullable=True)
    issue_date = Column(DateTime, nullable=True)
    expiry_date = Column(DateTime, nullable=True)
    is_deleted = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    revisions = relationship("DocumentRevision", back_populates="document", cascade="all, delete-orphan", lazy="selectin")

class DocumentRevision(Base):
    __tablename__ = "document_revisions"
    id = Column(String(64), primary_key=True)
    document_id = Column(String(64), ForeignKey("documents.id"), nullable=False, index=True)
    version = Column(Integer, nullable=False, default=1)
    storage_path = Column(String(512), nullable=False)
    original_filename = Column(String(256), nullable=False)
    mime_type = Column(String(255), nullable=False)
    file_size_bytes = Column(Integer, nullable=False)
    sha256_hash = Column(String(64), nullable=False, index=True)
    extracted_text = Column(Text, nullable=True)
    extraction_status = Column(String(32), nullable=False, default="pending") # pending, ready, needs_review, failed
    created_at = Column(DateTime, default=datetime.utcnow)

    document = relationship("Document", back_populates="revisions")

class DocumentRequirement(Base):
    __tablename__ = "document_requirements"
    id = Column(String(64), primary_key=True)
    user_id = Column(String(64), nullable=False, default="default_user", index=True)
    event_id = Column(String(64), ForeignKey("events.id"), nullable=True, index=True)
    task_id = Column(String(64), ForeignKey("tasks.id"), nullable=True, index=True)
    title = Column(String(256), nullable=False)
    description = Column(Text, nullable=True)
    rule_source = Column(String(64), nullable=True)
    status = Column(String(32), nullable=False, default="missing") # candidate, verified, missing, expired, unknown
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class DocumentLink(Base):
    __tablename__ = "document_links"
    id = Column(String(64), primary_key=True)
    requirement_id = Column(String(64), ForeignKey("document_requirements.id"), nullable=False, index=True)
    document_id = Column(String(64), ForeignKey("documents.id"), nullable=False, index=True)
    revision_id = Column(String(64), ForeignKey("document_revisions.id"), nullable=True)
    status = Column(String(32), nullable=False, default="candidate") # candidate, verified, rejected
    verified_at = Column(DateTime, nullable=True)
    verified_by = Column(String(64), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

class Entity(Base):
    __tablename__ = "entities"
    id = Column(String(64), primary_key=True)
    user_id = Column(String(64), nullable=False, default="default_user", index=True)
    name = Column(String(256), nullable=False)
    entity_type = Column(String(64), nullable=False) # person, organization, project, location
    metadata_json = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class Memory(Base):
    __tablename__ = "memories"
    id = Column(String(64), primary_key=True)
    user_id = Column(String(64), nullable=False, default="default_user", index=True)
    memory_type = Column(String(32), nullable=False) # semantic, episodic, procedural, prospective
    subject_id = Column(String(64), nullable=True)
    predicate = Column(String(128), nullable=False)
    value = Column(Text, nullable=False)
    context_text = Column(Text, nullable=True)
    source_kind = Column(String(32), nullable=False, default="chat") # chat, document, phone, import
    status = Column(String(32), nullable=False, default="active") # active, superseded, revoked
    valid_from = Column(DateTime, nullable=True)
    valid_to = Column(DateTime, nullable=True)
    version = Column(Integer, nullable=False, default=1)
    supersedes_id = Column(String(64), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    sources = relationship("MemorySource", back_populates="memory", cascade="all, delete-orphan", lazy="selectin")

class MemorySource(Base):
    __tablename__ = "memory_sources"
    id = Column(String(64), primary_key=True)
    memory_id = Column(String(64), ForeignKey("memories.id"), nullable=False, index=True)
    source_kind = Column(String(32), nullable=False)
    source_id = Column(String(64), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    memory = relationship("Memory", back_populates="sources")

class OperationReceipt(Base):
    __tablename__ = "operation_receipts"
    operation_id = Column(String(64), primary_key=True)
    user_id = Column(String(64), nullable=False, default="default_user", index=True)
    device_id = Column(String(64), nullable=True)
    operation_epoch = Column(String(64), nullable=False)
    canonical_hash = Column(String(64), nullable=False)
    status = Column(String(32), nullable=False) # applied, duplicate, conflict, rejected
    result_json = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

class ChangeBatch(Base):
    __tablename__ = "change_batches"
    id = Column(String(64), primary_key=True)
    user_id = Column(String(64), nullable=False, default="default_user", index=True)
    commit_seq = Column(Integer, nullable=False, index=True)
    entity_type = Column(String(32), nullable=False) # event, task, document, memory, proposal
    entity_id = Column(String(64), nullable=False)
    change_type = Column(String(16), nullable=False) # create, update, delete
    entity_version = Column(Integer, nullable=False, default=1)
    payload_json = Column(JSON, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

class DeviceRequest(Base):
    __tablename__ = "device_requests"
    id = Column(String(64), primary_key=True)
    user_id = Column(String(64), nullable=False, default="default_user", index=True)
    device_id = Column(String(64), nullable=False)
    capability = Column(String(64), nullable=False) # timezone, location, calendar_snapshot, battery
    purpose = Column(String(256), nullable=False)
    ttl_seconds = Column(Integer, nullable=False, default=300)
    status = Column(String(32), nullable=False, default="pending") # pending, completed, denied, expired, unavailable
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=False)

class DeviceObservation(Base):
    __tablename__ = "device_observations"
    id = Column(String(64), primary_key=True)
    user_id = Column(String(64), nullable=False, default="default_user", index=True)
    device_id = Column(String(64), nullable=False)
    request_id = Column(String(64), nullable=True)
    capability = Column(String(64), nullable=False)
    payload_json = Column(JSON, nullable=False)
    observed_at = Column(DateTime, nullable=False)
    received_at = Column(DateTime, default=datetime.utcnow)

class Job(Base):
    __tablename__ = "jobs"
    id = Column(String(64), primary_key=True)
    job_type = Column(String(64), nullable=False, index=True)
    payload_json = Column(JSON, nullable=False)
    status = Column(String(32), nullable=False, default="pending", index=True) # pending, processing, completed, failed, cancelled
    attempts = Column(Integer, nullable=False, default=0)
    max_attempts = Column(Integer, nullable=False, default=3)
    error_message = Column(Text, nullable=True)
    scheduled_at = Column(DateTime, default=datetime.utcnow, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class AuditEvent(Base):
    __tablename__ = "audit_events"
    id = Column(String(64), primary_key=True)
    user_id = Column(String(64), nullable=False, default="default_user", index=True)
    event_type = Column(String(64), nullable=False)
    details_json = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

class ImportBatch(Base):
    __tablename__ = "import_batches"
    id = Column(String(64), primary_key=True)
    user_id = Column(String(64), nullable=False, index=True)
    source_collection = Column(String(128), nullable=False)
    manifest_sha256 = Column(String(64), nullable=False)
    status = Column(String(32), nullable=False, default="running")
    report_json = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)


class DocumentOrigin(Base):
    __tablename__ = "document_origins"
    document_id = Column(String(64), ForeignKey("documents.id"), primary_key=True)
    source_collection = Column(String(128), nullable=False, index=True)
    source_path = Column(Text, nullable=False)
    privacy_class = Column(String(32), nullable=False)
    source_kind = Column(String(32), nullable=False)
    source_date = Column(String(64), nullable=True)
    metadata_json = Column(JSON, nullable=True)
    batch_id = Column(String(64), ForeignKey("import_batches.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
