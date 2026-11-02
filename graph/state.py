from typing import TypedDict, Any


class ClaimState(TypedDict, total=False):
    case_id: str

    claim_data: dict[str, Any]

    intake_result: str
    document_result: str
    summary_result: str
    routing_result: str
    sla_result: str

    missing_documents: list[str]
    risks: list[str]

    current_stage: str
    status: str

    human_decision: str
    human_rationale: str
    human_reviewer: str
    final_result: str

    errors: list[str]