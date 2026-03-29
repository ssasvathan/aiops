# Story 2.3: Publish READY Outbox Rows with Concurrency Safety

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As an SRE/platform engineer,
I want concurrent outbox publishers to drain READY rows safely,
so that Kafka publication is at-least-once without duplicate batch claims.

**Implements:** FR28, FR29

## Acceptance Criteria

1. **Given** multiple publisher instances are running
   **When** they select READY rows
   **Then** selection uses row-level locking with `FOR UPDATE SKIP LOCKED`
   **And** one row batch is claimed by only one publisher process.

2. **Given** a claimed READY row is processed
   **When** publication to Kafka succeeds or fails
   **Then** row state is updated consistently with at-least-once guarantees
   **And** transient failures do not block hot-path processing.

## Tasks / Subtasks

- [x] Task 1: Add `FOR UPDATE SKIP LOCKED` to `select_publishable` in `OutboxSqlRepository` (AC: 1)
  - [x] Confirm `select_publishable` in `outbox/repository.py` adds `.with_for_update(skip_locked=True)` to the SQLAlchemy `select()` statement — this is the one-line change described in D7.
  - [x] Confirm the change does NOT alter any other query (transitions, health snapshot, cleanup) — only the publishable selection query is modified.
  - [x] Confirm the existing `order_by(updated_at.asc())` and `limit(limit)` clauses are preserved — SKIP LOCKED batches are ordered oldest-first within the claimed set.
  - [x] Confirm SQLite unit tests still pass — SQLite does not support `FOR UPDATE`, but SQLAlchemy silently drops the clause for SQLite engines, so no test-specific workaround is needed.

- [x] Task 2: Verify `OutboxPublisherWorker.run_once` at-least-once publish lifecycle (AC: 1, 2)
  - [x] Confirm `run_once` calls `select_publishable` → `publish_case_events_after_invariant_a` → `transition_to_sent` for each successful publish — this is the at-least-once delivery path (Invariant B2).
  - [x] Confirm `run_once` calls `transition_publish_failure` on any exception from `publish_case_events_after_invariant_a` — failure does not leave the row in READY indefinitely.
  - [x] Confirm the per-record exception handler uses `except Exception` with `# noqa: BLE001` — any Kafka, S3, or denylist failure is caught and the row transitions to RETRY or DEAD without crashing the loop.
  - [x] Confirm `transition_publish_failure` uses the `OutboxPolicyV1` to resolve `max_retry_attempts` by `app_env`, eventually moving rows from RETRY to DEAD after exhausting retries.

- [x] Task 3: Verify `publish_case_events_after_invariant_a` enforces Invariant A before Kafka emission (AC: 2)
  - [x] Confirm `publish_case_events_after_invariant_a` in `outbox/publisher.py` raises `InvariantViolation` if `outbox_record.status` is not `READY` or `RETRY` — status guard prevents stale row re-publication.
  - [x] Confirm `_readback_casefile_for_outbox_record` reads `casefile_object_path` from object store and validates `case_id` and `triage_hash` against the outbox record — Invariant A enforced before every Kafka publish.
  - [x] Confirm `build_outbox_case_events` builds both `CaseHeaderEventV1` and `TriageExcerptV1` from the persisted `CaseFileTriageV1` — dual-event publication as specified in FR28.
  - [x] Confirm `sanitize_triage_excerpt_for_publish` applies shared denylist enforcement and re-validates the sanitized payload against `TriageExcerptV1` schema before `publish_case_events` is called — FR35 denylist enforcement at publish boundary.

- [x] Task 4: Verify `transition_to_sent` and `transition_publish_failure` use source-state SQL guards (AC: 2)
  - [x] Confirm `transition_to_sent` in `repository.py` passes `expected_source_statuses={current.status}` to `_write_transition` — the SQL `UPDATE WHERE status IN (...)` guard prevents double-transition if a concurrent worker already sent the row.
  - [x] Confirm `transition_to_sent` idempotency: if `current.status == "SENT"` it returns immediately without executing the UPDATE — prevents unnecessary DB round-trips on duplicate callbacks.
  - [x] Confirm `transition_publish_failure` passes `expected_source_statuses={current.status}` to `_write_transition` — idempotent on already-DEAD rows (`if current.status == "DEAD": return current`).
  - [x] Confirm `mark_outbox_record_sent` raises `InvariantViolation` if source status is not `READY` or `RETRY` — in-memory defence-in-depth before the SQL guard.
  - [x] Confirm `mark_outbox_record_publish_failure` raises `InvariantViolation` if source status is not `READY` or `RETRY` — in-memory defence-in-depth before the SQL guard.

