# Story 3.3: Invoke LLM for All Cases with Enriched Prompt and Schema Validation

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As an operations responder,
I want every case to receive enriched diagnostic analysis,
so that follow-up troubleshooting starts with structured hypotheses and next checks.

**Implements:** FR39, FR40, FR41

## Acceptance Criteria

1. **Given** a cold-path case is ready for diagnosis
   **When** prompt construction runs
   **Then** prompt content includes full finding fields, topology/routing context, domain hints, and few-shot guidance
   **And** invocation is performed regardless of environment, tier, or sustained flag.

2. **Given** the LLM returns a response
   **When** diagnosis parsing executes
   **Then** output is validated against `DiagnosisReportV1`
   **And** invalid schema responses are treated as invocation failure conditions.

## Tasks / Subtasks

- [x] Task 1: Wire cold-path processor boundary to invoke diagnosis for every consumed case (AC: 1, 2)
  - [x] Replace the Story 3.2 stub log in `src/aiops_triage_pipeline/__main__.py:_cold_path_process_event()` with an invocation path that calls cold-path diagnosis for each event after context retrieval + evidence summary.
  - [x] Keep message processing deterministic and sequential per D6: process one message at a time in `_cold_path_consumer_loop()`; no fan-out/background eligibility gating for this story.
  - [x] Build and pass required dependencies at composition root (`_run_cold_path()`): `LLMClient`, denylist, health registry, object store client, timeout configuration, and alert evaluator.
  - [x] Preserve consumer loop resilience pattern: per-message failures log structured warnings and continue; do not crash loop on case-level diagnosis failures.

- [x] Task 2: Enforce FR39 "all cases" invocation semantics (AC: 1)
  - [x] Remove or bypass current eligibility filtering (`prod + TIER_0 + sustained`) so diagnosis invocation is no longer constrained by environment/tier/sustained predicates.
  - [x] If `spawn_cold_path_diagnosis_task()` remains, ensure its behavior and tests reflect all-case invocation (or remove it and keep direct awaited invocation only).
  - [x] Update any stale comments/docs in code that still claim eligibility criteria apply.

- [x] Task 3: Enrich prompt content to satisfy FR40 requirements (AC: 1)
  - [x] Update `src/aiops_triage_pipeline/diagnosis/prompt.py:build_llm_prompt()` to include all `Finding` fields explicitly: `finding_id`, `name`, `severity`, `reason_codes`, `evidence_required`, `is_primary`, `is_anomalous`.
  - [x] Ensure prompt includes topology/routing context already in `TriageExcerptV1` (`topic_role`, `routing_key`) and clear anomaly family domain hints.
  - [x] Add explicit confidence calibration guidance and fault-domain examples in system instruction block.
  - [x] Add a deterministic few-shot example section (single canonical example) to improve consistency without introducing dynamic/non-deterministic prompt sections.

- [x] Task 4: Keep schema-validation failure handling explicit and deterministic (AC: 2)
  - [x] Ensure invalid/malformed LLM responses consistently map to schema-invalid failure handling (`LLM_SCHEMA_INVALID`) at the cold-path diagnosis boundary.
  - [x] Verify schema validation is always performed through `DiagnosisReportV1.model_validate(...)` before persistence/return.
  - [x] Preserve existing invariant handling separation: schema-invalid is invocation-failure class; non-LLM persistence failures still fail loud.

- [x] Task 5: Extend unit and integration coverage for story behavior (AC: 1, 2)
  - [x] Update `tests/unit/test_main.py` to assert `_cold_path_process_event()` performs diagnosis invocation after context retrieval/summary.
  - [x] Add/adjust tests proving invocation happens for non-prod and non-TIER_0/non-sustained cases (FR39 all-cases semantics).
  - [x] Update `tests/unit/diagnosis/test_prompt.py` with assertions for enriched fields (full finding attributes, topic_role, routing_key, domain hints, confidence guidance, few-shot block).
  - [x] Update `tests/unit/diagnosis/test_graph.py` to remove now-invalid eligibility assumptions and validate all-case invocation path.
  - [x] Update `tests/unit/integrations/test_llm.py` where needed to keep live-mode prompt/body and schema-parse expectations aligned.

- [x] Task 6: Documentation and operator guidance updates
  - [x] Update `docs/runtime-modes.md` cold-path section to document all-case invocation semantics and enriched prompt behavior.
  - [x] Update `docs/local-development.md` for local/mock diagnosis expectations (all cases invoked; LOG/MOCK/LIVE behavior unchanged by env/tier).

## Dev Notes

### Developer Context Section

