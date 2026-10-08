"""Model/documentation/implementation consistency, domain independence, A1 consistency, and the retained counterexample."""
from __future__ import annotations

import ast
import json
import re
import sys
from pathlib import Path

import pandas as pd
import pytest
from conftest import submit

from trustgate import DecisionType, EventType, RiskScore, TRANSITIONS, decide, ExternalSideEffect, PolicyConfig, ActionState
from trustgate import invariants as inv_module
from trustgate.invariants import check_all

ROOT = Path(__file__).resolve().parents[1]
A2 = ROOT / "docs" / "a2"
PKG = ROOT / "src" / "trustgate"
REQUIRED_DOCS = [
    "domain_glossary", "context_map", "domain_events", "entities", "value_objects", "process_model", "state_model",
    "data_dictionary", "data_governance", "invariants", "decision_table", "model_walkthrough",
    "failures_and_counterexamples", "unresolved_assumptions", "traceability", "verification", "ai-use-log", "a1_baseline",
]


def _cells(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def _table_rows(doc: str, id_pattern: str) -> list[list[str]]:
    rows = []
    for line in (A2 / f"{doc}.md").read_text(encoding="utf-8").splitlines():
        if line.startswith("|"):
            cells = _cells(line)
            if re.fullmatch(id_pattern, cells[0]):
                rows.append(cells)
    return rows


# ---- required artifacts
@pytest.mark.parametrize("doc", REQUIRED_DOCS)
def test_required_a2_document_exists_and_is_not_empty(doc):
    assert (A2 / f"{doc}.md").stat().st_size > 500


# ---- domain independence (task section 26)
FORBIDDEN = {"sklearn", "pandas", "numpy", "scipy", "torch", "transformers", "openai", "huggingface_hub", "sentence_transformers", "tensorflow"}
DOMAIN_MODULES = [p for p in PKG.glob("*.py")]


@pytest.mark.parametrize("path", DOMAIN_MODULES, ids=lambda p: p.name)
def test_domain_modules_import_only_stdlib_or_the_domain_itself(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        names = []
        if isinstance(node, ast.Import):
            names = [a.name.split(".")[0] for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.level == 0:
            names = [(node.module or "").split(".")[0]]
        for n in names:
            assert n not in FORBIDDEN, f"{path.name} imports forbidden library {n}"
            assert n in sys.stdlib_module_names or n == "trustgate", f"{path.name} imports non-stdlib {n}"


def test_ml_libraries_are_confined_to_the_adapters_package():
    # Domain modules are import-checked above; here: the only place that imports sklearn is the adapter.
    importers = [p.name for p in PKG.rglob("*.py")
                 if re.search(r"^\s*(import|from)\s+sklearn", p.read_text(encoding="utf-8"), re.M)]
    assert importers == ["sklearn_risk.py"]


# ---- state model document == implementation
def test_state_model_document_matches_transition_table():
    documented = {(ActionState(r[1]), EventType(r[2])): set() for r in _table_rows("state_model", r"T-\d\d")}
    for r in _table_rows("state_model", r"T-\d\d"):
        documented[(ActionState(r[1]), EventType(r[2]))].add(ActionState(r[4]))
    assert documented == {k: set(v) for k, v in TRANSITIONS.items()}


def test_documented_terminal_states_match_code():
    text = (A2 / "state_model.md").read_text(encoding="utf-8")
    m = re.search(r"Terminal states:\s*(.+)", text)
    assert m and {s.strip(" `") for s in m[1].split(",")} == {"BLOCKED", "REJECTED", "EXECUTED", "EXECUTION_FAILED"}


def test_domain_events_document_matches_event_enum():
    documented = {r[1] for r in _table_rows("domain_events", r"EVT-\d\d")}
    assert documented == {e.value for e in EventType}


# ---- invariants document == implementation; referenced tests exist
def test_invariants_document_lists_exactly_the_implemented_invariants():
    text = (A2 / "invariants.md").read_text(encoding="utf-8")
    documented = set(re.findall(r"^Invariant ID:\s*(INV-\d\d)", text, re.M))
    implemented_fns = {n for n in dir(inv_module) if n.startswith("inv_")}
    assert documented == {f"INV-{i:02d}" for i in range(1, 7)}
    assert len(implemented_fns) == len(documented)


def _defined_tests(file_name: str) -> set[str]:
    return set(re.findall(r"^def (test_\w+)\(", (ROOT / "tests" / file_name).read_text(encoding="utf-8"), re.M))


@pytest.mark.parametrize("doc", ["invariants", "traceability", "decision_table", "model_walkthrough",
                                 "failures_and_counterexamples", "verification"])
def test_every_test_referenced_in_the_documents_exists(doc):
    text = (A2 / f"{doc}.md").read_text(encoding="utf-8")
    refs = re.findall(r"tests/(test_\w+\.py)::(test_\w+)", text)
    assert refs, f"{doc}.md references no tests"
    for file_name, name in refs:
        assert name in _defined_tests(file_name), f"{doc}.md references missing test {file_name}::{name}"


def test_traceability_matrix_covers_all_invariants_and_events():
    text = (A2 / "traceability.md").read_text(encoding="utf-8")
    for i in range(1, 7):
        assert f"INV-{i:02d}" in text
    for e in EventType:
        assert e.value in text


# ---- A1 consistency (committed artifacts)
def test_refit_a1_labels_match_committed_a1_predictions_artifact():
    check = json.loads((ROOT / "results" / "processed" / "a1_consistency_check.json").read_text())
    committed = json.loads((ROOT / "results" / "metrics.json").read_text())
    assert check["label_mismatches_vs_results_predictions_csv"] == 0
    assert check["selected_C_refit"] == check["selected_C_committed"] == committed["selected_C"]
    assert check["test_rows"] == committed["test_size"]


def test_a2_decisions_never_allow_what_a1_labelled_harmful_on_the_committed_scores():
    scores = pd.read_csv(ROOT / "results" / "raw" / "a1_test_split_risk_scores.csv")
    policy = PolicyConfig()
    for r in scores.itertuples():
        d = decide(RiskScore(r.risk_score), ExternalSideEffect.NO, policy).decision
        if r.a1_predicted_label == "harmful":
            assert d is DecisionType.BLOCK
        else:
            assert d is not DecisionType.BLOCK


@pytest.mark.slow
def test_walkthrough_scores_reproduce_by_refitting_the_a1_classifier():
    from trustgate.adapters.sklearn_risk import fit_a1_baseline

    df = pd.read_csv(ROOT / "data" / "processed" / "jbb_behavior_classifier.csv")
    assessor, _, test_df, _ = fit_a1_baseline(df)
    committed = pd.read_csv(ROOT / "results" / "raw" / "a1_test_split_risk_scores.csv").set_index("behavior_id")
    for r in test_df.itertuples():
        assert assessor.assess(r.text, "llm_generate", {}) == pytest.approx(committed.loc[r.behavior_id, "risk_score"], abs=1e-6)


# ---- retained counterexample (A2 requirement: keep negative results)
@pytest.fixture(scope="module")
def committed_scores() -> pd.DataFrame:
    return pd.read_csv(ROOT / "results" / "raw" / "a1_test_split_risk_scores.csv").set_index("behavior_id")


def test_counterexample_cx1_a_harmful_request_is_allowed_while_every_invariant_holds(make_env, committed_scores):
    """DESIGNED/OBSERVED COUNTEREXAMPLE (CX-1): A1's known false negative (harmful_34) is ALLOWed by A2.

    This test PASSES by asserting the limitation exists. It documents that INV-01..06 check process consistency,
    not whether the risk estimate is right. If it ever fails because harmful_34 is no longer ALLOWed, the model
    or policy changed and docs/a2/failures_and_counterexamples.md must be updated.
    """
    row = committed_scores.loc["harmful_34"]
    assert row["label"] == "harmful" and row["a1_predicted_label"] == "benign"
    env = make_env(score=float(row["risk_score"]))
    a = submit(env, "CX-1")
    env.gate.execute("CX-1")
    assert a.decision.decision is DecisionType.ALLOW and a.state is ActionState.EXECUTED  # wrong outcome, valid process
    assert check_all(a, env.audit.records_for("CX-1"), env.policy) == []


def test_counterexample_cx2_no_threshold_on_the_risk_score_separates_the_a1_normal_and_false_negative_cases(committed_scores):
    """DESIGNED/OBSERVED COUNTEREXAMPLE (CX-2): the A1 normal request scores HIGHER than the A1 false negative,
    so any threshold that would REVIEW/BLOCK harmful_34 also REVIEWs/BLOCKs the normal benign_84 request."""
    normal, fn = committed_scores.loc["benign_84"], committed_scores.loc["harmful_34"]
    assert normal["label"] == "benign" and fn["label"] == "harmful"
    assert normal["risk_score"] > fn["risk_score"]


def test_counterexample_cx3_review_band_is_unused_on_the_a1_test_split(committed_scores):
    """OBSERVED NEGATIVE RESULT (CX-3): with the a-priori band [0.35, 0.50] no A1 test row lands in REVIEW."""
    decisions = [decide(RiskScore(s), ExternalSideEffect.NO, PolicyConfig()).decision for s in committed_scores["risk_score"]]
    assert DecisionType.REVIEW not in decisions
