# Story 2.2: BASELINE_DEVIATION Finding Model

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a platform engineer,
I want a BASELINE_DEVIATION finding model that carries deviation context through the pipeline,
so that downstream stages can process baseline deviations identically to existing finding types with full replay context.

## Acceptance Criteria

1. **Given** the `baseline/models.py` module
   **When** `BaselineDeviationContext` is defined
   **Then** it is a frozen Pydantic model (`BaseModel, frozen=True`) with fields: `metric_key (str)`, `deviation_direction (Literal["HIGH", "LOW"])`, `deviation_magnitude (float)`, `baseline_value (float)`, `current_value (float)`, `time_bucket (tuple[int, int])`
   **And** follows the frozen=True Pydantic model pattern (P4)

2. **Given** the `baseline/models.py` module
   **When** `BaselineDeviationStageOutput` is defined
   **Then** it is a frozen Pydantic model with fields: `findings (tuple[AnomalyFinding, ...])`, `scopes_evaluated (int)`, `deviations_detected (int)`, `deviations_suppressed_single_metric (int)`, `deviations_suppressed_dedup (int)`, `evaluation_time (datetime)`
   **And** follows the existing stage output pattern (P5)

3. **Given** the `models/anomaly.py` module
   **When** the `AnomalyFinding` model is extended
   **Then** it has a new optional field: `baseline_context: BaselineDeviationContext | None = None`
   **And** the `anomaly_family` Literal type includes `"BASELINE_DEVIATION"` alongside the existing three families
   **And** this is an additive-only change following Procedure A from `docs/schema-evolution-strategy.md`

4. **Given** a `BASELINE_DEVIATION` `AnomalyFinding` is constructed
   **When** `severity`, `is_primary`, and `proposed_action` values are set
   **Then** the story documentation specifies: severity=LOW, is_primary=False, and `proposed_action=NOTIFY` is enforced at the source (FR16, FR17)
   **And** every emitted finding includes sufficient context for offline replay: `metric_key`, `deviation_direction`, `deviation_magnitude`, `baseline_value`, `current_value`, correlated deviations list, `time_bucket` (NFR-A2)

5. **Given** existing `AnomalyFinding` instances for other anomaly families (CONSUMER_LAG, VOLUME_DROP, THROUGHPUT_CONSTRAINED_PROXY)
   **When** `baseline_context` is not provided
   **Then** it defaults to `None` and no existing functionality is affected
   **And** all existing unit tests continue to pass without modification

6. **Given** unit tests in `tests/unit/baseline/test_models.py`
   **When** tests are executed
   **Then** frozen model immutability is verified for both `BaselineDeviationContext` and `BaselineDeviationStageOutput`
   **And** `model_dump()` / `model_validate()` serialization round-trip is verified for both models
   **And** field validation (e.g., invalid `deviation_direction`) is verified
   **And** `AnomalyFinding` with `baseline_context` populated and with `baseline_context=None` are both tested
   **And** `AnomalyFinding` backward compatibility — existing families construct without `baseline_context` — is verified

7. **Given** documentation files `docs/data-models.md` and `docs/contracts.md`
   **When** story is complete
   **Then** `docs/data-models.md` is updated with `BaselineDeviationContext` and `BaselineDeviationStageOutput` model definitions
   **And** `docs/contracts.md` is updated with the additive `BASELINE_DEVIATION` literal on `anomaly_family`

## Tasks / Subtasks

- [x] Task 1: Implement `BaselineDeviationContext` and `BaselineDeviationStageOutput` in `baseline/models.py` (AC: 1, 2)
  - [x] 1.1 Open `src/aiops_triage_pipeline/baseline/models.py` (replace placeholder stub — the current file is a placeholder comment only)
  - [x] 1.2 Add imports: `from datetime import datetime`, `from typing import Literal`, `from pydantic import BaseModel`; import `AnomalyFinding` from `aiops_triage_pipeline.models.anomaly` (use TYPE_CHECKING guard if needed to avoid circular import)
  - [x] 1.3 Define `BaselineDeviationContext` as `BaseModel, frozen=True` with exact fields per AC1 and the canonical sketch in Dev Notes
  - [x] 1.4 Define `BaselineDeviationStageOutput` as `BaseModel, frozen=True` with exact fields per AC2 and canonical sketch in Dev Notes
  - [x] 1.5 Run `uv run ruff check src/aiops_triage_pipeline/baseline/models.py` — confirm clean
  - [x] 1.6 Run `uv run python -c "from aiops_triage_pipeline.baseline.models import BaselineDeviationContext, BaselineDeviationStageOutput; print('OK')"` — confirm importable without circular import errors

