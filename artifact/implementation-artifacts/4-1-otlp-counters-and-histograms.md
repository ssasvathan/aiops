# Story 4.1: OTLP Counters & Histograms

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As an SRE,
I want OTLP counters and histograms tracking baseline deviation detection effectiveness and performance,
so that I can monitor detection rates, suppression ratios, and computation latency in Dynatrace.

## Acceptance Criteria

1. **Given** the baseline deviation stage runs a cycle
   **When** deviations are detected
   **Then** the counter `aiops.baseline_deviation.deviations_detected` is incremented by the number of deviations found (FR29)

2. **Given** findings are emitted or suppressed during a cycle
   **When** the stage completes
   **Then** `aiops.baseline_deviation.findings_emitted` is incremented for each emitted finding (FR29)
   **And** `aiops.baseline_deviation.suppressed_single_metric` is incremented for each single-metric suppression (FR29)
   **And** `aiops.baseline_deviation.suppressed_dedup` is incremented for each hand-coded dedup suppression (FR29)

3. **Given** the stage execution is timed
   **When** the stage completes
   **Then** `aiops.baseline_deviation.stage_duration_seconds` histogram records the total stage duration (FR30)
   **And** `aiops.baseline_deviation.mad_computation_seconds` histogram records per-scope MAD computation time (FR30)

4. **Given** the OTLP instruments are created
   **When** they are initialized
   **Then** they use the OpenTelemetry SDK `_meter.create_counter()` and `_meter.create_histogram()` methods directly (matching the `outbox/metrics.py` and `health/metrics.py` patterns)
   **And** follow the `aiops.baseline_deviation.` naming prefix (P7)

5. **Given** unit tests in `tests/unit/pipeline/stages/test_baseline_deviation.py`
   **When** tests are executed
   **Then** counter increments and histogram recordings are verified with mock OTLP instruments via `monkeypatch` (matching the `tests/unit/health/test_metrics.py` pattern)
   **And** instrument names match the P7 naming convention exactly

## Tasks / Subtasks

- [x] Task 1: Create `src/aiops_triage_pipeline/baseline/metrics.py` with module-level OTLP instruments (AC: 4)
  - [x] 1.1 Create `baseline/metrics.py` — establish a `_meter = metrics.get_meter("aiops_triage_pipeline.baseline_deviation")` module-level meter (consistent with `outbox/metrics.py` and `health/metrics.py`)
  - [x] 1.2 Define module-level instruments with exact P7 names:
    - `_deviations_detected` = `_meter.create_counter("aiops.baseline_deviation.deviations_detected", description="...", unit="1")`
    - `_findings_emitted` = `_meter.create_counter("aiops.baseline_deviation.findings_emitted", description="...", unit="1")`
    - `_suppressed_single_metric` = `_meter.create_counter("aiops.baseline_deviation.suppressed_single_metric", description="...", unit="1")`
    - `_suppressed_dedup` = `_meter.create_counter("aiops.baseline_deviation.suppressed_dedup", description="...", unit="1")`
    - `_stage_duration_seconds` = `_meter.create_histogram("aiops.baseline_deviation.stage_duration_seconds", description="...", unit="s")`
    - `_mad_computation_seconds` = `_meter.create_histogram("aiops.baseline_deviation.mad_computation_seconds", description="...", unit="s")`
  - [x] 1.3 Define public recording functions (mirrors `outbox/metrics.py` style):
    - `record_deviations_detected(count: int) -> None`
    - `record_finding_emitted() -> None`
    - `record_suppressed_single_metric() -> None`
    - `record_suppressed_dedup() -> None`
    - `record_stage_duration(seconds: float) -> None`
    - `record_mad_computation(seconds: float) -> None`
  - [x] 1.4 Run `uv run ruff check src/aiops_triage_pipeline/baseline/metrics.py` — confirm 0 violations

