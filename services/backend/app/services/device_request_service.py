import uuid
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Tuple

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.canonical import DeviceObservation, DeviceRequest
from app.models.device_request import (
    CreateDeviceRequest,
    DeviceObservationPayload,
)


class DeviceRequestService:
    async def create_request(
        self,
        session: AsyncSession,
        user_id: str,
        target_device_id: str,
        req: CreateDeviceRequest,
    ) -> DeviceRequest:
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        expires_at = now + timedelta(seconds=req.ttl_seconds)

        dreq = DeviceRequest(
            id=f"dreq-{uuid.uuid4().hex[:12]}",
            user_id=user_id,
            device_id=req.device_id or target_device_id,
            capability=req.capability,
            purpose=req.purpose,
            ttl_seconds=req.ttl_seconds,
            status="pending",
            created_at=now,
            expires_at=expires_at,
        )
        session.add(dreq)
        await session.commit()
        await session.refresh(dreq)
        return dreq

    async def get_pending_requests(
        self,
        session: AsyncSession,
        user_id: str,
        device_id: Optional[str] = None,
    ) -> List[DeviceRequest]:
        now = datetime.now(timezone.utc).replace(tzinfo=None)

        # 1. Expirar automáticamente solicitudes vencidas
        exp_stmt = (
            update(DeviceRequest)
            .where(
                DeviceRequest.user_id == user_id,
                DeviceRequest.status == "pending",
                DeviceRequest.expires_at < now,
            )
            .values(status="expired")
        )
        await session.execute(exp_stmt)
        await session.commit()

        # 2. Consultar solicitudes vigentes
        filters = [
            DeviceRequest.user_id == user_id,
            DeviceRequest.status == "pending",
            DeviceRequest.expires_at >= now,
        ]
        if device_id:
            filters.append(DeviceRequest.device_id == device_id)

        stmt = select(DeviceRequest).where(*filters).order_by(DeviceRequest.created_at.asc())
        res = await session.execute(stmt)
        return list(res.scalars().all())

    async def get_request_by_id(
        self,
        session: AsyncSession,
        user_id: str,
        request_id: str,
    ) -> Optional[DeviceRequest]:
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        res = await session.execute(
            select(DeviceRequest).where(
                DeviceRequest.id == request_id,
                DeviceRequest.user_id == user_id,
            )
        )
        dreq = res.scalar_one_or_none()
        if dreq and dreq.status == "pending" and dreq.expires_at < now:
            dreq.status = "expired"
            await session.commit()
        return dreq

    async def record_observation(
        self,
        session: AsyncSession,
        user_id: str,
        device_id: str,
        request_id: str,
        obs: DeviceObservationPayload,
    ) -> Tuple[DeviceRequest, Optional[DeviceObservation]]:
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        dreq = await self.get_request_by_id(session, user_id, request_id)
        if not dreq:
            raise ValueError(f"Solicitud '{request_id}' no encontrada")

        if dreq.status == "expired" or dreq.expires_at < now:
            dreq.status = "expired"
            await session.commit()
            raise ValueError("La solicitud ha expirado (TTL superado)")

        if dreq.status != "pending":
            raise ValueError(f"La solicitud ya se encuentra en estado '{dreq.status}'")

        if obs.status == "denied":
            dreq.status = "denied"
            await session.commit()
            return dreq, None
        elif obs.status == "unavailable":
            dreq.status = "unavailable"
            await session.commit()
            return dreq, None

        # Estado completed: registrar observación
        dreq.status = "completed"
        observation = DeviceObservation(
            id=f"obs-{uuid.uuid4().hex[:12]}",
            user_id=user_id,
            device_id=device_id,
            request_id=request_id,
            capability=dreq.capability,
            payload_json=obs.payload,
            observed_at=obs.observed_at or now,
            received_at=now,
        )
        session.add(observation)
        await session.commit()
        await session.refresh(observation)
        return dreq, observation


device_request_service = DeviceRequestService()
