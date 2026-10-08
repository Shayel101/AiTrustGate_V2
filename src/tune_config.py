"""Configuration search for the risk assessor, with a pre-registered selection rule and a one-shot test evaluation.

Usage:
    python src/tune_config.py --preset quick|standard|wide [--grid configs/tuning_grid.json] [--n-jobs 12]
    python src/tune_config.py --preset standard --final-test      # evaluates the held-out split ONCE, after selection

Protocol (fixed before running; the same 80/20 stratified split and seed as A1's src/train.py):
  1. Every configuration is scored by repeated stratified CV on the TRAINING split only. The test split is never read
     unless --final-test is given.
  2. Selection rule: highest mean CV ROC-AUC (threshold-free, because the gate acts on score bands); ties -> lower log loss.
     The A1 configuration is always scored on the same folds as the reference.
  3. Policy thresholds are chosen on out-of-fold training scores under an explicit constraint (PROJECT DESIGN DECISION).
  4. With --final-test the reference and the selected configuration are evaluated once on the test split.
No lexicon phrases are edited here: adding phrases after looking at test errors (e.g. harmful_34) would leak the test split.
"""
from __future__ import annotations

import argparse
import itertools
import json
import os
import time
from typing import Any

import numpy as np
import pandas as pd
from joblib import Parallel, delayed
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score, brier_score_loss, fbeta_score, make_scorer, precision_score, recall_score, roc_auc_score,
)
from sklearn.model_selection import RepeatedStratifiedKFold, StratifiedKFold, cross_val_predict, cross_validate, train_test_split
from sklearn.pipeline import FeatureUnion, Pipeline
from sklearn.preprocessing import StandardScaler

from lexicon_features import FRAMING_PHRASES, INTENT_PHRASES, PhraseCountFeaturizer

SEED = 42
TEST_SIZE = 0.2
POS = "harmful"
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_PATH = os.path.join(REPO_ROOT, "data", "processed", "jbb_behavior_classifier.csv")
DEFAULT_GRID = os.path.join(REPO_ROOT, "configs", "tuning_grid.json")

# The A1 configuration (src/train.py with the C it selects), scored on the same folds as every candidate.
A1_CONFIG: dict[str, Any] = {
    "ngram": [1, 1], "min_df": 1, "sublinear_tf": True, "char": None,
    "lexicon": True, "lexicon_weight": 1, "class_weight": None, "penalty": "l2", "C": 0.2,
}

# PROJECT DESIGN DECISION: constraints for choosing policy thresholds on out-of-fold training scores.
MAX_HARMFUL_ALLOW_RATE = 0.05   # A1 reports FNR 0.05 as its value measure
MAX_REVIEW_LOAD = 0.30          # share of all requests sent to humans (placeholder budget, U-01)
BLOCK_GRID = [round(x, 2) for x in np.arange(0.40, 0.801, 0.05)]
REVIEW_GRID = [round(x, 2) for x in np.arange(0.15, 0.751, 0.05)]


def build_pipeline(cfg: dict[str, Any]) -> Pipeline:
    parts: list[tuple[str, Any]] = [("word", TfidfVectorizer(
        ngram_range=tuple(cfg["ngram"]), min_df=cfg["min_df"], sublinear_tf=cfg["sublinear_tf"]))]
    weights: dict[str, float] = {"word": 1.0}
    if cfg["char"]:
        parts.append(("char", TfidfVectorizer(analyzer="char_wb", ngram_range=tuple(cfg["char"]), sublinear_tf=True)))
        weights["char"] = 1.0
    if cfg["lexicon"]:
        for name, phrases in (("intent", INTENT_PHRASES), ("framing", FRAMING_PHRASES)):
            parts.append((name, Pipeline([("count", PhraseCountFeaturizer(phrases)), ("scale", StandardScaler())])))
            weights[name] = float(cfg["lexicon_weight"])
    return Pipeline([
        ("features", FeatureUnion(parts, transformer_weights=weights)),
        ("clf", LogisticRegression(C=cfg["C"], class_weight=cfg["class_weight"], max_iter=3000, random_state=SEED,
                                   **({"l1_ratio": 1.0, "solver": "liblinear"} if cfg["penalty"] == "l1" else {}))),
    ])


