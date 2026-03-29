# Project Context Analysis

## Requirements Overview

**Functional Requirements:**

60 FRs across 10 capability areas, plus 2 process/governance requirements:

| Area | FRs | Architectural Impact |
|---|---|---|
| Evidence Collection & Anomaly Detection | FR1-FR7 | Per-scope baselines from Redis, Prometheus ingestion, UNKNOWN propagation |
| Peak & Sustained Classification | FR8-FR11 | Externalized Redis state, parallelized computation, bounded memory |
| Topology Resolution & Ownership Routing | FR12-FR16 | Single-format YAML in config/, reload-on-change, multi-level ownership |
| Deterministic Gating & Action Decisions | FR17-FR25 | YAML-authoritative DSL engine, handler registry, post-condition safety assertions |
| Case Management & Persistence | FR26-FR31 | Write-once S3, SHA-256 hash chains, outbox state machine, policy stamps |
| Action Dispatch | FR32-FR35 | PagerDuty/Slack/ServiceNow adapters, denylist enforcement, structured log fallback |
| LLM Diagnosis (Cold Path) | FR36-FR43 | Independent Kafka consumer pod, evidence summary builder, enriched prompts, fallback reports |
| Distributed Operations | FR44-FR48 | Cycle lock, scope sharding, lease/fence, feature-flagged rollout |
| Configuration & Policy Management | FR49-FR53 | YAML policies loaded at startup, APP_ENV resolution, SASL_SSL validation |
| Observability & Health | FR54-FR58 | Health endpoint per pod, coordination state, OTLP metrics, structured logs with pod identity |

**Non-Functional Requirements:**

29 NFRs across 6 categories driving architectural decisions:

| Category | Count | Key Constraints |
|---|---|---|
| Performance | 7 | Gate eval p99 <= 500ms, outbox p95 <= 1min, batched Redis O(1), parallelized sustained computation |
| Security | 6 | Secret masking, shared denylist, SASL_SSL fail-fast, MI-1 guardrails, integration safety defaults |
| Scalability | 4 | Hot/hot 2-pod, scope sharding O(1) checkpoints, outbox row locking, Redis as single shared state layer |
| Reliability | 8 | DEAD=0 posture, write-once Invariant A, at-least-once Invariant B2, fail-open cycle lock, conservative sustained fallback |
| Auditability | 6 | 25-month retention, policy version stamps, schema envelope versioning, correlation IDs, pod identity |
| Integration | 4 | OFF\|LOG\|MOCK\|LIVE consistency, degradable failures non-blocking, PagerDuty dedup_key, Kafka offset commit |

**Scale & Complexity:**

- Primary domain: Backend event-driven pipeline / IT Operations AIOps
- Complexity level: High
- Estimated architectural components: 22 (from component inventory) plus new coordination, baseline computation, cold-path consumer, and evidence summary modules
- Runtime modes: 4 (hot-path, cold-path, outbox-publisher, casefile-lifecycle)
- External integrations: 6 (Prometheus, Kafka, PagerDuty, Slack, ServiceNow, LLM)

## CR Dependency Graph

CR-01 (Wire Redis) is the load-bearing foundation of this revision phase. Its design decisions propagate to five dependent CRs — a wrong call here is inherited by half the revision scope.

```
CR-01 (Wire Redis) ─────┬──> CR-03 (Unified baselines) ──> CR-03 enables AG6 activation
                         ├──> CR-04 (Sharded findings cache)
                         ├──> CR-05 (Distributed hot/hot) ──> highest-risk new capability
                         ├──> CR-10 (Redis bulk + memory)
                         └──> CR-07 (Cold-path consumer) ──> depends on CR-06

CR-11 (Topology simplify) ──> independent cleanup, no downstream deps

CR-02 (DSL rulebook) ──> independent refactor, structurally complex

CR-06 (Evidence summary) ──> CR-07 (Cold-path consumer) ──> CR-08 (Remove criteria)
                                                          ──> CR-09 (Prompt optimization)
```

**Blast radius ranking by downstream impact:**

