from fastmcp import FastMCP

from services.database import get_connection


mcp = FastMCP("Case MCP")


@mcp.tool()
def get_case(case_id: str) -> dict:
    """Get a claim case from PostgreSQL."""

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
        return {
            "success": False,
            "error": "Case not found",
        }

    return {
        "success": True,
        "case": dict(case),
    }


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
                    description,
                    status,
                    summary,
                    created_at,
                    updated_at
                FROM public.claims
                ORDER BY created_at DESC
                """
            )

            cases = cur.fetchall()

    return {
        "success": True,
        "cases": [
            dict(case)
            for case in cases
        ],
    }


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
                        summary
                    """,
                    (
                        case_id,
                        policy_number,
                        claimant_name,
                        claim_type,
                        claim_amount,
                        description,
                    ),
                )

                case = cur.fetchone()

            conn.commit()

        return {
            "success": True,
            "case": dict(case),
        }

    except Exception as exc:
        return {
            "success": False,
            "error": str(exc),
        }


@mcp.tool()
def find_similar_cases(
    policy_number: str,
) -> dict:
    """Find claims associated with the same policy."""

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
                    status
                FROM public.claims
                WHERE policy_number = %s
                ORDER BY created_at DESC
                """,
                (policy_number,),
            )

            cases = cur.fetchall()

    return {
        "success": True,
        "cases": [
            dict(case)
            for case in cases
        ],
    }


@mcp.tool()
def save_summary(
    case_id: str,
    summary: str,
) -> dict:
    """Save a generated case summary."""

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
                (
                    summary,
                    case_id,
                ),
            )

            case = cur.fetchone()

        conn.commit()

    if case is None:
        return {
            "success": False,
            "error": "Case not found",
        }

    return {
        "success": True,
        "case_id": case_id,
        "summary": summary,
    }


if __name__ == "__main__":
    mcp.run()