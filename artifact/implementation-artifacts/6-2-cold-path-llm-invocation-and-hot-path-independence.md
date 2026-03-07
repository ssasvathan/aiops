# Story 6.2: Cold-Path LLM Invocation & Hot-Path Independence

Status: review

## Story

As a platform operator,
I want LLM diagnosis invoked on the cold path as a non-blocking, fire-and-forget async task,
so that the hot-path triage pipeline (CaseFile write, outbox publish, Rulebook gating, action
execution) completes without waiting on LLM and cases are conditionally enriched based on
criteria (FR36, FR42, FR66).

## Acceptance Criteria

1. **Given** a case has completed hot-path processing (triage.json written, header published,
   action executed)
   **When** the case qualifies for LLM diagnosis (environment=PROD, tier=TIER_0,
   state=sustained per FR42)
   **Then** a fire-and-forget async LangGraph task is spawned consuming TriageExcerpt +
   structured evidence summary
2. **And** the hot path never waits on LLM completion — hot-path latency is unaffected by LLM
   invocation
3. **And** LLM input is bounded: TriageExcerptV1 + structured evidence summary string only,
   not raw logs or the full CaseFile
4. **And** LLM input is exposure-capped: `apply_denylist()` applied to `TriageExcerptV1` dict
   before sending to LLM (NFR-S8)
5. **And** the fire-and-forget task is registered with `HealthRegistry` (`"llm"` component) and
   an in-flight OTLP UpDownCounter gauge metric is incremented on task start / decremented on
   task complete or error
6. **And** LLM invocation timeout is <= 60 seconds (NFR-P4) — enforced via
   `asyncio.wait_for(timeout=60.0)` at the LangGraph graph invocation level
7. **And** cases not meeting invocation criteria skip LLM diagnosis entirely — no task spawned,
   no HealthRegistry update, no metric increment
8. **And** unit tests verify: hot-path completes independently, all four invocation criteria
   combinations, fire-and-forget task creation, HealthRegistry in-flight tracking, exposure-capped
   inputs, timeout enforcement

## Tasks / Subtasks

- [x] Task 1: Add LLM in-flight OTLP gauge to `health/metrics.py` (AC: 5)
  - [x] Add `_llm_cold_path_inflight` UpDownCounter:
    `name="aiops.llm.cold_path.inflight"`, `description="In-flight cold-path LLM invocations"`
  - [x] Add `llm_inflight_add(delta: int) -> None` function — calls `_llm_cold_path_inflight.add(delta, attributes={"component": "llm"})`
  - [x] No component-level delta tracking needed (unlike `record_status`): UpDownCounter's running sum
    is the gauge; `+1` on start and `-1` in finally always balance correctly

- [x] Task 2: Implement `diagnosis/graph.py` — LangGraph graph + fire-and-forget (AC: 1, 2, 3, 4, 5, 6, 7)
  - [x] `ColdPathDiagnosisState` TypedDict:
    `case_id: str`, `triage_excerpt: TriageExcerptV1`, `evidence_summary: str`,
    `diagnosis_report: DiagnosisReportV1 | None`
  - [x] `async def _invoke_llm_node(state: ColdPathDiagnosisState) -> dict` — calls
    `await llm_client.invoke(state["case_id"], state["triage_excerpt"], state["evidence_summary"])`
    and returns `{"diagnosis_report": report}`. The `llm_client` is injected via `functools.partial`
    at graph build time — keeps the node function type-safe and testable.
  - [x] `def build_diagnosis_graph(llm_client: LLMClient) -> CompiledGraph`:
    builds and compiles a LangGraph `StateGraph(ColdPathDiagnosisState)` with a single node
    `"invoke_llm"` bound to `partial(_invoke_llm_node, llm_client=llm_client)`,
    wired `START → invoke_llm → END`. Returns compiled graph.
    **Do NOT compile a module-level singleton** — compile per invocation (allows different
    client modes in tests without module-level state).
  - [x] `def meets_invocation_criteria(triage_excerpt: TriageExcerptV1, app_env: AppEnv) -> bool`:
    returns `True` only when ALL three hold:
    1. `app_env == AppEnv.prod`
    2. `triage_excerpt.criticality_tier == CriticalityTier.TIER_0`
    3. `triage_excerpt.sustained is True`
    All other combinations → `False`. No logging inside this pure predicate.
  - [x] `async def run_cold_path_diagnosis(*, case_id, triage_excerpt, evidence_summary, llm_client, denylist, health_registry, timeout_seconds=60.0) -> DiagnosisReportV1`:
    1. Apply denylist: `safe_excerpt_dict = apply_denylist(triage_excerpt.model_dump(mode="json"), denylist)`;
       reconstruct: `safe_excerpt = TriageExcerptV1.model_validate(safe_excerpt_dict)`.
       `evidence_summary` is a plain string — pass it unchanged (denylist applies to
       field-keyed dicts; string evidence is already bounded to public evidence metrics only).
    2. `await health_registry.update("llm", HealthStatus.HEALTHY, reason="cold_path_invocation_started")`
    3. `llm_inflight_add(+1)` (from `health.metrics`)
    4. Build graph: `graph = build_diagnosis_graph(llm_client)`
    5. Invoke with timeout: implemented per spec
    6. Structured log on entry, success, exception
  - [x] `def spawn_cold_path_diagnosis_task(*, case_id, triage_excerpt, evidence_summary, llm_client, denylist, health_registry, app_env, timeout_seconds=60.0) -> asyncio.Task | None`:
    1. `if not meets_invocation_criteria(triage_excerpt, app_env): return None`
    2. `logger.info("cold_path_diagnosis_task_spawned", case_id=..., env=..., tier=...)`
    3. `return asyncio.create_task(run_cold_path_diagnosis(...))` — NO await
    4. Return type: `asyncio.Task[DiagnosisReportV1]` (narrowed in type hint)

