SUSPICIOUS_PATTERNS = [
    "ignore previous instructions",
    "ignore all instructions",
    "ignore system instructions",
    "override instructions",
    "reveal system prompt",
    "reveal prompt",
    "system prompt",
    "developer message",
    "disregard previous",
]


def detect_prompt_injection(text: str) -> dict:
    """Detect suspicious instruction-like content in documents."""

    if not text:
        return {
            "detected": False,
            "matches": [],
        }

    normalized = text.lower()

    matches = [
        pattern
        for pattern in SUSPICIOUS_PATTERNS
        if pattern in normalized
    ]

    return {
        "detected": bool(matches),
        "matches": matches,
    }