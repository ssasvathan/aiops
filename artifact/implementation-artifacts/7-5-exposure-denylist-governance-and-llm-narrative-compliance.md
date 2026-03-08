# Story 7.5: Exposure Denylist Governance & LLM Narrative Compliance

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a compliance officer,
I want the exposure denylist maintained as a versioned, reviewable artifact with LLM-generated narrative compliance enforced,
so that denylist changes follow controlled change management and no LLM output leaks sensitive information (FR62, FR65).

## Acceptance Criteria

1. **Given** the exposure denylist is a versioned YAML file in the repository
   **When** a change to the denylist is proposed
   **Then** changes require pull request review by at least one designated approver (FR62)

2. **And** an audit log entry records: author, reviewer, timestamp, and diff summary (FR62)

3. **And** denylist version is bumped on every change

4. **When** LLM-generated narrative appears in any surfaced output (excerpt, Slack, SN)
   **Then** the narrative is filtered through `apply_denylist()` before surfacing (FR65)

5. **And** zero violations of the denylist in LLM-generated content

6. **And** unit tests verify: denylist version tracking, LLM narrative denylist enforcement, edge cases with LLM output containing denied patterns

## Tasks / Subtasks

- [x] Task 1: Add CODEOWNERS entry requiring security review for `config/denylist.yaml` (AC: 1)
  - [x] Create `.github/CODEOWNERS` file (or `CODEOWNERS` at repo root) with a designated approver rule for `config/denylist.yaml`
  - [x] Rule syntax: `config/denylist.yaml @<security-team-handle>` (use the project's owner/reviewer handle)

- [x] Task 2: Add structured changelog section to `config/denylist.yaml` (AC: 2, 3)
  - [x] Extend `DenylistV1` model in `denylist/loader.py` to include an optional `changelog` field: `changelog: tuple[DenylistChangelogEntry, ...]  = ()`
  - [x] Create `DenylistChangelogEntry` dataclass/model with fields: `version: str`, `date: str`, `author: str`, `reviewer: str`, `summary: str`
  - [x] Add initial changelog entry to `config/denylist.yaml` reflecting the v1.0.0 creation

- [x] Task 3: Sanitize LLM narrative output before persisting `diagnosis.json` (AC: 4, 5)
  - [x] In `src/aiops_triage_pipeline/diagnosis/graph.py`, after `validated_llm_report` is validated, apply `apply_denylist()` to `validated_llm_report.model_dump(mode="json")` and reconstruct `DiagnosisReportV1` from the sanitized dict
  - [x] Preserve `triage_hash` and `case_id` injection that follows (only sanitize narrative text fields — verdict, fault_domain, evidence_pack.facts, evidence_pack.next_checks, gaps)
  - [x] Ensure the sanitized report is the one written to `diagnosis.json` and returned from `run_cold_path_diagnosis()`

- [x] Task 4: Add unit tests for denylist version tracking (AC: 6)
  - [x] Add `tests/unit/denylist/test_governance.py` with:
    - `test_denylist_yaml_has_non_empty_version`: load `config/denylist.yaml` via `load_denylist()`, assert `denylist.denylist_version` is non-empty and matches semver pattern
    - `test_denylist_changelog_has_initial_entry`: assert `denylist.changelog` is non-empty and first entry has all required fields non-empty

- [x] Task 5: Add unit tests for LLM narrative output denylist enforcement (AC: 4, 5, 6)
  - [x] Add tests to `tests/unit/diagnosis/test_graph.py`:
    - `test_llm_narrative_output_sanitized_before_persist`: build a mock LLM that returns a `DiagnosisReportV1` whose `verdict` contains a denied value pattern (e.g., Bearer token). Assert the persisted report does NOT contain the denied pattern in `verdict`.
    - `test_llm_narrative_denied_field_in_facts_sanitized`: mock LLM returns `evidence_pack.facts` containing a credential URL (`postgresql://user:pass@host`). Assert the sanitized report's `facts` have the offending entry removed.
    - `test_llm_narrative_clean_output_passes_through_unchanged`: clean LLM output (no denied patterns) passes through `apply_denylist()` unchanged — no fields or list items removed.
    - `test_llm_narrative_sanitization_uses_active_denylist`: verify that a denylist with a specific pattern correctly removes matching content from LLM output (not just the empty denylist stub).

- [x] Task 6: Run quality gates with zero-skip posture (AC: 1–6)
  - [x] `uv run ruff check`
  - [x] `uv run pytest -q -m "not integration"`
  - [x] `TESTCONTAINERS_RYUK_DISABLED=true DOCKER_HOST=unix://$HOME/.docker/desktop/docker.sock uv run pytest -q -rs`
  - [x] Verify full run reports `0 skipped`

## Dev Notes

### Developer Context Section

- Story key: `7-5-exposure-denylist-governance-and-llm-narrative-compliance`
- Story ID: `7.5`
- Epic context: Epic 7 — Governance, Audit & Operational Observability. Story 7.5 closes the compliance loop by (a) formalizing the change-management process for `config/denylist.yaml` and (b) ensuring LLM-generated narrative content is sanitized through `apply_denylist()` before being written to `diagnosis.json`.
- Dependency context:
  - `DenylistV1` model (`denylist/loader.py`) and `apply_denylist()` (`denylist/enforcement.py`) are fully implemented — do NOT reinvent them.
  - `run_cold_path_diagnosis()` in `diagnosis/graph.py` already sanitizes the INPUT (`triage_excerpt`) before sending to the LLM (line 185). Story 7.5 adds OUTPUT sanitization of the returned `DiagnosisReportV1`.
  - The `config/denylist.yaml` file exists at `v1.0.0`. Story 7.5 extends its YAML schema to include a structured `changelog` section.
  - No FastAPI or HTTP endpoints are involved — purely Python callables and YAML schema extension.

**Critical implementation gap (do NOT miss):**

Currently in `run_cold_path_diagnosis()` (line 382–388 in `diagnosis/graph.py`):
```python
report = DiagnosisReportV1.model_validate(
    {
        **validated_llm_report.model_dump(mode="json"),
        "triage_hash": triage_hash,
        "case_id": case_id,
    }
)
```
The LLM output `validated_llm_report` is reconstructed WITHOUT applying `apply_denylist()` to it. This is the gap for FR65. The fix must apply `apply_denylist()` to the report dict before model reconstruction.

**Important subtlety:** The `apply_denylist()` function works on `dict[str, Any]`. When applied to `DiagnosisReportV1.model_dump(mode="json")`, it will:
- Remove any string field whose value matches a `denied_value_patterns` (e.g., verdict containing a Bearer token)
- Remove any field whose key matches `denied_field_names` (case-insensitive)

After sanitization, some fields may be absent from the dict. `DiagnosisReportV1` has `Optional` fields (`fault_domain`, `case_id`, `triage_hash`) and defaults (`next_checks=()`, `gaps=()`, `reason_codes=()`). Be careful that removing a required field like `verdict` would cause `ValidationError`. The expected behavior: if `verdict` is denied (extremely unlikely in practice but possible), the fallback should handle it gracefully. The simplest approach: sanitize, then re-inject `case_id` and `triage_hash` after sanitization, and only reconstruct if `schema_version` and `verdict` are still present.

**Simplest correct implementation in `run_cold_path_diagnosis()`:**
```python
# After: validated_llm_report = DiagnosisReportV1.model_validate(raw_report)
sanitized_report_dict = apply_denylist(validated_llm_report.model_dump(mode="json"), denylist)
report = DiagnosisReportV1.model_validate(
    {
        **sanitized_report_dict,
        "triage_hash": triage_hash,
        "case_id": case_id,
    }
)
```

### Technical Requirements

1. **CODEOWNERS — GitHub PR review enforcement (AC: 1):**
   - Create `.github/CODEOWNERS` (standard GitHub location) or `CODEOWNERS` at repo root
   - Entry: `config/denylist.yaml  @<approver>` — use a placeholder like `@security-team` since no real GitHub handles exist in the codebase
   - This is a documentation/governance artifact; no runtime code change

2. **`DenylistChangelogEntry` model (AC: 2, 3):**
   - Add as a nested `BaseModel, frozen=True` inside `denylist/loader.py`
   - Fields:
     - `version: str` — the denylist_version this entry was created for
     - `date: str` — ISO date of change (YYYY-MM-DD)
     - `author: str` — git author / PR creator
     - `reviewer: str` — PR approver handle
     - `summary: str` — one-line diff summary
   - `DenylistV1` gains: `changelog: tuple[DenylistChangelogEntry, ...] = ()`
   - Update `config/denylist.yaml` with first entry documenting v1.0.0 creation

3. **LLM output sanitization in `diagnosis/graph.py` (AC: 4, 5):**
   - Apply `apply_denylist()` to `validated_llm_report.model_dump(mode="json")` before injecting `triage_hash`/`case_id`
   - The sanitized dict is then passed to `DiagnosisReportV1.model_validate()`
   - If `model_validate` raises `ValidationError` after sanitization (e.g., `verdict` was denied), treat as `LLM_SCHEMA_INVALID` and use the existing fallback path — do NOT add a new exception branch; wrap this in the existing pydantic validation error block
   - Maintain same log structure (`cold_path_diagnosis_json_written`, `cold_path_diagnosis_completed`)

4. **Test for `test_denylist_yaml_has_non_empty_version`:**
   - Must load the REAL `config/denylist.yaml` via `load_denylist(Path("config/denylist.yaml"))` using a path relative to the project root
   - Use `pytest.ini`/`pyproject.toml` rootdir or resolve via `pathlib.Path(__file__).parents[N]` to find the repo root

### Architecture Compliance

- `denylist/loader.py` may grow `DenylistChangelogEntry` — still a leaf module
- Do NOT import `DenylistChangelogEntry` in `enforcement.py` — keep enforcement independent of changelog schema
- `diagnosis/graph.py` already imports `apply_denylist` — no new imports needed for the output sanitization
- Maintain frozen model discipline for `DenylistV1` and `DenylistChangelogEntry`
- Do NOT add `changelog` parsing logic to `enforcement.py` — it belongs only in `loader.py`
- The CODEOWNERS file does not affect Python module structure

### Library / Framework Requirements

Pinned versions — no new dependencies:
- `pydantic==2.12.5` — `DenylistChangelogEntry` uses standard `BaseModel, frozen=True`
- `pyyaml~=6.0` — already used in `load_denylist()`; the extended YAML schema is backward-compatible
- `pytest==9.0.2` — test fixtures using `tmp_path` and `MagicMock`

Implementation guidance:
- Import `apply_denylist` in `diagnosis/graph.py`: already present at line 24
- `DenylistChangelogEntry` goes in `denylist/loader.py` above `DenylistV1`
- Export `DenylistChangelogEntry` from `denylist/__init__.py` for test convenience

### File Structure Requirements

New files to create:
- `.github/CODEOWNERS` (governance artifact — PR review requirement)
- `tests/unit/denylist/test_governance.py` (denylist version tracking tests)

Existing files to modify:
- `src/aiops_triage_pipeline/denylist/loader.py` — add `DenylistChangelogEntry` model, add `changelog` field to `DenylistV1`
- `src/aiops_triage_pipeline/denylist/__init__.py` — export `DenylistChangelogEntry`
- `src/aiops_triage_pipeline/diagnosis/graph.py` — add `apply_denylist()` call on LLM output before reconstruction
- `config/denylist.yaml` — add `changelog` section with v1.0.0 initial entry
- `tests/unit/diagnosis/test_graph.py` — add 4 LLM narrative output sanitization tests

Files to NOT touch:
- `src/aiops_triage_pipeline/denylist/enforcement.py` — already correct; `apply_denylist()` is unchanged
- `src/aiops_triage_pipeline/contracts/*.py` — do not modify frozen contracts
- `src/aiops_triage_pipeline/models/case_file.py` — no schema changes needed
- `src/aiops_triage_pipeline/pipeline/stages/casefile.py` — no changes
- `src/aiops_triage_pipeline/integrations/slack.py` — already applies denylist to its own payload

### Testing Requirements

**New test file `tests/unit/denylist/test_governance.py`:**

| Test | What it verifies |
|------|-----------------|
| `test_denylist_yaml_has_non_empty_version` | `load_denylist(real_path)` returns `denylist_version` matching `r"v\d+\.\d+\.\d+"` |
| `test_denylist_changelog_has_initial_entry` | `denylist.changelog` is non-empty; first entry has all fields non-empty strings |
| `test_changelog_entry_version_matches_denylist_version` | Latest changelog entry's `version` equals `denylist.denylist_version` |

**New tests in `tests/unit/diagnosis/test_graph.py`:**

| Test | Scenario | Asserts |
|------|----------|---------|
| `test_llm_narrative_output_sanitized_before_persist` | LLM verdict contains `"Bearer AbCdEfGhIjKlMnOpQrSt12345"` | Returned report's `verdict` does NOT contain the token (field removed or replaced) |
| `test_llm_narrative_denied_field_in_facts_sanitized` | `evidence_pack.facts` contains `"postgresql://user:secret@db-host/prod"` | Returned report's `facts` tuple does not contain the credential URL |
| `test_llm_narrative_clean_output_passes_through_unchanged` | Clean LLM output with no denied patterns | All report fields preserved exactly |
| `test_llm_narrative_sanitization_uses_active_denylist` | Real denylist with `denied_value_patterns` targeting `Bearer` | Confirms sanitization works with non-empty denylist (not the empty stub) |

**Key invariants:**
- All new tests are pure unit tests (no containers, no Redis, no real LLM calls)
- Use `MagicMock(spec=LLMClient)` + `AsyncMock` for LLM client (pattern already used in test_graph.py)
- Use `_make_eligible_excerpt()` helper that already exists in test_graph.py
- Use `_make_mock_store()` helper that already exists in test_graph.py
- Preserve zero-skip discipline; all tests must pass without `@pytest.mark.skip`

**Quality gate commands:**
- `uv run ruff check`
- `uv run pytest -q -m "not integration"`
- `TESTCONTAINERS_RYUK_DISABLED=true DOCKER_HOST=unix://$HOME/.docker/desktop/docker.sock uv run pytest -q -rs`

### Previous Story Intelligence

From Story 7.4 (`7-4-policy-version-stamping-and-decision-reproducibility.md`):
- Established the `audit/` package pattern — `denylist/` similarly acts as a leaf package (imports from `contracts/`, `models/`; nothing imports from it except callers)
- Quality gate posture confirmed: zero-skip, ruff clean. Maintain.
- Full regression after 7.4: 730 tests, 0 skipped

From Story 6.2/6.3 (cold-path LLM invocation):
- `run_cold_path_diagnosis()` in `diagnosis/graph.py:165` is the authority for cold-path diagnosis flow
- `apply_denylist()` is already called at line 185 for INPUT sanitization
- The `validated_llm_report` reconstruction block (lines 382–388) is the insertion point for OUTPUT sanitization
- `_make_mock_store()` and `_make_eligible_excerpt()` fixtures exist in `tests/unit/diagnosis/test_graph.py`

From Story 1.5 (exposure denylist foundation):
- `DenylistV1` established with `denylist_version` field — the version string is the audit anchor
- The `denied_field_names` and `denied_value_patterns` cover credentials, Bearer tokens, and Ranger groups (see `config/denylist.yaml`)

### Git Intelligence Summary

Recent relevant commits:
- `dc5032f` (`fix(story-7.4): resolve review follow-ups and mark done`) — confirms 730-test baseline; story 7.5 builds on it
- `b4b76d2` (`feat(story-7.4): implement policy version stamping and decision reproducibility`) — `audit/` package created; `denylist/` remains unchanged from Epic 1

Actionable guidance:
- The `denylist/loader.py` extension is additive — no existing callers are broken by adding an optional `changelog` field with default `()`
- The `diagnosis/graph.py` change is a one-line insertion before the existing `DiagnosisReportV1.model_validate(...)` call — surgical and low-risk
- The CODEOWNERS file is net-new and does not affect any existing test

### Latest Tech Information

Research timestamp: 2026-03-08.

- **Pydantic 2.12.5 nested model in YAML:** `DenylistChangelogEntry` as a nested `BaseModel, frozen=True` within `DenylistV1` works with `pyyaml`'s `safe_load` + `model_validate`. Each changelog entry in YAML becomes a dict; Pydantic validates it into `DenylistChangelogEntry`.
- **CODEOWNERS syntax:** Standard GitHub CODEOWNERS — one rule per line: `config/denylist.yaml  @handle`. Place in `.github/CODEOWNERS` (preferred) or repo root `CODEOWNERS`. No runtime impact.
- **`apply_denylist()` on DiagnosisReportV1 dict:** `DiagnosisReportV1.model_dump(mode="json")` returns a plain dict with all string fields serialized. Applying `apply_denylist()` to it before `model_validate()` correctly filters narrative fields. The `reason_codes` tuple becomes a list in JSON mode — `apply_denylist()` handles lists recursively already.
- **Test pattern for real YAML loading:** Use `pathlib.Path(__file__).parents[3] / "config" / "denylist.yaml"` from within `tests/unit/denylist/test_governance.py` to reach the project root (`parents[3]` = 3 hops from the file's directory: denylist → unit → tests → project_root). Alternatively, use `pytest`'s `rootdir` conftest fixture if available. The simpler approach: use `conftest.py` to provide a `real_denylist_path` fixture.

### Project Context Reference

Applied rules from `artifact/project-context.md`:
- **Denylist framework rule:** "All outbound boundary shaping must use shared `apply_denylist(...)`" — Story 7.5 enforces this at the LLM OUTPUT boundary (currently the one gap)
- **Consistency over novelty:** Do not add a new sanitization function; reuse existing `apply_denylist()` directly
- **Change locality + traceability:** `denylist/loader.py`, `diagnosis/graph.py`, `config/denylist.yaml`, and their corresponding tests change together in one PR
- **Frozen model discipline:** `DenylistChangelogEntry` must be `frozen=True`
- **High-risk review workflow:** Changes to `denylist/` enforcement paths require explicit regression verification — run full test suite including integration

### Project Structure Notes

- `.github/CODEOWNERS` — new directory, new file. Standard GitHub governance artifact.
- `DenylistChangelogEntry` in `denylist/loader.py` — consistent with existing nested model pattern (cf. `EvidencePack` in `contracts/diagnosis_report.py`)
- `tests/unit/denylist/test_governance.py` — new file; mirrors pattern of `test_loader.py` and `test_enforcement.py` in the same package
- Import boundary: `denylist/loader.py` may only import from `pydantic`, `re`, `pathlib`, `typing` — no domain imports
- The `changelog` extension is additive to `DenylistV1`; existing `load_denylist()` function handles it automatically via Pydantic's `model_validate`

### References

- [Source: `artifact/planning-artifacts/epics.md` — Story 7.5 acceptance criteria (FR62, FR65)]
- [Source: `src/aiops_triage_pipeline/denylist/loader.py` — `DenylistV1` model with `denylist_version` field]
- [Source: `src/aiops_triage_pipeline/denylist/enforcement.py` — `apply_denylist()` shared function]
- [Source: `src/aiops_triage_pipeline/denylist/__init__.py` — public API exports]
- [Source: `config/denylist.yaml` — versioned denylist, v1.0.0, with `denied_field_names` and `denied_value_patterns`]
- [Source: `src/aiops_triage_pipeline/diagnosis/graph.py:165` — `run_cold_path_diagnosis()` with INPUT sanitization at line 185]
- [Source: `src/aiops_triage_pipeline/diagnosis/graph.py:382` — LLM output reconstruction WITHOUT output sanitization (the implementation gap)]
- [Source: `src/aiops_triage_pipeline/contracts/diagnosis_report.py` — `DiagnosisReportV1` fields: verdict, fault_domain, evidence_pack, next_checks, gaps]
- [Source: `tests/unit/diagnosis/test_graph.py:257` — existing `test_denylist_applied_to_triage_excerpt` (INPUT only; OUTPUT coverage added in this story)]
- [Source: `tests/unit/denylist/test_enforcement.py` — existing enforcement tests (no output-boundary tests)]
- [Source: `tests/unit/denylist/conftest.py` — `minimal_denylist` and `empty_denylist` fixtures]
- [Source: `artifact/project-context.md` — "All outbound boundary shaping must use shared apply_denylist(...)"]
- [Source: `artifact/planning-artifacts/architecture.md` — Architecture decision 2B, "LLM narrative surfacing" listed as 4th output boundary]

## Dev Agent Record

### Agent Model Used

claude-sonnet-4-6

### Debug Log References

- Sprint status discovery: selected first backlog story `7-5-exposure-denylist-governance-and-llm-narrative-compliance`
- Core context analyzed from:
  - `artifact/planning-artifacts/epics.md` — Epic 7, Story 7.5 acceptance criteria (FR62, FR65)
  - `artifact/planning-artifacts/architecture.md` — Architecture decision 2B (4 output boundaries including LLM narrative)
  - `artifact/project-context.md` — denylist framework rule, frozen model discipline
  - `artifact/implementation-artifacts/7-4-policy-version-stamping-and-decision-reproducibility.md` — previous story intelligence
- Source code analyzed:
  - `src/aiops_triage_pipeline/denylist/loader.py` — `DenylistV1` model (confirmed `denylist_version` field, no `changelog` field yet)
  - `src/aiops_triage_pipeline/denylist/enforcement.py` — `apply_denylist()` (correct, unchanged)
  - `src/aiops_triage_pipeline/diagnosis/graph.py` — confirmed INPUT sanitization at line 185; OUTPUT NOT sanitized at line 382–388
  - `config/denylist.yaml` — version v1.0.0, no changelog section (confirmed implementation gap)
  - `tests/unit/diagnosis/test_graph.py` — 885 lines, INPUT denylist test at line 257, NO OUTPUT sanitization tests
  - `tests/unit/denylist/test_enforcement.py` — 14 tests, none for governance or LLM output boundary
- Key insight: Two distinct implementation gaps — (1) no CODEOWNERS/audit-log for denylist governance (FR62), (2) LLM output (DiagnosisReportV1 narrative) not sanitized before persisting to diagnosis.json (FR65)
- Epic 7 status: `in-progress`; this is story 5 of 6 in the epic

### Completion Notes List

- ✅ Task 1: Created `.github/CODEOWNERS` with `config/denylist.yaml  @security-team` rule enforcing PR review for denylist changes (FR62).
- ✅ Task 2: Added `DenylistChangelogEntry` frozen Pydantic model to `denylist/loader.py`; extended `DenylistV1` with optional `changelog: tuple[DenylistChangelogEntry, ...] = ()`; exported `DenylistChangelogEntry` from `denylist/__init__.py`; added v1.0.0 changelog entry to `config/denylist.yaml`.
- ✅ Task 3: Applied `apply_denylist()` to LLM narrative OUTPUT (`validated_llm_report.model_dump(mode="json")`) before injecting `triage_hash`/`case_id` and writing `diagnosis.json`. Sanitization is wrapped in the existing `pydantic.ValidationError` handler so denied-required-field edge cases fall back as `LLM_SCHEMA_INVALID`.
- ✅ Task 4: Created `tests/unit/denylist/test_governance.py` with 3 governance tests: version semver format, changelog has initial entry with all fields non-empty, latest changelog version matches denylist_version.
- ✅ Task 5: Added 4 LLM narrative output sanitization tests to `tests/unit/diagnosis/test_graph.py`. Updated `test_denylist_applied_to_triage_excerpt` to account for two `apply_denylist` calls (INPUT + OUTPUT).
- ✅ Task 6: Quality gates — ruff: clean, unit tests: 718 passed 0 skipped, full suite: 737 passed 0 skipped (7 new tests added: 3 governance + 4 graph output sanitization).
- ✅ Code Review fixes (2026-03-08): Added ISO date validator to `DenylistChangelogEntry.date`; removed dead mock setup in clean-output test; renamed misleading test to `test_llm_narrative_required_field_denied_triggers_schema_invalid_fallback`; added new happy-path test `test_llm_narrative_optional_field_denied_sanitized_and_persisted`; added missing positive assertion to `test_llm_narrative_sanitization_uses_active_denylist`. Unit tests: 719, 0 skipped.

### File List

- `.github/CODEOWNERS` (new)
- `src/aiops_triage_pipeline/denylist/loader.py` (modified — added `DenylistChangelogEntry`, `changelog` field on `DenylistV1`)
- `src/aiops_triage_pipeline/denylist/__init__.py` (modified — export `DenylistChangelogEntry`)
- `src/aiops_triage_pipeline/diagnosis/graph.py` (modified — apply `apply_denylist()` to LLM output narrative before `DiagnosisReportV1` reconstruction)
- `config/denylist.yaml` (modified — added `changelog` section with v1.0.0 initial entry)
- `tests/unit/denylist/test_governance.py` (new — 3 governance tests)
- `tests/unit/diagnosis/test_graph.py` (modified — 5 new LLM output sanitization tests + updated existing denylist test; 1 test renamed)

## Change Log

- 2026-03-08: Code review fixes — ISO date validation on DenylistChangelogEntry, dead code removed, misleading test renamed, happy-path sanitize-and-persist test added, missing assertion added. 719 unit tests, 0 skipped. Status → done.
- 2026-03-08: Implemented Story 7.5 — denylist governance (CODEOWNERS, changelog schema) and LLM narrative output sanitization. 737 tests, 0 skipped.
- 2026-03-08: Created Story 7.5 implementation-ready context file with denylist governance design, LLM narrative output sanitization gap, CODEOWNERS approach, DenylistChangelogEntry schema, and comprehensive developer guardrails.
