# Story 2.3: Peak/Near-Peak Classification

Status: review

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a platform operator,
I want the system to compute peak/near-peak classification per (env, cluster_id, topic) against historical baselines,
so that anomalies during peak traffic are distinguished from off-peak anomalies for accurate gating decisions (FR3).

## Acceptance Criteria

1. **Given** evidence metrics and historical baseline data are available  
   **When** peak classification is computed  
   **Then** each `(env, cluster_id, topic)` is classified as `PEAK`, `NEAR_PEAK`, or `OFF_PEAK` based on p90/p95 of messages-in rate.

2. **And** baseline computation uses at least 7 days of history when available, and produces a lower-confidence fallback when less history exists.

3. **And** peak profiles are recomputed on a weekly cadence defined by `peak-policy-v1`.

4. **And** peak profile artifacts are cacheable under Redis `peak:{key}` entries with environment-specific TTLs from `redis-ttl-policy-v1`.

5. **And** classification output is available for downstream gating inputs (AG4 sustained+confidence gate and AG6 postmortem predicate evaluation).

6. **And** unit tests verify: known-baseline classification, near-peak boundary behavior around p90/p95 thresholds, and insufficient-history handling.

## Tasks / Subtasks

- [x] Task 1: Implement peak domain model layer and policy loading (AC: 1, 2, 3)
  - [x] Add `PeakClassification`, `PeakProfile`, and result container models in `src/aiops_triage_pipeline/models/peak.py`.
  - [x] Load and validate `peak-policy-v1` and `redis-ttl-policy-v1` through existing `load_policy_yaml(...)` patterns.
  - [x] Encode explicit classification states (`PEAK`, `NEAR_PEAK`, `OFF_PEAK`, and UNKNOWN-compatible path when evidence is missing).

- [x] Task 2: Implement baseline derivation + classification stage logic (AC: 1, 2, 3, 5)
  - [x] Implement Stage 2 logic in `src/aiops_triage_pipeline/pipeline/stages/peak.py` to group evidence by `(env, cluster_id, topic)`.
  - [x] Compute baseline percentiles from historical windows and classify current interval values against policy thresholds.
  - [x] Implement insufficient-history behavior with deterministic fallback classification + confidence signal.
  - [x] Preserve UNKNOWN-not-zero semantics for missing required metric series.

- [x] Task 3: Implement peak profile Redis cache adapter (AC: 3, 4)
  - [x] Implement `src/aiops_triage_pipeline/cache/peak_cache.py` with `peak:{key}` namespace and env-specific TTL application.
  - [x] Ensure cache read/write behavior is deterministic and does not become system-of-record.
  - [x] Ensure cache miss path recomputes and repopulates profile data correctly.

- [x] Task 4: Wire Stage 2 output for downstream consumers (AC: 5)
  - [x] Extend stage output contract to expose peak/near-peak flags by normalized scope.
  - [x] Ensure output shape is consumable by later AG4/AG6 gating and postmortem evaluation stages without ad hoc remapping.

- [x] Task 5: Add/extend tests for peak classification and cache behavior (AC: 6)
  - [x] Add unit tests for percentile threshold boundaries and classification correctness.
  - [x] Add unit tests for insufficient-history and missing-series handling.
  - [x] Add cache tests for key naming, TTL selection per environment, hit/miss behavior, and deterministic serialization.
  - [x] Add targeted integration test coverage to prove Stage 1 evidence rows feed Stage 2 classifications as expected.

- [x] Task 6: Quality gates
  - [x] Run `uv run pytest -q`.
  - [x] Run focused peak-related test modules during iteration.
  - [x] Run `uv run ruff check`.

## Dev Notes

### Developer Context Section

- This story introduces **Stage 2 peak/near-peak classification** and must remain a deterministic extension of the already implemented Stage 1 evidence/anomaly flow from Story 2.2.
- The classification scope for this story is topic-level identity: `(env, cluster_id, topic)` using the canonical metric `topic_messages_in_per_sec` from `prometheus-metrics-contract-v1`.
- Keep Story 2.3 narrowly scoped:
  - implement peak profile model(s), baseline computation, classification output, and cache support;
  - do not implement sustained window logic (Story 2.4), full UNKNOWN propagation orchestration (Story 2.5), or AG gate engine logic (Epic 5).
- Policy-driven behavior is mandatory:
  - thresholds and bucket defaults come from `peak-policy-v1`;
  - TTL behavior comes from `redis-ttl-policy-v1`;
  - avoid hardcoded environment- or cluster-specific rules in stage logic.
