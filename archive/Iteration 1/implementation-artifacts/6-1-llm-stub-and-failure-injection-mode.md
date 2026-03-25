# Story 6.1: LLM Stub & Failure-Injection Mode

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a platform developer,
I want the pipeline to run with LLM in stub and failure-injection modes for local and test
environments,
so that end-to-end pipeline testing works without external LLM API calls while prod always uses
live LLM (FR41).

## Acceptance Criteria

1. **Given** the pipeline is running in local or test environment
   **When** LLM stub mode is active (`INTEGRATION_MODE_LLM=MOCK`)
   **Then** the LLM stub produces a deterministic schema-valid `DiagnosisReportV1` with:
   `verdict="UNKNOWN"`, `confidence=DiagnosisConfidence.LOW`, `reason_codes=("LLM_STUB",)`
2. **And** no external LLM API calls are made in stub mode — `LLMClient.invoke()` in MOCK mode
   returns the stub report without any network I/O
3. **And** the stub client can be instantiated and `invoke()`d in unit tests (simulating
   cold-path invocation) with the stub output received and schema-validated
4. **When** failure-injection mode is active (via `LLMFailureMode` parameter)
   **Then** the following scenarios can be simulated, each producing the corresponding
   deterministic fallback `DiagnosisReportV1`:
   - Timeout → `reason_codes=("LLM_TIMEOUT",)`, `verdict="UNKNOWN"`, `confidence=LOW`
   - Unavailability → `reason_codes=("LLM_UNAVAILABLE",)`, `verdict="UNKNOWN"`, `confidence=LOW`
   - Malformed/schema-invalid output → `reason_codes=("LLM_SCHEMA_INVALID",)`, `verdict="UNKNOWN"`,
     `confidence=LOW`
   - Error response → `reason_codes=("LLM_ERROR",)`, `verdict="UNKNOWN"`, `confidence=LOW`
5. **When** the environment is `APP_ENV=prod`
   **Then** `INTEGRATION_MODE_LLM=MOCK` or `INTEGRATION_MODE_LLM=OFF` causes startup validation to
   raise `ValueError` — prod requires LIVE (or LOG as safe default)
6. **And** unit tests verify: stub output schema validity, no external calls in stub mode, each
   failure-injection scenario produces correct `reason_codes`, prod mode enforcement rejects MOCK
   and OFF

## Tasks / Subtasks

- [x] Task 1: Implement `diagnosis/fallback.py` — deterministic fallback report builder (AC: 1, 4)
  - [x] `build_fallback_report(reason_codes: tuple[str, ...], case_id: str | None = None) → DiagnosisReportV1`
  - [x] Returns `DiagnosisReportV1` with `verdict="UNKNOWN"`, `confidence=DiagnosisConfidence.LOW`,
    empty `EvidencePack(facts=(), missing_evidence=(), matched_rules=())`
  - [x] `case_id=None` is valid (fallback scenarios before case context is established)
  - [x] `triage_hash=None` (hash chain populated in Story 6.3)

- [x] Task 2: Implement `integrations/llm.py` — `LLMClient` with stub and failure injection (AC: 1, 2, 3, 4)
  - [x] `LLMFailureMode` enum: `NONE`, `TIMEOUT`, `UNAVAILABLE`, `MALFORMED`, `ERROR`
  - [x] `LLMClient(mode: IntegrationMode, failure_mode: LLMFailureMode = LLMFailureMode.NONE)`
  - [x] `async def invoke(case_id: str, triage_excerpt: TriageExcerptV1, evidence_summary: str) → DiagnosisReportV1`
  - [x] MOCK + `NONE` → `build_fallback_report(("LLM_STUB",), case_id)`
  - [x] MOCK + `TIMEOUT` → `build_fallback_report(("LLM_TIMEOUT",), case_id)`
  - [x] MOCK + `UNAVAILABLE` → `build_fallback_report(("LLM_UNAVAILABLE",), case_id)`
  - [x] MOCK + `MALFORMED` → `build_fallback_report(("LLM_SCHEMA_INVALID",), case_id)`
  - [x] MOCK + `ERROR` → `build_fallback_report(("LLM_ERROR",), case_id)`
  - [x] LOG mode → same as MOCK + NONE: return stub report (LOG is safe, not disabling)
  - [x] OFF mode → raise `ValueError("INTEGRATION_MODE_LLM=OFF is not a valid LLM operation mode")`
  - [x] LIVE mode → `raise NotImplementedError("LLM LIVE mode not implemented until Story 6.2")`
  - [x] Log a structured event for every invocation (mode, failure_mode, case_id, reason_codes)
  - [x] No external HTTP calls in any mode in this story

