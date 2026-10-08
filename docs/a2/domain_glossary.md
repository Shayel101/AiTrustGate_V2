# Domain glossary

Canonical vocabulary for the A2 domain model. Labels: **A1** = term exists in A1 files; **A2** = introduced in A2 (design decision).
Terminology conflicts found in the repository are listed in section 2. No A1 file or A1 code identifier was renamed.

## 1. Terms

| Term | Type | Definition | Synonyms | Forbidden / ambiguous usage | Source |
|---|---|---|---|---|---|
| Trust Gate | System / bounded context | The component that evaluates a proposed action before it is executed and returns a decision. | "gate", "trust layer" (assignment prompt) | Do not use for the underlying LLM, the classifier alone, or the reviewer. | A1 README "Workflow"; A2 |
| AgentAction | Entity (central) | One proposed unit of work that the gate evaluates and that may later be executed. Has identity (`action_id`) and a lifecycle (`ActionState`). | **request** (A1), tool call, command, operation | "request" alone is ambiguous: use *user request* for what a person typed and *AgentAction* for what the gate evaluates. "command"/"operation" are not used. | A1 "request" mapped (see 2.1); A2 |
| User request | Concept (attribute) | The text a person asked for. Stored as `AgentAction.request_text`. Untrusted. | prompt, `Goal` (JBB column), `text` (A1 code) | Not an entity: A1 never tracks it separately from the evaluated request. | A1 `prepare_data.py` |
| Tool | External concept | Something outside the gate that performs the work (A1: "the AI system"). Referenced only by `tool_name`. | "AI system" (A1), capability | Not a domain entity (no lifecycle inside the gate). | A1 "Workflow"; A2 |
| `llm_generate` | Value (tool name) | The pseudo-tool that represents "pass the request on to the AI system" - the only tool in A1. | - | Not a real API. | A2 |
| Risk assessor | Port / service | Supplies a risk estimate for an action. A1 implementation: TF-IDF + lexicon + Logistic Regression. | classifier, model | It estimates; it does **not** decide. | A1 `train.py`; A2 |
| Risk score | Value object | Number in [0, 1]; larger = riskier. Absent (`None`) if the assessor gave no estimate. | P(harmful), probability | Do not call it a "probability of harm" - it is an uncalibrated model output (U-06). | A2 |
| Risk band | Value object | `LOW`, `MEDIUM`, `HIGH` or `UNKNOWN`, derived from the score and the policy thresholds. | risk level (data dictionary alias) | - | A2 |
| Policy configuration | Value object | Immutable, versioned settings: band thresholds, tool side-effect registry, authorized reviewer ids. | policy | Not an entity: has no lifecycle in scope. | A2 |
| Policy evaluation | Action (verb phrase) | The pure function `decide(score, side effect, policy)` that maps conditions to a decision. | rule evaluation | Not an event: it changes no state by itself. | A2 |
| Decision | Value object | `TrustDecision`: `ALLOW`, `REVIEW` or `BLOCK` plus the rule id, inputs and versions it came from. | verdict, prediction (A1 `predicted_label`) | A decision is not a state and not an event. Do not call a model label a decision. | A1 (Allow/Block); A2 (REVIEW) |
| ALLOW | Decision value | Action may proceed to execution without human involvement. | allow (A1, lowercase) | - | A1 |
| BLOCK | Decision value | Action must not be executed; terminal. | block (A1) | "reject" is reserved for a human reviewer's rejection. | A1 |
| REVIEW | Decision value | Action needs a human reviewer's approval before it can be executed. | escalate | Not in A1. | A2 DESIGN DECISION |
| Human reviewer | External actor | A person (simulated in A2) named in the policy's reviewer list who grants or rejects approval. | approver | Not a domain entity; identified only by `reviewer_id`. | A1 "Non-software alternative"; A2 |
| Approval request | Entity | The pending question "may this action run?" created when the decision is REVIEW. | - | - | A2 |
| Approval | Outcome | `GRANTED` or `REJECTED` status of an approval request. | human_approved (data dictionary alias) | Approval is not authorization (see next row). | A2 |
| Authorization status | Value object | `AUTHORIZED` / `NOT_AUTHORIZED`: set by the gate itself (after ALLOW or a granted approval); the only thing that permits execution. | - | Not user identity or user permissions (A1 has none; U-05). | A2 |
| External side effect | Value object | `NO` / `YES` / `UNKNOWN`: whether executing the tool changes something outside the gate. Authority is the policy's tool registry, never the agent. | - | An agent-supplied claim is ignored. | A2 |
| Execution | Action | Calling the tool for an authorized action. Simulated in A2. | run, continue to the AI system (A1) | Never performed for real in this repository. | A1; A2 |
| Audit record | Entity | Immutable record of one event on one action (ids, states, timestamp, decision, versions, text digest). | log entry | Does not contain request text. | A1 "auditable" weakness; A2 |
| Audit store | Port | Append-only storage of audit records. | - | - | A2 |
| Event | Concept | A fact that happened and is recorded, named in the past tense (`ActionBlocked`). Triggers at most one state transition. | - | Not a state, not a decision. | A2 |
| State | Concept | Where an `AgentAction` is in its lifecycle (`BLOCKED`, `EXECUTED`, ...). | status | Decisions (`ALLOW`...) are not states. The state after ALLOW is `ALLOWED`. | A2 |
| Invariant | Concept | A condition that must hold in every reachable state (INV-01 ... INV-06). | - | - | A2 |
| Terminal state | Concept | State with no outgoing transition. | final state | - | A2 |
| Fail closed | Principle | On missing or unusable risk information the outcome is the stricter one (BLOCK). | - | - | A1-COST (false negatives are more severe); A2 |
| Benign / harmful | A1 label | Ground-truth class of a JBB-Behaviors row, and the A1 classifier's output. | - | A1 dataset labels, **not** domain states or decisions. | A1 |
| Normalize | Action | Canonicalize text (Unicode NFC, trim) and tool name (trim, lower-case). | - | Different from A1 `prepare_data.py` normalization, which is offline CSV shaping. | A2 |