- [x] Task 5: Verify `OutboxPublisherWorker` backlog health and SLO telemetry (AC: 2)
  - [x] Confirm `_emit_backlog_health_logs` calls `select_backlog_health` and emits structured log at appropriate severity level (info/warning/critical) based on `OutboxPolicyV1` state-age thresholds.
  - [x] Confirm `record_outbox_health_snapshot`, `record_outbox_publish_latency`, `record_outbox_publish_outcome`, and `record_outbox_delivery_slo_breach` are called at correct points in `run_once` — OTLP counters and histograms populated per publish cycle.
  - [x] Confirm `_evaluate_delivery_slo` computes p95/p99 from the rolling `_delivery_latency_samples_seconds` window (max 1000 samples) using `_nearest_rank_percentile` and emits threshold breach logs/counters when SLO is exceeded.
  - [x] Confirm `record_outbox_delivery_slo_breach` and `record_outbox_publish_outcome` are defined in `outbox/metrics.py` and use the `aiops.outbox.*` metric namespace — no inline metric definitions in `worker.py`.

- [x] Task 6: Verify `OutboxPublisherWorker` wiring and `OutboxRepositoryPublishProtocol` completeness (AC: 1, 2)
  - [x] Confirm `OutboxRepositoryPublishProtocol` in `worker.py` declares exactly the methods `worker.py` calls: `select_publishable`, `transition_to_sent`, `transition_publish_failure`, `select_backlog_health`.
  - [x] Confirm `OutboxSqlRepository` satisfies `OutboxRepositoryPublishProtocol` structurally — it implements all four methods with matching signatures.
  - [x] Confirm `OutboxPublisherWorker.__init__` raises `ValueError` for `batch_size <= 0` and `poll_interval_seconds <= 0` — invalid configuration caught at construction time.
  - [x] Confirm `run_forever` calls `run_once` → `time.sleep(poll_interval_seconds)` in a loop — publisher runs continuously without busy-polling.

- [x] Task 7: Add/expand unit tests to cover `select_publishable` SKIP LOCKED path and end-to-end publish lifecycle (AC: 1, 2)
  - [x] Add unit tests to `tests/unit/outbox/test_repository.py` verifying:
    - `select_publishable` returns READY rows ordered by `updated_at` ascending.
    - `select_publishable` returns RETRY rows where `next_attempt_at` is None or <= now.
    - `select_publishable` excludes RETRY rows where `next_attempt_at` > now.
    - `select_publishable` respects the `limit` parameter.
    - `transition_to_sent` succeeds from READY status.
    - `transition_to_sent` succeeds from RETRY status.
    - `transition_to_sent` is idempotent when already SENT.
    - `transition_publish_failure` transitions READY to RETRY on first failure.
    - `transition_publish_failure` transitions RETRY to DEAD when `max_retry_attempts` is exhausted.
  - [x] Verify existing worker tests in `tests/unit/outbox/test_worker.py` provide coverage for `run_once` success path, failure path, and SLO computation — do NOT modify existing passing tests.
  - [x] Run required quality gates:
    - [x] `uv run ruff check`
    - [x] `TESTCONTAINERS_RYUK_DISABLED=true DOCKER_HOST=unix://$HOME/.docker/desktop/docker.sock uv run pytest -q -rs`
  - [x] Confirm full regression result is `0 skipped`.

## Dev Notes

### Developer Context Section

- Story 2.3 is a **verification and hardening** story for the outbox publisher path. The core implementation (`outbox/worker.py`, `outbox/publisher.py`, `outbox/repository.py`, `outbox/state_machine.py`, `outbox/metrics.py`) is already in the codebase.
- **Key insight**: The primary net-new code change is adding `.with_for_update(skip_locked=True)` to `select_publishable` in `repository.py` (D7 — one-line change). The remainder of the story validates that the full publisher lifecycle (READY → SENT / READY → RETRY → DEAD) is correctly implemented with at-least-once guarantees and that the existing test coverage is sufficient or expanded.
- Do **not** reinvent the publisher machinery. Work within `outbox/worker.py`, `outbox/publisher.py`, `outbox/repository.py`, `outbox/state_machine.py`, `outbox/schema.py`, and `outbox/metrics.py`.
- The full state machine is: `PENDING_OBJECT → READY → SENT/RETRY → DEAD`. Story 2.3 covers the publisher's `READY → SENT/RETRY/DEAD` path (Stories 2.1 and 2.2 established the `PENDING_OBJECT → READY` path).
- **SKIP LOCKED in SQLAlchemy Core**: Use `.with_for_update(skip_locked=True)` chained on the `select()` statement in `select_publishable`. SQLAlchemy will translate this to `SELECT ... FOR UPDATE SKIP LOCKED` on Postgres and silently drop it for SQLite (unit tests use SQLite). No special test workaround needed.
- No UX artifact exists for this project. Backend event-driven pipeline only.

