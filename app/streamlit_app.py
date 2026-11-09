import asyncio
import os
import re
import sys
import uuid
from decimal import Decimal
from pathlib import Path
from typing import Any

import psycopg
import streamlit as st
from dotenv import load_dotenv
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.types import Command
from psycopg.rows import dict_row

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from graph.v2_graph_factory import get_v2_graph
from services.approver_validation import get_approver_directory, get_eligible_approvers, validate_approver_limit
from services.audit import initialize_audit_table, record_audit
from services.database import DATABASE_URL
from services.document_processor import process_document, save_document_result
from services.notifications import get_mailpit_messages

load_dotenv()
initialize_audit_table()

st.set_page_config(
    page_title="Intelligent Claims Processing",
    page_icon="⚕️",
    layout="wide",
)

st.markdown(
    """
    <style>
        :root {
            --bg: #f8fafc;
            --panel: rgba(255,255,255,0.86);
            --panel-border: rgba(148,163,184,0.18);
            --text: #0f172a;
            --muted: #475569;
            --blue: #2563eb;
            --green: #16a34a;
            --amber: #d97706;
            --red: #dc2626;
            --purple: #7c3aed;
            --gray: #64748b;
        }

        * { font-family: "Segoe UI", "Inter", sans-serif; }
        .stApp { background: var(--bg); color: var(--text); }
        .block-container,
        [data-testid="stMainBlockContainer"] {
            padding-top: 1.1rem !important;
            padding-bottom: 1rem !important;
            padding-left: 1.4rem !important;
            padding-right: 1.4rem !important;
            max-width: 1500px;
            overflow: visible !important;
        }
        [data-testid="stSidebar"] {
            background: #111827;
            color: #fff;
            border-right: 1px solid rgba(148,163,184,0.24);
        }
        [data-testid="stSidebar"] .stMarkdown,
        [data-testid="stSidebar"] p,
        [data-testid="stSidebar"] div,
        [data-testid="stSidebar"] span,
        [data-testid="stSidebar"] label,
        [data-testid="stSidebar"] .stRadio {
            color: #fff !important;
        }
        [data-testid="stSidebar"] .stRadio > div { gap: 0.5rem; }
        [role="radiogroup"] {
            display: flex;
            flex-direction: column;
            gap: 0.55rem;
            padding-top: 0.15rem;
        }
        [role="radiogroup"] > label {
            background: rgba(255,255,255,0.04) !important;
            border: 1px solid rgba(148,163,184,0.14);
            border-radius: 10px;
            padding: 0.55rem 0.7rem;
            margin: 0;
            color: #fff !important;
            font-weight: 600;
        }
        [role="radiogroup"] > label[data-checked="true"] {
            background: rgba(37,99,235,0.16) !important;
            border-color: rgba(96,165,250,0.7);
            box-shadow: 0 0 0 1px rgba(96,165,250,0.2);
        }
        h1, h2, h3, h4 {
            color: var(--text);
            letter-spacing: -0.03em;
            margin-top: 0;
            margin-bottom: 0.25rem;
            line-height: 1.25;
        }
        h1 { font-size: 1.85rem; }
        h2 { font-size: 1.55rem; }
        h3 { font-size: 1.1rem; }
        p, div, label, span { font-size: 0.92rem; }
        .stMetric {
            background: var(--panel);
            border: 1px solid var(--panel-border);
            border-radius: 12px;
            box-shadow: 0 8px 18px rgba(15,23,42,0.03);
            padding: 0.35rem 0.6rem;
        }
        [data-testid="stMetricValue"] {
            font-size: 1.45rem;
            font-weight: 700;
        }
        .compact-header {
            background: rgba(255,255,255,0.02);
            border: 1px solid rgba(148,163,184,0.08);
            border-radius: 10px;
            padding: 0.55rem 0.6rem 0.4rem 0.6rem;
            margin: 0 0 0.45rem 0;
            box-shadow: none;
        }
        .compact-header .title {
            font-size: 0.96rem;
            font-weight: 700;
            color: #ffffff;
            line-height: 1.15;
            letter-spacing: -0.02em;
        }
        .compact-header .subtitle {
            margin-top: 0.16rem;
            color: rgba(255,255,255,0.72);
            font-size: 0.64rem;
            letter-spacing: 0.08em;
            text-transform: uppercase;
        }
        .page-header {
            margin: 0 0 0.8rem 0;
            padding: 0;
            overflow: visible;
        }
        .page-header h2 {
            margin: 0;
            padding: 0;
            font-size: 1.55rem;
            line-height: 1.25;
            letter-spacing: -0.03em;
            overflow: visible;
            display: block;
        }
        .page-header .subtitle {
            margin-top: 0.3rem;
            margin-bottom: 0;
            color: var(--muted);
            font-size: 0.78rem;
            line-height: 1.4;
            overflow: visible;
        }
        .workflow-track {
            display: flex;
            flex-wrap: wrap;
            gap: 0.4rem;
            align-items: center;
            padding: 0.45rem 0.2rem 0.1rem;
        }
        .workflow-step {
            display: inline-flex;
            align-items: center;
            gap: 0.35rem;
            padding: 0.38rem 0.62rem;
            border-radius: 999px;
            border: 1px solid #dfe7f1;
            background: #f8fafc;
            color: var(--muted);
            font-size: 0.78rem;
            font-weight: 600;
            white-space: nowrap;
        }
        .workflow-step.complete { background: rgba(22,163,74,0.1); border-color: rgba(22,163,74,0.25); color: #166534; }
        .workflow-step.current { background: rgba(37,99,235,0.1); border-color: rgba(37,99,235,0.28); color: #1d4ed8; }
        .workflow-step.pending { background: #f8fafc; border-color: #e2e8f0; color: #64748b; }
        .workflow-step.exception { background: rgba(220,38,38,0.08); border-color: rgba(220,38,38,0.2); color: #b91c1c; }
        .workflow-arrow {
            font-size: 0.9rem;
            color: #94a3b8;
            margin: 0 0.1rem 0 -0.1rem;
        }
        .panel-box {
            background: rgba(255,255,255,0.85);
            border: 1px solid var(--panel-border);
            border-radius: 12px;
            padding: 0.7rem 0.8rem;
            margin-bottom: 0.75rem;
        }
        .status-card {
            background: rgba(37,99,235,0.05);
            border: 1px solid rgba(37,99,235,0.18);
            border-radius: 12px;
            padding: 0.7rem 0.8rem;
            margin-bottom: 0.7rem;
        }
        .status-card .title { font-size: 0.82rem; font-weight: 700; color: var(--blue); letter-spacing: 0.08em; text-transform: uppercase; }
        .status-item { font-size: 0.88rem; margin: 0.18rem 0; }
        .status-item.done { color: var(--green); }
        .status-item.active { color: var(--blue); font-weight: 600; }
        .status-item.pending { color: var(--gray); }
        .status-item.exception { color: var(--red); font-weight: 600; }
        .stDataFrame { border-radius: 12px; overflow: hidden; }
        div[data-testid="stExpander"] > div { border-radius: 10px; }
        .stButton > button {
            background: linear-gradient(135deg, #2563eb 0%, #1d4ed8 100%);
            color: white;
            border: none;
            border-radius: 10px;
            padding: 0.58rem 0.9rem;
            font-weight: 600;
        }
        .stButton > button:hover { filter: brightness(1.04); }
        .stForm, .stAlert { border-radius: 12px; }
        .stTextInput input, .stSelectbox select, .stNumberInput input, .stTextArea textarea {
            border-radius: 10px !important;
            border: 1px solid rgba(148,163,184,0.28) !important;
            min-height: 2rem !important;
            padding: 0.35rem 0.55rem !important;
        }
        .stTextArea textarea { min-height: 3rem !important; }
        .section-label {
            font-size: 0.76rem;
            font-weight: 700;
            letter-spacing: 0.08em;
            text-transform: uppercase;
            color: var(--muted);
            margin-bottom: 0.3rem;
        }
        .compact-list p { margin: 0.18rem 0; }
    </style>
    """,
    unsafe_allow_html=True,
)

