---
stepsCompleted: [1, 2, 3, 4, 5]
inputDocuments:
  - artifact/project-context.md
  - docs/index.md
  - docs/project-overview.md
  - docs/architecture.md
date: 2026-03-28
author: Sas
---

# Product Brief: aiOps

## Executive Summary

aiOps requires an urgent production release to address three inter-related gaps in
its triage pipeline that collectively render the AG4 confidence gate inert, allow
statistically insufficient peak classification baselines to feed gating decisions,
and permit duplicate scope processing under shard lease race conditions. All three
issues ship as a single coordinated fix.

A fourth gap — seasonality-aware peak classification using per-stream
`peak_window_policy` from the topology registry — was identified during analysis
but is explicitly out of scope for this release and tracked as a follow-on item.

---

## Core Vision

### Problem Statement

Three production-impacting defects have been identified in the aiOps triage pipeline:

1. **Shard Lease TTL Race** — If SHARD_LEASE_TTL_SECONDS is shorter than a full
   cycle execution, a second pod can acquire the same shard mid-cycle, causing two
   pods to process identical scopes simultaneously.

2. **Insufficient Peak History Baseline** — STAGE2_PEAK_HISTORY_MAX_DEPTH defaults
   to 12 samples (~1 hour at 5-minute intervals) across all environments. Production
   workloads require deeper baselines to reduce statistical noise in peak vs off-peak
   classification. Note: the current implementation uses global p90/p95 percentile
   thresholds across all historical samples regardless of time-of-day. Per-stream
   seasonality-aware classification (using the existing but unimplemented
   `peak_window_policy` topology registry config) is a separate follow-on item.

3. **AG4 Confidence Gate Is Inert** — GateInputContext.diagnosis_confidence defaults
   to 0.0 and is never populated on the hot path. AG4 requires >= 0.6 to permit
   TICKET or PAGE actions. Since the value is always 0.0, AG4 unconditionally
   suppresses every high-urgency action to OBSERVE — the confidence gate has never
   functioned since the topology stage was wired up.

### Problem Impact

- Every TICKET and PAGE action is universally suppressed to OBSERVE by AG4,
  regardless of actual evidence strength. The pipeline cannot escalate incidents.
- AG4 and AG6 gating decisions are fed statistically weak peak classifications
  built from a 1-hour window that cannot capture daily or weekly traffic patterns.
- Duplicate scope processing can occur under shard lease expiry, with downstream
  checkpoint deduplication as the only safety net.
- Audit trails show LOW_CONFIDENCE universally, making them unable to differentiate
  genuine low-confidence cases from the systemic default.

### Why Existing Solutions Fall Short

- The checkpoint mechanism provides downstream deduplication for shard races but
  does not prevent dual processing — it is a mitigation, not a fix.
- The cold-path DiagnosisConfidence enum (LOW/MEDIUM/HIGH) is intentionally
  decoupled from gating per architecture decision D6 and cannot populate the
  hot-path confidence scalar.
- No environment-specific peak depth overrides exist in any .env.* file today.
- The `peak_window_policy` per-stream config in the topology registry is loaded
  into memory but never consumed by the peak stage — the seasonality-aware
  classification the architecture intended was never implemented.

### Proposed Solution

A single coordinated release delivering three targeted fixes:

1. **TTL Configuration Fix** — Set SHARD_LEASE_TTL_SECONDS to exceed the maximum
   expected cycle duration plus a safety margin in all environment configurations.

2. **Environment-Specific Peak Depth** — Configure STAGE2_PEAK_HISTORY_MAX_DEPTH
   per environment: 30 days (prod), 15 days (uat), 7 days (dev). Update .env.*
   files and configuration documentation. This improves baseline statistical quality
   within the current global percentile approach.

3. **Deterministic Confidence Scoring** — A new hot-path-local scoring function
   computes diagnosis_confidence (0.0–1.0) from deterministic signals available
   before gate-input assembly:
   - **Tier 1 (base):** Evidence status coverage ratio (PRESENT/ABSENT/UNKNOWN/STALE)
   - **Tier 2 (amplifier):** Sustained status (is_sustained + streak ratio)
   - **Tier 3 (amplifier):** Peak window classification (is_peak_window/is_near_peak)
   Both diagnosis_confidence and proposed_action are populated on GateInputContext
   before collect_gate_inputs_by_scope. No frozen contract changes required. Both
   fields already exist with safe defaults. D6 invariant preserved — cold-path LLM
   output has zero influence. The 0.6 AG4 threshold and tier weights are a v1
   heuristic requiring UAT calibration before prod rollout.

### Fix Constraints & Invariants

- No frozen contract or schema changes — both GateInputContext fields already exist.
- D6 decoupling preserved — cold-path LLM output never influences hot-path scoring.
- Safe defaults maintained — existing OBSERVE/0.0 behavior is the fallback.
- Single coordinated release — #2 must be correct before #3 produces meaningful
  peak-amplified confidence scores.
