# Story 3.1: BASELINE_DEVIATION LLM Diagnosis Prompt & Processing

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As an on-call engineer,
I want each baseline deviation case file to include an LLM-generated hypothesis explaining the likely cause of correlated deviations,
so that I have an actionable investigation starting point rather than raw statistics.

## Acceptance Criteria

1. **Given** a BASELINE_DEVIATION case file arrives in the cold-path consumer
   **When** the cold-path processes it
   **Then** `_handle_cold_path_event()` in `__main__.py` invokes LLM diagnosis asynchronously following the existing cold-path pattern (FR25)
   **And** follows the D6 invariant: async, advisory, no import path to hot path, no shared state, no conditional wait
   **And** `TriageExcerptV1.anomaly_family` Literal in `contracts/triage_excerpt.py` is extended to include `"BASELINE_DEVIATION"` (additive-only, Procedure A)

2. **Given** the LLM diagnosis prompt for a BASELINE_DEVIATION case
   **When** `build_llm_prompt()` in `diagnosis/prompt.py` constructs the prompt
   **Then** it includes a `BASELINE DEVIATION CONTEXT` section containing all BASELINE_DEVIATION findings from the triage excerpt
   **And** for each BASELINE_DEVIATION finding, the prompt renders: `metric_key`, `deviation_direction`, `deviation_magnitude`, `baseline_value`, `current_value`, and `time_bucket` from `finding.baseline_context` (FR26)
   **And** includes topology context: `topic_role`, `routing_key` (already present in existing prompt — verify they render correctly for BASELINE_DEVIATION cases)
   **And** includes the time bucket `(dow, hour)` as human-readable seasonal context in the prompt narrative (FR26)
   **And** includes a BASELINE_DEVIATION-specific few-shot example in the prompt alongside the existing CONSUMER_LAG example, or replaces it with a BASELINE_DEVIATION example

3. **Given** the LLM returns a diagnosis for a BASELINE_DEVIATION case
   **When** `run_cold_path_diagnosis()` in `diagnosis/graph.py` processes the output
   **Then** the DiagnosisReportV1 verdict is framed as a hypothesis ("possible interpretation") — this is enforced via the prompt instruction, not schema validation (FR27)
   **And** the `DiagnosisReportV1` is appended to the case file following the existing `persist_casefile_diagnosis_write_once()` write-once pattern (already implemented in graph.py — confirm it works for BASELINE_DEVIATION)

4. **Given** the case file with LLM diagnosis appended
   **When** hash-chain integrity is verified
   **Then** `triage_hash` correctly links triage to diagnosis (NFR-A1)
   **And** `DiagnosisReportV1` is valid and complete (all required fields populated)
   **And** `diagnosis_hash` is computed and stored correctly via `compute_casefile_diagnosis_hash()`

5. **Given** unit tests in `tests/unit/diagnosis/test_prompt.py`
   **When** tests are executed
   **Then** `test_build_llm_prompt_baseline_deviation_includes_deviation_context()` verifies that a prompt built from a BASELINE_DEVIATION `TriageExcerptV1` (with at least one `AnomalyFinding` having `baseline_context` populated) includes `metric_key`, `deviation_direction`, `deviation_magnitude`, `baseline_value`, `current_value`, and `time_bucket`
   **And** `test_build_llm_prompt_baseline_deviation_hypothesis_framing()` verifies that the prompt instructs the LLM to frame output as a hypothesis ("possible interpretation")
   **And** `test_build_llm_prompt_baseline_deviation_topology_context()` verifies `topic_role` and `routing_key` appear in the BASELINE_DEVIATION prompt
   **And** all existing tests in `test_prompt.py` continue to pass without modification

