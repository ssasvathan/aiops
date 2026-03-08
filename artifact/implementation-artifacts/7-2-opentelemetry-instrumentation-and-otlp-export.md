# Story 7.2: OpenTelemetry Instrumentation & OTLP Export

Status: ready-for-dev

## Story

As an SRE/operator,
I want the AIOps system to expose health metrics for all its own components via OpenTelemetry SDK with OTLP export,
so that I can monitor the observer itself through Dynatrace and detect degradation before it impacts triage quality (NFR-O1).

## Acceptance Criteria

1. **Given** the pipeline components are running
   **When** meta-monitoring metrics are collected
   **Then** the following component metrics are exposed via OpenTelemetry SDK with OTLP export to Dynatrace:
   - Outbox: queue depth by state, age of oldest per state, publish latency histogram
   - Redis: connection status, cache hit/miss rate, dedupe key count
   - LLM: invocation count, latency histogram, timeout/error rate, fallback rate
   - Evidence Builder: evaluation interval adherence, cases produced per interval, UNKNOWN rate by metric
   - Prometheus connectivity: scrape success/failure, TelemetryDegradedEvent active/cleared
   - Pipeline: end-to-end compute latency histogram (NFR-P1a), delivery latency histogram (NFR-P1b), case throughput
2. **And** integration tests include an OpenTelemetry Collector container (via testcontainers) as OTLP receiver stub that asserts correct metric names, labels, and values
3. **And** unit tests verify: metric emission for each component, correct metric names and label structure

## Tasks / Subtasks

- [ ] Task 1: Add OTLP exporter bootstrap and runtime configuration (AC: 1)
  - [ ] Add a telemetry bootstrap module that configures `MeterProvider`, `PeriodicExportingMetricReader`, and `OTLPMetricExporter`
  - [ ] Add settings/env support for OTLP endpoint, protocol, headers, export interval, and service resource attributes
  - [ ] Initialize telemetry bootstrap from process entrypoint before metric emission begins
  - [ ] Preserve safe defaults for local runs and avoid outbound calls unless OTLP is configured

- [ ] Task 2: Keep Story 7.1 outbox metrics as canonical and OTLP-exported (AC: 1)
  - [ ] Reuse existing `aiops.outbox.*` metrics from `outbox/metrics.py` without renaming or duplicate instruments
  - [ ] Ensure labels stay stable (`state`, `severity`, `quantile`) for dashboard continuity

- [ ] Task 3: Implement Redis health + usage telemetry (AC: 1)
  - [ ] Emit Redis connection status gauge derived from degraded/healthy transitions
  - [ ] Emit Redis dedupe cache hit/miss counters at AG5 call sites
  - [ ] Emit dedupe key count gauge (or equivalent cardinality-safe approximation) for operational visibility

- [ ] Task 4: Expand LLM metrics beyond inflight gauge (AC: 1)
  - [ ] Keep existing in-flight metric and add invocation count, latency histogram, timeout/error counters, and fallback counters
  - [ ] Ensure metrics are updated on both success and all fallback/error paths in `diagnosis/graph.py`

- [ ] Task 5: Add Evidence Builder + Prometheus connectivity metrics (AC: 1)
  - [ ] Emit evaluation interval adherence/drift and cases-produced-per-interval metrics
  - [ ] Emit UNKNOWN evidence rate by metric key
  - [ ] Emit Prometheus scrape success/failure counters and active/cleared degraded-state signal

- [ ] Task 6: Add pipeline-level latency and throughput instrumentation (AC: 1)
  - [ ] Emit compute latency histogram for stages 1-4 (NFR-P1a)
  - [ ] Reuse outbox delivery latency histogram for NFR-P1b alignment
  - [ ] Emit case throughput metric per evaluation interval

- [ ] Task 7: Add OTLP collector integration test harness (AC: 2)
  - [ ] Add an OpenTelemetry Collector testcontainer fixture (session-scoped) to receive OTLP metrics
  - [ ] Add integration test asserting expected metric names, required labels, and representative values
  - [ ] Keep full-suite `0 skipped` posture: fail fast when prerequisites are missing