def expand_grid(grid: dict[str, Any]) -> list[dict[str, Any]]:
    keys = ["ngram", "min_df", "sublinear_tf", "char", "lexicon", "lexicon_weight", "class_weight", "penalty", "C"]
    seen, configs = set(), []
    for combo in itertools.product(*(grid[k] for k in keys)):
        cfg = dict(zip(keys, combo))
        if not cfg["lexicon"]:
            cfg["lexicon_weight"] = 1  # irrelevant without lexicon: avoid duplicate configs
        key = json.dumps(cfg, sort_keys=True)
        if key not in seen:
            seen.add(key)
            configs.append(cfg)
    ref = json.dumps(A1_CONFIG, sort_keys=True)
    if ref not in seen:
        configs.append(dict(A1_CONFIG))
    return configs


SCORING = {
    "auc": "roc_auc",
    "acc": "accuracy",
    "neg_logloss": "neg_log_loss",
    "neg_brier": make_scorer(brier_score_loss, response_method="predict_proba", pos_label=POS, greater_is_better=False),
    "recall": make_scorer(recall_score, pos_label=POS),
    "precision": make_scorer(precision_score, pos_label=POS, zero_division=0),
    "f2": make_scorer(fbeta_score, beta=2, pos_label=POS),
}


def score_config(cfg: dict[str, Any], X: pd.Series, y: pd.Series, cv: RepeatedStratifiedKFold) -> dict[str, Any]:
    t0 = time.perf_counter()
    res = cross_validate(build_pipeline(cfg), X, y, cv=cv, scoring=SCORING, n_jobs=1, return_train_score=False)
    row: dict[str, Any] = {"config": json.dumps(cfg, sort_keys=True)}
    for name in SCORING:
        vals = res[f"test_{name}"]
        sign = -1.0 if name.startswith("neg_") else 1.0
        row[f"{name.removeprefix('neg_')}_mean"] = sign * float(vals.mean())
        row[f"{name.removeprefix('neg_')}_std"] = float(vals.std())
    row["fold_auc"] = res["test_auc"].tolist()
    row["seconds"] = time.perf_counter() - t0
    return row


def marginals(res: pd.DataFrame) -> pd.DataFrame:
    """Per factor level: best and mean CV ROC-AUC over all configs that use it (how much each range matters)."""
    cfgs = pd.DataFrame([json.loads(c) for c in res["config"]])
    rows = []
    for key in ["ngram", "min_df", "sublinear_tf", "char", "lexicon", "lexicon_weight", "penalty", "C"]:
        level = cfgs[key].map(json.dumps)
        for lv, idx in level.groupby(level).groups.items():
            sub = res.loc[idx]
            rows.append({"factor": key, "level": lv, "n_configs": len(sub),
                         "best_auc": sub.auc_mean.max(), "mean_auc": sub.auc_mean.mean(),
                         "best_recall_at_0.5": sub.loc[sub.auc_mean.idxmax(), "recall_mean"]})
    return pd.DataFrame(rows)


def threshold_table(p: np.ndarray, y: np.ndarray) -> pd.DataFrame:
    harmful, benign = y == POS, y != POS
    rows = []
    for block in BLOCK_GRID:
        for review in REVIEW_GRID:
            if review > block:
                continue
            blocked, reviewed = p > block, (p >= review) & (p <= block)
            allowed = ~blocked & ~reviewed
            rows.append({
                "block_above": block, "review_lower": review,
                "harmful_allow_rate": float((allowed & harmful).sum() / harmful.sum()),
                "harmful_block_rate": float((blocked & harmful).sum() / harmful.sum()),
                "benign_block_rate": float((blocked & benign).sum() / benign.sum()),
                "benign_review_rate": float((reviewed & benign).sum() / benign.sum()),
                "benign_allow_rate": float((allowed & benign).sum() / benign.sum()),
                "review_load": float(reviewed.mean()),
            })
    return pd.DataFrame(rows)


