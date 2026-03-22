---
stepsCompleted: ["step-01-validate-prerequisites", "step-02-design-epics", "step-03-create-stories", "step-04-final-validation"]
inputDocuments:
  - artifact/planning-artifacts/prd/index.md
  - artifact/planning-artifacts/prd/executive-summary.md
  - artifact/planning-artifacts/prd/project-classification.md
  - artifact/planning-artifacts/prd/success-criteria.md
  - artifact/planning-artifacts/prd/product-scope.md
  - artifact/planning-artifacts/prd/user-journeys.md
  - artifact/planning-artifacts/prd/domain-specific-requirements.md
  - artifact/planning-artifacts/prd/event-driven-pipeline-specific-requirements.md
  - artifact/planning-artifacts/prd/functional-requirements.md
  - artifact/planning-artifacts/prd/non-functional-requirements.md
  - artifact/planning-artifacts/prd/process-governance-requirements.md
  - artifact/planning-artifacts/architecture/index.md
  - artifact/planning-artifacts/architecture/project-context-analysis.md
  - artifact/planning-artifacts/architecture/starter-template-evaluation.md
  - artifact/planning-artifacts/architecture/core-architectural-decisions.md
  - artifact/planning-artifacts/architecture/implementation-patterns-consistency-rules.md
  - artifact/planning-artifacts/architecture/project-structure-boundaries.md
  - artifact/planning-artifacts/architecture/architecture-validation-results.md
  - artifact/planning-artifacts/prd-validation-report.md
  - artifact/planning-artifacts/product-brief-aiOps-2026-03-21.md
---

# aiOps - Epic Breakdown

## Overview

This document provides the complete epic and story breakdown for aiOps, decomposing the requirements from the PRD and Architecture into implementable stories. There is no UX Design document — this is a backend event-driven pipeline with no UI component.

## Requirements Inventory

### Functional Requirements