- [x] Task 3: Add prod enforcement validator to `config/settings.py` (AC: 5)
  - [x] In the existing `model_validator(mode="after")` (currently `validate_kerberos_files`):
    add prod-mode LLM check, OR add a separate named `model_validator(mode="after")` method
  - [x] If `APP_ENV == AppEnv.prod` and `INTEGRATION_MODE_LLM in (IntegrationMode.OFF, IntegrationMode.MOCK)`:
    raise `ValueError(f"INTEGRATION_MODE_LLM must be LIVE in prod; got {self.INTEGRATION_MODE_LLM.value}")`
  - [x] LOG is intentionally allowed in prod as safe default (non-destructive, emits structured log)
  - [x] LIVE is required for actual production diagnosis invocation

- [x] Task 4: Unit tests for `diagnosis/fallback.py` (AC: 6)
  - [x] `tests/unit/diagnosis/test_fallback.py`
  - [x] Test: `build_fallback_report(("LLM_STUB",))` → schema_version="v1", verdict="UNKNOWN",
    confidence=DiagnosisConfidence.LOW, reason_codes=("LLM_STUB",), case_id=None
  - [x] Test: `build_fallback_report(("LLM_TIMEOUT",), case_id="case-123")` → case_id set correctly
  - [x] Test: `build_fallback_report(("LLM_UNAVAILABLE",))` → correct fields
  - [x] Test: `build_fallback_report(("LLM_SCHEMA_INVALID",))` → correct fields
  - [x] Test: `build_fallback_report(("LLM_ERROR",))` → correct fields
  - [x] Test: returned model is frozen — mutation raises `ValidationError` or `TypeError`
  - [x] Test: `evidence_pack` is an `EvidencePack` with all empty tuples

- [x] Task 5: Unit tests for `integrations/llm.py` (AC: 1, 2, 3, 4, 6)
  - [x] `tests/unit/integrations/test_llm.py`
  - [x] Test stub (MOCK, NONE): `await client.invoke(...)` returns `DiagnosisReportV1` with
    `reason_codes=("LLM_STUB",)`, `verdict="UNKNOWN"`, `confidence=LOW`; no HTTP call
  - [x] Test failure injection TIMEOUT: `reason_codes=("LLM_TIMEOUT",)`
  - [x] Test failure injection UNAVAILABLE: `reason_codes=("LLM_UNAVAILABLE",)`
  - [x] Test failure injection MALFORMED: `reason_codes=("LLM_SCHEMA_INVALID",)`
  - [x] Test failure injection ERROR: `reason_codes=("LLM_ERROR",)`
  - [x] Test LOG mode: returns same stub DiagnosisReport as MOCK+NONE
  - [x] Test OFF mode: raises `ValueError`
  - [x] Test LIVE mode: raises `NotImplementedError`
  - [x] Test case_id propagated: `report.case_id == case_id` for all non-OFF/LIVE modes
  - [x] All tests are `async def` using pytest-asyncio (`asyncio_mode=auto` is active)

- [x] Task 6: Unit tests for prod mode enforcement in `config/settings.py` (AC: 5, 6)
  - [x] Add to `tests/unit/config/test_settings.py`
  - [x] Test: `APP_ENV=prod` + `INTEGRATION_MODE_LLM=MOCK` → `Settings(...)` raises `ValidationError`
  - [x] Test: `APP_ENV=prod` + `INTEGRATION_MODE_LLM=OFF` → `Settings(...)` raises `ValidationError`
  - [x] Test: `APP_ENV=prod` + `INTEGRATION_MODE_LLM=LIVE` → `Settings(...)` succeeds
  - [x] Test: `APP_ENV=prod` + `INTEGRATION_MODE_LLM=LOG` → `Settings(...)` succeeds (LOG allowed)
  - [x] Test: `APP_ENV=local` + `INTEGRATION_MODE_LLM=MOCK` → `Settings(...)` succeeds
  - [x] Use `Settings(_env_file=None, APP_ENV="prod", INTEGRATION_MODE_LLM="MOCK", ...)` pattern
    (matches existing test pattern in the file)
  - [x] Call `get_settings.cache_clear()` before any test that constructs `Settings()` via the
    singleton path

