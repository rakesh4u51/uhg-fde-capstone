from fastmcp import FastMCP

mcp = FastMCP("Case MCP")

CASES = {
    "CASE-001": {
        "case_id": "CASE-001",
        "policy_number": "POL-1001",
        "claimant_name": "Test Customer",
        "claim_type": "Medical",
        "claim_amount": 25000,
        "status": "submitted",
        "summary": "",
    }
}


@mcp.tool()
def get_case(case_id: str) -> dict:
    """Get claim information using a case ID."""

    case = CASES.get(case_id)

    if case is None:
        return {
            "success": False,
            "error": "Case not found",
        }

    return {
        "success": True,
        "case": case,
    }


@mcp.tool()
def list_cases() -> dict:
    """List all claim cases."""

    return {
        "success": True,
        "cases": list(CASES.values()),
    }


@mcp.tool()
def register_case(
    case_id: str,
    policy_number: str,
    claimant_name: str,
    claim_type: str,
    claim_amount: float,
) -> dict:
    """Register a new claim."""

    if case_id in CASES:
        return {
            "success": False,
            "error": "Case already exists",
        }

    CASES[case_id] = {
        "case_id": case_id,
        "policy_number": policy_number,
        "claimant_name": claimant_name,
        "claim_type": claim_type,
        "claim_amount": claim_amount,
        "status": "submitted",
        "summary": "",
    }

    return {
        "success": True,
        "case": CASES[case_id],
    }


@mcp.tool()
def find_similar_cases(policy_number: str) -> dict:
    """Find claims belonging to the same policy."""

    matches = [
        case
        for case in CASES.values()
        if case["policy_number"] == policy_number
    ]

    return {
        "success": True,
        "cases": matches,
    }


@mcp.tool()
def save_summary(case_id: str, summary: str) -> dict:
    """Save the generated claim summary."""

    case = CASES.get(case_id)

    if case is None:
        return {
            "success": False,
            "error": "Case not found",
        }

    case["summary"] = summary

    return {
        "success": True,
        "case_id": case_id,
        "summary": summary,
    }


if __name__ == "__main__":
    mcp.run()