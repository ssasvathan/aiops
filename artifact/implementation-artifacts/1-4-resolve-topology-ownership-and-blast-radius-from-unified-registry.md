# Story 1.4: Resolve Topology, Ownership, and Blast Radius from Unified Registry

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As an on-call engineer,
I want topology and ownership resolution to be automatic and reloadable,
so that action routing and impact assessment are immediately available in each triage result.

**Implements:** FR12, FR13, FR14, FR15, FR16

## Acceptance Criteria

1. **Given** the topology registry file in `config/` uses the single supported format
   **When** the topology stage resolves a finding scope
   **Then** stream identity, topic role, and blast-radius classification are resolved for that scope
   **And** downstream impacted consumers are identified where applicable.

2. **Given** topology registry contents change on disk
   **When** the loader detects file change
   **Then** the hot-path reloads topology without process restart
   **And** ownership routing uses ordered fallback `consumer_group > topic > stream > platform default` with confidence scoring.

## Tasks / Subtasks

- [x] Task 1: Enforce unified topology-registry source-of-truth and single supported schema (AC: 1, 2)
  - [x] Define/verify canonical runtime file location as `config/topology-registry.yaml` and ensure hot-path startup wiring uses it via `TOPOLOGY_REGISTRY_PATH`.
  - [x] Remove legacy format ambiguity from loader contracts/rules for this story scope (single supported input format for runtime loading).
  - [x] Keep validation failures explicit and typed (`TopologyRegistryValidationError`) with actionable category/key context.

- [x] Task 2: Complete deterministic topology scope resolution and blast-radius enrichment (AC: 1)
  - [x] Resolve both supported scope shapes `(env, cluster_id, topic)` and `(env, cluster_id, group, topic)`.
  - [x] Ensure resolved output always includes stream identity, normalized topic role, criticality tier, and blast radius.
  - [x] Derive deterministic downstream impacts from source/sink/shared-component topology with stable ordering.

- [x] Task 3: Implement ordered ownership fallback with confidence-aware output (AC: 2)
  - [x] Enforce lookup precedence `consumer_group_owner -> topic_owner -> stream_default_owner -> platform_default`.
  - [x] Propagate chosen lookup level + routing target into Stage 3 output and downstream case assembly/dispatch.
  - [x] Include confidence metadata in resolution output path (or explicit rationale when absent) without breaking existing contracts.

- [x] Task 4: Harden runtime reload-on-change with last-known-good safety (AC: 2)
  - [x] Keep mtime-based reload checks in hot-path loop and swap snapshot atomically only on successful validation.
  - [x] On invalid reload input, retain last-known-good snapshot and emit structured warning with reason category.
  - [x] Add/confirm success logging for reload swaps and no-op behavior when source file is unchanged.

- [x] Task 5: Preserve Stage 3 to Stage 6/CaseFile integration invariants (AC: 1, 2)
  - [x] Ensure unresolved topology scopes are tracked explicitly and never fabricated into gate input context.
  - [x] Keep casefile topology context assembly strict (missing required topology context remains a loud failure).
  - [x] Preserve routing-context handoff into dispatch with deterministic fallback behavior for unresolved scopes.

- [x] Task 6: Expand topology-focused tests and run quality gates (AC: 1, 2)
  - [x] Extend loader tests for unified-format validation boundaries and reload behavior (including invalid reload preservation).
  - [x] Extend resolver/topology tests for fallback order, blast radius mapping, downstream impact determinism, and unresolved reasons.
  - [x] Add/extend scheduler/casefile/dispatch coverage where new ownership-confidence metadata flows through.
  - [x] Run lint and full regression with Docker-enabled pytest and **0 skipped tests**.

## Dev Notes

### Developer Context Section

- Story 1.4 is the topology/ownership context backbone for the rest of Epic 1 gate and dispatch behavior.
- Stage 3 output is consumed by Stage 4 gate-input assembly, CaseFile triage assembly, and Stage 7 dispatch routing; regressions here have broad blast radius.
- Existing code already contains substantial topology loader/resolver behavior and reload wiring; implementation should refine to the story scope instead of introducing parallel mechanisms.
- Keep this story tightly focused on topology context fidelity and reload safety; do not expand scope into cold-path or unrelated rule-engine changes.

### Technical Requirements

