# Story 1.1: Baseline Constants & Time Bucket Derivation

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a platform engineer,
I want baseline deviation constants and time bucket logic defined in a single source of truth,
so that all baseline components use consistent threshold values and bucket derivation logic.

## Acceptance Criteria

1. **Given** the baseline package is created with `baseline/__init__.py` and `baseline/constants.py`
   **When** `constants.py` is imported
   **Then** the following constants are available as module-level SCREAMING_SNAKE_CASE values:
   - `MAD_CONSISTENCY_CONSTANT = 0.6745`
   - `MAD_THRESHOLD = 4.0`
   - `MIN_CORRELATED_DEVIATIONS = 2`
   - `MIN_BUCKET_SAMPLES = 3`
   - `MAX_BUCKET_VALUES = 12`
   **And** no magic numbers are hardcoded anywhere outside this module (P2)

2. **Given** a UTC datetime for Wednesday at 14:00
   **When** `time_to_bucket()` is called
   **Then** it returns `(2, 14)` — Wednesday (`.weekday() == 2`) and hour 14

3. **Given** a non-UTC datetime (e.g., UTC+5, so 19:00 local = 14:00 UTC on Wednesday)
   **When** `time_to_bucket()` is called
   **Then** it converts to UTC before deriving the bucket
   **And** returns the correct `(dow, hour)` based on UTC-normalized time

4. **Given** any datetime input
   **When** `time_to_bucket()` is called
   **Then** `dow` is in range `0–6` (Monday=0, Sunday=6) and `hour` is in range `0–23`
   **And** this function is the sole source of truth for all datetime-to-bucket conversions (P3)

5. **Given** the new files `baseline/__init__.py`, `baseline/constants.py`, and `time_to_bucket()` in `baseline/computation.py`
   **When** unit tests in `tests/unit/baseline/test_constants.py` and `tests/unit/baseline/test_computation.py` are run
   **Then** all constant values and `time_to_bucket` edge cases (midnight, end-of-week, timezone boundaries) pass
   **And** `docs/project-structure.md`, `docs/component-inventory.md`, and `docs/data-models.md` are updated to reflect the new baseline package

## Tasks / Subtasks

- [x] Task 1: Create the `baseline` package skeleton (AC: 1)
  - [x] 1.1 Create `src/aiops_triage_pipeline/baseline/__init__.py` (empty, marks package)
  - [x] 1.2 Create `src/aiops_triage_pipeline/baseline/constants.py` with all 5 SCREAMING_SNAKE_CASE constants
  - [x] 1.3 Verify import works: `from aiops_triage_pipeline.baseline.constants import MAD_CONSISTENCY_CONSTANT` etc.

- [x] Task 2: Implement `time_to_bucket()` in `baseline/computation.py` (AC: 2, 3, 4)
  - [x] 2.1 Create `src/aiops_triage_pipeline/baseline/computation.py`
  - [x] 2.2 Implement `time_to_bucket(dt: datetime) -> tuple[int, int]` using `.astimezone(timezone.utc)` then `.weekday()` and `.hour`
  - [x] 2.3 Confirm `datetime.weekday()` (Mon=0) not `isoweekday()` (Mon=1) is used

- [x] Task 3: Create stub `baseline/models.py` (no AC this story — scaffold for future stories)
  - [x] 3.1 Create `src/aiops_triage_pipeline/baseline/models.py` with a module-level docstring noting placeholder for `BaselineDeviationContext` and `BaselineDeviationStageOutput` (Stories 1.2+)
  - [x] 3.2 Do NOT implement models in this story — they depend on Story 1.2+ context

