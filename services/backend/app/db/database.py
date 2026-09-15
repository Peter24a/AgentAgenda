import aiosqlite
import json
from datetime import datetime
from typing import List, Optional
from app.config import settings
from app.models.agenda import AgendaItemModel, ActivityCategory
from app.models.proposal import AgentProposalModel, ProposalStatus


def _proposal_from_row(row: aiosqlite.Row) -> AgentProposalModel:
    items_raw = json.loads(row["resulting_items"])
    return AgentProposalModel(
        id=row["id"],
        summary=row["summary"],
        reason=row["reason"],
        resulting_items=[AgendaItemModel.model_validate(x) for x in items_raw],
        status=ProposalStatus(row["status"]),
        created_at=datetime.fromisoformat(row["created_at"]),
    )

async def get_db():
    async with aiosqlite.connect(settings.db_path) as db:
        db.row_factory = aiosqlite.Row
        yield db

async def init_db():
    async with aiosqlite.connect(settings.db_path) as db:
        await db.execute("""
        CREATE TABLE IF NOT EXISTS events (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            description TEXT,
            start_time TEXT NOT NULL,
            end_time TEXT,
            category TEXT NOT NULL,
            is_completed INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL
        );
        """)
        await db.execute("""
        CREATE TABLE IF NOT EXISTS proposals (
            id TEXT PRIMARY KEY,
            summary TEXT NOT NULL,
            reason TEXT NOT NULL,
            resulting_items TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            created_at TEXT NOT NULL
        );
        """)
        await db.execute("""
        CREATE TABLE IF NOT EXISTS chat_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            text TEXT NOT NULL,
            is_user INTEGER NOT NULL,
            timestamp TEXT NOT NULL
        );
        """)
        await db.commit()

async def get_events_for_date(date_str: str) -> List[AgendaItemModel]:
    async with aiosqlite.connect(settings.db_path) as db:
        db.row_factory = aiosqlite.Row
        # Match events where start_time starts with date_str (YYYY-MM-DD)
        query = "SELECT * FROM events WHERE start_time LIKE ? ORDER BY start_time ASC"
        cursor = await db.execute(query, (f"{date_str}%",))
        rows = await cursor.fetchall()
        items = []
        for r in rows:
            items.append(AgendaItemModel(
                id=r["id"],
                title=r["title"],
                description=r["description"],
                start_time=datetime.fromisoformat(r["start_time"]),
                end_time=datetime.fromisoformat(r["end_time"]) if r["end_time"] else None,
                category=ActivityCategory(r["category"]) if r["category"] in [c.value for c in ActivityCategory] else ActivityCategory.general,
                is_completed=bool(r["is_completed"])
            ))
        return items

async def upsert_event(item: AgendaItemModel):
    async with aiosqlite.connect(settings.db_path) as db:
        await db.execute("""
        INSERT INTO events (id, title, description, start_time, end_time, category, is_completed, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            title=excluded.title,
            description=excluded.description,
            start_time=excluded.start_time,
            end_time=excluded.end_time,
            category=excluded.category,
            is_completed=excluded.is_completed;
        """, (
            item.id,
            item.title,
            item.description,
            item.start_time.isoformat(),
            item.end_time.isoformat() if item.end_time else None,
            item.category.value,
            1 if item.is_completed else 0,
            datetime.utcnow().isoformat()
        ))
        await db.commit()

async def get_event(event_id: str) -> Optional[AgendaItemModel]:
    async with aiosqlite.connect(settings.db_path) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM events WHERE id = ?", (event_id,))
        r = await cursor.fetchone()
        if not r:
            return None
        return AgendaItemModel(
            id=r["id"],
            title=r["title"],
            description=r["description"],
            start_time=datetime.fromisoformat(r["start_time"]),
            end_time=datetime.fromisoformat(r["end_time"]) if r["end_time"] else None,
            category=ActivityCategory(r["category"]) if r["category"] in [c.value for c in ActivityCategory] else ActivityCategory.general,
            is_completed=bool(r["is_completed"])
        )

async def delete_event(event_id: str) -> bool:
    async with aiosqlite.connect(settings.db_path) as db:
        cursor = await db.execute("DELETE FROM events WHERE id = ?", (event_id,))
        await db.commit()
        return cursor.rowcount > 0

