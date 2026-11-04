import asyncio

from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from graph.state import ClaimState
from services.database import DATABASE_URL
from services.mcp_client import (
    check_coverage,
    get_case,
    request_human_approval,
    validate_documents,
)
from services.v2_agent_runner import (
    run_document_v2,
    run_intake_v2,
    run_routing_v2,
    run_sla_v2,
    run_summary_v2,
)


def intake_node(state: ClaimState):
    print("\n[1] Running Intake Agent V2")

    result = asyncio.run(run_intake_v2(state["case_id"]))

    return {
        "intake_result": result,
        "current_stage": "intake_complete",
    }


def document_node(state: ClaimState):
    print("\n[2] Running Document Agent V2")

    claim = state["claim_data"]
    document_text = claim.get("document_text", "").strip()

    if not document_text:
        return {
            "document_result": "No supporting document text was provided.",
            "document_complete": False,
            "missing_documents": ["supporting_document"],
            "current_stage": "documents_incomplete",
        }

    result = asyncio.run(run_document_v2(state["case_id"]))

    return {
        "document_result": result,
        "document_complete": True,
        "missing_documents": [],
        "current_stage": "documents_complete",
    }


def summary_node(state: ClaimState):
    print("\n[3] Running Summary Agent V2")

    result = asyncio.run(run_summary_v2(state["case_id"]))

    return {
        "summary_result": result,
        "current_stage": "summary_complete",
    }


def route_after_documents(state: ClaimState):
    if state.get("document_complete"):
        return "summary"

    return "await_documents"


def await_documents_node(state: ClaimState):
    print("\n[3] Missing Documents Detected")

    return {
        "current_stage": "awaiting_documents",
        "status": "awaiting_documents",
        "missing_documents": state.get("missing_documents", []),
    }


def routing_node(state: ClaimState):
    print("\n[4] Running Routing Agent V2")

    result = asyncio.run(run_routing_v2(state["case_id"]))

    return {
        "routing_result": result,
        "current_stage": "routing_complete",
    }


def sla_node(state: ClaimState):
    print("\n[5] Running SLA Agent V2")

    result = asyncio.run(run_sla_v2(state["case_id"]))

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

    return {
        "human_decision": human_response.get("decision", "unknown"),
        "human_rationale": human_response.get("rationale", ""),
        "human_reviewer": human_response.get("reviewer", ""),
        "current_stage": "human_review_complete",
        "status": "human_decision_received",
    }


def finalize_node(state: ClaimState):
    print("\n[7] Finalizing Case")

    decision = state.get("human_decision", "unknown")
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


def route_after_supervisor(state: ClaimState):
    current_stage = state.get("current_stage", "submitted")
    document_validation = state.get("document_validation") or {}
    risks = set(state.get("risks") or [])
    errors = list(state.get("errors") or [])
    missing_documents = state.get("missing_documents") or []

    if missing_documents:
        return "await_documents"
    if document_validation.get("continue_allowed") is False:
        return "manual_review"
    if risks & {"low_confidence", "prompt_injection_detected", "policy_inconsistency", "claimant_name_mismatch", "amount_mismatch"}:
        return "manual_review"
    if state.get("document_complete") is False:
        return "await_documents"
    if current_stage not in {"submitted", "mcp_validation_complete", "intake_complete", "documents_complete", "summary_complete", "routing_complete", "sla_complete", "manual_review_complete"}:
        errors.append("Invalid transition blocked by supervisor.")
        return "manual_review"
    return "summary"


def supervisor_node(state: ClaimState):
    print("\n[Supervisor] Evaluating routing")

    current_stage = state.get("current_stage", "submitted")
    document_validation = state.get("document_validation") or {}
    risks = list(state.get("risks") or [])
    errors = list(state.get("errors") or [])
    failure_count = int(state.get("failure_count", 0))
    missing_documents = state.get("missing_documents") or []

    next_node = route_after_supervisor(state)

    if next_node == "manual_review":
        failure_count += 1
        if document_validation.get("continue_allowed") is False:
            errors.append("Document validation blocked continuation.")
        if missing_documents:
            errors.append("Missing required documents detected.")
    else:
        failure_count = 0

    if failure_count >= 2:
        next_node = "manual_review"
        errors.append("Repeated workflow failure detected.")

    routing_result = {
        "next": next_node,
        "reason": "Document validation and workflow guard checks",
        "valid": next_node != "manual_review" or bool(errors),
        "risks": list(dict.fromkeys(risks)),
        "errors": list(dict.fromkeys(errors)),
        "failure_count": failure_count,
    }

    update = {
        "supervisor_result": routing_result,
        "risks": list(dict.fromkeys(risks)),
        "errors": list(dict.fromkeys(errors)),
        "failure_count": failure_count,
        "current_stage": "supervisor_complete",
    }

    if next_node == "manual_review":
        update["status"] = "manual_review"

    return update


def manual_review_node(state: ClaimState):
    print("\n[Manual Review] Human intervention required")

    human_response = interrupt(
        {
            "case_id": state["case_id"],
            "status": "manual_review",
            "summary": state.get("summary_result"),
            "routing": state.get("routing_result"),
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
builder.add_edge("mcp_validation", "intake")
builder.add_edge("intake", "documents")
builder.add_edge("documents", "supervisor")
builder.add_conditional_edges(
    "supervisor",
    route_after_supervisor,
    {
        "summary": "summary",
        "manual_review": "manual_review",
        "await_documents": "await_documents",
    },
)
builder.add_edge("manual_review", "approval_request")
builder.add_edge("await_documents", END)
builder.add_edge("summary", "routing")
builder.add_edge("routing", "sla")
builder.add_edge("sla", "approval_request")
builder.add_edge("approval_request", "human_review")
builder.add_edge("human_review", "finalize")
builder.add_edge("finalize", END)

DB_URI = DATABASE_URL
checkpointer_context = PostgresSaver.from_conn_string(DB_URI)
checkpointer = checkpointer_context.__enter__()
checkpointer.setup()

graph = builder.compile(checkpointer=checkpointer)