- UNKNOWN-not-zero must be preserved:
  - missing required series remains UNKNOWN signal and must not be transformed to numeric defaults;
  - classification should clearly represent insufficient evidence/history conditions without faking confidence.
- Existing continuity anchors from Story 2.2 to reuse:
  - normalized `EvidenceRow` model and identity handling in `pipeline/stages/evidence.py`;
  - deterministic stage processing and structured warning patterns;
  - hot-path async safety expectations (`asyncio` friendly, no blocking I/O in compute path).

### Technical Requirements

- Implement explicit peak domain types in `src/aiops_triage_pipeline/models/peak.py` for:
  - per-scope baseline profile (percentiles + sample/history metadata),
  - per-scope classification output,
  - stage result container consumable by downstream pipeline stages.
- Stage 2 classification logic in `src/aiops_triage_pipeline/pipeline/stages/peak.py` must:
  - derive topic-level scope keys exactly as `(env, cluster_id, topic)`,
  - consume normalized Stage 1 evidence rows (do not re-query Prometheus),
  - classify current value against policy thresholds (`peak_percentile`, `near_peak_percentile`),
  - expose deterministic outputs for downstream AG4/AG6 consumers.
- Baseline/history requirements:
  - target baseline depth is 7 days when available,
  - retain behavior for low-history inputs (degraded confidence / explicit fallback state),
  - recompute cadence aligns with `recompute_frequency=weekly` from peak policy.
- Cache requirements in `src/aiops_triage_pipeline/cache/peak_cache.py`:
  - use Redis key namespace `peak:{key}` only,
  - apply env-specific TTL from `redis-ttl-policy-v1` (`peak_profile_seconds`),
  - treat cache as optimization only (cache loss must not break correctness).
- Data truthfulness requirements:
  - missing series remains UNKNOWN signal, never numeric zero,
  - non-finite values should not be used to synthesize baseline/classification certainty,
  - classification output must distinguish `OFF_PEAK` from `UNKNOWN/INSUFFICIENT_DATA`.
- Logging/error behavior:
  - keep structured warning logging on malformed inputs with deterministic skip behavior,
  - avoid broad exception swallowing in stage core logic,
  - do not introduce network/file I/O into per-scope classification loops.

### Architecture Compliance

- Preserve hot-path staged orchestration: Stage 1 evidence collection/anomaly detection feeds Stage 2 peak classification without introducing a parallel ingestion path.
- Keep contract-first model discipline:
  - use explicit typed models (`frozen=True`) for peak profile/classification outputs where they behave as stage contracts;
  - keep policy values sourced from versioned artifacts rather than inline constants.
- Keep deterministic computation boundaries:
  - no non-deterministic ordering in per-scope aggregation/classification;
  - same evidence input must yield same peak output for reproducibility.
- Respect import and package boundaries:
  - Stage implementation remains in `pipeline/stages/peak.py`;
  - cache concerns remain in `cache/peak_cache.py`;
  - shared stage/domain data remains in `models/peak.py`.
- Preserve UNKNOWN semantics and downstream compatibility:
  - missing evidence must not be converted to OFF_PEAK;
  - outputs must provide clear signals that later AG4/AG6 logic can consume safely.

### Library / Framework Requirements

- Python/runtime:
  - maintain Python `>=3.13` typing and style already used in codebase.
- Pydantic:
  - prefer `BaseModel, frozen=True` for new stage output/contract-like models.
  - use model validators for nested immutability where mapping fields are exposed.
- Async behavior:
  - keep Stage 2 compute path synchronous-in-process over in-memory rows (no blocking calls).
  - if TaskGroups are introduced for fan-out, ensure `create_task()` is called only while group is active (Python 3.13 behavior).
- Redis/cache:
  - integrate with existing Redis policy contract (`RedisTtlPolicyV1`) and key namespace conventions.
- Policy loading:
  - use `load_policy_yaml(...)` in `config/settings.py`; keep `config` package generic and decoupled from specific contract classes.
- Logging:
  - structured logging via existing logger helpers, with machine-parseable event names/fields.

### File Structure Requirements

- Primary implementation files:
  - `src/aiops_triage_pipeline/models/peak.py`
  - `src/aiops_triage_pipeline/pipeline/stages/peak.py`
  - `src/aiops_triage_pipeline/cache/peak_cache.py`
- Likely integration touchpoints:
  - `src/aiops_triage_pipeline/models/evidence.py` (if Stage 2 output type is embedded)
  - `src/aiops_triage_pipeline/pipeline/scheduler.py` (if stage orchestration wiring is expanded)
  - `src/aiops_triage_pipeline/models/__init__.py` (exports for new peak models)
