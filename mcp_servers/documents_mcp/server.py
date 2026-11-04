import re

from fastmcp import FastMCP

from services.database import get_connection

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


@mcp.tool()
def validate_case_documents(case_id: str) -> dict:
    """Check whether required claim documents are present."""

    documents = _fetch_documents(case_id)

    if not documents:
        return {
            "success": True,
            "complete": False,
            "missing_documents": [
                "supporting_document"
            ],
        }

    has_injection = any(bool(doc.get("injection_detected")) for doc in documents)

    return {
        "success": True,
        "complete": True,
        "missing_documents": [],
        "risks": ["prompt_injection_detected"] if has_injection else [],
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