st.sidebar.markdown(
    """
    <div class="compact-header">
        <div class="title">Intelligent Claims</div>
        <div class="title">Processing</div>
        <div class="subtitle">Claims Operations</div>
    </div>
    """,
    unsafe_allow_html=True,
)

page = st.sidebar.radio(
    "Navigation",
    [
        "Submit Claim",
        "Case Queue",
        "Case Workspace",
        "Manual Review Queue",
        "Human Review Queue",
        "Notifications",
        "Audit",
    ],
    key="sidebar_navigation",
)

if page == "Manual Review Queue":
    page = "Manual Review"
elif page == "Human Review Queue":
    page = "Human Review"


def format_status(value: Any) -> str:
    status = _canonical_case_status(value)
    labels = {
        "submitted": "Submitted",
        "processing": "Processing",
        "validated": "Validated",
        "intake": "Intake",
        "documents_processing": "Processing Documents",
        "awaiting_documents": "Awaiting Documents",
        "documents_revalidated": "Documents Revalidated",
        "manual_review": "Manual Review",
        "manual_review_held": "Manual Review",
        "awaiting_human_review": "Human Review",
        "human_review": "Human Review",
        "human_decision_received": "Human Review",
        "completed": "Completed",
        "rejected": "Rejected",
        "hold": "On Hold",
    }
    if status in labels:
        return labels[status]
    return status.replace("_", " ").title() if status else "Unknown"


def format_currency(value: Any) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    if number == 0:
        return "₹0"
    return f"₹{number:,.0f}"


def render_page_header(title: str, subtitle: str | None = None) -> None:
    st.markdown(
        """
        <div class="page-header">
            <h2>{title}</h2>
            {subtitle_html}
        </div>
        """.format(
            title=title,
            subtitle_html=f'<div class="subtitle">{subtitle}</div>' if subtitle else "",
        ),
        unsafe_allow_html=True,
    )


def _status_display_label(status: Any) -> str:
    return format_status(status)


def _render_processing_status(step_index: int = 0) -> None:
    steps = [
        "Validating claim",
        "Running Intake",
        "Processing Documents",
        "Creating Summary",
        "Routing Claim",
        "Setting SLA",
        "Human Review",
    ]
    html = """
    <div class="status-card">
        <div class="title">Processing Claim</div>
    """
    for idx, label in enumerate(steps):
        if idx < step_index:
            css_class = "done status-item"
            icon = "✓"
        elif idx == step_index:
            css_class = "active status-item"
            icon = "●"
        else:
            css_class = "pending status-item"
            icon = "○"
        html += f'<div class="{css_class}">{icon} {label}</div>'
    html += "</div>"
    st.markdown(html, unsafe_allow_html=True)


def _render_workflow_progress(status: Any, *, label: str = "Workflow Progress") -> None:
    normalized = _canonical_case_status(status)
    steps = [
        {"key": "submitted", "label": "Submitted"},
        {"key": "validation", "label": "Validation"},
        {"key": "intake", "label": "Intake"},
        {"key": "documents", "label": "Documents"},
        {"key": "summary", "label": "Summary"},
        {"key": "routing", "label": "Routing"},
        {"key": "sla", "label": "SLA"},
        {"key": "human_review", "label": "Human Review"},
        {"key": "completed", "label": "Completed"},
    ]
    stage_positions = {
        "submitted": 0,
        "processing": 0,
        "intake": 2,
        "documents_processing": 3,
        "awaiting_documents": 3,
        "documents_revalidated": 3,
        "manual_review": 3,
        "manual_review_held": 3,
        "summary": 4,
        "routing": 5,
        "sla": 6,
        "awaiting_human_review": 7,
        "human_review": 7,
        "human_decision_received": 7,
        "completed": 8,
    }
    current_index = stage_positions.get(normalized, 0)
    if normalized in {"error", "rejected"}:
        current_index = 0
    html = f'<div class="section-label">{label}</div><div class="workflow-track">'
    for idx, step in enumerate(steps):
        if normalized in {"error", "rejected"}:
            css_class = "workflow-step exception"
        elif idx < current_index:
            css_class = "workflow-step complete"
        elif idx == current_index:
            css_class = "workflow-step current"
        else:
            css_class = "workflow-step pending"
        if idx < len(steps) - 1:
            html += f'<div class="{css_class}">● {step["label"]}</div><div class="workflow-arrow">→</div>'
        else:
            html += f'<div class="{css_class}">● {step["label"]}</div>'
    html += '</div>'
    st.markdown(html, unsafe_allow_html=True)


def _safe_error_details(exc: Exception) -> str:
    raw = str(exc or "")
    if not raw.strip():
        return "Workflow error details unavailable."
    redacted = raw
    patterns = [
        r"(?i)(DATABASE_URL|password|api[_-]?key|secret|token)=([^\s,;]+)",
        r"(?i)(DATABASE_URL|password|api[_-]?key|secret|token)\s*[:=]\s*([^\s,;]+)",
    ]
    for pattern in patterns:
        redacted = re.sub(pattern, r"\1=[REDACTED]", redacted)
    return redacted


