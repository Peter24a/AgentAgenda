from typing import Any, Dict, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db_session, require_scope
from app.mcp.server import mcp_server
from app.models.auth import AuthContext
from app.services.context_export import context_export_service

router = APIRouter(tags=["Model Context Protocol (MCP) & Context Export"])


class ContextExportRequest(BaseModel):
    format: str = Field("json", description="Formato de salida: json o markdown")
    include_documents: bool = Field(True, description="Incluir metadatos del archivo documental")


@router.post(
    "/v1/mcp",
    summary="Model Context Protocol (MCP) JSON-RPC 2.0 endpoint",
    description="Permite que clientes externos (Codex, Cursor, Claude Desktop, ChatGPT) invoquen herramientas de lectura canónica.",
)
async def handle_mcp_request(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    auth: AuthContext = Depends(require_scope("mcp:read")),
):
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cuerpo de petición no es un JSON válido",
        )

    response = await mcp_server.handle_jsonrpc(
        session=session,
        user_id=auth.user_id,
        request_data=body,
    )
    return response


@router.post(
    "/v1/context/export",
    summary="Exportar contexto canónico portable con firma SHA-256",
    description="Genera un paquete de contexto completo o dossier Markdown para agentes externos con verificación criptográfica.",
)
async def export_context(
    req: ContextExportRequest,
    session: AsyncSession = Depends(get_db_session),
    auth: AuthContext = Depends(require_scope("mcp:read")),
):
    result = await context_export_service.export_canonical_context(
        session=session,
        user_id=auth.user_id,
        export_format=req.format,
        include_documents=req.include_documents,
    )
    return result
