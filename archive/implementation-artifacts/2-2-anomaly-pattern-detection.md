# Story 2.2: Anomaly Pattern Detection

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a platform operator,
I want the system to detect three anomaly patterns (consumer lag buildup, throughput-constrained proxy, and volume drop) from collected Prometheus telemetry,
so that the pipeline can identify real Kafka infrastructure issues and produce findings with explicit, per-finding evidence requirements (FR2, FR8).

## Acceptance Criteria

1. **Given** Prometheus metrics have been collected for an evaluation interval  
   **When** the anomaly detection engine processes interval metrics  
   **Then** it detects consumer lag buildup patterns.

2. **And** it detects throughput-constrained proxy patterns.

3. **And** it detects volume drop patterns.

4. **And** each detected finding declares its own `evidence_required[]` list (no central required-evidence registry).

5. **And** each detected finding is associated with its normalized scope key `(env, cluster_id, topic/group)` as appropriate by metric family.

6. **And** missing evidence is represented through existing `EvidenceStatus=UNKNOWN` semantics and is never interpreted as zero.

7. **And** unit tests verify detection behavior for each of the three patterns using harness-aligned telemetry characteristics.

8. **And** unit tests verify custom `evidence_required[]` construction and downstream compatibility with AG2 sufficiency evaluation inputs.

## Tasks / Subtasks

- [x] Task 1: Implement anomaly detection domain models and interfaces (AC: 1, 2, 3, 4, 5)
  - [x] Add model(s) for anomaly findings (pattern id/family, scope, severity, reason codes, `evidence_required[]`, `is_primary` hint).
  - [x] Keep models immutable where contract-like behavior is expected (`frozen=True` patterns consistent with project rules).
  - [x] Keep detection output keyed by normalized scope identity from Story 2.1 outputs.

- [x] Task 2: Implement consumer lag buildup detection (AC: 1, 4, 5, 6)
  - [x] Detect lag growth behavior using `consumer_group_lag` and offset/progress context from `consumer_group_offset`.
  - [x] Emit finding with anomaly family `CONSUMER_LAG` and required evidence primitives for AG2 evaluation.
  - [x] Ensure missing lag/offset series yields UNKNOWN-aware behavior (no zero-default shortcuts).

- [x] Task 3: Implement throughput-constrained proxy detection (AC: 2, 4, 5, 6)
  - [x] Detect constrained proxy pattern using throughput plus failure-rate context (`messages_in`, `total_produce_requests`, `failed_produce_requests`).
  - [x] Emit finding with anomaly family `THROUGHPUT_CONSTRAINED_PROXY`.
  - [x] Include explicit reason codes describing high throughput with elevated failure behavior.

- [x] Task 4: Implement volume drop detection (AC: 3, 4, 5, 6)
  - [x] Detect abrupt volume drop from expected ingress baseline context (using available interval evidence in this story; peak baseline integration remains Story 2.3).
  - [x] Emit finding with anomaly family `VOLUME_DROP`.
  - [x] Ensure low/near-zero observed traffic is distinguished from missing-series UNKNOWN.

- [x] Task 5: Wire anomaly detection into Stage 1 evidence flow outputs for downstream gating inputs (AC: 4, 5, 6, 8)
  - [x] Integrate detection entrypoint in the pipeline stage path without creating a parallel data-collection pipeline.
  - [x] Produce finding payloads consumable by later GateInput assembly (AG2 requires finding-declared evidence).
  - [x] Preserve deterministic behavior and structured warning/error logging conventions.

- [x] Task 6: Add unit and targeted integration tests (AC: 7, 8)
  - [x] Unit tests per anomaly detector with positive/negative and threshold-edge scenarios.
  - [x] Unit tests for `evidence_required[]` variability by finding type.
  - [x] Integration test using harness-like metric patterns to validate end-to-end detection output shape.

- [x] Task 7: Quality gates
  - [x] Run `uv run pytest -q` for full regression confidence.
  - [x] Run focused tests for detection/evidence modules during iteration.
  - [x] Run `uv run ruff check` for lint compliance.

## Dev Notes

### Developer Context Section

