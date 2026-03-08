# Story 6.3: Structured DiagnosisReport Output & Evidence Citation

Status: review

## Story

As a platform operator,
I want the LLM to produce a structured DiagnosisReport with evidence citations and UNKNOWN propagation,
so that diagnosis output is machine-parseable, traceable to evidence, and never fabricates findings
(FR37, FR38).

## Acceptance Criteria

1. **Given** the LLM has been invoked with TriageExcerpt and evidence summary
   **When** the LLM produces its response
   **Then** the output is a structured `DiagnosisReportV1` containing: `verdict`, `fault_domain`,
   `confidence`, `evidence_pack` (facts, missing_evidence, matched_rules), `next_checks`, `gaps` (FR37)
2. **And** the LLM cites evidence IDs/references from the structured evidence pack (FR38)
3. **And** the LLM explicitly propagates UNKNOWN for missing evidence — never invents metric values or
   fabricates findings (FR38)
4. **And** the `DiagnosisReport` is written to `cases/{case_id}/diagnosis.json` as a write-once stage
   file using `persist_casefile_diagnosis_write_once()`
5. **And** `diagnosis.json` includes SHA-256 hash of `triage.json` it depends on (hash chain):
   `CaseFileDiagnosisV1.triage_hash` and `DiagnosisReportV1.triage_hash` are both populated with the
   triage hash passed from the hot path
6. **And** LLM uses only bank-sanctioned endpoints (NFR-S8) — enforced via `LLM_BASE_URL` config
7. **And** unit tests verify: `DiagnosisReport` field completeness, evidence citation presence, UNKNOWN
   propagation instruction in prompt, hash chain to `triage.json`, `diagnosis.json` write-once
   persistence call

## Tasks / Subtasks

- [x] Task 1: Implement `diagnosis/prompt.py` — structured prompt builder (AC: 2, 3)
  - [x] `def build_llm_prompt(triage_excerpt: TriageExcerptV1, evidence_summary: str) -> str`
  - [x] Prompt MUST include a system instruction: produce JSON matching `DiagnosisReportV1` schema
  - [x] Prompt MUST include: cite only evidence IDs from the provided evidence pack (FR38)
  - [x] Prompt MUST include: use `UNKNOWN` for any missing or uncertain evidence — NEVER fabricate
    metric values, counts, or findings not present in the evidence pack
  - [x] Prompt MUST include: formatted triage excerpt key fields (anomaly_family, topic, cluster_id,
    stream_id, criticality_tier, sustained, evidence_status_map, findings)
  - [x] Prompt MUST include: the `evidence_summary` string
  - [x] Return value: a single string (system + user context merged) — the LLM endpoint receives this
    as the `"prompt"` field in the request body

- [x] Task 2: Update `integrations/llm.py` — LIVE mode uses prompt and parses structured output
  (AC: 1, 6)
  - [x] Add `prompt: str | None = None` keyword-only parameter to `invoke()`:
    `async def invoke(self, case_id: str, triage_excerpt: TriageExcerptV1, evidence_summary: str, *, prompt: str | None = None) -> DiagnosisReportV1`
  - [x] In LIVE mode: if `prompt is None`, raise `ValueError("LIVE mode requires prompt to be
    provided by the caller (diagnosis/graph.py)")`
  - [x] In LIVE mode: update request body to `{"case_id": case_id, "prompt": prompt}` (replaces
    old body with evidence_summary)
  - [x] In LIVE mode: parse structured JSON response:
    `response_data = response.json()` then `DiagnosisReportV1.model_validate(response_data)`
  - [x] In LIVE mode: update structured log from `"llm_invoke_live_stub"` to `"llm_invoke_live"`;
    remove the `LLM_LIVE_STUB` hardcoded return — Story 6.3 replaces the stub with real parsing
  - [x] MOCK/LOG mode: `prompt` parameter is accepted but silently ignored (no behavioural change)
  - [x] Update module-level docstring to reflect Story 6.3 completion of LIVE mode

- [x] Task 3: Update `diagnosis/graph.py` — build prompt, pass triage_hash, write diagnosis.json
  (AC: 4, 5)
  - [x] Add `triage_hash: str` and `object_store_client: ObjectStoreClientProtocol` parameters to
    `run_cold_path_diagnosis()` (both keyword-only, required)
  - [x] Add `triage_hash: str` and `object_store_client: ObjectStoreClientProtocol` parameters to
    `spawn_cold_path_diagnosis_task()` (both keyword-only, required), forward to
    `run_cold_path_diagnosis()`
  - [x] In `invoke_llm_node` inside `build_diagnosis_graph()`: import and call
    `from aiops_triage_pipeline.diagnosis.prompt import build_llm_prompt` then pass
    `prompt=build_llm_prompt(state["triage_excerpt"], state["evidence_summary"])` to
    `llm_client.invoke()`
  - [x] After `result = await asyncio.wait_for(graph.ainvoke(...), timeout=...)`, reconstruct report
    with `triage_hash`
  - [x] Write `diagnosis.json` after successful LLM response (before health update)
  - [x] Return the reconstructed `report` (with `triage_hash` populated) — do NOT return the original
    `raw_report`
  - [x] Add new imports: `from aiops_triage_pipeline.storage.client import ObjectStoreClientProtocol`
  - [x] Update module docstring to mention Story 6.3 additions

