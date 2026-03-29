# Core Architectural Decisions

## Decision Priority Analysis

**Critical Decisions (Block Implementation):**

| # | Decision | CRs Affected | Rationale |
|---|---|---|---|
| D1 | Redis key namespace: flat prefix `aiops:{data_type}:{scope_key}` | CR-01, CR-03, CR-04, CR-05, CR-10 | Foundation — all Redis consumers depend on this |
| D2 | Redis is ephemeral by design; correctness never depends on Redis data surviving a restart | All Redis CRs | Core reliability posture |
| D3 | Redis failure degradation matrix | All Redis CRs | Every consumer must degrade gracefully |
| D4 | Rule engine as isolated package `rule_engine/` with zero pipeline imports | CR-02 | Safety-critical path must be testable in isolation |
| D5 | Cycle lock protocol: single `SET NX EX` with TTL, no explicit unlock | CR-05 | Multi-replica safety foundation |
| D6 | Cold-path consumer: confluent-kafka, sequential processing, no eligibility criteria | CR-07, CR-08 | Activates the cold-path from stub to operational |
| D7 | Outbox row locking: `SELECT FOR UPDATE SKIP LOCKED` | CR-05 | Prevents duplicate Kafka publication |
| D13 | Redis connection pooling: shared pool sized for peak concurrent operations | All Redis CRs | Prevents pool exhaustion during bulk loads blocking cycle lock |

**Important Decisions (Shape Architecture):**

| # | Decision | CRs Affected | Rationale |
|---|---|---|---|
| D8 | Baseline computation as background task within hot-path with pluggable collector pattern | CR-03 | Future-proofs for multi-telemetry expansion |
| D9 | Evidence summary as programmatic builder with byte-identical stability guarantee | CR-06 | Cold-path LLM input quality |
| D10 | Topology v0 clean cut removal, YAML relocated to config/ | CR-11 | Simplification — no deprecation needed for greenfield |

**Deferred Decisions (Phase 2+):**

| # | Decision | Rationale for Deferral |
|---|---|---|
| D11 | Scope-level sharding across pods | Cycle lock handles Phase 1; sharding is throughput scaling, not correctness |
| D12 | Sharding implementation via Redis consistent hash ring | Designed but feature-flagged; activate when single-pod throughput is insufficient |

## Standing Architectural Principle

Every architectural decision assumes OpenShift as the target platform for dev, uat, and prod. Local/docker is the development-time convenience layer, not the primary target. No decision requires "adaptation" for uat/prod — the architecture is OpenShift-native.

| Environment | Platform | Action Cap | LLM Mode |
|---|---|---|---|
| local/docker | Docker Compose | OBSERVE | LOG (configurable to MOCK/LIVE) |
| dev | OpenShift | NOTIFY | LIVE |
| uat | OpenShift | TICKET | LIVE |
| prod | OpenShift | PAGE | LIVE |

## D1: Redis Key Namespace Strategy

**Decision:** Flat prefix convention `aiops:{data_type}:{scope_key}`

**Rationale:** Separate Redis instance per environment eliminates the need for environment isolation in keys. Flat prefix is shorter, scannable with `SCAN aiops:sustained:*`, and avoids over-engineering for Redis Cluster (not needed in Phase 1).

**Key patterns:**

| Data Type | Key Pattern | TTL |
|---|---|---|
| Sustained window state | `aiops:sustained:{cluster}:{group}:{topic}` | Configured via Redis TTL policy |
| Peak profile cache | `aiops:peak:{cluster}:{topic}` | Configured via Redis TTL policy |
| Per-scope baselines | `aiops:baseline:{source}:{scope_key}:{metric_key}` | Environment-specific |
| Cycle lock | `aiops:lock:cycle` | scheduler_interval + lock_margin |
| AG5 deduplication | `aiops:dedupe:{fingerprint}` | Configured TTL |
| Findings cache | `aiops:findings:{scope}:{interval}` | Short-lived (interval-scoped) |
| Shard checkpoint | `aiops:shard:checkpoint:{shard_id}:{interval}` | Short-lived (interval-scoped) |

**Migration:** Existing findings cache and AG5 dedupe keys migrated to the new namespace convention for consistency. Single-change migration — old keys expire naturally via TTL.

**Affects:** CR-01, CR-03, CR-04, CR-05, CR-10

## D2: Redis Ephemerality Principle

