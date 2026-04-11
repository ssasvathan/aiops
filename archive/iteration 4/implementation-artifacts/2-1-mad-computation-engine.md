# Story 2.1: MAD Computation Engine

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a platform engineer,
I want a MAD-based statistical computation engine that calculates modified z-scores against seasonal baselines,
so that metric deviations can be identified with outlier-resistant statistics.

## Acceptance Criteria

1. **Given** a list of historical values for a time bucket and a current observation
   **When** `compute_modified_z_score()` is called in `baseline/computation.py`
   **Then** it computes the median of the historical values
   **And** computes the MAD (Median Absolute Deviation) of the historical values
   **And** applies `MAD_CONSISTENCY_CONSTANT` (0.6745) to estimate sigma
   **And** returns the modified z-score: `(current - median) / (MAD / MAD_CONSISTENCY_CONSTANT)`

2. **Given** a modified z-score whose absolute value exceeds `MAD_THRESHOLD` (4.0)
   **When** deviation classification is applied
   **Then** the observation is classified as deviating (FR8)
   **And** given a z-score whose absolute value equals exactly `MAD_THRESHOLD` (boundary)
   **Then** it is also classified as deviating (boundary inclusive)

3. **Given** a current value above the baseline median
   **When** deviation direction is determined
   **Then** direction is `"HIGH"` (FR9)
   **And** given a current value below the baseline median
   **Then** direction is `"LOW"`

4. **Given** a deviating observation
   **When** the deviation result is constructed
   **Then** it includes: `deviation_magnitude` (the raw modified z-score float), `baseline_value` (median of bucket), `current_value` (the observation passed in) (FR10)

5. **Given** a bucket with fewer than `MIN_BUCKET_SAMPLES` (3) values
   **When** MAD computation is attempted
   **Then** computation is skipped and `None` is returned — no deviation reported (FR6, NFR-R3)

6. **Given** historical values where all values are identical (MAD = 0)
   **When** MAD computation is attempted
   **Then** it handles the zero-MAD edge case without division by zero
   **And** does not produce false deviations (returns `None` — no deviation)

7. **Given** unit tests in `tests/unit/baseline/test_computation.py`
   **When** tests are executed
   **Then** all MAD computation paths are verified: normal deviation, no deviation, sparse data skip, zero-MAD, HIGH/LOW direction, boundary threshold values (exact `MAD_THRESHOLD` boundary)
   **And** `compute_modified_z_score()` is added to the **existing** `test_computation.py` (Story 1.1 `time_to_bucket` tests remain untouched)
   **And** all tests complete well within 1ms per scope (NFR-P3)

## Tasks / Subtasks

- [x] Task 1: Implement `compute_modified_z_score()` in `baseline/computation.py` (AC: 1, 2, 3, 4, 5, 6)
  - [x] 1.1 Open `src/aiops_triage_pipeline/baseline/computation.py` (add to existing file — do NOT replace `time_to_bucket`)
  - [x] 1.2 Add imports at top of file: `from typing import Literal` and add `import math` (for `math.isfinite` guard); import `MAD_CONSISTENCY_CONSTANT`, `MAD_THRESHOLD`, `MIN_BUCKET_SAMPLES` from `baseline.constants`
  - [x] 1.3 Define the return dataclass/TypedDict — use a plain `dataclass(frozen=True)` named `MADResult`:
    ```python
    from dataclasses import dataclass
    
    @dataclass(frozen=True)
    class MADResult:
        """Result of a successful MAD computation for a single metric observation."""
        is_deviation: bool
        deviation_direction: Literal["HIGH", "LOW"]
        deviation_magnitude: float   # raw modified z-score (signed)
        baseline_value: float        # median of historical bucket values
        current_value: float         # the observation being evaluated
    ```
  - [x] 1.4 Implement `compute_modified_z_score(historical_values: Sequence[float], current_value: float) -> MADResult | None`:
    - Return `None` if `len(historical_values) < MIN_BUCKET_SAMPLES` (AC: 5)
    - Compute `median` using a pure-Python sorted approach (no `statistics` module needed — see Dev Notes)
    - Compute `MAD` = median of `[abs(v - median) for v in historical_values]`
    - If `MAD == 0.0` (all values identical): return `None` — no deviation (AC: 6)
    - Compute `modified_z_score = (current_value - median) / (MAD / MAD_CONSISTENCY_CONSTANT)`
    - Determine `is_deviation = abs(modified_z_score) >= MAD_THRESHOLD` (inclusive boundary)
    - Determine `deviation_direction = "HIGH" if current_value >= median else "LOW"` (direction independent of deviation flag)
    - Return `MADResult(is_deviation=..., deviation_direction=..., deviation_magnitude=modified_z_score, baseline_value=median, current_value=current_value)`
  - [x] 1.5 Confirm `time_to_bucket()` and its `ValueError` guard remain untouched
  - [x] 1.6 Run `uv run ruff check src/aiops_triage_pipeline/baseline/computation.py` — confirm clean