### Technical Requirements

- **FR28**: The outbox-publisher drains READY rows and publishes `CaseHeaderEventV1` and `TriageExcerptV1` to Kafka with at-least-once delivery (Invariant B2). Hot-path continues unaffected during Kafka unavailability — cases accumulate in Postgres.
- **FR29**: The outbox-publisher locks rows during selection to prevent concurrent publisher instances from publishing the same batch. Implemented by `SELECT FOR UPDATE SKIP LOCKED`.
- **NFR-R1**: DEAD outbox rows standing posture is 0. Any `DEAD` row triggers operational alerting via `_emit_dead_count_threshold_breach` in `OutboxPublisherWorker`.
- **NFR-R3**: Outbox guarantees at-least-once Kafka delivery — `transition_publish_failure` with retry-then-DEAD policy ensures eventual delivery or loud DEAD escalation.
- **NFR-SC3**: Outbox publisher supports concurrent instances with row locking preventing duplicate Kafka publication. Enforced by `SELECT FOR UPDATE SKIP LOCKED`.
- **NFR-P2**: Outbox delivery SLO: p95 <= 1 minute, p99 <= 5 minutes from READY to SENT. Monitored by `_evaluate_delivery_slo` in `OutboxPublisherWorker`.
- **NFR-S2**: Denylist enforcement applied at outbound boundary before Kafka payloads via `sanitize_triage_excerpt_for_publish`.
- **NFR-A1/A2**: Invariant A enforced before every Kafka publish via `_readback_casefile_for_outbox_record` — cannot publish without confirmed S3 artifact.

### Architecture Compliance

- **D7**: `SELECT FOR UPDATE SKIP LOCKED` is a one-line SQL change to `outbox/repository.py::select_publishable`. No schema changes, no new outbox status, no reaper process.
- `outbox/publisher.py` enforces Invariant A via `_readback_casefile_for_outbox_record`. Kafka publish only occurs after confirming `case_id` and `triage_hash` match the persisted casefile.
- The two-tier error handling in `OutboxPublisherWorker.run_once` follows the established pattern: per-record `except Exception` catch → `transition_publish_failure` → continue loop. The loop itself never halts for per-record errors.
- `outbox/worker.py` runtime mode: `outbox-publisher` pod (`__main__.py` → `outbox.worker.run()`). Package dependencies: `outbox/`, `integrations/kafka`, `health/`. No imports from `pipeline/`, `cache/`, `coordination/`, or `rule_engine/`.
- All new dependencies wired in `__main__.py`. No module-level singletons.
- `OutboxRepositoryPublishProtocol` is the structural protocol in `worker.py` that decouples the worker from `OutboxSqlRepository` for unit testing. `OutboxSqlRepository` satisfies it structurally (no `implements` keyword needed).
- Metrics follow `aiops.outbox.*` namespace. All metric instruments defined in `outbox/metrics.py`, not inline in `worker.py`.

### Library / Framework Requirements

Locked versions from `pyproject.toml` (source of truth):
- Python >= 3.13
- pydantic == 2.12.5 (`frozen=True`; `model_copy(update={...})` for state transitions in `state_machine.py`)
- pydantic-settings ~= 2.13.1
- SQLAlchemy == 2.0.47 (Core only)
  - `.with_for_update(skip_locked=True)` is valid SQLAlchemy Core 2.x syntax
  - SQLite drops `FOR UPDATE` silently — unit tests work without special flags
  - `RETURNING` clause used in `_write_transition`, `insert_pending_object`
- psycopg[c] == 3.3.3 (Postgres driver — integration tests only)
- confluent-kafka == 2.13.0 — publish via `CaseEventPublisherProtocol.publish_case_events`
- structlog == 25.5.0
- pytest == 9.0.2
- ruff ~= 0.15

Unit tests use **SQLite in-memory** (`create_engine("sqlite+pysqlite:///:memory:")`) — no Docker/Postgres required for unit coverage. SQLite ignores `FOR UPDATE SKIP LOCKED` transparently; Postgres enforces it in integration/production.

