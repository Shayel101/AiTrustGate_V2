# A1 baseline: inventory, frozen workflow, and conflicts

Status: A2 baseline. Frozen at git commit `1cd7bb0` ("a2: freeze A1 baseline"). Everything below is **existing A1 evidence**
unless explicitly labelled otherwise. Nothing here was re-verified against external sources in A2 (see
[unresolved_assumptions.md](unresolved_assumptions.md), U-14).

Labels used in all A2 documents:

- **A1 EVIDENCE** - stated in the A1 files or produced by A1 code.
- **A2 DESIGN DECISION** - chosen in A2; not supported by A1 evidence.
- **ASSUMPTION** - unverified; listed in `unresolved_assumptions.md`.
- **VERIFIED (A2)** - checked by an executed command in this repository (see `verification.md`).

## 1. Inventory of A1 artifacts

A1 documentation lives in [README-A1.md](../../README-A1.md) (the A1 author merged `doc.md`, `docs/evidence_ledger.md`,
`docs/failure_analysis.md` and `docs/ISE_A1_evidence_brief.md` into it; the pre-merge files still exist in git commit
`0909099`). The assignment brief is [docs/ISE_assignment_brief.txt](../ISE_assignment_brief.txt).

| Required item | Found? | Location | A1 reference ID (assigned in A2; A1 did not number items) |
|---|---|---|---|
| Problem statement | Yes | README-A1 "Purpose and A1 problem" | A1-PROB |
| Evidence ledger | Yes (6 claims) | README "Evidence ledger" | A1-EV-1 ... A1-EV-6 |
| Stakeholder information | Yes (5 stakeholders; analysis, **not** interviews) | README "Stakeholder map" | A1-STK |
| Current workflow | Yes | README "Workflow", "Purpose" | A1-WF |
| Software / non-software comparison | Yes | README "Non-software alternative" | A1-NS |
| Normal scenario | Yes (`benign_84`) | README "Normal, boundary, and abuse scenarios" | A1-SC-N |
| Boundary scenario | Yes (`benign_14` vs `harmful_14`) | same | A1-SC-B |
| Abuse scenario | Yes (`harmful_20`) | same | A1-SC-A |
| Counterexample / failure | Yes (FN `harmful_34`; 11 FPs) | README "Failure / counterexample analysis" | A1-FN, A1-FP |
| Constraints | Partly (stakeholder constraints; limitations; semester scope) | README "Stakeholder map", "Limitations" | A1-CON |
| Value measures | Yes (recall, FNR, precision, FPR, F1, reproducibility) | README "Quantified pain..." | A1-VAL |
| Failure cost (asymmetric) | Yes (FN more severe than FP) | same | A1-COST |
| Non-goals | Yes | README "Semester scope, non-goals..." | A1-NG |
| Unresolved assumptions | Yes (4) | same | A1-UA-1 ... A1-UA-4 |
| Stop conditions | Yes (3) | same | A1-STOP-1 ... A1-STOP-3 |
| Source references | Yes (JailbreakBench paper, HF dataset card, GitHub repo, NIST AI RMF) | README "Evidence ledger", "Verification appendix" | A1-SRC |
| AI-use / source-verification log | Yes | README "AI assistance and source-verification log" | A1-AI |
| Dataset | Yes - **real public benchmark** JBB-Behaviors (100 harmful + 100 benign), not synthetic | `data/raw/*.csv`, `data/processed/jbb_behavior_classifier.csv` | A1-DATA |
| Implementation | Yes | `src/prepare_data.py`, `train.py`, `evaluate.py`, `lexicon_features.py`, `integrity.py`, `compare_models.py` | A1-IMPL |
| Results | Yes | `results/metrics.json`, `predictions.csv`, `evaluation.txt`, `CHECKSUMS.sha256` | A1-RES |
| Configuration | Partial | `requirements.txt` (minimum versions only), `.gitignore` | - |
| **Tests** | **No** | - | missing |
| **Notebooks** | **No** | - (the A1 brief says a notebook belongs in the repository) | missing |
| `results/model_comparison.txt` | **No** - cited by README but not in the repository | - | missing |

Missing items are recorded in `unresolved_assumptions.md` (M-1 ... M-3) rather than invented.

## 2. A1 workflow, normalized (A1 EVIDENCE)

README "Workflow":

```
User request -> AI/LLM receives request -> Trust Gate evaluates risk -> Allow or Block -> if allowed, request continues to the AI system
```

