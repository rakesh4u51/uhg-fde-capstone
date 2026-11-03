from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from graph.state import ClaimState
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


async def intake_node(state: ClaimState):
    print("\n[1] Running Intake Agent V2")

    result = await run_intake_v2(state["case_id"])

    return {
        "intake_result": result,
        "current_stage": "intake_complete",
    }


async def document_node(state: ClaimState):
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

    result = await run_document_v2(state["case_id"])

    return {
        "document_result": result,
        "document_complete": True,
        "missing_documents": [],
        "current_stage": "documents_complete",
    }


async def summary_node(state: ClaimState):
    print("\n[3] Running Summary Agent V2")

    result = await run_summary_v2(state["case_id"])

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


async def routing_node(state: ClaimState):
    print("\n[4] Running Routing Agent V2")

    result = await run_routing_v2(state["case_id"])

    return {
        "routing_result": result,
        "current_stage": "routing_complete",
    }


async def sla_node(state: ClaimState):
    print("\n[5] Running SLA Agent V2")

    result = await run_sla_v2(state["case_id"])

    return {
        "sla_result": result,
        "current_stage": "sla_complete",
        "status": "awaiting_human_review",
    }


async def approval_request_node(state: ClaimState):
    print("\n[6] Requesting Human Approval via MCP")

    result = await request_human_approval(
        state["case_id"],
        "Demo Approver",
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


async def mcp_validation_node(state: ClaimState):
    print("\n[0] Running MCP Validation")

    claim = state["claim_data"]

    case_result = await get_case(state["case_id"])
    coverage_result = await check_coverage(
        claim["policy_number"],
        claim["claim_type"],
        claim["claim_amount"],
    )
    document_result = await validate_documents(state["case_id"])

    return {
        "case_lookup": case_result,
        "coverage_result": coverage_result,
        "document_validation": document_result,
        "current_stage": "mcp_validation_complete",
    }


builder = StateGraph(ClaimState)
builder.add_node("mcp_validation", mcp_validation_node)
builder.add_node("intake", intake_node)
builder.add_node("documents", document_node)
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
builder.add_conditional_edges(
    "documents",
    route_after_documents,
    {
        "summary": "summary",
        "await_documents": "await_documents",
    },
)
builder.add_edge("await_documents", END)
builder.add_edge("summary", "routing")
builder.add_edge("routing", "sla")
builder.add_edge("sla", "human_review")
builder.add_edge("human_review", "finalize")
builder.add_edge("finalize", END)

# Use an in-memory checkpointer so this V2 workflow can resume interrupts
# without a background event-loop conflict or Postgres startup dependency.
graph = builder.compile(checkpointer=MemorySaver())