def _display_value(value: Any) -> str:
    if value is None:
        return "—"
    if isinstance(value, Decimal):
        return f"{float(value):,.2f}"
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return f"{float(value):,.2f}"
    return str(value)


def _case_record(case_id: str) -> dict[str, Any] | None:
    with psycopg.connect(DATABASE_URL, row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    case_id,
                    policy_number,
                    claimant_name,
                    claim_type,
                    claim_amount,
                    description,
                    status,
                    summary,
                    created_at,
                    updated_at
                FROM public.claims
                WHERE case_id = %s
                """,
                (case_id,),
            )
            row = cur.fetchone()
    if row is None:
        return None
    row["status"] = _canonical_case_status(row.get("status"))
    return row


def _canonical_case_status(status: Any) -> str:
    value = str(status or "").strip().lower()
    if not value:
        return ""
    aliases = {
        "awaiting_document": "awaiting_documents",
        "awaiting_documents2": "awaiting_documents",
        "awaiting_documents_2": "awaiting_documents",
        "documents_waiting": "awaiting_documents",
    }
    return aliases.get(value, value)


def _workflow_stage_steps() -> list[str]:
    return [
        "submitted",
        "documents_processing",
        "awaiting_documents",
        "manual_review",
        "awaiting_human_review",
        "human_review",
        "completed",
    ]


def _workflow_stage_index(status: Any) -> int:
    normalized = _canonical_case_status(status)
    order = {stage: idx for idx, stage in enumerate(_workflow_stage_steps())}
    return order.get(normalized, 0)


def _render_workflow_status_bar(status: Any, *, label: str = "Workflow status") -> None:
    normalized = _canonical_case_status(status)
    steps = _workflow_stage_steps()
    current = _workflow_stage_index(normalized)
    total = max(len(steps) - 1, 1)
    progress = min(max(current / total, 0.0), 1.0)
    stage_name = {
        "submitted": "Submitted",
        "documents_processing": "Document Intake",
        "awaiting_documents": "Awaiting Documents",
        "manual_review": "Manual Review",
        "awaiting_human_review": "Awaiting Human Review",
        "human_review": "Human Review",
        "completed": "Completed",
    }.get(normalized, normalized or "Unknown")

    st.caption(f"{label}: {stage_name}")
    st.progress(progress, text=f"{stage_name} ({current}/{len(steps)-1})")


def _queue_cases() -> list[dict[str, Any]]:
    with psycopg.connect(DATABASE_URL, row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    case_id,
                    claimant_name,
                    claim_type,
                    claim_amount,
                    status,
                    created_at
                FROM public.claims
                ORDER BY created_at DESC
                """
            )
            rows = cur.fetchall()
    for row in rows:
        row["status"] = _canonical_case_status(row.get("status"))
    return rows


def _requested_documents_for_case(case_id: str) -> list[str]:
    with psycopg.connect(DATABASE_URL, row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT details
                FROM public.claim_audit
                WHERE case_id = %s AND action = 'documents_requested'
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (case_id,),
            )
            row = cur.fetchone()
    details = row.get("details") if row else {}
    if isinstance(details, dict):
        requested = details.get("requested_documents") or details.get("missing_documents") or ["supporting_document"]
        return [str(doc).strip() for doc in requested if str(doc).strip()]
    if isinstance(details, str):
        return [details.strip()] if details.strip() else ["supporting_document"]
    return ["supporting_document"]


def _resume_existing_case_documents(case_id: str, uploaded_files) -> dict[str, Any]:
    if not case_id:
        raise ValueError("A case_id is required to resume an existing case.")

    if not uploaded_files:
        raise ValueError("At least one document is required before resuming the case workflow.")

    thread_id = _recover_thread_id_for_case(case_id)
    if not thread_id:
        raise ValueError(f"No persisted workflow execution was found for case {case_id}.")

    saved: list[dict[str, Any]] = []
    for uploaded_file in uploaded_files or []:
        if uploaded_file is None or not getattr(uploaded_file, "name", None):
            continue
        upload_dir = Path("uploads") / case_id
        upload_dir.mkdir(parents=True, exist_ok=True)
        destination = upload_dir / uploaded_file.name
        destination.write_bytes(uploaded_file.getvalue())
        processed = process_document(str(destination))
        document_id = f"DOC-{uuid.uuid4().hex[:8].upper()}"
        payload = save_document_result(case_id, str(destination), document_id=document_id, result=processed)
        saved.append(payload)

    if not saved:
        raise ValueError("No document was saved for the selected case.")

    latest = saved[-1]
    resume_payload = {
        "case_id": case_id,
        "document_id": latest.get("document_id"),
        "document_text": latest.get("extracted_text") or "",
        "document_type": latest.get("document_type") or "unknown",
        "document_confidence": float(latest.get("confidence") or 0.0),
    }

    async def _run() -> dict[str, Any]:
        async with get_v2_graph() as graph:
            config = {"configurable": {"thread_id": thread_id}}
            snapshot = await graph.aget_state(config)
            state_values = snapshot.values if snapshot else {}
            if not state_values:
                raise ValueError(f"No LangGraph checkpoint exists for thread {thread_id}.")
            if "claim_data" not in state_values:
                raise ValueError("The persisted LangGraph checkpoint does not contain claim_data.")
            current_stage = state_values.get("current_stage")
            current_status = _canonical_case_status(state_values.get("status"))
            allowed_stages = {
                "awaiting_documents",
                "documents_processing",
                "documents_revalidated",
                "manual_review",
                "manual_review_held",
            }
            allowed_statuses = {
                "awaiting_documents",
                "documents_processing",
                "manual_review",
                "manual_review_held",
                "documents_revalidated",
            }
            if current_stage not in allowed_stages and current_status not in allowed_statuses:
                raise ValueError(
                    "The case is not currently paused for document resubmission. "
                    f"Stage: {current_stage}; status: {current_status}."
                )
            return await graph.ainvoke(Command(resume=resume_payload), config=config)

    return asyncio.run(_run())