**Decision:** Redis is ephemeral by design. Correctness never depends on Redis data surviving a restart.

**Rationale:** Redis serves as a performance and coordination accelerator, not a source of truth. The sources of truth are Postgres (durable outbox), S3 (write-once casefiles), Kafka (event publication), and Prometheus (telemetry). Every Redis data type is either reconstructable (baselines, peak profiles, findings) or designed for graceful loss (sustained state → None, cycle lock → fail-open, dedupe → brief window with PagerDuty backstop).

**Operational note:** Redis RDB/AOF persistence is an operational deployment choice for faster recovery. The architecture does not require it — it must be correct without persistence enabled.

**Affects:** All Redis-consuming CRs

## D3: Redis Failure Degradation Matrix

**Decision:** Every Redis consumer degrades gracefully on Redis unavailability — updates HealthRegistry, continues with capped/conservative behavior. No consumer halts the pipeline.

| Consumer | On Redis Unavailable | Behavior | HealthRegistry |
|---|---|---|---|
| Cycle lock | Fail-open — proceed as if acquired | Single-instance equivalent | Degraded |
| Sustained window state | Fall back to None | Conservative — no false sustained=true | Degraded |
| Peak profile cache | Return empty | Peak = UNKNOWN, propagates conservatively | Degraded |
| Per-scope baselines | Use cold-start defaults | Reverts to configured fallback thresholds | Degraded |
| AG5 deduplication | Existing degraded behavior | Action capped per existing implementation | Degraded |
| Findings cache | Skip cache | Recompute from Prometheus | Degraded |
| Shard checkpoint | Skip checkpoint | Process all scopes (full-scope fallback) | Degraded |

**Affects:** CR-01, CR-03, CR-04, CR-05, CR-10

## D4: DSL Rule Engine — Isolated Package

**Decision:** Self-contained `rule_engine/` package with zero imports from pipeline/, integrations/, storage/, health/, or config/. Imports only from contracts/. Custom implementation — no external DSL library dependency on the safety-critical gate evaluation path.

**Rationale:** The gate evaluation path makes PAGE/no-PAGE decisions with 25-month audit replay requirements. Zero external dependency on this path eliminates library abandonment risk. The predicate evaluation is simple enough (~6 types) that a library adds overhead without proportional value.

**Package structure:**
```
src/aiops_triage_pipeline/rule_engine/
    __init__.py          # Public API: evaluate_gates()
    engine.py            # Sequential gate evaluation loop
    handlers.py          # Handler registry + ~9 check-type handlers
    predicates.py        # Structured YAML predicate evaluator (~6 types)
    safety.py            # Post-condition assertions
    protocol.py          # CheckHandler protocol, CheckContext, CheckResult
```

**Dependency rules:**
- `rule_engine/` imports from `contracts/` only
- `pipeline/stages/gating.py` imports from `rule_engine/`
- AG5 dedupe store passed via dependency injection in CheckContext
- Handler registry: `MappingProxyType` frozen at import time
- Startup validation: every YAML check.type must have a registered handler (fail-fast)

**Handler protocol:**
- Input: GateCheck + CheckContext (gate input, current state, rulebook, injected dependencies)
- Output: `CheckResult(outcome, effect_key, reason_codes)` — where `effect_key` explicitly names which GateEffect attribute to apply
- Engine maps: `gate.effects[effect_key]` → `_apply_gate_effect()` (existing, unchanged)
- This generalizes multi-step handlers — AG1 returns `effect_key="cap_applied"` for env cap or `effect_key="tier_cap_applied"` for tier cap, without gate-specific branching in the engine

**Predicate types:** equals, in, gte/lte, current_action_gte, state_field_true, always. Composable with all_of/any_of.

**Safety layer:** Post-condition assertions after evaluation loop:
1. PAGE requires PROD + TIER_0
2. Invalid input requires OBSERVE
3. Action only decreased or unchanged from initial

**Test strategy:**
- Unit tests: call `rule_engine.evaluate_gates()` directly with in-memory inputs — zero infrastructure, zero Docker
- AG5 handler: unit tests inject a stub dedupe store (in-memory dict); integration tests inject real Redis-backed store (testcontainers)
- AG1 handler: test matrix covers env cap only, tier cap only, both caps, neither cap (existing 7 parametrized cases map to new handler result combinations)
- All existing 36 test functions (60+ parametrized cases) must pass unmodified

**Affects:** CR-02

