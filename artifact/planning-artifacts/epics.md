---
stepsCompleted: ['step-01-validate-prerequisites', 'step-02-design-epics', 'step-03-create-stories', 'step-04-final-validation']
inputDocuments:
  - artifact/planning-artifacts/prd.md
  - artifact/planning-artifacts/architecture/index.md
---

# aiOps - Epic Breakdown

## Overview

This document provides the complete epic and story breakdown for aiOps, decomposing the requirements from the PRD, UX Design if it exists, and Architecture requirements into implementable stories.

## Requirements Inventory

### Functional Requirements

FR1: The hot-path gating stage computes `diagnosis_confidence` (0.0-1.0) from a deterministic three-tier scoring function using evidence status counts, sustained state, and peak window classification.
FR2: Tier 1 computes a base coverage ratio from PRESENT evidence across total evaluated signals, with UNKNOWN weighted below PRESENT.
FR3: Tier 2 applies a sustained amplifier when `is_sustained=True` using consecutive bucket streak ratio; `is_sustained=None` is treated conservatively as non-amplifying.
FR4: Tier 3 applies a peak amplifier when `is_peak_window=True` or `is_near_peak_window=True`, with magnitude proportional to peak proximity.
FR5: The scoring logic derives `proposed_action` from the same signals; PRESENT+sustained+peak can produce TICKET/PAGE candidate actions, while insufficient confidence produces OBSERVE.
FR6: The gating stage enriches `GateInputContext` with `diagnosis_confidence` and `proposed_action` before `collect_gate_inputs_by_scope`.
FR7: On scoring exceptions, the system falls back safely to `diagnosis_confidence=0.0` and `proposed_action=OBSERVE`.
FR8: AG4 evaluates `diagnosis_confidence >= 0.6` as the confidence floor for TICKET/PAGE eligibility.
FR9: AG4 evaluates `is_sustained=True` as an independent sustained condition.
FR10: AG4 caps actions to OBSERVE when `diagnosis_confidence < 0.6` regardless of other gate states.
FR11: `ActionDecisionV1` records `diagnosis_confidence` and reason code for every AG4 evaluation.
FR12: Operators can configure `STAGE2_PEAK_HISTORY_MAX_DEPTH` per environment in `.env.prod`, `.env.uat`, and `.env.dev` without code changes.
FR13: The system loads environment-specific `STAGE2_PEAK_HISTORY_MAX_DEPTH` via `APP_ENV` selection with no fallback to global defaults when env values are present.
FR14: Configuration docs express depth sample counts with day conversions (prod=8640/30d, uat=4320/15d, dev=2016/7d at 5-minute intervals).
FR15: Operators can configure `SHARD_LEASE_TTL_SECONDS` per environment in `.env.*` files without code changes.
FR16: `SHARD_LEASE_TTL_SECONDS` is set above UAT-measured p95 cycle duration with at least a 30-second safety margin.
FR17: Residual shard race effects are suppressed by checkpoint deduplication so duplicate scope processing effects do not propagate downstream.
FR18: `ActionDecisionV1` carries non-zero `diagnosis_confidence` for scopes with at least one PRESENT evidence signal.
FR19: Audit records carry differentiated reason codes (for example `HIGH_CONFIDENCE_SUSTAINED_PEAK` vs `LOW_CONFIDENCE_INSUFFICIENT_EVIDENCE`) rather than universal `LOW_CONFIDENCE`.
FR20: `reproduce_gate_decision()` replays stored `CaseFileTriageV1` and produces identical `ActionDecisionV1` outputs, including `diagnosis_confidence`, given the same scoring policy version.

### NonFunctional Requirements

