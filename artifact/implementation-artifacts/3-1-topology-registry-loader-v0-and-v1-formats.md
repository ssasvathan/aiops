# Story 3.1: Topology Registry Loader (v0 + v1 Formats)

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a platform developer,
I want the system to load topology registries in both v0 (legacy) and v1 (instances-based) formats and canonicalize them to a single in-memory model,
so that the pipeline supports both registry versions during migration with strict validation on load (FR9, FR15).

## Acceptance Criteria

1. **Given** a topology registry file exists in v0 or v1 format  
   **When** the registry is loaded at startup  
   **Then** both v0 (legacy) and v1 (instances-based) formats are parsed and canonicalized to a single in-memory model.

2. **And** the registry is loaded into memory for local lookups (no external calls at query time).

3. **And** loading fails fast on duplicate `topic_index` keys within the same `(env, cluster_id)` scope.

4. **And** loading fails fast on duplicate consumer-group ownership keys.

5. **And** loading fails fast on missing `routing_key` references.

6. **And** registry reload on change completes within 5 seconds (NFR-P5).

7. **And** unit tests verify: v0 loading, v1 loading, canonicalization produces identical in-memory model, and all three fail-fast validation scenarios.

## Tasks / Subtasks

- [x] Task 1: Define canonical in-memory topology model and loader API (AC: 1, 2)
  - [x] Implement typed canonical structures shared by v0/v1 parsing paths.
  - [x] Keep loader output immutable and safe for concurrent read access.
  - [x] Expose a single loader entrypoint returning canonical model plus metadata/version info.

- [x] Task 2: Implement v0 and v1 parsing with canonicalization (AC: 1)
  - [x] Parse v0 topology shape and map into canonical structures.
  - [x] Parse v1 instances-based shape and map into canonical structures.
  - [x] Ensure equivalent v0/v1 fixtures normalize to the same canonical representation.

- [x] Task 3: Implement fail-fast validation matrix (AC: 3, 4, 5)
  - [x] Detect duplicate `topic_index` keys in `(env, cluster_id)` scope.
  - [x] Detect duplicate consumer-group ownership keys.
  - [x] Detect missing `routing_key` references for resolved ownership entries.
  - [x] Raise explicit typed errors with actionable context; do not continue on invalid registry.

- [x] Task 4: Implement reload-on-change behavior (AC: 6)
  - [x] Add file-change detection/polling with deterministic refresh behavior.
  - [x] Ensure reload path swaps model atomically after successful validation.
  - [x] Ensure invalid reload input preserves last-known-good in-memory model and emits structured error logs.

- [x] Task 5: Add focused unit tests for loader and validation semantics (AC: 7)
  - [x] Add v0 fixture loading and canonical assertions.
  - [x] Add v1 fixture loading and canonical assertions.
  - [x] Add duplicate `topic_index` failure test.
  - [x] Add duplicate consumer-group ownership failure test.
  - [x] Add missing `routing_key` failure test.
  - [x] Add reload-timing and last-known-good preservation tests.

- [x] Task 6: Quality gates
  - [x] Run focused tests for `registry` and `contracts` packages.
  - [x] Run full `uv run pytest -q` and `uv run ruff check` before moving to review.

## Dev Notes

### Story Requirements

- This story implements the first Epic 3 capability and is foundational for FR9/FR15, with direct downstream impact on FR10-FR14 and FR16.
- Scope is intentionally narrow:
  - In scope: v0/v1 load and canonicalization, startup/reload validation, in-memory model readiness.
  - Out of scope: resolver/routing decisions (Story 3.2+), blast radius computation (Story 3.3), ownership fallback execution (Story 3.4), compatibility view output (Story 3.5).
- Epic 2 retrospective indicates specific prep expectations that should be incorporated in this story implementation:
  - canonical v0/v1 fixtures,
  - explicit fail-fast matrix,
  - realistic cross-cluster scoping examples.

### Developer Context Section

- Current implementation state confirms `registry/loader.py`, `registry/resolver.py`, and `pipeline/stages/topology.py` are empty placeholders.
- Contract-level guardrails already exist and should be reused instead of duplicated:
  - `TopologyRegistryLoaderRulesV1` in `src/aiops_triage_pipeline/contracts/topology_registry.py`.
  - policy artifact `config/policies/topology-registry-loader-rules-v1.yaml`.
