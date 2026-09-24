"""Single durable extraction worker, started by Compose on the storage host."""
import asyncio
from datetime import datetime, timedelta, timezone
import json
import logging
from pathlib import Path

from sqlalchemy import text, update
from app.config import settings
from app.db.session import engine, get_db_context
from app.models.canonical import Job
from app.worker.worker import background_worker
from app.services.weekly_routines import maintain_weekly_routines

logger = logging.getLogger(__name__)
LEASE_TIMEOUT = timedelta(minutes=30)


async def recover_expired_jobs(session, *, now=None):
    """Requeue abandoned claims; recent claims belong to active runner/API work."""
    now = (now or datetime.now(timezone.utc)).replace(tzinfo=None)
    result = await session.execute(update(Job).where(
        Job.status == 'processing',
        Job.updated_at < now - LEASE_TIMEOUT,
    ).values(status='pending', updated_at=now))
    await session.commit()
    return result.rowcount


async def heartbeat():
    path = Path(settings.storage_path) / 'worker-heartbeat.json'
    while True:
        temp = path.with_suffix('.tmp')
        temp.write_text(json.dumps({'timestamp': datetime.now(timezone.utc).isoformat()}))
        temp.replace(path)
        await asyncio.sleep(5)


async def routine_maintenance():
    while True:
        try:
            await maintain_weekly_routines()
        except Exception:
            logger.exception("Weekly routine maintenance failed")
        await asyncio.sleep(300)


async def run():
    # Session-level advisory lock permits exactly one worker runner on PostgreSQL.
    async with engine.connect() as leader:
        if engine.dialect.name == 'postgresql':
            acquired = (await leader.execute(text('SELECT pg_try_advisory_lock(437610241)'))).scalar()
            if not acquired:
                raise RuntimeError('Another worker runner is already active')
        pulse = asyncio.create_task(heartbeat())
        routines = asyncio.create_task(routine_maintenance())
        try:
            while True:
                processed = 0
                try:
                    async with get_db_context() as session:
                        # Recheck expired leases after restart, not just at startup.
                        await recover_expired_jobs(session)
                        processed, _, _, _ = await background_worker.process_pending_jobs(session, limit=2)
                except Exception:
                    logger.exception('Worker iteration failed')
                await asyncio.sleep(0.1 if processed else 2)
        finally:
            pulse.cancel()
            routines.cancel()
            await asyncio.gather(pulse, routines, return_exceptions=True)
            (Path(settings.storage_path)/'worker-heartbeat.json').unlink(missing_ok=True)
            if engine.dialect.name == 'postgresql':
                await leader.execute(text('SELECT pg_advisory_unlock(437610241)'))


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run())
