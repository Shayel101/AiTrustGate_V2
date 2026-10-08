# Traceability matrix

Chain: **A1 evidence -> scenario -> domain concept -> event -> state transition -> invariant -> automated test.**
A1 IDs are defined in [a1_baseline.md](a1_baseline.md) (A1 itself did not number its items). Test references are checked by
`tests/test_model_consistency.py::test_every_test_referenced_in_the_documents_exists`; every event name and INV-01..06 appears here
(`test_traceability_matrix_covers_all_invariants_and_events`). Scenario IDs are those of [model_walkthrough.md](model_walkthrough.md).

## 1. Main matrix

| A1 ID | Requirement / problem (A1) | Scenario | Domain concept | Event | State transition | Invariant | Test |
|---|---|---|---|---|---|---|---|
| A1-WF | A request enters; the gate evaluates it | SCN-N1 | AgentAction (`llm_generate`) | ActionProposed | -> PROPOSED | INV-06 | `tests/test_state_transitions.py::test_allow_flow_reaches_executed` |
| A1-WF | request is canonicalized (A1 offline normalization) | SCN-N1 | RequestText, ToolName | ActionNormalized | T-01 PROPOSED -> NORMALIZED | - | `tests/test_validation.py::test_valid_action_is_accepted_and_normalized` |
| A1-WF | "Trust Gate evaluates risk" | SCN-N1, SCN-F1 | RiskScore, RiskAssessor port | RiskAssessed | T-02 NORMALIZED -> RISK_ASSESSED | INV-04 | `tests/test_state_transitions.py::test_decision_without_risk_assessment_is_refused` |
| A1-VAL (recall, FNR) / A1-COST | missing or invalid risk information must not let an action through (FN is the severe error) | SCN-A3 | RiskBand UNKNOWN | RiskAssessed (empty score), ActionBlocked | T-02, T-05 | INV-01, INV-04 | `tests/test_decision_rules.py::test_missing_risk_always_blocks` |
| A1-WF "Allow" | benign request is allowed through | SCN-N1 | DecisionType ALLOW, AuthorizationStatus | ActionAllowed | T-03 RISK_ASSESSED -> ALLOWED | INV-03, INV-04 | `tests/test_decision_rules.py::test_gate_applies_the_table_end_to_end` |
| A1-WF "Block" / A1-SC-A | harmful request is blocked | SCN-A1 | DecisionType BLOCK | ActionBlocked | T-05 RISK_ASSESSED -> BLOCKED | INV-01 | `tests/test_invariants.py::test_inv01_violation_is_detected` |
| A1-WF "if allowed, continues" | blocked requests do not reach the AI system | SCN-A1 | Tool execution | ToolExecutionStarted (refused) | forbidden BLOCKED -> EXECUTING | INV-01 | `tests/test_state_transitions.py::test_block_flow_is_terminal` |
| A1-WF "if allowed, continues" | allowed request is passed on | SCN-N1 | Tool execution | ToolExecutionStarted, ToolExecutionCompleted | T-08, T-10 ALLOWED -> EXECUTING -> EXECUTED | INV-03, INV-06 | `tests/test_state_transitions.py::test_allow_flow_reaches_executed` |
| A1-SC-B / A1-FP | uncertain/boundary requests are error-prone | SCN-B1 | RiskBand HIGH (benign request blocked) | ActionBlocked | T-05 | INV-04 | `tests/test_model_consistency.py::test_a2_decisions_never_allow_what_a1_labelled_harmful_on_the_committed_scores` |
| A1-NS | human review adds contextual judgement | SCN-B2 | ApprovalRequest, DecisionType REVIEW | HumanApprovalRequested | T-04 RISK_ASSESSED -> PENDING_APPROVAL | INV-02 | `tests/test_state_transitions.py::test_review_flow_approved_then_executed` |
| A1-NS | human review adds contextual judgement | SCN-B2 | ApprovalRequest (GRANTED) | HumanApprovalGranted | T-06 PENDING_APPROVAL -> APPROVED | INV-02, INV-03 | `tests/test_invariants.py::test_inv02_valid_pending_and_approved_executed_hold` |
| A1-NS | a human may say no | SCN-B3 | ApprovalRequest (REJECTED) | HumanApprovalRejected | T-07 PENDING_APPROVAL -> REJECTED | INV-02 | `tests/test_state_transitions.py::test_review_flow_rejected_is_terminal_and_never_executes` |
| A1-NG (not replacing human oversight) | execution of REVIEW actions needs approval | SCN-A2, SCN-A4 | AuthorizationStatus | (ToolExecutionStarted refused) | forbidden PENDING_APPROVAL -> EXECUTING | INV-02, INV-03 | `tests/test_invariants.py::test_inv02_violation_is_detected` |
| A1-NG | approval must come from an authorized human | SCN-A4 | PolicyConfig.reviewer_ids | (HumanApprovalGranted refused) | none (state unchanged) | INV-03 | `tests/test_state_transitions.py::test_unauthorized_reviewer_cannot_approve_and_state_is_unchanged` |
| A1-PROB (not auditable) | every decision and outcome is reconstructable | all | AuditRecord | AuditRecorded | after each transition | INV-05 | `tests/test_invariants.py::test_inv05_violation_is_detected` |
| A1-PROB (not auditable) | audit failure stops the gate | - | AuditStore port | AuditRecorded | - | INV-05 | `tests/test_invariants.py::test_inv05_gate_refuses_to_proceed_when_audit_store_drops_records` |
| A1-IMPL (classifier decides nothing alone) | policy, not model/agent, is the authority | SCN-B2, SCN-A2 | PolicyConfig, ExternalSideEffect | RiskAssessed, ActionAllowed / HumanApprovalRequested | T-03, T-04 | INV-04 | `tests/test_invariants.py::test_side_effect_authority_is_policy_not_agent` |
| A1-IMPL | the tool may fail; failure is recorded | (tests only) | EXECUTION_FAILED | ToolExecutionFailed | T-11 EXECUTING -> EXECUTION_FAILED | INV-05, INV-06 | `tests/test_state_transitions.py::test_tool_failure_is_recorded_and_terminal` |
| A1-VAL (reproducibility) | repeated runs give the same results | all | Clock, seeds, policy_version, model_version | - | - | - | `tests/test_model_consistency.py::test_walkthrough_scores_reproduce_by_refitting_the_a1_classifier` |
| A1-IMPL / A1-RES | A2 builds on A1's classifier without changing it | SCN-N1..F1 | RiskAssessor adapter | RiskAssessed | T-02 | INV-04 | `tests/test_model_consistency.py::test_refit_a1_labels_match_committed_a1_predictions_artifact` |
| A1-FN / A1-UA-2 | the lexicon misses synonyms ("bribe") | SCN-F1 | RiskScore (0.3146) | ActionAllowed | T-03 | INV-01..06 all hold (limit) | `tests/test_model_consistency.py::test_counterexample_cx1_a_harmful_request_is_allowed_while_every_invariant_holds` |
| A1-UA-2 | a normal request and the FN are not separable by threshold | SCN-N1 vs SCN-F1 | RiskScore | - | - | - | `tests/test_model_consistency.py::test_counterexample_cx2_no_threshold_on_the_risk_score_separates_the_a1_normal_and_false_negative_cases` |
| A1-UA-1 | REVIEW band untested on real data | all A1 rows | RiskBand MEDIUM | HumanApprovalRequested (never fires) | T-04 (not exercised by A1 rows) | - | `tests/test_model_consistency.py::test_counterexample_cx3_review_band_is_unused_on_the_a1_test_split` |
| A1-CON (single run, no repeats) | an authorized action runs at most once | - | Tool execution | ToolExecutionStarted (repeat refused) | forbidden EXECUTED -> EXECUTING | INV-06 | `tests/test_state_transitions.py::test_repeated_execution_is_refused_and_tool_runs_once` |
| A1-PROB (data handling) | audit keeps no request text | all | AuditRecord.text_sha256 | AuditRecorded | - | INV-05 | `tests/test_validation.py::test_audit_records_do_not_store_request_text` |

