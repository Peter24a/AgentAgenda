import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.canonical import Document, Event, Memory, Task
from app.models.memory import ContextAssembleRequest
from app.services.context_engine import context_engine
from app.services.preparation_service import preparation_service


MCP_TOOLS_DEFINITIONS = [
    {
        "name": "get_personal_context",
        "description": "Obtiene el bloque de contexto personal canónico optimizado (eventos del día, tareas pendientes y memorias vigentes respetando límite de tokens).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "purpose": {"type": "string", "description": "Propósito de la interacción (ej. general_chat, agenda_planning)"},
                "token_budget": {"type": "integer", "description": "Presupuesto máximo de tokens", "default": 2048},
                "as_of": {"type": "string", "description": "Fecha y hora de referencia ISO 8601"},
            },
        },
    },
    {
        "name": "query_agenda",
        "description": "Consulta eventos y citas programadas en un rango de fechas.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "from_date": {"type": "string", "description": "Fecha inicial ISO 8601 (ej. 2026-09-15)"},
                "to_date": {"type": "string", "description": "Fecha final ISO 8601 (ej. 2026-09-20)"},
            },
        },
    },
    {
        "name": "search",
        "description": "Busca recuerdos, preferencias y compromisos por palabras clave.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Término de búsqueda"},
                "limit": {"type": "integer", "default": 20},
            },
            "required": ["query"],
        },
    },
    {
        "name": "search_documents",
        "description": "Busca documentos catalogados en la bóveda privada (título, emisor, titular, tipo).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Texto a buscar en metadatos"},
                "doc_type": {"type": "string", "description": "Categoría documental (fiscal, identificacion, etc.)"},
            },
        },
    },
    {
        "name": "get_event_preparation",
        "description": "Consulta el estado de preparación y requisitos documentales de una cita específica.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "event_id": {"type": "string", "description": "ID del evento o cita"},
            },
            "required": ["event_id"],
        },
    },
]


