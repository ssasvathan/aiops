# Story 8.4: SN Correlation Fallback Rate Metrics

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As an SRE/operator,
I want Tier 1 vs Tier 2/3 SN correlation fallback rates tracked as metrics,
so that I can detect when the primary correlation path is degraded and escalate to the PD/SN integration team (FR50).

## Acceptance Criteria

1. **Given** SN Incident correlations are being performed
   **When** correlation results are recorded
   **Then** a Prometheus-compatible gauge metric is exposed per correlation tier (`tier1`, `tier2`, `tier3`, `none`)
2. **And** metrics are available on the /metrics endpoint (via OpenTelemetry OTLP export)
3. **And** alerting threshold for Tier 2/3 fallback rate is configurable per deployment
4. **And** high Tier 2/3 fallback rate indicates PD is not populating the SN correlation field and is actionable by the integration team
5. **And** SN linkage rate target is tracked: >= 90% of PAGE cases LINKED within 2-hour retry window
6. **And** unit tests verify: metric updates per tier, gauge accuracy across multiple correlations, configurable alerting threshold behavior

## Tasks / Subtasks

- [x] Task 1: Add SN correlation tier metric primitives in shared OTLP telemetry module (AC: 1, 2, 6)
  - [x] Extend `src/aiops_triage_pipeline/health/metrics.py` with a metric family for correlation tiers and helper function(s), reusing the existing gauge-via-delta pattern used elsewhere in the file.
  - [x] Keep label cardinality bounded to fixed values (`tier1`, `tier2`, `tier3`, `none`) and avoid dynamic/unbounded labels.
  - [x] Maintain existing `aiops.*` metric naming convention used across current OTLP instrumentation.

- [x] Task 2: Instrument ServiceNow correlation path with deterministic metric recording (AC: 1, 2, 4)
  - [x] Update `src/aiops_triage_pipeline/integrations/servicenow.py` to record correlation tier outcomes exactly once per `correlate_incident(...)` call.
  - [x] Ensure OFF/LOG/MOCK/LIVE modes all produce deterministic metric behavior without introducing outbound side effects.
  - [x] Preserve existing correlation result contract (`matched_tier`, `reason`, metadata) and avoid behavior drift in tiered matching logic.

- [x] Task 3: Add fallback-rate threshold configuration artifact support (AC: 3, 4, 6)
  - [x] Extend `src/aiops_triage_pipeline/contracts/operational_alert_policy.py` with an SN fallback-rate alert section using existing threshold/rule patterns.
  - [x] Update `config/policies/operational-alert-policy-v1.yaml` with per-environment warning/critical thresholds and reviewable rule metadata for SN correlation fallback rate.
  - [x] Keep rule-id uniqueness guarantees intact and update contract validation/tests accordingly.

- [x] Task 4: Add deterministic alert evaluation logic for fallback-rate thresholds (AC: 3, 4, 6)
  - [x] Extend `src/aiops_triage_pipeline/health/alerts.py` with a method to evaluate fallback rate against env-specific thresholds using existing evaluator style.
  - [x] Keep evaluation pure/deterministic (input signal + policy -> evaluation/no-evaluation) and avoid hidden state beyond explicitly needed rolling-window context.
  - [x] Include metadata in alert output that points operators to integration degradation signal (Tier 2/3 fallback growth).

- [x] Task 5: Track linkage success-rate signal for FR50/Success Criteria alignment (AC: 5)
  - [x] Add/extend telemetry signal(s) that let operators measure `LINKED within 2-hour window` rate for PAGE cases.
  - [x] Reuse linkage state machine outcomes (`LINKED`, `FAILED_TEMP`, `FAILED_FINAL`) from Story 8.3 rather than introducing parallel status tracking.
  - [x] Ensure metric semantics are explicit (numerator/denominator and time window assumptions documented in code comments/tests).

