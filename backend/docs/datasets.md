# CYBERGUARD Datasets

Two dataset layers feed CYBERGUARD:

1. **Detection-evaluation datasets** (`datasets/` at the project root) — labelled by `scripts/evaluate.py` to score the six detection modules. Every download and synthetic set is recorded in `datasets/provenance.json` (source URL, SHA-256 of the raw download, row counts, timestamps, licence notes, and a per-source `status` of `fetched` or `synthetic`).
2. **ML training datasets** (`backend/ml/data/`) — downloaded/derived by `ml/fetch_data.py` and split by `ml/preprocess.py` into the train/test CSVs used by `ml/train_models.py` and referenced by the evaluation report.

## 1. Detection-evaluation datasets (`datasets/provenance.json`)

Provenance file version 1, fetched 2026-09-07. The table below mirrors every entry exactly:

| Source | Path | Source / generator | Licence / status | Rows written | Labels | Caveats |
|---|---|---|---|---|---|---|
| `urlhaus_recent` | `datasets/urls/malicious_urls.csv` | URLhaus recent CSV — `https://urlhaus.abuse.ch/downloads/csv_recent/` (sha256 `a36ef105…`) | **CC0 1.0** — real, public threat feed (`fetched`) | 500 | `malicious` | Live-malware distribution links (a superset of phishing); point-in-time snapshot of often short-lived infrastructure. |
| `umbrella_top1m` | `datasets/urls/benign_urls.csv` | Cisco Umbrella top-1m zip — first 500 domains rewritten as `https://<domain>/` (sha256 `ec57cbbf…`) | Free to use with attribution to Cisco Umbrella (`fetched`) | 500 | `benign` | Popularity ≠ safety; infrastructure-heavy CDN domains can trip weak lexical heuristics (length/entropy). |
| `sms_spam_uci` | `datasets/messages/sms_labelled.csv` | UCI SMS Spam Collection (`sms+spam+collection.zip`, sha256 `1587ea43…`) | **CC BY 4.0** (Almeida et al.), via UCI ML Repository (`fetched`) | 600 | `phishing_like` (spam) / `benign` (ham) | SMS spam is a **proxy** for social-engineering text; classic prize/lottery spam only partially overlaps with phishing heuristics. |
| `synthetic_labelled_emails` | `datasets/emails/labelled_emails.csv` | `scripts/generate_synthetic_datasets.py`, seed 42 | **Simulated** — labelled by construction; no real personal data (`synthetic`) | 400 (200 benign / 200 phishing) | `benign` / `phishing` | Templates drawn from a fixed pool. |
| `synthetic_labelled_auth_logs` | `datasets/auth_logs/labelled_auth_logs.json` | `scripts/generate_synthetic_datasets.py`, seed 42 | **Simulated** — labelled by construction (`synthetic`) | 60 scenarios (30 normal / 30 attack) | `benign` / `attack` per scenario | Each scenario is a list of login events (`user`, `ip`, `location`, `device`, `status`, `timestamp`); attacks combine failed bursts, impossible travel, unknown devices, success-after-failures. |
| `synthetic_labelled_network` | `datasets/network/labelled_network.json` | `scripts/generate_synthetic_datasets.py`, seed 42 | **Simulated** — labelled by construction (`synthetic`) | 60 scenarios (30 normal / 30 attack) | `benign` / `attack` per scenario | Attacks combine C2 ports (4444/8888), >10 MB outbound transfers, beaconing-like repetition, 401 bursts, rate abuse. |
| `synthetic_labelled_media` | `datasets/media/labelled_media.json` + PNGs | `scripts/generate_synthetic_datasets.py`, seed 42 (Pillow) | **Simulated** — synthetic images (`synthetic`) | 40 images (20 benign / 20 manipulated) | `benign` / `manipulated` | Smooth gradient images with a subtle ripple; manipulated files splice a JPEG quality-60 recompressed 64×64 region. Calibrated for the ELA heuristic, not representative of natural photos. |

`provenance.json` is the single source of truth for what was fetched vs generated. If a download fails after retries it is recorded with `status: synthetic_fallback` and the generator produces a synthetic replacement (recorded as `status: synthetic`); in the committed provenance all four fetches succeeded and the three labelled sets are synthetic by design.

## 2. ML training / evaluation splits (`backend/ml/data/`)

Produced by `ml/fetch_data.py` (download) and `ml/preprocess.py` (dedupe, sampling, 80/20 split); consumed by `ml/train_models.py` and by the evaluation report's held-out metric pass.