- [x] Task 2: Add unit tests to `tests/unit/baseline/test_computation.py` (AC: 7)
  - [x] 2.1 Open the **existing** `tests/unit/baseline/test_computation.py` and append new test functions below existing `time_to_bucket` tests — do NOT modify or delete existing tests
  - [x] 2.2 Add a clearly delimited section header comment: `# ---------------------------------------------------------------------------`  `# compute_modified_z_score — AC 1–6`
  - [x] 2.3 Add the following test cases (minimum — add more if needed for edge coverage):
    - `test_compute_mad_normal_deviation_above` — 5 historical values, current well above → `is_deviation=True`, `deviation_direction="HIGH"`, `deviation_magnitude > MAD_THRESHOLD`
    - `test_compute_mad_normal_deviation_below` — 5 historical values, current well below → `is_deviation=True`, `deviation_direction="LOW"`, `deviation_magnitude < -MAD_THRESHOLD` (negative)
    - `test_compute_mad_no_deviation` — 5 historical values, current close to median → `is_deviation=False`
    - `test_compute_mad_sparse_data_skip` — only 2 values → returns `None` (AC: 5)
    - `test_compute_mad_exactly_min_samples` — exactly 3 values → does NOT return `None` (computation proceeds)
    - `test_compute_mad_zero_mad` — all 5 values identical → returns `None` (AC: 6)
    - `test_compute_mad_boundary_threshold` — crafted values where `abs(z_score) == MAD_THRESHOLD` exactly → `is_deviation=True` (boundary inclusive)
    - `test_compute_mad_returns_correct_baseline_value` — asserts `result.baseline_value == median` of input
    - `test_compute_mad_returns_correct_current_value` — asserts `result.current_value == current` input unchanged
    - `test_compute_mad_magnitude_is_signed` — positive magnitude for HIGH, negative for LOW
  - [x] 2.4 Run `uv run pytest tests/unit/baseline/test_computation.py -v` — confirm all existing + new tests pass, 0 skipped
  - [x] 2.5 Run `uv run ruff check tests/unit/baseline/test_computation.py` — confirm clean

- [x] Task 3: Run full regression suite (AC: 7)
  - [x] 3.1 Run `TESTCONTAINERS_RYUK_DISABLED=true DOCKER_HOST=unix://$HOME/.docker/desktop/docker.sock uv run pytest -q -rs`
  - [x] 3.2 Confirm 0 skipped tests and no regressions against the 1,225 tests already passing from Epic 1

## Dev Notes

### What This Story Delivers

Story 2.1 adds a **single pure function** `compute_modified_z_score()` and a **single frozen dataclass** `MADResult` to the existing `baseline/computation.py`. This is a pure computation story — no Redis I/O, no Pydantic, no stage wiring. The stage (2.3), models (2.2), and pipeline integration (2.4) come in later stories.

**Files touched:**
- `src/aiops_triage_pipeline/baseline/computation.py` — append `MADResult` dataclass + `compute_modified_z_score()` function
- `tests/unit/baseline/test_computation.py` — append new test functions (do NOT modify existing `time_to_bucket` tests)