- Expected tests to add/update:
  - `tests/unit/pipeline/stages/test_peak.py` (new)
  - `tests/unit/cache/test_peak_cache.py` (new)
  - `tests/unit/contracts/test_policy_models.py` (only if policy model behavior requires updates)
  - `tests/integration/pipeline/test_evidence_prometheus_integration.py` (extend for Stage 2 output path if needed)

### Testing Requirements

- Unit test coverage (required):
  - percentile threshold classification for p90/p95 boundaries;
  - deterministic classification on repeated identical input;
  - insufficient-history fallback behavior;
  - missing-series/UNKNOWN handling without zero-defaulting;
  - per-scope grouping correctness for `(env, cluster_id, topic)`.
- Cache test coverage (required):
  - `peak:{key}` naming compliance;
  - env-specific TTL selection via `redis-ttl-policy-v1`;
  - cache hit/miss behavior and recompute path.
- Integration test coverage (targeted):
  - Stage 1 normalized evidence rows flow into Stage 2 classification outputs with expected shape.
- Quality gates:
  - `uv run pytest -q`
  - focused peak tests while iterating
  - `uv run ruff check`

### Previous Story Intelligence

- Story 2.2 established deterministic Stage 1 outputs and immutable evidence/anomaly models.
- Reuse existing normalization and scoping discipline from `collect_evidence_rows(...)`; do not redefine cluster/topic identity logic.
- Preserve recently hardened detector/stage patterns:
  - explicit threshold behavior with boundary tests,
  - structured warnings for malformed samples,
  - no broad exception handlers in core hot-path logic.
- Keep changeset focused and composable so Story 2.4 (sustained) can consume Stage 2 outputs without refactoring.

### Git Intelligence Summary

- Recent work pattern shows story-specific implementation followed by targeted hardening commits.
- Most relevant recent files for extension:
  - `src/aiops_triage_pipeline/pipeline/stages/evidence.py`
  - `src/aiops_triage_pipeline/pipeline/stages/anomaly.py`
  - `src/aiops_triage_pipeline/models/anomaly.py`
  - `src/aiops_triage_pipeline/models/evidence.py`
  - `tests/unit/pipeline/stages/test_anomaly.py`
  - `tests/unit/pipeline/stages/test_evidence.py`
- Guidance: keep Story 2.3 implementation narrowly scoped to Stage 2 peak modules + tests, then run full regression/lint.

### Latest Tech Information

- Snapshot date: **March 3, 2026**.
- Prometheus upstream context:
  - latest release observed: `v3.10.0` (released February 24, 2026);
  - current LTS track observed: `3.5` supported through July 31, 2026.
- Project compatibility implication:
  - local stack references Prometheus `v2.50.1`; Story 2.3 should avoid dependency on 3.x-only behavior unless a stack upgrade is explicitly planned.
- Prometheus API/query notes relevant to this story:
  - stable API remains `/api/v1`;
  - missing-series functions (`absent`, `absent_over_time`) remain current and align with UNKNOWN handling strategy.
- Runtime/dependency notes:
  - Python 3.13 TaskGroup behavior should be respected if asynchronous fan-out is introduced;
  - `pydantic==2.12.5` remains on current stable release line;
  - public release feeds currently show `redis-py` latest at `7.1.1`, while project pin is `redis==7.2.1` in current artifacts, so dependency bumps should verify source availability in the target package index.

### Project Structure Notes

- Alignment with unified project structure:
  - Story 2.3 cleanly maps to existing architecture slots (`models/peak.py`, `pipeline/stages/peak.py`, `cache/peak_cache.py`) that are currently placeholders.
  - Naming should follow current project conventions: snake_case modules, explicit model names, deterministic stage helper names.
- Detected variances:
  - architecture artifact describes a fuller Stage 2 pipeline than currently implemented in source; Story 2.3 intentionally closes this gap by implementing the first real Stage 2 peak slice.
  - several architecture-listed test files for peak are not yet present in repo; this story should introduce focused tests rather than broad speculative scaffolding.

### Project Context Reference

- Consolidated implementation guardrails and anti-pattern constraints sourced from `artifact/project-context.md`.

### References

