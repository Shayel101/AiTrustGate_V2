# Verification evidence

All results in this file come from commands actually executed in this repository (Python 3.13.7, packages in `requirements-lock.txt`).
Raw output: `results/a2_test_output.txt` (pytest), `results/a2_walkthrough_output.txt` (walkthrough), `results/raw/a2_test_run1_failed_harness_defect.txt` (retained failed first run).
Limits of this evidence: see the note at the top of [ai-use-log.md](ai-use-log.md) - the same author (an AI assistant) wrote code, tests and documents; the
student's own review is pending.

## 1. Verification methods and what each one independently checks

| ID | Method | What it checks | Independent of | Evidence |
|---|---|---|---|---|
| V-1 | Documents parsed against code | The state-transition table in `state_model.md`, the event list in `domain_events.md`, and the 12-row table in `decision_table.md` equal `TRANSITIONS`, `EventType`, `DECISION_TABLE` | The code under test (the document is the reference) | `tests/test_model_consistency.py::test_state_model_document_matches_transition_table`, `tests/test_model_consistency.py::test_domain_events_document_matches_event_enum`, `tests/test_decision_rules.py::test_code_table_equals_documented_table` |
| V-2 | Second implementation (oracle) | `decide()` equals a separately written if/else rule on 107 scores x 3 side effects + missing score | `DECISION_TABLE` | `tests/test_decision_rules.py::test_decide_matches_independent_oracle_on_dense_grid` |
| V-3 | Exhaustive state x event matrix | All 11 states x 10 transition events (110 pairs): exactly the 11 listed transitions succeed, the other 99 raise and leave state unchanged | The hand-written flow tests | `tests/test_state_transitions.py::test_every_state_event_pair_is_allowed_iff_in_the_transition_table` |
| V-4 | Deliberate violations | Each of INV-01..06 is violated by direct field mutation (bypassing the guarded methods) and must be detected | The guarded methods | `tests/test_invariants.py::test_inv01_violation_is_detected` ... `test_inv06_violation_is_detected` |
| V-5 | Re-fit A1 against A1's committed results | The re-fitted A1 classifier thresholded at 0.5 reproduces all 40 committed test labels and the selected C (0.2) | A2 code | `results/processed/a1_consistency_check.json` (0 mismatches); `tests/test_model_consistency.py::test_refit_a1_labels_match_committed_a1_predictions_artifact`; slow test `tests/test_model_consistency.py::test_walkthrough_scores_reproduce_by_refitting_the_a1_classifier` |
| V-6 | A1 baseline checksum comparison | `results/CHECKSUMS.sha256` after re-running `prepare_data.py` + `train.py` equals the committed one | A2 | Done twice: before A2 changes (in the repo `.venv`) and in a clean checkout with a fresh venv; both identical |
| V-7 | Static type check | `mypy src/trustgate` | tests | `Success: no issues found in 11 source files` (mypy 2.4.0) |
| V-8 | Domain independence | Domain modules import only the standard library / `trustgate`; `sklearn` is imported only by the adapter | - | `tests/test_model_consistency.py::test_domain_modules_import_only_stdlib_or_the_domain_itself`, `tests/test_model_consistency.py::test_ml_libraries_are_confined_to_the_adapters_package` |
| V-9 | Document -> test links | Every test named in the invariants, traceability, decision-table, walkthrough, failures and verification documents exists | the prose | `tests/test_model_consistency.py::test_every_test_referenced_in_the_documents_exists` |
| V-10 | Clean re-run | Fresh Python 3.13.7 venv from `requirements.txt`, copy of the tree in `/tmp`, run `prepare_data.py`, `train.py`, `run_walkthrough.py`, `pytest` | the developer's `.venv` | A1 checksums identical; walkthrough output identical to the repository's (`diff` empty); see sections 2 and 4 for the pytest result |
| V-11 | Executed notebook | `notebooks/a2_walkthrough.ipynb` executed top to bottom with `nbclient`; outputs stored in the notebook | - | notebook file |

Not done (listed so nothing is implied): manual inspection by the student (pending), second human reviewer, upstream dataset byte comparison (U-13), calibration study (U-06), any
evaluation on data other than JBB-Behaviors.

