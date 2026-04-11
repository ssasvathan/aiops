# Project Structure & Boundaries

## Existing Structure (Unchanged)

The existing project structure remains intact. See `docs/project-structure.md` for the full tree. The baseline deviation feature adds files within the established layout conventions.

## New Files & Directories

```
src/aiops_triage_pipeline/
├── baseline/                              # NEW PACKAGE — baseline deviation domain
│   ├── __init__.py
│   ├── constants.py                       # P2: MAD_THRESHOLD, MIN_CORRELATED_DEVIATIONS, etc.
│   ├── client.py                          # D3: SeasonalBaselineClient (Redis I/O boundary)
│   ├── computation.py                     # MAD computation, time_to_bucket() (P3)
│   └── models.py                          # P4: BaselineDeviationContext
│                                          # P5: BaselineDeviationStageOutput
├── pipeline/
│   ├── stages/
│   │   ├── baseline_deviation.py          # D2: collect_baseline_deviation_stage_output()
│   │   └── ... (existing stages unchanged)
│   └── scheduler.py                       # MODIFIED: add run_baseline_deviation_stage_cycle()
│                                          #           add weekly recompute timer (D4)
│                                          #           extend backfill to seed baselines (D5)
├── models/
│   └── anomaly_finding.py                 # MODIFIED: add baseline_context field (P4)
└── ... (all other packages unchanged)

tests/
├── unit/
│   ├── baseline/                          # NEW — mirrors src/baseline/
│   │   ├── __init__.py
│   │   ├── test_constants.py              # Validate constant values
│   │   ├── test_client.py                 # SeasonalBaselineClient with mock Redis
│   │   ├── test_computation.py            # MAD math, time_to_bucket, edge cases
│   │   └── test_models.py                 # Frozen model validation, serialization
│   └── pipeline/
│       └── stages/
│           └── test_baseline_deviation.py # NEW — stage logic with mock client
└── integration/
    └── test_baseline_deviation.py         # NEW — Redis-backed baseline read/write/seed
```

## FR-to-File Mapping

| FR Category | FRs | Primary File(s) |
|---|---|---|
| Seasonal Baseline Management | FR1-FR6 | `baseline/client.py`, `baseline/constants.py` |
| Anomaly Detection (MAD) | FR7-FR10 | `baseline/computation.py` |
| Correlation & Noise Suppression | FR11-FR15 | `pipeline/stages/baseline_deviation.py` |
| Finding & Pipeline Integration | FR16-FR21 | `models/anomaly_finding.py`, `baseline/models.py` |
| Metric Discovery & Onboarding | FR22-FR24 | `baseline/client.py`, `pipeline/scheduler.py` |
| LLM Diagnosis | FR25-FR28 | No new files — existing cold-path handles new anomaly_family |
| Observability & Operations | FR29-FR32 | `pipeline/stages/baseline_deviation.py` (instruments created inline) |

## Architectural Boundaries

**Data Access Boundary:**
`baseline/client.py` (SeasonalBaselineClient) is the sole interface to Redis for baseline data. The stage function and scheduler never construct Redis keys or call Redis directly for baseline operations.

**Computation Boundary:**
`baseline/computation.py` contains pure functions (MAD calculation, time bucket derivation). No I/O, no side effects. All inputs passed as parameters.

**Stage Boundary:**
`pipeline/stages/baseline_deviation.py` is the composition point — it receives the client and evidence output, calls computation functions, applies correlation and dedup logic, and returns the stage output. Consistent with all other stage modules.

**Contract Boundary:**
`models/anomaly_finding.py` is modified (additive field). `baseline/models.py` defines new models that are baseline-specific. No existing contract files in `contracts/` are modified — BASELINE_DEVIATION flows through existing contracts unchanged.

## Integration Points

**Internal (stage-to-stage):**
- Evidence stage output → baseline deviation stage (observations + hand-coded findings for dedup)
- Peak stage output → baseline deviation stage (available but not directly consumed in MVP)
- Baseline deviation stage output → topology stage (findings enriched with routing context)

**Internal (scheduler orchestration):**
- `scheduler.py` constructs `SeasonalBaselineClient` at startup
- `scheduler.py` calls `run_baseline_deviation_stage_cycle()` between peak and topology
- `scheduler.py` manages weekly recompute timer and spawns background coroutine (D4)
- `scheduler.py` extends existing backfill to call `SeasonalBaselineClient.seed_from_history()` (D5)

**External (no new integrations):**
- Prometheus (existing client, used by backfill extension and recomputation)
- Redis (existing connection, new keyspace via SeasonalBaselineClient)
- All downstream integrations (Slack, PagerDuty, Kafka, S3) operate unchanged