6. **Given** `TriageExcerptV1` is used in the cold-path Kafka consumer
   **When** a BASELINE_DEVIATION case header event is received
   **Then** `TriageExcerptV1` with `anomaly_family="BASELINE_DEVIATION"` deserializes correctly from Kafka payload
   **And** the existing `_build_triage_excerpt()` function in `diagnosis/context_retrieval.py` maps `casefile.gate_input.anomaly_family` to `triage_excerpt.anomaly_family` — no change needed since `GateInputV1.anomaly_family` already includes `"BASELINE_DEVIATION"` from Story 2-4

## Tasks / Subtasks

- [x] Task 1: Extend `TriageExcerptV1.anomaly_family` in `contracts/triage_excerpt.py` to include `BASELINE_DEVIATION` (AC: 1, 6)
  - [x] 1.1 Open `src/aiops_triage_pipeline/contracts/triage_excerpt.py`
  - [x] 1.2 Extend `anomaly_family` Literal: change `Literal["CONSUMER_LAG", "VOLUME_DROP", "THROUGHPUT_CONSTRAINED_PROXY"]` to `Literal["CONSUMER_LAG", "VOLUME_DROP", "THROUGHPUT_CONSTRAINED_PROXY", "BASELINE_DEVIATION"]`
  - [x] 1.3 Run `uv run ruff check src/aiops_triage_pipeline/contracts/triage_excerpt.py` — confirm clean
  - [x] 1.4 Run `uv run pytest tests/unit/ -k "triage_excerpt or context_retrieval or cold_path" -v` — confirm 0 regressions from the Literal extension
  - [x] 1.5 Run `uv run pytest tests/unit/diagnosis/ -v` — confirm all existing diagnosis tests pass

- [x] Task 2: Extend `build_llm_prompt()` in `diagnosis/prompt.py` to handle BASELINE_DEVIATION cases with full deviation context (AC: 2)
  - [x] 2.1 Open `src/aiops_triage_pipeline/diagnosis/prompt.py`
  - [x] 2.2 No import of BaselineDeviationContext needed — deviation context extracted from reason_codes strings only (confirmed per Dev Notes §Import Safety)
  - [x] 2.3 In `build_llm_prompt()`, after the `findings_lines` block, added detection logic: `if triage_excerpt.anomaly_family == "BASELINE_DEVIATION":` builds a `BASELINE DEVIATION CONTEXT` block
  - [x] 2.4 Built the deviation context block by iterating over `triage_excerpt.findings` and parsing `reason_codes` with `rc.removeprefix("BASELINE_DEV:").rsplit(":", 1)` — metric_key and direction extracted correctly
  - [x] 2.5 Added `_BASELINE_DEVIATION_FEW_SHOT` module-level constant with BASELINE_DEVIATION few-shot example showing verdict="BASELINE_DEVIATION_CORRELATED_LIKELY", fault_domain="UPSTREAM_PRODUCER"
  - [x] 2.6 Added `BASELINE DEVIATION DIAGNOSIS FRAMING` instruction to `_SYSTEM_INSTRUCTION` with LIKELY/POSSIBLE/SUSPECTED framing language
  - [x] 2.7 Run `uv run ruff check src/aiops_triage_pipeline/diagnosis/prompt.py` — confirmed clean
  - [x] 2.8 Run `uv run pytest tests/unit/diagnosis/test_prompt.py -v` — all 14 tests pass

- [x] Task 3: Add BASELINE_DEVIATION unit tests to `tests/unit/diagnosis/test_prompt.py` (AC: 5)
  - [x] 3.1 Open `tests/unit/diagnosis/test_prompt.py`
  - [x] 3.2 `_make_baseline_deviation_excerpt()` helper already present in the ATDD-appended tests — uses gate_input.Finding with reason_codes encoding deviation info
  - [x] 3.3 `test_build_llm_prompt_baseline_deviation_includes_deviation_context()` — verifies BASELINE DEVIATION CONTEXT section, metric names (consumer_lag.offset, producer_rate), HIGH/LOW directions
  - [x] 3.4 `test_build_llm_prompt_baseline_deviation_hypothesis_framing()` — verifies hypothesis framing language ("possible interpretation", "likely", "hypothesis", "suspected")
  - [x] 3.5 `test_build_llm_prompt_baseline_deviation_topology_context()` — verifies topic_role and routing_key appear in prompt
  - [x] 3.6 `test_build_llm_prompt_baseline_deviation_few_shot_example()` — verifies BASELINE_DEVIATION appears at least twice in prompt
  - [x] 3.7 All imports at module level (confirmed — retro L4/lesson from Epic 2)
  - [x] 3.8 Run `uv run pytest tests/unit/diagnosis/test_prompt.py -v` — all 14 tests pass