- Architecture establishes `registry/` as the owned package for FR9-FR16, with `loader.py` providing canonicalization and `resolver.py` consuming that model in later stories.
- The loader must produce deterministic, typed, immutable structures so downstream stages can trust registry behavior without re-validation on every lookup.

### Technical Requirements

- Implement a single canonical internal model for topology entities needed by downstream resolution:
  - `env`, `cluster_id`, topic identity/index, stream metadata, ownership metadata, routing_key references.
- Canonicalization behavior must be deterministic:
  - stable key normalization,
  - stable ordering for serialized debug output/tests,
  - no reliance on incidental dict insertion ordering for semantic behavior.
- Validation must happen before model publication:
  - duplicate `topic_index` in same `(env, cluster_id)` is fatal,
  - duplicate consumer-group ownership key is fatal,
  - missing/unknown `routing_key` references are fatal.
- Loader error model must be explicit and actionable:
  - include source path, offending key, and validation category in exception/log metadata.
- Reload behavior must preserve service safety:
  - parse + validate candidate registry fully,
  - atomically swap to new model only on success,
  - keep last-known-good on failure.
- Runtime behavior requirement:
  - lookups must remain in-memory only after load (no network/filesystem calls per query path).

### Architecture Compliance

- Align with architecture package boundaries:
  - implement loading/canonicalization in `src/aiops_triage_pipeline/registry/loader.py`.
  - avoid stage-level direct file parsing in `pipeline/stages/*`.
- Preserve architecture intent for FR9/FR15:
  - support both v0 and v1 during migration,
  - enforce strict fail-fast loader validation,
  - keep one canonical model as single source of truth.
- Keep design consistent with project-wide invariants:
  - schema-first and immutable model approach,
  - no parallel abstractions for policy/validation logic,
  - structured logging with stable fields and correlation context.
- Performance and operability constraints to respect:
  - prepare loader/reload implementation to support <=5s refresh target,
  - ensure no hidden hot-path coupling that could violate later p99 lookup constraints.

### Library / Framework Requirements

- Python baseline: keep implementation compatible with project baseline (Python >=3.13).
- Pydantic contract discipline:
  - reuse existing frozen contract/policy patterns,
  - validate structured loader outputs at creation boundaries.
- YAML parsing safety:
  - use safe YAML loading semantics for untrusted file content,
  - do not use unsafe object-construction loaders.
- Dependency policy for this story:
  - do not introduce new parsing/watcher libraries unless strictly necessary,
  - prefer stdlib + existing dependencies to keep scope controlled.
- Logging/health integration:
  - use existing structured logging setup and health primitives,
  - do not create custom logging/event frameworks in loader code.

### File Structure Requirements

- Primary implementation files:
  - `src/aiops_triage_pipeline/registry/loader.py`
  - `src/aiops_triage_pipeline/registry/__init__.py` (exports for loader surface if needed)
- Supporting contract/policy touchpoints (reuse, avoid redefining):
  - `src/aiops_triage_pipeline/contracts/topology_registry.py`
  - `config/policies/topology-registry-loader-rules-v1.yaml`
- Story-boundary note:
  - `src/aiops_triage_pipeline/registry/resolver.py` and `src/aiops_triage_pipeline/pipeline/stages/topology.py` should remain minimal/placeholders for this story unless required for wiring tests only.
- Expected test files:
  - `tests/unit/registry/test_loader.py` (new)
  - `tests/unit/contracts/test_policy_models.py` (update if contract interaction edge cases are added)
  - optional fixture module under `tests/unit/registry/fixtures/` for v0/v1 canonical equivalence datasets.

### Testing Requirements

- Unit tests must prove functional AC coverage:
  - v0 fixture loads successfully into canonical model,
  - v1 fixture loads successfully into canonical model,
  - equivalent v0/v1 datasets canonicalize identically,
  - duplicate `topic_index` within `(env, cluster_id)` fails fast,
  - duplicate consumer-group ownership key fails fast,
  - missing `routing_key` reference fails fast.
- Reload behavior tests:
  - successful change reload completes within target budget in controlled test conditions,
  - invalid reload input preserves last-known-good snapshot,
  - structured error logging emitted for failed reload.
