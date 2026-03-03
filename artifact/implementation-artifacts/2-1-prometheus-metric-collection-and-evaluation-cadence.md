# Story 2.1: Prometheus Metric Collection & Evaluation Cadence

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a platform operator,
I want the system to query Prometheus metrics at 5-minute evaluation intervals aligned to wall-clock boundaries,
so that evidence collection is consistent, predictable, and uses canonical metric names from prometheus-metrics-contract-v1 (FR1).

## Acceptance Criteria

1. **Given** the pipeline is running and Prometheus is available
   **When** the evaluation scheduler fires
   **Then** queries execute at 5-minute wall-clock boundaries (00, 05, 10, ...) with drift <= 30 seconds (NFR-P2)

2. **And** queries use canonical metric names defined in `prometheus-metrics-contract-v1`

3. **And** label normalization is applied (`cluster_id := cluster_name` exact string)

4. **And** metrics are collected per `(env, cluster_id, topic/group)` scope

5. **And** missed intervals are logged as operational warnings

6. **And** unit tests verify wall-clock alignment, metric name compliance, and label normalization

## Tasks / Subtasks

- [x] Task 1: Implement 5-minute wall-clock evaluation scheduler behavior for evidence collection (AC: #1, #5)
  - [x] Add/extend scheduling logic to align execution to exact 5-minute boundaries (`:00/:05/:10/...`) with drift monitoring
  - [x] Record scheduling drift and emit warning logs when drift exceeds configured threshold (30s)
  - [x] Ensure missed interval behavior is explicit and logged

- [x] Task 2: Implement Prometheus query contract compliance and label normalization (AC: #2, #3, #4)
  - [x] Add canonical metric query definitions from `config/policies/prometheus-metrics-contract-v1.yaml`
  - [x] Normalize labels to internal identity (`cluster_id := cluster_name`) before downstream processing
  - [x] Enforce scoped collection keys `(env, cluster_id, topic/group)` for each evidence row

- [x] Task 3: Add unit tests for cadence and query semantics (AC: #1, #2, #3, #6)
  - [x] Test scheduler boundary alignment and drift threshold enforcement
  - [x] Test canonical metric usage against contract definitions
  - [x] Test label normalization behavior and scoped identity mapping

- [x] Task 4: Add integration-level validation for local Prometheus path (AC: #1, #4, #5)
  - [x] Verify Prometheus client integration path reads expected metrics from local compose stack/harness
  - [x] Verify operational warning behavior for unavailable/missed windows is observable in logs

- [x] Task 5: Quality gates
  - [x] Run unit tests for scheduling and evidence collection changes
  - [x] Run affected integration tests
  - [x] Run lint/format checks for modified files

## Dev Notes

### Developer Context Section

- This story is the first implementation story in Epic 2 and establishes the evidence collection cadence baseline for all downstream anomaly logic (Stories 2.2-2.7).
- Hot-path design requirement: scheduler runs on strict 5-minute wall-clock cadence (`:00/:05/:10/...`) with drift target `<=30s` (NFR-P2).
- Prometheus is a critical data source for this story's behavior; metric contract compliance is mandatory and must come from `config/policies/prometheus-metrics-contract-v1.yaml`.
- Identity normalization rule is mandatory: internal `cluster_id` derives from Prometheus `cluster_name` label (`cluster_id := cluster_name` exact mapping).
- Missing intervals are operationally significant: they must be logged as warnings, not silently skipped.
- Keep UNKNOWN semantics intact for missing telemetry in future stages; this story should not introduce zero-default behavior that could break Story 2.5.
- Reuse existing foundation from Epic 1:
  - Story 1.8 provided local infrastructure and Prometheus scrape scaffolding.
  - Story 1.9 added harness-generated canonical metrics and label patterns usable for integration verification.

### Technical Requirements

- Scheduler cadence:
  - Execute evidence collection at exact 5-minute wall-clock boundaries.
  - Track execution drift per interval and treat drift `>30s` as warning-level operational signal.
- Metric contract compliance:
  - Build Prometheus query set from `prometheus-metrics-contract-v1.yaml` canonical entries.
  - Do not add ad-hoc metric names for this story.
- Identity and scoping:
  - Normalize `cluster_name` from Prometheus payload into internal `cluster_id`.
  - Maintain identity keys by `(env, cluster_id, topic/group)` for evidence units.
- Error and observability behavior:
  - On missed interval or scheduling delay, emit structured warning log with interval context.
  - Preserve deterministic hot-path behavior; do not introduce blocking/retry loops that break cadence.
- Dependency boundaries:
  - Use existing integration and pipeline modules (`integrations/prometheus.py`, `pipeline/stages/evidence.py`, scheduler path) rather than introducing parallel collection paths.

### Architecture Compliance

- Orchestration model compliance:
  - Keep evidence collection in hot-path scheduler flow defined by architecture (`scheduler + asyncio.TaskGroup` model).
  - Maintain 5-minute wall-clock cadence semantics from architecture decision 4A.
- Contract-first compliance:
  - Treat `prometheus-metrics-contract-v1` as frozen contract authority for metric identity used in collection.
  - Ensure data produced by collection stage remains schema-compatible with downstream models/contracts.
- Cross-cutting concern compliance:
  - Preserve UNKNOWN-not-zero design intent for missing telemetry; do not coerce missing series to numeric zero.
  - Keep structured logging and correlation propagation aligned with established logging setup.
- Component boundary compliance:
  - Do not shift this story's implementation into unrelated components (diagnosis/outbox/dispatch).
  - Keep changes localized to scheduler, Prometheus integration, and evidence-stage plumbing.
- Non-functional compliance:
  - Respect NFR-P2 drift requirement (`<=30s`) and make drift observable via logs/metrics where existing mechanisms allow.

### Library / Framework Requirements

- Python/runtime:
  - Keep implementation compatible with Python `>=3.13` typing and async patterns already used in the codebase.
- Prometheus integration:
  - Use the project's existing Prometheus integration client/module rather than adding a second query client.
  - Metric names must come from policy contract definitions, not hardcoded ad-hoc strings scattered across code.
- Data validation/models:
  - Keep evidence and related contract models immutable where applicable (`frozen=True` pattern in project context).
  - Validate at boundaries for external data ingestion/deserialization.
- Scheduling/concurrency:
  - Follow existing asyncio-based orchestration; avoid introducing alternate schedulers or thread-based cadence logic for hot path.
- Logging/observability:
  - Use existing structured logging setup (`structlog` patterns) and shared correlation helpers.
  - Emit machine-parseable warning events for missed windows/drift breaches.
- Testing stack:
  - Use `pytest` / `pytest-asyncio` patterns already established in repository test suites.

### File Structure Requirements

- Primary implementation targets:
  - `src/aiops_triage_pipeline/pipeline/scheduler.py` (or existing scheduler entry module) for cadence boundary logic and drift handling.
  - `src/aiops_triage_pipeline/pipeline/stages/evidence.py` for evidence collection orchestration hooks.
  - `src/aiops_triage_pipeline/integrations/prometheus.py` for canonical metric query and label normalization behavior.
- Policy/contract references:
  - `config/policies/prometheus-metrics-contract-v1.yaml` as source of canonical metric identities.
- Test targets:
  - `tests/unit/pipeline/stages/test_evidence.py` for evidence-stage behavior.
  - `tests/unit/...` scheduler-focused tests (existing scheduler test module or new targeted unit file).
  - `tests/integration/...` only if required to verify local Prometheus path/harness interoperability.
- Do not modify unrelated areas for this story:
  - No changes in cold-path diagnosis modules.
  - No changes in outbox publisher or dispatch integrations unless a direct compilation/runtime dependency requires a minimal adjustment.

### Testing Requirements

- Unit tests (mandatory):
  - Verify scheduler fires on 5-minute wall-clock boundaries and measures drift.
  - Verify drift warning behavior when drift exceeds 30 seconds.
  - Verify canonical metric set used for Prometheus query construction aligns with `prometheus-metrics-contract-v1.yaml`.
  - Verify label normalization maps `cluster_name` input to internal `cluster_id` exactly.
  - Verify collected evidence keys are scoped by `(env, cluster_id, topic/group)`.
- Integration tests (targeted):
  - Verify local Prometheus/harness path is consumable by the evidence collection stage (existing integration harness where available).
  - Verify missed-window logging is observable in structured logs under induced timing delay scenarios.
- Regression expectations:
  - Run affected existing unit tests for pipeline stage/evidence and scheduler modules.
  - Run full test suite if scheduler changes have broad impact.
- Quality checks:
  - Run Ruff lint checks for modified code.
  - Ensure no new warnings/errors in existing CI-quality gates relevant to touched files.

### Previous Story Intelligence

- From Story 1.9 (`harness`):
  - Canonical Prometheus metric names are already exercised by harness output and validated against `prometheus-metrics-contract-v1.yaml`.
  - Harness labels use `cluster_name` (not `cluster_id`), which directly reinforces this story's required normalization mapping.
  - Local compose path already includes Prometheus scrape target for harness, enabling realistic integration verification for this story's collector.
- Practical implementation carry-forwards:
  - Keep contract-driven metric identity centralized; avoid duplicate per-file canonical lists.
  - Preserve structured warning logs for operational observability, matching existing style from foundation stories.
  - Keep changes scoped to evidence collection/scheduler paths; prior stories showed cleaner review outcomes when scope stayed tight.

### Git Intelligence Summary

- Recent commit pattern indicates a review-driven loop:
  - Story implementation commit followed by focused "code review fixes" commit(s).
  - Expectation for this story: ship minimal, test-backed implementation first, then address review deltas without broad refactors.
- Foundation trend from latest commits:
  - Epic 1 finalized local stack and harness prerequisites; Epic 2 should build on those assets rather than reworking infrastructure.
  - Commit history emphasizes story status discipline (ready-for-dev -> in-progress -> review) and complete story file hygiene.
- Practical guidance for this story:
  - Keep PR/change scope tight to scheduler + evidence collection modules.
  - Include clear unit tests in the same change to reduce follow-up churn.

### Latest Tech Information

- Prometheus Python client:
  - Official `prometheus-client` latest release is `0.24.1` (released 2026-01-14).
  - The project currently uses `prometheus-client~=0.24.0` for harness/testing context, which is aligned with latest stable patch line.
  - No story change needed to dependency policy; continue using current project pin strategy unless broader dependency review is requested.
- Python asyncio behavior relevant to scheduler orchestration:
  - Python 3.13 `asyncio.TaskGroup` remains the recommended structured-concurrency primitive.
  - 3.13 behavior note: `TaskGroup.create_task()` closes the coroutine if the task group is inactive, which reinforces the need to only create tasks inside active group context.
  - For this story, cadence logic should preserve current TaskGroup lifecycle discipline and avoid creating tasks before group entry/after shutdown.

### Project Context Reference

- [Source: `artifact/project-context.md#Technology Stack & Versions`]
  - Python `>=3.13`, pytest/pytest-asyncio, ruff rules, and Prometheus client version expectations.
- [Source: `artifact/project-context.md#Framework-Specific Rules`]
  - Deterministic hot-path behavior, integration framework rules, and degraded-mode expectations.
- [Source: `artifact/project-context.md#Critical Don't-Miss Rules`]
  - Do not collapse UNKNOWN to zero; preserve guardrails and structured error behavior.
- [Source: `artifact/planning-artifacts/epics.md#Story 2.1: Prometheus Metric Collection & Evaluation Cadence`]
  - Authoritative user story and ACs for cadence, metric compliance, normalization, and warnings.
- [Source: `artifact/planning-artifacts/architecture.md#Pipeline Orchestration`]
  - 5-minute wall-clock scheduler requirement and asyncio TaskGroup orchestration pattern.
- [Source: `artifact/planning-artifacts/architecture.md#Cross-Cutting Concerns Identified`]
  - UNKNOWN-not-zero propagation and operational telemetry/degraded-mode constraints.
- [Source: `artifact/implementation-artifacts/1-9-harness-traffic-generation.md#Completion Notes List`]
  - Existing harness metric generation and canonical naming verification baseline.
- [Source: `config/policies/prometheus-metrics-contract-v1.yaml`]
  - Canonical metric names and identity label semantics used by query/normalization logic.
- [Source: `https://pypi.org/project/prometheus-client/`]
  - Current release line context for `prometheus-client` package.
- [Source: `https://docs.python.org/3.13/library/asyncio-task.html#task-groups`]
  - `TaskGroup.create_task()` inactive-group coroutine-close behavior in Python 3.13.

### Project Structure Notes

- Alignment with unified project structure (paths, modules, naming)
- Detected conflicts or variances (with rationale)

### References

- Use the source list above as authoritative references for this story implementation.

## Dev Agent Record

### Agent Model Used

GPT-5 Codex

### Debug Log References

- `create-story` references `_bmad/core/tasks/validate-workflow.xml`, but that file is not present in this repository; checklist validation was executed directly against the loaded checklist content.
- Implemented scheduler cadence utilities and evidence-stage collection flow from currently-empty pipeline/integration stubs.
- `uv run ruff check` required elevated execution because sandbox blocked uv cache access under `/home/sas/.cache/uv`.

### Implementation Plan

- Build deterministic scheduler helpers for 5-minute boundary alignment, drift computation, and missed interval detection.
- Add contract-first Prometheus query definitions loaded from `config/policies/prometheus-metrics-contract-v1.yaml`.
- Normalize Prometheus labels with `cluster_id := cluster_name` and derive evidence identity scopes by metric family.
- Add unit and integration tests for scheduler behavior, contract compliance, normalization, and observable warning logging.
- Run full regression and lint gates before marking story complete.

### Completion Notes List

- Added `pipeline/scheduler.py` cadence logic for wall-clock boundary flooring, next boundary computation, drift tracking, and missed-interval warning events.
- Added `integrations/prometheus.py` contract-driven metric query definitions, label normalization, and HTTP instant-query client path for local Prometheus validation.
- Added `pipeline/stages/evidence.py` scope-key construction and sample collection with warning logs on unavailable/missed windows.
- Added `models/evidence.py` immutable evidence row model used by evidence-stage normalization.
- Added/updated tests to cover scheduler cadence, drift threshold behavior, canonical metric loading, label normalization, scope mapping, local Prometheus path, and warning observability.
- Validation results:
  - `uv run pytest -q` -> `163 passed, 1 skipped`
  - `uv run ruff check` -> `All checks passed`

### File List

- src/aiops_triage_pipeline/pipeline/scheduler.py (modified)
- src/aiops_triage_pipeline/integrations/prometheus.py (modified)
- src/aiops_triage_pipeline/pipeline/stages/evidence.py (modified)
- src/aiops_triage_pipeline/models/evidence.py (modified)
- tests/unit/pipeline/conftest.py (created)
- tests/unit/pipeline/test_scheduler.py (created)
- tests/unit/integrations/test_prometheus.py (created)
- tests/unit/pipeline/stages/test_evidence.py (created)
- tests/integration/integrations/test_prometheus_local.py (created)
- tests/integration/pipeline/test_evidence_prometheus_integration.py (created)
- tests/unit/logging/test_setup.py (updated)
- artifact/project-context.md (created)
- artifact/implementation-artifacts/sprint-status.yaml (updated)
- artifact/implementation-artifacts/2-1-prometheus-metric-collection-and-evaluation-cadence.md (updated)

## Senior Developer Review (AI)

**Reviewer:** Sas on 2026-03-02
**Outcome:** Changes Requested → Fixed

### Issues Found and Fixed

**HIGH — Fixed**
- **H1 UNKNOWN→Zero collapse** (`prometheus.py`): `item.get("value", [None, "0"])[1]` silently substituted `0.0` for absent values, violating the contract `truthfulness.missing_series` rule and project-context critical rule. Fixed: samples with no value are now skipped entirely, preserving UNKNOWN semantics for downstream stages.
- **H2 Blocking HTTP in asyncio hot path** (`evidence.py`): `urlopen()` blocked the event loop during evidence collection (up to 5s × 9 metrics). Fixed: `collect_prometheus_samples` is now `async` and wraps each `client.query_instant` call with `asyncio.to_thread`.
- **H3 Bare `except Exception` masked bugs** (`evidence.py`): All exceptions were caught and logged as "missed windows", hiding programming errors. Fixed: narrowed to `(URLError, TimeoutError, OSError, ValueError)`.
- **H4 Unguarded `KeyError` crashes** (`evidence.py`): `build_evidence_scope_key` used bare `dict[]` access for `env`, `topic`, `group` labels; a missing label crashed the entire collection batch. Fixed: validation raises `ValueError` with clear context; `collect_evidence_rows` catches and warns per-sample, skipping malformed ones.

**MEDIUM — Fixed**
- **M1 Relative contract path** (`prometheus.py`): `Path("config/policies/...")` resolved from CWD. Fixed: now `Path(__file__).resolve().parents[3] / ...` (absolute, CWD-independent).
- **M2 Double `normalize_labels` call** (`evidence.py`): `collect_evidence_rows` normalized labels then passed them to `build_evidence_scope_key` which normalized again. Fixed: pass raw `sample["labels"]` to `build_evidence_scope_key`.
- **M3 No `EvidenceRow` immutability test**: Added `test_evidence_row_is_immutable()`.
- **M4 Logging setup not isolated** (`test_scheduler.py`, `test_evidence.py`): Tests mutated root logger handlers without cleanup fixtures. Fixed: created `tests/unit/pipeline/conftest.py` with `log_stream` and `reset_structlog` (autouse) fixtures; updated tests to use fixture.
- **M5 `artifact/project-context.md` missing from File List**: File created during this story but not documented. Fixed.
- **M6 File List said "created" for modified files**: Pre-existing files shown as "M" in git were incorrectly labelled. Fixed.
- **Integration test not awaited** (`test_evidence_prometheus_integration.py`): `collect_prometheus_samples` became async but integration test remained sync. Fixed to `async def`.

### Validation After Fixes

- `uv run pytest -q` → `167 passed, 1 skipped`
- `uv run ruff check` → `All checks passed`

## Change Log

- 2026-03-03: Implemented Story 2.1 scheduler cadence and Prometheus evidence collection baseline with unit/integration tests and full quality-gate validation.
- 2026-03-02: Code review fixes — UNKNOWN→zero collapse, blocking HTTP (asyncio.to_thread), bare Exception narrowed, KeyError guards added, contract path made absolute, double normalize eliminated, EvidenceRow immutability test added, test logging isolation via conftest fixture.

### Story Completion Status

- ✅ Implementation complete and code-review fixes applied. All tasks and subtasks delivered with passing tests and lint checks.
