import asyncio
import os
import sys
import uuid
from pathlib import Path
from typing import Any

import psycopg
import streamlit as st
from dotenv import load_dotenv
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
        * {
            font-family: "Segoe UI", "Inter", sans-serif;
        }

        .stApp {
            background: linear-gradient(135deg, #f8fafc 0%, #edf6ff 38%, #f3f4f6 100%);
            color: #0f172a;
        }

        .block-container {
            padding-top: 2rem;
            padding-bottom: 3rem;
            max-width: 1460px;
        }

        [data-testid="stSidebar"] {
            background: linear-gradient(180deg, #0b1220 0%, #101827 100%);
            color: #ffffff;
            border-right: 1px solid rgba(148, 163, 184, 0.22);
        }

        [data-testid="stSidebar"] .stMarkdown,
        [data-testid="stSidebar"] .stRadio,
        [data-testid="stSidebar"] .stSelectbox,
        [data-testid="stSidebar"] .stTextInput,
        [data-testid="stSidebar"] label,
        [data-testid="stSidebar"] p,
        [data-testid="stSidebar"] div,
        [data-testid="stSidebar"] span {
            color: #ffffff !important;
            opacity: 1;
        }

        .stRadio > div {
            gap: 0.9rem;
        }

        [role="radiogroup"] {
            display: flex;
            flex-direction: column;
            gap: 0.75rem;
            padding-top: 0.4rem;
        }

        [role="radiogroup"] > label {
            background: rgba(255, 255, 255, 0.04) !important;
            border: 1px solid rgba(255, 255, 255, 0.15);
            border-radius: 12px;
            padding: 0.78rem 0.85rem 0.78rem 2.7rem;
            margin: 0;
            transition: all 0.2s ease;
            color: #ffffff !important;
            font-weight: 700;
            letter-spacing: 0.01em;
            opacity: 1;
            box-shadow: none;
            position: relative;
            overflow: visible;
        }

        [role="radiogroup"] > label::before {
            content: "";
            position: absolute;
            left: 0.9rem;
            top: 50%;
            transform: translateY(-50%);
            width: 0.72rem;
            height: 0.72rem;
            border-radius: 50%;
            background: rgba(148, 163, 184, 0.7);
            box-shadow: 0 0 0 2px rgba(255, 255, 255, 0.08);
        }

        [role="radiogroup"] > label[data-checked="true"]::before {
            background: linear-gradient(135deg, #7dd3fc 0%, #60a5fa 100%);
            box-shadow: 0 0 0 3px rgba(96, 165, 250, 0.18), 0 0 12px rgba(125, 211, 252, 0.45);
        }

        [role="radiogroup"] > label::after {
            content: "";
            position: absolute;
            left: 1.25rem;
            top: calc(100% + 0.14rem);
            width: calc(100% - 2.5rem);
            height: 2px;
            border-radius: 999px;
            background: linear-gradient(90deg, rgba(125,211,252,0.8), rgba(96,165,250,0.18));
            opacity: 0.8;
        }

        [role="radiogroup"] > label:last-child::after {
            display: none;
        }

        [role="radiogroup"] > label > div,
        [role="radiogroup"] > label > span,
        [role="radiogroup"] > label p,
        [role="radiogroup"] > label div {
            color: #ffffff !important;
            font-weight: 700;
            opacity: 1;
        }

        [role="radiogroup"] > label:hover {
            background: rgba(255, 255, 255, 0.07) !important;
            border-color: rgba(255, 255, 255, 0.25);
        }

        [role="radiogroup"] > label[data-checked="true"] {
            background: rgba(255, 255, 255, 0.08) !important;
            border-color: rgba(255, 255, 255, 0.82);
            box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.18);
        }

        [role="radiogroup"] input[type="radio"] {
            accent-color: #f8fafc;
            transform: scale(1.08);
        }

        h1, h2, h3, h4 {
            color: #0f172a;
            letter-spacing: -0.03em;
        }

        .stMetric {
            background: rgba(255, 255, 255, 0.72);
            border: 1px solid rgba(148, 163, 184, 0.15);
            border-radius: 16px;
            box-shadow: 0 10px 24px rgba(15, 23, 42, 0.04);
            padding: 0.75rem 1rem;
        }

        [data-testid="stMetricValue"] {
            color: #0f172a;
            font-size: 1.8rem;
            font-weight: 700;
        }

        .stDataFrame {
            border-radius: 16px;
            overflow: hidden;
            border: 1px solid rgba(148, 163, 184, 0.16);
            box-shadow: 0 10px 24px rgba(15, 23, 42, 0.04);
        }

        div[data-testid="stExpander"] > div {
            background: rgba(255, 255, 255, 0.7);
            border: 1px solid rgba(148, 163, 184, 0.16);
            border-radius: 12px;
            box-shadow: 0 8px 20px rgba(15, 23, 42, 0.04);
        }

        .stButton > button {
            background: linear-gradient(135deg, #2563eb 0%, #1d4ed8 100%);
            color: white;
            border: none;
            border-radius: 10px;
            padding: 0.65rem 1.05rem;
            font-weight: 600;
            box-shadow: 0 10px 22px rgba(37, 99, 235, 0.22);
        }

        .stButton > button:hover {
            filter: brightness(1.04);
            box-shadow: 0 12px 24px rgba(37, 99, 235, 0.28);
        }

        .stAlert {
            border-radius: 12px;
            border: 1px solid rgba(148, 163, 184, 0.18);
            background: rgba(255, 255, 255, 0.72);
        }

        .stForm {
            background: rgba(255, 255, 255, 0.72);
            border: 1px solid rgba(148, 163, 184, 0.16);
            border-radius: 18px;
            padding: 1rem 1.05rem;
            box-shadow: 0 12px 28px rgba(15, 23, 42, 0.04);
        }

        .stTextInput input, .stSelectbox select, .stNumberInput input, .stTextArea textarea {
            border-radius: 10px !important;
            border: 1px solid rgba(148, 163, 184, 0.3) !important;
            background: rgba(255, 255, 255, 0.82) !important;
        }
    </style>
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

    thread_id = _get_thread_id(case_id, create_if_missing=False)
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
            allowed_stages = {"awaiting_documents", "documents_revalidated", "manual_review", "manual_review_held"}
            allowed_statuses = {"awaiting_documents", "manual_review", "manual_review_held", "documents_revalidated"}
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


def _resume_manual_review(
    case_id: str,
    manual_input: dict[str, Any],
) -> dict[str, Any]:
    thread_id = _get_thread_id(
        case_id,
        create_if_missing=False,
    )

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

            if not state_values:
                raise ValueError(f"No LangGraph checkpoint exists for thread {thread_id}.")
            if "claim_data" not in state_values:
                raise ValueError("The persisted LangGraph checkpoint does not contain claim_data.")

            current_stage = state_values.get("current_stage")
            current_status = state_values.get("status")
            allowed_stages = {"manual_review", "manual_review_held", "documents_revalidated", "awaiting_documents"}
            allowed_statuses = {"manual_review", "manual_review_held", "awaiting_documents"}

            if current_stage not in allowed_stages and current_status not in allowed_statuses:
                raise ValueError(
                    "The case is not currently paused for Manual Review. "
                    f"Stage: {current_stage}; status: {current_status}."
                )

            return await graph.ainvoke(Command(resume=manual_input), config=config)

    return asyncio.run(_run())


def _resume_human_review(
    case_id: str,
    human_input: dict[str, str],
) -> dict[str, Any]:
    thread_id = _get_thread_id(
        case_id,
        create_if_missing=False,
    )

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

            state_values = (
                snapshot.values
                if snapshot
                else {}
            )

            print(
                "[Human Review] state keys:",
                sorted(state_values.keys()),
            )

            print(
                "[Human Review] stage:",
                state_values.get(
                    "current_stage"
                ),
            )

            print(
                "[Human Review] status:",
                state_values.get(
                    "status"
                ),
            )

            print(
                "[Human Review] "
                "claim_data exists:",
                "claim_data" in state_values,
            )

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

            current_stage = state_values.get(
                "current_stage"
            )

            current_status = state_values.get(
                "status"
            )

            allowed_stages = {
                "sla_complete",
                "approval_requested",
                "human_review",
            }

            allowed_statuses = {
                "awaiting_human_review",
            }

            if (
                current_stage not in allowed_stages
                and current_status
                not in allowed_statuses
            ):
                raise ValueError(
                    "The case is not currently "
                    "paused for Human Review. "
                    f"Stage: {current_stage}; "
                    f"status: {current_status}."
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

st.markdown(
    """
    <div style="
        background: linear-gradient(135deg, rgba(37,99,235,0.12), rgba(14,165,233,0.06));
        border: 1px solid rgba(37,99,235,0.14);
        border-radius: 16px;
        padding: 0.7rem 0.9rem;
        margin: 0 0 0.7rem 0;
        box-shadow: 0 10px 22px rgba(37,99,235,0.06);
    ">
        <div style="font-size: 0.68rem; font-weight: 700; letter-spacing: 0.12em; text-transform: uppercase; color: #2563eb; margin-bottom: 0.25rem;">
            Claims Operations Console
        </div>
        <div style="font-size: 1.3rem; font-weight: 800; color: #0f172a; line-height: 1.15;">
            Intelligent Claims Processing
        </div>
        <div style="margin-top: 0.18rem; color: #475569; font-size: 0.78rem; line-height: 1.3;">
            AI-assisted claims processing with human-in-the-loop controls
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)
_initialize_workflow_thread_table()
if page == "Submit Claim":
    st.header("Submit Claim")
    with st.form("claim_form"):
        case_id = st.text_input("Case ID", value=f"CASE-{uuid.uuid4().hex[:6].upper()}")
        policy_number = st.text_input("Policy Number", value="POL-1001")
        claimant_name = st.text_input("Claimant Name", value="Test Customer")
        claim_type = st.selectbox("Claim Type", ["Medical", "Vehicle", "Property", "Other"])
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
            try:
                _insert_case(case_id, policy_number, claimant_name, claim_type, float(claim_amount), description)
                print("[UI] Claim registered:", case_id)
                saved_documents = _persist_uploaded_documents(case_id, uploaded_files)
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
                st.success("Claim submitted and workflow started.")
            except Exception as exc:
                st.error(f"Unable to process claim: {exc}")

elif page == "Case Queue":
    st.header("Case Queue")
    cases = _queue_cases()
    if not cases:
        st.info("No cases available.")
    else:
        queue_df = [{
            "Case ID": row.get("case_id"),
            "Claimant": row.get("claimant_name"),
            "Claim Type": row.get("claim_type"),
            "Amount": row.get("claim_amount"),
            "Status": row.get("status"),
        } for row in cases]
        st.dataframe(queue_df, width="stretch")

elif page == "Case Workspace":
    st.header("Case Workspace")
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
            col1, col2, col3 = st.columns(3)
            canonical_status = _canonical_case_status(case.get("status"))
            with col1:
                st.metric("Case ID", case.get("case_id"))
            with col2:
                st.metric("Status", canonical_status)
            with col3:
                st.metric("Stage", canonical_status or "unknown")

            _render_workflow_status_bar(canonical_status, label="Case workflow")

            st.subheader("Claim Information")
            st.write({
                "Policy": case.get("policy_number"),
                "Claimant": case.get("claimant_name"),
                "Type": case.get("claim_type"),
                "Amount": case.get("claim_amount"),
                "Description": case.get("description"),
            })

            if canonical_status == "awaiting_documents":
                requested_documents = _requested_documents_for_case(selected_case)
                st.subheader("Additional Documents Required")
                st.write(f"Case: {selected_case}")
                st.write(f"Requested Documents: {', '.join(requested_documents)}")
                if documents:
                    st.write("Existing Documents:")
                    for document in documents:
                        st.write(f"- {document.get('file_name')} ({document.get('document_type')})")
                uploaded_document = st.file_uploader(
                    "Upload Additional Document",
                    type=["pdf", "png", "jpg", "jpeg"],
                    accept_multiple_files=False,
                    key=f"upload_additional_document_{selected_case}",
                )
                if st.button("Submit Documents & Resume Workflow", key=f"resume_case_documents_{selected_case}"):
                    if uploaded_document is None:
                        st.warning("Upload a replacement or additional document before resuming the case.")
                    else:
                        try:
                            result = _resume_existing_case_documents(selected_case, [uploaded_document])
                            st.session_state.workflow_result = result
                            st.success(f"Document uploaded and case {selected_case} resumed on the original workflow thread.")
                            st.write(result.get("status") or "awaiting_documents")
                        except Exception as exc:
                            st.error(f"Unable to resume existing case workflow: {exc}")

            if documents:
                st.subheader("Documents")
                for document in documents:
                    with st.expander(f"{document.get('file_name')} - {document.get('document_type')}"):
                        st.write({
                            "Document ID": document.get("document_id"),
                            "Confidence": document.get("confidence"),
                            "Injection Detected": document.get("injection_detected"),
                        })
            else:
                st.info("No documents attached.")

            if case.get("summary"):
                st.subheader("Summary")
                st.write(case.get("summary"))

            st.subheader("Case Timeline")
            with psycopg.connect(DATABASE_URL, row_factory=dict_row) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT id, case_id, actor, action, details, created_at
                        FROM public.claim_audit
                        WHERE case_id = %s
                        ORDER BY created_at ASC
                        """,
                        (selected_case,),
                    )
                    timeline_rows = cur.fetchall()
            if not timeline_rows:
                st.info("No audit events recorded for this case yet.")
            else:
                for row in timeline_rows:
                    details = row.get("details") or {}
                    safe_text = ""
                    if isinstance(details, dict):
                        safe_pairs = []
                        for key, value in details.items():
                            if key == "_audit_key":
                                continue
                            safe_pairs.append(f"{key}: {value}")
                        safe_text = "; ".join(safe_pairs) if safe_pairs else "No additional detail"
                    with st.expander(f"{row.get('created_at').strftime('%Y-%m-%d %H:%M:%S')} — {row.get('actor')} — {row.get('action')}"):
                        st.write(safe_text)

elif page == "Manual Review":
    st.header("Manual Review")
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
        for row in rows:
            case_id = row.get("case_id")
            claimant_name = row.get("claimant_name")
            claim_type = row.get("claim_type")
            claim_amount = row.get("claim_amount")
            status = row.get("status")
            summary = row.get("summary")
            description = row.get("description")
            policy_number = row.get("policy_number")
            documents = _list_documents(case_id)
            confidence = max((float(doc.get("confidence") or 0.0) for doc in documents), default=0.0)
            validation_issues = []
            risks = []
            security_flags = []
            for doc in documents:
                validation_issues.extend(doc.get("validation_issues") or [])
                risks.extend(doc.get("risks") or [])
                security_flags.extend(doc.get("security_flags") or [])

            with st.expander(f"{case_id} - {claimant_name}"):
                st.write({
                    "Case ID": case_id,
                    "Policy Number": policy_number,
                    "Claimant": claimant_name,
                    "Claim Type": claim_type,
                    "Claim Amount": claim_amount,
                    "Status": status,
                    "Description": description,
                    "Document Confidence": confidence,
                    "Validation Issues": validation_issues or "None",
                    "Risks": risks or "None",
                    "Security Flags": security_flags or "None",
                    "Summary": summary,
                })

                if documents:
                    st.subheader("Document details")
                    for document in documents:
                        with st.expander(f"{document.get('document_id')} - {document.get('file_name')}"):
                            st.write({
                                "Document ID": document.get("document_id"),
                                "Type": document.get("document_type"),
                                "File Name": document.get("file_name"),
                                "Confidence": document.get("confidence"),
                                "Injection Detected": document.get("injection_detected"),
                                "Extracted Text": document.get("extracted_text") or document.get("text") or "",
                            })

                reviewer = st.text_input("Reviewer", value="Ops Reviewer", key=f"manual_review_reviewer_{case_id}")
                action = st.selectbox(
                    "Action",
                    ["continue_processing", "reprocess_documents", "request_documents", "hold_case"],
                    key=f"manual_review_action_{case_id}",
                )
                rationale = st.text_area("Rationale", key=f"manual_review_rationale_{case_id}")

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
                            record_audit(case_id, reviewer, "manual_review_resolved", {
                                "action": action,
                                "rationale": rationale,
                            })
                            st.session_state.workflow_result = result
                            st.success("Manual review submitted.")
                            st.write(result.get("status") or "Manual review response recorded.")
                        except Exception as exc:
                            st.error(f"Unable to resume manual review workflow: {exc}")

elif page == "Human Review":
    st.header("Human Review")
    cases = _queue_cases()
    awaiting = [row for row in cases if row.get("status") in {"awaiting_human_review", "human_decision_received"}]
    if not awaiting:
        st.info("No claims currently require human decision.")
    else:
        chosen_case = st.selectbox("Case", [row["case_id"] for row in awaiting])
        case = _case_record(chosen_case)
        documents = _list_documents(chosen_case)
        if not case:
            st.warning("Case not found.")
        else:
            st.subheader(f"Case {chosen_case}")
            _render_workflow_status_bar(case.get("status"), label="Human Review workflow")
            st.write({
                "Claimant": case.get("claimant_name"),
                "Claim Type": case.get("claim_type"),
                "Amount": case.get("claim_amount"),
                "Status": case.get("status"),
            })
            if case.get("summary"):
                st.write("Summary")
                st.write(case.get("summary"))

            approver_directory = get_approver_directory()
            approver_names = [row.get("name") for row in approver_directory if row.get("active")]
            reviewer = st.selectbox("Reviewer", approver_names or ["Demo Approver", "Senior Approver", "Director Approver"])
            validation = validate_approver_limit(reviewer, float(case.get("claim_amount") or 0))
            if validation["valid"]:
                st.success(f"{reviewer} is authorized for {float(case.get('claim_amount') or 0):,.2f}.")
            else:
                st.error(f"{reviewer} cannot approve this claim amount. {validation.get('reason','')}")

            decision = st.selectbox("Decision", ["approved", "rejected", "request_more_information"], key="human_decision_selector")
            rationale = st.text_area("Decision Rationale", key="human_decision_rationale")
            requested_documents = st.text_area(
                "Requested Documents / Information",
                help="List any supporting documents or clarifications required before the claim can be finalized.",
                key="human_requested_documents",
                placeholder="itemized_bill\ntreatment_proof\nclaimant_id",
            ) if decision == "request_more_information" else ""

            if st.button("Submit Human Decision", type="primary", disabled=not validation["valid"]):
                if not rationale.strip():
                    st.error("Please provide a rationale before continuing.")
                elif decision == "request_more_information" and not requested_documents.strip():
                    st.error("Please list at least one requested document or clarification.")
                else:
                    payload = {
                        "decision": decision,
                        "rationale": rationale,
                        "reviewer": reviewer,
                    }
                    if decision == "request_more_information":
                        parsed_documents = [
                            item.strip()
                            for item in requested_documents.replace(";", "\n").splitlines()
                            if item.strip()
                        ]
                        payload["missing_documents"] = parsed_documents
                        payload["requested_documents"] = parsed_documents
                    try:
                        result = _resume_human_review(chosen_case, payload)
                        record_audit(chosen_case, reviewer, "human_decision_recorded", {"decision": decision, "rationale": rationale, "missing_documents": payload.get("missing_documents", [])})
                        st.session_state.workflow_result = result
                        if decision == "request_more_information":
                            st.info("Additional information requested. The claim remains open and is not finalized.")
                            st.write(result.get("status") or "awaiting_documents")
                        else:
                            st.success("Human review submitted.")
                            st.write(result.get("final_result", ""))
                    except Exception as exc:
                        st.error(f"Unable to resume workflow: {exc}")

elif page == "Notifications":
    st.header("Mailpit Notifications")
    messages = get_mailpit_messages()
    if not messages:
        st.info("No Mailpit messages are currently queued.")
    else:
        for message in messages[:20]:
            with st.expander(f"{message.get('Subject', 'Message')} - {message.get('From', 'unknown')}"):
                st.write({
                    "To": message.get("To"),
                    "From": message.get("From"),
                    "Subject": message.get("Subject"),
                    "Text": message.get("Text"),
                    "Created": message.get("Created"),
                })

elif page == "Audit":
    st.header("Audit History")
    case_filter = st.text_input("Filter by Case ID", key="audit_case_filter")
    action_filter = st.selectbox("Filter by Action", ["All", "claim_registered", "workflow_started", "mcp_validation_completed", "intake_completed", "document_persisted", "document_validation_completed", "documents_requested", "workflow_paused_for_documents", "manual_review_started", "manual_review_resolved", "summary_created", "case_routed", "approval_requested", "sla_scheduled", "notification_sent", "human_review_started", "additional_information_requested", "human_decision_recorded", "claim_finalized"], index=0)
    sort_order = st.radio("Sort order", ["Newest first", "Oldest first"], horizontal=True)

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
    query += " ORDER BY created_at " + ("DESC" if sort_order == "Newest first" else "ASC") + " LIMIT 200"

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
            with st.expander(f"{case_id} - {action} - {created_at}"):
                st.write({
                    "Audit ID": audit_id,
                    "Case ID": case_id,
                    "Actor": actor,
                    "Action": action,
                    "Timestamp": created_at,
                    "Details": safe_details,
                })


