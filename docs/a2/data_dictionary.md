# Data dictionary

Every field is tied to a domain need or an A1 artifact. The prompt's candidate fields were all evaluated; those without
A1 evidence or a consumer in the decision rule are **deferred** and not implemented.

Status: **A1** = exists in A1; **A2** = adopted by A2 design; **DEFERRED** = evaluated, not adopted.
Retention values are **project-level design decisions, not legal advice and not enforced by code** (see `data_governance.md`).

## 1. Fields in the model

| Field | Type | Required | Meaning | Source | Authority | Validation | Sensitivity | Retention | Deletion | Status / domain need |
|---|---|---|---|---|---|---|---|---|---|---|
| request_id | identifier str | yes | Correlation id of the originating request (A1: `behavior_id` for dataset rows) | agent / caller | caller (opaque) | identifier pattern; non-null | internal | with audit record | delete with audit record | A1 + A2: links evidence to A1 rows |
| action_id | identifier str | yes | Unique id of one AgentAction | agent / caller | gate rejects duplicates | identifier pattern; unique per gate | internal | with audit record | delete with audit record | A2: entity identity |
| user_request (`request_text`) | str | yes | Text to be acted on (A1 `text` / JBB `Goal`) | user via agent | **untrusted**; gate only normalizes | non-empty, no NUL, NFC; non-str rejected | **sensitive: may contain personal data or secrets** | in memory for the life of the gate process only; **never written to the audit store** | dropped with the process; no persistence in A2 | A1 |
| tool_name | str | yes | Which tool the action targets (`llm_generate` for A1 requests) | agent | policy registry decides what it means | `^[a-z][a-z0-9_]{0,63}$` after normalization | internal | with audit record; in memory otherwise | as above | A2: needed to look up the side effect |
| tool_arguments | mapping | no (default empty) | Free-form arguments for the tool | agent | **untrusted**; not risk-assessed (U-07) | mapping with non-empty `str` keys | **sensitive** (may contain anything) | in memory only | as above | A2: part of the tool-action extension |
| risk_score | float in [0,1] or None | yes (value may be None) | Risk estimate for `request_text` | risk assessor | assessor is authoritative for the *estimate* only | `RiskScore` range check; non-numeric rejected; `None` = fail closed | internal | with audit record (`risk_score`) | with audit record | A1 (model output) + A2 |
| risk_level (`risk_band`) | enum | derived | LOW/MEDIUM/HIGH/UNKNOWN | policy function | policy | derived, never set by callers | internal | in decision | as above | A2 |
| decision | enum | yes after RISK_ASSESSED | ALLOW/REVIEW/BLOCK | policy evaluation | **Trust Gate / policy** (not the model) | strict enum; INV-04 recomputation | internal | with audit record | with audit record | A1 (Allow/Block) + A2 (REVIEW) |
| rule_id | str `DT-nn` | with decision | Which decision-table row fired | policy | policy | must be in table | internal | with audit record | with audit record | A2: explainability |
| state | enum | yes | Lifecycle position | gate | gate | transition table | internal | with audit record (`to_state`) | with audit record | A2 |
| authorization_status | enum | yes (default NOT_AUTHORIZED) | May the tool be called? | gate | **gate only** | INV-03 | internal | in memory | with the action | A2 |
| human_approved (`approval.status`) | enum PENDING/GRANTED/REJECTED | only for REVIEW | Reviewer's verdict (tri-state instead of a boolean, because "not yet decided" must differ from "no") | human reviewer | **authorized reviewer** | decided once; reviewer id valid and listed | internal | with audit record | with audit record | A2 |
| reviewer_id | identifier str | with approval verdict | Who decided | caller, checked against policy list | policy list | identifier + membership | internal; pseudonymous | with audit record | delete with audit record | A2 |
| external_side_effect | enum | derived | Does the tool change something outside the gate? | policy tool registry | **policy registry**, never the agent | enum; unknown tool -> UNKNOWN | internal | in decision | as above | A2: decision-table condition |
| timestamp | tz-aware datetime (UTC) | yes | When an event happened | injected clock | system clock | tz-aware; not before previous event | internal | with audit record | with audit record | A2: audit ordering |
| policy_version | str | yes | Version of thresholds + registry used | policy config | policy | non-empty | internal | with audit record | with audit record | A2: reproducible decisions |
| model_version | str or None | with risk result | Which assessor produced the score (`a1-tfidf-lexicon-logreg-C0.2-seed42`) | risk assessor | assessor | str | internal | with audit record | with audit record | A2 |
| audit_id | identifier str | yes | Unique id of one audit record | audit store | audit store | unique; pattern | internal | per retention | delete | A2 |
| text_sha256 | hex str | yes | SHA-256 of normalized `request_text` | gate | gate | computed, not supplied | internal; low-entropy text can be confirmed by guessing | with audit record | with audit record | A2: data minimization |

## 2. Prompt fields evaluated and **deferred** (not implemented)

| Field | Decision | Reason |
|---|---|---|
| data_sensitivity | DEFERRED | A1 has no sensitivity labelling; JBB `Category` is a *harm category*, not data sensitivity; no data source or consumer. |
| reversibility | DEFERRED | No A1 evidence; would need per-tool knowledge. Partly covered by `external_side_effect`. |
| privilege_level | DEFERRED | A1 has no user identity or privileges (U-05). |
| prompt_injection_indicator | DEFERRED | No detector exists in A1 or A2; a field nobody can fill truthfully would invite false confidence. Injection through `tool_arguments` remains an open gap (U-07). |

## 3. A1 dataset fields (offline pipeline, unchanged)

`text`, `label` (`benign`/`harmful`), `category`, `source`, `behavior_id` in `data/processed/jbb_behavior_classifier.csv`;
provenance in [data/README.md](../../data/README.md).

## 4. Validation rules (task section 27) and where they are tested

| ID | Rule | Test (all in `tests/`) |
|---|---|---|
| V-01 | invalid enum values rejected | `test_validation.py::test_invalid_enum_values_are_rejected` |
| V-02 | missing/malformed mandatory identifiers rejected | `test_validation.py::test_missing_or_malformed_identifiers_are_rejected` |
| V-03 | risk score outside [0,1] rejected | `test_validation.py::test_risk_score_outside_unit_interval_or_non_numeric_is_rejected` |
| V-04 | illegal state transitions rejected | `test_state_transitions.py::test_every_state_event_pair_is_allowed_iff_in_the_transition_table` |
| V-05 | execution without authorization rejected | `test_validation.py::test_execution_without_authorization_is_rejected` |
| V-06 | execution after BLOCK rejected | `test_validation.py::test_execution_after_block_is_rejected` |
| V-07 | execution after REVIEW without approval rejected | `test_validation.py::test_execution_after_review_without_approval_is_rejected` |
| V-08 | malformed tool action rejected | `test_validation.py::test_malformed_tool_name_is_rejected`, `test_malformed_tool_arguments_are_rejected`, `test_malformed_request_text_is_rejected` |
| V-09 | missing audit record detected | `test_invariants.py::test_inv05_violation_is_detected` |
| V-10 | invalid timestamps rejected | `test_validation.py::test_invalid_timestamps_are_rejected`, `test_event_timestamp_going_backwards_is_rejected` |
