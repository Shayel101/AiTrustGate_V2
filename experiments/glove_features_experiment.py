"""Negative-result experiment: do pretrained GloVe word vectors lift the risk estimate to ~80% accuracy?

Needs `pip install gensim` (not in requirements.txt) and downloads glove-wiki-gigaword-100 (128 MB, GitHub-hosted) on first run.
CV on the TRAINING split only; the held-out split is never read. Run: python experiments/glove_features_experiment.py
Seed words below were written from general knowledge of harm categories, not from any dataset row.
"""
import os, re, sys, json, warnings
import numpy as np, pandas as pd
from gensim.models import KeyedVectors
import gensim.downloader as api
from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import RepeatedStratifiedKFold, cross_validate, train_test_split
from sklearn.pipeline import FeatureUnion, Pipeline
from sklearn.preprocessing import StandardScaler

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
from lexicon_features import FRAMING_PHRASES, INTENT_PHRASES, PhraseCountFeaturizer

kv = api.load("glove-wiki-gigaword-100")
df = pd.read_csv(os.path.join(ROOT, "data", "processed", "jbb_behavior_classifier.csv"))
train_df, test_df = train_test_split(df, test_size=0.2, random_state=42, stratify=df["label"])
X, y = train_df["text"], train_df["label"]

TOK = re.compile(r"[a-z]+")
def toks(t): return [w for w in TOK.findall(t.lower()) if w in kv.key_to_index]

# Seed words written from general knowledge of harm categories / benign framing (NOT from any dataset row).
HARM = "illegal crime criminal steal theft fraud scam hack attack weapon bomb kill murder violence abuse harass threaten blackmail extort exploit malware virus poison drug smuggle launder forge counterfeit cheat deceive manipulate stalk spy illegally secretly".split()
FRAME = "history historical describe explain discuss story fictional novel essay research academic overview general analysis documentary educational".split()
def centroid(words):
    v = np.mean([kv[w] for w in words if w in kv.key_to_index], axis=0); return v / np.linalg.norm(v)
CH, CF = centroid(HARM), centroid(FRAME)

def unit(v): n = np.linalg.norm(v); return v / n if n else v
cache = {}
def doc_feats(t):
    if t in cache: return cache[t]
    ws = toks(t)
    if not ws: f = np.zeros(100 + 6)
    else:
        V = np.array([kv[w] for w in ws]); mean = V.mean(0)
        U = V / np.linalg.norm(V, axis=1, keepdims=True)
        sh, sf = U @ CH, U @ CF
        f = np.concatenate([mean, [sh.max(), sh.mean(), sf.max(), sf.mean(), sh.max() - sf.max(), (sh > 0.5).sum()]])
    cache[t] = f; return f

class Emb(BaseEstimator, TransformerMixin):
    def __init__(self, part="mean"): self.part = part
    def fit(self, X, y=None): return self
    def transform(self, X):
        M = np.array([doc_feats(t) for t in X])
        return M[:, :100] if self.part == "mean" else M[:, 100:]

def build(use_tfidf=True, use_lex=True, lexw=3, mean_w=0.0, sem_w=0.0, C=2.0, min_df=2):
    parts, w = [], {}
    if use_tfidf: parts.append(("word", TfidfVectorizer(ngram_range=(1,1), min_df=min_df, sublinear_tf=True))); w["word"] = 1.0
    if use_lex:
        for n, ph in (("intent", INTENT_PHRASES), ("framing", FRAMING_PHRASES)):
            parts.append((n, Pipeline([("c", PhraseCountFeaturizer(ph)), ("s", StandardScaler())]))); w[n] = lexw
    if mean_w: parts.append(("mean", Pipeline([("e", Emb("mean")), ("s", StandardScaler())]))); w["mean"] = mean_w
    if sem_w: parts.append(("sem", Pipeline([("e", Emb("sem")), ("s", StandardScaler())]))); w["sem"] = sem_w
    return Pipeline([("f", FeatureUnion(parts, transformer_weights=w)), ("clf", LogisticRegression(C=C, max_iter=5000, random_state=42))])

