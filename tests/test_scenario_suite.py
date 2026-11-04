from services.approver_validation import get_eligible_approvers, validate_approver_limit
from services.notifications import build_mailpit_message, send_mailpit_email
import graph.workflow_v2 as workflow
from langgraph.types import Command


def test_scenario_1_clean_claim_routes_to_summary():
    state = {
        "case_id": "CASE-200",
        "current_stage": "documents_complete",
        "document_complete": True,
        "missing_documents": [],
        "document_validation": {"continue_allowed": True},
        "risks": [],
        "errors": [],
    }
    result = workflow.supervisor_node(state)
    assert result.goto == "summary"


def test_scenario_2_missing_documents_routes_to_await_documents(monkeypatch):
    monkeypatch.setattr(workflow, "_request_missing_documents", lambda case_id, missing: {"status": "awaiting_documents"})
    state = {
        "case_id": "CASE-201",
        "current_stage": "documents_incomplete",
        "document_complete": False,
        "missing_documents": ["supporting_document"],
        "document_validation": {"continue_allowed": True},
        "errors": [],
    }
    result = workflow.supervisor_node(state)
    assert result.goto == "await_documents"


def test_scenario_3_low_confidence_routes_to_manual_review():
    state = {"case_id": "CASE-202", "current_stage": "documents_complete", "document_complete": True, "missing_documents": [], "document_validation": {"continue_allowed": True}, "risks": ["low_confidence"], "errors": []}
    result = workflow.supervisor_node(state)
    assert result.goto == "manual_review"


def test_scenario_4_prompt_injection_routes_to_manual_review():
    state = {"case_id": "CASE-203", "current_stage": "documents_complete", "document_complete": True, "missing_documents": [], "document_validation": {"continue_allowed": True}, "risks": ["prompt_injection_detected"], "errors": []}
    result = workflow.supervisor_node(state)
    assert result.goto == "manual_review"


def test_scenario_5_invalid_transition_is_blocked():
    state = {"case_id": "CASE-204", "current_stage": "finalized", "document_complete": True, "missing_documents": [], "document_validation": {"continue_allowed": True}, "risks": [], "errors": []}
    result = workflow.supervisor_node(state)
    assert result.goto == "manual_review"


def test_scenario_6_approver_limit_allows_small_claim():
    result = validate_approver_limit("Demo Approver", 20000)
    assert result["valid"] is True


def test_scenario_7_approver_limit_blocks_large_claim():
    result = validate_approver_limit("Demo Approver", 50000)
    assert result["valid"] is False


def test_scenario_8_mailpit_payload_is_built_for_demo():
    message = build_mailpit_message("approver@example.com", "Follow-up", "Please review case CASE-205.")
    assert message["subject"] == "Follow-up"
    assert message["to"] == ["approver@example.com"]

    sent = send_mailpit_email("approver@example.com", "Follow-up", "Please review case CASE-205.")
    assert "success" in sent
    assert "payload" in sent or sent["success"] is True


def test_eligible_approvers_include_higher_limit_user():
    eligible = get_eligible_approvers(75000)
    assert "Senior Approver" in eligible or "Director Approver" in eligible
