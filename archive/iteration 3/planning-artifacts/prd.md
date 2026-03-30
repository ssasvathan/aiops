---
stepsCompleted: ['step-01-init', 'step-02-discovery', 'step-02b-vision', 'step-02c-executive-summary', 'step-03-success', 'step-01b-continue', 'step-04-journeys', 'step-05-domain', 'step-06-innovation', 'step-07-project-type', 'step-08-scoping', 'step-09-functional', 'step-10-nonfunctional', 'step-11-polish', 'step-11-complete']
inputDocuments:
  - artifact/planning-artifacts/product-brief-aiOps-2026-03-28.md
  - artifact/project-context.md
  - docs/index.md
  - docs/project-overview.md
  - docs/architecture.md
  - docs/architecture-patterns.md
  - docs/technology-stack.md
  - docs/component-inventory.md
  - docs/project-structure.md
  - docs/runtime-modes.md
  - docs/contracts.md
  - docs/api-contracts.md
  - docs/data-models.md
  - docs/schema-evolution-strategy.md
  - docs/development-guide.md
  - docs/contribution-guide.md
workflowType: 'prd'
date: '2026-03-28'
classification:
  projectType: api_backend
  domain: scientific
  complexity: medium
  projectContext: brownfield
briefCount: 1
researchCount: 0
brainstormingCount: 0
projectDocsCount: 15
---

# Product Requirements Document - aiOps

**Author:** Sas
**Date:** 2026-03-28

## Executive Summary

The aiOps triage pipeline has three production-impacting defects that collectively render the AG4 confidence gate permanently inert, feed gating decisions from a statistically insufficient 1-hour peak baseline, and expose the system to duplicate scope processing under shard lease race conditions. Every TICKET and PAGE action has been suppressed to OBSERVE since the topology stage was wired — the pipeline has never successfully escalated an incident. This release delivers three coordinated surgical fixes restoring full operational capability: correct lease TTL margins, environment-specific peak history depth, and a deterministic hot-path confidence scoring function that populates `GateInputContext.diagnosis_confidence` for the first time.

The core architectural insight: both `diagnosis_confidence` and `proposed_action` already exist on `GateInputContext` with safe zero/OBSERVE defaults. No frozen contract changes, schema modifications, or cold-path LLM influence are needed. Three fields of configuration and one new scoring function restore a gate that has been silently broken since go-live.

### What Makes This Special

This is a precision restoration, not a feature addition. The fix deliberately operates within all existing architectural invariants: the D6 hot/cold-path decoupling is preserved, the environment action cap framework remains authoritative, and the checkpoint mechanism continues as the downstream safety net for any residual race window. The confidence scoring function is tier-weighted and fully unit-testable from deterministic signals (evidence coverage ratio, sustained streak, peak window classification) — no probabilistic models, no external dependencies, no new infrastructure. The only calibration risk is threshold tuning, which is an explicit UAT activity rather than a go-live blocker.

## Project Classification

- **Project Type:** API Backend — event-driven pipeline service (Kafka-in, outbound actions to PagerDuty / ServiceNow / Slack)
- **Domain:** AI/ML Operations (AIOps) — deterministic rule engine with advisory LLM cold path; medium complexity
- **Complexity:** Medium — well-defined invariant set, no novel ML research, heuristic calibration required post-UAT
- **Project Context:** Brownfield — three targeted fixes to a production system with strict no-contract-change and D6-invariant constraints

## Success Criteria

### User Success

**Platform SRE / On-Call Engineers:**
- At least one TICKET or PAGE action is produced in UAT for a scope with PRESENT evidence and `sustained=true` — the first successful escalation the pipeline has ever produced.
- Audit trail records carry meaningful `diagnosis_confidence` values (non-zero, non-uniform) and accurate reason codes, enabling post-incident analysis and replay.
- No manual detection required for anomaly events that clear AG4 with scored confidence ≥ 0.6.

**Platform Operations Engineers:**
- All three `.env.*` files (prod, uat, dev) carry environment-specific `STAGE2_PEAK_HISTORY_MAX_DEPTH` values with no environment falling back to the legacy 12-sample default.
- `SHARD_LEASE_TTL_SECONDS` is configured with a margin above observed p95 cycle duration (baseline from UAT deployment logs); zero overlapping scope processing events per shard per cycle in UAT audit logs.
- Peak depth and lease TTL are directly adjustable via configuration without code change.

