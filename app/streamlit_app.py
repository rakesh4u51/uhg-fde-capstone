import sys
from pathlib import Path

import streamlit as st
from langgraph.types import Command


PROJECT_ROOT = Path(__file__).resolve().parent.parent

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from graph.workflow_v2 import graph

import os
import psycopg
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")


st.set_page_config(
    page_title="Intelligent Claims Processing",
    page_icon="⚕️",
    layout="wide",
)


# -------------------------------------------------
# Session State
# -------------------------------------------------

if "workflow_started" not in st.session_state:
    st.session_state.workflow_started = False

if "thread_id" not in st.session_state:
    st.session_state.thread_id = None

if "workflow_result" not in st.session_state:
    st.session_state.workflow_result = None

if "claim_data" not in st.session_state:
    st.session_state.claim_data = None


# -------------------------------------------------
# Header
# -------------------------------------------------

st.title("Intelligent Claims Processing")
st.caption(
    "AI-assisted claims processing with human-in-the-loop decision control"
)
st.divider()


# -------------------------------------------------
# Sidebar
# -------------------------------------------------

page = st.sidebar.radio(
    "Navigation",
    [
        "Submit Claim",
        "Case Status",
        "Human Review",
        "Audit",
    ],
)


# -------------------------------------------------
# Submit Claim
# -------------------------------------------------

if page == "Submit Claim":
    st.header("Submit Claim")

    with st.form("claim_form"):
        case_id = st.text_input("Case ID", value="CASE-001")
        policy_number = st.text_input("Policy Number", value="POL-1001")
        claimant_name = st.text_input("Claimant Name", value="Test Customer")
        claim_type = st.selectbox("Claim Type", ["Medical", "Vehicle"])
        claim_amount = st.number_input("Claim Amount", min_value=0.0, value=25000.0)
        description = st.text_area(
            "Description",
            value="Hospital treatment claim with medical bill.",
        )
        document_type = st.selectbox("Document Type", ["medical_bill", "unknown"])
        document_text = st.text_area(
            "Extracted Document Text",
            value="Hospital bill for Test Customer. Total amount 25000.",
        )
        document_confidence = st.slider(
            "Document Confidence",
            min_value=0.0,
            max_value=1.0,
            value=0.98,
            step=0.01,
        )

        submitted = st.form_submit_button("Process Claim", type="primary")

    if submitted:
        thread_id = f"{case_id}-streamlit"
        config = {"configurable": {"thread_id": thread_id}}

        claim_data = {
            "case_id": case_id,
            "policy_number": policy_number,
            "claimant_name": claimant_name,
            "claim_type": claim_type,
            "claim_amount": claim_amount,
            "description": description,
            "document_type": document_type,
            "document_text": document_text,
            "document_confidence": document_confidence,
        }

        initial_state = {
            "case_id": case_id,
            "claim_data": claim_data,
            "current_stage": "submitted",
            "status": "submitted",
            "errors": [],
        }

        st.session_state.thread_id = thread_id
        st.session_state.claim_data = claim_data

        with st.spinner("Agents are processing the claim..."):
            try:
                result = graph.invoke(initial_state, config=config)
                st.session_state.workflow_result = result
                st.session_state.workflow_started = True
                st.success("Claim processing started successfully.")
            except Exception as exc:  # pragma: no cover - UI feedback only
                st.error(f"Workflow error: {exc}")


# -------------------------------------------------
# Case Status
# -------------------------------------------------

elif page == "Case Status":
    st.header("Case Status")
    result = st.session_state.workflow_result

    if not result:
        st.info("Submit a claim first.")
    else:
        col1, col2, col3 = st.columns(3)

        with col1:
            st.metric("Case", result.get("case_id", "Unknown"))

        with col2:
            st.metric("Stage", result.get("current_stage", "Unknown"))

        with col3:
            st.metric("Status", result.get("status", "Unknown"))

        st.divider()

        with st.expander("Intake Result", expanded=False):
            st.write(result.get("intake_result", "Not available"))

        with st.expander("Document Analysis", expanded=False):
            st.write(result.get("document_result", "Not available"))

        st.subheader("Case Summary")
        st.write(result.get("summary_result", "Not available"))

        st.subheader("Routing")
        st.write(result.get("routing_result", "Not available"))

        st.subheader("SLA / Communication")
        st.write(result.get("sla_result", "Not available"))


# -------------------------------------------------
# Human Review
# -------------------------------------------------

elif page == "Human Review":
    st.header("Human Review")
    result = st.session_state.workflow_result

    if not result:
        st.info("No claim is currently awaiting review.")
    else:
        st.warning("Final claim decisions require authorized human review.")

        st.subheader("Case Summary")
        st.write(result.get("summary_result", "Not available"))

        st.subheader("Routing Recommendation")
        st.write(result.get("routing_result", "Not available"))

        decision = st.selectbox(
            "Decision",
            ["approved", "rejected", "request_more_information"],
        )
        reviewer = st.text_input("Reviewer", value="Demo Approver")
        rationale = st.text_area("Decision Rationale")

        if st.button("Submit Human Decision", type="primary"):
            if not rationale.strip():
                st.error("Please provide a rationale.")
            else:
                config = {"configurable": {"thread_id": st.session_state.thread_id}}
                human_input = {
                    "decision": decision,
                    "rationale": rationale,
                    "reviewer": reviewer,
                }

                try:
                    resumed = graph.invoke(
                        Command(resume=human_input),
                        config=config,
                    )
                    st.session_state.workflow_result = resumed
                    st.success("Human decision submitted.")
                    st.write(resumed.get("final_result", ""))
                except Exception as exc:  # pragma: no cover - UI feedback only
                    st.error(f"Resume failed: {exc}")


# -------------------------------------------------
# Audit
# -------------------------------------------------

elif page == "Audit":

    st.header("Audit History")

    try:

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

                audit_id = row[0]
                case_id = row[1]
                actor = row[2]
                action = row[3]
                details = row[4]
                created_at = row[5]

                with st.expander(
                    f"{case_id} - {action}"
                ):

                    st.write(
                        "Audit ID:",
                        audit_id,
                    )

                    st.write(
                        "Case ID:",
                        case_id,
                    )

                    st.write(
                        "Actor:",
                        actor,
                    )

                    st.write(
                        "Action:",
                        action,
                    )

                    st.write(
                        "Timestamp:",
                        created_at,
                    )

                    st.write(
                        "Details:",
                        details,
                    )

    except Exception as exc:

        st.error(
            f"Unable to load audit history: {exc}"
        )