- [ ] Task 8: Add/extend unit tests for each metric family and regression gates (AC: 3)
  - [ ] Unit test instrument updates for Redis, LLM, Evidence Builder, Prometheus connectivity, and pipeline metrics
  - [ ] Verify label shape and no metric drift/double-counting across repeated cycles
  - [ ] Run quality gates: `uv run ruff check`, targeted unit tests, and Docker-enabled full suite with 0 skipped

## Dev Notes

### Developer Context Section

- Story key: `7-2-opentelemetry-instrumentation-and-otlp-export`
- Story ID: `7.2`
- Epic context: Epic 7 operational observability expansion; Story 7.2 is the metrics/export foundation for Story 7.3 alert rules.
- Dependency context from Epic 7:
  - Story 7.1 already implemented outbox metrics and thresholds (`aiops.outbox.*`)
  - Story 7.3 assumes Story 7.2 metrics exist and are exported with stable names/labels

Implementation intent:
- Establish a single OTLP metrics pipeline and complete component-level meta-monitoring coverage without changing deterministic gating or durability behavior.

### Technical Requirements

1. OTLP pipeline initialization
- Configure an explicit metrics provider path for the app process using OpenTelemetry Python metrics SDK.
- Include resource attributes at minimum: service name, service version, deployment environment.
- Keep initialization idempotent and process-safe (avoid duplicate readers/exporters).

2. Metric families required by AC/NFR
- Outbox: continue exporting existing `aiops.outbox.queue_depth`, `aiops.outbox.oldest_age_seconds`, `aiops.outbox.casefile_write_to_publish_seconds`, and SLO counters.
- Redis: add connection status + dedupe hit/miss + dedupe cardinality signal.
- LLM: add invocation count, latency histogram, timeout/error/fallback rates while preserving in-flight gauge.
- Evidence Builder: add interval adherence, cases-per-interval, unknown-rate-by-metric.
- Prometheus connectivity: add scrape success/failure counters and degraded active/cleared signal.
- Pipeline: add stage compute latency (P1a) and throughput metrics; keep delivery latency mapped to outbox metric.

3. Label and cardinality discipline
- Use low-cardinality labels only (`component`, `state`, `status`, `result`, `metric_key` where bounded).
- Do not add `case_id` or unbounded user content to metric attributes.

4. Startup and config behavior
- Extend `Settings` with OTLP-related fields and safe defaults.
- Respect existing environment layering (`APP_ENV` + `.env.{APP_ENV}` + direct env overrides).
- Keep secrets masked in startup config logs.

5. Non-regression guarantees
- No change to gate decision semantics, outbox state machine semantics, or cold-path/hot-path separation.
- No replacement of existing structured logs with metrics-only signals; both remain required.

### Architecture Compliance

- Keep `health/registry.py` as the source of truth for component state transitions; metrics observe registry updates, not parallel status logic.
- Preserve architecture decision 4C: centralized HealthRegistry + OTLP export and integration-test collector validation.
- Keep lightweight `/health` endpoint approach; do not introduce FastAPI just for metrics export.
- Preserve package boundaries:
  - telemetry helpers under `health/`
  - outbox signals under `outbox/`
  - scheduler/evidence signals under `pipeline/`
  - no cross-import shortcuts that violate existing structure

### Library / Framework Requirements

Current pinned repo versions (must remain for this story unless explicitly approved):
- `opentelemetry-sdk==1.39.1`
- `opentelemetry-exporter-otlp==1.39.1`

Latest upstream reference (research timestamp: 2026-03-08):
- PyPI lists `opentelemetry-sdk` latest as `1.40.0` (released 2026-03-04).
- PyPI lists `opentelemetry-exporter-otlp` latest as `1.40.0` (released 2026-03-04).

Implementation decision for Story 7.2:
- Implement OTLP instrumentation using current pinned versions for stability and sprint scope control.
- Capture upgrade delta as follow-up maintenance work if needed; do not couple upgrade risk to observability feature delivery.

