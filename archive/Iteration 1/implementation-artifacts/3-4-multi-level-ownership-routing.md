# Story 3.4: Multi-Level Ownership Routing

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a platform operator,
I want cases routed to the correct owning team using a multi-level ownership lookup,
so that anomalies reach the right responders without manual intervention (FR13).

## Acceptance Criteria

1. **Given** an anomaly has been resolved to a stream  
   **When** ownership routing is computed  
   **Then** the system applies multi-level lookup in order: `consumer_group_owner -> topic_owner -> stream_default_owner -> platform_default` (FR13).
2. **And** the first non-null owner in the chain is selected as the routing target.
3. **And** the `routing_key` for the selected owner is resolved from the topology registry routing directory.
4. **And** cases with no owner at any level fall through to `platform_default` (never unrouted in valid registry configurations).
5. **And** unit tests verify: each level of the lookup chain, fallthrough behavior, platform-default catch-all, and routing-key resolution.

## Tasks / Subtasks

- [x] Task 1: Add immutable ownership-routing result models in resolver output (AC: 1, 2, 3, 4)
  - [x] Add typed literals/models for lookup levels (`consumer_group_owner`, `topic_owner`, `stream_default_owner`, `platform_default`) and selected routing outcome.
  - [x] Include routing target metadata needed downstream (`routing_key`, team identity fields from routing directory, optional support channel/escalation refs).
  - [x] Preserve unresolved semantics and reason-code discipline when routing cannot be computed from invalid registry data.

- [x] Task 2: Implement deterministic multi-level owner selection logic (AC: 1, 2, 4)
  - [x] For group scopes `(env, cluster_id, group, topic)`, evaluate consumer-group ownership first.
  - [x] For both topic and group scopes, evaluate topic owner second, then stream default owner, then platform default.
  - [x] Keep first-match semantics deterministic and stable across runs.

- [x] Task 3: Resolve and validate routing target via routing directory (AC: 3, 4)
  - [x] Resolve selected `routing_key` to canonical `routing_directory` entry.
  - [x] Add explicit unresolved reason for malformed/invalid ownership references that escape loader constraints.
  - [x] Ensure diagnostics contain lookup path and selected level for traceability.

- [x] Task 4: Expose routing outputs for downstream stages without regressing existing Stage 3 outputs (AC: 2, 3)
  - [x] Extend Stage 3 output to include routing context by scope.
  - [x] Keep `context_by_scope` and `impact_by_scope` behavior from Stories 3.2 and 3.3 unchanged.
  - [x] Preserve scheduler behavior that skips unresolved scopes before Stage 6 gate-input assembly.

- [x] Task 5: Add comprehensive unit tests for lookup chain and fallthrough behavior (AC: 5)
  - [x] Extend resolver tests for all four lookup levels and deterministic first-match selection.
  - [x] Add tests for group-vs-topic scope behavior and platform-default fallback.
  - [x] Add Stage 3 topology tests to verify resolved routing context is emitted for downstream consumption.

- [x] Task 6: Run quality gates
  - [x] `uv run pytest -q tests/unit/registry/test_resolver.py tests/unit/pipeline/stages/test_topology.py tests/unit/pipeline/test_scheduler_topology.py`
  - [x] `uv run pytest -q`
  - [x] `uv run ruff check`

## Dev Notes

### Story Requirements

- Scope is FR13 with explicit chain order and deterministic first-match behavior.
- Story 3.4 must produce routing context that later stages (CaseFile/header/excerpt publishing and action dispatch) can consume without re-resolving ownership.
- Story 3.4 should not implement Story 3.5 legacy compat views; keep scope limited to canonical v1 resolution and routing.

### Developer Context Section

- Artifact discovery used for this context:
  - `epics_content`: `artifact/planning-artifacts/epics.md`
  - `architecture_content`: `artifact/planning-artifacts/architecture.md`
  - `prd_content`: `artifact/planning-artifacts/prd/functional-requirements.md`, `artifact/planning-artifacts/prd/non-functional-requirements.md`
  - `project_context`: `artifact/project-context.md`
  - `ux_content`: not found
