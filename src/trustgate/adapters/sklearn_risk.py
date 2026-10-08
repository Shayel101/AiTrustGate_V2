"""Adapter that exposes the frozen A1 classifier (src/train.py) as a domain RiskAssessor.

Re-fits exactly the A1 procedure (same split, seed, grid, CV) so that its test-split labels can be
checked against the committed results/predictions.csv. A1 code is imported, not modified.
"""
from __future__ import annotations

from typing import Any, Mapping, Optional

import pandas as pd
from sklearn.model_selection import GridSearchCV, RepeatedStratifiedKFold, train_test_split

from train import C_GRID, RANDOM_SEED, TEST_SIZE, build_pipeline  # A1 baseline definitions

POSITIVE_LABEL = "harmful"


class SklearnRiskAssessor:
    def __init__(self, pipeline, selected_c: float) -> None:
        self._pipeline = pipeline
        self._harmful_idx = list(pipeline.classes_).index(POSITIVE_LABEL)
        self.model_version = f"a1-tfidf-lexicon-logreg-C{selected_c}-seed{RANDOM_SEED}"

    def assess(self, request_text: str, tool_name: str, tool_arguments: Mapping[str, Any]) -> Optional[float]:
        # Only the request text is scored; tool_arguments are NOT assessed (A1 model never saw them).
        return float(self._pipeline.predict_proba([request_text])[0][self._harmful_idx])


def fit_a1_baseline(df: pd.DataFrame) -> tuple[SklearnRiskAssessor, pd.DataFrame, pd.DataFrame, float]:
    train_df, test_df = train_test_split(df, test_size=TEST_SIZE, random_state=RANDOM_SEED, stratify=df["label"])
    cv = RepeatedStratifiedKFold(n_splits=5, n_repeats=10, random_state=RANDOM_SEED)
    grid = GridSearchCV(build_pipeline(), param_grid={"clf__C": C_GRID}, cv=cv, refit=True)
    grid.fit(train_df["text"], train_df["label"])
    best_c = grid.best_params_["clf__C"]
    return SklearnRiskAssessor(grid.best_estimator_, best_c), train_df, test_df, best_c
