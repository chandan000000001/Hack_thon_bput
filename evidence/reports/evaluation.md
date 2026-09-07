# CYBERGUARD Evaluation Report

Generated: 2026-09-07T22:27:31.991184+00:00
Git commit: 73f03fafa85b663570484414571e53fb2e137bb9

## Thresholds and blending

- Heuristic modules: **flagged** when `risk_score >= 41`.
- Media forensics: flagged when `manipulation_probability >= 0.5`.
- Hybrid blending: `hybrid_score = round(0.45 * heuristic_score + 0.55 * ml_probability * 100)`.
- **URL metrics computed on held-out split to avoid train/test overlap.** Email and network ML metrics are likewise computed on held-out splits produced by `ml/preprocess.py`; the deepfake module uses a deterministic sample of the held-out image test split.

## Datasets

| Module | Path | Provenance status |
|---|---|---|
| email | `backend/ml/data/test_emails.csv` | unknown |
| url | `backend/ml/data/test_urls.csv` | unknown |
| message | `datasets/messages/sms_labelled.csv` | unknown |
| account_takeover | `datasets/auth_logs/labelled_auth_logs.json` | unknown |
| network | `datasets/network/labelled_network.json` | unknown |
| deepfake_image | `backend/ml/data/image_manifest.csv` | unknown |

## Per-module metrics — Heuristics-only

| Module | n | Positives | Flagged | TP | FP | TN | FN | Accuracy | Precision | Recall | F1 | FPR | FNR | Mean ms | P95 ms |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| email_phishing | 24000 | 22638 | 461 | 309 | 152 | 1210 | 22329 | 0.0633 | 0.6703 | 0.0136 | 0.0268 | 0.1116 | 0.9864 | 0.155 | 0.175 |
| url | 200 | 100 | 85 | 85 | 0 | 100 | 15 | 0.925 | 1.0 | 0.85 | 0.9189 | 0.0 | 0.15 | 0.031 | 0.045 |
| message | 600 | 300 | 137 | 137 | 0 | 300 | 163 | 0.7283 | 1.0 | 0.4567 | 0.627 | 0.0 | 0.5433 | 0.046 | 0.085 |
| account_takeover | 60 | 30 | 22 | 22 | 0 | 30 | 8 | 0.8667 | 1.0 | 0.7333 | 0.8462 | 0.0 | 0.2667 | 0.02 | 0.031 |
| network | 60 | 30 | 22 | 22 | 0 | 30 | 8 | 0.8667 | 1.0 | 0.7333 | 0.8462 | 0.0 | 0.2667 | 0.018 | 0.029 |
| deepfake_image | 1000 | 500 | 1000 | 500 | 500 | 0 | 0 | 0.5 | 0.5 | 1.0 | 0.6667 | 1.0 | 0.0 | 1.41 | 2.808 |
| **Macro average** | | | | | | | | 0.6583 | 0.8617 | 0.6311 | 0.6553 | 0.1853 | 0.3688 | | |

## Per-module metrics — Hybrid (heuristics + trained ML)

| Module | n | Positives | Flagged | TP | FP | TN | FN | Accuracy | Precision | Recall | F1 | FPR | FNR | Mean ms | P95 ms |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| email_phishing | 24000 | 22638 | 22243 | 22086 | 157 | 1205 | 552 | 0.9705 | 0.9929 | 0.9756 | 0.9842 | 0.1153 | 0.0244 | 2.278 | 8.07 |
| url | 200 | 100 | 100 | 100 | 0 | 100 | 0 | 1.0 | 1.0 | 1.0 | 1.0 | 0.0 | 0.0 | 0.972 | 3.735 |
| message | 600 | 300 | 160 | 157 | 3 | 297 | 143 | 0.7567 | 0.9812 | 0.5233 | 0.6826 | 0.01 | 0.4767 | 1.45 | 4.946 |
| account_takeover | 60 | 30 | 22 | 22 | 0 | 30 | 8 | 0.8667 | 1.0 | 0.7333 | 0.8462 | 0.0 | 0.2667 | 0.02 | 0.031 |
| network | 60 | 30 | 24 | 22 | 2 | 28 | 8 | 0.8333 | 0.9167 | 0.7333 | 0.8148 | 0.0667 | 0.2667 | 11.641 | 33.949 |
| deepfake_image | 1000 | 500 | 1000 | 500 | 500 | 0 | 0 | 0.5 | 0.5 | 1.0 | 0.6667 | 1.0 | 0.0 | 5.111 | 2.422 |
| **Macro average** | | | | | | | | 0.8212 | 0.8985 | 0.8276 | 0.8324 | 0.1987 | 0.1724 | | |

account_takeover has no trained model yet; its hybrid row equals the heuristics-only row.

## ML artifact hashes (SHA-256)

| Artifact | SHA-256 |
|---|---|
| `ml/models/email_tfidf.pkl` | 43e287df596c4fedfe801385ff5339e6aba24b856cbd4bc14e1aad10e1531f12 |
| `ml/models/email_phishing_xgb.pkl` | f899c5126b8aaca262a5eb0a341ba4518d24e72f3288ae564bc658870d07f32e |
| `ml/models/url_xgb.pkl` | 44a31d78d871415d08bdf711f25f95e0bff88df3af611b4981c4a9a19810e06d |
| `ml/models/deepfake_cnn.pt` | bb202e2fe8a6a01d34390533554e82cf98b009533040f5df353afacc48a1ebcf |
| `ml/models/network_xgb.pkl` | 39dd3d33e7cccaedd98dcb7e0b051c0c6d7a1a62afd3c3eaaf844ca162f40bc4 |
| `ml/models/network_scaler.pkl` | 29bd792998528ee3e5a5b5cbf5ec2dddb0197ff786ec309b5c6e1226791dbf1a |

## Limitations

- The message module evaluates **SMS spam as a proxy** for social-engineering text; classic SMS spam only partially overlaps with phishing heuristics.
- The deepfake evaluation uses a deterministic sample (max 1000 images) of the held-out CIFAKE test split; the CNN was trained on 32x32 CIFAKE images, so metrics do not transfer to high-resolution photos.
- The network model is trained on **KDD99 (1998 DARPA IDS evaluation)** — decades-old traffic patterns; the hybrid flow mapping uses documented constants for duration and response bytes (flows carry neither).
- Latency covers only local detector + ML inference in a single process; no network, storage or LLM time is included.
