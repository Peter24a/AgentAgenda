"""Read-only MCP tools shared by a stateless Streamable HTTP endpoint."""
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo
from typing import Any
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import select

from app.api.deps import has_scope
from app.models.canonical import Document, Event
from app.models.memory import ContextAssembleRequest, MemorySearchRequest
from app.services.context_engine import context_engine
from app.services.context_visibility import safe_document_filters
from app.services.memory_service import memory_service
from app.services.preparation_service import preparation_service

PROTOCOL_VERSION = "2025-06-18"
SUPPORTED_VERSIONS = {PROTOCOL_VERSION, "2025-03-26"}


class Arguments(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class ContextArguments(Arguments):
    purpose: str = Field("external_agent", max_length=200)
    token_budget: int = Field(2048, ge=256, le=8192)
    as_of: str | None = None
    timezone: str = "America/Mexico_City"


class AgendaArguments(Arguments):
    from_date: str | None = None
    to_date: str | None = None
    limit: int = Field(100, ge=1, le=500)
    timezone: str = "America/Mexico_City"


class SearchArguments(Arguments):
    query: str = Field(min_length=1, max_length=500)
    limit: int = Field(20, ge=1, le=100)


class DocumentArguments(Arguments):
    query: str = Field("", max_length=500)
    doc_type: str | None = Field(None, max_length=64)


class PreparationArguments(Arguments):
    event_id: str = Field(min_length=1, max_length=64)


TOOLS = {
    "get_personal_context": (ContextArguments, ("memory:read", "agenda:read", "tasks:read"), "Consulta contexto vigente y acotado. Las fuentes documentales deben ser SAFE."),
    "query_agenda": (AgendaArguments, ("agenda:read",), "Consulta hasta 31 días de agenda. Fechas sin hora se interpretan en timezone; to_date incluye ese día."),
    "search": (SearchArguments, ("memory:read", "agenda:read"), "Busca memorias vigentes y eventos por texto, con límite explícito."),
    "search_documents": (DocumentArguments, ("documents:read",), "Busca metadatos de documentos explícitamente SAFE, sin originales ni texto extraído."),
    "get_event_preparation": (PreparationArguments, ("agenda:read", "documents:read"), "Consulta requisitos de preparación de un evento propio."),
}


def result_text(text):
    return {"content": [{"type": "text", "text": text}]}


def rpc_error(req_id, code, message):
    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}


def parse_time(value, zone):
    parsed = datetime.fromisoformat(value)
    return (parsed if parsed.tzinfo else parsed.replace(tzinfo=zone)).astimezone(timezone.utc).replace(tzinfo=None)


