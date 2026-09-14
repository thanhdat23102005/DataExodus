"""
Machine Learning — experimental tracker classifier.

Rule-based classification (pipeline/classify.py) stays the source of truth
for the study: every label it produces can be checked by hand against
Tracker Radar/EasyPrivacy, which is the whole point of keeping the sample
at 50 sites. This module asks a different, narrower question: can a
lightweight supervised model learn to approximate "is this a tracker?"
from request-level features alone (host shape, resource type, keyword
counts), without consulting a blocklist at all? That matters because
blocklists lag - a classifier that generalises could flag trackers a
static list misses. The rule-based labels are used as ground truth to
train and evaluate it; it does not feed back into the study's numbers.

Usage:
    python -m pipeline.ml_classifier
    python -m pipeline.ml_classifier --db data/dataexodus.duckdb
"""

from __future__ import annotations

import argparse
from pathlib import Path
from urllib.parse import urlparse

import duckdb
import joblib
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

DATA_DIR = Path(__file__).parent.parent / "data"

TRACKER_KEYWORDS = [
    "ads", "adserver", "analytics", "track", "pixel", "beacon", "tag",
    "sync", "doubleclick", "telemetry", "metrics", "collect", "stats",
]

NUMERIC_FEATURES = [
    "host_length", "num_subdomains", "num_digits_host", "path_length",
    "num_query_params", "tracker_keyword_hits",
]
BOOL_FEATURES = ["has_hyphen", "third_party", "insecure"]
CATEGORICAL_FEATURES = ["resource_type"]


def load_requests(db_path: Path) -> pd.DataFrame:
    """
    pipeline/process.py's schema has no 'method', 'host', 'third_party', or
    'insecure' columns (it was rewritten independently of this module) -
    host/third_party/insecure are derived in extract_features() from url and
    initiator instead, which is what's actually available.
    """
    con = duckdb.connect(str(db_path), read_only=True)
    df = con.execute(
        "SELECT url, initiator, resource_type, domain, is_tracker "
        "FROM requests"
    ).fetchdf()
    con.close()
    return df


def extract_features(df: pd.DataFrame) -> pd.DataFrame:
    """Turn raw request rows into a numeric/categorical feature table."""
    out = pd.DataFrame(index=df.index)
    parsed = df["url"].fillna("").apply(urlparse)
    host = parsed.apply(lambda p: p.hostname or "")
    initiator_host = df["initiator"].fillna("").apply(
        lambda i: urlparse(i).hostname or ""
    )

    out["host_length"] = host.str.len()
    out["num_subdomains"] = host.str.count(r"\.")
    out["num_digits_host"] = host.apply(lambda h: sum(c.isdigit() for c in h))
    out["has_hyphen"] = host.str.contains("-")
    out["path_length"] = parsed.apply(lambda p: len(p.path))
    out["num_query_params"] = parsed.apply(
        lambda p: len(p.query.split("&")) if p.query else 0
    )
    out["tracker_keyword_hits"] = host.apply(
        lambda h: sum(1 for kw in TRACKER_KEYWORDS if kw in h.lower())
    )
    # third_party/insecure aren't stored columns - derive them the same way
    # pipeline/classify.py's rule-based logic would: compare the request's
    # host against the page (initiator) that triggered it, and check scheme.
    out["third_party"] = (host != "") & (host != initiator_host)
    out["insecure"] = parsed.apply(lambda p: p.scheme == "http")
    out["resource_type"] = df["resource_type"].fillna("other")
    return out


def build_pipeline(model) -> Pipeline:
    pre = ColumnTransformer([
        ("num", StandardScaler(), NUMERIC_FEATURES + BOOL_FEATURES),
        ("cat", OneHotEncoder(handle_unknown="ignore"), CATEGORICAL_FEATURES),
    ])
    return Pipeline([("pre", pre), ("model", model)])


def evaluate(name: str, pipe: Pipeline, X_test, y_test) -> dict:
    y_pred = pipe.predict(X_test)
    acc = accuracy_score(y_test, y_pred)
    print(f"\n=== {name} ===")
    print(f"Accuracy: {acc:.3f}")
    print(classification_report(y_test, y_pred, zero_division=0))
    cm = confusion_matrix(y_test, y_pred)
    print("Confusion matrix [[TN FP] [FN TP]]:")
    print(cm)
    return {"name": name, "accuracy": acc, "confusion_matrix": cm.tolist()}


def main() -> list[dict]:
    parser = argparse.ArgumentParser(
        description="Train an experimental ML tracker classifier and compare "
                    "it against the rule-based labels"
    )
    parser.add_argument("--db", default=str(DATA_DIR / "dataexodus.duckdb"))
    parser.add_argument("--model-out", default=str(DATA_DIR / "ml_tracker_model.joblib"))
    parser.add_argument("--test-size", type=float, default=0.25)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    df = load_requests(Path(args.db))
    if df.empty:
        raise SystemExit(f"No rows in {args.db} - run the crawler + pipeline.process first")

    X = extract_features(df)
    y = df["is_tracker"].astype(int)

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=args.test_size, random_state=args.seed, stratify=y
    )

    print(f"Dataset: {len(df)} requests ({y.mean() * 100:.1f}% trackers by the "
          f"rule-based labels)")
    print(f"Train/test split: {len(X_train)} / {len(X_test)}")

    # Naive baseline the models need to beat to be worth anything: predict
    # "tracker" iff the request is third-party.
    baseline_acc = accuracy_score(y_test, X_test["third_party"].astype(int))
    print(f"\nBaseline (predict is_tracker = third_party): accuracy {baseline_acc:.3f}")

    results = [{"name": "baseline_third_party_only", "accuracy": baseline_acc}]

    logreg = build_pipeline(LogisticRegression(max_iter=1000, class_weight="balanced"))
    logreg.fit(X_train, y_train)
    results.append(evaluate("Logistic Regression", logreg, X_test, y_test))

    forest = build_pipeline(RandomForestClassifier(
        n_estimators=200, max_depth=6, random_state=args.seed, class_weight="balanced"
    ))
    forest.fit(X_train, y_train)
    results.append(evaluate("Random Forest", forest, X_test, y_test))

    best = max(results[1:], key=lambda r: r["accuracy"])
    best_pipe = logreg if best["name"] == "Logistic Regression" else forest
    joblib.dump(best_pipe, args.model_out)
    print(f"\nBest model: {best['name']} (accuracy {best['accuracy']:.3f}) -> {args.model_out}")

    return results


if __name__ == "__main__":
    main()
