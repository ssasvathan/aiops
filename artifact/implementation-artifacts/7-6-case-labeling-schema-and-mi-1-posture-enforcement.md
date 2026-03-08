# Story 7.6: Case Labeling Schema & MI-1 Posture Enforcement

Status: review

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a platform developer,
I want the CaseFile schema to support case labeling fields and automated MI creation to be provably impossible,
so that the Phase 2 labeling workflow has its schema foundation ready and the system maintains MI-1 posture at all times (FR63, FR64, FR67b).

## Acceptance Criteria

1. **Given** the CaseFile schema includes labeling fields
   **When** labeling data is considered
   **Then** the schema supports typed fields: `owner_confirmed`, `resolution_category`, `false_positive`, `missing_evidence_reason` (FR63)

2. **And** `labels.json` stage file can be written to `cases/{case_id}/labels.json` following the append-only pattern using the existing `persist_casefile_labels_write_once()` function

3. **And** label data quality validation rules are defined: completion rate >= 70% for eligible cases, consistency checks for key labels (FR64)

4. **And** label validation is implementable but the operator capture workflow is explicitly deferred to Phase 2 (schema and constants ready; no runtime enforcement in Phase 1)

5. **Given** the system interacts with ServiceNow
   **When** any automated process executes
   **Then** no automated process creates Major Incident (MI) objects in ServiceNow (FR67b)

6. **And** `ServiceNowLinkageContractV1.mi_creation_allowed` defaults to `False` and is enforced by the frozen contract

7. **And** an automated test verifies MI creation is impossible through any code path in `integrations/servicenow.py`

8. **And** unit tests verify: labeling schema field presence and typed validation, `labels.json` write capability via `persist_casefile_labels_write_once`, MI-1 posture

## Tasks / Subtasks

- [x] Task 1: Add `CaseFileLabelDataV1` typed model and update `CaseFileLabelsV1` schema (AC: 1, 2)
  - [x] In `src/aiops_triage_pipeline/models/case_file.py`, add `CaseFileLabelDataV1` model above `CaseFileLabelsV1`:
    - `owner_confirmed: bool | None = None`
    - `resolution_category: str | None = None`
    - `false_positive: bool | None = None`
    - `missing_evidence_reason: str | None = None`
    - Must be `frozen=True`
  - [x] Replace `labels: dict[str, str]` in `CaseFileLabelsV1` with `label_data: CaseFileLabelDataV1`
  - [x] Add label quality constants: `LABEL_COMPLETION_RATE_THRESHOLD: float = 0.70` and `LABEL_ELIGIBLE_FIELDS: tuple[str, ...] = ("owner_confirmed", "resolution_category", "false_positive")`
  - [x] Export `CaseFileLabelDataV1` from `src/aiops_triage_pipeline/models/__init__.py`

- [x] Task 2: Update existing test helpers that construct `CaseFileLabelsV1` (AC: 2)
  - [x] In `tests/unit/storage/test_casefile_io.py`, update `_sample_casefile_labels()` to use `label_data=CaseFileLabelDataV1(owner_confirmed=True, resolution_category="UNKNOWN")` instead of `labels={"owner_confirmed": "true", "resolution_category": "UNKNOWN"}`
  - [x] In `tests/unit/pipeline/stages/test_casefile.py`, update the `_make_labels_casefile()` helper (approx. line 325–332) similarly
  - [x] Run `uv run pytest -q -m "not integration"` to confirm zero breakage