NFR1: Confidence scoring adds less than 1ms p99 latency per scoring invocation in the hot-path gating stage.
NFR2: Hot-path gate evaluation p99 remains less than or equal to 500ms per cycle.
NFR3: Peak-profile memory scales linearly with `STAGE2_PEAK_HISTORY_MAX_DEPTH` and avoids heap exhaustion/OOM under normal load up to prod depth.
NFR4: Scoring introduces no new external I/O, credentials, or sensitive logging fields.
NFR5: `STAGE2_PEAK_HISTORY_MAX_DEPTH` and `SHARD_LEASE_TTL_SECONDS` are non-secret operational values safe for version-controlled env files.
NFR6: Scoring must not raise unhandled exceptions; failures must fail-safe to zero/OBSERVE defaults.
NFR7: `is_sustained=None` must be handled conservatively and never treated as `True`.
NFR8: All `.env.*` files must define explicit depth values with no fallback to legacy 12-sample defaults.
NFR9: `diagnosis_confidence` must be non-zero in `ActionDecisionV1` for scopes with at least one PRESENT evidence signal.
NFR10: `LOW_CONFIDENCE` must not be universal; UAT records must include at least one non-`LOW_CONFIDENCE` reason code.
NFR11: Confidence distribution in UAT must show variance; standard deviation below 0.05 across first 100 scored events indicates regression.
NFR12: Policy version fields in `CaseFileTriageV1` remain stamped, including scoring-policy version semantics.
NFR13: Scoring is fully unit-testable with deterministic synthetic inputs and no external service mocks.
NFR14: Full regression suite completes with 0 skipped tests post-change.
NFR15: AG4 boundaries are covered in tests (0.59 caps OBSERVE, 0.60 allows TICKET/PAGE, all-UNKNOWN remains below 0.6, PRESENT+sustained+peak reaches at least 0.6).
NFR16: All three fix components (scoring, peak depth config, TTL config) ship as one coordinated release.
NFR17: Documentation in `docs/` is updated for env-specific depth values and TTL calibration procedure in the same change set.
NFR18: Documentation uses project-native terminology only and excludes BMAD/workflow/story-ID references.

### Additional Requirements

- Starter template requirement: no starter template adoption; architecture explicitly marks this as a brownfield surgical fix and mandates preserving existing project structure and dependency graph.
- Preserve D6 invariant: scoring logic must remain hot-path-local with no import path to `diagnosis/` (cold-path LLM output must have zero influence on confidence).
- Preserve frozen contracts: no contract/schema changes to `GateInputContext` or `ActionDecisionV1`; enrich existing fields only.
- Keep action-authority hierarchy: AG0-AG6 and environment caps remain final authorities; scoring/proposed action is candidate input and can only be capped downward.
- Keep externalized policy authority in existing config/policy files; no movement of policy decisions into hardcoded logic.
- Environment configuration requirement: update and validate `config/.env.*` values for depth/TTL consistency with APP_ENV selection.
- Infrastructure/observability requirement: verify UAT telemetry and logs (OTLP/Prometheus and structured logs) to validate confidence distribution, `INSUFFICIENT_HISTORY` trend reduction, and zero overlap behavior.
- Integration boundary requirement: do not alter external integration adapters (`integrations/`) for PagerDuty/ServiceNow/Slack as part of this fix.
- Coordination reliability requirement: maintain checkpoint deduplication behavior as residual race safety net during TTL calibration.
- Testing requirement: maintain deterministic replay/backward-compatibility coverage (`reproduce_gate_decision`) for both pre-score and post-score records.

### FR Coverage Map

FR1: Epic 1 - Deterministic confidence computation from hot-path signals
FR2: Epic 1 - Tier-1 evidence coverage ratio logic
FR3: Epic 1 - Tier-2 sustained amplifier behavior
FR4: Epic 1 - Tier-3 peak amplifier behavior
FR5: Epic 1 - Proposed-action derivation from the scoring signal set
FR6: Epic 1 - GateInputContext enrichment before gate input collection
FR7: Epic 1 - Exception fail-safe to zero confidence and OBSERVE action
FR8: Epic 1 - AG4 confidence floor enforcement at 0.6
FR9: Epic 1 - AG4 sustained-condition enforcement
FR10: Epic 1 - AG4 low-confidence cap to OBSERVE
FR11: Epic 1 - Audit trail includes confidence and reason code
FR12: Epic 2 - Environment-specific peak history depth configuration
FR13: Epic 2 - APP_ENV-based depth loading without fallback to legacy default
FR14: Epic 2 - Depth/day conversion documentation accuracy
FR15: Epic 2 - Environment-specific shard lease TTL configuration
FR16: Epic 2 - TTL calibration from UAT p95 plus safety margin
FR17: Epic 2 - Residual race protection via checkpoint deduplication
FR18: Epic 1 - Non-zero confidence for scopes with PRESENT evidence
FR19: Epic 1 - Differentiated reason-code taxonomy in audit records
FR20: Epic 3 - Replay determinism for pre-score and post-score records

