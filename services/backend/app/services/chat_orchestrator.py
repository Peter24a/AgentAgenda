import asyncio
import hashlib
import json
import uuid
from zoneinfo import ZoneInfo
from datetime import date, datetime, timedelta, timezone
from typing import AsyncGenerator, Dict, List, Optional, Tuple

from sqlalchemy import select, func, or_, exists, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_context
from app.models.agenda import ActivityCategory, AgendaItemModel
from app.models.canonical import ChatMessage, ChatTurn, Event, Proposal, Memory, Document, DocumentContextGrant, ProposalContext
from app.models.chat import (
    ChatMessageModel,
    ChatMessageResponse,
    ChatTurnResponse,
    CreateTurnRequest,
)
from app.models.proposal import AgentProposalModel, ProposalStatus
from app.services.agenda_service import agenda_service
from app.services.document_retrieval import (
    document_retrieval, format_document_context, source_reference_appendix,
)
from app.services.llm_service import stream_chat_completion
from app.services.prompt_builder import build_llm_messages
from app.services.proposal_parser import extract_proposal_from_text
from app.services.proposal_service import proposal_service
from app.services.context_engine import context_engine
from app.services.file_delivery import file_delivery_response
from app.services.agenda_intent import prepare_agenda_intent, constrain_proposal, remember_agenda_clarification
from app.services.document_consent import handle_document_consent