- [x] Task 2: Extend `AnomalyFinding` in `models/anomaly.py` with `BASELINE_DEVIATION` and `baseline_context` field (AC: 3, 4, 5)
  - [x] 2.1 Open `src/aiops_triage_pipeline/models/anomaly.py`
  - [x] 2.2 Extend the `AnomalyFamily` Literal type: change `Literal["CONSUMER_LAG", "VOLUME_DROP", "THROUGHPUT_CONSTRAINED_PROXY"]` to include `"BASELINE_DEVIATION"`
  - [x] 2.3 Add `from __future__ import annotations` at the top if not present (to handle forward-reference to `BaselineDeviationContext`)
  - [x] 2.4 Add `TYPE_CHECKING` import block at the top: `from typing import TYPE_CHECKING` and `if TYPE_CHECKING: from aiops_triage_pipeline.baseline.models import BaselineDeviationContext`
  - [x] 2.5 Add the optional field to `AnomalyFinding`: `baseline_context: "BaselineDeviationContext | None" = None`
  - [x] 2.6 Verify existing `model_validator` `_validate_and_freeze_allowed_non_present_statuses` remains untouched
  - [x] 2.7 Verify existing `field_serializer` `_serialize_allowed_non_present_statuses` remains untouched
  - [x] 2.8 Run `uv run ruff check src/aiops_triage_pipeline/models/anomaly.py` — confirm clean
  - [x] 2.9 Run existing anomaly tests: `uv run pytest tests/unit/ -k "anomaly" -v` — confirm 0 regressions

- [x] Task 3: Create unit tests in `tests/unit/baseline/test_models.py` (AC: 6)
  - [x] 3.1 Create new file `tests/unit/baseline/test_models.py` (does not yet exist — this is a NEW file)
  - [x] 3.2 Add all imports at module level (no imports inside test functions — retro learning L4)
  - [x] 3.3 Implement `BaselineDeviationContext` tests:
    - `test_baseline_deviation_context_fields` — instantiate with valid values, assert all fields
    - `test_baseline_deviation_context_is_frozen` — verify `AttributeError` on attempted mutation
    - `test_baseline_deviation_context_serialization_round_trip` — `model_dump()` → `model_validate()` → equal to original
    - `test_baseline_deviation_context_invalid_direction` — `"MEDIUM"` raises `ValidationError`
    - `test_baseline_deviation_context_time_bucket_is_tuple` — `time_bucket` field is a `tuple[int, int]`
  - [x] 3.4 Implement `BaselineDeviationStageOutput` tests:
    - `test_baseline_deviation_stage_output_fields` — instantiate with valid values, assert all fields
    - `test_baseline_deviation_stage_output_is_frozen` — verify `AttributeError` on attempted mutation
    - `test_baseline_deviation_stage_output_serialization_round_trip` — `model_dump()` → `model_validate()` → equal to original
    - `test_baseline_deviation_stage_output_empty_findings` — zero findings, valid construction
  - [x] 3.5 Implement `AnomalyFinding` extension tests:
    - `test_anomaly_finding_baseline_context_defaults_none` — existing families construct without `baseline_context`, field is `None`
    - `test_anomaly_finding_with_baseline_context` — construct `AnomalyFinding` with `anomaly_family="BASELINE_DEVIATION"` and `baseline_context` populated
    - `test_anomaly_finding_baseline_deviation_family_accepted` — `"BASELINE_DEVIATION"` is a valid `anomaly_family` literal
    - `test_anomaly_finding_existing_families_unchanged` — each of CONSUMER_LAG, VOLUME_DROP, THROUGHPUT_CONSTRAINED_PROXY still construct normally
  - [x] 3.6 Run `uv run pytest tests/unit/baseline/test_models.py -v` — confirm all tests pass, 0 skipped
  - [x] 3.7 Run `uv run ruff check tests/unit/baseline/test_models.py` — confirm clean

