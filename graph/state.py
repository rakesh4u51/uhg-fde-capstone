from typing import TypedDict, Any


class ClaimState(TypedDict, total=False):
    case_id: str

    claim_data: dict[str, Any]
    document_ids: list[str]
    document_results: list[dict[str, Any]]

    intake_result: str
    document_result: str
    summary_result: str
    routing_result: str
    sla_result: str

    missing_documents: list[str]
    document_complete: bool
    risks: list[str]
    security_flags: list[str]
    validation_issues: list[str]

    current_stage: str
    status: str
    next_step: str
    supervisor_reason: str

    human_decision: str
    human_rationale: str
    human_reviewer: str
    final_result: str
    manual_review_reason: str

    case_lookup: dict[str, Any]
    coverage_result: dict[str, Any]
    document_validation: dict[str, Any]
    approval_request: dict[str, Any]

    errors: list[str]
    failure_count: int
    retry_count: int
    supervisor_result: dict[str, Any]
    manual_review_result: dict[str, Any]