### Business Success

1. **Pipeline escalation capability restored:** TICKET and PAGE actions are reachable in production. AG4 has never passed a high-urgency action; this release makes the gating mechanism functional for the first time.
2. **Operational risk eliminated:** The shard lease TTL race condition is resolved before any scaling of pod count or cycle frequency.
3. **Audit baseline established:** `ActionDecisionV1` records reflect real confidence scores and reason codes, making audit trails usable for post-incident analysis and replay.

### Technical Success

- **Fix 1 (Shard Lease TTL):** Zero overlapping scope processing events per shard per cycle in UAT. `SHARD_LEASE_TTL_SECONDS` set with margin above UAT-measured p95 cycle duration.
- **Fix 2 (Peak History Depth):** All `.env.prod`, `.env.uat`, `.env.dev` carry correct depth values. Proportion of `PeakWindowContext` records with `INSUFFICIENT_HISTORY` reason code decreases in UAT over first 24h post-deploy (requires deployed OTLP/Prometheus; not locally validatable).
- **Fix 3 (Confidence Scoring):** `diagnosis_confidence` is non-zero for all scopes with at least one PRESENT evidence signal. Score distribution shows meaningful variance (not flat 0.0). `LOW_CONFIDENCE` reason code appears only on scopes with genuinely weak evidence coverage, not universally. Full unit test suite passes with 0 skips, covering all AG4 boundary conditions (0.59 caps, 0.60 passes), all-UNKNOWN floor, and PRESENT+sustained+peak ceiling.

### Measurable Outcomes

| Outcome | Measure | Validation Environment |
|---------|---------|----------------------|
| AG4 gate functional | ≥1 TICKET/PAGE produced in UAT with PRESENT+sustained=true | UAT |
| No shard race | 0 overlapping scope events per shard per cycle | UAT audit logs |
| Peak depth configured | All 3 `.env.*` carry correct values, no fallback to 12-sample default | Any env (config inspection) |
| Confidence scoring correct | Non-zero variance in `diagnosis_confidence`; unit tests pass with 0 skips | Local (unit) + UAT (telemetry) |
| Audit trail meaningful | `LOW_CONFIDENCE` not universal; confidence values reflect actual evidence | UAT |

## Product Scope

### MVP — Minimum Viable Product

**Fix 1 — Shard Lease TTL Configuration**
- Update `SHARD_LEASE_TTL_SECONDS` in all environment configurations (`.env.prod`, `.env.uat`, `.env.dev`) to exceed the maximum expected cycle duration plus a safety margin.
- Baseline cycle duration must be measured from a UAT deployment before the final value is set; the checkpoint mechanism is the backstop in the interim.

**Fix 2 — Environment-Specific Peak History Depth**
- Set `STAGE2_PEAK_HISTORY_MAX_DEPTH` per environment: prod = 30 days, uat = 15 days, dev = 7 days.
- Remove reliance on the global 12-sample default across all deployed environments.
- Update configuration documentation to reflect environment-specific values.

**Fix 3 — Deterministic Hot-Path Confidence Scoring**
- Implement a new deterministic scoring function computing `diagnosis_confidence` (0.0–1.0) from three signal tiers:
  - Tier 1 (base): Evidence status coverage ratio (PRESENT / ABSENT / UNKNOWN / STALE counts)
  - Tier 2 (amplifier): Sustained status (`is_sustained` + consecutive bucket ratio)
  - Tier 3 (amplifier): Peak window classification (`is_peak_window` / `is_near_peak_window`)
- Derive `proposed_action` from the same signals.
- Enrich `GateInputContext` with both values before `collect_gate_inputs_by_scope` is called in the gating stage.
- No contract or schema changes — both fields already exist with safe defaults.
- Comprehensive unit tests: AG4 boundary conditions (0.59 caps, 0.60 passes), all-UNKNOWN floor, PRESENT+sustained+peak ceiling.
- D6 invariant preserved: cold-path LLM output has zero influence.

### Growth Features (Post-MVP)