- [x] Task 7: Quality gates
  - [x] `uv run ruff check` — 0 errors
  - [x] `uv run pytest -q -m "not integration"` — 585 passed (24 new), 0 skipped, 0 failures

## Dev Notes

### Developer Context Section

- Story key: `6-1-llm-stub-and-failure-injection-mode`
- Story ID: 6.1
- Epic 6 context: First story in Epic 6 (LLM-Enriched Diagnosis). This story builds the stub and
  failure-injection infrastructure that all subsequent Epic 6 stories depend on. Stories 6.2–6.4
  build on top of the `LLMClient` and `build_fallback_report` foundations created here.
- **Scope boundary**: This story creates `integrations/llm.py`, `diagnosis/fallback.py`, and
  modifies `config/settings.py`. It does NOT implement any real LangGraph graph execution
  (`diagnosis/graph.py` stays empty), any real LLM HTTP calls, or any prompt construction
  (`diagnosis/prompt.py` stays empty). The LIVE mode placeholder raises `NotImplementedError`.
- **Key invariant**: `LLMClient` in MOCK mode MUST NOT make any network calls — this is testable
  and critical for CI environments without LLM access.

### Technical Requirements

**`diagnosis/fallback.py`** — deterministic fallback report builder:
```python
from aiops_triage_pipeline.contracts.diagnosis_report import DiagnosisReportV1, EvidencePack
from aiops_triage_pipeline.contracts.enums import DiagnosisConfidence


def build_fallback_report(
    reason_codes: tuple[str, ...],
    case_id: str | None = None,
) -> DiagnosisReportV1:
    return DiagnosisReportV1(
        case_id=case_id,
        verdict="UNKNOWN",
        fault_domain=None,
        confidence=DiagnosisConfidence.LOW,
        evidence_pack=EvidencePack(facts=(), missing_evidence=(), matched_rules=()),
        next_checks=(),
        gaps=(),
        reason_codes=reason_codes,
        triage_hash=None,
    )
```

**`integrations/llm.py`** — LLM client with stub and failure injection:
```python
from enum import Enum
from aiops_triage_pipeline.config.settings import IntegrationMode
from aiops_triage_pipeline.contracts.diagnosis_report import DiagnosisReportV1
from aiops_triage_pipeline.contracts.triage_excerpt import TriageExcerptV1  # check actual path
from aiops_triage_pipeline.diagnosis.fallback import build_fallback_report
from aiops_triage_pipeline.logging.setup import get_logger


class LLMFailureMode(str, Enum):
    NONE = "NONE"
    TIMEOUT = "TIMEOUT"
    UNAVAILABLE = "UNAVAILABLE"
    MALFORMED = "MALFORMED"
    ERROR = "ERROR"


_FAILURE_REASON_CODES: dict[LLMFailureMode, str] = {
    LLMFailureMode.NONE: "LLM_STUB",
    LLMFailureMode.TIMEOUT: "LLM_TIMEOUT",
    LLMFailureMode.UNAVAILABLE: "LLM_UNAVAILABLE",
    LLMFailureMode.MALFORMED: "LLM_SCHEMA_INVALID",
    LLMFailureMode.ERROR: "LLM_ERROR",
}


class LLMClient:
    def __init__(
        self,
        mode: IntegrationMode,
        failure_mode: LLMFailureMode = LLMFailureMode.NONE,
    ) -> None:
        self._mode = mode
        self._failure_mode = failure_mode
        self._logger = get_logger(__name__)

    async def invoke(
        self,
        case_id: str,
        triage_excerpt: TriageExcerptV1,
        evidence_summary: str,
    ) -> DiagnosisReportV1:
        if self._mode == IntegrationMode.OFF:
            raise ValueError("INTEGRATION_MODE_LLM=OFF is not a valid LLM operation mode")
        if self._mode == IntegrationMode.LIVE:
            raise NotImplementedError("LLM LIVE mode not implemented until Story 6.2")
        # MOCK and LOG: return deterministic stub/fallback
        reason_code = _FAILURE_REASON_CODES[self._failure_mode]
        report = build_fallback_report((reason_code,), case_id=case_id)
        self._logger.info(
            "llm_invoke_stub",
            mode=self._mode.value,
            failure_mode=self._failure_mode.value,
            case_id=case_id,
            reason_codes=report.reason_codes,
        )
        return report
```

