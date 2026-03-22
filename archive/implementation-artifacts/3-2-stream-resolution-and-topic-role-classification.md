# Story 3.2: Stream Resolution & Topic Role Classification

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a platform operator,
I want the system to resolve stream_id, topic_role, criticality_tier, and source_system from the topology registry given an anomaly key,
so that each case is enriched with the context needed for routing and gating decisions (FR10, FR14).

## Acceptance Criteria

1. **Given** the topology registry is loaded in memory  
   **When** an anomaly key `(env, cluster_id, topic/group)` is resolved  
   **Then** the system returns: `stream_id`, `topic_role`, `criticality_tier`, and `source_system`.
2. **And** `topic_index` lookups are scoped by `(env, cluster_id)` to prevent cross-cluster collisions (FR14).
3. **And** resolution latency is p99 <= 50ms (NFR-P5).
4. **And** unresolvable anomaly keys return a clear `unresolved` status (not a silent default).
5. **And** unit tests verify: successful resolution, cross-cluster scoping, unresolvable key handling, and latency within bounds.

## Tasks / Subtasks

- [x] Task 1: Define resolver contracts and unresolved semantics (AC: 1, 4)
  - [x] Add immutable resolution output model(s) in `registry/resolver.py` with explicit `status` (`resolved` | `unresolved`) and reason code.
  - [x] Support anomaly scope shapes from upstream evidence/gating flows: `(env, cluster_id, topic)` and `(env, cluster_id, group, topic)`.
  - [x] Ensure unresolved results are explicit and typed, never implicit fallbacks.

- [x] Task 2: Implement scoped topology resolution in `registry/resolver.py` (AC: 1, 2, 4)
  - [x] Resolve `topic_index` via `snapshot.registry.topic_index_by_scope[(env, cluster_id)]`.
  - [x] Resolve `stream_id` and derive `criticality_tier` from stream/source metadata in canonical registry structures.
  - [x] Resolve `source_system` from topic entry/source mappings when available.
  - [x] Add deterministic topic-role normalization for gate-safe values (`SOURCE_TOPIC`, `SHARED_TOPIC`, `SINK_TOPIC`) with explicit unresolved handling for unsupported roles.

- [x] Task 3: Add Stage 3 topology assembly in `pipeline/stages/topology.py` (AC: 1, 4)
  - [x] Build `GateInputContext` by scope for Stage 6 using resolver outputs.
  - [x] Include structured unresolved diagnostics for missing scope/topic/stream metadata.
  - [x] Keep stage logic in-memory only; no filesystem/network calls on lookup path.

- [x] Task 4: Wire stage interface for scheduler integration readiness (AC: 1)
  - [x] Export topology stage helpers from `pipeline/stages/__init__.py`.
  - [x] Add/prepare a scheduler helper invocation point without breaking current Stage 1/2/6 flow.

- [x] Task 5: Add unit tests for resolver and topology stage (AC: 5)
  - [x] Add `tests/unit/registry/test_resolver.py` for success, scoped-collision prevention, and unresolved paths.
  - [x] Add `tests/unit/pipeline/stages/test_topology.py` for context assembly and unresolved propagation.
  - [x] Add latency assertion test (batch lookup benchmark) demonstrating p99 <= 50ms in controlled unit conditions.

- [x] Task 6: Quality gates
  - [x] Run `uv run pytest -q tests/unit/registry/test_resolver.py tests/unit/pipeline/stages/test_topology.py tests/unit/pipeline/test_scheduler.py tests/unit/registry/test_loader.py`.
  - [x] Run `uv run pytest -q`.
  - [x] Run `uv run ruff check`.

## Dev Notes

### Story Requirements

- Story scope is FR10 + FR14 with NFR-P5 latency bound; this is resolver-first work that unlocks downstream routing/gating stories.
- Inputs are already available from Story 3.1 canonical loader output (`TopologyRegistrySnapshot`) and Stage 1/2 scope keys.
- Unresolved behavior is a hard requirement: unresolved anomaly keys must produce explicit status/reason, never silent defaults.

### Developer Context Section