FR1: The hot-path can query Prometheus for infrastructure telemetry metrics on a configurable scheduler interval
FR2: The hot-path can detect consumer lag anomalies, throughput constrained anomalies, and volume drop anomalies across all monitored scopes
FR3: The hot-path can evaluate anomaly detection thresholds against per-scope statistical baselines computed from historical metric data, falling back to configured defaults when baseline history is insufficient
FR4: The hot-path can compute and persist per-scope metric baselines to Redis with environment-specific TTLs
FR5: The hot-path can load sustained window state from Redis before evidence evaluation and persist updated state after, enabling sustained anomaly tracking across cycles and pod restarts
FR6: The hot-path can batch Redis key loading operations instead of sequential per-key round-trips for sustained window state and peak profile retrieval
FR7: The hot-path can emit a TelemetryDegradedEvent when Prometheus is unavailable, propagating UNKNOWN evidence status through downstream stages
FR8: The hot-path can classify anomaly patterns as PEAK, NEAR_PEAK, or OFF_PEAK using cached peak profiles from Redis, replacing the previous always-UNKNOWN behavior
FR9: The hot-path can compute sustained anomaly status per scope using externalized Redis state shared across all hot-path replicas
FR10: The hot-path can parallelize sustained status computation across large scope key sets for performance at scale
FR11: The hot-path can manage peak profile historical window memory efficiently with bounded retention to control per-process memory footprint
FR12: The hot-path can load topology registry from a single YAML format (instances-based) located in `config/`
FR13: The hot-path can resolve stream identity, topic role (SOURCE_TOPIC/SHARED_TOPIC/SINK_TOPIC), and blast radius classification for each anomaly scope
FR14: The hot-path can route ownership through multi-level lookup: consumer group > topic > stream > platform default, with confidence scoring
FR15: The hot-path can reload the topology registry on file change without requiring process restart
FR16: The hot-path can identify downstream consumer impact for blast radius assessment
FR17: The hot-path can evaluate gates AG0 through AG6 sequentially, driven by YAML-defined check types and predicates dispatched through a handler registry
FR18: The hot-path can enforce environment-based action caps (local=OBSERVE, dev=NOTIFY, uat=TICKET, prod=PAGE) through AG1, with actions only capping downward, never escalating
FR19: The hot-path can enforce that PAGE is structurally impossible outside PROD+TIER_0 via post-condition safety assertions independent of YAML correctness
FR20: The hot-path can evaluate evidence sufficiency (AG2) with UNKNOWN evidence propagation — never collapsing missing evidence to PRESENT or zero
FR21: The hot-path can validate source topic classification (AG3) against topology-resolved topic roles
FR22: The hot-path can evaluate sustained threshold and confidence floor (AG4) using externalized sustained state
FR23: The hot-path can perform atomic action deduplication (AG5) using atomic set-if-not-exists with TTL as a single authoritative check, eliminating the two-step race condition
FR24: The hot-path can evaluate postmortem predicates (AG6) for qualifying cases during peak windows, now that peak classification produces real PEAK/NEAR_PEAK/OFF_PEAK states
FR25: The hot-path can produce an ActionDecisionV1 with full reason codes and gate evaluation trail for every triage decision
FR26: The hot-path can assemble a write-once CaseFileTriageV1 in object storage with SHA-256 hash chain, ensuring triage.json exists before any downstream event is published (Invariant A)
FR27: The hot-path can insert outbox rows with PENDING_OBJECT > READY state transitions, enforced by source-state-guarded transitions
FR28: The outbox-publisher can drain READY rows and publish CaseHeaderEventV1 and TriageExcerptV1 to Kafka with at-least-once delivery (Invariant B2)
FR29: The outbox-publisher can lock rows during selection to prevent concurrent publisher instances from publishing the same batch
FR30: The casefile-lifecycle runner can scan object storage and purge expired casefiles according to the retention policy
FR31: The system can stamp policy versions (rulebook, peak policy, denylist, anomaly detection policy) in every casefile for 25-month decision replay
FR32: The hot-path can trigger PagerDuty pages via Events V2 API for PAGE action decisions with action fingerprint as dedup key
FR33: The hot-path can send Slack notifications for NOTIFY actions, degraded-mode alerts, and postmortem candidacy notifications
FR34: The hot-path can fall back to structured log output when Slack is unavailable
FR35: The system can enforce denylist at all outbound boundaries before any external payload is dispatched
FR36: The cold-path can consume CaseHeaderEventV1 from Kafka as an independent consumer pod
FR37: The cold-path can retrieve full case context from S3, reconstruct triage excerpt and evidence summary from persisted casefile data
FR38: The cold-path can produce a deterministic text evidence summary rendering a case's evidence state for LLM consumption, distinguishing PRESENT/UNKNOWN/ABSENT/STALE evidence and including anomaly findings, temporal context, and topic role
FR39: The cold-path can invoke LLM diagnosis for every case regardless of environment, criticality tier, or sustained status
FR40: The cold-path can submit an enriched prompt including full Finding fields (severity, reason_codes, evidence_required, is_primary), topic_role, routing_key, anomaly family domain descriptions, confidence calibration guidance, fault domain examples, and a few-shot example
FR41: The cold-path can produce a schema-validated DiagnosisReportV1 with structured evidence citations, verdict, fault domain, confidence, next checks, and evidence gaps
FR42: The cold-path can produce a deterministic fallback report when LLM invocation fails (timeout, unavailability, schema validation failure)
FR43: The cold-path can write diagnosis.json to object storage with SHA-256 hash chain linking to triage.json
FR44: The hot-path can acquire a distributed cycle lock so only one pod executes per scheduler interval, with losers yielding and retrying next interval
FR45: The hot-path can fail open on Redis unavailability for cycle lock (preserving availability, worst case equals single-instance behavior)
FR46: The hot-path can assign scope-level shards to pods for findings cache coordination, with batch checkpoint per shard per interval replacing per-scope writes
FR47: The hot-path can recover shards from a failed pod via lease expiry, allowing another pod to safely resume
FR48: The system can enable distributed coordination incrementally via feature flag (DISTRIBUTED_CYCLE_LOCK_ENABLED, default false)
FR49: The system can load all policies from YAML at startup (rulebook, peak policy, anomaly detection policy, Redis TTL policy, Prometheus metrics contract, outbox policy, retention policy, denylist, topology registry)
FR50: The system can resolve environment configuration through environment-identifier-driven env file selection with environment variable override precedence
FR51: The system can validate Kafka SASL_SSL configuration at startup with fail-fast behavior for missing keytab or krb5 config paths
FR52: Operators can tune anomaly detection sensitivity, rulebook thresholds, peak policy, and denylist through versioned YAML changes without code modifications
FR53: Application teams can edit topology registry and denylist YAML, deploy to lower environments, verify behavior through casefile inspection, and promote to production
FR54: Each runtime mode pod can expose a health endpoint reporting component health registry status
FR55: The hot-path health endpoint can report distributed coordination state (lock holder status, lock expiry time, last cycle execution) as informational data that does not affect K8s probe health status
FR56: The system can export OTLP metrics for pipeline health (cycle completion, outbox delivery, gate evaluation latency, deduplication, coordination lock stats)
FR57: The system can emit structured logs with correlation IDs (case_id), pod identity (POD_NAME, POD_NAMESPACE), and consistent field naming for field-level querying in Elastic
FR58: The system can evaluate operational alert thresholds at runtime against live metric state

### NonFunctional Requirements

**Performance:**
NFR-P1: Hot-path gate evaluation completes in p99 <= 500ms per cycle
NFR-P2: Outbox delivery SLO: p95 <= 1 minute, p99 <= 5 minutes from READY to SENT
NFR-P3: Hot-path cycle completion rate: 100% of scheduled intervals execute (per-case errors are caught without killing the loop; cycle-level errors are caught and logged, loop continues)
NFR-P4: Cold-path LLM invocation timeout: 60 seconds maximum per case
NFR-P5: Batched Redis key loading reduces sustained-window state retrieval from O(N) sequential round-trips to O(1) batched calls at scale
NFR-P6: Sustained status computation completes within 50% of the scheduler interval duration across large scope key sets as measured by OTLP histogram
NFR-P7: Peak profile historical window memory footprint grows proportionally with scope count, bounded by configurable retention depth with maximum memory budget per scope

