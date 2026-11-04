from langgraph.types import Command

import graph.workflow_v2 as workflow
from app import streamlit_app
from services.database import get_connection
from services.document_processor import save_document_result


def test_hydrate_claim_data_preserves_extracted_text():
    case_id = "CASE-HYDRATE-TEXT"
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM public.claims WHERE case_id = %s",
                (case_id,),
            )
            if cur.fetchone() is None:
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
                    """,
                    (case_id, "POL-1001", "Test Customer", "Medical", 25000.0, "hydration check",),
                )
            conn.commit()

    saved = save_document_result(
        case_id,
        file_path="/tmp/hydration_document.txt",
        document_id="DOC-HYDRATE-TEXT",
        result=type(
            "DocResult",
            (),
            {
                "document_type": "medical_bill",
                "extracted_text": "Claimant Name: Test Customer\nAmount: $25,000\nHospital bill",
                "confidence": 0.95,
                "injection_detected": False,
            },
        )(),
    )

    hydrated = streamlit_app._hydrate_claim_data(case_id, {"case_id": case_id})

    assert saved["extracted_text"] == "Claimant Name: Test Customer\nAmount: $25,000\nHospital bill"
    assert hydrated["document_text"] == "Claimant Name: Test Customer\nAmount: $25,000\nHospital bill"


def test_clean_claim_routes_to_summary():
    state = {
        "case_id": "CASE-100",
        "current_stage": "documents_complete",
        "document_complete": True,
        "missing_documents": [],
        "document_validation": {"continue_allowed": True},
        "risks": [],
        "errors": [],
    }

    result = workflow.supervisor_node(state)

    assert isinstance(result, Command)
    assert result.goto == "summary"
    assert result.update["next_step"] == "summary"


def test_missing_document_routes_to_await_documents(monkeypatch):
    monkeypatch.setattr(
        workflow,
        "_request_missing_documents",
        lambda case_id, missing: {"status": "awaiting_documents"},
    )

    state = {
        "case_id": "CASE-101",
        "current_stage": "documents_incomplete",
        "document_complete": False,
        "missing_documents": ["supporting_document"],
        "document_validation": {"continue_allowed": True},
        "errors": [],
    }

    result = workflow.supervisor_node(state)

    assert isinstance(result, Command)
    assert result.goto == "await_documents"
    assert "awaiting_documents" in result.update["status"]


def test_missing_documents_do_not_override_risk_manual_review():
    state = {
        "case_id": "CASE-101A",
        "current_stage": "documents_complete",
        "document_complete": True,
        "missing_documents": ["supporting_document"],
        "document_validation": {"continue_allowed": True, "missing_documents": ["supporting_document"]},
        "risks": ["low_confidence"],
        "errors": [],
    }

    result = workflow.supervisor_node(state)

    assert isinstance(result, Command)
    assert result.goto == "manual_review"
    assert "manual_review" in result.update["status"]


def test_low_confidence_document_routes_to_manual_review():
    state = {
        "case_id": "CASE-102",
        "current_stage": "documents_complete",
        "document_complete": True,
        "missing_documents": [],
        "document_validation": {"continue_allowed": True},
        "risks": ["low_confidence"],
        "errors": [],
    }

    result = workflow.supervisor_node(state)

    assert isinstance(result, Command)
    assert result.goto == "manual_review"
    assert "manual_review" in result.update["status"]


def test_prompt_injection_routes_to_manual_review():
    state = {
        "case_id": "CASE-103",
        "current_stage": "documents_complete",
        "document_complete": True,
        "missing_documents": [],
        "document_validation": {"continue_allowed": True},
        "risks": ["prompt_injection_detected"],
        "errors": [],
    }

    result = workflow.supervisor_node(state)

    assert isinstance(result, Command)
    assert result.goto == "manual_review"


def test_amount_mismatch_routes_to_manual_review():
    state = {
        "case_id": "CASE-104",
        "current_stage": "documents_complete",
        "document_complete": True,
        "missing_documents": [],
        "document_validation": {"continue_allowed": True},
        "risks": ["amount_mismatch"],
        "errors": [],
    }

    result = workflow.supervisor_node(state)

    assert isinstance(result, Command)
    assert result.goto == "manual_review"


def test_invalid_transition_is_blocked():
    state = {
        "case_id": "CASE-105",
        "current_stage": "finalized",
        "document_complete": True,
        "missing_documents": [],
        "document_validation": {"continue_allowed": True},
        "risks": [],
        "errors": [],
    }

    result = workflow.supervisor_node(state)

    assert isinstance(result, Command)
    assert result.goto == "manual_review"
    assert any("Invalid transition" in str(error) for error in result.update["errors"])


def test_human_review_resume_sets_decision():
    monkeypatch = None
    state = {
        "case_id": "CASE-106",
        "summary_result": "Summary ready",
        "routing_result": "Route to adjuster",
    }

    original_interrupt = workflow.interrupt
    workflow.interrupt = lambda payload: {
        "decision": "approved",
        "rationale": "Reviewed by authorized reviewer.",
        "reviewer": "Approver A",
    }
    try:
        result = workflow.human_review_node(state)
    finally:
        workflow.interrupt = original_interrupt

    assert result["human_decision"] == "approved"
    assert result["current_stage"] == "human_review_complete"


def test_missing_document_resume_revalidates_documents(monkeypatch):
    original_interrupt = workflow.interrupt
    workflow.interrupt = lambda payload: {"document_text": "Claimant Name: Jane Doe\nAmount: $25,000"}
    try:
        state = {
            "case_id": "CASE-107",
            "claim_data": {"document_text": ""},
            "missing_documents": ["supporting_document"],
            "current_stage": "awaiting_documents",
        }
        result = workflow.await_documents_node(state)
    finally:
        workflow.interrupt = original_interrupt

    assert isinstance(result, Command)
    assert result.goto == "documents"
    assert result.update["missing_documents"] == []
