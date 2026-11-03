from fastmcp import FastMCP

from services.database import get_connection

mcp = FastMCP("Workflow MCP")


@mcp.tool()
def get_workload() -> dict:
    """Return available adjusters and their current workload."""

    return {
        "success": True,
        "adjusters": [
            {
                "name": "Adjuster A",
                "open_cases": 3,
            },
            {
                "name": "Adjuster B",
                "open_cases": 5,
            },
        ],
    }


@mcp.tool()
def assign_case(case_id: str, assignee: str) -> dict:
    """Assign a case to an adjuster."""

    return {
        "success": True,
        "case_id": case_id,
        "assigned_to": assignee,
    }


@mcp.tool()
def request_approval(case_id: str, approver: str) -> dict:
    """Send a case to an authorized human for approval."""

    return {
        "success": True,
        "case_id": case_id,
        "approver": approver,
        "status": "awaiting_human_approval",
    }


@mcp.tool()
def schedule_sla(case_id: str, hours: int = 24) -> dict:
    """Schedule the service-level target for a case."""

    return {
        "success": True,
        "case_id": case_id,
        "sla_hours": hours,
    }


@mcp.tool()
def send_notification(case_id: str, message: str) -> dict:
    """Create a case-related notification."""

    return {
        "success": True,
        "case_id": case_id,
        "message": message,
    }


@mcp.tool()
def request_documents(case_id: str, documents: list[str]) -> dict:
    """Request missing documents from the claimant."""

    return {
        "success": True,
        "case_id": case_id,
        "requested_documents": documents,
        "status": "awaiting_documents",
    }

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

    return {
        "success": True,
        "staff": [
            dict(person)
            for person in staff
        ],
    }

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
def claimant_letter(
    case_id: str,
    reason: str,
) -> str:
    """Reusable claimant communication prompt."""

    return f"""
Create a professional claimant communication for case {case_id}.

Reason:
{reason}

Requirements:
- Use only verified case information.
- Keep the explanation clear and concise.
- Clearly identify any requested information or documents.
- Do not expose internal agent reasoning.
- Do not include unnecessary personal information.
- Do not state that the claim is approved or rejected unless
  an authorized human decision has already been recorded.
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
- Use only verified information.
- Clearly separate facts from recommendations.
- Do not invent missing information.
- Do not approve, reject, or settle the claim.
- The final claim decision belongs to the authorized human reviewer.
"""

if __name__ == "__main__":
    mcp.run()