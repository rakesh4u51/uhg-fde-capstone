from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.types import interrupt

from graph.state import ClaimState

from agents.intake_agent import run_intake_agent
from agents.document_agent import run_document_agent
from agents.summary_agent import run_summary_agent
from agents.routing_agent import run_routing_agent
from agents.sla_agent import run_sla_agent

import asyncio

from services.mcp_client import (
    get_case,
    check_coverage,
    validate_documents,
    request_human_approval,
)


def intake_node(state: ClaimState):
    print("\n[1] Running Intake Agent")

    result = run_intake_agent(
        state["claim_data"]
    )

    return {
        "intake_result": result,
        "current_stage": "intake_complete",
    }


def document_node(state: ClaimState):
    print("\n[2] Running Document Agent")

    claim = state["claim_data"]

    document_text = claim.get(
        "document_text",
        ""
    ).strip()

    document_data = {
        "document_type": claim.get(
            "document_type",
            "unknown",
        ),
        "text": document_text,
        "confidence": claim.get(
            "document_confidence",
            0,
        ),
    }

    result = run_document_agent(document_data)

    if not document_text:
        return {
            "document_result": result,
            "document_complete": False,
            "missing_documents": [
                "supporting_document"
            ],
            "current_stage": "documents_incomplete",
        }

    return {
        "document_result": result,
        "document_complete": True,
        "missing_documents": [],
        "current_stage": "documents_complete",
    }
    print("\n[2] Running Document Agent")

    claim = state["claim_data"]

    document_data = {
        "document_type": claim.get(
            "document_type",
            "unknown",
        ),
        "text": claim.get(
            "document_text",
            "",
        ),
        "confidence": claim.get(
            "document_confidence",
            0,
        ),
    }

    result = run_document_agent(document_data)

    return {
        "document_result": result,
        "current_stage": "documents_complete",
    }


def summary_node(state: ClaimState):
    print("\n[3] Running Summary Agent")

    data = {
        "claim": state["claim_data"],
        "intake": state.get("intake_result"),
        "documents": state.get("document_result"),
    }

    result = run_summary_agent(data)

    return {
        "summary_result": result,
        "current_stage": "summary_complete",
    }

def route_after_documents(state: ClaimState):
    if state.get("document_complete"):
        return "summary"

    return "await_documents"

def route_after_documents(state: ClaimState):
    if state.get("document_complete"):
        return "summary"

    return "await_documents"

def await_documents_node(state: ClaimState):
    print("\n[3] Missing Documents Detected")

    return {
        "current_stage": "awaiting_documents",
        "status": "awaiting_documents",
        "missing_documents": state.get(
            "missing_documents",
            [],
        ),
    }

def routing_node(state: ClaimState):
    print("\n[4] Running Routing Agent")

    data = {
        "claim": state["claim_data"],
        "summary": state.get("summary_result"),
    }

    result = run_routing_agent(data)

    return {
        "routing_result": result,
        "current_stage": "routing_complete",
    }


def sla_node(state: ClaimState):
    print("\n[5] Running SLA Agent")

    data = {
        "claim": state["claim_data"],
        "routing": state.get("routing_result"),
    }

    result = run_sla_agent(data)

    return {
        "sla_result": result,
        "current_stage": "sla_complete",
        "status": "awaiting_human_review",
    }

def approval_request_node(state: ClaimState):
    print("\n[6] Requesting Human Approval via MCP")

    async def request():
        return await request_human_approval(
            state["case_id"],
            "Demo Approver",
        )

    result = asyncio.run(request())

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


    print("\n[7] Finalizing Case")

    decision = state.get("human_decision", "unknown")
    rationale = state.get("human_rationale", "")
    reviewer = state.get("human_reviewer", "")

    return {
        "final_result": (
            f"Human decision: {decision}. "
            f"Reviewer: {reviewer}. "
            f"Rationale: {rationale}"
        ),
        "current_stage": "finalized",
        "status": "completed",
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

    async def run_checks():
        case_result = await get_case(
            state["case_id"]
        )

        coverage_result = await check_coverage(
            claim["policy_number"],
            claim["claim_type"],
            claim["claim_amount"],
        )

        document_result = await validate_documents(
            state["case_id"]
        )

        return (
            case_result,
            coverage_result,
            document_result,
        )

    (
        case_result,
        coverage_result,
        document_result,
    ) = asyncio.run(run_checks())

    return {
        "case_lookup": case_result,
        "coverage_result": coverage_result,
        "document_validation": document_result,
        "current_stage": "mcp_validation_complete",
    }

builder = StateGraph(ClaimState)
builder.add_node(
    "mcp_validation",
    mcp_validation_node,
)

builder.add_node("intake", intake_node)
builder.add_node("documents", document_node)
builder.add_node("summary", summary_node)
builder.add_node("routing", routing_node)
builder.add_node("sla", sla_node)
builder.add_node("human_review", human_review_node)
builder.add_node(
    "await_documents",
    await_documents_node,
)
builder.add_node(
    "approval_request",
    approval_request_node,
)
builder.add_node("finalize", finalize_node)

builder.add_edge(
    START,
    "mcp_validation",
)

builder.add_edge(
    "mcp_validation",
    "intake",
)
builder.add_edge("intake", "documents")
builder.add_conditional_edges(
    "documents",
    route_after_documents,
    {
        "summary": "summary",
        "await_documents": "await_documents",
    },
)
builder.add_edge(
    "await_documents",
    END,
)
builder.add_edge("summary", "routing")
builder.add_edge("routing", "sla")
builder.add_edge(
    "sla",
    "approval_request",
)

builder.add_edge(
    "approval_request",
    "human_review",
)
builder.add_edge("human_review", "finalize")
builder.add_edge("finalize", END)

DB_URI = (
    "postgresql://postgres:postgres123"
    "@localhost:5432/genai_training"
)

checkpointer_context = PostgresSaver.from_conn_string(
    DB_URI
)

checkpointer = checkpointer_context.__enter__()

checkpointer.setup()

graph = builder.compile(
    checkpointer=checkpointer
)
