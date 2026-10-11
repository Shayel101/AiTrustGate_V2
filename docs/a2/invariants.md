# Invariants

Six invariants, implemented as pure predicates in `src/trustgate/invariants.py` and enforced at runtime by
`TrustGate` after every audited transition (`assert_invariants`). Each has a passing case, at least one deliberately violating input, and a test asserting detection. "Holds" means the predicate returns `True`.

A1 link: A1's gate is a pre-filter - a request judged harmful must not reach the AI system (A1-WF, A1-SC-A) and false negatives are the more severe failure (A1-COST). INV-02 and INV-05 derive from A1-NS (human review) and the A1-PROB weakness "not independently auditable" respectively and are A2 DESIGN DECISIONS.

```
Invariant ID: INV-01
Name: BlockedNeverExecutes
Formal statement: for every action a with a.decision = BLOCK:
    a.state = BLOCKED  AND  no event in a.history is ToolExecution{Started,Completed,Failed}
    AND a.authorization = NOT_AUTHORIZED
Business/domain justification: the whole point of the A1 gate is that a request judged harmful never reaches the AI system.
Preconditions: a decision has been issued.
Postconditions: the action is terminal and the tool was never called.
Violation example: an action with decision BLOCK whose state is set to EXECUTED (or whose authorization is AUTHORIZED, or whose
    history contains ToolExecutionStarted).
Expected system behavior: guarded methods refuse the transition (InvalidTransitionError); if a state is forged, check_all reports
    INV-01 and TrustGate raises InvariantViolation.
Automated test: tests/test_invariants.py::test_inv01_valid_blocked_action_holds,
    tests/test_invariants.py::test_inv01_violation_is_detected,
    tests/test_state_transitions.py::test_block_flow_is_terminal
```

```
Invariant ID: INV-02
Name: ReviewRequiresGrantedApproval
Formal statement: for every action a with a.decision = REVIEW that has started execution (state in {EXECUTING, EXECUTED,
    EXECUTION_FAILED} or a ToolExecution* event in history):
    a.approval exists AND a.approval.status = GRANTED AND a.approval.reviewer_id is non-empty
Business/domain justification: REVIEW exists so that a human, not the classifier, decides uncertain or consequential cases
    (A1-NS: human review contributes contextual judgement). Executing without that decision defeats its purpose.
Preconditions: decision is REVIEW.
Postconditions: execution implies a recorded human grant.
Violation example: a REVIEW action in state EXECUTED whose approval is missing, PENDING, REJECTED, or GRANTED without a reviewer id.
Expected system behavior: execution of PENDING_APPROVAL / REJECTED actions raises InvalidTransitionError; forged states are
    reported as INV-02.
Automated test: tests/test_invariants.py::test_inv02_valid_pending_and_approved_executed_hold,
    tests/test_invariants.py::test_inv02_violation_is_detected,
    tests/test_state_transitions.py::test_execution_without_approval_is_refused
```

```
Invariant ID: INV-03
Name: ExecutionRequiresAuthorization
Formal statement: (a started execution => a.decision exists AND a.authorization = AUTHORIZED) AND
    (a.authorization = AUTHORIZED => a.decision = ALLOW OR (a.decision = REVIEW AND a.approval.status = GRANTED))
Business/domain justification: authorization is the single permission to call a tool; it must be derivable only from the gate's
    own decision or a recorded approval, never forged or implied.
Preconditions: none.
Postconditions: execution and authorization are consistent with the decision trail.
Violation example: an EXECUTED action with NOT_AUTHORIZED; AUTHORIZED with no decision; AUTHORIZED while the approval is still PENDING.
Expected system behavior: start_execution raises AuthorizationError for NOT_AUTHORIZED actions; forged data is reported as INV-03.
Automated test: tests/test_invariants.py::test_inv03_valid_allow_and_approved_paths_hold,
    tests/test_invariants.py::test_inv03_violation_is_detected,
    tests/test_state_transitions.py::test_execution_without_authorization_is_refused_even_in_an_executable_state
```

```
Invariant ID: INV-04
Name: DecisionMatchesPolicy
Formal statement: for every action a with a decision d:
    d = decide(a.risk_score, policy.side_effect_for(a.tool_name), policy, a.model_version)  AND  d.risk_score = a.risk_score
Business/domain justification: the policy (not the model, not the agent) is the authority for the decision; a stored decision
    that cannot be reproduced from its recorded inputs indicates tampering or a bug.
Preconditions: a decision exists.
Postconditions: the decision is reproducible from recorded inputs and the active policy.
Violation example: risk score 0.9 with the decision flipped from BLOCK to ALLOW; risk score changed after the decision; a policy
    whose thresholds no longer reproduce the recorded decision.
Expected system behavior: check_all reports INV-04; TrustGate raises InvariantViolation.
Automated test: tests/test_invariants.py::test_inv04_valid_decisions_match_policy,
    tests/test_invariants.py::test_inv04_violation_is_detected
```

```
Invariant ID: INV-05
Name: AuditComplete
Formal statement: for every event e in a.history there exists an audit record r with r.action_id = a.action_id,
    r.event = e.event and r.to_state = e.to_state. (Hence every decision event and every terminal state is audited.)
Business/domain justification: A1-PROB: the current workflow is "not independently auditable". Every decision and terminal
    outcome must be reconstructable.
Preconditions: none.
Postconditions: the audit trail covers the whole history.
Violation example: the BLOCK decision event has no audit record; the audit list is empty; a record exists with a different to_state.
Expected system behavior: TrustGate checks after each append; a store that silently drops records makes the gate raise
    InvariantViolation before any further step (and before any tool call, because the execution-start record is written first).
Automated test: tests/test_invariants.py::test_inv05_valid_audit_is_complete_for_every_flow,
    tests/test_invariants.py::test_inv05_violation_is_detected,
    tests/test_invariants.py::test_inv05_gate_refuses_to_proceed_when_audit_store_drops_records
```

```
Invariant ID: INV-06
Name: ExecutionAtMostOnceAndTerminalFinal
Formal statement: count(ToolExecutionStarted in a.history) <= 1  AND  no event in a.history other than the last has a terminal
    to_state.
Business/domain justification: an authorized action must not run twice (duplicate side effects) and a terminal outcome
    (BLOCKED, REJECTED, EXECUTED, EXECUTION_FAILED) is final.
Preconditions: none.
Postconditions: history is a simple path ending at most once in a terminal state.
Violation example: two ToolExecutionStarted events; any event appended after EXECUTED.
Expected system behavior: repeated execute() raises InvalidTransitionError and the tool runs once; forged histories are
    reported as INV-06.
Automated test: tests/test_invariants.py::test_inv06_valid_histories_hold,
    tests/test_invariants.py::test_inv06_violation_is_detected,
    tests/test_state_transitions.py::test_repeated_execution_is_refused_and_tool_runs_once
```

## What the invariants do **not** guarantee

They check *process consistency*, not whether the risk estimate is right. A harmful request that the model scores low is ALLOWed with every invariant satisfied (counterexample CX-1, `failures_and_counterexamples.md`;
`tests/test_model_consistency.py::test_counterexample_cx1_a_harmful_request_is_allowed_while_every_invariant_holds`).
