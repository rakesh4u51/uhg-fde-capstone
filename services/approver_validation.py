from __future__ import annotations

from typing import Any

from services.database import get_connection


DEFAULT_APPROVERS = [
    {"name": "Demo Approver", "approval_limit": 25000, "role": "adjuster", "active": True},
    {"name": "Senior Approver", "approval_limit": 100000, "role": "supervisor", "active": True},
    {"name": "Director Approver", "approval_limit": 250000, "role": "director", "active": True},
]


def _normalize_approver_directory(rows: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    if not rows:
        return [dict(approver) for approver in DEFAULT_APPROVERS]

    normalized = []
    for row in rows:
        if not row.get("name"):
            continue
        normalized.append(
            {
                "name": row.get("name"),
                "role": row.get("role", "adjuster"),
                "approval_limit": float(row.get("approval_limit", 0) or 0),
                "active": bool(row.get("active", True)),
            }
        )

    if not normalized:
        return [dict(approver) for approver in DEFAULT_APPROVERS]

    required_names = {str(approver["name"]).lower() for approver in DEFAULT_APPROVERS}
    actual_names = {str(approver["name"]).lower() for approver in normalized}
    if not required_names.issubset(actual_names):
        return [dict(approver) for approver in DEFAULT_APPROVERS]

    return normalized


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
        return _normalize_approver_directory(rows)
    except Exception:
        pass

    return [dict(approver) for approver in DEFAULT_APPROVERS]


def validate_approver_limit(approver_name: str, claim_amount: float | int, staff_directory: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Check whether an approver can authorize a given claim amount."""
    directory = staff_directory or get_approver_directory()
    approver = next((item for item in directory if str(item.get("name", "")).lower() == str(approver_name).lower()), None)
    if approver is None:
        default_limit = 50000
        valid = float(claim_amount) <= default_limit
        return {
            "approver": approver_name,
            "approval_limit": default_limit,
            "claim_amount": float(claim_amount),
            "valid": valid,
            "source": "demo fallback configuration",
            "reason": "demo fallback configuration applied." if valid else "demo fallback configuration rejected this claim amount.",
        }

    active = bool(approver.get("active", True))
    role = str(approver.get("role", "")).lower()
    is_approver_role = role in {"approver", "adjuster", "supervisor", "director"}
    limit = float(approver.get("approval_limit", 0) or 0)
    claim_value = float(claim_amount)
    valid = active and is_approver_role and claim_value <= limit
    return {
        "approver": approver.get("name"),
        "approval_limit": limit,
        "claim_amount": claim_value,
        "valid": valid,
        "source": "public.staff",
        "reason": "Approved within approver limit and active approver role." if valid else "Claim amount exceeds approver approval limit or approver is inactive or not authorized.",
    }


def get_eligible_approvers(claim_amount: float | int, staff_directory: list[dict[str, Any]] | None = None) -> list[str]:
    directory = staff_directory or get_approver_directory()
    eligible = []
    for approver in directory:
        limit = float(approver.get("approval_limit", 0) or 0)
        if float(claim_amount) <= limit:
            eligible.append(str(approver.get("name", "")))
    return eligible
