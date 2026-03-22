# Story 3.3: Blast Radius & Downstream Impact Assessment

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a platform operator,
I want the system to compute blast radius classification and identify downstream components at risk,
so that responders understand the scope of impact when triaging an anomaly (FR11, FR12).

## Acceptance Criteria

1. **Given** an anomaly has been resolved to a stream with `topic_role`  
   **When** blast radius is computed  
   **Then** classification is either `LOCAL_SOURCE_INGESTION` or `SHARED_KAFKA_INGESTION` based on `topic_role` (FR11).
2. **And** downstream components are identified as `AT_RISK` with `exposure_type` in: `DOWNSTREAM_DATA_FRESHNESS_RISK`, `DIRECT_COMPONENT_RISK`, `VISIBILITY_ONLY` (FR12).
3. **And** blast radius and downstream impact outputs are available for inclusion in CaseFile and TriageExcerpt assembly paths.
4. **And** unit tests verify: classification for each supported topic role, downstream identification for each exposure type, and edge cases with no downstream components.

## Tasks / Subtasks

- [x] Task 1: Define typed blast-radius and downstream-impact models (AC: 1, 2, 3)
  - [x] Add immutable model(s)/literals for blast radius class, downstream risk status, and exposure type in a topology-owned module.
  - [x] Keep JSON-friendly, deterministic field names consistent with existing contract/model conventions.
  - [x] Ensure unresolved topology scopes can carry empty downstream impact without fabricated defaults.

- [x] Task 2: Implement deterministic blast-radius classification (AC: 1)
  - [x] Extend Stage 3 topology resolution path to derive blast radius from normalized `topic_role`.
  - [x] Keep mapping explicit and testable (no implicit fallthrough logic).
  - [x] Preserve Story 3.2 behavior and existing gate-input context fields.

- [x] Task 3: Implement downstream AT_RISK derivation (AC: 2)
  - [x] Derive at-risk components from canonical topology structures already loaded in-memory (`instances`, `sources`, `sinks`, `shared_components`).
  - [x] Emit deterministic `exposure_type` classification: `DOWNSTREAM_DATA_FRESHNESS_RISK`, `DIRECT_COMPONENT_RISK`, `VISIBILITY_ONLY`.
  - [x] Return stable ordering for downstream component outputs to keep tests deterministic.

- [x] Task 4: Make impact outputs consumable by later CaseFile/TriageExcerpt assembly (AC: 3)
  - [x] Expose blast-radius and downstream-impact fields from Stage 3 output object(s) without introducing Stage 4/5 side effects.
  - [x] Keep ready-to-consume shape for future `casefile.py` and excerpt assembly integration.
  - [x] Do not implement unrelated ownership routing chain logic (Story 3.4 scope).

- [x] Task 5: Add unit test coverage for Story 3.3 behavior (AC: 4)
  - [x] Extend/add `tests/unit/registry/test_resolver.py` for topic-role -> blast-radius mapping matrix.
  - [x] Extend/add `tests/unit/pipeline/stages/test_topology.py` for downstream component extraction + exposure types.
  - [x] Add no-downstream edge-case assertions and unresolved-scope safety assertions.

- [x] Task 6: Run quality gates
  - [x] `uv run pytest -q tests/unit/registry/test_resolver.py tests/unit/pipeline/stages/test_topology.py tests/unit/pipeline/test_scheduler_topology.py`
  - [x] `uv run pytest -q`
  - [x] `uv run ruff check`

## Dev Notes

### Story Requirements

- Story scope is FR11 + FR12 with explicit requirement that impact metadata is available to downstream CaseFile/TriageExcerpt assembly.
- This story builds directly on Story 3.2 outputs (`stream_id`, `topic_role`, `criticality_tier`, `source_system`) and should not duplicate resolver logic.
- Keep behavior deterministic and in-memory; topology registry remains the single source for blast-radius/downstream derivation.

### Developer Context Section

- Artifact discovery used for this context:
  - `epics_content`: `artifact/planning-artifacts/epics.md`
  - `architecture_content`: `artifact/planning-artifacts/architecture.md`
  - `prd_content`: `artifact/planning-artifacts/prd/functional-requirements.md`, `artifact/planning-artifacts/prd/non-functional-requirements.md`
  - `project_context`: `artifact/project-context.md`
  - `ux_content`: not found