Verbs: *propose, normalize, assess, decide, approve, reject, execute, record*. Each maps to exactly one method of `TrustGate`/`AgentAction`.

## 2. Terminology conflicts and canonical mapping

| # | Terms found | Where | Canonical term | Mapping / note |
|---|---|---|---|---|
| 2.1 | request / behavior / goal / text / prompt | A1 README ("request"), JBB CSV (`Goal`, `Behavior`), `prepare_data.py` (`text`) | **AgentAction** (entity) with attribute **request_text** | JBB `Goal` = `request_text`; JBB `Index`/`behavior_id` = `request_id`. JBB `Behavior` is a dataset-internal label and is not used. |
| 2.2 | action / tool call / command / operation | assignment prompt | **AgentAction**; the callable is the **tool** | "tool call" = executing an authorized AgentAction. |
| 2.3 | label / prediction / decision / verdict | A1 `predicted_label`; prompt `decision` | **Decision** for the gate output; **label** only for A1 dataset ground truth and A1 classifier output | A1 `harmful` -> score > 0.5 -> BLOCK; A1 `benign` -> score <= 0.5 -> ALLOW or REVIEW. |
| 2.4 | Allow / allow / ALLOW; Block / block / BLOCK | A1 prose vs code | Upper case `ALLOW`, `REVIEW`, `BLOCK` for the enum | Prose may use lower case. |
| 2.5 | risk / harmful probability / score | A1 prose and code | **risk score** (value), **risk band** (derived) | "risk level" in the prompt = risk band. |
| 2.6 | approval vs authorization | prompt | Distinct terms | Approval = reviewer's act. Authorization = status set by the gate. |
| 2.7 | AI/LLM (A1) vs Agent (prompt) vs Tool | A1 "AI system", prompt "agent" | The *proposer* of actions is the **agent** (outside the boundary); what executes is the **tool** | In A1 both are "the AI system". |