- **Seasonality-aware peak classification:** Consume per-stream `peak_window_policy` from the topology registry; classify peak windows using time-of-day buckets (business hours vs off-hours) rather than flat statistical percentiles. The config field is already loaded into memory — implementation is the gap.
- **Expanded confidence signals:** Incorporate additional hot-path signals (blast radius, downstream impact count) as confidence amplifiers once the v1 baseline is validated in UAT/prod.
- **New harness acceptance scenarios:** ATDD tests specifically targeting AG4 gate validation with synthetic PRESENT+sustained+peak inputs.

### Vision (Future)

- **Dynamic confidence threshold tuning:** Use UAT/prod telemetry to calibrate the scoring tier weights and the AG4 0.6 threshold against real anomaly distributions.
- **Per-environment TTL automation:** Derive `SHARD_LEASE_TTL_SECONDS` from observed p95 cycle duration telemetry rather than manual configuration.
- **Replay-enhanced calibration:** Use stored `CaseFileTriageV1` audit records and `reproduce_gate_decision()` to replay historical events against updated scoring tiers, validating threshold changes before deployment.

## User Journeys

### Journey 1: Platform SRE — The First Escalation (Success Path)

**Meet Alex.** Alex has been on-call for the aiOps service for seven months. Every week the pipeline processes hundreds of anomaly events. Every week Alex gets nothing from it — no pages, no tickets. Alex has learned to ignore the pipeline entirely and relies on manual dashboards. There's a quiet, nagging distrust: *is this thing even working?*

**Opening Scene — The old reality:**
It's 2 AM. A critical service anomaly fires. The pipeline ingests the event, runs through evidence collection, peak classification, topology resolution. AG4 evaluates gate inputs. `diagnosis_confidence = 0.0`. Cap fires: OBSERVE. No ticket raised. No page sent. Alex is asleep. The incident escalates manually 40 minutes later via a different alerting path. The aiOps audit trail shows `LOW_CONFIDENCE` — indistinguishable from every other event that ran through the pipeline since go-live.

**Rising Action — After the fix:**
The same night scenario repeats post-release. The anomaly event arrives. Evidence collection finds 4 of 6 signals PRESENT, one SUSTAINED with a 3-bucket streak. Tier 1 scoring: 0.67 base. Tier 2 amplifier: streak ratio adds 0.08. The event arrives during peak window (Tier 3): adds 0.05. Final `diagnosis_confidence = 0.80`. `proposed_action = TICKET`.

**Climax — The moment that matters:**
AG4 evaluates: `0.80 >= 0.6`, `sustained = true`. Gate passes. `proposed_action = TICKET`. Environment cap: prod allows TICKET. The outbox commits. The Kafka event publishes. PagerDuty fires.

**Resolution:**
Alex's phone rings at 2 AM. For the first time ever, it's an aiOps-sourced alert. The PagerDuty event has a traceable `case_id`. Alex opens the audit trail: `diagnosis_confidence = 0.80`, `reason_code = HIGH_CONFIDENCE_SUSTAINED_PEAK`. The evidence is readable. Alex acts. Incident contained in 8 minutes.

**New reality:** Alex now trusts the pipeline. Low-confidence OBSERVE decisions are also readable — Alex can distinguish "genuinely weak signal" from "systemic broken gate."

---

### Journey 2: Platform SRE — Weak Evidence, Correct Silence (Edge Case)

**Same Alex, different event.** A low-fidelity anomaly fires: 5 of 6 evidence signals are UNKNOWN or STALE. One is PRESENT, unsustained.

**Opening Scene:**
The event reaches the scoring function. Tier 1: 1 PRESENT / 5 UNKNOWN. Coverage ratio: 0.17. Base score: 0.17. No sustained streak (Tier 2: +0). Not peak window (Tier 3: +0). `diagnosis_confidence = 0.17`. `proposed_action = OBSERVE`.

**Climax:**
AG4: `0.17 < 0.6`. Cap fires: OBSERVE. No ticket. No page. Correct behavior.

**Resolution:**
Alex checks the next morning. The audit trail shows `diagnosis_confidence = 0.17`, `reason_code = LOW_CONFIDENCE_INSUFFICIENT_EVIDENCE`. Alex can now read *why* this event was suppressed. Pre-release, this looked identical to every other event — all showing `0.0`. Now Alex has confidence in the silence: it means genuinely weak signal, not a broken gate.

