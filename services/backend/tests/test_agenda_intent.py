from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import select

from app.models.agenda import AgendaItemModel
from app.models.canonical import ChatPendingAction
from app.models.proposal import AgentProposalModel
from app.services.agenda_intent import _plan, constrain_proposal, prepare_agenda_intent

ZONE = ZoneInfo('America/Mexico_City')
NOW = datetime(2026, 10, 15, 12, tzinfo=ZONE)  # Thursday; the model used to return Saturday 24.


@pytest.mark.parametrize(('expression','expected'), [
    ('hoy','2026-10-15'), ('mañana','2026-10-16'), ('pasado mañana','2026-10-17'),
    ('el viernes de esta semana','2026-10-16'),
    ('el viernes de la próxima semana','2026-10-23'),
    ('el viernes de la semana siguiente','2026-10-23'),
    ('el lunes de la semana que viene','2026-10-19'),
    ('el próximo viernes','2026-10-16'),
    ('el próximo jueves','2026-10-22'),
    ('2026-10-23','2026-10-23'), ('23/10/2026','2026-10-23'),
    ('23 de octubre de 2026','2026-10-23'),
])
def test_calendar_dates_are_computed_not_guessed(expression, expected):
    plan = _plan(f'Agenda llamada {expression} a las 15:00 durante una hora', NOW, date(2030,1,1))
    assert plan.reply is None
    assert plan.dates == [date.fromisoformat(expected)]
    assert plan.start_clock == time(15)
    assert plan.end_clock == time(16)


def test_calendar_crosses_year_boundary():
    plan = _plan('Agenda llamada el viernes de la próxima semana de 15:00 a 16:00', datetime(2026,12,31,12,tzinfo=ZONE), None)
    assert plan.dates == [date(2027,1,8)]
    assert plan.reply is None


@pytest.mark.parametrize(('message','missing'), [
    ('Agenda llamada', {'date','clock','duration'}),
    ('Agenda llamada mañana a las 3', {'clock_ambiguous','duration'}),
    ('Agenda llamada mañana a las 3pm', {'duration'}),
    ('Agenda gym lunes miércoles viernes de 09:00 a 10:00', {'scope'}),
    ('Agenda gym durante dos semanas de 09:00 a 10:00', {'weekdays'}),
    ('Agenda gym todos los lunes a las 09:00 durante una hora', {'start','end'}),
    ('Agenda gym todos los lunes desde hoy a las 09:00 durante una hora', {'end'}),
    ('Agenda gym todos los lunes desde 2026-10-19 hasta 2026-12-31', {'clock','duration'}),
])
def test_missing_details_short_circuit_proposal(message, missing):
    plan = _plan(message, NOW, None)
    assert plan.reply
    assert set(plan.missing) == missing


def test_invalid_calendar_date_and_weekday_mismatch_ask():
    assert 'no existe' in _plan('Agenda el 31 de febrero de 2027 a las 15:00 durante una hora', NOW, None).reply
    assert 'no cae en viernes' in _plan('Agenda el viernes 24 de octubre de 2026 a las 15:00 durante una hora', NOW, None).reply


@pytest.mark.parametrize('message', [
    'Agenda gimnasio lunes miércoles viernes durante dos semanas desde el 19 de octubre de 2026 de 15:00 a 16:00',
    'Agenda gimnasio lunes miércoles viernes del 19 al 30 de octubre de 2026 de 15:00 a 16:00',
    'Agenda gimnasio lunes miércoles viernes desde 2026-10-19 hasta 2026-10-30 de 15:00 a 16:00',
    'Agenda gimnasio lunes miércoles viernes la próxima semana durante dos semanas de 15:00 a 16:00',
])
def test_explicit_finite_repetition_has_exact_six_dates(message):
    plan = _plan(message, NOW, None)
    assert plan.reply is None
    assert plan.recurrence is None
    assert plan.dates == [date(2026,10,d) for d in (19,21,23,26,28,30)]