- [x] Task 4: Unit tests for `diagnosis/prompt.py` (new file: `tests/unit/diagnosis/test_prompt.py`)
  (AC: 2, 3, 7)
  - [x] `test_build_llm_prompt_returns_non_empty_string`
  - [x] `test_build_llm_prompt_contains_anomaly_family`
  - [x] `test_build_llm_prompt_contains_evidence_summary`
  - [x] `test_build_llm_prompt_instructs_json_output`
  - [x] `test_build_llm_prompt_instructs_unknown_propagation`
  - [x] `test_build_llm_prompt_instructs_evidence_citation`
  - [x] `test_build_llm_prompt_contains_evidence_status_map`
  - [x] All test functions sync; `_make_excerpt()` helper with PROD/TIER_0/sustained=True and populated evidence_status_map

- [x] Task 5: Update `tests/unit/diagnosis/test_graph.py` — new parameter signatures + persistence
  (AC: 4, 5, 7)
  - [x] Update ALL existing calls to `run_cold_path_diagnosis()` and `spawn_cold_path_diagnosis_task()` with new params
  - [x] `_FAKE_TRIAGE_HASH = "a" * 64` constant at module level
  - [x] `test_run_cold_path_diagnosis_populates_triage_hash`
  - [x] `test_run_cold_path_diagnosis_writes_diagnosis_json`
  - [x] `test_run_cold_path_diagnosis_casefile_triage_hash_matches`
  - [x] `test_spawn_cold_path_diagnosis_task_forwards_triage_hash`

- [x] Task 6: Update `tests/unit/integrations/test_llm.py` — LIVE mode prompt and structured parsing
  (AC: 1, 7)
  - [x] `test_live_mode_raises_if_prompt_is_none`
  - [x] `test_live_mode_sends_prompt_in_request_body`
  - [x] `test_live_mode_parses_structured_response_as_diagnosis_report`
  - [x] Existing MOCK/LOG mode tests pass; updated `test_live_mode_makes_http_post_to_base_url` for new LIVE behavior

- [x] Task 7: Quality gates
  - [x] `uv run ruff check` — 0 new errors
  - [x] `uv run pytest -q -m "not integration"` — 617 passed, 0 failures, 0 skipped (baseline 603 + 14 new tests)

## Dev Notes

### Developer Context Section

- Story key: `6-3-structured-diagnosisreport-output-and-evidence-citation`
- Story ID: 6.3
- Epic 6 context: Third story in Epic 6 (LLM-Enriched Diagnosis). Stories 6.1 and 6.2 are done:
  - 6.1: `LLMClient` with MOCK/LOG/LIVE modes + failure injection in `integrations/llm.py`
  - 6.2: Fire-and-forget LangGraph cold path in `diagnosis/graph.py`, in-flight gauge, invocation
    criteria, denylist enforcement — `run_cold_path_diagnosis()` currently returns `DiagnosisReportV1`
    in memory without writing to storage
  - 6.3 (this story): Prompt construction, structured LIVE response parsing, diagnosis.json write
  - 6.4 (next story): Schema validation failure handling, deterministic fallback for all LLM failure
    scenarios (unavailable / timeout / error / malformed) — fallback also writes `diagnosis.json`
- **Scope boundary**:
  - Story 6.3 adds: `diagnosis/prompt.py` (prompt builder), LIVE mode structured output parsing
    (replace stub), `diagnosis.json` write on successful LLM response, `triage_hash` hash chain
  - Story 6.3 does NOT add: schema validation failure handling, fallback writes to `diagnosis.json`,
    retry logic — all belong to Story 6.4
  - If `DiagnosisReportV1.model_validate(response_data)` raises `ValidationError` in Story 6.3,
    it propagates through the existing `BaseException` catch in `run_cold_path_diagnosis()` which
    logs and re-raises. Story 6.4 catches this and emits a fallback. This is intentional.

### Technical Requirements