- Story 3.2 already completed context reconstruction and deterministic evidence summary; this story starts from the existing `_cold_path_process_event()` boundary where diagnosis invocation is intentionally stubbed.
- The current codebase already contains diagnosis orchestration logic in `diagnosis/graph.py`, including prompt building, schema validation, and fallback behavior. The primary delta for this story is wiring + invocation semantics + prompt enrichment (not greenfield diagnosis architecture).
- **Critical conflict to resolve:** `meets_invocation_criteria()` currently enforces `prod + TIER_0 + sustained` gating, which conflicts with FR39. Story 3.3 must align behavior to invoke for every case.
- Keep scope tight to FR39-41:
  - implement all-case invocation and enriched prompt construction,
  - keep schema-validation failure handling explicit,
  - avoid introducing unrelated refactors to hot-path, outbox, or storage invariants.
- Do not regress existing Story 3.2 behavior (context retrieval failure and evidence summary failure must continue to skip case and continue loop).

### Technical Requirements

- FR39: invoke diagnosis for every cold-path case, independent of env/tier/sustained.
- FR40: enriched prompt must include complete finding semantics and routing/topology context with guidance (domain hints, confidence calibration, fault-domain examples, few-shot).
- FR41: LLM output must be schema-validated against `DiagnosisReportV1`; invalid schema must be treated as invocation failure.
- NFR-P4: cold-path LLM invocation timeout remains capped at 60 seconds.
- NFR-S2: denylist enforcement remains applied at outbound boundary handling (existing graph path sanitization must remain intact).
- NFR-R8 alignment: schema-invalid and invocation failures remain explicit and observable.

### Architecture Compliance

- D6 compliance is mandatory:
  - cold-path remains sequential poll-process-commit,
  - no eligibility criteria constraints for invocation at this stage,
  - consumer loop continues on per-message failure.
- D9 remains authoritative for evidence summary generation; this story consumes summary output and must not weaken deterministic summary assumptions.
- Composition-root wiring remains in `__main__.py`; avoid module-level singletons for new dependencies.
- Maintain package boundaries from `project-structure-boundaries.md`:
  - cold-path entry in `__main__.py`, diagnosis logic in `diagnosis/`, integration boundary in `integrations/llm.py`, storage boundary in `storage/`.

### Library / Framework Requirements

- Repository-pinned stack for this workstream:
  - `langgraph==1.0.9` (project pin)
  - `pydantic==2.12.5`
  - `pydantic-settings~=2.13.1`
  - `structlog==25.5.0`
  - `pytest==9.0.2`
  - `httpx` (as used by `integrations/llm.py`)
- Keep schema validation via Pydantic v2 `model_validate` / `model_validate_json` patterns at I/O boundaries.
- Do not add new LLM framework dependencies; extend existing prompt + graph + client flow only.

### File Structure Requirements

Primary implementation files:
- `src/aiops_triage_pipeline/__main__.py`
- `src/aiops_triage_pipeline/diagnosis/prompt.py`
- `src/aiops_triage_pipeline/diagnosis/graph.py`
- `src/aiops_triage_pipeline/integrations/llm.py` (only if needed for schema-failure mapping clarity)

Primary test files:
- `tests/unit/test_main.py`
- `tests/unit/diagnosis/test_prompt.py`
- `tests/unit/diagnosis/test_graph.py`
- `tests/unit/integrations/test_llm.py`

Documentation files:
- `docs/runtime-modes.md`
- `docs/local-development.md`

### Testing Requirements

Unit tests must cover:
- `_cold_path_process_event()` invokes diagnosis path after successful context retrieval + summary.
- Invocation occurs for all-case variants (e.g., local env, TIER_1, sustained=False) without eligibility suppression.
- Prompt includes all required FR40 fields and guidance blocks (full finding fields, routing/topology context, confidence calibration, fault-domain examples, few-shot).
- Schema-invalid LLM response path maps deterministically to `LLM_SCHEMA_INVALID` handling.
- Consumer loop behavior remains resilient: case-level diagnosis failures do not terminate loop processing.

Integration/regression expectations:
- Existing cold-path integration tests continue passing without regression.
- Full suite quality gate remains:
  - `uv run ruff check`
  - `TESTCONTAINERS_RYUK_DISABLED=true DOCKER_HOST=unix://$HOME/.docker/desktop/docker.sock uv run pytest -q -rs`
  - 0 skipped tests required.

### Previous Story Intelligence (Story 3.2)

- Story 3.2 established and validated the exact pre-invocation flow this story consumes:
  - `retrieve_case_context(case_id, object_store_client)`
  - `build_evidence_summary(triage_excerpt)`
