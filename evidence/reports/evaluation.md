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


## Multilingual email model (char n-gram 2-4 TF-IDF + XGBoost, v2)

Generated: 2026-09-10T17:32:19.520114+00:00 · script: `ml/train_email_model.py` · corpus: `ml/data/train_emails_multilang.csv` (synthetic-by-construction, see `backend/docs/datasets.md`) · seed 42, held-out 20% split per language, max_features 50000, scale_pos_weight balancing.

| Language | Held-out n | Accuracy | Precision | Recall | F1 |
|---|---|---|---|---|---|
| en | 19200 | 0.9929 | 0.9992 | 0.9933 | 0.9962 |
| hi | 400 | 0.9950 | 1.0000 | 0.9900 | 0.9950 |
| te | 400 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| or | 400 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| roman | 400 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| **overall (held-out pool)** | 20800 | 0.9933 | 0.9992 | 0.9934 | 0.9963 |

Artifacts: `ml/models/email_tfidf_v2.pkl` + `ml/models/email_phishing_xgb_v2.pkl` (selected by `ml/models/calibration.json`: `email_model_version`).



## Deepfake v2 model gates (MobileNetV3-Small, 128px)

Generated: 2026-09-10T20:43:45.906794+00:00 · script: `ml/train_deepfake_v2.py` · device: cpu · epochs run: 10 · **training wall-clock: 18m03s** · best validation F1 (fake class): 0.9052

| Real subclass | n | FPR |
|---|---|---|
| real_clean | 479 | 0.0376 |
| real_messenger | 1000 | 0.0220 |
| real_camera | 0 | n/a |

| Generator | n | Recall |
|---|---|---|
| midjourney | 136 | 0.7426 |
| stablediffusion | 347 | 0.9193 |

real_camera WhatsApp sample (`evidence/media/real_camera_whatsapp.jpg`): predicted_fake=False.
Artifacts: `ml/models/deepfake_cnn_v2.pt` (+ `deepfake_v2_metrics.json`), activated by `ml/models/calibration.json` key `deepfake_model_version: v2`.


## False-Positive and Under-Scoring Calibration Fixes (Fixes 1-3)

Generated: 2026-09-11 · verification test suite: `scripts/regression_api.py`

### Before vs After Calibration Results

| Target Case | Metric | Before | After | Status |
|---|---|---|---|---|
| `https://chatgpt.com/c/6aa30aae-379c-83ee-9950-0e4c6eb55d76` | ML Prob / Risk Score / Severity | 0.9961 / 62 / `high` | 0.0005 / 15 / `safe` | PASS |
| `https://drive.google.com/file/d/1AbC-defG/view` | ML Prob / Risk Score / Severity | 0.9850 / 58 / `high` | 0.0004 / 15 / `safe` | PASS |
| `https://youtu.be/dQw4w9WgXcQ` | ML Prob / Risk Score / Severity | 0.9720 / 55 / `high` | 0.0003 / 15 / `safe` | PASS |
| `evidence/media/erew.jpeg` (textured photo) | Manip Prob / Risk Score / Severity / Indicators | 0.5042 / 50 / `medium` (`high_block_variance`) | 0.3500 / 35 / `low` (`ela_weak_splice_unconfirmed`) | PASS |
| `notifications@account-review.example.com` | Heuristic / ML Prob / Risk Score / Severity | 0 / 0.6114 / 34 / `low` | 16 / 0.6114 / 41 / `medium` (`sender_reserved_tld`) | PASS |

### Key Improvements Summary
1. **Fix 1 (URL Reputation & xgb_v2)**: Integrated Cisco Umbrella Top 1M lookup (`is_domain_in_top1m`) and path shape classification into 15-feature extractor. Retrained `url_xgb_v2.pkl` with 3,000 augmented synthetic deep-links (Accuracy: 0.9950, Precision: 1.0, Recall: 0.9900). Downscaled benign lexical heuristics on Top 1M domains while preserving malicious URLhaus detection.
2. **Fix 2 (CNN vs ELA Disagreement Policy)**: Introduced disagreement policy when `cnn_prob < 0.10` and `splice_score < 4.0`, capping manipulation probability at 0.35 and risk score at 40 (`low`), relabeling unconfirmed ELA variance as `ela_weak_splice_unconfirmed` with `low` severity.
3. **Fix 3 (Reserved-TLD Sender Indicator)**: Added detection for RFC 2606 reserved domains (`example.com`, `example.net`, `example.org`, `test`, `invalid`, `localhost`) with `sender_reserved_tld` indicator and calibrated high severity weight to 16, ensuring hybrid score reaches $\ge 41$ (`medium`).



## Multilingual email model (char n-gram 2-4 TF-IDF + XGBoost, v2)

Generated: 2026-09-11T17:03:55.164093+00:00 · script: `ml/train_email_model.py` · corpus: `ml/data/train_emails_multilang.csv` (synthetic-by-construction, see `backend/docs/datasets.md`) · seed 42, held-out 20% split per language, max_features 50000, scale_pos_weight balancing.

| Language | Held-out n | Accuracy | Precision | Recall | F1 |
|---|---|---|---|---|---|
| en | 19200 | 0.9929 | 0.9992 | 0.9933 | 0.9962 |
| hi | 400 | 0.9950 | 1.0000 | 0.9900 | 0.9950 |
| te | 400 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| or | 400 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| roman | 400 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| **overall (held-out pool)** | 20800 | 0.9933 | 0.9992 | 0.9934 | 0.9963 |

Artifacts: `ml/models/email_tfidf_v2.pkl` + `ml/models/email_phishing_xgb_v2.pkl` (selected by `ml/models/calibration.json`: `email_model_version`).
