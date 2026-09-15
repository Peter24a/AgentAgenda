import uuid
from datetime import datetime, timezone
from typing import List, Optional, Tuple

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.canonical import Memory, MemorySource
from app.models.memory import (
    MemoryCorrectRequest,
    MemoryCreateRequest,
    MemoryForgetRequest,
    MemorySearchRequest,
)


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
    ) -> Tuple[List[Memory], int]:
        filters = [Memory.user_id == user_id]

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

        if req.as_of:
            # Filtrar por vigencia temporal
            filters.append(
                or_(
                    Memory.valid_from.is_(None),
                    Memory.valid_from <= req.as_of,
                )
            )
            filters.append(
                or_(
                    Memory.valid_to.is_(None),
                    Memory.valid_to >= req.as_of,
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

        # 1. Marcar memoria anterior como superseded
        old_mem.status = "superseded"
        old_mem.updated_at = now

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

        # 3. Registrar origen
        if req.source_id:
            src = MemorySource(
                id=f"src-{uuid.uuid4().hex[:12]}",
                memory_id=new_id,
                source_kind=req.source_kind,
                source_id=req.source_id,
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

        now = datetime.now(timezone.utc).replace(tzinfo=None)
        mem.status = "revoked"
        mem.updated_at = now
        await session.commit()
        return True


memory_service = MemoryService()
