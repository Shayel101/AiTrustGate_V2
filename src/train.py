"""Train and evaluate the AI Trust Gate baseline classifier.

Pipeline: TF-IDF word features + intent/framing phrase-count features (see
src/lexicon_features.py) -> Logistic Regression -> benign/harmful prediction.
Still a simple, linear, scikit-learn-only model; no embeddings or deep learning.

Usage:
    python src/train.py

Requires data/processed/jbb_behavior_classifier.csv to exist; run
src/prepare_data.py first if it does not.

Outputs:
    results/predictions.csv
    results/metrics.json
    results/evaluation.txt

This feature set was chosen via 5-fold x 10-repeat stratified cross-validation
on the training split only (50 scored folds; see README.md, "Model search and
validation" section, for the full comparison against plain TF-IDF and other
model families). The regularization strength C is re-selected automatically
every run via GridSearchCV on the training split only (never the test set),
instead of being hard-coded, so the choice is reproducible from code rather
than from a one-off notebook experiment. The held-out test set is evaluated
exactly once with the selected configuration.

A SHA-256 checksum manifest (results/CHECKSUMS.sha256) is written after each
run so the produced artifacts can be independently verified, and the raw
JBB-Behaviors CSVs are checked against a pinned manifest
(data/raw/CHECKSUMS.sha256) before training to detect accidental edits.
"""
from __future__ import annotations

import json
import os

import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score
from sklearn.model_selection import GridSearchCV, RepeatedStratifiedKFold, train_test_split
from sklearn.pipeline import FeatureUnion, Pipeline
from sklearn.preprocessing import StandardScaler

from evaluate import build_evaluation_report, compute_metrics, find_misclassified
from integrity import write_manifest
from lexicon_features import FRAMING_PHRASES, INTENT_PHRASES, PhraseCountFeaturizer
from prepare_data import OUTPUT_PATH, prepare_dataset

RANDOM_SEED = 42
TEST_SIZE = 0.2
# Regularization grid validated in README.md "Model search and validation";
# GridSearchCV re-confirms the best value on the training split every run.
C_GRID = [0.1, 0.15, 0.2, 0.25, 0.3, 0.4, 0.5, 0.7, 1.0]

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULTS_DIR = os.path.join(REPO_ROOT, "results")
PREDICTIONS_PATH = os.path.join(RESULTS_DIR, "predictions.csv")
METRICS_PATH = os.path.join(RESULTS_DIR, "metrics.json")
EVALUATION_PATH = os.path.join(RESULTS_DIR, "evaluation.txt")
CHECKSUMS_PATH = os.path.join(RESULTS_DIR, "CHECKSUMS.sha256")


def build_pipeline(C: float = 0.3) -> Pipeline:
    """Build the TF-IDF + lexicon-feature + LogisticRegression pipeline."""
    features = FeatureUnion([
        ("word_tfidf", TfidfVectorizer(sublinear_tf=True)),
        ("intent_phrases", Pipeline([
            ("count", PhraseCountFeaturizer(INTENT_PHRASES)),
            ("scale", StandardScaler()),
        ])),
        ("framing_phrases", Pipeline([
            ("count", PhraseCountFeaturizer(FRAMING_PHRASES)),
            ("scale", StandardScaler()),
        ])),
    ])
    return Pipeline([
        ("features", features),
        ("clf", LogisticRegression(random_state=RANDOM_SEED, C=C, max_iter=3000)),
    ])


def load_processed_dataset() -> pd.DataFrame:
    """Load the processed dataset, generating it from raw CSVs if it is missing."""
    if not os.path.exists(OUTPUT_PATH):
        print(f"{OUTPUT_PATH} not found; running data preparation first.")
        return prepare_dataset()
    return pd.read_csv(OUTPUT_PATH)