- FR12: Load topology registry from a single YAML format located in `config/`.
- FR13: Resolve stream identity, topic role, and blast radius per scope.
- FR14: Enforce ordered ownership routing fallback from consumer-group to platform default.
- FR15: Reload topology on file change without process restart.
- FR16: Identify downstream consumer/component impact for blast-radius assessment.
- NFR-SC1/NFR-SC4: Behavior must remain consistent across hot/hot replicas and shared Redis-backed orchestration assumptions.
- NFR-R6/NFR-R7: Validation/invariant failures are loud where critical; degradable runtime conditions preserve safe continuity.

### Architecture Compliance

- D10: Apply topology simplification intent (single supported topology format; no runtime format negotiation path).
- D2/D3: Preserve degradation posture and avoid introducing new hidden dependencies in topology resolution.
- Keep contract-first model discipline (`pydantic` frozen models) for topology payloads and stage outputs.
- Keep composition-root dependency wiring in `__main__.py`; no module-level mutable singleton loader state.
- Maintain deterministic behavior (stable ordering, explicit unresolved reason codes) to preserve audit/debug reproducibility.

### Library / Framework Requirements

- Keep project-pinned runtime versions for implementation unless explicitly scoped for upgrade:
  - Python >=3.13
  - pydantic==2.12.5
  - pydantic-settings~=2.13.1
  - pyyaml~=6.0
  - pytest==9.0.2
- Upstream snapshot (2026-03-22) for awareness only:
  - pyyaml 6.0.3
  - pydantic 2.12.5
  - pydantic-settings 2.13.1
  - pytest 9.0.2
  - SQLAlchemy 2.0.48
  - redis 7.3.0
- Decision for this story: stay on locked stack and apply current best practices compatible with existing project constraints.

### Project Structure Notes

- Primary code targets:
  - `src/aiops_triage_pipeline/registry/loader.py`
  - `src/aiops_triage_pipeline/registry/resolver.py`
  - `src/aiops_triage_pipeline/pipeline/stages/topology.py`
  - `src/aiops_triage_pipeline/pipeline/scheduler.py`
  - `src/aiops_triage_pipeline/__main__.py`
- Downstream topology-context surfaces to verify/update as needed:
  - `src/aiops_triage_pipeline/pipeline/stages/casefile.py`
  - `src/aiops_triage_pipeline/pipeline/stages/dispatch.py`
  - `src/aiops_triage_pipeline/models/case_file.py`
  - `src/aiops_triage_pipeline/contracts/triage_excerpt.py`
- Config and policy artifacts:
  - `config/policies/topology-registry-loader-rules-v1.yaml`
  - `config/topology-registry.yaml` (canonical runtime registry location expected by architecture)
  - `config/.env.*` (`TOPOLOGY_REGISTRY_PATH` alignment)
- Primary tests to extend:
  - `tests/unit/registry/test_loader.py`
  - `tests/unit/registry/test_resolver.py`
  - `tests/unit/pipeline/stages/test_topology.py`
  - `tests/unit/pipeline/test_scheduler_topology.py`

### Testing Requirements

- Required tests:
  - unified topology format acceptance and explicit failure categories for invalid input.
  - scope-shape handling for topic and consumer-group forms.
  - ownership fallback precedence and unresolved-path behavior (`owner_not_found`, `routing_key_not_found`).
  - blast-radius derivation and downstream-impact deterministic ordering.
  - reload-on-change success path and invalid-reload last-known-good preservation.
  - stage integration checks that unresolved scopes are not promoted into gate/casefile context.
- Required quality-gate commands:
  - `uv run ruff check`
  - `TESTCONTAINERS_RYUK_DISABLED=true DOCKER_HOST=unix://$HOME/.docker/desktop/docker.sock uv run pytest -q -rs`
- Sprint gate remains strict: 0 skipped tests.

### Previous Story Intelligence

- Story 1.3 hardened Stage 2 behavior (parallel sustained computation + bounded memory + observability) and touched `__main__.py`/`pipeline/scheduler.py` heavily.
- Story 1.4 will also touch scheduler-adjacent flow through Stage 3; avoid regressions to Stage 2 data flow and sustained-state continuity.
- Recent review patterns show value in explicit edge-case handling and deterministic fallback behavior; apply the same rigor in topology reload and ownership fall-through paths.

### Git Intelligence Summary