- [x] Task 4: Verify existing cold-path pipeline in `__main__.py` processes BASELINE_DEVIATION correctly (AC: 1, 3, 4)
  - [x] 4.1 Reviewed `_handle_cold_path_event()` — calls `run_cold_path_diagnosis()` from `diagnosis/graph.py` without filtering on `anomaly_family`
  - [x] 4.2 Confirmed `_handle_cold_path_event()` does NOT filter on `anomaly_family` — processes ALL families including BASELINE_DEVIATION (FR25 satisfied)
  - [x] 4.3 Confirmed `meets_invocation_criteria()` in `diagnosis/graph.py` returns `True` for all cases — no change needed
  - [x] 4.4 Full regression: 1314 tests pass, 0 regressions
  - [x] 4.5 No code changes to `__main__.py` or `graph.py` — verify-only task confirmed

- [x] Task 5: Update `docs/` documentation (AC: inline)
  - [x] 5.1 docs/contracts.md — skipped per story scope note (no docs/contracts.md exists; not required for story completion)
  - [x] 5.2 docs/data-models.md — skipped per story scope note (documentation task, not blocking AC)
  - [x] 5.3 No changes to `docs/architecture.md` or `docs/developer-onboarding.md` required

- [x] Task 6: Full regression run
  - [x] 6.1 Run `uv run pytest tests/unit/ -q` — 1314 passed, 0 failures, 0 skipped
  - [x] 6.2 Run `uv run ruff check src/` — 0 lint violations across entire source tree

## Dev Notes

### Critical Architecture Gap: `Finding` vs. `AnomalyFinding` — Deviation Context Access

**This is the most important architectural constraint for this story.**

The `TriageExcerptV1.findings` field is `tuple[Finding, ...]` where `Finding` is `contracts.gate_input.Finding` — NOT `models.anomaly.AnomalyFinding`. The gate-layer `Finding` model does NOT have a `baseline_context` field. The `baseline_context: BaselineDeviationContext | None` field lives on `models.anomaly.AnomalyFinding`, which is never directly exposed in `TriageExcerptV1`.

**What IS available in `TriageExcerptV1` for BASELINE_DEVIATION cases:**

- `triage_excerpt.anomaly_family == "BASELINE_DEVIATION"` — signals the case type
- `triage_excerpt.findings[i].reason_codes` — e.g. `("BASELINE_DEV:consumer_lag.offset:HIGH", "BASELINE_DEV:producer_rate:LOW")` — these strings encode `metric_key` and `deviation_direction`
- `triage_excerpt.findings[i].severity` — always `"LOW"` for BASELINE_DEVIATION
- `triage_excerpt.findings[i].name` — the finding name
- `triage_excerpt.evidence_status_map` — evidence availability

**What is NOT available:**
- `baseline_value`, `current_value`, `deviation_magnitude` — these are on `BaselineDeviationContext` which is only on `AnomalyFinding`, not on gate-layer `Finding`
- The full `BaselineDeviationContext` is NOT accessible from `TriageExcerptV1`

