"""Train the CYBERGUARD ML models (ML Step 2).

Trains the text/flow models from the preprocessed splits in ml/data/ (produced by
ml/preprocess.py) and saves the weights to ml/models/:

  1. email_phishing_xgb.pkl + email_tfidf.pkl  (TF-IDF + XGBoost, imbalance-aware)
  2. url_xgb.pkl                               (handcrafted URL features + XGBoost)
  3. (deepfake retired — see ml/train_deepfake_v2.py for the served model)
  4. network_xgb.pkl                           (scaled KDD features + XGBoost, binary)

Usage (from the backend directory):
    python ml/train_models.py [--max-emails 50000]
"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))  # backend/ on sys.path for every launch style

import argparse
import math
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

import joblib
import numpy as np
import pandas as pd

ML_DIR = Path(__file__).resolve().parent
DATA_DIR = ML_DIR / "data"
MODELS_DIR = ML_DIR / "models"
SEED = 42

SUSPICIOUS_URL_TLDS = {"xyz", "top", "zip", "ru", "cn", "tk", "click", "link", "work", "loan", "cam", "rest"}


def evaluate_predictions(y_true, y_pred) -> dict:
    from sklearn.metrics import accuracy_score, f1_score, precision_score, recall_score

    return {
        "accuracy": round(float(accuracy_score(y_true, y_pred)), 4),
        "precision": round(float(precision_score(y_true, y_pred, zero_division=0)), 4),
        "recall": round(float(recall_score(y_true, y_pred, zero_division=0)), 4),
        "f1": round(float(f1_score(y_true, y_pred, zero_division=0)), 4),
    }


def warn_missing(path: Path) -> None:
    print(f"WARNING: {path.name} not found — skipping this model (was ml/preprocess.py run?)")


# ---------------------------------------------------------------------------
# 1. NLP email phishing model (TF-IDF + XGBoost, imbalance-aware)
# ---------------------------------------------------------------------------

def train_email_model(max_emails: int) -> dict:
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.model_selection import train_test_split
    from xgboost import XGBClassifier

    train = pd.read_csv(DATA_DIR / "train_emails.csv").dropna()
    if len(train) > max_emails:
        train, _ = train_test_split(
            train, train_size=max_emails, random_state=SEED, stratify=train["label"]
        )
    test = pd.read_csv(DATA_DIR / "test_emails.csv").dropna()
    print(f"  emails: training on {len(train)} rows (sampled from the full split)")

    vectorizer = TfidfVectorizer(max_features=50000, stop_words="english")
    X_train = vectorizer.fit_transform(train["clean_text"])
    y_train = train["label"].astype(int)

    # The public dataset is heavily skewed towards phishing; XGBoost's
    # scale_pos_weight re-balances the gradient contributions per class.
    n_benign = int((y_train == 0).sum())
    n_phishing = int((y_train == 1).sum())
    scale_pos_weight = n_benign / n_phishing if n_phishing else 1.0
    print(f"  class balance: benign={n_benign} phishing={n_phishing} -> scale_pos_weight={scale_pos_weight:.4f}")

    model = XGBClassifier(
        n_estimators=200,
        max_depth=6,
        learning_rate=0.1,
        scale_pos_weight=scale_pos_weight,
        eval_metric="logloss",
        tree_method="hist",
        n_jobs=-1,
        random_state=SEED,
    )
    model.fit(X_train, y_train)

    X_test = vectorizer.transform(test["clean_text"])
    metrics = evaluate_predictions(test["label"].astype(int), model.predict(X_test))

    joblib.dump(vectorizer, MODELS_DIR / "email_tfidf.pkl")
    joblib.dump(model, MODELS_DIR / "email_phishing_xgb.pkl")
    return metrics


# ---------------------------------------------------------------------------
# 2. URL malicious model (handcrafted features + XGBoost)
# ---------------------------------------------------------------------------

def shannon_entropy(value: str) -> float:
    if not value:
        return 0.0
    counts = {}
    for char in value:
        counts[char] = counts.get(char, 0) + 1
    total = len(value)
    return -sum((count / total) * math.log2(count / total) for count in counts.values())


def extract_url_features(url: str, version: str = "v2") -> np.ndarray:
    """Feature vector:
    Base (8): [length, entropy, digit_ratio, has_ip, has_at_symbol,
               suspicious_tld, http_only, num_subdomains].
    v2 additions (7): domain_in_top1m, path_shape_cat, is_uuid_like,
                      is_hex32_like, is_short_id, is_homepage, is_other.
    """
    try:
        parsed = urlparse(url)
    except ValueError:
        parsed = urlparse(f"http://{url}")
    host = parsed.hostname or ""
    scheme = parsed.scheme

    digits = sum(char.isdigit() for char in url)
    alnum = sum(char.isalnum() for char in url)
    digit_ratio = digits / alnum if alnum else 0.0

    is_ip = bool(host) and host.replace(".", "").isdigit() and host.count(".") == 3
    tld = host.rsplit(".", 1)[-1].lower() if "." in host else ""
    subdomains = max(0, len([part for part in host.split(".") if part]) - 2)

    base = [
        len(url),
        shannon_entropy(url),
        digit_ratio,
        1.0 if is_ip else 0.0,
        1.0 if "@" in url else 0.0,
        1.0 if tld in SUSPICIOUS_URL_TLDS else 0.0,
        1.0 if scheme == "http" else 0.0,
        float(subdomains),
    ]
    if version == "v1":
        return np.array(base, dtype=np.float64)

    from app.core.url_reputation import is_domain_in_top1m, classify_path_shape, path_shape_to_vector
    in_top1m = 1.0 if is_domain_in_top1m(host) else 0.0
    shape = classify_path_shape(parsed.path, parsed.query)
    shape_vec = path_shape_to_vector(shape)

    return np.array(base + [in_top1m] + shape_vec, dtype=np.float64)


def train_url_model() -> dict:
    from xgboost import XGBClassifier

    train = pd.read_csv(DATA_DIR / "train_urls.csv").dropna()
    test = pd.read_csv(DATA_DIR / "test_urls.csv").dropna()
    print(f"  urls: training on {len(train)} rows")

    X_train = np.vstack(train["url"].map(lambda u: extract_url_features(u, version="v2")))
    y_train = (train["label"] == "malicious").astype(int)
    X_test = np.vstack(test["url"].map(lambda u: extract_url_features(u, version="v2")))
    y_test = (test["label"] == "malicious").astype(int)

    model = XGBClassifier(
        n_estimators=200,
        max_depth=4,
        learning_rate=0.1,
        eval_metric="logloss",
        tree_method="hist",
        n_jobs=-1,
        random_state=SEED,
    )
    model.fit(X_train, y_train)
    metrics = evaluate_predictions(y_test, model.predict(X_test))

    joblib.dump(model, MODELS_DIR / "url_xgb_v2.pkl")
    return metrics


# ---------------------------------------------------------------------------
# 3. Deepfake image model — REMOVED
# ---------------------------------------------------------------------------
# The 32x32 CIFAKE CNN (deepfake_cnn.pt) is retired: the served deepfake model
# is the 128px MobileNetV3-Small trained by ml/train_deepfake_v2.py on the
# GenImage + messenger-degraded corpus (ml/models/deepfake_cnn_v2.pt).


# ---------------------------------------------------------------------------
# 4. Network anomaly model (binary normal vs attack, XGBoost)
# ---------------------------------------------------------------------------

def train_network_model() -> dict:
    from xgboost import XGBClassifier

    train = pd.read_csv(DATA_DIR / "train_network.csv")
    test = pd.read_csv(DATA_DIR / "test_network.csv")
    print(f"  network: training on {len(train)} rows")

    scaler = joblib.load(MODELS_DIR / "network_scaler.pkl")
    print(f"  loaded fitted StandardScaler ({scaler.n_features_in_} features) from ml/models/network_scaler.pkl")

    y_train = (train["label"] != "normal").astype(int)
    y_test = (test["label"] != "normal").astype(int)
    X_train = train.drop(columns=["label"])
    X_test = test.drop(columns=["label"])

    model = XGBClassifier(
        n_estimators=200,
        max_depth=6,
        learning_rate=0.1,
        eval_metric="logloss",
        tree_method="hist",
        n_jobs=-1,
        random_state=SEED,
    )
    model.fit(X_train, y_train)
    metrics = evaluate_predictions(y_test, model.predict(X_test))

    joblib.dump(model, MODELS_DIR / "network_xgb.pkl")
    return metrics


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description="Train CYBERGUARD ML models")
    parser.add_argument("--max-emails", type=int, default=50000, help="max email rows to train on (default: 50000)")
    args = parser.parse_args()

    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    jobs = [
        ("email_phishing", lambda: train_email_model(args.max_emails), "email_phishing_xgb.pkl + email_tfidf.pkl"),
        ("url_malicious", train_url_model, "url_xgb.pkl"),
        ("network_anomaly", train_network_model, "network_xgb.pkl"),
    ]

    results = []
    for name, runner, artifact in jobs:
        print(f"\n=== Training {name} ===")
        started = time.time()
        try:
            metrics = runner()
            results.append((name, artifact, metrics, time.time() - started))
        except Exception as exc:
            print(f"  WARNING: {name} training failed, skipping: {exc}")

    print("\n" + "=" * 78)
    print("TRAINING SUMMARY")
    print("=" * 78)
    print(f"{'model':<18}{'artifact(s)':<38}{'acc':>8}{'prec':>8}{'rec':>8}{'f1':>8}{'secs':>8}")
    print("-" * 78)
    for name, artifact, metrics, seconds in results:
        print(
            f"{name:<18}{artifact:<38}{metrics['accuracy']:>8.4f}{metrics['precision']:>8.4f}"
            f"{metrics['recall']:>8.4f}{metrics['f1']:>8.4f}{seconds:>8.1f}"
        )
    print("=" * 78)
    print(f"Model weights saved to {MODELS_DIR.relative_to(ML_DIR.parents[1])}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
