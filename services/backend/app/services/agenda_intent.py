"""Conservative Spanish calendar planning before a model may propose mutations.

Calendar arithmetic and clarification state are server-owned.  This module does
not write events: the normal preview/confirmation boundary remains in place.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
import hashlib
import re
import unicodedata
import uuid
from zoneinfo import ZoneInfo

from app.models.canonical import ChatPendingAction

WEEKDAYS = {"lunes": 0, "martes": 1, "miercoles": 2, "jueves": 3,
            "viernes": 4, "sabado": 5, "domingo": 6}
MONTHS = {name: idx for idx, name in enumerate(("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"), 1)}
MONTHS["setiembre"] = 9
NUMBERS = {"un": 1, "una": 1, "uno": 1, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5, "seis": 6, "siete": 7, "ocho": 8, "nueve": 9, "diez": 10, "once": 11, "doce": 12}
DAY_PATTERN = r"(?:lunes|martes|miercoles|jueves|viernes|sabados?|domingos?)"
NUMBER_PATTERN = r"(?:\d+|" + "|".join(NUMBERS) + ")"


def _plain(value: str) -> str:
    return "".join(ch for ch in unicodedata.normalize("NFKD", value.lower()) if not unicodedata.combining(ch))


def _number(value: str) -> int:
    return int(value) if value.isdigit() else NUMBERS[value]


@dataclass
class IntentPlan:
    effective_message: str
    start_date: date
    end_date: date
    reply: str | None = None
    dates: list[date] = field(default_factory=list)
    start_clock: time | None = None
    end_clock: time | None = None
    end_day_offset: int = 0
    recurrence: dict | None = None
    is_mutation: bool = False
    operation: str = "query"
    timezone: str = "America/Mexico_City"
    missing: list[str] = field(default_factory=list)
    anchor: datetime | None = None

    def context_instruction(self) -> str:
        if not self.is_mutation:
            return f"Período consultado: {self.start_date.isoformat()} a {self.end_date.isoformat()} (ambos incluidos)."
        if self.reply:
            return self.reply
        dates = ", ".join(d.isoformat() for d in self.dates)
        schedule = f"Fechas verificadas por el servidor: {dates}."
        if self.start_clock and self.end_clock:
            schedule += f" Horario local {self.start_clock.strftime('%H:%M')}–{self.end_clock.strftime('%H:%M')} en {self.timezone}."
        if self.recurrence:
            schedule += f" Rutina semanal desde {self.recurrence['starts_on']} hasta {self.recurrence['ends_on'] or 'sin fecha final (autorizado explícitamente)'}."
        return schedule + " Usa exclusivamente estas fechas y horas; no recalcules los días de la semana."


def _operation(text: str) -> str:
    # Questions about existing entries do not become writes just for saying agenda.
    if re.search(r"\b(?:no|sin)\s+(?:agendes|agendar|crees|crear|modifiques|modificar|borres|borrar|organices|organizar|planees|planear|planifiques|planificar|armes|armar|recuerdes|recordar|programes|programar|repitas|repetir|canceles|cancelar|muevas|mover|cambies|cambiar)\b", text):
        return "query"
    if re.search(r"\brecuerdame\s+(?:que|cual|como|cuando|si|lo que)\b", text):
        return "query"
    if re.search(r"\b(?:organiza(?:me|r)?|planifica(?:me|r)?|planea(?:me|r)?|recuerdame|recordarme)\b", text) or re.search(r"\b(?:ayuda(?:me)?|ayudarme)\s+a\s+(?:armar|organizar|planificar|planear)\b", text):
        return "create"
    if re.search(r"\b(?:cancela|cancelar|elimina|eliminar|borra|borrar|quita|quitar)\b", text):
        return "delete"
    if re.search(r"\b(?:mueve|mover|reprograma|reprogramar|cambia|cambiar|modifica|modificar|pospone|posponer)\b", text):
        return "update"
    if re.search(r"\b(?:agenda(?:me|r|lo)?|agende|programa(?:me|r)?|anota(?:me|r)?|crea(?:me|r)?|agrega(?:me|r)?|pon(?:me)?|reserva(?:me|r)?|repite|repetir)\b", text):
        # 'mi agenda', 'la agenda', 'qué agenda' are nouns, not imperative.
        if re.search(r"\b(?:mi|la|tu|su|esta|ver|consulta|consultar|revisa|revisar) agenda\b", text) and not re.search(r"\b(?:agenda(?:me|r)|agenda\s+(?:una?|el|para|lunes|martes|miercoles|jueves|viernes|sabado|domingo))\b", text):
            return "query"
        return "create"
    if re.search(r"\b(?:quiero|necesito|puedes|podrias)\s+(?:una?\s+)?(?:reunion|cita|actividad|sesion|recordatorio)\b", text):
        return "create"
    return "query"


def _explicit_dates(text: str, today: date) -> tuple[list[tuple[int, date]], str | None]:
    found: list[tuple[int, date]] = []
    occupied: list[tuple[int, int]] = []
    patterns = [
        (r"\b(20\d{2})-(\d{1,2})-(\d{1,2})\b", "iso"),
        (r"\b(\d{1,2})/(\d{1,2})/(20\d{2})\b", "slash"),
        (r"\b(\d{1,2})\s+de\s+(" + "|".join(MONTHS) + r")(?:\s+(?:de(?:l)?\s+)?(20\d{2}))?\b", "month"),
    ]
    try:
        for pattern, kind in patterns:
            for m in re.finditer(pattern, text):
                if any(lo <= m.start() < hi for lo, hi in occupied):
                    continue
                if kind == "iso":
                    value = date(int(m[1]), int(m[2]), int(m[3]))
                elif kind == "slash":
                    value = date(int(m[3]), int(m[2]), int(m[1]))
                else:
                    value = date(int(m[3] or today.year), MONTHS[m[2]], int(m[1]))
                found.append((m.start(), value))
                occupied.append(m.span())
        # "del 19 al 30 de octubre" shares the month/year of the second date.
        for m in re.finditer(r"\b(?:del?\s+)?(\d{1,2})\s+(?:al|hasta el|a)\s+(\d{1,2})\s+de\s+(" + "|".join(MONTHS) + r")(?:\s+de\s+(20\d{2}))?\b", text):
            value = date(int(m[4] or today.year), MONTHS[m[3]], int(m[1]))
            found.append((m.start(1), value))
    except ValueError:
        return [], "Esa fecha no existe en el calendario. ¿Qué fecha exacta quieres usar?"
    return sorted(set(found)), None


def _clock(hour: str, minute: str | None, suffix: str | None, *, explicit_colon=False) -> tuple[time | None, bool]:
    h, m = int(hour), int(minute or 0)
    marker = (suffix or "").replace(".", "").replace(" ", "")
    if marker in {"pm", "delatarde", "delanoche"}:
        if not 1 <= h <= 12:
            return None, True
        h = h % 12 + 12
    elif marker in {"am", "delamanana", "delamadrugada"}:
        if not 1 <= h <= 12:
            return None, True
        h %= 12
    elif h <= 12 and not explicit_colon:
        return None, True
    if h > 23 or m > 59:
        return None, True
    return time(h, m), False


CLOCK_PATTERN = r"(\d{1,2})(?!\d)(?::(\d{2}))?\s*(a\.?\s*m\.?|p\.?\s*m\.?|de la manana|de la tarde|de la noche|de la madrugada)?"


def _times(text: str) -> tuple[time | None, time | None, int, str | None]:
    starts, ends = [], []
    for m in re.finditer(r"(?:\ba las?\s+|\bdesde las?\s+|\bdesde\s+|\bde\s+)" + CLOCK_PATTERN, text):
        if not m[2] and not m[3] and re.match(r"\s*(?:de\s+(?:" + "|".join(MONTHS) + r")|semanas?|dias?|horas?|minutos?)\b", text[m.end():]):
            continue
        starts.append((m.start(), _clock(m[1], m[2], m[3], explicit_colon=bool(m[2]))))
    # A bare 15:00 or 3pm is valid as a response to the time question.
    for m in re.finditer(r"(?<![\d:-])" + CLOCK_PATTERN + r"(?![\d:])", text):
        if m[2] or m[3]:
            prefix = text[max(0, m.start()-12):m.start()]
            if re.search(r"(?:hasta(?: las?)?|a(?: las?)?)\s+$", prefix) and starts and not re.search(r"a las?\s+$", prefix):
                continue
            starts.append((m.start(), _clock(m[1], m[2], m[3], explicit_colon=bool(m[2]))))
    for m in re.finditer(r"(?:\bhasta(?: las?)?\s+|\ba\s+|[-–]\s*)" + CLOCK_PATTERN, text):
        # Reject ISO date fragments as hours.
        if m.start() and text[m.start()] == '-' and text[m.start()-1].isdigit() and ':' not in text[max(0, m.start()-5):m.start()]:
            continue
        if not m[2] and not m[3] and re.match(r"\s+de\s+(?:" + "|".join(MONTHS) + r")\b", text[m.end():]):
            continue
        ends.append((m.start(), _clock(m[1], m[2], m[3], explicit_colon=bool(m[2]))))
    # For a range, the last explicit clock is the end rather than a new start.
    if ends:
        endpos = ends[-1][0]
        before_end = [pair for pair in starts if pair[0] < endpos]
        if before_end:
            starts = before_end
    start, ambiguous = sorted(starts)[-1][1] if starts else (None, False)
    end, end_ambiguous = ends[-1][1] if ends else (None, False)
    duration = None
    for m in re.finditer(r"\b(?:durante|por|dura(?:cion)?(?: de)?|de)\s+(" + NUMBER_PATTERN + r")\s*(horas?|minutos?)(?:\s+y\s+(media|cuarto))?\b", text):
        amount = _number(m[1]) * (60 if m[2].startswith("hora") else 1)
        if m[3]:
            amount += 30 if m[3] == 'media' else 15
        duration = amount
    if duration is None:
        m = re.search(r"\b(media hora|una hora y media|una hora|dos horas|\d+\s*(?:horas?|minutos?))\b", text)
        if m:
            if m[1] == 'media hora':
                duration = 30
            elif m[1] == 'una hora y media':
                duration = 90
            else:
                n, unit = m[1].split(maxsplit=1)
                duration = _number(n) * (60 if unit.startswith('hora') else 1)
    if ambiguous or end_ambiguous:
        return start, end, 0, "¿A qué hora exacta? Indícala en formato de 24 horas (por ejemplo, 15:00) o con a. m./p. m."
    offset = 0
    if duration is not None:
        if not 0 < duration <= 24*60:
            return start, None, 0, "¿Cuánto debe durar? Usa una duración de entre 1 minuto y 24 horas."
        if start:
            total = start.hour*60+start.minute+duration
            end, offset = time((total//60) % 24, total % 60), total//1440
    elif start and end:
        offset = int(end <= start)
    return start, end, offset, None


def _times_with_clarifications(text):
    parts = text.split('\naclaracion del usuario: ')
    start, end, offset, error = _times(parts[0])
    for part in parts[1:]:
        new_start, new_end, new_offset, new_error = _times(part)
        # End-time-only replies must retain the original start.
        end_only = bool(re.match(r'\s*(?:hasta(?: las?)?|termina(?: a las?)?)\s+', part))
        if end_only:
            new_start = None
        if new_start is not None:
            old_duration = None
            if start is not None and end is not None:
                old_duration = offset*1440+end.hour*60+end.minute-start.hour*60-start.minute
            start = new_start
            if new_end is not None:
                end, offset = new_end, new_offset
            elif old_duration is not None:
                total = start.hour*60+start.minute+old_duration
                end, offset = time((total//60)%24,total%60), total//1440
            else:
                end, offset = None, 0
            error = new_error
        elif new_end is not None and start is not None:
            end, offset, error = new_end, int(new_end<=start), new_error
        elif new_error:
            error = new_error
        # Duration-only answers need the known start to resolve their end.
        elif start is not None and re.search(r'\b(?:horas?|minutos?)\b', part):
            start, end, offset, error = _times(f'a las {start.strftime("%H:%M")} '+part)
    return start, end, offset, error


def _plan(message: str, now: datetime, view_date: date | None) -> IntentPlan:
    text, today = _plain(message), now.date()
    parts = text.split('\naclaracion del usuario: ')
    date_text = text
    for part in reversed(parts[1:]):
        values, date_error = _explicit_dates(part, today)
        if values or date_error or any(not re.search(r'de la\s+$', part[:m.start()]) for m in re.finditer(r'\b(?:hoy|manana|pasado manana)\b', part)):
            date_text = part
            break
    default_date = view_date or today
    default_monday = default_date-timedelta(days=default_date.weekday())
    zone = getattr(now.tzinfo, 'key', None) or 'America/Mexico_City'
    plan = IntentPlan(message, default_monday, default_monday+timedelta(days=6), timezone=zone, operation=_operation(text), anchor=now)
    plan.is_mutation = plan.operation != 'query'
    explicit, error = _explicit_dates(date_text, today)
    if error:
        plan.reply, plan.missing = error, ['date']
        return plan
    weekdays = sorted({WEEKDAYS[m.group().rstrip('s') if m.group() in ('sabados', 'domingos') else m.group()] for m in re.finditer(r'\b' + DAY_PATTERN + r'\b', text)})
    for span in re.finditer(r'\bde(?:l)?\s+('+DAY_PATTERN+r')\s+a(?:l)?\s+('+DAY_PATTERN+r')\b', text):
        first = WEEKDAYS[span[1].rstrip('s') if span[1] in ('sabados','domingos') else span[1]]
        last = WEEKDAYS[span[2].rstrip('s') if span[2] in ('sabados','domingos') else span[2]]
        weekdays = sorted(set(weekdays) | {(first+i)%7 for i in range((last-first)%7+1)})
    if re.search(r'\b(?:todos los dias|cada dia|diariamente)\b', text):
        weekdays = list(range(7))
    monday = today - timedelta(days=today.weekday())
    week_matches = list(re.finditer(r'\b(?:esta semana|semana actual|(?:la )?(?:proxima|siguiente) semana|semana (?:proxima|siguiente)|semana que (?:viene|entra)|semana pasada)\b', text))
    week_start = None
    if week_matches:
        match = week_matches[-1].group()
        week_start = monday + timedelta(days=(-7 if 'pasada' in match else 0 if match in ('esta semana','semana actual') else 7))
    relative = list(re.finditer(r'\b(?:pasado manana|manana|hoy)\b', date_text))
    # "de la mañana" is a clock marker, not tomorrow.
    relative = [m for m in relative if not re.search(r'de la\s+$', date_text[:m.start()])]
    relative_date = None
    if relative:
        relative_date = today + timedelta(days={'hoy':0,'manana':1,'pasado manana':2}[relative[-1].group()])
    upcoming = re.search(r'\b(?:proximo|siguiente)\s+(' + DAY_PATTERN + r')\b', text)
    if upcoming and week_start is None and not explicit:
        wd = WEEKDAYS[upcoming[1].rstrip('s') if upcoming[1] in ('sabados','domingos') else upcoming[1]]
        relative_date = today + timedelta(days=(wd-today.weekday()) % 7 or 7)
    weekly = bool(re.search(r'\b(?:todos los dias|cada dia|diariamente|cada\s+(?:semana|' + DAY_PATTERN + r')|todas las semanas|todos los\s+' + DAY_PATTERN + r'|semanalmente|semanal)\b', text))
    indefinite = bool(re.search(r'\b(?:indefinidamente|sin fecha (?:de )?fin(?:al)?|sin fin|sin limite|hasta (?:nuevo aviso|que te (?:diga|avise)))\b', text))
    week_count_match = re.search(r'\b(?:durante|por)\s+(' + NUMBER_PATTERN + r')\s+semanas?\b', text)
    week_count = _number(week_count_match[1]) if week_count_match else None
    if week_count and week_count > 12:
        plan.reply, plan.missing = '¿Podemos dividirlo en períodos de hasta 12 semanas o definir una rutina semanal con fecha de inicio y fin?', ['scope']
        return plan
    is_range = bool(re.search(r'\b(?:desde|del?|a partir|entre)\b.{0,45}\b(?:hasta|al|y el)\b', date_text)) and len(explicit) >= 2
    if plan.operation == 'delete' and date_text != text and explicit:
        # A concrete-date answer narrows a previously broad series request.
        indefinite = False
        if not is_range:
            weekly = False
    if date_text != text and (explicit or relative_date) and not weekly:
        week_start = None
        weekdays = sorted({WEEKDAYS[m.group().rstrip('s') if m.group() in ('sabados','domingos') else m.group()] for m in re.finditer(r'\b'+DAY_PATTERN+r'\b', date_text)})
    start_bound = explicit[0][1] if explicit else relative_date
    end_bound = explicit[-1][1] if is_range else None
    # A weekday immediately preceding a concrete date must agree with it.
    for pos, concrete in explicit:
        prefix = date_text[max(0,pos-24):pos]
        preceding = re.search(r'\b(' + DAY_PATTERN + r')\s*(?:el|,)?\s*$', prefix)
        if preceding:
            wd = WEEKDAYS[preceding[1].rstrip('s') if preceding[1] in ('sabados','domingos') else preceding[1]]
            if wd != concrete.weekday():
                plan.reply, plan.missing = f'El {concrete.isoformat()} no cae en {preceding[1]}. ¿Quieres esa fecha o el día de la semana que mencionaste?', ['date']
                return plan
    if not plan.is_mutation:
        if week_start:
            if weekdays and not week_count:
                plan.start_date, plan.end_date = week_start+timedelta(days=min(weekdays)), week_start+timedelta(days=max(weekdays))
            else:
                plan.start_date, plan.end_date = week_start, week_start + timedelta(days=7*(week_count or 1)-1)
        elif is_range:
            plan.start_date, plan.end_date = start_bound, end_bound
        elif explicit or relative_date:
            plan.start_date = plan.end_date = (explicit[-1][1] if explicit else relative_date)
        elif weekdays:
            # Read-only queries with unspecified weekday may safely inspect the whole current week.
            plan.start_date, plan.end_date = monday, monday + timedelta(days=6)
        elif re.search(r'\b(?:semana|proximos dias)\b', text):
            plan.start_date, plan.end_date = monday, monday+timedelta(days=6)
        if plan.end_date < plan.start_date or (plan.end_date-plan.start_date).days > 366:
            plan.reply = 'Indícame un período válido de hasta un año para consultar la agenda.'
        return plan
    if re.search(r'\b(?:cada\s+(?:dos|tres|cuatro|[2-9]\d*)\s+semanas?|mensualmente|cada mes|quincenal(?:mente)?|anualmente|cada ano)\b', text):
        plan.reply, plan.missing = 'Puedo preparar repeticiones semanales o fechas concretas. ¿Qué fechas exactas quieres para esa frecuencia?', ['date']
        return plan
    # Multiple different time blocks need separate explicit plans; never flatten
    # them into the last time mentioned by a model or a regular expression.
    for part in parts:
        requested_clocks = {_clock(m[1],m[2],m[3],explicit_colon=bool(m[2]))[0] for m in re.finditer(r'\ba las?\s+'+CLOCK_PATTERN,part)}
        requested_clocks.discard(None)
        if len(requested_clocks)>1:
            plan.reply, plan.missing = 'Hay varios horarios diferentes. Para prepararlos sin confusiones, indícame una actividad y su horario a la vez.', ['activity']
            return plan
    if plan.operation == 'delete' and not weekly and not explicit and not relative_date and re.search(r'\b(?:rutina|serie)\b',text):
        plan.reply, plan.missing = '¿Quieres detener toda la rutina o cancelar actividades de fechas concretas? Si son actividades concretas, indícame las fechas.', ['activity']
        return plan
    if weekly:
        if not weekdays:
            plan.missing.append('weekdays')
        has_start_phrase = bool(re.search(r'\b(?:desde|a partir|empieza|empezando|comienza|inicia|inicio)\b', text))
        if week_start is not None:
            start_bound = week_start
        elif not has_start_phrase and not (plan.operation == 'delete' and is_range):
            start_bound = None
        if start_bound is None:
            plan.missing.append('start')
        if week_count and start_bound:
            end_bound = start_bound+timedelta(days=week_count*7-1)
        elif len(explicit) >= 2 and re.search(r'\b(?:hasta|al|termina|fin)\b', text):
            end_bound = explicit[-1][1]
        elif len(explicit) == 1 and relative_date and has_start_phrase and re.search(r'\bhasta\b', text):
            start_bound, end_bound = relative_date, explicit[0][1]
        if plan.operation == 'delete':
            if week_start is not None and end_bound is None and not indefinite:
                end_bound = week_start+timedelta(days=7*(week_count or 1)-1)
            if end_bound is None or indefinite:
                plan.reply, plan.missing = '¿Quieres detener toda la rutina o cancelar actividades de fechas concretas? Si son actividades concretas, indícame las fechas.', ['activity']
                return plan
        if end_bound is None and not indefinite:
            plan.missing.append('end')
        if start_bound is not None and weekdays and (end_bound or indefinite):
            if end_bound and end_bound < start_bound:
                plan.reply, plan.missing = 'La fecha final es anterior al inicio. ¿Cuáles son las fechas correctas?', ['scope']
                return plan
            if plan.operation == 'delete':
                if (end_bound-start_bound).days > 84:
                    plan.reply, plan.missing = 'Para cancelar actividades concretas, indica un período de hasta 12 semanas. ¿Qué fechas quieres cancelar?', ['date']
                    return plan
                # Deleting bounded occurrences is never creation of a routine,
                # and must cover the whole explicitly requested interval.
                range_start, range_end = start_bound, end_bound
            else:
                plan.recurrence = {'weekdays':[day+1 for day in weekdays], 'starts_on':start_bound.isoformat(), 'ends_on':end_bound.isoformat() if end_bound else None, 'indefinite':indefinite}
                # Existing routine worker materializes the rolling four-week horizon.
                range_start = max(today, start_bound)
                range_end = min(end_bound or range_start+timedelta(days=27), range_start+timedelta(days=27))
            plan.dates = [range_start+timedelta(days=i) for i in range(max(0,(range_end-range_start).days+1)) if (range_start+timedelta(days=i)).weekday() in weekdays]
    elif weekdays and (week_start is not None or is_range or week_count and start_bound):
        begin = week_start if week_start is not None else start_bound
        finish = end_bound or begin+timedelta(days=7*(week_count or 1)-1)
        if finish < begin or (finish-begin).days > 84:
            plan.reply, plan.missing = 'Indica un período válido de hasta 12 semanas para crear estas actividades.', ['scope']
            return plan
        plan.dates = [begin+timedelta(days=i) for i in range((finish-begin).days+1) if (begin+timedelta(days=i)).weekday() in weekdays]
    elif plan.operation == 'update' and explicit:
        # In a move, earlier dates identify the source; the last mentioned
        # concrete/relative date is the destination, never a new series.
        candidates = explicit+[(m.start(),today+timedelta(days={'hoy':0,'manana':1,'pasado manana':2}[m.group()])) for m in relative]
        plan.dates = [max(candidates,key=lambda entry:entry[0])[1]]
    elif explicit and not is_range:
        plan.dates = sorted({d for _, d in explicit})
    elif relative_date:
        plan.dates = [relative_date]
    elif weekdays:
        plan.missing.append('scope')
    elif week_start is not None or week_count:
        plan.missing.append('weekdays')
    else:
        plan.missing.append('date')
    plan.start_clock, plan.end_clock, plan.end_day_offset, time_error = _times_with_clarifications(text)
    if plan.recurrence and plan.start_clock is not None and plan.start_clock == plan.end_clock and plan.end_day_offset:
        plan.reply, plan.missing = 'Las rutinas semanales necesitan una duración menor de 24 horas. ¿Cuánto debe durar cada sesión?', ['duration']
        return plan
    if plan.operation != 'delete':
        if time_error:
            plan.missing.append('clock_ambiguous')
        elif plan.start_clock is None:
            plan.missing.append('clock')
        if plan.end_clock is None:
            plan.missing.append('duration')
    if not plan.missing and not plan.dates:
        plan.missing.append('date')
    if plan.dates:
        context_dates = list(plan.dates)
        if plan.operation == 'update':
            context_dates.extend(d for _,d in explicit)
            context_dates.extend(today+timedelta(days={'hoy':0,'manana':1,'pasado manana':2}[m.group()]) for m in relative)
        plan.start_date, plan.end_date = min(context_dates), max(context_dates)
    if plan.missing:
        questions = []
        if 'scope' in plan.missing:
            questions.append('¿Sólo esta semana, la próxima semana o todas las semanas?')
        if 'date' in plan.missing:
            questions.append('¿Para qué fecha?')
        if 'weekdays' in plan.missing:
            questions.append('¿Qué días de la semana?')
        if 'start' in plan.missing:
            questions.append('¿Desde qué fecha debe comenzar la repetición?')
        if 'end' in plan.missing:
            questions.append('¿Hasta qué fecha o durante cuántas semanas? También puedes indicar «sin fecha final».')
        if 'clock_ambiguous' in plan.missing:
            questions.append(time_error)
        elif 'clock' in plan.missing:
            questions.append('¿A qué hora (por ejemplo, 15:00)?')
        if 'duration' in plan.missing:
            questions.append('¿Cuánto durará o a qué hora termina?')
        plan.reply = ' '.join(questions)
    return plan


def _pending_id(user_id: str, device_id: str | None) -> str:
    return 'agenda-' + hashlib.sha256(f'{user_id}\0{device_id or ""}'.encode()).hexdigest()[:40]


def _looks_like_answer(text: str, missing: list[str]) -> bool:
    if text.strip(' .!¿?') in ('si','no','cancelar','cancela','olvidalo','dejalo'):
        return True
    if re.search(r'^(?:¿|que\b|cual\b|cuanto\b|como\b|por que\b)', text.strip()):
        return False
    if 'activity' in missing and len(text) < 256:
        return True
    return bool(re.search(r'\b(?:hoy|manana|pasado|semana|semanas|desde|hasta|inicio|fecha|indefinidamente|' + DAY_PATTERN + '|' + '|'.join(MONTHS) + r')\b|\d|\b(?:media|una|dos) horas?\b', text))


async def prepare_agenda_intent(session, user_id, device_id, message, *, now, view_date=None) -> IntentPlan:
    """Read/advance only this device's short-lived pending calendar clarification.

    Caller owns the transaction and must commit even when ``reply`` short-circuits
    generation.  Unknown replies cannot accidentally inherit another request.
    """
    if isinstance(view_date, str):
        view_date = date.fromisoformat(view_date)
    if now.tzinfo is None:
        now = now.replace(tzinfo=ZoneInfo('America/Mexico_City'))
    instant = now.astimezone(timezone.utc).replace(tzinfo=None)
    key = _pending_id(user_id, device_id)
    pending = await session.get(ChatPendingAction, key)
    text = _plain(message)
    if pending and pending.expires_at <= instant:
        await session.delete(pending)
        await session.flush()
        pending = None
    effective, anchor = message, now
    if pending:
        if text.strip(' .!¿?') in ('no','cancelar','cancela','olvidalo','dejalo'):
            await session.delete(pending)
            return IntentPlan(message, now.date(), now.date(), reply='De acuerdo, cancelé esa preparación. No cambié tu agenda.')
        if _operation(text) == 'query' and _looks_like_answer(text, pending.payload.get('missing', [])) and not re.search(r'\b(?:que|cual|muestra|tengo|consulta|busca|archivo|documento)\b', text):
            if text.strip(' .!¿?') == 'si':
                return IntentPlan(message, now.date(), now.date(), reply=pending.payload['question'], is_mutation=True)
            effective = pending.payload['request'] + '\nAclaración del usuario: ' + message
            parsed_anchor = datetime.fromisoformat(pending.payload['anchor'])
            anchor = parsed_anchor.astimezone(ZoneInfo(pending.payload.get('timezone','America/Mexico_City')))
        elif _operation(text) != 'query':
            await session.delete(pending)
            await session.flush()
            pending = None
        else:
            return _plan(message, now, view_date)
    plan = _plan(effective, anchor, view_date)
    if plan.is_mutation and plan.reply:
        await remember_agenda_clarification(session,user_id,device_id,plan,plan.reply,now=now,missing=plan.missing)
    elif pending and effective != message:
        await session.delete(pending)
    return plan


async def remember_agenda_clarification(session, user_id, device_id, plan, question, *, now, missing=None):
    """Keep a server validation question in the same scoped, expiring workflow."""
    if now.tzinfo is None:
        now = now.replace(tzinfo=ZoneInfo(plan.timezone))
    instant = now.astimezone(timezone.utc).replace(tzinfo=None)
    anchor = plan.anchor or now
    payload = {'request':plan.effective_message, 'anchor':anchor.isoformat(), 'timezone':plan.timezone,
               'missing':missing if missing is not None else ['clock'], 'question':question}
    key = _pending_id(user_id,device_id)
    pending = await session.get(ChatPendingAction,key)
    if pending:
        pending.payload, pending.updated_at, pending.expires_at = payload, instant, instant+timedelta(minutes=30)
    else:
        session.add(ChatPendingAction(id=key,user_id=user_id,device_id=device_id,kind='agenda',payload=payload,
                                    expires_at=instant+timedelta(minutes=30),updated_at=instant))


def _valid_local_clock(day, clock, zone):
    wall = datetime.combine(day, clock)
    variants = [wall.replace(tzinfo=zone,fold=fold) for fold in (0,1)]
    valid = [candidate for candidate in variants if candidate.astimezone(timezone.utc).astimezone(zone).replace(tzinfo=None) == wall]
    return bool(valid) and len({candidate.utcoffset() for candidate in valid}) == 1


def constrain_proposal(plan: IntentPlan, proposal):
    """Bind a proposed template to verified dates, rejecting mixed/unclear blocks.

    Returns ``(proposal, None)`` or ``(None, clarification)``. Models never choose
    the calendar arithmetic, recurrence count, or ids of newly created events.
    """
    if not plan.is_mutation:
        return None, 'No preparé cambios porque no solicitaste modificar la agenda.'
    if plan.reply:
        return None, plan.reply
    if not proposal or not proposal.resulting_items:
        return None, 'No pude preparar esa actividad. ¿Qué título debe llevar?'
    if plan.operation == 'delete':
        if any(item.action != 'delete' for item in proposal.resulting_items):
            return None, '¿Cuál actividad quieres cancelar?'
        return proposal, None
    items = proposal.resulting_items
    if any(item.action == 'delete' for item in items):
        return None, 'La propuesta incluía una cancelación que no pediste. Indícame qué actividad quieres crear o mover.'
    signature = lambda item: (_plain(item.title).strip(), item.category, (item.description or '').strip())
    if len({signature(item) for item in items}) != 1:
        return None, 'Veo varias actividades distintas. Para confirmar sus fechas sin confusiones, indícame una actividad y su horario a la vez.'
    if plan.operation == 'update' and (len(items) != 1 or len(plan.dates) != 1):
        return None, '¿Qué actividad específica quieres mover y a qué fecha?'
    zone = ZoneInfo(plan.timezone)
    template = items[0]
    prepared = []
    for day in plan.dates:
        end_day = day+timedelta(days=plan.end_day_offset)
        if not _valid_local_clock(day,plan.start_clock,zone) or not _valid_local_clock(end_day,plan.end_clock,zone):
            return None, 'Ese horario coincide con un cambio de horario y es inexistente o ambiguo en tu zona. ¿Qué otra hora quieres usar?'
        begin = datetime.combine(day, plan.start_clock, zone)
        end = datetime.combine(day+timedelta(days=plan.end_day_offset), plan.end_clock, zone)
        prepared.append(template.model_copy(update={'id':template.id if plan.operation == 'update' else 'evt-chat-'+uuid.uuid4().hex, 'start_time':begin, 'end_time':end}))
    return proposal.model_copy(update={'resulting_items':prepared}), None
