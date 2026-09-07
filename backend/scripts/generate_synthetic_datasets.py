"""Generate seeded, deterministic synthetic labelled datasets (Part 8).

Creates (seed=42, fully deterministic):
  datasets/emails/labelled_emails.csv     200 benign + 200 phishing rows
  datasets/auth_logs/labelled_auth_logs.json   60 scenarios (30 normal / 30 attack)
  datasets/network/labelled_network.json       60 scenarios (30 normal / 30 attack)
  datasets/media/labelled_media.json + 20 benign / 20 manipulated images

If datasets/provenance.json flags a public source as "synthetic_fallback"
(URLhaus, Umbrella or UCI SMS failed to download), this script also
generates a synthetic replacement CSV for that category.

Run from the backend directory:
    python scripts/generate_synthetic_datasets.py
"""

import csv
import json
import random
from datetime import datetime, timedelta, timezone
from io import BytesIO
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
DATASETS_DIR = ROOT / "datasets"
PROVENANCE_PATH = DATASETS_DIR / "provenance.json"
SEED = 42
NOW_ISO = datetime.now(timezone.utc).isoformat()

rng = random.Random(SEED)


# ---------------------------------------------------------------------------
# Emails
# ---------------------------------------------------------------------------

BENIGN_SENDERS = [
    "notices@university.edu", "registrar@university.edu", "hr@company.example",
    "receipts@shop.example", "newsletter@news.example", "it-helpdesk@company.example",
    "events@university.edu", "billing@utility.example", "alumni@university.edu",
]
BENIGN_SUBJECTS = [
    "Library hours during exam week", "Seminar: Introduction to Databases",
    "Team meeting moved to Friday", "Your order has shipped",
    "Monthly payment receipt", "Weekly campus newsletter",
    "Office closed on Monday", "Course registration confirmation",
    "Water bill for June available", "Alumni meetup invitation",
]
BENIGN_OPENERS = [
    "Hello,", "Hi there,", "Dear student,", "Dear customer,", "Good morning,",
]
BENIGN_DETAILS = [
    "The central library will remain open until 10 PM during examination week. No action is required from students.",
    "The seminar takes place in Hall B at 3 PM on Thursday. Seats are limited to 80 attendees.",
    "The weekly team meeting has been moved to Friday at 11 AM. The agenda is attached in the shared drive.",
    "Your order #84{n} shipped today and should arrive within five business days. Thank you for your purchase.",
    "Your payment of ${amt}.00 was received on the 3rd. This receipt confirms the settled balance.",
    "Our newsletter this week covers campus sports results, the new cafe opening, and volunteering options.",
    "The office will be closed on Monday for scheduled maintenance. Regular service resumes Tuesday at 9 AM.",
    "Your registration for the autumn term has been confirmed. Timetables are published on the portal.",
    "The water bill for June is now available in your account. The amount is unchanged from May.",
    "You are invited to the alumni meetup on the 24th at the old student union building.",
]
BENIGN_CLOSINGS = [
    "Kind regards, Campus Services", "Regards, The Team", "Thanks, Administration",
    "Best wishes, Support Staff",
]

PHISHING_DOMAINS = [
    "micr0soft-verify.xyz", "paypa1-secure.top", "amaz0n-pay.xyz",
    "appleid-support.top", "netflix-billing.xyz", "company-portal-login.xyz",
]
PHISHING_SENDER_LOCALS = ["security-alert@", "support@", "billing@", "no-reply@", "account-services@"]
PHISHING_SUBJECTS = [
    "URGENT: verify your account immediately",
    "Action required: confirm your account now",
    "Your account will be suspended within 24 hours",
    "Security alert: verify password immediately",
    "Payment declined: update your billing immediately",
    "Unusual activity detected: confirm your account",
]
PHISHING_CREDENTIAL_PHRASES = [
    "verify your password", "confirm your account", "update your password now",
    "enter your password on the secure page",
]
PHISHING_THREAT_PHRASES = [
    "Failure to act will result in your account closed permanently.",
    "Ignoring this notice will lead to legal action against your account.",
    "Your account has been compromised and will be terminated.",
]
PHISHING_URL_TEMPLATES = [
    "http://185.220.101.{o}/login?session={n}",
    "http://secure-login.{domain}/verify?ref={n}",
    "https://{domain}/account/confirm?id={n}",
    "http://45.33.32.{o}/signin/{n}",
]