| Rank | CR | Downstream CRs Affected | Risk if Wrong |
|---|---|---|---|
| 1 | CR-01 (Wire Redis) | CR-03, CR-04, CR-05, CR-10, indirectly CR-07 | 5 CRs inherit design errors |
| 2 | CR-05 (Distributed hot/hot) | None directly, but affects all hot-path execution | Duplicate dispatches in production |
| 3 | CR-02 (DSL rulebook) | None directly, but affects all gate evaluation | Safety invariant regression |
| 4 | CR-06 (Evidence summary) | CR-07, CR-08, CR-09 | Cold-path chain blocked |
| 5 | CR-03 (Unified baselines) | Enables AG6 activation | Incorrect anomaly detection |

## Redis Role Expansion and Concentrated-Risk Trade-off

Redis goes from two responsibilities (AG5 dedupe + findings cache) to being the single shared state layer for the entire coordination and caching surface:

**Before revision (baseline):**
- AG5 action deduplication (SET NX EX)
- Findings cache (per-scope-per-interval idempotency)

**After revision (all 11 CRs landed):**
- AG5 atomic deduplication (unchanged but now single-step)
- Findings cache with sharded checkpoints (CR-04)
- Sustained window state persistence (CR-01, CR-05)
- Peak profile caching (CR-01)
- Per-scope metric baselines (CR-03)
- Distributed cycle lock (CR-05)
- Bulk key loading operations (CR-10)

**Trade-off (NFR-SC4):** Centralizing all coordination in Redis simplifies the programming model — one shared state layer, one failure mode to handle — but concentrates risk. The architecture mitigates this through:
- **Fail-open cycle lock** (NFR-R4): Redis down = single-instance behavior, not halt
- **Conservative sustained fallback** (NFR-R5): Redis down = None (first observation), no false sustained=true
- **Findings cache last-writer-wins**: Already correct for multi-instance
- **AG5 dedupe degradation**: Existing HealthRegistry degraded-mode handling

The architecture document must specify the degradation behavior for each Redis consumer when Redis is unavailable.

## Architectural Invariants (Stability Foundation)

These are not limitations — they are the stability foundation that makes the revision phase low-risk. Every CR builds on these as immovable guarantees:

**Contract invariants:**
- GateInputV1, ActionDecisionV1, CaseHeaderEventV1, TriageExcerptV1, DiagnosisReportV1 — all frozen, no breaking changes
- Schema envelope pattern and hash chain integrity preserved
- Pydantic v2 frozen models as source of truth for all payload shapes

**API invariants:**
- evaluate_rulebook_gates() public function signature unchanged
- Gate-input assembly (collect_gate_inputs_by_scope) unchanged
- _apply_gate_effect() unchanged
- All downstream consumers (dispatch, outbox, CaseFile assembly) unchanged

**Behavioral invariants:**
- PAGE structurally impossible outside PROD+TIER_0 — enforced by post-condition assertions independent of YAML
- Actions only cap downward, never escalate (monotonic reduction)
- Hot/cold path structural separation — no import path, no shared state, no conditional wait
- Write-once casefile semantics with SHA-256 hash chains
- Outbox durability (Invariant B2) — write-before-publish, crash-safe
- UNKNOWN never collapsed to PRESENT or zero
- Environment action caps: local=OBSERVE, dev=NOTIFY, uat=TICKET, prod=PAGE

**Infrastructure invariants:**
- Python 3.13 with asyncio, Pydantic v2, SQLAlchemy Core
- Redis as single shared state layer (NFR-SC4)
- Postgres for durable outbox and linkage retry
- S3-compatible object storage for write-once casefiles
- Pipeline stage ordering and scheduler cadence unchanged

## Technical Constraints & Dependencies

**Deployment target:**
- Dev OpenShift cluster with hot/hot 2-pod minimum
- Feature-flagged distributed coordination (DISTRIBUTED_CYCLE_LOCK_ENABLED, default false) for incremental rollout
- Single Docker image, multiple runtime modes via --mode argument