def test_weekly_routine_requires_explicit_end_or_indefinite():
    plan = _plan('Agenda gimnasio todos los lunes y miércoles desde 2026-10-19 sin fecha final de 09:00 a 10:00', NOW, None)
    assert plan.reply is None
    assert plan.recurrence == {'weekdays':[1,3], 'starts_on':'2026-10-19','ends_on':None,'indefinite':True}
    assert len(plan.dates) == 8


def test_weekly_routine_with_relative_start_and_explicit_end():
    plan = _plan('Agenda gimnasio todos los lunes desde hoy hasta el 30 de noviembre de 2026 de 09:00 a 10:00', NOW, None)
    assert plan.reply is None
    assert plan.recurrence['starts_on'] == '2026-10-15'
    assert plan.recurrence['ends_on'] == '2026-11-30'


def test_weekly_routine_with_two_week_duration():
    plan = _plan('Agenda gimnasio todos los lunes desde el 19 de octubre de 2026 por dos semanas de 09:00 a 10:00', NOW, None)
    assert plan.reply is None
    assert plan.recurrence['ends_on'] == '2026-11-01'
    assert plan.dates == [date(2026,10,19),date(2026,10,26)]


@pytest.mark.parametrize(('expression','begin','end','offset'), [
    ('de 09:00 a 10:00',time(9),time(10),0),
    ('de 3pm a 4pm',time(15),time(16),0),
    ('a las 3 p. m. durante media hora',time(15),time(15,30),0),
    ('a las 3 de la tarde durante una hora y media',time(15),time(16,30),0),
    ('a las 23:30 por 90 minutos',time(23,30),time(1),1),
    ('de 23:00 a 01:00',time(23),time(1),1),
    ('09:00-10:00',time(9),time(10),0),
])
def test_hours_and_midnight_are_deterministic(expression, begin, end, offset):
    plan = _plan(f'Agenda llamada mañana {expression}', NOW, None)
    assert plan.reply is None
    assert (plan.start_clock,plan.end_clock,plan.end_day_offset) == (begin,end,offset)


@pytest.mark.parametrize(('message','begin','end'), [
    ('¿Qué tengo esta semana?',date(2026,10,12),date(2026,10,18)),
    ('Muéstrame mi agenda la próxima semana',date(2026,10,19),date(2026,10,25)),
    ('¿Qué tengo el viernes de la próxima semana?',date(2026,10,23),date(2026,10,23)),
    ('¿Qué tengo mañana?',date(2026,10,16),date(2026,10,16)),
    ('¿Qué tengo desde 2026-10-19 hasta 2026-10-30?',date(2026,10,19),date(2026,10,30)),
    ('No agendes nada, consulta esta semana',date(2026,10,12),date(2026,10,18)),
])
def test_queries_expand_context_without_mutation(message, begin, end):
    plan = _plan(message, NOW, date(2025,1,1))
    assert not plan.is_mutation
    assert plan.reply is None
    assert (plan.start_date,plan.end_date) == (begin,end)


@pytest.mark.asyncio
async def test_clarifications_survive_session_and_anchor_is_frozen(db_session):
    first = await prepare_agenda_intent(db_session,'u','d','Agenda una llamada con Miguel',now=NOW)
    assert first.reply
    await db_session.commit()
    db_session.expunge_all()
    second = await prepare_agenda_intent(db_session,'u','d','Mañana a las 15:00 durante una hora',now=NOW+timedelta(minutes=2))
    assert second.reply is None
    assert second.dates == [date(2026,10,16)]
    assert 'Miguel' in second.effective_message
    await db_session.commit()
    assert not (await db_session.scalars(select(ChatPendingAction))).all()


