# Architecture Patterns

## Part: core

- project_type_id: backend
- primary_pattern: Service/API-centric event-driven pipeline
- secondary_patterns:
  - Stage-based processing pipeline (`evidence -> peak -> baseline_deviation -> topology -> casefile -> outbox -> gating -> dispatch`)
  - Contract-first modeling (Pydantic frozen schemas for events, policy, and domain payloads)
  - Durable outbox pattern for reliable Kafka publication
  - Retry-state orchestration for ServiceNow linkage durability
  - Adapter-based integration boundaries (Kafka, Prometheus, Slack, PagerDuty, ServiceNow)

## Pattern Rationale

- `src/aiops_triage_pipeline/pipeline/stages/*` implements deterministic stage modules with explicit IO models.
- `src/aiops_triage_pipeline/rule_engine/*` isolates AG0-AG3 YAML check dispatch behind a frozen handler registry with startup fail-fast validation.
- `src/aiops_triage_pipeline/outbox/*` separates state transitions, persistence, and publisher loop concerns.
- `src/aiops_triage_pipeline/linkage/*` uses durable SQL retry state with source-state guarded transitions.
- `src/aiops_triage_pipeline/contracts/*` and `models/*` enforce immutable event/data contracts.
- `src/aiops_triage_pipeline/integrations/*` isolates external side effects behind mode-aware adapters (`OFF|LOG|MOCK|LIVE`).

## Baseline Deviation Stage Pattern

### Function Signature

```python
def collect_baseline_deviation_stage_output(
    *,
    evidence_output: EvidenceStageOutput,
    peak_output: PeakStageOutput,
    baseline_client: SeasonalBaselineClient,
    evaluation_time: datetime,
) -> BaselineDeviationStageOutput:
```

All four parameters are explicit keyword-only (`*`). No wall clock reads, no global state. Fully deterministic: same inputs always produce identical outputs.

### Parameter Contract

- `evidence_output`: carries `EvidenceRow` observations and hand-coded `AnomalyFinding` results from Stage 1.
- `peak_output`: Stage 2 peak classification (received but not consumed by MVP detection logic; architecturally mandated for future use).
- `baseline_client`: `SeasonalBaselineClient` for Redis baseline reads via `read_buckets_batch()`.
- `evaluation_time`: injected UTC-aware datetime; sole source of `(dow, hour)` bucket identity via `time_to_bucket()`.

### 3-Layer Evaluation Logic

1. **MAD computation** — For each scope and metric, read historical bucket values from Redis via `baseline_client.read_buckets_batch(scope, metric_keys, dow, hour)`, then call `compute_modified_z_score(historical_values, current_value)`. Metrics with sparse history (`< MIN_BUCKET_SAMPLES`) or zero-MAD are skipped.

2. **Correlation gate** — Only scopes with `>= MIN_CORRELATED_DEVIATIONS` (2) deviating metrics emit a finding. Single-metric deviations are suppressed with a `baseline_deviation_suppressed_single_metric` log event.

3. **Hand-coded dedup** — Scopes that already have a `CONSUMER_LAG`, `VOLUME_DROP`, or `THROUGHPUT_CONSTRAINED_PROXY` finding in `evidence_output.anomaly_result.findings` are skipped (exact scope tuple match, D6). Suppressed with `baseline_deviation_suppressed_dedup` log event.

### Finding Shape

Emitted findings have `anomaly_family="BASELINE_DEVIATION"`, `severity="LOW"`, `is_primary=False`. `reason_codes` contains one entry per deviating metric in format `"BASELINE_DEV:{metric_key}:{direction}"`. `baseline_context` (`BaselineDeviationContext`) is populated from the alphabetically first deviating metric. `finding_id` is deterministic: `"BASELINE_DEVIATION:{scope_key}"` where `scope_key = "|".join(scope)`.

### Fail-Open Pattern

`ConnectionError`, `OSError`, and `TimeoutError` from Redis reads propagate to the stage-level handler which returns an empty `BaselineDeviationStageOutput` (all counters = 0) and emits `baseline_deviation_redis_unavailable`. Per-scope operational errors (`RuntimeError`, etc.) are caught individually and logged at WARNING, allowing remaining scopes to be processed.

## Architectural Style Assignment

- Assigned style: **Layered backend with event-pipeline core and durable side-effect boundaries**.
- Why: orchestration and business logic are centralized in pipeline stages, while persistence/integration effects are isolated through repositories and adapters.