**`diagnosis/prompt.py`** — structure:
```python
"""LLM diagnosis prompt builder — constructs structured prompt from triage context."""

from aiops_triage_pipeline.contracts.triage_excerpt import TriageExcerptV1


_SYSTEM_INSTRUCTION = """
You are a production incident diagnosis assistant for a Kafka-based AIOps platform.

Analyze the provided triage excerpt and evidence summary and produce a diagnosis report.

OUTPUT REQUIREMENTS:
- Respond ONLY with valid JSON matching the DiagnosisReportV1 schema (defined below)
- Do NOT include any text outside the JSON object
- Do NOT fabricate metric values, counts, or findings not present in the evidence pack
- If evidence is UNKNOWN or missing, propagate UNKNOWN — never assume presence or default to zero

EVIDENCE CITATION RULES:
- Cite only evidence IDs and keys explicitly provided in the evidence_status_map
- Reference specific findings by their finding_id from the findings list
- The evidence_pack.facts field must cite observable evidence (PRESENT status only)
- The evidence_pack.missing_evidence field must list any evidence with UNKNOWN/ABSENT/STALE status
- The evidence_pack.matched_rules field cites Rulebook finding IDs

DIAGNOSISREPORTV1 JSON SCHEMA:
{
  "schema_version": "v1",
  "case_id": "<string or null>",
  "verdict": "<non-empty string>",
  "fault_domain": "<string or null>",
  "confidence": "LOW" | "MEDIUM" | "HIGH",
  "evidence_pack": {
    "facts": ["<cited evidence fact>", ...],
    "missing_evidence": ["<UNKNOWN/ABSENT evidence ID>", ...],
    "matched_rules": ["<finding_id>", ...]
  },
  "next_checks": ["<recommended check>", ...],
  "gaps": ["<evidence gap>", ...],
  "reason_codes": [],
  "triage_hash": null
}
""".strip()


def build_llm_prompt(triage_excerpt: TriageExcerptV1, evidence_summary: str) -> str:
    """Build a structured LLM diagnosis prompt from triage context and evidence.

    Returns a single string containing system instructions and case context.
    The caller (diagnosis/graph.py) passes this as the 'prompt' field to LLMClient.invoke().
    Input is already denylist-sanitized by run_cold_path_diagnosis() before this is called.
    """
    # Format evidence_status_map for readability
    evidence_lines = "\n".join(
        f"  {key}: {status.value}" for key, status in triage_excerpt.evidence_status_map.items()
    )
    # Format findings
    findings_lines = "\n".join(
        f"  [{f.finding_id}] {f.name} (anomalous={f.is_anomalous})"
        for f in triage_excerpt.findings
    )

    case_context = f"""
CASE CONTEXT:
  case_id: {triage_excerpt.case_id}
  anomaly_family: {triage_excerpt.anomaly_family}
  topic: {triage_excerpt.topic}
  cluster_id: {triage_excerpt.cluster_id}
  stream_id: {triage_excerpt.stream_id}
  criticality_tier: {triage_excerpt.criticality_tier.value}
  sustained: {triage_excerpt.sustained}
  peak: {triage_excerpt.peak}
  env: {triage_excerpt.env.value}

EVIDENCE STATUS MAP (UNKNOWN = missing data — do NOT assume zero):
{evidence_lines if evidence_lines else "  (no evidence entries)"}

FINDINGS:
{findings_lines if findings_lines else "  (no findings)"}

EVIDENCE SUMMARY:
{evidence_summary}
""".strip()

    return f"{_SYSTEM_INSTRUCTION}\n\n{case_context}"
```

**`integrations/llm.py`** — updated LIVE branch:
```python
if self._mode == IntegrationMode.LIVE:
    if not self._base_url:
        raise ValueError("INTEGRATION_MODE_LLM=LIVE requires LLM_BASE_URL to be configured")
    if prompt is None:
        raise ValueError(
            "LIVE mode requires prompt to be provided by the caller (diagnosis/graph.py)"
        )
    import httpx  # Lazy import — only needed in LIVE mode

    body = {
        "case_id": case_id,
        "prompt": prompt,
    }
    async with httpx.AsyncClient(timeout=60.0) as client:
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        response = await client.post(
            f"{self._base_url}/diagnose",
            json=body,
            headers=headers,
        )
        response.raise_for_status()
    response_data = response.json()
    report = DiagnosisReportV1.model_validate(response_data)
    self._logger.info(
        "llm_invoke_live",
        mode=self._mode.value,
        case_id=case_id,
        status_code=response.status_code,
        verdict=report.verdict,
    )
    return report
```

**Updated `invoke()` signature** (full signature):
```python
async def invoke(
    self,
    case_id: str,
    triage_excerpt: TriageExcerptV1,
    evidence_summary: str,
    *,
    prompt: str | None = None,
) -> DiagnosisReportV1:
```

