import re


EMAIL_PATTERN = re.compile(
    r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"
)

PHONE_PATTERN = re.compile(
    r"\b(?:\+?\d{1,3}[-.\s]?)?(?:\d{10}|\d{3}[-.\s]\d{3}[-.\s]\d{4})\b"
)

SSN_PATTERN = re.compile(
    r"\b\d{3}-\d{2}-\d{4}\b"
)


def redact_pii(text: str) -> dict:
    """Redact common PII patterns before model processing."""

    if not text:
        return {
            "text": "",
            "pii_detected": False,
        }

    redacted = text
    detected = False

    if EMAIL_PATTERN.search(redacted):
        detected = True
        redacted = EMAIL_PATTERN.sub(
            "[REDACTED_EMAIL]",
            redacted,
        )

    if PHONE_PATTERN.search(redacted):
        detected = True
        redacted = PHONE_PATTERN.sub(
            "[REDACTED_PHONE]",
            redacted,
        )

    if SSN_PATTERN.search(redacted):
        detected = True
        redacted = SSN_PATTERN.sub(
            "[REDACTED_ID]",
            redacted,
        )

    return {
        "text": redacted,
        "pii_detected": detected,
    }