def _list_documents(case_id: str) -> list[dict[str, Any]]:
    with psycopg.connect(DATABASE_URL, row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    document_id,
                    case_id,
                    file_name,
                    document_type,
                    extracted_text,
                    confidence,
                    injection_detected,
                    created_at
                FROM public.documents
                WHERE case_id = %s
                ORDER BY created_at DESC
                """,
                (case_id,),
            )
            rows = cur.fetchall()
    return rows


def _insert_case(case_id: str, policy_number: str, claimant_name: str, claim_type: str, claim_amount: float, description: str) -> dict[str, Any]:
    with psycopg.connect(DATABASE_URL, row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO public.claims (
                    case_id,
                    policy_number,
                    claimant_name,
                    claim_type,
                    claim_amount,
                    description,
                    status
                ) VALUES (%s, %s, %s, %s, %s, %s, 'submitted')
                ON CONFLICT (case_id) DO UPDATE SET
                    policy_number = EXCLUDED.policy_number,
                    claimant_name = EXCLUDED.claimant_name,
                    claim_type = EXCLUDED.claim_type,
                    claim_amount = EXCLUDED.claim_amount,
                    description = EXCLUDED.description,
                    updated_at = NOW()
                RETURNING case_id, policy_number, claimant_name, claim_type, claim_amount, description, status
                """,
                (case_id, policy_number, claimant_name, claim_type, claim_amount, description),
            )
            row = cur.fetchone()
        conn.commit()
    return row


def _persist_uploaded_documents(case_id: str, uploaded_files) -> list[dict[str, Any]]:
    upload_dir = Path("uploads") / case_id
    upload_dir.mkdir(parents=True, exist_ok=True)

    saved: list[dict[str, Any]] = []
    for uploaded_file in uploaded_files or []:
        if not uploaded_file or not getattr(uploaded_file, "name", None):
            continue

        destination = upload_dir / uploaded_file.name
        destination.write_bytes(uploaded_file.getvalue())
        processed = process_document(str(destination))
        document_id = f"DOC-{uuid.uuid4().hex[:8].upper()}"
        payload = save_document_result(case_id, str(destination), document_id=document_id, result=processed)
        print("[UI] Document persisted:", payload.get("document_id"))
        saved.append(payload)

    return saved


def _hydrate_claim_data(case_id: str, claim_data: dict[str, Any] | None) -> dict[str, Any]:
    payload = dict(claim_data or {})
    payload["case_id"] = case_id
    payload.setdefault("document_text", "")
    payload.setdefault("document_type", "unknown")
    payload.setdefault("document_confidence", 0.0)
    payload.setdefault("document_ids", [])

    documents = _list_documents(case_id)
    if documents:
        payload["document_ids"] = [row.get("document_id") for row in documents if row.get("document_id")]
        texts = []
        confidence_values: list[float] = []
        for row in documents:
            value = row.get("extracted_text") or row.get("text") or ""
            if value:
                texts.append(str(value).strip())
            if row.get("confidence") is not None:
                try:
                    confidence_values.append(float(row["confidence"]))
                except (TypeError, ValueError):
                    pass
            if payload.get("document_type") in {None, "", "unknown"}:
                doc_type = row.get("document_type")
                if doc_type:
                    payload["document_type"] = doc_type
        payload["document_text"] = "\n\n".join(text for text in texts if text)
        payload["document_confidence"] = max(confidence_values) if confidence_values else 0.0

    return payload

def _initialize_workflow_thread_table() -> None:
    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS
                public.claim_workflow_threads
                (
                    case_id TEXT PRIMARY KEY,
                    thread_id TEXT NOT NULL,
                    created_at TIMESTAMPTZ
                        NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ
                        NOT NULL DEFAULT NOW()
                )
                """
            )

        conn.commit()


def _new_thread_id(
    case_id: str,
) -> str:
    return (
        f"{case_id}-"
        f"{uuid.uuid4().hex[:12]}"
    )


def _save_thread_id(
    case_id: str,
    thread_id: str,
) -> None:
    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO
                    public.claim_workflow_threads
                (
                    case_id,
                    thread_id
                )
                VALUES (%s, %s)
                ON CONFLICT (case_id)
                DO UPDATE SET
                    thread_id = EXCLUDED.thread_id,
                    updated_at = NOW()
                """,
                (
                    case_id,
                    thread_id,
                ),
            )

        conn.commit()

    st.session_state.setdefault(
        "workflow_threads",
        {},
    )[case_id] = thread_id


