"""Digital impersonation heuristic detector (Part 4).

Rule-based analysis of a message and its claimed identity. No ML or LLM
logic lives here — the LLM only writes the explanation.
"""

import re

AUTHORITY_KEYWORDS = (
    "chief executive officer",
    "chief financial officer",
    "director",
    "principal",
    "bank",
    "irs",
    "it support",
)

# Short acronyms are matched on word boundaries so they do not match
# fragments of unrelated words.
AUTHORITY_ACRONYMS = ("ceo", "cfo", "cto", "irs")

PRESSURE_PHRASES = (
    "urgent",
    "immediately",
    "do not question",
    "confidential",
    "asap",
)

UNUSUAL_REQUEST_PHRASES = (
    "gift card",
    "wire transfer",
    "bitcoin",
    "bypass procedure",
    "share codes",
)

SECRECY_PHRASES = (
    "don't tell anyone",
    "dont tell anyone",
    "keep this between us",
    "don't inform finance",
    "dont inform finance",
)


def _phrases_in_text(phrases: tuple[str, ...], text: str) -> list[str]:
    lowered = text.lower()
    return [phrase for phrase in phrases if phrase in lowered]


def _check_authority_identity(claimed_identity: str) -> list[dict]:
    matched = _phrases_in_text(AUTHORITY_KEYWORDS, claimed_identity)
    lowered = claimed_identity.lower()
    matched.extend(
        acronym for acronym in AUTHORITY_ACRONYMS if re.search(rf"\b{acronym}\b", lowered)
    )
    return [
        {
            "type": "authority_identity",
            "value": keyword,
            "severity": "high",
            "description": (
                f"Claimed identity contains the authority keyword '{keyword}'."
            ),
        }
        for keyword in matched
    ]


def _check_pressure(message: str) -> list[dict]:
    matched = _phrases_in_text(PRESSURE_PHRASES, message)
    return [
        {
            "type": "pressure_language",
            "value": phrase,
            "severity": "high",
            "description": f"Urgency/authority pressure phrase '{phrase}' found in the message.",
        }
        for phrase in matched
    ]


def _check_unusual_requests(message: str) -> list[dict]:
    matched = _phrases_in_text(UNUSUAL_REQUEST_PHRASES, message)
    return [
        {
            "type": "unusual_request",
            "value": phrase,
            "severity": "critical",
            "description": (
                f"Financial/unusual request phrase '{phrase}' found; impersonators "
                "commonly use such requests to extract money or access."
            ),
        }
        for phrase in matched
    ]


def _check_secrecy(message: str) -> list[dict]:
    matched = _phrases_in_text(SECRECY_PHRASES, message)
    return [
        {
            "type": "secrecy_request",
            "value": phrase,
            "severity": "high",
            "description": (
                f"Secrecy phrase '{phrase}' found; requests to keep communication "
                "secret are a classic impersonation tactic."
            ),
        }
        for phrase in matched
    ]


def analyze_impersonation_heuristics(message: str, claimed_identity: str) -> list[dict]:
    """Run all impersonation heuristics and return the indicator list."""
    indicators: list[dict] = []
    indicators.extend(_check_authority_identity(claimed_identity))
    indicators.extend(_check_pressure(message))
    indicators.extend(_check_unusual_requests(message))
    indicators.extend(_check_secrecy(message))
    return indicators
