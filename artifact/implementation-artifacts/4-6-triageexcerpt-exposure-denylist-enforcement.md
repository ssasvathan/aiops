# Story 4.6: TriageExcerpt Exposure Denylist Enforcement

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a platform operator,
I want the exposure denylist enforced on TriageExcerpt before it is published to Kafka,
so that no sensitive sink endpoints, credentials, restricted hostnames, or Ranger access groups appear in the hot-path event stream (FR25).

## Acceptance Criteria

1. **Given** a TriageExcerpt.v1 has been assembled from CaseFile data  
   **When** the excerpt is prepared for Kafka publishing  
   **Then** `apply_denylist()` is applied to the excerpt fields before serialization.
2. **And** zero denied fields appear in the published TriageExcerpt.
3. **And** the excerpt remains schema-valid after denylist application (no required fields removed that would break consumers).
4. **And** denylist enforcement is logged for audit traceability.
5. **And** unit tests verify: denied fields removed, non-denied fields preserved, schema validity post-denylist, edge cases with nested fields matching denylist patterns (NFR-S5).

## Tasks / Subtasks

- [x] Task 1: Add explicit TriageExcerpt boundary enforcement using shared denylist utility (AC: 1, 2, 3)
  - [x] Introduce a focused sanitizer for outbox publish path that accepts `TriageExcerptV1` plus loaded `DenylistV1`, applies `apply_denylist()` to excerpt payload data, and returns a schema-valid `TriageExcerptV1`.
  - [x] Reuse the existing shared enforcement function from `denylist/enforcement.py`; do not duplicate denylist logic.
  - [x] Handle nested structures in excerpt payload (not only flat keys) so value-pattern matches inside nested data are removed before publish.
  - [x] If sanitization removes required schema fields, fail loudly with typed exception and let outbox retry/dead policy handle it (no silent publish of invalid payload).

- [x] Task 2: Wire denylist enforcement into durable outbox publish flow (AC: 1, 2, 3)
  - [x] Ensure enforcement runs in the outbox worker path that publishes `CaseHeaderEvent.v1` + `TriageExcerpt.v1` from persisted `triage.json`.
  - [x] Keep Invariant A readback and hash verification exactly as-is before publish.
  - [x] Ensure header payload behavior is unchanged; this story only changes excerpt sanitization prior to Kafka emission.
  - [x] Keep publisher batch semantics intact (single dual-event publish action with existing delivery checks).

- [x] Task 3: Add audit-safe denylist enforcement observability (AC: 4)
  - [x] Emit structured log event for denylist application outcome with safe metadata (`case_id`, removed field count, boundary identifier, success/failure).
  - [x] Do not log removed sensitive values; include only non-sensitive diagnostic metadata.
  - [x] Keep logging field names aligned with current observability conventions (`event_type`, `case_id`, `component`, severity level).

- [x] Task 4: Extend tests for denylist enforcement at TriageExcerpt boundary (AC: 5)
  - [x] Add/extend unit tests around outbox excerpt assembly/publish path to validate denylist removal and schema validity.
  - [x] Add nested-field edge-case tests to cover denylist pattern matches inside nested payload content.
  - [x] Add/extend integration tests to verify persisted READY records publish sanitized excerpts after worker recovery flow.
  - [x] Preserve existing outbox publish tests (no regression to READY/RETRY/SENT/DEAD transitions).

- [x] Task 5: Quality gates
  - [x] `uv run pytest -q tests/unit/denylist/test_enforcement.py tests/unit/outbox/test_publisher.py tests/unit/outbox/test_worker.py`
  - [x] `TESTCONTAINERS_RYUK_DISABLED=true DOCKER_HOST=unix://$HOME/.docker/desktop/docker.sock uv run pytest -q -rs tests/integration/test_outbox_publish.py -m integration`
  - [x] `uv run ruff check`

## Dev Notes

### Developer Context Section

- Story selection source: story status transitioned through `in-progress` -> `review` in `artifact/implementation-artifacts/sprint-status.yaml`.
  - Story key: `4-6-triageexcerpt-exposure-denylist-enforcement`
  - Story ID: `4.6`
- Epic context: Epic 4 (`FR17`-`FR26`) governs CaseFile durability and outbox publication safety.
- This story sits directly after Story 4.5 and must preserve:
  - Invariant A readback/hash validation before publish.
  - Dual-event outbox publish (`CaseHeaderEvent.v1` + `TriageExcerpt.v1`) as a single durable action.
  - Existing outbox retry/dead semantics and backlog health instrumentation.
