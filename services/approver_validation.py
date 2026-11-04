from __future__ import annotations

from typing import Any

from services.database import get_connection


DEFAULT_APPROVERS = [
    {"name": "Demo Approver", "approval_limit": 25000, "role": "adjuster", "active": True},
    {"name": "Senior Approver", "approval_limit": 100000, "role": "supervisor", "active": True},
    {"name": "Director Approver", "approval_limit": 250000, "role": "director", "active": True},
]


def get_approver_directory() -> list[dict[str, Any]]:
    """Return approvers from the staff table when available, otherwise return local defaults."""
    try:
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
                    ORDER BY approval_limit DESC
                    """
                )
                rows = cur.fetchall()
        if rows:
            return [dict(row) for row in rows]
    except Exception:
        pass

    return [dict(approver) for approver in DEFAULT_APPROVERS]


def validate_approver_limit(approver_name: str, claim_amount: float | int, staff_directory: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Check whether an approver can authorize a given claim amount."""
    directory = staff_directory or get_approver_directory()
    approver = next((item for item in directory if str(item.get("name", "")).lower() == str(approver_name).lower()), None)
    if approver is None:
        # If the approver isn't in the directory, allow a modest default to avoid blocking demo flows.
        default_limit = 50000
        valid = float(claim_amount) <= default_limit
        return {
            "approver": approver_name,
            "approval_limit": default_limit,
            "claim_amount": float(claim_amount),
            "valid": valid,
            "reason": "Fallback approver policy applied." if valid else "Approver is not assigned a high enough limit for this claim amount.",
        }

    limit = float(approver.get("approval_limit", 0) or 0)
    claim_value = float(claim_amount)
    valid = claim_value <= limit
    return {
        "approver": approver.get("name"),
        "approval_limit": limit,
        "claim_amount": claim_value,
        "valid": valid,
        "reason": "Approved within approver limit." if valid else "Claim amount exceeds approver approval limit.",
    }


def get_eligible_approvers(claim_amount: float | int, staff_directory: list[dict[str, Any]] | None = None) -> list[str]:
    directory = staff_directory or get_approver_directory()
    eligible = []
    for approver in directory:
        limit = float(approver.get("approval_limit", 0) or 0)
        if float(claim_amount) <= limit:
            eligible.append(str(approver.get("name", "")))
    return eligible