---

### Journey 3: Platform Operations — Deployment, Calibration & UAT Validation

**Meet Jordan.** Jordan owns the aiOps operational config: environment files, shard coordination tuning, deployment lifecycle. Jordan has known about the inert AG4 gate for months but couldn't fix it at the config layer — it required code. The shard lease TTL is a constant source of anxiety; Jordan has seen duplicate processing in logs but has no lever to correct it without a code change.

**Opening Scene:**
Jordan receives the release build. Three changes to deploy: TTL config fix, env-specific peak depth, new confidence scoring function.

**Rising Action — Configuration:**
Jordan opens `.env.prod`, `.env.uat`, `.env.dev`. Sets `STAGE2_PEAK_HISTORY_MAX_DEPTH`: prod=8640 (30 days at 5-min intervals), uat=4320 (15 days), dev=2016 (7 days). No more global 12-sample default. All three files updated, committed, reviewed.

For `SHARD_LEASE_TTL_SECONDS`: Jordan knows the correct value requires a UAT cycle baseline. Jordan deploys to UAT first, runs three full pipeline cycles, pulls p95 cycle duration from logs: measured at 47 seconds. Sets `SHARD_LEASE_TTL_SECONDS = 90` (47s p95 + 43s margin). Config committed.

**Climax — UAT Observation:**
Jordan monitors UAT for the first 24 hours. OTLP/Prometheus dashboards show:
- `INSUFFICIENT_HISTORY` reason code rate: drops from 78% → 12% as the deeper baseline accumulates
- Shard audit logs: zero overlapping scope events across 144 cycles
- `diagnosis_confidence` values: non-zero variance across scopes, meaningful distribution emerging

**Resolution:**
Jordan signs off on UAT. Prod deploy proceeds. For the first time, Jordan has direct operational control over peak depth and TTL without a code change. The `SHARD_LEASE_TTL_SECONDS` value is now documented with its UAT-measured baseline for the next ops review.

---

### Journey 4: Developer — Implementing the Fix with Confidence

**Meet Sam.** Sam is the backend engineer assigned the three-fix release. The codebase is well-structured but the AG4 gate failure is subtle — `diagnosis_confidence` defaults to 0.0, gets passed through, never caught by a test because no test ever checked what the scoring function *produces*. There are no unit tests for confidence scoring because there was no scoring function.

**Opening Scene:**
Sam reads the PRD and architecture docs. Key invariants noted: D6 decoupling must be preserved (no cold-path influence on hot-path scoring), both fields already exist on `GateInputContext` with safe defaults, the fix must be hot-path-local.