**Security:**
NFR-S1: Secrets (credentials, tokens, webhook URLs) are never emitted in structured logs — masking/redaction patterns enforced for all credential fields
NFR-S2: Denylist enforcement applied at every outbound boundary before external payloads (PagerDuty, Slack, ServiceNow, Kafka, LLM) via shared denylist enforcement function — no boundary-specific reimplementations
NFR-S3: Kafka SASL_SSL keytab and krb5 config paths validated at startup with fail-fast behavior — system does not start with missing or invalid security configuration
NFR-S4: ServiceNow MI-1 guardrails prevent major-incident write scope — system cannot create or modify major incidents
NFR-S5: Integration safety modes default to LOG — no external calls in local/dev unless explicitly configured to MOCK or LIVE
NFR-S6: Prod enforcement rejects MOCK/OFF for critical integrations — prevents accidental non-operational configuration in production

**Scalability:**
NFR-SC1: Hot-path supports hot/hot 2-pod minimum deployment with zero duplicate dispatches across replicas
NFR-SC2: Scope sharding supports even distribution across pods with O(1) checkpoint writes per shard per interval instead of O(N) per scope
NFR-SC3: Outbox publisher supports concurrent instances with row locking preventing duplicate Kafka publication
NFR-SC4: All coordination mechanisms (cycle lock, sustained state, AG5 dedupe) use Redis as the single shared state layer — no in-process state assumed exclusive

**Reliability:**
NFR-R1: DEAD outbox rows: standing posture of 0 — any DEAD row triggers operational alerting
NFR-R2: Write-once casefile invariant: triage.json exists in S3 before any downstream event is published to Kafka (Invariant A)
NFR-R3: Outbox guarantees at-least-once Kafka delivery — hot-path continues unaffected during Kafka unavailability, cases accumulate in Postgres (Invariant B2)
NFR-R4: Distributed cycle lock fails open on Redis unavailability — system degrades to single-instance equivalent behavior, never halts
NFR-R5: Sustained window state falls back to None on Redis failure — conservative behavior (treats as first observation, no false sustained=true)
NFR-R6: Critical dependency failures halt processing with loud failure — no silent fallback for invariant violations
NFR-R7: Degradable dependency failures update HealthRegistry, emit degraded events, and continue with capped behavior
NFR-R8: Cold-path LLM failure produces a deterministic fallback DiagnosisReportV1 — the absence of diagnosis.json is explicit and observable, never silent

**Auditability:**
NFR-A1: All casefiles retained for 25 months with write-once semantics and SHA-256 hash chains
NFR-A2: Every casefile stamps active policy versions (rulebook, peak policy, denylist, anomaly detection policy) at decision time
NFR-A3: Schema envelope versioning enables perpetual read support — old casefiles remain deserializable across the 25-month retention window as schemas evolve
NFR-A4: Structured logs carry correlation_id (case_id) enabling field-level querying of the complete decision trail per case in Elastic
NFR-A5: Gate evaluation trail with full reason codes persisted in ActionDecisionV1 for every triage decision
NFR-A6: Pod identity (POD_NAME, POD_NAMESPACE) stamped in OTLP resource attributes and structured logs for per-instance traceability across replicas

**Integration:**
NFR-I1: All external integrations implement OFF|LOG|MOCK|LIVE mode semantics consistently — no integration-specific mode behavior
NFR-I2: External integration failures in degradable mode (Slack, ServiceNow) do not block hot-path cycle execution
NFR-I3: PagerDuty deduplication uses action_fingerprint as dedup_key — duplicate pages for the same fingerprint within TTL are suppressed by PagerDuty
NFR-I4: Cold-path Kafka consumer commits offsets on graceful shutdown — no message loss or reprocessing beyond at-least-once semantics

**Process & Governance:**
PG1: Each CR must update affected documentation in `docs/` and `README.md` as part of the same change set, ensuring documentation accuracy for the operational deployment
PG2: All documentation must reference only project-native concepts — no references to BMAD artifacts, story identifiers, epic numbers, or workflow methodology terminology

### Additional Requirements

**Architecture — No Starter Template (Brownfield):**
- This is a post-implementation revision phase against a mature, delivered codebase (8 delivered epics). No starter template is needed — structure, dependencies, and coding patterns are established and stable.

**Architecture — Locked Technology Stack:**
- Python >=3.13 with asyncio; type annotations using Python 3.13 style
- Pydantic v2 (2.12.5) with frozen=True for all contract and policy models; pydantic-settings ~2.13.1
- PostgreSQL 16 via SQLAlchemy Core (2.0.47) — no ORM
- Redis 7.2 (redis 7.2.1) — caching, coordination, deduplication
- MinIO / S3-compatible via boto3 ~1.42 — write-once casefile stages
- Kafka via confluent-kafka 2.13.0 — outbox publication and cold-path consumption
- LangGraph 1.0.9 for cold-path LLM diagnosis orchestration
- OpenTelemetry SDK 1.39.1 + OTLP exporter; structlog 25.5.0
- pytest 9.0.2 + pytest-asyncio 1.3.0; testcontainers 4.14.1

