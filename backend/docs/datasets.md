# CYBERGUARD Datasets

Labelled datasets used by the offline evaluation harness (`scripts/evaluate.py`). All files live under `datasets/` at the project root; every download and every synthetic set is recorded in `datasets/provenance.json` (source URL, SHA-256 of the raw download, row counts, timestamps, licence notes, and a per-source status of `fetched`, `synthetic_fallback` or `synthetic`).

## Dataset inventory

| Name | Path | Source / generator | Licence / simulated status | Rows | Label semantics | Known caveats |
|---|---|---|---|---|---|---|
| Malicious URLs | `datasets/urls/malicious_urls.csv` | URLhaus recent CSV (`urlhaus.abuse.ch`, first 500 rows) | CC0 1.0 — real, public threat feed | ≤ 500 | `malicious` | Live-malware distribution links; point-in-time snapshot; URLs are often short-lived infrastructure. Falls back to synthetic if the download fails. |
| Benign URLs | `datasets/urls/benign_urls.csv` | Cisco Umbrella top-1m zip (first 500 domains, rewritten as `https://<domain>/`) | Free to use with attribution to Cisco Umbrella | ≤ 500 | `benign` | Popularity is not the same as safety; top domains are infrastructure-heavy (CDNs) and can trigger weak lexical heuristics such as length/entropy. |
| SMS messages | `datasets/messages/sms_labelled.csv` | UCI SMS Spam Collection (`SMSSpamCollection`, balanced cap of 600) | CC BY 4.0 (Almeida et al.), via UCI ML Repository | ≤ 600 | `phishing_like` (spam) / `benign` (ham) | SMS spam is a **proxy** for social-engineering text; classic prize/lottery spam only partially overlaps with phishing heuristics. |
| Labelled emails | `datasets/emails/labelled_emails.csv` | `scripts/generate_synthetic_datasets.py` (seed 42) | Simulated — labelled by construction | 400 (200 benign / 200 phishing) | `benign` / `phishing` | Templates vary but are drawn from a fixed pool; no real personal data. |
| Auth-log scenarios | `datasets/auth_logs/labelled_auth_logs.json` | `scripts/generate_synthetic_datasets.py` (seed 42) | Simulated — labelled by construction | 60 scenarios (30 normal / 30 attack) | `benign` / `attack` per scenario | Each scenario is a list of login events (`user`, `ip`, `location`, `device`, `status`, `timestamp`); attack scenarios combine failed bursts, impossible travel, unknown devices and success-after-failures. |
| Network scenarios | `datasets/network/labelled_network.json` | `scripts/generate_synthetic_datasets.py` (seed 42) | Simulated — labelled by construction | 60 scenarios (30 normal / 30 attack) | `benign` / `attack` per scenario | Attack scenarios combine C2 ports (4444/8888), >10 MB outbound transfers, beaconing-like repetition, 401 bursts and rate abuse. |
| Media images | `datasets/media/labelled_media.json` + PNGs | `scripts/generate_synthetic_datasets.py` (seed 42, Pillow) | Simulated — labelled by construction | 40 images (20 benign / 20 manipulated) | `benign` / `manipulated` | Smooth gradient images with a subtle ripple; manipulated files splice a JPEG quality-60 recompressed 64×64 region. Calibrated for the ELA heuristic, not representative of natural photos. |

`datasets/provenance.json` is the single source of truth for what was fetched vs generated. A source whose download failed after 3 retries is recorded with `status: synthetic_fallback`, and `generate_synthetic_datasets.py` then produces a synthetic replacement CSV for that category (recorded with `status: synthetic`).

## Ground truth construction

- **Malicious URLs (URLhaus):** URLhaus is a curated abuse.ch feed of URLs observed distributing malware. Every row written to `malicious_urls.csv` carries `label=malicious` directly from the feed — this is treated as authoritative malicious ground truth for the URL detector. Caveat: it represents *malware distribution*, which is a superset of phishing; some URLs may not trip phishing-oriented lexical heuristics.
- **Benign URLs (Cisco Umbrella):** the Umbrella top-1m list ranks the most-queried domains on the internet. The first 500 domains are treated as authoritative benign ground truth (`label=benign`). Caveat: popularity implies trustworthiness only statistically; a handful of CDN/redirector domains may legitimately look "suspicious" to lexical analysis.
- **Synthetic sets:** emails, auth-log scenarios, network scenarios and media images are labelled **by construction** — the generator script writes benign samples without any attack indicators and attack samples with specific, enumerated detection signals (lookalike domains, credential phrases, impossible travel, C2 ports, spliced JPEG regions, …). Ground truth is therefore exact by definition, and measured recall reflects whether the detectors catch the signals they were designed for.
- **SMS labels:** the UCI SMS Spam Collection is human-labelled `spam`/`ham`. `spam` maps to `phishing_like` because much SMS spam is socially engineered, but it is a proxy label, not a true phishing annotation (see caveats above).

## Reproduction

All commands run from the `backend/` directory with the project venv:

```bash
# 1. Download the public datasets (~2 MB total). Requires internet access.
#    Failures are non-fatal and recorded as synthetic_fallback.
python scripts/fetch_datasets.py

# 2. Generate the synthetic datasets (seed 42, deterministic) and cover any
#    fallback categories flagged in provenance.json.
python scripts/generate_synthetic_datasets.py

# 3. Run the offline evaluation (no network, no LLM calls). Writes
#    evidence/reports/evaluation.md and evaluation.json.
python scripts/evaluate.py
```

Because the synthetic generators are seeded (`random.Random(42)`) and the public downloads are content-addressed (SHA-256 recorded in `provenance.json`), re-running the pipeline reproduces the same evaluation inputs. The evaluation metrics themselves depend only on the committed detector code.
