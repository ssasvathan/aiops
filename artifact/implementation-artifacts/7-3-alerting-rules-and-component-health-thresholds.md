# Story 7.3: Alerting Rules and Component Health Thresholds

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As an SRE/operator,
I want alerting rules defined for all monitored components with configurable thresholds,
so that I am proactively notified when any component degrades beyond acceptable bounds (NFR-O2).

## Acceptance Criteria

1. **Given** OpenTelemetry metrics are being exported from Story 7.2
   **When** alerting rules are defined
   **Then** alerting rules exist for: outbox age thresholds (per outbox-policy-v1), DEAD>0 (crit in prod), Redis connection loss, Prometheus unavailability (TelemetryDegradedEvent), LLM error rate spikes, evaluation interval drift, and pipeline latency breach
2. **And** alert definitions are versioned and reviewable as operational artifacts
3. **And** alerting thresholds are configurable per environment
4. **And** each alert rule includes: condition, severity (warn/crit), affected component, and recommended action
5. **And** unit tests verify: threshold breach detection for each alert rule, correct severity classification, configurable threshold overrides

## Tasks / Subtasks

- [x] Task 1: Add a versioned operational alert policy artifact and contract (AC: 1, 2, 3, 4)
  - [x] Create `config/policies/operational-alert-policy-v1.yaml` with explicit rules for outbox, Redis, Prometheus, LLM, scheduler drift, and pipeline latency
  - [x] Add frozen Pydantic contract(s) under `src/aiops_triage_pipeline/contracts/` for policy schema validation
  - [x] Enforce required env coverage (`local`, `dev`, `uat`, `prod`) and threshold ordering/validations in contract validators
  - [x] Export new contract types in `src/aiops_triage_pipeline/contracts/__init__.py`

- [x] Task 2: Implement centralized alert rule evaluation logic (AC: 1, 3, 4)
  - [x] Add `src/aiops_triage_pipeline/health/alerts.py` with a deterministic evaluator that produces normalized alert evaluations (`rule_id`, `component`, `severity`, `condition`, `recommended_action`)
  - [x] Reuse existing signals rather than duplicating telemetry logic:
    - outbox backlog + SLO breach signals from `outbox/worker.py`
    - Redis status from `health/registry.py` / `health/metrics.py`
    - Prometheus degraded state from `run_evidence_stage_cycle()`
    - LLM error metrics from `diagnosis/graph.py` + `health/metrics.py`
    - scheduler drift + stage latency from `pipeline/scheduler.py`
  - [x] Keep evaluator side effects limited to structured alert events (no action decision mutation)

- [x] Task 3: Wire alert evaluations into runtime paths (AC: 1, 4)
  - [x] Integrate outbox rule checks where outbox threshold breaches are already detected
  - [x] Integrate scheduler/Prometheus rule checks in scheduler cycle utilities
  - [x] Integrate LLM error-rate rule checks in cold-path completion/error paths
  - [x] Emit a stable structured event (for example `operational_alert_rule_triggered`) with required fields for downstream ops tooling

- [x] Task 4: Ensure environment-specific configurability and startup transparency (AC: 3)
  - [x] Load alert policy via existing `load_policy_yaml(...)` path and bind active env thresholds by `APP_ENV`
  - [x] Add startup log fields indicating active alert policy version and env profile
  - [x] Keep secrets masked and preserve existing config precedence rules

- [x] Task 5: Preserve versioned/reviewable operational artifact workflow (AC: 2)
  - [x] Keep alert definitions in repository-managed YAML under `config/policies/`
  - [x] Include stable rule IDs and human-readable operator guidance per rule
  - [x] Ensure changes are easy to diff and review in PRs (no generated/unordered output)

- [x] Task 6: Add/extend unit tests for all alert rules and overrides (AC: 5)
  - [x] Add `tests/unit/health/test_alerts.py` covering every rule's threshold breach behavior and severity classification
  - [x] Add/extend tests in `tests/unit/outbox/test_worker.py`, `tests/unit/pipeline/test_scheduler.py`, and `tests/unit/diagnosis/test_graph.py` for integration points
  - [x] Add contract validation tests for alert policy schema in `tests/unit/contracts/`
  - [x] Include env override tests proving local/dev/uat/prod threshold selection works as expected