- [x] Task 3: Implement LIVE mode in `integrations/llm.py` + add settings (AC: 6)
  - [x] Add to `config/settings.py` (after `INTEGRATION_MODE_LLM`):
    `LLM_BASE_URL: str | None = None` and `LLM_API_KEY: str | None = None`
  - [x] Add to `settings.log_active_config()`:
    `LLM_BASE_URL` and `LLM_API_KEY` (masked)
  - [x] Update `LLMClient.__init__` to accept `base_url` and `api_key`.
  - [x] Add `httpx>=0.27` to `pyproject.toml` and run `uv lock`.
  - [x] Implement LIVE mode in `LLMClient.invoke()` with lazy `import httpx`.
  - [x] Update `_FAILURE_REASON_CODES` (LIVE mode does not use the failure-reason-code map).
  - [x] Update docstring: remove "until Story 6.2" reference.

- [x] Task 4: Unit tests for `diagnosis/graph.py` (AC: 8)
  - [x] `tests/unit/diagnosis/test_graph.py`
  - [x] Test `meets_invocation_criteria` — prod + TIER_0 + sustained → True
  - [x] Test `meets_invocation_criteria` — not prod (local) → False
  - [x] Test `meets_invocation_criteria` — prod + not TIER_0 (TIER_1) → False
  - [x] Test `meets_invocation_criteria` — prod + TIER_0 + NOT sustained → False
  - [x] Test `spawn_cold_path_diagnosis_task` — ineligible (local env) → returns None
  - [x] Test `spawn_cold_path_diagnosis_task` — eligible → returns `asyncio.Task`
  - [x] Test fire-and-forget independence: task not done immediately, completes after await
  - [x] Test HealthRegistry tracking: `"llm"` → HEALTHY on success
  - [x] Test denylist applied via `unittest.mock.patch` on `apply_denylist`
  - [x] Test timeout enforcement: patch `asyncio.wait_for` to verify `timeout=60.0`; real timeout test
  - [x] All test functions are `async def` (asyncio_mode=auto)
  - [x] Fresh `HealthRegistry()` per test, `_make_eligible_excerpt()` helper

- [x] Task 5: Update `tests/unit/integrations/test_llm.py` — LIVE mode tests (AC: 6, 8)
  - [x] Test: `LLMClient(mode=LIVE)` with `base_url=None` → raises `ValueError` containing "LLM_BASE_URL"
  - [x] Test: `LLMClient(mode=LIVE)` with `base_url="http://..."` → httpx POST made to `base_url/diagnose`
  - [x] Replaced `test_live_mode_raises_not_implemented` with new LIVE mode tests
  - [x] Updated `test_llm_module_imports_no_http_library` to allow httpx lazy import

- [x] Task 6: Quality gates
  - [x] `uv run ruff check` — 0 new errors (2 pre-existing E501 in unrelated files)
  - [x] `uv run pytest -q -m "not integration"` — 607 passed, 0 skipped, 0 failures

## Dev Notes

### Developer Context Section