- [x] Task 4: Create `tests/unit/baseline/` package and unit tests (AC: 5)
  - [x] 4.1 Create `tests/unit/baseline/__init__.py`
  - [x] 4.2 Create `tests/unit/baseline/test_constants.py` — assert exact float/int values for all 5 constants
  - [x] 4.3 Create `tests/unit/baseline/test_computation.py` covering:
    - Wednesday 14:00 UTC → `(2, 14)`
    - Non-UTC datetime (UTC+5, local 19:00 Wed) → `(2, 14)` (UTC-normalized)
    - Midnight Sunday UTC → `(6, 0)` (Sunday = weekday 6, hour 0)
    - Monday 00:00 UTC → `(0, 0)`
    - Saturday 23:00 UTC → `(5, 23)`
    - Timezone boundary: local time Thursday 01:00 UTC+5 = Wednesday 20:00 UTC → `(2, 20)`

- [x] Task 5: Update documentation (AC: 5)
  - [x] 5.1 Update `docs/project-structure.md` — add `baseline/` sub-tree entry under `src/aiops_triage_pipeline/`
  - [x] 5.2 Update `docs/component-inventory.md` — add `SeasonalBaselineClient` placeholder row and `baseline/` computation module entry under Runtime Components
  - [x] 5.3 Update `docs/data-models.md` — add section noting the baseline package and that `BaselineDeviationContext` / `BaselineDeviationStageOutput` models are forthcoming (Story 1.2)

- [x] Task 6: Run full regression suite (AC: 5)
  - [x] 6.1 Run `TESTCONTAINERS_RYUK_DISABLED=true DOCKER_HOST=unix://$HOME/.docker/desktop/docker.sock uv run pytest -q -rs`
  - [x] 6.2 Confirm 0 skipped tests and no regressions

## Dev Notes

### What This Story Delivers

This is a pure scaffolding story. It creates the `baseline/` Python package with exactly two functional files:
- `baseline/constants.py` — 5 numerical constants, nothing else
- `baseline/computation.py` — 1 pure function (`time_to_bucket`)

Everything else in the `baseline/` package (`client.py`, full `models.py`) is built in later stories. Create `models.py` as an empty stub with only a docstring.

### Critical Implementation Pattern: P2 (Constants)

All baseline deviation constants live **exclusively** in `baseline/constants.py`. The implementation pattern from architecture:

```python
# src/aiops_triage_pipeline/baseline/constants.py
MAD_CONSISTENCY_CONSTANT = 0.6745   # Scaling constant to make MAD consistent estimator of sigma
MAD_THRESHOLD = 4.0                  # Modified z-score threshold for deviation classification
MIN_CORRELATED_DEVIATIONS = 2        # Minimum deviating metrics to emit a finding (correlation gate)
MIN_BUCKET_SAMPLES = 3               # Minimum historical samples required to compute MAD
MAX_BUCKET_VALUES = 12               # Maximum values stored per bucket (~12 weeks of weekly samples)
```

**Anti-pattern to prevent:** Do NOT hardcode `0.6745`, `4.0`, `3`, `2`, or `12` anywhere outside this file. All future stories (1.2, 1.3, 2.1, etc.) import from here.

### Critical Implementation Pattern: P3 (time_to_bucket)

Exact canonical implementation from architecture:

```python
# src/aiops_triage_pipeline/baseline/computation.py
from datetime import datetime, timezone


def time_to_bucket(dt: datetime) -> tuple[int, int]:
    """Convert a datetime to a (day_of_week, hour) bucket using UTC-normalized time.

    Returns:
        tuple[int, int]: (dow, hour) where dow uses datetime.weekday() convention
            (Monday=0, Tuesday=1, ..., Sunday=6) and hour is 0-23.
    """
    utc_dt = dt.astimezone(timezone.utc)
    return (utc_dt.weekday(), utc_dt.hour)
```

**Anti-patterns to prevent:**
- Do NOT use `datetime.isoweekday()` (Monday=1, Sunday=7) — use `weekday()` (Monday=0, Sunday=6)
- Do NOT use local time — always normalize to UTC first with `.astimezone(timezone.utc)`
- Do NOT derive buckets inline anywhere else — always call this function

This function is the **sole source of truth** for all datetime-to-bucket conversions. Every other component (Stage 1.2 client, Stage 1.3 backfill, Stage 2.1 MAD engine) must import and call this function.

### Project Structure Context