Do not upgrade dependencies in this story unless required for FR28/FR29 correctness or a security response.

### File Structure Requirements

Primary change target (minimal change expected — one-line SQL modification):
- `src/aiops_triage_pipeline/outbox/repository.py` — `OutboxSqlRepository.select_publishable`: add `.with_for_update(skip_locked=True)` to the `select()` statement

Primary verification targets (no changes expected unless gaps found):
- `src/aiops_triage_pipeline/outbox/worker.py` — `OutboxPublisherWorker`: `run_once`, `run_forever`, `_emit_backlog_health_logs`, `_evaluate_delivery_slo`
- `src/aiops_triage_pipeline/outbox/publisher.py` — `publish_case_events_after_invariant_a`, `build_outbox_case_events`, `sanitize_triage_excerpt_for_publish`, `_readback_casefile_for_outbox_record`
- `src/aiops_triage_pipeline/outbox/state_machine.py` — `mark_outbox_record_sent`, `mark_outbox_record_publish_failure`, `compute_retry_delay_seconds`, `resolve_max_retry_attempts`
- `src/aiops_triage_pipeline/outbox/metrics.py` — `record_outbox_publish_outcome`, `record_outbox_publish_latency`, `record_outbox_delivery_slo_breach`, `record_outbox_health_snapshot`

Primary test targets (add functions — do NOT modify existing passing tests):
- `tests/unit/outbox/test_repository.py` — add `select_publishable`, `transition_to_sent`, `transition_publish_failure` coverage
- `tests/unit/outbox/test_worker.py` — verify existing `run_once` success/failure path coverage (extend if gaps found)

Do not create new packages. All changes are localized to existing `outbox/` and test files.

### Testing Requirements

Test patterns follow the established project conventions:
- Test names: `test_{action}_{condition}_{expected}` format.
- Unit test doubles: per-file, dict-backed or SQLite-in-memory. No shared fake infrastructure.
- Use `create_engine("sqlite+pysqlite:///:memory:")` + `create_outbox_table(engine)` for repository unit tests.

Required test coverage additions:

**Repository tests (`test_repository.py`):**
- `test_select_publishable_returns_ready_rows_ordered_by_updated_at` — ordering correctness
- `test_select_publishable_returns_retry_rows_when_next_attempt_at_is_none` — retry eligibility
- `test_select_publishable_returns_retry_rows_when_next_attempt_at_is_past` — retry eligibility with timestamp
- `test_select_publishable_excludes_retry_rows_when_next_attempt_at_is_future` — retry gating
- `test_select_publishable_respects_limit_parameter` — batch size control
- `test_transition_to_sent_succeeds_from_ready` — positive transition
- `test_transition_to_sent_succeeds_from_retry` — retry recovery path
- `test_transition_to_sent_is_idempotent_when_already_sent` — idempotent safety
- `test_transition_publish_failure_transitions_ready_to_retry_on_first_failure` — retry creation
- `test_transition_publish_failure_transitions_retry_to_dead_when_attempts_exhausted` — DEAD escalation

Required quality commands:
- `uv run ruff check`
- `TESTCONTAINERS_RYUK_DISABLED=true DOCKER_HOST=unix://$HOME/.docker/desktop/docker.sock uv run pytest -q -rs`

Sprint gate requirement: 0 skipped tests. Current baseline is 904 passed, 0 skipped (from Story 2.2).

### Previous Story Intelligence

- **Story 2.2 established** the PENDING_OBJECT → READY insertion path and confirmed the two-tier error handling pattern (`CriticalDependencyError` re-raised; `InvariantViolation` re-raised; all others wrapped via `_wrap_repo_exc`).
- **Story 2.2 confirmed** `_write_transition` is the authoritative SQL-level source-state guard for all transitions — used by `transition_to_ready`, `transition_to_sent`, and `transition_publish_failure`.
- **Story 2.2 confirmed** `OutboxRecordV1` field validators (`_validate_outbox_triage_hash`, `_validate_timestamp_order`) enforce invariants at model construction time — `model_copy(update=...)` is the correct pattern for state transitions.
- **Code quality discipline from 2.2:**
  - pytest test names follow `test_{action}_{condition}_{expected}` format.
  - `File List` in Dev Agent Record must be populated completely before marking done.
  - No shared fake infrastructure across unit test files — SQLite in-memory per test file for repository tests.
  - Exception chaining: all `raise self._wrap_repo_exc(exc)` calls use `from exc` — confirmed fixed in 2.2 review.