- Story key: `6-2-cold-path-llm-invocation-and-hot-path-independence`
- Story ID: 6.2
- Epic 6 context: Second story in Epic 6 (LLM-Enriched Diagnosis). This story wires the
  fire-and-forget infrastructure and invocation criteria that Story 6.1's LLMClient stub
  depends on. Stories 6.3 and 6.4 build on top of the `diagnosis/graph.py` foundation by
  adding structured prompt engineering and deterministic fallback respectively.
- **Scope boundary**: This story implements `diagnosis/graph.py` (LangGraph graph + fire-and-forget
  launcher), extends `health/metrics.py` (in-flight gauge), adds `LLM_BASE_URL`/`LLM_API_KEY`
  settings, implements LIVE mode in `LLMClient` (minimal HTTP scaffold), and adds `httpx` as
  a dependency. It does NOT implement prompt engineering (`diagnosis/prompt.py` stays empty),
  structured response parsing (Story 6.3), schema validation or fallback for LIVE failures
  (Story 6.4), or writing `diagnosis.json` to object storage (Story 6.3).
- **LIVE mode stub**: The LIVE mode implemented here is intentionally minimal — it makes an
  HTTP POST to `LLM_BASE_URL/diagnose` and returns a stub DiagnosisReportV1 with
  `reason_codes=("LLM_LIVE_STUB",)`. Story 6.3 replaces this with proper prompt construction
  and structured output parsing. Do not invest engineering effort in the LIVE response parsing
  in this story.
- **Hot-path independence**: The `spawn_cold_path_diagnosis_task()` function uses
  `asyncio.create_task()` — no await. The calling hot-path code continues immediately.
  The asyncio event loop will schedule the task in the background.

### Technical Requirements

**`diagnosis/graph.py`** — imports and structure:
```python
import asyncio
from functools import partial
from typing import TypedDict

from langgraph.graph import StateGraph, START, END

from aiops_triage_pipeline.config.settings import AppEnv
from aiops_triage_pipeline.contracts.diagnosis_report import DiagnosisReportV1
from aiops_triage_pipeline.contracts.enums import CriticalityTier, HealthStatus
from aiops_triage_pipeline.contracts.triage_excerpt import TriageExcerptV1
from aiops_triage_pipeline.denylist.enforcement import apply_denylist
from aiops_triage_pipeline.denylist.loader import DenylistV1
from aiops_triage_pipeline.health.metrics import llm_inflight_add
from aiops_triage_pipeline.health.registry import HealthRegistry
from aiops_triage_pipeline.integrations.llm import LLMClient
from aiops_triage_pipeline.logging.setup import get_logger
from aiops_triage_pipeline.models.health import HealthStatus
```

**`ColdPathDiagnosisState` TypedDict** — uses Python 3.13 built-in style, NOT `typing.TypedDict`
from `typing_extensions`:
```python
from typing import TypedDict

class ColdPathDiagnosisState(TypedDict):
    case_id: str
    triage_excerpt: TriageExcerptV1
    evidence_summary: str
    diagnosis_report: DiagnosisReportV1 | None
```

**LangGraph graph construction** — LangGraph 1.0.9 pattern:
```python
def build_diagnosis_graph(llm_client: LLMClient):
    async def invoke_llm_node(state: ColdPathDiagnosisState) -> dict:
        report = await llm_client.invoke(
            case_id=state["case_id"],
            triage_excerpt=state["triage_excerpt"],
            evidence_summary=state["evidence_summary"],
        )
        return {"diagnosis_report": report}

    graph = StateGraph(ColdPathDiagnosisState)
    graph.add_node("invoke_llm", invoke_llm_node)
    graph.add_edge(START, "invoke_llm")
    graph.add_edge("invoke_llm", END)
    return graph.compile()
```

**Note on LangGraph import**: LangGraph 1.0.9 exports `StateGraph`, `START`, `END` from
`langgraph.graph`. The compiled graph type is `langchain_core.runnables.base.Runnable` /
`langgraph.graph.graph.CompiledGraph` — for return type annotation use `Any` or omit if
complex to type, to avoid coupling to internal LangGraph types.

**`run_cold_path_diagnosis` return type annotation**: `-> DiagnosisReportV1` — the graph's
`ainvoke` returns `dict`; extract `result["diagnosis_report"]` which is set by the node.
`None` should never occur if the node ran correctly; assert or raise if it does.