## Epic List

### Epic 1: Trustworthy Escalation Decisions
Enable on-call engineers to receive correct TICKET/PAGE escalations from deterministic confidence and sustained evidence instead of universal OBSERVE suppression.
**FRs covered:** FR1, FR2, FR3, FR4, FR5, FR6, FR7, FR8, FR9, FR10, FR11, FR18, FR19

### Epic 2: Operable Environment Controls for Signal Quality and Lease Safety
Enable platform operations to tune peak-history depth and shard lease TTL per environment without code changes, reducing calibration and race risk.
**FRs covered:** FR12, FR13, FR14, FR15, FR16, FR17

### Epic 3: Replayable Audit Assurance and Release-Grade Verification
Enable engineering and audit stakeholders to verify decision reproducibility and backward compatibility for production confidence in releases.
**FRs covered:** FR20

## Epic 1: Trustworthy Escalation Decisions

Deliver deterministic scoring and AG4 integration so high-confidence sustained events can escalate with explainable audit outcomes.

### Story 1.1: Implement Deterministic Confidence Scoring Core

As a Platform SRE,
I want confidence scores to be computed deterministically from evidence, sustained, and peak inputs,
So that gate decisions are explainable and repeatable.

**FRs Implemented:** FR1, FR2, FR3, FR4, FR5, FR7

**Acceptance Criteria:**

**Given** evidence status counts and sustained/peak context are available for a scope
**When** the scoring function executes in the gating stage
**Then** it computes `diagnosis_confidence` in the `0.0..1.0` range using tiered logic
**And** it derives a candidate `proposed_action` from the same inputs

**Given** `is_sustained=None` is present from degraded coordination context
**When** the scoring function evaluates tier amplifiers
**Then** sustained amplification is not applied
**And** the behavior remains deterministic for identical inputs

**Given** the scoring function raises an internal exception
**When** gating continues
**Then** the output falls back to `diagnosis_confidence=0.0` and `proposed_action=OBSERVE`
**And** processing does not terminate with an unhandled exception

### Story 1.2: Enrich Gate Inputs and Enforce AG4 Confidence/Sustained Rules

As a Platform SRE,
I want AG4 to evaluate both confidence and sustained conditions with clear capping behavior,
So that escalations only occur for strong, sustained signals.

**FRs Implemented:** FR6, FR8, FR9, FR10

**Acceptance Criteria:**

**Given** scoring outputs are produced for a scope
**When** gate inputs are assembled
**Then** `GateInputContext` is enriched with both `diagnosis_confidence` and `proposed_action`
**And** enrichment occurs before `collect_gate_inputs_by_scope`

**Given** AG4 evaluates a scope with `diagnosis_confidence < 0.6`
**When** candidate action is TICKET or PAGE
**Then** AG4 caps the action to OBSERVE
**And** cap behavior is independent of other positive gate signals

**Given** AG4 evaluates a scope with `diagnosis_confidence >= 0.6` and `is_sustained=True`
**When** environment caps permit the candidate action
**Then** AG4 allows TICKET/PAGE progression
**And** PAGE outside PROD+TIER_0 remains blocked by existing cap authority

**Given** AG4 evaluates a scope with `diagnosis_confidence >= 0.6` and `is_sustained=False`
**When** candidate action is TICKET or PAGE
**Then** AG4 suppresses escalation to OBSERVE
**And** suppression reasoning is captured as sustained-condition failure

### Story 1.3: Persist Differentiated Confidence and Reason-Code Audit Outcomes

As an Incident Responder,
I want each decision record to include meaningful confidence and reason details,
So that I can distinguish weak-signal silence from valid escalations.

**FRs Implemented:** FR11, FR18, FR19

