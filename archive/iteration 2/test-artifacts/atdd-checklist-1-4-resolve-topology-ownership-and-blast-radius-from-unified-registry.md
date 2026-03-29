---
stepsCompleted:
  - step-01-preflight-and-context
  - step-02-generation-mode
  - step-03-test-strategy
  - step-04c-aggregate
  - step-05-validate-and-complete
lastStep: step-05-validate-and-complete
lastSaved: '2026-03-22T15-23-28Z'
workflowType: testarch-atdd
inputDocuments:
  - artifact/implementation-artifacts/1-4-resolve-topology-ownership-and-blast-radius-from-unified-registry.md
  - pyproject.toml
  - tests/conftest.py
  - src/aiops_triage_pipeline/config/settings.py
  - src/aiops_triage_pipeline/registry/loader.py
  - src/aiops_triage_pipeline/registry/resolver.py
  - src/aiops_triage_pipeline/pipeline/stages/topology.py
  - src/aiops_triage_pipeline/pipeline/scheduler.py
  - tests/unit/registry/test_loader.py
  - tests/unit/registry/test_resolver.py
  - tests/unit/pipeline/stages/test_topology.py
  - tests/unit/pipeline/test_scheduler_topology.py
  - _bmad/tea/testarch/knowledge/data-factories.md
  - _bmad/tea/testarch/knowledge/component-tdd.md
  - _bmad/tea/testarch/knowledge/test-quality.md
  - _bmad/tea/testarch/knowledge/test-healing-patterns.md
  - _bmad/tea/testarch/knowledge/test-levels-framework.md
  - _bmad/tea/testarch/knowledge/test-priorities-matrix.md
  - _bmad/tea/testarch/knowledge/ci-burn-in.md
  - _bmad/tea/testarch/knowledge/overview.md
  - _bmad/tea/testarch/knowledge/api-request.md
  - _bmad/tea/testarch/knowledge/auth-session.md
  - _bmad/tea/testarch/knowledge/recurse.md
  - _bmad/tea/testarch/knowledge/pactjs-utils-overview.md
  - _bmad/tea/testarch/knowledge/pactjs-utils-consumer-helpers.md
  - _bmad/tea/testarch/knowledge/pactjs-utils-provider-verifier.md
  - _bmad/tea/testarch/knowledge/pactjs-utils-request-filter.md
  - _bmad/tea/testarch/knowledge/pact-mcp.md
---

# ATDD Checklist - Epic 1, Story 4: Resolve Topology, Ownership, and Blast Radius from Unified Registry

**Date:** 2026-03-22
**Author:** Sas
**Primary Test Level:** API/Integration (backend)

---

## Story Summary

Story 1.4 requires topology/ownership resolution to be automatic, deterministic, and reloadable from a unified registry source. The red-phase ATDD suite encodes expected future behavior around canonical registry ownership resolution, fallback confidence metadata, and downstream blast-radius semantics.

**As an** on-call engineer  
**I want** topology and ownership resolution to be automatic and reloadable  
**So that** action routing and impact assessment are immediately available in triage results

---

## Acceptance Criteria

1. Given topology registry file in `config/` uses a single supported format, when Stage 3 resolves scope, then stream identity/topic role/blast radius resolve and downstream impacted consumers are identified.
2. Given topology registry contents change on disk, when loader detects change, then topology reloads without restart and ownership routing follows `consumer_group > topic > stream > platform default` with confidence scoring.

---

## Workflow Execution Log

### Step 1 - Preflight & Context

- Detected stack: `backend` (`pyproject.toml` + pytest test tree; no frontend/browser framework).
- Prerequisites: satisfied (story has testable ACs; pytest config present; dev environment available).
- Framework/pattern sources reviewed: `pyproject.toml`, `tests/conftest.py`, existing registry/topology unit tests.
- Knowledge profile loaded for backend ATDD: core + backend + Playwright-utils API-only subset + pact utilities as configured.

### Step 2 - Generation Mode

- Mode selected: `AI generation` (backend stack; no browser recording required).

### Step 3 - Test Strategy

- P0 scenarios:
  - Canonical topology registry runtime path defaulting behavior.
  - Enforce single supported registry schema at load time.
