import json
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.canonical import (
    SyncHead, OperationReceipt, ChangeBatch, Event, Task, Proposal, Document, Memory
)
from app.models.sync import (
    SyncOperation, SyncPushRequest, SyncPushResponse, OperationResult,
    SyncPullResponse, ChangeItem, SyncBootstrapResponse, SyncAckRequest,
    SyncAckResponse, OperationReceiptResponse
)


class SyncService:
    async def _get_or_create_sync_head(self, session: AsyncSession, user_id: str) -> SyncHead:
        """Obtiene o inicializa sync_head."""
        stmt = select(SyncHead).where(SyncHead.user_id == user_id)
        # En PostgreSQL aplicamos row lock
        if session.bind and session.bind.dialect.name == "postgresql":
            stmt = stmt.with_for_update()
            
        res = await session.execute(stmt)
        head = res.scalar_one_or_none()
        if not head:
            head = SyncHead(user_id=user_id, current_seq=0)
            session.add(head)
            await session.flush()
        return head

    async def push_operations(
        self,
        session: AsyncSession,
        user_id: str,
        device_id: Optional[str],
        req: SyncPushRequest,
    ) -> SyncPushResponse:
        results: List[OperationResult] = []
        head = await self._get_or_create_sync_head(session, user_id)
        current_seq = head.current_seq

        for op in req.operations:
            canonical_hash = op.get_canonical_hash()

            # 1. Comprobar recibo previo de idempotencia
            receipt_stmt = select(OperationReceipt).where(
                OperationReceipt.operation_id == op.operation_id,
                OperationReceipt.user_id == user_id
            )
            res_rcpt = await session.execute(receipt_stmt)
            existing_receipt = res_rcpt.scalar_one_or_none()

            if existing_receipt:
                if existing_receipt.canonical_hash == canonical_hash:
                    # Mismo ID y mismo payload: duplicado inocuo
                    prev_result = existing_receipt.result_json or {}
                    results.append(OperationResult(
                        operation_id=op.operation_id,
                        entity_id=op.entity_id,
                        entity_type=op.entity_type,
                        status="duplicate",
                        new_version=prev_result.get("new_version"),
                        error_message="Operación duplicada previamente procesada",
                        current_server_state=prev_result.get("current_server_state")
                    ))
                    continue
                else:
                    # Mismo ID con diferente payload: conflicto
                    results.append(OperationResult(
                        operation_id=op.operation_id,
                        entity_id=op.entity_id,
                        entity_type=op.entity_type,
                        status="conflict",
                        error_message="Conflicto de idempotencia: mismo operation_id con payload diferente"
                    ))
                    continue

            # 2. Despachar la operación según tipo de entidad
            op_result, new_version, change_payload = await self._apply_single_operation(
                session, user_id, op
            )
            results.append(op_result)

            # 3. Si se aplicó con éxito, asignar commit_seq y registrar ChangeBatch + Receipt
            if op_result.status == "applied":
                current_seq += 1
                head.current_seq = current_seq

                change_id = f"cb-{op.operation_id}"
                batch = ChangeBatch(
                    id=change_id,
                    user_id=user_id,
                    commit_seq=current_seq,
                    entity_type=op.entity_type,
                    entity_id=op.entity_id,
                    change_type=op.action,
                    entity_version=new_version,
                    payload_json=change_payload,
                    created_at=datetime.utcnow()
                )
                session.add(batch)

                receipt = OperationReceipt(
                    operation_id=op.operation_id,
                    user_id=user_id,
                    device_id=device_id or req.device_id,
                    operation_epoch=op.operation_epoch,
                    canonical_hash=canonical_hash,
                    status="applied",
                    result_json={
                        "new_version": new_version,
                        "commit_seq": current_seq,
                        "applied_at": datetime.utcnow().isoformat()
                    },
                    created_at=datetime.utcnow()
                )
                session.add(receipt)
                await session.flush()

        await session.commit()
        return SyncPushResponse(
            sync_schema_version=req.sync_schema_version,
            commit_seq=current_seq,
            results=results
        )

    async def _apply_single_operation(
        self,
        session: AsyncSession,
        user_id: str,
        op: SyncOperation
    ) -> Tuple[OperationResult, Optional[int], Optional[Dict[str, Any]]]:
        """Aplica una mutación lógica sobre la entidad correspondiente."""
        if op.entity_type == "event":
            return await self._apply_event_op(session, user_id, op)
        elif op.entity_type == "task":
            return await self._apply_task_op(session, user_id, op)
        elif op.entity_type == "proposal":
            return await self._apply_proposal_op(session, user_id, op)
        elif op.entity_type == "memory":
            return await self._apply_memory_op(session, user_id, op)
        else:
            return (
                OperationResult(
                    operation_id=op.operation_id,
                    entity_id=op.entity_id,
                    entity_type=op.entity_type,
                    status="rejected",
                    error_message=f"Tipo de entidad '{op.entity_type}' aún no soportada en sync"
                ),
                None,
                None
            )

    async def _apply_event_op(
        self, session: AsyncSession, user_id: str, op: SyncOperation
    ) -> Tuple[OperationResult, Optional[int], Optional[Dict[str, Any]]]:
        stmt = select(Event).where(Event.id == op.entity_id, Event.user_id == user_id)
        res = await session.execute(stmt)
        event = res.scalar_one_or_none()

        if op.action == "create":
            if op.base_version != 0:
                return OperationResult(
                    operation_id=op.operation_id,
                    entity_id=op.entity_id,
                    entity_type="event",
                    status="rejected",
                    error_message="Creación exige base_version=0"
                ), None, None

            if event and not event.is_deleted:
                return OperationResult(
                    operation_id=op.operation_id,
                    entity_id=op.entity_id,
                    entity_type="event",
                    status="conflict",
                    new_version=event.version,
                    error_message="El evento ya existe en el servidor",
                    current_server_state={"title": event.title, "version": event.version}
                ), None, None

            start_dt = datetime.fromisoformat(op.payload["start_time"]) if "start_time" in op.payload else datetime.utcnow()
            end_dt = datetime.fromisoformat(op.payload["end_time"]) if op.payload.get("end_time") else None

            if event and event.is_deleted:
                event.title = op.payload.get("title", "Sin título")
                event.description = op.payload.get("description")
                event.start_time = start_dt
                event.end_time = end_dt
                event.timezone = op.payload.get("timezone", "America/Mexico_City")
                event.category = op.payload.get("category", "general")
                event.is_completed = bool(op.payload.get("is_completed", False))
                event.is_deleted = False
                event.version = event.version + 1
            else:
                event = Event(
                    id=op.entity_id,
                    user_id=user_id,
                    title=op.payload.get("title", "Sin título"),
                    description=op.payload.get("description"),
                    start_time=start_dt,
                    end_time=end_dt,
                    timezone=op.payload.get("timezone", "America/Mexico_City"),
                    category=op.payload.get("category", "general"),
                    is_completed=bool(op.payload.get("is_completed", False)),
                    version=1,
                    is_deleted=False
                )
                session.add(event)
            await session.flush()
            return OperationResult(
                operation_id=op.operation_id,
                entity_id=op.entity_id,
                entity_type="event",
                status="applied",
                new_version=event.version
            ), event.version, op.payload

        elif op.action in ("update", "set_status"):
            if not event or event.is_deleted:
                return OperationResult(
                    operation_id=op.operation_id,
                    entity_id=op.entity_id,
                    entity_type="event",
                    status="rejected",
                    error_message="El evento no existe o fue eliminado"
                ), None, None

            if event.version != op.base_version:
                return OperationResult(
                    operation_id=op.operation_id,
                    entity_id=op.entity_id,
                    entity_type="event",
                    status="conflict",
                    new_version=event.version,
                    error_message=f"Conflicto de versión: servidor={event.version}, cliente={op.base_version}",
                    current_server_state={"title": event.title, "version": event.version, "is_completed": event.is_completed}
                ), None, None

            if "title" in op.payload:
                event.title = op.payload["title"]
            if "description" in op.payload:
                event.description = op.payload["description"]
            if "start_time" in op.payload:
                event.start_time = datetime.fromisoformat(op.payload["start_time"])
            if "end_time" in op.payload:
                event.end_time = datetime.fromisoformat(op.payload["end_time"]) if op.payload["end_time"] else None
            if "category" in op.payload:
                event.category = op.payload["category"]
            if "is_completed" in op.payload:
                event.is_completed = bool(op.payload["is_completed"])

            event.version += 1
            await session.flush()
            return OperationResult(
                operation_id=op.operation_id,
                entity_id=op.entity_id,
                entity_type="event",
                status="applied",
                new_version=event.version
            ), event.version, op.payload

        elif op.action == "delete":
            if not event or event.is_deleted:
                return OperationResult(
                    operation_id=op.operation_id,
                    entity_id=op.entity_id,
                    entity_type="event",
                    status="applied",
                    new_version=event.version if event else 1
                ), event.version if event else 1, {"is_deleted": True}

            if event.version != op.base_version:
                return OperationResult(
                    operation_id=op.operation_id,
                    entity_id=op.entity_id,
                    entity_type="event",
                    status="conflict",
                    new_version=event.version,
                    error_message=f"Conflicto de versión en borrado: base={op.base_version}, actual={event.version}"
                ), None, None

            event.is_deleted = True
            event.version += 1
            await session.flush()
            return OperationResult(
                operation_id=op.operation_id,
                entity_id=op.entity_id,
                entity_type="event",
                status="applied",
                new_version=event.version
            ), event.version, {"is_deleted": True}

        return OperationResult(
            operation_id=op.operation_id,
            entity_id=op.entity_id,
            entity_type="event",
            status="rejected",
            error_message=f"Acción '{op.action}' no reconocida"
        ), None, None

    async def _apply_task_op(
        self, session: AsyncSession, user_id: str, op: SyncOperation
    ) -> Tuple[OperationResult, Optional[int], Optional[Dict[str, Any]]]:
        stmt = select(Task).where(Task.id == op.entity_id, Task.user_id == user_id)
        res = await session.execute(stmt)
        task = res.scalar_one_or_none()

        if op.action == "create":
            if op.base_version != 0:
                return OperationResult(
                    operation_id=op.operation_id,
                    entity_id=op.entity_id,
                    entity_type="task",
                    status="rejected",
                    error_message="Creación exige base_version=0"
                ), None, None

            if task and not task.is_deleted:
                return OperationResult(
                    operation_id=op.operation_id,
                    entity_id=op.entity_id,
                    entity_type="task",
                    status="conflict",
                    new_version=task.version,
                    error_message="La tarea ya existe en el servidor"
                ), None, None

            due_dt = datetime.fromisoformat(op.payload["due_date"]) if op.payload.get("due_date") else None
            task = Task(
                id=op.entity_id,
                user_id=user_id,
                title=op.payload.get("title", "Nueva tarea"),
                description=op.payload.get("description"),
                status=op.payload.get("status", "pending"),
                priority=op.payload.get("priority", "medium"),
                due_date=due_dt,
                version=1,
                is_deleted=False
            )
            session.add(task)
            await session.flush()
            return OperationResult(
                operation_id=op.operation_id,
                entity_id=op.entity_id,
                entity_type="task",
                status="applied",
                new_version=task.version
            ), task.version, op.payload

        elif op.action in ("update", "set_status"):
            if not task or task.is_deleted:
                return OperationResult(
                    operation_id=op.operation_id,
                    entity_id=op.entity_id,
                    entity_type="task",
                    status="rejected",
                    error_message="La tarea no existe o fue eliminada"
                ), None, None

            if task.version != op.base_version:
                return OperationResult(
                    operation_id=op.operation_id,
                    entity_id=op.entity_id,
                    entity_type="task",
                    status="conflict",
                    new_version=task.version,
                    error_message=f"Conflicto de versión: servidor={task.version}, cliente={op.base_version}"
                ), None, None

            if "title" in op.payload:
                task.title = op.payload["title"]
            if "description" in op.payload:
                task.description = op.payload["description"]
            if "status" in op.payload:
                task.status = op.payload["status"]
            if "priority" in op.payload:
                task.priority = op.payload["priority"]
            if "due_date" in op.payload:
                task.due_date = datetime.fromisoformat(op.payload["due_date"]) if op.payload["due_date"] else None

            task.version += 1
            await session.flush()
            return OperationResult(
                operation_id=op.operation_id,
                entity_id=op.entity_id,
                entity_type="task",
                status="applied",
                new_version=task.version
            ), task.version, op.payload

        elif op.action == "delete":
            if not task or task.is_deleted:
                return OperationResult(
                    operation_id=op.operation_id,
                    entity_id=op.entity_id,
                    entity_type="task",
                    status="applied",
                    new_version=task.version if task else 1
                ), task.version if task else 1, {"is_deleted": True}

            if task.version != op.base_version:
                return OperationResult(
                    operation_id=op.operation_id,
                    entity_id=op.entity_id,
                    entity_type="task",
                    status="conflict",
                    new_version=task.version,
                    error_message=f"Conflicto de versión en borrado: base={op.base_version}, actual={task.version}"
                ), None, None

            task.is_deleted = True
            task.version += 1
            await session.flush()
            return OperationResult(
                operation_id=op.operation_id,
                entity_id=op.entity_id,
                entity_type="task",
                status="applied",
                new_version=task.version
            ), task.version, {"is_deleted": True}

        return OperationResult(
            operation_id=op.operation_id,
            entity_id=op.entity_id,
            entity_type="task",
            status="rejected",
            error_message=f"Acción '{op.action}' no soportada en tareas"
        ), None, None

    async def _apply_proposal_op(
        self, session: AsyncSession, user_id: str, op: SyncOperation
    ) -> Tuple[OperationResult, Optional[int], Optional[Dict[str, Any]]]:
        stmt = select(Proposal).where(Proposal.id == op.entity_id, Proposal.user_id == user_id)
        res = await session.execute(stmt)
        prop = res.scalar_one_or_none()

        if op.action == "create":
            if prop:
                return OperationResult(
                    operation_id=op.operation_id,
                    entity_id=op.entity_id,
                    entity_type="proposal",
                    status="duplicate",
                    new_version=1
                ), 1, op.payload

            prop = Proposal(
                id=op.entity_id,
                user_id=user_id,
                summary=op.payload.get("summary", "Propuesta"),
                reason=op.payload.get("reason", "Ajuste de agenda"),
                resulting_items=op.payload.get("resulting_items", []),
                status=op.payload.get("status", "pending")
            )
            session.add(prop)
            await session.flush()
            return OperationResult(
                operation_id=op.operation_id,
                entity_id=op.entity_id,
                entity_type="proposal",
                status="applied",
                new_version=1
            ), 1, op.payload

        elif op.action == "set_status":
            if not prop:
                return OperationResult(
                    operation_id=op.operation_id,
                    entity_id=op.entity_id,
                    entity_type="proposal",
                    status="rejected",
                    error_message="Propuesta no encontrada"
                ), None, None

            prop.status = op.payload.get("status", prop.status)
            await session.flush()
            return OperationResult(
                operation_id=op.operation_id,
                entity_id=op.entity_id,
                entity_type="proposal",
                status="applied",
                new_version=1
            ), 1, op.payload

        return OperationResult(
            operation_id=op.operation_id,
            entity_id=op.entity_id,
            entity_type="proposal",
            status="rejected",
            error_message="Acción no soportada en propuestas"
        ), None, None

    async def _apply_memory_op(
        self, session: AsyncSession, user_id: str, op: SyncOperation
    ) -> Tuple[OperationResult, Optional[int], Optional[Dict[str, Any]]]:
        stmt = select(Memory).where(Memory.id == op.entity_id, Memory.user_id == user_id)
        res = await session.execute(stmt)
        mem = res.scalar_one_or_none()

        if op.action == "create":
            if op.base_version != 0:
                return OperationResult(
                    operation_id=op.operation_id,
                    entity_id=op.entity_id,
                    entity_type="memory",
                    status="rejected",
                    error_message="Creación exige base_version=0",
                ), None, None

            if mem and mem.status == "active":
                return OperationResult(
                    operation_id=op.operation_id,
                    entity_id=op.entity_id,
                    entity_type="memory",
                    status="conflict",
                    new_version=mem.version,
                    error_message="La memoria ya existe en el servidor",
                    current_server_state={"predicate": mem.predicate, "value": mem.value, "version": mem.version},
                ), None, None

            now = datetime.utcnow()
            valid_from = datetime.fromisoformat(op.payload["valid_from"]) if op.payload.get("valid_from") else None
            valid_to = datetime.fromisoformat(op.payload["valid_to"]) if op.payload.get("valid_to") else None

            if mem:
                mem.memory_type = op.payload.get("memory_type", "semantic")
                mem.predicate = op.payload.get("predicate", "fact")
                mem.value = op.payload.get("value", "")
                mem.context_text = op.payload.get("context_text")
                mem.source_kind = op.payload.get("source_kind", "manual")
                mem.status = "active"
                mem.valid_from = valid_from
                mem.valid_to = valid_to
                mem.version += 1
                mem.updated_at = now
            else:
                mem = Memory(
                    id=op.entity_id,
                    user_id=user_id,
                    memory_type=op.payload.get("memory_type", "semantic"),
                    predicate=op.payload.get("predicate", "fact"),
                    value=op.payload.get("value", ""),
                    context_text=op.payload.get("context_text"),
                    source_kind=op.payload.get("source_kind", "manual"),
                    status="active",
                    valid_from=valid_from,
                    valid_to=valid_to,
                    version=1,
                    created_at=now,
                    updated_at=now,
                )
                session.add(mem)
            await session.flush()
            return OperationResult(
                operation_id=op.operation_id,
                entity_id=op.entity_id,
                entity_type="memory",
                status="applied",
                new_version=mem.version,
            ), mem.version, op.payload

        elif op.action in ("update", "correct"):
            if not mem:
                return OperationResult(
                    operation_id=op.operation_id,
                    entity_id=op.entity_id,
                    entity_type="memory",
                    status="conflict",
                    error_message="Memoria no encontrada para actualización",
                ), None, None

            if op.base_version != mem.version:
                return OperationResult(
                    operation_id=op.operation_id,
                    entity_id=op.entity_id,
                    entity_type="memory",
                    status="conflict",
                    new_version=mem.version,
                    error_message=f"Conflicto de versión: base={op.base_version}, server={mem.version}",
                    current_server_state={"predicate": mem.predicate, "value": mem.value, "version": mem.version},
                ), None, None

            if "value" in op.payload:
                mem.value = op.payload["value"]
            if "context_text" in op.payload:
                mem.context_text = op.payload["context_text"]
            if "predicate" in op.payload:
                mem.predicate = op.payload["predicate"]
            if "valid_to" in op.payload:
                mem.valid_to = datetime.fromisoformat(op.payload["valid_to"]) if op.payload["valid_to"] else None

            mem.version += 1
            mem.updated_at = datetime.utcnow()
            await session.flush()
            return OperationResult(
                operation_id=op.operation_id,
                entity_id=op.entity_id,
                entity_type="memory",
                status="applied",
                new_version=mem.version,
            ), mem.version, op.payload

        elif op.action in ("delete", "forget", "revoke"):
            if not mem or mem.status == "revoked":
                return OperationResult(
                    operation_id=op.operation_id,
                    entity_id=op.entity_id,
                    entity_type="memory",
                    status="applied",
                    new_version=mem.version if mem else 1,
                ), mem.version if mem else 1, {"status": "revoked"}

            if op.base_version != mem.version:
                return OperationResult(
                    operation_id=op.operation_id,
                    entity_id=op.entity_id,
                    entity_type="memory",
                    status="conflict",
                    new_version=mem.version,
                    error_message=f"Conflicto de versión: base={op.base_version}, server={mem.version}",
                    current_server_state={"status": mem.status, "version": mem.version},
                ), None, None

            mem.status = "revoked"
            mem.version += 1
            mem.updated_at = datetime.utcnow()
            await session.flush()
            return OperationResult(
                operation_id=op.operation_id,
                entity_id=op.entity_id,
                entity_type="memory",
                status="applied",
                new_version=mem.version,
            ), mem.version, {"status": "revoked"}

        return OperationResult(
            operation_id=op.operation_id,
            entity_id=op.entity_id,
            entity_type="memory",
            status="rejected",
            error_message=f"Acción '{op.action}' no soportada en memorias",
        ), None, None

    async def pull_changes(
        self,
        session: AsyncSession,
        user_id: str,
        since_seq: int = 0,
        limit: int = 100
    ) -> SyncPullResponse:
        head = await self._get_or_create_sync_head(session, user_id)
        current_seq = head.current_seq

        stmt = (
            select(ChangeBatch)
            .where(ChangeBatch.user_id == user_id, ChangeBatch.commit_seq > since_seq)
            .order_by(ChangeBatch.commit_seq.asc())
            .limit(limit + 1)
        )
        res = await session.execute(stmt)
        rows = res.scalars().all()

        has_more = len(rows) > limit
        effective_rows = rows[:limit]

        changes = [
            ChangeItem(
                id=r.id,
                commit_seq=r.commit_seq,
                entity_type=r.entity_type,
                entity_id=r.entity_id,
                change_type=r.change_type,
                entity_version=r.entity_version,
                payload=r.payload_json or {},
                created_at=r.created_at
            )
            for r in effective_rows
        ]

        return SyncPullResponse(
            sync_schema_version=1,
            current_seq=current_seq,
            has_more=has_more,
            changes=changes
        )

    async def get_bootstrap(
        self,
        session: AsyncSession,
        user_id: str
    ) -> SyncBootstrapResponse:
        head = await self._get_or_create_sync_head(session, user_id)

        # 1. Eventos activos (no borrados)
        events_res = await session.execute(
            select(Event).where(Event.user_id == user_id, Event.is_deleted == False)
        )
        events = [
            {
                "id": e.id,
                "title": e.title,
                "description": e.description,
                "start_time": e.start_time.isoformat(),
                "end_time": e.end_time.isoformat() if e.end_time else None,
                "timezone": e.timezone,
                "category": e.category,
                "is_completed": e.is_completed,
                "version": e.version,
            }
            for e in events_res.scalars().all()
        ]

        # 2. Tareas activas
        tasks_res = await session.execute(
            select(Task).where(Task.user_id == user_id, Task.is_deleted == False)
        )
        tasks = [
            {
                "id": t.id,
                "title": t.title,
                "description": t.description,
                "status": t.status,
                "priority": t.priority,
                "due_date": t.due_date.isoformat() if t.due_date else None,
                "version": t.version,
            }
            for t in tasks_res.scalars().all()
        ]

        # 3. Propuestas
        prop_res = await session.execute(
            select(Proposal).where(Proposal.user_id == user_id)
        )
        proposals = [
            {
                "id": p.id,
                "summary": p.summary,
                "reason": p.reason,
                "resulting_items": p.resulting_items,
                "status": p.status,
            }
            for p in prop_res.scalars().all()
        ]

        # 4. Memorias activas
        mems_res = await session.execute(
            select(Memory).where(Memory.user_id == user_id, Memory.status == "active")
        )
        memories = [
            {
                "id": m.id,
                "memory_type": m.memory_type,
                "predicate": m.predicate,
                "value": m.value,
                "context_text": m.context_text,
                "source_kind": m.source_kind,
                "status": m.status,
                "valid_from": m.valid_from.isoformat() if m.valid_from else None,
                "valid_to": m.valid_to.isoformat() if m.valid_to else None,
                "version": m.version,
            }
            for m in mems_res.scalars().all()
        ]

        return SyncBootstrapResponse(
            sync_schema_version=1,
            watermark_seq=head.current_seq,
            events=events,
            tasks=tasks,
            proposals=proposals,
            memories=memories,
        )

    async def acknowledge(
        self,
        session: AsyncSession,
        user_id: str,
        ack_req: SyncAckRequest
    ) -> SyncAckResponse:
        # Registra confirmación y estado de réplica
        return SyncAckResponse(
            success=True,
            acknowledged_seq=ack_req.last_applied_seq
        )

    async def get_operation_receipt(
        self,
        session: AsyncSession,
        user_id: str,
        operation_id: str
    ) -> Optional[OperationReceiptResponse]:
        stmt = select(OperationReceipt).where(
            OperationReceipt.operation_id == operation_id,
            OperationReceipt.user_id == user_id
        )
        res = await session.execute(stmt)
        r = res.scalar_one_or_none()
        if not r:
            return None
        return OperationReceiptResponse(
            operation_id=r.operation_id,
            user_id=r.user_id,
            device_id=r.device_id,
            operation_epoch=r.operation_epoch,
            canonical_hash=r.canonical_hash,
            status=r.status,
            result=r.result_json,
            created_at=r.created_at
        )


sync_service = SyncService()