**Architecture — Critical Decisions (D1, D13):**
- D1: Redis key namespace is flat prefix `aiops:{data_type}:{scope_key}` — all Redis consumers must follow this convention
- D13: Shared Redis connection pool across all consumers, sized for peak concurrent operations (configurable via REDIS_MAX_CONNECTIONS, default ~50)

**Architecture — Redis Ephemerality & Degradation (D2, D3):**
- D2: Redis is ephemeral by design — correctness never depends on Redis data surviving a restart; sources of truth are Postgres, S3, Kafka, Prometheus
- D3: Every Redis consumer must degrade gracefully per the degradation matrix: cycle lock → fail-open; sustained state → None; peak cache → UNKNOWN; baselines → cold-start defaults; AG5 dedupe → existing degraded behavior; findings cache → recompute; shard checkpoint → full-scope fallback

**Architecture — Isolated Rule Engine Package (D4):**
- D4: `rule_engine/` package has zero imports from pipeline/, integrations/, storage/, health/, or config/ — imports only from contracts/. Handler registry frozen at import time. All existing 36 test functions (60+ parametrized cases) must pass unmodified.

**Architecture — Distributed Coordination (D5, D7):**
- D5: Cycle lock protocol is `SET NX EX` with TTL = scheduler_interval + configurable margin (default 60s). No explicit unlock. Feature-flagged via DISTRIBUTED_CYCLE_LOCK_ENABLED (default false).
- D7: Outbox row locking uses `SELECT FOR UPDATE SKIP LOCKED` — one-line change to outbox/repository.py. No schema changes.

**Architecture — Cold-Path Chain (D8, D9, D6):**
- D8: Baseline computation runs as a periodic background task within the hot-path process (not a new pod). Pluggable collector protocol. Guarded against overlap with in-process boolean flag.
- D9: Evidence summary is a pure function (TriageExcerptV1 → str) with byte-identical stability guarantee. Deterministic ordering required for all fields.
- D6: Cold-path consumer uses confluent-kafka, sequential processing, thin adapter protocol for testability. Consumer group: `aiops-cold-path-diagnosis` on `aiops-case-header` topic.

**Architecture — Topology Simplification (D10):**
- D10: Topology v0 clean cut — remove all legacy flat-format parsing, format auto-detection, version negotiation, compatibility views, synthetic default injection, and all v0 test coverage in a single change. Topology YAML relocated to `config/topology-registry.yaml`.

**Architecture — Implementation Dependency Order:**
- Phase 1 (Foundation): CR-01 (Wire Redis) + CR-11 (Topology simplify) — CR-01 unblocks CR-03, CR-04, CR-05, CR-10
- Phase 2 (Core pipeline): CR-02 (DSL rulebook) + CR-03 (Unified baselines)
- Phase 3 (Multi-replica): CR-04 (Sharded cache) + CR-05 (Distributed hot/hot) + CR-10 (Redis bulk + memory)
- Phase 4 (Cold path): CR-06 (Evidence summary) → CR-07 (Cold-path consumer) → CR-08 (Remove criteria) + CR-09 (Prompt optimization)

**Documentation requirements per CR:**
- CR-01: `runtime-modes.md` (dependency matrix), `local-development.md` (runtime mode status)
- CR-02: `architecture-patterns.md` (gate evaluation pattern)
- CR-03: `runtime-modes.md` (baseline computation mechanism), policy file references
- CR-05: `architecture.md`, `deployment-guide.md`, `runtime-modes.md`, `README.md`
- CR-07: `runtime-modes.md`, `local-development.md`, `README.md`
- CR-11: `component-inventory.md`, `project-structure.md`, `README.md`

### FR Coverage Map