- Recent commit sequence in this repo follows: create story context -> implement -> fix review findings -> sync sprint status.
- Most recent commits primarily modified Stage 2/peak files; topology files were less recently touched, so topology-specific regression tests must be explicit.
- Actionable guidance for Story 1.4:
  - keep changes localized to topology loader/resolver/stage + affected contracts/models/tests.
  - preserve current structured logging/event naming style for reload/unresolved telemetry.
  - avoid broad refactors outside Story 1.4 scope to keep blast radius controlled.

### Latest Tech Information

- Snapshot date: 2026-03-22.
- PyPI latest versions:
  - `pyyaml`: 6.0.3
  - `pydantic`: 2.12.5
  - `pydantic-settings`: 2.13.1
  - `pytest`: 9.0.2
  - `SQLAlchemy`: 2.0.48
  - `redis`: 7.3.0
- Relevant official docs for this story:
  - Python `pathlib.Path.stat()`/mtime behavior for change detection semantics.
  - Pydantic v2 model concepts for immutable/frozen contract handling.
  - PyYAML safe parsing guidance for trusted/untrusted YAML boundaries.
- Decision for this story: keep locked dependency set, apply latest-known safe parser/modeling practices, and avoid dependency upgrades in-scope.

### Project Context Reference

- Loaded and applied `archive/project-context.md` rules:
  - Python 3.13 typing conventions and frozen-model discipline.
  - config module remains a leaf; avoid contract-coupled settings loading.
  - deterministic guardrails and explicit degraded/error signaling are preserved.
  - structured logging + health/observability patterns are reused, not reimplemented.

### References

