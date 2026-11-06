from __future__ import annotations

from typing import Any

from fastmcp import FastMCP

from services.audit import record_audit
from services.database import get_connection


mcp = FastMCP("Case MCP")


def _safe_case_payload(case_row: dict[str, Any] | None) -> dict[str, Any]:
    if not case_row:
        return {}
    case = dict(case_row)
    return {
        "case_id": case.get("case_id"),
        "policy_number": case.get("policy_number"),
        "claim_type": case.get("claim_type"),
        "claim_amount": case.get("claim_amount"),
        "status": case.get("status"),
        "summary": case.get("summary"),
        "created_at": case.get("created_at"),
        "updated_at": case.get("updated_at"),
    }


def _audit_tool(server_name: str, tool_name: str, case_id: str | None, outcome: str, **extra: Any) -> None:
    if not case_id:
        return
    payload: dict[str, Any] = {"server": server_name, "tool": tool_name, "case_id": case_id, "outcome": outcome}
    payload.update(extra)
    record_audit(case_id, f"mcp:{server_name}", "mcp_tool_called", payload, stage="mcp")


@mcp.tool()
def get_case(case_id: str) -> dict:
    """Get a claim case from PostgreSQL."""
    if not case_id or not str(case_id).strip():
        return {"success": False, "error": "case_id is required"}

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    case_id,
                    policy_number,
                    claimant_name,
                    claim_type,
                    claim_amount,
                    description,
                    status,
                    summary,
                    created_at,
                    updated_at
                FROM public.claims
                WHERE case_id = %s
                """,
                (case_id,),
            )
            case = cur.fetchone()

    if case is None:
        _audit_tool("case_mcp", "get_case", case_id, "not_found")
        return {"success": False, "error": "Case not found"}

    _audit_tool("case_mcp", "get_case", case_id, "success")
    return {"success": True, "case": _safe_case_payload(case)}


@mcp.tool()
def list_cases() -> dict:
    """List claim cases from PostgreSQL."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    case_id,
                    policy_number,
                    claimant_name,
                    claim_type,
                    claim_amount,
                    status,
                    summary,
                    created_at,
                    updated_at
                FROM public.claims
                ORDER BY created_at DESC
                """
            )
            cases = cur.fetchall()
    return {"success": True, "cases": [_safe_case_payload(dict(case)) for case in cases]}


@mcp.tool()
def register_case(
    case_id: str,
    policy_number: str,
    claimant_name: str,
    claim_type: str,
    claim_amount: float,
    description: str = "",
) -> dict:
    """Register a new claim in PostgreSQL."""
    if not case_id or not str(case_id).strip():
        return {"success": False, "error": "case_id is required"}
    if not policy_number or not str(policy_number).strip():
        return {"success": False, "error": "policy_number is required"}
    if not claim_type or not str(claim_type).strip():
        return {"success": False, "error": "claim_type is required"}
    try:
        amount = float(claim_amount)
    except (TypeError, ValueError):
        return {"success": False, "error": "claim_amount must be numeric and non-negative"}
    if amount < 0:
        return {"success": False, "error": "claim_amount must be numeric and non-negative"}

    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO public.claims
                    (
                        case_id,
                        policy_number,
                        claimant_name,
                        claim_type,
                        claim_amount,
                        description,
                        status
                    )
                    VALUES
                    (
                        %s, %s, %s, %s,
                        %s, %s, 'submitted'
                    )
                    RETURNING
                        case_id,
                        policy_number,
                        claimant_name,
                        claim_type,
                        claim_amount,
                        description,
                        status,
                        summary,
                        created_at,
                        updated_at
                    """,
                    (case_id, policy_number, claimant_name, claim_type, amount, description),
                )
                case = cur.fetchone()
            conn.commit()
    except Exception as exc:
        return {"success": False, "error": f"Failed to register case: {exc}"}

    _audit_tool("case_mcp", "register_case", case_id, "success")
    return {"success": True, "case": _safe_case_payload(case)}


