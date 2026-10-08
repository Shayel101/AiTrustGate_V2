"""Small, interpretable lexicon features that complement the TF-IDF word features.

JBB-Behaviors deliberately pairs each benign example with a topically identical
harmful one (e.g. "write a mining script" vs. "hijack a computer to mine crypto
covertly"). Plain word-frequency (TF-IDF) features struggle here because the
shared topic words dominate and the few words that actually carry intent get
diluted. These two counters give the model direct, human-inspectable signal for
that intent distinction, instead of hoping TF-IDF finds it implicitly.

This is still a simple, linear, scikit-learn-only pipeline (no embeddings, no
deep learning): TF-IDF word features + two numeric phrase-count features, fed
into Logistic Regression via FeatureUnion.
"""
from __future__ import annotations

import numpy as np
from sklearn.base import BaseEstimator, TransformerMixin

# Phrases more common in JBB's harmful framing (action/intent to cause harm or
# evade detection/consent).
INTENT_PHRASES = [
    "hack", "steal", "exploit", "bypass", "evade", "unauthorized", "illegal",
    "without consent", "without their consent", "without permission",
    "without direct access", "blackmail", "extort", "traffic", "hijack",
    "ransomware", "malware", "counterfeit", "phishing", "deepfake", "weapon",
    "bomb", "kill", "murder", "torture", "manipulate", "scam", "fraud",
    "launder", "cheat", "circumvent", "forge", "tamper", "poison", "sabotage",
    "smuggle", "abuse", "coerce", "evading detection", "avoid getting caught",
    "without getting caught", "get away with",
]

# Phrases more common in JBB's benign framing (descriptive/historical/fictional).
FRAMING_PHRASES = [
    "describe", "discuss", "explain", "history of", "typical", "standard",
    "general", "briefly", "fictional", "fiction", "story", "novel", "poem",
    "essay", "documentary", "research", "academic", "overview", "context of",
    "legislation", "developments", "biography", "listicle", "case study",
    "analysis", "fan fiction", "historical context",
]


class PhraseCountFeaturizer(BaseEstimator, TransformerMixin):
    """Counts (case-insensitive) occurrences of a fixed phrase list per document."""

    def __init__(self, phrases: list[str]) -> None:
        self.phrases = phrases

    def fit(self, X, y=None) -> "PhraseCountFeaturizer":
        return self

    def transform(self, X) -> np.ndarray:
        counts = np.zeros((len(X), 1))
        for i, text in enumerate(X):
            lowered = str(text).lower()
            counts[i, 0] = sum(lowered.count(phrase) for phrase in self.phrases)
        return counts