class MCPServer:
    def get_tool_definitions(self, auth):
        return [{"name": name, "description": description,
                 "inputSchema": schema.model_json_schema(),
                 "annotations": {"readOnlyHint": True, "destructiveHint": False, "openWorldHint": False}}
                for name, (schema, scopes, description) in TOOLS.items()
                if all(has_scope(auth, scope) for scope in scopes)]

    async def call_tool(self, session, auth, tool_name, arguments):
        if tool_name not in TOOLS:
            raise ValueError("Herramienta desconocida")
        schema, scopes, _ = TOOLS[tool_name]
        if not all(has_scope(auth, scope) for scope in scopes):
            return {"isError": True, **result_text("Permiso insuficiente para esta herramienta")}
        args = schema.model_validate(arguments)
        user_id = auth.user_id
        if tool_name == "get_personal_context":
            zone = ZoneInfo(args.timezone)
            as_of = datetime.fromisoformat(args.as_of) if args.as_of else None
            if as_of and as_of.tzinfo is None:
                as_of = as_of.replace(tzinfo=zone)
            req = ContextAssembleRequest(purpose=args.purpose, token_budget=args.token_budget,
                                         as_of=as_of, timezone=args.timezone)
            response = await context_engine.assemble_context(session, user_id, req)
            return result_text(response.assembled_context)
        if tool_name == "query_agenda":
            zone = ZoneInfo(args.timezone)
            today = datetime.now(zone).date()
            start = parse_time(args.from_date or today.isoformat(), zone)
            if args.to_date:
                end = parse_time(args.to_date, zone)
                if len(args.to_date) == 10:
                    end += timedelta(days=1)
            else:
                end = start + timedelta(days=7)
            if end <= start or end - start > timedelta(days=31):
                raise ValueError("El intervalo debe ser positivo y no superar 31 días")
            events = (await session.scalars(select(Event).where(
                Event.user_id == user_id, Event.is_deleted.is_(False),
                Event.start_time >= start, Event.start_time < end,
            ).order_by(Event.start_time.asc()).limit(args.limit + 1))).all()
            lines = [f"Eventos (límite {args.limit}; hay más: {len(events) > args.limit}):"]
            for event in events[:args.limit]:
                clock = event.start_time.replace(tzinfo=timezone.utc).astimezone(zone).isoformat()
                lines.append(f"- ID: {event.id} | [{clock}] {event.title} ({event.description or ''})")
            return result_text("\n".join(lines))
        if tool_name == "search":
            query = args.query.strip()
            if not query:
                raise ValueError("query no puede estar vacío")
            memories, _ = await memory_service.search_memories(
                session, user_id, MemorySearchRequest(query=query, limit=args.limit), for_model=True,
            )
            pattern = f"%{query}%"
            events = (await session.scalars(select(Event).where(
                Event.user_id == user_id, Event.is_deleted.is_(False),
                Event.title.ilike(pattern) | Event.description.ilike(pattern),
            ).order_by(Event.start_time.desc()).limit(args.limit))).all()
            lines = [f"Resultados (máximo {args.limit} por categoría):"]
            lines += [context_engine.memory_line(memory) for memory in memories]
            lines += [f"- {event.title} ({event.start_time} UTC)" for event in events]
            return result_text("\n".join(lines))
        if tool_name == "search_documents":
            filters = list(safe_document_filters(user_id))
            if args.query.strip():
                pattern = f"%{args.query.strip()}%"
                filters.append(Document.title.ilike(pattern) | Document.issuer.ilike(pattern))
            if args.doc_type:
                filters.append(Document.doc_type == args.doc_type)
            documents = (await session.scalars(select(Document).where(*filters).order_by(Document.title).limit(20))).all()
            return result_text("\n".join([f"Documentos SAFE (máximo 20): {len(documents)}"] + [
                f"- [{doc.id}] {doc.title} (Tipo: {doc.doc_type}, Emisor: {doc.issuer})" for doc in documents
            ]))
        prep = await preparation_service.get_event_preparation(session, user_id, args.event_id)
        if prep is None:
            return {"isError": True, **result_text("Evento no encontrado")}
        return result_text("\n".join([f"Preparación para: {prep.event_title}"] + [
            f"- Requisito: {item.title}" for item in prep.requirements
        ]))

    async def handle_jsonrpc(self, session, auth, request_data: Any):
        if not isinstance(request_data, dict):
            return rpc_error(None, -32600, "Se requiere una petición JSON-RPC individual")
        req_id = request_data.get("id")
        if (request_data.get("jsonrpc") != "2.0" or not isinstance(request_data.get("method"), str)
                or ("id" in request_data and (type(req_id) not in (str, int)))
                or not isinstance(request_data.get("params", {}), dict)):
            return rpc_error(None, -32600, "Petición JSON-RPC inválida")
        method = request_data["method"]
        params = request_data.get("params", {})
        if "id" not in request_data:
            # Notifications have no JSON-RPC response, including unknown ones.
            return None
        if method == "initialize":
            if (not isinstance(params.get("protocolVersion"), str)
                    or not isinstance(params.get("clientInfo"), dict)
                    or not isinstance(params.get("capabilities"), dict)):
                return rpc_error(req_id, -32602, "Parámetros initialize inválidos")
            offered = params["protocolVersion"]
            return {"jsonrpc": "2.0", "id": req_id, "result": {
                "protocolVersion": offered if offered in SUPPORTED_VERSIONS else PROTOCOL_VERSION,
                "serverInfo": {"name": "agentagenda-mcp", "version": "1.1.0"},
                "capabilities": {"tools": {"listChanged": False}},
            }}
        if method == "ping":
            result = {}
        elif method == "tools/list":
            result = {"tools": self.get_tool_definitions(auth)}
        elif method == "tools/call":
            try:
                result = await self.call_tool(session, auth, params.get("name"), params.get("arguments", {}))
            except (ValueError, TypeError, KeyError, ValidationError):
                return rpc_error(req_id, -32602, "Nombre o argumentos de herramienta inválidos")
        else:
            return rpc_error(req_id, -32601, "Método no encontrado")
        return {"jsonrpc": "2.0", "id": req_id, "result": result}


mcp_server = MCPServer()
