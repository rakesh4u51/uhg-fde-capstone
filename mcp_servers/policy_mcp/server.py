from fastmcp import FastMCP

from services.database import get_connection


mcp = FastMCP("Policy MCP")


def fetch_policy(policy_number: str):
    """Internal helper to fetch a policy from PostgreSQL."""

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    policy_number,
                    product,
                    status,
                    coverage_limit,
                    covered_claim_types
                FROM public.policies
                WHERE policy_number = %s
                """,
                (policy_number,),
            )

            policy = cur.fetchone()

    return policy


@mcp.tool()
def get_policy(policy_number: str) -> dict:
    """Get policy details from PostgreSQL."""

    policy = fetch_policy(policy_number)

    if policy is None:
        return {
            "success": False,
            "error": "Policy not found",
        }

    return {
        "success": True,
        "policy": dict(policy),
    }


@mcp.tool()
def check_coverage(
    policy_number: str,
    claim_type: str,
    claim_amount: float,
) -> dict:
    """Check whether a claim is within policy coverage."""

    policy = fetch_policy(policy_number)

    if policy is None:
        return {
            "success": False,
            "covered": False,
            "reason": "Policy not found",
        }

    policy = dict(policy)

    if policy["status"] != "active":
        return {
            "success": True,
            "covered": False,
            "reason": "Policy is not active",
        }

    covered_types = policy.get(
        "covered_claim_types",
        [],
    )

    if claim_type not in covered_types:
        return {
            "success": True,
            "covered": False,
            "reason": "Claim type is not covered",
        }

    if float(claim_amount) > float(
        policy["coverage_limit"]
    ):
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
    """Search policy information by product."""

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    policy_number,
                    product,
                    status,
                    coverage_limit,
                    covered_claim_types
                FROM public.policies
                WHERE product ILIKE %s
                ORDER BY policy_number
                """,
                (f"%{product}%",),
            )

            policies = cur.fetchall()

    return {
        "success": True,
        "policies": [
            dict(policy)
            for policy in policies
        ],
    }

@mcp.resource("policy://{policy_number}")
def policy_resource(policy_number: str) -> dict:
    """Expose policy information as an MCP resource."""

    policy = fetch_policy(policy_number)

    if policy is None:
        return {
            "success": False,
            "error": "Policy not found",
        }

    return {
        "success": True,
        "policy": dict(policy),
    }

@mcp.resource("policy-wording://{product}")
def policy_wording_resource(product: str) -> dict:
    """Expose policy information for a product."""

    with get_connection() as conn:
        with conn.cursor() as cur:

            cur.execute(
                """
                SELECT
                    policy_number,
                    product,
                    status,
                    coverage_limit,
                    covered_claim_types
                FROM public.policies
                WHERE product ILIKE %s
                ORDER BY policy_number
                """,
                (f"%{product}%",),
            )

            policies = cur.fetchall()

    if not policies:
        return {
            "success": False,
            "error": "Product not found",
        }

    return {
        "success": True,
        "product": product,
        "policies": [
            dict(policy)
            for policy in policies
        ],
    }

if __name__ == "__main__":
    mcp.run()