- [x] Task 7: Run quality gates with zero-skip posture (AC: 5)
  - [x] `uv run ruff check`
  - [x] `uv run pytest -q -m "not integration"`
  - [x] `TESTCONTAINERS_RYUK_DISABLED=true DOCKER_HOST=unix://$HOME/.docker/desktop/docker.sock uv run pytest -q -rs`
  - [x] Verify full run reports `0 skipped`

## Dev Notes

### Developer Context Section

- Story key: `7-3-alerting-rules-and-component-health-thresholds`
- Story ID: `7.3`
- Epic context: Epic 7 operational observability hardening; Story 7.3 builds rule-based alerting on top of Story 7.1 outbox health signals and Story 7.2 OTLP component metrics.
- Dependency context:
  - Story 7.1 already implemented outbox threshold detection/logging and DEAD posture enforcement.
  - Story 7.2 already implemented OTLP metric emission for Redis, LLM, Prometheus connectivity, evidence interval behavior, and pipeline latency.

Implementation intent:
- Create a single, versioned, environment-aware alert-rule layer that consumes existing signals and emits consistent operational alert events without changing deterministic triage/gating outcomes.

### Technical Requirements

1. Alert rule scope must match NFR-O2 exactly
- Required rule families: outbox age thresholds, outbox DEAD>0 posture, Redis connection loss, Prometheus unavailability/telemetry degraded, LLM error-rate spikes, scheduler interval drift, pipeline latency breaches.

2. Reuse existing policy and runtime sources
- Outbox thresholds and DEAD posture remain authoritative in `config/policies/outbox-policy-v1.yaml`; do not re-encode different values elsewhere.
- For non-outbox rules, define thresholds in a dedicated operational alert policy artifact with per-environment values.

3. Rule representation requirements
- Each rule must provide at least:
  - `rule_id`
  - `component`
  - `condition` (machine-readable + operator-readable)
  - `severity` (`warning`/`critical`)
  - `recommended_action`
- Rule IDs must be stable and review-friendly (for example `ALERT_OUTBOX_READY_AGE_CRITICAL`).

4. Deterministic behavior and bounded cardinality
- No dynamic labels with high cardinality (`case_id`, free text, unbounded keys) in emitted alert metrics/events.
- Alert evaluator must be deterministic and side-effect safe; it must not alter gate decisions, outbox state transitions, or degraded-mode caps.

5. Config and startup behavior
- Policy loading must use existing `load_policy_yaml(...)` pattern.
- Active alert policy version + env must be logged at startup per NFR-O4 transparency expectations.

### Architecture Compliance

- Keep alerting logic within existing boundaries:
  - Cross-cutting health/telemetry logic under `health/`
  - Existing outbox threshold checks remain in `outbox/worker.py`
  - Scheduler cadence/latency behavior remains in `pipeline/scheduler.py`
  - LLM invocation/error behavior remains in `diagnosis/graph.py`
- Maintain `HealthRegistry` as the source of truth for component health transitions.
- Preserve architecture decision 4C: centralized degraded-state coordination + OTLP telemetry.
- Do not introduce FastAPI or a new runtime service for this story.
- Preserve custom exception taxonomy (`CriticalDependencyError` vs degradable flows); alerting augments observability, not control-flow safety behavior.

### Library / Framework Requirements

Pinned repo versions to keep for this story scope:
- `opentelemetry-sdk==1.39.1`
- `opentelemetry-exporter-otlp==1.39.1`
- `prometheus-client~=0.24.0`
- `pydantic==2.12.5`

Implementation guidance:
- Continue using OpenTelemetry metrics primitives already established in `health/metrics.py`.
- Use Pydantic frozen models for the new alert policy contract.
- Use structured logging patterns already established with `structlog`.

Latest reference snapshot (researched 2026-03-08):
- Prometheus alerting rules documentation emphasizes explicit `for`/`keep_firing_for` windows and label/annotation templating; mirror this semantics in local rule metadata to avoid ambiguous flapping behavior.
- Dynatrace OTLP ingest for metrics remains `/api/v2/otlp/v1/metrics`; keep OTLP metric naming stable to avoid dashboard/alert drift.

### File Structure Requirements

