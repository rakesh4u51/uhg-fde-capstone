import re

SUSPICIOUS_PATTERNS = [
    "ignore previous instructions",
    "ignore all instructions",
    "ignore system instructions",
    "override system instructions",
    "override instructions",
    "reveal system prompt",
    "reveal the system prompt",
    "reveal prompt",
    "developer message",
    "disregard previous instructions",
    "disregard the previous instructions",
    "do not follow the instructions",
    "do not follow instructions",
    "ignore the developer instructions",
]

COMBINED_PATTERNS = [
    "system prompt",
    "prompt injection",
    "act as if",
    "you are now",
    "ignore the rules",
    "ignore these instructions",
    "bypass safety",
    "bypass the safety",
]


def detect_prompt_injection(text: str) -> dict:
    """Flag typical prompt-injection text while avoiding noisy false positives."""

    if not text:
        return {"detected": False, "matches": []}

    normalized = re.sub(r"\s+", " ", str(text)).strip().lower()
    matches = []

    for pattern in SUSPICIOUS_PATTERNS:
        if pattern in normalized:
            matches.append(pattern)

    for pattern in COMBINED_PATTERNS:
        if pattern in normalized:
            matches.append(pattern)

    unique_matches = list(dict.fromkeys(matches))
    strong_hit = any(pattern in normalized for pattern in SUSPICIOUS_PATTERNS)
    weak_hit_count = sum(1 for pattern in COMBINED_PATTERNS if pattern in normalized)
    detected = bool(strong_hit or weak_hit_count >= 2)

    return {
        "detected": detected,
        "matches": unique_matches,
    }