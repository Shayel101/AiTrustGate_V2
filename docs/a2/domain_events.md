# Domain events

An **event** is a fact that has happened, recorded in the past tense. It is not an entity (no lifecycle of its own), not a
state (a condition that persists) and not a decision (a value). Every event except `AuditRecorded` is recorded in the
action's `history` and in the audit store, and triggers at most one state transition (see [state_model.md](state_model.md)).

A1 support column: **A1** = the A1 workflow contains this step; **A2** = A2 design decision.

## 1. Event catalog

| ID | Event | Triggering condition | Actor / source | Input | Affected entity | Resulting state | Side effects | Allowed in state(s) | A1 support |
|---|---|---|---|---|---|---|---|---|---|
| EVT-01 | ActionProposed | The agent submits a request/tool call that passes validation | Agent (untrusted) | `action_id`, `request_id`, `request_text`, `tool_name`, `tool_arguments` | AgentAction (created) | PROPOSED | Audit record | none (creation event; no prior state) | A1 (request enters the workflow) |
| EVT-02 | ActionNormalized | The gate canonicalizes text and tool name | Trust Gate | proposed action | AgentAction | NORMALIZED | Audit record | PROPOSED | A1 (offline normalization in `prepare_data.py`); runtime step is A2 |
| EVT-03 | RiskAssessed | The risk assessor returned a score in [0,1] or reported none | Risk assessor via gate | normalized `request_text` | AgentAction | RISK_ASSESSED | Stores `risk_score` (or none) and `model_version`; audit record | NORMALIZED | A1 ("Trust Gate evaluates risk") |
| EVT-04 | ActionAllowed | Policy evaluation yields ALLOW | Trust Gate (policy) | risk score, side effect, policy | AgentAction | ALLOWED | Sets `authorization = AUTHORIZED`; stores decision; audit record | RISK_ASSESSED | A1 ("Allow") |
| EVT-05 | HumanApprovalRequested | Policy evaluation yields REVIEW | Trust Gate (policy) | same | AgentAction; ApprovalRequest (created) | PENDING_APPROVAL | Creates `ApprovalRequest` (PENDING); stores decision; audit record | RISK_ASSESSED | A2 (A1 only names human review as the non-software alternative) |
| EVT-06 | ActionBlocked | Policy evaluation yields BLOCK | Trust Gate (policy) | same | AgentAction | BLOCKED | Stores decision; authorization stays NOT_AUTHORIZED; audit record | RISK_ASSESSED | A1 ("Block") |
| EVT-07 | HumanApprovalGranted | An authorized reviewer grants the pending request | Human reviewer | `action_id`, `reviewer_id` | AgentAction; ApprovalRequest | APPROVED | Approval -> GRANTED; `authorization = AUTHORIZED`; audit record | PENDING_APPROVAL | A2 |
| EVT-08 | HumanApprovalRejected | An authorized reviewer rejects the pending request | Human reviewer | `action_id`, `reviewer_id` | AgentAction; ApprovalRequest | REJECTED | Approval -> REJECTED; audit record | PENDING_APPROVAL | A2 |
| EVT-09 | ToolExecutionStarted | Execution requested for an AUTHORIZED action in ALLOWED or APPROVED | Trust Gate | `action_id` | AgentAction | EXECUTING | Audit record written **before** the tool is called | ALLOWED, APPROVED | A1 ("if allowed, request continues to the AI system") |
| EVT-10 | ToolExecutionCompleted | The tool returned without error | Tool (untrusted) via gate | tool result (not stored) | AgentAction | EXECUTED | Audit record | EXECUTING | A1 (implicit) |
| EVT-11 | ToolExecutionFailed | The tool raised an error | Tool (untrusted) via gate | error (class/detail not stored) | AgentAction | EXECUTION_FAILED | Audit record | EXECUTING | A2 |
| EVT-12 | AuditRecorded | An audit record was appended to the store | Audit store | audit record | AuditRecord (created) | none (stateless event) | Append-only write | any time after EVT-01 | A1 weakness "not independently auditable"; A2 |

In every state **not** listed in "Allowed in state(s)" the event is forbidden and raises `InvalidTransitionError`
(`tests/test_state_transitions.py::test_every_state_event_pair_is_allowed_iff_in_the_transition_table`
exercises all 11 states x 10 transition events).

## 2. Candidate events considered and not adopted

| Candidate | Decision | Reason |
|---|---|---|
| ActionRequested | Merged into EVT-01 | A1 has no step between the user's request and the evaluated request; the user's text is an attribute (`request_text`). |
| PolicyEvaluated | Not an event | Policy evaluation is a pure function (an *action*); it changes no state by itself. Its result is recorded by EVT-04/05/06. |
| DecisionIssued | Split into EVT-04, EVT-05, EVT-06 | Each outcome has a different guard, side effect and target state; the decision value itself is the `TrustDecision` value object. |
| RiskAssessmentFailed | Not adopted | "No usable estimate" is `RiskAssessed` with an empty score (decision table rows DT-01..03 -> BLOCK). |
| ValidationFailed / ExecutionDenied | Not adopted | Refused inputs and refused transitions raise exceptions and create no event. **Known gap:** such attempts are not audited (G-1 in `failures_and_counterexamples.md`). |

## 3. Machine-readable catalog

The authoritative machine-readable event list is the `EventType` enum in `src/trustgate/values.py` and the `TRANSITIONS`
table in `src/trustgate/entities.py`; `tests/test_model_consistency.py::test_domain_events_document_matches_event_enum`
fails if this document and the enum diverge. No separate JSON catalog was created, to avoid a third copy.
