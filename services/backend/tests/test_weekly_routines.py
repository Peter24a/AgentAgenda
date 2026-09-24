from datetime import datetime, timedelta, timezone
import pytest
from sqlalchemy import select, func
from app.models.canonical import WeeklyRoutine, Event, ChangeBatch
from app.services.weekly_routines import expand_routine, materialize_routine, maintain_weekly_routines, set_routine_enabled

NOW = datetime(2026, 9, 21, 12, tzinfo=timezone.utc)

async def routine(session, **kwargs):
    row = WeeklyRoutine(id='weekly-test',user_id='default_user',name='Test routine',timezone='America/Mexico_City',starts_on='2026-09-21',generation=1,enabled=True,
                        template_json=[dict(id='monday',iso_weekday=1,start_time='23:30',end_time='00:30',title='Synthetic study',category='study')], **kwargs)
    session.add(row)
    await session.commit()
    return row

@pytest.mark.asyncio
async def test_rolling_weekly_calendar_midnight_and_idempotence(db_session):
    await routine(db_session)
    report=await materialize_routine('weekly-test','default_user',now=NOW)
    assert report['created']==4
    rows=(await db_session.scalars(select(Event).order_by(Event.start_time))).all()
    assert rows[0].start_time==datetime(2026,9,22,5,30)
    assert rows[0].end_time==datetime(2026,9,22,6,30)
    assert (await materialize_routine('weekly-test','default_user',now=NOW))['created']==0
    assert await maintain_weekly_routines(now=NOW)==0
    assert await maintain_weekly_routines(now=NOW+timedelta(days=7))==1
    assert await db_session.scalar(select(func.count()).select_from(Event))==5
    assert await db_session.scalar(select(func.count()).select_from(ChangeBatch))==5

@pytest.mark.asyncio
async def test_edits_deletions_disable_resume_and_owner_are_preserved(db_session):
    await routine(db_session)
    await materialize_routine('weekly-test','default_user',now=NOW)
    rows=(await db_session.scalars(select(Event).order_by(Event.start_time))).all()
    rows[0].title='Edited by owner';rows[0].version+=1
    rows[1].is_deleted=True;rows[1].version+=1
    await db_session.commit()
    assert await set_routine_enabled('weekly-test','other',False,now=NOW) is None
    await set_routine_enabled('weekly-test','default_user',False,now=NOW)
    assert await maintain_weekly_routines(now=NOW+timedelta(days=7))==0
    await set_routine_enabled('weekly-test','default_user',True,now=NOW)
    await db_session.refresh(rows[0]);await db_session.refresh(rows[1])
    assert rows[0].title=='Edited by owner' and rows[1].is_deleted
    assert await db_session.scalar(select(func.count()).select_from(Event))==4

@pytest.mark.asyncio
async def test_deadline_and_conflict_preserve_real_events(db_session):
    r=await routine(db_session)
    r.template_json=[{**r.template_json[0],'until':'2026-10-05'}]
    db_session.add(Event(id='manual',user_id='default_user',title='Existing appointment',category='work',timezone='America/Mexico_City',start_time=datetime(2026,9,22,5),end_time=datetime(2026,9,22,6)))
    await db_session.commit()
    report=await materialize_routine(r.id,r.user_id,now=NOW)
    assert report['created']==2 and report['skipped_conflict']==1
    assert await maintain_weekly_routines(now=NOW)==0
    r.template_json=[{**r.template_json[0]}, {**r.template_json[0],'id':'overlap'}]
    with pytest.raises(ValueError,match='overlapping'):
        expand_routine(r,NOW.date(),NOW.date()+timedelta(days=20))

@pytest.mark.asyncio
async def test_routine_api_scoping(client,db_session):
    await routine(db_session)
    r=await client.get('/v1/agenda/routines')
    assert r.status_code==200 and len(r.json())==1
    r=await client.put('/v1/agenda/routines/weekly-test/enabled',json={'enabled':False})
    assert r.status_code==200 and r.json()['existing_events_preserved']
    assert (await client.put('/v1/agenda/routines/missing/enabled',json={'enabled':False})).status_code==404
