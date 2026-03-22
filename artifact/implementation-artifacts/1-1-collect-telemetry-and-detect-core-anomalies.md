# Story 1.1: Collect Telemetry and Detect Core Anomalies

Status: review

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As an on-call engineer,
I want hot-path telemetry collection and anomaly detection to run on schedule,
so that incident signals are detected early with explicit degraded evidence handling.

**Implements:** FR1, FR2, FR7

## Acceptance Criteria

1. **Given** the scheduler interval is configured and Prometheus is reachable
   **When** the hot-path cycle executes
   **Then** the pipeline queries Prometheus and evaluates lag, throughput-constrained, and volume-drop anomalies for each monitored scope
   **And** findings are produced with evidence status that supports downstream gating.

2. **Given** Prometheus is unavailable or times out
   **When** a cycle executes
   **Then** a `TelemetryDegradedEvent` is emitted
   **And** missing telemetry is represented as `UNKNOWN` evidence rather than coerced to present/zero values.

## Tasks / Subtasks

- [x] Task 1: Run Stage 1 collection on scheduler cadence using contract-driven metric queries (AC: 1)
  - [x] Use `collect_prometheus_samples_with_diagnostics(...)` through `run_evidence_stage_cycle(...)`.
  - [x] Keep metric identity and scope-key behavior aligned with `prometheus-metrics-contract-v1.yaml`.
  - [x] Preserve async-safe collection (`asyncio.to_thread`) to avoid blocking the event loop.

- [x] Task 2: Detect core anomaly families from normalized evidence rows (AC: 1)
  - [x] Ensure detector coverage for `CONSUMER_LAG`, `THROUGHPUT_CONSTRAINED_PROXY`, and `VOLUME_DROP`.
  - [x] Keep finding payloads compatible with downstream gate assembly (`Finding`, `evidence_required`, reason codes).
  - [x] Preserve deterministic scope grouping and ordering.

- [x] Task 3: Implement degraded telemetry handling with strict UNKNOWN semantics (AC: 2)
  - [x] On full outage, set `telemetry_degraded_active=True`, emit one pending `TelemetryDegradedEvent`, and cap `max_safe_action=NOTIFY`.
  - [x] On recovery, emit resolved event and clear cap.
  - [x] Never map missing series to numeric zero; maintain `EvidenceStatus.UNKNOWN`.

- [x] Task 4: Preserve operational signals and health transitions (AC: 1, 2)
  - [x] Update Prometheus component health status transitions (`HEALTHY`/`UNAVAILABLE`).
  - [x] Emit degraded-active and transition metrics plus latency/alert hooks.

- [x] Task 5: Add and/or update focused tests and run quality gates (AC: 1, 2)
  - [x] Evidence-stage unit tests for outage detection, pending/resolved event emission, and UNKNOWN map behavior.
  - [x] Scheduler wiring tests for Stage 1 execution path and degraded transitions.
  - [x] Run full suite with zero skips and lint checks.

### Review Follow-ups (AI)

- [x] [AI-Review][MEDIUM] Replaced substring-based fallback gating with robust exception classification for connectivity failures. [tests/integration/integrations/test_prometheus_local.py]
- [x] [AI-Review][MEDIUM] Strengthened smoke assertions by validating full sample shape and requiring non-empty fallback self-series (`up`) when contract metric is empty. [tests/integration/integrations/test_prometheus_local.py]
- [x] [AI-Review][LOW] Added offline CI guardrails for fallback image startup with configurable image override (`AIOPS_PROMETHEUS_TEST_IMAGE`) and actionable failure guidance. [tests/integration/integrations/test_prometheus_local.py]
- [x] [AI-Review][LOW] Tightened completion-note traceability to match the actual scope of modified files in this implementation pass. [artifact/implementation-artifacts/1-1-collect-telemetry-and-detect-core-anomalies.md]

## Dev Notes

### Developer Context Section

