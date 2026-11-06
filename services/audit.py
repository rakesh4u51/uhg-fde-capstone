import hashlib
import json
import os
import re
from collections.abc import Mapping
from typing import Any

import psycopg
from dotenv import load_dotenv


load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

_SENSITIVE_KEY_RE = re.compile(
    r"(password|secret|token|api[_-]?key|authorization|database[_-]?url|openrouter_api_key|anthropic_api_key|openai_api_key|smtp_password)",
    re.IGNORECASE,
)
_REDACTED_TEXT_KEYS = {
    "extracted_text",
    "document_text",
    "full_text",
    "body",
    "email_body",
    "raw_document",
    "mail_body",
    "content",
    "prompt",
    "system_prompt",
}

_AUDIT_SEEN_KEYS: set[str] = set()


def _safe_scalar(value: Any, *, max_chars: int = 180) -> Any:
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        text = value.strip()
        if len(text) > max_chars:
            return text[:max_chars] + "..."
        return text
    return str(value)[:max_chars]


def _sanitize_for_audit(value: Any) -> Any:
    if isinstance(value, Mapping):
        sanitized: dict[str, Any] = {}
        for key, item in value.items():
            normalized_key = str(key).lower()
            if _SENSITIVE_KEY_RE.search(str(key)):
                sanitized[str(key)] = "***REDACTED***"
                continue
            if normalized_key in _REDACTED_TEXT_KEYS:
                sanitized[str(key)] = "[redacted]"
                continue
            sanitized[str(key)] = _sanitize_for_audit(item)
        return sanitized
    if isinstance(value, list):
        return [_sanitize_for_audit(item) for item in value]
    if isinstance(value, tuple):
        return [_sanitize_for_audit(item) for item in value]
    if isinstance(value, set):
        return [_sanitize_for_audit(item) for item in sorted(value)]
    return _safe_scalar(value)


def _audit_dedupe_key(case_id: str, actor: str, action: str, details: dict[str, Any], stage: str | None = None) -> str:
    payload = {
        "case_id": case_id,
        "actor": actor,
        "action": action,
        "stage": stage,
        "details": details,
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def initialize_audit_table():
    if not DATABASE_URL:
        return None

    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS public.claim_audit (
                    id BIGSERIAL PRIMARY KEY,
                    case_id TEXT NOT NULL,
                    actor TEXT NOT NULL,
                    action TEXT NOT NULL,
                    details JSONB NOT NULL DEFAULT '{}'::jsonb,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
        conn.commit()

    return True


def record_audit(
    case_id: str,
    actor: str,
    action: str,
    details: dict | None = None,
    *,
    thread_id: str | None = None,
    stage: str | None = None,
    dedupe_key: str | None = None,
):
    if not isinstance(case_id, str) or not case_id.strip():
        raise ValueError("case_id is required for audit logging.")
    if not isinstance(actor, str) or not actor.strip():
        actor = "system"
    if not isinstance(action, str) or not action.strip():
        raise ValueError("action is required for audit logging.")

    if not DATABASE_URL:
        return {"id": None, "created_at": None, "duplicate": False}

    initialize_audit_table()
    safe_details = _sanitize_for_audit(details or {})
    dedupe_value = dedupe_key or _audit_dedupe_key(case_id.strip(), actor.strip(), action.strip(), safe_details, stage)
    if dedupe_value in _AUDIT_SEEN_KEYS:
        return {"id": None, "created_at": None, "duplicate": True}
    _AUDIT_SEEN_KEYS.add(dedupe_value)

    safe_details["_audit_key"] = dedupe_value
    if thread_id:
        safe_details["thread_id"] = str(thread_id)
    if stage:
        safe_details["stage"] = str(stage)

    try:
        payload = json.dumps(safe_details)
    except (TypeError, ValueError) as exc:
        raise RuntimeError(f"Audit details are not JSON serializable: {exc}") from exc

    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO public.claim_audit
                    (case_id, actor, action, details)
                VALUES
                    (%s, %s, %s, %s::jsonb)
                RETURNING id, created_at
                """,
                (
                    case_id,
                    actor,
                    action,
                    payload,
                ),
            )
            record = cur.fetchone()
        conn.commit()

    return {
        "id": record[0],
        "created_at": record[1],
        "duplicate": False,
    }