- [x] Task 2: Wire OTLP recording calls into `pipeline/stages/baseline_deviation.py` (AC: 1, 2, 3)
  - [x] 2.1 Import `from aiops_triage_pipeline.baseline import metrics as baseline_metrics` at module level in `baseline_deviation.py`
  - [x] 2.2 After the detection loop: call `baseline_metrics.record_deviations_detected(deviations_detected)` once per cycle
  - [x] 2.3 Inside the finding emission block: call `baseline_metrics.record_finding_emitted()` for each emitted finding
  - [x] 2.4 Inside the single-metric suppression block: call `baseline_metrics.record_suppressed_single_metric()`
  - [x] 2.5 Inside the dedup suppression block: call `baseline_metrics.record_suppressed_dedup()`
  - [x] 2.6 Wrap per-scope MAD computation timing: capture `t0 = time.perf_counter()` before `_evaluate_scope()`, `baseline_metrics.record_mad_computation(time.perf_counter() - t0)` after (only on non-error path)
  - [x] 2.7 After `elapsed_ms = (time.perf_counter() - started_at) * 1000`: call `baseline_metrics.record_stage_duration(elapsed_ms / 1000)` (convert ms → seconds for histogram unit "s")
  - [x] 2.8 Run `uv run ruff check src/aiops_triage_pipeline/pipeline/stages/baseline_deviation.py` — confirm 0 violations

- [x] Task 3: Add OTLP unit tests to `tests/unit/pipeline/stages/test_baseline_deviation.py` (AC: 5)
  - [x] 3.1 Add `_RecordingInstrument` class (mirrors `tests/unit/health/test_metrics.py` pattern — copy exactly) to the test file
  - [x] 3.2 Add test `test_deviations_detected_counter_incremented()`:
    - Monkeypatch `baseline_metrics._deviations_detected` with `_RecordingInstrument()`
    - Run stage with 3 deviating metrics across 1 scope that emits a finding
    - Assert `instrument.calls == [(3, None)]` (count=3, no attributes)
  - [x] 3.3 Add test `test_findings_emitted_counter_incremented()`:
    - Monkeypatch `baseline_metrics._findings_emitted`
    - Run stage producing 1 correlated finding
    - Assert `instrument.calls == [(1, None)]`
  - [x] 3.4 Add test `test_suppressed_single_metric_counter_incremented()`:
    - Monkeypatch `baseline_metrics._suppressed_single_metric`
    - Run stage where 1 scope has exactly 1 deviating metric (< MIN_CORRELATED_DEVIATIONS)
    - Assert `instrument.calls == [(1, None)]`
  - [x] 3.5 Add test `test_suppressed_dedup_counter_incremented()`:
    - Monkeypatch `baseline_metrics._suppressed_dedup`
    - Run stage with a scope already fired by CONSUMER_LAG hand-coded detector
    - Assert `instrument.calls == [(1, None)]`
  - [x] 3.6 Add test `test_stage_duration_histogram_recorded()`:
    - Monkeypatch `baseline_metrics._stage_duration_seconds`
    - Run stage with one scope
    - Assert `len(instrument.calls) == 1` and `instrument.calls[0][0] > 0` (duration > 0 seconds)
  - [x] 3.7 Add test `test_mad_computation_histogram_recorded_per_scope()`:
    - Monkeypatch `baseline_metrics._mad_computation_seconds`
    - Run stage with 2 scopes
    - Assert `len(instrument.calls) == 2` (one recording per scope evaluated)
  - [x] 3.8 Add test `test_instrument_names_match_p7_convention()`:
    - Import `baseline_metrics` module
    - Assert `baseline_metrics._deviations_detected.name == "aiops.baseline_deviation.deviations_detected"` — repeat for all 6 instruments
    - NOTE: OTel `_ProxyCounter` doesn't expose `.name`; resolved by wrapping instruments in `_NamedCounter`/`_NamedHistogram` classes in `baseline/metrics.py`
  - [x] 3.9 Run `uv run pytest tests/unit/pipeline/stages/test_baseline_deviation.py -v` — confirm all existing tests + new tests pass
  - [x] 3.10 Run `uv run ruff check tests/unit/pipeline/stages/test_baseline_deviation.py` — 0 violations
  - [x] 3.11 **MANDATORY ATDD GATE** (Epic 3 Lesson L1): Run `uv run pytest tests/unit/ -q` — confirm target count (1319 existing + ~7 new = ~1326) all pass, 0 failures, before requesting code review

- [x] Task 4: Full regression run (AC: inline)
  - [x] 4.1 Run `uv run pytest tests/unit/ -q` — confirm all prior tests pass + new tests pass, 0 failures, 0 skipped
  - [x] 4.2 Run `uv run ruff check src/ tests/` — 0 lint violations across entire source tree and test suite

## Dev Notes

### Architecture Decision: Separate `baseline/metrics.py` Module vs. Inline

The `project-structure-boundaries.md` notes "instruments created inline" in `pipeline/stages/baseline_deviation.py`. However, the **established codebase pattern** uses separate metrics modules:
- `src/aiops_triage_pipeline/outbox/metrics.py` — separate module for outbox OTLP instruments
- `src/aiops_triage_pipeline/health/metrics.py` — separate module for health/pipeline instruments