- Artifact discovery used for this story context:
  - `epics_content`: `artifact/planning-artifacts/epics.md`
  - `architecture_content`: `artifact/planning-artifacts/architecture.md`
  - `prd_content`: `artifact/planning-artifacts/prd/functional-requirements.md`, `artifact/planning-artifacts/prd/non-functional-requirements.md`
  - `project_context`: `artifact/project-context.md`
  - `ux_content`: not found
- Current codebase state:
  - `src/aiops_triage_pipeline/registry/loader.py` is implemented and provides immutable snapshot + scoped topic index.
  - `src/aiops_triage_pipeline/registry/resolver.py` is empty (target for core implementation).
  - `src/aiops_triage_pipeline/pipeline/stages/topology.py` is empty (target for Stage 3 assembly).
  - `pipeline/stages/gating.py` already expects resolved context via `GateInputContext` (`stream_id`, `topic_role`, `criticality_tier`).
- Integration implication:
  - Resolver output contract must align exactly with GateInputContext requirements and preserve deterministic behavior.

### Technical Requirements

- Implement deterministic resolver APIs over immutable snapshots (`TopologyRegistrySnapshot` / `CanonicalTopologyRegistry`) with no hidden mutable state.
- Accept anomaly scope keys from existing stage outputs:
  - topic scope: `(env, cluster_id, topic)`
  - group scope: `(env, cluster_id, group, topic)`
- Resolution algorithm requirements:
  - Lookup scope index by exact `(env, cluster_id)` tuple.
  - Lookup topic by exact topic key within scoped index.
  - Extract `stream_id` from `CanonicalTopicEntry.stream_id`.
  - Resolve `criticality_tier` from matched stream/source metadata with deterministic fallback order documented in code.
  - Resolve `source_system` from topic entry and/or stream source entries when present.
- Topic-role normalization requirements:
  - Normalize registry roles to gate-compatible literal set (`SOURCE_TOPIC`, `SHARED_TOPIC`, `SINK_TOPIC`).
  - If role cannot be safely normalized, return `unresolved` with reason `UNSUPPORTED_TOPIC_ROLE`.
- Unresolved requirements:
  - Must include explicit status + reason code (`scope_not_found`, `topic_not_found`, `stream_not_found`, etc.).
  - Must be structured for logging and test assertions.
- Performance requirement:
  - Maintain lookup complexity O(1)-style against precomputed maps to support p99 <= 50ms.

### Architecture Compliance

- Preserve architecture ownership boundaries:
  - `registry/` owns topology canonical model + resolution logic (FR9-FR16 core).
  - `pipeline/stages/topology.py` performs stage assembly and orchestration only.
- Keep hot-path behavior deterministic and local:
  - resolver does not perform I/O (registry already loaded in memory).
  - unresolved outcomes are explicit and deterministic.
- Reuse existing immutable-model pattern:
  - frozen Pydantic models and mapping proxies from loader outputs must remain read-only.
- Respect performance and operability constraints:
  - lookup path designed for NFR-P5 p99 <= 50ms.
  - structured logs with consistent `event_type` fields for unresolved diagnostics.
- Avoid cross-cutting duplication:
  - do not reimplement policy loading, logging context plumbing, or health primitives.

### Library / Framework Requirements

- Python 3.13 typing conventions (`tuple[str, ...]`, `X | None`) and Ruff lint rules from `pyproject.toml`.
- Pydantic v2 frozen contract discipline:
  - use immutable models for resolver outputs where persisted/passed across stages.
  - validate at creation boundaries; avoid ad-hoc dict payloads for core contracts.
- Reuse existing topology contracts and loader rules:
  - `TopologyRegistryLoaderRulesV1`
  - `TopologyRegistrySnapshot` and canonical models from `registry.loader`
- YAML handling remains in loader only; resolver/stage code should not parse YAML.
- Structured logging via existing `get_logger` and shared correlation conventions.

### File Structure Requirements

- Primary implementation files:
  - `src/aiops_triage_pipeline/registry/resolver.py`
  - `src/aiops_triage_pipeline/pipeline/stages/topology.py`
- Likely touched integration files:
  - `src/aiops_triage_pipeline/pipeline/stages/__init__.py`
  - `src/aiops_triage_pipeline/pipeline/scheduler.py` (if wiring helper for stage invocation)