- P1 scenarios:
  - Ownership fallback output includes selected confidence metadata.
  - Downstream impact list excludes non-downstream source leakage.
- P2/P3: none defined for this red-phase slice.

### Step 4 - Generate + Aggregate

- Worker A output: `/tmp/tea-atdd-api-tests-2026-03-22T15-23-28Z.json` (4 backend red tests).
- Worker B output: `/tmp/tea-atdd-e2e-tests-2026-03-22T15-23-28Z.json` (0 tests; backend no browser E2E).
- Aggregation summary: `/tmp/tea-atdd-summary-2026-03-22T15-23-28Z.json`.
- Generated files written:
  - `tests/atdd/story_1_4_topology_registry_red_phase.py`
  - `tests/atdd/fixtures/story_1_4_test_data.py`

### Step 5 - Validate & Complete

- Red-phase verification run: `uv run pytest -q tests/atdd/story_1_4_topology_registry_red_phase.py -q`.
- Result: 4/4 tests failed as designed (RED phase confirmed).
- No checklist/template section left unpopulated; N/A fields explicitly marked.

---

## Failing Tests Created (RED Phase)

### API/Integration Tests (4 tests)

**File:** `tests/atdd/story_1_4_topology_registry_red_phase.py` (136 lines)

- ✅ **Test:** `test_p0_settings_default_topology_registry_path_points_to_canonical_config_file`
  - **Status:** RED - currently `Settings.TOPOLOGY_REGISTRY_PATH` defaults to `None`
  - **Verifies:** canonical runtime topology path defaults to `config/topology-registry.yaml`
- ✅ **Test:** `test_p0_loader_rejects_legacy_v1_registry_format`
  - **Status:** RED - loader currently accepts version `1`
  - **Verifies:** runtime loader enforces single supported topology schema
- ✅ **Test:** `test_p1_resolver_exposes_selected_owner_confidence_in_diagnostics`
  - **Status:** RED - diagnostics currently omit selected owner confidence
  - **Verifies:** confidence-aware ownership fallback output
- ✅ **Test:** `test_p1_resolver_downstream_impacts_only_list_downstream_components`
  - **Status:** RED - current impacts include `source` component
  - **Verifies:** downstream impact set aligns with downstream-only semantics

### E2E Tests (0 tests)

**File:** `N/A (backend stack)`

- Backend workflow selected API/integration-level acceptance tests only.

### Component Tests (0 tests)

**File:** `N/A`

- Not in scope for this backend story acceptance surface.

---

## Data Factories Created

### Topology Scope Factory

**File:** `tests/atdd/fixtures/story_1_4_test_data.py`

**Exports:**

- `TopologyScope` - typed scope tuple container
- `build_primary_scope()` - canonical scope fixture for Story 1.4 red tests

**Example Usage:**

```python
from tests.atdd.fixtures.story_1_4_test_data import build_primary_scope

scope = build_primary_scope()
assert scope.topic == "orders"
```

---

## Fixtures Created

### Story 1.4 ATDD Support Fixture

**File:** `tests/atdd/fixtures/story_1_4_test_data.py`

**Fixtures/Helpers:**

- `build_primary_scope` - returns deterministic `(env, cluster_id, topic)` inputs for red tests
  - **Setup:** constructs canonical scope object
  - **Provides:** stable scope data for test setup
  - **Cleanup:** none required (pure in-memory helper)

---

## Mock Requirements

N/A for current red-phase coverage. Tests use inline YAML fixtures and direct module calls; no external service mocking required.

---

## Required data-testid Attributes

N/A for backend-only Story 1.4.

---

## Implementation Checklist

### Test: P0 canonical topology registry path default

**File:** `tests/atdd/story_1_4_topology_registry_red_phase.py`

**Tasks to make this test pass:**

- [ ] Define canonical default topology path (`config/topology-registry.yaml`) in runtime settings/bootstrap.
- [ ] Ensure hot-path startup wiring reads the canonical path when env var is not set.
- [ ] Add/adjust configuration tests for canonical default behavior.
- [ ] Run test: `uv run pytest -q tests/atdd/story_1_4_topology_registry_red_phase.py -q`
- [ ] ✅ Test passes (green phase)

**Estimated Effort:** 1.5 hours