class ChatOrchestrator:
    def __init__(self):
        self._subscribers: Dict[str, List[asyncio.Queue]] = {}
        self._active_tasks: Dict[str, asyncio.Task] = {}

    @staticmethod
    def _proposal_id(user_id: str, turn_id: str) -> str:
        return "prop-chat-" + hashlib.sha256((user_id + "\0" + turn_id).encode()).hexdigest()[:40]

    @staticmethod
    def _proposal_text(proposal, zone):
        days = ('lunes', 'martes', 'miércoles', 'jueves', 'viernes', 'sábado', 'domingo')
        lines = ['Revisa esta propuesta; sólo se aplicará cuando la confirmes.']
        if proposal.routine:
            routine = proposal.routine
            until = f'hasta {routine.ends_on}' if routine.ends_on else 'sin fecha de fin'
            lines.append(f'Rutina semanal desde {routine.starts_on}, {until}. Se mantendrá automáticamente; estas son las próximas sesiones.')
        for item in proposal.resulting_items:
            start = item.start_time.astimezone(zone) if item.start_time.tzinfo else item.start_time.replace(tzinfo=zone)
            end = item.end_time.astimezone(zone) if item.end_time and item.end_time.tzinfo else item.end_time
            action = 'Cancelar' if item.action == 'delete' else 'Agendar/ajustar'
            lines.append(f'- {action} «{item.title}»: {days[start.weekday()]} {start:%d/%m/%Y}, {start:%H:%M}' + (f'–{end:%H:%M}' if end else '') + '.')
        data = {'summary': proposal.summary, 'reason': proposal.reason,
                'items': [item.model_dump(mode='json') for item in proposal.resulting_items]}
        return '\n'.join(lines) + '\n\n```proposal\n' + json.dumps(data, ensure_ascii=False) + '\n```'

    @staticmethod
    def _proposal_items_signature(items):
        """Match legacy persisted items without inventing IDs or a timezone on replay."""
        result = []
        for raw in items:
            item = raw if isinstance(raw, AgendaItemModel) else AgendaItemModel.model_validate(raw)
            value = item.model_dump(mode="json")
            for field in ("start_time", "end_time"):
                instant = getattr(item, field)
                value[field] = instant.replace(tzinfo=None).isoformat() if instant else None
            result.append(value)
        return result

    async def _stored_turn_proposal(self, session, turn, assistant_content):
        stored = await proposal_service.get_proposal(session, turn.user_id, self._proposal_id(turn.user_id, turn.id))
        if stored is None and assistant_content and turn.completed_at:
            # Older releases used random IDs. Recover only a unique, exact stored
            # proposal from this turn's generation window, never a newly parsed ID.
            parsed, _ = extract_proposal_from_text(assistant_content)
            if parsed:
                candidates = (await session.execute(select(Proposal).where(
                    Proposal.user_id == turn.user_id,
                    Proposal.created_at >= turn.created_at,
                    Proposal.created_at <= turn.completed_at,
                    Proposal.summary == parsed.summary,
                    Proposal.reason == parsed.reason,
                ).limit(11))).scalars().all()
                signature = self._proposal_items_signature(parsed.resulting_items)
                matches = [candidate for candidate in candidates
                           if self._proposal_items_signature(candidate.resulting_items or []) == signature]
                if len(candidates) <= 10 and len(matches) == 1:
                    stored = matches[0]
        if stored is None:
            return None
        metadata = await session.get(ProposalContext, stored.id)
        return AgentProposalModel(
            id=stored.id, summary=stored.summary, reason=stored.reason,
            resulting_items=[AgendaItemModel.model_validate(item) for item in stored.resulting_items or []],
            status=ProposalStatus(stored.status), created_at=stored.created_at,
            routine=metadata.payload.get('routine') if metadata and metadata.user_id == turn.user_id else None,
        )

    async def create_or_get_turn(
        self,
        session: AsyncSession,
        user_id: str,
        device_id: Optional[str],
        req: CreateTurnRequest,
        allow_document_context: bool = True,
        allow_memory_context: bool = True,
        allow_document_consent: bool = True,
    ) -> Tuple[ChatTurnResponse, bool]:
        """Crea un turno de chat durable o recupera el existente si coincide el client_message_id."""
        now = datetime.now(timezone.utc).replace(tzinfo=None)

        # Serialize creation for an owner: concurrent retries must see the first
        # committed turn even on clients which supply an idempotency key.
        if session.bind and session.bind.dialect.name == "postgresql":
            lock = int.from_bytes(hashlib.sha256(("chat-create\0" + user_id).encode()).digest()[:8], "big", signed=True)
            await session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": lock})

        # Idempotencia: si ya existe client_message_id, retornar el turno existente
        if req.client_message_id:
            query = select(ChatTurn).where(
                ChatTurn.client_message_id == req.client_message_id,
                ChatTurn.user_id == user_id,
            )
            res = await session.execute(query)
            existing_turn = res.scalar_one_or_none()
            if existing_turn:
                resp = await self.get_turn_response(session, user_id, existing_turn.id)
                if resp:
                    return resp, False

        turn_id = f"turn-{uuid.uuid4().hex[:12]}"
        turn = ChatTurn(
            id=turn_id,
            user_id=user_id,
            device_id=device_id,
            client_message_id=req.client_message_id,
            status="queued",
            created_at=now,
        )
        user_msg = ChatMessage(
            id=f"msg-{uuid.uuid4().hex[:12]}",
            turn_id=turn_id,
            user_id=user_id,
            role="user",
            content=req.message,
            received_at=now,
            created_at=now,
        )
        session.add(turn)
        await session.flush()
        session.add(user_msg)
        await session.commit()

        # Iniciar generación asíncrona desacoplada en segundo plano
        task = asyncio.create_task(
            self._execute_turn_generation(
                turn_id=turn_id,
                user_id=user_id,
                date_str=req.date,
                iana_timezone=req.timezone or "America/Mexico_City",
                explicit_history=req.history,
                context_recipient=f"device:{device_id}" if device_id else None,
                allow_document_context=allow_document_context,
                allow_memory_context=allow_memory_context,
                allow_document_consent=allow_document_consent,
            )
        )
        self._active_tasks[turn_id] = task

        response = ChatTurnResponse(
            turn_id=turn_id,
            user_id=user_id,
            client_message_id=req.client_message_id,
            status="queued",
            user_message=req.message,
            created_at=now,
        )
        return response, True

    async def _execute_turn_generation(
        self,
        turn_id: str,
        user_id: str,
        date_str: Optional[str],
        iana_timezone: str = "America/Mexico_City",
        explicit_history: Optional[List[ChatMessageModel]] = None,
        context_recipient: Optional[str] = None,
        allow_document_context: bool = True,
        allow_memory_context: bool = True,
        allow_document_consent: bool = True,
    ):
        """Ejecuta la generación en segundo plano sin depender del ciclo de vida del socket HTTP."""
        try:
            local_zone = ZoneInfo(iana_timezone)
        except (KeyError, ValueError):
            local_zone = ZoneInfo('America/Mexico_City')
        target_date = date_str or datetime.now(local_zone).strftime("%Y-%m-%d")

        try:
            # 1. Marcar como running
            async with get_db_context() as session:
                res = await session.execute(
                    select(ChatTurn).where(ChatTurn.id == turn_id)
                )
                turn = res.scalar_one()
                turn.status = "running"
                await session.commit()

            await self._broadcast(turn_id, {"type": "status", "status": "running"})

            # 2. Ensamblar contexto de agenda y conversación reciente
            async with get_db_context() as session:
                user_msg_obj = await session.scalar(select(ChatMessage).where(
                    ChatMessage.turn_id == turn_id, ChatMessage.user_id == user_id,
                    ChatMessage.role == "user",
                ))
                user_message_text = user_msg_obj.content if user_msg_obj else ""
                recipient_device = context_recipient.removeprefix('device:') if context_recipient else None
                file_response = (await file_delivery_response(session, user_id, user_message_text)
                                 if allow_document_context else None)
                document_id = None
                if allow_document_context and file_response is None:
                    consent = await handle_document_consent(
                        session, user_id, recipient_device, user_message_text,
                        can_authorize=allow_document_consent,
                    )
                    file_response = consent.reply
                    user_message_text = consent.retrieval_query or user_message_text
                    document_id = consent.authorized_document_id
                plan = None
                if file_response is None:
                    plan = await prepare_agenda_intent(
                        session, user_id, recipient_device, user_message_text,
                        now=datetime.now(local_zone), view_date=date.fromisoformat(target_date),
                    )
                    file_response = plan.reply
                    user_message_text = plan.effective_message
                    await session.commit()
                events = await agenda_service.list_events(
                    session=session,
                    user_id=user_id,
                    start_date=plan.start_date.isoformat() if plan else target_date,
                    end_date=plan.end_date.isoformat() if plan else target_date,
                    timezone=iana_timezone,
                )
                if plan and plan.operation in ('update', 'delete'):
                    # Include source commitments as well as the destination
                    # dates, e.g. "move today's appointment to next Tuesday".
                    keyed = {event.id: event for event in events}
                    for anchor in {date.fromisoformat(target_date), datetime.now(local_zone).date()}:
                        monday = anchor - timedelta(days=anchor.weekday())
                        source_events = await agenda_service.list_events(
                            session, user_id, start_date=monday.isoformat(),
                            end_date=(monday + timedelta(days=6)).isoformat(), timezone=iana_timezone,
                        )
                        keyed.update((event.id, event) for event in source_events)
                    events = list(keyed.values())
                agenda_models = [
                    AgendaItemModel(
                        id=e.id,
                        title=e.title,
                        description=e.description,
                        start_time=e.start_time.replace(tzinfo=timezone.utc).astimezone(local_zone),
                        end_time=e.end_time.replace(tzinfo=timezone.utc).astimezone(local_zone) if e.end_time else None,
                        category=ActivityCategory(
                            e.category
                            if e.category in [c.value for c in ActivityCategory]
                            else "general"
                        ),
                        is_completed=e.is_completed,
                    )
                    for e in events
                ]

                # Historial reciente: preferir historial durable de DB si no se envió explícito
                history_models: List[ChatMessageModel] = []
                memory_barrier = await session.scalar(select(func.max(Memory.updated_at)).where(
                    Memory.user_id == user_id, Memory.status.in_(("revoked", "superseded")),
                ))
                document_barrier = await session.scalar(select(func.max(Document.updated_at)).where(
                    Document.user_id == user_id, Document.is_deleted.is_(True),
                ))
                grant_barrier = await session.scalar(select(func.max(DocumentContextGrant.revoked_at)).where(
                    DocumentContextGrant.user_id == user_id,
                    DocumentContextGrant.recipient_id == context_recipient,
                ))
                barriers = [v for v in (memory_barrier, document_barrier, grant_barrier) if v]
                history_after = max(barriers) if barriers else None
                has_document_grants = bool(await session.scalar(select(exists().where(
                    DocumentContextGrant.user_id == user_id,
                ))))
                # Client history has no trusted provenance. After a revocation,
                # rebuild from durable messages newer than the invalidation.
                if explicit_history and history_after is None and not has_document_grants and allow_memory_context and allow_document_context:
                    history_models = explicit_history
                else:
                    history_filters = [ChatMessage.user_id == user_id]
                    recipient_device = context_recipient.removeprefix('device:') if context_recipient else None
                    same_recipient = exists(select(ChatTurn.id).where(ChatTurn.id == ChatMessage.turn_id, ChatTurn.device_id == recipient_device))
                    history_filters.append(or_(ChatMessage.role == "user", ChatMessage.turn_id.is_(None), same_recipient))
                    if history_after:
                        history_filters.append(ChatMessage.created_at > history_after)
                    # Prior assistant text can contain data fetched under wider
                    # scopes. Do not reuse it for a reduced-scope client.
                    if not (allow_memory_context and allow_document_context):
                        history_filters.append(ChatMessage.role == "user")
                    msg_res = await session.execute(
                        select(ChatMessage)
                        .where(*history_filters)
                        .order_by(ChatMessage.created_at.desc())
                        .limit(18)
                    )
                    recent_msgs = list(reversed(msg_res.scalars().all()))
                    # Excluir el mensaje actual del turno que acabamos de guardar
                    for m in recent_msgs:
                        if m.turn_id == turn_id and m.role == "user":
                            continue
                        history_models.append(
                            ChatMessageModel(
                                text=m.content,
                                is_user=(m.role == "user"),
                                timestamp=m.created_at,
                            )
                        )

                memory_context = ''
                if allow_memory_context and file_response is None:
                    recall = await context_engine.past_conversation_context(session, user_id, user_message_text, after=history_after, exclude_turn=turn_id)
                    memory_context = await context_engine.memory_context(
                        session, user_id, query=user_message_text,
                        as_of=datetime.now(timezone.utc), token_budget=900 if recall else 1950,
                        recipient_id=context_recipient,
                    )
                    if recall:
                        memory_context += "\n" + recall
                if allow_document_context and file_response is None:
                    passages = await document_retrieval.search(
                        session, user_id, user_message_text, recipient_id=context_recipient,
                        document_id=document_id, limit=10 if document_id else 5,
                    )
                    document_context = format_document_context(passages)
                else:
                    document_context = ""

            llm_messages = build_llm_messages(
                current_date=target_date,
                events=agenda_models,
                user_message=user_message_text,
                history=history_models,
                document_context=document_context,
                memory_context=memory_context,
                current_time=datetime.now(local_zone).isoformat(timespec='minutes'),
                agenda_period=(plan.start_date.isoformat(), plan.end_date.isoformat()) if plan else None,
                resolved_schedule=({
                    'dates': [day.isoformat() for day in plan.dates],
                    'start_time': plan.start_clock.isoformat() if plan.start_clock else None,
                    'end_time': plan.end_clock.isoformat() if plan.end_clock else None,
                    'operation': plan.operation,
                } if plan and plan.is_mutation and not plan.reply else None),
            )

            # 3. Stream de inferencia local
            full_response = ""
            if file_response is not None:
                full_response = file_response
                await self._broadcast(turn_id, {"type": "token", "content": file_response})
            else:
                async for chunk in stream_chat_completion(llm_messages):
                    full_response += chunk
                    # Validate calendar actions before displaying model dates.
                    if not (plan and plan.is_mutation):
                        await self._broadcast(turn_id, {"type": "token", "content": chunk})

            # 4. Extraer posibles propuestas estructuradas
            proposal, clean_text = extract_proposal_from_text(full_response) if file_response is None else (None, full_response)
            if "```proposal" in full_response and (proposal is None or not proposal.resulting_items):
                raise ValueError("No pude preparar un cambio válido. No se modificó la agenda; precisa el cambio e intenta de nuevo.")
            if proposal:
                proposal = proposal.model_copy(update={"id": self._proposal_id(user_id, turn_id)})
                # The model sees local clock times. Attach their zone before
                # persistence so confirming a proposal cannot shift it six hours.
                proposal = proposal.model_copy(update={'resulting_items': [
                    item.model_copy(update={
                        'start_time': item.start_time if item.start_time.tzinfo else item.start_time.replace(tzinfo=local_zone),
                        'end_time': (item.end_time if item.end_time.tzinfo else item.end_time.replace(tzinfo=local_zone)) if item.end_time else None,
                    }) for item in proposal.resulting_items
                ]})
                if plan and plan.is_mutation:
                    proposal, clarification = constrain_proposal(plan, proposal)
                    if clarification:
                        full_response = clarification
                    if proposal and plan.operation == 'delete':
                        actual_by_id = {event.id: event for event in agenda_models}
                        canonical_items = []
                        for item in proposal.resulting_items:
                            actual = actual_by_id.get(item.id)
                            if actual is None or actual.start_time.astimezone(local_zone).date() not in plan.dates:
                                proposal = None
                                full_response = 'No identifiqué una actividad en la fecha que pediste cancelar. Indica su nombre, fecha y hora; no cambié tu agenda.'
                                break
                            actual_clock = actual.start_time.astimezone(local_zone).time().replace(tzinfo=None)
                            if plan.start_clock is not None and actual_clock != plan.start_clock:
                                proposal = None
                                full_response = 'La actividad encontrada tiene otro horario. Indica cuál quieres cancelar; no cambié tu agenda.'
                                break
                            same_title = [event for event in agenda_models
                                          if ' '.join(event.title.casefold().split()) == ' '.join(actual.title.casefold().split())
                                          and event.start_time.astimezone(local_zone).date() == actual.start_time.astimezone(local_zone).date()
                                          and (plan.start_clock is None or event.start_time.astimezone(local_zone).time().replace(tzinfo=None) == plan.start_clock)]
                            if len(same_title) > 1:
                                proposal = None
                                full_response = 'Hay varias actividades con ese nombre en esa fecha. Indica la hora exacta de la que quieres cancelar; no cambié tu agenda.'
                                break
                            # The card must describe the exact existing row
                            # that its ID will cancel, never model-supplied dates.
                            canonical_items.append(actual.model_copy(update={'action': 'delete'}))
                        if proposal and len(plan.dates) > 1:
                            # A finite repeated cancellation covers every
                            # requested date. One model template may not silently
                            # reduce six requested cancellations to just one.
                            titles = {' '.join(item.title.casefold().split()) for item in canonical_items}
                            if len(titles) != 1:
                                proposal = None
                                full_response = 'Hay varias actividades distintas en la cancelación. Indica una actividad y las fechas que quieres cancelar; no cambié tu agenda.'
                            else:
                                selected_title = next(iter(titles))
                                expanded_items = []
                                for requested_date in plan.dates:
                                    matches = [event for event in agenda_models
                                               if ' '.join(event.title.casefold().split()) == selected_title
                                               and event.start_time.astimezone(local_zone).date() == requested_date
                                               and (plan.start_clock is None or event.start_time.astimezone(local_zone).time().replace(tzinfo=None) == plan.start_clock)]
                                    if len(matches) != 1:
                                        proposal = None
                                        full_response = 'No encontré una única actividad con ese nombre en cada una de las fechas solicitadas. Precisa las fechas y horas que quieres cancelar; no preparé una cancelación parcial.'
                                        break
                                    expanded_items.append(matches[0].model_copy(update={'action': 'delete'}))
                                canonical_items = expanded_items
                        if proposal:
                            proposal = proposal.model_copy(update={'resulting_items': canonical_items})
                    if proposal and plan.operation == 'update' and any(
                        item.id not in {event.id for event in agenda_models} for item in proposal.resulting_items
                    ):
                        proposal = None
                        full_response = 'No identifiqué de forma inequívoca la actividad existente. Indica su nombre y fecha para modificarla sin crear otra.'
                    if proposal and plan.recurrence and plan.operation == 'create':
                        template = proposal.resulting_items[0]
                        proposal = proposal_service.prepare_recurring_proposal(user_id, proposal, {
                            'title': template.title, 'description': template.description,
                            'category': template.category.value, 'timezone': local_zone.key,
                            'starts_on': plan.recurrence['starts_on'], 'ends_on': plan.recurrence.get('ends_on'),
                            'iso_weekdays': plan.recurrence['weekdays'],
                            'start_time': plan.start_clock.strftime('%H:%M'), 'end_time': plan.end_clock.strftime('%H:%M'),
                        })
                    if proposal:
                        async with get_db_context() as validation_session:
                            try:
                                proposal = await proposal_service.validate_proposal(validation_session, user_id, proposal)
                            except ValueError as exc:
                                proposal = None
                                full_response = str(exc) + ' ¿Qué horario prefieres?'
                    if proposal:
                        item = proposal.resulting_items[0]
                        action = 'Cancelar' if plan.operation == 'delete' else 'Mover' if plan.operation == 'update' else 'Agendar'
                        label = ('Rutina semanal: ' if proposal.routine else action + ': ') + item.title
                        if len(proposal.resulting_items) == 1:
                            label += f' ({item.start_time:%d/%m/%Y})'
                        proposal = proposal.model_copy(update={'summary': label[:256], 'reason': 'Fechas y horarios verificados para tu solicitud; pendiente de tu confirmación.'})
                        full_response = self._proposal_text(proposal, local_zone)
                    else:
                        async with get_db_context() as clarification_session:
                            await remember_agenda_clarification(
                                clarification_session, user_id, recipient_device, plan, full_response,
                                now=datetime.now(local_zone),
                            )
                            await clarification_session.commit()
                else:
                    proposal = None
                    full_response = 'Para cambiar la agenda, indica la actividad, la fecha y el horario. Te mostraré una propuesta antes de aplicarla.'
            if plan and plan.is_mutation and file_response is None:
                await self._broadcast(turn_id, {"type": "token", "content": full_response})
            # Use only the complete records in the final budgeted source message.
            # This deterministic index remains available after the prompt is gone.
            source_appendix = (
                source_reference_appendix(llm_messages[-2]["content"])
                if allow_document_context and document_context and len(llm_messages) >= 3
                else ""
            )
            if source_appendix:
                full_response += source_appendix
                await self._broadcast(turn_id, {"type": "token", "content": source_appendix})
            now = datetime.now(timezone.utc).replace(tzinfo=None)

            async with get_db_context() as session:
                if proposal:
                    await proposal_service.save_proposal(session, user_id, proposal)
                    await self._broadcast(
                        turn_id,
                        {
                            "type": "proposal",
                            "proposal": proposal.model_dump(mode="json"),
                        },
                    )

                # 5. Persistir mensaje del asistente de forma durable
                asst_msg = ChatMessage(
                    id=f"msg-{uuid.uuid4().hex[:12]}",
                    turn_id=turn_id,
                    user_id=user_id,
                    role="assistant",
                    content=full_response,
                    received_at=now,
                    created_at=now,
                )
                session.add(asst_msg)

                # 6. Finalizar turno
                res_turn = await session.execute(
                    select(ChatTurn).where(ChatTurn.id == turn_id)
                )
                turn = res_turn.scalar_one()
                turn.status = "completed"
                turn.completed_at = now
                await session.commit()

            await self._broadcast(
                turn_id,
                {"type": "done", "turn_id": turn_id, "status": "completed", "assistant_message_id": asst_msg.id},
            )

        except Exception as e:
            async with get_db_context() as session:
                res_err = await session.execute(
                    select(ChatTurn).where(ChatTurn.id == turn_id)
                )
                turn_err = res_err.scalar_one_or_none()
                if turn_err:
                    turn_err.status = "failed"
                    turn_err.error_message = str(e)
                    await session.commit()

            await self._broadcast(
                turn_id,
                {"type": "error", "message": str(e), "turn_id": turn_id},
            )

        finally:
            self._active_tasks.pop(turn_id, None)

    async def _broadcast(self, turn_id: str, event: dict):
        queues = self._subscribers.get(turn_id, [])
        for q in list(queues):
            try:
                q.put_nowait(event)
            except Exception:
                pass

    async def subscribe_stream(
        self, turn_id: str, user_id: str = "default_user"
    ) -> AsyncGenerator[str, None]:
        async for chunk in self.subscribe_turn_sse(turn_id, user_id):
            yield chunk

    async def subscribe_turn_sse(
        self, turn_id: str, user_id: str
    ) -> AsyncGenerator[str, None]:
        """Suscripción SSE a un turno. Si ya terminó, entrega el resultado inmediatamente."""
        # Register before the status query so a fast file response cannot finish
        # between the snapshot and subscription. Ownership is checked before yield.
        q = asyncio.Queue()
        self._subscribers.setdefault(turn_id, []).append(q)
        try:
            # 1. Inspeccionar estado actual en base de datos
            async with get_db_context() as session:
                turn_resp = await self.get_turn_response(session, user_id, turn_id)

            if not turn_resp:
                yield f"data: {json.dumps({'type': 'error', 'message': 'Turno no encontrado'})}\n\n"
                return

            # Si ya está completado, entregar el mensaje completo y cerrar
            if turn_resp.status == "completed":
                yield f"data: {json.dumps({'type': 'status', 'status': 'completed'})}\n\n"
                if turn_resp.assistant_message:
                    yield f"data: {json.dumps({'type': 'token', 'content': turn_resp.assistant_message})}\n\n"
                if turn_resp.proposal:
                    yield f"data: {json.dumps({'type': 'proposal', 'proposal': turn_resp.proposal.model_dump(mode='json')})}\n\n"
                yield f"data: {json.dumps({'type': 'done', 'turn_id': turn_id, 'status': 'completed', 'assistant_message_id': turn_resp.assistant_message_id})}\n\n"
                return

            if turn_resp.status == "failed":
                yield f"data: {json.dumps({'type': 'error', 'message': turn_resp.error_message or 'Generación fallida'})}\n\n"
                return

            # Emitir estado inicial
            yield f"data: {json.dumps({'type': 'status', 'status': turn_resp.status})}\n\n"

            while True:
                try:
                    event = await asyncio.wait_for(q.get(), timeout=60.0)
                    yield f"data: {json.dumps(event)}\n\n"
                    if event.get("type") in ("done", "error"):
                        break
                except asyncio.TimeoutError:
                    # Heartbeat / keepalive
                    yield ": ping\n\n"
        finally:
            if turn_id in self._subscribers and q in self._subscribers[turn_id]:
                self._subscribers[turn_id].remove(q)
                if not self._subscribers[turn_id]:
                    self._subscribers.pop(turn_id, None)

    async def get_turn_response(
        self, session: AsyncSession, user_id: str, turn_id: str
    ) -> Optional[ChatTurnResponse]:
        res = await session.execute(
            select(ChatTurn).where(ChatTurn.id == turn_id, ChatTurn.user_id == user_id)
        )
        turn = res.scalar_one_or_none()
        if not turn:
            return None

        # Obtener mensajes del turno
        msgs_res = await session.execute(
            select(ChatMessage)
            .where(ChatMessage.turn_id == turn_id)
            .order_by(ChatMessage.created_at.asc())
        )
        messages = msgs_res.scalars().all()

        user_content = next((m.content for m in messages if m.role == "user"), "")
        asst_message = next((m for m in messages if m.role == "assistant"), None)
        asst_content = asst_message.content if asst_message else None

        proposal_obj = await self._stored_turn_proposal(session, turn, asst_content)

        return ChatTurnResponse(
            turn_id=turn.id,
            user_id=turn.user_id,
            client_message_id=turn.client_message_id,
            status=turn.status,
            user_message=user_content,
            assistant_message=asst_content,
            assistant_message_id=asst_message.id if asst_message else None,
            proposal=proposal_obj,
            error_message=turn.error_message,
            created_at=turn.created_at,
            completed_at=turn.completed_at,
        )

    async def list_messages(
        self,
        session: AsyncSession,
        user_id: str,
        cursor: Optional[str] = None,
        limit: int = 50,
    ) -> List[ChatMessageResponse]:
        """Devuelve el historial de mensajes paginado de forma durable."""
        query = (
            select(ChatMessage)
            .where(ChatMessage.user_id == user_id)
            .order_by(ChatMessage.created_at.desc())
            .limit(limit)
        )
        if cursor:
            # Si el cursor es un ID de mensaje, buscar su created_at
            cursor_res = await session.execute(
                select(ChatMessage).where(ChatMessage.id == cursor)
            )
            cursor_msg = cursor_res.scalar_one_or_none()
            if cursor_msg:
                query = (
                    select(ChatMessage)
                    .where(
                        ChatMessage.user_id == user_id,
                        ChatMessage.created_at < cursor_msg.created_at,
                    )
                    .order_by(ChatMessage.created_at.desc())
                    .limit(limit)
                )

        res = await session.execute(query)
        msgs = list(reversed(res.scalars().all()))

        return [
            ChatMessageResponse(
                id=m.id,
                turn_id=m.turn_id,
                role=m.role,
                content=m.content,
                client_created_at=m.client_created_at,
                received_at=m.received_at,
                created_at=m.created_at,
            )
            for m in msgs
        ]


chat_orchestrator = ChatOrchestrator()
