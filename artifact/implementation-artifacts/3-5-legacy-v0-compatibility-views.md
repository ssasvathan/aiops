# Story 3.5: Legacy v0 Compatibility Views

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a platform developer,
I want backward-compatible compatibility views for legacy consumers during v0 to v1 migration,
so that existing v0 consumers receive identical field values and types with no breaking changes during the transition (FR16).

## Acceptance Criteria

1. **Given** the topology registry has been loaded and canonicalized from either v0 or v1 format  
   **When** a legacy consumer requests data through the compat view  
   **Then** v0 schema fields are returned with identical values, types, and semantics as the original v0 format.
2. **And** no breaking changes exist in field names, types, or semantics for v0 consumers.
3. **And** compat views are derived from the canonical in-memory model (single source of truth, not a parallel data path).
4. **And** unit tests verify: v0 compat output matches expected v0 schema exactly, field-by-field comparison against reference v0 data.

## Tasks / Subtasks

- [x] Task 1: Define the v0 compatibility view contract and canonical projection API (AC: 1, 2, 3)
  - [x] Add a typed compatibility projection API under `registry` that returns v0-shaped output from `TopologyRegistrySnapshot`.
  - [x] Define deterministic scope behavior for instance-scoped registries (explicit `(env, cluster_id)` input; no ambiguous cross-scope merges).
  - [x] Ensure output values are deterministic and stable in ordering for repeatable consumer behavior and tests.

- [x] Task 2: Implement canonical-to-v0 projection logic (AC: 1, 2, 3)
  - [x] Build `streams[]` output with v0 field names/types (`stream_id`, `env`, optional stream metadata, `topics`, `sources`, `sinks`, `shared_components`).
  - [x] Build top-level `topic_index` projection exactly as expected by v0 consumers (`topic -> {role, stream_id, source_system?}`).
  - [x] Ensure projection uses only canonical in-memory model (`snapshot.registry`) and never re-parses raw YAML.

- [x] Task 3: Handle multi-instance and collision edge cases safely (AC: 1, 2)
  - [x] Define and implement behavior for streams/topics absent in requested scope (exclude cleanly, do not fabricate).
  - [x] Validate no cross-cluster leakage in compat output when same topic exists in different `(env, cluster_id)` scopes.
  - [x] Preserve fail-loud behavior for invalid scope requests (explicit error/unresolved status; no silent fallback).

- [x] Task 4: Expose the compatibility view through registry package boundaries (AC: 3)
  - [x] Export the new compatibility projection interface via `registry/__init__.py`.
  - [x] Keep resolver/stage behavior unchanged for existing hot-path flows.
  - [x] Keep module boundaries aligned with architecture ownership (`registry/` owns FR9-FR16).

- [x] Task 5: Add regression-focused test coverage for compat invariants (AC: 4)
  - [x] Golden test: v0 fixture -> canonicalize -> compat projection equals expected v0 schema field-by-field.
  - [x] Equivalence test: semantically equivalent v1 fixture -> canonicalize -> compat projection equals v0 golden output.
  - [x] Scope isolation test: same topic name in different clusters yields scope-correct compat output with no collisions.
  - [x] Negative tests for unsupported/missing scope selection and required-key/type preservation.

- [x] Task 6: Quality gates
  - [x] `uv run pytest -q tests/unit/registry/test_loader.py tests/unit/registry/test_resolver.py tests/unit/pipeline/stages/test_topology.py`
  - [x] `uv run pytest -q`
  - [x] `uv run ruff check`

### Review Follow-ups (AI)