**`diagnosis/graph.py`** — updated `build_diagnosis_graph()` inner node:
```python
def build_diagnosis_graph(llm_client: LLMClient) -> Any:
    async def invoke_llm_node(state: ColdPathDiagnosisState) -> dict:
        from aiops_triage_pipeline.diagnosis.prompt import build_llm_prompt  # avoid circular at module level
        built_prompt = build_llm_prompt(state["triage_excerpt"], state["evidence_summary"])
        report = await llm_client.invoke(
            case_id=state["case_id"],
            triage_excerpt=state["triage_excerpt"],
            evidence_summary=state["evidence_summary"],
            prompt=built_prompt,
        )
        return {"diagnosis_report": report}
    # ... rest unchanged
```

**Note on import placement**: `from aiops_triage_pipeline.diagnosis.prompt import build_llm_prompt`
can be at module level (top of `graph.py`) since `graph.py` is already in the `diagnosis/` package
and `prompt.py` is a sibling module — no circular import risk. Use module-level import for clarity.

**`run_cold_path_diagnosis()` updated signature**:
```python
async def run_cold_path_diagnosis(
    *,
    case_id: str,
    triage_excerpt: TriageExcerptV1,
    evidence_summary: str,
    llm_client: LLMClient,
    denylist: DenylistV1,
    health_registry: HealthRegistry,
    object_store_client: ObjectStoreClientProtocol,  # NEW in Story 6.3
    triage_hash: str,                                 # NEW in Story 6.3
    timeout_seconds: float = 60.0,
) -> DiagnosisReportV1:
```

**Write flow inside `run_cold_path_diagnosis()` (after `result = await asyncio.wait_for(...)`):**
```python
raw_report = result["diagnosis_report"]
if raw_report is None:
    raise RuntimeError(f"LangGraph node did not populate diagnosis_report for case {case_id}")

# Reconstruct with triage_hash for hash chain (AC5)
report = DiagnosisReportV1.model_validate(
    {**raw_report.model_dump(mode="json"), "triage_hash": triage_hash, "case_id": case_id}
)

# Write diagnosis.json (AC4)
casefile_placeholder = CaseFileDiagnosisV1(
    case_id=case_id,
    diagnosis_report=report,
    triage_hash=triage_hash,
    diagnosis_hash=DIAGNOSIS_HASH_PLACEHOLDER,
)
computed_hash = compute_casefile_diagnosis_hash(casefile_placeholder)
casefile = CaseFileDiagnosisV1(
    case_id=case_id,
    diagnosis_report=report,
    triage_hash=triage_hash,
    diagnosis_hash=computed_hash,
)
persist_casefile_diagnosis_write_once(object_store_client=object_store_client, casefile=casefile)
_logger.info("cold_path_diagnosis_json_written", case_id=case_id, triage_hash=triage_hash)

await health_registry.update("llm", HealthStatus.HEALTHY)
_logger.info("cold_path_diagnosis_completed", case_id=case_id)
return report
```

**`spawn_cold_path_diagnosis_task()` updated signature** (forward new params):
```python
def spawn_cold_path_diagnosis_task(
    *,
    case_id: str,
    triage_excerpt: TriageExcerptV1,
    evidence_summary: str,
    llm_client: LLMClient,
    denylist: DenylistV1,
    health_registry: HealthRegistry,
    object_store_client: ObjectStoreClientProtocol,  # NEW in Story 6.3
    triage_hash: str,                                 # NEW in Story 6.3
    app_env: AppEnv,
    timeout_seconds: float = 60.0,
) -> "asyncio.Task[DiagnosisReportV1] | None":
```

**New imports in `diagnosis/graph.py`**:
```python
from aiops_triage_pipeline.diagnosis.prompt import build_llm_prompt
from aiops_triage_pipeline.models.case_file import CaseFileDiagnosisV1, DIAGNOSIS_HASH_PLACEHOLDER
from aiops_triage_pipeline.storage.casefile_io import (
    compute_casefile_diagnosis_hash,
    persist_casefile_diagnosis_write_once,
)
from aiops_triage_pipeline.storage.client import ObjectStoreClientProtocol
```

### Architecture Compliance

- **Import rules**: `diagnosis/` CAN import from `storage/` (not in "Cannot Import From" column).
  `storage/` is not in the explicit "Can Import From" list but is also not restricted — confirmed by
  the data flow diagram: "Cold Path: DiagnosisReport → Object Storage (diagnosis.json)".
  [Source: `artifact/planning-artifacts/architecture.md` import rules table, line 659]
- **`integrations/` cannot import `diagnosis/`**: the LIVE mode prompt is built by `diagnosis/graph.py`
  and passed as `prompt: str` to `llm_client.invoke()`. `llm.py` never imports `prompt.py`.
  [Source: `artifact/planning-artifacts/architecture.md` import rules table, line 661]
- **Write-once invariant**: `persist_casefile_diagnosis_write_once()` enforces write-once semantics
  with idempotent retry. Duplicate calls for the same `case_id` and matching payload succeed silently.
  [Source: `src/aiops_triage_pipeline/storage/casefile_io.py`]
