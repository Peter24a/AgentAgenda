from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import get_explicit_auth, get_db_session
from app.models.auth import AuthContext, DeviceResponse
from app.models.canonical import Device

router = APIRouter(prefix="/v1/devices", tags=["Devices"])

@router.get("")
async def list_devices(auth: AuthContext = Depends(get_explicit_auth), session: AsyncSession = Depends(get_db_session)):
    devices = (await session.execute(select(Device).where(Device.user_id == auth.user_id).order_by(Device.created_at))).scalars().all()
    return {"devices": [DeviceResponse.model_validate(d, from_attributes=True) for d in devices]}
