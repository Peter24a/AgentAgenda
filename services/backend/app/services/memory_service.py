import uuid
from datetime import datetime, timezone
from typing import List, Optional, Tuple

from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.canonical import Memory, MemorySource
from app.models.memory import (
    MemoryCorrectRequest,
    MemoryCreateRequest,
    MemoryForgetRequest,
    MemorySearchRequest,
)
from app.services.context_visibility import memory_source_visibility


class MemoryService:
    async def create_memory(
        self,
        session: AsyncSession,
        user_id: str,
        req: MemoryCreateRequest,
    ) -> Memory:
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        mem_id = f"mem-{uuid.uuid4().hex[:12]}"

        memory = Memory(
            id=mem_id,
            user_id=user_id,
            memory_type=req.memory_type,
            subject_id=req.subject_id,
            predicate=req.predicate,
            value=req.value,
            context_text=req.context_text,
            source_kind=req.source_kind,
            status="active",
            valid_from=req.valid_from,
            valid_to=req.valid_to,
            version=1,
            supersedes_id=None,
            created_at=now,
            updated_at=now,
        )
        session.add(memory)

        if req.source_id:
            src = MemorySource(
                id=f"src-{uuid.uuid4().hex[:12]}",
                memory_id=mem_id,
                source_kind=req.source_kind,
                source_id=req.source_id,
                created_at=now,
            )
            session.add(src)

        await session.commit()
        await session.refresh(memory)
        return memory

    async def search_memories(
        self,
        session: AsyncSession,
        user_id: str,
        req: MemorySearchRequest,
        *,
        for_model: bool = False,
    ) -> Tuple[List[Memory], int]:
        filters = [Memory.user_id == user_id]
        if for_model:
            filters.extend([Memory.status == "active", memory_source_visibility(user_id)])

        if req.status and req.status.lower() != "all":
            filters.append(Memory.status == req.status.lower())

        if req.memory_type and req.memory_type.strip():
            filters.append(Memory.memory_type == req.memory_type.strip())

        if req.predicate and req.predicate.strip():
            filters.append(Memory.predicate == req.predicate.strip())

        if req.query and req.query.strip():
            pattern = f"%{req.query.strip()}%"
            filters.append(
                or_(
                    Memory.predicate.ilike(pattern),
                    Memory.value.ilike(pattern),
                    Memory.context_text.ilike(pattern),
                )
            )

        as_of = req.as_of or (datetime.now(timezone.utc) if for_model else None)
        if as_of:
            if as_of.tzinfo:
                as_of = as_of.astimezone(timezone.utc).replace(tzinfo=None)
            # Filtrar por vigencia temporal
            filters.append(
                or_(
                    Memory.valid_from.is_(None),
                    Memory.valid_from <= as_of,
                )
            )
            filters.append(
                or_(
                    Memory.valid_to.is_(None),
                    Memory.valid_to >= as_of,
                    # Check-ins describe an instant in the past; their point
                    # interval is not an expiry of the historical observation.
                    (Memory.memory_type == "episodic") & (Memory.predicate == "activity_check_in") if for_model else False,
                )
            )

        # Count total
        count_stmt = select(func.count(Memory.id)).where(*filters)
        total_res = await session.execute(count_stmt)
        total = total_res.scalar() or 0

        # Query items
        stmt = (
            select(Memory)
            .where(*filters)
            .order_by(Memory.updated_at.desc())
            .limit(req.limit)
            .offset(req.offset)
        )
        res = await session.execute(stmt)
        memories = list(res.scalars().all())

        return memories, total

    async def get_memory_by_id(
        self,
        session: AsyncSession,
        user_id: str,
        memory_id: str,
    ) -> Optional[Memory]:
        stmt = select(Memory).where(
            Memory.id == memory_id,
            Memory.user_id == user_id,
        )
        res = await session.execute(stmt)
        return res.scalar_one_or_none()

    async def correct_memory(
        self,
        session: AsyncSession,
        user_id: str,
        req: MemoryCorrectRequest,
    ) -> Memory:
        old_mem = await self.get_memory_by_id(session, user_id, req.memory_id)
        if not old_mem:
            raise ValueError(f"Memoria '{req.memory_id}' no encontrada")

        if old_mem.status != "active":
            raise ValueError(f"No se puede corregir una memoria en estado '{old_mem.status}'")

        now = datetime.now(timezone.utc).replace(tzinfo=None)

        # Claim this active revision atomically; two concurrent corrections must
        # not publish two active descendants of the same fact.
        changed = await session.execute(update(Memory).where(
            Memory.id == old_mem.id, Memory.user_id == user_id, Memory.status == "active",
        ).values(status="superseded", updated_at=now))
        if changed.rowcount != 1:
            raise ValueError("La memoria cambió; consulte su versión vigente")

        # 2. Crear nueva versión
        new_id = f"mem-{uuid.uuid4().hex[:12]}"
        new_mem = Memory(
            id=new_id,
            user_id=user_id,
            memory_type=old_mem.memory_type,
            subject_id=old_mem.subject_id,
            predicate=old_mem.predicate,
            value=req.new_value,
            context_text=req.reason or old_mem.context_text,
            source_kind=req.source_kind or old_mem.source_kind,
            status="active",
            valid_from=old_mem.valid_from,
            valid_to=old_mem.valid_to,
            version=old_mem.version + 1,
            supersedes_id=old_mem.id,
            created_at=now,
            updated_at=now,
        )
        session.add(new_mem)

        # Keep prior provenance so a correction cannot discard the source's
        # privacy/revocation boundary by changing source_kind to 'chat'.
        sources = {(source.source_kind, source.source_id) for source in old_mem.sources}
        if req.source_id:
            sources.add((req.source_kind, req.source_id))
        for source_kind, source_id in sources:
            src = MemorySource(
                id=f"src-{uuid.uuid4().hex[:12]}",
                memory_id=new_id,
                source_kind=source_kind,
                source_id=source_id,
                created_at=now,
            )
            session.add(src)

        await session.commit()
        await session.refresh(new_mem)
        return new_mem

    async def forget_memory(
        self,
        session: AsyncSession,
        user_id: str,
        req: MemoryForgetRequest,
    ) -> bool:
        mem = await self.get_memory_by_id(session, user_id, req.memory_id)
        if not mem:
            raise ValueError(f"Memoria '{req.memory_id}' no encontrada")
        if mem.status == "superseded":
            raise ValueError("La memoria tiene una corrección; revoque su versión vigente")

        now = datetime.now(timezone.utc).replace(tzinfo=None)
        mem.status = "revoked"
        mem.updated_at = now
        await session.commit()
        return True


memory_service = MemoryService()