- [x] Task 3: Create `tests/unit/models/` package and comprehensive label + MI-1 posture test file (AC: 1, 3, 5, 6, 7, 8)
  - [x] Create `tests/unit/models/__init__.py` (empty)
  - [x] Create `tests/unit/models/test_case_file_labels.py` with:
    - `test_label_data_has_required_fields`: assert `CaseFileLabelDataV1` has `owner_confirmed`, `resolution_category`, `false_positive`, `missing_evidence_reason`
    - `test_label_data_fields_typed_correctly`: `owner_confirmed` and `false_positive` are `bool | None`, `resolution_category` and `missing_evidence_reason` are `str | None`
    - `test_label_data_is_frozen`: mutation of `CaseFileLabelDataV1` instance raises `ValidationError`
    - `test_labels_v1_uses_label_data_model`: `CaseFileLabelsV1` has `label_data` field of type `CaseFileLabelDataV1`
    - `test_labels_v1_is_frozen`: mutation of `CaseFileLabelsV1` instance raises `ValidationError`
    - `test_label_completion_rate_threshold_is_seventy_percent`: `LABEL_COMPLETION_RATE_THRESHOLD == 0.70`
    - `test_label_eligible_fields_are_defined`: `LABEL_ELIGIBLE_FIELDS` contains `owner_confirmed`, `resolution_category`, `false_positive`
    - `test_labels_json_write_once_creates_file`: construct a valid `CaseFileLabelsV1` with real hash and call `persist_casefile_labels_write_once()` using `_FakeObjectStoreClient` (import pattern from `test_casefile_io.py`); assert result path is `cases/{case_id}/labels.json` and write_result is `"created"`
    - `test_labels_json_idempotent_write_returns_idempotent`: call `persist_casefile_labels_write_once()` twice; second call returns `write_result="idempotent"`
    - `test_mi_creation_not_allowed_by_default`: `ServiceNowLinkageContractV1().mi_creation_allowed is False`
    - `test_mi_creation_contract_is_frozen`: attempt to set `mi_creation_allowed` on a frozen `ServiceNowLinkageContractV1` raises `ValidationError`
    - `test_servicenow_integration_has_no_create_major_incident`: `hasattr(aiops_triage_pipeline.integrations.servicenow, "create_major_incident")` is `False`

- [x] Task 4: Run quality gates with zero-skip posture (AC: 1–8)
  - [x] `uv run ruff check`
  - [x] `uv run pytest -q -m "not integration"`
  - [x] `TESTCONTAINERS_RYUK_DISABLED=true DOCKER_HOST=unix://$HOME/.docker/desktop/docker.sock uv run pytest -q -rs`
  - [x] Verify full run reports `0 skipped`

## Dev Notes

### Developer Context Section

- Story key: `7-6-case-labeling-schema-and-mi-1-posture-enforcement`
- Story ID: `7.6`
- Epic context: Epic 7 — Governance, Audit & Operational Observability. This is the final story (6 of 6) in Epic 7. It closes the Phase 1A governance closure by (a) converting the generic `labels: dict[str, str]` in `CaseFileLabelsV1` to a proper typed model with the 4 required labeling fields (FR63), (b) defining label quality constants for future use (FR64), and (c) asserting MI-1 posture through automated tests (FR67b).
- Dependency context:
  - `CaseFileLabelsV1` in `models/case_file.py` (line 162) currently uses `labels: dict[str, str]` — Story 7.6 replaces this with `label_data: CaseFileLabelDataV1`.
  - `persist_casefile_labels_write_once()` in `storage/casefile_io.py` already exists and is fully functional — do NOT modify it.
  - `compute_casefile_labels_hash()` and `LABELS_HASH_PLACEHOLDER` in `models/case_file.py` are already defined and in use — do NOT change.
  - `ServiceNowLinkageContractV1.mi_creation_allowed: bool = False` is already defined in `contracts/sn_linkage.py` — no changes needed to that file.
  - `integrations/servicenow.py` is already an empty stub (1 line, no functions) — no changes needed.
  - Two existing test helpers use the old `labels=dict(...)` constructor and MUST be updated: `tests/unit/storage/test_casefile_io.py:_sample_casefile_labels()` (line ~174–186) and `tests/unit/pipeline/stages/test_casefile.py:_make_labels_casefile()` (line ~324–332).

**Critical implementation note — field rename impact:**
Renaming `labels: dict[str, str]` → `label_data: CaseFileLabelDataV1` is a **breaking schema change**. Pydantic will reject old `labels={}` construction. The two existing test helpers that use the old field name will cause `ValidationError` at test runtime if not updated. Update BOTH before running tests. Search for `labels={"owner_confirmed"` in the codebase to find all occurrences.

**Critical implementation note — `_FakeObjectStoreClient` reuse:**
The `_FakeObjectStoreClient` class in `tests/unit/storage/test_casefile_io.py` is NOT exported — it's a local test helper. For `test_case_file_labels.py`, either:
- Import directly via relative path (if pytest allows), OR
- Inline a minimal fake client (copy the relevant methods — `put_if_absent` and `get_object_bytes`) since it's a small class
The latter is safer. The fake client is 30 lines and straightforward.