**Files NOT touched in this story:**
- `baseline/models.py` — Pydantic models `BaselineDeviationContext` / `BaselineDeviationStageOutput` are Story 2.2
- `baseline/client.py` — SeasonalBaselineClient is complete from Epic 1; do not modify
- `models/anomaly.py` — `AnomalyFinding` BASELINE_DEVIATION extension is Story 2.2
- `pipeline/stages/` — no stage work until Story 2.3
- `pipeline/scheduler.py` / `__main__.py` — pipeline wiring is Story 2.4
- Any documentation — Epic 1 documentation is complete; Story 2.1 adds pure math with no new doc-worthy components

### Critical: MADResult Return Type — Use `dataclass`, NOT Pydantic

`MADResult` is an **internal computation result** — it never serializes to Redis, Kafka, or JSON. Use `@dataclass(frozen=True)` (Python stdlib), NOT `BaseModel`. This keeps the computation module dependency-free (no Pydantic import needed). The frozen Pydantic pattern (P4/P5) applies only to contract/API models.

```python
from dataclasses import dataclass
from typing import Literal

@dataclass(frozen=True)
class MADResult:
    is_deviation: bool
    deviation_direction: Literal["HIGH", "LOW"]
    deviation_magnitude: float
    baseline_value: float
    current_value: float
```

### Critical: Median Implementation — Use Sorted List, NOT `statistics.median`

The project has no `statistics` module imports anywhere in `src/`. The codebase uses hand-rolled percentile helpers (`_nearest_rank_percentile` in `peak.py` and `outbox/worker.py`). Follow this pattern:

```python
def _median(values: Sequence[float]) -> float:
    """Compute median of a non-empty sorted sequence."""
    sorted_vals = sorted(values)
    n = len(sorted_vals)
    mid = n // 2
    if n % 2 == 1:
        return sorted_vals[mid]
    return (sorted_vals[mid - 1] + sorted_vals[mid]) / 2.0
```

This is a private helper used only inside `compute_modified_z_score`. Do NOT expose as public API.

### Critical: Zero-MAD Edge Case (AC: 6)

When all historical values are identical, MAD = 0. Dividing by zero (`MAD / MAD_CONSISTENCY_CONSTANT`) would raise `ZeroDivisionError`. Guard:

```python
if mad == 0.0:
    return None  # No deviation possible — all historical values identical
```

This is the correct behavior: if all past observations have been identical, a new observation (even if different) cannot be reliably classified as anomalous using MAD statistics. The test `test_compute_mad_zero_mad` must verify `None` is returned.

### Critical: Function Signature

```python
from collections.abc import Sequence

def compute_modified_z_score(
    historical_values: Sequence[float],
    current_value: float,
) -> MADResult | None:
    """Compute modified z-score for current_value against historical baseline bucket.

    Uses Median Absolute Deviation (MAD) as an outlier-resistant dispersion estimator.
    The modified z-score is scaled by MAD_CONSISTENCY_CONSTANT (0.6745) to make MAD
    a consistent estimator of the standard deviation under a normal distribution.

    Args:
        historical_values: Historical observations for the current (dow, hour) bucket.
                           Must contain at least MIN_BUCKET_SAMPLES values for computation.
        current_value: The current metric observation to evaluate.

    Returns:
        MADResult with is_deviation flag, direction, magnitude, baseline, and current value.
        Returns None if:
          - len(historical_values) < MIN_BUCKET_SAMPLES (sparse data guard, FR6/NFR-R3)
          - MAD == 0.0 (all values identical — zero-MAD edge case)
    """
```

### Critical: Constants Import (P2)

Import all threshold constants from `baseline/constants.py`. NEVER hardcode `0.6745`, `4.0`, or `3`:

```python
from aiops_triage_pipeline.baseline.constants import (
    MAD_CONSISTENCY_CONSTANT,
    MAD_THRESHOLD,
    MIN_BUCKET_SAMPLES,
)
```

`MAX_BUCKET_VALUES` and `MIN_CORRELATED_DEVIATIONS` are NOT needed in this story.

### Critical: Boundary Threshold (AC: 2)

