# Value objects

Value objects are defined by their value, immutable, and validated at construction. Implementation: `src/trustgate/values.py`
and `src/trustgate/policy.py`. "Strict" parsing means exact enum member/value; lower-case or near-miss strings are rejected
(`tests/test_validation.py::test_invalid_enum_values_are_rejected`).

| Name | Type | Valid values / range | Normalization | Validation | Null allowed? | Semantic meaning |
|---|---|---|---|---|---|---|
| RiskScore | frozen dataclass(float) | finite float in **[0, 1]** | `int` -> `float` | rejects NaN, inf, bool, strings, out-of-range (`test_risk_score_outside_unit_interval_or_non_numeric_is_rejected`) | **No.** "No estimate" is `None` one level up (`AgentAction.risk_score`) | Uncalibrated model output; higher = riskier. Not an authoritative probability (U-06). |
| RiskBand | enum | `LOW`, `MEDIUM`, `HIGH`, `UNKNOWN` | derived from score + policy | - | No (`UNKNOWN` represents absence) | `HIGH`: score > `block_above` (0.50); `MEDIUM`: 0.35 <= score <= 0.50; `LOW`: below 0.35; `UNKNOWN`: no score. Thresholds: A2 DESIGN DECISION, 0.50 mirrors A1's implicit label boundary. |
| DecisionType | str enum | `ALLOW`, `REVIEW`, `BLOCK` | none | strict | No | The gate's verdict. `REVIEW` is not in A1. |
| TrustDecision | frozen dataclass | `decision`, `rule_id` (DT-01..DT-12), `risk_score`, `risk_band`, `external_side_effect`, `policy_version`, `model_version` | - | must equal `decide(...)` of its inputs (INV-04) | `risk_score`, `model_version` may be None | Immutable record of how and why a decision was reached. |
| ExternalSideEffect | str enum | `NO`, `YES`, `UNKNOWN` | none | strict | No | Whether executing the tool changes something outside the gate. `UNKNOWN` is treated like `YES`. Authority: policy registry. |
| AuthorizationStatus | str enum | `NOT_AUTHORIZED`, `AUTHORIZED` | none | strict | No (default `NOT_AUTHORIZED`) | The only status that permits execution; set by the gate. |
| ApprovalStatus | str enum | `PENDING`, `GRANTED`, `REJECTED` | none | strict | No | Outcome of an approval request. |
| ActionState | str enum | 11 states ([state_model.md](state_model.md)) | none | strict | No | Lifecycle position. |
| EventType | str enum | 12 events ([domain_events.md](domain_events.md)) | none | strict | No | Event names. |
| Identifier (`action_id`, `request_id`, `reviewer_id`, `audit_id`) | validated `str` | `^[A-Za-z0-9][A-Za-z0-9._:-]{0,63}$` | none (never trimmed or lower-cased) | pattern; `None`, empty, whitespace, over 64 chars rejected | **No** | Opaque stable identifier. Implemented as a validated string rather than a wrapper class to keep the model small. |
| ToolName | normalized `str` | `^[a-z][a-z0-9_]{0,63}$` after trim + lower-case | trim, lower-case | pattern | **No** | Name of a tool known (or not) to the policy registry. |
| RequestText | normalized `str` | non-empty after trim, no NUL | Unicode NFC, trim | non-str, empty, NUL rejected | **No** | Untrusted user text. |
| Timestamp | tz-aware `datetime` (UTC) | any timezone-aware datetime | converted to UTC | naive datetimes, strings, ints rejected; must not precede the previous event of the same action | **No** | Time of an event (from an injected clock). |
| PolicyConfig | frozen dataclass | `review_lower`, `block_above` with `0 <= review_lower <= block_above <= 1`; tool registry; reviewer ids | tool names normalized | `test_invalid_thresholds_are_rejected`, `test_invalid_side_effect_registry_entry_is_rejected`, `test_invalid_reviewer_id_is_rejected` | No | Immutable, versioned (`policy_version = "policy-0.2.0"`) configuration. |

Considered and **not** adopted as value objects (no A1 evidence and no data to ground them; see `data_dictionary.md`):
`SensitivityLevel`, `ReversibilityLevel`, `PrivilegeLevel`.