- Test files to add/update:
  - `tests/unit/registry/test_resolver.py`
  - `tests/unit/pipeline/stages/test_topology.py`
- Keep Story 3.2 scope focused:
  - do not implement blast radius/downstream impact (Story 3.3).
  - do not implement ownership routing fallback chain (Story 3.4).
  - do not implement v0 compatibility view surface (Story 3.5).

### Testing Requirements

- Resolver unit tests:
  - successful resolution for topic and group scope keys.
  - cross-cluster scoping: same topic across different clusters resolves against exact `(env, cluster_id)` only.
  - unresolved cases with explicit reason codes (`scope_not_found`, `topic_not_found`, `stream_not_found`, `unsupported_topic_role`).
- Stage assembly tests:
  - build `GateInputContext` correctly from resolved metadata.
  - unresolved resolution path does not silently fabricate context.
- Determinism/performance tests:
  - repeated lookup benchmark asserts p99 <= 50ms under representative in-memory dataset.
  - no network/filesystem mocks should be required for resolver hot path.
- Regression safety:
  - existing loader tests remain green.
  - existing gating tests remain green after context integration.
- Commands:
  - `uv run pytest -q tests/unit/registry/test_resolver.py tests/unit/pipeline/stages/test_topology.py`
  - `uv run pytest -q`
  - `uv run ruff check`

### Previous Story Intelligence

- Story 3.1 delivered immutable canonical topology structures and reload-safe snapshots; Story 3.2 should consume these directly instead of introducing alternate registry representations.
- Loader guarantees already in place and safe to rely on:
  - strict duplicate protection for `topic_index` within scope.
  - strict ownership validation for duplicate consumer-group keys.
  - configurable enforcement for missing routing keys (`routing_key_required`).
  - optional strict unknown topic-role validation (`fail_on_unknown_topic_role`).
- Canonical structures currently expose:
  - `topic_index_by_scope[(env, cluster_id)] -> topic -> CanonicalTopicEntry`
  - `streams_by_id[stream_id] -> CanonicalStream`
- Practical implementation guidance from 3.1:
  - preserve immutable/read-only behavior (mapping proxies).
  - preserve typed, actionable validation/diagnostic messages.
  - preserve deterministic ordering assumptions in tests.
- Reuse patterns already validated in 3.1 test suite: typed error categories, fixture-based v0/v1 equivalence, and explicit reload behavior assertions.

### Git Intelligence Summary

Recent commit patterns (latest 5) show:

- `47ce6ae` implemented Story 3.1 loader with strong validation, immutable canonical models, and focused unit tests.
- `7a9eac8` and `9e00864` reinforced Stage 1/2 reliability and UNKNOWN propagation discipline in gating/evidence flow.
- Test-first workflow is consistent (`tests/unit/...` + targeted integration updates) and should be mirrored in Story 3.2.

Actionable implementation guidance from recent commits:

- Follow stage-local design and avoid cross-module coupling.
- Keep contract-aligned field naming (`stream_id`, `topic_role`, `criticality_tier`) to prevent downstream gate-input breakage.
- Preserve UNKNOWN/degraded-mode safety philosophy: unresolved topology keys must be explicit and observable.
- Keep structured logging events consistent with existing `event_type` naming conventions.

### Latest Tech Information

Verification date: **March 4, 2026**.

- **Python runtime line:**
  - Python.org release page lists **Python 3.13.12** with release date **February 3, 2026**.
  - Implication: keep project pinned to Python 3.13 line, but validate Story 3.2 behavior on latest 3.13 patch runtime.

- **Pydantic:**
  - PyPI lists **pydantic 2.12.5** as current release for the pinned project line.
  - Official strict-mode docs confirm strict validation can be enforced per validation call, field, or model configuration.
  - Implication: resolver boundary models should avoid silent coercion for ambiguous inputs.

- **PyYAML:**
  - PyPI lists **PyYAML 6.0.3** as latest release.
  - PyYAML documentation warns `yaml.load` is not safe for untrusted input and recommends `yaml.safe_load`.
  - Implication: Story 3.2 should continue to rely on loader-layer safe parsing; resolver/stage logic should stay YAML-agnostic.

