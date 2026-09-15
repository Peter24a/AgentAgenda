import hashlib
import json
import os
import re
import shutil
import uuid
from datetime import datetime, timezone
from typing import Dict, Optional, Tuple

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.canonical import Document, DocumentRevision, Job
from app.models.document import UploadInitRequest, UploadSessionResponse


class DocumentStorageService:
    def __init__(self):
        self._sessions: Dict[str, Dict] = {}
        self._ensure_storage_dirs()

    def _ensure_storage_dirs(self):
        base = settings.storage_path
        os.makedirs(base, exist_ok=True)
        os.makedirs(os.path.join(base, "documents"), exist_ok=True)
        os.makedirs(os.path.join(base, "temp"), exist_ok=True)

    def start_upload_session(
        self, user_id: str, req: UploadInitRequest
    ) -> UploadSessionResponse:
        self._ensure_storage_dirs()

        if req.expected_size_bytes > settings.max_upload_size_bytes:
            raise ValueError(
                f"El tamaño del archivo ({req.expected_size_bytes} bytes) excede el límite permitido "
                f"de {settings.max_upload_size_bytes} bytes"
            )

        upload_id = f"upl-{uuid.uuid4().hex[:12]}"
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        temp_path = os.path.join(settings.storage_path, "temp", f"{upload_id}.part")

        # Inicializar archivo temporal vacío
        with open(temp_path, "wb") as f:
            pass

        session_meta = {
            "upload_id": upload_id,
            "user_id": user_id,
            "filename": req.filename,
            "mime_type": req.mime_type,
            "expected_size_bytes": req.expected_size_bytes,
            "expected_sha256": req.expected_sha256.lower() if req.expected_sha256 else None,
            "title": req.title,
            "alias": req.alias,
            "doc_type": req.doc_type,
            "issuer": req.issuer,
            "holder": req.holder,
            "document_id": req.document_id,
            "uploaded_bytes": 0,
            "status": "pending",
            "temp_path": temp_path,
            "created_at": now,
            "published_doc_id": None,
            "published_rev_id": None,
        }
        self._sessions[upload_id] = session_meta

        return UploadSessionResponse(
            upload_id=upload_id,
            status="pending",
            uploaded_bytes=0,
            expected_size_bytes=req.expected_size_bytes,
            created_at=now,
        )

    async def append_chunk(
        self, upload_id: str, user_id: str, chunk: bytes
    ) -> int:
        session = self._sessions.get(upload_id)
        if not session or session["user_id"] != user_id:
            raise ValueError("Sesión de carga no encontrada o no autorizada")

        if session["status"] not in ("pending", "uploading"):
            raise ValueError(f"No se pueden subir bytes en estado '{session['status']}'")

        temp_path = session["temp_path"]
        with open(temp_path, "ab") as f:
            f.write(chunk)

        session["uploaded_bytes"] += len(chunk)
        session["status"] = "uploading"

        if session["uploaded_bytes"] > settings.max_upload_size_bytes:
            session["status"] = "aborted"
            if os.path.exists(temp_path):
                os.remove(temp_path)
            raise ValueError("El archivo excedió el límite máximo configurado")

        return session["uploaded_bytes"]

    def get_upload_session(
        self, upload_id: str, user_id: str
    ) -> Optional[UploadSessionResponse]:
        session = self._sessions.get(upload_id)
        if not session or session["user_id"] != user_id:
            return None

        return UploadSessionResponse(
            upload_id=session["upload_id"],
            status=session["status"],
            uploaded_bytes=session["uploaded_bytes"],
            expected_size_bytes=session["expected_size_bytes"],
            created_at=session["created_at"],
        )

    async def complete_upload(
        self, session_db: AsyncSession, upload_id: str, user_id: str
    ) -> Tuple[Document, DocumentRevision]:
        session = self._sessions.get(upload_id)
        if not session or session["user_id"] != user_id:
            raise ValueError("Sesión de carga no encontrada o no autorizada")

        now = datetime.now(timezone.utc).replace(tzinfo=None)

        # Idempotencia: si ya se completó previamente, retornar las entidades publicadas
        if session["status"] == "completed" and session["published_doc_id"]:
            doc_res = await session_db.execute(
                select(Document).where(Document.id == session["published_doc_id"])
            )
            doc = doc_res.scalar_one_or_none()
            rev_res = await session_db.execute(
                select(DocumentRevision).where(DocumentRevision.id == session["published_rev_id"])
            )
            rev = rev_res.scalar_one_or_none()
            if doc and rev:
                return doc, rev

        temp_path = session["temp_path"]
        if not os.path.exists(temp_path):
            raise ValueError("El archivo temporal de carga no existe o fue descartado")

        # Calcular tamaño y hash SHA-256
        sha256_hash = hashlib.sha256()
        total_size = 0
        with open(temp_path, "rb") as f:
            while chunk := f.read(65536):
                sha256_hash.update(chunk)
                total_size += len(chunk)

        computed_digest = sha256_hash.hexdigest().lower()

        # Verificación estricta de hash SHA-256
        if session["expected_sha256"] and session["expected_sha256"] != computed_digest:
            session["status"] = "aborted"
            if os.path.exists(temp_path):
                os.remove(temp_path)
            raise ValueError(
                f"Discrepancia de integridad criptográfica: hash esperado {session['expected_sha256']}, "
                f"hash calculado {computed_digest}"
            )

        # Verificación de tamaño esperado
        if session["expected_size_bytes"] != total_size:
            session["status"] = "aborted"
            if os.path.exists(temp_path):
                os.remove(temp_path)
            raise ValueError(
                f"Discrepancia de tamaño de archivo: esperado {session['expected_size_bytes']} bytes, "
                f"recibido {total_size} bytes"
            )

        # Mover a la bóveda privada canonical
        clean_filename = re.sub(r"[^a-zA-Z0-9_.-]", "_", session["filename"])
        vault_filename = f"{computed_digest}_{clean_filename}"
        vault_path = os.path.join(settings.storage_path, "documents", vault_filename)

        # Si ya existe un archivo idéntico (deduplicación por contenido SHA-256), podemos sobreescribir o reutilizar
        shutil.move(temp_path, vault_path)

        # Publicar documento y revisión en base de datos PostgreSQL/SQLite
        doc_id = session["document_id"]
        doc: Optional[Document] = None

        if doc_id:
            doc_res = await session_db.execute(
                select(Document).where(
                    Document.id == doc_id,
                    Document.user_id == user_id,
                    Document.is_deleted.is_(False),
                )
            )
            doc = doc_res.scalar_one_or_none()
            if not doc:
                raise ValueError(f"Documento destino '{doc_id}' no encontrado o fue eliminado")

            # Obtener versión máxima existente
            ver_res = await session_db.execute(
                select(func.max(DocumentRevision.version)).where(
                    DocumentRevision.document_id == doc.id
                )
            )
            max_ver = ver_res.scalar() or 0
            new_version = max_ver + 1
            doc.updated_at = now
        else:
            doc_title = session["title"] or session["filename"]
            doc = Document(
                id=f"doc-{uuid.uuid4().hex[:12]}",
                user_id=user_id,
                title=doc_title,
                alias=session["alias"],
                doc_type=session["doc_type"] or "generic",
                issuer=session["issuer"],
                holder=session["holder"],
                is_deleted=False,
                created_at=now,
                updated_at=now,
            )
            session_db.add(doc)
            new_version = 1

        rev = DocumentRevision(
            id=f"rev-{uuid.uuid4().hex[:12]}",
            document_id=doc.id,
            version=new_version,
            storage_path=vault_path,
            original_filename=session["filename"],
            mime_type=session["mime_type"],
            file_size_bytes=total_size,
            sha256_hash=computed_digest,
            extracted_text=None,
            extraction_status="pending",
            created_at=now,
        )
        session_db.add(rev)

        # Registrar job asíncrono para extracción documental futura (Feature 9)
        job = Job(
            id=f"job-{uuid.uuid4().hex[:12]}",
            job_type="document_extraction",
            payload_json={"document_id": doc.id, "revision_id": rev.id},
            status="pending",
            created_at=now,
        )
        session_db.add(job)

        await session_db.commit()

        session["status"] = "completed"
        session["published_doc_id"] = doc.id
        session["published_rev_id"] = rev.id

        return doc, rev


document_storage = DocumentStorageService()