async def toggle_event(event_id: str) -> Optional[AgendaItemModel]:
    async with aiosqlite.connect(settings.db_path) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM events WHERE id = ?", (event_id,))
        r = await cursor.fetchone()
        if not r:
            return None
        new_status = 0 if r["is_completed"] else 1
        await db.execute("UPDATE events SET is_completed = ? WHERE id = ?", (new_status, event_id))
        await db.commit()
        return AgendaItemModel(
            id=r["id"],
            title=r["title"],
            description=r["description"],
            start_time=datetime.fromisoformat(r["start_time"]),
            end_time=datetime.fromisoformat(r["end_time"]) if r["end_time"] else None,
            category=ActivityCategory(r["category"]) if r["category"] in [c.value for c in ActivityCategory] else ActivityCategory.general,
            is_completed=bool(new_status)
        )

async def save_proposal(proposal: AgentProposalModel):
    async with aiosqlite.connect(settings.db_path) as db:
        items_json = json.dumps([item.model_dump(mode="json") for item in proposal.resulting_items])
        await db.execute("""
        INSERT INTO proposals (id, summary, reason, resulting_items, status, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            summary=excluded.summary,
            reason=excluded.reason,
            resulting_items=excluded.resulting_items,
            status=excluded.status;
        """, (
            proposal.id,
            proposal.summary,
            proposal.reason,
            items_json,
            proposal.status.value,
            proposal.created_at.isoformat()
        ))
        await db.commit()

async def get_proposal(proposal_id: str) -> Optional[AgentProposalModel]:
    async with aiosqlite.connect(settings.db_path) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM proposals WHERE id = ?", (proposal_id,))
        row = await cursor.fetchone()
        if not row:
            return None
        return _proposal_from_row(row)

async def get_latest_pending_proposal() -> Optional[AgentProposalModel]:
    async with aiosqlite.connect(settings.db_path) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM proposals WHERE status = 'pending' ORDER BY created_at DESC LIMIT 1")
        row = await cursor.fetchone()
        if not row:
            return None
        return _proposal_from_row(row)


async def process_pending_proposal(
    proposal_id: str,
    target_status: ProposalStatus,
) -> tuple[Optional[AgentProposalModel], bool]:
    """Atomically accept or reject a proposal that is still pending.

    Returns the current proposal and whether this call performed the transition.
    Accepting also writes every resulting event in the same transaction.
    """
    if target_status not in (ProposalStatus.accepted, ProposalStatus.rejected):
        raise ValueError("target_status must be accepted or rejected")

    async with aiosqlite.connect(settings.db_path) as db:
        db.row_factory = aiosqlite.Row
        try:
            await db.execute("BEGIN IMMEDIATE")
            cursor = await db.execute(
                "SELECT * FROM proposals WHERE id = ?", (proposal_id,)
            )
            row = await cursor.fetchone()
            if not row:
                await db.rollback()
                return None, False

            proposal = _proposal_from_row(row)
            if proposal.status != ProposalStatus.pending:
                await db.rollback()
                return proposal, False

            if target_status == ProposalStatus.accepted:
                for item in proposal.resulting_items:
                    await db.execute(
                        """
                        INSERT INTO events (
                            id, title, description, start_time, end_time,
                            category, is_completed, created_at
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(id) DO UPDATE SET
                            title=excluded.title,
                            description=excluded.description,
                            start_time=excluded.start_time,
                            end_time=excluded.end_time,
                            category=excluded.category,
                            is_completed=excluded.is_completed;
                        """,
                        (
                            item.id,
                            item.title,
                            item.description,
                            item.start_time.isoformat(),
                            item.end_time.isoformat() if item.end_time else None,
                            item.category.value,
                            1 if item.is_completed else 0,
                            datetime.utcnow().isoformat(),
                        ),
                    )

            await db.execute(
                "UPDATE proposals SET status = ? WHERE id = ?",
                (target_status.value, proposal_id),
            )
            await db.commit()
            return proposal.model_copy(update={"status": target_status}), True
        except Exception:
            await db.rollback()
            raise