def _get_thread_id(
    case_id: str,
    create_if_missing: bool = False,
) -> str | None:
    thread_map = st.session_state.setdefault(
        "workflow_threads",
        {},
    )

    session_thread_id = thread_map.get(
        case_id
    )

    if session_thread_id:
        return session_thread_id

    with psycopg.connect(
        DATABASE_URL,
        row_factory=dict_row,
    ) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT thread_id
                FROM public.claim_workflow_threads
                WHERE case_id = %s
                """,
                (case_id,),
            )

            row = cur.fetchone()

    if row:
        thread_id = row["thread_id"]

        thread_map[case_id] = thread_id

        return thread_id

    if not create_if_missing:
        return None

    thread_id = _new_thread_id(
        case_id
    )

    _save_thread_id(
        case_id,
        thread_id,
    )

    return thread_id


def _recover_thread_id_for_case(case_id: str) -> str | None:
    existing = _get_thread_id(case_id, create_if_missing=False)
    if existing:
        return existing

    async def _scan() -> str | None:
        async with AsyncPostgresSaver.from_conn_string(DATABASE_URL) as saver:
            candidates: list[dict[str, Any]] = []
            async for checkpoint_tuple in saver.alist(None, limit=500):
                config = checkpoint_tuple.config or {}
                checkpoint = checkpoint_tuple.checkpoint or {}
                channel_values = checkpoint.get("channel_values") or {}
                if channel_values.get("case_id") != case_id:
                    continue
                thread_id = (config.get("configurable") or {}).get("thread_id")
                if not thread_id:
                    continue
                if "claim_data" not in channel_values:
                    continue
                state_status = _canonical_case_status(channel_values.get("status"))
                state_stage = _canonical_case_status(channel_values.get("current_stage"))
                pause_states = {
                    "awaiting_documents",
                    "documents_revalidated",
                    "manual_review",
                    "manual_review_held",
                    "awaiting_human_review",
                    "human_review",
                    "approval_requested",
                    "sla_complete",
                }
                priority = 1
                if state_status in pause_states or state_stage in pause_states:
                    priority = 2
                candidates.append({
                    "thread_id": thread_id,
                    "status": state_status,
                    "stage": state_stage,
                    "priority": priority,
                })

            if not candidates:
                print(f"[Workflow Recovery] No resumable checkpoints found for case {case_id}.")
                return None

            best_index = 0
            for idx in range(1, len(candidates)):
                candidate = candidates[idx]
                best_candidate = candidates[best_index]
                if candidate["priority"] > best_candidate["priority"]:
                    best_index = idx
                elif candidate["priority"] == best_candidate["priority"] and idx > best_index:
                    best_index = idx

            best = candidates[best_index]
            print(f"[Workflow Recovery] case_id={case_id} candidates={candidates} selected_thread={best['thread_id']}")
            return best["thread_id"]

    thread_id = asyncio.run(_scan())
    if thread_id:
        _save_thread_id(case_id, thread_id)
        return thread_id
    return None


def _resume_manual_review(
    case_id: str,
    manual_input: dict[str, Any],
) -> dict[str, Any]:
    thread_id = _recover_thread_id_for_case(case_id)

    if not thread_id:
        raise ValueError(
            "No persisted workflow execution was found for case "
            f"{case_id}. Start the claim workflow before submitting a manual review decision."
        )

    print("[Manual Review] case_id:", case_id)
    print("[Manual Review] thread_id:", thread_id)

    async def _run() -> dict[str, Any]:
        async with get_v2_graph() as graph:
            config = {"configurable": {"thread_id": thread_id}}
            snapshot = await graph.aget_state(config)
            state_values = snapshot.values if snapshot else {}
            current_stage = state_values.get("current_stage")
            current_status = _canonical_case_status(state_values.get("status"))
            print("[Manual Review] checkpoint_stage:", current_stage)
            print("[Manual Review] checkpoint_status:", current_status)

            if not state_values:
                raise ValueError(f"No LangGraph checkpoint exists for thread {thread_id}.")
            if "claim_data" not in state_values:
                raise ValueError("The persisted LangGraph checkpoint does not contain claim_data.")

            with psycopg.connect(DATABASE_URL, row_factory=dict_row) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT status FROM public.claims WHERE case_id = %s",
                        (case_id,),
                    )
                    row = cur.fetchone()
            db_status = _canonical_case_status((row or {}).get("status")) if row else ""
            print("[Manual Review] database_status:", db_status)

            allowed_stages = {
                "manual_review",
                "manual_review_held",
                "documents_processing",
                "documents_revalidated",
                "awaiting_documents",
                "documents_complete",
            }
            allowed_statuses = {
                "manual_review",
                "manual_review_held",
                "documents_processing",
                "awaiting_documents",
                "documents_revalidated",
                "documents_complete",
            }

            if current_stage not in allowed_stages and current_status not in allowed_statuses and db_status not in allowed_statuses:
                raise ValueError(
                    "The case is not currently paused for Manual Review. "
                    f"Stage: {current_stage}; status: {current_status}; db_status: {db_status}."
                )

            return await graph.ainvoke(Command(resume=manual_input), config=config)

    return asyncio.run(_run())


def _resume_human_review(
    case_id: str,
    human_input: dict[str, str],
) -> dict[str, Any]:
    thread_id = _recover_thread_id_for_case(case_id)

    if not thread_id:
        raise ValueError(
            "No persisted workflow execution "
            f"was found for case {case_id}. "
            "Start the claim workflow before "
            "submitting a human decision."
        )

    print(
        "[Human Review] case_id:",
        case_id,
    )
    print(
        "[Human Review] thread_id:",
        thread_id,
    )

    async def _run() -> dict[str, Any]:
        async with get_v2_graph() as graph:
            config = {
                "configurable": {
                    "thread_id": thread_id,
                }
            }

            snapshot = await graph.aget_state(
                config
            )
            state_values = snapshot.values if snapshot else {}
            current_stage = state_values.get("current_stage")
            current_status = _canonical_case_status(state_values.get("status"))

            print(
                "[Human Review] state keys:",
                sorted(state_values.keys()),
            )
            print("[Human Review] stage:", current_stage)
            print("[Human Review] status:", current_status)
            print("[Human Review] claim_data exists:", "claim_data" in state_values)

            if not state_values:
                raise ValueError(
                    "No LangGraph checkpoint "
                    f"exists for thread {thread_id}."
                )

            if "claim_data" not in state_values:
                raise ValueError(
                    "The persisted LangGraph "
                    "checkpoint does not contain "
                    "claim_data. This case may have "
                    "been created before workflow "
                    "thread persistence was enabled."
                )

            with psycopg.connect(DATABASE_URL, row_factory=dict_row) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT status FROM public.claims WHERE case_id = %s",
                        (case_id,),
                    )
                    row = cur.fetchone()
            db_status = _canonical_case_status((row or {}).get("status")) if row else ""
            print("[Human Review] database_status:", db_status)

            allowed_stages = {
                "sla_complete",
                "approval_requested",
                "human_review",
                "awaiting_human_review",
            }
            allowed_statuses = {"awaiting_human_review", "routing_complete", "sla_complete"}

            if (
                current_stage not in allowed_stages
                and current_status not in allowed_statuses
                and db_status not in allowed_statuses
            ):
                raise ValueError(
                    "The case is not currently "
                    "paused for Human Review. "
                    f"Stage: {current_stage}; "
                    f"status: {current_status}; db_status: {db_status}."
                )

            return await graph.ainvoke(
                Command(
                    resume=human_input
                ),
                config=config,
            )

    return asyncio.run(
        _run()
    )


def _start_case_workflow(
    case_id: str,
    claim_data: dict[str, Any],
    thread_id: str | None = None,
) -> dict[str, Any]:
    thread_id = thread_id or _new_thread_id(case_id)
    _save_thread_id(case_id, thread_id)
    st.session_state.setdefault("workflow_threads", {})[case_id] = thread_id

    initial_state = {
        "case_id": case_id,
        "claim_data": claim_data,
        "current_stage": "submitted",
        "status": "submitted",
        "errors": [],
    }

    print("[Workflow Start] case_id:", case_id)
    print("[Workflow Start] thread_id:", thread_id)

    async def _run() -> dict[str, Any]:
        async with get_v2_graph() as graph:
            return await graph.ainvoke(
                initial_state,
                config={"configurable": {"thread_id": thread_id}},
            )

    return asyncio.run(_run())


if "workflow_result" not in st.session_state:
    st.session_state.workflow_result = None
if "selected_case" not in st.session_state:
    st.session_state.selected_case = None

_initialize_workflow_thread_table()
if page == "Submit Claim":
    render_page_header("Submit Claim", "Register claim details and supporting evidence.")
    with st.form("claim_form"):
        left, right = st.columns([1, 1])
        with left:
            case_id = st.text_input("Case ID", value=f"CASE-{uuid.uuid4().hex[:6].upper()}")
            policy_number = st.text_input("Policy Number", value="POL-1001")
            claimant_name = st.text_input("Claimant Name", value="Test Customer")
            claim_type = st.selectbox("Claim Type", ["Medical", "Vehicle", "Property", "Other"])
        with right:
            claim_amount = st.number_input("Claim Amount", min_value=0.0, value=25000.0)
            description = st.text_area("Description", value="Hospital treatment claim with medical bill.")
            uploaded_files = st.file_uploader(
                "Supporting Documents",
                type=["pdf", "png", "jpg", "jpeg"],
                accept_multiple_files=True,
            )
        submitted = st.form_submit_button("Process Claim", type="primary")

    if submitted:
        if not case_id.strip():
            st.error("Case ID is required.")
        else:
            processing_status = st.empty()
            _render_processing_status(0)
            try:
                _insert_case(case_id, policy_number, claimant_name, claim_type, float(claim_amount), description)
                print("[UI] Claim registered:", case_id)
                _persist_uploaded_documents(case_id, uploaded_files)
                claim_data = {
                    "case_id": case_id,
                    "policy_number": policy_number,
                    "claimant_name": claimant_name,
                    "claim_type": claim_type,
                    "claim_amount": float(claim_amount),
                    "description": description,
                }
                claim_data = _hydrate_claim_data(case_id, claim_data)
                thread_id = _new_thread_id(case_id)
                print("[UI] Starting LangGraph:", thread_id)
                record_audit(case_id, "streamlit_ui", "claim_registered", {"policy_number": policy_number, "claim_type": claim_type, "claim_amount": float(claim_amount)})
                result = _start_case_workflow(case_id, claim_data, thread_id=thread_id)
                record_audit(case_id, "langgraph_supervisor", "workflow_started", {"thread_id": thread_id, "initial_stage": "submitted"}, stage="submitted")
                st.session_state.workflow_result = result
                st.session_state.selected_case = case_id
                processing_status.empty()
                st.success("Claim submitted and workflow started.")
                _render_workflow_progress("submitted")
            except Exception as exc:
                processing_status.empty()
                st.error("Unable to continue workflow.")
                with st.expander("Technical Details"):
                    st.code(_safe_error_details(exc))

elif page == "Case Queue":
    render_page_header("Case Queue", "Monitor active and completed claims.")
    cases = _queue_cases()
    if not cases:
        st.info("No cases available.")
    else:
        search_term = st.text_input("Search cases", placeholder="Case ID, claimant, type, status", key="case_queue_search")
        normalized = (search_term or "").strip().lower()
        filtered_cases = cases
        if normalized:
            filtered_cases = [
                row for row in cases
                if any(
                    normalized in str(value or "").lower()
                    for value in [
                        row.get("case_id"),
                        row.get("claimant_name"),
                        row.get("claim_type"),
                        row.get("status"),
                    ]
                )
            ]

        page_size = 10
        total_pages = max(1, (len(filtered_cases) + page_size - 1) // page_size) if filtered_cases else 1
        page_number = st.number_input(
            "Page",
            min_value=1,
            max_value=total_pages,
            value=1,
            step=1,
            key="case_queue_page",
        )
        start_index = (page_number - 1) * page_size
        end_index = start_index + page_size
        page_cases = filtered_cases[start_index:end_index]

        if not page_cases:
            st.info("No cases match the current search.")
        else:
            queue_rows = []
            for row in page_cases:
                queue_rows.append({
                    "Case ID": row.get("case_id"),
                    "Claimant": row.get("claimant_name"),
                    "Type": row.get("claim_type"),
                    "Amount": float(row.get("claim_amount") or 0.0),
                    "Status": _status_display_label(row.get("status")),
                    "Updated": row.get("created_at"),
                })
            st.dataframe(queue_rows, width="stretch", hide_index=True)
            st.caption(f"Showing {len(page_cases)} of {len(filtered_cases)} matching cases • Page {page_number} of {total_pages}")

elif page == "Case Workspace":
    render_page_header("Case Workspace", "Review claim information, evidence and workflow progress.")
    cases = _queue_cases()
    case_options = [row["case_id"] for row in cases]
    selected_case = st.selectbox("Select Case", case_options, index=0 if case_options else None)
    if not selected_case:
        st.info("No cases to display.")
    else:
        case = _case_record(selected_case)
        documents = _list_documents(selected_case)
        if not case:
            st.info("Case not found.")
        else:
            canonical_status = _canonical_case_status(case.get("status"))
            metric_col1, metric_col2, metric_col3, metric_col4 = st.columns(4)
            with metric_col1:
                st.metric("Case ID", case.get("case_id"))
            with metric_col2:
                st.metric("Status", _status_display_label(canonical_status))
            with metric_col3:
                st.metric("Claim Type", _display_value(case.get("claim_type")))
            with metric_col4:
                st.metric("Amount", _display_value(case.get("claim_amount")))

            _render_workflow_progress(canonical_status, label="Workflow Progress")

            tabs = st.tabs(["Overview", "Documents", "AI Summary", "Timeline"])
            with tabs[0]:
                overview_col1, overview_col2 = st.columns(2)
                with overview_col1:
                    st.markdown("### Claim Details")
                    st.markdown(f"- Policy: {_display_value(case.get('policy_number'))}")
                    st.markdown(f"- Claimant: {_display_value(case.get('claimant_name'))}")
                    st.markdown(f"- Claim Type: {_display_value(case.get('claim_type'))}")
                    st.markdown(f"- Amount: {_display_value(case.get('claim_amount'))}")
                    st.markdown(f"- SLA: {_display_value(case.get('updated_at'))}")
                with overview_col2:
                    st.markdown("### Processing")
                    st.markdown(f"- Assigned handler: Team Lead")
                    st.markdown(f"- Approver: Demo Approver")
                    st.markdown(f"- Description: {_display_value(case.get('description'))}")

            with tabs[1]:
                if not documents:
                    st.info("No documents attached.")
                else:
                    for document in documents:
                        confidence = float(document.get("confidence") or 0.0)
                        validation = "Passed" if confidence >= 0.75 else "Review"
                        security = "No" if not document.get("injection_detected") else "Flagged"
                        with st.container():
                            st.markdown(
                                f"**{document.get('file_name')}**  \n"
                                f"Type: {document.get('document_type')}  \n"
                                f"Confidence: {confidence:.2f}  \n"
                                f"Validation: {validation}  \n"
                                f"Security: {security}"
                            )
                            with st.expander("View Extracted Text"):
                                st.write(document.get("extracted_text") or document.get("text") or "No extracted text available.")

            with tabs[2]:
                summary_payload = case.get("summary")
                if not summary_payload:
                    st.info("No AI summary available yet.")
                else:
                    if isinstance(summary_payload, dict):
                        for section, content in summary_payload.items():
                            st.markdown(f"### {section.replace('_', ' ').title()}")
                            if isinstance(content, list):
                                for item in content:
                                    st.markdown(f"- {item}")
                            else:
                                st.write(content)
                    else:
                        st.write(summary_payload)

            with tabs[3]:
                with psycopg.connect(DATABASE_URL, row_factory=dict_row) as conn:
                    with conn.cursor() as cur:
                        cur.execute(
                            """
                            SELECT actor, action, details, created_at
                            FROM public.claim_audit
                            WHERE case_id = %s
                            ORDER BY created_at DESC
                            """,
                            (selected_case,),
                        )
                        timeline_rows = cur.fetchall()
                if not timeline_rows:
                    st.info("No audit events recorded for this case yet.")
                else:
                    for row in timeline_rows:
                        with st.expander(f"{row.get('created_at')} — {row.get('actor')} — {row.get('action')}"):
                            details = row.get("details") or {}
                            if isinstance(details, dict):
                                detail_text = "; ".join(f"{key}: {value}" for key, value in details.items() if key != "_audit_key")
                            else:
                                detail_text = str(details)
                            st.write(detail_text or "No additional detail")

            if canonical_status == "awaiting_documents":
                requested_documents = _requested_documents_for_case(selected_case)
                st.markdown("<div class='panel-box'><strong>Additional Documents Required</strong></div>", unsafe_allow_html=True)
                info_cols = st.columns(3)
                with info_cols[0]:
                    st.markdown(f"**Requested documents:** {', '.join(requested_documents)}")
                with info_cols[1]:
                    st.markdown("**Request reason:** Low confidence or missing supporting evidence")
                with info_cols[2]:
                    st.markdown("**Last notification:** Available in audit trail")
                uploaded_document = st.file_uploader(
                    "Upload Additional Documents",
                    type=["pdf", "png", "jpg", "jpeg"],
                    accept_multiple_files=False,
                    key=f"upload_additional_document_{selected_case}",
                )
                if st.button("Upload & Resume Workflow", key=f"resume_case_documents_{selected_case}"):
                    if uploaded_document is None:
                        st.warning("Upload a supporting document before resuming the case.")
                    else:
                        try:
                            result = _resume_existing_case_documents(selected_case, [uploaded_document])
                            st.session_state.workflow_result = result
                            st.success(f"Document uploaded and case {selected_case} resumed on the original workflow thread.")
                        except Exception as exc:
                            st.error("Unable to continue workflow.")
                            with st.expander("Technical Details"):
                                st.code(_safe_error_details(exc))

elif page == "Manual Review":
    render_page_header("Manual Review", "Resolve document and validation exceptions.")
    with psycopg.connect(DATABASE_URL, row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT case_id, claimant_name, claim_type, claim_amount, status, summary, description, policy_number
                FROM public.claims
                WHERE status IN ('manual_review', 'manual_review_held')
                ORDER BY updated_at DESC
                """
            )
            rows = cur.fetchall()

    if not rows:
        st.info("No manual-review cases currently waiting.")
    else:
        case_ids = [row.get("case_id") for row in rows]
        selected_case = st.selectbox("Cases Requiring Manual Review", case_ids)
        selected_row = next(row for row in rows if row.get("case_id") == selected_case)
        case_id = selected_row.get("case_id")
        claimant_name = selected_row.get("claimant_name")
        claim_type = selected_row.get("claim_type")
        claim_amount = float(selected_row.get("claim_amount") or 0.0)
        summary = selected_row.get("summary")
        description = selected_row.get("description")
        policy_number = selected_row.get("policy_number")
        documents = _list_documents(case_id)
        confidence = max((float(doc.get("confidence") or 0.0) for doc in documents), default=0.0)
        threshold = 0.75
        validation_issues = []
        risks = []
        security_flags = []
        for doc in documents:
            validation_issues.extend(doc.get("validation_issues") or [])
            risks.extend(doc.get("risks") or [])
            security_flags.extend(doc.get("security_flags") or [])

        metric_cols = st.columns(4)
        with metric_cols[0]:
            st.metric("Case ID", case_id)
        with metric_cols[1]:
            st.metric("Claimant", claimant_name)
        with metric_cols[2]:
            st.metric("Amount", _display_value(claim_amount))
        with metric_cols[3]:
            st.metric("Confidence", f"{confidence:.2f}")

        st.markdown("### Review Reason")
        if confidence < threshold:
            st.info("Low document confidence")
        else:
            st.info("Reviewing validation and security risk factors")
        st.caption(f"Confidence: {confidence:.2f}")
        st.caption(f"Threshold: {threshold:.2f}")

        risk_cols = st.columns(3)
        with risk_cols[0]:
            st.markdown("**Risks**")
            if risks:
                for item in risks:
                    st.markdown(f"- {item}")
            else:
                st.write("None identified")
        with risk_cols[1]:
            st.markdown("**Validation Issues**")
            if validation_issues:
                for item in validation_issues:
                    st.markdown(f"- {item}")
            else:
                st.write("None")
        with risk_cols[2]:
            st.markdown("**Security Flags**")
            if security_flags:
                for item in security_flags:
                    st.markdown(f"- {item}")
            else:
                st.write("None")

        st.markdown("### Reviewer Decision")
        reviewer = st.text_input("Reviewer", value="Ops Reviewer", key=f"manual_review_reviewer_{case_id}")
        action = st.selectbox(
            "Action",
            ["continue_processing", "reprocess_documents", "request_documents", "hold_case"],
            format_func=lambda value: {
                "continue_processing": "Continue Processing",
                "reprocess_documents": "Reprocess Documents",
                "request_documents": "Request Documents",
                "hold_case": "Hold Case",
            }.get(value, value),
            key=f"manual_review_action_{case_id}",
        )
        rationale = st.text_area("Rationale", key=f"manual_review_rationale_{case_id}")
        st.caption("Manual Review resolves processing exceptions. It does not approve or reject a claim.")
        if st.button("Submit Manual Review", key=f"submit_manual_review_{case_id}"):
            if not rationale.strip():
                st.error("Rationale is required for Manual Review.")
            else:
                try:
                    result = _resume_manual_review(case_id, {
                        "action": action,
                        "reviewer": reviewer,
                        "rationale": rationale,
                        "missing_documents": ["supporting_document"] if action == "request_documents" else [],
                    })
                    record_audit(case_id, reviewer, "manual_review_resolved", {"action": action, "rationale": rationale})
                    st.session_state.workflow_result = result
                    st.success("Manual review submitted.")
                except Exception as exc:
                    st.error("Unable to continue workflow.")
                    with st.expander("Technical Details"):
                        st.code(_safe_error_details(exc))