Following the established codebase pattern (not the architectural note, which predated seeing this pattern at scale), **create `baseline/metrics.py`** as a dedicated module. This:
1. Keeps the stage function focused on detection logic
2. Enables clean `monkeypatch` isolation in tests (exactly as `test_metrics.py` does)
3. Avoids module-level instrument creation inside `baseline_deviation.py` which would complicate test isolation

The architecture's "inline" intent is satisfied by having the stage import and call the helpers — the instruments live in the baseline package, co-located with the stage domain.

### OTLP Instrument Creation Pattern

Exact pattern from `outbox/metrics.py` (the cleanest reference):

```python
from opentelemetry import metrics

_meter = metrics.get_meter("aiops_triage_pipeline.baseline_deviation")

_deviations_detected = _meter.create_counter(
    name="aiops.baseline_deviation.deviations_detected",
    description="Total metric deviations detected by baseline deviation stage",
    unit="1",
)
_findings_emitted = _meter.create_counter(
    name="aiops.baseline_deviation.findings_emitted",
    description="Total correlated BASELINE_DEVIATION findings emitted",
    unit="1",
)
_suppressed_single_metric = _meter.create_counter(
    name="aiops.baseline_deviation.suppressed_single_metric",
    description="Total findings suppressed due to single-metric threshold",
    unit="1",
)
_suppressed_dedup = _meter.create_counter(
    name="aiops.baseline_deviation.suppressed_dedup",
    description="Total findings suppressed due to hand-coded detector dedup",
    unit="1",
)
_stage_duration_seconds = _meter.create_histogram(
    name="aiops.baseline_deviation.stage_duration_seconds",
    description="Baseline deviation stage execution time per cycle",
    unit="s",
)
_mad_computation_seconds = _meter.create_histogram(
    name="aiops.baseline_deviation.mad_computation_seconds",
    description="MAD computation time per scope per cycle",
    unit="s",
)
```

Public recording functions (no attributes needed for these counters — the stage output already captures counts):

```python
def record_deviations_detected(count: int) -> None:
    if count <= 0:
        return
    _deviations_detected.add(count)


def record_finding_emitted() -> None:
    _findings_emitted.add(1)


def record_suppressed_single_metric() -> None:
    _suppressed_single_metric.add(1)


def record_suppressed_dedup() -> None:
    _suppressed_dedup.add(1)


def record_stage_duration(seconds: float) -> None:
    _stage_duration_seconds.record(max(seconds, 0.0))


def record_mad_computation(seconds: float) -> None:
    _mad_computation_seconds.record(max(seconds, 0.0))
```

### Wiring into `collect_baseline_deviation_stage_output()`

The stage already has `started_at = time.perf_counter()` at the top and `elapsed_ms = (time.perf_counter() - started_at) * 1000` at the bottom. Instrument the existing timing points:

**Import addition** (module level, after existing imports):
```python
from aiops_triage_pipeline.baseline import metrics as baseline_metrics
```

**Inside the dedup suppression block** (after `deviations_suppressed_dedup += 1`):
```python
baseline_metrics.record_suppressed_dedup()
```

**Per-scope MAD timing** — wrap `_evaluate_scope()` call:
```python
_scope_t0 = time.perf_counter()
try:
    result = _evaluate_scope(...)
except (ConnectionError, OSError, TimeoutError):
    raise
except Exception as exc:
    logger.warning(...)
    continue
baseline_metrics.record_mad_computation(time.perf_counter() - _scope_t0)
```

**After finding emission** (`findings.append(finding_or_suppressed)`):
```python
baseline_metrics.record_finding_emitted()
```

**After single-metric suppression** (`deviations_suppressed_single_metric += 1`):
```python
baseline_metrics.record_suppressed_single_metric()
```

**After detection loop** (before `elapsed_ms` computation):
```python
baseline_metrics.record_deviations_detected(deviations_detected)
```

**After `elapsed_ms` computation**:
```python
baseline_metrics.record_stage_duration(elapsed_ms / 1000)
```

### MAD Timing Scope: What to Time

`_evaluate_scope()` encompasses all MAD computation for one scope: Redis reads (`read_buckets_batch`), per-metric `compute_modified_z_score()`, correlation gate evaluation, and finding construction. The histogram `mad_computation_seconds` is defined in the architecture as "per-scope MAD computation time" — timing `_evaluate_scope()` is the correct scope.