- Current implementation baseline:
  - `registry.loader` canonicalizes ownership data into immutable structures: `consumer_group_owners`, `topic_owners`, `stream_default_owner`, `platform_default`, and `routing_directory`.
  - `registry.loader` fail-fast validates duplicate ownership keys and missing routing key references (FR15 guardrails).
  - `registry.resolver` resolves ownership routing context and emits `ownership_routing` for resolved scopes.
  - `pipeline/stages/topology.py` exports `context_by_scope`, `impact_by_scope`, `routing_by_scope`, and `unresolved_by_scope`.
  - `contracts/case_header_event.py` and `contracts/triage_excerpt.py` require `routing_key`, so Stage 3 routing context remains a prerequisite for downstream story work.

### Technical Requirements

- Implement multi-level owner lookup exactly in this order:
  1. `consumer_group_owner` (only when scope includes `group`)
  2. `topic_owner`
  3. `stream_default_owner`
  4. `platform_default`
- Selection semantics:
  - First matching level wins.
  - Matching keys are exact on normalized scope parts (`env`, `cluster_id`, `group`, `topic`, `stream_id`).
  - No probabilistic fallback; no level skipping when a prior level has a match.
- Routing resolution semantics:
  - Selected `routing_key` must resolve to a routing-directory entry.
  - Resolver output should include selected lookup level and resolved routing metadata for downstream use.
- Unresolved/error semantics:
  - Preserve explicit unresolved outputs with stable `reason_code` + diagnostics.
  - Do not fabricate a routing target when ownership map data is missing/invalid.
  - If registry misconfiguration escapes loader checks, surface deterministic unresolved reason and structured diagnostics.
- Performance and determinism constraints:
  - Keep resolver pure in-memory; no additional I/O or network calls.
  - Maintain p99 lookup behavior consistent with NFR-P5 expectations.
  - Keep deterministic ordering and immutable outputs for reproducible tests.

### Architecture Compliance

- Place ownership-routing logic in Stage 3 topology boundary (`registry/resolver.py`, `pipeline/stages/topology.py`), consistent with architecture mapping for FR9-FR16.
- Keep resolver output immutable and typed (Pydantic frozen models / immutable mappings), matching existing resolver and loader patterns.
- Preserve FR14 scope isolation by `(env, cluster_id)`; no cross-cluster ownership leakage.
- Preserve hot-path deterministic behavior:
  - no background tasks,
  - no external service calls,
  - no runtime mutation of registry state.
- Preserve explicit unresolved behavior and structured logging for routing misses/misconfigurations.
- Do not introduce Story 3.5 compatibility-view logic into Story 3.4 implementation.

### Library / Framework Requirements

- Use existing pinned stack and conventions; do not add new dependencies for Story 3.4.
- Keep model typing and validation aligned with Pydantic v2 immutable patterns already used in resolver/loader outputs.
- Keep logging on the shared `structlog` setup (`get_logger`) with stable `event_type` fields.
- Reuse canonical loader outputs instead of re-parsing raw YAML:
  - `CanonicalOwnershipMap`
  - `RoutingDirectoryEntry`
  - `CanonicalStream` / instance scope metadata
- Maintain Python 3.13-compatible code style and existing Ruff/pytest standards.

### File Structure Requirements

- Primary implementation files:
  - `src/aiops_triage_pipeline/registry/resolver.py`
  - `src/aiops_triage_pipeline/pipeline/stages/topology.py`
- Exports (only if new public types/functions are introduced):
  - `src/aiops_triage_pipeline/registry/__init__.py`
  - `src/aiops_triage_pipeline/pipeline/stages/__init__.py`
- Primary test files:
  - `tests/unit/registry/test_resolver.py`
  - `tests/unit/pipeline/stages/test_topology.py`
  - `tests/unit/pipeline/test_scheduler_topology.py` (if stage output shape changes)
- Keep ownership lookups inside resolver boundary; avoid duplicating lookup logic in scheduler/gating/casefile stages.
- Keep file-local naming and module boundaries consistent with current Epic 3 conventions.

### Testing Requirements

- Resolver tests must cover each chain level independently:
  - consumer-group owner hit (group scope)
  - topic owner hit
  - stream-default owner hit
  - platform-default fallback hit
- Add negative-path tests:
  - unresolved when required routing metadata cannot be resolved from malformed registry content
  - deterministic reason codes + diagnostics for routing misses