Dynatrace OTLP requirements to follow:
- Use OTLP metrics endpoint path `/api/v2/otlp/v1/metrics`.
- Configure auth using OTLP headers (API token) through environment-driven exporter settings.

### File Structure Requirements

Primary files expected to change:
- `src/aiops_triage_pipeline/health/metrics.py`
- `src/aiops_triage_pipeline/health/registry.py` (only if instrumentation hooks need extension)
- `src/aiops_triage_pipeline/config/settings.py`
- `src/aiops_triage_pipeline/__main__.py` (or equivalent bootstrap entrypoint path)
- `src/aiops_triage_pipeline/cache/dedupe.py`
- `src/aiops_triage_pipeline/diagnosis/graph.py`
- `src/aiops_triage_pipeline/pipeline/scheduler.py`
- `src/aiops_triage_pipeline/outbox/metrics.py` (stability checks and any required additive fields)
- `config/.env.local`
- `config/.env.dev`
- `config/.env.uat.template`
- `config/.env.prod.template`

Likely new source file(s):
- `src/aiops_triage_pipeline/health/otlp.py` (bootstrap/exporter wiring)

Tests to add/update:
- `tests/unit/health/test_metrics.py` (new or expanded)
- `tests/unit/cache/test_dedupe.py`
- `tests/unit/diagnosis/test_graph.py`
- `tests/unit/pipeline/test_scheduler.py`
- `tests/integration/conftest.py` (OTLP collector fixture)
- `tests/integration/test_otlp_export.py` (new)

### Testing Requirements

Minimum unit coverage:
- Metric emission correctness for each required component family.
- Label shape assertions for bounded attributes.
- Counter/histogram/gauge update behavior under repeated cycles (no drift).

Minimum integration coverage:
- Testcontainers OTLP collector receives exported metrics.
- Assertions verify expected metric names and representative labels/values.
- Coverage includes at least one success and one degraded/failure signal path.

Regression gates:
- `uv run ruff check`
- `uv run pytest -q -m "not integration"`
- `TESTCONTAINERS_RYUK_DISABLED=true DOCKER_HOST=unix://$HOME/.docker/desktop/docker.sock uv run pytest -q -rs`
- Full run must complete with `0 skipped`.

### Previous Story Intelligence

From Story 7.1 (`7-1-outbox-health-monitoring-and-dead-0-posture.md`):
- Outbox telemetry foundations already exist and passed full-suite regression with `0 skipped`.
- Existing pattern uses UpDownCounter delta accounting to avoid gauge drift; preserve that approach for any new gauge-like instruments.
- Existing outbox metric names and labels are already wired into tests and should be treated as stable API.
- Integration no-skip posture was explicitly hardened in recent fixes; do not add skip-based fallback paths in new integration tests.

### Git Intelligence Summary

Recent commits relevant to implementation approach:
- `ffc9759` (`feat: implement story 7-1 outbox health monitoring and DEAD posture`): established outbox metrics, threshold logging, and full regression behavior.
- `81ff48a` (`test(integration): remove redis container deprecation warning`): confirms current team preference to fix test infrastructure instead of skipping.
- `65c073f` and `b8f0a27` (story 6.4 hardening): reinforce fail-loud behavior for critical path errors and strong fallback handling patterns.

Actionable guidance:
- Reuse metric helper patterns introduced in Story 7.1.
- Keep failures explicit and observable; do not silently suppress telemetry setup/runtime issues in prod paths.
- Maintain the same test rigor (unit + integration + full regression with 0 skipped).

### Latest Tech Information

Research timestamp: 2026-03-08.

- OpenTelemetry Python examples for metrics continue to rely on `MeterProvider` + `PeriodicExportingMetricReader` + `OTLPMetricExporter`.
- OpenTelemetry SDK and OTLP exporter latest releases are `1.40.0` (PyPI, released 2026-03-04), while repo remains pinned to `1.39.1`.
- Dynatrace OTLP metric ingest endpoint format is `/api/v2/otlp/v1/metrics`; OTLP headers support API-token based auth.
- Dynatrace metric ingest behavior includes scope/resource dimension handling (`otel.scope.name`, `otel.scope.version`), so meter naming and stable attributes should be intentional to avoid dashboard churn.