The new files slot into the existing package structure:
```
src/aiops_triage_pipeline/
├── baseline/                   ← NEW PACKAGE (this story)
│   ├── __init__.py             ← empty, marks package
│   ├── constants.py            ← 5 constants only
│   ├── computation.py          ← time_to_bucket() only
│   └── models.py               ← empty stub (future stories)
├── pipeline/
│   ├── baseline_backfill.py    ← EXISTS (do NOT modify in this story)
│   ├── baseline_store.py       ← EXISTS (do NOT modify in this story)
│   └── stages/
│       ├── peak.py, evidence.py, etc.  ← EXISTS unchanged
└── models/
    └── anomaly.py              ← EXISTS (do NOT modify in this story)
```

**Existing files to NOT touch in this story:**
- `pipeline/baseline_backfill.py` — existing backfill (Story 1.3 extends this)
- `pipeline/baseline_store.py` — existing Redis cache (separate from seasonal baseline client)
- `models/anomaly.py` — `AnomalyFinding` extension (Story 2.x)
- Any `pipeline/stages/` file

**Important distinction:** `pipeline/baseline_store.py` and `pipeline/baseline_backfill.py` are the **existing** peak-history Redis cache. The new `baseline/` package creates a **separate** seasonal baseline layer. Do not conflate them.

### Existing Code Patterns to Follow

**Package `__init__.py`**: All existing sub-packages use empty `__init__.py` files (see `integrations/__init__.py`, `models/__init__.py`). Keep `baseline/__init__.py` empty.

**Import style** (from existing stage files like `pipeline/stages/peak.py`):
```python
from datetime import UTC, datetime, timezone  # UTC alias available in Python 3.11+
```
Use `from datetime import datetime, timezone` — `timezone.utc` is the explicit form used in `time_to_bucket`.

**Module docstring pattern** (from `pipeline/baseline_backfill.py`):
```python
"""Brief one-line description of the module."""
```

**Type annotation style** (Python 3.13, from `models/anomaly.py`):
```python
def time_to_bucket(dt: datetime) -> tuple[int, int]:  # built-in tuple, not typing.Tuple
```

### Testing Notes

**Test file pattern** (mirror `tests/unit/pipeline/conftest.py` setup):
- Unit tests in `tests/unit/baseline/` use standard pytest — no async, no fixtures needed for pure functions
- Use `assert` statements directly; no complex fixtures

**Example test structure** for `test_computation.py`:
```python
from datetime import datetime, timezone, timedelta

from aiops_triage_pipeline.baseline.computation import time_to_bucket


def test_time_to_bucket_wednesday_14_utc():
    dt = datetime(2026, 1, 7, 14, 0, 0, tzinfo=timezone.utc)  # Wednesday Jan 7 2026
    assert time_to_bucket(dt) == (2, 14)  # weekday()=2 for Wednesday


def test_time_to_bucket_converts_non_utc_to_utc():
    # UTC+5, local Wednesday 19:00 = UTC Wednesday 14:00
    utc_plus_5 = timezone(timedelta(hours=5))
    dt = datetime(2026, 1, 7, 19, 0, 0, tzinfo=utc_plus_5)
    assert time_to_bucket(dt) == (2, 14)


def test_time_to_bucket_sunday_midnight_utc():
    # Sunday = weekday() 6, midnight = hour 0
    dt = datetime(2026, 1, 11, 0, 0, 0, tzinfo=timezone.utc)  # Sunday Jan 11 2026
    assert time_to_bucket(dt) == (6, 0)
```

**Example test structure** for `test_constants.py`:
```python
from aiops_triage_pipeline.baseline import constants


def test_mad_consistency_constant():
    assert constants.MAD_CONSISTENCY_CONSTANT == 0.6745


def test_mad_threshold():
    assert constants.MAD_THRESHOLD == 4.0


def test_min_correlated_deviations():
    assert constants.MIN_CORRELATED_DEVIATIONS == 2


def test_min_bucket_samples():
    assert constants.MIN_BUCKET_SAMPLES == 3


def test_max_bucket_values():
    assert constants.MAX_BUCKET_VALUES == 12
```