| Module | Raw source | Licence / origin | Files (rows on disk) | Label semantics |
|---|---|---|---|---|
| email | Hugging Face `cybersectony/PhishingEmailDetectionv2.0` — `raw_emails.csv` (232,809) → sampled to 120,000 | Public HF dataset; the gated `pirocheto/phishing-email` was skipped | `train_emails.csv` (95,996) / `test_emails.csv` (24,000) | 0 benign, 1 phishing/fraud (~94% phishing; balanced via `scale_pos_weight`) |
| url | 500 URLhaus malicious + 500 Umbrella benign | CC0 1.0 / Cisco Umbrella attribution | `train_urls.csv` (800) / `test_urls.csv` (200) | 1 malicious, 0 benign |
| deepfake_image | CIFAKE via the accessible mirror `dragonintelligence/CIFAKE-image-dataset` (train split) | Public research dataset (CIFAR-10 photos vs AI-generated fakes) | `image_manifest.csv` (100,000) + `images/train/{real,fake}` (40,000 + 40,000) and `images/test/{real,fake}` (10,000 + 10,000) | `real` (CIFAR-10 photo) vs `fake` (AI-generated); ImageFolder order: 0='fake', 1='real' |
| network | `sklearn.datasets.fetch_kddcup99(subset="SF")` — 1998 DARPA IDS evaluation | Public research dataset | `raw_network.csv` (73,237) → `train_network.csv` (58,589) / `test_network.csv` (14,648) | binary: normal vs any attack; features f0–f3 (log-duration, service, log-src_bytes, log-dst_bytes) |

The evaluation report computes **URL metrics on the held-out test split** to avoid train/test overlap; email and network ML metrics likewise use held-out splits; the deepfake module uses a deterministic sample (max 1000 images) of the held-out test split.

## 3. Multilingual Indic corpus (`backend/ml/data/train_emails_multilang.csv`)

**Synthetic-by-construction.** No large public Indic phishing corpus exists (Hinglish/Telugu/Odia phishing text is not available as a labelled public dataset in the scale of the English corpora above), so the multilingual training corpus is generated entirely by `ml/build_indic_corpus.py` from templates and the keyword resource — it contains no real personal data and no scraped messages.

| Property | Value |
|---|---|
| Generator | `ml/build_indic_corpus.py` (deterministic, seed 42) |
| Keyword resource | `ml/indic_keywords.json` — urgency / credential / payment / OTP / KYC phrases, ≥ 25 entries per language |
| Languages | `en` (all 95,996 existing rows from `train_emails.csv`), `hi` (Devanagari), `te` (Telugu), `or` (Odia), `roman` (romanised Hinglish/Tenglish) |
| Rows per Indic language | 1,000 phishing + 1,000 benign (slot-filled from 10 phishing + 10 benign templates per language) |
| Variations | synonym swap, name/amount/date/OTP randomisation, script mixing (Indic script with Latin digits, brand names and URLs) |
| Optional augmentation | `--llm-augment` paraphrases a seeded subset of phishing rows offline through the LLM gateway (batched, cached via `explanation_cache`; no request-time LLM usage) |
| Output columns | `clean_text`, `label` (1 phishing / 0 benign), `lang` |

The v2 email model (`ml/models/email_tfidf_v2.pkl` + `email_phishing_xgb_v2.pkl`, character n-gram 2–4 TF-IDF + XGBoost, selected by `ml/models/calibration.json`) trains on this corpus; its per-language held-out metrics are appended to [`evidence/reports/evaluation.md`](../../../evidence/reports/evaluation.md). Caveat: templates come from fixed pools, so measured per-language metrics reflect detector performance on this synthetic distribution, not on real-world Indic phishing campaigns; benign templates are transactional/service mail, so domain shift on other benign genres is expected.

## 4. Deepfake v2 data (`backend/ml/data/genimage/`)

Built by `ml/fetch_genimage.py` (download) and `ml/degrade_messenger.py` (messenger subclass); recorded in `ml/data/genimage/provenance.json` + `manifest.csv`. Per-class download is capped at 20000 images; the counts below are what the mirror yielded within the shard budget actually fetched.

| Subclass | Source / generator | Licence / status | Rows | Label semantics | Caveats |
|---|---|---|---|---|---|
| `real_clean` | GenImage benchmark (HF mirror `nebula/GenImage-arrow`) — the ImageNet-derived **real** subset bundled with every generator shard | **CC BY-NC-SA 4.0** (`fetched`) | 4,790 | 0 (real) | Real photographs; research-only licence. |
| `stablediffusion` | GenImage — Stable Diffusion v1.4 generator subset (same mirror) | **CC BY-NC-SA 4.0** (`fetched`) | 3,474 | 1 (fake) | AI-generated images. |
| `midjourney` | GenImage — Midjourney generator subset (same mirror) | **CC BY-NC-SA 4.0** (`fetched`) | 1,360 | 1 (fake) | AI-generated images. |
| `real_messenger` | `ml/degrade_messenger.py` from `real_clean` (seed 42) | **Simulated** — messenger degradation of real photos | 10,000 | 0 (real) | Longest side ≤ 1600 px, JPEG quality 70–85 random, EXIF stripped, optional mild sharpening — the encoding WhatsApp/Telegram apply to genuine photos. |
| `real_camera` | User-contributed files in `datasets/media/real_camera/` | Contributor-provided | 0 at last build | 0 (real) | Evaluation-only split; contributors must use **non-sensitive personal images** (see `datasets/media/real_camera/README.txt`). |
| WhatsApp sample | `evidence/media/real_camera_whatsapp.jpg` — one genuine photo in messenger encoding (500×421, q78, EXIF stripped) | Derived from `real_clean` | 1 | 0 (real) | Used by the API regression suite and always included in the real_camera gate. |

