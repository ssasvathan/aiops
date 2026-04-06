# Project Context Analysis

## Requirements Overview

**Functional Requirements:**
32 FRs across 7 categories drive the architecture:
- **Seasonal Baseline Management (FR1-FR6):** Redis-backed storage of 168 time buckets per scope/metric, cold-start seeding from Prometheus, incremental updates, weekly recomputation, sample cap at 12 weeks, minimum sample guard
- **Anomaly Detection (FR7-FR10):** MAD computation per scope/metric/bucket, modified z-score threshold classification, deviation direction and magnitude capture
- **Correlation & Noise Suppression (FR11-FR15):** Per-scope deviation aggregation, correlated deviation gate (2+ metrics), single-metric suppression with DEBUG logging, hand-coded detector dedup, correlated context in findings
- **Finding & Pipeline Integration (FR16-FR21):** BASELINE_DEVIATION finding model with severity LOW / is_primary=False / proposed_action=NOTIFY, passthrough compatibility with topology, gating (AG0-AG6), casefile, outbox, and dispatch stages
- **Metric Discovery & Onboarding (FR22-FR24):** Contract-driven metric auto-discovery, zero-code onboarding via Prometheus contract YAML, scope discovery from evidence stage
- **LLM Diagnosis (FR25-FR28):** Cold-path async processing for BASELINE_DEVIATION cases, hypothesis-framed output, fallback diagnosis on LLM failure, hash-chain integrity
- **Observability & Operations (FR29-FR32):** OTLP counters (deviations detected, findings emitted/suppressed), histograms (stage latency, MAD computation), structured log events, HealthRegistry integration

**FR-to-Component Clustering (Architectural Traceability):**

| Architectural Component | FRs | Nature |
|---|---|---|
| Seasonal Baseline Store | FR1-FR6, FR22-FR24 | New component — Redis keyspace, read/write patterns, metric discovery |
| Baseline Deviation Stage | FR7-FR15 | New component — MAD computation, correlation gate, dedup check |
| Finding Model Extension | FR16-FR21 | Extension — additive BASELINE_DEVIATION literal, passthrough validation |
| Cold-Path Diagnosis Extension | FR25-FR28 | Extension — new case type in existing cold-path consumer |
| Observability Instrumentation | FR29-FR32 | Cross-cutting — OTLP counters/histograms/logs across all new components |

This yields **3 new components** (baseline store, deviation stage, backfill/recomputation engine) and **2 extensions** (finding model, cold-path diagnosis).

**Non-Functional Requirements:**
17 NFRs across 4 categories constrain the architecture:
- **Performance (P1-P6):** 40s stage budget, 50ms Redis batch reads, 1ms MAD computation, 10-minute cold-start backfill, 10-minute weekly recomputation, 5ms incremental update overhead
- **Scalability (S1-S4):** 200MB Redis ceiling at 3x load (2.52M keys), linear scaling with scope count, zero-code new metric onboarding, batch read performance at scale
- **Reliability (R1-R5):** Per-scope error isolation, fail-open on Redis unavailability, MIN_BUCKET_SAMPLES guard, atomic/idempotent recomputation, independent disableability
- **Auditability (A1-A4):** SHA-256 hash-chain on case files, full deviation context for offline replay, structured suppression logging, reproducible gate decisions

**Scale & Complexity:**

- Primary domain: Backend event-driven pipeline (AIOps / Operational Intelligence)
- Complexity level: Medium-High
- Architectural footprint: 3 new components + 2 extensions to existing components

## Technical Constraints & Dependencies

**Hard Constraints (from existing architecture):**
- **Pipeline stage ordering:** Baseline deviation must execute after evidence and peak stages, before topology enrichment. Precise insertion: `evidence → peak → baseline_deviation → topology → casefile → outbox → gating → dispatch`. Note: the evidence stage IS the anomaly detection stage — it runs the hand-coded detectors (CONSUMER_LAG, VOLUME_DROP, THROUGHPUT_CONSTRAINED_PROXY) and produces AnomalyFinding objects
- **Hot-path determinism:** No LLM, no external calls, no non-deterministic behavior in the new stage. The baseline deviation stage must be a pure function of its inputs — same Redis baseline state + same Prometheus observations + same hand-coded detector output = same findings
- **Frozen contract models:** AnomalyFinding extension must be additive (new anomaly_family literal), not breaking. Follows Procedure A from schema-evolution-strategy.md (additive-only, no version bump)
- **Existing gate framework (AG0-AG6):** Processes BASELINE_DEVIATION findings unchanged — NOTIFY cap means only AG1 environment cap can apply (lowering, never raising)
- **Cold-path D6 invariant:** LLM diagnosis for baseline deviation is async, advisory, no import path to hot path
- **Write-once casefile semantics:** Hash-chain integrity applies to all BASELINE_DEVIATION case files
- **Redis coordination model:** TTL-based expiry, fail-open semantics, no explicit unlock

