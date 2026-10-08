"""Data preparation for the AI Trust Gate baseline classifier.

Loads the official JBB-Behaviors harmful/benign CSV files from data/raw/,
normalizes them into a single labeled dataset, and writes the result to
data/processed/jbb_behavior_classifier.csv.

Usage:
    python src/prepare_data.py
"""
from __future__ import annotations

import os

import pandas as pd

from integrity import check_against_manifest, sha256_file, write_manifest

RANDOM_SEED = 42

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW_DIR = os.path.join(REPO_ROOT, "data", "raw")
PROCESSED_DIR = os.path.join(REPO_ROOT, "data", "processed")
HARMFUL_PATH = os.path.join(RAW_DIR, "harmful-behaviors.csv")
BENIGN_PATH = os.path.join(RAW_DIR, "benign-behaviors.csv")
OUTPUT_PATH = os.path.join(PROCESSED_DIR, "jbb_behavior_classifier.csv")
RAW_MANIFEST_PATH = os.path.join(RAW_DIR, "CHECKSUMS.sha256")


def _load_behaviors_csv(path: str, label: str, source_dataset: str) -> pd.DataFrame:
    """Load one JBB-Behaviors CSV and normalize it into text/label/category/source columns."""
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"Missing required dataset file: {path}\n"
            "Download it first, e.g.:\n"
            "  mkdir -p data/raw && cd data/raw\n"
            f"  curl -L -o {os.path.basename(path)} "
            "https://huggingface.co/datasets/JailbreakBench/JBB-Behaviors/resolve/main/data/"
            f"{os.path.basename(path)}"
        )

    df = pd.read_csv(path)
    required_columns = {"Index", "Goal", "Behavior", "Category", "Source"}
    missing = required_columns - set(df.columns)
    if missing:
        raise ValueError(f"{path} is missing expected columns: {missing}")

    normalized = pd.DataFrame(
        {
            # The Goal column is the request/prompt text used for classification.
            "text": df["Goal"].astype(str),
            "label": label,
            "category": df["Category"].astype(str),
            "source": df["Source"].astype(str),
            "behavior_id": source_dataset + "_" + df["Index"].astype(str),
        }
    )
    return normalized


def prepare_dataset() -> pd.DataFrame:
    """Combine harmful and benign behaviors into one shuffled, labeled dataset."""
    for warning in check_against_manifest([HARMFUL_PATH, BENIGN_PATH], RAW_MANIFEST_PATH, REPO_ROOT):
        print(f"WARNING: {warning}")

    harmful = _load_behaviors_csv(HARMFUL_PATH, label="harmful", source_dataset="harmful")
    benign = _load_behaviors_csv(BENIGN_PATH, label="benign", source_dataset="benign")

    combined = pd.concat([harmful, benign], ignore_index=True)
    # Fixed seed keeps row order (and therefore downstream splits) reproducible.
    shuffled = combined.sample(frac=1, random_state=RANDOM_SEED).reset_index(drop=True)

    os.makedirs(PROCESSED_DIR, exist_ok=True)
    shuffled.to_csv(OUTPUT_PATH, index=False)

    if not os.path.exists(RAW_MANIFEST_PATH):
        write_manifest([HARMFUL_PATH, BENIGN_PATH], RAW_MANIFEST_PATH, REPO_ROOT)
        print(f"Pinned raw-data checksums to {RAW_MANIFEST_PATH}")

    return shuffled


def main() -> None:
    df = prepare_dataset()
    print(f"Wrote {len(df)} rows to {OUTPUT_PATH}")
    print(df["label"].value_counts().to_string())
    print(f"data/processed SHA-256: {sha256_file(OUTPUT_PATH)[:16]}...")


if __name__ == "__main__":
    main()
