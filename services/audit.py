import json
import os

import psycopg
from dotenv import load_dotenv


load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")


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
):
    if not DATABASE_URL:
        return {"id": None, "created_at": None}

    initialize_audit_table()
    details = details or {}

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
                    json.dumps(details),
                ),
            )
            record = cur.fetchone()
        conn.commit()

    return {
        "id": record[0],
        "created_at": record[1],
    }