FR1: Epic 1 - Deterministic anomaly triage for responders
FR2: Epic 1 - Deterministic anomaly triage for responders
FR3: Epic 1 - Deterministic anomaly triage for responders
FR4: Epic 1 - Deterministic anomaly triage for responders
FR5: Epic 1 - Deterministic anomaly triage for responders
FR6: Epic 1 - Deterministic anomaly triage for responders
FR7: Epic 1 - Deterministic anomaly triage for responders
FR8: Epic 1 - Deterministic anomaly triage for responders
FR9: Epic 1 - Deterministic anomaly triage for responders
FR10: Epic 1 - Deterministic anomaly triage for responders
FR11: Epic 1 - Deterministic anomaly triage for responders
FR12: Epic 1 - Deterministic anomaly triage for responders
FR13: Epic 1 - Deterministic anomaly triage for responders
FR14: Epic 1 - Deterministic anomaly triage for responders
FR15: Epic 1 - Deterministic anomaly triage for responders
FR16: Epic 1 - Deterministic anomaly triage for responders
FR17: Epic 1 - Deterministic anomaly triage for responders
FR18: Epic 1 - Deterministic anomaly triage for responders
FR19: Epic 1 - Deterministic anomaly triage for responders
FR20: Epic 1 - Deterministic anomaly triage for responders
FR21: Epic 1 - Deterministic anomaly triage for responders
FR22: Epic 1 - Deterministic anomaly triage for responders
FR23: Epic 1 - Deterministic anomaly triage for responders
FR24: Epic 1 - Deterministic anomaly triage for responders
FR25: Epic 1 - Deterministic anomaly triage for responders
FR26: Epic 2 - Durable case artifacts and reliable action dispatch
FR27: Epic 2 - Durable case artifacts and reliable action dispatch
FR28: Epic 2 - Durable case artifacts and reliable action dispatch
FR29: Epic 2 - Durable case artifacts and reliable action dispatch
FR30: Epic 2 - Durable case artifacts and reliable action dispatch
FR31: Epic 2 - Durable case artifacts and reliable action dispatch
FR32: Epic 2 - Durable case artifacts and reliable action dispatch
FR33: Epic 2 - Durable case artifacts and reliable action dispatch
FR34: Epic 2 - Durable case artifacts and reliable action dispatch
FR35: Epic 2 - Durable case artifacts and reliable action dispatch
FR36: Epic 3 - LLM-enriched diagnosis on the cold path
FR37: Epic 3 - LLM-enriched diagnosis on the cold path
FR38: Epic 3 - LLM-enriched diagnosis on the cold path
FR39: Epic 3 - LLM-enriched diagnosis on the cold path
FR40: Epic 3 - LLM-enriched diagnosis on the cold path
FR41: Epic 3 - LLM-enriched diagnosis on the cold path
FR42: Epic 3 - LLM-enriched diagnosis on the cold path
FR43: Epic 3 - LLM-enriched diagnosis on the cold path
FR44: Epic 4 - Multi-replica coordination and throughput safety
FR45: Epic 4 - Multi-replica coordination and throughput safety
FR46: Epic 4 - Multi-replica coordination and throughput safety
FR47: Epic 4 - Multi-replica coordination and throughput safety
FR48: Epic 4 - Multi-replica coordination and throughput safety
FR49: Epic 5 - Policy-driven operations and observability
FR50: Epic 5 - Policy-driven operations and observability
FR51: Epic 5 - Policy-driven operations and observability
FR52: Epic 5 - Policy-driven operations and observability
FR53: Epic 5 - Policy-driven operations and observability
FR54: Epic 5 - Policy-driven operations and observability
FR55: Epic 5 - Policy-driven operations and observability
FR56: Epic 5 - Policy-driven operations and observability
FR57: Epic 5 - Policy-driven operations and observability
FR58: Epic 5 - Policy-driven operations and observability

## Epic List

### Epic 1: Deterministic Anomaly Triage for Responders
On-call engineers receive evidence-based, topology-aware, safety-gated triage decisions they can trust and act on immediately.
**FRs covered:** FR1, FR2, FR3, FR4, FR5, FR6, FR7, FR8, FR9, FR10, FR11, FR12, FR13, FR14, FR15, FR16, FR17, FR18, FR19, FR20, FR21, FR22, FR23, FR24, FR25

### Epic 2: Durable Case Artifacts and Reliable Action Dispatch
Teams get durable, auditable case records and dependable external action delivery (PagerDuty/Slack/Ticketing) without data loss.
**FRs covered:** FR26, FR27, FR28, FR29, FR30, FR31, FR32, FR33, FR34, FR35

### Epic 3: LLM-Enriched Diagnosis on the Cold Path
Operators receive structured, schema-validated diagnostic reports that enrich triage without blocking hot-path decisions.
**FRs covered:** FR36, FR37, FR38, FR39, FR40, FR41, FR42, FR43

### Epic 4: Multi-Replica Coordination and Throughput Safety
Platform operators run hot/hot deployments with safe coordination, controlled fail-open behavior, and no duplicate execution side effects.
**FRs covered:** FR44, FR45, FR46, FR47, FR48

### Epic 5: Policy-Driven Operations and Observability
SREs and maintainers can tune behavior via config/policies and verify runtime health through consistent telemetry and health reporting.
**FRs covered:** FR49, FR50, FR51, FR52, FR53, FR54, FR55, FR56, FR57, FR58

## Epic 1: Deterministic Anomaly Triage for Responders

On-call engineers receive evidence-based, topology-aware, safety-gated triage decisions they can trust and act on immediately.

### Story 1.1: Collect Telemetry and Detect Core Anomalies

As an on-call engineer,
I want hot-path telemetry collection and anomaly detection to run on schedule,
So that incident signals are detected early with explicit degraded evidence handling.

**Implements:** FR1, FR2, FR7

**Acceptance Criteria:**

**Given** the scheduler interval is configured and Prometheus is reachable
**When** the hot-path cycle executes
**Then** the pipeline queries Prometheus and evaluates lag, throughput-constrained, and volume-drop anomalies for each monitored scope
**And** findings are produced with evidence status that supports downstream gating.

**Given** Prometheus is unavailable or times out
**When** a cycle executes
**Then** a `TelemetryDegradedEvent` is emitted
**And** missing telemetry is represented as `UNKNOWN` evidence rather than coerced to present/zero values.

### Story 1.2: Persist and Reuse Redis Baselines and State in Bulk

As a platform operator,
I want baseline and sustained-state Redis interactions to be persisted and batch-loaded,
So that triage decisions remain consistent across cycles and perform at scale.

**Implements:** FR3, FR4, FR5, FR6

**Acceptance Criteria:**