### Test: P0 reject legacy v1 topology registry format

**File:** `tests/atdd/story_1_4_topology_registry_red_phase.py`

**Tasks to make this test pass:**

- [ ] Update loader rules/runtime policy to support only unified schema for hot-path loading.
- [ ] Preserve typed validation errors with explicit category/context.
- [ ] Update loader tests/contracts for single-format behavior.
- [ ] Run test: `uv run pytest -q tests/atdd/story_1_4_topology_registry_red_phase.py -q`
- [ ] ✅ Test passes (green phase)

**Estimated Effort:** 2.0 hours

### Test: P1 ownership fallback confidence metadata surfaced

**File:** `tests/atdd/story_1_4_topology_registry_red_phase.py`

**Tasks to make this test pass:**

- [ ] Thread selected owner confidence from ownership map through resolver output.
- [ ] Include selected confidence in diagnostics or dedicated typed output field.
- [ ] Extend resolver/unit tests for confidence propagation across fallback levels.
- [ ] Run test: `uv run pytest -q tests/atdd/story_1_4_topology_registry_red_phase.py -q`
- [ ] ✅ Test passes (green phase)

**Estimated Effort:** 2.0 hours

### Test: P1 downstream impact semantics are downstream-only

**File:** `tests/atdd/story_1_4_topology_registry_red_phase.py`

**Tasks to make this test pass:**

- [ ] Refine downstream impact derivation semantics for source topic flows.
- [ ] Keep deterministic ordering of downstream impacts.
- [ ] Align stage/casefile integration assertions with refined impact semantics.
- [ ] Run test: `uv run pytest -q tests/atdd/story_1_4_topology_registry_red_phase.py -q`
- [ ] ✅ Test passes (green phase)

**Estimated Effort:** 1.5 hours

---

## Running Tests

```bash
# Run all failing tests for this story
uv run pytest -q tests/atdd/story_1_4_topology_registry_red_phase.py -q

# Run specific test
uv run pytest -q tests/atdd/story_1_4_topology_registry_red_phase.py::test_p0_loader_rejects_legacy_v1_registry_format -q

# Run verbose diagnostics
uv run pytest tests/atdd/story_1_4_topology_registry_red_phase.py -vv

# Run with max-fail=1 for rapid loop
uv run pytest tests/atdd/story_1_4_topology_registry_red_phase.py --maxfail=1 -q
```

---

## Red-Green-Refactor Workflow

### RED Phase (Complete) ✅

- ✅ Tests authored against expected Story 1.4 outcomes.
- ✅ Red verification executed; all 4 tests fail for implementation gaps (not syntax/test bugs).
- ✅ Implementation checklist prepared for green-phase execution.

### GREEN Phase (DEV Team - Next Steps)

1. Pick one failing P0 test.
2. Implement minimum production change to satisfy that assertion.
3. Re-run the same targeted test until green.
4. Repeat per remaining test in priority order.

### REFACTOR Guidance

- Keep topology resolution deterministic and contract-first.
- Preserve loud failures for invalid critical topology context.
- Maintain hot-path reload safety with last-known-good snapshots.

---

## Validation Notes

### Failure Evidence Captured

Execution command:

`uv run pytest -q tests/atdd/story_1_4_topology_registry_red_phase.py -q`

Observed red failures:

- `TOPOLOGY_REGISTRY_PATH` default is `None` (expected canonical path)
- loader does not reject legacy version `1`
- diagnostics missing `selected_owner_confidence`
- downstream impacts include `source` component beyond downstream-only expectation

### Risks / Assumptions

- Assumes Story 1.4 target behavior includes canonical default path when env var is unset.
- Assumes confidence metadata is expected in resolver output path (diagnostics or typed field).
- Assumes downstream-impact semantics should exclude source-origin entry for this story boundary.

---

## Next Steps for DEV Team

1. Implement Story 1.4 changes to satisfy the 4 red tests.
2. Convert this ATDD file into green assertions by making implementation pass unchanged tests.
3. After green, integrate/rename tests into normal discovery paths if desired.

**Output File:** `artifact/test-artifacts/atdd-checklist-1-4-resolve-topology-ownership-and-blast-radius-from-unified-registry.md`