- This is Epic 2 Story 2.2 and builds directly on Story 2.1 evidence collection outputs (`collect_prometheus_samples`, `collect_evidence_rows`, and scope-key behavior).
- Scope for this story is anomaly finding generation only (FR2, FR8): no peak baseline computation (Story 2.3), no sustained-window computation (Story 2.4), and no full UNKNOWN propagation orchestration (Story 2.5).
- Detection must stay deterministic and hot-path friendly: no blocking external calls, no LLM dependency, and no non-deterministic ranking heuristics.
- Findings produced here are consumed by later GateInput assembly and AG2 sufficiency logic, so every finding must carry explicit `evidence_required[]`.
- Use Story 2.1 normalization and scope semantics:
  - Topic-scoped detectors: `(env, cluster_id, topic)`
  - Lag detectors: `(env, cluster_id, group, topic)`
- Preserve UNKNOWN-not-zero semantics end to end: missing series are UNKNOWN evidence, never numeric defaults.
- Reuse policy/contracts rather than ad-hoc constants:
  - `config/policies/prometheus-metrics-contract-v1.yaml`
  - `config/policies/rulebook-v1.yaml`
  - `config/policies/peak-policy-v1.yaml` (compatibility reference only for now)
- Keep implementation narrow and traceable so Stories 2.3/2.4/2.5 can extend without refactoring core detectors.

### Technical Requirements

- Implement three detector paths:
  - `CONSUMER_LAG`
  - `THROUGHPUT_CONSTRAINED_PROXY`
  - `VOLUME_DROP`
- Each detector emits finding objects that include:
  - deterministic anomaly family/pattern id
  - normalized scope key
  - `evidence_required[]`
  - machine-parseable reason codes
  - optional `is_primary` when multiple findings exist for one scope
- Evidence semantics:
  - Use existing Stage 1 collection outputs; do not create alternate metric-ingestion paths.
  - Missing or unavailable evidence stays UNKNOWN-aligned; do not impute zeros.
  - Distinguish low observed values from missing-series UNKNOWN for volume-drop logic.
- Identity and scoping requirements:
  - Lag detectors require `group` and `topic` labels in addition to `(env, cluster_id)`.
  - Topic-level detectors scope by `(env, cluster_id, topic)`.
  - Preserve deterministic key ordering and type consistency.
- Detector configuration:
  - Centralize detector thresholds/constants in one module.
  - If thresholds are introduced, document rationale and test boundary values.
  - Do not couple detector thresholds to full peak-profile policy internals in Story 2.3.
- Error and observability behavior:
  - For malformed samples or missing required labels, emit structured warnings and skip invalid sample/finding generation.
  - Do not throw uncaught raw exceptions from detector evaluation paths in hot-path processing.
  - Keep log fields consistent with structured logging conventions used in Story 2.1.

### Architecture Compliance

- Hot-path orchestration compliance:
  - Keep anomaly detection execution inside the hot-path stage flow and compatible with 5-minute scheduler cadence.
  - Do not add network calls, filesystem scans, or long-running loops in detector logic.
- Contract-first compliance:
  - Keep anomaly family naming compatible with `GateInputV1.anomaly_family` allowed values.
  - Keep finding payload shape aligned with `contracts/gate_input.py::Finding` expectations.
- Policy compliance:
  - Respect Rulebook defaults: `missing_series_policy=UNKNOWN_NOT_ZERO` and `required_evidence_policy=PRESENT_ONLY`.
  - Ensure detector outputs provide evidence keys AG2 can evaluate deterministically.
- Boundary compliance:
  - Keep changes localized to `pipeline/stages`, `models`, and related tests for this story.
  - Avoid premature coupling to topology/casefile/outbox/diagnosis modules beyond typed interface needs.
- Reliability and safety compliance:
  - On input insufficiency, degrade to no actionable finding or lower-confidence output; never fabricate certainty.
  - Preserve deterministic outcomes for identical input samples.

### Library / Framework Requirements

- Python/runtime:
  - Keep compatibility with Python `>=3.13` typing conventions (`X | None`, built-in generics).
  - Maintain async safety in hot path; avoid introducing blocking calls in detection paths.
- Data modeling:
  - Use Pydantic v2 model patterns for new detector/finding structures requiring validation and immutability.
  - Prefer `frozen=True` for contract-like structures consumed downstream.
- Prometheus integration:
  - Continue using Stage 1 normalized sample outputs from `integrations/prometheus.py` and `pipeline/stages/evidence.py`.
  - Do not bypass contract-driven metric identity from `prometheus-metrics-contract-v1`.
- Policy/config loading:
  - Reuse existing policy loading patterns; do not hardcode environment-specific policy behavior in detectors.
- Logging/observability:
  - Use structured logging helpers from `logging/setup.py` and existing event-field conventions.
