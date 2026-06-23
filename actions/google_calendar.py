from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from googleapiclient.discovery import build

from actions.google_auth import get_google_creds

TZ = ZoneInfo("America/Sao_Paulo")


def _service():
    return build("calendar", "v3", credentials=get_google_creds(), cache_discovery=False)


def _parse_dt(date_str: str, time_str: str = "") -> datetime:
    fmt = "%Y-%m-%d %H:%M" if time_str else "%Y-%m-%d"
    raw = f"{date_str} {time_str}".strip()
    dt  = datetime.strptime(raw, fmt)
    return dt.replace(tzinfo=TZ)


def _fmt_event(ev: dict) -> str:
    summary = ev.get("summary", "Sem título")
    start   = ev.get("start", {})
    dt_str  = start.get("dateTime") or start.get("date", "")
    if "T" in dt_str:
        dt = datetime.fromisoformat(dt_str)
        when = dt.strftime("%d/%m às %H:%M")
    else:
        when = dt_str
    loc = f" — {ev['location']}" if ev.get("location") else ""
    return f"• {summary} ({when}{loc})"


def _list_events(params: dict) -> str:
    when   = params.get("when", "hoje").lower()
    now    = datetime.now(TZ)

    if when in ("hoje", "today"):
        t_min = now.replace(hour=0, minute=0, second=0, microsecond=0)
        t_max = t_min + timedelta(days=1)
        label = "hoje"
    elif when in ("amanhã", "amanha", "tomorrow"):
        t_min = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        t_max = t_min + timedelta(days=1)
        label = "amanhã"
    elif when in ("semana", "week", "essa semana"):
        t_min = now
        t_max = now + timedelta(days=7)
        label = "nos próximos 7 dias"
    else:
        t_min = now
        t_max = now + timedelta(days=30)
        label = "no próximo mês"

    result = _service().events().list(
        calendarId="primary",
        timeMin=t_min.isoformat(),
        timeMax=t_max.isoformat(),
        singleEvents=True,
        orderBy="startTime",
        maxResults=15,
    ).execute()

    events = result.get("items", [])
    if not events:
        return f"Nenhum compromisso {label}, senhor."

    lines = [f"Seus compromissos {label}:"]
    lines += [_fmt_event(e) for e in events]
    return "\n".join(lines)


def _create_event(params: dict) -> str:
    title    = params.get("title", "Compromisso")
    date_str = params.get("date", "")
    time_str = params.get("time", "")
    duration = int(params.get("duration_minutes", 60))
    location = params.get("location", "")
    desc     = params.get("description", "")
    guests   = params.get("guests", [])

    if not date_str:
        return "Preciso da data para criar o evento."

    start_dt = _parse_dt(date_str, time_str)
    end_dt   = start_dt + timedelta(minutes=duration)

    body: dict = {
        "summary":  title,
        "start":    {"dateTime": start_dt.isoformat(), "timeZone": "America/Sao_Paulo"},
        "end":      {"dateTime": end_dt.isoformat(),   "timeZone": "America/Sao_Paulo"},
    }
    if location:
        body["location"] = location
    if desc:
        body["description"] = desc
    if guests:
        body["attendees"] = [{"email": g.strip()} for g in (guests if isinstance(guests, list) else [guests])]

    ev = _service().events().insert(calendarId="primary", body=body, sendUpdates="all").execute()
    when = start_dt.strftime("%d/%m às %H:%M")
    return f"Evento criado: '{title}' em {when}. ID: {ev['id'][:8]}"


def _delete_event(params: dict) -> str:
    query = params.get("title") or params.get("query", "")
    date  = params.get("date", "")
    if not query:
        return "Me diga o nome do evento para cancelar."

    now    = datetime.now(TZ)
    t_min  = now if not date else _parse_dt(date)
    t_max  = t_min + timedelta(days=30)

    result = _service().events().list(
        calendarId="primary",
        q=query,
        timeMin=t_min.isoformat(),
        timeMax=t_max.isoformat(),
        singleEvents=True,
        orderBy="startTime",
        maxResults=5,
    ).execute()

    events = result.get("items", [])
    if not events:
        return f"Nenhum evento encontrado com '{query}'."
    if len(events) > 1:
        lines = ["Encontrei mais de um evento. Qual deles?"]
        lines += [_fmt_event(e) + f" [ID: {e['id'][:8]}]" for e in events]
        return "\n".join(lines)

    ev = events[0]
    _service().events().delete(calendarId="primary", eventId=ev["id"]).execute()
    return f"Evento '{ev.get('summary')}' cancelado com sucesso."


def _find_free_slots(params: dict) -> str:
    date     = params.get("date", "")
    duration = int(params.get("duration_minutes", 60))
    if not date:
        return "Me diga a data para verificar horários livres."

    t_min = _parse_dt(date, "08:00")
    t_max = _parse_dt(date, "20:00")

    result = _service().events().list(
        calendarId="primary",
        timeMin=t_min.isoformat(),
        timeMax=t_max.isoformat(),
        singleEvents=True,
        orderBy="startTime",
    ).execute()

    events = result.get("items", [])
    busy   = []
    for ev in events:
        s = ev["start"].get("dateTime")
        e = ev["end"].get("dateTime")
        if s and e:
            busy.append((datetime.fromisoformat(s), datetime.fromisoformat(e)))

    slots = []
    cursor = t_min
    for s, e in sorted(busy):
        if (s - cursor).total_seconds() >= duration * 60:
            slots.append(f"{cursor.strftime('%H:%M')} – {s.strftime('%H:%M')}")
        cursor = max(cursor, e)
    if (t_max - cursor).total_seconds() >= duration * 60:
        slots.append(f"{cursor.strftime('%H:%M')} – {t_max.strftime('%H:%M')}")

    if not slots:
        return f"Sem horários livres de {duration} min em {date}."
    return f"Horários livres em {date}:\n" + "\n".join(f"• {s}" for s in slots)


def google_calendar(parameters: dict, player=None, **_) -> str:
    params = parameters or {}
    action = params.get("action", "list").lower().strip()
    print(f"[Calendar] {action}  {params}")
    if player:
        player.write_log(f"[Calendar] {action}")

    try:
        if action in ("list", "listar", "hoje", "amanhã", "semana"):
            return _list_events(params)
        if action in ("create", "criar", "agendar", "add"):
            return _create_event(params)
        if action in ("delete", "deletar", "cancelar", "remover"):
            return _delete_event(params)
        if action in ("free", "livre", "horários livres", "disponibilidade"):
            return _find_free_slots(params)
        return f"Ação desconhecida: '{action}'. Use: list, create, delete, free."
    except Exception as e:
        print(f"[Calendar] Erro: {e}")
        return f"Erro no Google Calendar: {e}"