- `_cold_path_process_event()` currently contains a deliberate Story 3.3 stub (`cold_path_context_ready`) and already applies continue-on-failure behavior for retrieval/summary exceptions.
- Dependency injection path for `object_store_client` was wired through `_run_cold_path()` and `_cold_path_consumer_loop()` in Story 3.2; preserve this style for additional diagnosis dependencies.
- Story 3.2 test baseline includes failure-path logging checks; extend this same style instead of adding parallel control-flow patterns.

### Git Intelligence Summary

Recent commit patterns (latest 5 commits) show consistent implementation conventions to reuse:
- Cold-path work is wired through `__main__.py` composition root and validated with focused unit tests (`tests/unit/test_main.py`) plus targeted integration coverage.
- Settings and runtime behavior changes include paired updates in docs and env/config artifacts.
- Story artifacts and `sprint-status.yaml` are updated as part of workflow completion, with traceability artifacts generated separately.
- Incremental commits favor low-risk deltas in existing files over broad package reorganization.

Actionable implication for Story 3.3:
- Implement by extending existing cold-path boundaries and tests in place; avoid introducing new orchestration layers or refactoring unrelated runtime modes.

### Latest Tech Information

External verification date: 2026-03-23.

- `langgraph` latest on PyPI is `1.1.3` (released 2026-03-18); project architecture currently pins `1.0.9`. Keep story scope on behavior changes, not dependency upgrades.
- `pydantic` latest on PyPI is `2.12.5` (released 2025-11-26), matching project pin.
- `pydantic-settings` latest on PyPI is `2.13.1` (released 2026-02-19), matching project compatible range.
- `structlog` latest on PyPI is `25.5.0` (released 2025-10-27), matching project pin.
- `pytest` latest on PyPI is `9.0.2` (released 2025-12-06), matching project pin.
- Pydantic docs continue to recommend `model_validate` / `model_validate_json` for validation at boundaries; use this as the canonical schema-check mechanism for diagnosis parsing.
- `httpx` latest stable on PyPI remains `0.28.1`; existing timeout/transport error handling paths in diagnosis graph remain aligned with current API surface.

### Project Context Reference

Applied `archive/project-context.md` rules to this story context:
- Keep hot/cold separation: cold-path diagnosis is advisory and must not alter deterministic gate authority.
- Preserve explicit UNKNOWN semantics and structured evidence usage in prompt/output handling.
- Use shared denylist enforcement and structured logging primitives; no parallel enforcement stack.
- Keep failure classification explicit: degradable/invocation failures stay observable, and invariant violations do not silently pass.
- Maintain contract-first boundaries and avoid ad-hoc schema drift outside `DiagnosisReportV1`.

### References

- [Source: `artifact/planning-artifacts/epics.md` — Epic 3 / Story 3.3]
- [Source: `artifact/planning-artifacts/prd/functional-requirements.md` — FR39, FR40, FR41]
- [Source: `artifact/planning-artifacts/prd/non-functional-requirements.md` — NFR-P4, NFR-S2, NFR-R8]
- [Source: `artifact/planning-artifacts/architecture/core-architectural-decisions.md` — D6, D9]
- [Source: `artifact/planning-artifacts/architecture/implementation-patterns-consistency-rules.md`]
- [Source: `artifact/planning-artifacts/architecture/project-structure-boundaries.md`]
- [Source: `archive/project-context.md`]
- [Source: `artifact/implementation-artifacts/3-2-reconstruct-case-context-and-build-deterministic-evidence-summary.md`]
- [Source: `src/aiops_triage_pipeline/__main__.py`]
- [Source: `src/aiops_triage_pipeline/diagnosis/graph.py`]
- [Source: `src/aiops_triage_pipeline/diagnosis/prompt.py`]
- [Source: `src/aiops_triage_pipeline/integrations/llm.py`]
- [Source: `src/aiops_triage_pipeline/contracts/diagnosis_report.py`]
- [Source: `https://pypi.org/project/langgraph/`]
- [Source: `https://pypi.org/project/pydantic/`]
- [Source: `https://pypi.org/project/pydantic-settings/`]
- [Source: `https://pypi.org/project/structlog/`]
- [Source: `https://pypi.org/project/pytest/`]
- [Source: `https://pypi.org/project/httpx/`]
- [Source: `https://docs.pydantic.dev/latest/concepts/models/`]

## Dev Agent Record

### Agent Model Used

gpt-5-codex

### Debug Log References

- create-story workflow execution (`bmad-bmm-create-story`) for explicit story key: `3-3-invoke-llm-for-all-cases-with-enriched-prompt-and-schema-validation`.
- Source analysis included sprint status, epics/PRD/architecture artifacts, previous story file, recent git history, and current cold-path code paths.
- `uv run ruff check`
- `uv run pytest -q tests/atdd/test_story_3_3_invoke_llm_for_all_cases_with_enriched_prompt_and_schema_validation_red_phase.py tests/unit/diagnosis/test_prompt.py tests/unit/diagnosis/test_graph.py tests/unit/test_main.py`
- `TESTCONTAINERS_RYUK_DISABLED=true DOCKER_HOST=unix://$HOME/.docker/desktop/docker.sock uv run pytest -q -rs`