- Story 1.1 is the foundation for Epic 1 and should be treated as load-bearing for all downstream gate/topology/casefile work.
- The current code already contains Stage 1 scaffolding in:
  - `src/aiops_triage_pipeline/pipeline/scheduler.py`
  - `src/aiops_triage_pipeline/pipeline/stages/evidence.py`
  - `src/aiops_triage_pipeline/pipeline/stages/anomaly.py`
  - `src/aiops_triage_pipeline/integrations/prometheus.py`
- This story must keep hot-path deterministic and non-blocking. Do not introduce LLM calls, network fan-out beyond Prometheus collection, or new persistence dependencies.
- Degraded telemetry behavior is a safety contract, not a convenience feature:
  - full source outage -> explicit degraded event + NOTIFY cap
  - partial misses -> no full outage transition
  - missing metrics -> UNKNOWN evidence (never zero-fill)
- Preserve immutable model semantics (`frozen=True` + mapping freeze) in evidence outputs to prevent accidental downstream mutation.

### Technical Requirements

- Stage 1 collection must use contract-driven metric keys and canonical names from `config/policies/prometheus-metrics-contract-v1.yaml`.
- Supported anomaly families in this story:
  - `CONSUMER_LAG`
  - `THROUGHPUT_CONSTRAINED_PROXY`
  - `VOLUME_DROP`
- Evidence and finding outputs must remain compatible with downstream gate-input assembly (`contracts/gate_input.py`).
- `TelemetryDegradedEvent` behavior must remain edge-triggered:
  - emit one `pending` event when entering full outage state
  - suppress duplicate pending events while still degraded
  - emit one `resolved` event when healthy telemetry resumes
- On outage, `max_safe_action` must cap to `Action.NOTIFY`; on recovery, clear cap to `None`.
- Error classification must preserve current intent:
  - source/unavailable errors contribute to outage detection
  - non-success Prometheus API payloads contribute to outage detection
  - non-outage data-shape errors should not falsely trigger global outage state.

### Architecture Compliance

- Keep composition-root and dependency injection patterns intact (`__main__.py` wiring, no module-level singleton mutation).
- Keep package boundaries stable:
  - Stage logic in `pipeline/stages/*`
  - integration adapter behavior in `integrations/prometheus.py`
  - no cross-import violations into unrelated packages.
- Preserve architecture invariants relevant to this story:
  - UNKNOWN evidence must never collapse to PRESENT or zero.
  - hot-path must continue under degradable dependency failure with explicit health and telemetry signals.
  - structured logging and operational-alert emission must use existing shared primitives.
- Do not change public contract shapes for downstream artifacts unless explicitly required by this story’s acceptance criteria.

### Library / Framework Requirements

- Runtime and testing stack for this story remains pinned by project policy:
  - Python `>=3.13`
  - `pydantic==2.12.5`
  - `pydantic-settings~=2.13.1`
  - `pytest==9.0.2`
  - `redis==7.2.1`
- Prometheus interaction must stay on documented HTTP API semantics used by `query_instant` (`/api/v1/query`, success/error envelope, vector response expectation).
- Use existing project patterns:
  - `structlog`-based structured events
  - `asyncio.to_thread` for blocking Prometheus calls
  - Pydantic frozen models for stage outputs and event models.
- Unless this story explicitly requires upgrade work, do not bump dependency versions in implementation changes.

### Project Structure Notes

- Primary files to review/update for Story 1.1:
  - `src/aiops_triage_pipeline/pipeline/scheduler.py`
  - `src/aiops_triage_pipeline/pipeline/stages/evidence.py`
  - `src/aiops_triage_pipeline/pipeline/stages/anomaly.py`
  - `src/aiops_triage_pipeline/integrations/prometheus.py`
  - `src/aiops_triage_pipeline/models/evidence.py`
  - `src/aiops_triage_pipeline/models/events.py`
- Primary tests to review/update:
  - `tests/unit/pipeline/stages/test_evidence.py`
  - `tests/unit/pipeline/test_scheduler.py`