def pick_thresholds(table: pd.DataFrame) -> dict[str, Any] | None:
    ok = table[(table.harmful_allow_rate <= MAX_HARMFUL_ALLOW_RATE) & (table.review_load <= MAX_REVIEW_LOAD)]
    if ok.empty:
        return None
    best = ok.sort_values(["benign_allow_rate", "block_above"], ascending=[False, False]).iloc[0]
    return {k: float(best[k]) for k in table.columns}


def decide_bands(p: np.ndarray, block: float, review: float) -> np.ndarray:
    return np.where(p > block, "BLOCK", np.where(p >= review, "REVIEW", "ALLOW"))


def evaluate_once(name: str, cfg: dict[str, Any], thresholds: tuple[float, float],
                  Xtr: pd.Series, ytr: pd.Series, Xte: pd.Series, yte: pd.Series) -> dict[str, Any]:
    model = build_pipeline(cfg).fit(Xtr, ytr)
    p = model.predict_proba(Xte)[:, list(model.classes_).index(POS)]
    y = yte.to_numpy()
    decisions = decide_bands(p, thresholds[1], thresholds[0])
    pred_label = np.where(p > 0.5, POS, "benign")
    out: dict[str, Any] = {
        "name": name, "config": cfg, "block_above": thresholds[1], "review_lower": thresholds[0],
        "test_auc": float(roc_auc_score(y == POS, p)),
        "test_accuracy_at_0.5": float(accuracy_score(y, pred_label)),
        "test_recall_at_0.5": float(recall_score(y, pred_label, pos_label=POS)),
        "test_precision_at_0.5": float(precision_score(y, pred_label, pos_label=POS, zero_division=0)),
        "decisions_by_true_label": {
            lab: {d: int(((y == lab) & (decisions == d)).sum()) for d in ("ALLOW", "REVIEW", "BLOCK")}
            for lab in ("benign", "harmful")
        },
    }
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--preset", default="quick", choices=["quick", "standard", "wide"])
    ap.add_argument("--grid", default=DEFAULT_GRID)
    ap.add_argument("--n-jobs", type=int, default=-1)
    ap.add_argument("--final-test", action="store_true", help="evaluate the held-out split once, after selection")
    args = ap.parse_args()

    with open(args.grid, encoding="utf-8") as f:
        grid = json.load(f)[args.preset]
    out_dir = os.path.join(REPO_ROOT, "results", "tuning", args.preset)
    os.makedirs(out_dir, exist_ok=True)

    df = pd.read_csv(DATA_PATH)
    train_df, test_df = train_test_split(df, test_size=TEST_SIZE, random_state=SEED, stratify=df["label"])
    X, y = train_df["text"], train_df["label"]
    cv = RepeatedStratifiedKFold(n_splits=grid["cv"]["n_splits"], n_repeats=grid["cv"]["n_repeats"], random_state=SEED)

    configs = expand_grid(grid)
    print(f"preset={args.preset}: {len(configs)} configurations x {cv.get_n_splits()} folds, "
          f"train n={len(train_df)}; test split not read unless --final-test")
    t0 = time.perf_counter()
    rows = Parallel(n_jobs=args.n_jobs)(delayed(score_config)(c, X, y, cv) for c in configs)
    elapsed = time.perf_counter() - t0
    res = pd.DataFrame(rows)
    res["is_a1_reference"] = res["config"] == json.dumps(A1_CONFIG, sort_keys=True)
    res = res.sort_values(["auc_mean", "logloss_mean"], ascending=[False, True]).reset_index(drop=True)
    res.drop(columns=["fold_auc"]).to_csv(os.path.join(out_dir, "all_configs.csv"), index=False)

    best = res.iloc[0]
    ref = res[res.is_a1_reference].iloc[0]
    diff = np.array(best.fold_auc) - np.array(ref.fold_auc)
    best_cfg = json.loads(best.config)
    print(f"search time {elapsed:.1f}s ({elapsed / len(configs):.2f}s/config wall)")
    cols = ["auc_mean", "auc_std", "acc_mean", "recall_mean", "precision_mean", "logloss_mean", "brier_mean", "config"]
    pd.set_option("display.width", 250, "display.max_colwidth", 140)
    print("\nTop 10 by mean CV ROC-AUC (training split only):")
    print(res[cols].head(10).to_string(float_format=lambda v: f"{v:.4f}"))
    print("\nA1 reference configuration on the same folds:")
    print(res[res.is_a1_reference][cols].to_string(float_format=lambda v: f"{v:.4f}"))
    print(f"\nPaired fold-wise AUC difference (best - A1): mean {diff.mean():+.4f}, sd {diff.std():.4f}, "
          f"folds better {int((diff > 0).sum())}/{len(diff)}")
    near = res[res.auc_mean >= best.auc_mean - best.auc_std / np.sqrt(grid["cv"]["n_repeats"])]
    print(f"configurations within 1 repeat-SE of the best: {len(near)} (a wide plateau means the choice is not sharply identified)")
    marg = marginals(res)
    marg.to_csv(os.path.join(out_dir, "marginals.csv"), index=False)
    print("\nEffect of each factor level (best / mean CV AUC over configs using it):")
    print(marg.to_string(index=False, float_format=lambda v: f"{v:.4f}"))

    # Out-of-fold scores of the selected configuration -> policy thresholds (training split only).
    oof = cross_val_predict(build_pipeline(best_cfg), X, y, cv=StratifiedKFold(5, shuffle=True, random_state=SEED),
                            method="predict_proba")
    proba_idx = list(np.unique(y)).index(POS)
    p_oof = oof[:, proba_idx]
    table = threshold_table(p_oof, y.to_numpy())
    table.to_csv(os.path.join(out_dir, "threshold_table_oof.csv"), index=False)
    chosen = pick_thresholds(table)
    print("\nOut-of-fold policy thresholds (constraint: harmful ALLOW rate <= "
          f"{MAX_HARMFUL_ALLOW_RATE}, review load <= {MAX_REVIEW_LOAD}):", chosen or "no feasible pair")

    summary: dict[str, Any] = {
        "preset": args.preset, "n_configs": len(configs), "cv": grid["cv"], "seed": SEED,
        "search_seconds": elapsed, "selection_rule": "max mean CV ROC-AUC on training split; tie -> lower log loss",
        "best_config": best_cfg,
        "best_cv": {k: float(best[k]) for k in cols[:-1]},
        "a1_reference_cv": {k: float(ref[k]) for k in cols[:-1]},
        "paired_auc_diff_mean": float(diff.mean()), "paired_auc_diff_sd": float(diff.std()),
        "folds_better": int((diff > 0).sum()), "n_folds": int(len(diff)),
        "configs_within_1_se": int(len(near)),
        "oof_thresholds": chosen,
        "constraints": {"max_harmful_allow_rate": MAX_HARMFUL_ALLOW_RATE, "max_review_load": MAX_REVIEW_LOAD},
    }

    if args.final_test:
        Xte, yte = test_df["text"], test_df["label"]
        runs = [
            evaluate_once("A1 reference, policy 0.35/0.50", A1_CONFIG, (0.35, 0.50), X, y, Xte, yte),
            evaluate_once("selected config, policy 0.35/0.50", best_cfg, (0.35, 0.50), X, y, Xte, yte),
        ]
        if chosen:
            runs.append(evaluate_once("selected config, OOF-tuned thresholds", best_cfg,
                                      (chosen["review_lower"], chosen["block_above"]), X, y, Xte, yte))
        summary["final_test_evaluated_once"] = runs
        print("\nFINAL TEST (held-out split, evaluated once):")
        for r in runs:
            d = r["decisions_by_true_label"]
            print(f"  {r['name']:42} AUC {r['test_auc']:.3f} acc@0.5 {r['test_accuracy_at_0.5']:.3f} "
                  f"recall@0.5 {r['test_recall_at_0.5']:.3f} | benign {d['benign']} | harmful {d['harmful']}")

    with open(os.path.join(out_dir, "summary.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)
    print(f"\nwrote {out_dir}/all_configs.csv, threshold_table_oof.csv, summary.json")


if __name__ == "__main__":
    main()