- [x] [AI-Review][High] Validate `env`/`cluster_id` runtime types in `build_v0_compat_view(...)` and raise `TopologyRegistryCompatibilityError(category="invalid_scope")` instead of uncaught `AttributeError` for non-string inputs. [`src/aiops_triage_pipeline/registry/loader.py:675`]
- [x] [AI-Review][High] Preserve legacy list ordering for compat `sources`/`sinks`; removed compatibility-layer list re-sorting and preserved canonical instance order. [`src/aiops_triage_pipeline/registry/loader.py:611`]
- [x] [AI-Review][Medium] Add regression tests for non-string scope inputs (e.g., `None`, numeric) so invalid scope handling remains typed and fail-loud. [`tests/unit/registry/test_loader.py:698`]
- [x] [AI-Review][Medium] Reconcile story metadata and change accounting: status/completion notes updated and workspace-context note added for unrelated tracked/untracked artifacts. [`artifact/implementation-artifacts/3-5-legacy-v0-compatibility-views.md:303`]

## Dev Notes

### Story Requirements

- Story 3.5 implements FR16 and is the final Epic 3 migration-hardening step.
- Scope is backward-compatible v0 views only; do not re-implement FR10-FR15 behavior already delivered in Stories 3.1-3.4.
- The compat view is transitional for legacy consumers during v0->v1 migration (Phase 1A support; deprecation begins in later phases).

### Developer Context Section

- Artifact discovery context used:
  - `epics_content`: `artifact/planning-artifacts/epics.md`
  - `architecture_content`: `artifact/planning-artifacts/architecture.md`
  - `prd_content`: `artifact/planning-artifacts/prd/functional-requirements.md`, `artifact/planning-artifacts/prd/open-items-deferred-design-decisions.md`, `artifact/planning-artifacts/prd/innovation-novel-patterns.md`, `artifact/planning-artifacts/prd/glossary-terminology.md`, `artifact/planning-artifacts/prd/project-scoping-phased-development.md`
  - `project_context`: `artifact/project-context.md`
  - `ux_content`: not found
- Current implementation baseline:
  - `registry.loader` already canonicalizes both v0 and v1 into a shared immutable model.
  - `registry.resolver` and `pipeline/stages/topology` consume only canonical structures and enforce deterministic resolved/unresolved semantics.
  - There is no explicit v0 compatibility view API yet; this story should add it without introducing a parallel parse path.
- Key migration nuance:
  - v1 uses instance-scoped `topic_index` keyed by `(env, cluster_id)` while v0 shape is not instance-scoped.
  - Compat behavior must be explicit and deterministic to avoid cross-cluster collisions or ambiguous merges.

### Technical Requirements

- Implement a deterministic canonical-to-v0 projection function with explicit scope selection (`env`, `cluster_id`) for instance-scoped data.
- Output contract must preserve legacy v0 field names, value semantics, and primitive types:
  - top-level keys include `version`, `streams`, `topic_index`
  - `streams[]` contain legacy stream fields and scope-associated entries
  - `topic_index` values retain `role`, `stream_id`, and optional `source_system` semantics
- Projection must read from immutable canonical models only (`CanonicalTopologyRegistry`), never from raw YAML text or separate legacy-specific storage.
- Ordering must be stable and deterministic across runs (stream ordering, topic ordering, ownership-adjacent metadata ordering where applicable).
- Unknown/missing scope or incompatible projection conditions must fail loudly with typed/contextual errors, not silent defaults.
- No behavior regressions in existing resolver/stage paths:
  - topic resolution behavior unchanged
  - ownership routing chain unchanged
  - unresolved reason code taxonomy unchanged

### Architecture Compliance

- Keep FR9-FR16 ownership in `registry/` package as defined by architecture mapping.
- Enforce single-source-of-truth model:
  - canonical model remains authoritative
  - compatibility view is a derived projection only
  - no branch-specific legacy parsing pipeline
- Preserve instance-scoped safety invariants from Stories 3.1-3.4:
  - `(env, cluster_id)` scoping remains strict
  - no cross-cluster topic collisions
  - no mutable shared global state introduced
- Preserve deterministic and immutable design language used in current registry models and stage outputs.
- Do not leak compatibility concerns into unrelated boundaries (`pipeline/`, `diagnosis/`, `outbox/`) beyond consuming projected data where explicitly needed.

