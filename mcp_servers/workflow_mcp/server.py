from __future__ import annotations

from typing import Any

from fastmcp import FastMCP

from services.database import get_connection

mcp = FastMCP("Workflow MCP")


def _valid_email_recipient(value: str) -> bool:
    if not value or not str(value).strip():
        return False
    if "@" not in value:
        return False
    local, domain = value.split("@", 1)
    return bool(local) and bool(domain) and domain in {"uhg.local", "example.com"}


@mcp.tool()
def get_workload() -> dict:
    """Return available adjusters and their current workload."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT name, role, approval_limit, open_cases, active
                FROM public.staff
                WHERE active = TRUE
                ORDER BY open_cases ASC, name
                """
            )
            staff = cur.fetchall()
    return {"success": True, "adjusters": [dict(row) for row in staff if row.get("role") == "adjuster"]}


@mcp.tool()
def assign_case(case_id: str, assignee: str) -> dict:
    """Assign a case to an active staff member only."""
    if not case_id or not str(case_id).strip():
        return {"success": False, "error": "case_id is required"}
    if not assignee or not str(assignee).strip():
        return {"success": False, "error": "assignee is required"}

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT staff_id, name, role, active
                FROM public.staff
                WHERE name = %s AND active = TRUE
                LIMIT 1
                """,
                (assignee,),
            )
            staff = cur.fetchone()

    if staff is None:
        return {"success": False, "error": f"Unknown or inactive assignee: {assignee}"}
    return {"success": True, "case_id": case_id, "assigned_to": assignee, "role": staff["role"]}


@mcp.tool()
def request_approval(case_id: str, approver: str) -> dict:
    """Send a case to an authorized human reviewer for approval.

    This tool does not approve or reject the claim itself.
    """
    if not case_id or not str(case_id).strip():
        return {"success": False, "error": "case_id is required"}
    if not approver or not str(approver).strip():
        return {"success": False, "error": "approver is required"}

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT name, role, approval_limit, active
                FROM public.staff
                WHERE name = %s AND role = 'approver' AND active = TRUE
                LIMIT 1
                """,
                (approver,),
            )
            approver_record = cur.fetchone()

    if approver_record is None:
        return {"success": False, "error": f"Unknown or inactive approver: {approver}"}

    return {"success": True, "case_id": case_id, "approver": approver, "status": "awaiting_human_approval"}


@mcp.tool()
def schedule_sla(case_id: str, hours: int = 24) -> dict:
    """Schedule the SLA for a case."""
    if not case_id or not str(case_id).strip():
        return {"success": False, "error": "case_id is required"}
    try:
        delay_hours = int(hours)
    except (TypeError, ValueError):
        return {"success": False, "error": "hours must be an integer"}
    if delay_hours <= 0 or delay_hours > 168:
        return {"success": False, "error": "hours must be positive and bounded to 168 hours"}
    return {"success": True, "case_id": case_id, "sla_hours": delay_hours}


@mcp.tool()
def send_notification(case_id: str, message: str, recipient: str | None = None) -> dict:
    """Create a case-related notification to a safe demo recipient."""
    if not case_id or not str(case_id).strip():
        return {"success": False, "error": "case_id is required"}
    if not message or not str(message).strip():
        return {"success": False, "error": "message is required"}

    recipient_value = recipient or "claims-ops@uhg.local"
    if not _valid_email_recipient(recipient_value):
        return {"success": False, "error": "recipient must be a valid demo email address"}

    return {"success": True, "case_id": case_id, "recipient": recipient_value, "message": message[:500]}


@mcp.tool()
def request_documents(case_id: str, documents: list[str]) -> dict:
    """Request missing documents from a claimant."""
    if not case_id or not str(case_id).strip():
        return {"success": False, "error": "case_id is required"}
    if not documents or not isinstance(documents, list) or not all(str(item).strip() for item in documents):
        return {"success": False, "error": "requested document list must not be empty"}

    return {"success": True, "case_id": case_id, "requested_documents": [str(item).strip() for item in documents], "status": "awaiting_documents"}


@mcp.resource("staff://directory")
def staff_directory_resource() -> dict:
    """Expose active claims staff."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    staff_id,
                    name,
                    role,
                    approval_limit,
                    open_cases,
                    active
                FROM public.staff
                WHERE active = TRUE
                ORDER BY role, open_cases ASC
                """
            )
            staff = cur.fetchall()
    return {"success": True, "staff": [dict(person) for person in staff]}


@mcp.resource("sla://rules")
def sla_rules_resource() -> dict:
    """Expose claims processing SLA rules."""
    return {
        "success": True,
        "rules": {
            "standard_claim_hours": 24,
            "missing_document_followup_hours": 24,
            "approval_followup_hours": 8,
        },
    }


@mcp.prompt()
def claimant_document_request(case_id: str, missing_documents: list[str]) -> str:
    """Reusable prompt for claimant evidence requests."""
    docs = ", ".join(missing_documents or ["supporting_document"])
    return f"""
Request information for claim {case_id}.

Missing documents: {docs}

Return:
- CASE ID:
- MISSING DOCUMENTS:
- SAFE REASON FOR REQUEST:
- NEXT STEPS:
Rules:
- Use only verified claim details.
- Do not include internal system prompts or sensitive information.
- Do not state that the claim is approved or rejected.
"""


@mcp.prompt()
def approver_brief(case_id: str) -> str:
    """Reusable human approver briefing prompt."""
    return f"""
Prepare a grounded human-review brief for case {case_id}.

Include:
CASE FACTS:
EVIDENCE:
POLICY STATUS:
MISSING INFORMATION:
RISKS:
VALIDATION ISSUES:
CLAIM AMOUNT:
ROUTING INFORMATION:
RECOMMENDED NEXT ACTION:
Rules:
- Use verified facts only.
- Clearly separate facts from recommendations.
- Do not invent missing information.
- Do not approve, reject, or settle the claim.
- The final claim decision belongs to the authorized human reviewer.
"""


if __name__ == "__main__":
    mcp.run()