- **Hash chain**: `CaseFileDiagnosisV1.triage_hash` references the SHA-256 of `triage.json` —
  passed from the hot path. The `DiagnosisReportV1.triage_hash` is also populated (the report
  embeds the chain reference for auditors reading the report without the casefile wrapper).
  [Source: `docs/architecture.md` § Handoff Artifact, `models/case_file.py` `CaseFileDiagnosisV1`]
- **Denylist boundary**: `prompt.py` operates on already-sanitized `triage_excerpt` (denylist applied
  by `run_cold_path_diagnosis()` before prompt construction — same as Story 6.2). No additional
  `apply_denylist()` call needed inside `prompt.py`.
  [Source: `docs/architecture.md` § LLM Input Bounds; `diagnosis/graph.py` denylist logic]
- **UNKNOWN propagation**: `build_llm_prompt()` explicitly instructs the LLM: do NOT assume zero,
  do NOT fabricate values for UNKNOWN evidence. The `evidence_status_map` is included in the prompt
  so the LLM can identify which evidence is UNKNOWN (FR38).
- **`diagnosis.json` object path**: `cases/{case_id}/diagnosis.json` — built by
  `build_casefile_stage_object_key(case_id=case_id, stage="diagnosis")` inside
  `persist_casefile_diagnosis_write_once()`.
  [Source: `src/aiops_triage_pipeline/storage/casefile_io.py:192`]
- **Story 6.4 handoff**: The `BaseException` catch in `run_cold_path_diagnosis()` is preserved as-is.
  Story 6.4 will modify the except block to emit fallback reports and write fallback `diagnosis.json`.
  Story 6.3 must NOT add fallback logic.

### Library / Framework Requirements

Verification date: 2026-03-07.

- **`DiagnosisReportV1.model_validate(data: dict)`**: Pydantic v2 validation from a dict. All
  required fields (`verdict`, `confidence`, `evidence_pack`) must be present in the dict or
  `ValidationError` is raised. `schema_version` defaults to `"v1"` if omitted. `case_id` and
  `triage_hash` are optional (`str | None`). `next_checks`, `gaps`, `reason_codes` default to `()`.
  [Source: `src/aiops_triage_pipeline/contracts/diagnosis_report.py`]
- **`CaseFileDiagnosisV1(frozen=True)`**: requires `case_id: str`, `diagnosis_report: DiagnosisReportV1`,
  `triage_hash: str` (64-char hex), `diagnosis_hash: str` (64-char hex). The `_validate_hash_fields`
  validator rejects non-64-char strings. Use `DIAGNOSIS_HASH_PLACEHOLDER = "0" * 64` for the initial
  computation. [Source: `src/aiops_triage_pipeline/models/case_file.py:117`]
- **`compute_casefile_diagnosis_hash(casefile: CaseFileDiagnosisV1) -> str`**: temporarily replaces
  `diagnosis_hash` with placeholder, serializes to JSON, returns SHA-256 hex. The input `casefile`
  must have `diagnosis_hash=DIAGNOSIS_HASH_PLACEHOLDER` for correct computation.
  [Source: `src/aiops_triage_pipeline/storage/casefile_io.py:85`]
- **`persist_casefile_diagnosis_write_once(*, object_store_client, casefile)`**: validates that
  `casefile.diagnosis_hash == compute_casefile_diagnosis_hash(casefile)` before persisting (raises
  `InvariantViolation` otherwise). Returns `CasefileStagePersistResult`.
  [Source: `src/aiops_triage_pipeline/storage/casefile_io.py:235`]
- **`ObjectStoreClientProtocol`**: Protocol with `put_if_absent(key, body, content_type, checksum_sha256, metadata)`,
  `get_object_bytes(key)`. For unit tests, use `unittest.mock.MagicMock(spec=ObjectStoreClientProtocol)`.
  Set `put_if_absent.return_value = PutIfAbsentResult.CREATED`. For the idempotent check path to
  not trigger, stub `get_object_bytes` to raise `ObjectNotFoundError` (since `CREATED` = new write,
  `get_object_bytes` is only called on `ALREADY_EXISTS`).
  [Source: `src/aiops_triage_pipeline/storage/client.py:65`]
- **`response.json()`** (httpx): returns a `dict[str, Any]` from the JSON response body. If the
  response body is not valid JSON, raises `httpx.DecodingError`. The LLM endpoint MUST return
  `Content-Type: application/json` with a body matching `DiagnosisReportV1` schema.
- **`PutIfAbsentResult`**: `StrEnum` in `storage/client.py`; values `CREATED` and `ALREADY_EXISTS`.
  Import: `from aiops_triage_pipeline.storage.client import PutIfAbsentResult`.