- [x] Task 4: Run full regression suite (AC: 5, 6)
  - [x] 4.1 Run `uv run pytest tests/unit/ -q` — confirm 0 regressions against prior test count (1,240 passing from Story 2.1)
  - [x] 4.2 Confirm 0 skipped tests
  - [x] 4.3 Note: pre-existing 4 failures in `tests/unit/integrations/test_llm.py` (openai/Python 3.13 incompatibility) are NOT regressions from this story

- [x] Task 5: Update documentation (AC: 7)
  - [x] 5.1 Update `docs/data-models.md` — add section documenting `BaselineDeviationContext` and `BaselineDeviationStageOutput` (location hint: near the existing "forthcoming (Story 2.2)" note on line 74)
  - [x] 5.2 Update `docs/contracts.md` — add note documenting the additive `BASELINE_DEVIATION` literal on `AnomalyFinding.anomaly_family`

## Dev Notes

### What This Story Delivers

Story 2.2 implements the **model layer** for the baseline deviation feature — three changes across two files:

1. **`baseline/models.py`** (NEW content — replaces placeholder stub): `BaselineDeviationContext` + `BaselineDeviationStageOutput`
2. **`models/anomaly.py`** (MODIFIED — additive only): `AnomalyFinding.anomaly_family` gains `"BASELINE_DEVIATION"` literal; `AnomalyFinding` gains `baseline_context` field
3. **`tests/unit/baseline/test_models.py`** (NEW file): unit tests for all new models

**Files touched:**
- `src/aiops_triage_pipeline/baseline/models.py` — implement full content (was placeholder stub)
- `src/aiops_triage_pipeline/models/anomaly.py` — additive extension only
- `tests/unit/baseline/test_models.py` — NEW file (does not yet exist)
- `docs/data-models.md` — add model documentation
- `docs/contracts.md` — add BASELINE_DEVIATION literal note

**Files NOT touched in this story:**
- `baseline/computation.py` — complete from Story 2.1; do NOT modify
- `baseline/client.py` — complete from Epic 1; do NOT modify
- `baseline/constants.py` — complete from Epic 1; do NOT modify
- `pipeline/stages/baseline_deviation.py` — stage logic is Story 2.3
- `pipeline/scheduler.py` — scheduler wiring is Story 2.4
- Any existing test files — add new files, never modify completed story tests

### Critical: `AnomalyFinding` is in `models/anomaly.py`, NOT `contracts/`

The file to modify is `src/aiops_triage_pipeline/models/anomaly.py`. There is also a `contracts/` folder — do NOT modify anything in `contracts/`. The `Finding` class in `contracts/gate_input.py` is a different model (gate input contract); do NOT confuse it with `AnomalyFinding`.

Current `AnomalyFamily` in `models/anomaly.py` (line 11):
```python
AnomalyFamily = Literal["CONSUMER_LAG", "VOLUME_DROP", "THROUGHPUT_CONSTRAINED_PROXY"]
```

After this story:
```python
AnomalyFamily = Literal["CONSUMER_LAG", "VOLUME_DROP", "THROUGHPUT_CONSTRAINED_PROXY", "BASELINE_DEVIATION"]
```

### Critical: `GateInputV1.anomaly_family` in `contracts/gate_input.py` — DO NOT MODIFY

`contracts/gate_input.py` has its own `anomaly_family` Literal on `GateInputV1` (line 95). The architecture specifies FR18-FR21 (topology, gating, casefile, dispatch passthrough) require ZERO modifications to existing stages. The `GateInputV1` is the gate contract — do not add `BASELINE_DEVIATION` there in this story. Story 2.4 handles pipeline integration; this story is models only.

### Critical: Circular Import Resolution for `baseline/models.py` → `models/anomaly.py`

`BaselineDeviationStageOutput` holds `findings: tuple[AnomalyFinding, ...]`, which requires importing `AnomalyFinding` from `models/anomaly.py`. Meanwhile, `models/anomaly.py` needs to reference `BaselineDeviationContext` for the `baseline_context` field.

