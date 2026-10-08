# Decision table: ALLOW / REVIEW / BLOCK

**Material rule chosen:** whether a proposed action is `ALLOW`ed, sent to `REVIEW`, or `BLOCK`ed (A1's "Allow or Block" step,
extended with `REVIEW`). Implemented in `src/trustgate/policy.py` (`DECISION_TABLE`, `risk_band`, `decide`).

## 1. What is A1 evidence and what is design

| Element | Status |
|---|---|
| Two outcomes ALLOW / BLOCK; harmful request must not reach the AI system | **A1 EVIDENCE** (A1-WF) |
| Block boundary at risk score 0.50 | **A1 EVIDENCE (code-derived)**: sklearn `LogisticRegression.predict` returns "harmful" iff P(harmful) > 0.5. **VERIFIED (A2):** all 40 committed test labels are reproduced by thresholding the re-fitted model at 0.5 (`results/processed/a1_consistency_check.json`). |
| Fail closed when risk is unknown | **PROJECT DESIGN DECISION**, motivated by A1-COST (false negatives are more severe than false positives) |
| REVIEW outcome and its band `0.35 <= score <= 0.50` | **PROJECT DESIGN DECISION.** 0.35 is an a-priori value, **not** tuned on any data (U-01). Nothing in A1 supports this number. |
| Low-risk action with an external side effect (or unknown side effect) goes to REVIEW | **PROJECT DESIGN DECISION** (A2 tool-action extension; A1 has no side effects) |
| Unknown side effect treated like YES | **PROJECT DESIGN DECISION** (conservative default) |

## 2. Conditions

| Condition | Values | Derived from |
|---|---|---|
| RiskBand | `UNKNOWN` (no score), `LOW` (score < 0.35), `MEDIUM` (0.35 <= score <= 0.50), `HIGH` (score > 0.50) | risk score + `PolicyConfig(review_lower=0.35, block_above=0.50)` |
| ExternalSideEffect | `NO`, `YES`, `UNKNOWN` | policy tool registry (`llm_generate` = NO; unregistered tool = UNKNOWN) |

## 3. Complete table (4 x 3 = 12 rows; every combination appears exactly once)

| Rule | RiskBand | ExternalSideEffect | Decision | Rationale |
|---|---|---|---|---|
| DT-01 | UNKNOWN | NO | BLOCK | No usable risk estimate: fail closed |
| DT-02 | UNKNOWN | YES | BLOCK | Fail closed |
| DT-03 | UNKNOWN | UNKNOWN | BLOCK | Fail closed |
| DT-04 | HIGH | NO | BLOCK | A1: labelled harmful |
| DT-05 | HIGH | YES | BLOCK | A1: labelled harmful |
| DT-06 | HIGH | UNKNOWN | BLOCK | A1: labelled harmful |
| DT-07 | MEDIUM | NO | REVIEW | Uncertain band, human judgement (A1-NS) |
| DT-08 | MEDIUM | YES | REVIEW | Uncertain and consequential |
| DT-09 | MEDIUM | UNKNOWN | REVIEW | Uncertain band |
| DT-10 | LOW | NO | ALLOW | A1: labelled benign, nothing external changes |
| DT-11 | LOW | YES | REVIEW | Low risk but consequential: a human confirms |
| DT-12 | LOW | UNKNOWN | REVIEW | Unknown tool: never silently allowed |

## 4. Default and missing-value behavior

- Missing risk score -> `UNKNOWN` band -> **BLOCK** (rows DT-01..03).
- Out-of-range, NaN, or non-numeric score is **not** a decision input: construction of `RiskScore` raises `ValidationError`; the action
  stays `NORMALIZED` and cannot execute (`test_assessor_returning_out_of_range_score_leaves_action_unexecutable`).
- Missing side-effect knowledge -> `UNKNOWN` -> behaves like `YES`.
- Agent-declared side effects are ignored (`test_side_effect_authority_is_policy_not_agent`).
- There is no "default" row: the table is total; `decide` indexes it directly and a missing key would raise `KeyError`
  (`test_table_is_complete_over_all_condition_combinations`).

## 5. Properties verified by tests

| Property | Test |
|---|---|
| Table in this document equals `DECISION_TABLE` in code (parsed from this file) | `tests/test_decision_rules.py::test_code_table_equals_documented_table` |
| Each of the 12 rows is produced by `decide` | `tests/test_decision_rules.py::test_each_documented_row_is_produced_by_decide` |
| Independent oracle (separately written if/else) agrees on a dense grid of 107 scores x 3 effects + missing score | `tests/test_decision_rules.py::test_decide_matches_independent_oracle_on_dense_grid` |
| Band boundaries (0.3499999, 0.35, 0.5, 0.5000001) | `tests/test_decision_rules.py::test_band_boundaries` |
| Missing risk always blocks | `tests/test_decision_rules.py::test_missing_risk_always_blocks` |
| Monotone in risk; side effect never relaxes a decision | `tests/test_decision_rules.py::test_decision_is_monotone_in_risk`, `tests/test_decision_rules.py::test_side_effect_never_makes_a_decision_less_strict` |
| A1 compatibility: score > 0.5 always BLOCK; ALLOW only if score <= 0.5 (A2 never allows what A1 blocks) | `tests/test_decision_rules.py::test_a2_never_allows_what_a1_blocks_and_blocks_exactly_what_a1_labels_harmful` |
| Policy config rejects invalid thresholds | `tests/test_decision_rules.py::test_invalid_thresholds_are_rejected` |
| End to end through the gate | `tests/test_decision_rules.py::test_gate_applies_the_table_end_to_end` |

## 6. Known limits of this rule

- The thresholds are **not validated**: on the A1 test split the REVIEW band is never used (CX-3), and the A1 false negative scores
  below it (CX-1, CX-2). See `failures_and_counterexamples.md`.
- The score is an uncalibrated Logistic Regression output (U-06), so "0.35" has no probabilistic meaning.