### File Structure Requirements

**New files to create:**
- `src/aiops_triage_pipeline/diagnosis/prompt.py` — LLM prompt builder (currently 1 empty line)
- `tests/unit/diagnosis/test_prompt.py` — unit tests for `build_llm_prompt()`

**Files to modify:**
- `src/aiops_triage_pipeline/diagnosis/graph.py` — new params for `run_cold_path_diagnosis()` and
  `spawn_cold_path_diagnosis_task()`; prompt building in node; diagnosis.json write; new imports
- `src/aiops_triage_pipeline/integrations/llm.py` — `prompt` kwarg on `invoke()`; LIVE mode
  structured parsing; updated docstring
- `tests/unit/diagnosis/test_graph.py` — update existing tests with new params; add new tests
- `tests/unit/integrations/test_llm.py` — add 3 LIVE mode tests for prompt/parsing behavior

**Files to read before implementing (do not modify):**
- `src/aiops_triage_pipeline/models/case_file.py` — `CaseFileDiagnosisV1` fields and validators
- `src/aiops_triage_pipeline/storage/casefile_io.py` — `persist_casefile_diagnosis_write_once()`,
  `compute_casefile_diagnosis_hash()`, `DIAGNOSIS_HASH_PLACEHOLDER` (imported from `models/case_file.py`)
- `src/aiops_triage_pipeline/storage/client.py` — `ObjectStoreClientProtocol`, `PutIfAbsentResult`
- `src/aiops_triage_pipeline/contracts/triage_excerpt.py` — `TriageExcerptV1` fields for prompt
- `src/aiops_triage_pipeline/contracts/gate_input.py` — `Finding` type (used in triage_excerpt.findings)
- `src/aiops_triage_pipeline/diagnosis/graph.py` — current implementation to understand what changes
- `src/aiops_triage_pipeline/integrations/llm.py` — current LIVE mode to understand what to replace
- `tests/unit/diagnosis/test_graph.py` — all existing tests to update signatures
- `tests/unit/integrations/test_llm.py` — all existing tests to update if needed

**Files NOT to modify:**
- `src/aiops_triage_pipeline/contracts/diagnosis_report.py` — contract is correct and frozen
- `src/aiops_triage_pipeline/diagnosis/fallback.py` — fallback builder unchanged (Story 6.4 scope)
- `src/aiops_triage_pipeline/pipeline/stages/` — any file; hot-path stages are off-limits
- `src/aiops_triage_pipeline/models/case_file.py` — model is correct; only read it

### Previous Story Intelligence

From Story 6.2 (`6-2-cold-path-llm-invocation-and-hot-path-independence.md`):
- **Baseline test count after code review**: 608 passed, 0 skipped, 0 failures (non-integration).
  Current re-run shows **603 passed** with 17 deselected + errors (some integration tests failing
  from missing Docker). Run `uv run pytest -q -m "not integration"` to confirm current baseline
  before starting. Expect 603 as your unit test baseline.
- **`run_cold_path_diagnosis()` current return**: `DiagnosisReportV1` without `triage_hash`.
  Story 6.3 reconstructs it with `triage_hash` before returning. This is a non-breaking change
  to return type (same type, now with a field populated).
- **Story 6.2 code review M1 fix**: `build_diagnosis_graph()` is inside the `try` block in
  `run_cold_path_diagnosis()`. Preserve this — `build_diagnosis_graph()` must remain inside `try`
  so `finally: llm_inflight_add(-1)` always balances.
- **Story 6.2 code review M2 fix**: `None` check on `result["diagnosis_report"]` is already in
  place. In Story 6.3, the `None` check happens BEFORE the triage_hash reconstruction. Keep it.
- **`asyncio_mode=auto`**: all async test functions run automatically. New tests for prompt.py
  are sync (`def test_*() -> None`) — `build_llm_prompt` is a sync function.
- **`_make_eligible_excerpt()` helper**: already in `test_graph.py`. For `test_prompt.py`, create
  a new `_make_excerpt()` helper with PROD env, TIER_0, sustained=True, and a populated
  `evidence_status_map` (include at least one UNKNOWN and one PRESENT entry).
- **`settings.py` pattern**: `Settings(_env_file=None, APP_ENV="prod", ...)` for LIVE mode tests —
  no new settings fields needed in Story 6.3.
- **`get_settings.cache_clear()`**: call before any test that constructs `Settings()` via singleton.

From recent commits:
- `82cedbc` review: fix code review findings for story 6.2 — baseline is this commit state
- `de3d138` story 6.2: cold-path llm invocation and hot-path independence

### Git Intelligence Summary