Do NOT time scope-skipped-by-dedup (hand-coded scope exits before `_evaluate_scope()` call). Only time scopes that actually compute.

### Testing Pattern: `_RecordingInstrument` and `monkeypatch`

Copy the `_RecordingInstrument` class from `tests/unit/health/test_metrics.py` verbatim:

```python
class _RecordingInstrument:
    def __init__(self) -> None:
        self.calls: list[tuple[float, dict[str, str] | None]] = []

    def add(self, value: float, attributes: dict[str, str] | None = None) -> None:
        self.calls.append((value, attributes))

    def record(self, value: float, attributes: dict[str, str] | None = None) -> None:
        self.calls.append((value, attributes))
```

Monkeypatch the module-level instrument, NOT the meter:

```python
def test_deviations_detected_counter_incremented(monkeypatch) -> None:
    from aiops_triage_pipeline.baseline import metrics as baseline_metrics

    instrument = _RecordingInstrument()
    monkeypatch.setattr(baseline_metrics, "_deviations_detected", instrument)

    mock_client = _make_mock_client(...)  # 3 deviating metrics
    result = collect_baseline_deviation_stage_output(...)

    assert instrument.calls == [(3, None)]
```

Import `baseline_metrics` **inside** the test function body — not at module level — to ensure monkeypatch applies to the correct module reference. (Epic 2 Retro TD-3 / structlog lazy instantiation lesson applies here: deferred imports allow test fixtures to take effect before the import runs.)

### P7 Naming Convention Verification

The 6 instrument names (P7 from architecture):

| Instrument | Name |
|---|---|
| Counter | `aiops.baseline_deviation.deviations_detected` |
| Counter | `aiops.baseline_deviation.findings_emitted` |
| Counter | `aiops.baseline_deviation.suppressed_single_metric` |
| Counter | `aiops.baseline_deviation.suppressed_dedup` |
| Histogram | `aiops.baseline_deviation.stage_duration_seconds` |
| Histogram | `aiops.baseline_deviation.mad_computation_seconds` |

These match FR29 (4 counters) and FR30 (2 histograms) exactly. Note: the architecture specifies 4 counters and 2 histograms; this story covers all 6 instruments.

### No Changes to Existing Counter Logic

The stage already tracks `deviations_detected`, `deviations_suppressed_single_metric`, `deviations_suppressed_dedup`, `findings` count as local variables in `collect_baseline_deviation_stage_output()`. The OTLP recording mirrors these existing counters to the telemetry backend — it does NOT replace the local variables (which are also returned in `BaselineDeviationStageOutput` for unit test verification). Both local counting and OTLP emission should occur.

### TD-2: `test_finding_baseline_context_populated` Weekday Assertion (Epic 2/3 Carry)

Epic 3 retrospective noted TD-2: `test_finding_baseline_context_populated` has a weekday assertion mismatch (documented in Epic 2 retro, carried from Epic 3). This story adds tests to `test_baseline_deviation.py`. **Before adding new tests, check if this assertion mismatch still exists** and fix it as part of this story (it's the right time — we're already in the file). Look for:

```python
# Suspect line in test_finding_baseline_context_populated
assert result.findings[0].baseline_context.time_bucket == (something, something)
```

Verify the `FIXED_EVAL_TIME = datetime(2026, 4, 5, 14, 0, tzinfo=UTC)` used in the test file is `Sunday 14:00 UTC`. `datetime(2026, 4, 5)` is a Sunday, so `weekday() = 6`. The bucket should be `(6, 14)`. Fix if wrong.

### Fail-Open Path: No OTLP Recording on Redis Failure

When Redis is unavailable and the stage returns early (the `except Exception` block at the outer level), **do NOT record OTLP counters**. The early return in the fail-open path returns an empty `BaselineDeviationStageOutput` with all counts at 0. No counter increments should be emitted because no processing occurred. The `record_deviations_detected()` and `record_stage_duration()` calls are after the except block — they will NOT be reached. This is correct behavior.

### Scope of This Story vs. Story 4-2

Story 4-1 covers FR29 (4 counters) and FR30 (2 histograms) only.

Story 4-2 covers FR31 (structured log events) and FR32 (HealthRegistry). The structured log events (`baseline_deviation_stage_started`, `baseline_deviation_stage_completed`, etc.) **already exist** in the current `baseline_deviation.py` (see the current implementation — they were added in Story 2.3). Story 4-2 will verify completeness and add the HealthRegistry integration.