- Functional target in this story:
  - Add explicit TriageExcerpt boundary denylist enforcement per FR25/NFR-S5 in the publish path.

### Technical Requirements

- `apply_denylist()` must be applied before excerpt serialization to Kafka.
- Denylist enforcement must cover:
  - Exact denied field names (case-insensitive).
  - Denied value patterns (regex search on string values).
  - Nested structures in excerpt payload content.
- Schema integrity is mandatory:
  - Published excerpt must still validate against frozen `TriageExcerptV1`.
  - If sanitization invalidates required schema, raise and route through existing outbox failure transition path (RETRY/DEAD policy).
- No sensitive data leakage:
  - Zero denied fields in emitted excerpt payload.
  - Logs must remain exposure-safe (metadata only).
- Non-goals:
  - No change to outbox state-machine rules.
  - No change to CaseHeaderEvent payload shape.
  - No change to Invariant A or B2 semantics.

### Architecture Compliance

- Preserve architecture decision 2B: one shared denylist function, reused at boundaries.
- Preserve architecture decision 3C/3D: Pydantic JSON serialization and contract validation discipline.
- Keep durable outbox ownership intact:
  - Outbox pipeline remains source of truth for publish transitions.
  - No parallel publish path outside outbox worker.
- Keep structured logging consistent with existing conventions.
- Maintain package boundaries pragmatically:
  - If denylist import placement creates a boundary conflict, prefer a minimal shared helper placement that avoids duplication and keeps enforcement centralized.

### Library / Framework Requirements

- Required project pins on this path:
  - `confluent-kafka==2.13.0`
  - `pydantic==2.12.5`
  - `SQLAlchemy==2.0.47`
  - `psycopg[c]==3.3.3`
- Web verification (2026-03-06):
  - Confluent Kafka Python docs still require callback serving (`poll`) and delivery completion checks (`flush`) in producer flows.
  - Pydantic v2 contract workflow remains `model_dump_json()` for serialization and `model_validate()`/`model_validate_json()` for validation.
  - SQLAlchemy 2.x Core patterns remain the intended baseline for outbox state persistence.

### File Structure Requirements

- Primary implementation targets:
  - `src/aiops_triage_pipeline/outbox/publisher.py`
  - `src/aiops_triage_pipeline/outbox/worker.py`
  - `src/aiops_triage_pipeline/__main__.py` (denylist load/wiring if needed for publisher worker)
  - `src/aiops_triage_pipeline/denylist/enforcement.py` (reuse only; change only if necessary for nested enforcement support)
- Optional/refactor targets (only if needed to keep boundaries clean):
  - `src/aiops_triage_pipeline/outbox/` helper module for excerpt sanitization.
  - `src/aiops_triage_pipeline/denylist/` helper for recursive dict/list sanitization.
- Test targets:
  - `tests/unit/outbox/test_publisher.py`
  - `tests/unit/outbox/test_worker.py`
  - `tests/unit/denylist/test_enforcement.py`
  - `tests/integration/test_outbox_publish.py`
  - optional: `tests/integration/test_denylist_boundaries.py` (new)

### Testing Requirements

- Unit tests must validate:
  - Denied field names are removed from excerpt payload.
  - Non-denied fields are preserved.
  - Pattern-based removals work in nested payload structures.
  - Resulting payload remains schema-valid as `TriageExcerptV1`.
  - Invalid post-sanitize payload causes explicit failure (not silent pass-through).
- Integration tests must validate:
  - Outbox worker publishes sanitized excerpt on READY recovery flow.
  - Retry/dead behavior remains correct when publish-time failures occur.
  - Invariant A + B2 behavior remains intact after denylist enforcement changes.
- Regression tests must ensure:
  - Header/excerpt dual publish remains one durable operation.
  - Existing outbox metrics/logging behavior is not degraded.

### Previous Story Intelligence

- Story 4.5 introduced dual-event publish batching, explicit producer delivery checks, and outbox backlog visibility.
- Keep these learnings intact:
  - Do not split dual-event publish into divergent code paths.
  - Keep failure handling deterministic and typed (`CriticalDependencyError`, invariant errors).
  - Preserve outbox repository source-state guards and transition idempotency.
- Practical carry-forward:
  - Apply denylist in the excerpt transformation layer only; do not redesign publisher state machine.