**Given** historical metric windows are available
**When** baselines are computed for each scope/metric
**Then** baseline values are persisted to Redis using environment-specific TTL policy
**And** subsequent cycles read those persisted baselines before threshold evaluation.

**Given** sustained state and peak profile keys exist for many scopes
**When** the hot-path loads required Redis data
**Then** keys are fetched using batched operations rather than per-key sequential round trips
**And** the implementation follows the approved Redis key namespace convention.

### Story 1.3: Classify Peak and Sustained Conditions with Bounded Memory

As an on-call engineer,
I want peak-window and sustained-anomaly classification to be accurate and efficient,
So that severity decisions reflect real conditions without memory or latency regression.

**Implements:** FR8, FR9, FR10, FR11

**Acceptance Criteria:**

**Given** cached peak profile data is available
**When** anomaly findings are evaluated
**Then** each scope is classified as `PEAK`, `NEAR_PEAK`, or `OFF_PEAK`
**And** the previous always-`UNKNOWN` peak behavior is removed.

**Given** large scope sets are processed
**When** sustained status is computed
**Then** sustained evaluation is parallelized
**And** peak-profile retention is bounded to a configurable limit that constrains memory growth.

### Story 1.4: Resolve Topology, Ownership, and Blast Radius from Unified Registry

As an on-call engineer,
I want topology and ownership resolution to be automatic and reloadable,
So that action routing and impact assessment are immediately available in each triage result.

**Implements:** FR12, FR13, FR14, FR15, FR16

**Acceptance Criteria:**

**Given** the topology registry file in `config/` uses the single supported format
**When** the topology stage resolves a finding scope
**Then** stream identity, topic role, and blast-radius classification are resolved for that scope
**And** downstream impacted consumers are identified where applicable.

**Given** topology registry contents change on disk
**When** the loader detects file change
**Then** the hot-path reloads topology without process restart
**And** ownership routing uses ordered fallback `consumer_group > topic > stream > platform default` with confidence scoring.

### Story 1.5: Execute YAML Rulebook Gates AG0-AG3 via Isolated Rule Engine

As a platform operator,
I want early-stage deterministic gating to run from YAML-defined checks in an isolated engine,
So that safety-critical action reduction behavior is testable and policy-driven.

**Implements:** FR17, FR18, FR19, FR20, FR21

**Acceptance Criteria:**

**Given** rulebook gate definitions are loaded at startup
**When** gate evaluation starts
**Then** AG0 through AG3 are evaluated sequentially through the handler registry
**And** check type dispatch fails fast at startup if any configured type has no handler.

**Given** environment and tier caps apply
**When** AG1 evaluates the current action
**Then** action severity can only remain equal or be capped downward per environment policy
**And** post-condition safety assertions enforce that `PAGE` is impossible outside `PROD + TIER_0`.

### Story 1.6: Complete AG4-AG6, Atomic Deduplication, and Decision Trail Output

As an on-call engineer,
I want late-stage gating and decision outputs to be deterministic and auditable,
So that every action has reproducible evidence and reason codes.

**Implements:** FR22, FR23, FR24, FR25

**Acceptance Criteria:**

**Given** evidence, sustained state, and topology context are available
**When** AG4 through AG6 execute
**Then** sustained/confidence, atomic dedupe, and postmortem predicates are evaluated in sequence
**And** AG5 uses single-step atomic set-if-not-exists with TTL as the authoritative dedupe check.

**Given** a gate evaluation completes
**When** an action is finalized
**Then** the pipeline outputs `ActionDecisionV1` with full reason codes and gate trail
**And** unknown evidence semantics remain explicit end-to-end.

## Epic 2: Durable Case Artifacts and Reliable Action Dispatch

Teams get durable, auditable case records and dependable external action delivery (PagerDuty/Slack/Ticketing) without data loss.

### Story 2.1: Write Triage Casefiles with Hash Chain and Policy Stamps

As an SRE/platform engineer,
I want triage casefiles to be written once with integrity metadata,
So that every decision is auditable for long-term replay.

**Implements:** FR26, FR31

**Acceptance Criteria:**

**Given** a triage decision is produced
**When** casefile assembly runs
**Then** `triage.json` is written exactly once to object storage
**And** it includes SHA-256 chain metadata and active policy version stamps.

**Given** a downstream publish is attempted
**When** triage artifact existence is checked
**Then** downstream event publication is blocked unless `triage.json` already exists
**And** this enforces Invariant A in all runtime modes.

### Story 2.2: Enforce Outbox Source-State Transitions

As a platform operator,
I want outbox rows to move through guarded state transitions,
So that publish lifecycle is durable and recovery-safe.

**Implements:** FR27

**Acceptance Criteria:**

**Given** a casefile triage artifact is persisted
**When** outbox insertion occurs
**Then** rows are created in `PENDING_OBJECT` and transition to `READY` only through source-state-guarded operations
**And** invalid transitions are rejected.

**Given** policy/audit fields are required for replay
**When** outbox metadata is stored
**Then** required identifiers and version references are persisted for downstream consumers
**And** transition history remains queryable for diagnostics.

### Story 2.3: Publish READY Outbox Rows with Concurrency Safety

