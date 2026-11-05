import asyncio
from typing import Any

from fastmcp import Client
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, Send, interrupt

from graph.state import ClaimState
from mcp_servers.workflow_mcp.server import mcp as workflow_mcp
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


def _unique(values: list[str] | None) -> list[str]:
    return list(dict.fromkeys((values or [])))


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
    return data


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

    if missing_documents:
        return "await_documents", "Missing required documents detected."

    if document_complete is False:
        return "await_documents", "Document processing is incomplete."

    if validation.get("continue_allowed") is False:
        return "manual_review", "Document validation blocked continuation."

    if any(flag in risks for flag in {"low_confidence", "prompt_injection_detected", "amount_mismatch", "claimant_name_mismatch", "policy_inconsistency"}) or security_flags:
        return "manual_review", "Security or validation risk requires manual review."

    if current_stage in {"submitted", "mcp_validation_complete", "intake_complete", "documents_complete"}:
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

    return {
        "intake_result": result,
        "current_stage": "intake_complete",
        "status": "intake_complete",
    }


def document_node(state: ClaimState):
    print("\n[2] Running Document Agent V2")

    claim_data = _normalise_document_data(state)
    document_text = claim_data.get("document_text", "").strip()
    document_ids = state.get("document_ids") or []

    if len(document_ids) > 1:
        worker_calls = [
            Send("document_worker", {"case_id": state["case_id"], "document_id": doc_id, "claim_data": claim_data})
            for doc_id in document_ids
        ]
        return Command(
            goto=worker_calls,
            update={
                "current_stage": "documents_fanout",
                "status": "documents_fanout",
                "document_complete": False,
            },
        )

    if not document_text:
        missing_documents = _required_documents_for_claim_type(claim_data.get("claim_type"))
        return {
            "document_result": "No supporting document text was provided.",
            "document_complete": False,
            "missing_documents": missing_documents,
            "current_stage": "documents_incomplete",
            "status": "awaiting_documents",
        }

    result = asyncio.run(run_document_v2(state["case_id"]))

    return {
        "document_result": result,
        "document_complete": True,
        "missing_documents": [],
        "current_stage": "documents_complete",
        "status": "documents_complete",
        "document_results": [{"document_id": state.get("case_id"), "result": result}],
    }


def document_worker_node(state: ClaimState):
    case_id = state.get("case_id")
    document_id = state.get("document_id")
    document_results = list(state.get("document_results") or [])
    result = asyncio.run(run_document_v2(case_id))
    document_results.append({"document_id": document_id, "result": result})
    return {
        "document_results": document_results,
        "document_complete": True,
        "current_stage": "documents_complete",
        "status": "documents_complete",
    }


def summary_node(state: ClaimState):
    print("\n[3] Running Summary Agent V2")

    result = asyncio.run(run_summary_v2(state["case_id"]))

    return {
        "summary_result": result,
        "current_stage": "summary_complete",
        "status": "summary_complete",
    }


def await_documents_node(state: ClaimState):
    print("\n[Await Documents] Missing documents detected")

    missing_documents = list(state.get("missing_documents") or [])
    if missing_documents:
        notify_missing_documents(
            state["case_id"],
            "claims-ops@uhg.local",
            missing_documents,
        )

    resume = interrupt(
        {
            "case_id": state["case_id"],
            "status": "awaiting_documents",
            "missing_documents": missing_documents,
            "message": "Missing document data is required before continuing.",
        }
    )

    if isinstance(resume, dict) and resume:
        claim_data = _normalise_document_data(state)
        if resume.get("document_text"):
            claim_data["document_text"] = resume["document_text"]
        if resume.get("document_type"):
            claim_data["document_type"] = resume["document_type"]
        if resume.get("document_confidence") is not None:
            claim_data["document_confidence"] = resume["document_confidence"]

        if claim_data.get("document_text", "").strip():
            return Command(
                goto="documents",
                update={
                    "claim_data": claim_data,
                    "missing_documents": [],
                    "document_complete": False,
                    "status": "documents_resumed",
                    "current_stage": "documents_revalidated",
                },
            )

        return Command(
            goto="await_documents",
            update={
                "missing_documents": state.get("missing_documents", []),
                "status": "awaiting_documents",
                "current_stage": "awaiting_documents",
            },
        )

    return Command(
        goto="await_documents",
        update={
            "status": "awaiting_documents",
            "current_stage": "awaiting_documents",
        },
    )


def routing_node(state: ClaimState):
    print("\n[4] Running Routing Agent V2")

    result = asyncio.run(run_routing_v2(state["case_id"]))

    return {
        "routing_result": result,
        "current_stage": "routing_complete",
        "status": "routing_complete",
    }