**In-flight gauge in `health/metrics.py`** — add below the existing `_component_health_gauge`:
```python
_llm_cold_path_inflight = _meter.create_up_down_counter(
    name="aiops.llm.cold_path.inflight",
    description="Number of in-flight cold-path LLM diagnosis invocations",
    unit="1",
)

def llm_inflight_add(delta: int) -> None:
    """Increment (+1) or decrement (-1) the LLM cold-path in-flight gauge.

    Called by diagnosis/graph.py on task start (+1) and in finally block (-1).
    Uses a simple UpDownCounter — no delta-tracking needed because start/stop
    calls always balance and we never read back the counter value here.
    """
    _llm_cold_path_inflight.add(delta, attributes={"component": "llm"})
```

**`spawn_cold_path_diagnosis_task` — asyncio.Task type hint**:
```python
def spawn_cold_path_diagnosis_task(
    *,
    case_id: str,
    triage_excerpt: TriageExcerptV1,
    evidence_summary: str,
    llm_client: LLMClient,
    denylist: DenylistV1,
    health_registry: HealthRegistry,
    app_env: AppEnv,
    timeout_seconds: float = 60.0,
) -> "asyncio.Task[DiagnosisReportV1] | None":
    if not meets_invocation_criteria(triage_excerpt, app_env):
        return None
    _logger.info(
        "cold_path_diagnosis_task_spawned",
        case_id=case_id,
        env=triage_excerpt.env.value,
        tier=triage_excerpt.criticality_tier.value,
        timeout_seconds=timeout_seconds,
    )
    return asyncio.create_task(
        run_cold_path_diagnosis(
            case_id=case_id,
            triage_excerpt=triage_excerpt,
            evidence_summary=evidence_summary,
            llm_client=llm_client,
            denylist=denylist,
            health_registry=health_registry,
            timeout_seconds=timeout_seconds,
        )
    )
```

**LLMClient LIVE mode — httpx import placement**: keep `import httpx` inside the LIVE branch
to avoid breaking import-time for envs without httpx. Once httpx is in `pyproject.toml` this
is just a style choice (import will succeed), but keeping it local follows the lazy-import
pattern already used in this codebase (`config/settings.py` uses `import yaml` lazily).

**`config/settings.py` — new fields placement**: add after `INTEGRATION_MODE_LLM`:
```python
LLM_BASE_URL: str | None = None   # Bank-sanctioned LLM endpoint base URL (LIVE mode)
LLM_API_KEY: str | None = None    # Bearer auth token for LLM endpoint (optional in LIVE mode)
```

### Architecture Compliance

- **Hot/cold path separation**: `diagnosis/graph.py` must NOT be imported from
  `pipeline/stages/`. The `spawn_cold_path_diagnosis_task()` function would be called from
  the hot-path runner (`__main__.py` or future `pipeline/runner.py`) after all 7 hot-path
  stages complete — not from within the stages themselves.
  [Source: `artifact/planning-artifacts/architecture.md` import rules table: `pipeline/stages/` cannot import `diagnosis/`]
- **`diagnosis/` import boundary**: `diagnosis/` may import from `contracts/`, `models/`,
  `config/`, `health/`, `errors/`, `logging/`, `denylist/`, AND `integrations/` (no restriction
  in architecture table). `diagnosis/graph.py` importing `integrations/llm.py` is allowed.
  [Source: `artifact/planning-artifacts/architecture.md` import rules table, line 659]
- **`integrations/` import boundary**: `integrations/llm.py` may NOT import from `diagnosis/`.
  This is preserved — `llm.py` does not import `graph.py`. The LangGraph graph lives in
  `diagnosis/` and calls `LLMClient` from `integrations/`, not the reverse.
- **Non-blocking guarantee**: `asyncio.create_task()` returns immediately without awaiting.
  The event loop schedules the task for later execution. The caller (hot-path) receives a
  `Task` object and continues without blocking. [Source: `docs/architecture.md` § Non-Blocking Guarantee]
- **Invocation criteria**: ALL THREE must hold — `PROD` + `TIER_0` + `sustained=True`. This is
  an AND predicate, not OR. Cases that fail ANY criterion skip entirely.
  [Source: `docs/architecture.md` § Invocation Criteria table; `artifact/planning-artifacts/epics.md` Story 6.2 AC]
- **Denylist boundary**: `apply_denylist()` is the ONLY enforcement function. Applied to
  `triage_excerpt.model_dump(mode="json")` before passing to `LLMClient.invoke()`.
  `evidence_summary` is a structured evidence string constructed from public Prometheus
  metrics — it does not pass through `apply_denylist()` (strings, not field-keyed dicts).
  If evidence_summary ever contains free-text from external sources, revisit this in Story 6.3.
  [Source: `artifact/project-context.md` § Denylist framework; `docs/architecture.md` § LLM Input Bounds]
