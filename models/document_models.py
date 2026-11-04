from typing import Any

from pydantic import BaseModel, Field


class DocumentExtractionResult(BaseModel):
    """Structured extraction result for a single claim document."""

    claimant_name: str | None = None
    document_type: str | None = None
    amount: float | None = None
    policy_number: str | None = None
    service_date: str | None = None
    confidence: float = 0.0
    missing_fields: list[str] = Field(default_factory=list)
    validation_issues: list[str] = Field(default_factory=list)
    injection_detected: bool = False
    pii_redacted: bool = False
    conversion_error: str | None = None
    extracted_text: str = ""
    file_path: str | None = None
    document_structure: dict[str, Any] = Field(default_factory=dict)


class DocumentProcessingResult(DocumentExtractionResult):
    """Alias kept for readability when a processor returns the structured payload."""

    pass