@pytest.mark.asyncio
async def test_three_turn_week_scope_time_and_duration(db_session):
    await prepare_agenda_intent(db_session,'u','d','Agenda gym lunes miércoles viernes',now=NOW)
    await db_session.commit()
    second = await prepare_agenda_intent(db_session,'u','d','Sólo la próxima semana',now=NOW)
    await db_session.commit()
    assert second.dates == [date(2026,10,d) for d in (19,21,23)]
    assert set(second.missing) == {'clock','duration'}
    third = await prepare_agenda_intent(db_session,'u','d','A las 09:00 durante una hora',now=NOW)
    assert third.reply is None
    assert len(third.dates) == 3


@pytest.mark.asyncio
async def test_pending_user_device_isolation_and_expiry(db_session):
    await prepare_agenda_intent(db_session,'u','d','Agenda una llamada',now=NOW)
    await db_session.commit()
    assert not (await prepare_agenda_intent(db_session,'other','d','mañana a las 15:00 durante una hora',now=NOW)).is_mutation
    assert not (await prepare_agenda_intent(db_session,'u','other','mañana a las 15:00 durante una hora',now=NOW)).is_mutation
    expired = await prepare_agenda_intent(db_session,'u','d','mañana a las 15:00 durante una hora',now=NOW+timedelta(minutes=31))
    assert not expired.is_mutation
    await db_session.commit()
    assert not (await db_session.scalars(select(ChatPendingAction))).all()


@pytest.mark.asyncio
async def test_midnight_clarification_keeps_original_today(db_session):
    anchor = NOW.replace(hour=23,minute=58)
    await prepare_agenda_intent(db_session,'u','d','Agenda una llamada mañana',now=anchor)
    await db_session.commit()
    plan = await prepare_agenda_intent(db_session,'u','d','A las 15:00 durante una hora',now=anchor+timedelta(minutes=5))
    assert plan.reply is None
    assert plan.dates == [date(2026,10,16)]


@pytest.mark.asyncio
async def test_unrelated_queries_do_not_inherit_pending_activity(db_session):
    await prepare_agenda_intent(db_session,'u','d','Agenda una llamada',now=NOW)
    await db_session.commit()
    for message in ('¿Qué tengo mañana?','Analiza el documento 2026','/archivo contrato 2026','¿Qué es una semana?'):
        plan = await prepare_agenda_intent(db_session,'u','d',message,now=NOW)
        assert not plan.is_mutation
        assert plan.effective_message == message
    assert len((await db_session.scalars(select(ChatPendingAction))).all()) == 1


@pytest.mark.asyncio
async def test_cancel_and_yes_never_create_undetailed_event(db_session):
    first = await prepare_agenda_intent(db_session,'u','d','Agenda una llamada',now=NOW)
    await db_session.commit()
    yes = await prepare_agenda_intent(db_session,'u','d','sí',now=NOW)
    assert yes.reply == first.reply
    cancel = await prepare_agenda_intent(db_session,'u','d','no',now=NOW)
    assert 'cancelé' in cancel.reply
    await db_session.commit()
    assert not (await db_session.scalars(select(ChatPendingAction))).all()


def _proposal(items=1):
    return AgentProposalModel(id='p',summary='Gimnasio',reason='Solicitado',resulting_items=[AgendaItemModel(id=f'evt-{i}',title='Gimnasio',start_time=datetime(2020,1,1,2),end_time=datetime(2020,1,1,3)) for i in range(items)])


def test_model_dates_and_number_of_occurrences_are_not_trusted():
    plan = _plan('Agenda gimnasio lunes miércoles viernes la próxima semana durante dos semanas de 15:00 a 16:00', NOW, None)
    result, error = constrain_proposal(plan, _proposal())
    assert error is None
    assert len(result.resulting_items) == 6
    assert [i.start_time.date() for i in result.resulting_items] == plan.dates
    assert all(i.start_time.hour == 15 and i.start_time.utcoffset() == timedelta(hours=-6) for i in result.resulting_items)
    assert len({i.id for i in result.resulting_items}) == 6


def test_mixed_activities_ask_before_constraining():
    proposal = _proposal(2)
    proposal.resulting_items[1].title = 'Otra actividad'
    plan = _plan('Agenda gimnasio mañana a las 15:00 durante una hora',NOW,None)
    result,error = constrain_proposal(plan,proposal)
    assert result is None
    assert 'varias actividades' in error


