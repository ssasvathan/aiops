# Project Context Analysis

## Requirements Overview

**Functional Requirements:**

20 FRs across 5 concern-based groups:

| Area | FRs | Architectural Impact |
|---|---|---|
| Confidence Scoring | FR1-FR7 | New deterministic scoring function in hot-path gating stage; 3-tier design (coverage ratio, sustained amplifier, peak amplifier); derives both `diagnosis_confidence` and `proposed_action` |
| AG4 Gate Evaluation | FR8-FR11 | AG4 evaluates `diagnosis_confidence >= 0.6` as confidence floor; records confidence value and reason code in `ActionDecisionV1` audit trail |
| Peak History Depth | FR12-FR14 | Environment-specific `STAGE2_PEAK_HISTORY_MAX_DEPTH` in `.env.*` files; no code change, configuration-only fix |
| Shard Lease TTL | FR15-FR17 | `SHARD_LEASE_TTL_SECONDS` set with margin above UAT-measured p95; checkpoint mechanism as safety net |
| Audit & Observability | FR18-FR20 | Non-zero `diagnosis_confidence` in `ActionDecisionV1`; differentiated reason codes; `reproduce_gate_decision()` correctness |

**Non-Functional Requirements:**

16 NFRs driving architectural constraints:

| Category | Count | Key Constraints |
|---|---|---|
| Performance | 3 | Scoring function < 1ms p99; hot-path gate eval p99 <= 500ms (standing); memory scales linearly with peak depth |
| Security | 2 | No new external I/O or credentials; config values safe for version control |
| Reliability | 3 | No unhandled exceptions (fail-safe to 0.0/OBSERVE); `is_sustained=None` handled conservatively; all `.env.*` files carry explicit values |
| Auditability | 4 | Non-zero confidence in audit records; differentiated reason codes; confidence distribution variance; policy version stamps |
| Testability | 3 | Unit-testable from deterministic inputs; 0 skipped tests; AG4 boundary conditions covered (0.59 caps, 0.60 passes) |
| Process | 3 | Single coordinated release; config docs updated; no BMAD terminology in docs |

**Scale & Complexity:**

- Primary domain: Backend event-driven pipeline (AIOps)
- Complexity level: Low — surgical fix within established architecture
- Change surface: 1 new function + 3 config file edits + documentation updates
- No new architectural components, packages, or runtime modes

## Architectural Posture: Confirm, Don't Reinvent

No new architectural decisions of the D1-D13 caliber are required for this release. The Iteration 2 architecture is the standing foundation and every fix operates within its established invariants, patterns, and package boundaries.

The sole architectural novelty is the **placement and interface of the scoring function** within the existing gating stage. All other changes are configuration edits and documentation updates.

Implementing agents should treat this as "confirm standing decisions apply" — not as an opportunity to introduce new packages, new abstractions, or new architectural patterns.

## Fix Dependency Graph

```
Fix 1 (Shard Lease TTL config) ─── operationally independent ───┐
                                                                  │
Fix 2 (Peak History Depth config) ──> Fix 3 (Scoring Function) ──┤
         must be correct first          uses peak amplifier        │
                                                                  ▼
                                                    Single Coordinated Release
```

- **Fix 2 → Fix 3 causal dependency:** The tier 3 peak amplifier in the scoring function consumes peak classification results. If peak depth is still at the legacy 12-sample default, the amplifier operates on statistically insufficient baselines.
- **Fix 1 is independent:** TTL correction has no code-level dependency on Fix 2 or Fix 3, but ships in the same release for operational coherence.

## Architectural Invariants (Standing from Iteration 2)

These are immovable constraints inherited from the Iteration 2 architecture. This release operates entirely within them:

| Invariant | Implication for This Release |
|---|---|
| D6: Hot/cold path separation | Scoring function must have zero import path to `diagnosis/` package |
| Frozen contracts | `GateInputContext`, `ActionDecisionV1` fields already exist — no changes needed |
| PAGE only in PROD+TIER_0 | Scoring function populates `proposed_action` but environment cap framework remains authoritative |
| UNKNOWN-not-zero | Coverage ratio must weight UNKNOWN distinctly from PRESENT and from zero |
| Actions only cap downward | `proposed_action` is a candidate; gating + env caps can only reduce, never escalate |
| Write-once casefiles + hash chains | No changes to casefile assembly, hashing, or persistence |
| Policy version stamps | v1 tier weights are part of scoring policy — must be traceable in casefiles |
| Audit replay determinism | `reproduce_gate_decision()` must produce identical `ActionDecisionV1` including new confidence values |