**Chosen pattern (TYPE_CHECKING guard in `models/anomaly.py`):**

```python
# models/anomaly.py
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from aiops_triage_pipeline.baseline.models import BaselineDeviationContext
```

Then declare the field with a string annotation:
```python
baseline_context: "BaselineDeviationContext | None" = None
```

`baseline/models.py` imports `AnomalyFinding` normally (one-directional import at runtime):
```python
from aiops_triage_pipeline.models.anomaly import AnomalyFinding
```

This pattern avoids circular imports at runtime while preserving type checking. Verify importability with `uv run python -c "..."` after implementation (Task 1.6).

**Precedent:** The Epic 1 retro noted a deferred import in `client.py` for a similar circular dependency. The TYPE_CHECKING pattern is cleaner for models — use it here.

### Critical: Canonical Model Implementations (P4, P5)

**`BaselineDeviationContext`** (P4 — frozen Pydantic model, baseline-specific):

```python
from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class BaselineDeviationContext(BaseModel, frozen=True):
    """Per-metric deviation context carried in BASELINE_DEVIATION findings.

    Provides full offline replay context per NFR-A2: every emitted finding
    includes metric_key, deviation_direction, deviation_magnitude, baseline_value,
    current_value, and time_bucket.
    """
    metric_key: str
    deviation_direction: Literal["HIGH", "LOW"]
    deviation_magnitude: float    # Modified z-score (signed; negative = LOW)
    baseline_value: float         # Median of the historical bucket
    current_value: float          # The observed value being evaluated
    time_bucket: tuple[int, int]  # (dow, hour) bucket — output of time_to_bucket()
```

**`BaselineDeviationStageOutput`** (P5 — frozen Pydantic stage output pattern):

```python
class BaselineDeviationStageOutput(BaseModel, frozen=True):
    """Output of the baseline deviation stage for one pipeline cycle.

    Follows the existing stage output pattern (PeakStageOutput, etc.): frozen
    Pydantic model with findings tuple and summary counters. Per-scope breakdowns
    belong in OTLP counters and DEBUG-level structured logs, not in this model.
    """
    findings: tuple[AnomalyFinding, ...]
    scopes_evaluated: int
    deviations_detected: int
    deviations_suppressed_single_metric: int
    deviations_suppressed_dedup: int
    evaluation_time: datetime
```

**`AnomalyFinding` extension** (additive-only per Procedure A):

```python
# Change line 11 in models/anomaly.py:
AnomalyFamily = Literal["CONSUMER_LAG", "VOLUME_DROP", "THROUGHPUT_CONSTRAINED_PROXY", "BASELINE_DEVIATION"]

# Add field to AnomalyFinding class (after is_primary):
baseline_context: "BaselineDeviationContext | None" = None
```

### Critical: Correlated Deviations Architecture (P4 clarification)

The architecture (P4) specifies: "The correlated deviations list lives on the finding level (the finding's `findings` tuple contains one entry per correlated metric), not nested inside each context."

This means: for a scope where 3 metrics deviate, Story 2.3 will produce **one `AnomalyFinding`** with `anomaly_family="BASELINE_DEVIATION"` whose `baseline_context` carries context for one representative metric, while the `reason_codes` tuple carries references to all correlated deviating metrics.

For this story (2.2), implement the model exactly as specified above — `BaselineDeviationContext` holds **one metric's context**. Story 2.3 will decide how many findings to emit per scope.

### Critical: BASELINE_DEVIATION Finding Attributes (FR16, FR17, NFR-A2)

When a BASELINE_DEVIATION finding is constructed (Story 2.3), it must have:
- `severity="LOW"` (FR16)
- `is_primary=False` (FR16)
- `proposed_action=NOTIFY` enforced at source (FR17) — NOTE: `AnomalyFinding` does NOT currently have a `proposed_action` field; this is set via the gate input assembly in `GateInputV1`. Do NOT add `proposed_action` to `AnomalyFinding`. The "set at source" concept means the BASELINE_DEVIATION findings will always generate `proposed_action=NOTIFY` when the gate input is assembled in Story 2.4.

Document this in the test for AC4 — the story documents intent, the implementation is in Story 2.3/2.4.

### Critical: Additive Change — Procedure A Verification

