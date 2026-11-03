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


@mcp.tool()
def list_documents(case_id: str) -> dict:
    """List documents for a claim."""

    return {
        "success": True,
        "documents": DOCUMENTS.get(case_id, []),
    }


@mcp.tool()
def extract_text(case_id: str) -> dict:
    """Return extracted document text."""

    documents = DOCUMENTS.get(case_id, [])

    results = []

    for document in documents:
        results.append(
            {
                "document_id": document["document_id"],
                "text": document["text"],
                "confidence": document["confidence"],
            }
        )

    return {
        "success": True,
        "results": results,
    }


@mcp.tool()
def classify_document(case_id: str) -> dict:
    """Return document classifications."""

    documents = DOCUMENTS.get(case_id, [])

    classifications = []

    for document in documents:
        classifications.append(
            {
                "document_id": document["document_id"],
                "document_type": document["document_type"],
            }
        )

    return {
        "success": True,
        "classifications": classifications,
    }


@mcp.tool()
def extract_fields(case_id: str) -> dict:
    """Return important fields extracted from documents."""

    if case_id == "CASE-001":
        return {
            "success": True,
            "fields": {
                "claimant_name": "Test Customer",
                "amount": 25000,
            },
        }

    return {
        "success": True,
        "fields": {},
    }


@mcp.tool()
def validate_case_documents(case_id: str) -> dict:
    """Check whether required claim documents are present."""

    documents = DOCUMENTS.get(case_id, [])

    if not documents:
        return {
            "success": True,
            "complete": False,
            "missing_documents": [
                "supporting_document"
            ],
        }

    return {
        "success": True,
        "complete": True,
        "missing_documents": [],
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
                (
                    case_id,
                    doc_id,
                ),
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