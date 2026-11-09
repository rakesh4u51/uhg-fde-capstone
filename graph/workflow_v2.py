import asyncio
from typing import Any

from fastmcp import Client
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, Send, interrupt

from services.document_processor import (
    _extract_amount,
    _extract_claimant_name,
    _extract_policy_number,
    _extract_service_date,
)

from graph.state import ClaimState
from mcp_servers.workflow_mcp.server import mcp as workflow_mcp
from services.audit import record_audit
from services.database import DATABASE_URL, get_connection
from services.mcp_client import (
    check_coverage,
    get_case,
    request_human_approval,
    validate_documents,
)
from services.notifications import (
    notify_approval_request,
    notify_missing_documents,
    notify_sla_escalation,
    schedule_case_follow_up,
)
from services.v2_agent_runner import (
    run_document_v2,
    run_intake_v2,
    run_routing_v2,
    run_sla_v2,
    run_summary_v2,
)

FAILURE_THRESHOLD = 2
BLOCKING_VALIDATION_RISKS = {
    "low_confidence",
    "prompt_injection_detected",
    "amount_mismatch",
    "claimant_name_mismatch",
    "policy_inconsistency",
}


def _canonical_status(value: Any) -> str:
    status = str(value or "").strip().lower()
    if not status:
        return ""
    aliases = {
        "awaiting_document": "awaiting_documents",
        "awaiting_documents2": "awaiting_documents",
        "awaiting_documents_2": "awaiting_documents",
        "documents_waiting": "awaiting_documents",
    }
    return aliases.get(status, status)


def _unique(values: list[str] | None) -> list[str]:
    return list(dict.fromkeys((values or [])))


def _blocking_risks_for_state(state: ClaimState) -> set[str]:
    return set(state.get("risks") or []) & BLOCKING_VALIDATION_RISKS


def _request_missing_documents(case_id: str, missing_documents: list[str]) -> dict[str, Any]:
    async def _invoke() -> dict[str, Any]:
        async with Client(workflow_mcp) as client:
            return await client.call_tool(
                "request_documents",
                {
                    "case_id": case_id,
                    "documents": missing_documents,
                },
            )

    result = asyncio.run(_invoke())
    if hasattr(result, "data"):
        return result.data
    return result


def _required_documents_for_claim_type(claim_type: str | None) -> list[str]:
    value = (claim_type or "").strip().lower()
    normalized = "".join(value.split())

    if any(token in normalized for token in ("medical", "health", "hospital", "injury")):
        return ["medical_bill"]
    if any(token in normalized for token in ("vehicle", "car", "auto", "motor")):
        return ["accident_report", "repair_estimate"]
    if any(token in normalized for token in ("property", "home", "dwelling", "fire")):
        return ["property_damage_photos", "repair_invoice"]
    return ["supporting_document"]


def _normalise_document_data(state: ClaimState) -> dict[str, Any]:
    data = dict(state.get("claim_data") or {})
    if "document_text" not in data:
        data["document_text"] = ""
    if "document_confidence" not in data:
        data["document_confidence"] = 0.0
    if "document_type" not in data:
        data["document_type"] = "unknown"
    if "document_ids" not in data:
        data["document_ids"] = state.get("document_ids") or []
    return data


def _load_document_ids(case_id: str) -> list[str]:
    if not case_id:
        return []
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT document_id
                FROM public.documents
                WHERE case_id = %s
                ORDER BY created_at ASC
                """,
                (case_id,),
            )
            rows = cur.fetchall()
    return [str(row["document_id"]) for row in rows if row.get("document_id")]


def _safe_claim_context(state: ClaimState) -> dict[str, Any]:
    claim_data = _normalise_document_data(state)
    claim_data["case_id"] = state.get("case_id")
    claim_data["document_ids"] = list(state.get("document_ids") or _load_document_ids(state.get("case_id") or ""))
    return claim_data


def _document_result_failure(case_id: str, document_id: str, message: str) -> dict[str, Any]:
    return {
        "document_id": document_id,
        "case_id": case_id,
        "document_type": "unknown",
        "confidence": 0.0,
        "processing_complete": False,
        "complete": False,
        "extracted_fields": {},
        "missing_fields": [],
        "risks": ["document_processing_failure"],
        "security_flags": [],
        "validation_issues": [message],
    }


def _process_document_worker_result(case_id: str, document_id: str, claim_data: dict[str, Any]) -> dict[str, Any]:
    if not case_id or not document_id:
        return _document_result_failure(case_id or "", document_id or "", "Missing case_id or document_id.")

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT document_id, case_id, file_name, document_type, extracted_text, confidence, injection_detected, created_at
                FROM public.documents
                WHERE case_id = %s AND document_id = %s
                ORDER BY created_at ASC
                LIMIT 1
                """,
                (case_id, document_id),
            )
            row = cur.fetchone()

    if row is None:
        return _document_result_failure(case_id, document_id, f"Document {document_id} was not found for case {case_id}.")

    extracted_text = (row.get("extracted_text") or "").strip()
    document_type = row.get("document_type") or "unknown"
    confidence = float(row.get("confidence") or 0.0)
    injection_detected = bool(row.get("injection_detected"))

    stored_claimant = (claim_data.get("claimant_name") or "").strip()
    stored_policy = (claim_data.get("policy_number") or "").strip()
    stored_amount = claim_data.get("claim_amount")
    threshold = float(claim_data.get("document_confidence_threshold") or claim_data.get("confidence_threshold") or 0.75)

    extracted_fields = {
        "claimant_name": _extract_claimant_name(extracted_text),
        "policy_number": _extract_policy_number(extracted_text),
        "amount": _extract_amount(extracted_text),
        "service_date": _extract_service_date(extracted_text),
    }

    missing_fields = [field for field, value in extracted_fields.items() if value in (None, "", 0, 0.0)]
    risks: list[str] = []
    security_flags: list[str] = []
    validation_issues: list[str] = []

    if injection_detected:
        risks.append("prompt_injection_detected")
        security_flags.append("prompt_injection_detected")
        validation_issues.append("Prompt injection detected; document handling was restricted.")

    doc_claimant = (extracted_fields.get("claimant_name") or "").strip()
    if doc_claimant and stored_claimant and doc_claimant.lower() != stored_claimant.lower():
        risks.append("claimant_name_mismatch")
        validation_issues.append("Claimant name mismatch between document and case record.")

    doc_policy = (extracted_fields.get("policy_number") or "").strip()
    if doc_policy and stored_policy and doc_policy.lower() != stored_policy.lower():
        risks.append("policy_inconsistency")
        validation_issues.append("Policy number mismatch between document and case record.")

    doc_amount = extracted_fields.get("amount")
    if doc_amount is not None and stored_amount is not None:
        if abs(float(doc_amount) - float(stored_amount)) > 0.01:
            risks.append("amount_mismatch")
            validation_issues.append("Amount mismatch between document and claim amount.")

    if confidence < threshold:
        risks.append("low_confidence")
        validation_issues.append("Low confidence extraction requires manual review.")

    processing_complete = bool(document_id) and bool(document_type) and bool(extracted_text) and not bool(risks or validation_issues or security_flags)
    result = {
        "document_id": document_id,
        "case_id": case_id,
        "document_type": document_type,
        "confidence": round(confidence, 4),
        "processing_complete": processing_complete,
        "complete": processing_complete,
        "extracted_fields": {k: v for k, v in extracted_fields.items() if v not in (None, "", 0, 0.0)},
        "missing_fields": missing_fields,
        "risks": list(dict.fromkeys(risks)),
        "security_flags": list(dict.fromkeys(security_flags)),
        "validation_issues": list(dict.fromkeys(validation_issues)),
    }
    record_audit(
        case_id,
        "document_worker",
        "document_processing_completed",
        {
            "document_id": document_id,
            "document_type": document_type,
            "confidence": result["confidence"],
            "risks": result["risks"],
            "security_flags": result["security_flags"],
            "complete": result["complete"],
        },
        stage="documents_processing",
    )
    return result