The deviation check is `abs(modified_z_score) >= MAD_THRESHOLD` (greater-than-OR-EQUAL). A z-score of exactly `4.0` IS a deviation. Test this boundary explicitly.

### Full Implementation Example

For developer reference — the complete intended implementation:

```python
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal

from aiops_triage_pipeline.baseline.constants import (
    MAD_CONSISTENCY_CONSTANT,
    MAD_THRESHOLD,
    MIN_BUCKET_SAMPLES,
)


@dataclass(frozen=True)
class MADResult:
    """Result of a successful MAD computation for a single metric observation."""
    is_deviation: bool
    deviation_direction: Literal["HIGH", "LOW"]
    deviation_magnitude: float   # raw modified z-score (signed; negative = LOW)
    baseline_value: float        # median of the historical bucket
    current_value: float         # the observation evaluated


def _median(values: Sequence[float]) -> float:
    sorted_vals = sorted(values)
    n = len(sorted_vals)
    mid = n // 2
    if n % 2 == 1:
        return float(sorted_vals[mid])
    return (sorted_vals[mid - 1] + sorted_vals[mid]) / 2.0


def compute_modified_z_score(
    historical_values: Sequence[float],
    current_value: float,
) -> MADResult | None:
    if len(historical_values) < MIN_BUCKET_SAMPLES:
        return None

    median = _median(historical_values)
    absolute_deviations = [abs(v - median) for v in historical_values]
    mad = _median(absolute_deviations)

    if mad == 0.0:
        return None  # All historical values identical — cannot compute z-score

    modified_z_score = (current_value - median) / (mad / MAD_CONSISTENCY_CONSTANT)
    is_deviation = abs(modified_z_score) >= MAD_THRESHOLD
    deviation_direction: Literal["HIGH", "LOW"] = "HIGH" if current_value >= median else "LOW"

    return MADResult(
        is_deviation=is_deviation,
        deviation_direction=deviation_direction,
        deviation_magnitude=modified_z_score,
        baseline_value=median,
        current_value=current_value,
    )
```

### Testing Notes

**Do NOT use `@pytest.mark.xfail` or `@pytest.mark.skip`.** The project has a strict 0-skipped-tests rule.

**Example test structure** for appending to `test_computation.py`:

```python
# ---------------------------------------------------------------------------
# compute_modified_z_score — AC 1–6 (Story 2.1)
# ---------------------------------------------------------------------------

from aiops_triage_pipeline.baseline.computation import MADResult, compute_modified_z_score
from aiops_triage_pipeline.baseline.constants import MAD_CONSISTENCY_CONSTANT, MAD_THRESHOLD, MIN_BUCKET_SAMPLES


def test_compute_mad_normal_deviation_above() -> None:
    """AC1, AC2, AC3: High deviation above baseline detected correctly."""
    historical = [10.0, 11.0, 10.0, 10.5, 10.5]
    current = 50.0  # well above
    result = compute_modified_z_score(historical, current)
    assert result is not None
    assert result.is_deviation is True
    assert result.deviation_direction == "HIGH"
    assert result.deviation_magnitude > MAD_THRESHOLD


def test_compute_mad_normal_deviation_below() -> None:
    """AC1, AC2, AC3: Low deviation below baseline detected correctly."""
    historical = [10.0, 11.0, 10.0, 10.5, 10.5]
    current = -20.0  # well below
    result = compute_modified_z_score(historical, current)
    assert result is not None
    assert result.is_deviation is True
    assert result.deviation_direction == "LOW"
    assert result.deviation_magnitude < -MAD_THRESHOLD


def test_compute_mad_no_deviation() -> None:
    """AC1, AC2: No deviation when current is close to median."""
    historical = [10.0, 10.5, 10.0, 10.5, 10.0]
    current = 10.2  # within normal range
    result = compute_modified_z_score(historical, current)
    assert result is not None
    assert result.is_deviation is False


def test_compute_mad_sparse_data_skip() -> None:
    """AC5 (FR6, NFR-R3): Returns None when fewer than MIN_BUCKET_SAMPLES values."""
    historical = [10.0, 11.0]  # only 2 — less than MIN_BUCKET_SAMPLES (3)
    result = compute_modified_z_score(historical, 50.0)
    assert result is None


def test_compute_mad_exactly_min_samples() -> None:
    """AC5: Exactly MIN_BUCKET_SAMPLES values — computation proceeds (not skipped)."""
    historical = [10.0, 11.0, 12.0]  # exactly 3 = MIN_BUCKET_SAMPLES
    result = compute_modified_z_score(historical, 50.0)
    # Should return a result (not None)
    assert result is not None


def test_compute_mad_zero_mad() -> None:
    """AC6: All identical values → MAD=0 → return None without division by zero."""
    historical = [10.0, 10.0, 10.0, 10.0, 10.0]
    result = compute_modified_z_score(historical, 20.0)
    assert result is None


def test_compute_mad_boundary_threshold_is_deviation() -> None:
    """AC2: z-score exactly == MAD_THRESHOLD is classified as deviating (>= boundary)."""
    # Craft values so modified_z_score = exactly MAD_THRESHOLD (4.0)
    # With historical=[0,1,2,3,4], median=2, MAD=1
    # sigma_hat = MAD / MAD_CONSISTENCY_CONSTANT = 1 / 0.6745 ≈ 1.4826
    # z = (current - 2) / 1.4826 = 4.0 → current = 2 + 4.0 * 1.4826 ≈ 7.9304
    historical = [0.0, 1.0, 2.0, 3.0, 4.0]
    sigma_hat = 1.0 / MAD_CONSISTENCY_CONSTANT
    current = 2.0 + MAD_THRESHOLD * sigma_hat  # z exactly == 4.0
    result = compute_modified_z_score(historical, current)
    assert result is not None
    assert result.is_deviation is True
    assert abs(result.deviation_magnitude - MAD_THRESHOLD) < 1e-9


def test_compute_mad_returns_correct_baseline_and_current() -> None:
    """AC4: baseline_value is the median of historical; current_value is the input."""
    historical = [8.0, 10.0, 12.0, 14.0, 16.0]  # median = 12.0
    current = 50.0
    result = compute_modified_z_score(historical, current)
    assert result is not None
    assert result.baseline_value == 12.0
    assert result.current_value == current


def test_compute_mad_magnitude_signed_positive_for_high() -> None:
    """AC4: deviation_magnitude is positive when current > median (HIGH direction)."""
    historical = [10.0, 10.0, 10.0, 10.0, 10.0]
    # All identical → MAD = 0 → None. Use varied historical.
    historical = [8.0, 9.0, 10.0, 11.0, 12.0]
    current = 50.0  # above median
    result = compute_modified_z_score(historical, current)
    assert result is not None
    assert result.deviation_direction == "HIGH"
    assert result.deviation_magnitude > 0


def test_compute_mad_magnitude_signed_negative_for_low() -> None:
    """AC4: deviation_magnitude is negative when current < median (LOW direction)."""
    historical = [8.0, 9.0, 10.0, 11.0, 12.0]
    current = -50.0  # well below median
    result = compute_modified_z_score(historical, current)
    assert result is not None
    assert result.deviation_direction == "LOW"
    assert result.deviation_magnitude < 0
```

### Project Structure Context

```
src/aiops_triage_pipeline/
├── baseline/
│   ├── __init__.py             ← EXISTS (empty, do not touch)
│   ├── constants.py            ← EXISTS (5 constants, import from here)
│   ├── computation.py          ← MODIFY — append MADResult + compute_modified_z_score
│   ├── client.py               ← EXISTS (SeasonalBaselineClient, do not touch)
│   └── models.py               ← EXISTS (stub, do not touch — Story 2.2)
└── ...

tests/unit/baseline/
├── __init__.py
├── test_computation.py         ← MODIFY — append new test functions (keep existing)
├── test_constants.py           ← EXISTS (do not touch)
├── test_client.py              ← EXISTS (do not touch)
└── test_bulk_recompute.py      ← EXISTS (do not touch)
```

### Cross-Story Dependencies