**Label quality constants — placement:**
Add `LABEL_COMPLETION_RATE_THRESHOLD` and `LABEL_ELIGIBLE_FIELDS` as module-level constants in `models/case_file.py` immediately above the `CaseFileLabelDataV1` class definition. These are schema-layer constants, not enforcement logic.

### Technical Requirements

1. **`CaseFileLabelDataV1` model (AC: 1):**
   - Location: `src/aiops_triage_pipeline/models/case_file.py`, immediately above `CaseFileLabelsV1`
   - `class CaseFileLabelDataV1(BaseModel, frozen=True):`
   - Fields (all optional since Phase 2 captures these):
     - `owner_confirmed: bool | None = None`
     - `resolution_category: str | None = None`
     - `false_positive: bool | None = None`
     - `missing_evidence_reason: str | None = None`
   - No validators needed — all fields are optional primitives
   - No imports needed beyond `pydantic.BaseModel`

2. **`CaseFileLabelsV1` update (AC: 1, 2):**
   - Replace `labels: dict[str, str]` with `label_data: CaseFileLabelDataV1`
   - The hash validators (`_validate_required_hash_fields`, `_validate_optional_diagnosis_hash`) remain UNCHANGED
   - The existing hash computation (`compute_casefile_labels_hash`, `LABELS_HASH_PLACEHOLDER`) works correctly — `_compute_casefile_hash` operates on `model_dump(mode="json")` which includes the nested `label_data` dict

3. **Label quality constants (AC: 3, 4):**
   ```python
   # Label data quality thresholds (FR64) — enforcement deferred to Phase 2
   LABEL_COMPLETION_RATE_THRESHOLD: float = 0.70
   LABEL_ELIGIBLE_FIELDS: tuple[str, ...] = (
       "owner_confirmed",
       "resolution_category",
       "false_positive",
   )
   ```
   Place these in `models/case_file.py` above `CaseFileLabelDataV1`.

4. **`models/__init__.py` export (AC: 1):**
   - Add `CaseFileLabelDataV1` to the import list and `__all__` in `src/aiops_triage_pipeline/models/__init__.py`
   - Follow the existing pattern for `CaseFileLabelsV1` in that file

5. **MI-1 posture tests (AC: 5, 6, 7):**
   - `test_servicenow_integration_has_no_create_major_incident`: import `aiops_triage_pipeline.integrations.servicenow` module and assert `not hasattr(module, "create_major_incident")`. This is the automated test that verifies no MI creation code path exists.
   - The `servicenow.py` integration file is intentionally a stub — it has 1 line (likely just an empty module or a comment). Do not add any code to it.

### Architecture Compliance

- `CaseFileLabelDataV1` is an internal domain model — it belongs in `models/case_file.py` alongside `CaseFileTriageV1`, `CaseFileDiagnosisV1`, `CaseFileLinkageV1`, and `CaseFileLabelsV1`
- Keep `frozen=True` on `CaseFileLabelDataV1` — consistent with all other CaseFile stage models (frozen contract discipline, architecture decision 3B)
- Do NOT add any label validation enforcement logic — Phase 2 work only; constants defined here are schema-layer hints
- Do NOT modify `casefile_io.py` — the `persist_casefile_labels_write_once()` function works with any `CaseFileLabelsV1` regardless of its `label_data` field structure
- Do NOT import `CaseFileLabelDataV1` in `contracts/` — it is an internal model, not a frozen contract
- The `ServiceNowLinkageContractV1` in `contracts/sn_linkage.py` requires NO changes — MI-1 posture is already structurally enforced
- Import graph: `models/case_file.py` imports from `contracts/`, `pydantic` — adding `CaseFileLabelDataV1` doesn't change the import graph

### Library / Framework Requirements

Pinned versions — no new dependencies:
- `pydantic==2.12.5` — `CaseFileLabelDataV1` uses standard `BaseModel, frozen=True` with primitive optional fields
- `pytest==9.0.2` — test helpers using `_FakeObjectStoreClient` pattern
- `pytest-asyncio==1.3.0` — no async in this story, but it's the test runner

