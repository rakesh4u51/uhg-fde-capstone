import re
import uuid
from pathlib import Path
from typing import Any

from models.document_models import DocumentProcessingResult
from security.injection_guard import detect_prompt_injection
from security.pii_guard import redact_pii
from services.database import get_connection

try:  # Docling is optional in this lab environment.
    from docling.document_converter import DocumentConverter
except Exception:  # pragma: no cover - runtime environment dependent
    DocumentConverter = None


CURRENCY_PATTERN = re.compile(r"\$\s?\d[\d,]*(?:\.\d{2})?|\d[\d,]*(?:\.\d{2})?\s*(?:USD|US\$)\b", re.IGNORECASE)
CLAIMANT_PATTERNS = [
    re.compile(
        r"^(?:claimant(?:\s+name)?|patient|insured|policyholder)\s*[:\-]\s*(.+?)(?=\s*(?:\n|$|(?:policy(?:\s*(?:number|num|#))?|amount|service\s+date|contact|date\s+of\s+birth|dob)))",
        re.IGNORECASE | re.MULTILINE,
    ),
    re.compile(
        r"^name\s*[:\-]\s*(.+?)(?=\s*(?:\n|$|(?:policy(?:\s*(?:number|num|#))?|amount|service\s+date|contact|date\s+of\s+birth|dob)))",
        re.IGNORECASE | re.MULTILINE,
    ),
]
POLICY_PATTERNS = [
    re.compile(r"^(?:policy\s*(?:number|num)|policy number|policy#|policy)\s*[:\-]\s*(.+)$", re.IGNORECASE | re.MULTILINE),
    re.compile(r"\b(?:POL|POLICY)[-_ ]?\d+[A-Z0-9-]*\b", re.IGNORECASE),
]
DATE_PATTERNS = [
    re.compile(r"\b(?:\d{4})-(?:\d{2})-(?:\d{2})\b"),
    re.compile(r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{1,2},?\s+\d{4}\b", re.IGNORECASE),
]


def _normalize_text(value: str) -> str:
    text = (value or "").replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(
        r"(?<=[A-Za-z0-9])\s+(?=(?:Claimant|Patient|Insured|Policyholder|Policy|Amount|Service|Date|Contact|Provider|Claim|Status|Description|Summary|DOB|Date of Birth))",
        "\n",
        text,
        flags=re.IGNORECASE,
    )
    return "\n".join(line.strip() for line in text.splitlines()).strip()


def _coerce_structure(value: Any) -> Any:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, dict):
        return {str(k): _coerce_structure(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_coerce_structure(item) for item in value]
    if hasattr(value, "model_dump"):
        return _coerce_structure(value.model_dump())
    if hasattr(value, "__dict__"):
        data = {
            key: _coerce_structure(val)
            for key, val in vars(value).items()
            if not key.startswith("_")
        }
        return data
    return str(value)


def _extract_from_document(document: Any) -> tuple[str, dict[str, Any]]:
    text = ""

    exporters = []
    for name in ("export_to_text", "export_to_markdown", "export_to_html"):
        if hasattr(document, name):
            exporters.append(name)

    if exporters:
        for name in exporters:
            try:
                candidate = getattr(document, name)()
                if isinstance(candidate, str) and candidate.strip():
                    text = candidate
                    break
            except Exception:
                continue

    if not text and hasattr(document, "text"):
        text = str(getattr(document, "text"))

    if not text and hasattr(document, "body"):
        body = getattr(document, "body")
        if hasattr(body, "export_to_text"):
            text = str(body.export_to_text())

    structure: dict[str, Any] = {}
    for attr_name in ("texts", "sections", "pages"):
        if hasattr(document, attr_name):
            structure[attr_name] = _coerce_structure(getattr(document, attr_name))

    return _normalize_text(text), structure


def _extract_claimant_name(text: str) -> str | None:
    for pattern in CLAIMANT_PATTERNS:
        match = pattern.search(text)
        if match:
            value = match.group(1).strip()
            value = value.split("\n", 1)[0].strip()
            if value:
                return value
    return None


def _extract_policy_number(text: str) -> str | None:
    for pattern in POLICY_PATTERNS:
        match = pattern.search(text)
        if match:
            value = match.group(1).strip() if match.lastindex else match.group(0).strip()
            value = value.split("\n", 1)[0].strip()
            if value:
                return value
    return None


def _extract_amount(text: str) -> float | None:
    match = None
    for pattern in (
        re.compile(r"\$\s?\d[\d,]*(?:\.\d{2})?", re.IGNORECASE),
        re.compile(r"\b\d[\d,]*(?:\.\d{2})?\s*(?:USD|US\$)\b", re.IGNORECASE),
        re.compile(r"\b\d[\d,]*(?:\.\d{2})?\b"),
    ):
        for candidate in pattern.finditer(text):
            raw = candidate.group(0).replace(",", "").replace("$", "").replace("USD", "").replace("US$", "").strip()
            if not raw:
                continue
            try:
                value = float(raw)
                if value > 0:
                    match = value
                    break
            except ValueError:
                continue
        if match is not None:
            break
    return match


def _extract_service_date(text: str) -> str | None:
    for pattern in DATE_PATTERNS:
        match = pattern.search(text)
        if match:
            return match.group(0).strip()
    return None


def _infer_document_type(file_name: str, text: str) -> str | None:
    lowered_name = (file_name or "").lower()
    lowered_text = text.lower()

    if any(term in lowered_name for term in ("invoice", "bill", "medical", "hospital")) or any(term in lowered_text for term in ("hospital bill", "medical bill", "provider", "treatment")):
        return "medical_bill"
    if any(term in lowered_name for term in ("receipt", "statement")) or any(term in lowered_text for term in ("receipt", "service rendered")):
        return "receipt"
    if any(term in lowered_name for term in ("claim", "submission")) or "claim form" in lowered_text:
        return "claim_form"
    if "policy" in lowered_text or "coverage" in lowered_text:
        return "policy_document"
    if "letter" in lowered_name or "correspondence" in lowered_name:
        return "letter"
    return None


def _calculate_confidence(text: str, field_count: int, conversion_error: str | None, injection_detected: bool) -> float:
    if not text.strip():
        return 0.0

    confidence = 0.55
    confidence += min(0.25, field_count * 0.12)

    if field_count >= 4 and not injection_detected:
        confidence += 0.15

    if conversion_error:
        confidence -= 0.15
    if injection_detected:
        confidence -= 0.35
    if len(text.split()) < 20 and field_count < 4:
        confidence -= 0.10

    return max(0.0, min(1.0, round(confidence, 2)))


def _choose_missing_fields(values: dict[str, Any]) -> list[str]:
    missing = []
    for field_name in ("claimant_name", "document_type", "amount", "policy_number", "service_date"):
        value = values.get(field_name)
        if value in (None, "", []):
            missing.append(field_name)
    return missing


def save_document_result(
    case_id: str,
    file_path: str,
    document_id: str | None = None,
    result: DocumentProcessingResult | None = None,
) -> dict[str, Any]:
    """Persist the extracted document metadata to the PostgreSQL documents table."""

    if not case_id:
        raise ValueError("case_id is required to store a document result")

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM public.claims WHERE case_id = %s",
                (case_id,),
            )
            if cur.fetchone() is None:
                raise ValueError(f"case_id '{case_id}' does not exist in public.claims")

    if result is None:
        result = process_document(file_path)

    if document_id is None:
        document_id = f"DOC-{uuid.uuid4().hex[:8].upper()}"

    path = Path(file_path)
    payload = {
        "document_id": document_id,
        "case_id": case_id,
        "file_name": path.name,
        "document_type": result.document_type,
        "extracted_text": result.extracted_text,
        "confidence": float(result.confidence),
        "injection_detected": bool(result.injection_detected),
    }

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO public.documents (
                    document_id,
                    case_id,
                    file_name,
                    document_type,
                    extracted_text,
                    confidence,
                    injection_detected
                ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (document_id) DO UPDATE SET
                    case_id = EXCLUDED.case_id,
                    file_name = EXCLUDED.file_name,
                    document_type = EXCLUDED.document_type,
                    extracted_text = EXCLUDED.extracted_text,
                    confidence = EXCLUDED.confidence,
                    injection_detected = EXCLUDED.injection_detected
                RETURNING document_id, case_id, file_name, document_type, extracted_text, confidence, injection_detected
                """,
                (
                    payload["document_id"],
                    payload["case_id"],
                    payload["file_name"],
                    payload["document_type"],
                    payload["extracted_text"],
                    payload["confidence"],
                    payload["injection_detected"],
                ),
            )
            row = cur.fetchone()
            if row is not None:
                payload.update(dict(row))
            conn.commit()

    return payload


def process_document(file_path: str) -> DocumentProcessingResult:
    """Convert a document to text, sanitize it, and return structured extraction metadata."""

    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Document not found: {file_path}")

    extracted_text = ""
    structure: dict[str, Any] = {}
    conversion_error: str | None = None

    if DocumentConverter is not None:
        try:
            converter = DocumentConverter()
            conversion_result = converter.convert(str(path))
            if isinstance(conversion_result, list):
                conversion_result = conversion_result[0]

            if hasattr(conversion_result, "document"):
                document = conversion_result.document
                extracted_text, structure = _extract_from_document(document)
            else:
                extracted_text, structure = _extract_from_document(conversion_result)
        except Exception as exc:  # pragma: no cover - external library may vary
            conversion_error = f"Docling conversion failed: {exc}"
    else:
        conversion_error = "Docling is not installed in the current environment."

    if not extracted_text:
        try:
            extracted_text = path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            extracted_text = ""

    normalized = _normalize_text(extracted_text)
    injection = detect_prompt_injection(normalized)
    pii = redact_pii(normalized)
    safe_text = pii["text"]

    claimant_name = _extract_claimant_name(safe_text)
    policy_number = _extract_policy_number(safe_text)
    amount = _extract_amount(safe_text)
    service_date = _extract_service_date(safe_text)
    document_type = _infer_document_type(path.name, safe_text)

    field_values = {
        "claimant_name": claimant_name,
        "document_type": document_type,
        "amount": amount,
        "policy_number": policy_number,
        "service_date": service_date,
    }

    result = DocumentProcessingResult(
        claimant_name=claimant_name,
        document_type=document_type,
        amount=amount,
        policy_number=policy_number,
        service_date=service_date,
        confidence=0.0,
        missing_fields=[],
        validation_issues=[],
        injection_detected=injection.get("detected", False),
        pii_redacted=bool(pii.get("pii_detected")),
        conversion_error=conversion_error,
        extracted_text=safe_text,
        file_path=str(path),
        document_structure=structure,
    )

    result.missing_fields = _choose_missing_fields(field_values)
    result.confidence = _calculate_confidence(
        safe_text,
        len([value for value in field_values.values() if value not in (None, "")]),
        conversion_error,
        result.injection_detected,
    )

    if result.injection_detected:
        result.validation_issues.append("Prompt injection detected; content was not forwarded to the LLM.")
    if result.pii_redacted:
        result.validation_issues.append("PII was redacted before processing.")
    if result.confidence < 0.5:
        result.validation_issues.append("Low confidence extraction.")
    if conversion_error and not safe_text.strip():
        result.validation_issues.append("Document could not be read reliably.")

    return result


def validate_document_case(
    case_id: str,
    document_result: DocumentProcessingResult | None = None,
    file_path: str | None = None,
) -> dict[str, Any]:
    """Deterministically validate extracted document data against the case and policy records."""

    if not case_id:
        raise ValueError("case_id is required for validation")

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    case_id,
                    claimant_name,
                    policy_number,
                    claim_type,
                    claim_amount,
                    status,
                    summary
                FROM public.claims
                WHERE case_id = %s
                """,
                (case_id,),
            )
            claim = cur.fetchone()

            if claim is None:
                raise ValueError(f"Unknown claim case_id: {case_id}")

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
                (claim["policy_number"],),
            )
            policy = cur.fetchone()

            cur.execute(
                """
                SELECT document_id, file_name, document_type, confidence, injection_detected
                FROM public.documents
                WHERE case_id = %s
                ORDER BY created_at ASC
                """,
                (case_id,),
            )
            documents = cur.fetchall()

    if document_result is None:
        if file_path is None:
            raise ValueError("Either document_result or file_path is required for validation")
        document_result = process_document(file_path)

    issues: list[str] = []
    risks: list[str] = []
    missing_documents: list[str] = []

    if not documents:
        missing_documents.append("supporting_document")
        issues.append("Missing required supporting document.")

    if document_result.injection_detected or any("prompt injection" in item.lower() for item in document_result.validation_issues):
        issues.append("Prompt injection detected; safe handling required before workflow continuation.")
        risks.append("prompt_injection_detected")

    document_claimant = (document_result.claimant_name or "").strip()
    stored_claimant = (claim["claimant_name"] or "").strip()
    if document_claimant and stored_claimant and document_claimant.lower() != stored_claimant.lower():
        issues.append("Claimant name mismatch between document and case record.")
        risks.append("claimant_name_mismatch")

    if document_result.amount is not None and claim["claim_amount"] is not None:
        document_amount = float(document_result.amount)
        claim_amount = float(claim["claim_amount"])
        if abs(document_amount - claim_amount) > 0.01:
            issues.append("Amount mismatch between document and claim amount.")
            risks.append("amount_mismatch")

    if document_result.confidence < 0.6:
        issues.append("Low confidence extraction requires manual review.")
        risks.append("low_confidence")

    if policy is not None:
        coverage_limit = float(policy["coverage_limit"])
        claim_amount = float(claim["claim_amount"])
        covered_types = policy.get("covered_claim_types") or []
        if policy["status"] != "active":
            issues.append("Policy is not active.")
            risks.append("policy_inactive")
        if claim["claim_type"] not in covered_types:
            issues.append("Claim type is not covered by the assigned policy.")
            risks.append("policy_inconsistency")
        if claim_amount > coverage_limit:
            issues.append("Claim amount exceeds policy coverage limit.")
            risks.append("policy_limit_exceeded")
    elif claim.get("policy_number"):
        issues.append("Policy record missing for the claim's policy number.")
        risks.append("policy_missing")

    continue_allowed = not bool(issues or missing_documents)

    return {
        "case_id": case_id,
        "continue_allowed": continue_allowed,
        "issues": issues,
        "risks": risks,
        "missing_documents": missing_documents,
        "claim": dict(claim),
        "policy": dict(policy) if policy else None,
        "document_count": len(documents),
        "confidence": float(document_result.confidence),
        "document_claimant_name": document_claimant,
        "document_amount": document_result.amount,
        "case_claimant_name": stored_claimant,
        "case_amount": float(claim["claim_amount"]),
    }