- Keep changes localized to Stage 1 requirements; avoid speculative edits in topology/gating/casefile/outbox/cold-path modules.
- Preserve module naming and boundaries defined in `artifact/planning-artifacts/architecture/project-structure-boundaries.md`.

### Testing Requirements

- Required unit coverage:
  - Prometheus total-outage detection and outage reason propagation.
  - Pending/resolved `TelemetryDegradedEvent` emission transitions.
  - `max_safe_action` cap behavior during outage and cap clearing on recovery.
  - UNKNOWN evidence map behavior for missing metric series.
  - Detection of all three anomaly families under representative samples.
- Required scheduler integration-style unit coverage:
  - `run_evidence_stage_cycle` wiring from query -> evidence -> anomaly output.
  - HealthRegistry transitions for Prometheus availability.
  - Metrics/operational-alert hooks for degraded transitions and stage latency.
- Quality gate commands:
  - `TESTCONTAINERS_RYUK_DISABLED=true DOCKER_HOST=unix://$HOME/.docker/desktop/docker.sock uv run pytest -q -rs`
  - `uv run ruff check`
- Sprint rule: zero skipped tests. Missing prerequisites must be fixed, not bypassed.

### Latest Tech Information

- Snapshot date: 2026-03-22.
- Prometheus upstream latest release currently shows `3.10.0` dated `2026-02-24`.
- Prometheus HTTP API docs continue to define the standard `status/data/errorType/error` response envelope and query parameters (`query`, `timeout`, `limit`) used by this project’s Stage 1 collection behavior.
- Python dependency release checks relevant to this story:
  - `pydantic` latest on PyPI: `2.12.5` (released 2025-11-26) -> aligned with project pin.
  - `pytest` release in use: `9.0.2` (released 2025-12-06) -> aligned with project pin.
  - `redis` latest on PyPI: `7.3.0` (released 2026-03-06) while project pin is `7.2.1`.
- Guidance for implementation:
  - Do not introduce Prometheus 3.10-specific assumptions unless accompanied by explicit environment upgrade validation.
  - Keep dependency versions unchanged for Story 1.1 unless upgrade is explicitly scoped.

### References