**Acceptance Criteria:**

**Given** a scope contains at least one PRESENT evidence signal
**When** `ActionDecisionV1` is written
**Then** `diagnosis_confidence` is non-zero for that decision path
**And** values vary across scopes rather than collapsing to a flat default

**Given** decisions are persisted for mixed confidence scenarios
**When** reason codes are assigned
**Then** differentiated codes are emitted (for example high-confidence sustained-peak vs insufficient-evidence low-confidence)
**And** `LOW_CONFIDENCE` is no longer universal across records

## Epic 2: Operable Environment Controls for Signal Quality and Lease Safety

Provide operations-controlled configuration for peak history and shard lease timing to improve scoring context quality and coordination safety.

### Story 2.1: Configure Environment-Specific Peak History Depth and Loading

As a Platform Operations Engineer,
I want explicit peak-history depth values per environment,
So that scoring has sufficient baseline context without code changes.

**FRs Implemented:** FR12, FR13, FR14

**Acceptance Criteria:**

**Given** environment files are maintained for prod, uat, and dev
**When** peak depth configuration is applied
**Then** each environment defines `STAGE2_PEAK_HISTORY_MAX_DEPTH` explicitly
**And** values align with documented day conversions at 5-minute intervals

**Given** application startup selects env config through `APP_ENV`
**When** settings are loaded
**Then** environment-specific depth values are used
**And** no fallback to the legacy 12-sample default occurs when explicit values exist

**Given** `STAGE2_PEAK_HISTORY_MAX_DEPTH` is missing or invalid for the selected `APP_ENV`
**When** configuration validation executes at startup
**Then** the system emits an operator-visible validation warning or startup failure with the invalid key and environment
**And** service startup does not continue with an implicit legacy default value

### Story 2.2: Calibrate and Apply Shard Lease TTL with Race-Safety Guardrails

As a Platform Operations Engineer,
I want shard lease TTL calibrated from observed UAT cycle timing,
So that overlapping shard processing risk is controlled during operations.

**FRs Implemented:** FR15, FR16, FR17

**Acceptance Criteria:**

**Given** UAT cycle durations are observed and p95 is measured
**When** `SHARD_LEASE_TTL_SECONDS` is set
**Then** configured TTL exceeds measured p95 by at least 30 seconds
**And** the calibration basis is documented for operational review

**Given** transient residual race windows can still occur during calibration
**When** duplicate processing attempts are encountered
**Then** checkpoint deduplication suppresses duplicate downstream processing effects
**And** overlap effects do not propagate to external action systems

## Epic 3: Replayable Audit Assurance and Release-Grade Verification

Ensure decision replay remains deterministic across historical and newly scored records for audit trust and safe rollout.

### Story 3.1: Validate Replay Determinism Across Pre-Score and Post-Score Casefiles

As an Audit and Compliance Reviewer,
I want replay outputs to remain identical for identical inputs across casefile generations,
So that decision histories remain trustworthy and defensible.

**FRs Implemented:** FR20

**Acceptance Criteria:**

**Given** stored casefiles from both pre-release (`confidence=0.0`) and post-release scored records
**When** `reproduce_gate_decision()` is executed under the same policy version
**Then** replayed `ActionDecisionV1` outputs match expected deterministic results
**And** backward compatibility is preserved without contract/schema migration

### Story 3.2: Enforce Deterministic Test and Regression Quality Gate

As a Developer,
I want targeted scoring/gating boundaries and full regression to pass with zero skips,
So that release readiness is demonstrated objectively.

**FRs Implemented:** FR20 (verification and release readiness enforcement)
**NFRs Validated:** NFR13, NFR14, NFR15

**Acceptance Criteria:**

**Given** AG4 boundary scenarios are encoded in unit tests
**When** tests execute for score `0.59`, `0.60`, all-UNKNOWN, and PRESENT+sustained+peak cases
**Then** gate outcomes match policy expectations
**And** tests remain deterministic with no external-service dependency for scoring logic

**Given** the full project regression suite is executed with required runtime prerequisites
**When** the quality gate runs
**Then** all tests pass
**And** skipped-test count is zero