- [Source: `artifact/planning-artifacts/epics.md#Story 2.3: Peak/Near-Peak Classification`]
- [Source: `artifact/planning-artifacts/epics.md#Story 2.2: Anomaly Pattern Detection`]
- [Source: `artifact/planning-artifacts/architecture.md#Pipeline Orchestration`]
- [Source: `artifact/planning-artifacts/architecture.md#Data Architecture`]
- [Source: `artifact/planning-artifacts/architecture.md#Structure Patterns`]
- [Source: `artifact/planning-artifacts/prd/functional-requirements.md` (FR3, FR7)]
- [Source: `artifact/project-context.md#Critical Don't-Miss Rules`]
- [Source: `artifact/project-context.md#Testing Rules`]
- [Source: `config/policies/peak-policy-v1.yaml`]
- [Source: `config/policies/redis-ttl-policy-v1.yaml`]
- [Source: `config/policies/prometheus-metrics-contract-v1.yaml`]
- [Source: `src/aiops_triage_pipeline/pipeline/stages/evidence.py`]
- [Source: `src/aiops_triage_pipeline/pipeline/stages/anomaly.py`]
- [Source: `src/aiops_triage_pipeline/models/evidence.py`]
- [Source: `artifact/implementation-artifacts/2-2-anomaly-pattern-detection.md`]
- [Source: `https://github.com/prometheus/prometheus/releases` (checked March 3, 2026)]
- [Source: `https://prometheus.io/docs/introduction/release-cycle/`]
- [Source: `https://prometheus.io/docs/prometheus/latest/querying/functions/`]
- [Source: `https://prometheus.io/docs/prometheus/latest/querying/api/`]
- [Source: `https://docs.python.org/3.13/library/asyncio-task.html#task-groups`]
- [Source: `https://github.com/redis/redis-py/releases`]
- [Source: `https://github.com/pydantic/pydantic/releases`]
- [Source: `https://pypi.org/project/prometheus-client/`]

### Story Completion Status

- Story file generated with comprehensive implementation context and marked `ready-for-dev`.
- Completion note: **Ultimate context engine analysis completed - comprehensive developer guide created**.

## Dev Agent Record

### Agent Model Used

GPT-5 Codex

### Debug Log References

- Story context assembled from sprint status, epics, architecture, PRD fallback, project context, previous story intelligence, git history, and latest technical verification.
- Output file initialized from template and completed section-by-section in workflow order.
- Implemented Stage 2 peak models, classification stage, and cache adapter with deterministic scope handling.
- Executed quality gates: focused peak tests, full test suite, and Ruff lint.

### Implementation Plan

- Add immutable peak domain models and downstream-friendly context mapping.
- Implement Stage 2 policy-driven classification using nearest-rank percentile thresholds and UNKNOWN-safe behavior.
- Add Redis cache helpers for `peak:{key}` profile caching with env-specific TTL from policy.
- Wire Stage 2 output into scheduler and add unit/integration coverage for Stage 1 -> Stage 2 flow.

### Completion Notes List

- Implemented immutable Stage 2 models: `PeakProfile`, `PeakClassification`, `PeakWindowContext`, and `PeakStageOutput`.
- Added policy loading for `peak-policy-v1` and `redis-ttl-policy-v1` via `load_policy_yaml(...)`.
- Implemented deterministic Stage 2 classification with p90/p95 thresholding, insufficient-history fallback confidence, and UNKNOWN-safe missing-series handling.
- Implemented Redis peak profile cache adapter with required `peak:{key}` namespacing, env-specific TTL lookup, deterministic serialization, and read-through miss recompute path.
- Wired Stage 2 output into scheduler with downstream-ready `peak_context_by_scope`.
- Added unit tests for peak boundaries, deterministic behavior, insufficient history, unknown-series handling, cache semantics, and scheduler wiring.
- Added integration coverage to verify Stage 1 evidence rows feed Stage 2 peak output shape.
- Quality gates passed: `uv run pytest -q` (203 passed) and `uv run ruff check` (all checks passed).
- Story status set to `review`.

### File List

- artifact/implementation-artifacts/2-3-peak-near-peak-classification.md
- artifact/implementation-artifacts/sprint-status.yaml
- src/aiops_triage_pipeline/cache/__init__.py
- src/aiops_triage_pipeline/cache/peak_cache.py
- src/aiops_triage_pipeline/models/__init__.py
- src/aiops_triage_pipeline/models/peak.py
- src/aiops_triage_pipeline/pipeline/scheduler.py
- src/aiops_triage_pipeline/pipeline/stages/__init__.py
- src/aiops_triage_pipeline/pipeline/stages/peak.py
- tests/integration/pipeline/test_evidence_prometheus_integration.py
- tests/unit/cache/test_peak_cache.py
- tests/unit/pipeline/stages/test_peak.py
- tests/unit/pipeline/test_scheduler.py

### Change Log

- 2026-03-03: Implemented Story 2.3 Stage 2 peak/near-peak classification, caching, scheduler wiring, and test coverage; moved status to `review`.