Existing files expected to be touched:
- `src/aiops_triage_pipeline/outbox/worker.py`
- `src/aiops_triage_pipeline/pipeline/scheduler.py`
- `src/aiops_triage_pipeline/diagnosis/graph.py`
- `src/aiops_triage_pipeline/config/settings.py` (only if new policy path/settings are required)
- `src/aiops_triage_pipeline/contracts/__init__.py`

Likely new files:
- `config/policies/operational-alert-policy-v1.yaml`
- `src/aiops_triage_pipeline/contracts/operational_alert_policy.py`
- `src/aiops_triage_pipeline/health/alerts.py`

Tests to add/update:
- `tests/unit/health/test_alerts.py`
- `tests/unit/contracts/test_operational_alert_policy.py`
- `tests/unit/outbox/test_worker.py`
- `tests/unit/pipeline/test_scheduler.py`
- `tests/unit/diagnosis/test_graph.py`

### Testing Requirements

Minimum unit coverage:
- Every required rule has explicit positive + negative threshold tests.
- Severity mapping correctness (`warning` vs `critical`) for each rule.
- Environment-specific override selection (`local`, `dev`, `uat`, `prod`) for each configurable threshold family.
- Contract validation tests for malformed policy definitions (missing envs, invalid threshold ordering, invalid severity/action).

Regression and integration expectations:
- Existing Prometheus degraded/Redis degraded/outbox threshold tests must continue to pass without behavior regression.
- If integration behavior changes, add/extend integration tests without introducing skip fallbacks.
- Full regression must remain zero-skip.

Required quality gate commands:
- `uv run ruff check`
- `uv run pytest -q -m "not integration"`
- `TESTCONTAINERS_RYUK_DISABLED=true DOCKER_HOST=unix://$HOME/.docker/desktop/docker.sock uv run pytest -q -rs`

### Previous Story Intelligence

From Story 7.2 (`7-2-opentelemetry-instrumentation-and-otlp-export.md`):
- Story 7.2 intentionally stabilized metric names/labels across components; Story 7.3 must consume these as a stable API.
- Integration posture is fail-fast/no-skip. Avoid any new skip-based fallbacks for alerting tests.
- Unknown-rate metric handling deliberately avoids synthetic 0 values when denominator is missing; do not reinterpret missing denominator as healthy.
- Runtime bootstrap already includes OTLP setup + masked settings logging; reuse rather than duplicating telemetry initialization.

From Story 7.1 (`7-1-outbox-health-monitoring-and-dead-0-posture.md` via repo history and current code):
- Outbox threshold and DEAD posture semantics are already encoded in `outbox/worker.py` and `outbox-policy-v1`; treat these as authoritative for outbox-related alert rules.

### Git Intelligence Summary

Recent relevant commits:
- `2fc3e44` (`feat: implement story 7.2 OTLP instrumentation and export`)
  - Added OTLP bootstrap, component metrics, and test harness patterns this story should build on.
- `7bbbf21` (`fix: resolve Story 7.2 review findings`)
  - Reinforced fail-fast integration fixture posture and metric correctness assertions.
- `ac4c85c` (`reconcile outbox review fixes and align story artifacts`)
  - Tightened outbox threshold handling/tests; avoid conflicting reimplementation in Story 7.3.
- `860ee68` (`chore(story-7.2): mark story done and sync sprint status`)
  - Confirms Story 7.2 completion baseline and readiness for rule-layer follow-up.

Actionable guidance:
- Implement alerting as an additive layer over existing metrics/events.
- Avoid introducing parallel threshold logic that can drift from outbox-policy and existing scheduler/registry semantics.
- Keep tests explicit and deterministic; align with existing unit test style (structured log assertions, direct model/assert usage).

### Latest Tech Information

Research timestamp: 2026-03-08.

- Prometheus alerting rules support `for` and `keep_firing_for` controls to reduce flapping and define sustained conditions; this is directly relevant to LLM-error-spike and drift alert semantics.
- Prometheus alert rules support labels and annotations templating; keep local operational artifact fields compatible with these concepts (`severity`, `summary`, `description`, runbook/action text).
- PyPI currently lists `opentelemetry-sdk` at `1.39.1` and `opentelemetry-exporter-otlp` at `1.39.1` in the primary package pages used for this project baseline.
- PyPI currently lists `prometheus-client` at `0.24.0`, which matches the current harness dependency baseline.
- Dynatrace OTLP metric ingest path remains `/api/v2/otlp/v1/metrics`.