class MCPServer:
    def get_tool_definitions(self) -> List[Dict[str, Any]]:
        return MCP_TOOLS_DEFINITIONS

    async def call_tool(
        self,
        session: AsyncSession,
        user_id: str,
        tool_name: str,
        arguments: Dict[str, Any],
    ) -> Dict[str, Any]:
        if tool_name == "get_personal_context":
            purpose = arguments.get("purpose", "external_agent")
            budget = arguments.get("token_budget", 2048)
            as_of = None
            if arguments.get("as_of"):
                try:
                    as_of = datetime.fromisoformat(arguments["as_of"])
                except Exception:
                    pass

            req = ContextAssembleRequest(
                purpose=purpose,
                token_budget=budget,
                as_of=as_of,
                include_agenda=True,
                include_memories=True,
            )
            resp = await context_engine.assemble_context(session, user_id, req)
            return {"content": [{"type": "text", "text": resp.assembled_context}]}

        elif tool_name == "query_agenda":
            from_date = arguments.get("from_date")
            to_date = arguments.get("to_date")
            filters = [Event.user_id == user_id, Event.is_deleted.is_(False)]
            if from_date:
                try:
                    filters.append(Event.start_time >= datetime.fromisoformat(from_date))
                except Exception:
                    pass
            if to_date:
                try:
                    filters.append(Event.start_time <= datetime.fromisoformat(to_date))
                except Exception:
                    pass

            stmt = select(Event).where(*filters).order_by(Event.start_time.asc())
            res = await session.execute(stmt)
            events = list(res.scalars().all())

            text_lines = [f"Se encontraron {len(events)} eventos:"]
            for ev in events:
                time_str = ev.start_time.strftime("%Y-%m-%d %H:%M") if ev.start_time else "Sin fecha"
                text_lines.append(f"- ID: {ev.id} | [{time_str}] {ev.title} {f'({ev.description})' if ev.description else ''}")

            return {"content": [{"type": "text", "text": "\n".join(text_lines)}]}

        elif tool_name == "search":
            query = arguments.get("query", "").strip()
            pattern = f"%{query}%"

            # Buscar en memorias
            mem_stmt = (
                select(Memory)
                .where(
                    Memory.user_id == user_id,
                    Memory.status == "active",
                    (Memory.predicate.ilike(pattern) | Memory.value.ilike(pattern)),
                )
                .limit(arguments.get("limit", 20))
            )
            mem_res = await session.execute(mem_stmt)
            mems = list(mem_res.scalars().all())

            # Buscar en eventos
            ev_stmt = (
                select(Event)
                .where(
                    Event.user_id == user_id,
                    Event.is_deleted.is_(False),
                    (Event.title.ilike(pattern) | Event.description.ilike(pattern)),
                )
                .limit(arguments.get("limit", 20))
            )
            ev_res = await session.execute(ev_stmt)
            events = list(ev_res.scalars().all())

            lines = [f"Resultados de búsqueda para '{query}':"]
            if mems:
                lines.append("\nMemorias:")
                for m in mems:
                    lines.append(f"- [{m.predicate}]: {m.value}")
            if events:
                lines.append("\nEventos:")
                for ev in events:
                    lines.append(f"- {ev.title} ({ev.start_time})")

            return {"content": [{"type": "text", "text": "\n".join(lines)}]}

        elif tool_name == "search_documents":
            query = arguments.get("query", "").strip()
            doc_type = arguments.get("doc_type")
            filters = [Document.user_id == user_id, Document.is_deleted.is_(False)]
            if query:
                pattern = f"%{query}%"
                filters.append(Document.title.ilike(pattern) | Document.issuer.ilike(pattern))
            if doc_type:
                filters.append(Document.doc_type == doc_type)

            stmt = select(Document).where(*filters).limit(20)
            res = await session.execute(stmt)
            docs = list(res.scalars().all())

            lines = [f"Encontrados {len(docs)} documentos:"]
            for d in docs:
                lines.append(f"- [{d.id}] {d.title} (Tipo: {d.doc_type}, Emisor: {d.issuer})")

            return {"content": [{"type": "text", "text": "\n".join(lines)}]}

        elif tool_name == "get_event_preparation":
            event_id = arguments.get("event_id")
            prep = await preparation_service.get_event_preparation(session, user_id, event_id)
            if not prep:
                return {"isError": True, "content": [{"type": "text", "text": f"Evento '{event_id}' no encontrado"}]}

            lines = [
                f"Preparación para: {prep.event_title}",
                f"Estado de preparación: {prep.readiness_status}",
                f"Requisitos totales: {prep.total_requirements}",
                f"Verificados: {prep.verified_count} | Candidatos: {prep.candidate_count} | Faltantes: {prep.missing_count} | Vencidos: {prep.expired_count}",
            ]
            for r in prep.requirements:
                lines.append(f"- Requisito: {r.title} [{r.status}]")

            return {"content": [{"type": "text", "text": "\n".join(lines)}]}

        else:
            return {"isError": True, "content": [{"type": "text", "text": f"Herramienta desconocida: '{tool_name}'"}]}

    async def handle_jsonrpc(
        self, session: AsyncSession, user_id: str, request_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        req_id = request_data.get("id")
        method = request_data.get("method")
        params = request_data.get("params") or {}

        if method == "initialize":
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "serverInfo": {
                        "name": "agentagenda-mcp",
                        "version": "1.0.0",
                    },
                    "capabilities": {
                        "tools": {"listChanged": False},
                    },
                },
            }

        elif method == "notifications/initialized":
            return {}

        elif method == "ping":
            return {"jsonrpc": "2.0", "id": req_id, "result": {}}

        elif method == "tools/list":
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "tools": self.get_tool_definitions(),
                },
            }

        elif method == "tools/call":
            tool_name = params.get("name")
            arguments = params.get("arguments") or {}
            result = await self.call_tool(session, user_id, tool_name, arguments)
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": result,
            }

        else:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {
                    "code": -32601,
                    "message": f"Método no encontrado: '{method}'",
                },
            }


mcp_server = MCPServer()