Do NOT add HealthRegistry calls or new structured log events in this story. Scope boundary is strictly FR29+FR30.

### Structlog Logger Instantiation (Epic 2 Retro TD-3 / L3 Applied)

The `collect_baseline_deviation_stage_output()` function already correctly instantiates its logger **inside the function body** (`logger = get_logger("pipeline.stages.baseline_deviation")`). The new `baseline/metrics.py` module has no structlog usage — it only uses OpenTelemetry. No structlog concern for this story.

### Current Test Count

1,319 unit tests collected (after Epic 3). Target for this story: approximately +7 new tests:
- 6 counter/histogram recording tests
- 1 instrument naming convention test
- **Target: ~1,326 tests passing. Zero regressions required.**

### Project Structure Notes

**New files:**
- `src/aiops_triage_pipeline/baseline/metrics.py` — new OTLP instruments module

**Files to modify:**
- `src/aiops_triage_pipeline/pipeline/stages/baseline_deviation.py` — add OTLP recording calls + import
- `tests/unit/pipeline/stages/test_baseline_deviation.py` — add OTLP counter/histogram tests

**Alignment with project-structure-boundaries.md:**
- Architecture maps FR29-FR32 to `pipeline/stages/baseline_deviation.py` as primary file. Creating `baseline/metrics.py` as an auxiliary module is consistent with `outbox/metrics.py` pattern — the stage remains the "primary file" where instruments are called; `baseline/metrics.py` is the instrument definition module.
- No changes to contracts, models, or other packages.

### References

- Epic 4 Story 4.1 requirements: `artifact/planning-artifacts/epics.md` §Epic 4, Story 4.1
- FR29: OTLP counters (deviations detected, findings emitted/suppressed)
- FR30: OTLP histograms (stage latency, MAD computation time)
- NFR-P1: Stage must complete within 40 seconds per cycle — measured via `aiops.baseline_deviation.stage_duration_seconds` histogram
- NFR-P3: MAD computation per scope within 1ms — observable via `aiops.baseline_deviation.mad_computation_seconds`
- P7 naming convention: `artifact/planning-artifacts/architecture/implementation-patterns-consistency-rules.md` §P7
- Existing stage implementation: `src/aiops_triage_pipeline/pipeline/stages/baseline_deviation.py`
- Reference OTLP module (outbox pattern): `src/aiops_triage_pipeline/outbox/metrics.py`
- Reference OTLP module (health/pipeline pattern): `src/aiops_triage_pipeline/health/metrics.py`
- Reference test pattern: `tests/unit/health/test_metrics.py`
- Existing stage tests: `tests/unit/pipeline/stages/test_baseline_deviation.py`
- OTLP bootstrap: `src/aiops_triage_pipeline/health/otlp.py`
- Epic 3 Retrospective lessons (L1 ATDD-run-before-review gate): `artifact/implementation-artifacts/epic-3-retro-2026-04-05.md`
- Epic 4 preparation tasks: `artifact/implementation-artifacts/epic-3-retro-2026-04-05.md` §Next Epic Preview

## Dev Agent Record

### Agent Model Used

claude-sonnet-4-6

### Debug Log References

None — implementation proceeded without blockers.

### Completion Notes List

- Created `src/aiops_triage_pipeline/baseline/metrics.py` with 6 OTLP instruments (4 counters + 2 histograms). Used thin `_NamedCounter`/`_NamedHistogram` wrapper classes to expose `.name` attribute since OTel `_ProxyCounter` doesn't expose it natively — required for `test_instrument_names_match_p7_convention`.
- Wired all 6 recording calls into `collect_baseline_deviation_stage_output()` in `baseline_deviation.py`: dedup suppression, per-scope MAD timing, single-metric suppression, finding emission, total deviations detected, and stage duration.
- All 28 tests in `test_baseline_deviation.py` pass (21 existing + 7 new OTLP tests).
- Full regression: 1326 tests pass, 0 failures, 0 skipped. Zero ruff violations.

### File List

- `src/aiops_triage_pipeline/baseline/metrics.py` (created)
- `src/aiops_triage_pipeline/pipeline/stages/baseline_deviation.py` (modified)
- `tests/unit/pipeline/stages/test_baseline_deviation.py` (modified — ATDD tests appended + 2 review fix tests added)
- `artifact/implementation-artifacts/sprint-status.yaml` (modified — story status updated to review)
- `artifact/test-artifacts/atdd-checklist-4-1-otlp-counters-and-histograms.md` (created — ATDD checklist)