def build_email_rows() -> list[list[str]]:
    rows = []
    for i in range(200):
        sender = rng.choice(BENIGN_SENDERS)
        subject = rng.choice(BENIGN_SUBJECTS)
        body = (
            f"{rng.choice(BENIGN_OPENERS)}\n\n"
            f"{rng.choice(BENIGN_DETAILS).format(n=i % 100, amt=20 + (i * 7) % 90)}\n\n"
            f"{rng.choice(BENIGN_CLOSINGS)}"
        )
        rows.append(["benign", sender, subject, body])
    for i in range(200):
        domain = rng.choice(PHISHING_DOMAINS)
        sender = rng.choice(PHISHING_SENDER_LOCALS) + domain
        subject = rng.choice(PHISHING_SUBJECTS)
        url = rng.choice(PHISHING_URL_TEMPLATES).format(
            domain=domain, o=i % 250 + 1, n=100000 + i
        )
        body = (
            f"Dear customer,\n\nWe detected unusual activity on your profile. "
            f"You must {rng.choice(PHISHING_CREDENTIAL_PHRASES)} within 24 hours: {url}\n\n"
            f"{rng.choice(PHISHING_THREAT_PHRASES)}\n\nSecurity Team"
        )
        rows.append(["phishing", sender, subject, body])
    return rows


# ---------------------------------------------------------------------------
# Auth logs
# ---------------------------------------------------------------------------

AUTH_USERS = ["alice.j", "bob.k", "carol.m", "dave.p", "erin.r"]
AUTH_LOCATIONS = ["New York, US", "London, UK", "Singapore, SG"]
ATTACK_LOCATION = "Moscow, RU"
KNOWN_DEVICE = "Windows-Chrome"
ATTACK_DEVICE = "Linux-Firefox"


def _auth_ts(base_day: int, hour: int, minute: int) -> str:
    stamp = datetime(2026, 7, 1, hour, minute, tzinfo=timezone.utc) + timedelta(days=base_day)
    return stamp.isoformat().replace("+00:00", "Z")


