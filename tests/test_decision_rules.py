"""Decision rule (docs/a2/decision_table.md): table fidelity, independent oracle, boundaries, A1 compatibility."""
from __future__ import annotations

import re
from pathlib import Path

import pytest
from conftest import submit

from trustgate import DECISION_TABLE, DecisionType, ExternalSideEffect, PolicyConfig, RiskBand, RiskScore, ValidationError, decide, risk_band
from trustgate.policy import A1_DECISION_BOUNDARY, DEFAULT_REVIEW_LOWER

DOC = Path(__file__).resolve().parents[1] / "docs" / "a2" / "decision_table.md"
POLICY = PolicyConfig()
STRICTNESS = {DecisionType.ALLOW: 0, DecisionType.REVIEW: 1, DecisionType.BLOCK: 2}
EFFECTS = list(ExternalSideEffect)
GRID = [i / 100 for i in range(101)] + [0.3499999, 0.35, 0.3500001, 0.4999999, 0.5, 0.5000001]


def oracle(score, effect):
    """Independent re-statement of the rule from the prose in decision_table.md (not a copy of DECISION_TABLE)."""
    if score is None:
        return DecisionType.BLOCK            # no usable estimate: fail closed
    if score > 0.5:
        return DecisionType.BLOCK            # A1 boundary: harmful
    if score >= 0.35:
        return DecisionType.REVIEW           # uncertain band
    return DecisionType.ALLOW if effect is ExternalSideEffect.NO else DecisionType.REVIEW


def _doc_rows():
    rows = {}
    for line in DOC.read_text(encoding="utf-8").splitlines():
        m = re.match(r"\|\s*(DT-\d\d)\s*\|\s*(\w+)\s*\|\s*(\w+)\s*\|\s*(ALLOW|REVIEW|BLOCK)\s*\|", line)
        if m:
            rows[(RiskBand(m[2]), ExternalSideEffect(m[3]))] = (m[1], DecisionType(m[4]))
    return rows


def test_table_is_complete_over_all_condition_combinations():
    assert set(DECISION_TABLE) == {(b, e) for b in RiskBand for e in ExternalSideEffect}
    assert len(DECISION_TABLE) == 12


def test_code_table_equals_documented_table():
    assert _doc_rows() == DECISION_TABLE


@pytest.mark.parametrize("band,effect", sorted(DECISION_TABLE, key=lambda k: (k[0].value, k[1].value)))
def test_each_documented_row_is_produced_by_decide(band, effect):
    sample = {RiskBand.LOW: 0.10, RiskBand.MEDIUM: 0.40, RiskBand.HIGH: 0.90, RiskBand.UNKNOWN: None}[band]
    d = decide(None if sample is None else RiskScore(sample), effect, POLICY)
    rule_id, expected = _doc_rows()[(band, effect)]
    assert (d.rule_id, d.decision, d.risk_band) == (rule_id, expected, band)


def test_decide_matches_independent_oracle_on_dense_grid():
    for effect in EFFECTS:
        assert decide(None, effect, POLICY).decision == oracle(None, effect)
        for s in GRID:
            assert decide(RiskScore(s), effect, POLICY).decision == oracle(s, effect), (s, effect)


@pytest.mark.parametrize("score,band", [
    (0.0, RiskBand.LOW), (0.3499999, RiskBand.LOW), (0.35, RiskBand.MEDIUM), (0.5, RiskBand.MEDIUM),
    (0.5000001, RiskBand.HIGH), (1.0, RiskBand.HIGH),
])
def test_band_boundaries(score, band):
    assert risk_band(RiskScore(score), POLICY) is band


def test_thresholds_are_the_documented_defaults():
    assert (DEFAULT_REVIEW_LOWER, A1_DECISION_BOUNDARY) == (0.35, 0.50)


# ---- missing / unknown values
@pytest.mark.parametrize("effect", EFFECTS)
def test_missing_risk_always_blocks(effect):
    assert decide(None, effect, POLICY).decision is DecisionType.BLOCK


def test_unknown_side_effect_is_treated_like_yes():
    for s in GRID:
        assert decide(RiskScore(s), ExternalSideEffect.UNKNOWN, POLICY).decision == decide(RiskScore(s), ExternalSideEffect.YES, POLICY).decision


def test_unregistered_tool_is_unknown_and_goes_to_review_at_low_risk(make_env):
    a = submit(make_env(score=0.05), tool="some_unregistered_tool")
    assert a.decision.external_side_effect is ExternalSideEffect.UNKNOWN and a.decision.decision is DecisionType.REVIEW


# ---- properties
def test_decision_is_monotone_in_risk():
    for effect in EFFECTS:
        levels = [STRICTNESS[decide(RiskScore(s), effect, POLICY).decision] for s in sorted(GRID)]
        assert levels == sorted(levels)


def test_side_effect_never_makes_a_decision_less_strict():
    for s in GRID:
        no = STRICTNESS[decide(RiskScore(s), ExternalSideEffect.NO, POLICY).decision]
        yes = STRICTNESS[decide(RiskScore(s), ExternalSideEffect.YES, POLICY).decision]
        assert yes >= no


def test_a2_never_allows_what_a1_blocks_and_blocks_exactly_what_a1_labels_harmful():
    # A1 labels "harmful" iff P(harmful) > 0.5 (sklearn LogisticRegression, see README / src/train.py)
    for effect in EFFECTS:
        for s in GRID:
            d = decide(RiskScore(s), effect, POLICY).decision
            if s > 0.5:
                assert d is DecisionType.BLOCK
            if d is DecisionType.ALLOW:
                assert s <= 0.5


def test_decision_carries_policy_and_rule_provenance():
    d = decide(RiskScore(0.9), ExternalSideEffect.NO, POLICY, "model-x")
    assert (d.policy_version, d.model_version, d.rule_id) == ("policy-0.2.0", "model-x", "DT-04")


# ---- policy configuration validation
@pytest.mark.parametrize("lo,hi", [(0.6, 0.5), (-0.1, 0.5), (0.3, 1.1)])
def test_invalid_thresholds_are_rejected(lo, hi):
    with pytest.raises(ValidationError):
        PolicyConfig(review_lower=lo, block_above=hi)


def test_invalid_side_effect_registry_entry_is_rejected():
    with pytest.raises(ValidationError):
        PolicyConfig(tool_side_effects={"send_email": "NO"})
    with pytest.raises(ValidationError):
        PolicyConfig(tool_side_effects={"Bad Name": ExternalSideEffect.NO})


def test_invalid_reviewer_id_is_rejected():
    with pytest.raises(ValidationError):
        PolicyConfig(reviewer_ids=frozenset({""}))


def test_gate_applies_the_table_end_to_end(make_env):
    expected = {0.1: DecisionType.ALLOW, 0.4: DecisionType.REVIEW, 0.9: DecisionType.BLOCK}
    for score, decision in expected.items():
        assert submit(make_env(score=score)).decision.decision is decision
    assert submit(make_env(score=0.1), tool="send_email").decision.decision is DecisionType.REVIEW