**Rising Action — Implementation:**
Sam implements the three-tier scoring function in the gating stage. Starts with a failing test: `assert score_confidence(all_present, sustained=True, peak=True) >= 0.6`. Test fails (function doesn't exist). Writes function. Test passes. Adds boundary tests: 0.59 caps to OBSERVE, 0.60 passes TICKET. All-UNKNOWN floors to 0.0. PRESENT+sustained+peak reaches ceiling.

For the config fixes: Sam updates `.env.*` files (Jordan will fine-tune TTL from UAT; Sam sets a safe placeholder value and documents it needs calibration). Updates config documentation.

**Climax — Full Regression:**
`TESTCONTAINERS_RYUK_DISABLED=true ... uv run pytest -q -rs` — 0 failed, 0 skipped. Ruff clean. All three fixes verified: scoring function unit-tested, config values in place, TTL documented for UAT calibration.

**Resolution:**
Sam opens the PR. The change surface is deliberately narrow: one new function, three config file edits, one doc update. No contract changes, no schema migrations, no cold-path touches. The review is clean. Sam has confidence the D6 invariant is intact — the scoring function only reads hot-path signals.

---

### Journey 5: Incident Responder — Receiving the First Real Ticket (Secondary)

The PagerDuty integration has been in LIVE mode since go-live, but has never fired a TICKET or PAGE action. Post-release, the first properly-scored event fires a `TICKET` action. ServiceNow receives a `POST` to its table API. A new incident record is created with `case_id`, `scope_id`, `confidence_score = 0.80`, and traceable action decision metadata. The on-call responder follows the linked audit record. The pipeline's first real downstream handoff completes without manual intervention.

---

### Journey 6: Audit & Compliance Reviewer — A Meaningful Audit Trail (Secondary)

**Pre-release:** Every `ActionDecisionV1` record in storage carries `diagnosis_confidence = 0.0`, `reason_code = LOW_CONFIDENCE`. Running a compliance query: 100% of records show identical values regardless of actual evidence strength. The audit trail is operationally useless for post-incident analysis.

**Post-release:** The reviewer runs the same query. Records now show a distribution: 0.17, 0.54, 0.80, 0.72, 0.31. `LOW_CONFIDENCE` appears only on records with genuine coverage gaps. `HIGH_CONFIDENCE_SUSTAINED_PEAK` appears on correctly-escalated events. Replay via `reproduce_gate_decision()` now produces meaningful reproducible outputs. The audit trail is a real decision record.

### Journey Requirements Summary

| Journey | Capabilities Revealed |
|---|---|
| SRE Success Path | Confidence scoring function; AG4 gate pass; outbox publish; PagerDuty/ServiceNow action fire; audit trail with meaningful confidence + reason code |
| SRE Edge Case | All-UNKNOWN floor behavior; OBSERVE cap for low-confidence; readable audit record distinguishing silence from broken gate |
| Platform Ops | Env-specific config (peak depth, TTL); UAT cycle baseline measurement; OTLP/Prometheus INSUFFICIENT_HISTORY metric; zero-overlap shard verification |
| Developer | Deterministic scoring unit tests; AG4 boundary coverage (0.59/0.60); D6 invariant preservation; full regression 0-skip gate |
| Incident Responder | ServiceNow/PagerDuty LIVE action on first valid TICKET/PAGE; linked audit record in downstream system |
| Audit Reviewer | Non-zero variance in confidence values; reason code differentiation; `reproduce_gate_decision()` correctness |

## Domain-Specific Requirements

The following requirements reflect AIOps/scientific domain constraints that shape this release. They are standing invariants every change must preserve.

### Audit & Decision Reproducibility

- The confidence scoring function must be a pure deterministic function — identical inputs always produce identical `diagnosis_confidence` output, satisfying the replayability guarantee of `reproduce_gate_decision()`
- Policy version stamping in every casefile remains mandatory — the v1 tier weights and AG4 threshold are part of the scoring policy and must be traceable in audit records
- Structured logs with `correlation_id` (case_id) must carry the new `diagnosis_confidence` and `reason_code` fields for field-level querying in Elastic
- `ActionDecisionV1` audit records must reflect real scoring outcomes — `LOW_CONFIDENCE` must not appear universally; it must indicate genuinely weak evidence coverage

### Validation Methodology

- The v1 confidence tier weights and AG4 0.6 threshold are heuristics — UAT calibration is a named pre-production activity, not a go-live blocker
- Scoring function correctness is unit-testable locally from deterministic inputs; threshold calibration requires deployed UAT telemetry
- No production baseline for AG4 behavior exists — UAT is the first calibration environment
- KPI telemetry (OTLP/Prometheus confidence distribution, gate reason code distribution) requires a deployed environment; local validation is limited to unit correctness

### Operational Safety Invariants

- PAGE is structurally impossible outside PROD+TIER_0 — enforced by environment caps independent of scoring outcomes
- Actions only cap downward, never escalate — the confidence scoring function populates `proposed_action` but the environment cap framework remains authoritative
- Hot/cold path separation (D6) must be preserved — the scoring function reads only hot-path signals; cold-path LLM output has zero influence on `diagnosis_confidence`
- UNKNOWN evidence is never collapsed to PRESENT or zero — coverage ratio scoring must preserve UNKNOWN as a distinct low-weight signal, not treat it as absence or presence

### Degraded Mode Handling

- Redis unavailability: sustained state falls back to `None` (conservative — treats as first observation, no false `sustained=true`) — the scoring function must handle `is_sustained=None` gracefully
- If scoring function raises an exception, the pipeline must fall back to `diagnosis_confidence=0.0` and `proposed_action=OBSERVE` — same safe defaults as pre-release

## Innovation & Novel Patterns

### Detected Innovation Areas

**1. Deterministic confidence scoring as a safety engineering artifact.**
The confidence scoring function is explicitly a v1 heuristic — but it is tier-weighted, fully unit-testable from deterministic signals, and produces reproducible outputs. The innovation is treating confidence as a safety-layer input (AG4 gate) rather than a probabilistic ML output. This preserves the structural guarantee that LLM never overrides gating decisions (D6 invariant) while making the confidence gate functional for the first time.

**2. UNKNOWN-as-first-class-signal in evidence coverage scoring.**
Rather than treating missing evidence as zero or as absence, the coverage ratio scores UNKNOWN signals at a reduced weight distinct from both PRESENT and ABSENT. This is a precision restoration of the existing architecture's UNKNOWN-not-zero invariant — most observability scoring collapses missing data; this system propagates it through every confidence tier.

**3. Evidence truthfulness propagated into gate confidence.**
The three-tier design (coverage ratio → sustained amplifier → peak amplifier) encodes the architectural belief that evidence quality has orthogonal dimensions: breadth (how many signals are PRESENT), duration (how long the anomaly has persisted), and temporal context (peak vs off-peak). This multi-dimensional scoring is novel relative to single-threshold gate approaches.

**4. Surgical brownfield activation within frozen contract constraints.**
Both `diagnosis_confidence` and `proposed_action` already exist on `GateInputContext` with safe zero/OBSERVE defaults. The fix activates the gate by populating existing fields — no contract changes, no schema migrations, no interface additions. This is the pattern for safely activating dormant capabilities in a frozen-contract system.

### Validation Approach

- **Scoring correctness:** Unit tests covering all AG4 boundary conditions (0.59 caps, 0.60 passes), all-UNKNOWN floor, PRESENT+sustained+peak ceiling — locally verifiable
- **UNKNOWN propagation:** Test that UNKNOWN evidence reduces coverage ratio below PRESENT without zeroing it — confirms UNKNOWN-not-zero invariant
- **D6 invariant preservation:** Test that the scoring function has no import path to or shared state with cold-path diagnosis components
- **Threshold calibration:** UAT deployment with real anomaly events; confidence distribution telemetry reviewed before prod promotion

### Innovation Risk Mitigation

| Risk | Mitigation |
|---|---|
| Tier weights produce too-low scores, suppressing valid escalations | UAT calibration activity; weights are configurable constants, not hardcoded |
| Tier weights produce too-high scores, flooding with false positives | AG4 0.6 threshold acts as floor; UAT observation period before prod |
| UNKNOWN evidence treated as zero (collapses invariant) | Explicit test case: all-UNKNOWN must floor at < 0.6; unit test in regression suite |
| Scoring function not hot-path-local (violates D6) | Code review gate: no imports from `diagnosis/` package in scoring function module |

## Event-Driven Pipeline Specific Requirements

### Project-Type Overview

aiOps is an event-driven triage pipeline with integration adapters — not a conventional REST API backend. This release makes targeted changes to the gating stage (scoring function addition), environment configuration files, and operational documentation. No new runtime modes, no new pods, no new Kafka topics.

### Technical Architecture Considerations

**Runtime Modes — Unchanged by this release:**

| Mode | Change in this release |
|---|---|
| `hot-path` | New scoring function added to gating stage; no interface changes |
| `cold-path` | No changes |
| `outbox-publisher` | No changes |
| `casefile-lifecycle` | No changes |

**Inbound/Outbound Interfaces — Unchanged:**
- Health endpoint, Prometheus ingestion, Kafka publication, PagerDuty, Slack, ServiceNow — all unchanged
- `GateInputContext` fields `diagnosis_confidence` and `proposed_action` were already part of the frozen contract with safe defaults; populating them is not a contract change

**Contract and Data Format:**
- No new frozen contract models
- No schema envelope version bumps
- `ActionDecisionV1` audit records will carry non-zero `diagnosis_confidence` for the first time — this is a behavioral change within the existing contract, not a structural one

### Scoring Function Implementation Considerations

- The scoring function must be placed in the hot-path gating stage module, not in a shared utility — it is gating-stage-local by design
- It must accept evidence status counts, sustained state, and peak classification as inputs, and return `(diagnosis_confidence: float, proposed_action: ActionType)`
- It must have no import dependency on `diagnosis/` package — D6 invariant enforcement
- It must handle `is_sustained=None` (Redis fallback) as a conservative non-amplifying input
- Tier weight constants must be defined as named module-level constants (not magic numbers) to support future calibration without code archaeology

### Configuration Change Considerations

- `STAGE2_PEAK_HISTORY_MAX_DEPTH` and `SHARD_LEASE_TTL_SECONDS` are environment-specific values — changes go in `.env.prod`, `.env.uat`, `.env.dev` only
- The `STAGE2_PEAK_HISTORY_MAX_DEPTH` values are expressed in samples (not days) — documentation must make the conversion explicit (5-minute intervals: 30d = 8640 samples, 15d = 4320, 7d = 2016)
- `SHARD_LEASE_TTL_SECONDS` final value for prod/uat must be derived from UAT-measured p95 cycle duration; a placeholder value with explicit documentation is acceptable for the initial PR

## Project Scoping & Phased Development

### MVP Strategy & Philosophy

**MVP Approach:** Surgical fix — activate dormant capabilities within existing architecture, no new infrastructure
**Resource Requirements:** Single backend engineer; no infrastructure or platform team involvement required beyond UAT access for calibration

### Risk Mitigation Strategy

**Technical Risks:** D6 invariant violation — mitigated by code review gate (no `diagnosis/` imports in scoring module) and test assertion that LLM output has zero path to `diagnosis_confidence`
**Calibration Risk:** Tier weights produce wrong distribution — mitigated by explicit UAT calibration activity before prod promotion; weights are named constants not hardcoded values
**Operational Risk:** Incorrect TTL value before UAT baseline — mitigated by checkpoint mechanism as downstream safety net; UAT measurement is a named pre-prod step

## Functional Requirements

### Confidence Scoring

- FR1: The hot-path gating stage can compute `diagnosis_confidence` (0.0–1.0) from a three-tier deterministic scoring function using evidence status counts, sustained state, and peak window classification as inputs
- FR2: The scoring function Tier 1 can compute a base coverage ratio from the proportion of PRESENT evidence signals relative to total evaluated signals, with UNKNOWN signals weighted below PRESENT
- FR3: The scoring function Tier 2 can apply a sustained amplifier when `is_sustained=True` using consecutive bucket streak ratio, with `is_sustained=None` treated as a non-amplifying conservative input
- FR4: The scoring function Tier 3 can apply a peak amplifier when `is_peak_window=True` or `is_near_peak_window=True`, with amplifier magnitude proportional to peak proximity
- FR5: The scoring function can derive `proposed_action` from the same signals — PRESENT+sustained+peak combination produces a TICKET or PAGE candidate; insufficient evidence coverage that cannot produce `diagnosis_confidence >= 0.6` without tier amplifiers produces OBSERVE
- FR6: The hot-path gating stage can enrich `GateInputContext` with both `diagnosis_confidence` and `proposed_action` before `collect_gate_inputs_by_scope` is called
- FR7: The scoring function can produce `diagnosis_confidence=0.0` and `proposed_action=OBSERVE` as a safe fallback on any exception, preserving pre-release behavior

### AG4 Gate Evaluation

- FR8: AG4 can evaluate `diagnosis_confidence >= 0.6` as the confidence floor condition for permitting TICKET or PAGE actions
- FR9: AG4 can evaluate `is_sustained=True` as the sustained condition independent of confidence scoring
- FR10: AG4 can cap any action to OBSERVE when `diagnosis_confidence < 0.6`, regardless of other gate states
- FR11: The gate evaluation trail in `ActionDecisionV1` can record the `diagnosis_confidence` value and reason code for every AG4 evaluation

### Peak History Depth Configuration

- FR12: Operators can configure `STAGE2_PEAK_HISTORY_MAX_DEPTH` per environment in `.env.prod`, `.env.uat`, `.env.dev` without code change
- FR13: The system can load environment-specific `STAGE2_PEAK_HISTORY_MAX_DEPTH` values through the existing `APP_ENV`-driven env file selection with no fallback to global defaults when environment-specific values are present
- FR14: Configuration documentation can express the sample-count values with explicit day-equivalent conversions (prod=8640/30d, uat=4320/15d, dev=2016/7d at 5-minute intervals)

### Shard Lease TTL Configuration

- FR15: Operators can configure `SHARD_LEASE_TTL_SECONDS` per environment in `.env.*` files without code change
- FR16: The configured TTL value can be set to exceed the p95 cycle duration measured from UAT deployment logs, with a minimum safety margin of 30 seconds above the measured p95 (e.g., UAT-measured p95 of 47s → `SHARD_LEASE_TTL_SECONDS = 90` or greater)
- FR17: The system can suppress duplicate scope processing effects through the checkpoint deduplication mechanism for any residual race window during the TTL calibration period, ensuring no duplicate scope processing effects reach downstream systems

### Audit & Observability

- FR18: `ActionDecisionV1` audit records can carry non-zero `diagnosis_confidence` values for all scopes with at least one PRESENT evidence signal
- FR19: Audit records can carry `reason_code` values that differentiate confidence levels (e.g., `HIGH_CONFIDENCE_SUSTAINED_PEAK`, `LOW_CONFIDENCE_INSUFFICIENT_EVIDENCE`) rather than universal `LOW_CONFIDENCE`
- FR20: `reproduce_gate_decision()` can replay stored `CaseFileTriageV1` records and produce identical `ActionDecisionV1` outputs including the new `diagnosis_confidence` value, given the same scoring function version

## Non-Functional Requirements

### Performance

- NFR-P1: The confidence scoring function adds < 1ms p99 latency to the hot-path gating stage per scoring invocation
- NFR-P2: Hot-path gate evaluation p99 <= 500ms per cycle (inherited standing requirement — scoring function must not degrade this)
- NFR-P3: Hot-path peak profile memory footprint scales linearly with `STAGE2_PEAK_HISTORY_MAX_DEPTH`; increasing to environment-specific depths (up to prod=8640 samples) must not cause heap exhaustion or OOM errors under normal operating scope load

### Security

- NFR-S1: The scoring function introduces no new external I/O, no new credential handling, and no new log fields requiring masking
- NFR-S2: `STAGE2_PEAK_HISTORY_MAX_DEPTH` and `SHARD_LEASE_TTL_SECONDS` values must contain no secrets, credentials, or sensitive data — both values must be safe to store in version-controlled env-files alongside other operational configuration

### Reliability

- NFR-R1: The scoring function must not raise unhandled exceptions — any failure must produce safe zero/OBSERVE defaults (fail-safe, not fail-loud)
- NFR-R2: `is_sustained=None` (Redis fallback state) must be handled as a non-amplifying conservative input — the function must never treat `None` as `True`
- NFR-R3: All three `.env.*` files must carry explicit depth values after this release — no environment must fall back to the implicit 12-sample default

### Auditability

- NFR-A1: `diagnosis_confidence` must be non-zero in `ActionDecisionV1` for any scope with at least one PRESENT evidence signal — zero is no longer the universal value
- NFR-A2: `LOW_CONFIDENCE` reason code must not appear universally — in UAT audit records, at least one record must carry a non-`LOW_CONFIDENCE` reason code (e.g., `HIGH_CONFIDENCE_SUSTAINED_PEAK`), confirming the scoring function produces differentiated outcomes rather than a flat default
- NFR-A3: Confidence score distribution in UAT audit records must show variance across scopes — a standard deviation < 0.05 in `diagnosis_confidence` values across the first 100 scored events indicates a regression requiring investigation
- NFR-A4: All policy version fields in `CaseFileTriageV1` must continue to be stamped — the scoring function's tier weights are part of the versioned scoring policy

### Testability

- NFR-T1: The scoring function must be fully unit-testable from deterministic synthetic inputs — no mocking of external services required
- NFR-T2: Full regression suite must complete with 0 skipped tests post-change
- NFR-T3: AG4 boundary conditions must be covered: score=0.59 produces OBSERVE cap, score=0.60 permits TICKET/PAGE, all-UNKNOWN produces score < 0.6, PRESENT+sustained+peak produces score >= 0.6

### Process & Governance

- PG1: All three fix components (scoring function, peak depth config, TTL config) ship as a single coordinated release — Fix 2 must be correct before Fix 3 produces meaningful peak-amplified scores
- PG2: Configuration documentation in `docs/` must be updated to reflect environment-specific depth values and the TTL calibration procedure as part of the same change set
- PG3: Documentation must reference only project-native concepts — no references to BMAD artifacts, story identifiers, or workflow methodology terminology
