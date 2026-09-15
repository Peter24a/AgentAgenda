import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from app.config import settings
from app.models.canonical import Base

# Detect engine options based on dialect
engine_kwargs = {"echo": False}
if "sqlite" in settings.database_url:
    from sqlalchemy.pool import StaticPool
    if ":memory:" in settings.database_url:
        engine_kwargs["connect_args"] = {"check_same_thread": False}
        engine_kwargs["poolclass"] = StaticPool
else:
    engine_kwargs["pool_size"] = 10
    engine_kwargs["max_overflow"] = 20
    engine_kwargs["pool_pre_ping"] = True

engine = create_async_engine(settings.database_url, **engine_kwargs)

async_session_factory = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False
)

async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise

@asynccontextmanager
async def get_db_context() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise

async def init_canonical_db():
    """Crea las estructuras canónicas y el directorio de almacenamiento privado si no existen."""
    # Asegurar que el directorio de almacenamiento privado de documentos exista
    os.makedirs(settings.storage_path, exist_ok=True)
    os.makedirs(os.path.join(settings.storage_path, "documents"), exist_ok=True)
    os.makedirs(os.path.join(settings.storage_path, "temp"), exist_ok=True)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