**Testing architecture constraints (load-bearing for verification):**
- Existing 36 gating test functions (60+ parametrized cases) serve as regression safety net for CR-02 — all must pass unmodified
- CR-05 (distributed coordination) requires multi-process integration tests with real Redis — unit tests cannot verify race conditions, cycle lock contention, or cross-replica sustained-state consistency
- CR-02 (DSL rulebook) migration must demonstrate byte-identical replay for historical CaseFiles under the new engine — 25-month audit replay backward compatibility
- CR-07 (cold-path consumer) introduces the first Kafka consumer in the system — consumer lifecycle (offset management, rebalance handling, graceful shutdown with commit) is new territory requiring integration tests against real Kafka
- Each architectural decision should specify its verification strategy alongside the design, not as an afterthought

## Cross-Cutting Concerns (Prioritized by Blast Radius)

Ranked by how many CRs and components are affected if the concern is handled incorrectly:

| Priority | Concern | CRs Affected | Impact if Wrong |
|---|---|---|---|
| 1 | **Distributed coordination** — cycle lock, sustained state, atomic dedupe, outbox locking, scope sharding | CR-01, CR-04, CR-05, CR-10 | Duplicate dispatches, divergent decisions, data races |
| 2 | **Redis state model** — key namespacing, TTL strategy, failure degradation per consumer | CR-01, CR-03, CR-04, CR-05, CR-10 | Cross-CR key collisions, inconsistent degradation, memory pressure |
| 3 | **Environment action caps** — monotonic reduction, PAGE structural impossibility | CR-02, CR-05 | Safety invariant violation — pages outside PROD+TIER_0 |
| 4 | **UNKNOWN propagation** — missing evidence never collapsed | CR-01, CR-02, CR-03 | False confidence, incorrect gate decisions |
| 5 | **Write-once integrity** — SHA-256 hash chains, put_if_absent, no read-modify-write | CR-04, CR-05 | Tampered audit trail, casefile corruption |
| 6 | **Denylist enforcement** — shared apply_denylist() at every outbound boundary | CR-06, CR-07, CR-09 | Sensitive data in LLM prompts or external notifications |
| 7 | **Integration safety framework** — OFF\|LOG\|MOCK\|LIVE mode semantics | CR-07 | Unintended external calls in dev/local |
| 8 | **Policy version stamping** — every casefile stamps active versions | CR-02, CR-03 | Unreproducible decisions within 25-month window |
| 9 | **Schema envelope versioning** — perpetual read support for 25-month retention | All CRs (standing) | Old casefiles become unreadable |
| 10 | **Pod identity observability** — POD_NAME/POD_NAMESPACE in OTLP and structlog | CR-05 | Indistinguishable replicas in monitoring |

## Operational Readiness Definition

The architecture must define what "operationally ready" means as a system property — the acceptance criteria for the revision phase as a whole:

**Pipeline liveness:**
- Hot-path cycle completion rate at 100% of scheduled intervals
- Cold-path consumer processing CaseHeaderEventV1 from Kafka and writing diagnosis.json to S3
- Outbox-publisher draining READY rows with p95 <= 1min delivery

**Coordination health:**
- Two hot-path pods running with zero duplicate dispatches
- Cycle lock acquired/yielded/failed counters visible in OTLP metrics
- Sustained-state Redis hit/miss rates visible

**Observability completeness:**
- Health endpoint per pod reporting meaningful component state including coordination status
- Pod identity in all OTLP metrics and structured logs
- Correlation IDs (case_id) enabling per-case decision trail queries in Elastic

**Configuration authority:**
- YAML rulebook is the authoritative execution specification — gate behavior changes through YAML, not code
- Topology registry loads from config/ in single format
- All policies loaded at startup with version stamps in casefiles

**Degradation posture:**
- Redis unavailability: fail-open (cycle lock), conservative (sustained state), degraded (caching) — never halt
- Prometheus unavailability: UNKNOWN evidence propagated, TelemetryDegradedEvent emitted
- LLM unavailability: deterministic fallback DiagnosisReportV1
- Kafka unavailability: hot-path continues, cases accumulate in outbox