### Library / Framework Requirements

- Keep implementation compatible with project runtime baseline: Python >= 3.13.
- Reuse existing project stack and patterns; do not add new dependencies for compatibility projection logic.
- Maintain Pydantic v2 immutable-model discipline for any new typed outputs.
- If serialization helpers are needed, keep YAML handling safe (`yaml.safe_load` style behavior already enforced in loader path); no unsafe loaders.
- Keep structured logging through shared `structlog` utilities if adding projection diagnostics.
- Do not alter contract policy semantics in `TopologyRegistryLoaderRulesV1` unless explicitly required by story acceptance criteria.

### File Structure Requirements

- Primary implementation surface (expected):
  - `src/aiops_triage_pipeline/registry/loader.py` (compat projection from canonical model)
  - `src/aiops_triage_pipeline/registry/__init__.py` (public export for projection API)
- Optional extraction if complexity warrants (still under `registry/`):
  - `src/aiops_triage_pipeline/registry/compat.py` (projection-specific helpers)
- Primary tests:
  - `tests/unit/registry/test_loader.py` (v0/v1 canonical + compat projections)
  - `tests/unit/registry/test_resolver.py` (non-regression checks as needed)
  - `tests/unit/pipeline/stages/test_topology.py` (verify no Stage 3 regressions)
- Keep all compatibility-projection logic inside registry boundary; downstream stages consume results, not re-derive them.

### Testing Requirements

- Add explicit FR16 compatibility tests:
  - v0 input fixture round-trip to expected v0 compat structure.
  - v1 equivalent fixture projection to the exact same expected v0 compat structure.
  - Field-by-field checks on keys, value semantics, and Python primitive types.
- Add scope/collision tests:
  - multi-cluster same-topic scenarios must not collide in compat output.
  - wrong/missing scope selection returns explicit failure path.
- Add determinism tests:
  - projection output ordering stable across repeated calls.
  - no incidental map-order variance in generated compat structures.
- Preserve regression guarantees for existing paths:
  - `resolve_anomaly_scope` behavior remains unchanged.
  - Stage 3 topology context/impact/routing outputs remain unchanged.
- Required pre-review commands:
  - `uv run pytest -q tests/unit/registry/test_loader.py tests/unit/registry/test_resolver.py tests/unit/pipeline/stages/test_topology.py`
  - `uv run pytest -q`
  - `uv run ruff check`

### Previous Story Intelligence

- Story 3.4 established deterministic ownership routing outputs and strict unresolved semantics:
  - preserve reason-code discipline (`owner_not_found`, `routing_key_not_found`, etc.)
  - preserve deterministic lookup path diagnostics
  - avoid fabricated routing targets
- Story 3.3 reinforced additive Stage 3 evolution:
  - extend outputs without regressing existing `context_by_scope` behavior
  - maintain deterministic ordering and deduplication patterns
- Story 3.2/3.1 established scoping and canonicalization foundations:
  - `(env, cluster_id)` scoping is mandatory to prevent cross-cluster collisions
  - canonical model is already stable and immutable; compat views should be pure projections over this model
  - fail-fast validation and typed error reporting are established standards
- Implementation implication for Story 3.5:
  - deliver compatibility projection as an additive registry capability
  - do not alter topology resolution contract or scheduler behavior

### Git Intelligence Summary

Recent commit patterns relevant to this story:

- `e8f368a` `fix(story-3.3): dedupe downstream impacts and finalize review sync`
  - Reinforced deterministic output and non-regression expectations in Stage 3 + resolver tests.
- `24d6c01` `feat: finalize story 3.2 review fixes and validation hardening`
  - Hardened unresolved handling, scheduler/topology integration behavior, and loader validation paths.
- `47ce6ae` `feat(registry): implement topology loader v0/v1 with validations and reload`
  - Introduced canonical model and validation architecture that Story 3.5 should project from.