- [x] Task 6: Add and update tests for new metrics + threshold behavior (AC: 6)
  - [x] Update `tests/unit/integrations/test_servicenow.py` to assert metric recording for each tier result.
  - [x] Update `tests/unit/health/test_alerts.py` for new fallback-rate threshold evaluation behavior.
  - [x] Update `tests/unit/contracts/test_operational_alert_policy.py` for contract/yaml validation of new fallback-rate alert section.
  - [x] Extend `tests/integration/test_otlp_export.py` to verify export of new SN correlation metric names/labels/values.

- [x] Task 7: Run quality gates with zero-skip posture
  - [x] `uv run ruff check`
  - [x] `uv run pytest -q -m "not integration"`
  - [x] `TESTCONTAINERS_RYUK_DISABLED=true DOCKER_HOST=unix://$HOME/.docker/desktop/docker.sock uv run pytest -q -rs`
  - [x] Confirm full regression reports `0 skipped`

## Dev Notes

### Developer Context Section

- Story key: `8-4-sn-correlation-fallback-rate-metrics`
- Story ID: `8.4`
- Epic context:
  - 8.1 implemented tiered SN correlation.
  - 8.2 implemented idempotent Problem/PIR upsert + linkage stage persistence.
  - 8.3 implemented linkage retry state machine and terminal recovery.
  - 8.4 adds observability and thresholded operability for correlation fallback behavior.

Current baseline in code:
- Tiered correlation decision is implemented in `ServiceNowClient.correlate_incident(...)` and emits `matched_tier` (`tier1|tier2|tier3|none`).
- OTLP metrics live in `src/aiops_triage_pipeline/health/metrics.py` and are validated by `tests/integration/test_otlp_export.py`.
- Operational alert thresholds/metadata live in `OperationalAlertPolicyV1` + `config/policies/operational-alert-policy-v1.yaml` and are evaluated by `OperationalAlertEvaluator`.
- No in-app Prometheus scraping endpoint exists today; architecture uses OTLP export path for metrics.

### Technical Requirements

1. Record tier outcome telemetry for every correlation attempt with fixed low-cardinality labels.
2. Provide Prometheus-compatible series semantics for tier breakdown and Tier2/3 fallback trend analysis.
3. Add deployment-configurable fallback-rate thresholds (warning/critical) in versioned policy artifacts.
4. Ensure fallback-rate alert evaluation is deterministic and environment-aware.
5. Include a measurable signal for SN linkage success target (`>= 90% within 2-hour window`) aligned with Phase 1B success criteria.
6. Preserve existing ServiceNow correlation and linkage behavior from Stories 8.1-8.3 (no regressions in matching, idempotent upsert, retry-state behavior).
7. Preserve integration safety defaults and MI-1 posture.
8. Keep instrumentation non-blocking and lightweight for cold-path execution.

### Architecture Compliance

- Preserve architecture decision: metrics export through OpenTelemetry OTLP pipeline, not by introducing a new application web framework surface.
- Keep module boundaries:
  - instrumentation helpers in `health/metrics.py`
  - SN behavior in `integrations/servicenow.py`
  - alert policy schema in `contracts/operational_alert_policy.py`
  - alert evaluation logic in `health/alerts.py`
- Maintain deterministic hot/cold-path separation; this story augments observability and must not alter gating authority.
- Keep denylist and integration mode patterns unchanged.

### Library / Framework Requirements

- Use current project stack/pins from `pyproject.toml` unless explicitly required otherwise:
  - `opentelemetry-sdk==1.39.1`
  - `opentelemetry-exporter-otlp==1.39.1`
  - `SQLAlchemy==2.0.47`
  - `structlog==25.5.0`
- Use existing OTel API/instrument style already present in `health/metrics.py`.
- Follow Prometheus metric naming/labeling practices (bounded cardinality, consistent units/semantics) while preserving repository naming conventions.

### File Structure Requirements

Primary files expected to change:

- `src/aiops_triage_pipeline/health/metrics.py`
- `src/aiops_triage_pipeline/integrations/servicenow.py`
- `src/aiops_triage_pipeline/contracts/operational_alert_policy.py`
- `config/policies/operational-alert-policy-v1.yaml`
- `src/aiops_triage_pipeline/health/alerts.py`
- `tests/unit/integrations/test_servicenow.py`
- `tests/unit/health/test_alerts.py`
- `tests/unit/contracts/test_operational_alert_policy.py`
- `tests/integration/test_otlp_export.py`

Files to avoid changing in this story:

- `src/aiops_triage_pipeline/pipeline/stages/gating.py` (out of scope)
- `src/aiops_triage_pipeline/contracts/action_decision.py` (out of scope)
- unrelated epic/story artifacts

### Testing Requirements

Minimum expected coverage:

1. Tier metric updates for each outcome: `tier1`, `tier2`, `tier3`, `none`.
2. Gauge/state accuracy across repeated correlations (including mixed tier sequences).
3. No regression in existing tiered-correlation behavior and integration modes.
4. Policy contract validation for new fallback-rate alert section and rule-id uniqueness.
5. Alert evaluator behavior across `local/dev/uat/prod` thresholds.
6. OTLP integration test confirms new metric names/labels/values are exported.
7. Full regression run completes with `0 skipped`.

### Previous Story Intelligence

From Story 8.3 implementation and review outcomes:

- Reuse established linkage/ServiceNow modules; avoid parallel orchestration paths.
- Keep retry/linkage terminal semantics authoritative from persisted state (`LINKED`/`FAILED_FINAL`).
- Preserve idempotency and write-scope boundaries for SN integration paths.
- Maintain explicit denylist handling for outbound content and structured logging fields.
- Keep mode-aware behavior (`OFF|LOG|MOCK|LIVE`) deterministic and side-effect-safe in non-LIVE modes.

### Git Intelligence Summary

Recent commits indicate stable extension points for this story:

- `e64fa04` fixed linkage terminal recovery and FAILED_FINAL escalation coverage in linkage state + tests.
- `fba8a75` added Story 8.3 retry state machine and touched `servicenow.py`, `linkage.py`, policy/contracts, and tests.
- `04df332`, `d87532d`, `a0ac885` established SN correlation/upsert foundations and test patterns.

Actionable guidance:

- Build 8.4 on existing instrumentation and SN modules; do not introduce a new telemetry subsystem.
- Follow contract+policy+code+tests in one change pattern for threshold configurability.

### Latest Tech Information

Research timestamp: 2026-03-08.

- PyPI shows:
  - `opentelemetry-sdk` latest is `1.40.0` (released 2026-03-04); repo pin is `1.39.1`.
  - `opentelemetry-exporter-otlp` latest is `1.40.0` (released 2026-03-04); repo pin is `1.39.1`.
  - `SQLAlchemy` latest stable is `2.0.48` (released 2026-03-02); repo pin is `2.0.47`.
  - `prometheus-client` latest is `0.24.1` (released 2026-01-14); repo dev pin is `~0.24.0`.
- Prometheus naming guidance emphasizes:
  - consistent base units and semantic consistency per metric,
  - meaningful aggregation over label dimensions,
  - avoiding high-cardinality labels.
- ServiceNow Table API (Zurich reference) confirms primary endpoints used by this integration pattern:
  - `GET /api/now/table/{tableName}`
  - `PATCH /api/now/table/{tableName}/{sys_id}`
  - `POST /api/now/table/{tableName}`
  - query parameters such as `sysparm_query`, pagination via `sysparm_limit`/`sysparm_offset`.
- ServiceNow inbound REST rate-limit docs specify response headers and failure semantics, including `X-RateLimit-*`, `Retry-After`, and `429 Too Many Requests`.
- Slack docs state incoming webhooks are rate-limited (1 per second baseline) and rate-limit responses include `HTTP 429` with `Retry-After`.

Implementation takeaway:

- Implement 8.4 using existing pinned dependencies and current module patterns.
- Keep metric labels bounded and deterministic.
- Ensure fallback-rate handling and any alerting/retry semantics remain compatible with upstream 429 + `Retry-After` behavior.

### Project Context Reference

