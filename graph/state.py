from typing import Annotated, Any, TypeVar, TypedDict

T = TypeVar("T")


def _append_unique_strings(left: list[str] | None, right: list[str] | None) -> list[str]:
    merged = list(left or []) + list(right or [])
    return list(dict.fromkeys(merged))


def _freeze_for_hash(value: Any) -> Any:
    if isinstance(value, dict):
        return tuple(sorted((str(k), _freeze_for_hash(v)) for k, v in value.items()))
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_for_hash(item) for item in value)
    if isinstance(value, set):
        return tuple(sorted(_freeze_for_hash(item) for item in value))
    return value


def _append_unique_dicts(left: list[dict[str, Any]] | None, right: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    seen: set[Any] = set()
    for item in (left or []) + (right or []):
        key = _freeze_for_hash(item)
        if key not in seen:
            merged.append(item)
            seen.add(key)
    return merged


def _take_latest(left: T | None, right: T | None) -> T | None:
    return right if right is not None else left


class ClaimState(TypedDict, total=False):
    case_id: str
    thread_id: str

    claim_data: dict[str, Any]
    document_ids: Annotated[list[str], _append_unique_strings]
    document_results: Annotated[list[dict[str, Any]], _append_unique_dicts]
    document_confidences: Annotated[list[float], _append_unique_strings]
    processing_complete: Annotated[bool | None, _take_latest]
    document_complete: Annotated[bool | None, _take_latest]
    continue_allowed: Annotated[bool | None, _take_latest]
    document_confidence: float

    intake_result: str
    document_result: str
    summary_result: str
    routing_result: str
    sla_result: str

    missing_documents: Annotated[list[str], _append_unique_strings]
    risks: Annotated[list[str], _append_unique_strings]
    security_flags: Annotated[list[str], _append_unique_strings]
    validation_issues: Annotated[list[str], _append_unique_strings]

    current_stage: Annotated[str | None, _take_latest]
    status: Annotated[str | None, _take_latest]
    next_step: Annotated[str | None, _take_latest]
    supervisor_reason: Annotated[str | None, _take_latest]

    manual_review_reason: str
    manual_review_action: str
    manual_review_reviewer: str
    manual_review_rationale: str
    manual_review_result: dict[str, Any]

    human_decision: str
    human_rationale: str
    human_reviewer: str
    final_result: str

    case_lookup: dict[str, Any]
    coverage_result: dict[str, Any]
    document_validation: dict[str, Any]
    approval_request: dict[str, Any]

    errors: list[str]
    failure_count: int
    retry_count: int
    supervisor_result: dict[str, Any]
    manual_review_result: dict[str, Any]