- **Review findings from 2.2 to apply to 2.3:**
  - C1 (from 2.2): Task subtasks must be explicitly present in test files — do not mark a test `[x]` without confirming the function exists by name.
  - L2 (from 2.2): Exception chaining (`from exc`) must be present for all `raise self._wrap_repo_exc(exc)` calls.
  - L3 (from 2.2): Remove stale docstrings that reference RED/FAIL state after implementation.
  - M1: File List must include all changed/added files.

### Git Intelligence Summary

Recent commit history (relevant):
- `7aa68be` — `bmad(epic-2/2-2-enforce-outbox-source-state-transitions): complete workflow and quality gates`
- `7d2f3e2` — `bmad(epic-2/2-1-write-triage-casefiles-with-hash-chain-and-policy-stamps): code review fixes, ATDD artifact, traceability report`
- `0c17da5` — `bmad(epic-2/2-1-write-triage-casefiles-with-hash-chain-and-policy-stamps): complete workflow and quality gates`

Actionable guidance:
- Keep Story 2.3 changes localized to `outbox/` package and its tests — no unrelated refactors.
- The `select_publishable` SKIP LOCKED change is the primary deliverable. All other tasks are verification.
- Commit message convention: `bmad(epic-2/2-3-publish-ready-outbox-rows-with-concurrency-safety): ...`
- The baseline after Story 2.2 was 904 passed, 0 skipped. Any regression from the current baseline is unacceptable.

### Latest Tech Information

External lookup date: 2026-03-22.
- **SQLAlchemy 2.0.47** (locked): `.with_for_update(skip_locked=True)` is the correct Core API for `SELECT FOR UPDATE SKIP LOCKED`. It chains on the `select()` construct and generates `FOR UPDATE SKIP LOCKED` on Postgres. On SQLite (unit tests), SQLAlchemy silently omits the `FOR UPDATE` clause — no special handling needed.
- **SQLite (unit tests)**: SQLite 3.x does not support `FOR UPDATE`. SQLAlchemy's dialect layer strips it automatically for `sqlite+pysqlite:///:memory:` engines. All unit tests continue to run without modification.
- **psycopg[c] 3.3.3** (locked): `SELECT FOR UPDATE SKIP LOCKED` is a standard Postgres 9.5+ feature. No version compatibility issues at Postgres 16.
- **confluent-kafka 2.13.0** (locked): `publish_case_events` is a synchronous call. Any Kafka unavailability raises an exception caught by `run_once`'s per-record `except Exception` handler.
- **pydantic 2.12.5** (locked): `model_copy(update={...})` for frozen model state transitions (confirmed pattern from state_machine.py).
- PyPI vulnerability metadata for checked packages reported 0 listed vulnerabilities at lookup time (2026-03-22).

### Project Context Reference

Applied `archive/project-context.md` constraints:
- Python 3.13 typing conventions (`X | None`, built-in generics, `Literal` for status types).
- All contract/data models use `BaseModel, frozen=True` with `model_copy(update=...)` for state transitions.
- Boundary validation: `OutboxRecordV1` field validators enforce invariants at model construction time.
- Structured logging: `get_logger("outbox.worker")` with `event_type`, `case_id`, `status`, `delivery_attempts` fields.
- `CriticalDependencyError` propagation for Postgres failures — repository never swallows these.
- Per-record `except Exception` in `run_once` catches publish failures and transitions rows; never halts the loop.
- Zero-skip test discipline enforced at sprint gate.
- No AI agent invents new abstractions — work within existing `outbox/` package boundaries.

### References

- [Source: `artifact/planning-artifacts/epics.md` — Epic 2, Story 2.3, FR28, FR29]
- [Source: `artifact/planning-artifacts/epics.md` — NFR-R1, NFR-R3, NFR-SC3, NFR-P2, NFR-S2, NFR-A1, NFR-A2]
- [Source: `artifact/planning-artifacts/architecture/core-architectural-decisions.md` — D7 (Outbox row locking: SELECT FOR UPDATE SKIP LOCKED)]
- [Source: `artifact/planning-artifacts/architecture/implementation-patterns-consistency-rules.md` — two-tier error handling, test patterns, OTLP metrics namespace]
- [Source: `artifact/planning-artifacts/architecture/project-structure-boundaries.md` — outbox/ package structure, outbox-publisher runtime mode boundaries]
- [Source: `artifact/implementation-artifacts/2-2-enforce-outbox-source-state-transitions.md`]
- [Source: `artifact/implementation-artifacts/sprint-status.yaml`]
- [Source: `src/aiops_triage_pipeline/outbox/repository.py`]
- [Source: `src/aiops_triage_pipeline/outbox/worker.py`]
- [Source: `src/aiops_triage_pipeline/outbox/publisher.py`]
- [Source: `src/aiops_triage_pipeline/outbox/state_machine.py`]
- [Source: `src/aiops_triage_pipeline/outbox/schema.py`]
- [Source: `src/aiops_triage_pipeline/outbox/metrics.py`]
- [Source: `config/policies/outbox-policy-v1.yaml`]
- [Source: `archive/project-context.md`]
- [Source: `tests/unit/outbox/test_repository.py`]
- [Source: `tests/unit/outbox/test_worker.py`]