**Fallback:** if the GenImage download fails entirely, `fetch_genimage.py` records the failure in `provenance.json` and builds the manifest from the existing **CIFAKE** split (`ml/data/images/`), which is kept untouched as the fallback and as v1's training data. Per-generator failures are tolerated individually (a failed generator is recorded and skipped; CIFAKE fallback only triggers when no generator yielded images).

**Synthetic-by-construction note:** the real_messenger subclass is produced by programmatic degradation (resize/JPEG/EXIF strip), not by actually sending photos through messenger apps — it models their encoding pipeline rather than being collected from one. Provenance file: `ml/data/genimage/provenance.json` (HF repo, per-generator status, row counts, cap, timestamps).

The v2 deepfake model (`ml/models/deepfake_cnn_v2.pt`, MobileNetV3-Small at 128 px, selected by `ml/models/calibration.json` key `deepfake_model_version`) trains on real = real_clean + real_messenger vs fake = all generator subclasses; its per-subclass FPR / per-generator recall tables are appended to [`evidence/reports/evaluation.md`](../../../evidence/reports/evaluation.md).

## 5. URL Whitelist & Deep-link Augmentation (`backend/ml/data/url_whitelist/top1m.txt`)

Fetched from Cisco Umbrella static export (`http://s3-us-west-1.amazonaws.com/umbrella-static/top-1m.csv.zip`) containing 1,000,000 top-queried internet domains:
- **Location on disk:** `backend/ml/data/url_whitelist/top1m.txt` (1,000,000 domain names, one per line, lowercase).
- **Lookup module:** `backend/app/core/url_reputation.py` provides multi-part ccTLD extraction (`get_registrable_domain`) and high-reputation domain checks (`is_domain_in_top1m`).
- **Deep-link Augmentation:** `ml/augment_urls.py` generates 3,000 benign deep-links combining sampled high-reputation domains with popular share and resource path patterns (`/c/<uuid>`, `/d/<hex32>`, `/watch?v=<id>`, `/share/<token>`, `/p/<hex16>`, `/file/d/<id>/view`). Added to `ml/data/train_urls.csv` (3,800 total rows) to train `ml/models/url_xgb_v2.pkl`.

## Ground truth construction

- **Malicious URLs (URLhaus):** every row carries `label=malicious` directly from the curated abuse.ch feed — authoritative for malware distribution, a superset of phishing.
- **Benign URLs (Cisco Umbrella):** the first 500 top-queried domains are treated as authoritative `benign`; popularity implies trustworthiness only statistically.
- **Synthetic sets:** emails, auth-log scenarios, network scenarios and media images are labelled **by construction** — benign samples contain no attack indicators; attack samples enumerate specific detection signals (lookalike domains, credential phrases, impossible travel, C2 ports, spliced JPEG regions, …). Measured recall therefore reflects whether the detectors catch the signals they were designed for.
- **SMS labels:** human-labelled `spam`/`ham`; `spam` maps to `phishing_like` — a proxy, not a true phishing annotation.
- **CIFAKE / KDD99 labels:** dataset-provided; see [`docs/models.md`](models.md) for their caveats (32×32 resolution; 1998 traffic).

## Reproduction

All commands run from the `backend/` directory with the project venv:

```bash
# 1. Download the public evaluation datasets (~2 MB). Failures are non-fatal
#    and recorded as synthetic_fallback in provenance.json.
python scripts/fetch_datasets.py

# 2. Generate the synthetic datasets (seed 42, deterministic).
python scripts/generate_synthetic_datasets.py

# 3. Run the offline evaluation (no network, no LLM calls). Writes
#    evidence/reports/evaluation.md and evaluation.json.
python scripts/evaluate.py
```

ML training data is fetched separately by `python ml/fetch_data.py`, then split with `ml/preprocess.py` and trained with `ml/train_models.py` (artifacts land in `ml/models/`; their SHA-256 hashes are recorded in the evaluation report). Because the synthetic generators are seeded (`random.Random(42)`) and the public downloads are content-addressed (SHA-256 recorded in `provenance.json`), re-running the pipeline reproduces the same evaluation inputs.