def sla_node(state: ClaimState):
    print("\n[5] Running SLA Agent V2")

    result = asyncio.run(run_sla_v2(state["case_id"]))
    notify_sla_escalation(state["case_id"], "claims-ops@uhg.local", delay_hours=24.0)
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
        "status": "awaiting_human_review",
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
    _persist_case_status(state["case_id"], "awaiting_human_review", "approval_requested")

    return {
        "approval_request": result,
        "status": "awaiting_human_review",
        "current_stage": "approval_requested",
    }


def human_review_node(state: ClaimState):
    print("\n[6] Waiting for Human Review")

    human_response = interrupt(
        {
            "case_id": state["case_id"],
            "status": "awaiting_human_review",
            "summary": state.get("summary_result"),
            "routing": state.get("routing_result"),
            "message": "Human decision required",
        }
    )
    _persist_case_status(state["case_id"], "human_decision_received", "human_review_complete")

    return {
        "human_decision": human_response.get("decision", "unknown"),
        "human_rationale": human_response.get("rationale", ""),
        "human_reviewer": human_response.get("reviewer", ""),
        "current_stage": "human_review_complete",
        "status": "human_decision_received",
    }


def finalize_node(state: ClaimState):
    print("\n[7] Finalizing Case")

    decision = state.get("human_decision")
    if not decision:
        raise ValueError("Cannot finalize case without an authorized human decision.")

    rationale = state.get("human_rationale", "")
    reviewer = state.get("human_reviewer", "")

    final_result = (
        f"Human decision: {decision}. "
        f"Reviewer: {reviewer}. "
        f"Rationale: {rationale}"
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

    return {
        "case_lookup": case_result,
        "coverage_result": coverage_result,
        "document_validation": document_result,
        "current_stage": "mcp_validation_complete",
    }


def supervisor_node(state: ClaimState):
    print("\n[Supervisor] Evaluating routing")

    reason = ""
    status = state.get("status") or ""
    current_stage = state.get("current_stage") or "submitted"
    validation = state.get("document_validation") or {}
    missing_documents = list(state.get("missing_documents") or [])
    validation_missing = list((validation.get("missing_documents") or []) or [])
    missing_documents.extend(validation_missing)
    missing_documents = list(dict.fromkeys(missing_documents))

    if state.get("human_decision"):
        reason = "Human decision received; finalization is required."
        return Command(
            goto="finalize",
            update={
                "next_step": "finalize",
                "status": "ready_to_finalize",
                "supervisor_reason": reason,
            },
        )

    if status == "manual_review" or current_stage == "manual_review":
        reason = "Manual review is required before continuing."
        return Command(
            goto="manual_review",
            update={
                "next_step": "manual_review",
                "status": "manual_review",
                "supervisor_reason": reason,
            },
        )

    if current_stage in {"finalized", "completed"} or status in {"completed", "finalized"}:
        reason = f"Invalid transition from {current_stage or status}; workflow is blocked."
        return Command(
            goto="manual_review",
            update={
                "next_step": "manual_review",
                "status": "manual_review",
                "supervisor_reason": reason,
                "errors": [reason],
            },
        )

    if state.get("document_complete") is False:
        reason = "Document processing is incomplete."
        return Command(
            goto="await_documents",
            update={
                "next_step": "await_documents",
                "status": "awaiting_documents",
                "supervisor_reason": reason,
            },
        )

    if validation.get("continue_allowed") is False:
        reason = "Document validation blocked continuation."
        return Command(
            goto="manual_review",
            update={
                "next_step": "manual_review",
                "status": "manual_review",
                "supervisor_reason": reason,
            },
        )

    risks = set(state.get("risks") or [])
    security_flags = set(state.get("security_flags") or [])
    if any(
        flag in risks
        for flag in {
            "low_confidence",
            "prompt_injection_detected",
            "amount_mismatch",
            "claimant_name_mismatch",
            "policy_inconsistency",
        }
    ) or security_flags:
        reason = "Security or validation risk requires manual review."
        return Command(
            goto="manual_review",
            update={
                "next_step": "manual_review",
                "status": "manual_review",
                "supervisor_reason": reason,
            },
        )

    if missing_documents:
        reason = "Missing required documents detected."
        return Command(
            goto="await_documents",
            update={
                "next_step": "await_documents",
                "status": "awaiting_documents",
                "supervisor_reason": reason,
            },
        )

    if current_stage in {"submitted", "mcp_validation_complete"}:
        reason = "Intake processing must run before the claim can continue."
        return Command(
            goto="intake",
            update={
                "next_step": "intake",
                "status": "intake_required",
                "supervisor_reason": reason,
            },
        )

    if current_stage == "intake_complete":
        reason = "Documents are required before summary generation."
        return Command(
            goto="documents",
            update={
                "next_step": "documents",
                "status": "documents_required",
                "supervisor_reason": reason,
            },
        )

    if current_stage in {"documents_complete", "documents_revalidated"}:
        reason = "Valid documents are ready for summary generation."
        return Command(
            goto="summary",
            update={
                "next_step": "summary",
                "status": "summary_required",
                "supervisor_reason": reason,
            },
        )

    if current_stage == "summary_complete":
        reason = "Summary is complete and routing can proceed."
        return Command(
            goto="routing",
            update={
                "next_step": "routing",
                "status": "routing_required",
                "supervisor_reason": reason,
            },
        )

    if current_stage == "routing_complete":
        reason = "Routing is complete and SLA handling can proceed."
        return Command(
            goto="sla",
            update={
                "next_step": "sla",
                "status": "sla_required",
                "supervisor_reason": reason,
            },
        )

    if current_stage == "sla_complete":
        reason = "SLA is complete and an authorized human review is required."
        return Command(
            goto="human_review",
            update={
                "next_step": "human_review",
                "status": "awaiting_human_review",
                "supervisor_reason": reason,
            },
        )

    if current_stage == "human_review_complete":
        reason = "Human review is complete and the claim can be finalized."
        return Command(
            goto="finalize",
            update={
                "next_step": "finalize",
                "status": "ready_to_finalize",
                "supervisor_reason": reason,
            },
        )

    if not state.get("intake_result"):
        reason = "Intake data is missing; intake must run first."
        return Command(
            goto="intake",
            update={
                "next_step": "intake",
                "status": "intake_required",
                "supervisor_reason": reason,
            },
        )

    if not state.get("document_result"):
        reason = "Document processing has not completed."
        return Command(
            goto="documents",
            update={
                "next_step": "documents",
                "status": "documents_required",
                "supervisor_reason": reason,
            },
        )

    if not state.get("summary_result"):
        reason = "Summary generation is required before routing."
        return Command(
            goto="summary",
            update={
                "next_step": "summary",
                "status": "summary_required",
                "supervisor_reason": reason,
            },
        )

    if not state.get("routing_result"):
        reason = "Routing decision is required before SLA evaluation."
        return Command(
            goto="routing",
            update={
                "next_step": "routing",
                "status": "routing_required",
                "supervisor_reason": reason,
            },
        )

    if not state.get("sla_result"):
        reason = "SLA evaluation is required before human review."
        return Command(
            goto="sla",
            update={
                "next_step": "sla",
                "status": "sla_required",
                "supervisor_reason": reason,
            },
        )

    if current_stage in {"finalized", "completed"} or status in {"completed", "finalized"}:
        reason = f"Invalid transition from {current_stage or status}; workflow is blocked."
        return Command(
            goto="manual_review",
            update={
                "next_step": "manual_review",
                "status": "manual_review",
                "supervisor_reason": reason,
                "errors": [reason],
            },
        )

    reason = "SLA and routing are complete; human review is required."
    return Command(
        goto="human_review",
        update={
            "next_step": "human_review",
            "status": "awaiting_human_review",
            "supervisor_reason": reason,
        },
    )


def manual_review_node(state: ClaimState):
    print("\n[Manual Review] Human intervention required")

    human_response = interrupt(
        {
            "case_id": state["case_id"],
            "status": "manual_review",
            "summary": state.get("summary_result"),
            "routing": state.get("routing_result"),
            "manual_review_reason": state.get("manual_review_reason") or state.get("supervisor_reason"),
            "risks": state.get("risks", []),
            "errors": state.get("errors", []),
            "message": "Manual review required before continuing.",
        }
    )

    return {
        "manual_review_result": human_response,
        "human_decision": human_response.get("decision", "unknown"),
        "human_rationale": human_response.get("rationale", ""),
        "human_reviewer": human_response.get("reviewer", ""),
        "current_stage": "manual_review_complete",
        "status": "manual_review_complete",
    }


builder = StateGraph(ClaimState)
builder.add_node("mcp_validation", mcp_validation_node)
builder.add_node("intake", intake_node)
builder.add_node("documents", document_node)
builder.add_node("document_worker", document_worker_node)
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
builder.add_edge("document_worker", "supervisor")
builder.add_edge("documents", "supervisor")
builder.add_edge("summary", "supervisor")
builder.add_edge("routing", "supervisor")
builder.add_edge("sla", "supervisor")
builder.add_edge("approval_request", "human_review")
builder.add_edge("human_review", "supervisor")
builder.add_edge("await_documents", "supervisor")
builder.add_edge("manual_review", "supervisor")
builder.add_edge("finalize", END)

