"""SHA-256 file-integrity helpers used for reproducibility and tamper detection.

Two concrete uses in this project:
1. prepare_data.py checks the raw JBB-Behaviors CSVs against a pinned
   manifest (data/raw/CHECKSUMS.sha256) before loading them, so an
   accidentally (or deliberately) edited benchmark file is flagged instead of
   silently changing results.
2. train.py writes results/CHECKSUMS.sha256 after each run, so anyone can
   verify the committed results/ files were not modified by hand.
"""
from __future__ import annotations

import hashlib
import os


def sha256_file(path: str, chunk_size: int = 65536) -> str:
    """Return the hex SHA-256 digest of a file's contents."""
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_manifest(paths: list[str], manifest_path: str, base_dir: str) -> None:
    """Write a `sha256sum`-compatible manifest (hash + path relative to base_dir)."""
    lines = []
    for path in paths:
        if not os.path.exists(path):
            continue
        rel_path = os.path.relpath(path, base_dir)
        lines.append(f"{sha256_file(path)}  {rel_path}")
    with open(manifest_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def read_manifest(manifest_path: str) -> dict[str, str]:
    """Parse a `sha256sum`-format manifest into {relative_path: hash}."""
    entries: dict[str, str] = {}
    if not os.path.exists(manifest_path):
        return entries
    with open(manifest_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            digest, _, rel_path = line.partition("  ")
            entries[rel_path] = digest
    return entries


def check_against_manifest(paths: list[str], manifest_path: str, base_dir: str) -> list[str]:
    """Return a list of human-readable warnings for files that don't match the manifest.

    A missing manifest or a file absent from the manifest is not an error (e.g. a
    freshly re-downloaded file); only a *mismatched* hash for a file that IS in
    the manifest is flagged, since that indicates the file's contents changed.
    """
    expected = read_manifest(manifest_path)
    warnings: list[str] = []
    for path in paths:
        if not os.path.exists(path):
            continue
        rel_path = os.path.relpath(path, base_dir)
        expected_hash = expected.get(rel_path)
        if expected_hash is None:
            continue
        actual_hash = sha256_file(path)
        if actual_hash != expected_hash:
            warnings.append(
                f"{rel_path}: SHA-256 does not match data/raw/CHECKSUMS.sha256 "
                f"(expected {expected_hash[:16]}..., got {actual_hash[:16]}...). "
                "This file may have been hand-edited or re-downloaded from a "
                "different source; results/predictions may not be reproducible."
            )
    return warnings