elif page == "Human Review":
    render_page_header("Human Review", "Authorized final claim decision.")
    cases = _queue_cases()
    awaiting = [row for row in cases if row.get("status") in {"awaiting_human_review", "human_decision_received"}]
    if not awaiting:
        st.info("No claims currently require human decision.")
    else:
        chosen_case = st.selectbox("Case", [row["case_id"] for row in awaiting])
        case = _case_record(chosen_case)
        if not case:
            st.warning("Case not found.")
        else:
            metric_cols = st.columns(5)
            with metric_cols[0]:
                st.metric("Case ID", chosen_case)
            with metric_cols[1]:
                st.metric("Claim Type", _display_value(case.get("claim_type")))
            with metric_cols[2]:
                st.metric("Amount", _display_value(case.get("claim_amount")))
            with metric_cols[3]:
                st.metric("Policy", _display_value(case.get("policy_number")))
            with metric_cols[4]:
                st.metric("Routing", _status_display_label(case.get("status")))

            _render_workflow_progress(case.get("status"), label="Workflow Progress")
            if case.get("summary"):
                st.markdown("### AI Summary")
                if isinstance(case.get("summary"), dict):
                    for section, content in case["summary"].items():
                        st.markdown(f"**{section.replace('_', ' ').title()}:**")
                        if isinstance(content, list):
                            for item in content:
                                st.markdown(f"- {item}")
                        else:
                            st.write(content)
                else:
                    st.write(case.get("summary"))

            approver_directory = get_approver_directory()
            approver_names = [row.get("name") for row in approver_directory if row.get("active")]
            reviewer = st.selectbox("Reviewer", approver_names or ["Demo Approver", "Senior Approver", "Director Approver"])
            validation = validate_approver_limit(reviewer, float(case.get("claim_amount") or 0))
            if validation["valid"]:
                st.success(f"✓ {reviewer} is authorized for {_display_value(float(case.get('claim_amount') or 0))}.")
            else:
                st.error(f"✕ Reviewer approval limit is insufficient")

            decision = st.selectbox(
                "Decision",
                ["approved", "rejected", "request_more_information"],
                format_func=lambda value: {
                    "approved": "Approved",
                    "rejected": "Rejected",
                    "request_more_information": "Request More Information",
                }.get(value, value),
            )
            rationale = st.text_area("Decision Rationale", key="human_decision_rationale")
            if decision == "request_more_information":
                requested_documents = st.text_area(
                    "Requested Information",
                    placeholder="itemized_bill\ntreatment_proof\nclaimant_id",
                    height=80,
                )
            else:
                requested_documents = ""

            st.caption("Final claim decisions require an authorized human reviewer.")
            submit_disabled = not validation["valid"]
            if st.button("Submit Human Decision", type="primary", disabled=submit_disabled):
                if not rationale.strip():
                    st.error("Please provide a rationale before continuing.")
                elif decision == "request_more_information" and not requested_documents.strip():
                    st.error("Please list at least one requested document or clarification.")
                else:
                    payload = {"decision": decision, "rationale": rationale, "reviewer": reviewer}
                    if decision == "request_more_information":
                        payload["missing_documents"] = [item.strip() for item in requested_documents.replace(";", "\n").splitlines() if item.strip()]
                        payload["requested_documents"] = payload["missing_documents"]
                    try:
                        result = _resume_human_review(chosen_case, payload)
                        record_audit(chosen_case, reviewer, "human_decision_recorded", {"decision": decision, "rationale": rationale, "missing_documents": payload.get("missing_documents", [])})
                        st.session_state.workflow_result = result
                        if decision == "request_more_information":
                            st.info("Additional information requested. The claim remains open and is not finalized.")
                        else:
                            st.success("Human review submitted.")
                    except Exception as exc:
                        st.error("Unable to continue workflow.")
                        with st.expander("Technical Details"):
                            st.code(_safe_error_details(exc))