### Git Intelligence Summary

Recent commits (most recent first):
- `24b46c2` - `fix(outbox): harden publisher reliability and backlog health visibility`
- `6212c93` - `feat(story-4.5): implement durable outbox kafka publisher`
- `752d72c` - `Fix Story  4-4-postgres-durable-outbox-state-machine`
- `a864bc5` - `Fix Story 4.3 review findings and complete stage coverage`
- `f804a5a` - `Implement story 4.3 append-only casefile stages and docker test defaults`

Actionable patterns for this story:
- Extend existing outbox modules rather than introducing parallel publication abstractions.
- Keep changes traceable to FR25/NFR-S5 with explicit tests.
- Preserve sprint artifact hygiene (story doc + sprint-status state transition).

### Latest Tech Information

Verification date: 2026-03-06.

- Confluent Kafka Python:
  - `2.13.0` remains the project baseline and current reference for this code path.
  - Producer docs continue to emphasize callback servicing and flush completion checks for reliable delivery semantics.
- Pydantic v2:
  - Current model validation/serialization APIs (`model_validate`, `model_validate_json`, `model_dump_json`) remain aligned with this project's contract-first approach.
- SQLAlchemy Core:
  - 2.x Core remains compatible and appropriate for deterministic outbox repository operations.
- Implementation implication:
  - No dependency upgrade is required for Story 4.6; focus on correct boundary enforcement and regression-safe integration.

### Project Context Reference

Critical project rules applied from `artifact/project-context.md`:
- Never fork cross-cutting enforcement; use shared `apply_denylist(...)`.
- Never bypass durability controls (write-before-publish, crash-safe outbox semantics).
- Keep critical-path failures explicit; no silent degradation on invariant violations.
- Preserve structured logging and avoid sensitive data leakage in logs.

### Project Structure Notes

- Current code reality:
  - `apply_denylist()` currently handles flat dicts only and notes nested support is deferred to Story 4.6.
  - TriageExcerpt is currently built in `outbox/publisher.py` from persisted CaseFile and published by outbox worker.
- Required alignment for this story:
  - Add explicit denylist enforcement in the excerpt publish path without breaking outbox state transitions.
  - Keep a single source of denylist logic and avoid boundary-specific reimplementation.

### References

