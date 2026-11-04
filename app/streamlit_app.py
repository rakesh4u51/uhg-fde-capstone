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
            gap: 0.6rem;
        }

        [role="radiogroup"] > label {
            background: rgba(255, 255, 255, 0.04) !important;
            border: 1px solid rgba(255, 255, 255, 0.15);
            border-radius: 12px;
            padding: 0.82rem 0.9rem;
            margin: 0.2rem 0;
            transition: all 0.2s ease;
            color: #ffffff !important;
            font-weight: 700;
            letter-spacing: 0.01em;
            opacity: 1;
            box-shadow: none;
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
    return row


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
    return rows


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


def _new_thread_id(case_id: str) -> str:
    return f"{case_id}-{uuid.uuid4().hex[:12]}"


def _get_thread_id(case_id: str) -> str:
    thread_map = st.session_state.setdefault("workflow_threads", {})
    if case_id not in thread_map:
        thread_map[case_id] = _new_thread_id(case_id)
    return thread_map[case_id]


def _resume_human_review(case_id: str, human_input: dict[str, str]) -> dict[str, Any]:
    thread_id = _get_thread_id(case_id)
    async def _run() -> dict[str, Any]:
        async with get_v2_graph() as graph:
            return await graph.ainvoke(
                Command(resume=human_input),
                config={"configurable": {"thread_id": thread_id}},
            )

    return asyncio.run(_run())


def _start_case_workflow(case_id: str, claim_data: dict[str, Any], thread_id: str | None = None) -> dict[str, Any]:
    thread_id = thread_id or _get_thread_id(case_id)
    st.session_state.setdefault("workflow_threads", {})[case_id] = thread_id
    initial_state = {
        "case_id": case_id,
        "claim_data": claim_data,
        "current_stage": "submitted",
        "status": "submitted",
        "errors": [],
    }

    async def _run() -> dict[str, Any]:
        async with get_v2_graph() as graph:
            return await graph.ainvoke(
                initial_state,
                config={"configurable": {"thread_id": thread_id}},
            )

    return asyncio.run(_run())


st.set_page_config(
    page_title="Intelligent Claims Processing",
    page_icon="⚕️",
    layout="wide",
)

if "workflow_result" not in st.session_state:
    st.session_state.workflow_result = None
if "selected_case" not in st.session_state:
    st.session_state.selected_case = None

st.markdown(
    """
    <div style="
        background: linear-gradient(135deg, rgba(37,99,235,0.12), rgba(14,165,233,0.06));
        border: 1px solid rgba(37,99,235,0.14);
        border-radius: 20px;
        padding: 1.3rem 1.5rem;
        margin-bottom: 1.25rem;
        box-shadow: 0 14px 30px rgba(37,99,235,0.08);
    ">
        <div style="font-size: 0.82rem; font-weight: 700; letter-spacing: 0.12em; text-transform: uppercase; color: #2563eb; margin-bottom: 0.45rem;">
            Claims Operations Console
        </div>
        <div style="font-size: 2.25rem; font-weight: 800; color: #0f172a; line-height: 1.1;">
            Intelligent Claims Processing
        </div>
        <div style="margin-top: 0.45rem; color: #475569; font-size: 1rem;">
            AI-assisted claims processing with human-in-the-loop controls
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)
st.divider()

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
                st.session_state.setdefault("workflow_threads", {})[case_id] = thread_id
                print("[UI] Starting LangGraph:", thread_id)
                result = _start_case_workflow(case_id, claim_data, thread_id=thread_id)
                record_audit(case_id, "streamlit_ui", "claim_submitted", {"policy_number": policy_number, "claim_type": claim_type, "claim_amount": float(claim_amount)})
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
            with col1:
                st.metric("Case ID", case.get("case_id"))
            with col2:
                st.metric("Status", case.get("status"))
            with col3:
                st.metric("Stage", case.get("status") or "unknown")

            st.subheader("Claim Information")
            st.write({
                "Policy": case.get("policy_number"),
                "Claimant": case.get("claimant_name"),
                "Type": case.get("claim_type"),
                "Amount": case.get("claim_amount"),
                "Description": case.get("description"),
            })

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

elif page == "Manual Review":
    st.header("Manual Review")
    with psycopg.connect(DATABASE_URL, row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT case_id, claimant_name, claim_type, claim_amount, status, summary, description
                FROM public.claims
                WHERE status = 'manual_review'
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
            with st.expander(f"{case_id} - {claimant_name}"):
                st.write({
                    "Claim Type": claim_type,
                    "Claim Amount": claim_amount,
                    "Current Stage": status,
                    "Status": status,
                    "Description": description,
                    "Summary": summary,
                })

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

            if st.button("Submit Human Decision", type="primary", disabled=not validation["valid"]):
                if not rationale.strip():
                    st.error("Please provide a rationale before continuing.")
                else:
                    try:
                        result = _resume_human_review(chosen_case, {
                            "decision": decision,
                            "rationale": rationale,
                            "reviewer": reviewer,
                        })
                        record_audit(chosen_case, reviewer, "human_decision_recorded", {"decision": decision, "rationale": rationale})
                        st.session_state.workflow_result = result
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
    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    id,
                    case_id,
                    actor,
                    action,
                    details,
                    created_at
                FROM public.claim_audit
                ORDER BY created_at DESC
                LIMIT 100
                """
            )
            rows = cur.fetchall()

    if not rows:
        st.info("No audit records found.")
    else:
        for row in rows:
            audit_id, case_id, actor, action, details, created_at = row
            with st.expander(f"{case_id} - {action}"):
                st.write({
                    "Audit ID": audit_id,
                    "Case ID": case_id,
                    "Actor": actor,
                    "Action": action,
                    "Timestamp": created_at,
                    "Details": details,
                })


