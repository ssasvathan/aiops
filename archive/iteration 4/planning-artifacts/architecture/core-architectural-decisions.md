# Core Architectural Decisions

## Decision Priority Analysis

**Critical Decisions (Block Implementation):**
All 6 decisions below are critical — they define the data model, stage interface, and integration patterns that all implementation work depends on.

**Deferred Decisions (Post-MVP):**
- Metric personality auto-classification (Phase 2 — MAD works universally for MVP)
- YAML-configurable thresholds (Phase 2 — code constants sufficient for MVP)
- Multi-signal baseline extension (Phase 3 — Redis key schema designed to not preclude it)

## Data Architecture

**D1: Redis Key Schema — Flat String Keys**

| Aspect | Decision |
|---|---|
| Pattern | `aiops:seasonal_baseline:{scope}:{metric_key}:{dow}:{hour}` |
| Value format | JSON-serialized list of up to 12 floats |
| Key count | ~756K (9 metrics × 500 scopes × 168 buckets) |
| Read pattern | `mget` batched by scope (9 keys per scope per cycle) |
| Write pattern | Individual `SET` per key for incremental updates |
| Rationale | Consistent with existing flat key patterns (dedupe, cache, coordination locks). Simple, well-understood, predictable `mget` performance |
| Affects | SeasonalBaselineClient, backfill seeding, weekly recomputation |

**D3: Baseline Data Abstraction — Dedicated `SeasonalBaselineClient` Class**

| Aspect | Decision |
|---|---|
| Pattern | Client class encapsulating all Redis baseline I/O |
| Interface | `read_buckets()`, `update_bucket()`, `seed_from_history()`, `bulk_recompute()` |
| Injection | Constructed at startup, injected into stage function |
| Testability | Stage tests use mock/fake client — no Redis dependency in unit tests |
| Rationale | Follows existing project pattern (RedisActionDedupeStore, PagerDutyClient, SlackClient). Encapsulates key formatting, serialization, batching. Clean I/O boundary |
| Affects | Baseline deviation stage, backfill extension, weekly recomputation |

## Pipeline Integration

**D2: Stage Interface — Single Stage Function**

| Aspect | Decision |
|---|---|
| Pattern | Single `collect_baseline_deviation_stage_output()` domain function |
| Inputs | `evidence_output`, `peak_output`, `baseline_client`, `evaluation_time` |
| Output | `BaselineDeviationStageOutput` (zero or more findings + stage metadata) |
| Scheduler integration | Wrapped by `run_baseline_deviation_stage_cycle()` in scheduler.py |
| Internal decomposition | Sub-functions for MAD computation, correlation, dedup — internal to stage module |
| Rationale | Consistent with `collect_evidence_stage_output`, `collect_peak_stage_output`, etc. Scheduler sees one entry point. Pure function of explicit inputs enables deterministic unit testing |
| Affects | pipeline/stages/, pipeline/scheduler.py |

**D6: Dedup Scope Matching — Exact Scope Tuple Match**

| Aspect | Decision |
|---|---|
| Pattern | Set lookup: `if scope in hand_coded_finding_scopes: skip` |
| Scope identity | Exact scope tuple from AnomalyFinding (e.g., `(env, cluster_id, topic)`) |
| Granularity | Precise — only suppresses where hand-coded detector covers the exact same scope |
| Rationale | PRD says "hand-coded detectors retain priority" — this means suppression at the overlap, not broad topic-level suppression. Topic-level match would over-suppress and could miss genuine anomalies on non-overlapping scopes |
| Affects | Baseline deviation stage dedup logic |

## Backfill & Recomputation Architecture

**D4: Weekly Recomputation — Background Async with In-Memory Build + Bulk Write**