- Test stack:
  - Use existing `pytest` and `pytest-asyncio` patterns.
  - Keep detector unit tests fast/deterministic; add targeted integration checks where they provide unique confidence.

### Project Structure Notes

- Primary implementation targets:
  - `src/aiops_triage_pipeline/pipeline/stages/evidence.py` (integration point from collected samples into detection flow)
  - `src/aiops_triage_pipeline/models/evidence.py` (shared evidence/finding model additions where appropriate)
  - `src/aiops_triage_pipeline/contracts/gate_input.py` (compatibility reference for finding/evidence shape)
- Optional new modules if separation improves maintainability:
  - `src/aiops_triage_pipeline/pipeline/stages/anomaly.py` for detector orchestration
  - `src/aiops_triage_pipeline/models/anomaly.py` for detector/finding models
- Test targets:
  - `tests/unit/pipeline/stages/test_evidence.py` (extend evidence-stage wiring coverage)
  - `tests/unit/pipeline/stages/test_anomaly.py` (new detector-focused suite)
  - `tests/integration/pipeline/test_evidence_prometheus_integration.py` (targeted end-to-end detection shape verification)
- Alignment notes:
  - Follow existing package boundaries and snake_case naming conventions.
  - Keep contracts in `contracts/` as leaf artifacts; avoid reverse dependencies from contracts into pipeline modules.
- Detected variances:
  - Several downstream stage modules are intentionally sparse at this point (for example `peak.py`); Story 2.2 should implement only the minimal anomaly slice needed and avoid speculative scaffolding.

### Testing Requirements

- Unit tests (mandatory):
  - Consumer lag buildup detector:
    - positive detection when lag increases while offset movement indicates constrained consumption
    - negative case when lag is flat/decreasing
    - UNKNOWN/missing evidence handling does not produce false positives
  - Throughput-constrained proxy detector:
    - positive detection for high throughput plus elevated produce failure ratio
    - negative case for normal failure ratio under similar load
    - threshold-boundary behavior around cutoffs
  - Volume-drop detector:
    - positive detection for sharp traffic drop relative to prior interval context
    - negative case for stable low-volume topics that are not dropping
    - explicit distinction between near-zero present values and missing-series UNKNOWN
  - Finding shape tests:
    - each finding includes `evidence_required[]`, normalized scope key, anomaly family, and reason codes
    - per-finding `evidence_required[]` varies by anomaly type where expected (FR8)
- Integration tests (targeted):
  - Evidence collection + anomaly detection flow from normalized Stage 1 samples into detector outputs
  - Harness-aligned pattern verification for lag, proxy, and volume scenarios
- Regression expectations:
  - Existing Story 2.1 tests remain green
  - New detection logic must not break sample normalization/scoping behavior
  - Maintain deterministic outcomes without timing-flaky assertions
- Quality gates:
  - `uv run pytest -q`
  - focused detector/evidence tests during iteration
  - `uv run ruff check`

### Previous Story Intelligence

- Story 2.1 established:
  - contract-driven Prometheus metric query definitions
  - strict label normalization (`cluster_id := cluster_name`)
  - structured warning logging for malformed/unavailable telemetry
  - async-safe evidence collection path
- Carry forward successful patterns:
  - build anomaly detectors from normalized Stage 1 sample rows instead of re-parsing raw Prometheus payloads
  - preserve UNKNOWN semantics by skipping/imputing nothing for missing or non-finite values
  - keep machine-parseable structured logs (`event_type`, consistent fields)
- Defects corrected in Story 2.1 that must not regress:
  - no UNKNOWN-to-zero collapse
  - no blocking calls on hot-path async loop
  - no broad `except Exception` in core processing paths
  - no unguarded label access that can crash a whole interval
- Continuity guidance:
  - `collect_prometheus_samples` and `collect_evidence_rows` remain the natural feed for anomaly detection
  - keep detector wiring narrow so Stories 2.3/2.4/2.5 can layer cleanly

### Git Intelligence Summary

- Recent commit pattern:
  - story implementation commits are typically followed by focused code-review fix commits
  - scope discipline is strong: changes usually stay inside story boundaries plus tests/artifacts
- Most recent commit titles:
  - `96c80c7 Epic 1 Retrospective — foundation complete, clear to proceed to Epic 2`
  - `17a56f0 Story 1.9: Harness Traffic Generation — ready for review`
  - `1d18bea Story 1.8: Code review fixes — Local Development Environment`
  - `28b32b5 Story 1.8: Local Development Environment (docker-compose) - ready for review`
  - `ab1e40f Story 1.7: Code review fixes — Structured Logging Foundation`