def test_proposal_overnight_end_is_next_day():
    plan = _plan('Agenda trabajo mañana a las 23:30 durante 90 minutos',NOW,None)
    result,error = constrain_proposal(plan,_proposal())
    assert error is None
    item = result.resulting_items[0]
    assert item.start_time.date() == date(2026,10,16)
    assert item.end_time == datetime(2026,10,17,1,tzinfo=ZONE)

@pytest.mark.asyncio
async def test_explicit_date_correction_resolves_original_weekday_mismatch(db_session):
    first = await prepare_agenda_intent(db_session,'u','d','Agenda llamada el viernes 24 de octubre de 2026 a las 15:00 durante una hora',now=NOW)
    assert first.reply
    await db_session.commit()
    corrected = await prepare_agenda_intent(db_session,'u','d','23 de octubre de 2026',now=NOW)
    assert corrected.reply is None
    assert corrected.dates == [date(2026,10,23)]


@pytest.mark.asyncio
async def test_guard_clarification_overrides_existing_clock_and_keeps_duration(db_session):
    from app.services.agenda_intent import remember_agenda_clarification
    plan = _plan('Agenda llamada mañana de 15:00 a 16:00',NOW,None)
    await remember_agenda_clarification(db_session,'u','d',plan,'Ese horario se cruza, ¿a qué hora?',now=NOW)
    await db_session.commit()
    corrected = await prepare_agenda_intent(db_session,'u','d','A las 18:00',now=NOW)
    assert corrected.reply is None
    assert (corrected.start_clock,corrected.end_clock) == (time(18),time(19))


@pytest.mark.asyncio
async def test_end_time_answer_does_not_replace_start(db_session):
    await prepare_agenda_intent(db_session,'u','d','Agenda llamada mañana a las 15:00',now=NOW)
    await db_session.commit()
    plan = await prepare_agenda_intent(db_session,'u','d','Hasta las 16:00',now=NOW)
    assert plan.reply is None
    assert (plan.start_clock,plan.end_clock) == (time(15),time(16))


@pytest.mark.asyncio
async def test_duration_only_answer(db_session):
    await prepare_agenda_intent(db_session,'u','d','Agenda llamada mañana a las 15:00',now=NOW)
    await db_session.commit()
    plan = await prepare_agenda_intent(db_session,'u','d','Una hora',now=NOW)
    assert plan.reply is None
    assert (plan.start_clock,plan.end_clock) == (time(15),time(16))


def test_context_without_date_covers_selected_week():
    plan = _plan('¿Qué compromisos tengo?',NOW,date(2026,11,5))
    assert (plan.start_date,plan.end_date) == (date(2026,11,2),date(2026,11,8))

@pytest.mark.parametrize(('day','clock'), [('2027-03-14','02:30'),('2026-11-01','01:30')])
def test_dst_nonexistent_or_ambiguous_clock_never_gets_silently_normalized(day,clock):
    zone = ZoneInfo('America/New_York')
    now = datetime(2026,10,15,12,tzinfo=zone)
    plan = _plan(f'Agenda llamada {day} a las {clock} durante 15 minutos',now,None)
    assert plan.reply is None
    result,error = constrain_proposal(plan,_proposal())
    assert result is None
    assert 'cambio de horario' in error


def test_routine_full_day_duration_asks_before_proposing():
    plan = _plan('Agenda guardia todos los lunes desde hoy sin fecha final a las 09:00 durante 24 horas',NOW,None)
    assert 'menor de 24 horas' in plan.reply


def test_weekday_range_expands_all_five_days():
    plan = _plan('Agenda ejercicio de lunes a viernes la próxima semana a las 09:00 durante una hora',NOW,None)
    assert plan.reply is None
    assert plan.dates == [date(2026,10,d) for d in range(19,24)]