### Documentation Update Specifics

**`docs/project-structure.md`** — append to the source tree listing under `src/aiops_triage_pipeline/`:
```
- `baseline/` - baseline deviation domain (constants, computation, client, models)
```

**`docs/component-inventory.md`** — add two rows to the Runtime Components table:
| Baseline Constants | Configuration | `baseline/constants.py` | Yes | MAD_CONSISTENCY_CONSTANT, MAD_THRESHOLD, MIN_CORRELATED_DEVIATIONS, MIN_BUCKET_SAMPLES, MAX_BUCKET_VALUES |
| Baseline Computation | Computation | `baseline/computation.py` | Yes | time_to_bucket() — sole UTC-normalized (dow, hour) bucket derivation function |

**`docs/data-models.md`** — add a new section `## Baseline Deviation` noting:
- Seasonal baseline Redis key schema: `aiops:seasonal_baseline:{scope}:{metric_key}:{dow}:{hour}` (value: JSON float list, max 12 items)
- Time bucket index: `(dow, hour)` where `dow` = `datetime.weekday()` (Mon=0, Sun=6), `hour` = 0–23 (always UTC)
- `BaselineDeviationContext` and `BaselineDeviationStageOutput` models — forthcoming (Story 1.2)

### Cross-Story Dependencies

**This story is a foundation dependency for all other baseline stories:**
- Story 1.2 (SeasonalBaselineClient) imports `MAX_BUCKET_VALUES` from `constants.py` and calls `time_to_bucket()` for bucket key formation
- Story 1.3 (Cold-Start Backfill) imports `time_to_bucket()` for partitioning Prometheus time-series data
- Story 2.1 (MAD Engine) imports `MAD_CONSISTENCY_CONSTANT`, `MAD_THRESHOLD`, `MIN_BUCKET_SAMPLES` from `constants.py`
- Story 2.x (Stage) imports `MIN_CORRELATED_DEVIATIONS`

**Do not pre-implement anything from later stories.** No Redis I/O, no Pydantic models, no stage logic. This story is constants + one function.

### Project Structure Notes

- New package location: `src/aiops_triage_pipeline/baseline/` — follows exact naming from Architecture document (project-structure-boundaries.md)
- Test location: `tests/unit/baseline/` — mirrors source package structure per project-context.md testing rules
- No `pyproject.toml` changes needed — the new `baseline/` package is automatically included as part of the `aiops_triage_pipeline` package (src layout)
- No `__all__` export definitions needed — existing packages don't use them

### References