## 2. Event coverage

| Event | State transition(s) | Invariant(s) | Test |
|---|---|---|---|
| ActionProposed | creation -> PROPOSED | INV-06 | `tests/test_state_transitions.py::test_creation_and_stateless_events_are_never_transitions` |
| ActionNormalized | T-01 | - | `tests/test_validation.py::test_valid_action_is_accepted_and_normalized` |
| RiskAssessed | T-02 | INV-04 | `tests/test_state_transitions.py::test_decision_without_risk_assessment_is_refused` |
| ActionAllowed | T-03 | INV-03, INV-04 | `tests/test_state_transitions.py::test_allow_flow_reaches_executed` |
| HumanApprovalRequested | T-04 | INV-02 | `tests/test_state_transitions.py::test_review_flow_approved_then_executed` |
| ActionBlocked | T-05 | INV-01 | `tests/test_state_transitions.py::test_block_flow_is_terminal` |
| HumanApprovalGranted | T-06 | INV-02, INV-03 | `tests/test_state_transitions.py::test_duplicate_approval_is_refused` |
| HumanApprovalRejected | T-07 | INV-02 | `tests/test_state_transitions.py::test_review_flow_rejected_is_terminal_and_never_executes` |
| ToolExecutionStarted | T-08, T-09 | INV-01, INV-02, INV-03, INV-06 | `tests/test_state_transitions.py::test_execution_start_is_audited_before_the_tool_is_called` |
| ToolExecutionCompleted | T-10 | INV-06 | `tests/test_state_transitions.py::test_allow_flow_reaches_executed` |
| ToolExecutionFailed | T-11 | INV-05, INV-06 | `tests/test_state_transitions.py::test_tool_failure_is_recorded_and_terminal` |
| AuditRecorded | (stateless) | INV-05 | `tests/test_validation.py::test_audit_store_rejects_duplicate_ids_backwards_time_and_foreign_objects` |