- Non-regression tests:
  - existing contract tests remain green,
  - no unintended behavior introduced into scheduler/evidence/gating stages.
- Required verification commands before review:
  - `uv run pytest -q tests/unit/registry/test_loader.py tests/unit/contracts/test_policy_models.py`
  - `uv run pytest -q`
  - `uv run ruff check`

### Latest Tech Information

Verification date: **March 4, 2026**.

- **Python runtime line:**
  - Python.org shows **Python 3.13.12** (released February 3, 2026) as the latest 3.13 maintenance release.
  - Python.org also notes 3.14.x is the latest feature series.
  - Implementation implication: keep project runtime on 3.13 for stability, but assume latest 3.13 patch-level behavior in local/dev environments.

- **Pydantic:**
  - Pydantic GitHub releases show **v2.12.5** (November 26, 2025) as latest release at verification time.
  - This matches the project-pinned baseline in planning artifacts/project context.
  - Implementation implication: no version migration needed for Story 3.1; continue frozen-model + explicit validation pattern.

- **PyYAML:**
  - PyPI lists **PyYAML 6.0.3** (September 25, 2025) as latest release.
  - Project uses `pyyaml~=6.0`, which is compatible with 6.0.3.
  - PyYAML documentation warns that `yaml.load` is unsafe for untrusted input and recommends `yaml.safe_load`.
  - Implementation implication: registry loader should use safe loading semantics by default and avoid unsafe loaders.

- **Pydantic strictness behavior (for loader validation hardening):**
  - Official docs show strict mode can be enabled per-validation call, field, or model config.
  - Implementation implication (inference): for registry schema/contract validation paths, use strict validation in high-risk boundaries to avoid silent coercion masking malformed registry inputs.

### Project Context Reference

Mandatory guardrails from `artifact/project-context.md` that directly apply:

- Keep contract/policy models immutable and validated at boundaries.
- Keep `config` package generic/leaf and avoid coupling loader code to unrelated modules.
- Use structured logging primitives; avoid ad-hoc unstructured error reporting.
- Keep async/concurrency safety explicit when swapping shared registry snapshots.
- Never bypass deterministic guardrails or introduce silent fallback for critical validation errors.
- Add/update targeted tests for loader behavior and failure paths in the same change set.

### Story Completion Status

- Story context generation complete.
- Story file created at `artifact/implementation-artifacts/3-1-topology-registry-loader-v0-and-v1-formats.md`.
- Status set to `ready-for-dev`.
- Completion note: **Ultimate context engine analysis completed - comprehensive developer guide created**.

## Project Structure Notes

- Keep Story 3.1 changes localized to registry loading and validation concerns.
- Avoid implementing full routing resolution logic in this story; that belongs to Story 3.2+.
- Ensure canonical model design anticipates upcoming FR10-FR14 needs so later stories extend, not rewrite, the loader.

## References

- [Source: `artifact/planning-artifacts/epics.md#Epic 3: Topology Resolution & Case Routing`]
- [Source: `artifact/planning-artifacts/epics.md#Story 3.1: Topology Registry Loader (v0 + v1 Formats)`]
- [Source: `artifact/planning-artifacts/prd/functional-requirements.md` (FR9, FR15)]
- [Source: `artifact/planning-artifacts/prd/non-functional-requirements.md` (NFR-P5)]
- [Source: `artifact/planning-artifacts/architecture.md` (Topology & Ownership architecture mapping and package ownership)]
- [Source: `artifact/project-context.md`]
- [Source: `artifact/implementation-artifacts/epic-2-retro-2026-03-04.md` (Epic 3 preparation tasks)]
- [Source: `src/aiops_triage_pipeline/contracts/topology_registry.py`]
- [Source: `config/policies/topology-registry-loader-rules-v1.yaml`]
- [Source: `src/aiops_triage_pipeline/registry/loader.py`]
- [Source: `src/aiops_triage_pipeline/registry/resolver.py`]
- [Source: `src/aiops_triage_pipeline/pipeline/stages/topology.py`]
- [Source: `https://www.python.org/downloads/release/python-31312/`]
- [Source: `https://github.com/pydantic/pydantic/releases`]
- [Source: `https://pypi.org/project/PyYAML/`]
- [Source: `https://pyyaml.org/wiki/PyYAMLDocumentation`]
- [Source: `https://docs.pydantic.dev/latest/concepts/strict_mode/`]