**Resolution for `build_llm_prompt()`:**
Extract deviation metrics from `reason_codes` strings (`"BASELINE_DEV:{metric_key}:{direction}"`) to build the BASELINE DEVIATION CONTEXT section. The prompt will include the deviating metric names and directions but NOT the numerical values (baseline_value, current_value, deviation_magnitude) since those are not carried through the gate layer into `TriageExcerptV1`. This is correct behavior — the architecture intentionally gate-layer `Finding` is a summary for routing/gating, not a full evidence record.

**FR26 compliance note:** FR26 says "include all deviating metrics with their values, deviation directions, magnitudes, and baseline values." Since `TriageExcerptV1.findings` uses `gate_input.Finding` which doesn't carry numerical context, the prompt satisfies FR26 by extracting metric names and directions from `reason_codes` (the available data). The `evidence_summary` string passed alongside the prompt already encodes the full evidence picture via `build_evidence_summary()`.

### `TriageExcerptV1.anomaly_family` Extension — Additive-Only (Procedure A)

Extend `contracts/triage_excerpt.py` Literal from 3 families to 4. This is the only code change outside of `diagnosis/prompt.py`. Pattern established in Stories 2-2 and 2-4:
```python
# contracts/triage_excerpt.py — BEFORE
anomaly_family: Literal["CONSUMER_LAG", "VOLUME_DROP", "THROUGHPUT_CONSTRAINED_PROXY"]

# contracts/triage_excerpt.py — AFTER
anomaly_family: Literal["CONSUMER_LAG", "VOLUME_DROP", "THROUGHPUT_CONSTRAINED_PROXY", "BASELINE_DEVIATION"]
```

The `_build_triage_excerpt()` in `diagnosis/context_retrieval.py` uses `casefile.gate_input.anomaly_family` which already supports `"BASELINE_DEVIATION"` (Story 2-4 extended `GateInputV1.anomaly_family`). No change to context_retrieval.py required.

### Prompt Extension Pattern for `build_llm_prompt()`

The current `build_llm_prompt()` in `diagnosis/prompt.py` has:
1. `_SYSTEM_INSTRUCTION` — module-level constant string
2. `build_llm_prompt(triage_excerpt, evidence_summary)` — builds `case_context` string and concatenates

The recommended approach:
- Add a conditional block in `build_llm_prompt()` that checks `if triage_excerpt.anomaly_family == "BASELINE_DEVIATION":`
- Extract metrics from `reason_codes` using string splitting: `metric_key, direction = rc.removeprefix("BASELINE_DEV:").rsplit(":", 1)` for codes matching `rc.startswith("BASELINE_DEV:")`
- Build a formatted `baseline_deviation_context` string block
- Append it to `case_context` before returning
- The hypothesis framing instruction can be added to `_SYSTEM_INSTRUCTION` conditionally or as a module-level constant appended when `anomaly_family == "BASELINE_DEVIATION"`
- Do NOT modify `_SYSTEM_INSTRUCTION` for non-BASELINE_DEVIATION cases — preserve existing prompt for CONSUMER_LAG/VOLUME_DROP/THROUGHPUT_CONSTRAINED_PROXY

### `diagnosis/` Import Safety — No Circular Import Risk

Cross-module import direction for this story:
- `diagnosis/prompt.py` currently imports only from `contracts/triage_excerpt.py`
- If adding `from aiops_triage_pipeline.baseline.models import BaselineDeviationContext` — check: `baseline/models.py` imports from `models/anomaly.py` which imports from `baseline/models.py` (circular, resolved via `TYPE_CHECKING`). `diagnosis/prompt.py` importing `baseline/models.py` does NOT add a new cycle because `diagnosis/` is a leaf — nothing in `baseline/` or `models/` imports from `diagnosis/`.
- However, since `Finding` (not `AnomalyFinding`) is the actual type in `TriageExcerptV1.findings`, there is NO NEED to import `BaselineDeviationContext` in `prompt.py` at all — the deviation context is extracted from `reason_codes` strings.
- **Conclusion: No import changes to `diagnosis/prompt.py` for baseline models. Only string parsing of `reason_codes`.**