- **HealthRegistry component name**: `"llm"` — consistent with the degraded-mode table in
  architecture (`LLM → deterministic fallback`). Not `"llm_cold_path"` or `"cold_path"`.
- **`asyncio.wait_for` placement**: timeout is applied at the `graph.ainvoke()` call in
  `run_cold_path_diagnosis()`, NOT inside the LangGraph node. This ensures the 60s budget
  covers the entire graph execution including node overhead, not just the HTTP call.
  [Source: `docs/architecture.md` § LLM Input Bounds, NFR-P4]
- **No writing `diagnosis.json`** in this story. `run_cold_path_diagnosis()` returns a
  `DiagnosisReportV1` in memory. Persisting it to object storage is Story 6.3.

### Library / Framework Requirements

Verification date: 2026-03-07.

- **LangGraph 1.0.9**: `StateGraph`, `START`, `END` from `langgraph.graph`. The compiled graph
  exposes `ainvoke(state: dict)` which is a coroutine. `StateGraph.add_node(name, fn)` where
  `fn` is an `async def` accepting `state: TypedDict` and returning `dict` with partial-state
  updates. `add_edge(START, node_name)` and `add_edge(node_name, END)` with string node names.
  `compile()` returns a `CompiledStateGraph` (avoid importing this type directly; use `Any`
  for the return type annotation of `build_diagnosis_graph` if needed).
- **Python 3.13 typing**: `asyncio.Task[DiagnosisReportV1]` (built-in generic, no need for
  `typing.Task`). `TypedDict` from `typing` (not `typing_extensions`). `X | None` (union syntax).
- **pytest-asyncio `asyncio_mode=auto`**: all `async def` test functions run automatically.
  For `asyncio.create_task()` tests — the task runs on the event loop managed by pytest-asyncio.
  To actually run the task to completion in a test: `await asyncio.sleep(0)` yields control
  to the event loop, then `await task` retrieves the result.
- **httpx 0.27+**: `httpx.AsyncClient` is the async client class. Use as an async context
  manager: `async with httpx.AsyncClient(timeout=60.0) as client:`. `client.post(url, json=body, headers=headers)` returns an `httpx.Response`. `response.raise_for_status()` raises
  `httpx.HTTPStatusError` for 4xx/5xx. For unit tests, use `unittest.mock.patch` or
  `httpx.MockTransport` to avoid real network calls.
- **HealthRegistry**: instantiate fresh in tests — `registry = HealthRegistry()` (no singleton).
  `await registry.update("llm", HealthStatus.HEALTHY)` is async. `registry.get("llm")` is sync.
  [Source: `src/aiops_triage_pipeline/health/registry.py`]
- **structlog**: `get_logger("diagnosis.graph")` is the logger name for `diagnosis/graph.py`.
  Consistent with pattern: `get_logger("pipeline.scheduler")` for scheduler, etc.
- **Ruff**: line length 100, target py313. The `asyncio.Task` generic annotation may require
  a `from __future__ import annotations` import if Ruff complains about forward references —
  add it if needed.

### File Structure Requirements

**New files to create:**
- `src/aiops_triage_pipeline/diagnosis/graph.py` — LangGraph graph + fire-and-forget (currently 1 empty line)
- `tests/unit/diagnosis/test_graph.py` — unit tests for the graph and invoker

**Files to modify:**
- `src/aiops_triage_pipeline/health/metrics.py` — add `llm_inflight_add()` + in-flight counter
- `src/aiops_triage_pipeline/integrations/llm.py` — implement LIVE mode + update docstring
- `src/aiops_triage_pipeline/config/settings.py` — add `LLM_BASE_URL`, `LLM_API_KEY`
- `pyproject.toml` — add `"httpx>=0.27"` to `[project.dependencies]`, run `uv lock`
- `tests/unit/integrations/test_llm.py` — add LIVE mode tests