## 3. Invariant coverage

| Invariant | Positive test | Violation test |
|---|---|---|
| INV-01 BlockedNeverExecutes | `tests/test_invariants.py::test_inv01_valid_blocked_action_holds` | `tests/test_invariants.py::test_inv01_violation_is_detected` |
| INV-02 ReviewRequiresGrantedApproval | `tests/test_invariants.py::test_inv02_valid_pending_and_approved_executed_hold` | `tests/test_invariants.py::test_inv02_violation_is_detected` |
| INV-03 ExecutionRequiresAuthorization | `tests/test_invariants.py::test_inv03_valid_allow_and_approved_paths_hold` | `tests/test_invariants.py::test_inv03_violation_is_detected` |
| INV-04 DecisionMatchesPolicy | `tests/test_invariants.py::test_inv04_valid_decisions_match_policy` | `tests/test_invariants.py::test_inv04_violation_is_detected` |
| INV-05 AuditComplete | `tests/test_invariants.py::test_inv05_valid_audit_is_complete_for_every_flow` | `tests/test_invariants.py::test_inv05_violation_is_detected` |
| INV-06 ExecutionAtMostOnceAndTerminalFinal | `tests/test_invariants.py::test_inv06_valid_histories_hold` | `tests/test_invariants.py::test_inv06_violation_is_detected` |

## 4. A1 items deliberately **not** traced to A2 behavior

A1-STK (stakeholder map), A1-SRC / A1-EV-* (sources), A1-AI (A1's AI log), A1-STOP-1/3: they are A1 evidence that A2 relies on or
leaves open; they have no executable counterpart in the A2 model. Open points: `unresolved_assumptions.md`.
