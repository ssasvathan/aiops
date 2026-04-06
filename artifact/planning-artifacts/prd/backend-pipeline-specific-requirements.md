# Backend Pipeline Specific Requirements

## Project-Type Overview

aiOps is not a traditional API backend — it's an event-driven pipeline service with a single HTTP health endpoint. The "interfaces" are internal pipeline stage contracts, external integration adapters, and data schemas. The baseline deviation feature adds a new stage and extends existing contracts without changing the pipeline's external surface area.

## Technical Architecture Considerations

**Pipeline Stage Contract**

The baseline deviation stage has a well-defined input/output contract within the pipeline:

| Aspect | Detail |
|---|---|
| **Stage position** | After anomaly stage, before topology stage |
| **Input** | Anomaly stage output (hand-coded detector findings per scope), current Prometheus observations per scope/metric, Redis seasonal baseline buckets |
| **Output** | Zero or more `AnomalyFinding` objects with `anomaly_family="BASELINE_DEVIATION"` appended to the findings collection |
| **Side effects** | Redis write (update current time bucket with new observation) |
| **Determinism** | Fully deterministic — same inputs produce same outputs |

**Data Schemas**

| Schema | Format | Location |
|---|---|---|
| Seasonal baseline values | JSON-serialized float list per bucket | Redis: `aiops:seasonal_baseline:{scope}:{metric_key}:{dow}:{hour}` |
| AnomalyFinding extension | Pydantic frozen model with new `BASELINE_DEVIATION` literal | `contracts/` or `models/` — extends existing `anomaly_family` Literal type |
| Baseline deviation context | Additional fields on AnomalyFinding: `metric_key`, `deviation_direction`, `deviation_magnitude`, `baseline_value`, `current_value`, `correlated_deviations` | Same model |
| Threshold constants | Python module constants | Code-level, not YAML |

**Contract Versioning**

- `AnomalyFinding` adds `BASELINE_DEVIATION` to the `anomaly_family` Literal — this is an additive change, not a breaking change
- No frozen contract changes to `GateInputV1`, `ActionDecisionV1`, `CaseHeaderEventV1`, or `TriageExcerptV1` — baseline deviation findings flow through these unchanged
- `CaseFileTriageV1` already handles arbitrary finding families — no schema change needed
- Cold-path `DiagnosisReportV1` handles BASELINE_DEVIATION cases identically to existing families

**Authentication & Integration**

No new external integrations. Baseline deviation uses:
- Prometheus (existing client) — for cold-start backfill and weekly recomputation
- Redis (existing client) — for seasonal baseline storage
- All downstream integrations (Slack, PagerDuty, ServiceNow, Kafka) operate unchanged

## Implementation Considerations

**Redis Key Volume**
- 9 metrics × 500 scopes × 168 buckets = 756,000 keys
- Each key holds a JSON list of up to 12 float values (~100-200 bytes per key)
- Total estimated Redis memory: ~75-150 MB — well within typical Redis deployment capacity
- Key TTL: no expiry (baselines are persistent); weekly recomputation is the freshness mechanism

**Cycle Budget Impact**
- Per-scope MAD computation: O(n) where n ≤ 12 values per bucket — trivial
- Redis reads: `mget` for all metrics × current time bucket per scope — one round-trip per scope batch
- Correlation check: in-memory aggregation per scope — negligible
- Target: < 15% increase in p95 cycle duration (current p95: 263s, budget: ~39s for baseline stage)

**Cold-Start Backfill Extension**
- Existing backfill queries 30-day `query_range()` for all 9 metrics
- Extension: partition returned data into 168 time buckets and write to Redis seasonal baseline keys
- Backfill is blocking on startup — pipeline does not begin cycling until baselines are seeded
- New metrics added to contract YAML receive backfill on next startup