- Add scope-shape tests:
  - group scope evaluates consumer-group ownership
  - topic-only scope skips consumer-group level and starts at topic owner
- Topology stage tests must verify routing context is emitted for resolved scopes and absent for unresolved scopes.
- Scheduler topology tests must remain green and continue skipping unresolved scopes without Stage 6 regressions.
- Minimum command set before completion:
  - `uv run pytest -q tests/unit/registry/test_resolver.py tests/unit/pipeline/stages/test_topology.py tests/unit/pipeline/test_scheduler_topology.py`
  - `uv run pytest -q`
  - `uv run ruff check`

### Previous Story Intelligence

- Story 3.3 reinforced strict resolved/unresolved output contracts in resolver models.
- Story 3.3 established deterministic ordering and deduplication patterns for Stage 3 derived outputs.
- Story 3.3 added `impact_by_scope` without regressing existing `context_by_scope` behavior; follow the same additive pattern for routing context.
- Story 3.2 and 3.3 both preserve scheduler safety behavior: unresolved scopes are explicitly logged/skipped before Stage 6 gate-input assembly.
- Reuse these proven patterns for Story 3.4:
  - immutable typed output models
  - stable reason-code taxonomy
  - deterministic sort/selection logic
  - no hidden defaulting/fabrication

### Git Intelligence Summary

Recent commit patterns relevant to Story 3.4:

- `e8f368a` (`fix(story-3.3): dedupe downstream impacts and finalize review sync`)
  - Reinforced deterministic output expectations in resolver and Stage 3 tests.
- `24d6c01` (`feat: finalize story 3.2 review fixes and validation hardening`)
  - Hardened resolver/topology unresolved handling and scheduler skip behavior.
- `47ce6ae` (`feat(registry): implement topology loader v0/v1 with validations and reload`)
  - Introduced canonical ownership and routing models plus fail-fast validation scaffolding.

Actionable implementation guidance:

- Keep Story 3.4 implementation additive and contract-safe, following recent Epic 3 review-hardening patterns.
- Prefer explicit typed models and deterministic selection over ad-hoc dict mutation.
- Expand tests in the same resolver/stage test files already used in Stories 3.2 and 3.3 to preserve continuity and regression confidence.

### Latest Tech Information

Verification date: **March 4, 2026**.

- **Python runtime**
  - Python.org currently lists **Python 3.14.0** as latest feature release and **Python 3.13.12** as the current 3.13 maintenance release (released **February 3, 2026**).
  - Story implication: keep implementation fully Python 3.13 compatible per project baseline; avoid 3.14-only syntax/features.

- **SQLAlchemy**
  - PyPI lists **SQLAlchemy 2.0.48** (released **March 2, 2026**) while project is pinned to `2.0.47`.
  - Story implication: no migration is required for Story 3.4; keep resolver/stage logic dependency-neutral unless broader dependency upgrade is planned.

- **Pydantic**
  - PyPI lists **pydantic 2.12.5** (released **November 26, 2025**), matching current project pin.
  - Story implication: continue using existing frozen-model patterns; no version-driven behavior changes required.

- **pytest**
  - PyPI lists **pytest 9.0.2** (released **December 6, 2025**), matching current project pin.
  - Story implication: continue with existing unit-test patterns and no framework migration work.

- **Ruff**
  - PyPI lists **ruff 0.15.4** (released **February 26, 2026**); project range is `~0.15`.
  - Story implication: current linting baseline remains aligned; no style-tooling changes needed for Story 3.4.

Inference from sources:
- No blocker-level ecosystem change affects Story 3.4 implementation; focus should remain on deterministic ownership routing logic and regression-safe tests.

### Project Context Reference

Relevant guardrails from `artifact/project-context.md`:

- Keep deterministic guardrails authoritative; no ambiguous routing behavior.
- Preserve immutable model discipline and validate at boundaries.
- Use shared logging and health/event primitives; do not introduce parallel frameworks.
- Keep configuration and policy logic centralized (no ad-hoc cap/routing evaluators outside designated modules).
- Add targeted regression tests for any behavior changes in resolver/topology paths.
- Preserve fail-loud behavior for critical-path misconfiguration and avoid silent fallbacks.

### Story Completion Status

