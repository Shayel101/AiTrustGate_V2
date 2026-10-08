# Data governance: source, authority, quality, retention, deletion, privacy

Scope: the A2 prototype only. **No claim of legal or regulatory compliance is made**; none was checked against any
applicable policy or regulation. Values marked *PROJECT DESIGN DECISION* are prototype defaults, **documented but not
enforced by code** (there is no persistent store in A2; see U-10, U-11).

## 1. Source and authority per critical field

The principle: *the component that supplies a value is not automatically the authority for it.*

| Field | Source (where it originates) | Authority (who decides it is true / what it means) | Why |
|---|---|---|---|
| `request_text` | user, relayed by the agent | nobody - it is untrusted input | Content is validated and normalized only |
| `tool_name`, `tool_arguments` | agent | nobody for meaning; the **policy registry** gives meaning to `tool_name` | Agent cannot vouch for itself |
| `risk_score` | risk assessor (A1 classifier via adapter) | assessor for the **estimate**; **not** for the decision | A1 treats the classifier as a screen, never as the final authority; the architecture here keeps the decision in the policy |
| `external_side_effect` | policy configuration (tool registry) | policy configuration | Agent-declared side effects are ignored (`test_side_effect_authority_is_policy_not_agent`) |
| `decision`, `rule_id`, `authorization_status`, `state` | Trust Gate (policy evaluation) | **Trust Gate / policy** | Only the gate may authorize execution |
| `human_approved` (`approval.status`), `reviewer_id` | human reviewer | **authorized reviewer** (member of policy list) | Approval is a human act; authentication not modelled (U-04) |
| `timestamp` | injected clock (system clock in production) | system clock | Never taken from the agent |
| `policy_version` | policy configuration | policy configuration | - |
| `model_version` | risk assessor adapter | assessor adapter | Identifies A1 model + C + seed |
| `audit_id`, audit records | audit store | **audit store** ("what happened") | Append-only; not editable by the agent |
| tool outcome | external tool | nobody - recorded, not trusted | Only success/failure is kept |
| A1 `label`, `category`, `source` | JBB-Behaviors authors | JBB-Behaviors authors | Public benchmark; see `data/README.md` |

## 2. Quality rules

| Field | Validation | Missing-value behavior | Stale-data behavior | Conflicting-data behavior |
|---|---|---|---|---|
| `request_text` | non-empty, no NUL, str | **reject** at proposal (no entity, no audit - gap G-1) | n/a (point-in-time input) | n/a |
| ids | pattern; unique `action_id` | reject | n/a | duplicate `action_id` rejected |
| `tool_name` | pattern; registry lookup | reject if malformed; unregistered -> `UNKNOWN` side effect (treated like YES) | registry is read at decision time; later registry changes do not rewrite past decisions | agent claim vs registry: **registry wins**, claim ignored |
| `risk_score` | finite float in [0,1] | `None` -> **BLOCK** (fail closed, DT-01..03) | n/a; score is per action | out-of-range -> `ValidationError`, action stays NORMALIZED and can never execute |
| decision | recomputed by INV-04 | cannot be missing after RISK_ASSESSED | decisions are not re-evaluated; a changed policy does not apply retroactively (INV-04 will then flag mismatch if re-checked under a different policy - by design) | decision != recomputation -> INV-04 violated |
| `timestamp` | tz-aware; UTC; monotonic per action | reject | n/a | earlier-than-previous rejected |
| approval | decided once; reviewer listed | PENDING until decided; **no timeout** (D-5) | a stale PENDING approval never expires (U-02) | second verdict rejected (`InvalidTransitionError`) |

## 3. Retention (PROJECT DESIGN DECISION, not enforced)

| Data | Proposed retention | Rationale |
|---|---|---|
| Audit records (ids, states, decision, rule, versions, tool name, risk score, text digest) | 180 days | Long enough to investigate incidents in a semester-scale pilot; no raw text. The number is a placeholder (U-11). |
| ApprovalRequest verdicts | same as audit records | Needed to explain executions |
| Raw `request_text`, `tool_arguments` | **not persisted by the gate**; held in process memory for the life of the process only | Data minimization. Note: `TrustGate` keeps actions in a dict for the life of the process and has no purge method (limitation) |
| A1 dataset and results | for the life of the repository | Public benchmark and reproducibility evidence |
| Scenario fixtures | for the life of the repository | `SYNTHETIC DATA - GENERATED FOR PROTOTYPING` |

## 4. Deletion / anonymization when retention expires (PROJECT DESIGN DECISION, not implemented)

1. Delete expired audit records and approval records entirely; keep only aggregate counts (e.g. decisions per rule id per
   day) that contain no ids.
2. Do not delete audit records of an action that is still non-terminal.
3. Because `text_sha256` can confirm a guessed text, treat it as pseudonymous data, not anonymous data; delete it with the record.
4. Deleting must be logged as a separate administrative event (not designed in A2).

## 5. Privacy

| Topic | Position |
|---|---|
| Personal data | A2 uses no real personal data. User text in a real deployment could contain personal data, hence `request_text`/`tool_arguments` are classified **sensitive** and never written to the audit store. |
| Credentials / secrets | None in this repository: all identifiers are synthetic (`reviewer-sim-01`, `A-1`), no tokens or keys. A real deployment must assume users paste secrets into requests. |
| Sensitive content | A1 data contains descriptions of harmful behaviors (public benchmark). It is used for classification only; no behavior is executed. |
| Data minimization | Audit stores a SHA-256 digest instead of text (`test_audit_records_do_not_store_request_text`). |
| Masking / redaction | Not implemented. Any future log of raw text would need redaction first. |
| Access restrictions | Not implemented (no users, no storage). A real audit store and the reviewer UI would need role-based access; reviewers see action content. |
| Integrity | A1: SHA-256 manifests for raw data and results. A2: `results/A2_CHECKSUMS.sha256` over A2 outputs. Audit-store tamper-evidence is not implemented (U-10). |