Per `docs/schema-evolution-strategy.md` Procedure A:
- [x] New field has a default value: `baseline_context: ... = None` ✓ (backward compatible)
- [x] Consumer code handles `None`: downstream gate input assembly in Story 2.4 will check `baseline_context is not None`
- [x] Existing tests still pass without modification ← verify in Task 4
- [x] New tests cover the new field when present and when absent ← Task 3.5

Do NOT add `BASELINE_DEVIATION` to `contracts/gate_input.py`'s `GateInputV1.anomaly_family` in this story. That change is part of Story 2.4 pipeline integration.

### Critical: `from __future__ import annotations`

Adding `from __future__ import annotations` to `models/anomaly.py` makes ALL annotations strings (lazy evaluation). This is safe for Pydantic v2 which handles string annotations correctly via `model_rebuild()`. However, this may affect existing tests if they rely on `AnomalyFinding.__annotations__` directly. Verify with `uv run pytest tests/unit/ -k "anomaly" -v` immediately after adding.

**Alternative if `from __future__ import annotations` causes issues:** Use `Optional` with explicit string: `baseline_context: Optional["BaselineDeviationContext"] = None` without the future import, combined with `model_rebuild()` call at module level after `BaselineDeviationContext` is imported at runtime.

### Pattern: How Other Stage Outputs Are Structured (P5 reference)

Look at `src/aiops_triage_pipeline/models/peak.py` → `PeakStageOutput(BaseModel, frozen=True)` for the exact stage output pattern. `BaselineDeviationStageOutput` follows the same frozen Pydantic pattern but is simpler — no nested Mappings requiring `MappingProxyType` freeze, just a `tuple` for findings and `int`/`datetime` scalars.

### Testing Notes

**`test_models.py` is a NEW file** — it does not exist yet. Create it fresh at `tests/unit/baseline/test_models.py`.

**Frozen immutability test pattern** (from Epic 1 retro L2 and existing `test_client.py` patterns):

```python
import pytest
from pydantic import ValidationError

from aiops_triage_pipeline.baseline.models import BaselineDeviationContext, BaselineDeviationStageOutput
from aiops_triage_pipeline.models.anomaly import AnomalyFinding


def test_baseline_deviation_context_is_frozen() -> None:
    """AC1: BaselineDeviationContext is immutable (frozen=True)."""
    ctx = BaselineDeviationContext(
        metric_key="consumer_group_lag",
        deviation_direction="HIGH",
        deviation_magnitude=5.2,
        baseline_value=100.0,
        current_value=180.0,
        time_bucket=(2, 14),
    )
    with pytest.raises(Exception):  # ValidationError or AttributeError
        ctx.metric_key = "modified"  # type: ignore[misc]
```

**Serialization round-trip pattern:**

```python
def test_baseline_deviation_context_serialization_round_trip() -> None:
    """AC1: model_dump → model_validate round-trip preserves all fields."""
    ctx = BaselineDeviationContext(
        metric_key="topic_messages_in_per_sec",
        deviation_direction="LOW",
        deviation_magnitude=-6.1,
        baseline_value=500.0,
        current_value=10.0,
        time_bucket=(1, 9),
    )
    dumped = ctx.model_dump()
    restored = BaselineDeviationContext.model_validate(dumped)
    assert restored == ctx
```

**Invalid direction validation test:**

```python
def test_baseline_deviation_context_invalid_direction() -> None:
    """AC1: Non-Literal direction raises ValidationError."""
    with pytest.raises(ValidationError):
        BaselineDeviationContext(
            metric_key="consumer_group_lag",
            deviation_direction="MEDIUM",  # invalid
            deviation_magnitude=5.0,
            baseline_value=100.0,
            current_value=200.0,
            time_bucket=(0, 10),
        )
```

**Do NOT use `@pytest.mark.xfail` or `@pytest.mark.skip`** (0-skipped-tests project rule).

**Module-level imports only** — no imports inside test functions (retro L4, ruff I001).

### Project Structure Context

