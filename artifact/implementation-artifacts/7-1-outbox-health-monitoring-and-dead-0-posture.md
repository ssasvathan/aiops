# Story 7.1: Outbox Health Monitoring & DEAD=0 Posture

Status: ready-for-dev

## Story

As an SRE/operator,
I want outbox health monitored with alerting thresholds and DEAD=0 enforced as a standing prod requirement,
so that I am immediately aware of publishing delays, stuck records, or critical DEAD accumulation (FR52,
FR53, FR54).

## Acceptance Criteria

1. **Given** the outbox is operational with records in various states
   **When** outbox health metrics are collected
   **Then** the following are monitored: PENDING_OBJECT age (>5m warn, >15m crit), READY age (>2m
   warn, >10m crit), RETRY age (>30m crit), DEAD count (>0 crit in prod) (FR52)
2. **And** outbox delivery SLO is measured: p95 <= 1 min, p99 <= 5 min from CaseFile write to Kafka
   publish; p99 > 10 min is critical (FR53)
3. **And** DEAD=0 is enforced as a standing prod posture; any DEAD row triggers a critical alert (FR54)
4. **And** DEAD records require human investigation and explicit replay/resolution; no automatic retry
5. **And** outbox queue depth by state (PENDING_OBJECT, READY, RETRY, DEAD, SENT), age of oldest per
   state, and publish latency histogram are exposed as metrics
6. **And** unit tests verify: threshold breach detection for each state, DEAD>0 alerting, SLO measurement
   calculation

## Tasks / Subtasks

- [ ] Task 1: Extend outbox policy contract to include monitoring and SLO thresholds (AC: 1, 2, 3)
  - [ ] Add threshold models under `src/aiops_triage_pipeline/contracts/outbox_policy.py` for:
    - per-state age thresholds (`pending_object`, `ready`, `retry`)
    - `dead_count_critical_threshold` by environment
    - delivery SLO thresholds (`p95_target_seconds`, `p99_target_seconds`, `p99_critical_seconds`)
  - [ ] Update `config/policies/outbox-policy-v1.yaml` with explicit threshold values matching FR52/FR53
  - [ ] Keep existing retention and max-retry fields backward-compatible
  - [ ] Add/adjust contract-policy tests in `tests/unit/contracts/test_policy_models.py`

- [ ] Task 2: Expand repository outbox health snapshot to include all monitored states (AC: 1, 5)
  - [ ] Replace tuple-based backlog health return with a typed snapshot model/dataclass in
    `src/aiops_triage_pipeline/outbox/repository.py`
  - [ ] Ensure snapshot includes:
    - queue depth for `PENDING_OBJECT`, `READY`, `RETRY`, `DEAD`, `SENT`
    - oldest age seconds for `PENDING_OBJECT`, `READY`, `RETRY`, `DEAD`
  - [ ] Keep timezone-aware age calculations and non-negative age values
  - [ ] Add repository unit coverage for multi-state snapshots

- [ ] Task 3: Add full outbox health and latency metrics instrumentation (AC: 2, 5)
  - [ ] Expand `src/aiops_triage_pipeline/outbox/metrics.py` to expose:
    - queue depth by state metric (with `state` label)
    - oldest age by state metric/histogram (with `state` label)
    - publish latency histogram (`casefile_write_to_publish_seconds`)
    - delivery SLO breach counters (warn/critical)
  - [ ] Keep existing `record_outbox_publish_outcome` semantics
  - [ ] Ensure metric update helpers avoid counter drift in repeated polling cycles

- [ ] Task 4: Implement threshold evaluation and DEAD=0 alerting in outbox worker (AC: 1, 2, 3, 4)
  - [ ] Update `src/aiops_triage_pipeline/outbox/worker.py` to consume expanded health snapshot and
    evaluate thresholds by state
  - [ ] Emit structured alert logs with stable fields:
    - `event_type="outbox.health.threshold_breach"`
    - `state`, `severity`, `actual_value`, `threshold_value`, `app_env`
  - [ ] Enforce `DEAD>0` as critical in `prod`; non-prod behavior may be warning/info but must not auto-retry
  - [ ] Compute publish latency per successful send from `created_at` to publish timestamp and feed
    histogram/SLO tracker
  - [ ] Evaluate rolling p95/p99 delivery SLO and emit warning/critical alerts on breach

- [ ] Task 5: Keep DEAD lifecycle strictly manual after DEAD transition (AC: 4)
  - [ ] Verify no code path transitions `DEAD -> RETRY/READY/SENT` automatically
  - [ ] Add explicit unit guard test in `tests/unit/outbox/test_state_machine.py` and/or
    `tests/unit/outbox/test_worker.py` that DEAD records are terminal without manual replay action
  - [ ] Ensure logs/messages explicitly state human investigation and explicit replay are required