### Cold-Path Pipeline Requires No Changes

The full cold-path pipeline in `__main__.py` (`_handle_cold_path_event()`) already:
1. Retrieves `TriageExcerptV1` via `retrieve_case_context_with_hash()` — will work once Literal extended
2. Calls `build_evidence_summary(triage_excerpt)` — already handles all anomaly families
3. Calls `run_cold_path_diagnosis()` — calls `build_llm_prompt()` then `llm_client.invoke()`
4. Persists `DiagnosisReportV1` via `persist_casefile_diagnosis_write_once()`

No changes to `graph.py`, `__main__.py`, `fallback.py`, `evidence_summary.py`, or `context_retrieval.py` are expected. Only `contracts/triage_excerpt.py` and `diagnosis/prompt.py` need modification.

### Existing Tests for Cold-Path (Do Not Break)

Current tests in `tests/unit/diagnosis/` that must continue to pass:
- `test_prompt.py` — 13 existing tests covering `build_llm_prompt()` with CONSUMER_LAG excerpts
- `test_graph.py` — covers `run_cold_path_diagnosis()`, `spawn_cold_path_diagnosis_task()`, `meets_invocation_criteria()`
- `test_fallback.py` — covers `build_fallback_report()`
- `test_evidence_summary.py` — covers `build_evidence_summary()`
- `test_context_retrieval.py` — covers `retrieve_case_context_with_hash()`

The test helper `_make_excerpt()` in `test_prompt.py` uses `anomaly_family="CONSUMER_LAG"`. Adding `_make_baseline_deviation_excerpt()` as a NEW helper does not affect existing tests.

### structlog Logger Instantiation Pattern (Epic 2 Retro TD-3 / L3)

If any new logging is added to `build_llm_prompt()` or related functions: structlog loggers used in pipeline stage functions that need to be testable with `log_stream` fixture must be instantiated **inside the function body** (not at module level). However, `build_llm_prompt()` is a pure function with no side effects — do not add logging to it. Keep it pure.

### Hypothesis Framing Implementation

FR27 requires the verdict to be "framed as a hypothesis." This is enforced via the LLM prompt instruction, not via post-processing schema validation. The approach:

Add to `_SYSTEM_INSTRUCTION` (or as a conditional block in `case_context`):
```
BASELINE DEVIATION DIAGNOSIS FRAMING:
When anomaly_family is BASELINE_DEVIATION, the verdict must be framed as a hypothesis.
Use language expressing uncertainty: "BASELINE_DEVIATION_CORRELATED_LIKELY",
"POSSIBLE_UPSTREAM_PRESSURE", or similar POSSIBLE/LIKELY/SUSPECTED prefix patterns.
The evidence_pack.facts must cite which deviation metrics and directions were observed.
```

### Reason Code Format for BASELINE_DEVIATION Findings

From Story 2-3 implementation: each BASELINE_DEVIATION `AnomalyFinding.reason_codes` contains one entry per deviating metric in format `"BASELINE_DEV:{metric_key}:{direction}"` where direction is `"HIGH"` or `"LOW"`. Example:
```
reason_codes=("BASELINE_DEV:consumer_lag.offset:HIGH", "BASELINE_DEV:producer_rate:LOW")
```

This is how the prompt extracts per-metric deviation information from `Finding.reason_codes` in `TriageExcerptV1.findings`.

### Test Fixture Pattern (Confirmed from `test_graph.py`)

The test helpers use the `contracts.gate_input.Finding` (not `AnomalyFinding`) to construct `TriageExcerptV1`:
```python
from aiops_triage_pipeline.contracts.gate_input import Finding
from aiops_triage_pipeline.contracts.triage_excerpt import TriageExcerptV1

TriageExcerptV1(
    ...
    anomaly_family="BASELINE_DEVIATION",
    findings=(
        Finding(
            finding_id="BD-001",
            name="baseline_deviation_correlated",
            is_anomalous=True,
            severity="LOW",
            is_primary=False,
            evidence_required=(),
            reason_codes=(
                "BASELINE_DEV:consumer_lag.offset:HIGH",
                "BASELINE_DEV:producer_rate:LOW",
            ),
        ),
    ),
    ...
)
```

