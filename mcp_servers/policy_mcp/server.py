from fastmcp import FastMCP

mcp = FastMCP("Policy MCP")


POLICIES = {
    "POL-1001": {
        "policy_number": "POL-1001",
        "product": "Health Plus",
        "status": "active",
        "coverage_limit": 500000,
        "covered_claim_types": ["Medical"],
    },
    "POL-1002": {
        "policy_number": "POL-1002",
        "product": "Motor Protect",
        "status": "active",
        "coverage_limit": 300000,
        "covered_claim_types": ["Vehicle"],
    },
}


@mcp.tool()
def get_policy(policy_number: str) -> dict:
    """Get policy details."""

    policy = POLICIES.get(policy_number)

    if policy is None:
        return {
            "success": False,
            "error": "Policy not found",
        }

    return {
        "success": True,
        "policy": policy,
    }


@mcp.tool()
def check_coverage(
    policy_number: str,
    claim_type: str,
    claim_amount: float,
) -> dict:
    """Check whether the claim is covered by the policy."""

    policy = POLICIES.get(policy_number)

    if policy is None:
        return {
            "success": False,
            "covered": False,
            "reason": "Policy not found",
        }

    if policy["status"] != "active":
        return {
            "success": True,
            "covered": False,
            "reason": "Policy is not active",
        }

    if claim_type not in policy["covered_claim_types"]:
        return {
            "success": True,
            "covered": False,
            "reason": "Claim type is not covered",
        }

    if claim_amount > policy["coverage_limit"]:
        return {
            "success": True,
            "covered": False,
            "reason": "Claim amount exceeds policy limit",
        }

    return {
        "success": True,
        "covered": True,
        "reason": "Claim is within policy coverage",
    }


@mcp.tool()
def search_policy_wording(product: str) -> dict:
    """Get simplified policy wording."""

    wording = {
        "Health Plus":
            "Medical claims are covered subject to policy terms and coverage limits.",
        "Motor Protect":
            "Vehicle claims are covered subject to policy terms and coverage limits.",
    }

    return {
        "success": True,
        "wording": wording.get(
            product,
            "Policy wording not found",
        ),
    }


if __name__ == "__main__":
    mcp.run()