Actionable guidance:

- Keep changes localized to `registry` compatibility projection and tests.
- Follow recent Epic 3 pattern: deterministic outputs, explicit diagnostics, strict test coverage.
- Treat resolver/topology/scheduler behavior as regression-sensitive surfaces; verify they remain unchanged.

### Latest Tech Information

Verification date: **March 4, 2026**.

- **Python runtime line (official python.org)**
  - Latest Python 3 release page shows **Python 3.14.3** (released **February 3, 2026**).
  - Python 3.13 release page shows **Python 3.13.12** (released **February 3, 2026**).
  - Story implication: keep implementation fully Python 3.13-compatible for this repo baseline while avoiding dependence on 3.14-only syntax/features.

- **Pydantic**
  - PyPI lists **2.12.5** as latest stable.
  - Story implication: continue existing Pydantic v2 frozen-model patterns; no migration required in this story.

- **SQLAlchemy**
  - SQLAlchemy project page lists latest release **2.0.46** (released **January 21, 2026**).
  - Story implication: this compat-view story is registry/projection logic only; no ORM upgrade work is required.

- **pytest**
  - PyPI lists latest pytest **9.0.2** (released **December 6, 2025**).
  - Story implication: current test framework baseline remains valid.

- **Ruff**
  - PyPI lists latest Ruff **0.15.1** (released **November 3, 2025**).
  - Story implication: existing lint baseline remains suitable for this story.

- **PyYAML**
  - PyPI lists latest PyYAML **6.0.3** (released **September 25, 2025**).
  - Story implication: no parser-library change needed; keep safe-loading behavior and deterministic validation patterns.

Inference from sources:
- No blocker-level ecosystem change affects Story 3.5 scope; focus should stay on deterministic, tested canonical->v0 compatibility projection.

### Project Context Reference

Critical guardrails from `artifact/project-context.md` applied to this story:

- Keep schema/contract model discipline immutable (`frozen=True`) and validate at boundaries.
- Preserve deterministic guardrails and avoid silent fallbacks for critical-path data integrity.
- Keep `config` and policy loading patterns generic; avoid ad-hoc coupling.
- Reuse shared logging/error patterns and keep diagnostics structured.
- Keep changes local and traceable with adjacent targeted tests.
- For high-risk areas (contracts, gating-adjacent topology data, degraded behavior), require explicit regression verification before completion.

### Story Completion Status

- Story context generation complete.
- Story file: `artifact/implementation-artifacts/3-5-legacy-v0-compatibility-views.md`.
- Status: `done`.
- Completion note: **Senior code review follow-ups were fixed and verified with targeted + full quality gates.**

## Project Structure Notes

- Keep compatibility projection logic in `registry/` as a pure derivation from canonical state.
- Do not introduce dual-source behavior (canonical + separate legacy parse path).
- Keep Stage 3 consumers unchanged unless explicitly integrating a compat-view caller.

## References

- [Source: `artifact/planning-artifacts/epics.md#Story 3.5: Legacy v0 Compatibility Views`]
- [Source: `artifact/planning-artifacts/prd/functional-requirements.md` (FR16)]
- [Source: `artifact/planning-artifacts/prd/open-items-deferred-design-decisions.md` (DF-1)]
- [Source: `artifact/planning-artifacts/prd/glossary-terminology.md` (`compat views`, `topology-registry-loader-rules-v1`)]
- [Source: `artifact/planning-artifacts/prd/innovation-novel-patterns.md` (migration correctness guidance)]
- [Source: `artifact/planning-artifacts/prd/project-scoping-phased-development.md` (v0->v1 migration risk/cut-line)]
- [Source: `artifact/planning-artifacts/architecture.md` (FR9-FR16 mapping to `registry/`)]
- [Source: `artifact/project-context.md`]
- [Source: `artifact/implementation-artifacts/3-4-multi-level-ownership-routing.md`]
- [Source: `src/aiops_triage_pipeline/registry/loader.py`]
- [Source: `src/aiops_triage_pipeline/registry/resolver.py`]
- [Source: `src/aiops_triage_pipeline/pipeline/stages/topology.py`]
- [Source: `tests/unit/registry/test_loader.py`]
- [Source: `tests/unit/registry/test_resolver.py`]
- [Source: `tests/unit/pipeline/stages/test_topology.py`]
- [Source: `https://www.python.org/downloads/latest/python3/`]
- [Source: `https://www.python.org/downloads/release/python-31312/`]
- [Source: `https://github.com/pydantic/pydantic/releases`]
- [Source: `https://www.sqlalchemy.org/`]
- [Source: `https://pypi.org/project/pytest/`]
- [Source: `https://pypi.org/project/ruff/`]
- [Source: `https://pypi.org/project/PyYAML/`]

