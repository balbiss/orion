import json
import threading
import time
import uuid
from datetime import datetime, date
from pathlib import Path

NOTES_FILE = Path.home() / ".jarvis_notes.json"
_notifier_started = False
_speak_callback = None


def set_speak_callback(fn):
    """Register the Orion speak function so reminders are spoken out loud."""
    global _speak_callback
    _speak_callback = fn


# ── Storage ────────────────────────────────────────────────────────────────

def _load() -> list:
    if not NOTES_FILE.exists():
        return []
    try:
        return json.loads(NOTES_FILE.read_text(encoding="utf-8"))
    except Exception:
        return []


def _save(notes: list):
    NOTES_FILE.write_text(
        json.dumps(notes, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


# ── Windows notification ───────────────────────────────────────────────────

def _notify(title: str, message: str):
    try:
        from win10toast import ToastNotifier
        ToastNotifier().show_toast(title, message, duration=8, threaded=True)
    except Exception:
        pass


def _speak_windows(text: str):
    """Fallback: use Windows SAPI to speak if Gemini session is unavailable."""
    try:
        import win32com.client
        speaker = win32com.client.Dispatch("SAPI.SpVoice")
        speaker.Speak(text)
    except Exception:
        pass


# ── Background checker ─────────────────────────────────────────────────────

def _background_checker():
    """Runs in background, checks for upcoming appointments every 60 seconds."""
    while True:
        try:
            notes = _load()
            now = datetime.now()
            today = now.date().isoformat()
            changed = False

            for note in notes:
                if note.get("notified"):
                    continue
                if note.get("date") != today:
                    continue
                note_time = note.get("time", "")
                if not note_time:
                    continue

                try:
                    scheduled = datetime.strptime(
                        f"{today} {note_time}", "%Y-%m-%d %H:%M"
                    )
                    diff = (scheduled - now).total_seconds()
                    if -60 <= diff <= 300:  # within next 5 min or just passed
                        msg = f"Sir, reminder: {note['text']}"
                        _notify("⏰ ORION — Compromisso", note["text"])
                        spoke = False
                        if _speak_callback:
                            try:
                                _speak_callback(msg)
                                spoke = True
                            except Exception as e:
                                print(f"[Notes] Speak error: {e}")
                        if not spoke:
                            _speak_windows(msg)
                        note["notified"] = True
                        changed = True
                        print(f"[Notes] 🔔 Notified: {note['text']}")
                except Exception:
                    pass

            if changed:
                _save(notes)
        except Exception as e:
            print(f"[Notes] Checker error: {e}")

        time.sleep(60)


def _ensure_notifier():
    global _notifier_started
    if not _notifier_started:
        t = threading.Thread(target=_background_checker, daemon=True)
        t.start()
        _notifier_started = True


# ── Actions ────────────────────────────────────────────────────────────────

def _add(text: str, note_date: str = None, note_time: str = None) -> str:
    notes = _load()
    today = date.today().isoformat()
    resolved_date = note_date or today

    note = {
        "id":         str(uuid.uuid4())[:8],
        "text":       text,
        "date":       resolved_date,
        "time":       note_time or "",
        "created_at": datetime.now().isoformat(),
        "notified":   False,
    }
    notes.append(note)
    _save(notes)

    # Also create a Task Scheduler reminder if date+time given
    if note_date and note_time:
        try:
            from actions.reminder import reminder
            reminder(parameters={
                "date":    note_date,
                "time":    note_time,
                "message": f"Compromisso: {text}",
            })
        except Exception as e:
            print(f"[Notes] Could not set reminder: {e}")

    extra = f" on {resolved_date}" + (f" at {note_time}" if note_time else "")
    return f"Saved: \"{text}\"{extra}."


def _list_today() -> str:
    notes = _load()
    today = date.today().isoformat()
    today_notes = [n for n in notes if n.get("date") == today]

    if not today_notes:
        return "No notes or appointments for today, sir."

    lines = [f"Today ({today}):"]
    for n in sorted(today_notes, key=lambda x: x.get("time") or ""):
        t = f" at {n['time']}" if n.get("time") else ""
        lines.append(f"  • {n['text']}{t}")
    return "\n".join(lines)


def _list_upcoming() -> str:
    notes = _load()
    today = date.today().isoformat()
    upcoming = [
        n for n in notes
        if n.get("date", "") >= today
    ]
    if not upcoming:
        return "No upcoming notes or appointments, sir."

    by_date: dict[str, list] = {}
    for n in upcoming:
        by_date.setdefault(n["date"], []).append(n)

    lines = []
    for d in sorted(by_date):
        lines.append(f"\n📅 {d}:")
        for n in sorted(by_date[d], key=lambda x: x.get("time") or ""):
            t = f" at {n['time']}" if n.get("time") else ""
            lines.append(f"  • {n['text']}{t}")
    return "\n".join(lines).strip()


def _search(query: str) -> str:
    notes = _load()
    hits = [n for n in notes if query.lower() in n["text"].lower()]
    if not hits:
        return f"No notes found for: \"{query}\"."
    lines = [f"Found {len(hits)} note(s):"]
    for n in hits:
        t = f" at {n['time']}" if n.get("time") else ""
        lines.append(f"  • [{n['date']}{t}] {n['text']}")
    return "\n".join(lines)


def _delete(note_id: str = None, text: str = None) -> str:
    notes = _load()
    before = len(notes)
    if note_id:
        notes = [n for n in notes if n["id"] != note_id]
    elif text:
        notes = [n for n in notes if text.lower() not in n["text"].lower()]
    _save(notes)
    return f"Deleted {before - len(notes)} note(s)."


def _clear_old() -> str:
    notes = _load()
    today = date.today().isoformat()
    kept = [n for n in notes if n.get("date", "") >= today]
    _save(kept)
    return f"Cleared {len(notes) - len(kept)} old note(s)."


# ── Entry point ────────────────────────────────────────────────────────────

def quick_notes(
    parameters:     dict,
    response=None,
    player=None,
    session_memory=None,
) -> str:
    _ensure_notifier()

    params = parameters or {}
    action = params.get("action", "today").lower().strip()

    if player:
        player.write_log(f"[Notes] {action}")
    print(f"[Notes] ▶ {action}  {params}")

    if action in ("add", "save", "create"):
        text = params.get("text", "").strip()
        if not text:
            return "Please provide the note text, sir."
        return _add(
            text=text,
            note_date=params.get("date"),
            note_time=params.get("time"),
        )

    if action in ("today", "list_today"):
        return _list_today()

    if action in ("upcoming", "list", "all"):
        return _list_upcoming()

    if action == "search":
        return _search(params.get("query", ""))

    if action == "delete":
        return _delete(
            note_id=params.get("id"),
            text=params.get("text") or params.get("query"),
        )

    if action == "clear_old":
        return _clear_old()

    return f"Unknown notes action: '{action}'. Use: add, today, upcoming, search, delete."
