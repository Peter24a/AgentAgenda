import json
import re
from datetime import datetime, timedelta
from uuid import UUID

from app.models.agenda import AgendaItemModel
from app.models.chat import ChatMessageModel
from app.services.document_retrieval import MESSAGE_OVERHEAD_TOKENS, PROMPT_TOKEN_BUDGET, estimate_tokens
from app.services.prompt_builder import _agenda_context, build_llm_messages


def week_events(*, title_size=0):
    monday = datetime(2026, 10, 12)
    return [AgendaItemModel(
        id=str(UUID(int=1 + day * 10 + slot)),
        title=("Actividad " + str(slot)) if not title_size else "Título muy largo " * title_size,
        start_time=monday + timedelta(days=day, hours=slot + 8),
        end_time=monday + timedelta(days=day, hours=slot + 8, minutes=30),
    ) for day in range(7) for slot in range(10)]


def test_seventy_weekly_events_have_complete_ids_and_every_day_count():
    events = week_events()
    context = _agenda_context(events, "2026-10-15", ("2026-10-12", "2026-10-18"))
    assert estimate_tokens(context) <= 4500
    assert "mostradas: 70/70; omitidas: 0" in context
    for day in range(12, 19):
        assert f"2026-10-{day}:10" in context
    rows = [line for line in context.splitlines() if line.startswith("[id:")]
    assert len(rows) == 70
    for event, row in zip(events, rows):
        assert f"[id:{json.dumps(event.id)}]" in row
        assert event.start_time.strftime("%Y-%m-%d %H:%M") in row
        assert event.end_time.strftime("%H:%M") in row
    assert "[Fragmento recortado]" not in context


def test_week_budget_preserves_complete_priority_rows_and_warns_when_omitted():
    events = list(reversed(week_events(title_size=1000)))
    context = _agenda_context(events, "2026-10-15", ("2026-10-12", "2026-10-18"))
    assert estimate_tokens(context) <= 4500
    assert "No afirmes que un día o intervalo está libre" in context
    rows = [line for line in context.splitlines() if line.startswith("[id:")]
    assert 0 < len(rows) < 70
    ids = [json.loads(re.match(r"^\[id:(.*?)\]", row).group(1)) for row in rows]
    assert ids == [event.id for event in events[:len(rows)]]
    assert all(row.endswith("(general)") for row in rows)
    for day in range(12, 19):
        assert f"2026-10-{day}:10" in context


def test_daily_counts_include_overnight_events_and_empty_days():
    events = [AgendaItemModel(id="overnight", title="Guardia", start_time=datetime(2026, 10, 12, 23),
                              end_time=datetime(2026, 10, 14, 0))]
    context = _agenda_context(events, "2026-10-15", ("2026-10-12", "2026-10-18"))
    assert "2026-10-12:1" in context and "2026-10-13:1" in context
    assert "2026-10-14:0" in context and "2026-10-18:0" in context
    assert "2026-10-14 00:00" in context


def test_huge_history_sources_and_resolved_dates_fit_whole_prompt_budget():
    events = week_events(title_size=1000)
    dates = [(datetime(2026, 10, 12) + timedelta(days=i)).date().isoformat() for i in range(367)]
    messages = build_llm_messages(
        current_date="2026-10-15", current_time="2026-10-15T12:00:00-06:00",
        events=events, agenda_period=("2026-10-12", "2026-10-18"),
        resolved_schedule={"dates": dates, "start_time": "14:00:00", "end_time": "15:00:00", "operation": "create"},
        user_message="Consulta semanal " * 20000,
        history=[ChatMessageModel(text="Conversación antigua " * 20000, is_user=bool(i % 2),
                                  timestamp=datetime(2026, 1, 1)) for i in range(18)],
        document_context="Evidencia documental " * 20000,
        memory_context="Recuerdo personal " * 20000,
    )
    assert sum(estimate_tokens(message["content"]) + MESSAGE_OVERHEAD_TOKENS for message in messages) <= PROMPT_TOKEN_BUDGET
    system = messages[0]["content"]
    match = re.search(r"FECHAS Y HORAS VERIFICADAS POR EL SERVIDOR: (.+)\n", system)
    verified = json.loads(match.group(1))
    assert verified["total_dates"] == 367
    assert verified["first_date"] == dates[0] and verified["last_date"] == dates[-1]
    assert verified["dates"] == dates[:len(verified["dates"]) ]
    assert verified["dates_omitted"] == 367 - len(verified["dates"]) > 0
    assert "incluidas las fechas omitidas" in system
    for day in range(12, 19):
        assert f"2026-10-{day}:10" in system
    assert messages[-1]["role"] == "user"


def test_long_period_reports_missing_day_counts_without_assuming_availability():
    context = _agenda_context([], "2026-10-15", ("2026-01-01", "2026-12-31"))
    assert estimate_tokens(context) <= 4500
    assert "Faltan los conteos" in context
    assert "No afirmes que un día o intervalo está libre" in context