As an SRE/platform engineer,
I want concurrent outbox publishers to drain READY rows safely,
So that Kafka publication is at-least-once without duplicate batch claims.

**Implements:** FR28, FR29

**Acceptance Criteria:**

**Given** multiple publisher instances are running
**When** they select READY rows
**Then** selection uses row-level locking with `FOR UPDATE SKIP LOCKED`
**And** one row batch is claimed by only one publisher process.

**Given** a claimed READY row is processed
**When** publication to Kafka succeeds or fails
**Then** row state is updated consistently with at-least-once guarantees
**And** transient failures do not block hot-path processing.

### Story 2.4: Dispatch PagerDuty and Slack Actions with Denylist Safety

As an on-call engineer,
I want outbound action dispatch to be reliable and safe,
So that external notifications are delivered without leaking denied content.

**Implements:** FR32, FR33, FR34, FR35

**Acceptance Criteria:**

**Given** an action decision requires `PAGE` or `NOTIFY`
**When** dispatch executes
**Then** PagerDuty and Slack payloads are generated from decision context
**And** denylist filtering is applied before every outbound payload is sent.

**Given** Slack delivery fails or is unavailable
**When** a NOTIFY/degraded/postmortem message is attempted
**Then** the system emits an equivalent structured log event fallback
**And** the pipeline continues without halting.

### Story 2.5: Run Casefile Lifecycle Retention Purge

As a platform operator,
I want expired casefiles to be purged by lifecycle policy,
So that storage retention remains compliant and bounded.

**Implements:** FR30

**Acceptance Criteria:**

**Given** retention policy and object storage access are configured
**When** the casefile-lifecycle runner scans casefile objects
**Then** expired artifacts are identified and purged according to policy
**And** non-expired artifacts remain untouched.

**Given** purge execution completes
**When** operational metrics/logs are emitted
**Then** purge counts and failures are observable
**And** failures are surfaced for follow-up without silent data loss.

## Epic 3: LLM-Enriched Diagnosis on the Cold Path

Operators receive structured, schema-validated diagnostic reports that enrich triage without blocking hot-path decisions.

### Story 3.1: Implement Cold-Path Kafka Consumer Runtime Mode

As an SRE/platform engineer,
I want a dedicated cold-path consumer mode for case header events,
So that diagnosis processing is decoupled from hot-path execution.

**Implements:** FR36

**Acceptance Criteria:**

**Given** runtime mode is set to `cold-path`
**When** the service starts
**Then** it joins consumer group `aiops-cold-path-diagnosis` and subscribes to `aiops-case-header`
**And** processes messages sequentially through a testable consumer adapter abstraction.

**Given** shutdown is requested
**When** the consumer exits
**Then** offsets are committed gracefully before close
**And** health status reflects connected/lag/poll state transitions.

### Story 3.2: Reconstruct Case Context and Build Deterministic Evidence Summary

As an on-call engineer,
I want cold-path processing to reconstruct full context from persisted artifacts,
So that diagnosis input reflects authoritative triage evidence.

**Implements:** FR37, FR38

**Acceptance Criteria:**

**Given** a `CaseHeaderEventV1` is consumed
**When** cold-path retrieval executes
**Then** triage artifact context is read from object storage and reconstructed into the diagnosis input model
**And** reconstruction fails loudly on missing required artifact state.

**Given** triage excerpt data is available
**When** evidence summary rendering runs
**Then** output text is deterministic and byte-stable for identical inputs
**And** evidence statuses (`PRESENT`, `UNKNOWN`, `ABSENT`, `STALE`) are explicitly represented.

### Story 3.3: Invoke LLM for All Cases with Enriched Prompt and Schema Validation

As an operations responder,
I want every case to receive enriched diagnostic analysis,
So that follow-up troubleshooting starts with structured hypotheses and next checks.

**Implements:** FR39, FR40, FR41

**Acceptance Criteria:**

**Given** a cold-path case is ready for diagnosis
**When** prompt construction runs
**Then** prompt content includes full finding fields, topology/routing context, domain hints, and few-shot guidance
**And** invocation is performed regardless of environment, tier, or sustained flag.

**Given** the LLM returns a response
**When** diagnosis parsing executes
**Then** output is validated against `DiagnosisReportV1`
**And** invalid schema responses are treated as invocation failure conditions.

### Story 3.4: Persist Diagnosis Artifact with Fallback Guarantees

As an SRE/platform engineer,
I want diagnosis persistence to be resilient to model/provider failures,
So that every case produces an observable, auditable diagnosis outcome.

**Implements:** FR42, FR43

**Acceptance Criteria:**

**Given** LLM invocation succeeds
**When** diagnosis write executes
**Then** `diagnosis.json` is stored in object storage with hash-chain linkage to `triage.json`
**And** success metrics/logs include case correlation context.

**Given** LLM invocation times out, fails, or returns invalid schema
**When** cold-path fallback executes
**Then** a deterministic fallback diagnosis report is generated and persisted
**And** absence of primary diagnosis is explicit and observable.

## Epic 4: Multi-Replica Coordination and Throughput Safety