## Technical Constraints & Dependencies

**Scoring function placement constraint:**
- The scoring function must live in `pipeline/stages/gating.py` — hot-path gating stage local. Not in a shared utility, not in a new module, not in a separate package.
- Tier weight constants defined as named module-level constants in the same module (not magic numbers).
- No import dependency on `diagnosis/` package — D6 invariant enforcement.

**`is_sustained=None` precision constraint:**
- Redis fallback produces `None`, not `False`. The scoring function must treat `None` as a distinct non-amplifying input.
- Code must use `if is_sustained is True:` (identity check), not `if is_sustained:` (truthy check). While `None` is falsy and the truthy check happens to produce correct behavior, it is not *explicitly* correct and masks the three-state semantics (`True` / `False` / `None`).
- Tests must cover `None` as a distinct case, not rely on falsy equivalence.

**Deployment constraints:**
- OpenShift target for dev/uat/prod; Docker Compose for local development
- Single Docker image, multiple runtime modes via `--mode` argument
- Environment action caps: local=OBSERVE, dev=NOTIFY, uat=TICKET, prod=PAGE

**Release coordination constraint (PG1):**
- All three fixes ship as a single coordinated release
- Fix 2 must be correct before Fix 3 produces meaningful peak-amplified scores

**Calibration constraint:**
- AG4 0.6 threshold and tier weights are v1 heuristics — UAT calibration is a named pre-production activity, not a go-live blocker
- No production baseline for AG4 behavior exists — UAT is the first calibration environment

**Backward compatibility constraint:**
- Existing stored `CaseFileTriageV1` records were created when `diagnosis_confidence` was always 0.0. `reproduce_gate_decision()` must handle both pre-release (0.0 confidence, OBSERVE) and post-release (scored confidence) records correctly. This is a regression risk requiring explicit test coverage.

## Verification Architecture

Three distinct verification layers, each addressing a different concern:

| Layer | What It Verifies | How |
|---|---|---|
| **Unit (scoring correctness)** | Scoring function produces correct `diagnosis_confidence` and `proposed_action` from deterministic inputs | Synthetic inputs covering AG4 boundary (0.59 caps, 0.60 passes), all-UNKNOWN floor, PRESENT+sustained+peak ceiling, `is_sustained=None` distinct handling |
| **Structural (D6 isolation)** | Scoring function module has no import path to `diagnosis/` package | Static import analysis test — architecture enforcement, not behavior test |
| **Config validation** | All `.env.*` files carry explicit `STAGE2_PEAK_HISTORY_MAX_DEPTH` and `SHARD_LEASE_TTL_SECONDS` values with no fallback to legacy defaults | Assertion tests against config file contents |

Additionally: `reproduce_gate_decision()` backward compatibility test — replay a stored pre-release casefile (confidence=0.0) and verify identical output.

## Cross-Cutting Concerns

| Priority | Concern | Impact |
|---|---|---|
| 1 | **D6 invariant enforcement** | Scoring function must be hot-path-local; cold-path LLM output has zero influence on `diagnosis_confidence` |
| 2 | **UNKNOWN evidence semantics** | Coverage ratio must not collapse UNKNOWN to zero or PRESENT; explicit weight distinction required |
| 3 | **Audit trail integrity** | `ActionDecisionV1` records must reflect real scoring outcomes, not universal defaults |
| 4 | **Safe defaults preservation** | Any scoring exception must fall back to 0.0/OBSERVE — pre-release behavior as safety net |
| 5 | **`is_sustained=None` three-state precision** | `None` (Redis fallback) must be handled as a distinct case from `True` and `False` in both code and tests |
| 6 | **Backward compatibility** | `reproduce_gate_decision()` must handle pre-release casefiles (confidence=0.0) correctly alongside post-release scored records |
| 7 | **Coordinated config + code release** | Peak depth configuration must be correct for tier 3 amplifier to produce meaningful peak-amplified scores |
