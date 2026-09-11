"""Augment URL training data with synthetic benign deep-links (Fix 1).

Generates ~3,000 benign deep-links combining sampled Cisco Umbrella top-1M domains
with common share/content path templates (/c/<uuid>, /d/<hex32>, /watch?v=<id>,
/share/<token>, /p/<hex16>, /file/d/<id>/view).
"""

import csv
import random
import secrets
import uuid
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = BACKEND_DIR / "ml" / "data"
TOP1M_PATH = DATA_DIR / "url_whitelist" / "top1m.txt"
TRAIN_URLS_PATH = DATA_DIR / "train_urls.csv"

SEED = 42


def generate_synthetic_benign_urls(count: int = 3000) -> list[list[str]]:
    random.seed(SEED)
    domains: list[str] = []
    if TOP1M_PATH.exists():
        with TOP1M_PATH.open("r", encoding="utf-8") as f:
            for line in f:
                d = line.strip().lower()
                if d:
                    domains.append(d)
                if len(domains) >= 50000:
                    break

    key_domains = [
        "chatgpt.com", "openai.com", "google.com", "youtube.com", "youtu.be",
        "drive.google.com", "github.com", "notion.so", "zoom.us", "slack.com",
        "figma.com", "canva.com", "dropbox.com", "medium.com", "nytimes.com",
        "bbc.co.uk", "wikipedia.org", "amazon.com", "microsoft.com", "apple.com",
        "linkedin.com", "reddit.com", "spotify.com",
    ]

    pool = key_domains * 25 + (domains if domains else key_domains)

    templates = [
        lambda d: f"https://{d}/c/{uuid.uuid4()}",
        lambda d: f"https://{d}/d/{secrets.token_hex(16)}",
        lambda d: f"https://{d}/watch?v={secrets.token_urlsafe(8)[:11]}",
        lambda d: f"https://{d}/share/{secrets.token_urlsafe(16)}",
        lambda d: f"https://{d}/p/{secrets.token_hex(8)}",
        lambda d: f"https://{d}/file/d/{secrets.token_urlsafe(16)}/view",
    ]

    rows = [
        ["https://chatgpt.com/c/6aa30aae-379c-83ee-9950-0e4c6eb55d76", "benign"],
        ["https://drive.google.com/file/d/1AbC-defG/view", "benign"],
        ["https://youtu.be/dQw4w9WgXcQ", "benign"],
    ]

    while len(rows) < count:
        dom = random.choice(pool)
        tmpl = random.choice(templates)
        rows.append([tmpl(dom), "benign"])

    return rows


def augment_train_urls() -> int:
    # Read existing original dataset
    original_rows: list[list[str]] = []
    if TRAIN_URLS_PATH.exists():
        with TRAIN_URLS_PATH.open("r", newline="", encoding="utf-8") as f:
            reader = csv.reader(f)
            header = next(reader, ["url", "label"])
            for row in reader:
                if len(row) >= 2:
                    original_rows.append(row[:2])

    # Keep original 801 rows (before augmentation)
    # The original dataset has 801 data rows (400 benign homepages + 401 malicious)
    base_rows = [r for r in original_rows if not any(k in r[0] for k in ("/c/", "/watch?v=", "/share/", "/file/d/"))]
    if len(base_rows) < 400:  # Fallback if filtering was too aggressive
        base_rows = original_rows[:801]

    synthetic = generate_synthetic_benign_urls(3000)
    all_rows = base_rows + synthetic

    with TRAIN_URLS_PATH.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["url", "label"])
        writer.writerows(all_rows)

    print(f"Augmented train_urls.csv: {len(base_rows)} base + {len(synthetic)} synthetic = {len(all_rows)} total rows")
    return len(all_rows)


if __name__ == "__main__":
    augment_train_urls()