## Dev Agent Record

### Agent Model Used

GPT-5 Codex

### Debug Log References

- Workflow runner: `_bmad/core/tasks/workflow.xml` with config `_bmad/bmm/workflows/4-implementation/create-story/workflow.yaml`.
- Story selected by user input as `3-5-legacy-v0-compatibility-views`.
- Core context loaded from Epic 3 story definitions, FR16 requirements, architecture registry boundaries, current registry/resolver implementation, and prior Epic 3 story outcomes.
- Latest-technology verification completed on March 4, 2026 from official Python, SQLAlchemy, PyPI, and Pydantic release sources.
- Implemented `build_v0_compat_view(...)` with typed models (`V0CompatView`, `V0CompatStream`, `V0CompatTopicIndexEntry`) and `to_legacy_dict()` rendering.
- Added explicit `TopologyRegistryCompatibilityError` for invalid/missing scope failures with typed categories.
- Projection logic is canonical-only (`snapshot.registry`) with deterministic scope filtering, stream/topic ordering, and stable nested mapping serialization.
- Fixed review issues: explicit non-string scope handling in compat API, preserved legacy `sources`/`sinks` ordering semantics, and added non-string scope regression tests.
- Executed quality gates:
  - `uv run pytest -q tests/unit/registry/test_loader.py tests/unit/registry/test_resolver.py tests/unit/pipeline/stages/test_topology.py` (48 passed)
  - `uv run pytest -q` (306 passed)
  - `uv run ruff check` (passed)

### Completion Notes List

- Implemented FR16 legacy compatibility projection as a typed registry API and exported it from `registry/__init__.py`.
- Added fail-loud invalid/missing scope handling via `TopologyRegistryCompatibilityError` to avoid silent fallback behavior.
- Added regression-focused unit tests for golden v0 compatibility output, v1 equivalence, scope collision isolation, and negative scope/type cases.
- Verified no regressions in resolver/topology paths by running required targeted tests plus full suite and lint checks.
- Reconciled story status and review accounting after applying all AI-review follow-ups.

### Change Log

- 2026-03-04: Implemented Story 3.5 (legacy v0 compatibility views), added typed projection API and error model, expanded loader tests, and passed all required quality gates.
- 2026-03-04: Senior code review completed; 2 High and 2 Medium issues recorded under `Review Follow-ups (AI)` and story status returned to `in-progress`.
- 2026-03-04: Fixed all code review follow-ups (scope type handling, ordering semantics, regression tests) and set story status to `done`.

### File List

- `src/aiops_triage_pipeline/registry/loader.py`
- `src/aiops_triage_pipeline/registry/__init__.py`
- `tests/unit/registry/test_loader.py`
- `artifact/implementation-artifacts/3-5-legacy-v0-compatibility-views.md`
- `artifact/implementation-artifacts/sprint-status.yaml`
- Workspace note: `artifact/implementation-artifacts/4-1-casefile-triage-stage-assembly.md` exists as separate/unrelated story artifact and was not modified for Story 3.5.