### Completion Notes List

- Wired cold-path composition root to build and inject diagnosis dependencies (`LLMClient`, denylist, health registry, object store client, timeout, alert evaluator) into the sequential consumer path.
- Replaced `_cold_path_process_event()` diagnosis stub with deterministic in-line invocation via `run_cold_path_diagnosis()` and preserved fail-open per-message warning behavior.
- Updated `diagnosis/graph.py` all-case semantics: `meets_invocation_criteria()` now always returns `True`; spawn path now no longer applies env/tier/sustained gating.
- Enriched `build_llm_prompt()` with complete finding fields, `topic_role`/`routing_key`, confidence calibration guidance, fault-domain hints, and deterministic few-shot guidance.
- Updated unit and ATDD-aligned tests for all-case invocation semantics and prompt enrichment expectations.
- Updated operator docs for cold-path all-case invocation behavior and local LLM mode expectations.
- Full regression completed with zero skipped tests: `1042 passed`.
- Senior review fix: removed nested `asyncio.run()` invocation from the active cold-path event loop by introducing an async processor boundary that is awaited by the consumer loop.
- Senior review fix: diagnosis hash-chain linkage now uses the persisted `triage_hash` from validated context retrieval instead of deriving a surrogate hash from `case_id`.
- Senior review fix: aligned story/ATDD/unit test wiring with `retrieve_case_context_with_hash()` and added regression coverage for async processor boundary usage.

### File List

- `artifact/implementation-artifacts/3-3-invoke-llm-for-all-cases-with-enriched-prompt-and-schema-validation.md`
- `artifact/implementation-artifacts/sprint-status.yaml`
- `src/aiops_triage_pipeline/__main__.py`
- `src/aiops_triage_pipeline/diagnosis/context_retrieval.py`
- `src/aiops_triage_pipeline/diagnosis/graph.py`
- `src/aiops_triage_pipeline/diagnosis/prompt.py`
- `tests/unit/test_main.py`
- `tests/unit/diagnosis/test_graph.py`
- `tests/unit/diagnosis/test_prompt.py`
- `tests/unit/diagnosis/test_context_retrieval.py`
- `tests/unit/integrations/test_llm.py`
- `tests/atdd/test_story_3_3_invoke_llm_for_all_cases_with_enriched_prompt_and_schema_validation_red_phase.py`
- `tests/atdd/fixtures/story_3_3_test_data.py`
- `docs/runtime-modes.md`
- `docs/local-development.md`

## Senior Developer Review (AI)

### Outcome

- Decision: **Approve with fixes applied**

### Findings (All Resolved)

1. **Critical** — Cold-path diagnosis invocation used `asyncio.run()` inside an already-running event loop path (`_cold_path_consumer_loop()`), causing runtime failures and skipped diagnosis execution.
   - Fix: Introduced `_cold_path_process_event_async()` and made `_cold_path_consumer_loop()` await async message processing directly.

2. **High** — `triage_hash` sent to diagnosis persistence path was derived from `sha256(case_id)` instead of the persisted `triage.json` hash-chain value, breaking intended chain linkage semantics.
   - Fix: Added `retrieve_case_context_with_hash()` and threaded validated persisted `triage_hash` into diagnosis invocation.

3. **Low** — Story/test artifact context drift (stale RED-phase wording and missing file traceability entries for implemented/reviewed paths) reduced review auditability.
   - Fix: Updated unit/ATDD wiring tests and refreshed this story’s completion notes + file list.

### Verification

- `uv run ruff check src/aiops_triage_pipeline/__main__.py src/aiops_triage_pipeline/diagnosis/context_retrieval.py tests/unit/test_main.py tests/atdd/test_story_3_3_invoke_llm_for_all_cases_with_enriched_prompt_and_schema_validation_red_phase.py`
- `uv run pytest -q tests/unit/test_main.py tests/unit/diagnosis/test_graph.py tests/unit/diagnosis/test_prompt.py tests/unit/integrations/test_llm.py tests/atdd/test_story_3_3_invoke_llm_for_all_cases_with_enriched_prompt_and_schema_validation_red_phase.py`

## Change Log

- 2026-03-23: Senior code review performed and remediation applied for async invocation boundary correctness, persisted triage hash-chain propagation, and review artifact traceability updates.

## Story Completion Status

- Story status: `done`
- Completion note: Story 3.3 implementation and senior review remediation complete; acceptance criteria validated with focused lint/test regression after fixes.
