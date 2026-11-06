from __future__ import annotations

from typing import Any

from fastmcp import FastMCP

from services.database import get_connection


mcp = FastMCP("Policy MCP")


def fetch_policy(policy_number: str):
    """Internal helper to fetch a policy from PostgreSQL."""
    if not policy_number or not str(policy_number).strip():
        return None

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


def _safe_policy(policy: dict[str, Any] | None) -> dict[str, Any]:
    if not policy:
        return {}
    policy = dict(policy)
    return {
        "policy_number": policy.get("policy_number"),
        "product": policy.get("product"),
        "status": policy.get("status"),
        "coverage_limit": policy.get("coverage_limit"),
        "covered_claim_types": policy.get("covered_claim_types"),
    }


@mcp.tool()
def get_policy(policy_number: str) -> dict:
    """Get policy details from PostgreSQL."""
    if not policy_number or not str(policy_number).strip():
        return {"success": False, "error": "policy_number is required"}

    policy = fetch_policy(policy_number)
    if policy is None:
        return {"success": False, "error": "Policy not found"}
    return {"success": True, "policy": _safe_policy(policy)}


@mcp.tool()
def check_coverage(policy_number: str, claim_type: str, claim_amount: float) -> dict:
    """Check policy coverage without making a final claim decision."""
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

    policy = fetch_policy(policy_number)
    if policy is None:
        return {"success": False, "covered": False, "reason": "Policy not found", "policy_number": policy_number}

    policy = dict(policy)
    covered_types = list(policy.get("covered_claim_types") or [])

    if policy.get("status") != "active":
        return {
            "success": True,
            "covered": False,
            "reason": "Policy is not active",
            "policy_number": policy_number,
            "policy_status": policy.get("status"),
            "coverage_limit": policy.get("coverage_limit"),
            "covered_claim_types": covered_types,
            "claim_type": claim_type,
            "claim_amount": amount,
        }

    if claim_type not in covered_types:
        return {
            "success": True,
            "covered": False,
            "reason": "Claim type is not covered",
            "policy_number": policy_number,
            "policy_status": policy.get("status"),
            "coverage_limit": policy.get("coverage_limit"),
            "covered_claim_types": covered_types,
            "claim_type": claim_type,
            "claim_amount": amount,
        }

    if amount > float(policy.get("coverage_limit") or 0):
        return {
            "success": True,
            "covered": False,
            "reason": "Claim amount exceeds policy limit",
            "policy_number": policy_number,
            "policy_status": policy.get("status"),
            "coverage_limit": policy.get("coverage_limit"),
            "covered_claim_types": covered_types,
            "claim_type": claim_type,
            "claim_amount": amount,
        }

    return {
        "success": True,
        "covered": True,
        "reason": "Claim is within policy coverage",
        "policy_number": policy_number,
        "policy_status": policy.get("status"),
        "coverage_limit": policy.get("coverage_limit"),
        "covered_claim_types": covered_types,
        "claim_type": claim_type,
        "claim_amount": amount,
    }


def _coerce_policy_clause(policy: dict[str, Any]) -> str:
    policy_number = str(policy.get("policy_number") or "unknown")
    product = str(policy.get("product") or "unknown")
    status = str(policy.get("status") or "unknown")
    limit = policy.get("coverage_limit")
    covered = policy.get("covered_claim_types") or []
    if isinstance(covered, str):
        covered = [covered]
    covered_text = ", ".join(str(item) for item in covered) if covered else "listed claim types"
    return (
        f"Policy {policy_number} ({product}) is {status}. "
        f"It covers {covered_text} up to {limit}."
    )