- Current implementation baseline (important for Story 3.3):
  - `src/aiops_triage_pipeline/registry/resolver.py` resolves topology scope to stream/topic-role/tier with explicit unresolved semantics.
  - `src/aiops_triage_pipeline/pipeline/stages/topology.py` currently produces gate-input context + unresolved map only.
  - `src/aiops_triage_pipeline/pipeline/stages/casefile.py` and `src/aiops_triage_pipeline/pipeline/stages/outbox.py` are placeholders; Story 3.3 should provide consumable impact data without overreaching into those stages.
  - `src/aiops_triage_pipeline/contracts/triage_excerpt.py` currently has no blast-radius/downstream fields; design outputs to integrate cleanly later.

### Technical Requirements

- Implement blast-radius classification as a pure deterministic mapping from normalized topic role:
  - `SOURCE_TOPIC` -> `LOCAL_SOURCE_INGESTION`
  - `SHARED_TOPIC` -> `SHARED_KAFKA_INGESTION`
  - `SINK_TOPIC` -> `SHARED_KAFKA_INGESTION` (shared-path impact context, no source-local assumption)
- Implement downstream-at-risk identification from canonical topology data structures already loaded by registry loader.
- Exposure typing must only use allowed values:
  - `DOWNSTREAM_DATA_FRESHNESS_RISK`
  - `DIRECT_COMPONENT_RISK`
  - `VISIBILITY_ONLY`
- Keep unresolved behavior explicit: if topology scope is unresolved, do not fabricate blast/downstream outputs.
- Keep outputs stable-sorted by deterministic keys (e.g., component id/name) for reproducible tests and logs.
- Preserve NFR-P5 lookup discipline: no new runtime I/O in topology stage path.

### Architecture Compliance

- Topology and impact logic belongs to Stage 3/domain registry boundary (`registry/` + `pipeline/stages/topology.py`).
- Do not bypass existing immutable model discipline (`frozen=True` style models and mapping proxies where applicable).
- Keep hot-path deterministic and non-blocking; Story 3.3 must not introduce LLM/external dependency into path.
- Preserve cross-cutting controls:
  - structured logging with stable `event_type`
  - explicit unresolved diagnostics
  - no silent defaults that alter gating/triage behavior
- Ensure story output remains compatible with future Stage 4 CaseFile assembly and TriageExcerpt publication paths.

### Library / Framework Requirements

- Use existing pinned stack and project conventions:
  - Python 3.13 line, Ruff style/linting, pytest/pytest-asyncio test patterns.
  - Pydantic v2 immutable-model patterns for structured outputs.
- Reuse existing modules/utilities instead of introducing parallel patterns:
  - `registry.loader` canonical models
  - `registry.resolver` scope-resolution outputs
  - stage logging helper `get_logger`
- No new dependency should be required for Story 3.3.

### File Structure Requirements

- Primary implementation targets:
  - `src/aiops_triage_pipeline/registry/resolver.py`
  - `src/aiops_triage_pipeline/pipeline/stages/topology.py`
- Optional/refactor targets if needed for clarity (keep scope tight):
  - `src/aiops_triage_pipeline/registry/__init__.py`
  - `src/aiops_triage_pipeline/pipeline/stages/__init__.py`
- Test targets:
  - `tests/unit/registry/test_resolver.py`
  - `tests/unit/pipeline/stages/test_topology.py`
  - `tests/unit/pipeline/test_scheduler_topology.py` (only if stage-output integration contract changes)
- Out-of-scope in this story:
  - Ownership routing fallback chain implementation (Story 3.4)
  - Legacy v0 compatibility view surface work (Story 3.5)

### Testing Requirements

- Add/extend tests that prove:
  - blast-radius classification matrix per normalized topic role.
  - downstream AT_RISK derivation includes all three exposure types with deterministic ordering.
  - no-downstream case yields empty downstream list, not error.
  - unresolved topology scope keeps explicit unresolved outcome without fabricated impact metadata.
- Keep regression safety:
  - existing Story 3.2 resolver/topology tests remain green.
  - gating/scheduler tests remain green with no contract breakage.
- Validation commands:
  - `uv run pytest -q tests/unit/registry/test_resolver.py tests/unit/pipeline/stages/test_topology.py tests/unit/pipeline/test_scheduler_topology.py`
  - `uv run pytest -q`
  - `uv run ruff check`

### Previous Story Intelligence

