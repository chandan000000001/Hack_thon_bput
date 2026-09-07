"""Phishing email heuristic detector (Part 3).

Rule-based only: extracts indicators from the sender address, subject and
body. No ML or LLM logic lives here — the LLM only writes the explanation.
"""

import re
from urllib.parse import urlparse

from app.services.ml_inference import ml_indicator, predict_email

# Known brands and their official registrable domains, used to catch
# look-alike sender domains (e.g. paypa1.com, micr0soft-support.com).
BRAND_OFFICIAL_DOMAINS = {
    "microsoft": {"microsoft.com", "microsoftonline.com", "office.com", "outlook.com", "live.com"},
    "paypal": {"paypal.com"},
    "google": {"google.com", "googlemail.com"},
    "amazon": {"amazon.com"},
    "apple": {"apple.com", "icloud.com"},
    "facebook": {"facebook.com"},
    "netflix": {"netflix.com"},
    "dhl": {"dhl.com"},
    "fedex": {"fedex.com"},
    "hsbc": {"hsbc.com"},
    "wellsfargo": {"wellsfargo.com"},
}

# Leet-tolerant character classes so paypa1/micr0soft-style domains still
# match the brand name.
LEET_CHAR_CLASSES = {
    "o": "[o0]",
    "i": "[i1l!|]",
    "l": "[l1i!|]",
    "e": "[e3]",
    "a": "[a4@]",
    "s": "[s5$]",
    "t": "[t7+]",
    "g": "[g9q]",
    "b": "[b8]",
}


def _brand_pattern(brand: str) -> re.Pattern:
    return re.compile(
        "".join(LEET_CHAR_CLASSES.get(char, re.escape(char)) for char in brand),
        re.IGNORECASE,
    )

URGENCY_KEYWORDS = ("urgent", "immediately", "suspend", "verify")

CREDENTIAL_REQUEST_PHRASES = (
    "verify password",
    "confirm account",
    "confirm your account",
    "update your password",
    "validate your credentials",
    "enter your password",
    "reset your password now",
)

THREAT_LANGUAGE_PHRASES = (
    "account closed",
    "legal action",
    "account will be terminated",
    "account has been compromised",
    "lawsuit",
    "unauthorized activity",
)

SUSPICIOUS_URL_TLDS = {"xyz", "top", "zip", "click", "link", "work", "loan", "cam", "rest"}

URL_IN_BODY_PATTERN = re.compile(r"https?://[^\s\"'<>\)]+", re.IGNORECASE)
IP_HOST_PATTERN = re.compile(r"^https?://\d{1,3}(?:\.\d{1,3}){3}(?:[/:]|$)", re.IGNORECASE)

# --- SMS / message-specific heuristics (Part 8 tuning) ---
# The evaluator runs SMS text through the same body-based analysis, so these
# patterns capture SMS spam vocabulary that email heuristics alone miss.
# 5-6 digit shortcodes ("Txt WIN to 87121") and international/long phone numbers.
SMS_SHORTCODE_PATTERN = re.compile(r"\b\d{5,6}\b")
SMS_PHONE_PATTERN = re.compile(r"(?:\+\d{6,}\b|\b0\d{9,10}\b)")
# SMS spam vocabulary (spec keywords plus common UCI-SMS-style spam words).
SMS_KEYWORD_PATTERN = re.compile(
    r"\b(txt|reply\s+stop|winner|won|win|claim|loan|cash|urgent\s+call|free|prize|"
    r"reward|congrat\w*|selected|subscription|ringtone|charged|voucher|guaranteed|"
    r"exclusive|nokia)\b",
    re.IGNORECASE,
)
# Share of digits among alphanumeric characters above which a short message
# looks like machine-generated spam (shortcodes, amounts, premium numbers).
SMS_DIGIT_RATIO_THRESHOLD = 0.15
SMS_DIGIT_MIN_COUNT = 5
# Four or more consecutive ALL-CAPS words ("WIN A FREE PRIZE TODAY").
SMS_ALL_CAPS_PATTERN = re.compile(r"\b[A-Z]{2,}(?:\s+[A-Z]{2,}){3,}")


def _extract_sender_domain(sender: str) -> str:
    domain = sender.strip().rsplit("@", 1)[-1].lower()
    return domain.strip(">.") if domain else ""


def _registrable_domain(domain: str) -> str:
    """Approximate the registrable domain as the last two labels."""
    labels = [label for label in domain.split(".") if label]
    if len(labels) < 2:
        return domain
    return ".".join(labels[-2:])


def _check_lookalike_domain(sender: str) -> list[dict]:
    domain = _extract_sender_domain(sender)
    if not domain or "." not in domain:
        return []

    registrable = _registrable_domain(domain)
    for brand, official_domains in BRAND_OFFICIAL_DOMAINS.items():
        if (
            registrable not in official_domains
            and _brand_pattern(brand).search(registrable)
        ):
            official = sorted(official_domains)[0]
            return [
                {
                    "type": "lookalike_domain",
                    "value": registrable,
                    "severity": "critical",
                    "description": (
                        f"Sender domain '{registrable}' appears to imitate the "
                        f"official domain '{official}'."
                    ),
                }
            ]
    return []


def _check_urgency(text: str) -> list[dict]:
    lowered = text.lower()
    return [
        {
            "type": "urgency",
            "value": keyword,
            "severity": "high",
            "description": f"Urgency keyword '{keyword}' found in the email.",
        }
        for keyword in URGENCY_KEYWORDS
        if keyword in lowered
    ]


