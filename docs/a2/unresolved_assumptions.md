# Unresolved assumptions and missing artifacts

Nothing below is converted into a fact. "Status" values: **open** (not verified), **partly** (some evidence), **A1-open** (already
open in A1). Source IDs: A1-UA-n = A1's own unresolved assumptions (README "Semester scope, non-goals, assumptions, and stop conditions").

## 1. Missing A1 artifacts

| ID | Missing artifact | Why it matters | Can A2 proceed without it? | Verification needed |
|---|---|---|---|---|
| M-1 | Tests for A1 code (no `tests/` existed) | No automated check that A1 scripts keep working | Yes. A2 added tests for the A2 model; A1 reproduction is checked by `results/processed/a1_consistency_check.json` and the checksum comparison in `verification.md` | A1 author may add unit tests for `evaluate.py`, `integrity.py`, `lexicon_features.py` |
| M-2 | Notebook (A1 brief says a notebook belongs in the repository) | Brief asks for executable top-to-bottom evidence | Yes. `notebooks/a2_walkthrough.ipynb` was added for A2 only; an A1 notebook was not created (A1 is not rewritten) | Decide whether A1 resubmission needs one |
| M-3 | `results/model_comparison.txt` (cited by README) | A1's reproducibility claim | Yes | Regenerated in A2 (R-2); table values match README |
| M-4 | Interviews / observed users | A1 stakeholder map is an analysis, not field evidence | Yes, but A2 cannot claim stakeholder validation | Real stakeholder input would be needed; none is fabricated here |
| M-5 | License and upstream revision of the dataset not recorded in A1 | Provenance | Yes | License **verified** on the dataset card on 2026-10-08 (MIT). Upstream revision not recorded: open (U-13) |

## 2. Assumptions

| ID | Assumption | Evidence currently available | Why it matters | Risk if false | How it could be verified | Status |
|---|---|---|---|---|---|---|
| U-01 | REVIEW lower threshold 0.35 is a sensible boundary | None; chosen a priori. On the A1 test split no row falls in the band (CX-3) | Determines how much goes to humans vs ALLOW | Too low: reviewer overload. Too high: false negatives pass (CX-1/CX-2) | Choose it by out-of-fold scores on the **training** split only, then evaluate once on the test split; measure reviewer load. **Partly done:** `src/tune_config.py` computes out-of-fold thresholds on the training split (`results/tuning/*/threshold_table_oof.csv`); they are a candidate, not adopted, and rest on 160 rows and an invented review-load budget of 30% | partly |
| U-02 | Adding REVIEW improves outcomes (catches errors, acceptable latency) | None for A1 data; CX-3 shows no effect there. No timeout (G-4) | Core A2 extension | REVIEW adds cost with no safety gain | Run on a larger or non-paired set; measure recovered FPs/caught FNs and review time | open |
| U-03 | The tool side-effect registry is complete and correct | Only 3 simulated tools | Authority for DT-11/DT-12 | A mislabelled tool (e.g. side effect marked NO) is ALLOWed | Review registry per real tool; default is UNKNOWN (safe) | open |
| U-04 | Reviewers are real, authenticated and competent; the allowlist is trustworthy | A1-NS only says humans bring judgement and also introduce "latency and reviewer inconsistency" | Approval is an authorization step | Forged approvals; inconsistent verdicts | Authentication design; inter-reviewer agreement study | open |
| U-05 | User identity and per-user permissions are out of scope | A1-UA-4: request text alone is assumed sufficient | "Authorization" here means the gate's own status, not the user's rights | A user lacking rights could still get ALLOW | Add identity to the model | A1-open |
| U-06 | The A1 Logistic Regression score behaves like a usable risk measure | Only that thresholding at 0.5 reproduces A1 labels (VERIFIED) | Thresholds 0.35/0.50 assume score order matters; probabilities are not calibrated | Bands have no probabilistic meaning | Calibration analysis (reliability diagram) on held-out data | open |
| U-07 | `tool_arguments` can stay unscored | None (A1 never saw them) | Injection or harmful payload in arguments | Harmful action with innocuous text is ALLOWed | Extend the assessor and re-evaluate | open |
| U-08 | Behavior on JBB-Behaviors transfers to real agent actions | None; A1-UA-1 says transfer is unverified; JBB is topic-paired, English, 200 rows | All metrics describe this split only | Real-world error rates unknown | Evaluate on real, non-paired traffic | A1-open |
| U-09 | Approval binds to what executes | None (G-3) | TOCTOU | A reviewer approves A, B executes | Bind approval to a digest of normalized text + arguments and re-check at execution | open |
| U-10 | In-memory audit store is adequate | Prototype only | Durability, tamper evidence, access control | Lost or altered audit trail | Persistent append-only store with integrity chain | open |
| U-11 | Retention of 180 days and deletion rules; `text_sha256` is not re-identifying | None; design placeholder; no legal review | Privacy | Over-retention; short texts can be confirmed by guessing the hash | Policy owner and legal review (not done) | open |
| U-12 | Single process, sequential use | Code has no locks | Concurrency | Double execution under races (INV-06 is only checked per object) | Concurrency tests / transactional store | open |
| U-13 | The committed raw CSVs are byte-identical to the upstream files | A1 README: files were reconstructed via a web-fetch tool because `curl` failed; A1 pins checksums of **its own copies**. A2 retried `curl` on 2026-10-08: connection timed out (no upstream bytes obtained) | Dataset provenance | Training data could differ from the official benchmark | Download from the official source on a networked machine and compare SHA-256 to `data/raw/CHECKSUMS.sha256` | open |
| U-14 | A1 evidence-ledger claims (paper, NIST dates, DOI) are correct | A1 states they were checked; A2 did **not** re-verify them (only the dataset license and 100/100 row counts on the dataset card were seen on 2026-10-08) | Citations | Wrong claims carried forward | Re-read the sources | A1-open |
| U-15 | A hand-curated lexicon + TF-IDF is an adequate risk proxy | A1-UA-2; CX-1 shows a failure | Quality of the estimate | Evasion by synonyms | Compare with a stronger assessor behind the same port | A1-open |
| U-16 | Failing closed on a missing estimate is acceptable to users | A1-COST says FN is more severe than FP but gives no tolerance | Availability | Assessor outage blocks everything | Operational requirement from the deploying organization | open |
