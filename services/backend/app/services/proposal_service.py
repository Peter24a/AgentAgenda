import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.canonical import Proposal, Event, ChangeBatch, SyncHead
from app.models.proposal import AgentProposalModel, ProposalStatus, ProposalActionResponse
from app.models.agenda import AgendaItemModel, ActivityCategory


class ProposalService:
    async def get_proposal(
        self, session: AsyncSession, user_id: str, proposal_id: str
    ) -> Optional[Proposal]:
        stmt = select(Proposal).where(
            Proposal.id == proposal_id, Proposal.user_id == user_id
        )
        res = await session.execute(stmt)
        return res.scalar_one_or_none()

    async def get_latest_pending(
        self, session: AsyncSession, user_id: str
    ) -> Optional[Proposal]:
        stmt = (
            select(Proposal)
            .where(Proposal.user_id == user_id, Proposal.status == "pending")
            .order_by(Proposal.created_at.desc())
            .limit(1)
        )
        res = await session.execute(stmt)
        return res.scalar_one_or_none()

    async def save_proposal(
        self, session: AsyncSession, user_id: str, model: AgentProposalModel
    ) -> Proposal:
        stmt = select(Proposal).where(Proposal.id == model.id, Proposal.user_id == user_id)
        res = await session.execute(stmt)
        prop = res.scalar_one_or_none()

        items_data = [item.model_dump(mode="json") for item in model.resulting_items]

        if prop:
            prop.summary = model.summary
            prop.reason = model.reason
            prop.resulting_items = items_data
            prop.status = model.status.value
            prop.updated_at = datetime.utcnow()
        else:
            prop = Proposal(
                id=model.id,
                user_id=user_id,
                summary=model.summary,
                reason=model.reason,
                resulting_items=items_data,
                status=model.status.value,
                created_at=model.created_at or datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )
            session.add(prop)

        await session.commit()
        await session.refresh(prop)
        return prop

    async def confirm_proposal(
        self, session: AsyncSession, user_id: str, proposal_id: str
    ) -> ProposalActionResponse:
        """Acepta una propuesta aplicando atómicamente todos los eventos e incrementando sync_head."""
        stmt = select(Proposal).where(
            Proposal.id == proposal_id, Proposal.user_id == user_id
        )
        if session.bind and session.bind.dialect.name == "postgresql":
            stmt = stmt.with_for_update()

        res = await session.execute(stmt)
        prop = res.scalar_one_or_none()

        if not prop:
            return ProposalActionResponse(
                success=False,
                proposal_id=proposal_id,
                status=ProposalStatus.rejected,
                message="Propuesta no encontrada",
            )

        if prop.status != "pending":
            return ProposalActionResponse(
                success=False,
                proposal_id=proposal_id,
                status=ProposalStatus(prop.status),
                message=f"La propuesta ya fue procesada anteriormente ({prop.status})",
            )

        # 1. Obtener sync_head
        head_stmt = select(SyncHead).where(SyncHead.user_id == user_id)
        if session.bind and session.bind.dialect.name == "postgresql":
            head_stmt = head_stmt.with_for_update()
        res_head = await session.execute(head_stmt)
        head = res_head.scalar_one_or_none()
        if not head:
            head = SyncHead(user_id=user_id, current_seq=0)
            session.add(head)
            await session.flush()

        current_seq = head.current_seq
        items = prop.resulting_items or []

        # 2. Aplicar cada item en la agenda
        for it in items:
            item_id = it.get("id") or f"evt-{uuid.uuid4().hex[:8]}"
            start_dt = datetime.fromisoformat(it["start_time"]) if "start_time" in it else datetime.utcnow()
            end_dt = datetime.fromisoformat(it["end_time"]) if it.get("end_time") else None
            if start_dt.tzinfo:
                start_dt = start_dt.astimezone(timezone.utc).replace(tzinfo=None)
            if end_dt and end_dt.tzinfo:
                end_dt = end_dt.astimezone(timezone.utc).replace(tzinfo=None)
            cat = it.get("category", "general")

            evt_stmt = select(Event).where(Event.id == item_id, Event.user_id == user_id)
            res_evt = await session.execute(evt_stmt)
            evt = res_evt.scalar_one_or_none()

            if evt:
                evt.title = it.get("title", evt.title)
                evt.description = it.get("description", evt.description)
                evt.start_time = start_dt
                evt.end_time = end_dt
                evt.category = cat
                evt.is_completed = bool(it.get("is_completed", False))
                evt.is_deleted = False
                evt.version += 1
                evt.updated_at = datetime.utcnow()
                new_ver = evt.version
            else:
                evt = Event(
                    id=item_id,
                    user_id=user_id,
                    title=it.get("title", "Nueva actividad"),
                    description=it.get("description"),
                    start_time=start_dt,
                    end_time=end_dt,
                    timezone=it.get("timezone", "America/Mexico_City"),
                    category=cat,
                    is_completed=bool(it.get("is_completed", False)),
                    version=1,
                    is_deleted=False,
                    created_at=datetime.utcnow(),
                    updated_at=datetime.utcnow(),
                )
                session.add(evt)
                new_ver = 1

            # 3. Registrar lote de sincronización
            current_seq += 1
            head.current_seq = current_seq
            change = ChangeBatch(
                id=f"cb-prop-{uuid.uuid4().hex[:8]}",
                user_id=user_id,
                commit_seq=current_seq,
                entity_type="event",
                entity_id=item_id,
                change_type="update" if evt else "create",
                entity_version=new_ver,
                payload_json=it,
                created_at=datetime.utcnow(),
            )
            session.add(change)

        # 4. Marcar propuesta como aceptada
        prop.status = "accepted"
        prop.updated_at = datetime.utcnow()

        await session.commit()

        return ProposalActionResponse(
            success=True,
            proposal_id=proposal_id,
            status=ProposalStatus.accepted,
            message="Propuesta aceptada e integrada en tu agenda con éxito.",
        )

    async def reject_proposal(
        self, session: AsyncSession, user_id: str, proposal_id: str
    ) -> ProposalActionResponse:
        stmt = select(Proposal).where(
            Proposal.id == proposal_id, Proposal.user_id == user_id
        )
        res = await session.execute(stmt)
        prop = res.scalar_one_or_none()

        if not prop:
            return ProposalActionResponse(
                success=False,
                proposal_id=proposal_id,
                status=ProposalStatus.rejected,
                message="Propuesta no encontrada",
            )

        prop.status = "rejected"
        prop.updated_at = datetime.utcnow()
        await session.commit()

        return ProposalActionResponse(
            success=True,
            proposal_id=proposal_id,
            status=ProposalStatus.rejected,
            message="Propuesta descartada.",
        )


proposal_service = ProposalService()
