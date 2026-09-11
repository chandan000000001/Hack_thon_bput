"""URL reputation and structural analysis service (Fix 1).

Provides high-reputation domain lookup backed by the Cisco Umbrella top-1M list
(ml/data/url_whitelist/top1m.txt) and structural path shape classification to
prevent false positives on legitimate deep links (e.g. chatgpt.com/c/<uuid>,
drive.google.com, and youtube links).
"""

import logging
import re
from pathlib import Path

logger = logging.getLogger("cyberguard.url_reputation")

_BACKEND_DIR = Path(__file__).resolve().parents[2]
TOP1M_PATH = _BACKEND_DIR / "ml" / "data" / "url_whitelist" / "top1m.txt"

# Standard ccTLD second-level public suffixes (e.g. .co.uk, .com.au, .co.in)
MULTI_PART_SECOND_LEVELS = {
    "co", "com", "org", "net", "gov", "edu", "ac", "ne", "or",
    "gen", "firm", "ind", "nic", "mil",
}

# Regex patterns for path shapes
UUID_PATTERN = re.compile(
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
)
HEX32_PATTERN = re.compile(r"(?:\b|/)[0-9a-fA-F]{32}(?:\b|/|$)")
HEX16_PATTERN = re.compile(r"(?:\b|/)[0-9a-fA-F]{16}(?:\b|/|$)")
SHORT_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_-]{6,32}$")
VIDEO_ID_PARAM_PATTERN = re.compile(r"(?:^|&)(?:v|id)=([a-zA-Z0-9_-]{6,32})")

PATH_SHAPE_CATEGORIES = ("uuid-like", "hex32-like", "short-id", "homepage", "other")

_TOP1M_SET: set[str] | None = None


def get_registrable_domain(domain: str) -> str:
    """Extract registrable domain (e.g. chatgpt.com, bbc.co.uk) handling ccTLDs."""
    domain = domain.strip().lower().rstrip(".")
    if ":" in domain:
        domain = domain.split(":", 1)[0]
    parts = [p for p in domain.split(".") if p]
    if len(parts) <= 2:
        return domain
    # Check multi-part ccTLDs: 2-letter last part + known second-level
    if len(parts[-1]) == 2 and parts[-2] in MULTI_PART_SECOND_LEVELS:
        return ".".join(parts[-3:])
    return ".".join(parts[-2:])


def _load_top1m_set() -> set[str]:
    global _TOP1M_SET
    if _TOP1M_SET is not None:
        return _TOP1M_SET
    domains = set()
    if TOP1M_PATH.exists():
        try:
            with TOP1M_PATH.open("r", encoding="utf-8") as f:
                for line in f:
                    dom = line.strip().lower()
                    if dom:
                        domains.add(dom)
            logger.info("Loaded %d domains from %s", len(domains), TOP1M_PATH)
        except Exception as exc:
            logger.warning("Failed to load top1m.txt: %s", exc)
    else:
        logger.warning("Top-1M list not found at %s", TOP1M_PATH)
    # Ensure standard major high-reputation domains are always recognized
    domains.update({"chatgpt.com", "openai.com", "google.com", "youtube.com", "youtu.be", "wikipedia.org"})
    _TOP1M_SET = domains
    return _TOP1M_SET


def is_domain_in_top1m(domain: str) -> bool:
    """Check whether domain or its registrable domain exists in Umbrella top-1M."""
    if not domain:
        return False
    domain = domain.strip().lower().rstrip(".")
    if ":" in domain:
        domain = domain.split(":", 1)[0]
    top_set = _load_top1m_set()
    if domain in top_set:
        return True
    registrable = get_registrable_domain(domain)
    return registrable in top_set


def classify_path_shape(path: str, query: str = "") -> str:
    """Classify the structural pattern of the URL path/query.

    Returns one of: 'uuid-like', 'hex32-like', 'short-id', 'homepage', 'other'.
    """
    clean_path = path.strip()
    clean_query = query.strip()

    # 1. Homepage
    if clean_path in ("", "/", "/index.html", "/index.htm", "/index.php") and not clean_query:
        return "homepage"

    # 2. UUID-like (e.g. /c/6aa30aae-379c-83ee-9950-0e4c6eb55d76)
    if UUID_PATTERN.search(clean_path) or UUID_PATTERN.search(clean_query):
        return "uuid-like"

    # 3. Hex32-like (e.g. /d/6aa30aae379c83ee99500e4c6eb55d76)
    if HEX32_PATTERN.search(clean_path) or HEX32_PATTERN.search(clean_query):
        return "hex32-like"

    # 4. Short-ID (e.g. /watch?v=dQw4w9WgXcQ, /file/d/1AbC-defG/view, /p/hex16, /share/token, /dQw4w9WgXcQ)
    if VIDEO_ID_PARAM_PATTERN.search(clean_query):
        return "short-id"

    if HEX16_PATTERN.search(clean_path):
        return "short-id"

    segments = [s for s in clean_path.strip("/").split("/") if s]
    if len(segments) == 1 and SHORT_ID_PATTERN.match(segments[0]):
        return "short-id"

    if any(s in ("c", "d", "p", "v", "share", "file", "view") for s in segments):
        for s in segments:
            if SHORT_ID_PATTERN.match(s) and s not in ("c", "d", "p", "v", "share", "file", "view"):
                return "short-id"

    # Fallback to other
    return "other"


def path_shape_to_vector(shape: str) -> list[float]:
    """Encode path shape as categorical index followed by 5 one-hot floats."""
    idx = PATH_SHAPE_CATEGORIES.index(shape) if shape in PATH_SHAPE_CATEGORIES else 4
    one_hot = [1.0 if s == shape else 0.0 for s in PATH_SHAPE_CATEGORIES]
    return [float(idx)] + one_hot