- Story 3.2 established strict unresolved semantics and deterministic topology scope handling; keep that contract intact.
- Story 3.2 also ensured unresolved scopes are skipped safely before gate-input assembly in scheduler flow; Story 3.3 must preserve this safety behavior.
- Existing Stage 3 context already includes `source_system`; build on this context rather than duplicating data extraction paths.
- Reuse established patterns:
  - immutable typed outputs
  - explicit reason codes
  - deterministic ordering in tests

### Git Intelligence Summary

Recent commit intelligence (latest 5 commits):

- `24d6c01` finalized Story 3.2 review fixes; touched resolver/topology/scheduler and related tests.
- `47ce6ae` implemented topology loader canonicalization and validation foundations used by Story 3.3.
- `7a9eac8` and `9e00864` reinforce project-wide pattern: explicit degraded/UNKNOWN handling over implicit defaults.

Actionable guidance:

- Keep stage-local responsibilities and avoid cross-module coupling.
- Keep field naming and literal values contract-safe to avoid downstream breakage.
- Follow test-first/regression-safe workflow used in recent Epic 2/3 commits.

### Latest Tech Information

Verification date: **March 4, 2026**.

- **Python runtime line**
  - Python.org shows **Python 3.13.12** released on **February 3, 2026**.
  - Story implication: stay on Python 3.13 line for implementation/testing and avoid 3.14-only syntax/features.

- **SQLAlchemy / pytest / pydantic project lines**
  - Current project pins (`SQLAlchemy==2.0.47`, `pytest==9.0.2`, `pydantic==2.12.5`) remain aligned with the architecture baseline and recent project artifacts.
  - Story implication: no version migration is required for Story 3.3; focus on deterministic topology logic and tests.

- **Pydantic strict validation guidance**
  - Official docs continue to emphasize strict validation options for safer boundary handling.
  - Story implication: keep typed model boundaries explicit; avoid permissive coercions in new impact output models.

Inference from sources:
- No blocker-level ecosystem change was identified for this story; the implementation should proceed using the existing pinned stack.

### Project Context Reference

Relevant rules from `artifact/project-context.md`:

- Keep deterministic guardrails authoritative; no silent behavior drift.
- Keep models immutable by default and validate at boundaries.
- Reuse shared logging/correlation and health-safe patterns (no parallel framework creation).
- Add targeted tests with any behavior change; avoid placeholder-only coverage.
- Preserve safe defaults and avoid accidental widening of blast/action semantics.

### Story Completion Status

- Story context generation complete.
- Story file: `artifact/implementation-artifacts/3-3-blast-radius-and-downstream-impact-assessment.md`.
- Status: `done`.
- Completion note: **Implementation completed and senior code review fixes applied.**

## Project Structure Notes

- Story 3.3 should extend Stage 3 topology context without introducing coupling to unfinished Stage 4/5 implementation files.
- Keep impact outputs cleanly reusable by future CaseFile/TriageExcerpt assembly work.

## References

- [Source: `artifact/planning-artifacts/epics.md#Story 3.3: Blast Radius & Downstream Impact Assessment`]
- [Source: `artifact/planning-artifacts/prd/functional-requirements.md` (FR11, FR12)]
- [Source: `artifact/planning-artifacts/prd/non-functional-requirements.md` (NFR-P5)]
- [Source: `artifact/planning-artifacts/architecture.md` (Topology & Ownership, Stage 3 placement, immutable model patterns)]
- [Source: `artifact/project-context.md`]
- [Source: `artifact/implementation-artifacts/3-2-stream-resolution-and-topic-role-classification.md`]
- [Source: `src/aiops_triage_pipeline/registry/loader.py`]
- [Source: `src/aiops_triage_pipeline/registry/resolver.py`]
- [Source: `src/aiops_triage_pipeline/pipeline/stages/topology.py`]
- [Source: `src/aiops_triage_pipeline/contracts/triage_excerpt.py`]
- [Source: `https://www.python.org/downloads/release/python-31312/`]
- [Source: `https://pydantic.dev/articles/pydantic-v2-12-release`]
- [Source: `https://docs.pydantic.dev/latest/concepts/strict_mode/`]
- [Source: `https://pypi.org/project/SQLAlchemy/2.0.47/`]
- [Source: `https://pypi.org/project/pytest/9.0.2/`]

## Dev Agent Record

### Agent Model Used

GPT-5 Codex

### Debug Log References