Inference from sources:
- No immediate version migration is required for Story 3.2 because project-pinned versions align with current stable lines relevant to this work.

### Project Context Reference

Rules from `artifact/project-context.md` that apply directly:

- Keep contract/data models immutable by default (`frozen=True`) and validate at boundaries.
- Keep deterministic guardrails authoritative; no silent behavior drift in topology-to-gate context mapping.
- Reuse shared logging/correlation patterns; do not hand-roll alternate context propagation.
- Add targeted unit tests in the same change set for resolver/stage behavior.
- Preserve safe defaults and explicit unresolved signaling rather than implicit assumptions.

### Story Completion Status

- Story context generation complete.
- Story file: `artifact/implementation-artifacts/3-2-stream-resolution-and-topic-role-classification.md`.
- Status: `done`.
- Completion note: **Implementation and adversarial review complete; high/medium findings fixed and validated.**

## Project Structure Notes

- This story should establish the reusable topology resolution core used by Story 3.3 (blast radius) and Story 3.4 (ownership routing).
- Keep resolver logic isolated from dispatch/outbox/casefile concerns.
- Treat resolver output as stable contract for future stage wiring and routing decisions.

## References

- [Source: `artifact/planning-artifacts/epics.md#Story 3.2: Stream Resolution & Topic Role Classification`]
- [Source: `artifact/planning-artifacts/prd/functional-requirements.md` (FR10, FR14)]
- [Source: `artifact/planning-artifacts/prd/non-functional-requirements.md` (NFR-P5)]
- [Source: `artifact/planning-artifacts/architecture.md` (Topology & Ownership mapping)]
- [Source: `artifact/project-context.md`]
- [Source: `artifact/implementation-artifacts/3-1-topology-registry-loader-v0-and-v1-formats.md`]
- [Source: `src/aiops_triage_pipeline/registry/loader.py`]
- [Source: `src/aiops_triage_pipeline/pipeline/stages/gating.py`]
- [Source: `src/aiops_triage_pipeline/pipeline/scheduler.py`]
- [Source: `https://www.python.org/downloads/release/python-31312/`]
- [Source: `https://pypi.org/project/pydantic/`]
- [Source: `https://docs.pydantic.dev/latest/concepts/strict_mode/`]
- [Source: `https://pypi.org/project/PyYAML/`]
- [Source: `https://pyyaml.org/wiki/PyYAMLDocumentation`]

## Dev Agent Record

### Agent Model Used

GPT-5 Codex

### Debug Log References

- Workflow runner: `_bmad/core/tasks/workflow.xml` with config `_bmad/bmm/workflows/4-implementation/dev-story/workflow.yaml`.
- Story selected from `artifact/implementation-artifacts/sprint-status.yaml` as first `ready-for-dev` story in order.
- Red phase: added resolver/topology tests first and confirmed import failures before implementation.
- Implemented resolver contracts + lookup logic in `src/aiops_triage_pipeline/registry/resolver.py`.
- Implemented Stage 3 context assembly and unresolved propagation in `src/aiops_triage_pipeline/pipeline/stages/topology.py`.
- Added Stage 3 integration readiness helper in `src/aiops_triage_pipeline/pipeline/scheduler.py`.
- Senior developer review fixed unresolved-scope gate-input crash by filtering unresolved scopes before Stage 6 assembly in scheduler flow.
- Senior developer review propagated resolver `source_system` into Stage 3 `GateInputContext` for contract continuity.
- Noted workspace-level unrelated modification in `artifact/implementation-artifacts/3-1-topology-registry-loader-v0-and-v1-formats.md` (not part of Story 3.2 implementation scope).
- Follow-up review hardening: loader now fails fast on non-string optional topology fields and non-string `topics` mapping values.
- Follow-up review bookkeeping: Story 3.2 File List now includes the modified Story 3.1 artifact for git/story parity.
- Validation commands executed:
  - `uv run pytest -q tests/unit/registry/test_loader.py tests/unit/registry/test_resolver.py tests/unit/pipeline/stages/test_topology.py tests/unit/pipeline/test_scheduler.py tests/unit/pipeline/test_scheduler_topology.py` (40 passed)
  - `uv run pytest -q` (283 passed)
  - `uv run ruff check` (all checks passed)