## D5: Distributed Cycle Lock Protocol

**Decision:** Redis `SET NX EX` with TTL-based expiry. No explicit unlock. Feature-flagged via `DISTRIBUTED_CYCLE_LOCK_ENABLED` (default false).

**Protocol:**
```
lock_key  = "aiops:lock:cycle"
lock_ttl  = scheduler_interval + 60s (default margin, configurable via CYCLE_LOCK_MARGIN_SECONDS)
acquired  = redis.set(lock_key, pod_name, nx=True, ex=lock_ttl)
```

**Default lock margin:** 60 seconds. For a 300s scheduler interval, total TTL = 360s. This gives headroom for cycles that run slightly over the interval without holding the lock so long that a dead pod blocks the next interval for minutes.

**Scheduler loop:**
1. Feature flag off → execute cycle (current single-instance behavior)
2. Feature flag on → attempt lock acquisition
   - Acquired → execute cycle; lock auto-expires via TTL
   - Not acquired → log "cycle yielded to {holder}"; sleep to next interval
   - Redis unavailable → fail-open; execute cycle (degraded)

**No explicit unlock.** Lock expires via TTL. Avoids complexity of unlock-on-completion failure scenarios.

**OTLP counters:** cycle_lock_acquired, cycle_lock_yielded, cycle_lock_failed

**Test strategy:**
- Unit tests: lock acquisition/yield/fail-open logic with a mock Redis client
- Integration tests: two concurrent processes competing for the lock with real Redis (testcontainers)
- Operational verification: OTLP counter assertions in the dev OpenShift deployment

**Affects:** CR-05

## D6: Cold-Path Consumer Architecture

**Decision:** confluent-kafka Consumer in dedicated `--mode cold-path` pod. Sequential message processing. No eligibility criteria (CR-08). Consumer wrapped in a thin adapter protocol for testability.

**Consumer group:** `aiops-cold-path-diagnosis` on `aiops-case-header` topic.

**Library:** confluent-kafka (same as existing publisher) — reuses SASL_SSL/Kerberos configuration. No new Kafka library dependency.

**Consumer adapter:** The confluent-kafka Consumer is wrapped in a thin protocol/interface so tests can inject a fake consumer yielding predetermined messages. Production code and test code interact with the adapter interface, not the confluent-kafka API directly.

**Processing loop:**
1. Poll for CaseHeaderEventV1
2. Deserialize via schema envelope
3. Read triage.json from S3 (guaranteed by Invariant A)
4. Reconstruct TriageExcerptV1 from persisted casefile
5. Build evidence summary (CR-06)
6. Call run_cold_path_diagnosis() (existing)
7. Commit offset
8. Loop

**Health endpoint:** Dedicated `/health` reporting consumer group state (last poll timestamp, lag, connected).

**Graceful shutdown:** SIGTERM → close consumer (commit offsets) → exit.

**Integration modes:**

| Environment | LLM Mode |
|---|---|
| local/docker | LOG (configurable to MOCK/LIVE) |
| dev/uat/prod (OpenShift) | LIVE |

**Affects:** CR-07, CR-08

## D7: Outbox Row Locking

**Decision:** `SELECT FOR UPDATE SKIP LOCKED` — one-line SQL change to existing query in `outbox/repository.py`.

**Rationale:** Battle-tested Postgres primitive. No schema changes, no new outbox status, no reaper process. The existing state machine (PENDING_OBJECT → READY → SENT/RETRY/DEAD) is unchanged.

**Affects:** CR-05

## D8: Baseline Computation with Pluggable Collector Pattern

**Decision:** Periodic background task within the hot-path process. No new runtime mode or pod. Designed with pluggable collector protocol for multi-telemetry expansion.

**Scheduling:** Configurable interval (`BASELINE_COMPUTATION_INTERVAL_SECONDS`), independent of scheduler tick. Guarded against self-overlap via in-process boolean flag — if computation is running when the next trigger fires, the trigger is skipped (not queued, not run concurrently).

**Overlap guard test:** Verify that concurrent trigger is skipped, not stacked. Prevents subtle memory/CPU pressure from accumulated baseline computations.

**Collector protocol:**
```python
class BaselineCollector(Protocol):
    def collect_historical(
        self, scopes: Sequence[ScopeKey], window: timedelta
    ) -> Mapping[ScopeKey, Mapping[MetricKey, Sequence[float]]]: ...
```