@mcp.tool()
def find_similar_cases(policy_number: str, case_id: str | None = None) -> dict:
    """Find claims associated with the same policy without assuming fraud."""
    if not policy_number or not str(policy_number).strip():
        return {"success": False, "error": "policy_number is required"}

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    case_id,
                    policy_number,
                    claimant_name,
                    claim_type,
                    claim_amount,
                    status,
                    summary,
                    created_at
                FROM public.claims
                WHERE policy_number = %s
                ORDER BY created_at DESC
                """,
                (policy_number,),
            )
            cases = cur.fetchall()

    filtered_cases = [dict(item) for item in cases if not case_id or item.get("case_id") != case_id]
    similarity_indicator = "possible_match" if filtered_cases else "none"
    return {"success": True, "similarity_indicator": similarity_indicator, "cases": [_safe_case_payload(item) for item in filtered_cases]}


@mcp.tool()
def save_summary(case_id: str, summary: str) -> dict:
    """Save a generated case summary."""
    if not case_id or not str(case_id).strip():
        return {"success": False, "error": "case_id is required"}
    if not summary or not str(summary).strip():
        return {"success": False, "error": "summary is required"}

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE public.claims
                SET
                    summary = %s,
                    updated_at = NOW()
                WHERE case_id = %s
                RETURNING case_id
                """,
                (summary[:4000], case_id),
            )
            updated = cur.fetchone()
        conn.commit()

    if updated is None:
        _audit_tool("case_mcp", "save_summary", case_id, "not_found")
        return {"success": False, "error": "Case not found"}

    _audit_tool("case_mcp", "save_summary", case_id, "success")
    return {"success": True, "case_id": case_id, "summary": summary[:4000]}


@mcp.tool()
def get_case_timeline(case_id: str) -> dict:
    """Return a case timeline from the audit ledger."""
    if not case_id or not str(case_id).strip():
        return {"success": False, "error": "case_id is required"}

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, case_id, actor, action, details, created_at
                FROM public.claim_audit
                WHERE case_id = %s
                ORDER BY created_at ASC
                """,
                (case_id,),
            )
            events = cur.fetchall()

    return {"success": True, "case_id": case_id, "timeline": [dict(event) for event in events]}


@mcp.resource("case://{case_id}")
def case_resource(case_id: str) -> dict:
    """Expose a safe case view as an MCP resource."""
    if not case_id or not str(case_id).strip():
        return {"success": False, "error": "case_id is required"}

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    case_id,
                    policy_number,
                    claim_type,
                    claim_amount,
                    status,
                    summary,
                    created_at,
                    updated_at
                FROM public.claims
                WHERE case_id = %s
                """,
                (case_id,),
            )
            case = cur.fetchone()

    if case is None:
        return {"success": False, "error": "Case not found"}

    return {"success": True, "case": _safe_case_payload(case)}


@mcp.resource("case://{case_id}/timeline")
def case_timeline_resource(case_id: str) -> dict:
    """Expose the audit timeline for a claim."""
    if not case_id or not str(case_id).strip():
        return {"success": False, "error": "case_id is required"}

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, case_id, actor, action, details, created_at
                FROM public.claim_audit
                WHERE case_id = %s
                ORDER BY created_at ASC
                """,
                (case_id,),
            )
            events = cur.fetchall()

    return {"success": True, "case_id": case_id, "timeline": [dict(event) for event in events]}


@mcp.prompt()
def case_summary(case_id: str) -> str:
    """Reusable prompt for generating a grounded case summary."""
    return f"""
Review insurance claim {case_id}.

Generate a concise case summary using only information retrieved from approved case,
policy, document, and workflow resources.

Return these sections:
FACTS:
- Verified claim facts only.
EVIDENCE:
- Supporting document evidence.
POLICY STATUS:
- Coverage information supported by policy data.
MISSING INFORMATION:
- Important information that is unavailable.
RISKS:
- Validation issues, low-confidence information, duplicate indicators, or security concerns.
NEXT ACTION:
- Recommend the next processing step.
Rules:
- Use retrieved facts only.
- Separate facts from recommendations.
- Do not invent information.
- Do not make a final claim decision.
- Final claim decisions belong to an authorized human reviewer.
"""


if __name__ == "__main__":
    mcp.run()