from fastmcp import FastMCP

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


if __name__ == "__main__":
    mcp.run()