- Constants values and P2 rule: [Source: artifact/planning-artifacts/architecture/implementation-patterns-consistency-rules.md#P2]
- `time_to_bucket` canonical implementation and P3 rule: [Source: artifact/planning-artifacts/architecture/implementation-patterns-consistency-rules.md#P3]
- New file locations: [Source: artifact/planning-artifacts/architecture/project-structure-boundaries.md#New-Files-Directories]
- Stage ordering and hot-path determinism: [Source: artifact/planning-artifacts/architecture/core-architectural-decisions.md#D2]
- Documentation update requirements: [Source: artifact/planning-artifacts/architecture/core-architectural-decisions.md#Documentation-Impact]
- Acceptance criteria source: [Source: artifact/planning-artifacts/epics.md#Story-1.1]
- Python 3.13 typing style, frozen models, structlog: [Source: artifact/project-context.md#Critical-Implementation-Rules]
- Test framework (pytest, asyncio_mode=auto, 0 skips): [Source: artifact/project-context.md#Testing-Rules]
- Full regression command: [Source: artifact/project-context.md#Testing-Rules]

## Dev Agent Record

### Agent Model Used

claude-sonnet-4-6

### Debug Log References

None — implementation was straightforward with no unexpected issues.

### Completion Notes List

- Created `baseline/` package with 4 files: `__init__.py` (empty), `constants.py` (5 constants), `computation.py` (`time_to_bucket`), `models.py` (stub).
- `time_to_bucket` uses `.astimezone(timezone.utc)` + `.weekday()` + `.hour` — exact canonical pattern from architecture.
- Removed `@pytest.mark.xfail(strict=True)` decorators from both test files and moved top-level imports to module level (ruff I001 fix applied).
- 18 tests pass: 7 constants tests + 11 computation tests covering UTC, non-UTC, timezone day-boundary crossings, and return type validation.
- Pre-existing 4 failures in `tests/unit/integrations/test_llm.py` (openai library Python 3.13 incompatibility) confirmed unrelated to this story.
- All 3 documentation files updated per story spec.

### Senior Developer Review (AI)

**Reviewer:** claude-sonnet-4-6 — 2026-04-05

**Outcome:** APPROVED (with fixes applied)

**Findings fixed during review:**

1. **[MEDIUM] Missing SeasonalBaselineClient placeholder row in `docs/component-inventory.md`**
   Task 5.2 was marked [x] complete but the SeasonalBaselineClient placeholder row was not added to component-inventory.md. The Documentation Update Specifics section listed only two rows, creating an internal contradiction with the task description. Fixed by adding the SeasonalBaselineClient placeholder row to component-inventory.md (Story 1.2 placeholder).

2. **[MEDIUM] `time_to_bucket()` silently accepted naive datetimes — inconsistent with project patterns**
   `dt.astimezone(timezone.utc)` on a naive datetime converts via local system timezone, producing silent miscalculations. All other datetime-accepting functions in this codebase raise `ValueError` for naive datetimes (casefile.py, outbox, lifecycle, etc.). Fixed by adding `if dt.tzinfo is None: raise ValueError(...)` guard in `computation.py` and a corresponding test `test_time_to_bucket_raises_for_naive_datetime` in `test_computation.py`.

3. **[LOW] Unused `noqa: PLC0415` directive in `test_constants.py:61`**
   PLC0415 (pylint-style rule) is not in the ruff `select` list (`E,F,I,N,W`). The noqa comment suppressed a rule that was never active. Import-inside-function does not trigger any active ruff rule. Fixed by removing the noqa comment entirely.

4. **[LOW] Integer constants lacked type assertions in `test_constants.py`**
   `assert constant == 2` passes if the constant is `2.0` (float) due to Python's int/float equality. Three integer constants (`MIN_CORRELATED_DEVIATIONS`, `MIN_BUCKET_SAMPLES`, `MAX_BUCKET_VALUES`) had no `isinstance(..., int)` assertion. Fixed by adding `assert isinstance(constant, int)` to each integer constant test.

**Post-fix state:** 19 unit tests passing (was 18). Ruff clean. No regressions.

### Change Log

- 2026-04-05: Implemented Story 1.1 — baseline package scaffold with constants and time_to_bucket function. 18 unit tests added and passing.
- 2026-04-05: Code review — 4 findings (2 Medium, 2 Low) found and fixed. 1 test added. Story marked done.

### File List

- `src/aiops_triage_pipeline/baseline/__init__.py` (created)
- `src/aiops_triage_pipeline/baseline/constants.py` (created)
- `src/aiops_triage_pipeline/baseline/computation.py` (created — updated in review: added naive datetime guard)
- `src/aiops_triage_pipeline/baseline/models.py` (created)
- `tests/unit/baseline/__init__.py` (existed — pre-created)
- `tests/unit/baseline/test_constants.py` (updated — removed xfail decorators, moved imports to module level; updated in review: added isinstance type assertions, removed unused noqa)
- `tests/unit/baseline/test_computation.py` (updated — removed xfail decorators, moved imports to module level; updated in review: added naive datetime guard test)
- `docs/project-structure.md` (updated — added baseline/ entry)
- `docs/component-inventory.md` (updated — added Baseline Constants, Baseline Computation, and SeasonalBaselineClient placeholder rows)
- `docs/data-models.md` (updated — added Baseline Deviation section)
- `artifact/implementation-artifacts/sprint-status.yaml` (updated — status: done)
