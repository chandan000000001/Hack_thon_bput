"""Digital impersonation heuristic detector (Part 4).

Rule-based analysis of a message and its claimed identity. No ML or LLM
logic lives here — the LLM only writes the explanation.
"""

import re

from app.core.calibration import get_impersonation_calibration

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


def _check_authority_identity(claimed_identity: str, has_request_indicators: bool) -> list[dict]:
    calib = get_impersonation_calibration()
    alone_sev = calib.get("authority_alone_severity", "low")
    escalated_sev = calib.get("authority_escalated_severity", "high")

    severity = escalated_sev if has_request_indicators else alone_sev

    matched = _phrases_in_text(AUTHORITY_KEYWORDS, claimed_identity)
    lowered = claimed_identity.lower()
    matched.extend(
        acronym for acronym in AUTHORITY_ACRONYMS if re.search(rf"\b{acronym}\b", lowered)
    )

    indicators = []
    for keyword in matched:
        desc = (
            f"Claimed identity contains authority keyword '{keyword}' "
            f"(escalated to {severity.upper()} due to accompanying request indicators)."
            if has_request_indicators
            else f"Claimed identity contains authority keyword '{keyword}' (LOW weight without request indicators)."
        )
        indicators.append(
            {
                "type": "authority_identity",
                "value": keyword,
                "severity": severity,
                "description": desc,
            }
        )
    return indicators


def _check_pressure(message: str) -> list[dict]:
    calib = get_impersonation_calibration()
    phrases = tuple(calib.get("request_indicators", {}).get("urgency", PRESSURE_PHRASES))
    matched = _phrases_in_text(phrases, message)
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
    calib = get_impersonation_calibration()
    phrases = tuple(calib.get("request_indicators", {}).get("secrecy", SECRECY_PHRASES))
    matched = _phrases_in_text(phrases, message)
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


def _check_payment_requests(message: str) -> list[dict]:
    calib = get_impersonation_calibration()
    phrases = tuple(calib.get("request_indicators", {}).get("payment_request", ()))
    # Only match if not already matched as an unusual_request
    lowered = message.lower()
    matched = [p for p in phrases if p in lowered and not any(u in p or p in u for u in UNUSUAL_REQUEST_PHRASES if u in lowered)]
    return [
        {
            "type": "payment_request",
            "value": phrase,
            "severity": "medium",
            "description": f"Payment/invoice related phrase '{phrase}' identified in the message.",
        }
        for phrase in matched
    ]


def _check_status_confirmation(message: str) -> list[dict]:
    calib = get_impersonation_calibration()
    phrases = tuple(calib.get("request_indicators", {}).get("status_confirmation", ()))
    matched = _phrases_in_text(phrases, message)
    return [
        {
            "type": "status_confirmation",
            "value": phrase,
            "severity": "medium",
            "description": f"Status confirmation request '{phrase}' found in the message.",
        }
        for phrase in matched
    ]


def _check_channel_change(message: str) -> list[dict]:
    calib = get_impersonation_calibration()
    phrases = tuple(calib.get("request_indicators", {}).get("channel_change", ()))
    matched = _phrases_in_text(phrases, message)
    return [
        {
            "type": "channel_change",
            "value": phrase,
            "severity": "medium",
            "description": f"Communication channel redirection phrase '{phrase}' found in the message.",
        }
        for phrase in matched
    ]


def analyze_impersonation_heuristics(message: str, claimed_identity: str) -> list[dict]:
    """Run all impersonation heuristics and return the indicator list.

    authority_identity alone carries LOW weight. It escalates to HIGH only
    when combined with at least one request-type indicator (payment or status
    confirmation request, urgency, secrecy, channel change).
    """
    request_indicators: list[dict] = []
    request_indicators.extend(_check_pressure(message))
    request_indicators.extend(_check_unusual_requests(message))
    request_indicators.extend(_check_secrecy(message))
    request_indicators.extend(_check_payment_requests(message))
    request_indicators.extend(_check_status_confirmation(message))
    request_indicators.extend(_check_channel_change(message))

    has_requests = len(request_indicators) > 0
    authority_indicators = _check_authority_identity(claimed_identity, has_requests)

    indicators: list[dict] = []
    indicators.extend(authority_indicators)
    indicators.extend(request_indicators)
    return indicators