## 2. Executed commands and real results

| Command | Result |
|---|---|
| `python src/prepare_data.py` (A1) | 200 rows (100 harmful, 100 benign); processed SHA-256 prefix `95c3af2fb3114a0a` |
| `python src/train.py` (A1) | unchanged A1 numbers: accuracy 0.700, recall (harmful) 0.950, precision 0.633; checksums identical to the committed manifest |
| `python src/compare_models.py` (A1) | regenerated `results/model_comparison.txt`; CV means 0.6706 / 0.5575 / 0.5369 / 0.5350 / 0.4725 / 0.4719 as in the A1 README |
| `python src/run_walkthrough.py` | 9 scenarios, 8 pass, **1 fail (SCN-F1, retained)**; 0 invariant violations in any scenario; A1 re-fit label mismatches: 0 |
| `python -m pytest -v` | final summary in section 3 and in `results/a2_test_output.txt` |
| `mypy src/trustgate --ignore-missing-imports` | no issues in 11 source files |

## 3. Final test run

Command: `python -m pytest -v > results/a2_test_output.txt` in the repository `.venv` (Python 3.13.7, pytest 9.1.1).
Last line of the saved output: `============================= 339 passed in 13.87s ==============================` (0 failed, 0 skipped; 331 before `tests/test_tuning.py` with 8 tests was added).
Breakdown by file: `tests/test_invariants.py` (INV-01..06 positive and violating cases, gate enforcement), `tests/test_state_transitions.py` (110 state x event pairs, flows, approvals, repeats),
`tests/test_decision_rules.py` (table, oracle, boundaries, properties), `tests/test_validation.py` (enums, ids, scores, tool actions, timestamps, audit),
`tests/test_model_consistency.py` (document/code consistency, domain independence, A1 consistency, counterexamples CX-1..CX-3).
A final clean-checkout re-run (fresh venv, copy of the final tree) is recorded in section 5.

## 4. Failed runs retained

| Run | Result | Cause | Fix |
|---|---|---|---|
| First pytest run (code tests only, `-k "not documented"`) | 15 failed, 266 passed | test-harness defect (R-1) | `ACTION_PROPOSED`/`AUDIT_RECORDED` excluded from the parametrization; see `failures_and_counterexamples.md` |
| Clean-checkout run (V-10), before the last documents existed | 4 failed, 327 passed | `verification.md` and `ai-use-log.md` not yet written (3 failures counting the reference check) plus one over-strict test (`test_ml_libraries_are_confined_to_the_adapters_package` grepped comments for "sklearn") | documents written; the test now inspects import statements |
| Repo run with a 259-byte draft `verification.md` | 1 failed, 330 passed | the draft was shorter than the 500-byte minimum enforced by `test_required_a2_document_exists_and_is_not_empty` | this document |

Example tests used for the V-9 reference check: `tests/test_invariants.py::test_inv05_gate_refuses_to_proceed_when_audit_store_drops_records`,
`tests/test_state_transitions.py::test_repeated_execution_is_refused_and_tool_runs_once`.

## 5. Final clean-checkout re-run (V-10)

Procedure: new venv from `requirements.txt` (Python 3.13.7), `rsync` of the final working tree (without `.venv`, `.git`, caches) to `/tmp/a2_checkout`, then in that copy:
`python src/prepare_data.py`, `python src/train.py`, `python src/run_walkthrough.py`, `python -m pytest -q`, `mypy src/trustgate --ignore-missing-imports`.
Observed: `shasum -a 256 -c results/CHECKSUMS.sha256` all `OK` and identical to the repository's manifest; `diff` of the walkthrough output and of
`results/raw/walkthrough_scenarios.json` against the repository's files was empty; `331 passed in 12.29s` (at that time, before `tests/test_tuning.py` was added); mypy `Success: no issues found in 11 source files`.

Additional A1 cross-check: the A1 README lists the hash prefix `aab3c4414b920479` for `results/model_comparison.txt`; the SHA-256 of the file regenerated in A2 starts with
`aab3c4414b920479` (see `results/A2_CHECKSUMS.sha256`), i.e. the regenerated file is byte-identical to the one A1 describes.