- Confidence scoring is a v1 heuristic — UAT calibration is required; no production
  baseline data exists since AG4 has never been active.

### Out of Scope (Tracked as Follow-On)

- Per-stream `peak_window_policy` consumption by peak stage (seasonality-aware
  time-of-day classification using topology registry config).

---

## Target Users

### Primary Users

**Platform SRE / On-Call Engineers**
The primary intended beneficiaries of the pipeline's action decisions. These engineers
are responsible for responding to anomaly escalations surfaced by aiOps. With AG4 inert,
every TICKET and PAGE action has been suppressed to OBSERVE since the topology stage was
connected — meaning the pipeline has never successfully escalated an incident to this
team. After this release, they will for the first time receive correctly gated TICKET
and PAGE actions based on deterministic confidence scoring. Their success moment: an
anomaly event flows through the pipeline, clears AG4 with a scored confidence >= 0.6
and a sustained signal, and fires a PagerDuty or ServiceNow action with a meaningful
audit record.

**Platform Operations Engineers**
The team responsible for deploying, configuring, and monitoring the aiOps pipeline.
They manage environment-specific configuration (.env.*), shard coordination tuning
(SHARD_LEASE_TTL_SECONDS), and peak baseline depth (STAGE2_PEAK_HISTORY_MAX_DEPTH).
The TTL race condition exposes them to duplicate scope processing detectable only via
audit logs. The 1-hour peak baseline window forces them to tolerate misclassifications
they cannot correct without a code change. After this release, environment-specific
depth configuration and correct lease TTL margins are under their direct operational
control.

### Secondary Users

**Incident Responders (ServiceNow / PagerDuty / Slack)**
Downstream recipients of the pipeline's action outputs via outbound integrations
(PagerDuty Events V2, ServiceNow table API, Slack webhook). Currently receive no
TICKET or PAGE traffic due to AG4 suppression. These are not direct users of the
pipeline but are the ultimate consumers of its correct behaviour.

**Audit & Compliance Reviewers**
Consumers of ActionDecisionV1 audit trails and stored casefiles. Every audit record
currently carries diagnosis_confidence=0.0 and LOW_CONFIDENCE regardless of actual
evidence strength, making the audit trail unreliable as a decision record. After
this release, confidence values and reason codes will reflect real scoring outcomes,
enabling meaningful audit and replay analysis.

### User Journey

**Platform SRE — Before Fix:**
Anomaly event detected → pipeline runs → AG4 evaluates confidence (always 0.0) →
caps to OBSERVE → no escalation fired → SRE unalerted → manual detection required.

**Platform SRE — After Fix:**
Anomaly event detected → evidence scored (coverage + sustained + peak) →
diagnosis_confidence populated (e.g. 0.75) → AG4 clears (>= 0.6, sustained=true) →
TICKET or PAGE action fired → PagerDuty/ServiceNow receives event → SRE on-call
alerted with traceable audit record.

**Platform Ops — Before Fix:**
Pipeline deployed across envs → single global STAGE2_PEAK_HISTORY_MAX_DEPTH=12
(1 hour) → peak misclassifications untunable without code change → shard lease TTL
potentially shorter than cycle duration → duplicate processing logged.

**Platform Ops — After Fix:**
Environment-specific depth configured (prod=30d, uat=15d, dev=7d) → statistical
baseline quality improved per environment → SHARD_LEASE_TTL_SECONDS set with margin
→ duplicate processing risk eliminated.

---

## Success Metrics

### Business Objectives

1. Restore pipeline escalation capability — TICKET and PAGE actions must be
   reachable in production after this release. AG4 has never passed a high-urgency
   action; this release makes the gating mechanism functional for the first time.

2. Reduce operational risk from duplicate scope processing — the TTL race condition
   must be eliminated before scaling pod count or increasing cycle frequency.

3. Establish a meaningful audit baseline — confidence and reason codes in
   ActionDecisionV1 records must reflect real scoring outcomes, making audit trails
   usable for post-incident analysis and replay.

### Key Performance Indicators

**Fix #1 — Shard Lease TTL**

- KPI: Zero overlapping scope processing events per shard per cycle in UAT audit logs.
- KPI: SHARD_LEASE_TTL_SECONDS configured with margin above observed p95 cycle
  duration, measured from deployed UAT run logs (local runs are not representative).
- Note: Cycle duration baseline must be established from a UAT deployment before the
  TTL value is finalised. The checkpoint mechanism remains the downstream safety net
  if a race occurs before the value is tuned.

**Fix #2 — Peak History Depth**

- KPI: All three environment .env.* files carry correct STAGE2_PEAK_HISTORY_MAX_DEPTH
  values (prod=30d, uat=15d, dev=7d) with no environment falling back to the legacy
  12-sample default post-deploy.
