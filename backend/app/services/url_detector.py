"""URL heuristic detector (Part 3).

Lexical/rule-based analysis of a single URL. No ML or LLM logic here.
"""

import math
from collections import Counter
from urllib.parse import urlparse

from app.services.ml_inference import ml_indicator, predict_url

BRAND_NAMES = (
    "microsoft",
    "paypal",
    "google",
    "amazon",
    "apple",
    "facebook",
    "netflix",
    "office365",
    "outlook",
    "dhl",
    "fedex",
    "hsbc",
)

SUSPICIOUS_TLDS = {"xyz", "top", "zip", "click", "link", "work", "loan", "cam", "rest"}

SUSPICIOUS_PATH_KEYWORDS = ("login", "verify", "secure", "signin", "sign-in", "update", "account")

MAX_NORMAL_URL_LENGTH = 75
ENTROPY_THRESHOLD = 4.0

# --- URLhaus-informed indicators (Part 8 tuning) ---
# Executable/script/payload file extensions observed in malware distribution
# URLs (spec list first, plus common payload/binary extensions seen in
# URLhaus campaigns).
EXECUTABLE_OR_PAYLOAD_EXTENSIONS = {
    "exe", "zip", "scr", "php", "js", "html",
    "vbs", "hta", "bat", "cmd", "ps1", "sh", "bin", "apk", "jar", "msi", "dll",
    "ppc", "mips", "mipsel", "arm", "sh4", "m68k", "i586", "x32", "x64", "sparc",
}
# TLDs frequently abused by URLhaus campaigns; combined with a long path this
# is a strong distribution-page signature.
URLHAUS_SUSPICIOUS_TLDS = {"ru", "cn", "top", "xyz"}
URLHAUS_MIN_PATH_LENGTH = 20
# A path segment this long with mixed letters/digits and high entropy looks
# machine-generated (e.g. /x7f9a2b/malware.exe).
RANDOM_SEGMENT_MIN_LENGTH = 10
RANDOM_SEGMENT_ENTROPY_THRESHOLD = 3.0
# Digit share of alphanumeric characters in host+path above which the URL
# looks machine-generated (IP hosts always trip this).
EXCESSIVE_DIGIT_RATIO = 0.3
EXCESSIVE_DIGIT_MIN_COUNT = 5


def _shannon_entropy(value: str) -> float:
    if not value:
        return 0.0
    counts = Counter(value)
    length = len(value)
    return -sum((count / length) * math.log2(count / length) for count in counts.values())


def _parse_url(url: str) -> urlparse.ParseResult:
    try:
        parsed = urlparse(url)
    except ValueError:
        try:
            parsed = urlparse(f"http://{url}")
        except ValueError:
            parsed = urlparse("http://invalid/")  # unparseable URL: fall back to defaults
    if not parsed.scheme:
        try:
            parsed = urlparse(f"http://{url}")
        except ValueError:
            parsed = urlparse("http://invalid/")
    return parsed


def _check_ip_host(host: str) -> list[dict]:
    labels = host.split(".")
    if (
        len(labels) == 4
        and all(label.isdigit() and 0 <= int(label) <= 255 for label in labels)
        and host != ""
    ):
        return [
            {
                "type": "ip_host",
                "value": host,
                "severity": "critical",
                "description": "The URL uses a raw IP address instead of a domain name.",
            }
        ]
    return []


def _check_length_and_entropy(url: str) -> list[dict]:
    indicators: list[dict] = []
    if len(url) > MAX_NORMAL_URL_LENGTH:
        indicators.append(
            {
                "type": "url_length",
                "value": str(len(url)),
                "severity": "medium",
                "description": f"URL is unusually long ({len(url)} characters, threshold {MAX_NORMAL_URL_LENGTH}).",
            }
        )
    entropy = _shannon_entropy(url)
    if entropy > ENTROPY_THRESHOLD:
        indicators.append(
            {
                "type": "url_entropy",
                "value": f"{entropy:.2f}",
                "severity": "medium",
                "description": f"URL character entropy is high ({entropy:.2f}, threshold {ENTROPY_THRESHOLD}), suggesting randomized text.",
            }
        )
    return indicators


def _check_tld(host: str) -> list[dict]:
    tld = host.rsplit(".", 1)[-1].lower() if "." in host else ""
    if tld in SUSPICIOUS_TLDS:
        return [
            {
                "type": "suspicious_tld",
                "value": f".{tld}",
                "severity": "high",
                "description": f"The URL uses the suspicious TLD '.{tld}'.",
            }
        ]
    return []


def _check_brand_in_subdomain(host: str) -> list[dict]:
    labels = [label for label in host.lower().split(".") if label]
    if len(labels) < 3:
        return []
    registrable = ".".join(labels[-2:])
    subdomain_part = ".".join(labels[:-2])
    for brand in BRAND_NAMES:
        if brand in subdomain_part and brand not in registrable:
            return [
                {
                    "type": "brand_in_subdomain",
                    "value": host,
                    "severity": "critical",
                    "description": (
                        f"Trusted brand '{brand}' appears in the subdomain but the "
                        f"actual registrable domain is '{registrable}'."
                    ),
                }
            ]
    return []