**Files to read before implementing (do not modify):**
- `src/aiops_triage_pipeline/diagnosis/fallback.py` — fallback pattern reference
- `src/aiops_triage_pipeline/diagnosis/__init__.py` — package boundary (currently empty)
- `src/aiops_triage_pipeline/health/registry.py` — `HealthRegistry.update()` signature
- `src/aiops_triage_pipeline/health/metrics.py` — existing `_meter` and counter pattern
- `src/aiops_triage_pipeline/denylist/enforcement.py` — `apply_denylist()` signature
- `src/aiops_triage_pipeline/contracts/triage_excerpt.py` — `TriageExcerptV1` fields
- `src/aiops_triage_pipeline/contracts/enums.py` — `Environment`, `CriticalityTier`, `HealthStatus`
- `src/aiops_triage_pipeline/config/settings.py` — `AppEnv`, `IntegrationMode`, `Settings`
- `src/aiops_triage_pipeline/integrations/llm.py` — `LLMClient` existing structure
- `tests/unit/diagnosis/test_fallback.py` — existing diagnosis test file pattern
- `tests/unit/integrations/test_llm.py` — existing LLM test pattern for `_make_excerpt()`

**Files currently empty (1 line) — do NOT fill in for this story:**
- `src/aiops_triage_pipeline/diagnosis/prompt.py` — prompt builder (Story 6.3)

**Files NOT to modify:**
- `src/aiops_triage_pipeline/pipeline/stages/` — any file; hot-path stages are off-limits
- `src/aiops_triage_pipeline/contracts/diagnosis_report.py` — contract is already correct
- `src/aiops_triage_pipeline/diagnosis/fallback.py` — fallback builder is already correct

### Previous Story Intelligence

From Story 6.1 (`6-1-llm-stub-and-failure-injection-mode.md`):
- **Baseline test count**: 590 passed (after code review), 0 skipped, 0 failures (non-integration).
  Story 6.2 adds ~12-15 new unit tests. Target: 602+ passed, 0 skipped.
- **`LLMClient.invoke()` signature**: `async def invoke(self, case_id: str, triage_excerpt: TriageExcerptV1, evidence_summary: str) -> DiagnosisReportV1`.
  Parameters are positional-or-keyword. When calling from LangGraph node: use keyword args
  for clarity.
- **Architecture boundary fix from code review**: `integrations/llm.py` may NOT import from
  `diagnosis/fallback.py`. The LIVE mode implementation must construct `DiagnosisReportV1`
  directly using `contracts/diagnosis_report.py` types — same pattern as the existing MOCK/LOG
  mode (which already inline-constructs the report). [Source: Story 6.1 code review H1 fix]
- **`TriageExcerptV1` import path**: `from aiops_triage_pipeline.contracts.triage_excerpt import TriageExcerptV1` — confirmed in Story 6.1.
- **`asyncio_mode=auto`**: no `@pytest.mark.asyncio` needed. Test functions: `async def test_*() -> None`.
- **Settings test pattern**: `Settings(_env_file=None, APP_ENV="prod", KAFKA_BOOTSTRAP_SERVERS="localhost:9092", DATABASE_URL="postgresql+psycopg://u:p@h/db", REDIS_URL="redis://localhost:6379/0", S3_ENDPOINT_URL="http://localhost:9000", S3_ACCESS_KEY="key", S3_SECRET_KEY="secret", S3_BUCKET="bucket", INTEGRATION_MODE_LLM="LIVE", LLM_BASE_URL="http://llm-endpoint.bank.internal")` — remember to include new LLM fields when constructing `Settings` with LIVE mode in tests.
- **`get_settings.cache_clear()`**: call before any test that constructs `Settings()` via singleton path.
- **Code review discipline**: every assertion must verify a meaningful field, not just "no exception raised". For task-creation tests: assert `isinstance(task, asyncio.Task)` AND await it to verify it completes successfully.

From recent commit `913466e` (story 6.1: implement LLM stub and failure-injection mode):
- `LLMClient` is in `integrations/llm.py` with full MOCK/LOG/OFF mode implementations.
- `diagnosis/fallback.py` has `build_fallback_report()`.
- Regression baseline: `uv run pytest -q -m "not integration"` → check current count before
  starting — the file says 590 but re-run to confirm current state.

### Git Intelligence Summary

Recent commits (most recent first):
- `913466e` story 6.1: implement LLM stub and failure-injection mode
- `173274f` refactor: clarify `confidence_floor` is a no-op
- `2f7d6f6` chore: reorder epic 6 stories
- `d040080` docs: add epic 5 retrospective
- `edd65c8` docs: add cold-path/hot-path handoff contract to architecture

Actionable patterns:
- Story 6.1 used `asyncio_mode=auto` with separate test functions per scenario. Story 6.2
  should follow the same discipline: one test function per invocation criteria combination
  (not a parametrized loop). Four `test_meets_invocation_criteria_*` functions.