def main() -> None:
    df = load_processed_dataset()

    # Stratified 80/20 split keeps the benign/harmful ratio balanced in both splits.
    train_df, test_df = train_test_split(
        df,
        test_size=TEST_SIZE,
        random_state=RANDOM_SEED,
        stratify=df["label"],
    )

    # Select C automatically via grid search, scored with the same repeated CV
    # used to validate the feature set, on the training split only. This makes
    # the hyperparameter choice reproducible from code instead of hard-coded.
    cv = RepeatedStratifiedKFold(n_splits=5, n_repeats=10, random_state=RANDOM_SEED)
    grid = GridSearchCV(
        build_pipeline(),
        param_grid={"clf__C": C_GRID},
        cv=cv,
        refit=True,
    )
    grid.fit(train_df["text"], train_df["label"])

    model = grid.best_estimator_
    best_c = grid.best_params_["clf__C"]
    cv_mean = grid.cv_results_["mean_test_score"][grid.best_index_]
    cv_std = grid.cv_results_["std_test_score"][grid.best_index_]
    model_description = (
        "TF-IDF (sublinear_tf=True) + intent/framing phrase-count features "
        f"+ LogisticRegression (C={best_c}, selected via GridSearchCV)"
    )

    y_pred = model.predict(test_df["text"])
    y_true = test_df["label"]
    train_accuracy = accuracy_score(train_df["label"], model.predict(train_df["text"]))

    metrics = compute_metrics(y_true, y_pred)
    metrics_out = {
        "dataset_size": len(df),
        "train_size": len(train_df),
        "test_size": len(test_df),
        "random_seed": RANDOM_SEED,
        "test_split_fraction": TEST_SIZE,
        "model": model_description,
        "selected_C": best_c,
        "c_grid_searched": C_GRID,
        "train_accuracy": train_accuracy,
        "cv_accuracy_mean": cv_mean,
        "cv_accuracy_std": cv_std,
        "cv_folds": "5-fold x 10-repeat StratifiedKFold (50 scored folds), training split only",
        **metrics,
    }

    os.makedirs(RESULTS_DIR, exist_ok=True)

    with open(METRICS_PATH, "w", encoding="utf-8") as f:
        json.dump(metrics_out, f, indent=2)

    report_text = build_evaluation_report(y_true, y_pred)
    header = (
        f"Dataset size: {len(df)} | Train size: {len(train_df)} | "
        f"Test size: {len(test_df)} | Random seed: {RANDOM_SEED}\n"
        f"Model: {model_description}\n"
        f"Training-set accuracy (fit check, not a generalization estimate): {train_accuracy:.4f}\n"
        f"Accuracy (held-out test set, evaluated once): {metrics['accuracy']:.4f}\n"
        f"5-fold x 10-repeat CV accuracy on training split (best C={best_c}): {cv_mean:.4f} "
        f"(+/- {cv_std:.4f})\n\n"
    )
    with open(EVALUATION_PATH, "w", encoding="utf-8") as f:
        f.write(header + report_text)

    predictions_out = test_df.copy()
    predictions_out["predicted_label"] = y_pred
    predictions_out["correct"] = predictions_out["label"] == predictions_out["predicted_label"]
    predictions_out.to_csv(PREDICTIONS_PATH, index=False)

    misclassified = find_misclassified(test_df, y_true, y_pred)

    write_manifest(
        [OUTPUT_PATH, METRICS_PATH, PREDICTIONS_PATH, EVALUATION_PATH],
        CHECKSUMS_PATH,
        REPO_ROOT,
    )

    print(header)
    print(report_text)
    print(f"Misclassified rows: {len(misclassified)} / {len(test_df)}")
    print(f"Saved predictions to {PREDICTIONS_PATH}")
    print(f"Saved metrics to {METRICS_PATH}")
    print(f"Saved evaluation report to {EVALUATION_PATH}")
    print(f"Saved SHA-256 checksums to {CHECKSUMS_PATH}")


if __name__ == "__main__":
    main()
