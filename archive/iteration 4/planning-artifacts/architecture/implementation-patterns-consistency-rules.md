# Implementation Patterns & Consistency Rules

## Pattern Scope

The project already has 72 AI agent rules in `artifact/project-context.md` covering naming conventions, framework patterns, testing, quality, and workflow. The patterns below are **specific to the baseline deviation feature** — conflict points where agents implementing different stories could diverge if not specified.

## Conflict Points Identified

7 areas where AI agents could make conflicting implementation choices for the baseline deviation feature.

## P1: Scope Tuple Representation

**Rule:** Use `tuple[str, ...]` for scope identity in all baseline deviation code — consistent with the existing evidence stage pattern. No typed scope model, no joined strings, no frozen dataclasses.

**Example:**
```python
# Correct
scope: tuple[str, ...] = ("prod", "kafka-prod-east", "orders.completed")

# Wrong — do not introduce
@dataclass(frozen=True)
class BaselineScope:
    env: str
    cluster_id: str
    topic: str
```

## P2: Baseline Deviation Constants

**Rule:** All baseline deviation constants live in a single `baseline/constants.py` module. SCREAMING_SNAKE_CASE per Python convention. No inline magic numbers.

```python
# baseline/constants.py
MAD_CONSISTENCY_CONSTANT = 0.6745
MAD_THRESHOLD = 4.0
MIN_CORRELATED_DEVIATIONS = 2
MIN_BUCKET_SAMPLES = 3
MAX_BUCKET_VALUES = 12
```

**Anti-pattern:** Hardcoding `0.6745` or `4.0` inline in computation functions.

## P3: Time Bucket Derivation

**Rule:** A single pure function `time_to_bucket(dt: datetime) -> tuple[int, int]` is the sole source of truth for converting a datetime to a `(dow, hour)` bucket. Uses `datetime.weekday()` (Monday=0 through Sunday=6) on UTC-normalized time. Lives in the baseline module. Used by stage, backfill, and recomputation — no alternative implementations.

**Example:**
```python
def time_to_bucket(dt: datetime) -> tuple[int, int]:
    utc_dt = dt.astimezone(timezone.utc)
    return (utc_dt.weekday(), utc_dt.hour)
```

**Anti-pattern:** Calling `datetime.isoweekday()`, using local time, or deriving buckets inline without this function.

## P4: AnomalyFinding Extension Shape

**Rule:** Add a single optional field `baseline_context: BaselineDeviationContext | None = None` to the existing `AnomalyFinding` model. Do not add multiple optional fields directly to AnomalyFinding.

`BaselineDeviationContext` is a frozen Pydantic model:

```python
class BaselineDeviationContext(BaseModel, frozen=True):
    metric_key: str
    deviation_direction: Literal["HIGH", "LOW"]
    deviation_magnitude: float  # modified z-score
    baseline_value: float       # median of bucket
    current_value: float
    time_bucket: tuple[int, int]  # (dow, hour)
```

The correlated deviations list lives on the finding level (the finding's `findings` tuple contains one entry per correlated metric), not nested inside each context.

**Anti-pattern:** Adding `deviation_direction`, `deviation_magnitude`, `baseline_value`, `current_value` as top-level Optional fields on AnomalyFinding.

## P5: Stage Output Model

**Rule:** `BaselineDeviationStageOutput` follows the existing stage output pattern (frozen Pydantic model):

```python
class BaselineDeviationStageOutput(BaseModel, frozen=True):
    findings: tuple[AnomalyFinding, ...]
    scopes_evaluated: int
    deviations_detected: int
    deviations_suppressed_single_metric: int
    deviations_suppressed_dedup: int
    evaluation_time: datetime
```

No per-scope breakdown in the stage output. Per-scope detail belongs in OTLP counters and DEBUG-level structured logs.

## P6: Structured Log Event Naming

**Rule:** All baseline deviation structured log events use the prefix `baseline_deviation_`:

| Event Name | When Emitted |
|---|---|
| `baseline_deviation_stage_started` | Stage begins execution |
| `baseline_deviation_stage_completed` | Stage finishes (includes scopes_evaluated, findings count) |
| `baseline_deviation_finding_emitted` | Correlated finding passes all checks |
| `baseline_deviation_suppressed_single_metric` | Single-metric deviation suppressed (DEBUG level) |
| `baseline_deviation_suppressed_dedup` | Suppressed due to hand-coded detector overlap |
| `baseline_deviation_redis_unavailable` | Fail-open triggered on Redis error |
| `baseline_deviation_recompute_started` | Weekly recomputation background task begins |
| `baseline_deviation_recompute_completed` | Recomputation finishes (includes key count, duration) |
| `baseline_deviation_recompute_failed` | Recomputation error (includes exc_info) |
| `baseline_deviation_backfill_seeded` | Cold-start backfill completes (includes scope/metric/bucket counts) |

## P7: OTLP Instrument Naming

**Rule:** All baseline deviation OTLP instruments use the `aiops.baseline_deviation.` prefix, created via existing shared helpers.

**Counters** (via `create_counter`):
- `aiops.baseline_deviation.deviations_detected`
- `aiops.baseline_deviation.findings_emitted`
- `aiops.baseline_deviation.suppressed_single_metric`
- `aiops.baseline_deviation.suppressed_dedup`

**Histograms** (via `create_histogram`):
- `aiops.baseline_deviation.stage_duration_seconds`
- `aiops.baseline_deviation.mad_computation_seconds`

## Enforcement

**All AI agents implementing baseline deviation stories MUST:**
1. Import constants from `baseline/constants.py` — never hardcode threshold values
2. Use `time_to_bucket()` for all datetime-to-bucket conversions — never derive inline
3. Use the `baseline_deviation_` prefix for all structured log events
4. Use the `aiops.baseline_deviation.` prefix for all OTLP instruments
5. Follow existing project-context.md rules for all patterns not specified above
