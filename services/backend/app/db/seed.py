from datetime import datetime
import aiosqlite
from sqlalchemy import select, func

from app.config import settings
from app.db.database import upsert_event
from app.db.session import async_session_factory
from app.models.agenda import AgendaItemModel, ActivityCategory
from app.models.canonical import Event

async def seed_initial_data_if_empty():
    now = datetime.now()
    today_base = datetime(now.year, now.month, now.day)

    initial_items = [
        AgendaItemModel(
            id="seed-sleep-1",
            title="Dormir & Descanso Profundo",
            description="Ciclo reparador con seguimiento de sueño Pixel",
            start_time=today_base.replace(hour=0, minute=0),
            end_time=today_base.replace(hour=7, minute=0),
            category=ActivityCategory.sleep,
            is_completed=True,
        ),
        AgendaItemModel(
            id="seed-coffee-1",
            title="Café de Especialidad & Desayuno",
            description="Lectura ligera de notas del proyecto y café matutino",
            start_time=today_base.replace(hour=7, minute=30),
            end_time=today_base.replace(hour=8, minute=15),
            category=ActivityCategory.food,
            is_completed=True,
        ),
        AgendaItemModel(
            id="seed-work-1",
            title="Desarrollo Flutter & Agente Local",
            description="Optimización de shaders 120 FPS y conector de inferencia",
            start_time=today_base.replace(hour=9, minute=0),
            end_time=today_base.replace(hour=13, minute=0),
            category=ActivityCategory.work,
            is_completed=False,
        ),
        AgendaItemModel(
            id="seed-food-2",
            title="Almuerzo Saludable",
            description="Comida rica en proteína y desconexión breve de pantallas",
            start_time=today_base.replace(hour=14, minute=0),
            end_time=today_base.replace(hour=15, minute=0),
            category=ActivityCategory.food,
            is_completed=False,
        ),
        AgendaItemModel(
            id="seed-study-1",
            title="Arquitectura de Sistemas & Papers LLM",
            description="Revisión de técnicas de KV Cache y quantized inference",
            start_time=today_base.replace(hour=16, minute=30),
            end_time=today_base.replace(hour=18, minute=0),
            category=ActivityCategory.study,
            is_completed=False,
        ),
        AgendaItemModel(
            id="seed-exercise-1",
            title="Entrenamiento Funcional / Gimnasio",
            description="Fuerza y movilidad aeróbica para desconectar",
            start_time=today_base.replace(hour=18, minute=30),
            end_time=today_base.replace(hour=19, minute=45),
            category=ActivityCategory.exercise,
            is_completed=False,
        ),
        AgendaItemModel(
            id="seed-leisure-1",
            title="Tiempo Libre & Desconexión",
            description="Cena relajada, música ambiental y descanso",
            start_time=today_base.replace(hour=20, minute=30),
            end_time=today_base.replace(hour=22, minute=30),
            category=ActivityCategory.leisure,
            is_completed=False,
        ),
    ]

    # 1. Seed legacy SQLite if empty
    try:
        async with aiosqlite.connect(settings.db_path) as db:
            cursor = await db.execute("SELECT COUNT(*) FROM events")
            row = await cursor.fetchone()
            if not row or row[0] == 0:
                for item in initial_items:
                    await upsert_event(item)
    except Exception:
        pass

    # 2. Seed canonical database if empty
    try:
        async with async_session_factory() as session:
            stmt = select(func.count()).select_from(Event)
            res = await session.execute(stmt)
            count = res.scalar() or 0
            if count == 0:
                for item in initial_items:
                    event = Event(
                        id=item.id,
                        user_id="default_user",
                        title=item.title,
                        description=item.description,
                        start_time=item.start_time,
                        end_time=item.end_time,
                        timezone=settings.default_timezone,
                        category=item.category.value,
                        is_completed=item.is_completed,
                        version=1,
                        is_deleted=False,
                    )
                    session.add(event)
                await session.commit()
    except Exception:
        pass