A1 gate output is a binary `benign` / `harmful` label from TF-IDF + intent/framing phrase counts + Logistic Regression
(`src/train.py`). The label is produced with `predict`, i.e. P(harmful) > 0.5. A1 never uses the probability.

## 3. Conflicts between the A2 assignment prompt and A1 (A1 version preserved)

| ID | A2 prompt assumes | A1 says / does | Resolution in A2 |
|---|---|---|---|
| C-1 | Gate evaluates a **tool-using agent's proposed action** | Gate screens a **user request text** before an LLM answers it | A1 kept. The domain term `AgentAction` is the canonical name for "the thing the gate evaluates"; an A1 request is an `AgentAction` with `tool_name = llm_generate`. Tool metadata is an optional A2 extension used only in synthetic scenarios. |
| C-2 | Decisions `ALLOW / REVIEW / BLOCK` | Only Allow / Block | `ALLOW` and `BLOCK` are A1. `REVIEW` is an **A2 DESIGN DECISION**. Compatibility is enforced: A2 blocks every request A1 labels harmful (INV via `test_a2_never_allows_what_a1_blocks_and_blocks_exactly_what_a1_labels_harmful`). |
| C-3 | Policy engine, human approval, tool execution, audit record are parts of the system | Not in A1. Human review appears only as the *non-software alternative* (A1-NS); "not independently auditable" appears as the weakness of the current workflow (A1-PROB) | Added as **A2 DESIGN DECISIONS**, each justified by those two A1 statements and flagged as unverified in `unresolved_assumptions.md`. |
| C-4 | Possible BGE-small embeddings, optional stronger safety model | A1 non-goals: "large or local LLMs, deep learning architectures, embeddings, web applications, databases, Docker/cloud" | Not adopted. The domain model is independent of any model (`RiskAssessor` port), so embeddings could be added later without changing the rules. |
| C-5 | "Current synthetic dataset" | No synthetic data. A1 uses the real public JBB-Behaviors benchmark and says so | Preserved. Only the A2 scenario fixtures for tool actions are synthetic and are labelled `SYNTHETIC DATA - GENERATED FOR PROTOTYPING`. |
| C-6 | Risk score in [0, 1] | A1 outputs hard labels | The re-fitted A1 pipeline's `predict_proba` is used as the score. **VERIFIED (A2):** thresholding it at 0.5 reproduces all 40 committed test predictions (`results/processed/a1_consistency_check.json`). Note: LR probabilities are not calibrated (U-06). |
| C-7 | Tool-argument, privilege, sensitivity, reversibility, injection fields | A1 only ever sees request text | Evaluated in `data_dictionary.md`; not adopted (no A1 evidence, no data to ground them). |
| C-8 | Gate placed before execution | README diagram shows "AI/LLM receives request" before "Trust Gate evaluates" | Treated as the same intent (screen before generation begins, per README "Purpose"). |
| C-9 | A repository that executes top-to-bottom | README "Setup" runs, but no tests, no lock file (`requirements.txt` has `>=` ranges), README says Python 3.10+ / verified 3.13.7 | `requirements.txt` now pins exact versions; `requirements-lock.txt` freezes the full environment. A1 README statements that this contradicts were updated (see section 5). |

## 4. A1 baseline reproduction (VERIFIED (A2))

Before any A2 change, `python src/prepare_data.py` and `python src/train.py` were re-run in the project's `.venv`
(Python 3.13.7). `results/CHECKSUMS.sha256` was byte-identical to the committed one, i.e. A1's headline numbers
(accuracy 0.700, recall 0.950, precision 0.633, 12 errors out of 40) reproduce.

## 5. A1 artifacts changed by A2 (nothing else was modified)

| File | Change | Why |
|---|---|---|
| `README.md` | Added an "ISE-A2" section and TOC entry; corrected the sentence that said `requirements.txt` pins only minimum versions and the "single documentation file" sentence | Reproducibility / accuracy |
| `requirements.txt` | Exact pins for direct dependencies, plus `pytest`, `nbformat`, `nbclient`, `ipykernel` | Freeze dependencies |
| `results/model_comparison.txt` | Regenerated by `python src/compare_models.py` (cited by A1, absent from repo) | Close A1 gap M-3 |
| `src/*.py` (A1 scripts) | **Not modified.** A2 imports `train.build_pipeline`, `train.C_GRID` etc. | Keep A1 frozen |