- [ ] Task 6: Add/expand unit and integration tests for outbox observability behavior (AC: 6)
  - [ ] Update/add tests in `tests/unit/outbox/test_worker.py` for threshold checks:
    - PENDING_OBJECT warn/critical
    - READY warn/critical
    - RETRY critical
    - DEAD>0 critical in prod
  - [ ] Add dedicated metrics tests (new `tests/unit/outbox/test_metrics.py`) for queue depth, oldest age,
    and publish latency recording behavior
  - [ ] Add SLO measurement tests for p95/p99 window calculations and critical breach (`p99 > 10m`)
  - [ ] Add/extend integration test in `tests/integration/test_outbox_publish.py` validating metric/log
    emission path during worker execution

- [ ] Task 7: Quality gates and regression checks
  - [ ] `uv run ruff check`
  - [ ] `uv run pytest -q -m "not integration"`
  - [ ] `TESTCONTAINERS_RYUK_DISABLED=true DOCKER_HOST=unix://$HOME/.docker/desktop/docker.sock uv run pytest -q -rs`
  - [ ] Full suite must complete with `0 skipped`

## Dev Notes

### Developer Context Section

- Story key: `7-1-outbox-health-monitoring-and-dead-0-posture`
- Story ID: `7.1`
- Epic context: First delivery story in Epic 7 (Governance, Audit & Operational Observability).
- Cross-story context inside Epic 7:
  - Story 7.2 builds OTLP export breadth and component-level instrumentation.
  - Story 7.3 defines alerting rules as reviewable operational artifacts.
  - Story 7.1 must establish correct outbox health data and threshold semantics that 7.2/7.3 will consume.

Implementation intent:
- Build robust in-process outbox health signals now (state depth, state ages, publish latency) so later
  observability and alert-rule stories can stay configuration-centric rather than reworking core outbox
  logic.

### Technical Requirements

1. Outbox monitoring domain model
- Introduce a typed health snapshot for worker+metrics flow instead of positional tuple returns.
- Snapshot must include all states in `OUTBOX_STATES` and oldest-age fields needed for FR52.

2. Threshold semantics
- Implement FR52 thresholds exactly:
  - `PENDING_OBJECT` age: warn > 300s, critical > 900s
  - `READY` age: warn > 120s, critical > 600s
  - `RETRY` age: critical > 1800s
  - `DEAD` count: critical if `> 0` in `prod`
- Implement FR53 SLO thresholds:
  - p95 <= 60s target
  - p99 <= 300s target
  - p99 > 600s critical breach

3. Delivery latency measurement
- Derive latency from durable timestamps already in outbox records:
  - start: record creation/write-confirmed insertion time (`created_at`)
  - end: publish success transition time (`transition_to_sent`/publish timestamp)
- Record per-message latency to histogram and feed SLO evaluation window.

4. Logging and alert events
- Keep structured logging style from existing outbox worker.
- Add distinct health/threshold event types rather than overloading publish success/failure events.
- Include `case_id` when alert pertains to a specific record; include aggregate values for queue-level
  alerts.

5. DEAD posture constraints
- Do not add any automatic DEAD replay mechanism.
- DEAD remains a terminal automated state; operator replay/resolution is explicit/manual.

### Architecture Compliance

- Respect outbox state-machine authority:
  - transitions remain controlled by `outbox/state_machine.py` and guarded by repository source-state
    checks.
- Keep hot path and cold path separation intact:
  - this story only changes outbox publisher observability and monitoring behavior.
- Keep config package generic:
  - policy loading remains through `load_policy_yaml(path, model_class)` in `config/settings.py`.
- Maintain structured telemetry approach:
  - use existing OpenTelemetry SDK meter usage patterns in `health/metrics.py` and `outbox/metrics.py`.
- Maintain critical/degradable behavior split:
  - Kafka/postgres/object-store failures remain critical-path semantics; monitoring signals do not mask
    critical failures.

### Library / Framework Requirements

Current pinned stack in repo (must remain unless explicitly approved):
- `opentelemetry-sdk==1.39.1`
- `opentelemetry-exporter-otlp==1.39.1`
- `SQLAlchemy==2.0.47`
- `pydantic==2.12.5`

Guidance for Story 7.1:
- Reuse current OpenTelemetry instrument APIs already in project (`create_up_down_counter`,
  `create_histogram`, `create_counter`).
- Keep metrics naming consistent with existing `aiops.outbox.*` prefix for dashboard continuity.
- Do not introduce parallel telemetry libraries or ad-hoc `/metrics` collectors in this story.

### File Structure Requirements

