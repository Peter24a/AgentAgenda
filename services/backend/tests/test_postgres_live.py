import os
import uuid
import pytest
from datetime import datetime
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from app.models.canonical import Base, SyncHead, Event

PG_URL = os.getenv("TEST_PG_URL")

@pytest.mark.skipif(not PG_URL, reason="TEST_PG_URL not provided, skipping live Postgres test")
@pytest.mark.asyncio
async def test_live_postgres_canonical():
    engine = create_async_engine(PG_URL, echo=False)
    
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        
    session_factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    
    test_uid = f"user_{uuid.uuid4().hex[:8]}"
    test_eid = f"evt_{uuid.uuid4().hex[:8]}"
    
    async with session_factory() as session:
        try:
            head = SyncHead(user_id=test_uid, current_seq=100)
            session.add(head)
            
            evt = Event(
                id=test_eid,
                user_id=test_uid,
                title="Evento en Postgres Real",
                start_time=datetime.utcnow(),
                timezone="America/Mexico_City",
                category="work"
            )
            session.add(evt)
            await session.commit()
            
            res_head = await session.execute(select(SyncHead).where(SyncHead.user_id == test_uid))
            stored_head = res_head.scalar_one()
            assert stored_head.current_seq == 100
            
            res_evt = await session.execute(select(Event).where(Event.id == test_eid))
            stored_evt = res_evt.scalar_one()
            assert stored_evt.title == "Evento en Postgres Real"
        finally:
            # Clean up
            await session.rollback()
            clean_head = await session.execute(select(SyncHead).where(SyncHead.user_id == test_uid))
            h = clean_head.scalar_one_or_none()
            if h:
                await session.delete(h)
            clean_evt = await session.execute(select(Event).where(Event.id == test_eid))
            e = clean_evt.scalar_one_or_none()
            if e:
                await session.delete(e)
            await session.commit()
        
    await engine.dispose()