Recent commits (most recent first):
- `82cedbc` review: fix code review findings for story 6.2
- `de3d138` story 6.2: cold-path LLM invocation and hot-path independence
- `913466e` story 6.1: implement LLM stub and failure-injection mode
- `173274f` refactor: clarify confidence_floor is a no-op
- `edd65c8` docs: add cold-path/hot-path handoff contract to architecture

Actionable patterns:
- Story 6.2 test discipline: one function per scenario, `async def` for async tests, sync `def`
  for sync tests. New tests in `test_prompt.py` are sync — do NOT add `asyncio_mode=auto` markers.
- Update ALL existing `test_graph.py` calls to `run_cold_path_diagnosis()` and
  `spawn_cold_path_diagnosis_task()`. There are at least 10 existing test functions in that file —
  missing one will cause a `TypeError: unexpected keyword argument` or `missing required argument`
  failure at runtime. Do not be lazy — update every call.
- The `_make_eligible_excerpt()` helper in `test_graph.py` creates `env=Environment.PROD`,
  `criticality_tier=CriticalityTier.TIER_0`, `sustained=True`. For `test_prompt.py`'s helper,
  add `evidence_status_map={"consumer_lag": EvidenceStatus.UNKNOWN, "throughput": EvidenceStatus.PRESENT}`
  and `findings=(...)` with at least one Finding. Check `gate_input.py` for Finding constructor.

### Latest Tech Information

Verification date: 2026-03-07.

- **`DiagnosisReportV1.model_validate(data)`**: Pydantic v2.12.5. If `data` contains extra fields
  not in the model, they are ignored (no `model_config = ConfigDict(extra="forbid")`). If required
  fields are missing, `ValidationError` is raised. For `verdict: Annotated[str, Field(min_length=1)]`,
  an empty string raises `ValidationError`. `evidence_pack` must be a dict or `EvidencePack` instance;
  if passing a dict: `{"facts": [], "missing_evidence": [], "matched_rules": []}` — empty lists
  work (no min-length constraint). Tuples vs lists: Pydantic v2 accepts lists for `tuple[str, ...]`
  fields during validation and converts them.
- **`httpx 0.27` `response.json()`**: synchronous method on `httpx.Response`. Returns `Any` (usually
  `dict`). If the response body is empty or not JSON, raises `httpx.DecodingError`. Always use
  `response.raise_for_status()` BEFORE `response.json()` to ensure non-2xx exceptions are raised first.
- **`model_dump(mode="json")`**: returns a dict with JSON-safe values (enum → `.value`, datetime →
  ISO string, tuple → list). Use `{**raw_report.model_dump(mode="json"), "triage_hash": triage_hash}`
  to merge — the spread creates a new dict, preserving all existing fields.
- **`CaseFileDiagnosisV1` frozen=True validation**: the `_validate_hash_fields` validator requires
  both `triage_hash` and `diagnosis_hash` to be exactly 64-char lowercase hex. Passing `"a" * 64`
  (64 'a' chars) is valid. Passing any string of wrong length raises `ValidationError` immediately.

### Project Context Reference

Applied rules from `artifact/project-context.md`:
- **Consistency over novelty**: reuse `compute_casefile_diagnosis_hash()` and
  `persist_casefile_diagnosis_write_once()` from `storage/casefile_io.py` — identical pattern
  to how `persist_casefile_triage_write_once()` works. No ad-hoc serialization.
- **Never fabricate**: `build_llm_prompt()` must EXPLICITLY instruct the LLM not to fabricate.
  This is a FR38 compliance requirement — include it verbatim in the system instruction.
- **No placeholder-only coverage**: `test_build_llm_prompt_contains_unknown_propagation_instruction()`
  must assert on the actual text content, not just that `len(prompt) > 0`.
- **Immutable frozen models**: `DiagnosisReportV1` is `frozen=True`. Reconstruct via
  `DiagnosisReportV1.model_validate({...})` — do NOT attempt `model_copy(update={...})`.
  Same for `CaseFileDiagnosisV1`.
- **Test discipline**: use `MagicMock(spec=ObjectStoreClientProtocol)` not bare `MagicMock()` for
  the store — `spec` catches typos in method names at test time.
- **No silent fallbacks**: Story 6.3 does NOT add fallback in the except block — exceptions from
  `model_validate()` or storage writes propagate. Story 6.4 owns fallback.

### Project Structure Notes

- `src/aiops_triage_pipeline/diagnosis/prompt.py` — currently 1 empty line; implement here
- `tests/unit/diagnosis/test_prompt.py` — new file; `tests/unit/diagnosis/__init__.py` already exists
- `tests/unit/diagnosis/test_graph.py` — already exists with 15+ tests; update ALL signatures
- `tests/unit/integrations/test_llm.py` — already exists; add 3 new tests at the bottom
- `src/aiops_triage_pipeline/storage/casefile_io.py` — `DIAGNOSIS_HASH_PLACEHOLDER` is imported
  from `models/case_file.py` via `from aiops_triage_pipeline.models.case_file import DIAGNOSIS_HASH_PLACEHOLDER`
  — note: `casefile_io.py` itself re-imports it, so use the canonical source at `models/case_file.py`