Applied rules from `artifact/project-context.md`:

- Reuse shared frameworks/utilities; no parallel policy or instrumentation frameworks.
- Preserve deterministic behavior and integration mode safety defaults.
- Keep structured logging and denylist posture intact.
- Add targeted unit/integration tests for every touched contract/policy/integration behavior.
- Enforce full-suite zero-skip quality gate.

### Project Structure Notes

- Preferred implementation location is additive inside existing modules, not new subsystem packages.
- Keep tests mirrored to affected domain packages.
- No architecture exception is needed for this story if OTLP path and alert-policy pattern are followed.

### References

- [Source: `artifact/planning-artifacts/epics.md` (Epic 8, Story 8.4)]
- [Source: `artifact/planning-artifacts/prd/functional-requirements.md` (FR46-FR50)]
- [Source: `artifact/planning-artifacts/prd/non-functional-requirements.md` (NFR-O1, NFR-O2, NFR-R1, NFR-R3)]
- [Source: `artifact/planning-artifacts/prd/success-criteria.md` (SN linkage + fallback trend outcomes)]
- [Source: `artifact/planning-artifacts/prd/project-scoping-phased-development.md` (Phase 1B exit criteria)]
- [Source: `artifact/planning-artifacts/architecture.md` (OTLP-first metrics, no FastAPI, package boundaries)]
- [Source: `artifact/project-context.md` (implementation/testing guardrails)]
- [Source: `artifact/implementation-artifacts/8-3-sn-linkage-retry-and-state-machine.md` (previous story learnings)]
- ServiceNow Table API: https://www.servicenow.com/docs/bundle/zurich-api-reference/page/integrate/inbound-rest/concept/c_TableAPI.html
- ServiceNow inbound REST API rate limiting: https://www.servicenow.com/docs/bundle/yokohama-api-reference/page/integrate/inbound-rest/concept/inbound-REST-API-rate-limiting.html
- Slack rate limits: https://api.slack.com/apis/rate-limits
- Prometheus metric naming: https://prometheus.io/docs/practices/naming/
- Prometheus instrumentation practices: https://prometheus.io/docs/practices/instrumentation/
- PyPI opentelemetry-sdk: https://pypi.org/project/opentelemetry-sdk/
- PyPI opentelemetry-exporter-otlp: https://pypi.org/project/opentelemetry-exporter-otlp/
- PyPI SQLAlchemy: https://pypi.org/project/SQLAlchemy/
- PyPI prometheus-client: https://pypi.org/project/prometheus-client/

### Story Completion Status

- Story document created: `artifact/implementation-artifacts/8-4-sn-correlation-fallback-rate-metrics.md`
- Workflow status set for handoff: `done`
- Completion note: Implementation complete with zero-skip regression gate passed (`823 passed`, `0 skipped`).

## Dev Agent Record

### Agent Model Used

GPT-5 Codex

### Debug Log References

- Implemented `aiops.servicenow.*` fallback/linkage metrics in `health/metrics.py` using bounded-label gauge-via-delta patterns.
- Wired deterministic per-call correlation metric recording into `ServiceNowClient.correlate_incident(...)` across OFF/LOG/MOCK/LIVE modes.
- Extended operational alert policy contract + YAML + evaluator for SN fallback-rate thresholds with env-specific warning/critical metadata.
- Added PAGE linkage SLO metric emission from linkage state-machine terminal transitions in `pipeline/stages/linkage.py`.
- Completed quality gates: `uv run ruff check`, `uv run pytest -q -m "not integration"`, and full Docker-enabled regression with zero skips.

### Implementation Plan

- Add bounded-cardinality ServiceNow correlation + linkage SLO metric helpers in shared telemetry module.
- Instrument correlation path to record exactly one tier outcome per `correlate_incident(...)` invocation.
- Extend operational alert policy schema/artifact/evaluator with SN fallback-rate thresholds and rule metadata.
- Capture PAGE linkage SLO outcomes only from terminal retry-state transitions (LINKED/FAILED_FINAL).
- Validate through unit + integration tests and full regression quality gates.