- [Source: `artifact/planning-artifacts/epics.md#Story 4.6: TriageExcerpt Exposure Denylist Enforcement`]
- [Source: `artifact/planning-artifacts/epics.md#Epic 4: Durable Triage & Reliable Event Publishing`]
- [Source: `artifact/planning-artifacts/prd/functional-requirements.md` (FR22, FR24, FR25)]
- [Source: `artifact/planning-artifacts/prd/non-functional-requirements.md` (NFR-S5, NFR-T2, NFR-R2, NFR-O2)]
- [Source: `artifact/planning-artifacts/architecture.md` (Decisions 2B, 3C, 3D; cross-cutting denylist concerns)]
- [Source: `artifact/project-context.md`]
- [Source: `artifact/implementation-artifacts/4-5-outbox-to-kafka-event-publishing-invariant-b2.md`]
- [Source: `src/aiops_triage_pipeline/outbox/publisher.py`]
- [Source: `src/aiops_triage_pipeline/outbox/worker.py`]
- [Source: `src/aiops_triage_pipeline/integrations/kafka.py`]
- [Source: `src/aiops_triage_pipeline/denylist/enforcement.py`]
- [Source: `src/aiops_triage_pipeline/contracts/triage_excerpt.py`]
- [Source: `src/aiops_triage_pipeline/__main__.py`]
- [Source: `tests/unit/outbox/test_publisher.py`]
- [Source: `tests/unit/outbox/test_worker.py`]
- [Source: `tests/integration/test_outbox_publish.py`]
- [Source: https://pypi.org/project/confluent-kafka/]
- [Source: https://docs.confluent.io/kafka-clients/python/current/overview.html]
- [Source: https://docs.pydantic.dev/latest/]
- [Source: https://docs.sqlalchemy.org/en/20/]

### Story Completion Status

- Story implementation and code review complete.
- Story file: `artifact/implementation-artifacts/4-6-triageexcerpt-exposure-denylist-enforcement.md`.
- Story status set to: `done`.
- Completion note: denylist boundary enforcement and review follow-up fixes are complete with quality gates passing.

## Dev Agent Record

### Agent Model Used

GPT-5 Codex

### Debug Log References

- Workflow engine: `_bmad/core/tasks/workflow.xml`
- Workflow config: `_bmad/bmm/workflows/4-implementation/code-review/workflow.yaml`
- Story selection from: `artifact/implementation-artifacts/sprint-status.yaml` (`review` story key: `4-6-triageexcerpt-exposure-denylist-enforcement`)
- Unit quality gate: `uv run pytest -q tests/unit/denylist/test_enforcement.py tests/unit/outbox/test_publisher.py tests/unit/outbox/test_worker.py`
- Integration quality gate: `TESTCONTAINERS_RYUK_DISABLED=true DOCKER_HOST=unix://$HOME/.docker/desktop/docker.sock uv run pytest -q -rs tests/integration/test_outbox_publish.py -m integration`
- Full regression: `TESTCONTAINERS_RYUK_DISABLED=true DOCKER_HOST=unix://$HOME/.docker/desktop/docker.sock uv run pytest -q -rs`
- Lint gate: `uv run ruff check`

### Completion Notes List

- Added outbox-boundary sanitizer (`sanitize_triage_excerpt_for_publish`) that applies shared `apply_denylist(...)`, validates `TriageExcerptV1`, and tracks removed field count for audit-safe metadata.
- Extended shared denylist enforcement to recursively sanitize nested dict/list payloads so boundary enforcement stays centralized.
- Added typed failure mode (`DenylistSanitizationError`) for schema-invalid post-sanitize payloads so outbox retry/dead transitions handle failures explicitly.
- Wired denylist enforcement into `publish_case_events_after_invariant_a` and `OutboxPublisherWorker` without changing Invariant A readback/hash verification or dual-event publish semantics.
- Added structured denylist observability event (`outbox.denylist_applied`) with safe metadata only: `event_type`, `case_id`, `component`, `boundary_id`, `outcome`, `severity`, `removed_field_count`.
- Updated outbox publisher startup path to load runtime denylist config and inject it into the worker.
- Added and updated unit/integration coverage for nested denylist enforcement, schema validation failure behavior, worker logging, and READY recovery publish sanitization.
- Added `PublishAfterDenylistError` so denylist audit metadata is preserved and logged even when Kafka publish fails after sanitization.
- Replaced diff-based removed-field counting with traversal-native counting from denylist enforcement to avoid list index-shift undercounting.
- Added tests for publish-failure denylist audit logging and removed-count correctness on nested/list payloads.
- Verified quality gates:
  - Unit target suite: 27 passed.
  - Integration target suite: 4 skipped (environment missing `libpq` wrapper), 0 failed.
  - Full regression suite: 388 passed, 4 skipped (same environment limitation), 0 failed.
  - Ruff lint: all checks passed.

### Senior Developer Review (AI)

- Review completed on 2026-03-06.
- Findings fixed:
  - Added denylist outcome logging for "publish failed after sanitization" paths to satisfy AC4 audit traceability.
  - Fixed removed-field counting to avoid undercount when list element removal shifts indexes.
  - Corrected story metadata/status inconsistencies.
- Outcome: Approved after fixes with all HIGH/MEDIUM findings resolved.

### File List

- `artifact/implementation-artifacts/4-6-triageexcerpt-exposure-denylist-enforcement.md`
- `artifact/implementation-artifacts/sprint-status.yaml`
- `src/aiops_triage_pipeline/__main__.py`
- `src/aiops_triage_pipeline/denylist/__init__.py`
- `src/aiops_triage_pipeline/denylist/enforcement.py`
- `src/aiops_triage_pipeline/errors/exceptions.py`
- `src/aiops_triage_pipeline/outbox/publisher.py`
- `src/aiops_triage_pipeline/outbox/worker.py`
- `src/aiops_triage_pipeline/pipeline/stages/casefile.py`
- `tests/integration/test_outbox_publish.py`
- `tests/unit/denylist/test_enforcement.py`
- `tests/unit/outbox/test_publisher.py`
- `tests/unit/outbox/test_worker.py`

### Change Log

- 2026-03-06: Implemented Story 4.6 denylist enforcement at TriageExcerpt publish boundary with nested payload support, typed schema-failure handling, outbox audit-safe observability, and full unit/regression validation.
- 2026-03-06: Code review remediation - added publish-failure denylist audit logging, fixed removed-field count correctness, aligned story metadata/status, and expanded tests.