**Wide Input Surface (unique to this stage):**
The baseline deviation stage has 4 input sources — wider than any existing stage:
1. Current Prometheus observations (from evidence stage output)
2. Hand-coded detector findings per scope (from evidence stage output, for dedup — FR14)
3. Redis seasonal baseline data for the current time bucket (direct Redis read)
4. Current time bucket identifier (derived from wall clock — dow:hour)

The stage function signature must make all 4 inputs explicit with no hidden dependencies, enabling deterministic unit testing with injected inputs.

**Redis Read/Write Patterns:**
- **Read pattern (per cycle):** Every cycle reads the current time bucket for all scope x metric combinations — up to 4,500 keys (500 scopes x 9 metrics). Batching strategy (by scope, by metric, or single mget) is an architectural decision constrained by NFR-P2 (50ms per scope batch)
- **Write pattern 1 — Incremental update:** Per-cycle append of current observation to the current time bucket (hot-path, every 5 minutes)
- **Write pattern 2 — Cold-start seed:** Blocking startup, partitions 30-day Prometheus query_range into 168 time buckets per scope/metric
- **Write pattern 3 — Weekly recomputation:** Background job, replaces all bucket contents from Prometheus raw data, must be atomic/idempotent per NFR-R4

**Infrastructure Dependencies (all pre-existing):**
- Redis 7.2: seasonal baseline key storage (new keyspace), existing dedupe/cache usage unaffected
- Prometheus v2.50.1: cold-start backfill source (query_range API), weekly recomputation source
- S3/MinIO: casefile storage for BASELINE_DEVIATION triage artifacts
- PostgreSQL 16: outbox table for BASELINE_DEVIATION case events (existing schema, no changes)
- Kafka: CaseHeaderEventV1 publication via outbox-publisher (existing flow, no changes)

**Existing Patterns to Conform To:**
- Structured logging via structlog with correlation_id binding
- OTLP instrumentation via shared health/metrics primitives
- Pydantic frozen models with validators for structural invariants
- Environment action caps (local=OBSERVE, dev=NOTIFY) via rulebook AG1

## Cross-Cutting Concerns Identified

- **Observability:** New OTLP counters and histograms for the baseline deviation stage must follow existing instrumentation patterns (create_counter, create_histogram, create_up_down_counter)
- **Reliability:** Fail-open behavior on Redis unavailability must be consistent with existing coordination fail-open semantics; per-scope error isolation follows existing per-case error handling pattern
- **Auditability:** BASELINE_DEVIATION case files must maintain identical SHA-256 hash-chain integrity as existing families; gate decisions must be reproducible via reproduce_gate_decision()
- **Dedup Coordination:** Hand-coded detector priority requires the baseline deviation stage to inspect evidence stage output and suppress findings for scopes already covered — this is an embedded predicate within the stage (not a separate stage), unit-testable via mock evidence output
- **Contract Compliance:** The additive BASELINE_DEVIATION literal follows Procedure A from schema-evolution-strategy.md (additive-only, no version bump)
- **Testability:** The baseline deviation stage must be a pure function of its explicit inputs (observations, baseline data, detector output, time bucket). The time bucket must be injectable to eliminate wall-clock dependency. Weekly recomputation and cold-start backfill are independently testable functions. Dedup check is a simple set lookup on evidence output, testable at unit level without pipeline orchestration
- **Signal-Agnostic Extensibility:** Architecture decisions now (Redis key schema, MAD computation abstraction, metric discovery interface) must not preclude Phase 3 multi-signal extension (Tempo traces, Loki logs)
