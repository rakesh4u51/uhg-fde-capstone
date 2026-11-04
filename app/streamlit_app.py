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

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from graph.v2_graph_factory import get_v2_graph
from services.approver_validation import get_approver_directory, get_eligible_approvers, validate_approver_limit
from services.database import DATABASE_URL
from services.document_processor import process_document, save_document_result

load_dotenv()

st.set_page_config(
    page_title="Intelligent Claims Processing",
    page_icon="⚕️",
    layout="wide",
)


def _case_record(case_id: str) -> dict[str, Any] | None:
    with psycopg.connect(DATABASE_URL) as conn:
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
                    current_stage,
                    created_at,
                    updated_at,
                    manual_review_reason,
                    risks,
                    security_flags,
                    validation_issues
                FROM public.claims
                WHERE case_id = %s
                """,
                (case_id,),
            )
            row = cur.fetchone()
    if row is None:
        return None
    return dict(row)


def _queue_cases() -> list[dict[str, Any]]:
    with psycopg.connect(DATABASE_URL) as conn:
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
    return [dict(row) for row in rows]


def _list_documents(case_id: str) -> list[dict[str, Any]]:
    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    document_id,
                    case_id,
                    file_name,
                    document_type,
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
    return [dict(row) for row in rows]


def _insert_case(case_id: str, policy_number: str, claimant_name: str, claim_type: str, claim_amount: float, description: str) -> dict[str, Any]:
    with psycopg.connect(DATABASE_URL) as conn:
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
    return dict(row)


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
        saved.append(payload)

    return saved


def _get_thread_id(case_id: str) -> str:
    thread_map = st.session_state.setdefault("workflow_threads", {})
    if case_id not in thread_map:
        thread_map[case_id] = f"{case_id}-{uuid.uuid4().hex[:10]}"
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


def _start_case_workflow(case_id: str, claim_data: dict[str, Any]) -> dict[str, Any]:
    thread_id = _get_thread_id(case_id)
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

st.title("Intelligent Claims Processing")
st.caption("AI-assisted claims processing with human-in-the-loop controls")
st.divider()

page = st.sidebar.radio(
    "Navigation",
    [
        "Submit Claim",
        "Case Queue",
        "Case Workspace",
        "Manual Review",
        "Human Review",
        "Audit",
    ],
)

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
                _persist_uploaded_documents(case_id, uploaded_files)
                claim_data = {
                    "case_id": case_id,
                    "policy_number": policy_number,
                    "claimant_name": claimant_name,
                    "claim_type": claim_type,
                    "claim_amount": float(claim_amount),
                    "description": description,
                }
                result = _start_case_workflow(case_id, claim_data)
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
        st.dataframe(queue_df, use_container_width=True)

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
                st.metric("Stage", case.get("current_stage") or "unknown")

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
    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT case_id, claimant_name, claim_type, claim_amount, manual_review_reason, risks, security_flags, validation_issues, current_stage, status
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
            case_id, claimant_name, claim_type, claim_amount, reason, risks, security_flags, validation_issues, current_stage, status = row
            with st.expander(f"{case_id} - {claimant_name}"):
                st.write({
                    "Claim Type": claim_type,
                    "Claim Amount": claim_amount,
                    "Current Stage": current_stage,
                    "Status": status,
                    "Manual Review Reason": reason,
                    "Risks": risks,
                    "Security Flags": security_flags,
                    "Validation Issues": validation_issues,
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
                        st.session_state.workflow_result = result
                        st.success("Human review submitted.")
                        st.write(result.get("final_result", ""))
                    except Exception as exc:
                        st.error(f"Unable to resume workflow: {exc}")

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