- Actionable guidance for Story 2.2:
  - keep the changeset focused on anomaly detection + tests + story artifact updates
  - expect a follow-up review-fix pass; keep detector code easy to revise in targeted patches
  - favor incremental additions over broad refactors in currently sparse stage modules

### Latest Tech Information

- Snapshot date for this section: **March 3, 2026**.
- Prometheus release context:
  - Upstream `prometheus/prometheus` currently shows release **3.10.0** published **October 29, 2025**.
  - Prometheus support matrix indicates **Prometheus 3.5** is LTS through **July 31, 2026**.
  - Project implication: local stack currently pins Prometheus `v2.50.1`; Story 2.2 should avoid dependence on 3.x-only behavior unless an explicit stack upgrade is planned.
- PromQL missing-series semantics:
  - `absent()` and `absent_over_time()` remain standard functions for detecting missing series.
  - Use these semantics as guidance for UNKNOWN classification; do not map absence to numeric zero.
- Prometheus HTTP API stability:
  - `/api/v1/query` remains documented under the stable v1 HTTP API.
  - Existing Story 2.1 client path remains aligned.
- Python runtime note (3.13):
  - `asyncio.TaskGroup.create_task()` closes the coroutine if the task group is inactive.
  - Implication: if detector fan-out uses TaskGroups, create tasks only while the group is active.
- Python `prometheus-client` package context:
  - Latest PyPI release is **0.24.1** (released **January 14, 2026**).
  - Repository currently uses `prometheus-client~=0.24.0` for harness/testing, aligned with current patch line.

### Project Context Reference

- [Source: `artifact/planning-artifacts/epics.md#Story 2.2: Anomaly Pattern Detection`]
- [Source: `artifact/planning-artifacts/epics.md#Story 2.1: Prometheus Metric Collection & Evaluation Cadence`]
- [Source: `artifact/planning-artifacts/architecture.md#Pipeline Orchestration`]
- [Source: `artifact/planning-artifacts/architecture.md#Cross-Cutting Concerns Identified`]
- [Source: `artifact/planning-artifacts/prd/functional-requirements.md` (FR2, FR8)]
- [Source: `artifact/planning-artifacts/prd/event-driven-aiops-platform-specific-requirements.md#Hot-Path vs Cold-Path Separation`]
- [Source: `artifact/project-context.md#Critical Don't-Miss Rules`]
- [Source: `artifact/project-context.md#Framework-Specific Rules`]
- [Source: `artifact/implementation-artifacts/2-1-prometheus-metric-collection-and-evaluation-cadence.md#Previous Story Intelligence`]
- [Source: `config/policies/prometheus-metrics-contract-v1.yaml`]
- [Source: `config/policies/rulebook-v1.yaml`]
- [Source: `config/policies/peak-policy-v1.yaml`]
- [Source: `src/aiops_triage_pipeline/pipeline/stages/evidence.py`]
- [Source: `src/aiops_triage_pipeline/contracts/gate_input.py`]
- [Source: `https://github.com/prometheus/prometheus/releases` (checked March 3, 2026)]
- [Source: `https://prometheus.io/docs/introduction/release-cycle/`]
- [Source: `https://prometheus.io/docs/prometheus/latest/querying/functions/` (`absent`, `absent_over_time`)]
- [Source: `https://prometheus.io/docs/prometheus/latest/querying/api/`]
- [Source: `https://docs.python.org/3.13/library/asyncio-task.html#task-groups`]
- [Source: `https://pypi.org/project/prometheus-client/`]

## Dev Agent Record

### Agent Model Used

GPT-5 Codex

### Debug Log References