### Implementation Plan

- Added immutable `TopologyResolution` output with explicit `resolved`/`unresolved` status and reason codes.
- Implemented deterministic resolver flow: parse scope -> scoped `topic_index` lookup -> stream lookup -> topic-role normalization -> criticality/source-system derivation.
- Added Stage 3 assembly to build `GateInputContext` by scope and preserve unresolved diagnostics for downstream handling.
- Wired scheduler helper (`run_topology_stage_cycle`) without changing existing Stage 1/2/6 execution paths.
- Added focused unit coverage for success paths, cross-cluster scoping, unresolved reason codes, and latency p99 threshold.

### Completion Notes List

- Implemented immutable topology resolution contracts with explicit unresolved semantics and typed diagnostics.
- Added scoped topology resolution against `topic_index_by_scope[(env, cluster_id)]` with deterministic topic-role normalization.
- Added stream/source-derived metadata resolution (`stream_id`, `criticality_tier`, `source_system`) for topic and group anomaly scopes.
- Added Stage 3 topology assembly output with `GateInputContext` maps and unresolved tracking for downstream visibility.
- Added scheduler Stage 3 helper invocation point and stage exports for integration readiness.
- Preserved `source_system` in `GateInputContext` so Stage 3 does not drop resolver metadata needed for downstream routing context.
- Prevented unresolved topology scopes from crashing Stage 6 assembly by skipping unresolved scopes with explicit scheduler warning logs.
- Added and passed targeted unit tests for resolver/stage behavior and p99 latency bound checks.
- Passed full regression suite and lint checks; no regressions introduced.

### File List

- `src/aiops_triage_pipeline/registry/resolver.py`
- `src/aiops_triage_pipeline/registry/__init__.py`
- `src/aiops_triage_pipeline/registry/loader.py`
- `src/aiops_triage_pipeline/pipeline/stages/topology.py`
- `src/aiops_triage_pipeline/pipeline/stages/__init__.py`
- `src/aiops_triage_pipeline/pipeline/stages/gating.py`
- `src/aiops_triage_pipeline/pipeline/scheduler.py`
- `tests/unit/registry/test_resolver.py`
- `tests/unit/registry/test_loader.py`
- `tests/unit/pipeline/stages/test_topology.py`
- `tests/unit/pipeline/test_scheduler.py`
- `tests/unit/pipeline/test_scheduler_topology.py`
- `artifact/implementation-artifacts/3-1-topology-registry-loader-v0-and-v1-formats.md`
- `artifact/implementation-artifacts/3-2-stream-resolution-and-topic-role-classification.md`
- `artifact/implementation-artifacts/sprint-status.yaml`

### Senior Developer Review (AI)

- **Review date:** 2026-03-04
- **Outcome:** Changes Requested → Fixed
- **High findings fixed:**
  - Unresolved scopes previously caused Stage 6 `KeyError`; scheduler now skips unresolved scopes and logs `scheduler.gate_input_scope_skipped_unresolved`.
  - `source_system` returned by resolver is now preserved in Stage 3 context (`GateInputContext.source_system`).
- **Medium findings fixed:**
  - Story File List updated to include all Story 3.2 code/test changes touched in git.
  - Story status metadata normalized to reflect completed implementation and review.
  - Loader now fails fast (typed validation error) on non-string optional string fields in topology YAML.
  - Loader now fails fast (typed validation error) on non-string entries in `topics` string mappings.
- **Low findings fixed:**
  - Validation metadata refreshed to current run results (`40 passed` targeted suite, `283 passed` full suite) to keep review evidence accurate.

### Change Log

- 2026-03-04: Implemented Story 3.2 topology resolver and Stage 3 assembly, added scheduler readiness helper, added resolver/topology tests with latency assertion, and passed targeted/full quality gates.
- 2026-03-04: Applied senior developer review fixes: preserved `source_system` through Stage 3 context, prevented unresolved-scope Stage 6 crashes, expanded test coverage, and synchronized story metadata/file list.
- 2026-03-04: Applied follow-up review hardening: strict fail-fast validation for optional string fields and `topics` mappings in topology loader; updated Story 3.2 File List for git/story parity; reran targeted and full quality gates.