### References

- [Source: `artifact/planning-artifacts/epics.md#Story 6.3`]
- [Source: `docs/architecture.md#Cold-Path / Hot-Path Handoff Contract` — write-once, hash chain,
  UNKNOWN propagation, LLM input bounds, fallback posture, boundary rules]
- [Source: `artifact/planning-artifacts/architecture.md` decision 4B (fire-and-forget LangGraph);
  decision 1C (object storage layout: `cases/{case_id}/{stage}.json`); import rules table line 659;
  cross-cutting concerns table (denylist at LLM narrative surfacing boundary)]
- [Source: `artifact/project-context.md` — consistency rules, UNKNOWN propagation, test discipline]
- [Source: `src/aiops_triage_pipeline/contracts/diagnosis_report.py` — `DiagnosisReportV1`,
  `EvidencePack`, `DiagnosisConfidence`, `triage_hash: str | None = None`]
- [Source: `src/aiops_triage_pipeline/models/case_file.py` — `CaseFileDiagnosisV1` (triage_hash +
  diagnosis_hash validators), `DIAGNOSIS_HASH_PLACEHOLDER`]
- [Source: `src/aiops_triage_pipeline/storage/casefile_io.py` — `persist_casefile_diagnosis_write_once()`,
  `compute_casefile_diagnosis_hash()`, `build_casefile_stage_object_key()`]
- [Source: `src/aiops_triage_pipeline/storage/client.py` — `ObjectStoreClientProtocol`, `PutIfAbsentResult`]
- [Source: `src/aiops_triage_pipeline/contracts/triage_excerpt.py` — `TriageExcerptV1` all fields]
- [Source: `src/aiops_triage_pipeline/contracts/gate_input.py` — `Finding` fields]
- [Source: `src/aiops_triage_pipeline/diagnosis/graph.py` — current implementation (Story 6.2)]
- [Source: `src/aiops_triage_pipeline/integrations/llm.py` — current LIVE stub to replace]
- [Source: `artifact/implementation-artifacts/6-2-cold-path-llm-invocation-and-hot-path-independence.md`
  — regression baseline 608 tests (re-confirm at 603 unit), code review fixes M1/M2, test helpers]

## Dev Agent Record

### Agent Model Used

claude-sonnet-4-6

### Debug Log References

### Completion Notes List

- Implemented `diagnosis/prompt.py` with `build_llm_prompt()` — structured prompt with system instruction, UNKNOWN propagation rule, evidence citation rules, DiagnosisReportV1 JSON schema, and formatted case context (evidence_status_map, findings, evidence_summary)
- Updated `integrations/llm.py`: added `prompt: str | None = None` kwarg; LIVE mode now validates prompt is provided, sends `{"case_id", "prompt"}` body, parses structured JSON response via `DiagnosisReportV1.model_validate()`, logs `llm_invoke_live`; removed `LLM_LIVE_STUB` stub return
- Updated `diagnosis/graph.py`: added `object_store_client` and `triage_hash` to `run_cold_path_diagnosis()` and `spawn_cold_path_diagnosis_task()`; `invoke_llm_node` now builds prompt via `build_llm_prompt()`; after LLM returns, reconstructs `DiagnosisReportV1` with `triage_hash`, builds `CaseFileDiagnosisV1` with computed hash, writes `diagnosis.json` via `persist_casefile_diagnosis_write_once()`
- Added 7 unit tests in `tests/unit/diagnosis/test_prompt.py`
- Added 4 new tests + updated 6 existing tests in `tests/unit/diagnosis/test_graph.py`
- Added 3 new tests + updated `test_live_mode_makes_http_post_to_base_url` in `tests/unit/integrations/test_llm.py`
- Final: 617 passed (603 baseline + 14 new), 0 failures, 0 skipped

### Change Log

- 2026-03-07: Story 6.3 implementation complete — structured DiagnosisReport output, evidence citation prompt, triage_hash hash chain, diagnosis.json write-once persistence, LIVE mode structured parsing

### File List

- `src/aiops_triage_pipeline/diagnosis/prompt.py` (created)
- `src/aiops_triage_pipeline/integrations/llm.py` (modified)
- `src/aiops_triage_pipeline/diagnosis/graph.py` (modified)
- `tests/unit/diagnosis/test_prompt.py` (created)
- `tests/unit/diagnosis/test_graph.py` (modified)
- `tests/unit/integrations/test_llm.py` (modified)
- `artifact/implementation-artifacts/sprint-status.yaml` (modified)