Implementation implication:
- No dependency bump is required for Story 7.3; focus on rule definitions/evaluation over the current telemetry stack.

### Project Context Reference

Applied rules from `artifact/project-context.md`:
- Deterministic guardrails remain authoritative; alerting must never alter gate decisions.
- Preserve `HealthRegistry` as centralized degraded-state coordination.
- Keep config boundaries intact (`config` as leaf, env precedence rules unchanged).
- Maintain structured logging and secret masking.
- Enforce no-skip quality gate discipline.

### Project Structure Notes

- Keep operational alert policy under `config/policies/` with stable, reviewable YAML format.
- Keep policy contracts under `contracts/` and runtime evaluation under `health/` to preserve architectural layering.
- Integrate alert checks at existing signal origins (`outbox/`, `scheduler`, `diagnosis`) instead of polling duplicate state from unrelated modules.
- Prefer additive changes over broad refactors in hot-path or outbox publish control flow.

### References

- [Source: `artifact/planning-artifacts/epics.md` - Story 7.3 acceptance criteria]
- [Source: `artifact/planning-artifacts/epics.md` - Story 7.1 and Story 7.2 dependency context]
- [Source: `artifact/planning-artifacts/prd/non-functional-requirements.md` - NFR-O2 alert rule requirements]
- [Source: `artifact/planning-artifacts/architecture.md` - Decision 4C (HealthRegistry + OTLP + degraded mode coordination)]
- [Source: `config/policies/outbox-policy-v1.yaml` - outbox thresholds and DEAD posture]
- [Source: `src/aiops_triage_pipeline/outbox/worker.py` - outbox threshold breach emission patterns]
- [Source: `src/aiops_triage_pipeline/pipeline/scheduler.py` - scheduler drift and Prometheus degraded transitions]
- [Source: `src/aiops_triage_pipeline/health/metrics.py` - existing metrics families to consume]
- [Source: `src/aiops_triage_pipeline/diagnosis/graph.py` - LLM error metric emission context]
- [Source: `artifact/project-context.md` - implementation guardrails]
- [Source: `https://prometheus.io/docs/prometheus/latest/configuration/alerting_rules/`]
- [Source: `https://prometheus.io/docs/prometheus/latest/configuration/template_reference/`]
- [Source: `https://pypi.org/project/opentelemetry-sdk/`]
- [Source: `https://pypi.org/project/opentelemetry-exporter-otlp/`]
- [Source: `https://pypi.org/project/prometheus-client/`]
- [Source: `https://docs.dynatrace.com/docs/ingest-from/opentelemetry/getting-started/metrics/ingest/metrics-via-otlp-exporter`]

## Dev Agent Record

### Agent Model Used

GPT-5 (Codex)

### Debug Log References

- Sprint status discovery selected first backlog story `7-3-alerting-rules-and-component-health-thresholds`.
- Core context analyzed from:
  - `artifact/planning-artifacts/epics.md`
  - `artifact/planning-artifacts/architecture.md`
  - `artifact/project-context.md`
  - `artifact/implementation-artifacts/7-2-opentelemetry-instrumentation-and-otlp-export.md`
- Repository runtime/test context analyzed from:
  - `src/aiops_triage_pipeline/outbox/worker.py`
  - `src/aiops_triage_pipeline/pipeline/scheduler.py`
  - `src/aiops_triage_pipeline/health/metrics.py`
  - `src/aiops_triage_pipeline/config/settings.py`
  - `tests/unit/outbox/test_worker.py`
  - `tests/unit/pipeline/test_scheduler.py`
  - `tests/unit/health/test_metrics.py`
- Implementation completed:
  - Added `config/policies/operational-alert-policy-v1.yaml` with stable rule IDs and per-env thresholds.
  - Added frozen policy contract `src/aiops_triage_pipeline/contracts/operational_alert_policy.py` and exported types in `contracts/__init__.py`.
  - Added deterministic alert evaluator in `src/aiops_triage_pipeline/health/alerts.py`.
  - Wired alert emission (`operational_alert_rule_triggered`) into:
    - `src/aiops_triage_pipeline/outbox/worker.py`
    - `src/aiops_triage_pipeline/pipeline/scheduler.py`
    - `src/aiops_triage_pipeline/diagnosis/graph.py`
  - Added startup policy transparency in `src/aiops_triage_pipeline/__main__.py`.
