"""Train the v2 multilingual email phishing model (char n-gram TF-IDF + XGBoost).

Replaces the v1 word-level TF-IDF with character n-grams (2-4): character
n-grams handle Indic scripts (Devanagari, Telugu, Odia) and romanised
Hinglish/Tenglish without any transliteration or request-time translation.

Training data: ml/data/train_emails_multilang.csv (built by
ml/build_indic_corpus.py) — existing English rows plus 1000 phishing + 1000
benign rows per Indic language. A stratified 80/20 split is drawn per language
(seed 42); the model trains on the combined training pools and is evaluated
per language on the held-out 20%.

Outputs (ml/models/): email_tfidf_v2.pkl, email_phishing_xgb_v2.pkl.
The per-language table is printed and appended to evidence/reports/evaluation.md.

Usage (from the backend directory):
    python ml/train_email_model.py
"""

import sys
from datetime import datetime, timezone
from pathlib import Path

import joblib
import pandas as pd

ML_DIR = Path(__file__).resolve().parent
DATA_DIR = ML_DIR / "data"
MODELS_DIR = ML_DIR / "models"
REPO_ROOT = ML_DIR.parents[1]
EVAL_REPORT = REPO_ROOT / "evidence" / "reports" / "evaluation.md"
SEED = 42

LANG_ORDER = ("en", "hi", "te", "or", "roman")


def evaluate(y_true, y_pred) -> dict:
    from sklearn.metrics import accuracy_score, f1_score, precision_score, recall_score

    return {
        "accuracy": round(float(accuracy_score(y_true, y_pred)), 4),
        "precision": round(float(precision_score(y_true, y_pred, zero_division=0)), 4),
        "recall": round(float(recall_score(y_true, y_pred, zero_division=0)), 4),
        "f1": round(float(f1_score(y_true, y_pred, zero_division=0)), 4),
    }


def main() -> int:
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.model_selection import train_test_split
    from xgboost import XGBClassifier

    corpus_path = DATA_DIR / "train_emails_multilang.csv"
    if not corpus_path.exists():
        print(f"ERROR: {corpus_path} not found — run ml/build_indic_corpus.py first")
        return 1
    frame = pd.read_csv(corpus_path).dropna(subset=["clean_text", "label", "lang"])
    frame["label"] = frame["label"].astype(int)

    # Stratified 80/20 split per language so every language has held-out rows.
    train_parts, eval_parts = [], []
    for lang, group in frame.groupby("lang", sort=False):
        train, test = train_test_split(
            group, test_size=0.2, random_state=SEED, stratify=group["label"]
        )
        train_parts.append(train)
        eval_parts.append(test)
        print(f"  split {lang}: {len(train)} train / {len(test)} held-out")
    train_df = pd.concat(train_parts, ignore_index=True)
    eval_df = pd.concat(eval_parts, ignore_index=True)
    print(f"  combined training pool: {len(train_df)} rows; held-out pool: {len(eval_df)} rows")

    # Character n-grams (2-4) — script-agnostic features, no transliteration.
    vectorizer = TfidfVectorizer(
        analyzer="char",
        ngram_range=(2, 4),
        max_features=50000,
        sublinear_tf=True,
    )
    X_train = vectorizer.fit_transform(train_df["clean_text"])
    y_train = train_df["label"].to_numpy()

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

    X_eval = vectorizer.transform(eval_df["clean_text"])
    eval_df = eval_df.assign(prediction=model.predict(X_eval))

    per_lang = []
    for lang in LANG_ORDER:
        group = eval_df[eval_df["lang"] == lang]
        if group.empty:
            continue
        metrics = evaluate(group["label"], group["prediction"])
        per_lang.append((lang, len(group), metrics))

    overall = evaluate(eval_df["label"], eval_df["prediction"])

    # Persist the v2 artifacts + a machine-readable metrics sidecar.
    joblib.dump(vectorizer, MODELS_DIR / "email_tfidf_v2.pkl")
    joblib.dump(model, MODELS_DIR / "email_phishing_xgb_v2.pkl")

    header = (
        "\n\n## Multilingual email model (char n-gram 2-4 TF-IDF + XGBoost, v2)\n\n"
        f"Generated: {datetime.now(timezone.utc).isoformat()} · script: `ml/train_email_model.py` · "
        f"corpus: `ml/data/train_emails_multilang.csv` (synthetic-by-construction, see `backend/docs/datasets.md`) · "
        f"seed {SEED}, held-out 20% split per language, max_features 50000, scale_pos_weight balancing.\n\n"
        "| Language | Held-out n | Accuracy | Precision | Recall | F1 |\n|---|---|---|---|---|---|\n"
    )
    lines = [
        f"| {lang} | {n} | {m['accuracy']:.4f} | {m['precision']:.4f} | {m['recall']:.4f} | {m['f1']:.4f} |"
        for lang, n, m in per_lang
    ]
    footer = (
        f"| **overall (held-out pool)** | {len(eval_df)} | {overall['accuracy']:.4f} | "
        f"{overall['precision']:.4f} | {overall['recall']:.4f} | {overall['f1']:.4f} |\n\n"
        "Artifacts: `ml/models/email_tfidf_v2.pkl` + `ml/models/email_phishing_xgb_v2.pkl` "
        "(selected by `ml/models/calibration.json`: `email_model_version`).\n"
    )
    table = header + "\n".join(lines) + "\n" + footer

    print("\n  Per-language metrics on the held-out 20% split:")
    print("  | Language | n | Accuracy | Precision | Recall | F1 |")
    for lang, n, m in per_lang:
        print(f"  | {lang} | {n} | {m['accuracy']:.4f} | {m['precision']:.4f} | {m['recall']:.4f} | {m['f1']:.4f} |")
    print(
        f"  | overall | {len(eval_df)} | {overall['accuracy']:.4f} | "
        f"{overall['precision']:.4f} | {overall['recall']:.4f} | {overall['f1']:.4f} |"
    )

    with EVAL_REPORT.open("a", encoding="utf-8") as fh:
        fh.write(table)
    print(f"  appended per-language table -> {EVAL_REPORT}")

    failing = [(lang, m["f1"]) for lang, _, m in per_lang if m["f1"] < 0.85]
    if failing:
        print(f"  WARNING: per-language F1 below 0.85: {failing}")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
