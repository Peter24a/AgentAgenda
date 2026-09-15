from typing import Any, Dict, Optional, Literal
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db_session, get_explicit_auth, has_scope
from app.mcp.server import mcp_server, SUPPORTED_VERSIONS, rpc_error
from app.config import settings
from app.models.auth import AuthContext
from app.services.context_export import context_export_service

router = APIRouter(tags=["Model Context Protocol (MCP) & Context Export"])


class ContextExportRequest(BaseModel):
    format: Literal["json", "markdown"] = "json"
    include_documents: bool = Field(False, description="Incluir metadatos documentales SAFE")


async def require_mcp_auth(auth: AuthContext = Depends(get_explicit_auth)):
    if not has_scope(auth, "mcp:read"):
        raise HTTPException(status_code=403, detail="Se requiere mcp:read")
    return auth


@router.post(
    "/v1/mcp",
    summary="Model Context Protocol (MCP) JSON-RPC 2.0 endpoint",
    description="Permite que clientes externos (Codex, Cursor, Claude Desktop, ChatGPT) invoquen herramientas de lectura canónica.",
)
async def handle_mcp_request(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    auth: AuthContext = Depends(require_mcp_auth),
):
    origin = request.headers.get("origin")
    allowed_origins = {value.strip().rstrip("/") for value in settings.mcp_allowed_origins.split(",") if value.strip()}
    allowed_origins.add(str(request.base_url).rstrip("/"))
    if origin is not None and origin.rstrip("/") not in allowed_origins:
        raise HTTPException(status_code=403, detail="Origin no autorizado")
    version = request.headers.get("mcp-protocol-version")
    if version is not None and version not in SUPPORTED_VERSIONS:
        raise HTTPException(status_code=400, detail="Versión MCP no soportada")
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(rpc_error(None, -32700, "JSON inválido"), status_code=400)

    response = await mcp_server.handle_jsonrpc(
        session=session,
        auth=auth,
        request_data=body,
    )
    if response is None:
        return Response(status_code=202)
    return response


@router.post(
    "/v1/context/export",
    summary="Exportar contexto autorizado con hash de integridad SHA-256",
    description="Genera una copia de contexto; el hash no es una firma ni un respaldo restaurable.",
)
async def export_context(
    req: ContextExportRequest,
    session: AsyncSession = Depends(get_db_session),
    auth: AuthContext = Depends(require_mcp_auth),
):
    scopes = ["agenda:read", "tasks:read", "memory:read"]
    if req.include_documents:
        scopes.append("documents:read")
    if not all(has_scope(auth, scope) for scope in scopes):
        raise HTTPException(status_code=403, detail="Permisos insuficientes para las categorías de exportación")
    result = await context_export_service.export_canonical_context(
        session=session,
        user_id=auth.user_id,
        export_format=req.format,
        include_documents=req.include_documents,
    )
    return result