## Dev Agent Record

### Agent Model Used

claude-sonnet-4-6

### Debug Log References

- Create-story workflow executed in YOLO/full-auto mode for explicit story key `2-3-publish-ready-outbox-rows-with-concurrency-safety`.
- Story context assembled from: epics.md (Epic 2, Story 2.3, FR28, FR29), architecture shards (core decisions D7, implementation patterns, project structure boundaries), previous story artifact (2-2), project-context.md, and direct source inspection of `outbox/repository.py`, `outbox/worker.py`, `outbox/publisher.py`, `outbox/state_machine.py`, `outbox/schema.py`, `outbox/metrics.py`, and existing outbox unit tests.
- Validate-workflow task dependency `_bmad/core/tasks/validate-workflow.xml` not present; checklist invocation skipped.

### Completion Notes List

- Story artifact created with status `ready-for-dev` and comprehensive outbox publisher concurrency-safety implementation guardrails.
- Sprint tracking status updated from `backlog` to `ready-for-dev` for Story 2.3.
- Key implementation insight: The primary net-new code change is `.with_for_update(skip_locked=True)` in `select_publishable` (D7 one-line change). The publisher, state machine, worker, and metrics machinery are already in the codebase; this story's primary value is adding the SKIP LOCKED concurrency guard and verifying the full READY → SENT/RETRY/DEAD publish lifecycle is correct.
- SQLAlchemy dialect transparently drops `FOR UPDATE` for SQLite (unit tests) — no test workaround needed.
- Implementation complete (2026-03-22): Added `.with_for_update(skip_locked=True)` to `select_publishable` in `OutboxSqlRepository`. Verified all Tasks 1–7 against existing codebase. Removed stale RED phase comment block from test file per Story 2.2 review learning L3. All 914 tests pass, 0 skipped. `ruff check` passes clean.

### File List

- `src/aiops_triage_pipeline/outbox/repository.py` — added `.with_for_update(skip_locked=True)` to `select_publishable` query (D7 one-line change); added `InvariantViolation` re-raise to `select_publishable` exception guard for pattern consistency
- `tests/unit/outbox/test_repository.py` — added 10 new test functions covering `select_publishable` and `transition_to_sent`/`transition_publish_failure` lifecycle paths
- `artifact/implementation-artifacts/sprint-status.yaml` — updated story status from `ready-for-dev` to `review`
- `artifact/test-artifacts/atdd-checklist-2-3-publish-ready-outbox-rows-with-concurrency-safety.md` — ATDD checklist artifact generated for story 2.3

### Change Log

- 2026-03-22: Added `SELECT FOR UPDATE SKIP LOCKED` to `OutboxSqlRepository.select_publishable` via `.with_for_update(skip_locked=True)` — implements FR29 (row-level locking for concurrent outbox publishers) as specified in D7. Added 10 new `select_publishable` / `transition_to_sent` / `transition_publish_failure` repository test functions. 914 tests pass, 0 skipped.
- 2026-03-22 (code review): Added `InvariantViolation` re-raise to `select_publishable` exception guard for pattern consistency with all other public repository methods. Updated File List to include `sprint-status.yaml` and ATDD checklist artifact.

## Story Completion Status

- Story status: `done`
- Completion note: All tasks complete. Primary change: `.with_for_update(skip_locked=True)` added to `select_publishable`. Full publisher lifecycle (READY → SENT/RETRY/DEAD), Invariant A enforcement, SLO telemetry, and protocol wiring all verified against existing codebase. Code review complete: 2 Medium findings (File List gaps) and 1 Low finding (exception guard pattern inconsistency) all fixed. Quality gates: `ruff check` clean, 914 passed 0 skipped.
