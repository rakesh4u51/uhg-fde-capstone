import pytest

from agents.summary_agent_v2 import build_grounded_summary


@pytest.mark.parametrize(
    ("case", "policy", "coverage", "validation", "expected_text"),
    [
        (
            {"case_id": "CASE-100", "claim_type": "Medical", "claim_amount": 25000},
            {"policy_number": "POL-1001", "status": "active", "coverage_limit": 50000, "covered_claim_types": ["Medical"]},
            {"covered": True, "reason": "Claim is within policy coverage"},
            {"missing_documents": [], "risks": [], "issues": []},
            "POL-1001",
        ),
        (
            {"case_id": "CASE-101", "claim_type": "Medical", "claim_amount": 25000},
            {"policy_number": "POL-1001", "status": "active", "coverage_limit": 50000, "covered_claim_types": ["Medical"]},
            {"covered": True, "reason": "Claim is within policy coverage"},
            {"missing_documents": ["medical_bill"], "risks": [], "issues": []},
            "medical_bill",
        ),
        (
            {"case_id": "CASE-102", "claim_type": "Medical", "claim_amount": 30000},
            {"policy_number": "POL-1001", "status": "active", "coverage_limit": 50000, "covered_claim_types": ["Medical"]},
            {"covered": True, "reason": "Claim is within policy coverage"},
            {"missing_documents": [], "risks": ["amount_mismatch"], "issues": ["Amount mismatch between document and claim amount."]},
            "amount_mismatch",
        ),
        (
            {"case_id": "CASE-103", "claim_type": "Medical", "claim_amount": 25000},
            {"policy_number": "POL-1001", "status": "active", "coverage_limit": 50000, "covered_claim_types": ["Medical"]},
            {"covered": True, "reason": "Claim is within policy coverage"},
            {"missing_documents": [], "risks": ["prompt_injection_detected"], "issues": ["Prompt injection detected; document handling was restricted."]},
            "prompt_injection_detected",
        ),
        (
            {"case_id": "CASE-104", "claim_type": "Medical", "claim_amount": 75000},
            {"policy_number": "POL-1001", "status": "active", "coverage_limit": 50000, "covered_claim_types": ["Medical"]},
            {"covered": False, "reason": "Claim amount exceeds policy limit"},
            {"missing_documents": [], "risks": ["policy_limit_exceeded"], "issues": ["Claim amount exceeds policy limit"]},
            "exceeds policy limit",
        ),
    ],
)
def test_grounded_summary_includes_policy_references(case, policy, coverage, validation, expected_text):
    summary = build_grounded_summary(
        case_id=case["case_id"],
        case=case,
        policy=policy,
        coverage=coverage,
        documents=[{"document_type": "medical_bill"}],
        fields={"claimant_name": "Test Customer", "claim_type": case["claim_type"]},
        validation=validation,
    )

    assert "FACTS:" in summary
    assert "EVIDENCE:" in summary
    assert "POLICY AND COVERAGE:" in summary
    assert "Policy References:" in summary
    assert expected_text in summary
    assert "approved" not in summary.lower()
    assert "rejected" not in summary.lower()
    assert "settled" not in summary.lower()