def _persist_case_status(case_id: str, status: str, current_stage: str | None = None) -> None:
    if not case_id:
        return
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE public.claims
                SET status = %s,
                    updated_at = NOW()
                WHERE case_id = %s
                """,
                (status, case_id),
            )
        conn.commit()


def _transition_guard(state: ClaimState) -> tuple[str, str]:
    current_stage = state.get("current_stage", "submitted")
    missing_documents = state.get("missing_documents") or []
    risks = set(state.get("risks") or [])
    security_flags = set(state.get("security_flags") or [])
    validation = state.get("document_validation") or {}
    document_complete = state.get("document_complete")
    human_decision = state.get("human_decision")

    if human_decision:
        return "finalize", "Human decision received; finalization is required."

    if current_stage in {"submitted", "mcp_validation_complete"}:
        return "intake", "Intake processing must run before the claim can continue."

    if current_stage == "intake_complete":
        return "documents", "Documents are required before summary generation."

    if document_complete is False:
        return "await_documents", "Document processing is incomplete."

    if validation.get("continue_allowed") is False and current_stage not in {"submitted", "mcp_validation_complete", "intake_complete"}:
        return "manual_review", "Document validation blocked continuation."

    if (any(flag in risks for flag in {"low_confidence", "prompt_injection_detected", "amount_mismatch", "claimant_name_mismatch", "policy_inconsistency"}) or security_flags) and current_stage not in {"submitted", "mcp_validation_complete", "intake_complete"}:
        return "manual_review", "Security or validation risk requires manual review."

    if missing_documents:
        return "await_documents", "Missing required documents detected."

    if current_stage in {"documents_complete", "documents_revalidated"}:
        if missing_documents or document_complete is False or validation.get("continue_allowed") is False or _blocking_risks_for_state(state) or security_flags:
            return "manual_review", "Unresolved validation risk prevents summary generation."
        return "summary", "Valid documents are ready for summary generation."

    if current_stage == "summary_complete":
        return "routing", "Summary is complete and routing can proceed."

    if current_stage == "routing_complete":
        return "sla", "Routing is complete and SLA handling can proceed."

    if current_stage == "sla_complete":
        return "human_review", "SLA is complete and an authorized human review is required."

    if current_stage == "human_review_complete":
        return "finalize", "Human review is complete and the claim can be finalized."

    if current_stage in {"awaiting_documents", "manual_review_complete"}:
        return "documents", "Workflow is resuming validation or review."

    return "manual_review", f"Invalid transition from {current_stage}; workflow is blocked."


def intake_node(state: ClaimState):
    print("\n[1] Running Intake Agent V2")

    result = asyncio.run(run_intake_v2(state["case_id"]))
    record_audit(
        state["case_id"],
        "intake_agent",
        "intake_completed",
        {
            "status": "intake_complete",
            "result_preview": result[:180] if isinstance(result, str) else str(result),
        },
        stage="intake_complete",
    )

    return {
        "intake_result": result,
        "current_stage": "intake_complete",
        "status": "intake_complete",
    }


def document_node(state: ClaimState):
    print("\n[2] Running Document Agent V2")

    case_id = state.get("case_id")
    claim_data = _safe_claim_context(state)
    preferred_document_id = str(state.get("document_id") or state.get("resume_document_id") or claim_data.get("document_id") or "").strip()
    document_ids = list(state.get("document_ids") or _load_document_ids(case_id or ""))
    if preferred_document_id:
        document_ids = [doc_id for doc_id in document_ids if doc_id == preferred_document_id]
        if not document_ids:
            document_ids = [preferred_document_id]
    if document_ids:
        worker_calls = [
            Send(
                "document_worker",
                {
                    "case_id": case_id,
                    "document_id": doc_id,
                    "claim_data": claim_data,
                    "thread_id": state.get("thread_id"),
                },
            )
            for doc_id in document_ids
        ]
        record_audit(
            case_id,
            "workflow",
            "document_processing_started",
            {
                "document_count": len(document_ids),
                "document_ids": document_ids,
                "thread_id": state.get("thread_id"),
            },
            stage="documents_processing",
        )
        return Command(
            goto=worker_calls,
            update={
                "document_ids": document_ids,
                "document_complete": False,
                "processing_complete": False,
                "current_stage": "documents_processing",
                "status": "documents_processing",
            },
        )

    claim_data = _normalise_document_data(state)
    document_text = claim_data.get("document_text", "").strip()
    if not document_text:
        missing_documents = _required_documents_for_claim_type(claim_data.get("claim_type"))
        return {
            "document_result": "No supporting document text was provided.",
            "document_complete": False,
            "missing_documents": missing_documents,
            "current_stage": "awaiting_documents",
            "status": "awaiting_documents",
        }

    result = asyncio.run(run_document_v2(case_id))

    return {
        "document_result": result,
        "document_complete": True,
        "missing_documents": [],
        "document_results": [{"document_id": case_id, "result": result}],
        "current_stage": "documents_complete",
        "status": "documents_complete",
    }


def document_worker_node(state: ClaimState):
    case_id = state.get("case_id")
    document_id = state.get("document_id")
    claim_data = state.get("claim_data") or {}
    record_audit(
        case_id,
        "document_worker",
        "document_processing_started",
        {"document_id": document_id, "case_id": case_id, "thread_id": state.get("thread_id")},
        stage="documents_processing",
    )
    result = _process_document_worker_result(case_id, document_id, claim_data)
    return {
        "document_results": [result],
    }


def document_aggregation_node(state: ClaimState):
    document_results = list(state.get("document_results") or [])
    document_ids = list(state.get("document_ids") or _load_document_ids(state.get("case_id") or ""))
    claim_data = _normalise_document_data(state)
    claim_type = (claim_data.get("claim_type") or "").strip()

    unique_results = []
    seen_result_ids: set[str] = set()
    for item in document_results:
        doc_id = str(item.get("document_id") or "").strip()
        if doc_id and doc_id in seen_result_ids:
            continue
        if doc_id:
            seen_result_ids.add(doc_id)
        unique_results.append(item)

    document_count = len(unique_results)
    document_types = sorted({str(item.get("document_type") or "unknown") for item in unique_results})
    confidence_values = [float(item.get("confidence") or 0.0) for item in unique_results]
    minimum_confidence = min(confidence_values) if confidence_values else 0.0
    required_documents = _required_documents_for_claim_type(claim_type)
    present_types = {str(item.get("document_type") or "unknown").lower() for item in unique_results}
    generic_document_types = {"unknown", "supporting_document", "receipt", "claim_form", "policy_document", "letter"}
    all_workers_succeeded = bool(unique_results) and all(item.get("processing_complete") is True for item in unique_results)
    missing_required: list[str] = []
    for required in required_documents:
        matched = False
        for present in present_types:
            if required == present or required in {"medical_bill", "clinical_documentation", "discharge_summary"} and present in {"medical_bill", "clinical_documentation", "discharge_summary"}:
                matched = True
                break
            if required == "accident_report" and present == "accident_report":
                matched = True
                break
            if required == "repair_estimate" and present == "repair_estimate":
                matched = True
                break
            if required == "property_damage_photos" and present == "property_damage_photos":
                matched = True
                break
            if required == "repair_invoice" and present == "repair_invoice":
                matched = True
                break
            if present in generic_document_types and all_workers_succeeded:
                matched = True
                break
        if not matched:
            missing_required.append(required)

    all_risks: set[str] = set()
    all_security_flags: set[str] = set()
    all_validation_issues: set[str] = set()
    worker_failures = False
    for item in unique_results:
        for risk in item.get("risks") or []:
            all_risks.add(str(risk))
        for flag in item.get("security_flags") or []:
            all_security_flags.add(str(flag))
        for issue in item.get("validation_issues") or []:
            all_validation_issues.add(str(issue))
        if item.get("processing_complete") is False:
            worker_failures = True

    overall_document_complete = bool(unique_results) and not missing_required and all_workers_succeeded
    threshold = float(claim_data.get("document_confidence_threshold") or claim_data.get("confidence_threshold") or 0.75)
    continue_allowed = (
        overall_document_complete
        and all_workers_succeeded
        and minimum_confidence >= threshold
        and not all_risks
        and not all_security_flags
        and not all_validation_issues
    )
    validation_payload = {
        "case_id": state.get("case_id"),
        "continue_allowed": continue_allowed,
        "document_count": document_count,
        "document_types": document_types,
        "required_documents": required_documents,
        "missing_documents": missing_required,
        "complete": overall_document_complete,
        "processing_complete": all_workers_succeeded,
        "confidence": round(minimum_confidence, 4),
        "confidence_threshold": threshold,
        "risks": sorted(all_risks),
        "security_flags": sorted(all_security_flags),
        "issues": sorted(all_validation_issues),
        "worker_failures": worker_failures,
    }

    record_audit(
        state.get("case_id"),
        "document_aggregate",
        "document_aggregation_completed",
        {
            "document_count": document_count,
            "document_types": document_types,
            "minimum_confidence": round(minimum_confidence, 4),
            "missing_documents": missing_required,
            "risks": validation_payload["risks"],
            "security_flags": validation_payload["security_flags"],
            "continue_allowed": continue_allowed,
        },
        stage="documents_complete",
    )

    aggregate_summary = (
        f"Document processing complete for {document_count} document(s): "
        f"types={', '.join(document_types) if document_types else 'unknown'}; "
        f"confidence={round(minimum_confidence, 4)}; "
        f"missing={', '.join(missing_required) if missing_required else 'none'}; "
        f"risks={', '.join(sorted(all_risks)) if all_risks else 'none'}"
    )

    return {
        "document_ids": document_ids,
        "document_result": aggregate_summary,
        "document_results": unique_results,
        "processing_complete": all_workers_succeeded,
        "document_complete": overall_document_complete,
        "continue_allowed": continue_allowed,
        "document_confidence": round(minimum_confidence, 4),
        "document_confidences": confidence_values,
        "missing_documents": missing_required,
        "risks": sorted(all_risks),
        "security_flags": sorted(all_security_flags),
        "validation_issues": sorted(all_validation_issues),
        "document_validation": validation_payload,
        "current_stage": "documents_complete",
        "status": "documents_complete",
    }


def summary_node(state: ClaimState):
    print("\n[3] Running Summary Agent V2")

    result = asyncio.run(run_summary_v2(state["case_id"]))
    record_audit(
        state["case_id"],
        "summary_agent",
        "summary_created",
        {
            "summary_sections": ["FACTS", "EVIDENCE", "POLICY STATUS", "MISSING INFORMATION", "RISKS", "VALIDATION ISSUES"],
            "risk_count": len(state.get("risks") or []),
            "missing_information_count": len(state.get("missing_documents") or []),
            "summary_length": len(str(result or "")),
        },
        stage="summary_complete",
    )

    return {
        "summary_result": result,
        "current_stage": "summary_complete",
        "status": "summary_complete",
    }


def await_documents_node(state: ClaimState):
    print("\n[Await Documents] Missing documents detected")

    missing_documents = list(state.get("missing_documents") or [])
    if missing_documents:
        notification = notify_missing_documents(
            state["case_id"],
            "claims-ops@uhg.local",
            missing_documents,
        )
        record_audit(
            state["case_id"],
            "workflow_mcp",
            "documents_requested",
            {
                "requested_documents": list(missing_documents),
                "reason": "missing_required_documents",
                "notification_success": bool(notification.get("success")),
            },
            stage="awaiting_documents",
        )
    record_audit(
        state["case_id"],
        "system",
        "workflow_paused_for_documents",
        {
            "missing_documents": list(missing_documents),
        },
        stage="awaiting_documents",
    )
    _persist_case_status(state["case_id"], "awaiting_documents", "awaiting_documents")

    resume = interrupt(
        {
            "case_id": state["case_id"],
            "status": "awaiting_documents",
            "missing_documents": missing_documents,
            "message": "Missing document data is required before continuing.",
        }
    )

    if resume is None or not isinstance(resume, dict) or not resume:
        _persist_case_status(state["case_id"], "awaiting_documents", "awaiting_documents")
        return {
            "missing_documents": list(missing_documents),
            "current_stage": "awaiting_documents",
            "status": "awaiting_documents",
            "interrupt_pending": True,
        }

    if isinstance(resume, dict) and resume:
        claim_data = _normalise_document_data(state)
        if resume.get("document_text"):
            claim_data["document_text"] = resume["document_text"]
        if resume.get("document_type"):
            claim_data["document_type"] = resume["document_type"]
        if resume.get("document_confidence") is not None:
            claim_data["document_confidence"] = resume["document_confidence"]
        if resume.get("document_id"):
            claim_data["document_id"] = resume["document_id"]
            claim_data["document_ids"] = [str(resume["document_id"])]
        if not claim_data.get("document_type"):
            claim_data["document_type"] = "supporting_document"

        document_received = bool(resume.get("document_id")) or bool(claim_data.get("document_text", "").strip())
        if document_received:
            record_audit(
                state["case_id"],
                "documents_mcp",
                "additional_document_received",
                {
                    "document_id": resume.get("document_id"),
                    "document_type": claim_data.get("document_type"),
                    "confidence": claim_data.get("document_confidence"),
                    "text_present": bool(claim_data.get("document_text", "").strip()),
                },
                stage="documents_revalidated",
            )
            _persist_case_status(state["case_id"], "documents_revalidated", "documents_revalidated")
            return Command(
                goto="documents",
                update={
                    "claim_data": claim_data,
                    "document_id": claim_data.get("document_id"),
                    "document_ids": list(claim_data.get("document_ids") or []),
                    "missing_documents": [],
                    "document_validation": {"missing_documents": [], "continue_allowed": False, "complete": False},
                    "continue_allowed": False,
                    "document_complete": False,
                    "processing_complete": False,
                    "current_stage": "documents_revalidated",
                    "status": "documents_revalidated",
                },
            )

        _persist_case_status(state["case_id"], "awaiting_documents", "awaiting_documents")
        return Command(
            goto="await_documents",
            update={
                "missing_documents": state.get("missing_documents", []),
                "current_stage": "awaiting_documents",
                "status": "awaiting_documents",
            },
        )

    return Command(
        goto="await_documents",
        update={
            "current_stage": "awaiting_documents",
            "status": "awaiting_documents",
        },
    )


def routing_node(state: ClaimState):
    print("\n[4] Running Routing Agent V2")

    result = asyncio.run(run_routing_v2(state["case_id"]))
    record_audit(
        state["case_id"],
        "routing_agent",
        "case_routed",
        {
            "routing_reason": "lowest_workload_and_case_readiness",
            "selected_approver": "Demo Approver",
            "result_preview": result[:200] if isinstance(result, str) else str(result),
        },
        stage="routing_complete",
    )

    return {
        "routing_result": result,
        "current_stage": "routing_complete",
        "status": "routing_complete",
    }


def sla_node(state: ClaimState):
    print("\n[5] Running SLA Agent V2")

    result = asyncio.run(run_sla_v2(state["case_id"]))
    record_audit(
        state["case_id"],
        "sla_agent",
        "sla_scheduled",
        {
            "delay_hours": 24.0,
            "job_name": "sla",
            "recipient": "claims-ops@uhg.local",
        },
        stage="sla_complete",
    )
    schedule_case_follow_up(
        state["case_id"],
        delay_hours=24.0,
        callback=lambda case_id: notify_sla_escalation(case_id, "claims-ops@uhg.local", delay_hours=24.0),
        job_name="sla",
    )
    _persist_case_status(state["case_id"], "awaiting_human_review", "sla_complete")

    return {
        "sla_result": result,
        "current_stage": "sla_complete",
        "status": "sla_complete",
    }


def approval_request_node(state: ClaimState):
    print("\n[6] Requesting Human Approval via MCP")

    result = asyncio.run(
        request_human_approval(
            state["case_id"],
            "Demo Approver",
        )
    )
    claim_data = state.get("claim_data") or {}
    claim_amount = float(claim_data.get("claim_amount") or 0)
    notify_approval_request(state["case_id"], "Demo Approver", claim_amount)
    record_audit(
        state["case_id"],
        "workflow_mcp",
        "approval_requested",
        {
            "approver": "Demo Approver",
            "claim_amount": claim_amount,
            "status": "awaiting_human_review",
        },
        stage="approval_requested",
    )
    _persist_case_status(state["case_id"], "awaiting_human_review", "approval_requested")

    return {
        "approval_request": result,
    }


def human_review_node(state: ClaimState):
    print("\n[6] Waiting for Human Review")

    approver_options = ["Demo Approver", "Senior Approver", "Director Approver"]
    record_audit(
        state["case_id"],
        "system",
        "human_review_started",
        {
            "eligible_approvers": approver_options,
            "claim_amount": float((state.get("claim_data") or {}).get("claim_amount") or 0),
            "thread_id": state.get("case_id"),
        },
        stage="awaiting_human_review",
    )

    pending_state = {
        "current_stage": "awaiting_human_review",
        "status": "awaiting_human_review",
        "next_step": "human_review",
    }
    human_response = interrupt(
        {
            "case_id": state["case_id"],
            "status": "awaiting_human_review",
            "summary": state.get("summary_result"),
            "routing": state.get("routing_result"),
            "message": "Human decision required",
        }
    )
    human_response = human_response or {}
    if not human_response:
        _persist_case_status(state["case_id"], "awaiting_human_review", "awaiting_human_review")
        return {
            "human_decision": "",
            "human_rationale": "",
            "human_reviewer": "",
            "current_stage": "awaiting_human_review",
            "status": "awaiting_human_review",
            "interrupt_pending": True,
        }
    decision = str(human_response.get("decision") or "unknown").strip()
    rationale = str(human_response.get("rationale") or "").strip()
    reviewer = str(human_response.get("reviewer") or "").strip()
    requested_documents = list(human_response.get("missing_documents") or human_response.get("requested_documents") or [])

    if decision == "request_more_information":
        requested_documents = _unique(requested_documents or list(state.get("missing_documents") or []))
        record_audit(
            state["case_id"],
            f"human_reviewer:{reviewer or 'unknown'}",
            "additional_information_requested",
            {
                "reviewer": reviewer,
                "rationale": rationale,
                "requested_documents": requested_documents,
            },
            stage="awaiting_documents",
        )
        _persist_case_status(state["case_id"], "awaiting_documents", "awaiting_documents")
        return Command(
            goto="await_documents",
            update={
                "human_decision": decision,
                "human_rationale": rationale,
                "human_reviewer": reviewer,
                "missing_documents": requested_documents,
                "document_complete": False,
                "next_step": "await_documents",
                "supervisor_reason": "Additional information requested by an authorized reviewer.",
                "status": "awaiting_documents",
                "current_stage": "awaiting_documents",
            },
        )

    if decision in {"approved", "rejected"}:
        record_audit(
            state["case_id"],
            f"human_reviewer:{reviewer or 'unknown'}",
            "human_decision_recorded",
            {
                "decision": decision,
                "reviewer": reviewer,
                "rationale": rationale,
            },
            stage="human_review_complete",
        )
        _persist_case_status(state["case_id"], "human_review_complete", "human_review_complete")
        return {
            "human_decision": decision,
            "human_rationale": rationale,
            "human_reviewer": reviewer,
            "current_stage": "human_review_complete",
            "status": "human_review_complete",
        }

    record_audit(
        state["case_id"],
        f"human_reviewer:{reviewer or 'unknown'}",
        "human_review_pending_decision",
        {
            "decision": decision,
            "reviewer": reviewer,
            "rationale": rationale,
            "requested_documents": requested_documents,
        },
        stage="awaiting_human_review",
    )
    _persist_case_status(state["case_id"], "awaiting_human_review", "awaiting_human_review")
    return {
        "human_decision": "",
        "human_rationale": rationale,
        "human_reviewer": reviewer,
        "current_stage": "awaiting_human_review",
        "status": "awaiting_human_review",
    }


def finalize_node(state: ClaimState):
    print("\n[7] Finalizing Case")

    decision = str(state.get("human_decision") or "").strip()
    if not decision or decision == "request_more_information":
        raise ValueError("Cannot finalize case without an authorized final human decision.")

    rationale = state.get("human_rationale", "")
    reviewer = state.get("human_reviewer", "")

    final_result = (
        f"Human decision: {decision}. "
        f"Reviewer: {reviewer}. "
        f"Rationale: {rationale}"
    )
    record_audit(
        state["case_id"],
        f"human_reviewer:{reviewer or 'unknown'}",
        "claim_finalized",
        {
            "final_decision": decision,
            "reviewer": reviewer,
            "final_status": "completed",
        },
        stage="finalized",
    )

    return {
        "final_result": final_result,
        "current_stage": "finalized",
        "status": "completed",
    }


def mcp_validation_node(state: ClaimState):
    print("\n[0] Running MCP Validation")

    claim = state["claim_data"]

    case_result = asyncio.run(get_case(state["case_id"]))
    coverage_result = asyncio.run(
        check_coverage(
            claim["policy_number"],
            claim["claim_type"],
            claim["claim_amount"],
        )
    )
    document_result = asyncio.run(validate_documents(state["case_id"]))
    record_audit(
        state["case_id"],
        "mcp_validation",
        "mcp_validation_completed",
        {
            "case_found": bool(case_result.get("success")),
            "coverage_result": coverage_result,
            "document_validation_result": document_result,
        },
        stage="mcp_validation_complete",
    )

    return {
        "case_lookup": case_result,
        "coverage_result": coverage_result,
        "document_validation": document_result,
        "current_stage": "mcp_validation_complete",
    }


def supervisor_node(state: ClaimState):
    print("\n[Supervisor] Evaluating routing")

    reason = ""
    status = _canonical_status(state.get("status") or "")
    current_stage = _canonical_status(state.get("current_stage") or "submitted")
    validation = state.get("document_validation") or {}
    missing_documents = list(state.get("missing_documents") or [])
    validation_missing = list((validation.get("missing_documents") or []) or [])
    missing_documents.extend(validation_missing)
    missing_documents = list(dict.fromkeys(missing_documents))

    human_decision = str(state.get("human_decision") or "").strip()
    if state.get("interrupt_pending") is True:
        reason = "Workflow is paused for external input or human review."
        return Command(
            goto=END,
            update={
                "next_step": "pause",
                "supervisor_reason": reason,
                "status": status or current_stage or "pending",
                "current_stage": current_stage or status or "pending",
                "interrupt_pending": True,
            },
        )

    if human_decision == "request_more_information":
        reason = "Additional information is required before the claim can be finalized."
        return Command(
            goto="await_documents",
            update={
                "next_step": "await_documents",
                "supervisor_reason": reason,
                "status": "awaiting_documents",
                "current_stage": "awaiting_documents",
            },
        )

    if human_decision in {"approved", "rejected"}:
        reason = "Human decision received; finalization is required."
        return Command(
            goto="finalize",
            update={
                "next_step": "finalize",
                "supervisor_reason": reason,
                "status": "finalized",
                "current_stage": "finalized",
            },
        )

    if status in {"awaiting_human_review", "human_review"} or current_stage in {"awaiting_human_review", "human_review", "approval_requested"}:
        reason = "Human review is awaiting a final decision."
        return Command(
            goto="human_review",
            update={
                "next_step": "human_review",
                "supervisor_reason": reason,
                "status": "awaiting_human_review",
                "current_stage": "awaiting_human_review",
            },
        )

    if status == "manual_review" or current_stage == "manual_review":
        reason = "Manual review is required before continuing."
        return Command(
            goto="manual_review",
            update={
                "next_step": "manual_review",
                "supervisor_reason": reason,
                "status": "manual_review",
                "current_stage": "manual_review",
            },
        )

    if status == "manual_review_held" or current_stage == "manual_review_held":
        reason = "Manual review is currently held pending a deliberate resolution."
        return Command(
            goto="manual_review",
            update={
                "next_step": "manual_review",
                "supervisor_reason": reason,
                "status": "manual_review_held",
                "current_stage": "manual_review_held",
            },
        )

    if current_stage in {"finalized", "completed"} or status in {"completed", "finalized"}:
        reason = f"Invalid transition from {current_stage or status}; workflow is blocked."
        return Command(
            goto="manual_review",
            update={
                "next_step": "manual_review",
                "supervisor_reason": reason,
                "errors": [reason],
                "status": "manual_review",
                "current_stage": "manual_review",
            },
        )

    if status in {"awaiting_documents", "documents_incomplete"} or current_stage == "awaiting_documents":
        reason = "Missing required documents detected."
        return Command(
            goto="await_documents",
            update={
                "next_step": "await_documents",
                "supervisor_reason": reason,
                "status": "awaiting_documents",
                "current_stage": "awaiting_documents",
            },
        )

    failed_workers = [
        item for item in state.get("document_results") or [] if item.get("processing_complete") is False
    ]
    document_results = state.get("document_results") or []
    document_processing_complete = bool(document_results) and (
        state.get("processing_complete") is True or state.get("document_complete") is True
    )

    if state.get("document_complete") is False and not missing_documents and failed_workers:
        if len(failed_workers) >= FAILURE_THRESHOLD:
            reason = "Document worker failures require manual review."
            return Command(
                goto="manual_review",
                update={
                    "next_step": "manual_review",
                    "supervisor_reason": reason,
                    "status": "manual_review",
                    "current_stage": "manual_review",
                },
            )
        reason = "Document processing failed; re-running document validation."
        return Command(
            goto="documents",
            update={
                "next_step": "documents",
                "supervisor_reason": reason,
                "status": "documents_processing",
                "current_stage": "documents_processing",
            },
        )

    if current_stage in {"submitted", "mcp_validation_complete"}:
        reason = "Intake processing must run before the claim can continue."
        return Command(
            goto="intake",
            update={
                "next_step": "intake",
                "supervisor_reason": reason,
                "status": "intake_pending",
                "current_stage": "mcp_validation_complete",
            },
        )

    if current_stage == "intake_complete":
        reason = "Documents are required before summary generation."
        return Command(
            goto="documents",
            update={
                "next_step": "documents",
                "supervisor_reason": reason,
                "status": "documents_processing",
                "current_stage": "intake_complete",
            },
        )

    if validation.get("continue_allowed") is False and current_stage not in {"submitted", "mcp_validation_complete", "intake_complete"}:
        reason = "Document validation blocked continuation."
        return Command(
            goto="manual_review",
            update={
                "next_step": "manual_review",
                "supervisor_reason": reason,
                "status": "manual_review",
                "current_stage": "manual_review",
            },
        )

    risks = set(state.get("risks") or [])
    security_flags = set(state.get("security_flags") or [])
    blocking_risks = _blocking_risks_for_state(state)
    if (blocking_risks or security_flags) and current_stage not in {"submitted", "mcp_validation_complete", "intake_complete"}:
        reason = "Security or validation risk requires manual review."
        return Command(
            goto="manual_review",
            update={
                "next_step": "manual_review",
                "supervisor_reason": reason,
                "status": "manual_review",
                "current_stage": "manual_review",
            },
        )

    if missing_documents:
        reason = "Missing required documents detected."
        return Command(
            goto="await_documents",
            update={
                "next_step": "await_documents",
                "supervisor_reason": reason,
                "status": "awaiting_documents",
                "current_stage": "awaiting_documents",
            },
        )

    if current_stage in {"documents_processing", "documents_revalidated"} and not document_processing_complete:
        reason = f"Invalid repeated document stage from {current_stage}; workflow is blocked."
        return Command(
            goto="manual_review",
            update={
                "next_step": "manual_review",
                "supervisor_reason": reason,
                "status": "manual_review",
                "current_stage": "manual_review",
                "errors": [reason],
            },
        )

    if missing_documents:
        reason = "Missing required documents detected."
        return Command(
            goto="await_documents",
            update={
                "next_step": "await_documents",
                "supervisor_reason": reason,
                "status": "awaiting_documents",
                "current_stage": "awaiting_documents",
            },
        )

    if current_stage in {"documents", "documents_processing", "documents_complete", "documents_revalidated"} and document_processing_complete:
        if state.get("continue_allowed") is True:
            reason = "Valid documents are ready for summary generation."
            return Command(
                goto="summary",
                update={
                    "next_step": "summary",
                    "supervisor_reason": reason,
                    "status": "summary_ready",
                    "current_stage": "documents_complete",
                },
            )
        reason = f"Invalid transition from {current_stage}; workflow is blocked."
        return Command(
            goto="manual_review",
            update={
                "next_step": "manual_review",
                "supervisor_reason": reason,
                "status": "manual_review",
                "current_stage": "manual_review",
                "errors": [reason],
            },
        )

    if state.get("document_complete") is False:
        reason = "Document processing is incomplete."
        return Command(
            goto="await_documents",
            update={
                "next_step": "await_documents",
                "supervisor_reason": reason,
                "status": "awaiting_documents",
                "current_stage": "awaiting_documents",
            },
        )

    if current_stage in {"submitted", "mcp_validation_complete"}:
        reason = "Intake processing must run before the claim can continue."
        return Command(
            goto="intake",
            update={
                "next_step": "intake",
                "supervisor_reason": reason,
            },
        )

    if current_stage == "intake_complete":
        reason = "Documents are required before summary generation."
        return Command(
            goto="documents",
            update={
                "next_step": "documents",
                "supervisor_reason": reason,
            },
        )

    if current_stage in {"documents_complete", "documents_revalidated"}:
        if missing_documents or state.get("document_complete") is False or state.get("continue_allowed") is False or _blocking_risks_for_state(state) or security_flags:
            reason = "Unresolved validation risk prevents summary generation."
            return Command(
                goto="manual_review",
                update={
                    "next_step": "manual_review",
                    "supervisor_reason": reason,
                    "status": "manual_review",
                    "current_stage": "manual_review",
                },
            )
        reason = "Valid documents are ready for summary generation."
        return Command(
            goto="summary",
            update={
                "next_step": "summary",
                "supervisor_reason": reason,
            },
        )

    if current_stage == "summary_complete":
        reason = "Summary is complete and routing can proceed."
        return Command(
            goto="routing",
            update={
                "next_step": "routing",
                "supervisor_reason": reason,
            },
        )

    if current_stage == "routing_complete":
        reason = "Routing is complete and SLA handling can proceed."
        return Command(
            goto="sla",
            update={
                "next_step": "sla",
                "supervisor_reason": reason,
            },
        )

    if current_stage == "sla_complete":
        if missing_documents or state.get("document_complete") is False or state.get("continue_allowed") is False or _blocking_risks_for_state(state) or security_flags:
            reason = "Unresolved validation risk blocks human review."
            return Command(
                goto="manual_review",
                update={
                    "next_step": "manual_review",
                    "supervisor_reason": reason,
                    "status": "manual_review",
                    "current_stage": "manual_review",
                },
            )
        reason = "SLA is complete and an authorized human review is required."
        return Command(
            goto="human_review",
            update={
                "next_step": "human_review",
                "supervisor_reason": reason,
            },
        )

    if current_stage == "human_review_complete":
        reason = "Human review is complete and the claim can be finalized."
        return Command(
            goto="finalize",
            update={
                "next_step": "finalize",
                "supervisor_reason": reason,
            },
        )

    if not state.get("intake_result"):
        reason = "Intake data is missing; intake must run first."
        return Command(
            goto="intake",
            update={
                "next_step": "intake",
                "supervisor_reason": reason,
            },
        )

    if not state.get("document_result") and not state.get("document_results"):
        reason = "Document processing has not completed."
        return Command(
            goto="documents",
            update={
                "next_step": "documents",
                "supervisor_reason": reason,
            },
        )

    if not state.get("summary_result"):
        reason = "Summary generation is required before routing."
        return Command(
            goto="summary",
            update={
                "next_step": "summary",
                "supervisor_reason": reason,
            },
        )

    if not state.get("routing_result"):
        reason = "Routing decision is required before SLA evaluation."
        return Command(
            goto="routing",
            update={
                "next_step": "routing",
                "supervisor_reason": reason,
            },
        )

    if not state.get("sla_result"):
        reason = "SLA evaluation is required before human review."
        return Command(
            goto="sla",
            update={
                "next_step": "sla",
                "supervisor_reason": reason,
            },
        )

    if current_stage in {"finalized", "completed"} or status in {"completed", "finalized"}:
        reason = f"Invalid transition from {current_stage or status}; workflow is blocked."
        return Command(
            goto="manual_review",
            update={
                "next_step": "manual_review",
                "supervisor_reason": reason,
                "errors": [reason],
            },
        )

    reason = "SLA and routing are complete; human review is required."
    return Command(
        goto="human_review",
        update={
            "next_step": "human_review",
            "supervisor_reason": reason,
        },
    )


def manual_review_node(state: ClaimState):
    print("\n[Manual Review] Human intervention required")

    case_id = state.get("case_id")
    if case_id:
        _persist_case_status(case_id, "manual_review", "manual_review")

    reason = state.get("manual_review_reason") or state.get("supervisor_reason") or "Manual review required before continuing."
    record_audit(
        case_id,
        "system",
        "manual_review_started",
        {
            "case_id": case_id,
            "reason": reason,
            "risks": state.get("risks", []),
            "errors": state.get("errors", []),
            "status": state.get("status"),
            "current_stage": state.get("current_stage"),
        },
    )

    manual_response = interrupt(
        {
            "case_id": case_id,
            "status": "manual_review",
            "summary": state.get("summary_result"),
            "routing": state.get("routing_result"),
            "manual_review_reason": reason,
            "risks": state.get("risks", []),
            "errors": state.get("errors", []),
            "message": "Manual review required before continuing.",
        }
    )
    manual_response = manual_response or {}
    if not manual_response:
        _persist_case_status(case_id, "manual_review", "manual_review")
        return {
            "manual_review_reason": reason,
            "status": "manual_review",
            "current_stage": "manual_review",
            "interrupt_pending": True,
        }
    action = str(manual_response.get("action") or "hold_case").strip() or "hold_case"
    reviewer = str(manual_response.get("reviewer") or "unknown").strip() or "unknown"
    rationale = str(manual_response.get("rationale") or "").strip()
    resolved_risks = list(manual_response.get("resolved_risks") or [])

    if action == "continue_processing":
        remaining_risks = [risk for risk in state.get("risks", []) if risk not in resolved_risks]
        if state.get("document_complete") is False or state.get("continue_allowed") is False or set(remaining_risks) & BLOCKING_VALIDATION_RISKS or set(state.get("security_flags") or []):
            result = {
                "manual_review_action": action,
                "manual_review_reviewer": reviewer,
                "manual_review_rationale": rationale,
                "manual_review_reason": "Blocking validation risks remain unresolved.",
                "manual_review_result": manual_response,
                "status": "manual_review",
                "current_stage": "manual_review",
                "risks": remaining_risks,
            }
            _persist_case_status(case_id, "manual_review", "manual_review")
            record_audit(case_id, reviewer, "manual_review_blocked", {"action": action, "rationale": rationale, "remaining_risks": remaining_risks})
            return Command(goto="manual_review", update=result)

        result = {
            "manual_review_action": action,
            "manual_review_reviewer": reviewer,
            "manual_review_rationale": rationale,
            "manual_review_reason": "",
            "manual_review_result": manual_response,
            "risks": remaining_risks,
            "missing_documents": [],
            "document_validation": {"missing_documents": [], "continue_allowed": False, "complete": False},
            "status": "documents_revalidated",
            "current_stage": "documents_revalidated",
            "document_complete": False,
            "continue_allowed": False,
            "processing_complete": False,
        }
        _persist_case_status(case_id, "documents_revalidated", "documents_revalidated")
        record_audit(case_id, reviewer, "manual_review_resolved", {"action": action, "rationale": rationale, "resolved_risks": resolved_risks})
        return Command(goto="documents", update=result)

    if action == "reprocess_documents":
        result = {
            "manual_review_action": action,
            "manual_review_reviewer": reviewer,
            "manual_review_rationale": rationale,
            "manual_review_reason": "",
            "manual_review_result": manual_response,
            "document_complete": False,
            "continue_allowed": False,
            "missing_documents": [],
            "status": "documents_revalidated",
            "current_stage": "documents_revalidated",
        }
        _persist_case_status(case_id, "documents_revalidated", "documents_revalidated")
        record_audit(case_id, reviewer, "manual_review_reprocess_requested", {"action": action, "rationale": rationale})
        return Command(goto="documents", update=result)

    if action == "request_documents":
        requested_documents = list(manual_response.get("missing_documents") or state.get("missing_documents") or [])
        result = {
            "manual_review_action": action,
            "manual_review_reviewer": reviewer,
            "manual_review_rationale": rationale,
            "manual_review_reason": "",
            "manual_review_result": manual_response,
            "missing_documents": requested_documents,
            "document_complete": False,
            "continue_allowed": False,
            "status": "awaiting_documents",
            "current_stage": "awaiting_documents",
        }
        _persist_case_status(case_id, "awaiting_documents", "awaiting_documents")
        record_audit(case_id, reviewer, "additional_documents_requested", {"action": action, "rationale": rationale, "documents": requested_documents})
        return Command(goto="await_documents", update=result)

    result = {
        "manual_review_action": "hold_case",
        "manual_review_reviewer": reviewer,
        "manual_review_rationale": rationale,
        "manual_review_result": manual_response,
        "manual_review_reason": reason,
        "current_stage": "manual_review_held",
        "status": "manual_review_held",
    }
    _persist_case_status(case_id, "manual_review_held", "manual_review_held")
    record_audit(case_id, reviewer, "manual_review_held", {"action": "hold_case", "rationale": rationale})
    return result


builder = StateGraph(ClaimState)
builder.add_node("mcp_validation", mcp_validation_node)
builder.add_node("intake", intake_node)
builder.add_node("documents", document_node)
builder.add_node("document_worker", document_worker_node)
builder.add_node("document_aggregation", document_aggregation_node)
builder.add_node("supervisor", supervisor_node)
builder.add_node("manual_review", manual_review_node)
builder.add_node("summary", summary_node)
builder.add_node("routing", routing_node)
builder.add_node("sla", sla_node)
builder.add_node("human_review", human_review_node)
builder.add_node("await_documents", await_documents_node)
builder.add_node("approval_request", approval_request_node)
builder.add_node("finalize", finalize_node)

builder.add_edge(START, "mcp_validation")
builder.add_edge("mcp_validation", "supervisor")
builder.add_edge("intake", "supervisor")
builder.add_edge("documents", "supervisor")
builder.add_edge("document_worker", "document_aggregation")
builder.add_edge("document_aggregation", "supervisor")
builder.add_edge("summary", "supervisor")
builder.add_edge("routing", "supervisor")
builder.add_edge("sla", "supervisor")
builder.add_edge("approval_request", "human_review")
builder.add_edge("human_review", "supervisor")
builder.add_edge("await_documents", "supervisor")
builder.add_edge("manual_review", "supervisor")
builder.add_edge("finalize", END)