Implementation patterns to follow:
- `CaseFileLabelDataV1` follows the same pattern as `CaseFileDownstreamImpact` and `CaseFileRoutingContext` — nested frozen models inside `case_file.py`
- `_FakeObjectStoreClient` pattern for labels.json write test: copy from `tests/unit/storage/test_casefile_io.py` (the class starting at line ~246)
- Test for schema field presence: use `CaseFileLabelDataV1.model_fields` dict to verify field names and annotations

### File Structure Requirements

New files to create:
- `tests/unit/models/__init__.py` (empty — new test package)
- `tests/unit/models/test_case_file_labels.py` (labeling schema, labels.json write, MI-1 posture tests)

Existing files to modify:
- `src/aiops_triage_pipeline/models/case_file.py` — add `LABEL_COMPLETION_RATE_THRESHOLD`, `LABEL_ELIGIBLE_FIELDS` constants, add `CaseFileLabelDataV1` model, update `CaseFileLabelsV1.labels` → `label_data`
- `src/aiops_triage_pipeline/models/__init__.py` — export `CaseFileLabelDataV1`
- `tests/unit/storage/test_casefile_io.py` — update `_sample_casefile_labels()` helper (line ~179–186)
- `tests/unit/pipeline/stages/test_casefile.py` — update labels helper (line ~325–332)

Files to NOT touch:
- `src/aiops_triage_pipeline/storage/casefile_io.py` — already fully implemented; `persist_casefile_labels_write_once()` is complete
- `src/aiops_triage_pipeline/contracts/sn_linkage.py` — `mi_creation_allowed: bool = False` already correct
- `src/aiops_triage_pipeline/integrations/servicenow.py` — intentional stub; no code to add
- `src/aiops_triage_pipeline/models/case_file.py:LABELS_HASH_PLACEHOLDER` — do NOT change or remove
- Any `contracts/*.py` — frozen contracts are final; this story adds an internal model only

### Testing Requirements

**New test file `tests/unit/models/test_case_file_labels.py`:**

| Test | What it verifies |
|------|-----------------|
| `test_label_data_has_required_fields` | `CaseFileLabelDataV1.model_fields` contains all 4 required field names |
| `test_label_data_fields_typed_correctly` | `owner_confirmed` and `false_positive` annotations include `bool`; `resolution_category` and `missing_evidence_reason` annotations include `str` |
| `test_label_data_is_frozen` | Mutation of `CaseFileLabelDataV1` instance raises `ValidationError` |
| `test_labels_v1_uses_label_data_model` | `CaseFileLabelsV1.model_fields["label_data"].annotation` is `CaseFileLabelDataV1` |
| `test_labels_v1_is_frozen` | Mutation of `CaseFileLabelsV1` instance raises `ValidationError` |
| `test_label_completion_rate_threshold_is_seventy_percent` | `LABEL_COMPLETION_RATE_THRESHOLD == 0.70` |
| `test_label_eligible_fields_are_defined` | `LABEL_ELIGIBLE_FIELDS` is a tuple containing `"owner_confirmed"`, `"resolution_category"`, `"false_positive"` |
| `test_labels_json_write_once_creates_file` | `persist_casefile_labels_write_once()` writes `cases/{case_id}/labels.json`; `write_result == "created"` |
| `test_labels_json_idempotent_write_returns_idempotent` | Second identical write returns `write_result == "idempotent"` |
| `test_mi_creation_not_allowed_by_default` | `ServiceNowLinkageContractV1().mi_creation_allowed is False` |
| `test_mi_creation_contract_is_frozen` | Setting `mi_creation_allowed` on frozen instance raises `ValidationError` |
| `test_servicenow_integration_has_no_create_major_incident` | `not hasattr(servicenow_module, "create_major_incident")` |

**Test construction pattern for labels.json write tests:**
```python
from aiops_triage_pipeline.models.case_file import (
    CaseFileLabelDataV1, CaseFileLabelsV1, LABELS_HASH_PLACEHOLDER
)
from aiops_triage_pipeline.storage.casefile_io import (
    compute_casefile_labels_hash, persist_casefile_labels_write_once
)

def _make_labels_casefile(*, case_id: str = "case-abc-123") -> CaseFileLabelsV1:
    base = CaseFileLabelsV1(
        case_id=case_id,
        label_data=CaseFileLabelDataV1(owner_confirmed=True, resolution_category="FALSE_POSITIVE"),
        triage_hash="a" * 64,
        labels_hash=LABELS_HASH_PLACEHOLDER,
    )
    return base.model_copy(update={"labels_hash": compute_casefile_labels_hash(base)})
```