**`TriageExcerptV1` import path** — check the correct path before implementing:
```python
from aiops_triage_pipeline.contracts.triage_excerpt import TriageExcerptV1
# OR
from aiops_triage_pipeline.contracts.case_header_event import TriageExcerptV1
```
Read `src/aiops_triage_pipeline/contracts/` to find the correct module for `TriageExcerptV1`.

**`config/settings.py` prod enforcement** — add inside the existing `model_validator` or as a
separate named validator. Pydantic v2 allows multiple `model_validator(mode="after")` methods
if they have distinct names:
```python
@model_validator(mode="after")
def validate_llm_prod_mode(self) -> "Settings":
    if (
        self.APP_ENV == AppEnv.prod
        and self.INTEGRATION_MODE_LLM in (IntegrationMode.OFF, IntegrationMode.MOCK)
    ):
        raise ValueError(
            f"INTEGRATION_MODE_LLM must be LIVE in prod environment; "
            f"got {self.INTEGRATION_MODE_LLM.value}"
        )
    return self
```

**Logging pattern** — use `get_logger(__name__)` from `aiops_triage_pipeline.logging.setup`.
Structured event name: `"llm_invoke_stub"`. Key-value fields: `mode`, `failure_mode`, `case_id`,
`reason_codes`. Match the structlog style in all other integration files.

**`DiagnosisConfidence` enum** (from `contracts/enums.py`):
```python
class DiagnosisConfidence(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
```

**`confidence_floor` in `GateEffect` is NOT the same as `DiagnosisReportV1.confidence`**:
`GateEffect.confidence_floor` is a reserved gate-engine field with zero runtime effect on
`ActionDecisionV1` output (see commit 173274f). Do not conflate these. The LLM confidence lives
entirely in `DiagnosisReportV1.confidence` and has no effect on hot-path gating decisions.

### Architecture Compliance

- **Hot/cold path separation**: `LLMClient` is cold-path only. It must never be imported or
  instantiated from `pipeline/stages/`. Import rules table prohibits `pipeline/` from importing
  `diagnosis/` internals. [Source: `artifact/planning-artifacts/architecture.md` import rules table]
- **`diagnosis/` import boundary**: `diagnosis/` may import from `contracts/`, `models/`,
  `config/`, `health/`, `errors/`, `logging/`. It must NOT import from `pipeline/` or `outbox/`.
- **`integrations/llm.py` import boundary**: `integrations/` may import from `contracts/`,
  `config/`, `errors/`, `logging/`. Must NOT import from `pipeline/` or `diagnosis/` internals.
  `LLMClient` in `integrations/llm.py` may import `build_fallback_report` from `diagnosis/fallback.py`
  ONLY IF `diagnosis/` is classified as an allowed dependency for `integrations/`. If not, move
  `build_fallback_report` call into `diagnosis/` and have `integrations/llm.py` expose only the
  raw failure mode semantics. **Preferred resolution**: place `build_fallback_report` in
  `diagnosis/fallback.py` and let `integrations/llm.py` import it — `integrations/` imports
  `contracts/` and shared packages, not pipeline stages. This is acceptable if it doesn't violate
  the one-way import rule. Verify against the import rules table before implementing.
- **IntegrationMode**: reuse the global `IntegrationMode` from `config/settings.py` — do NOT
  create a separate `LLMIntegrationMode` enum (unlike PD/Slack which have their own enums, LLM
  is controlled centrally via `INTEGRATION_MODE_LLM` in `Settings`).
- **Non-destructive default**: `IntegrationMode.LOG` is the default and must remain safe — no
  outbound calls, no side effects.