- The `_make_excerpt()` helper in `test_llm.py` uses `env=Environment.LOCAL` and
  `criticality_tier=CriticalityTier.TIER_1`. For `test_graph.py`, create a similar
  `_make_eligible_excerpt()` helper with `env=Environment.PROD` and
  `criticality_tier=CriticalityTier.TIER_0` and `sustained=True`.
- Health registry tests already exist in `tests/unit/health/test_registry.py`. Study the
  pattern there for testing `HealthRegistry.update()` behavior with a fresh instance.

### Latest Tech Information

Verification date: 2026-03-07.

- **LangGraph 1.0.9**: The `StateGraph` API in this version uses:
  - `StateGraph(StateType)` where `StateType` is a `TypedDict` subclass
  - `.add_node(name: str, action: Callable)` where action is sync or async
  - `.add_edge(from_node, to_node)` where `START` and `END` are special sentinels
  - `.compile()` returns a compiled graph with `.ainvoke(input: dict, config: RunnableConfig | None = None)`
  - The `.ainvoke(input)` method returns a coroutine — must be awaited
  - Node functions receive `state: StateType` as their argument and return `dict` with
    the state keys to update (partial state updates)
  - `langchain_core` is a transitive dependency of `langgraph` — no separate install needed
- **httpx 0.27**: `httpx.AsyncClient` supports `async with` context manager. `client.post()`
  returns `httpx.Response`. `raise_for_status()` is a synchronous method on the response.
  `httpx.HTTPStatusError` is raised for non-2xx. `httpx.TimeoutException` for timeouts.
  Note: `asyncio.wait_for` (applied at graph.ainvoke level) is separate from httpx's own
  timeout — both should be set; httpx timeout is a safety net, asyncio.wait_for is the
  authoritative 60s budget.
- **asyncio.create_task()**: must be called from within a running event loop. In tests,
  pytest-asyncio provides the event loop. In production, this is called from within the
  async hot-path runner. `asyncio.create_task()` accepts a coroutine and returns an
  `asyncio.Task`. Tasks are scheduled to run on the next event loop iteration.
- **pydantic v2.12.5 `model_dump(mode="json")`**: for `TriageExcerptV1`, this converts
  enum fields to their `.value` strings (e.g., `Environment.PROD → "prod"`), `datetime`
  to ISO string, tuples to lists. The resulting dict is safe to pass to `apply_denylist()`.
  After sanitization, `TriageExcerptV1.model_validate(sanitized_dict)` reconstructs the model.
  If a required field is removed by the denylist, `ValidationError` is raised — the denylist
  must not remove required TriageExcerptV1 fields. In practice, the bank's denylist targets
  field VALUES (denied_value_patterns) or sensitive field names — not the structural contract
  fields of TriageExcerptV1.

### Project Context Reference

Applied rules from `artifact/project-context.md`:
- **Consistency over novelty**: reuse `get_logger(__name__)` or `get_logger("diagnosis.graph")`.
  Reuse `HealthRegistry` from `health/registry.py`. Reuse `apply_denylist()` from
  `denylist/enforcement.py`. No new parallel patterns.
- **Integration safety**: `spawn_cold_path_diagnosis_task()` only spawns in eligible cases.
  Non-PROD environments NEVER trigger LLM calls — the `meets_invocation_criteria` check is
  the guard.
- **No placeholder-only coverage**: every unit test must assert meaningful behavior.
  For `spawn_cold_path_diagnosis_task` returning a Task: assert `isinstance(task, asyncio.Task)`
  AND `await task` to get the `DiagnosisReportV1` AND assert `report.schema_version == "v1"`.
- **Test discipline**: use `async def`, one scenario per test function, fresh `HealthRegistry()`
  per test that touches it (never `get_health_registry()`).
- **Immutable frozen models**: `TriageExcerptV1` is `frozen=True`. Reconstruct via
  `TriageExcerptV1.model_validate(sanitized_dict)` — do NOT try `model_copy(update={...})` for
  denylist sanitization.

### Project Structure Notes

- `src/aiops_triage_pipeline/diagnosis/graph.py` — currently 1 empty line; implement here
- `tests/unit/diagnosis/__init__.py` — already exists (empty)
- `tests/unit/diagnosis/test_fallback.py` — already exists with 7 tests; create `test_graph.py` here
- `tests/unit/integrations/test_llm.py` — already exists; add 2 new LIVE mode tests at the end
- No new package directories needed

### References