Primary files to modify:
- `src/aiops_triage_pipeline/contracts/outbox_policy.py`
- `config/policies/outbox-policy-v1.yaml`
- `src/aiops_triage_pipeline/outbox/repository.py`
- `src/aiops_triage_pipeline/outbox/metrics.py`
- `src/aiops_triage_pipeline/outbox/worker.py`
- `tests/unit/contracts/test_policy_models.py`
- `tests/unit/outbox/test_worker.py`
- `tests/unit/outbox/test_state_machine.py`
- `tests/integration/test_outbox_publish.py`

Likely new test file:
- `tests/unit/outbox/test_metrics.py`

Files that should not require modification for this story:
- `src/aiops_triage_pipeline/pipeline/stages/gating.py`
- `src/aiops_triage_pipeline/diagnosis/*`
- `src/aiops_triage_pipeline/integrations/servicenow.py`

### Testing Requirements

Minimum unit test expectations:
- State-age threshold detection for each monitored state.
- Severity correctness (warn vs critical) per threshold.
- `DEAD>0` critical alerting in prod.
- SLO computation correctness for p95/p99 against deterministic latency samples.
- Metric-recording helper correctness (no negative ages, no gauge drift over successive updates).

Integration expectations:
- Outbox worker flow emits expected health metrics/logging while processing READY/RETRY/DEAD scenarios.
- Existing durability behavior (Invariant B2) remains intact.

Regression expectations:
- No skipped tests in full suite.
- Existing outbox publish and retry tests continue passing without behavior regressions.

### Previous Story Intelligence

Not applicable for implementation continuity.
- This is story `7.1`, the first story in Epic 7, so there is no earlier Epic 7 story file to mine for
  learnings.

### Git Intelligence Summary

Not applicable for this story context package.
- No Epic 7 implementation commit baseline exists yet.

### Latest Tech Information

Research timestamp: 2026-03-08.

- PyPI package pages currently list the project-pinned OpenTelemetry packages at the same line as
  the stack used by this repo (`1.39.1`) and do not require a forced version shift for this story.
- OpenTelemetry Python guidance continues to support metric instrument usage already present in code
  (`UpDownCounter`, `Histogram`, labeled attributes), so Story 7.1 should focus on complete metric
  coverage and threshold logic rather than telemetry framework migration.

Implementation decision for this story:
- Stay on current pinned OpenTelemetry versions and implement FR52/FR53 behavior in project code.
- Defer any dependency upgrade evaluation to dedicated dependency maintenance work, not this feature.

### Project Context Reference

Applied project-context rules from `artifact/project-context.md`:
- Reuse existing shared outbox and telemetry helpers; do not create duplicate enforcement paths.
- Maintain structured logging and avoid secret leakage in alert fields.
- Preserve critical invariants and do not introduce silent fallback on critical failures.
- Add targeted tests for behavior changes; avoid placeholder-only test additions.

### Project Structure Notes

- Keep outbox observability behavior centered in `outbox/` package.
- Keep policy schema enforcement in `contracts/` plus policy YAML in `config/policies/`.
- Keep test topology mirrored under `tests/unit/outbox/` and `tests/integration/`.

### References

- [Source: `artifact/planning-artifacts/epics.md` - Story 7.1 acceptance criteria]
- [Source: `artifact/planning-artifacts/prd/functional-requirements.md` - FR52, FR53, FR54]
- [Source: `artifact/planning-artifacts/prd/non-functional-requirements.md` - NFR-P1b, NFR-R4, NFR-O1, NFR-O2]
- [Source: `artifact/planning-artifacts/architecture.md` - Operability/monitoring architecture, outbox + health package boundaries]
- [Source: `artifact/project-context.md` - coding, testing, and cross-cutting enforcement rules]
- [Source: `src/aiops_triage_pipeline/outbox/worker.py` - existing backlog health + publish transition behavior]
- [Source: `src/aiops_triage_pipeline/outbox/repository.py` - backlog health query and state transition repository semantics]
- [Source: `src/aiops_triage_pipeline/outbox/metrics.py` - current outbox metrics baseline]
- [Source: `https://pypi.org/project/opentelemetry-sdk/` - package version context]
- [Source: `https://pypi.org/project/opentelemetry-exporter-otlp/` - package version context]

## Dev Agent Record

### Agent Model Used

GPT-5 (Codex)

### Debug Log References

- Story selected from `artifact/implementation-artifacts/sprint-status.yaml`: `7-1-outbox-health-monitoring-and-dead-0-posture`
- Epic 7 context extracted from `artifact/planning-artifacts/epics.md`
- Architecture + PRD + project context artifacts analyzed for FR/NFR traceability

### Completion Notes List

- Ultimate context engine analysis completed - comprehensive developer guide created.
- Story status set to `ready-for-dev` for implementation handoff.

### File List

- artifact/implementation-artifacts/7-1-outbox-health-monitoring-and-dead-0-posture.md
- artifact/implementation-artifacts/sprint-status.yaml