```
src/aiops_triage_pipeline/
├── baseline/
│   ├── __init__.py             ← EXISTS (empty, do not touch)
│   ├── constants.py            ← EXISTS (5 constants, do not touch)
│   ├── computation.py          ← EXISTS (MADResult + compute_modified_z_score, do not touch)
│   ├── client.py               ← EXISTS (SeasonalBaselineClient, do not touch)
│   └── models.py               ← MODIFY — replace placeholder stub with full implementation
├── models/
│   └── anomaly.py              ← MODIFY — additive extension only
└── ...

tests/unit/baseline/
├── __init__.py                 ← EXISTS
├── test_constants.py           ← EXISTS (do not touch)
├── test_computation.py         ← EXISTS (do not touch)
├── test_client.py              ← EXISTS (do not touch)
├── test_bulk_recompute.py      ← EXISTS (do not touch)
└── test_models.py              ← NEW FILE — create fresh

docs/
├── data-models.md              ← UPDATE — add BaselineDeviationContext and BaselineDeviationStageOutput
└── contracts.md                ← UPDATE — add BASELINE_DEVIATION literal note
```

### Cross-Story Dependencies

**This story depends on:**
- Story 2.1 (DONE): `MADResult` frozen dataclass fields (`is_deviation`, `deviation_direction`, `deviation_magnitude`, `baseline_value`, `current_value`) map 1:1 to `BaselineDeviationContext` fields — this is intentional architecture

**This story is a dependency for:**
- Story 2.3 (Baseline Deviation Stage): uses `BaselineDeviationContext`, `BaselineDeviationStageOutput`, and `AnomalyFinding(anomaly_family="BASELINE_DEVIATION")`
- Story 2.4 (Pipeline Integration): relies on the `BASELINE_DEVIATION` literal being present in `AnomalyFamily`

### Previous Story Learnings Applied (Epic 1 Retro + Story 2.1)

1. **[L1] Canonical sketches prevent architectural rework** — exact model implementations are pre-specified in Dev Notes above. First-pass implementation should require only quality polish.

2. **[L4 retro] Module-level imports only** — all imports in `test_models.py` must be at module level, not inside test functions (ruff I001).

3. **[L2 retro] Test `is` for boolean, not truthiness** — test `result.is_deviation is True` not `assert result.is_deviation`. For model fields, test exact types: `assert isinstance(ctx.time_bucket, tuple)`.