def build_auth_scenarios() -> list[dict]:
    scenarios = []
    for i in range(30):
        user = AUTH_USERS[i % len(AUTH_USERS)]
        events = []
        for login_index in range(rng.randint(2, 4)):
            events.append(
                {
                    "user": user,
                    "ip": f"10.0.{i % 20}.{20 + login_index}",
                    "location": AUTH_LOCATIONS[i % len(AUTH_LOCATIONS)],
                    "device": KNOWN_DEVICE,
                    "status": "success",
                    "timestamp": _auth_ts(i // 30, 9 + login_index * 2, rng.randint(0, 59)),
                }
            )
        scenarios.append({"label": "benign", "events": events})

    for i in range(30):
        user = AUTH_USERS[i % len(AUTH_USERS)]
        day = i // 30
        template = i % 4
        events = []
        base_hour, base_minute = 9, 0
        if template in (0, 3):  # failed burst + success-after-failures
            for f in range(rng.randint(4, 6)):
                events.append(
                    {
                        "user": user, "ip": f"185.220.101.{7 + f}",
                        "location": ATTACK_LOCATION, "device": ATTACK_DEVICE,
                        "status": "failed",
                        "timestamp": _auth_ts(day, base_hour, base_minute + f * 2),
                    }
                )
        if template in (1, 2, 3):  # impossible travel vs baseline success
            events.append(
                {
                    "user": user, "ip": f"10.0.{i % 20}.9",
                    "location": AUTH_LOCATIONS[i % len(AUTH_LOCATIONS)],
                    "device": KNOWN_DEVICE, "status": "success",
                    "timestamp": _auth_ts(day, base_hour, base_minute),
                }
            )
            events.append(
                {
                    "user": user, "ip": f"185.220.101.{9}",
                    "location": ATTACK_LOCATION, "device": ATTACK_DEVICE,
                    "status": "success",
                    "timestamp": _auth_ts(day, base_hour, base_minute + rng.randint(7, 45)),
                }
            )
        if template in (1, 3):  # failed burst too
            for f in range(4):
                events.append(
                    {
                        "user": user, "ip": f"185.220.101.{7 + f}",
                        "location": ATTACK_LOCATION, "device": ATTACK_DEVICE,
                        "status": "failed",
                        "timestamp": _auth_ts(day, base_hour + 1, base_minute + f * 3),
                    }
                )
        if template in (2, 3):  # success-after-failures tail
            for f in range(3):
                events.append(
                    {
                        "user": user, "ip": f"45.33.32.{10 + f}",
                        "location": ATTACK_LOCATION, "device": ATTACK_DEVICE,
                        "status": "failed",
                        "timestamp": _auth_ts(day, base_hour + 2, base_minute + f),
                    }
                )
            events.append(
                {
                    "user": user, "ip": "45.33.32.10",
                    "location": ATTACK_LOCATION, "device": ATTACK_DEVICE,
                    "status": "success",
                    "timestamp": _auth_ts(day, base_hour + 2, base_minute + 5),
                }
            )
        scenarios.append({"label": "attack", "events": events})
    return scenarios


# ---------------------------------------------------------------------------
# Network / API logs
# ---------------------------------------------------------------------------

def _flow(source: str, dest: str, port: int, bytes_out: int) -> dict:
    return {"source_ip": source, "dest_ip": dest, "port": port, "bytes_out": bytes_out, "protocol": "tcp"}


def _api_log(endpoint: str, method: str, source_ip: str, status_code: int) -> dict:
    return {"endpoint": endpoint, "method": method, "source_ip": source_ip, "status_code": status_code}


def build_network_scenarios() -> list[dict]:
    scenarios = []
    for i in range(30):
        flows = [
            _flow(f"10.0.{i % 20}.{30 + f}", f"93.184.216.{30 + f}", rng.choice([80, 443]),
                  rng.randint(10_000, 900_000))
            for f in range(rng.randint(2, 4))
        ]
        api_logs = [
            _api_log(f"/api/v1/resource/{rng.randint(1, 30)}", rng.choice(["GET", "POST"]),
                     f"172.16.{i % 10}.{10 + k}", rng.choice([200, 200, 200, 404]))
            for k in range(rng.randint(3, 6))
        ]
        scenarios.append({"label": "benign", "flows": flows, "api_logs": api_logs})

    for i in range(30):
        template = i % 4
        attacker_ip = f"185.220.101.{50 + i % 40}"
        flows, api_logs = [], []
        if template in (0, 3):  # C2 / backdoor port
            flows.append(_flow("10.0.4.21", "45.33.49.12", rng.choice([4444, 8888]),
                               rng.randint(500_000, 5_000_000)))
        if template in (0, 1, 2, 3):  # exfiltration-sized transfer
            flows.append(_flow("10.0.7.15", f"104.244.72.{20 + i % 10}", 443,
                               rng.randint(11_000_000, 50_000_000)))
        if template in (1, 3):  # beaconing-like repetition
            beacon_dest = "91.219.237.22"
            for b in range(8):
                flows.append(_flow("10.0.2.8", beacon_dest, 443, 512 + b))
        if template in (0, 2):  # repeated API auth failures
            for k in range(rng.randint(7, 12)):
                api_logs.append(_api_log("/api/v1/auth/token", "POST", attacker_ip, 401))
        if template in (1, 2, 3):  # rate abuse
            for k in range(55):
                api_logs.append(_api_log(f"/api/v1/items/{k}", "GET", attacker_ip, 200))
        scenarios.append({"label": "attack", "flows": flows, "api_logs": api_logs})
    return scenarios


# ---------------------------------------------------------------------------
# Media
# ---------------------------------------------------------------------------

MEDIA_SIZE = 256
PASTE_BOX = (96, 96)
PASTE_SIZE = 64
PASTE_JPEG_QUALITY = 60
RIPPLE_AMPLITUDE = 8
RIPPLE_WAVELENGTH = 24


def build_gradient(seed_offset: int) -> Image.Image:
    import numpy as np

    axis = np.linspace(0, 255, MEDIA_SIZE)
    xx, yy = np.meshgrid(axis, axis)
    shift = (seed_offset * 13) % 40
    ripple = RIPPLE_AMPLITUDE * np.sin((xx + shift) / RIPPLE_WAVELENGTH * 2 * np.pi) * np.sin(
        yy / RIPPLE_WAVELENGTH * 2 * np.pi
    )
    red = np.clip(xx + ripple, 0, 255).astype(np.uint8)
    green = np.clip(yy + ripple, 0, 255).astype(np.uint8)
    blue = np.clip((xx + yy) / 2 + ripple, 0, 255).astype(np.uint8)
    return Image.fromarray(np.dstack([red, green, blue]), "RGB")


def build_media(manifest: list[dict]) -> None:
    media_dir = DATASETS_DIR / "media"
    media_dir.mkdir(parents=True, exist_ok=True)

    for i in range(20):
        path = media_dir / f"benign_{i:02d}.png"
        build_gradient(i).save(path)
        manifest.append(
            {
                "file": str(path.relative_to(ROOT)),
                "label": "benign",
                "method_of_creation": "Programmatic smooth gradient with sinusoidal ripple (Pillow); single PNG save, no compression history.",
            }
        )

    for i in range(20):
        gradient = build_gradient(20 + i)
        region = gradient.crop(
            (PASTE_BOX[0], PASTE_BOX[1], PASTE_BOX[0] + PASTE_SIZE, PASTE_BOX[1] + PASTE_SIZE)
        )
        buffer = BytesIO()
        region.save(buffer, "JPEG", quality=PASTE_JPEG_QUALITY)
        buffer.seek(0)
        manipulated = gradient.copy()
        manipulated.paste(Image.open(buffer).convert("RGB"), PASTE_BOX)
        path = media_dir / f"manipulated_{i:02d}.png"
        manipulated.save(path)
        manifest.append(
            {
                "file": str(path.relative_to(ROOT)),
                "label": "manipulated",
                "method_of_creation": (
                    f"Same gradient with a {PASTE_SIZE}x{PASTE_SIZE} region pasted from a "
                    f"separately JPEG quality-{PASTE_JPEG_QUALITY} recompressed copy (spliced ELA discontinuity)."
                ),
            }
        )


# ---------------------------------------------------------------------------
# Fallback coverage for failed public downloads
# ---------------------------------------------------------------------------

FALLBACK_BENIGN_DOMAINS = [
    "wikipedia.org", "github.com", "university.edu", "shop.example", "news.example",
    "cloudflare.com", "apple.com", "microsoft.com", "amazon.com", "bbc.co.uk",
    "nature.com", "python.org", "mozilla.org", "archive.org", "openstreetmap.org",
]


def build_fallback_urls() -> list[list[str]]:
    rows = []
    for i in range(200):
        domain = FALLBACK_BENIGN_DOMAINS[i % len(FALLBACK_BENIGN_DOMAINS)]
        sub = "" if i % 3 == 0 else rng.choice(["www.", "docs.", "mail.", "cdn."])
        rows.append([f"https://{sub}{domain}/", "benign"])
    for i in range(200):
        domain = rng.choice(PHISHING_DOMAINS)
        url = rng.choice(PHISHING_URL_TEMPLATES).format(domain=domain, o=i % 250 + 1, n=900000 + i)
        rows.append([url, "malicious"])
    return rows


FALLBACK_HAM = [
    "Hey, are we still meeting for lunch tomorrow?",
    "The bus leaves at 7, don't be late.",
    "Thanks for the notes, they really helped.",
    "Can you pick up milk on the way home?",
    "Happy birthday! Have a great day.",
    "I'll call you after the lecture ends.",
    "The movie starts at 8, see you there.",
    "Don't forget your umbrella today.",
]
FALLBACK_SPAM = [
    "URGENT! Your mobile number has won a prize, call now to verify your account",
    "Free entry to win a new phone, text WIN to 80085 immediately",
    "Your account will be suspended, confirm your details at http://185.220.101.9/verify",
    "You have been selected for a cash prize, claim it now at http://prize-claim.xyz/top",
    "Emergency: transfer the payment today to avoid account closure",
    "Congratulations! You won tickets, reply YES immediately",
]


def build_fallback_messages() -> list[list[str]]:
    rows = []
    for i in range(300):
        rows.append(["benign", rng.choice(FALLBACK_HAM) + f" (ref {i})"])
    for i in range(300):
        rows.append(["phishing_like", rng.choice(FALLBACK_SPAM) + f" [{i}]"])
    return rows


def main() -> None:
    (DATASETS_DIR / "emails").mkdir(parents=True, exist_ok=True)
    (DATASETS_DIR / "auth_logs").mkdir(parents=True, exist_ok=True)
    (DATASETS_DIR / "network").mkdir(parents=True, exist_ok=True)
    (DATASETS_DIR / "media").mkdir(parents=True, exist_ok=True)

    email_rows = build_email_rows()
    emails_path = DATASETS_DIR / "emails" / "labelled_emails.csv"
    with emails_path.open("w", newline="", encoding="utf-8") as handle:
        csv.writer(handle).writerows([["label", "sender", "subject", "body"]] + email_rows)

    auth_scenarios = build_auth_scenarios()
    auth_path = DATASETS_DIR / "auth_logs" / "labelled_auth_logs.json"
    auth_path.write_text(json.dumps(auth_scenarios, indent=2) + "\n", encoding="utf-8")

    network_scenarios = build_network_scenarios()
    network_path = DATASETS_DIR / "network" / "labelled_network.json"
    network_path.write_text(json.dumps(network_scenarios, indent=2) + "\n", encoding="utf-8")

    media_manifest: list[dict] = []
    build_media(media_manifest)
    media_path = DATASETS_DIR / "media" / "labelled_media.json"
    media_path.write_text(json.dumps(media_manifest, indent=2) + "\n", encoding="utf-8")

    synthetic_entries = [
        {
            "source": "synthetic_labelled_emails",
            "generator": "scripts/generate_synthetic_datasets.py",
            "seed": SEED,
            "status": "synthetic",
            "rows_written": len(email_rows),
            "licence_note": "Synthetic data generated for this project; contains no real personal data.",
            "created_at": NOW_ISO,
        },
        {
            "source": "synthetic_labelled_auth_logs",
            "generator": "scripts/generate_synthetic_datasets.py",
            "seed": SEED,
            "status": "synthetic",
            "rows_written": len(auth_scenarios),
            "licence_note": "Synthetic data generated for this project; contains no real personal data.",
            "created_at": NOW_ISO,
        },
        {
            "source": "synthetic_labelled_network",
            "generator": "scripts/generate_synthetic_datasets.py",
            "seed": SEED,
            "status": "synthetic",
            "rows_written": len(network_scenarios),
            "licence_note": "Synthetic data generated for this project; contains no real personal data.",
            "created_at": NOW_ISO,
        },
        {
            "source": "synthetic_labelled_media",
            "generator": "scripts/generate_synthetic_datasets.py",
            "seed": SEED,
            "status": "synthetic",
            "rows_written": len(media_manifest),
            "licence_note": "Synthetic images generated with Pillow for this project.",
            "created_at": NOW_ISO,
        },
    ]

    # Cover any public source flagged synthetic_fallback by the fetcher.
    provenance = load_or_init_provenance()
    fallback_sources = {
        e["source"] for e in provenance.get("entries", []) if e.get("status") == "synthetic_fallback"
    }
    if "urlhaus_recent" in fallback_sources or "umbrella_top1m" in fallback_sources:
        url_rows = build_fallback_urls()
        malicious = [r for r in url_rows if r[1] == "malicious"]
        benign = [r for r in url_rows if r[1] == "benign"]
        if "urlhaus_recent" in fallback_sources:
            _write_csv(DATASETS_DIR / "urls" / "malicious_urls.csv", ["url", "label"], malicious)
            synthetic_entries.append(_fallback_entry("synthetic_malicious_urls", len(malicious)))
            print("Covered urlhaus_recent with synthetic malicious URLs.")
        if "umbrella_top1m" in fallback_sources:
            _write_csv(DATASETS_DIR / "urls" / "benign_urls.csv", ["url", "label"], benign)
            synthetic_entries.append(_fallback_entry("synthetic_benign_urls", len(benign)))
            print("Covered umbrella_top1m with synthetic benign URLs.")
    if "sms_spam_uci" in fallback_sources:
        sms_rows = build_fallback_messages()
        _write_csv(DATASETS_DIR / "messages" / "sms_labelled.csv", ["label", "text"], sms_rows)
        synthetic_entries.append(_fallback_entry("synthetic_sms_messages", len(sms_rows)))
        print("Covered sms_spam_uci with synthetic messages.")

    kept = [
        e for e in provenance.get("entries", [])
        if not str(e.get("source", "")).startswith("synthetic")
    ]
    provenance["entries"] = kept + synthetic_entries
    PROVENANCE_PATH.write_text(json.dumps(provenance, indent=2) + "\n", encoding="utf-8")

    print("\n=== Synthetic dataset summary (seed=42) ===")
    for entry in synthetic_entries:
        print(f"{entry['source']:<32} rows/scenarios: {entry['rows_written']}")


def load_or_init_provenance() -> dict:
    if PROVENANCE_PATH.exists():
        try:
            return json.loads(PROVENANCE_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    return {"version": 1, "entries": []}


def _write_csv(path: Path, header: list[str], rows: list[list[str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        csv.writer(handle).writerows([header] + rows)


def _fallback_entry(source: str, rows: int) -> dict:
    return {
        "source": source,
        "generator": "scripts/generate_synthetic_datasets.py",
        "seed": SEED,
        "status": "synthetic",
        "rows_written": rows,
        "licence_note": "Synthetic replacement for a public dataset that failed to download.",
        "created_at": NOW_ISO,
    }


if __name__ == "__main__":
    main()