- Quality gates executed:
  - `uv run ruff check` → pass
  - `uv run pytest -q -m "not integration"` → 693 passed, 19 deselected
  - `TESTCONTAINERS_RYUK_DISABLED=true DOCKER_HOST=unix://$HOME/.docker/desktop/docker.sock uv run pytest -q -rs` → 712 passed, 0 skipped

### Completion Notes List

- Created implementation-ready story context for Story 7.3 with explicit AC traceability.
- Added architecture guardrails to prevent duplicate threshold logic and preserve deterministic behavior.
- Added concrete file-level guidance and test strategy for versioned alert policy + runtime evaluator.
- Included latest technology/documentation references relevant to alert-rule semantics.
- Implemented a versioned operational alert policy artifact and frozen schema contract with env-specific thresholds.
- Implemented centralized deterministic alert evaluation with normalized payload fields (`rule_id`, `component`, `severity`, `condition`, `recommended_action`).
- Integrated operational alert emission into outbox threshold checks, scheduler drift/prometheus/latency paths, and cold-path LLM completion paths.
- Added/extended contract, evaluator, and runtime-integration unit tests covering severity mapping, threshold breaches, and env overrides.
- Completed full regression with Docker-enabled execution and zero skipped tests.
- Review fix pass addressed code-review findings: Redis runtime alert wiring, explicit severity in policy artifacts/contracts, and DEAD>0 threshold semantics across environments.

### File List

- artifact/implementation-artifacts/7-3-alerting-rules-and-component-health-thresholds.md
- config/policies/outbox-policy-v1.yaml
- config/policies/operational-alert-policy-v1.yaml
- src/aiops_triage_pipeline/__main__.py
- src/aiops_triage_pipeline/contracts/__init__.py
- src/aiops_triage_pipeline/contracts/outbox_policy.py
- src/aiops_triage_pipeline/contracts/operational_alert_policy.py
- src/aiops_triage_pipeline/diagnosis/graph.py
- src/aiops_triage_pipeline/health/__init__.py
- src/aiops_triage_pipeline/health/alerts.py
- src/aiops_triage_pipeline/outbox/worker.py
- src/aiops_triage_pipeline/pipeline/scheduler.py
- tests/unit/contracts/test_operational_alert_policy.py
- tests/unit/contracts/test_policy_models.py
- tests/unit/diagnosis/test_graph.py
- tests/unit/health/test_alerts.py
- tests/unit/outbox/test_worker.py
- tests/unit/pipeline/test_scheduler.py
- artifact/implementation-artifacts/sprint-status.yaml

### Senior Developer Review (AI)

- 2026-03-08: Changes Requested findings were resolved and revalidated.
- Fixed: Redis connection-loss operational rule now emits from runtime degradation path.
- Fixed: Rule descriptors now include explicit `severity` in policy contract and artifact.
- Fixed: `DEAD>0` now alerts in all environments (warning non-prod, critical prod).
- Traceability: Story task/subtask completion state aligned with implemented behavior.
- Verification:
  - `uv run ruff check` → pass
  - `uv run pytest -q -rs tests/unit/contracts/test_operational_alert_policy.py tests/unit/contracts/test_policy_models.py tests/unit/health/test_alerts.py tests/unit/outbox/test_worker.py tests/unit/pipeline/test_scheduler.py tests/unit/diagnosis/test_graph.py` → 146 passed
  - `TESTCONTAINERS_RYUK_DISABLED=true DOCKER_HOST=unix://$HOME/.docker/desktop/docker.sock uv run pytest -q -rs` → 712 passed, 0 skipped

## Change Log

- 2026-03-08: Created Story 7.3 implementation-ready context file with architecture constraints, rule-definition guidance, and testing gates.
- 2026-03-08: Implemented operational alert policy contract/artifact, runtime alert evaluation integration, startup transparency logging, and full zero-skip quality-gate validation.
- 2026-03-08: Applied code-review remediation for Story 7.3 and revalidated with full zero-skip regression.