- [Source: `artifact/planning-artifacts/epics.md` - Epic 1, Story 1.1]
- [Source: `artifact/planning-artifacts/prd/functional-requirements.md` - FR1, FR2, FR7]
- [Source: `artifact/planning-artifacts/prd/non-functional-requirements.md` - reliability/performance constraints]
- [Source: `artifact/planning-artifacts/prd/domain-specific-requirements.md` - UNKNOWN/degraded handling invariants]
- [Source: `artifact/planning-artifacts/prd/event-driven-pipeline-specific-requirements.md` - hot-path runtime and interface constraints]
- [Source: `artifact/planning-artifacts/architecture/core-architectural-decisions.md` - D2, D3 and Stage behavior constraints]
- [Source: `artifact/planning-artifacts/architecture/implementation-patterns-consistency-rules.md`]
- [Source: `artifact/planning-artifacts/architecture/project-structure-boundaries.md`]
- [Source: `archive/project-context.md`]
- [Source: `src/aiops_triage_pipeline/pipeline/scheduler.py`]
- [Source: `src/aiops_triage_pipeline/pipeline/stages/evidence.py`]
- [Source: `src/aiops_triage_pipeline/pipeline/stages/anomaly.py`]
- [Source: `src/aiops_triage_pipeline/integrations/prometheus.py`]
- [Source: `tests/unit/pipeline/stages/test_evidence.py`]
- [Source: `tests/unit/pipeline/test_scheduler.py`]
- [Source: https://github.com/prometheus/prometheus/releases]
- [Source: https://prometheus.io/docs/prometheus/latest/querying/api/]
- [Source: https://pypi.org/project/pydantic/]
- [Source: https://pypi.org/project/pytest/]
- [Source: https://pypi.org/project/redis/]

## Dev Agent Record

### Agent Model Used

GPT-5 Codex

### Debug Log References

- Story context generated from planning artifacts, architecture shards, current codebase, and latest-version checks.
- Full regression gate run after Docker Desktop startup: `TESTCONTAINERS_RYUK_DISABLED=true DOCKER_HOST=unix://$HOME/.docker/desktop/docker.sock uv run pytest -q -rs` -> `827 passed`, `0 skipped`.
- Quality gate lint run: `uv run ruff check` -> passed after import/order and line-wrap cleanup.

### Completion Notes List

- Story document created in `ready-for-dev` state with implementation guardrails, architecture constraints, testing requirements, and latest tech notes.
- Verified this implementation pass is focused on Story artifact updates plus integration smoke hardening (no functional Stage 1 pipeline code changes in this diff).
- Updated integration smoke coverage to use robust connectivity-failure classification instead of fragile message matching.
- Strengthened integration smoke validation with full sample-shape assertions and fallback self-metric liveness checks when contract series is empty.
- Added fallback container guardrails for offline/air-gapped environments with configurable image override and explicit pre-pull guidance.
- Story moved back to `review` after resolving all medium/low review findings.

### File List

- artifact/implementation-artifacts/1-1-collect-telemetry-and-detect-core-anomalies.md
- artifact/implementation-artifacts/sprint-status.yaml
- src/aiops_triage_pipeline/__main__.py
- tests/integration/integrations/test_prometheus_local.py

## Senior Developer Review (AI)

### Reviewer

- Reviewer: Sas
- Date: 2026-03-22
- Outcome: Changes Requested

### Git vs Story Validation

- Story file list entries: 4
- Git changed files: 4
- Discrepancies: 0

### AC Validation Summary

- AC1: IMPLEMENTED (verified in scheduler/evidence/anomaly path and unit coverage).
- AC2: IMPLEMENTED (verified outage detection, pending/resolved event transitions, UNKNOWN semantics, and cap behavior).

### Findings

1. [MEDIUM] Fallback trigger logic is brittle because it depends on exception message substrings rather than stable exception semantics. [tests/integration/integrations/test_prometheus_local.py:39]
2. [MEDIUM] Integration smoke test assertions are too weak and can pass on empty vectors, which limits defect-detection value for query-path regressions. [tests/integration/integrations/test_prometheus_local.py:51]
3. [LOW] Containerized fallback path adds a runtime image-pull dependency that can fail in offline/air-gapped CI without a preloaded image strategy. [tests/integration/integrations/test_prometheus_local.py:41]
4. [LOW] Story traceability is ambiguous: completion notes imply broad implementation work while recorded changed files reflect limited/new behavior scope. [artifact/implementation-artifacts/1-1-collect-telemetry-and-detect-core-anomalies.md:198]

### Resolution (2026-03-22)

- [x] Finding 1 resolved in integration smoke fallback exception handling.
- [x] Finding 2 resolved with stronger assertions and fallback self-series liveness verification.
- [x] Finding 3 resolved with fallback image override + explicit pre-pull/offline guidance in test failure path.
- [x] Finding 4 resolved by rewriting completion notes for accurate scope traceability.

## Change Log

- 2026-03-22: Story created via create-story workflow with exhaustive artifact analysis and ready-for-dev context.
- 2026-03-22: Dev-story implementation completed; enforced zero-skip regression gate, added non-skipping Prometheus integration fallback, and advanced story to review.
- 2026-03-22: Senior developer adversarial review completed; 2 MEDIUM and 2 LOW findings recorded, follow-up action items added, story moved to in-progress.
- 2026-03-22: Resolved all medium/low review findings; hardened integration smoke fallback behavior/assertions and clarified implementation traceability.

## Story Completion Status

- Story status: `review`
- Completion note: Medium/low review findings resolved and follow-up checklist completed; ready for re-review.