- Story context generation complete.
- Story file: `artifact/implementation-artifacts/3-4-multi-level-ownership-routing.md`.
- Status: `done`.
- Completion note: **Ultimate context engine analysis completed - comprehensive developer guide created.**

## Project Structure Notes

- Story 3.4 should extend Stage 3 topology outputs with ownership-routing metadata in the same additive style used for Story 3.3 impact metadata.
- Avoid coupling Stage 3 directly to Stage 4/6 implementation details beyond stable typed context outputs.
- Keep resolver as the single ownership lookup authority; downstream stages should consume resolver/stage outputs rather than duplicating ownership lookup logic.

## References

- [Source: `artifact/planning-artifacts/epics.md#Story 3.4: Multi-Level Ownership Routing`]
- [Source: `artifact/planning-artifacts/prd/functional-requirements.md` (FR13, FR14, FR15, FR16)]
- [Source: `artifact/planning-artifacts/prd/non-functional-requirements.md` (NFR-P5)]
- [Source: `artifact/planning-artifacts/architecture.md` (Topology & Ownership placement for FR9-FR16)]
- [Source: `artifact/project-context.md`]
- [Source: `artifact/implementation-artifacts/3-3-blast-radius-and-downstream-impact-assessment.md`]
- [Source: `src/aiops_triage_pipeline/registry/loader.py`]
- [Source: `src/aiops_triage_pipeline/registry/resolver.py`]
- [Source: `src/aiops_triage_pipeline/pipeline/stages/topology.py`]
- [Source: `src/aiops_triage_pipeline/pipeline/scheduler.py`]
- [Source: `src/aiops_triage_pipeline/contracts/case_header_event.py`]
- [Source: `src/aiops_triage_pipeline/contracts/triage_excerpt.py`]
- [Source: `https://www.python.org/downloads/`]
- [Source: `https://www.python.org/downloads/release/python-31312/`]
- [Source: `https://pypi.org/project/SQLAlchemy/`]
- [Source: `https://pypi.org/project/pydantic/`]
- [Source: `https://pypi.org/project/pytest/`]
- [Source: `https://pypi.org/project/ruff/`]

## Dev Agent Record

### Agent Model Used

GPT-5 Codex

### Debug Log References

- Workflow runner: `_bmad/core/tasks/workflow.xml` with config `_bmad/bmm/workflows/4-implementation/dev-story/workflow.yaml`.
- Target story discovered from `artifact/implementation-artifacts/sprint-status.yaml` as first `ready-for-dev` item in order: `3-4-multi-level-ownership-routing`.
- Resolver implementation added typed ownership routing result models and deterministic lookup-chain selection in `src/aiops_triage_pipeline/registry/resolver.py`.
- Stage 3 topology output extended with routing context mapping in `src/aiops_triage_pipeline/pipeline/stages/topology.py`.
- Public exports updated for new routing models/contexts in `src/aiops_triage_pipeline/registry/__init__.py` and `src/aiops_triage_pipeline/pipeline/stages/__init__.py`.
- Story tests expanded for all lookup levels, routing-directory resolution, malformed reference handling, and Stage 3 routing outputs.
- Validation executed:
  - `uv run pytest -q tests/unit/registry/test_resolver.py tests/unit/pipeline/stages/test_topology.py tests/unit/pipeline/test_scheduler_topology.py`
  - `uv run pytest -q`
  - `uv run ruff check`

### Completion Notes List

- Implemented immutable ownership routing outputs:
  - `OwnershipLookupLevel` literal set (`consumer_group_owner`, `topic_owner`, `stream_default_owner`, `platform_default`)
  - `OwnershipRoutingTarget` and `OwnershipRoutingResolution` models
  - `TopologyResolution.ownership_routing` with resolved/unresolved invariants
- Implemented deterministic owner lookup chain in resolver:
  - group scopes: consumer-group owner -> topic owner -> stream default owner -> platform default
  - topic scopes: topic owner -> stream default owner -> platform default
  - first-match deterministic selection with no fabricated routing targets