- **Prod enforcement**: MOCK and OFF are rejected in prod at startup (Settings validator). LOG is
  intentionally allowed as a safe default — operators choosing LOG in prod get stub output with
  structured logging. LIVE is the intended prod mode once Story 6.2 implements the real graph.
  [Source: `docs/architecture.md` § Fallback Posture; `docs/architecture.md` § Invocation Criteria]
- **No retry in a single cycle**: Story 6.1 has no retry logic. Story 6.4 will handle the
  no-retry invariant for real LLM calls. [Source: `docs/architecture.md` § LLM Input Bounds, NFR-P4]

### Library / Framework Requirements

Verification date: 2026-03-07.

- **Python 3.13 typing**: use `X | None`, built-in generics (`tuple[str, ...]`, not `Tuple[str, ...]`).
- **Pydantic v2 `frozen=True`**: `DiagnosisReportV1` and `EvidencePack` are already frozen.
  `build_fallback_report` returns a frozen model — mutation in tests must fail.
- **pytest-asyncio `asyncio_mode=auto`**: all `async def` tests in `test_llm.py` run automatically
  without `@pytest.mark.asyncio`. Do NOT add the marker explicitly (it's set globally in
  `pyproject.toml`).
- **structlog**: use `get_logger(__name__)` from `aiops_triage_pipeline.logging.setup`. The
  logging pipeline is already configured — do not re-configure it in `LLMClient.__init__`.
- **No new dependencies required**: all necessary packages (`pydantic`, `structlog`) are already
  in `pyproject.toml`.
- **Ruff**: line length 100, target py313, `E,F,I,N,W` with N818 ignored. Run `uv run ruff check`
  before completion.

### File Structure Requirements

**New files to create:**
- `src/aiops_triage_pipeline/diagnosis/fallback.py` — `build_fallback_report()` function
- `src/aiops_triage_pipeline/integrations/llm.py` — `LLMClient` + `LLMFailureMode`
- `tests/unit/diagnosis/test_fallback.py` — unit tests for fallback builder
- `tests/unit/integrations/test_llm.py` — unit tests for LLM stub and failure injection

**Files to modify:**
- `src/aiops_triage_pipeline/config/settings.py` — add prod mode validator for `INTEGRATION_MODE_LLM`
- `tests/unit/config/test_settings.py` — add prod mode enforcement tests

**Files to read before implementing (do not modify):**
- `src/aiops_triage_pipeline/contracts/diagnosis_report.py` — `DiagnosisReportV1` + `EvidencePack`
  fields (already read during story creation)
- `src/aiops_triage_pipeline/contracts/enums.py` — `DiagnosisConfidence` enum
- `src/aiops_triage_pipeline/contracts/` — find `TriageExcerptV1` module path
- `src/aiops_triage_pipeline/integrations/pagerduty.py` — MOCK mode pattern reference
- `src/aiops_triage_pipeline/integrations/slack.py` — LOG mode pattern reference
- `src/aiops_triage_pipeline/logging/setup.py` — `get_logger` import path
- `tests/unit/config/test_settings.py` — existing test pattern for `Settings(...)` construction
- `tests/unit/integrations/test_pagerduty.py` — integration test structure reference

**Files that are currently empty (1 line) — do NOT fill in for this story:**
- `src/aiops_triage_pipeline/diagnosis/graph.py` — LangGraph graph (Story 6.2)
- `src/aiops_triage_pipeline/diagnosis/prompt.py` — prompt builder (Story 6.3)

**Files NOT to modify:**
- `src/aiops_triage_pipeline/contracts/diagnosis_report.py` — contract is already correct
- Any `pipeline/stages/` files — cold-path code stays out of the hot path

### Previous Story Intelligence

From Story 5.9 (`5-9-end-to-end-hot-path-pipeline-test.md`):
- Regression baseline: **561 non-integration tests pass, 0 skipped, 0 failures** (non-integration
  suite). Story 6.1 adds ~13 new unit tests. Target: 574+ passed, 0 skipped.
