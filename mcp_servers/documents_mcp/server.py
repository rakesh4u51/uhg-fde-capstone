import re

from fastmcp import FastMCP

from services.database import get_connection
from services.document_processor import (
    _extract_amount,
    _extract_claimant_name,
    _required_documents_for_claim_type,
)

mcp = FastMCP("Documents MCP")


DOCUMENTS = {
    "CASE-001": [
        {
            "document_id": "DOC-001",
            "name": "medical_bill.pdf",
            "document_type": "medical_bill",
            "text": (
                "Hospital bill for Test Customer. "
                "Total amount 25000."
            ),
            "confidence": 0.98,
        }
    ]
}


def _fetch_documents(case_id: str) -> list[dict]:
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT
                        document_id,
                        case_id,
                        file_name AS name,
                        document_type,
                        extracted_text AS text,
                        confidence,
                        injection_detected,
                        created_at
                    FROM public.documents
                    WHERE case_id = %s
                    ORDER BY created_at ASC
                    """,
                    (case_id,),
                )
                rows = cur.fetchall()
        return [dict(row) for row in rows]
    except Exception:
        return DOCUMENTS.get(case_id, [])


@mcp.tool()
def list_documents(case_id: str) -> dict:
    """List documents for a claim."""

    documents = _fetch_documents(case_id)
    return {
        "success": True,
        "documents": documents,
    }


@mcp.tool()
def extract_text(case_id: str) -> dict:
    """Return extracted document text."""

    documents = _fetch_documents(case_id)
    results = []

    for document in documents:
        results.append(
            {
                "document_id": document["document_id"],
                "text": document.get("text") or document.get("extracted_text") or "",
                "confidence": document.get("confidence"),
            }
        )

    return {
        "success": True,
        "results": results,
    }


@mcp.tool()
def classify_document(case_id: str) -> dict:
    """Return document classifications."""

    documents = _fetch_documents(case_id)

    classifications = []

    for document in documents:
        classifications.append(
            {
                "document_id": document["document_id"],
                "document_type": document.get("document_type"),
            }
        )

    return {
        "success": True,
        "classifications": classifications,
    }


@mcp.tool()
def extract_fields(case_id: str) -> dict:
    """Return important fields extracted from documents."""

    documents = _fetch_documents(case_id)
    fields: dict[str, object] = {}

    if documents:
        text = documents[0].get("text") or documents[0].get("extracted_text") or ""
        claimant_match = re.search(r"(?:claimant(?:\s+name)?|patient|insured|policyholder)\s*[:\-]\s*([^\n]+)", text, re.IGNORECASE)
        amount_match = re.search(r"\$\s?\d[\d,]*(?:\.\d{2})?", text, re.IGNORECASE)
        if claimant_match:
            fields["claimant_name"] = claimant_match.group(1).strip()
        if amount_match:
            fields["amount"] = float(amount_match.group(0).replace(",", "").replace("$", ""))

    return {
        "success": True,
        "fields": fields,
    }


def _required_documents_for_claim_type(claim_type: str | None) -> list[str]:
    value = (claim_type or "").strip().lower()
    normalized = "".join(value.split())

    if any(token in normalized for token in ("medical", "health", "hospital", "injury")):
        return ["medical_bill"]
    if any(token in normalized for token in ("vehicle", "car", "auto", "motor")):
        return ["accident_report", "repair_estimate"]
    if any(token in normalized for token in ("property", "home", "dwelling", "fire")):
        return ["property_damage_photos", "repair_invoice"]
    return ["supporting_document"]


@mcp.tool()
def validate_case_documents(case_id: str) -> dict:
    """Check whether required claim documents are present and consistent with the case."""

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT claimant_name, claim_amount, claim_type, policy_number
                FROM public.claims
                WHERE case_id = %s
                """,
                (case_id,),
            )
            claim = cur.fetchone()

    if claim is None:
        return {
            "success": False,
            "complete": False,
            "continue_allowed": False,
            "issues": ["Claim not found."],
            "risks": [],
            "missing_documents": [],
        }

    documents = _fetch_documents(case_id)
    issues: list[str] = []
    risks: list[str] = []
    missing_documents: list[str] = []

    if not documents:
        missing_documents = _required_documents_for_claim_type(claim["claim_type"])
        issues.append("Missing required supporting document(s) for the claim type.")
    else:
        first_document = documents[0]
        extracted_text = first_document.get("text") or first_document.get("extracted_text") or ""
        document_claimant = _extract_claimant_name(extracted_text)
        document_amount = _extract_amount(extracted_text)
        stored_claimant = (claim["claimant_name"] or "").strip()
        stored_amount = claim["claim_amount"]

        if document_claimant and stored_claimant and document_claimant.lower() != stored_claimant.lower():
            issues.append("Claimant name mismatch between document and case record.")
            risks.append("claimant_name_mismatch")

        if document_amount is not None and stored_amount is not None:
            if abs(float(document_amount) - float(stored_amount)) > 0.01:
                issues.append("Amount mismatch between document and claim amount.")
                risks.append("amount_mismatch")

        confidence = float(first_document.get("confidence") or 0.0)
        if confidence < 0.6:
            issues.append("Low confidence extraction requires manual review.")
            risks.append("low_confidence")

        if bool(first_document.get("injection_detected")):
            issues.append("Prompt injection detected; safe handling required before workflow continuation.")
            risks.append("prompt_injection_detected")

    continue_allowed = not bool(issues or missing_documents)

    return {
        "success": True,
        "complete": continue_allowed,
        "continue_allowed": continue_allowed,
        "issues": issues,
        "risks": risks,
        "missing_documents": missing_documents,
    }

@mcp.resource("document://{case_id}/{doc_id}")
def document_resource(
    case_id: str,
    doc_id: str,
) -> dict:
    """Expose a claim document as an MCP resource."""

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    document_id,
                    case_id,
                    file_name,
                    document_type,
                    extracted_text,
                    confidence,
                    injection_detected,
                    created_at
                FROM public.documents
                WHERE case_id = %s
                  AND document_id = %s
                """,
                (case_id, doc_id),
            )

            document = cur.fetchone()

    if document is None:
        return {
            "success": False,
            "error": "Document not found",
        }

    return {
        "success": True,
        "document": dict(document),
    }


if __name__ == "__main__":
    mcp.run()