| Aspect | Decision |
|---|---|
| Pattern | Background asyncio coroutine spawned from hot-path on weekly timer |
| Compute phase | Queries Prometheus `query_range`, partitions into 168 buckets entirely in memory |
| Write phase | Single Redis pipeline bulk write (`mset`/pipelined `SET`) — millisecond execution |
| Consistency | Hot-path reads old baselines during compute phase (valid). Bulk write creates negligible inconsistency window |
| Trigger | Hot-path checks `aiops:seasonal_baseline:last_recompute` timestamp each cycle; spawns background task if 7+ days elapsed |
| Failure mode | Pod restart mid-computation loses in-flight work — no corruption since nothing written to Redis. Retries next cycle |
| Memory | ~150MB temporary in-process during computation. Acceptable for background task |
| Rationale | Self-contained — hot-path manages its own baseline freshness. No additional runtime mode, no external scheduler. Compute-then-bulk-write eliminates concurrent write hazard. Satisfies NFR-R4 (idempotent writes) |
| Affects | pipeline/scheduler.py (timer + spawn), SeasonalBaselineClient (bulk_recompute method) |

**D5: Cold-Start Backfill — Extend Existing Backfill**

| Aspect | Decision |
|---|---|
| Pattern | Extend existing peak history backfill to also seed seasonal baselines |
| Data source | Same 30-day Prometheus `query_range` results already fetched for peak history |
| Partitioning | Existing backfill data partitioned into 168 time buckets by `SeasonalBaselineClient.seed_from_history()` |
| Blocking | Remains blocking on startup — pipeline does not cycle until both peak history and baselines are seeded |
| New metrics | Metrics added to Prometheus contract YAML receive backfill on next startup automatically |
| Rationale | Avoids duplicate Prometheus queries. Same raw data serves two purposes (peak history + baseline seeding). Leverages existing backfill infrastructure |
| Affects | Existing backfill code in scheduler.py startup, SeasonalBaselineClient |

## Decision Impact Analysis

**Implementation Sequence:**
1. D1 (Redis key schema) + D3 (SeasonalBaselineClient) — foundation, no dependencies
2. D5 (backfill extension) — depends on D1/D3, seeds the data
3. D2 (stage interface) + D6 (dedup matching) — the stage itself, depends on D1/D3
4. D4 (weekly recomputation) — depends on D1/D3, can be built after stage is working

**Cross-Component Dependencies:**
- D1 ↔ D3: Key schema defines the client's internal key formatting
- D2 → D3: Stage function receives the client as an injected dependency
- D2 → D6: Dedup logic is internal to the stage function
- D4 → D3: Recomputation uses `SeasonalBaselineClient.bulk_recompute()`
- D5 → D3: Backfill seeding uses `SeasonalBaselineClient.seed_from_history()`

## Documentation Impact

The following existing documentation files must be updated during implementation to reflect the architectural decisions above:

| Document | Updates Required |
|---|---|
| `docs/architecture.md` | Add baseline deviation stage to component overview, update stage flow diagram, add Redis seasonal baseline keyspace to data architecture |
| `docs/architecture-patterns.md` | Add baseline deviation stage to stage-based processing pipeline list |
| `docs/component-inventory.md` | Add SeasonalBaselineClient, baseline deviation stage module |
| `docs/data-models.md` | Add seasonal baseline Redis schema, AnomalyFinding BASELINE_DEVIATION extension, BaselineDeviationStageOutput model |
| `docs/contracts.md` | Document additive BASELINE_DEVIATION literal on anomaly_family |
| `docs/runtime-modes.md` | Add weekly recomputation background task to hot-path mode documentation, update dependency matrix (hot-path Redis usage expanded) |
| `docs/developer-onboarding.md` | Update pipeline journey with new stage, update stage flow diagrams, add baseline deviation to per-stage walkthrough |
| `docs/project-structure.md` | Add new module locations (baseline stage, baseline client) |
| `artifact/project-context.md` | Add baseline deviation framework rules to Critical Implementation Rules |

**Rule:** Each implementation story that introduces or modifies behavior covered by these documents must include the corresponding documentation update in the same change set — per the existing workflow rule in project-context.md.