cv = RepeatedStratifiedKFold(n_splits=5, n_repeats=5, random_state=42)
def run(name, **kw):
    r = cross_validate(build(**kw), X, y, cv=cv, scoring={"auc": "roc_auc", "acc": "accuracy"}, n_jobs=1)
    print(f"{name:55} AUC {r['test_auc'].mean():.4f}±{r['test_auc'].std():.3f}  acc@0.5 {r['test_acc'].mean():.4f}", flush=True)
    return r

run("A1-standard-best (tfidf+lex w3, C2, min_df2)")
for C in (0.05, 0.1, 0.3, 1.0):
    for mw in (0.1, 0.3, 1.0):
        run(f"+glove mean w={mw} C={C}", mean_w=mw, C=C)
for sw in (0.5, 1.0, 2.0):
    for C in (0.3, 1.0, 2.0):
        run(f"+semantic proto feats w={sw} C={C}", sem_w=sw, C=C)
for C in (0.1, 0.3, 1.0):
    run(f"semantic + glove mean + lex + tfidf C={C}", mean_w=0.3, sem_w=1.0, C=C)
    run(f"glove mean only C={C}", use_tfidf=False, use_lex=False, mean_w=1.0, C=C)
    run(f"semantic feats only C={C}", use_tfidf=False, use_lex=False, sem_w=1.0, C=C)
    run(f"lex + semantic (no tfidf, no mean) C={C}", use_tfidf=False, sem_w=1.0, C=C)

print("---- round 2: per-seed max-similarity features + other learners", flush=True)
from sklearn.svm import SVC
from sklearn.ensemble import HistGradientBoostingClassifier
SEEDS = sorted(set(w for w in HARM + FRAME if w in kv.key_to_index))
SV = np.array([unit(kv[w]) for w in SEEDS])
seed_cache = {}
def seed_feats(t):
    if t in seed_cache: return seed_cache[t]
    ws = toks(t)
    f = np.zeros(len(SEEDS)) if not ws else (np.array([unit(kv[w]) for w in ws]) @ SV.T).max(0)
    seed_cache[t] = f; return f
class Seed(BaseEstimator, TransformerMixin):
    def fit(self, X, y=None): return self
    def transform(self, X): return np.array([seed_feats(t) for t in X])
def run2(name, model):
    r = cross_validate(model, X, y, cv=cv, scoring={"auc": "roc_auc", "acc": "accuracy"}, n_jobs=1)
    print(f"{name:55} AUC {r['test_auc'].mean():.4f}±{r['test_auc'].std():.3f}  acc@0.5 {r['test_acc'].mean():.4f}", flush=True)
for C in (0.01, 0.03, 0.1, 0.3):
    run2(f"per-seed sim ({len(SEEDS)} feats) LR C={C}", Pipeline([("s", Seed()), ("sc", StandardScaler()), ("c", LogisticRegression(C=C, max_iter=5000))]))
sem = lambda: Pipeline([("e", Emb("sem")), ("s", StandardScaler())])
for C in (0.3, 1, 3):
    run2(f"semantic 6 feats + SVC rbf C={C}", Pipeline([("e", Emb("sem")), ("s", StandardScaler()), ("c", SVC(C=C, probability=True, random_state=42))]))
run2("semantic 6 feats + HistGB", Pipeline([("e", Emb("sem")), ("c", HistGradientBoostingClassifier(max_depth=2, max_iter=60, learning_rate=0.05, random_state=42))]))
fu = lambda: FeatureUnion([("seed", Pipeline([("s", Seed()), ("sc", StandardScaler())])), ("sem", sem()),
                           ("intent", Pipeline([("c", PhraseCountFeaturizer(INTENT_PHRASES)), ("s", StandardScaler())])),
                           ("framing", Pipeline([("c", PhraseCountFeaturizer(FRAMING_PHRASES)), ("s", StandardScaler())]))])
for C in (0.01, 0.03, 0.1):
    run2(f"seed-sim + semantic + lexicon counts LR C={C}", Pipeline([("f", fu()), ("c", LogisticRegression(C=C, max_iter=5000))]))
