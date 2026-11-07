from __future__ import annotations

import json
import os
from datetime import datetime, timedelta
from email.message import EmailMessage
from typing import Any, Callable

from apscheduler.schedulers.background import BackgroundScheduler
from dotenv import load_dotenv

from services.audit import record_audit

load_dotenv()

MAILPIT_HOST = os.getenv("MAILPIT_HOST", "localhost")
MAILPIT_SMTP_PORT = int(os.getenv("MAILPIT_SMTP_PORT", "1025"))
MAILPIT_HTTP_PORT = int(os.getenv("MAILPIT_HTTP_PORT", "8025"))

_DEFAULT_SCHEDULER: BackgroundScheduler | None = None


def get_scheduler() -> BackgroundScheduler:
    global _DEFAULT_SCHEDULER
    if _DEFAULT_SCHEDULER is None or not getattr(_DEFAULT_SCHEDULER, "running", False):
        _DEFAULT_SCHEDULER = BackgroundScheduler()
        _DEFAULT_SCHEDULER.start()
    return _DEFAULT_SCHEDULER


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


def notify_missing_documents(case_id: str, recipient: str, missing_documents: list[str]) -> dict[str, Any]:
    subject = f"Missing Documents for {case_id}"
    body = (
        f"Case {case_id} is waiting for the following supporting documents: "
        + ", ".join(missing_documents)
        + "."
    )
    result = send_mailpit_email(recipient, subject, body)
    record_audit(
        case_id,
        "workflow_mcp",
        "notification_sent",
        {
            "notification_type": "missing_documents",
            "recipient": recipient,
            "subject": subject,
            "missing_documents": list(missing_documents),
        },
    )
    return result


def notify_approval_request(case_id: str, approver: str, claim_amount: float | int) -> dict[str, Any]:
    subject = f"Approval request for {case_id}"
    body = (
        f"Case {case_id} requires human approval. "
        f"Claim amount: {float(claim_amount):,.2f}. "
        f"Reviewer: {approver}."
    )
    result = send_mailpit_email(approver.lower().replace(" ", ".") + "@example.com", subject, body)
    record_audit(
        case_id,
        "workflow_mcp",
        "notification_sent",
        {
            "notification_type": "approval_request",
            "recipient": approver.lower().replace(" ", ".") + "@example.com",
            "subject": subject,
            "claim_amount": float(claim_amount),
        },
    )
    return result


def notify_sla_escalation(case_id: str, recipient: str, delay_hours: float = 24.0) -> dict[str, Any]:
    subject = f"SLA escalation for {case_id}"
    body = f"Case {case_id} has reached the SLA escalation threshold after {delay_hours} hours."
    result = send_mailpit_email(recipient, subject, body)
    record_audit(
        case_id,
        "sla_agent",
        "sla_escalated",
        {
            "recipient": recipient,
            "delay_hours": float(delay_hours),
            "reason": "sla_threshold_reached",
        },
    )
    return result


def schedule_case_follow_up(
    case_id: str,
    delay_hours: float = 24.0,
    callback: Callable | None = None,
    job_name: str = "sla",
) -> BackgroundScheduler:
    scheduler = get_scheduler()

    def _job() -> None:
        if callback:
            callback(case_id)

    run_at = datetime.now() + timedelta(hours=max(float(delay_hours), 0.01))
    scheduler.add_job(
        _job,
        "date",
        run_date=run_at,
        id=f"{job_name}-{case_id}",
        replace_existing=True,
    )
    return scheduler


def schedule_follow_up(case_id: str, delay_hours: float = 24.0, callback: Callable | None = None) -> BackgroundScheduler:
    return schedule_case_follow_up(case_id, delay_hours=delay_hours, callback=callback, job_name="sla")


def get_mailpit_messages() -> list[dict[str, Any]]:
    import urllib.request

    url = f"http://{MAILPIT_HOST}:{MAILPIT_HTTP_PORT}/api/v1/messages"
    try:
        with urllib.request.urlopen(url, timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))
            return payload.get("messages", [])
    except Exception:
        return []