def _check_credential_requests(text: str) -> list[dict]:
    lowered = text.lower()
    return [
        {
            "type": "credential_request",
            "value": phrase,
            "severity": "critical",
            "description": (
                f"Credential request phrase '{phrase}' found; the email asks "
                "the recipient to submit account credentials."
            ),
        }
        for phrase in CREDENTIAL_REQUEST_PHRASES
        if phrase in lowered
    ]


def _check_threat_language(text: str) -> list[dict]:
    lowered = text.lower()
    return [
        {
            "type": "threat_language",
            "value": phrase,
            "severity": "high",
            "description": f"Threat language '{phrase}' found in the email.",
        }
        for phrase in THREAT_LANGUAGE_PHRASES
        if phrase in lowered
    ]


def _check_body_urls(body: str) -> list[dict]:
    indicators: list[dict] = []
    seen_hosts: set[str] = set()
    for url_match in URL_IN_BODY_PATTERN.finditer(body):
        url = url_match.group(0)
        try:
            parsed = urlparse(url)
        except ValueError:
            continue  # malformed URL (e.g. unbalanced brackets) - ignore
        if IP_HOST_PATTERN.match(url):
            indicators.append(
                {
                    "type": "ip_url_in_body",
                    "value": url,
                    "severity": "critical",
                    "description": "Link in the email body points directly to an IP address.",
                }
            )
        parsed = urlparse(url)
        tld = parsed.hostname.rsplit(".", 1)[-1].lower() if parsed.hostname else ""
        if tld in SUSPICIOUS_URL_TLDS:
            indicators.append(
                {
                    "type": "suspicious_tld_in_body",
                    "value": url,
                    "severity": "critical",
                    "description": f"Link in the email body uses the suspicious TLD '.{tld}'.",
                }
            )
        host = parsed.hostname or ""
        if host and host not in seen_hosts:
            seen_hosts.add(host)
            if url.lower().startswith("http://"):
                indicators.append(
                    {
                        "type": "insecure_link",
                        "value": url,
                        "severity": "high",
                        "description": "Link in the email body uses plain HTTP instead of HTTPS.",
                    }
                )
    return indicators


def _check_sms_patterns(text: str) -> list[dict]:
    """SMS/message-specific indicators (shortcodes, spam vocabulary, casing)."""
    indicators: list[dict] = []

    shortcode_match = SMS_SHORTCODE_PATTERN.search(text)
    if shortcode_match:
        shortcodes = sorted(set(SMS_SHORTCODE_PATTERN.findall(text)))
        indicators.append(
            {
                "type": "sms_shortcode",
                "value": ", ".join(shortcodes[:5]),
                "severity": "high",
                "description": (
                    "Message contains 5-6 digit shortcodes "
                    f"({', '.join(shortcodes[:3])}), common in bulk SMS spam and premium-rate scams."
                ),
            }
        )

    phone_match = SMS_PHONE_PATTERN.search(text)
    if phone_match:
        phones = sorted(set(SMS_PHONE_PATTERN.findall(text)))
        indicators.append(
            {
                "type": "sms_phone_number",
                "value": ", ".join(phones[:3]),
                "severity": "high",
                "description": (
                    "Message contains an international or long phone number, "
                    "typical of call-back SMS scams."
                ),
            }
        )

    for keyword in sorted(set(SMS_KEYWORD_PATTERN.findall(text))):
        indicators.append(
            {
                "type": "sms_spam_keyword",
                "value": keyword.lower(),
                "severity": "high",
                "description": (
                    f"SMS spam keyword '{keyword.lower()}' found; bulk messaging "
                    "campaigns repeatedly use this vocabulary."
                ),
            }
        )

    digit_count = sum(char.isdigit() for char in text)
    alpha_count = sum(char.isalpha() for char in text)
    if (
        alpha_count
        and digit_count >= SMS_DIGIT_MIN_COUNT
        and digit_count / alpha_count > SMS_DIGIT_RATIO_THRESHOLD
    ):
        indicators.append(
            {
                "type": "high_digit_ratio",
                "value": f"digit_ratio={digit_count / alpha_count:.2f}",
                "severity": "medium",
                "description": (
                    "Message has an unusually high ratio of digits to letters, "
                    "consistent with shortcodes, amounts and premium numbers."
                ),
            }
        )

    caps_match = SMS_ALL_CAPS_PATTERN.search(text)
    if caps_match:
        indicators.append(
            {
                "type": "all_caps_text",
                "value": caps_match.group(0)[:40],
                "severity": "medium",
                "description": "Message contains four or more consecutive ALL-CAPS words, a common spam emphasis tactic.",
            }
        )

    return indicators


def analyze_email_heuristics(sender: str, subject: str, body: str) -> list[dict]:
    """Run all phishing heuristics and return the indicator list.

    Hybrid mode (ML Step 3): after the heuristic indicators, the trained
    email model scores the combined sender/subject/body; when available the
    ml_model indicator is appended and callers obtain the blended score via
    ml_inference.score_with_ml (0.45 * heuristic + 0.55 * ML).
    """
    indicators: list[dict] = []
    indicators.extend(_check_lookalike_domain(sender))
    indicators.extend(_check_urgency(subject))
    indicators.extend(_check_urgency(body))
    indicators.extend(_check_credential_requests(subject))
    indicators.extend(_check_credential_requests(body))
    indicators.extend(_check_threat_language(subject))
    indicators.extend(_check_threat_language(body))
    indicators.extend(_check_body_urls(body))
    indicators.extend(_check_sms_patterns(body))

    probability = predict_email("\n".join([sender, subject, body]))
    if probability is not None:
        indicators.append(ml_indicator("email_phishing_xgb.pkl", probability))
    return indicators