- Added explicit unresolved reason handling for malformed ownership references (`routing_key_not_found`) and missing ownership (`owner_not_found`) with structured diagnostics including lookup path and selected level.
- Extended Stage 3 output with `routing_by_scope` while preserving `context_by_scope` and `impact_by_scope` behavior.
- Added/updated unit tests covering all four lookup levels, group-vs-topic behavior, platform fallback, malformed routing references, and downstream Stage 3/scheduler routing context propagation.
- Hardened loader validation to fail fast on duplicate topic-owner and stream-default-owner keys, preventing silent first-match shadowing.
- Completed validation gates successfully:
  - `uv run pytest -q tests/unit/registry/test_resolver.py tests/unit/pipeline/stages/test_topology.py tests/unit/pipeline/test_scheduler_topology.py` (21 passed)
  - `uv run pytest -q tests/unit/registry/test_loader.py tests/unit/registry/test_resolver.py tests/unit/pipeline/stages/test_topology.py tests/unit/pipeline/test_scheduler_topology.py` (38 passed)
  - `uv run pytest -q` (295 passed)
  - `uv run ruff check` (all checks passed)

### File List

- `src/aiops_triage_pipeline/registry/resolver.py`
- `src/aiops_triage_pipeline/registry/loader.py`
- `src/aiops_triage_pipeline/pipeline/stages/topology.py`
- `src/aiops_triage_pipeline/registry/__init__.py`
- `src/aiops_triage_pipeline/pipeline/stages/__init__.py`
- `tests/unit/registry/test_loader.py`
- `tests/unit/registry/test_resolver.py`
- `tests/unit/pipeline/stages/test_topology.py`
- `tests/unit/pipeline/test_scheduler_topology.py`
- `artifact/implementation-artifacts/3-4-multi-level-ownership-routing.md`
- `artifact/implementation-artifacts/sprint-status.yaml`

## Senior Developer Review (AI)

- Reviewer: Sas
- Date: 2026-03-04
- Outcome: Approve (all findings fixed)

### Findings

1. [MEDIUM] Missing explicit regression coverage for unresolved `owner_not_found` path when ownership chain has no match and `platform_default` is absent (`tests/unit/registry/test_resolver.py`).
2. [MEDIUM] Story context text was stale and contradictory (`Status: ready-for-dev` in context section while story was under review; baseline text still described pre-implementation state) (`artifact/implementation-artifacts/3-4-multi-level-ownership-routing.md`).
3. [LOW] Ownership lookup previously used linear scans over ownership collections; optimized to indexed lookups in canonical ownership map for O(1) resolution per level (`src/aiops_triage_pipeline/registry/loader.py`, `src/aiops_triage_pipeline/registry/resolver.py`).

### Fixes Applied

- Added resolver regression test for unresolved `owner_not_found` path and strengthened traceability assertions for ownership lookup diagnostics.
- Corrected stale story context status/baseline text to match implemented state.
- Optimized ownership selection path by precomputing immutable ownership indexes during topology load and using indexed resolver lookups.
- Added fail-fast loader validation for duplicate `topic_owners` keys and duplicate `stream_default_owner` keys.
- Added loader regression tests for duplicate topic-owner and stream-default-owner validation failures.
- Updated story File List to include all actually changed source/test files.
- Re-ran quality gates after fixes:
  - `uv run pytest -q tests/unit/registry/test_resolver.py tests/unit/pipeline/stages/test_topology.py tests/unit/pipeline/test_scheduler_topology.py`
  - `uv run pytest -q`
  - `uv run ruff check`

### Findings (Workflow Re-Run)

1. [MEDIUM] Story File List was incomplete: `src/aiops_triage_pipeline/registry/loader.py` changed in git but missing from documented File List.
2. [MEDIUM] Loader accepted duplicate topic-owner keys without explicit fail-fast validation, allowing silent first-entry shadowing.
3. [MEDIUM] Loader accepted duplicate stream-default-owner keys without explicit fail-fast validation, allowing silent first-entry shadowing.

## Change Log

- 2026-03-04: Implemented Story 3.4 multi-level ownership routing, added resolver/stage routing models and deterministic selection chain, expanded unit tests, and passed full quality gates.
- 2026-03-04: Senior developer adversarial review completed; added missing unresolved-owner regression coverage, corrected story-context inconsistencies, and marked story done.
- 2026-03-04: Fixed low-severity performance finding by replacing linear ownership scans with precomputed immutable lookup indexes.
- 2026-03-04: Follow-up adversarial review fixed missing duplicate-key validation for topic-owner and stream-default-owner loader paths, added loader regression tests, and reconciled File List with git reality.