- KPI: Proportion of PeakWindowContext records carrying INSUFFICIENT_HISTORY reason
  code decreases in UAT over the first 24 hours after deploy, measured via existing
  OTLP/Prometheus telemetry (not available locally — requires deployed environment).
- KPI: No regression in peak classification stability vs pre-release baseline.

**Fix #3 — AG4 Confidence Scoring**

- KPI: diagnosis_confidence is non-zero in audit trail records for all scopes with
  at least one PRESENT evidence signal (zero is no longer the universal value).
- KPI: Confidence score distribution shows meaningful variance across scopes — not
  a flat 0.0 distribution.
- KPI: LOW_CONFIDENCE reason code appears only on scopes with genuinely weak evidence
  coverage, not as a universal default across all gate evaluations.
- KPI: At least one TICKET or PAGE action decision is produced in UAT against a
  scenario with PRESENT evidence + sustained=true (no specific harness scenario
  pre-defined; UAT calibration is required to establish the threshold baseline).
- KPI: Existing action decision counters and gate reason code counters in
  Prometheus/OTLP reflect expected distributions post-deploy (requires UAT/prod
  access — not validatable locally).

### Validation Approach

- Fix #1 and Fix #2 config correctness: verifiable in any environment via config
  inspection and log review.
- Fix #3 scoring logic correctness: unit-testable locally with synthetic
  evidence/peak/sustained inputs against known expected outputs.
- Fix #3 threshold calibration and KPI telemetry: UAT deployment required.
  No production baseline exists for AG4 behaviour — UAT is the calibration step.
- Full telemetry KPIs: require access to deployed Prometheus/OTLP stack,
  not available on local development machines.

---

## MVP Scope

### Core Features (This Release)

**Fix 1 — Shard Lease TTL Configuration**
- Update SHARD_LEASE_TTL_SECONDS in all environment configurations to exceed
  the maximum expected cycle duration plus a safety margin.
- Cycle duration baseline must be measured from a UAT deployment before the
  final value is set. The checkpoint mechanism is the backstop in the interim.

**Fix 2 — Environment-Specific Peak History Depth**
- Set STAGE2_PEAK_HISTORY_MAX_DEPTH per environment in .env.* files:
  prod = 30 days, uat = 15 days, dev = 7 days.
- Remove reliance on the global 12-sample default in all deployed environments.
- Update configuration documentation to reflect environment-specific values.

**Fix 3 — Deterministic Hot-Path Confidence Scoring**
- Implement a new deterministic scoring function (hot-path-local) that computes
  diagnosis_confidence (0.0–1.0) from three signal tiers:
    - Tier 1: Evidence status coverage ratio (PRESENT/ABSENT/UNKNOWN/STALE)
    - Tier 2: Sustained status (is_sustained + consecutive bucket ratio)
    - Tier 3: Peak window classification (is_peak_window / is_near_peak_window)
- Derive proposed_action from the same signals.
- Enrich GateInputContext with both values before collect_gate_inputs_by_scope
  is called in the gating stage. No contract or schema changes — both fields
  already exist with safe defaults.
- Include comprehensive unit tests covering AG4 boundary conditions (0.59 caps,
  0.60 passes), all-UNKNOWN floor behaviour, and PRESENT+sustained+peak ceiling.
- D6 invariant preserved: cold-path LLM output has zero influence.

### Out of Scope for This Release

- Per-stream seasonality-aware peak classification via peak_window_policy from
  topology registry (existing config field is loaded but implementation is
  missing — tracked as a follow-on item).
- Confidence threshold tuning beyond the v1 heuristic — calibration is a
  post-UAT activity based on real telemetry.
- New harness acceptance scenarios specifically for AG4 gate validation.
- Any changes to frozen contracts, casefile schemas, or audit replay logic.

### MVP Success Criteria

- All three .env.* files updated and verified — no environment falls back to
  legacy defaults.
- Unit test suite passes with 0 skips, covering all confidence scoring boundary
  conditions.
- At least one TICKET or PAGE action is produced in UAT for a scope with
  PRESENT evidence and sustained=true.
- diagnosis_confidence shows non-zero variance in UAT audit records.
- No duplicate scope processing events observed in UAT audit logs per shard
  per cycle.

### Future Vision

- **Seasonality-aware peak classification** — consume per-stream peak_window_policy
  from the topology registry; classify peak windows using time-of-day buckets
  (business hours vs off-hours) rather than flat statistical percentiles.
- **Dynamic confidence threshold tuning** — use UAT/prod telemetry to calibrate
  the scoring tier weights and the AG4 0.6 threshold against real anomaly
  distributions.
- **Expanded confidence signals** — incorporate additional hot-path signals
  (e.g. blast radius, downstream impact count) as confidence amplifiers once
  the v1 baseline is validated.
- **Per-environment TTL automation** — derive SHARD_LEASE_TTL_SECONDS from
  observed p95 cycle duration telemetry rather than manual configuration.
