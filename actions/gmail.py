from __future__ import annotations

import base64
import re
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from googleapiclient.discovery import build

from actions.google_auth import get_google_creds


def _service():
    return build("gmail", "v1", credentials=get_google_creds(), cache_discovery=False)


def _make_message(to: str, subject: str, body: str, reply_to: str = "") -> dict:
    msg = MIMEMultipart()
    msg["To"]      = to
    msg["Subject"] = subject
    if reply_to:
        msg["In-Reply-To"] = reply_to
        msg["References"]  = reply_to
    msg.attach(MIMEText(body, "plain", "utf-8"))
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    return {"raw": raw}


def _decode_body(payload: dict) -> str:
    body = ""
    if payload.get("body", {}).get("data"):
        body = base64.urlsafe_b64decode(payload["body"]["data"]).decode("utf-8", errors="replace")
    elif payload.get("parts"):
        for part in payload["parts"]:
            if part.get("mimeType") == "text/plain" and part.get("body", {}).get("data"):
                body = base64.urlsafe_b64decode(part["body"]["data"]).decode("utf-8", errors="replace")
                break
    return body.strip()


def _header(msg: dict, name: str) -> str:
    headers = msg.get("payload", {}).get("headers", [])
    for h in headers:
        if h["name"].lower() == name.lower():
            return h["value"]
    return ""


def _send_email(params: dict) -> str:
    to      = params.get("to", "")
    subject = params.get("subject", "")
    body    = params.get("body", "")
    if not to or not body:
        return "Preciso do destinatário e do corpo do email."
    if not subject:
        subject = "Mensagem do ORION"

    msg = _make_message(to, subject, body)
    _service().users().messages().send(userId="me", body=msg).execute()
    return f"Email enviado para {to} com assunto '{subject}'."


def _list_emails(params: dict) -> str:
    query    = params.get("query", "is:unread")
    max_res  = int(params.get("max", 5))
    label    = params.get("label", "")

    q = query
    if label:
        q = f"label:{label} {q}"

    result = _service().users().messages().list(
        userId="me", q=q, maxResults=max_res
    ).execute()

    msgs = result.get("messages", [])
    if not msgs:
        return "Nenhum email encontrado."

    lines = [f"Encontrei {len(msgs)} email(s):"]
    svc = _service()
    for m in msgs:
        full = svc.users().messages().get(userId="me", id=m["id"], format="metadata",
                                          metadataHeaders=["From","Subject","Date"]).execute()
        sender  = _header(full, "From")
        subject = _header(full, "Subject") or "(sem assunto)"
        date    = _header(full, "Date")[:16] if _header(full, "Date") else ""
        lines.append(f"• [{date}] {subject} — de: {sender}")

    return "\n".join(lines)


def _read_email(params: dict) -> str:
    query   = params.get("query") or params.get("from") or params.get("subject", "")
    if not query:
        return "Me diga de quem ou qual assunto quer ler."

    result = _service().users().messages().list(
        userId="me", q=query, maxResults=1
    ).execute()

    msgs = result.get("messages", [])
    if not msgs:
        return f"Nenhum email encontrado com '{query}'."

    full    = _service().users().messages().get(userId="me", id=msgs[0]["id"], format="full").execute()
    sender  = _header(full, "From")
    subject = _header(full, "Subject") or "(sem assunto)"
    body    = _decode_body(full.get("payload", {}))

    if len(body) > 800:
        body = body[:800] + "…"

    return f"Email de: {sender}\nAssunto: {subject}\n\n{body}"


def _reply_email(params: dict) -> str:
    query   = params.get("query") or params.get("from") or params.get("subject", "")
    body    = params.get("body", "")
    if not query or not body:
        return "Preciso de qual email responder e o conteúdo da resposta."

    result = _service().users().messages().list(
        userId="me", q=query, maxResults=1
    ).execute()
    msgs = result.get("messages", [])
    if not msgs:
        return f"Email não encontrado com '{query}'."

    full       = _service().users().messages().get(userId="me", id=msgs[0]["id"], format="full").execute()
    sender     = _header(full, "From")
    subject    = _header(full, "Subject") or ""
    message_id = _header(full, "Message-ID")
    thread_id  = full.get("threadId")

    email_match = re.search(r"<(.+?)>", sender)
    to_addr     = email_match.group(1) if email_match else sender
    reply_subj  = subject if subject.startswith("Re:") else f"Re: {subject}"

    msg = _make_message(to_addr, reply_subj, body, reply_to=message_id)
    msg["threadId"] = thread_id
    _service().users().messages().send(userId="me", body=msg).execute()
    return f"Resposta enviada para {to_addr}."


def gmail(parameters: dict, player=None, **_) -> str:
    params = parameters or {}
    action = params.get("action", "list").lower().strip()
    print(f"[Gmail] {action}  {params}")
    if player:
        player.write_log(f"[Gmail] {action}")

    try:
        if action in ("send", "enviar", "mandar"):
            return _send_email(params)
        if action in ("list", "listar", "inbox", "não lidos"):
            return _list_emails(params)
        if action in ("read", "ler", "abrir", "ver"):
            return _read_email(params)
        if action in ("reply", "responder"):
            return _reply_email(params)
        return f"Ação desconhecida: '{action}'. Use: send, list, read, reply."
    except Exception as e:
        print(f"[Gmail] Erro: {e}")
        return f"Erro no Gmail: {e}"