def test_multiple_different_time_blocks_ask_instead_of_flattening():
    plan = _plan('Agenda gimnasio mañana a las 09:00 durante una hora y gimnasio pasado mañana a las 15:00 durante una hora',NOW,None)
    assert 'varios horarios' in plan.reply

@pytest.mark.parametrize('message', ['Organízame el día','Ayúdame a armar mi rutina','Ayúdame a organizar mi semana','Recuérdame hacer ejercicio','Puedes planificar mi semana'])
def test_common_planning_requests_are_mutations_that_require_details(message):
    plan = _plan(message,NOW,None)
    assert plan.is_mutation
    assert plan.reply


@pytest.mark.parametrize('message', ['No organices nada, consulta mi agenda','Sin planificar cambios, dime qué tengo','No me recuerdes nada','¿Qué recordatorios tengo?','Recuérdame qué tenía mañana'])
def test_read_requests_and_negated_common_imperatives_are_not_mutations(message):
    plan = _plan(message,NOW,None)
    assert not plan.is_mutation


@pytest.mark.parametrize(('expression','target','first','last'), [
    ('del 2026-11-03 al 2026-11-05',date(2026,11,5),date(2026,11,3),date(2026,11,5)),
    ('del 2026-11-03 a mañana',date(2026,10,16),date(2026,10,16),date(2026,11,3)),
    ('de hoy a mañana',date(2026,10,16),date(2026,10,15),date(2026,10,16)),
])
def test_moves_keep_source_context_but_only_propose_destination(expression,target,first,last):
    plan = _plan(f'Mueve la llamada {expression} a las 15:00 durante una hora',NOW,None)
    assert plan.reply is None
    assert plan.dates == [target]
    assert (plan.start_date,plan.end_date) == (first,last)

@pytest.mark.parametrize('message', [
    'Cancela estudio todos los lunes desde hoy sin fecha final',
    'Cancela estudio todos los lunes',
    'Cancela la rutina de estudio',
])
def test_unbounded_routine_deletion_asks_scope_without_creation_metadata(message):
    plan = _plan(message,NOW,None)
    assert plan.operation == 'delete'
    assert 'toda la rutina' in plan.reply
    assert plan.recurrence is None
    assert '/pausar' not in plan.reply


@pytest.mark.parametrize('message', [
    'Cancela estudio todos los lunes desde el 19 de octubre de 2026 hasta el 30 de noviembre de 2026',
    'Cancela estudio todos los lunes del 19 de octubre de 2026 al 30 de noviembre de 2026',
])
def test_bounded_repeated_deletion_is_full_date_set_without_routine_metadata(message):
    plan = _plan(message,NOW,None)
    assert plan.reply is None
    assert plan.operation == 'delete'
    assert plan.recurrence is None
    assert plan.start_clock is None
    assert plan.dates == [date(2026,10,19)+timedelta(days=7*i) for i in range(7)]


def test_week_bounded_deletion_does_not_require_routine_end():
    plan = _plan('Cancela estudio todos los lunes esta semana',NOW,None)
    assert plan.reply is None
    assert plan.recurrence is None
    assert plan.dates == [date(2026,10,12)]


@pytest.mark.asyncio
async def test_routine_delete_can_be_narrowed_to_concrete_occurrence(db_session):
    first = await prepare_agenda_intent(db_session,'u','d','Cancela estudio todos los lunes desde hoy sin fecha final',now=NOW)
    assert first.reply
    await db_session.commit()
    narrowed = await prepare_agenda_intent(db_session,'u','d','Sólo el 19 de octubre de 2026',now=NOW)
    assert narrowed.reply is None
    assert narrowed.operation == 'delete'
    assert narrowed.recurrence is None
    assert narrowed.dates == [date(2026,10,19)]


def test_concrete_deletion_still_has_no_clock_requirement():
    plan = _plan('Cancela la llamada mañana',NOW,None)
    assert plan.reply is None
    assert plan.recurrence is None
    assert plan.dates == [date(2026,10,16)]