def _deterministic_policy_match(query: str, policy_number: str | None = None) -> tuple[dict[str, Any] | None, float, str]:
    normalized_query = " ".join(str(query or "").lower().split())
    if not normalized_query:
        return None, 0.0, "empty query"

    with get_connection() as conn:
        with conn.cursor() as cur:
            if policy_number:
                cur.execute(
                    """
                    SELECT policy_number, product, status, coverage_limit, covered_claim_types
                    FROM public.policies
                    WHERE policy_number = %s
                    LIMIT 1
                    """,
                    (policy_number,),
                )
                rows = cur.fetchall()
            else:
                cur.execute(
                    """
                    SELECT policy_number, product, status, coverage_limit, covered_claim_types
                    FROM public.policies
                    ORDER BY policy_number
                    """
                )
                rows = cur.fetchall()

    best_match = None
    best_score = 0.0
    for row in rows:
        policy = dict(row)
        clause = _coerce_policy_clause(policy)
        haystack = " ".join(
            [
                str(policy.get("policy_number") or ""),
                str(policy.get("product") or ""),
                str(policy.get("status") or ""),
                str(policy.get("coverage_limit") or ""),
                " ".join(str(item) for item in (policy.get("covered_claim_types") or [])),
                clause,
            ]
        ).lower()

        score = 0.0
        for token in normalized_query.split():
            if token in haystack:
                score += 0.18
        for phrase in ("medical", "hospital", "inpatient", "treatment", "coverage", "covered", "policy"):
            if phrase in normalized_query and phrase in haystack:
                score += 0.25

        if policy_number and str(policy.get("policy_number")) == str(policy_number):
            score += 0.4
        if score > best_score:
            best_score = score
            best_match = policy

    if best_match is None:
        return None, 0.0, "no match"
    return best_match, min(best_score, 1.0), "deterministic_lookup"


@mcp.tool()
def search_policy_wording(query: str | None = None, policy_number: str | None = None, product: str | None = None) -> dict:
    """Search the policy catalog using deterministic matches and optional pgvector when configured."""
    target_query = str(query or product or "").strip()
    target_policy = str(policy_number or "").strip() or None

    if not target_query and not target_policy:
        return {"success": False, "error": "query or policy_number is required"}

    if target_policy:
        policy = fetch_policy(target_policy)
        if policy is None:
            return {"success": False, "policy_number": target_policy, "matches": [], "reason": "Policy not found"}
        clause = _coerce_policy_clause(dict(policy))
        return {
            "success": True,
            "policy_number": target_policy,
            "matching_policy_clause": clause,
            "similarity_score": 1.0,
            "source": "deterministic_lookup",
            "limitation": "pgvector not configured; deterministic policy lookup is active.",
        }

    policy, score, source = _deterministic_policy_match(target_query, target_policy)
    if policy is None:
        return {
            "success": False,
            "query": target_query,
            "policy_number": target_policy,
            "matches": [],
            "reason": "No matching policy wording found.",
            "source": source,
            "limitation": "pgvector not configured; deterministic lookup did not find a match.",
        }

    clause = _coerce_policy_clause(policy)
    return {
        "success": True,
        "policy_number": policy.get("policy_number"),
        "matching_policy_clause": clause,
        "similarity_score": round(float(score), 3),
        "source": source,
        "limitation": "pgvector not configured; using deterministic policy lookup.",
    }


@mcp.resource("policy://{policy_number}")
def policy_resource(policy_number: str) -> dict:
    """Expose safe policy information as an MCP resource."""
    policy = fetch_policy(policy_number)
    if policy is None:
        return {"success": False, "error": "Policy not found"}
    return {"success": True, "policy": _safe_policy(policy)}


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
        return {"success": False, "error": "Product not found"}
    return {"success": True, "product": product, "policies": [_safe_policy(dict(policy)) for policy in policies]}


@mcp.prompt()
def coverage_explanation(policy_number: str, claim_type: str, claim_amount: float) -> str:
    """Reusable prompt explaining coverage status without final decision authority."""
    return f"""
Explain coverage for policy {policy_number}.

Use the verified policy record and the claim details below.
CLAIM TYPE: {claim_type}
CLAIM AMOUNT: {claim_amount}
Return:
- POLICY STATUS:
- COVERAGE RESULT:
- COVERAGE LIMIT:
- RELEVANT POLICY WORDING:
- UNRESOLVED POLICY ISSUES:
Rules:
- Use only verified policy information.
- Do not make a final claim decision.
- Separate policy status from recommendation.
"""


if __name__ == "__main__":
    mcp.run()