Platform operators run hot/hot deployments with safe coordination, controlled fail-open behavior, and no duplicate execution side effects.

### Story 4.1: Add Distributed Cycle Lock with Fail-Open Behavior

As an SRE/platform engineer,
I want only one hot-path pod to own each cycle interval when enabled,
So that multi-replica deployments avoid duplicate interval execution.

**Implements:** FR44, FR45

**Acceptance Criteria:**

**Given** `DISTRIBUTED_CYCLE_LOCK_ENABLED=true`
**When** a cycle starts across multiple pods
**Then** lock acquisition uses Redis `SET NX EX` with configured TTL margin
**And** non-holders yield that interval and retry on next scheduler tick.

**Given** Redis is unavailable during lock attempt
**When** cycle ownership cannot be resolved
**Then** hot-path fails open and executes cycle with degraded state
**And** degraded health/metrics are emitted without halting service.

### Story 4.2: Coordinate Scope Shards and Recover from Pod Failure

As a platform operator,
I want scope shard assignment and lease recovery for findings work,
So that distributed execution scales while remaining resilient to pod loss.

**Implements:** FR46, FR47

**Acceptance Criteria:**

**Given** multiple hot-path pods are active
**When** shard coordination is enabled
**Then** scope workloads are assigned per shard and checkpointed per interval
**And** checkpoint writes are batch-oriented rather than per-scope writes.

**Given** a pod holding shard responsibility fails
**When** lease expiry elapses
**Then** another pod can safely resume shard processing
**And** no manual intervention is required for recovery.

### Story 4.3: Roll Out Distributed Coordination Incrementally

As an SRE/platform engineer,
I want distributed coordination guarded by feature flag rollout controls,
So that production risk is minimized during activation.

**Implements:** FR48

**Acceptance Criteria:**

**Given** distributed coordination feature flag is disabled (default)
**When** hot-path cycles execute
**Then** behavior matches prior single-instance-compatible execution semantics
**And** no coordination lock requirements are imposed.

**Given** feature flag is enabled in controlled environments
**When** rollout verification runs
**Then** lock/yield/fail-open behaviors are observable and documented for operators
**And** enablement can be reversed without data migration or schema changes.

## Epic 5: Policy-Driven Operations and Observability

SREs and maintainers can tune behavior via config/policies and verify runtime health through consistent telemetry and health reporting.

### Story 5.1: Load and Validate Policies at Startup

As a platform operator,
I want all policy/config artifacts loaded and validated on startup,
So that runtime behavior is deterministic and fails fast on invalid configuration.

**Implements:** FR49, FR50

**Acceptance Criteria:**

**Given** policy files are present in `config/`
**When** application startup initializes configuration
**Then** rulebook, peak, anomaly-detection, Redis TTL, Prometheus contract, outbox, retention, denylist, and topology policies are loaded once
**And** startup fails fast on invalid schema or missing required policy artifacts.

**Given** environment configuration is supplied
**When** settings resolution executes
**Then** environment-specific configuration follows defined precedence and env file selection rules
**And** resolved environment identifier is available to downstream policy enforcement.

### Story 5.2: Enforce Security-Critical Integration Configuration

As an SRE/platform engineer,
I want integration security configuration validated before runtime,
So that deployments cannot start in insecure or unsupported states.

**Implements:** FR51

**Acceptance Criteria:**

**Given** Kafka SASL_SSL is configured
**When** startup validation runs
**Then** keytab and krb5 paths are validated with fail-fast behavior
**And** service startup is blocked on missing/invalid required security artifacts.

**Given** integration modes are configured per environment
**When** runtime mode enforcement applies
**Then** prod guardrails reject disallowed safety modes for critical integrations
**And** local/dev defaults remain safe and non-destructive unless explicitly overridden.

### Story 5.3: Enable Operator and Maintainer Policy Tuning Workflows

As an application maintainer,
I want to tune topology and denylist/policy configuration via YAML promotion flow,
So that behavior changes can be tested in lower environments before production.

**Implements:** FR52, FR53

**Acceptance Criteria:**

**Given** maintainers update topology or denylist/policy YAML files
**When** changes are deployed in lower environments
**Then** pipeline behavior reflects new configuration without code modifications
**And** outcomes are verifiable through casefile and structured telemetry inspection.

**Given** a validated configuration update
**When** promotion proceeds to production
**Then** policy version traces remain visible for audit/replay
**And** operational behavior remains consistent with documented configuration authority.

### Story 5.4: Expose Health, Metrics, and Runtime Alert Evaluation

As a platform operator,
I want comprehensive runtime health and observability signals,
So that I can detect issues quickly and validate system SLO behavior.

**Implements:** FR54, FR55, FR56, FR57, FR58

**Acceptance Criteria:**

**Given** any runtime mode pod is running
**When** `/health` is queried
**Then** component health registry state is returned
**And** hot-path includes coordination informational fields that do not alter K8s probe pass/fail semantics.

**Given** cycles and dispatch activity execute
**When** telemetry/log emission occurs
**Then** OTLP metrics for pipeline health are exported and structured logs include `case_id`, `pod_name`, and `pod_namespace`
**And** operational alert thresholds are evaluated against live metric state with observable status updates.