- Workflow runner: `_bmad/core/tasks/workflow.xml` with config `_bmad/bmm/workflows/4-implementation/code-review/workflow.yaml`.
- Story selected from `artifact/implementation-artifacts/sprint-status.yaml` as the active `review` story.
- Discover-inputs protocol executed against planning artifacts and project-context.
- Previous story intelligence loaded from `artifact/implementation-artifacts/3-2-stream-resolution-and-topic-role-classification.md`.
- Git intelligence analyzed from latest 5 commits.
- Web research performed for latest technical specifics and validation date stamped.
- Validation task fallback: `_bmad/core/tasks/validate-workflow.xml` was not present in repository; manual checklist-aligned validation applied.
- Implemented Story 3.3 in resolver + topology stage with typed blast-radius/downstream models and deterministic derivations.
- Added `impact_by_scope` Stage 3 output shape for CaseFile/TriageExcerpt consumption paths.
- Executed quality gates:
  - `uv run pytest -q tests/unit/registry/test_resolver.py tests/unit/pipeline/stages/test_topology.py tests/unit/pipeline/test_scheduler_topology.py`
  - `uv run pytest -q`
  - `uv run ruff check`
- Senior code review follow-up:
  - Deduplicated repeated downstream impact entries for repeated topology source/sink rows.
  - Added regression coverage for downstream impact deduplication behavior.
  - Updated story metadata to remove stale `ready-for-dev` completion status.

### Completion Notes List

- Story 3.3 implementation context prepared with explicit scope boundaries and anti-pattern guardrails.
- Required acceptance criteria translated into concrete implementation/testing tasks.
- Architecture/project-context constraints translated into actionable developer guardrails.
- Added immutable resolver models and literals:
  - blast radius: `LOCAL_SOURCE_INGESTION` and `SHARED_KAFKA_INGESTION`
  - downstream impact risk status: `AT_RISK`
  - exposure types: `DOWNSTREAM_DATA_FRESHNESS_RISK`, `DIRECT_COMPONENT_RISK`, `VISIBILITY_ONLY`
- Implemented explicit topic-role -> blast-radius mapping and deterministic downstream impact derivation from canonical `sources`, `sinks`, and `shared_components`.
- Extended Stage 3 output with `impact_by_scope` while preserving existing gate-input context behavior and unresolved handling.
- Added/updated unit tests for blast radius matrix, exposure typing coverage, deterministic ordering, unresolved safety, no-downstream edge cases, and scheduler integration.
- Senior review fix: duplicate downstream impacts are now deduplicated by `(component_type, component_id, exposure_type, risk_status)`.
- Story status updated to `done`; sprint status transitioned to `done`.

### File List

- `artifact/implementation-artifacts/3-3-blast-radius-and-downstream-impact-assessment.md`
- `artifact/implementation-artifacts/sprint-status.yaml`
- `src/aiops_triage_pipeline/registry/resolver.py`
- `src/aiops_triage_pipeline/pipeline/stages/topology.py`
- `src/aiops_triage_pipeline/registry/__init__.py`
- `src/aiops_triage_pipeline/pipeline/stages/__init__.py`
- `tests/unit/registry/test_resolver.py`
- `tests/unit/pipeline/stages/test_topology.py`
- `tests/unit/pipeline/test_scheduler_topology.py`

### Senior Developer Review (AI)

- **Review date:** 2026-03-04
- **Outcome:** Changes Requested → Fixed
- **High findings fixed:**
  - Repeated topology entries could emit duplicate downstream impact records (`source` and `sink`) for the same component, which can inflate CaseFile/TriageExcerpt impact payloads.
  - Fix applied in `src/aiops_triage_pipeline/registry/resolver.py` by deduplicating downstream impacts before final ordering.
- **Medium findings fixed:**
  - Added regression coverage to lock deduplication behavior (`tests/unit/registry/test_resolver.py::test_resolve_anomaly_scope_deduplicates_repeated_downstream_components`).
  - Corrected stale story metadata that still claimed `ready-for-dev` in the completion section while the story was under implementation/review.
- **Low findings fixed:**
  - Corrected workflow/debug provenance in Dev Agent Record to reference the executed `code-review` workflow and review-driven story selection path.

### Change Log

- 2026-03-04: Implemented Story 3.3 blast-radius and downstream-impact Stage 3 outputs, added deterministic derivation logic, and expanded resolver/topology/scheduler tests.
- 2026-03-04: Applied senior developer review fixes: deduplicated repeated downstream impacts in resolver output, added dedup regression test coverage, and synchronized story status metadata to `done`.
- 2026-03-04: Low-severity documentation cleanup: corrected Dev Agent Record workflow/debug provenance to reflect code-review execution context.