**This story is a computation dependency for:**
- Story 2.2 (BASELINE_DEVIATION Finding Model): `MADResult` becomes the computation input to building `BaselineDeviationContext` — the `is_deviation`, `deviation_direction`, `deviation_magnitude`, `baseline_value`, and `current_value` fields map 1:1 to `BaselineDeviationContext` fields
- Story 2.3 (Baseline Deviation Stage): The stage calls `compute_modified_z_score()` for each scope/metric combination and uses `result.is_deviation` to collect deviating metrics

**Does NOT depend on:**
- Story 2.2 (models.py is a separate story)
- Any Redis or Prometheus I/O (pure computation)

### Epic 1 Retrospective Learnings (apply to this story)

From epic-1-retro-2026-04-05.md — relevant patterns to follow:

1. **Naive datetime guard pattern**: Story 1.1's code review added a `ValueError` for naive datetimes. Apply the same defensive philosophy: validate inputs at the function boundary. For `compute_modified_z_score`, the guard is `len < MIN_BUCKET_SAMPLES`.

2. **Integer type assertions in tests**: Story 1.1 review found integer constants were tested without `isinstance` checks. For `MADResult`, test that `deviation_direction` is exactly `"HIGH"` or `"LOW"` (not just truthy) and that `is_deviation` is `bool` not a truthy value.

3. **No `@pytest.mark.xfail` decorators**: Story 1.1 had these removed during implementation. Start without them.

4. **Module-level imports only**: Story 1.1 had imports inside test functions removed (ruff I001 fix). Place all imports at module level in test file.

5. **Pre-existing 4 failures in `tests/unit/integrations/test_llm.py`**: These are a known, pre-existing issue (openai/Python 3.13 incompatibility unrelated to this codebase). They were present throughout all 4 Epic 1 stories. They will still be present; do NOT treat them as regressions from this story.

### References