## Dev Agent Record

### Agent Model Used

GPT-5 Codex

### Debug Log References

- Workflow runner: `_bmad/core/tasks/workflow.xml` with config `_bmad/bmm/workflows/4-implementation/dev-story/workflow.yaml`.
- Story selected from `artifact/implementation-artifacts/sprint-status.yaml` as first `ready-for-dev` item in development order.
- Implemented `src/aiops_triage_pipeline/registry/loader.py` with:
  - immutable canonical topology models for streams/instances/topic index,
  - v0 + v1 parsing and deterministic canonicalization,
  - strict fail-fast validation and typed errors with context,
  - reload manager preserving last-known-good model on invalid changes.
- Added public exports in `src/aiops_triage_pipeline/registry/__init__.py`.
- Added focused tests in `tests/unit/registry/test_loader.py` for v0/v1 load, canonical equivalence, fail-fast matrix, and reload behavior.
- Validation commands executed successfully:
  - `uv run pytest -q tests/unit/registry/test_loader.py tests/unit/contracts/test_policy_models.py` (36 passed)
  - `uv run pytest -q` (265 passed, 1 skipped)
  - `uv run ruff check` (all checks passed)

### Completion Notes List

- Implemented topology registry loader with a single canonical in-memory model and metadata-returning entrypoint for v0/v1 registries.
- Added strict validation matrix for duplicate scoped `topic_index`, duplicate consumer-group ownership keys, and missing `routing_key` references.
- Implemented reload-on-change path with atomic snapshot swap and structured failure logging while preserving last-known-good state.
- Added 10 focused unit tests for AC coverage, including canonical equivalence and reload timing/preservation behavior.
- Verified non-regression and quality gates with full test suite and lint checks.

### File List

- `src/aiops_triage_pipeline/registry/loader.py`
- `src/aiops_triage_pipeline/registry/__init__.py`
- `tests/unit/registry/test_loader.py`
- `artifact/implementation-artifacts/3-1-topology-registry-loader-v0-and-v1-formats.md`
- `artifact/implementation-artifacts/sprint-status.yaml`

### Change Log

- 2026-03-04: Implemented Story 3.1 loader/canonicalization/validation/reload and added focused registry tests; passed full repo quality gates.
- 2026-03-04: Senior code review fixes applied for rule-driven validation and strict ownership confidence parsing; story moved to done.

### Senior Developer Review (AI)

- Reviewer: Sas
- Date: 2026-03-04
- Outcome: Changes Requested (resolved in this review pass)

#### Findings

1. **HIGH** - Loader rules from `TopologyRegistryLoaderRulesV1` were partially ignored at runtime (`routing_key_required`, `fail_on_unknown_topic_role` had no behavioral effect), so policy toggles in `config/policies/topology-registry-loader-rules-v1.yaml` were not enforceable.
2. **MEDIUM** - Ownership confidence parsing silently coerced malformed values to `None`, masking malformed registry input instead of failing fast with typed context.
3. **MEDIUM** - Canonical equivalence testing asserted only selected subsets of the canonical model; this allowed regressions in unasserted fields.

#### Fixes Applied

- Updated loader to apply rule-driven behavior:
  - `routing_key_required` now gates missing routing-key enforcement.
  - `fail_on_unknown_topic_role` now enforces an explicit known role set and fails fast when enabled.
- Updated ownership confidence parsing to raise `TopologyRegistryValidationError` on invalid non-float values with specific offending keys.
- Expanded unit tests to cover:
  - full canonical model equivalence for equivalent v0/v1 fixtures,
  - missing routing-key behavior when `routing_key_required=False`,
  - strict unknown-topic-role behavior when `fail_on_unknown_topic_role=True`,
  - invalid confidence failure semantics.
- Verification run after fixes:
  - `uv run pytest -q tests/unit/registry/test_loader.py` (13 passed)
  - `uv run pytest -q tests/unit/contracts/test_policy_models.py` (26 passed)
  - `uv run pytest -q` (268 passed, 1 skipped)
  - `uv run ruff check src/aiops_triage_pipeline/registry/loader.py src/aiops_triage_pipeline/registry/__init__.py tests/unit/registry/test_loader.py` (all checks passed)