- `asyncio_mode=auto` is active globally — `async def` tests run without explicit mark.
- Pattern for Settings construction in tests:
  ```python
  Settings(
      _env_file=None,
      APP_ENV="prod",
      KAFKA_BOOTSTRAP_SERVERS="localhost:9092",
      DATABASE_URL="postgresql+psycopg://u:p@h/db",
      REDIS_URL="redis://localhost:6379/0",
      S3_ENDPOINT_URL="http://localhost:9000",
      S3_ACCESS_KEY="key",
      S3_SECRET_KEY="secret",
      S3_BUCKET="bucket",
      INTEGRATION_MODE_LLM="MOCK",
  )
  ```
- `get_settings.cache_clear()` is needed between tests that construct `Settings()` via the
  singleton — use `monkeypatch` or explicit `cache_clear()` in teardown.
- Code reviews in Epic 5 consistently flagged: meaningful assertions over "no exception raised",
  test isolation, complete field verification. Apply same discipline in new tests.

From recent commit `173274f` (refactor: clarify `confidence_floor`):
- `GateEffect.confidence_floor` has zero runtime effect on `ActionDecisionV1` output — it is a
  reserved gate-engine field, NOT connected to LLM diagnosis confidence.
- `DiagnosisReportV1.confidence` (LOW/MEDIUM/HIGH) is the LLM-domain confidence vector,
  completely separate from the gate engine.
- Do not attempt to wire `DiagnosisReportV1.confidence` into gate decisions — this would violate
  the hot/cold path separation invariant.

From commit `edd65c8` (docs: add cold-path/hot-path handoff contract):
- The handoff contract defines 5 fallback scenarios with exact `reason_codes`:
  `LLM_UNAVAILABLE`, `LLM_TIMEOUT`, `LLM_ERROR`, `LLM_SCHEMA_INVALID`, `LLM_STUB`
- These are already documented in `contracts/diagnosis_report.py` module docstring.
- `diagnosis.json` must include `triage_hash` (hash chain) — but this is Story 6.3's
  responsibility. For Story 6.1, `triage_hash=None` in all fallback reports is correct.

### Git Intelligence Summary

Recent commits (most recent first):
- `173274f` refactor: clarify `confidence_floor` is a no-op (inline comment + contract test)
- `2f7d6f6` chore: reorder epic 6 stories and mark epic 5 retro done
- `d040080` docs: add epic 5 retrospective
- `edd65c8` docs: add cold-path/hot-path handoff contract to architecture
- `c169e24` story 5.9: implement end-to-end hot-path pipeline test

Actionable patterns:
- Story 5.9 code review (Senior Dev AI): every assertion must validate a meaningful property —
  "no exception raised" is insufficient. For 6.1 unit tests: assert specific fields
  (`verdict`, `confidence`, `reason_codes`, `case_id`, `schema_version`) not just type.
- The `diagnosis/` package skeleton was created in a prior scaffolding pass — `__init__.py` exists
  in `tests/unit/diagnosis/` (currently empty). Do not create a new `__init__.py` there.
- `integrations/` tests already exist for `pagerduty`, `slack`, `kafka`, `prometheus`. Pattern:
  test each mode explicitly with a separate test function.

### Latest Tech Information

Verification date: 2026-03-07.

- **Pydantic v2.12.5**: `model_validate()` raises `ValidationError` on schema mismatch. Frozen
  model mutation raises `ValidationError` (not `AttributeError`) in Pydantic v2. Use
  `pytest.raises(ValidationError)` to test immutability, or catch `TypeError` if the model uses
  `__setattr__` guard — verify with a quick test.
- **pytest-asyncio 1.3.0**: `asyncio_mode=auto` in `pyproject.toml` means all `async def` test
  functions are automatically treated as asyncio tests. Do NOT add `@pytest.mark.asyncio`.
- **structlog 25.5.0**: `get_logger(__name__)` returns a `BoundLogger`. Use `.info()`, `.warning()`,
  `.error()` with keyword arguments for structured fields.
- **LangGraph 1.0.9** is already in `pyproject.toml` but Story 6.1 does NOT invoke any LangGraph
  APIs. `diagnosis/graph.py` remains empty. LangGraph usage begins in Story 6.2.

### Project Context Reference