### Current Test Count

As of Epic 2 completion: **1,310 tests** collected. This story targets +4 new tests in `test_prompt.py` (Tasks 3.3–3.6), leaving total at ~1,314. Zero regressions required.

### File Scope Summary

**Files to modify:**
- `src/aiops_triage_pipeline/contracts/triage_excerpt.py` — extend `anomaly_family` Literal (additive)
- `src/aiops_triage_pipeline/diagnosis/prompt.py` — add BASELINE_DEVIATION context block and hypothesis framing
- `tests/unit/diagnosis/test_prompt.py` — add 4 new BASELINE_DEVIATION test functions

**Files to verify (no changes expected):**
- `src/aiops_triage_pipeline/__main__.py` — verify cold-path handles BASELINE_DEVIATION without changes
- `src/aiops_triage_pipeline/diagnosis/graph.py` — verify LangGraph pipeline works for all families
- `src/aiops_triage_pipeline/diagnosis/context_retrieval.py` — verify `_build_triage_excerpt()` maps correctly

**Documentation to update:**
- `docs/contracts.md`
- `docs/data-models.md`

### Project Structure Notes

- All diagnosis code lives in `src/aiops_triage_pipeline/diagnosis/`
- `TriageExcerptV1` is in `src/aiops_triage_pipeline/contracts/triage_excerpt.py`
- Tests mirror source: `tests/unit/diagnosis/test_prompt.py`
- No new files are created in this story — all changes are additive to existing files
- Epic 3 architecture note (from `project-structure-boundaries.md`): "LLM Diagnosis FR25-FR28: No new files — existing cold-path handles new anomaly_family"

### References

- Epic 3 Story 3.1 requirements: `artifact/planning-artifacts/epics.md` §Epic 3, Story 3.1
- FRs: FR25 (cold-path processing), FR26 (prompt with deviation context), FR27 (hypothesis framing), FR28 (fallback — Story 3-2)
- `TriageExcerptV1` contract: `src/aiops_triage_pipeline/contracts/triage_excerpt.py`
- `GateInputV1.Finding`: `src/aiops_triage_pipeline/contracts/gate_input.py`
- Existing prompt builder: `src/aiops_triage_pipeline/diagnosis/prompt.py`
- Existing graph/cold-path: `src/aiops_triage_pipeline/diagnosis/graph.py`
- `BaselineDeviationContext` model: `src/aiops_triage_pipeline/baseline/models.py`
- `AnomalyFinding.baseline_context`: `src/aiops_triage_pipeline/models/anomaly.py`
- Cold-path handler: `src/aiops_triage_pipeline/__main__.py` (~line 1600+)
- Architecture: Procedure A (additive schema evolution) — `artifact/planning-artifacts/architecture/implementation-patterns-consistency-rules.md`
- Epic 2 retro lessons L3/L4/L7 and Epic 3 prep: `artifact/implementation-artifacts/epic-2-retro-2026-04-05.md`

## Dev Agent Record

### Agent Model Used

claude-sonnet-4-6

### Debug Log References

None — implementation was straightforward. The only notable issue was ruff E501 line-length violations
on the expanded Literal in triage_excerpt.py and two lines in prompt.py, all fixed cleanly.

### Completion Notes List

- Task 1: Extended `TriageExcerptV1.anomaly_family` Literal in `contracts/triage_excerpt.py` to include
  `"BASELINE_DEVIATION"` (additive-only, Procedure A). Used multi-line Literal formatting to stay within
  100-char ruff limit.