**Key invariants:**
- All new tests are pure unit tests (no containers, no object storage, no external calls)
- Use inline `_FakeObjectStoreClient` (copy from `test_casefile_io.py`) for labels.json write tests
- Preserve zero-skip discipline; all tests must pass without `@pytest.mark.skip`
- Do NOT use `AsyncMock` — no async in this story

**Quality gate commands:**
- `uv run ruff check`
- `uv run pytest -q -m "not integration"`
- `TESTCONTAINERS_RYUK_DISABLED=true DOCKER_HOST=unix://$HOME/.docker/desktop/docker.sock uv run pytest -q -rs`

### Previous Story Intelligence

From Story 7.5 (`7-5-exposure-denylist-governance-and-llm-narrative-compliance.md`):
- Baseline: 719 unit tests, 0 skipped; 737 full suite, 0 skipped
- Frozen model pattern with optional nested fields is well-established (`DenylistChangelogEntry`, `DenylistV1`)
- `_make_mock_store()` / `_FakeObjectStoreClient` patterns are the preferred approach for testing I/O functions
- Code review findings: always add ISO/type validators where semantics demand it, remove dead mock setups in tests, keep test names descriptive

From Story 4.2 (`CaseFileLabelsV1` origins):
- `CaseFileLabelsV1` was designed for append-only stage files with hash-chain integrity
- `LABELS_HASH_PLACEHOLDER = "0" * 64` is the canonical placeholder for hash computation
- The `_compute_casefile_hash` internal function in `casefile_io.py` uses `model_dump(mode="json")` → this automatically serializes nested Pydantic models to dicts — `CaseFileLabelDataV1` fields will appear as a nested dict in the hash computation, which is correct

From Stories 4.7 / 7.1 (lifecycle + monitoring):
- `CaseFileStageName = Literal["triage", "diagnosis", "linkage", "labels"]` in `casefile_io.py` is already set up
- No changes needed to lifecycle management for this story

### Git Intelligence Summary

Recent relevant commits:
- `e5dc6bf` (`fix(story-7.5): resolve review follow-ups and mark done`) — 719 unit tests baseline, 0 skipped; story 7.6 builds directly on this
- `4455c5b` (`feat(story-7.5): implement denylist governance and LLM narrative output sanitization`) — established `frozen=True` nested model pattern in `denylist/loader.py`; same pattern applies to `CaseFileLabelDataV1`
- `b4b76d2` (`feat(story-7.4): implement policy version stamping and decision reproducibility`) — `audit/` package pattern; `models/case_file.py` was not touched in 7.4

Actionable guidance:
- The field rename from `labels: dict[str, str]` → `label_data: CaseFileLabelDataV1` is the only structural schema change; search for `"labels"` in test files and update ALL `labels=` kwargs
- The hash computation is unaffected by the schema change (it uses `model_dump(mode="json")` which handles nested models transparently)
- No integration tests touch `CaseFileLabelsV1` directly — the full test suite should pass cleanly after the two test helper updates

### Latest Tech Information

Research timestamp: 2026-03-08.

- **Pydantic 2.12.5 — inspecting field annotations:** `CaseFileLabelDataV1.model_fields["owner_confirmed"].annotation` returns the annotation for runtime introspection in tests. For `bool | None`, the annotation is `bool | None` (a `types.UnionType`). Use `get_type_hints(CaseFileLabelDataV1)` for clean annotation access: `get_type_hints(CaseFileLabelDataV1)["owner_confirmed"]` returns `bool | None`.
- **Frozen model mutation test:** `with pytest.raises(ValidationError): model.field = value` — Pydantic v2 raises `ValidationError` on frozen model mutation (not `TypeError`). Use `pytest.raises(ValidationError)`.
- **`model_dump(mode="json")` on nested models:** When `CaseFileLabelsV1.label_data` is serialized via `model_dump(mode="json")`, `CaseFileLabelDataV1` becomes a `dict[str, Any]` with the 4 optional fields (None values serialized as `null`). The hash computation in `_compute_casefile_hash` works correctly with this.
- **`hasattr` for MI-1 posture test:** `import aiops_triage_pipeline.integrations.servicenow as sn_module; assert not hasattr(sn_module, "create_major_incident")` is the correct pattern. Since `servicenow.py` is a near-empty stub, this assertion will trivially pass.