**Phase 1:** Only `PrometheusMetricCollector` implemented. Protocol, registry, and Redis store designed for future collectors (log, trace, VM) but no speculative implementation.

**Redis baseline store:** Telemetry-source-agnostic key pattern `aiops:baseline:{source}:{scope_key}:{metric_key}` — future sources get their own namespace.

**Affects:** CR-03

## D9: Evidence Summary Builder

**Decision:** Programmatic builder function with byte-identical stability guarantee. Lives in `diagnosis/evidence_summary.py`.

**Design:** Pure function: TriageExcerptV1 → str. Deterministic ordering (sorted keys, fixed section order). No timestamps in output. Conditionally includes sections based on evidence status.

**Deterministic ordering requirement:** All TriageExcerptV1 fields must have deterministic iteration order in the builder. Any unordered collections (sets, unordered dicts) must be sorted before rendering. Implementation must verify this for every field path used in the summary.

**Output sections:** Case context, evidence status (PRESENT with values / UNKNOWN with reasons / ABSENT), anomaly findings (all fields), temporal context (sustained, peak classification).

**Affects:** CR-06

## D10: Topology Simplification — Clean Cut

**Decision:** Remove all v0 code in one change. Relocate topology YAML to `config/topology-registry.yaml`.

**Removed:** Legacy flat-format parser, format auto-detection, version negotiation, v0 compatibility views, synthetic default injection, all v0 test coverage.

**Unchanged:** Canonical in-memory model, registry resolver, pipeline topology stage, reload-on-change, all resolver tests.

**Affects:** CR-11

## D11-D12: Scope Sharding (Designed, Deferred)

**Phase 1 decision:** Cycle lock (CR-05) handles multi-replica safety. CR-04 delivers batch checkpoint optimization (O(N) → O(1) per-interval writes) without actual scope partitioning.

**Phase 2 primary path:** Redis consistent hash ring — custom thin module (~100-200 lines) using hashlib + Redis sorted set. Each pod registers with TTL heartbeat, reads active pods, computes responsible scopes locally. Feature-flagged via `SHARD_REGISTRY_ENABLED`. Existing idempotency guards (findings cache, S3 put_if_absent, AG5 dedupe) provide defense-in-depth during transient overlap.

**Phase 2 fallback:** StatefulSet ordinals with modulo assignment as prototype stepping stone.

**Phase 3+ consideration:** If scope counts exceed 10,000+ or sub-minute intervals needed, evaluate ZooKeeper SetPartitioner (with asyncio bridge) or Kafka-based scope assignment for push-based rebalancing.

**Not recommended:** Celery/Ray/Dask (wrong abstraction), Flink (complete rewrite), K8s Operator (overkill).

## D13: Redis Connection Pooling

**Decision:** Shared Redis connection pool across all consumers, sized to accommodate peak concurrent operations.

**Rationale:** With 7 Redis consumers in the hot-path, separate pools waste connections. A shared pool prevents the scenario where a bulk baseline load exhausts connections and blocks cycle lock acquisition.

**Pool sizing:** Must accommodate peak concurrent operations — bulk key load (CR-10) + cycle lock acquisition (CR-05) + sustained state read (CR-01) are the likely concurrent peaks. Configurable via `REDIS_MAX_CONNECTIONS` with a sensible default (e.g., 50).

**Affects:** All Redis CRs

## Decision Impact Analysis

**Implementation sequence (dependency-driven):**

| Order | Decision | Must Complete Before |
|---|---|---|
| 1 | D1 (Redis namespace) + D13 (Connection pool) | D2, D3, D5, D8 |
| 2 | D10 (Topology clean cut) | Independent — can parallel with D1 |
| 3 | D4 (Rule engine package) | Independent — can parallel with D1 |
| 4 | D2 + D3 (Redis ephemerality + degradation) | D5, D8 |
| 5 | D5 (Cycle lock) + D7 (Outbox locking) | D6 |
| 6 | D8 (Baseline computation) | D9 |
| 7 | D9 (Evidence summary) | D6 |
| 8 | D6 (Cold-path consumer) | — |

**Cross-decision dependencies:**
- D1 + D13 define the key patterns and connection model that all Redis consumers use
- D4 is self-contained — can be developed and tested in complete isolation
- D5 + D7 together enable multi-replica safety
- D8 → D9 → D6 is the cold-path activation chain
- D10 is independent and can be done at any point