def _check_scheme(scheme: str) -> list[dict]:
    if scheme == "http":
        return [
            {
                "type": "insecure_scheme",
                "value": "http",
                "severity": "high",
                "description": "The URL uses plain HTTP instead of HTTPS.",
            }
        ]
    return []


def _check_path_keywords(path: str) -> list[dict]:
    lowered = path.lower()
    matched = [keyword for keyword in SUSPICIOUS_PATH_KEYWORDS if keyword in lowered]
    if matched:
        return [
            {
                "type": "suspicious_path_keyword",
                "value": ", ".join(matched),
                "severity": "medium",
                "description": f"URL path contains credential-harvesting keywords: {', '.join(matched)}.",
            }
        ]
    return []


def _path_extension(path: str) -> str:
    last_segment = path.rstrip("/").rsplit("/", 1)[-1]
    if "." not in last_segment:
        return ""
    return last_segment.rsplit(".", 1)[-1].lower()


def _check_executable_extension(path: str) -> list[dict]:
    extension = _path_extension(path)
    if extension and extension in EXECUTABLE_OR_PAYLOAD_EXTENSIONS:
        return [
            {
                "type": "executable_extension",
                "value": f".{extension}",
                "severity": "high",
                "description": (
                    f"The URL path serves an executable, script or payload file "
                    f"(.{extension}), typical of malware distribution pages."
                ),
            }
        ]
    return []


def _check_random_path_segments(path: str) -> list[dict]:
    for segment in path.split("/"):
        segment = segment.strip()
        if len(segment) < RANDOM_SEGMENT_MIN_LENGTH:
            continue
        letters = sum(char.isalpha() for char in segment)
        digits = sum(char.isdigit() for char in segment)
        if letters == 0 or digits == 0:
            continue
        if _shannon_entropy(segment) > RANDOM_SEGMENT_ENTROPY_THRESHOLD:
            return [
                {
                    "type": "random_path_segment",
                    "value": segment,
                    "severity": "medium",
                    "description": (
                        f"Path segment '{segment}' looks machine-generated "
                        "(high entropy, mixed letters and digits)."
                    ),
                }
            ]
    return []


def _check_excessive_digits(host: str, path: str) -> list[dict]:
    text = host + path
    digit_count = sum(char.isdigit() for char in text)
    alpha_count = sum(char.isalpha() for char in text)
    if digit_count >= EXCESSIVE_DIGIT_MIN_COUNT and alpha_count and digit_count / (digit_count + alpha_count) > EXCESSIVE_DIGIT_RATIO:
        return [
            {
                "type": "excessive_digits",
                "value": f"digit_ratio={digit_count / (digit_count + alpha_count):.2f}",
                "severity": "medium",
                "description": (
                    "The URL host/path contains an excessive proportion of digits, "
                    "typical of machine-generated malware distribution links."
                ),
            }
        ]
    return []


def _check_urlhaus_pattern(host: str, path: str) -> list[dict]:
    tld = host.rsplit(".", 1)[-1].lower() if "." in host else ""
    if tld in URLHAUS_SUSPICIOUS_TLDS and len(path) > URLHAUS_MIN_PATH_LENGTH:
        return [
            {
                "type": "urlhaus_pattern",
                "value": f".{tld} TLD with {len(path)}-character path",
                "severity": "high",
                "description": (
                    f"Abused TLD '.{tld}' combined with a long path matches the "
                    "URLhaus malware-distribution URL pattern."
                ),
            }
        ]
    return []


def analyze_url_heuristics(url: str) -> list[dict]:
    """Run all URL heuristics and return the indicator list.

    Hybrid mode (ML Step 3): the trained URL model scores the URL after the
    heuristic indicators; when available the ml_model indicator is appended
    and callers obtain the blended score via ml_inference.score_with_ml.
    """
    parsed = _parse_url(url)
    host = (parsed.hostname or "").lower()

    indicators: list[dict] = []
    indicators.extend(_check_ip_host(host))
    indicators.extend(_check_length_and_entropy(url))
    indicators.extend(_check_tld(host))
    indicators.extend(_check_brand_in_subdomain(host))
    indicators.extend(_check_scheme(parsed.scheme))
    indicators.extend(_check_path_keywords(parsed.path))
    indicators.extend(_check_executable_extension(parsed.path))
    indicators.extend(_check_random_path_segments(parsed.path))
    indicators.extend(_check_excessive_digits(host, parsed.path))
    indicators.extend(_check_urlhaus_pattern(host, parsed.path))

    probability = predict_url(url)
    if probability is not None:
        # Safety principle: ML may raise but never lower the heuristic
        # verdict (monotonic blending — see ml_inference.blend_scores).
        indicators.append(ml_indicator("url_xgb.pkl", probability))
    return indicators