### Project Context Reference

Applied rules from `artifact/project-context.md`:
- **Frozen model discipline:** `CaseFileLabelDataV1` must be `frozen=True` — consistent with all CaseFile stage models (3B architecture decision)
- **Schema-first model style:** Explicit typed fields over generic `dict[str, str]` — this story converts the labels from a generic dict to a properly typed schema
- **Contract + serialization framework:** `CaseFileLabelsV1.label_data` serialized via `model_dump_json()` at I/O boundaries (unchanged behavior — `casefile_io.py` handles this)
- **Consistency over novelty:** Reuse `persist_casefile_labels_write_once()` for labels.json write capability test — do not create a new persist function
- **Change locality + traceability:** `models/case_file.py`, `models/__init__.py`, the two test helpers, and the new test file change together
- **High-risk review workflow:** Schema changes to CaseFile models require explicit regression verification — run full test suite after Task 2 (test helper updates) and before Task 3

### Project Structure Notes

- `CaseFileLabelDataV1` placed in `models/case_file.py` — consistent with all other CaseFile nested models (`CaseFilePolicyVersions`, `CaseFileDownstreamImpact`, `CaseFileRoutingContext`, etc.)
- `tests/unit/models/` — new test package; follows the mirror-by-domain pattern (`models/` in src → `tests/unit/models/` for tests)
- Import boundary: `models/case_file.py` may import from `pydantic`, `contracts/`, `typing`, `re` — `CaseFileLabelDataV1` adds no new imports
- The label quality constants (`LABEL_COMPLETION_RATE_THRESHOLD`, `LABEL_ELIGIBLE_FIELDS`) are module-level constants, NOT model fields — they are schema-layer metadata, not runtime enforcement

### References

- [Source: `artifact/planning-artifacts/epics.md` — Story 7.6 acceptance criteria (FR63, FR64, FR67b)]
- [Source: `artifact/planning-artifacts/architecture.md` — Architecture decision 1C (object storage layout: `cases/{case_id}/labels.json`), 3B (frozen contract enforcement), governance requirements table]
- [Source: `src/aiops_triage_pipeline/models/case_file.py:162` — `CaseFileLabelsV1` with `labels: dict[str, str]` (the field to replace)]
- [Source: `src/aiops_triage_pipeline/models/case_file.py:19` — `LABELS_HASH_PLACEHOLDER = "0" * 64`]
- [Source: `src/aiops_triage_pipeline/storage/casefile_io.py:309` — `persist_casefile_labels_write_once()` (fully implemented; no changes)]
- [Source: `src/aiops_triage_pipeline/storage/casefile_io.py:105` — `compute_casefile_labels_hash()` (fully implemented; no changes)]
- [Source: `src/aiops_triage_pipeline/contracts/sn_linkage.py` — `ServiceNowLinkageContractV1.mi_creation_allowed: bool = False` (no changes needed)]
- [Source: `src/aiops_triage_pipeline/integrations/servicenow.py` — empty stub (no changes needed)]
- [Source: `tests/unit/storage/test_casefile_io.py:174` — `_sample_casefile_labels()` helper (update required)]
- [Source: `tests/unit/pipeline/stages/test_casefile.py:324` — labels casefile helper (update required)]
- [Source: `tests/unit/storage/test_casefile_io.py:246` — `_FakeObjectStoreClient` class (copy for new tests)]
- [Source: `artifact/project-context.md` — "Frozen model discipline", "Consistency over novelty", "Schema-first model style"]

## Dev Agent Record

### Agent Model Used

claude-sonnet-4-6

### Debug Log References