### Completion Notes List

- Added ServiceNow correlation tier gauges (`tier1|tier2|tier3|none`) and deterministic fallback-rate gauge computation.
- Added PAGE linkage SLO telemetry with explicit denominator/numerator semantics and 2-hour window behavior.
- Added SN fallback-rate policy section with env thresholds + unique rule-id enforcement in contract validation.
- Added deterministic evaluator method for SN fallback-rate alerts with metadata (`fallback_tiers`, `sample_size`).
- Expanded tests for metrics helpers, correlation instrumentation, policy validation, evaluator behavior, linkage-stage metric emission, and OTLP export.
- Wired runtime fallback-rate alert evaluation directly into `ServiceNowClient` correlation finalization so policy thresholds now trigger operational alert events.
- Tightened PAGE linkage SLO semantics: `skipped` linkage outcomes are excluded from success-rate accounting, and within-window success now requires explicit timing.
- Switched fallback/linkage rate gauges from unbounded lifetime averages to bounded rolling windows for faster degradation visibility.
- All quality gates passed; full suite result: `823 passed`, no skipped tests reported.

### Senior Developer Review (AI)

- Reviewer: Sas
- Date: 2026-03-08
- Outcome: Approved after fixes
- Review findings addressed:
  - HIGH: Fallback-rate thresholds were not wired to runtime evaluation.
  - HIGH: Linkage SLO success metric could be inflated by `skipped`/ambiguous timing paths.
  - MEDIUM: Rate gauges used unbounded lifetime averages and masked short-term degradation.
- Validation commands run:
  - `uv run ruff check src/aiops_triage_pipeline/health/metrics.py src/aiops_triage_pipeline/integrations/servicenow.py src/aiops_triage_pipeline/pipeline/stages/linkage.py tests/unit/health/test_metrics.py tests/unit/integrations/test_servicenow.py tests/unit/pipeline/stages/test_linkage.py`
  - `uv run pytest -q -m "not integration" tests/unit/health/test_metrics.py tests/unit/integrations/test_servicenow.py tests/unit/pipeline/stages/test_linkage.py tests/unit/health/test_alerts.py tests/unit/contracts/test_operational_alert_policy.py`
  - `TESTCONTAINERS_RYUK_DISABLED=true DOCKER_HOST=unix://$HOME/.docker/desktop/docker.sock uv run pytest -q -rs tests/integration/test_otlp_export.py -m integration`
  - `TESTCONTAINERS_RYUK_DISABLED=true DOCKER_HOST=unix://$HOME/.docker/desktop/docker.sock uv run pytest -q -rs`
  - Results: `823 passed`, `0 skipped`

### File List

- artifact/implementation-artifacts/8-4-sn-correlation-fallback-rate-metrics.md
- artifact/implementation-artifacts/sprint-status.yaml
- config/policies/operational-alert-policy-v1.yaml
- src/aiops_triage_pipeline/contracts/operational_alert_policy.py
- src/aiops_triage_pipeline/health/alerts.py
- src/aiops_triage_pipeline/health/metrics.py
- src/aiops_triage_pipeline/integrations/servicenow.py
- src/aiops_triage_pipeline/pipeline/stages/linkage.py
- tests/integration/test_otlp_export.py
- tests/unit/contracts/test_operational_alert_policy.py
- tests/unit/health/test_alerts.py
- tests/unit/health/test_metrics.py
- tests/unit/integrations/test_servicenow.py
- tests/unit/pipeline/stages/test_linkage.py

## Change Log

- 2026-03-08: Implemented Story 8.4 end-to-end (SN fallback metrics, policy thresholds, evaluator, linkage SLO telemetry, tests, and zero-skip quality gates); status moved to `review`.
- 2026-03-08: Senior Developer Review (AI) completed; resolved 2 HIGH + 1 MEDIUM findings (runtime alert wiring, SLO semantic tightening, rolling-rate gauges), reran full zero-skip regression, and marked story `done`.
