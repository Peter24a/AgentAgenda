import os
from datetime import datetime, timezone
from typing import Any, Dict
from fastapi import APIRouter, Depends
import httpx
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db_session
from app.config import settings
from app.models.canonical import Job

router = APIRouter(tags=["System Status"])


@router.get(
    "/v1/status",
    summary="Estado de salud integral del sistema y subsistemas",
    description="Informa sobre el estado de la base de datos canónica, versión del protocolo sync, almacenamiento y LLM.",
)
async def get_system_status(
    session: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    now_iso = datetime.now(timezone.utc).isoformat()

    # 1. Base de datos
    db_status = "connected"
    dialect = "unknown"
    try:
        await session.execute(text("SELECT 1"))
        if session.bind:
            dialect = session.bind.dialect.name
    except Exception as e:
        db_status = f"error: {str(e)}"

    # 2. Cola de trabajos (Worker)
    pending_jobs = 0
    try:
        job_res = await session.execute(
            select(func.count(Job.id)).where(Job.status == "pending")
        )
        pending_jobs = job_res.scalar() or 0
    except Exception:
        pass

    # 3. Almacenamiento privado
    storage_ok = os.path.exists(settings.storage_path)

    # 4. Estado LLM
    llm_info = {
        "model": settings.llm_model,
        "api_base": settings.llm_api_base,
        "status": "configured",
    }
    try:
        async with httpx.AsyncClient(timeout=1.0) as client:
            resp = await client.get(f"{settings.llm_api_base}/models")
            if resp.status_code == 200:
                llm_info["status"] = "online"
    except Exception:
        llm_info["status"] = "offline_or_local"

    overall_status = "healthy" if db_status == "connected" and storage_ok else "degraded"

    return {
        "status": overall_status,
        "service": settings.app_name,
        "version": "1.0.0",
        "sync_schema_version": 1,
        "database": {
            "status": db_status,
            "dialect": dialect,
        },
        "storage": {
            "status": "ready" if storage_ok else "missing_directory",
            "path": settings.storage_path,
        },
        "worker": {
            "status": "active",
            "pending_jobs": pending_jobs,
        },
        "llm": llm_info,
        "timestamp": now_iso,
    }
