"""Fetch public labelled datasets for CYBERGUARD evaluation (Part 8).

Downloads (60s timeout, 3 retries each):
  1. URLhaus recent CSV           -> datasets/urls/malicious_urls.csv
  2. Cisco Umbrella top-1m        -> datasets/urls/benign_urls.csv
  3. UCI SMS Spam Collection      -> datasets/messages/sms_labelled.csv

Every outcome (fetched or failed) is recorded in datasets/provenance.json.
Failures never crash the script; failed sources are flagged with
status "synthetic_fallback" so generate_synthetic_datasets.py can cover
that category instead. Run from the backend directory:
    python scripts/fetch_datasets.py
"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))  # backend/ on sys.path for every launch style

import csv
import hashlib
import io
import json
import sys
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[2]
DATASETS_DIR = ROOT / "datasets"
PROVENANCE_PATH = DATASETS_DIR / "provenance.json"

TIMEOUT_SECONDS = 60
RETRIES = 3
MAX_URLHAUS_ROWS = 500
MAX_UMBRELLA_ROWS = 500
MAX_SMS_ROWS = 600

USER_AGENT = "CYBERGUARD-dataset-fetch/1.0 (security research prototype)"

SOURCES = {
    "urlhaus_recent": {
        "url": "https://urlhaus.abuse.ch/downloads/csv_recent/",
        "licence_note": "URLhaus database by abuse.ch, licensed CC0 1.0.",
    },
    "umbrella_top1m": {
        "url": "http://s3-us-west-1.amazonaws.com/umbrella-static/top-1m.csv.zip",
        "licence_note": "Cisco Umbrella Top 1M list; free to use with attribution to Cisco Umbrella.",
    },
    "sms_spam_uci": {
        "url": "https://archive.ics.uci.edu/static/public/228/sms+spam+collection.zip",
        "licence_note": "SMS Spam Collection v.1 (Almeida et al.), CC BY 4.0, distributed via the UCI Machine Learning Repository.",
    },
}


def fetch(url: str) -> bytes | None:
    """Download a URL with timeout and retries. Returns None on failure."""
    request = Request(url, headers={"User-Agent": USER_AGENT})
    for attempt in range(1, RETRIES + 1):
        try:
            with urlopen(request, timeout=TIMEOUT_SECONDS) as response:
                return response.read()
        except Exception as exc:
            print(f"  WARNING: attempt {attempt}/{RETRIES} failed for {url}: {exc}")
            if attempt < RETRIES:
                time.sleep(2 * attempt)
    return None


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_csv(path: Path, rows: list[list[str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        csv.writer(handle).writerows(rows)


def parse_urlhaus(raw: bytes) -> list[list[str]]:
    """URLhaus csv_recent: comment lines start with '#'; the 'url' column holds the link."""
    text = raw.decode("utf-8", errors="replace")
    lines = [line for line in text.splitlines() if line and not line.startswith("#")]
    rows = list(csv.reader(lines))
    if not rows:
        return []
    url_index = None
    for index, row in enumerate(rows[:3]):
        if "url" in [cell.strip().lower() for cell in row]:
            url_index = [cell.strip().lower() for cell in row].index("url")
            rows = rows[index + 1:]
            break
    if url_index is None:
        url_index = 2  # documented URLhaus layout: id, timecreated, url, ...
    parsed = []
    for row in rows:
        if len(row) > url_index and row[url_index].strip().startswith("http"):
            parsed.append([row[url_index].strip(), "malicious"])
        if len(parsed) >= MAX_URLHAUS_ROWS:
            break
    return parsed


def parse_umbrella(raw: bytes) -> list[list[str]]:
    """Umbrella top-1m zip: rank,domain per line; first 500 domains as benign URLs."""
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        with archive.open("top-1m.csv") as member:
            text = member.read().decode("utf-8", errors="replace")
    parsed = []
    for line in text.splitlines():
        domain = line.strip().split(",")[-1].strip()
        if domain:
            parsed.append([f"https://{domain}/", "benign"])
        if len(parsed) >= MAX_UMBRELLA_ROWS:
            break
    return parsed


def parse_sms(raw: bytes) -> list[list[str]]:
    """UCI SMS Spam Collection zip: SMSSpamCollection, tab-separated label<TAB>text."""
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        with archive.open("SMSSpamCollection") as member:
            text = member.read().decode("utf-8", errors="replace")
    spam_rows = []
    ham_rows = []
    for line in text.splitlines():
        parts = line.split("\t", 1)
        if len(parts) != 2:
            continue
        label, message = parts[0].strip(), parts[1].strip()
        if not message:
            continue
        mapped = "phishing_like" if label == "spam" else "benign"
        (spam_rows if mapped == "phishing_like" else ham_rows).append([mapped, message])
    # Balanced cap as available: up to half the budget from each class.
    half = MAX_SMS_ROWS // 2
    picked = spam_rows[:half] + ham_rows[:half]
    remainder = (spam_rows + ham_rows)[len(picked):]
    return (picked + remainder)[:MAX_SMS_ROWS]


def load_provenance() -> dict:
    if PROVENANCE_PATH.exists():
        try:
            return json.loads(PROVENANCE_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            print("  WARNING: provenance.json unreadable; starting a fresh file.")
    return {"version": 1, "entries": []}


def main() -> None:
    (DATASETS_DIR / "urls").mkdir(parents=True, exist_ok=True)
    (DATASETS_DIR / "messages").mkdir(parents=True, exist_ok=True)

    outputs = {
        "urlhaus_recent": (DATASETS_DIR / "urls" / "malicious_urls.csv", parse_urlhaus),
        "umbrella_top1m": (DATASETS_DIR / "urls" / "benign_urls.csv", parse_umbrella),
        "sms_spam_uci": (DATASETS_DIR / "messages" / "sms_labelled.csv", parse_sms),
    }

    fresh_entries = []
    for name, spec in SOURCES.items():
        print(f"Fetching {name} from {spec['url']} ...")
        raw = fetch(spec["url"])
        entry = {
            "source": name,
            "url": spec["url"],
            "licence_note": spec["licence_note"],
            "fetched_at": now_iso(),
        }
        target_path, parser = outputs[name]
        rows = []
        if raw is None:
            entry["status"] = "synthetic_fallback"
            entry["error"] = "download failed after retries"
            print(f"  FAILED after {RETRIES} attempts. Marked synthetic_fallback: "
                  f"run generate_synthetic_datasets.py to cover this category.")
        else:
            entry["sha256"] = sha256_hex(raw)
            rows = parser(raw)
            if not rows:
                entry["status"] = "synthetic_fallback"
                entry["error"] = "downloaded but no rows could be parsed"
                print("  WARNING: parsed 0 rows; marked synthetic_fallback.")
            else:
                entry["status"] = "fetched"
                entry["rows_written"] = len(rows)
                header = ["label", "text"] if name == "sms_spam_uci" else ["url", "label"]
                write_csv(target_path, [header] + rows)
                print(f"  OK: {len(rows)} rows -> {target_path.relative_to(ROOT)}")

        fresh_entries.append(entry)

    provenance = load_provenance()
    replaced = {entry["source"] for entry in fresh_entries}
    kept = [e for e in provenance.get("entries", []) if e.get("source") not in replaced]
    provenance["entries"] = kept + fresh_entries
    PROVENANCE_PATH.write_text(json.dumps(provenance, indent=2) + "\n", encoding="utf-8")

    print("\n=== Fetch summary ===")
    print(f"{'source':<18} {'status':<20} {'rows':>6}")
    print("-" * 46)
    for entry in fresh_entries:
        rows = entry.get("rows_written", 0)
        print(f"{entry['source']:<18} {entry['status']:<20} {rows:>6}")
    fallbacks = [e["source"] for e in fresh_entries if e["status"] == "synthetic_fallback"]
    if fallbacks:
        print(f"\nFallback flagged: {', '.join(fallbacks)}")
        print("Run scripts/generate_synthetic_datasets.py to cover the missing categories.")


if __name__ == "__main__":
    sys.exit(main())