Applied rules from `artifact/project-context.md`:
- **Immutable frozen models**: `DiagnosisReportV1` and `EvidencePack` are `frozen=True`. The
  fallback builder creates them once — no post-construction mutation anywhere.
- **Integration safety**: MOCK/LOG mode must make zero outbound calls. The `LLMClient` in all
  non-LIVE modes has no `urllib`, `httpx`, or `requests` imports.
- **Consistency over novelty**: reuse `get_logger(__name__)` from `logging/setup.py`. Do not
  introduce a new logging adapter. Reuse `IntegrationMode` from `config/settings.py` directly
  rather than creating a parallel `LLMIntegrationMode` enum.
- **No placeholder-only coverage**: every test assertion must verify a meaningful field, not just
  call `invoke()` and assert "no exception".
- **Validate at boundaries**: `build_fallback_report` constructs the model at the boundary —
  Pydantic validates on construction. No re-validation needed in the caller.
- **Test discipline**: `asyncio_mode=auto` is active; no explicit marker needed. One test per
  scenario (one failure mode per test function). No shared mutable state between tests.

### Project Structure Notes

- `src/aiops_triage_pipeline/diagnosis/fallback.py` — currently 1 empty line; implement here
- `src/aiops_triage_pipeline/integrations/llm.py` — currently 1 empty line; implement here
- `tests/unit/diagnosis/` — directory exists, `__init__.py` present (empty). Create
  `test_fallback.py` here directly — no `__init__.py` needed for the test file itself.
- `tests/unit/integrations/` — directory exists with existing test files. Create `test_llm.py`
  here following the same module-level import/class structure as `test_pagerduty.py`.
- No new packages or directories needed. All paths are already scaffolded.

### References

- [Source: `artifact/planning-artifacts/epics.md#Story 6.1` (lines 998–1018)]
- [Source: `artifact/planning-artifacts/epics.md#Epic 6: LLM-Enriched Diagnosis` (lines 994–996)]
- [Source: `docs/architecture.md#Cold-Path / Hot-Path Handoff Contract` — non-blocking guarantee,
  invocation criteria, handoff artifact schema, fallback posture, boundary rules]
- [Source: `artifact/planning-artifacts/architecture.md` (decision 4B: cold-path orchestration,
  fire-and-forget; NFR-P4: 60s LLM timeout; NFR-S8: exposure denylist + bank-sanctioned endpoints;
  import rules table: `integrations/` and `diagnosis/` boundaries)]
- [Source: `artifact/project-context.md` (integration safety, frozen models, asyncio rules)]
- [Source: `src/aiops_triage_pipeline/contracts/diagnosis_report.py` — `DiagnosisReportV1`,
  `EvidencePack` fields and docstring (valid reason_codes)]
- [Source: `src/aiops_triage_pipeline/contracts/enums.py` — `DiagnosisConfidence` LOW/MEDIUM/HIGH]
- [Source: `src/aiops_triage_pipeline/config/settings.py` — `IntegrationMode`, `AppEnv`,
  `Settings` model_validator pattern, `INTEGRATION_MODE_LLM` default=LOG]
- [Source: `src/aiops_triage_pipeline/integrations/pagerduty.py` — MOCK mode pattern reference]
- [Source: `tests/unit/config/test_settings.py` — `Settings(_env_file=None, ...)` construction pattern]
- [Source: `artifact/implementation-artifacts/5-9-end-to-end-hot-path-pipeline-test.md` —
  regression baseline 561 non-integration tests, asyncio_mode=auto, test discipline standards]
- [Source: git commit `173274f` — `confidence_floor` is reserved no-op, not LLM confidence]
- [Source: git commit `edd65c8` — cold-path/hot-path handoff contract added to `docs/architecture.md`]

## Dev Agent Record

### Agent Model Used

claude-sonnet-4-6

### Debug Log References

