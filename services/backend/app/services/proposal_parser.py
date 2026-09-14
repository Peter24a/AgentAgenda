import re
import json
import uuid
from datetime import datetime
from typing import Optional, Tuple
from app.models.agenda import AgendaItemModel, ActivityCategory
from app.models.proposal import AgentProposalModel, ProposalStatus

PROPOSAL_REGEX = re.compile(r"```proposal\s*(\{.*?\})\s*```", re.DOTALL)

def extract_proposal_from_text(text: str) -> Tuple[Optional[AgentProposalModel], str]:
    match = PROPOSAL_REGEX.search(text)
    if not match:
        return None, text

    raw_json = match.group(1)
    clean_text = PROPOSAL_REGEX.sub("", text).strip()

    try:
        data = json.loads(raw_json)
        summary = data.get("summary", "Propuesta de ajuste de agenda")
        reason = data.get("reason", "Organización óptima según tu petición")
        raw_items = data.get("items", [])

        resulting_items = []
        for it in raw_items:
            item_id = it.get("id") or f"prop-{uuid.uuid4().hex[:8]}"
            cat_str = it.get("category", "general")
            cat = ActivityCategory(cat_str) if cat_str in [c.value for c in ActivityCategory] else ActivityCategory.general
            start_dt = datetime.fromisoformat(it["start_time"])
            end_dt = datetime.fromisoformat(it["end_time"]) if it.get("end_time") else None

            resulting_items.append(AgendaItemModel(
                id=item_id,
                title=it.get("title", "Actividad"),
                description=it.get("description"),
                start_time=start_dt,
                end_time=end_dt,
                category=cat,
                is_completed=False,
            ))

        proposal = AgentProposalModel(
            id=f"prop-{uuid.uuid4().hex[:10]}",
            summary=summary,
            reason=reason,
            resulting_items=resulting_items,
            status=ProposalStatus.pending,
            created_at=datetime.utcnow()
        )
        return proposal, clean_text
    except Exception as e:
        print(f"[ProposalParser] Error parsing proposal block: {e}")
        return None, text