4. **[Code review finding #2 from 2.1] No invalid `noqa` comments** — only add `noqa` for rules in the active ruff select set `E,F,I,N,W`. Do not add `noqa: ARG002` or `noqa: BLE001`.

5. **[Story 2.1 Dev Notes] Frozen Pydantic vs frozen dataclass** — `BaselineDeviationContext` and `BaselineDeviationStageOutput` are Pydantic models (`BaseModel, frozen=True`) because they serialize to Redis/JSON. `MADResult` is a plain `dataclass(frozen=True)` because it is internal computation. Do NOT use `@dataclass` for the models in this story.

6. **[Epic 1 retro File List discipline]** — File List section in Dev Agent Record must be complete. All created/modified files must be listed at the end of the story.

7. **[Story 2.1 retro: pre-existing test failures]** — 4 failures in `tests/unit/integrations/test_llm.py` are pre-existing (openai/Python 3.13 incompatibility). Do NOT treat as regressions.

### References

- P4 (AnomalyFinding extension shape — `baseline_context` field, `BaselineDeviationContext`): [Source: artifact/planning-artifacts/architecture/implementation-patterns-consistency-rules.md#P4]
- P5 (Stage output frozen Pydantic pattern — `BaselineDeviationStageOutput`): [Source: artifact/planning-artifacts/architecture/implementation-patterns-consistency-rules.md#P5]
- FR16 (BASELINE_DEVIATION family, severity=LOW, is_primary=False): [Source: artifact/planning-artifacts/epics.md#Functional-Requirements]
- FR17 (proposed_action=NOTIFY at source): [Source: artifact/planning-artifacts/epics.md#Functional-Requirements]
- NFR-A2 (full replay context — all deviation fields): [Source: artifact/planning-artifacts/epics.md#NonFunctional-Requirements]
- Procedure A (additive-only schema evolution): [Source: docs/schema-evolution-strategy.md#Procedure-A]
- Story 2.2 acceptance criteria source: [Source: artifact/planning-artifacts/epics.md#Story-2.2]
- File locations (`baseline/models.py`, `models/anomaly.py`): [Source: artifact/planning-artifacts/architecture/project-structure-boundaries.md#New-Files-Directories]
- Contract boundary (no changes to `contracts/` folder): [Source: artifact/planning-artifacts/architecture/project-structure-boundaries.md#Architectural-Boundaries]
- Stage output pattern reference: [Source: src/aiops_triage_pipeline/models/peak.py — PeakStageOutput]
- `AnomalyFinding` current definition: [Source: src/aiops_triage_pipeline/models/anomaly.py]
- `AnomalyFamily` current Literal (line 11): [Source: src/aiops_triage_pipeline/models/anomaly.py]
- Testing rules (0 skips, asyncio_mode=auto, pytest-asyncio 1.3.0): [Source: artifact/project-context.md#Testing-Rules]
- Ruff config (line-length 100, py313, E/F/I/N/W): [Source: artifact/project-context.md#Code-Quality-Rules]
- `from __future__ import annotations` Pydantic v2 compatibility: [Source: Pydantic v2 docs — string annotations supported with model_rebuild()]
- Epic 1 retrospective learnings: [Source: artifact/implementation-artifacts/epic-1-retro-2026-04-05.md]
- Story 2.1 Dev Agent Record (code review findings, lessons): [Source: artifact/implementation-artifacts/2-1-mad-computation-engine.md#Dev-Agent-Record]

## Dev Agent Record

### Agent Model Used

claude-sonnet-4-6

### Debug Log References

- Circular import resolution: Used `from __future__ import annotations` + `TYPE_CHECKING` guard in `models/anomaly.py`, with `AnomalyFinding.model_rebuild()` called at end of `baseline/models.py` after `BaselineDeviationContext` is defined. This resolved the Pydantic v2 "not fully defined" error while keeping the one-directional runtime import from `baseline/models.py` → `models/anomaly.py`.

### Completion Notes List

- Implemented `BaselineDeviationContext` (frozen Pydantic, 6 fields) and `BaselineDeviationStageOutput` (frozen Pydantic, 6 fields) in `baseline/models.py`.
- Extended `AnomalyFinding` in `models/anomaly.py` with `BASELINE_DEVIATION` literal in `AnomalyFamily` and optional `baseline_context` field (additive-only per Procedure A).
- ATDD tests pre-existed in `tests/unit/baseline/test_models.py` (19 tests). All 19 pass after implementation.
- Full regression run: 1259 passed, 0 skipped (1240 pre-existing + 19 new).
- Ruff clean on all modified source files.
- Documentation updated in `docs/data-models.md` and `docs/contracts.md`.

### File List

- `src/aiops_triage_pipeline/baseline/models.py` — replaced placeholder stub with full implementation
- `src/aiops_triage_pipeline/models/anomaly.py` — additive extension: `BASELINE_DEVIATION` literal + `baseline_context` field
- `tests/unit/baseline/test_models.py` — NEW file: 19 unit tests covering AC1–AC6
- `docs/data-models.md` — added `BaselineDeviationContext` and `BaselineDeviationStageOutput` model documentation
- `docs/contracts.md` — added `AnomalyFinding` domain model section documenting `BASELINE_DEVIATION` family
- `artifact/test-artifacts/atdd-checklist-2-2-baseline-deviation-finding-model.md` — ATDD checklist generated alongside implementation

### Change Log

- 2026-04-05: Implemented Story 2.2 — `BaselineDeviationContext`, `BaselineDeviationStageOutput`, and `AnomalyFinding` extension with `BASELINE_DEVIATION` family and `baseline_context` field. 19 new tests added, 1259 total passing.
- 2026-04-05: Code review (adversarial) — 8 findings (0 Critical, 2 High, 3 Medium, 3 Low), all fixed. Added 2 new serialization round-trip tests (AnomalyFinding+baseline_context, BaselineDeviationStageOutput with populated findings). Removed redundant `BaselineDeviationStageOutput.model_rebuild()` call. Added doc note on intentional omission of cross-field validator. Fixed missing blank line in docs/data-models.md. Fixed File List missing test_models.py and ATDD checklist. 1261 total passing, 0 skipped.