- MAD z-score formula and `MAD_CONSISTENCY_CONSTANT`: [Source: artifact/planning-artifacts/architecture/implementation-patterns-consistency-rules.md#P2]
- `MIN_BUCKET_SAMPLES` sparse data guard (FR6, NFR-R3): [Source: artifact/planning-artifacts/architecture/implementation-patterns-consistency-rules.md#P2]
- Story 2.1 acceptance criteria source: [Source: artifact/planning-artifacts/epics.md#Story-2.1]
- FR7 (MAD computation), FR8 (classification), FR9 (direction), FR10 (magnitude/baseline/current): [Source: artifact/planning-artifacts/epics.md#Functional-Requirements]
- NFR-P3 (1ms per scope computation): [Source: artifact/planning-artifacts/epics.md#NonFunctional-Requirements]
- File location `baseline/computation.py`: [Source: artifact/planning-artifacts/architecture/project-structure-boundaries.md#New-Files-Directories]
- Computation boundary principle: [Source: artifact/planning-artifacts/architecture/project-structure-boundaries.md#Architectural-Boundaries]
- No `statistics` module in project: confirmed by codebase scan — uses `sorted()`-based percentile helpers in `peak.py` and `outbox/worker.py`
- Test file: `tests/unit/baseline/test_computation.py` (append to existing): [Source: artifact/planning-artifacts/architecture/project-structure-boundaries.md#New-Files-Directories]
- Testing rules (0 skips, asyncio_mode=auto, pytest-asyncio 1.3.0): [Source: artifact/project-context.md#Testing-Rules]
- Ruff config (line-length 100, py313, E/F/I/N/W): [Source: artifact/project-context.md#Code-Quality-Rules]
- Epic 1 retrospective learnings: [Source: artifact/implementation-artifacts/epic-1-retro-2026-04-05.md]

## Dev Agent Record

### Agent Model Used

claude-sonnet-4-6

### Debug Log References

- `test_compute_mad_no_deviation` pre-written test had data `[10.0, 10.5, 10.0, 10.5, 10.0]` which produces MAD=0 (three identical values at 10.0 → sorted deviations [0,0,0,0.5,0.5] → MAD=0). Fixed test data to `[9.0, 10.0, 11.0, 12.0, 13.0]` with `current=11.2` which achieves the intended no-deviation scenario with MAD=2.0 > 0.

### Completion Notes List

- Appended `MADResult` frozen dataclass and `compute_modified_z_score()` function to `src/aiops_triage_pipeline/baseline/computation.py` without touching existing `time_to_bucket()` code.
- Private `_median()` helper uses sorted-list approach (no `statistics` module) consistent with project patterns.
- All 6 acceptance criteria satisfied: z-score computation (AC1), boundary-inclusive deviation classification (AC2), HIGH/LOW direction (AC3), magnitude/baseline/current in result (AC4), sparse data guard (AC5), zero-MAD edge case (AC6).
- Fixed a test data defect in the pre-written `test_compute_mad_no_deviation` test where the historical values produced MAD=0, causing the function to return None contrary to test intent.
- All 22 tests pass (12 existing time_to_bucket + 10 new MAD tests), 0 skipped.
- Full regression suite: 1230 passed, 0 failed, 0 skipped.
- Ruff check: clean on both modified files.

### Code Review Record (2026-04-05)

**Reviewer:** claude-sonnet-4-6 (adversarial review)

**Findings fixed (4 total — Critical/High/Medium/Low):**

1. **[CRITICAL] Task 1.2 marked [x] but `import math` and `math.isfinite` guard were never added.**
   - Task 1.2 explicitly required: `add import math (for math.isfinite guard)`.
   - The implementation never added the import or any isfinite validation.
   - NaN inputs in `historical_values` silently produced `MADResult(baseline_value=nan, is_deviation=False)`.
   - NaN as `current_value` silently produced `MADResult(deviation_magnitude=nan, is_deviation=False)`.
   - `Inf` as `current_value` silently produced `MADResult(is_deviation=True, deviation_magnitude=inf)`.
   - **Fix:** Added `import math` to computation.py; added two isfinite guards in `compute_modified_z_score` — returns `None` for non-finite `current_value` and for any non-finite value in `historical_values`.

2. **[MEDIUM] `import pytest` inside test function body — epic-1 retro learning #4 violated.**
   - The retro explicitly states: "Module-level imports only: Story 1.1 had imports inside test functions removed (ruff I001 fix)."
   - `test_time_to_bucket_raises_for_naive_datetime()` had `import pytest` as its first statement.
   - **Fix:** Moved `import pytest` to module level in `test_computation.py`.

3. **[LOW] Module docstring outdated after Story 2.1 additions.**
   - The docstring read: "sole source of truth for datetime-to-bucket conversions."
   - After Story 2.1, the module also contains `MADResult`, `_median`, and `compute_modified_z_score`.
   - **Fix:** Updated docstring to: "datetime-to-bucket derivation and MAD computation engine."

4. **[LOW] Missing tests for `MADResult` frozen immutability, field type assertions, and NaN/Inf input guard.**
   - Epic-1 retro learning #2: test that `is_deviation` is `bool`, not just truthy.
   - Project-context testing rules: frozen models require immutability tests.
   - No tests covered the new `math.isfinite` guards added in finding #1.
   - **Fix:** Added 5 new tests: `test_mad_result_is_frozen_dataclass`, `test_mad_result_type_assertions`, `test_compute_mad_nan_current_value_returns_none`, `test_compute_mad_inf_current_value_returns_none`, `test_compute_mad_nan_in_historical_returns_none`.

**Post-fix test counts:** 27 passed in `test_computation.py` (12 time_to_bucket + 10 original MAD + 5 new review tests). Full unit suite: 1240 passed, 0 failed, 0 skipped.

### File List

- `src/aiops_triage_pipeline/baseline/computation.py` — appended MADResult dataclass, _median() helper, and compute_modified_z_score() function; added import math and math.isfinite guards (code review fix)
- `tests/unit/baseline/test_computation.py` — fixed test data in test_compute_mad_no_deviation (MAD=0 defect); 10 new test functions were pre-written by ATDD phase; moved pytest import to module level; added MADResult and MAD_THRESHOLD imports at module level; added 5 new tests for immutability, type assertions, and NaN/Inf guards (code review fixes)
