"""Reproducible model comparison used to select the final classifier.

Runs several simple, scikit-learn-only model families through the same
5-fold x 10-repeat stratified cross-validation on the training split (never
touching the test set), then reports each config's CV accuracy plus a single
train/test fit for reference. This is the reproducible companion to the
narrative comparison described in README.md ("Model search and validation").

Usage:
    python src/compare_models.py

Output:
    results/model_comparison.txt
"""
from __future__ import annotations

import os
import warnings

import pandas as pd
from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.ensemble import RandomForestClassifier, VotingClassifier
from sklearn.calibration import CalibratedClassifierCV
from sklearn.feature_extraction.text import CountVectorizer, TfidfVectorizer
from sklearn.linear_model import LogisticRegression, SGDClassifier
from sklearn.metrics import accuracy_score
from sklearn.model_selection import RepeatedStratifiedKFold, cross_val_score, train_test_split
from sklearn.naive_bayes import ComplementNB
from sklearn.pipeline import FeatureUnion, Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.svm import LinearSVC

from lexicon_features import FRAMING_PHRASES, INTENT_PHRASES, PhraseCountFeaturizer
from prepare_data import OUTPUT_PATH, prepare_dataset

RANDOM_SEED = 42
TEST_SIZE = 0.2

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_PATH_TXT = os.path.join(REPO_ROOT, "results", "model_comparison.txt")


def _lexicon_pipeline(clf) -> Pipeline:
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
    return Pipeline([("features", features), ("clf", clf)])


def build_candidates() -> list[tuple[str, Pipeline]]:
    """Return (name, pipeline) pairs to compare. Kept short to run quickly."""
    return [
        (
            "TF-IDF (word) + LogisticRegression(C=0.3)  [round-1 baseline]",
            Pipeline([
                ("vec", TfidfVectorizer(sublinear_tf=True)),
                ("clf", LogisticRegression(C=0.3, max_iter=3000, random_state=RANDOM_SEED)),
            ]),
        ),
        (
            "CountVec + ComplementNB(alpha=0.5)  [round-2 search]",
            Pipeline([
                ("vec", CountVectorizer()),
                ("clf", ComplementNB(alpha=0.5)),
            ]),
        ),
        (
            "TF-IDF (word) + SGD(hinge, alpha=0.01)  [round-2 search]",
            Pipeline([
                ("vec", TfidfVectorizer(sublinear_tf=True)),
                ("clf", SGDClassifier(loss="hinge", alpha=0.01, random_state=RANDOM_SEED, max_iter=3000)),
            ]),
        ),
        (
            "TF-IDF (word) + RandomForest(n=300)  [round-2 search]",
            Pipeline([
                ("vec", TfidfVectorizer(sublinear_tf=True)),
                ("clf", RandomForestClassifier(n_estimators=300, random_state=RANDOM_SEED)),
            ]),
        ),
        (
            "TF-IDF (word) + Voting(LR+NB+SVM)  [round-2 search]",
            Pipeline([
                ("vec", TfidfVectorizer(sublinear_tf=True)),
                ("clf", VotingClassifier(estimators=[
                    ("lr", LogisticRegression(C=0.3, max_iter=3000, random_state=RANDOM_SEED)),
                    ("nb", ComplementNB(alpha=0.5)),
                    ("svm", CalibratedClassifierCV(LinearSVC(C=0.3, random_state=RANDOM_SEED), cv=3)),
                ], voting="soft")),
            ]),
        ),
        (
            "TF-IDF + intent/framing phrases + LogisticRegression(C=0.3)  [FINAL, round-3]",
            _lexicon_pipeline(LogisticRegression(C=0.3, max_iter=3000, random_state=RANDOM_SEED)),
        ),
    ]


def main() -> None:
    warnings.filterwarnings("ignore")

    processed_path = OUTPUT_PATH
    if not os.path.exists(processed_path):
        prepare_dataset()
    df = pd.read_csv(processed_path)

    train_df, test_df = train_test_split(
        df, test_size=TEST_SIZE, random_state=RANDOM_SEED, stratify=df["label"]
    )
    cv = RepeatedStratifiedKFold(n_splits=5, n_repeats=10, random_state=RANDOM_SEED)

    rows = []
    for name, pipe in build_candidates():
        scores = cross_val_score(pipe, train_df["text"], train_df["label"], cv=cv)
        pipe.fit(train_df["text"], train_df["label"])
        train_acc = accuracy_score(train_df["label"], pipe.predict(train_df["text"]))
        test_acc = accuracy_score(test_df["label"], pipe.predict(test_df["text"]))
        rows.append((name, scores.mean(), scores.std(), train_acc, test_acc))

    rows.sort(key=lambda r: r[1], reverse=True)

    lines = [
        "AI Trust Gate - Model Comparison (reproducible)",
        "=" * 60,
        f"Train size: {len(train_df)} | Test size: {len(test_df)} | seed: {RANDOM_SEED}",
        "CV: 5-fold x 10-repeat StratifiedKFold on the training split only (50 scored folds)",
        "",
        f"{'Model':<65} {'CV mean':>8} {'CV std':>8} {'Train acc':>10} {'Test acc':>9}",
        "-" * 103,
    ]
    for name, cv_mean, cv_std, train_acc, test_acc in rows:
        lines.append(f"{name:<65} {cv_mean:>8.4f} {cv_std:>8.4f} {train_acc:>10.4f} {test_acc:>9.4f}")

    text = "\n".join(lines)
    print(text)

    os.makedirs(os.path.dirname(OUTPUT_PATH_TXT), exist_ok=True)
    with open(OUTPUT_PATH_TXT, "w", encoding="utf-8") as f:
        f.write(text + "\n")
    print(f"\nSaved comparison table to {OUTPUT_PATH_TXT}")


if __name__ == "__main__":
    main()