Implementation implication:
- Deliver Story 7.2 on pinned versions and keep metric names/labels stable.
- Prepare for low-risk follow-up dependency bump once this feature set is merged and validated.

### Project Context Reference

Applied rules from `artifact/project-context.md`:
- Keep deterministic guardrails authoritative; observability must not alter gating outcomes.
- Preserve shared cross-cutting primitives (`HealthRegistry`, structured logging, denylist patterns).
- Maintain config-layer boundaries and environment precedence behavior.
- Avoid secret leakage in logs; OTLP headers/tokens must stay masked.
- Enforce full-suite no-skip quality gate.

### Project Structure Notes

- Centralize common telemetry wiring under `health/` and keep component-specific emission where behavior originates (`outbox/`, `cache/`, `diagnosis/`, `pipeline/`).
- Keep metric naming under `aiops.*` namespace and avoid one-off per-module naming deviations.
- Prefer additive instrumentation changes over refactors that disturb tested logic in hot path or outbox publisher state transitions.

### References

- [Source: `artifact/planning-artifacts/epics.md` - Story 7.2 acceptance criteria]
- [Source: `artifact/planning-artifacts/epics.md` - Story 7.3 dependency on Story 7.2 metrics]
- [Source: `artifact/planning-artifacts/prd/non-functional-requirements.md` - NFR-O1, NFR-P1a, NFR-P1b]
- [Source: `artifact/planning-artifacts/architecture.md` - Decision 4C OTLP export + HealthRegistry]
- [Source: `artifact/planning-artifacts/architecture.md` - health package structure and OTLP collector testing requirement]
- [Source: `artifact/implementation-artifacts/7-1-outbox-health-monitoring-and-dead-0-posture.md` - prior story learnings and validated metric patterns]
- [Source: `src/aiops_triage_pipeline/health/metrics.py` - existing health metric primitives]
- [Source: `src/aiops_triage_pipeline/outbox/metrics.py` - existing outbox metric naming/labels]
- [Source: `src/aiops_triage_pipeline/diagnosis/graph.py` - current LLM inflight metric + health transitions]
- [Source: `src/aiops_triage_pipeline/pipeline/scheduler.py` - evidence/degraded-event flow and timing context]
- [Source: `https://opentelemetry.io/docs/languages/python/exporters/`]
- [Source: `https://pypi.org/project/opentelemetry-sdk/`]
- [Source: `https://pypi.org/project/opentelemetry-exporter-otlp/`]
- [Source: `https://docs.dynatrace.com/docs/ingest-from/opentelemetry/getting-started/metrics/ingest/metrics-via-otlp-exporter`]
- [Source: `https://docs.dynatrace.com/docs/analyze-explore-automate/metrics/upgrade/metric-ingestion-opentelemetry`]

## Dev Agent Record

### Agent Model Used

GPT-5 (Codex)

### Debug Log References

- Story selected from `artifact/implementation-artifacts/sprint-status.yaml`: `7-2-opentelemetry-instrumentation-and-otlp-export`
- Epic and NFR context extracted from planning artifacts
- Prior story and git history mined for implementation patterns and risk guardrails
- Latest OTLP/OpenTelemetry specifics verified against official upstream docs

### Completion Notes List

- Story artifact created with comprehensive developer guardrails for Story 7.2.
- Prior-story and git intelligence included to prevent regressions and duplicate work.
- Latest technical references included with explicit pinned-vs-latest guidance.
- Story status set to `ready-for-dev`.

### File List

- artifact/implementation-artifacts/7-2-opentelemetry-instrumentation-and-otlp-export.md
- artifact/implementation-artifacts/sprint-status.yaml

## Change Log

- 2026-03-07: Created Story 7.2 implementation-ready context file with architecture, testing, and OTLP export guardrails.