- Sprint status discovery: selected first backlog story `7-6-case-labeling-schema-and-mi-1-posture-enforcement` from `artifact/implementation-artifacts/sprint-status.yaml`
- Epic 7 status: `in-progress` (story 6 of 6; no update needed)
- Core context analyzed from:
  - `artifact/planning-artifacts/epics.md` — Story 7.6 acceptance criteria (FR63, FR64, FR67b)
  - `artifact/planning-artifacts/architecture.md` — Architecture decisions 1C, 3B, governance requirements
  - `artifact/project-context.md` — frozen model discipline, schema-first, consistency over novelty
  - `artifact/implementation-artifacts/7-5-exposure-denylist-governance-and-llm-narrative-compliance.md` — baseline 719 unit tests, 0 skipped; nested frozen model patterns
- Source code analyzed:
  - `src/aiops_triage_pipeline/models/case_file.py:162` — confirmed `CaseFileLabelsV1` uses `labels: dict[str, str]` (implementation gap for FR63)
  - `src/aiops_triage_pipeline/models/case_file.py:19` — `LABELS_HASH_PLACEHOLDER` confirmed
  - `src/aiops_triage_pipeline/storage/casefile_io.py` — `persist_casefile_labels_write_once()`, `compute_casefile_labels_hash()` fully implemented
  - `src/aiops_triage_pipeline/contracts/sn_linkage.py` — `mi_creation_allowed: bool = False` confirmed
  - `src/aiops_triage_pipeline/integrations/servicenow.py` — confirmed 1-line stub with no MI creation methods
  - `tests/unit/storage/test_casefile_io.py:174` — `_sample_casefile_labels()` uses old `labels={}` dict (must update)
  - `tests/unit/pipeline/stages/test_casefile.py:325` — second helper using old `labels={}` dict (must update)
- Key implementation gap: `CaseFileLabelsV1.labels: dict[str, str]` is generic; FR63 requires typed fields `owner_confirmed`, `resolution_category`, `false_positive`, `missing_evidence_reason`
- MI-1 posture already architecturally enforced; test required to make enforcement provable and regression-safe
- Red/Green check before implementation: `uv run python -c "from aiops_triage_pipeline.models.case_file import CaseFileLabelsV1; assert 'label_data' in CaseFileLabelsV1.model_fields"` failed before schema update and passed after update.
- Task 2 quality gate: `uv run pytest -q -m "not integration"` → `719 passed, 19 deselected`.
- Task 3 targeted test gate: `uv run pytest -q tests/unit/models/test_case_file_labels.py` → `12 passed`.
- Task 4 quality gates:
  - `uv run ruff check` (after import-order fix in `models/__init__.py`) → `All checks passed!`
  - `uv run pytest -q -m "not integration"` → `731 passed, 19 deselected`.
  - `TESTCONTAINERS_RYUK_DISABLED=true DOCKER_HOST=unix://$HOME/.docker/desktop/docker.sock uv run pytest -q -rs` → `750 passed` with `0 skipped`.

### Completion Notes List

- Implemented typed label schema support by adding `CaseFileLabelDataV1` and replacing `CaseFileLabelsV1.labels` with `CaseFileLabelsV1.label_data`.
- Added schema-layer label quality constants (`LABEL_COMPLETION_RATE_THRESHOLD`, `LABEL_ELIGIBLE_FIELDS`) for FR64 while deferring runtime enforcement to Phase 2.
- Updated all existing `CaseFileLabelsV1` test helpers to construct `label_data` instead of legacy `labels` dict payloads.
- Added a new `tests/unit/models/test_case_file_labels.py` suite covering required label fields, type annotations, frozen-model behavior, labels write-once behavior, and MI-1 posture checks.
- Verified quality gates and regressions with zero-skip posture across full suite.

### File List

- src/aiops_triage_pipeline/models/case_file.py
- src/aiops_triage_pipeline/models/__init__.py
- tests/unit/storage/test_casefile_io.py
- tests/unit/pipeline/stages/test_casefile.py
- tests/unit/models/__init__.py
- tests/unit/models/test_case_file_labels.py
- artifact/implementation-artifacts/sprint-status.yaml
- artifact/implementation-artifacts/7-6-case-labeling-schema-and-mi-1-posture-enforcement.md

## Change Log

- 2026-03-08: Created Story 7.6 implementation-ready context file with CaseFileLabelDataV1 schema design, label quality constants, MI-1 posture tests, and comprehensive developer guardrails.
- 2026-03-08: Implemented Story 7.6 schema and test changes, added labels model test package, and validated full regression with zero skipped tests.