- Workflow engine: `_bmad/core/tasks/workflow.xml`
- Workflow config: `_bmad/bmm/workflows/4-implementation/create-story/workflow.yaml`
- Story selection source: `artifact/implementation-artifacts/sprint-status.yaml`
- Core artifacts analyzed:
  - `artifact/planning-artifacts/epics.md` (Epic 6, Story 6.1 at line 998)
  - `artifact/planning-artifacts/architecture.md` (decisions 4B, 3B, import rules, NFR-P4, NFR-S8)
  - `docs/architecture.md` (cold-path/hot-path handoff contract, fallback posture, boundary rules)
  - `artifact/project-context.md`
  - `src/aiops_triage_pipeline/contracts/diagnosis_report.py` (DiagnosisReportV1, EvidencePack)
  - `src/aiops_triage_pipeline/contracts/enums.py` (DiagnosisConfidence)
  - `src/aiops_triage_pipeline/config/settings.py` (IntegrationMode, AppEnv, Settings)
  - `src/aiops_triage_pipeline/integrations/pagerduty.py` (MOCK mode pattern)
  - `src/aiops_triage_pipeline/integrations/base.py` (empty — placeholder)
  - `src/aiops_triage_pipeline/diagnosis/fallback.py` (empty — to implement)
  - `src/aiops_triage_pipeline/diagnosis/graph.py` (empty — do not fill in this story)
  - `src/aiops_triage_pipeline/integrations/llm.py` (empty — to implement)
  - `tests/unit/config/test_settings.py` (Settings construction pattern)
  - `artifact/implementation-artifacts/5-9-end-to-end-hot-path-pipeline-test.md`

### Completion Notes List

- Implemented `build_fallback_report()` in `diagnosis/fallback.py` — returns a frozen `DiagnosisReportV1`
  with `verdict="UNKNOWN"`, `confidence=LOW`, empty `EvidencePack`, and caller-supplied `reason_codes`.
- Implemented `LLMClient` in `integrations/llm.py` with `LLMFailureMode` enum covering all 5 failure
  scenarios. MOCK and LOG modes return deterministic stub reports with no network I/O. OFF raises
  `ValueError`, LIVE raises `NotImplementedError` (placeholder for Story 6.2).
- Added `validate_llm_prod_mode` as a separate named `model_validator(mode="after")` in
  `config/settings.py`. Rejects `MOCK` and `OFF` in `APP_ENV=prod`; allows `LOG` and `LIVE`.
- `TriageExcerptV1` import confirmed at `aiops_triage_pipeline.contracts.triage_excerpt`.

**Code review fixes (claude-sonnet-4-6):**
- [H1] Fixed architecture boundary violation: `integrations/llm.py` was importing from
  `diagnosis/fallback.py` in violation of the import rules table. Inlined the `DiagnosisReportV1`
  construction directly in `LLMClient.invoke()` using only `contracts/` types (allowed boundary).
- [M1] Added `docs/local-development.md` and `tests/unit/integrations/test_llm.py` to File List
  (both modified as part of this story but omitted from Dev Agent Record).
- [M2] Added `test_llm_module_imports_no_http_library` to verify AC2 (no network I/O in stub mode).
- [M3] Fixed misleading error message in `validate_llm_prod_mode`: changed "must be LIVE" to
  "must be LIVE or LOG" to correctly document both allowed prod modes.
- [L1] Split loop-based `test_case_id_propagated_in_failure_injection_mode` into 4 separate test
  functions (one per failure mode) per project "one test per scenario" rule.
- [L2] Added `schema_version == "v1"` assertion to `test_mock_none_returns_stub_report`.
- 5 new tests added during review (1 network I/O + 4 split case_id tests replacing the loop test).
  Net: +5 tests. Total: 590 passed, 0 skipped, 0 failures.

### File List

**New files:**
- `src/aiops_triage_pipeline/diagnosis/fallback.py`
- `src/aiops_triage_pipeline/integrations/llm.py`
- `tests/unit/diagnosis/test_fallback.py`
- `tests/unit/integrations/test_llm.py`

**Modified files:**
- `src/aiops_triage_pipeline/config/settings.py`
- `tests/unit/config/test_settings.py`
- `tests/unit/integrations/test_llm.py`
- `artifact/implementation-artifacts/sprint-status.yaml`
- `docs/local-development.md`

## Change Log

- 2026-03-07: Story 6.1 implemented — LLM stub and failure-injection mode. Created
  `diagnosis/fallback.py`, `integrations/llm.py`; added prod-mode validator to
  `config/settings.py`; added 24 unit tests. 585 tests passed, 0 skipped.