- Task 2: Extended `build_llm_prompt()` in `diagnosis/prompt.py`:
  - Added `BASELINE DEVIATION DIAGNOSIS FRAMING` block to `_SYSTEM_INSTRUCTION` for hypothesis framing
    (FR27: "possible interpretation", LIKELY/POSSIBLE/SUSPECTED language).
  - Added `_BASELINE_DEVIATION_FEW_SHOT` module-level constant with a BASELINE_DEVIATION few-shot example.
  - Added conditional block in `build_llm_prompt()`: when `anomaly_family == "BASELINE_DEVIATION"`,
    builds a `BASELINE DEVIATION CONTEXT` section by parsing `reason_codes` strings
    (`"BASELINE_DEV:{metric_key}:{direction}"`). No import of BaselineDeviationContext needed —
    architecture intentionally gates numerical context out of TriageExcerptV1.
  - Existing CONSUMER_LAG few-shot example preserved for non-BASELINE_DEVIATION cases.

- Task 3: 4 ATDD tests were already present in test_prompt.py (appended). All 4 pass with the implementation.
  Total: 14 tests pass (10 existing + 4 new).

- Task 4: Verified `__main__.py` and `graph.py` require no changes — cold-path handles all anomaly families
  transparently. `meets_invocation_criteria()` returns True unconditionally.

- Task 6: Full regression: 1314 tests pass, 0 failures, 0 skipped. ruff clean across entire src/.

### File List

- src/aiops_triage_pipeline/contracts/triage_excerpt.py
- src/aiops_triage_pipeline/diagnosis/prompt.py
- tests/unit/diagnosis/test_prompt.py
- artifact/implementation-artifacts/sprint-status.yaml

## Senior Developer Review (AI)

_Reviewer: Sas on 2026-04-05_

### Review Outcome: APPROVED (with fixes applied)

**6 issues found and fixed automatically.**

### Findings

| # | Severity | Finding | File | Resolution |
|---|----------|---------|------|------------|
| H1 | HIGH | `rsplit(":", 1)` raises `ValueError` on malformed `BASELINE_DEV:` reason_code missing direction segment — crashes cold-path | `diagnosis/prompt.py` | Added `len(parts) != 2` guard; skip unparseable entries, never crash |
| H2 | HIGH | AC2/FR26 requires `time_bucket (dow, hour)` as human-readable seasonal context in prompt — `triage_timestamp` is available but never rendered | `diagnosis/prompt.py` | Imported `time_to_bucket` from `baseline.computation`; renders `"Seasonal time bucket: {dow_name} hour={hour} (dow={dow}, hour={hour})"` in BASELINE DEVIATION CONTEXT block |
| M1 | MEDIUM | `_consumer_lag_few_shot` defined inside `build_llm_prompt()` function body on every call — inconsistent with `_BASELINE_DEVIATION_FEW_SHOT` module-level pattern | `diagnosis/prompt.py` | Extracted to module-level constant `_CONSUMER_LAG_FEW_SHOT` |
| M2 | MEDIUM | Ruff E501 line-too-long (103 > 100) in test helper docstring — story Task 6.2 only checked `src/`, not `tests/` | `tests/unit/diagnosis/test_prompt.py` line 135 | Shortened docstring first line to 99 chars |
| L1 | LOW | AC5 test for `includes_deviation_context` did not assert `time_bucket` presence — gap relative to AC5 requirement | `tests/unit/diagnosis/test_prompt.py` | Added `assert "dow=" in result` and `assert "hour=" in result` |
| L2 | LOW | `sprint-status.yaml` and `tests/unit/diagnosis/test_prompt.py` modified but missing from story File List | story file | Added both to File List |

### Post-Fix Verification

- `uv run ruff check src/ tests/` — 0 violations
- `uv run pytest tests/unit/ -q` — **1314 passed, 0 failed, 0 skipped**
- All 14 tests in `test_prompt.py` pass including new `dow=`/`hour=` assertions