- [Source: `artifact/planning-artifacts/epics.md#Story 6.2` (lines 1019–1037)]
- [Source: `docs/architecture.md#Cold-Path / Hot-Path Handoff Contract` — non-blocking guarantee,
  invocation criteria table, LLM input bounds, in-flight gauge, fallback posture, boundary rules]
- [Source: `artifact/planning-artifacts/architecture.md` decision 4B (fire-and-forget LangGraph,
  HealthRegistry, in-flight gauge); NFR-P4 (60s LLM timeout); NFR-S8 (denylist + bank-sanctioned
  endpoints); import rules table line 659 (`diagnosis/` may import `integrations/`)]
- [Source: `artifact/project-context.md` — consistency rules, integration safety, test discipline]
- [Source: `src/aiops_triage_pipeline/health/registry.py` — `HealthRegistry.update()` signature,
  component naming convention, `get_health_registry()` singleton warning for tests]
- [Source: `src/aiops_triage_pipeline/health/metrics.py` — `_meter`, `_component_health_gauge`,
  `_prev_status_values` delta-tracking pattern; in-flight counter does NOT need delta tracking]
- [Source: `src/aiops_triage_pipeline/integrations/llm.py` — existing `LLMClient` structure,
  `_FAILURE_REASON_CODES`, `DiagnosisReportV1` inline construction in MOCK/LOG mode]
- [Source: `src/aiops_triage_pipeline/denylist/enforcement.py` — `apply_denylist(fields: dict, denylist: DenylistV1) -> dict`; operates on field-keyed dicts, not plain strings]
- [Source: `src/aiops_triage_pipeline/contracts/triage_excerpt.py` — `TriageExcerptV1` fields,
  `frozen=True`; `env: Environment`, `criticality_tier: CriticalityTier`, `sustained: bool`]
- [Source: `src/aiops_triage_pipeline/contracts/enums.py` — `Environment.PROD`, `CriticalityTier.TIER_0`, `HealthStatus`]
- [Source: `artifact/implementation-artifacts/6-1-llm-stub-and-failure-injection-mode.md` —
  regression baseline 590 tests, architecture boundary fix H1, test helper `_make_excerpt()`]
- [Source: git commit `edd65c8` — cold-path/hot-path handoff contract in `docs/architecture.md`]

## Dev Agent Record

### Agent Model Used

claude-sonnet-4-6

### Debug Log References

### Completion Notes List

- Implemented `diagnosis/graph.py` with `ColdPathDiagnosisState`, `build_diagnosis_graph()`,
  `meets_invocation_criteria()`, `run_cold_path_diagnosis()`, and `spawn_cold_path_diagnosis_task()`.
- LangGraph 1.0.9 `StateGraph` wired START → invoke_llm → END; compiled per call, not singleton.
- `asyncio.wait_for(timeout=60.0)` wraps `graph.ainvoke()` for NFR-P4 compliance.
- `apply_denylist()` applied to `triage_excerpt.model_dump(mode="json")` before LLM invocation (NFR-S8).
- HealthRegistry `"llm"` component updated: HEALTHY on start and success, DEGRADED on any failure.
- `llm_inflight_add(+1/-1)` brackets graph invocation via finally block for balanced gauge.
- LIVE mode in `LLMClient`: lazy `import httpx`, POST to `{LLM_BASE_URL}/diagnose`, returns stub
  `DiagnosisReportV1(reason_codes=("LLM_LIVE_STUB",))`. Story 6.3 replaces with structured parsing.
- `LLM_BASE_URL` and `LLM_API_KEY` added to `Settings` with masked logging in `log_active_config()`.
- `httpx>=0.27` added to pyproject.toml dependencies; `uv lock` updated.
- 17 new unit tests added: 15 in `test_graph.py` + 2 new LIVE mode tests in `test_llm.py`.
  Replaced `test_live_mode_raises_not_implemented`. Updated import-guard test to allow httpx.
- Regression: 607 passed, 0 skipped, 0 failures (baseline 590 + 17 new).

### File List

**New files:**
- `src/aiops_triage_pipeline/diagnosis/graph.py`
- `tests/unit/diagnosis/test_graph.py`

**Modified files:**
- `src/aiops_triage_pipeline/health/metrics.py`
- `src/aiops_triage_pipeline/integrations/llm.py`
- `src/aiops_triage_pipeline/config/settings.py`
- `pyproject.toml`
- `uv.lock`
- `tests/unit/integrations/test_llm.py`
- `artifact/implementation-artifacts/sprint-status.yaml`
