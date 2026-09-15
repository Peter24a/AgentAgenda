import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from app.config import settings
from app.db.database import (
    get_events_for_date,
    get_proposal,
    init_db,
    process_pending_proposal,
    save_proposal,
)
from app.models.agenda import AgendaItemModel
from app.models.proposal import AgentProposalModel, ProposalStatus


class ProposalProcessingTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self._original_db_path = settings.db_path
        self._temp_dir = tempfile.TemporaryDirectory()
        settings.db_path = str(Path(self._temp_dir.name) / "test.db")
        await init_db()

    async def asyncTearDown(self):
        settings.db_path = self._original_db_path
        self._temp_dir.cleanup()

    async def _save_sample_proposal(self) -> AgentProposalModel:
        start = datetime(2026, 9, 14, 10, 0)
        proposal = AgentProposalModel(
            id="proposal-1",
            summary="Agregar bloque de trabajo",
            reason="Reservar tiempo de enfoque",
            resulting_items=[
                AgendaItemModel(
                    id="event-1",
                    title="Trabajo profundo",
                    start_time=start,
                    end_time=start + timedelta(hours=1),
                )
            ],
        )
        await save_proposal(proposal)
        return proposal

    async def test_accept_applies_items_and_status_together(self):
        await self._save_sample_proposal()

        proposal, processed = await process_pending_proposal(
            "proposal-1", ProposalStatus.accepted
        )

        self.assertTrue(processed)
        self.assertEqual(proposal.status, ProposalStatus.accepted)
        stored = await get_proposal("proposal-1")
        self.assertEqual(stored.status, ProposalStatus.accepted)
        events = await get_events_for_date("2026-09-14")
        self.assertEqual([event.id for event in events], ["event-1"])

    async def test_processed_proposal_cannot_change_status(self):
        await self._save_sample_proposal()
        await process_pending_proposal("proposal-1", ProposalStatus.accepted)

        proposal, processed = await process_pending_proposal(
            "proposal-1", ProposalStatus.rejected
        )

        self.assertFalse(processed)
        self.assertEqual(proposal.status, ProposalStatus.accepted)
        stored = await get_proposal("proposal-1")
        self.assertEqual(stored.status, ProposalStatus.accepted)

    async def test_reject_does_not_apply_items(self):
        await self._save_sample_proposal()

        proposal, processed = await process_pending_proposal(
            "proposal-1", ProposalStatus.rejected
        )

        self.assertTrue(processed)
        self.assertEqual(proposal.status, ProposalStatus.rejected)
        self.assertEqual(await get_events_for_date("2026-09-14"), [])


if __name__ == "__main__":
    unittest.main()