elif page == "Notifications":
    render_page_header("Notifications", "Latest operational notifications.")
    messages = get_mailpit_messages()
    if not messages:
        st.info("No Mailpit messages are currently queued.")
    else:
        for message in messages[:20]:
            with st.expander(f"{message.get('Subject', 'Message')} · {message.get('To', 'unknown')}"):
                st.markdown(f"- Subject: {message.get('Subject', 'Message')}")
                st.markdown(f"- Recipient: {message.get('To', 'unknown')}")
                st.markdown(f"- Created: {message.get('Created', 'unknown')}")
                st.markdown(f"- Type: {message.get('Type', 'general')}")
                st.write(message.get("Text", "No message content available."))

elif page == "Audit":
    render_page_header("Audit Trail", "Trace automated and human actions across the case lifecycle.")
    filters_col1, filters_col2, filters_col3 = st.columns([1.1, 1.2, 1])
    with filters_col1:
        case_filter = st.text_input("Case ID", key="audit_case_filter")
    with filters_col2:
        action_filter = st.selectbox(
            "Action",
            ["All", "claim_registered", "workflow_started", "mcp_validation_completed", "intake_completed", "document_persisted", "document_validation_completed", "documents_requested", "workflow_paused_for_documents", "manual_review_started", "manual_review_resolved", "summary_created", "case_routed", "approval_requested", "sla_scheduled", "notification_sent", "human_review_started", "additional_information_requested", "human_decision_recorded", "claim_finalized"],
            index=0,
        )
    with filters_col3:
        sort_order = st.radio("Sort Order", ["Newest first", "Oldest first"], horizontal=True)

    query = """
        SELECT
            id,
            case_id,
            actor,
            action,
            details,
            created_at
        FROM public.claim_audit
        WHERE (%s = '' OR case_id ILIKE %s)
    """
    params: list[Any] = [case_filter or "", f"%{case_filter or ''}%"]
    if action_filter != "All":
        query += " AND action = %s "
        params.append(action_filter)
    query += " ORDER BY created_at " + ("DESC" if sort_order == "Newest first" else "ASC")

    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            cur.execute(query, params)
            rows = cur.fetchall()

    if not rows:
        st.info("No audit records found for the selected filters.")
    else:
        for row in rows:
            audit_id, case_id, actor, action, details, created_at = row
            safe_details = details or {}
            if isinstance(safe_details, dict):
                safe_details = {k: v for k, v in safe_details.items() if k != "_audit_key"}
            with st.expander(f"{created_at} — {case_id} — {action}"):
                st.markdown(f"- Actor: {actor}")
                st.markdown(f"- Case: {case_id}")
                st.markdown(f"- Action: {action}")
                st.markdown(f"- Timestamp: {created_at}")
                if safe_details:
                    st.write(safe_details)
                else:
                    st.write("No additional detail")