- [Source: `artifact/planning-artifacts/epics.md` - Epic 1, Story 1.4]
- [Source: `artifact/planning-artifacts/prd/functional-requirements.md` - FR12, FR13, FR14, FR15, FR16]
- [Source: `artifact/planning-artifacts/prd/non-functional-requirements.md` - NFR-SC1, NFR-SC4, NFR-R6, NFR-R7]
- [Source: `artifact/planning-artifacts/prd/domain-specific-requirements.md` - degraded mode + safety invariants]
- [Source: `artifact/planning-artifacts/architecture/core-architectural-decisions.md` - D10 and topology-related constraints]
- [Source: `artifact/planning-artifacts/architecture/implementation-patterns-consistency-rules.md`]
- [Source: `artifact/planning-artifacts/architecture/project-structure-boundaries.md`]
- [Source: `artifact/implementation-artifacts/1-3-classify-peak-and-sustained-conditions-with-bounded-memory.md`]
- [Source: `artifact/implementation-artifacts/sprint-status.yaml`]
- [Source: `src/aiops_triage_pipeline/registry/loader.py`]
- [Source: `src/aiops_triage_pipeline/registry/resolver.py`]
- [Source: `src/aiops_triage_pipeline/pipeline/stages/topology.py`]
- [Source: `src/aiops_triage_pipeline/pipeline/scheduler.py`]
- [Source: `src/aiops_triage_pipeline/__main__.py`]
- [Source: `src/aiops_triage_pipeline/pipeline/stages/casefile.py`]
- [Source: `src/aiops_triage_pipeline/pipeline/stages/dispatch.py`]
- [Source: `src/aiops_triage_pipeline/models/case_file.py`]
- [Source: `tests/unit/registry/test_loader.py`]
- [Source: `tests/unit/registry/test_resolver.py`]
- [Source: `tests/unit/pipeline/stages/test_topology.py`]
- [Source: `tests/unit/pipeline/test_scheduler_topology.py`]
- [Source: `archive/project-context.md`]
- [Source: https://pypi.org/project/PyYAML/]
- [Source: https://pypi.org/project/pydantic/]
- [Source: https://pypi.org/project/pydantic-settings/]
- [Source: https://pypi.org/project/pytest/]
- [Source: https://pypi.org/project/SQLAlchemy/]
- [Source: https://pypi.org/project/redis/]
- [Source: https://docs.python.org/3/library/pathlib.html#pathlib.Path.stat]
- [Source: https://docs.pydantic.dev/latest/concepts/models/]
- [Source: https://pyyaml.org/wiki/PyYAMLDocumentation]

## Dev Agent Record

### Agent Model Used

GPT-5 Codex

### Debug Log References

- Implemented canonical topology path defaults and env alignment (`config/topology-registry.yaml`, `TOPOLOGY_REGISTRY_PATH`).
- Enforced single runtime registry schema support (v2 only) and explicit `unsupported_version` validation category.
- Added ownership confidence diagnostics and explicit confidence rationale when confidence is absent.
- Updated resolver downstream-impact derivation to include downstream entities only (shared components + sinks).
- Added reload no-op structured logging and dispatch routing-context topic-scope fallback for group scopes.
- Updated loader/resolver/topology/main/contract tests plus ATDD story tests to match the new behavior.

### Implementation Plan

- Keep existing Stage 3/4/7 contracts stable and push confidence metadata through diagnostics.
- Constrain runtime registry loading to unified schema while preserving explicit typed failure categories.
- Preserve deterministic ordering across ownership fallback and downstream impact output.
- Validate with lint + full Docker-enabled regression gate (no skipped tests).

### Completion Notes List

- Canonical runtime topology registry path is now `config/topology-registry.yaml` with settings/env defaults aligned.
- Topology loader now accepts only version 2 input schema and fails legacy schemas with typed `unsupported_version`.
- Ownership fallback remains deterministic and now emits `selected_owner_confidence` (or explicit reason when absent) in diagnostics.
- Stage 3 routing-context fallback for group scopes now deterministically reuses topic-scope routing when needed for dispatch handoff.
- Downstream impacts are deterministic and constrained to downstream entities (shared components and sinks).
- Validation completed and re-verified in code review: `uv run ruff check` and full Docker-enabled regression `857 passed`, `0 skipped`.

### File List

- .gitignore
- artifact/implementation-artifacts/1-4-resolve-topology-ownership-and-blast-radius-from-unified-registry.md
- artifact/implementation-artifacts/sprint-status.yaml
- artifact/test-artifacts/atdd-checklist-1-4-resolve-topology-ownership-and-blast-radius-from-unified-registry.md
- config/.env.dev
- config/.env.local
- config/.env.prod.template
- config/.env.uat.template
- config/policies/topology-registry-loader-rules-v1.yaml
- config/topology-registry.yaml
- src/aiops_triage_pipeline/__main__.py
- src/aiops_triage_pipeline/config/settings.py
- src/aiops_triage_pipeline/contracts/topology_registry.py
- src/aiops_triage_pipeline/registry/loader.py
- src/aiops_triage_pipeline/registry/resolver.py
- tests/atdd/fixtures/story_1_4_test_data.py
- tests/atdd/story_1_4_topology_registry_red_phase.py
- tests/unit/contracts/test_policy_models.py
- tests/unit/pipeline/stages/test_topology.py
- tests/unit/registry/test_loader.py
- tests/unit/registry/test_resolver.py
- tests/unit/test_main.py

## Senior Developer Review (AI)

### Reviewer

- Reviewer: Sas (AI Code Review Workflow)
- Date: 2026-03-22
- Outcome: Approved after fixes

### Findings and Resolutions

- [MEDIUM][Resolved] File-list traceability drift: `tests/atdd/fixtures/story_1_4_test_data.py` and generated ATDD checklist artifact were present but not listed in Dev Agent Record File List. Updated File List to include all implementation artifacts for Story 1.4.
- [MEDIUM][Resolved] Workspace hygiene gap: generated temp outputs under `artifact/test-artifacts/atdd-temp/` and compiled bytecode under `tests/atdd/__pycache__/` were left behind, creating noisy undocumented deltas. Removed generated temp/bytecode files and added `.gitignore` rule for `artifact/test-artifacts/atdd-temp/`.
- [MEDIUM][Resolved] Review audit trail missing: story lacked a dedicated senior review record section for findings/resolution traceability. Added this section and synchronized Change Log with review-fix completion.

### Verification Evidence

- `uv run ruff check` → pass
- `TESTCONTAINERS_RYUK_DISABLED=true DOCKER_HOST=unix://$HOME/.docker/desktop/docker.sock uv run pytest -q -rs` → `857 passed`, `0 skipped`

## Story Completion Status

- Story status: `done`
- Completion note: Story implementation and adversarial code review fixes completed; lint and full Docker-enabled regression re-run passed with zero skips.

## Change Log

- 2026-03-22: Story created via create-story workflow with exhaustive artifact and code-context analysis; status set to ready-for-dev.
- 2026-03-22: Implemented Story 1.4 topology ownership/blast-radius updates; completed tests and moved story to review.
- 2026-03-22: Completed `bmad-bmm-code-review` findings remediation; reran lint/full regression (`857 passed`, `0 skipped`); set story to done.
