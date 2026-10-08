## A2 summary: domain model and testable specification for the AI Trust Gate

**Problem/context.** A1 investigated a gate that screens LLM requests (TF-IDF + lexicon + Logistic Regression on the public JBB-Behaviors benchmark) and allows or blocks them. A2 turns that workflow into an executable domain model without rewriting A1; elements A1 lacks (REVIEW, human approval, audit, tool actions) are labelled design decisions.

**Domain model.** One lifecycle entity, `AgentAction` (A1's request), with `ApprovalRequest` and `AuditRecord`; value objects such as `RiskScore` in [0,1] and `DecisionType`. 11 states, 12 events, 12-row decision table (risk band x external side effect). The domain imports only the standard library; the A1 classifier is an adapter.

**Key invariants.** Six, e.g. a BLOCKed action never executes, a REVIEW action executes only after a granted approval, every event is audited, execution happens at most once.

**Test method.** 331 pytest tests: each invariant has passing and deliberately violating inputs; all 110 state-event pairs are tested; documents are parsed against code; an independent oracle checks the decision rule; the A1 model is re-fitted and matches A1's committed predictions (0 of 40 differ).

**Counterexample.** A1's harmful request `harmful_34` scores 0.3146, is ALLOWed and executed (simulated) while every invariant holds: invariants check process consistency, not risk-estimate quality. On A1's test split the REVIEW band is never used.

**Limitation.** Thresholds (0.35/0.50) are uncalibrated and untuned; tool arguments are not risk-scored; reviewers are not authenticated; refused attempts are not audited.

**AI and verification.** GitHub Copilot wrote code, tests and documents; checks were deterministic (pytest, mypy, clean re-run). Student review is pending.

**Reproducibility.** Python 3.13.7, pinned `requirements.txt` plus lock file, seed 42, policy-0.2.0; commands in README.