- Implemented immutable anomaly domain models in `src/aiops_triage_pipeline/models/anomaly.py` and exported model symbols via `src/aiops_triage_pipeline/models/__init__.py`.
- Implemented detector orchestration and detector functions in `src/aiops_triage_pipeline/pipeline/stages/anomaly.py` for `CONSUMER_LAG`, `THROUGHPUT_CONSTRAINED_PROXY`, and `VOLUME_DROP`.
- Added GateInput-compatible finding payload mapping in anomaly stage via `build_gate_findings_by_scope(...)`.
- Wired evidence + anomaly flow in `src/aiops_triage_pipeline/pipeline/stages/evidence.py` with `collect_evidence_stage_output(...)`.
- Added `EvidenceStageOutput` in `src/aiops_triage_pipeline/models/evidence.py` for downstream stage consumption.
- Added scheduler-to-stage runtime wiring via `run_evidence_stage_cycle(...)` in `src/aiops_triage_pipeline/pipeline/scheduler.py`.
- Updated consumer lag detector to require growth over interval samples and constrained offset progress.
- Updated volume drop detector to compare current sample against same-scope baseline context from earlier interval samples.
- Hardened nested immutability using `MappingProxyType` for evidence labels and scope maps.
- Added detector unit tests in `tests/unit/pipeline/stages/test_anomaly.py`.
- Extended evidence-stage unit tests in `tests/unit/pipeline/stages/test_evidence.py`.
- Added targeted integration flow test in `tests/integration/pipeline/test_evidence_prometheus_integration.py`.
- Added scheduler wiring test in `tests/unit/pipeline/test_scheduler.py`.
- Validation executed:
  - `uv run pytest -q` -> `186 passed`
  - `uv run ruff check` -> `All checks passed!`

### Completion Notes List

- Added explicit anomaly finding model and grouped detection result keyed by normalized scope identity.
- Implemented deterministic, threshold-based detectors for lag buildup, constrained proxy throughput failures, and volume drop.
- Implemented lag growth validation (start/end comparison) and explicit decreasing/flat negative-case coverage.
- Implemented volume-drop baseline comparison (`current` vs prior baseline samples) to avoid single-point false positives.
- Preserved UNKNOWN-not-zero semantics by requiring evidence presence for each detector and skipping detections when required series are missing.
- Added evidence-stage output assembly that includes normalized rows, anomaly findings, and GateInput-compatible finding payloads.
- Added scheduler-level Stage 1 wiring helper to run collection + anomaly derivation as a single cycle.
- Enforced nested immutability for mapping fields to align runtime behavior with frozen-model claims.
- Added/updated unit and integration tests covering positive, negative, threshold-boundary, and payload-shape scenarios for all anomaly families.
- Executed full test suite and lint checks with all gates passing.

### File List

- artifact/implementation-artifacts/2-1-prometheus-metric-collection-and-evaluation-cadence.md (modified)
- src/aiops_triage_pipeline/models/anomaly.py (new)
- src/aiops_triage_pipeline/models/evidence.py (modified)
- src/aiops_triage_pipeline/models/__init__.py (modified)
- src/aiops_triage_pipeline/integrations/prometheus.py (modified)
- src/aiops_triage_pipeline/pipeline/scheduler.py (modified)
- src/aiops_triage_pipeline/pipeline/stages/anomaly.py (new)
- src/aiops_triage_pipeline/pipeline/stages/evidence.py (modified)
- tests/integration/integrations/test_prometheus_local.py (new)
- tests/unit/pipeline/stages/test_anomaly.py (new)
- tests/unit/pipeline/stages/test_evidence.py (modified)
- tests/integration/pipeline/test_evidence_prometheus_integration.py (modified)
- tests/unit/integrations/test_prometheus.py (new)
- tests/unit/logging/test_setup.py (modified)
- tests/unit/pipeline/conftest.py (new)
- tests/unit/pipeline/test_scheduler.py (new)
- artifact/project-context.md (new)
- artifact/implementation-artifacts/2-2-anomaly-pattern-detection.md (modified)
- artifact/implementation-artifacts/sprint-status.yaml (modified)

## Change Log

- 2026-03-03: Implemented Story 2.2 anomaly detection models, detectors, evidence-stage wiring, and comprehensive test coverage; status moved to `review`.
- 2026-03-03: Applied code-review fixes: lag growth + baseline-aware volume drop logic, scheduler wiring helper, nested immutability hardening, expanded tests, and synchronized File List with actual workspace changes.
- 2026-03-02: Applied second code-review pass: (H1) volume-drop detector changed to min/max (order-independent) — eliminates positional-index fragility; lag offset_progress now max-min spread; lag_end uses max(); (H2) AnomalyDetectionResult.findings_by_scope auto-derived from findings in model_validator — inconsistent construction no longer possible; (H3/M1) removed dead ratio check and unreachable baseline<=0 guard from volume-drop detector; (M2) normalize_labels called once per sample in collect_evidence_rows; (M4) misclassified integration test moved to unit suite; (L1) removed redundant @pytest.mark.asyncio.
