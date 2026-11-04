from __future__ import annotations

import json
import os
from email.message import EmailMessage
from typing import Any, Callable

from apscheduler.schedulers.background import BackgroundScheduler
from dotenv import load_dotenv

load_dotenv()

MAILPIT_HOST = os.getenv("MAILPIT_HOST", "localhost")
MAILPIT_SMTP_PORT = int(os.getenv("MAILPIT_SMTP_PORT", "1025"))
MAILPIT_HTTP_PORT = int(os.getenv("MAILPIT_HTTP_PORT", "8025"))


def build_mailpit_message(to_address: str, subject: str, body: str, sender: str = "claims-demo@uhg.local") -> dict[str, Any]:
    return {
        "to": [to_address],
        "from": sender,
        "subject": subject,
        "body": body,
    }


def send_mailpit_email(to_address: str, subject: str, body: str, sender: str = "claims-demo@uhg.local") -> dict[str, Any]:
    """Send a message to a local Mailpit inbox if it is running. This is intended for demo and test environments."""
    try:
        import smtplib

        message = EmailMessage()
        message["From"] = sender
        message["To"] = to_address
        message["Subject"] = subject
        message.set_content(body)

        with smtplib.SMTP(MAILPIT_HOST, MAILPIT_SMTP_PORT) as smtp_client:
            smtp_client.send_message(message)
        return {"success": True, "to": to_address, "subject": subject}
    except Exception:
        payload = build_mailpit_message(to_address, subject, body, sender)
        return {"success": False, "message": "Mailpit not available; queued payload for demo use.", "payload": payload}


def schedule_follow_up(case_id: str, delay_hours: float = 24.0, callback: Callable | None = None) -> BackgroundScheduler:
    scheduler = BackgroundScheduler()
    scheduler.start()

    def _job() -> None:
        if callback:
            callback(case_id)

    scheduler.add_job(_job, "interval", hours=max(delay_hours, 0.01), id=f"sla-{case_id}", replace_existing=True)
    return scheduler


def get_mailpit_messages() -> list[dict[str, Any]]:
    import urllib.request

    url = f"http://{MAILPIT_HOST}:{MAILPIT_HTTP_PORT}/api/v1/messages"
    try:
        with urllib.request.urlopen(url, timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))
            return payload.get("messages", [])
    except Exception:
        return []
