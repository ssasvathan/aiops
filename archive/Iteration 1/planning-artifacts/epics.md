---
stepsCompleted: [step-01-validate-prerequisites, step-02-design-epics]
inputDocuments:
  - artifact/planning-artifacts/prd/index.md
  - artifact/planning-artifacts/prd/functional-requirements.md
  - artifact/planning-artifacts/prd/non-functional-requirements.md
  - artifact/planning-artifacts/prd/domain-specific-requirements.md
  - artifact/planning-artifacts/prd/event-driven-aiops-platform-specific-requirements.md
  - artifact/planning-artifacts/prd/project-scoping-phased-development.md
  - artifact/planning-artifacts/prd/user-journeys.md
  - artifact/planning-artifacts/prd/success-criteria.md
  - artifact/planning-artifacts/prd/executive-summary.md
  - artifact/planning-artifacts/prd/product-scope.md
  - artifact/planning-artifacts/prd/innovation-novel-patterns.md
  - artifact/planning-artifacts/prd/open-items-deferred-design-decisions.md
  - artifact/planning-artifacts/prd/glossary-terminology.md
  - artifact/planning-artifacts/architecture.md
---

# aiOps - Epic Breakdown

## Overview

This document provides the complete epic and story breakdown for aiOps, decomposing the requirements from the PRD and Architecture into implementable stories.

## Requirements Inventory

### Functional Requirements

**Evidence Collection & Processing (FR1-FR8)**

FR1: The system can collect Prometheus metrics at 5-minute evaluation intervals using canonical metric names from prometheus-metrics-contract-v1
FR2: The system can detect three anomaly patterns: consumer lag buildup, throughput-constrained proxy, and volume drop
FR3: The system can compute peak/near-peak classification per (env, cluster_id, topic) against historical baselines (p90/p95 of messages-in rate)
FR4: The system can compute sustained status (5 consecutive anomalous buckets) for each anomaly
FR5: The system can map missing Prometheus series to EvidenceStatus=UNKNOWN (never treated as zero) and propagate UNKNOWN through peak, sustained, and confidence computations
FR6: The system can produce an evidence_status_map for each case mapping evidence primitives to PRESENT/UNKNOWN/ABSENT/STALE
FR7: The system can cache evidence windows, peak profiles, and per-interval findings in Redis with environment-specific TTLs per redis-ttl-policy-v1
FR8: Each Finding can declare its own evidence_required[] list (no central required-evidence registry)

**Topology & Ownership (FR9-FR16)**

FR9: The system can load topology registry in both v0 (legacy) and v1 (instances-based) formats and canonicalize to a single in-memory model
FR10: The system can resolve stream_id, topic_role, criticality_tier, and source_system from topology registry given an anomaly key (env, cluster_id, topic/group)
FR11: The system can compute blast radius classification (LOCAL_SOURCE_INGESTION vs SHARED_KAFKA_INGESTION) based on topic_role
FR12: The system can identify downstream components as AT_RISK with exposure_type (DOWNSTREAM_DATA_FRESHNESS_RISK, DIRECT_COMPONENT_RISK, VISIBILITY_ONLY)
FR13: The system can route cases to the correct owning team using multi-level ownership lookup: consumer_group_owner -> topic_owner -> stream_default_owner -> platform_default
FR14: The system can scope topic_index by (env, cluster_id) to prevent cross-cluster collisions
FR15: The system can validate registry on load: fail-fast on duplicate topic_index keys, duplicate consumer-group ownership keys, or missing routing_key references
FR16: The system can provide backward-compatible compat views for legacy consumers during v0->v1 migration

**CaseFile Management (FR17-FR21)**

FR17: The system can assemble a CaseFile triage stage (triage.json) containing: evidence snapshot, gating inputs (GateInput.v1 fields), ActionDecision.v1, policy version stamps, and SHA-256 content hash
FR18: The system can write CaseFile triage.json to object storage as a write-once artifact before any Kafka header publish (Invariant A)
FR19: The system can write additional CaseFile stage files (diagnosis, linkage, labels) to the same case directory without mutating prior stage files, preserving hash integrity chain across stages
FR20: The system can enforce data minimization: no PII, credentials, or secrets in CaseFiles; sensitive fields redacted per exposure denylist
FR21: The system can enforce CaseFile retention (25 months prod) via automated lifecycle policies with auditable purge operations

**Event Publishing & Durability (FR22-FR26)**

FR22: The system can publish CaseHeaderEvent.v1 + TriageExcerpt.v1 to Kafka via Postgres durable outbox after CaseFile triage.json write is confirmed
FR23: The outbox can manage state transitions: PENDING_OBJECT -> READY -> SENT (+ RETRY, DEAD) with publish-after-crash guarantee (Invariant B2)
FR24: The system can enforce that hot-path consumers receive only header/excerpt — no object-store reads required for routing/paging decisions
FR25: The system can enforce exposure denylist on TriageExcerpt: no sensitive sink endpoints, credentials, restricted hostnames, or Ranger access groups
FR26: The system can retain outbox records per outbox-policy-v1: SENT (14d prod), DEAD (90d prod), PENDING/READY/RETRY until resolved

**Action Gating & Safety (FR27-FR35)**

FR27: The system can evaluate GateInput.v1 through Rulebook gates AG0-AG6 sequentially and produce an ActionDecision.v1
FR28: The system can cap actions by environment per AG1: local=OBSERVE, dev=NOTIFY, uat=TICKET, prod=PAGE eligible
FR29: The system can cap actions by criticality tier in prod per AG1: TIER_0=PAGE eligible, TIER_1=TICKET, TIER_2/UNKNOWN=NOTIFY
FR30: The system can deny PAGE for SOURCE_TOPIC anomalies per AG3; final_action caps to TICKET or lower
FR31: The system can evaluate finding-declared evidence_required[] per AG2; insufficient evidence downgrades action
FR32: The system can require sustained=true and confidence>=0.6 for PAGE/TICKET actions per AG4
FR33: The system can deduplicate actions by action_fingerprint with TTLs per action type (PAGE 120m, TICKET 240m, NOTIFY 60m) per AG5
FR34: The system can detect dedupe store (Redis) unavailability and cap to NOTIFY-only per AG5 degraded mode
FR35: The system can evaluate PM_PEAK_SUSTAINED predicate (peak && sustained && TIER_0 in PROD) for selective postmortem obligation per AG6

**Diagnosis & Intelligence (FR36-FR42, FR66)**

FR36: The system can invoke LLM diagnosis on the cold path (non-blocking) consuming TriageExcerpt + structured evidence summary to produce DiagnosisReport.v1
FR37: The LLM can produce structured DiagnosisReport output: verdict, fault_domain, confidence, evidence_pack, next_checks, gaps
FR38: The LLM can cite evidence IDs/references and explicitly propagate UNKNOWN for missing evidence
FR39: The system can fall back to a schema-valid DiagnosisReport when LLM is unavailable/timeout/error
FR40: The system can validate LLM output against DiagnosisReport schema; invalid output triggers deterministic fallback
FR41: The system can run in LLM stub/failure-injection mode for local and test use; LLM must run LIVE in prod
FR42: The system can conditionally invoke LLM based on case criteria (environment=PROD, tier=TIER_0, state=sustained)
FR66: The system can execute CaseFile triage write, outbox publish, Rulebook gating, and action execution without waiting on LLM diagnosis completion

**Notification & Action Execution (FR43-FR50)**

FR43: The system can send PAGE triggers to PagerDuty with stable pd_incident_id
FR44: The system can send SOFT postmortem enforcement notifications to Slack/log when PM_PEAK_SUSTAINED fires (Phase 1A)
FR45: The system can emit structured NotificationEvent to logs (JSON) when Slack is not configured
FR46: The system can search for PD-created SN Incidents using tiered correlation: Tier 1 -> Tier 2 -> Tier 3 (Phase 1B)
FR47: The system can create/update SN Problem + PIR tasks idempotently via external_id keying (Phase 1B)
FR48: The system can retry SN linkage with exponential backoff + jitter over 2-hour window (Phase 1B)
FR49: The system can track SN linkage state: PENDING -> SEARCHING -> LINKED or FAILED_FINAL (Phase 1B)
FR50: The system can track Tier 1 vs Tier 2/3 SN correlation fallback rates as Prometheus metrics (Phase 1B)

**Operability & Monitoring (FR51-FR54, FR67)**

FR51: The system can emit DegradedModeEvent to logs and Slack when Redis is unavailable
FR52: The system can monitor and alert on outbox health: PENDING_OBJECT age, READY age, RETRY age, DEAD count
FR53: The system can measure outbox delivery SLO: p95 <= 1 min, p99 <= 5 min
FR54: The system can enforce DEAD=0 prod posture as a standing operational requirement
FR67a: The system can emit TelemetryDegradedEvent when Prometheus is unavailable; pipeline caps actions to OBSERVE/NOTIFY
FR67b: The system can guarantee that no automated process creates Major Incident (MI) objects in ServiceNow (MI-1 posture)

### NonFunctional Requirements

**Performance (NFR-P1a through NFR-P6)**

NFR-P1a: Compute latency — Prometheus query start -> CaseFile triage.json written: p95 <= 30s, p99 <= 60s
NFR-P1b: Delivery latency (Outbox SLO) — CaseFile triage write -> Kafka header published: p95 <= 1min, p99 <= 5min
NFR-P1c: Action dispatch latency — Kafka header observed -> PD trigger/Slack/log: tracked, no hard SLO initially
NFR-P2: Evaluation interval adherence — 5-min intervals aligned to wall-clock, drift <= 30s
NFR-P3: Rulebook gating latency — GateInput.v1 -> ActionDecision.v1: p99 <= 500ms
NFR-P4: LLM cold-path response bound — LLM invocation timeout <= 60s, fallback on exceed
NFR-P5: Registry lookup latency — Topology resolution: p99 <= 50ms, reload <= 5s
NFR-P6: Concurrent case throughput — >= 100 concurrent active cases per evaluation interval

**Security (NFR-S1 through NFR-S8)**

NFR-S1: Encryption in transit — TLS 1.2+ for all network communication (plaintext OK for local docker-compose)
NFR-S2: Encryption at rest — SSE for CaseFiles, encrypted volumes for Postgres, TLS for Redis in prod
NFR-S3: CaseFile access control — restricted to pipeline service accounts (rw), audit users (ro), lifecycle management
NFR-S4: Integration credential management — secrets manager/mounted secrets, never in config/CaseFiles/logs
NFR-S5: Exposure denylist enforcement coverage — applied at every output boundary, zero violations target
NFR-S6: Audit log completeness — all SN/PD/Slack/CaseFile/outbox operations logged with full context, 90-day retention
NFR-S7: No privilege escalation via configuration — mode changes require deployment, not runtime toggle
NFR-S8: LLM data handling — denylist on inputs/outputs, bank-sanctioned endpoints, no training on data

**Reliability (NFR-R1 through NFR-R5)**

NFR-R1: Pipeline continuity — Redis/LLM/Slack/SN failures: continue with degraded behavior
NFR-R2: Critical path failure = stop — Object Storage/Postgres/Kafka/Prometheus unavailable: halt or cap
NFR-R3: Recovery behavior — component-specific recovery semantics (Redis rebuild, outbox resume, etc.)
NFR-R4: DEAD=0 prod posture — any DEAD outbox row is critical, requires human investigation
NFR-R5: Data durability — CaseFile and outbox survive single-node failures (infrastructure-level)

**Operability (NFR-O1 through NFR-O6)**

NFR-O1: Meta-monitoring — expose health metrics for outbox, Redis, LLM, Evidence Builder, Prometheus, pipeline
NFR-O2: Alerting thresholds defined — outbox age, DEAD>0, Redis loss, Prometheus unavailability, LLM errors, interval drift
NFR-O3: Structured logging — JSON with consistent fields: timestamp, correlation_id, component, event_type, severity
NFR-O4: Configuration transparency — active config logged at startup and queryable at runtime
NFR-O5: Deployment independence — each phase independently deployable, cold-path independently restartable
NFR-O6: Graceful shutdown — complete in-flight cycles, flush outbox, log shutdown state

**Testability & Auditability (NFR-T1 through NFR-T6)**

NFR-T1: Decision reproducibility — historical gating decisions reproducible from CaseFile + policy versions
NFR-T2: Invariant verification — automated tests for Invariant A, B2, UNKNOWN propagation, denylist, TelemetryDegradedEvent
NFR-T3: LLM degradation testing — stub/failure-injection/timeout/malformed output testing
NFR-T4: Storm-control simulation — Redis failure, rapid duplicates, rapid recovery tests
NFR-T5: End-to-end pipeline test — full hot-path locally via docker-compose, zero external dependencies
NFR-T6: Audit trail completeness verification — CaseFile contains all evidence, gates, policies, hash

### Additional Requirements

**From Architecture — Starter Template (impacts Epic 1 Story 1):**

- Project initialization using `uv init --python 3.13 --package --name aiops-triage-pipeline`
- Python 3.13, uv 0.10.6, Ruff ~0.15.x, pytest 9.0.2, structlog 25.5.0
- Full technology stack pinned: confluent-kafka 2.13.0, SQLAlchemy 2.0.47, Pydantic v2 2.12.5, redis-py 7.2.1, boto3 ~1.42, opentelemetry-sdk 1.39.1, LangGraph 1.0.9, pydantic-settings ~2.13.1, psycopg[c] 3.3.3, pytest-asyncio 1.3.0, testcontainers 4.14.1

**From Architecture — Data Architecture Decisions:**

- SQLAlchemy Core (not full ORM) for outbox — precise transactional control
- Hand-rolled DDL (not Alembic) — single-table outbox, stable schema
- Object storage layout: cases/{case_id}/{stage}.json (named stage files, no env prefix)
- Redis key design: prefix by purpose (evidence:/peak:/dedupe:), no env prefix

**From Architecture — Security & Secrets:**

- Environment variables via pydantic-settings; Kerberos file path validation at startup
- Exposure denylist as versioned YAML, frozen Pydantic model, single shared apply_denylist() function enforced at 4 output boundaries

**From Architecture — Pipeline Communication & Serialization:**

- Direct Pydantic model passing in-memory between hot path stages
- Validate at creation (frozen=True) + re-validate on deserialization from external sources
- JSON with Pydantic .model_dump_json() on Kafka, no schema registry
- CaseFile stages as Pydantic JSON, SHA-256 hash for tamper-evidence, invariant test assertion

**From Architecture — Pipeline Orchestration:**

- Scheduler + asyncio.TaskGroup concurrent pipeline on 5-min wall-clock cadence
- Fire-and-forget async LangGraph cold path, registered with HealthRegistry, in-flight gauge metric
- Centralized HealthRegistry (asyncio-safe) + OpenTelemetry SDK with OTLP to Dynatrace
- OTLP Collector stub in testcontainers for integration tests

**From Architecture — Infrastructure & Deployment:**

- Single Docker image, multiple entrypoints (--mode hot-path|cold-path|outbox-publisher)
- docker-compose Mode A: Kafka+ZooKeeper, Postgres, Redis, MinIO, Prometheus
- APP_ENV selects .env.{APP_ENV} config file
- CI/CD deferred, codebase structured CI-ready
- 12 frozen contracts constraining the design space
- Implementation sequence: init -> contracts -> config -> denylist -> HealthRegistry -> data layer -> hot path -> cold path -> outbox publisher -> OTLP -> docker-compose -> integration tests

**From Architecture — Cross-Cutting Concerns:**

- Exposure denylist enforcement at every output boundary (4 boundaries)
- UNKNOWN-not-zero propagation through every evidence layer
- Policy version stamping on every CaseFile
- Integration mode abstraction (OFF/LOG/MOCK/LIVE) for all 9 external integrations
- Degraded-mode safety with per-component strategies
- Storm control via dedupe + degraded-mode caps
- Structured logging with case_id correlation
- Meta-monitoring (observability of the observer)

**From PRD — Phased Development:**

- Phase 0: Validation Harness (proves signals are real)
- Phase 1A: MVP Triage Pipeline (full hot path + cold-path LLM)
- Phase 1B: ServiceNow Integration (tiered correlation + idempotent upsert)
- Phase 2: Better Evidence + Triage Quality (advisory ML, labeling loop)
- Phase 3: Hybrid Topology + Sink Health
- Dependencies: Phase 0 -> 1A -> 1B -> 2 -> 3

**From PRD — Domain-Specific Requirements:**

- Audit trail completeness (25-month retention, decision traceability)
- MI-1 posture (no automated Major Incident creation)
- Evidence integrity & immutability (write-once, SHA-256, policy version stamps)
- Data minimization & privacy (no PII/secrets, sensitive field redaction, store only necessary evidence)
- Policy governance & change management (versioned artifacts, approval gates)
- LLM role boundaries (bounded role, provenance-aware, exposure-capped, non-blocking, cost-controlled, schema-safe)

### FR Coverage Map

FR1: Epic 2 - Prometheus metric collection at 5-min intervals
FR2: Epic 2 - Three anomaly pattern detection (lag, constrained proxy, volume drop)
FR3: Epic 2 - Peak/near-peak classification per (env, cluster_id, topic)
FR4: Epic 2 - Sustained status computation (5 consecutive anomalous buckets)
FR5: Epic 2 - Missing Prometheus series -> UNKNOWN propagation
FR6: Epic 2 - Evidence_status_map per case (PRESENT/UNKNOWN/ABSENT/STALE)
FR7: Epic 2 - Redis caching with environment-specific TTLs
FR8: Epic 2 - Finding-declared evidence_required[] lists
FR9: Epic 3 - Topology registry loader (v0 + v1 formats)
FR10: Epic 3 - Stream_id, topic_role, criticality_tier resolution
FR11: Epic 3 - Blast radius classification
FR12: Epic 3 - Downstream AT_RISK identification
FR13: Epic 3 - Multi-level ownership routing lookup
FR14: Epic 3 - Topic_index scoped by (env, cluster_id)
FR15: Epic 3 - Registry validation (fail-fast on duplicates/missing refs)
FR16: Epic 3 - Backward-compatible compat views for v0->v1 migration
FR17: Epic 4 - CaseFile triage stage assembly
FR18: Epic 4 - Write-once CaseFile to object storage (Invariant A)
FR19: Epic 4 - Append-only CaseFile stage files with hash integrity chain
FR20: Epic 4 - Data minimization enforcement (no PII/secrets)
FR21: Epic 4 - CaseFile retention (25 months prod) with auditable purge
FR22: Epic 4 - Kafka publish via Postgres durable outbox
FR23: Epic 4 - Outbox state transitions (PENDING_OBJECT -> READY -> SENT + RETRY, DEAD)
FR24: Epic 4 - Hot-path header/excerpt only (no object-store reads)
FR25: Epic 4 - Exposure denylist on TriageExcerpt
FR26: Epic 4 - Outbox record retention per outbox-policy-v1
FR27: Epic 5 - Rulebook gates AG0-AG6 sequential evaluation
FR28: Epic 5 - Environment action caps (local=OBSERVE, dev=NOTIFY, uat=TICKET, prod=PAGE)
FR29: Epic 5 - Criticality tier caps in prod (TIER_0=PAGE, TIER_1=TICKET, TIER_2/UNKNOWN=NOTIFY)
FR30: Epic 5 - SOURCE_TOPIC PAGE denial (AG3)
FR31: Epic 5 - Evidence sufficiency evaluation (AG2)
FR32: Epic 5 - Sustained + confidence threshold for PAGE/TICKET (AG4)
FR33: Epic 5 - Action deduplication by fingerprint with TTLs (AG5)
FR34: Epic 5 - Redis unavailability -> NOTIFY-only cap (AG5 degraded)
FR35: Epic 5 - PM_PEAK_SUSTAINED postmortem predicate (AG6)
FR36: Epic 6 - Cold-path LLM diagnosis invocation
FR37: Epic 6 - Structured DiagnosisReport output
FR38: Epic 6 - Evidence citation + UNKNOWN propagation in LLM output
FR39: Epic 6 - Deterministic fallback DiagnosisReport
FR40: Epic 6 - LLM output schema validation
FR41: Epic 6 - LLM stub/failure-injection mode (local/test only)
FR42: Epic 6 - Conditional LLM invocation criteria
FR43: Epic 5 - PagerDuty PAGE triggers with stable pd_incident_id
FR44: Epic 5 - SOFT postmortem enforcement via Slack/log
FR45: Epic 5 - Structured NotificationEvent to logs fallback
FR46: Epic 8 - Tiered SN Incident correlation (Tier 1 -> 2 -> 3)
FR47: Epic 8 - Idempotent SN Problem + PIR task upsert
FR48: Epic 8 - SN linkage retry with exponential backoff + jitter
FR49: Epic 8 - SN linkage state tracking
FR50: Epic 8 - SN correlation fallback rate metrics
FR51: Epic 5 - DegradedModeEvent emission on Redis unavailability
FR52: Epic 7 - Outbox health monitoring and alerting
FR53: Epic 7 - Outbox delivery SLO measurement
FR54: Epic 7 - DEAD=0 prod posture enforcement
FR55: Epic 1 - Local end-to-end via docker-compose (Mode A)
FR56: Epic 1 - Optional remote environment connection (Mode B)
FR57: Epic 1 - Integration OFF/LOG/MOCK/LIVE mode configuration
FR58: Epic 1 - Harness traffic generation (Phase 0)
FR59: Epic 1 - Local durability invariant validation (MinIO + Postgres)
FR60: Epic 7 - Policy version stamping in CaseFiles
FR61: Epic 7 - Historical decision reproducibility
FR62: Epic 7 - Exposure denylist as versioned reviewable artifact
FR63: Epic 7 - Case labeling support (schema from Phase 1A, workflow Phase 2)
FR64: Epic 7 - Label data quality validation (Phase 2 workflow)
FR65: Epic 7 - LLM narrative exposure denylist compliance
FR66: Epic 6 - Hot-path independence from LLM (non-blocking)
FR67a: Epic 2 - TelemetryDegradedEvent on Prometheus unavailability
FR67b: Epic 7 - MI-1 posture (no automated MI creation)

## Epic List

### Epic 1: Project Foundation & Developer Experience
Developers can initialize, build, and run the aiOps pipeline locally with all foundational infrastructure, frozen contracts, configuration, and docker-compose topology in place.
**FRs covered:** FR55, FR56, FR57, FR58, FR59
**Phase alignment:** Phase 0 foundation

## Epic 1: Project Foundation & Developer Experience

Developers can initialize, build, and run the aiOps pipeline locally with all foundational infrastructure, frozen contracts, configuration, and docker-compose topology in place.

### Story 1.1: Project Initialization & Repository Structure

As a platform developer,
I want a properly initialized Python project with all dependencies pinned and the canonical directory structure in place,
So that all subsequent development has a consistent, reproducible foundation.

**Acceptance Criteria:**

**Given** a clean repository
**When** the project is initialized with `uv init --python 3.13 --package --name aiops-triage-pipeline`
**Then** the `pyproject.toml` contains all pinned dependencies (confluent-kafka 2.13.0, SQLAlchemy 2.0.47, Pydantic v2 2.12.5, redis-py 7.2.1, boto3 ~1.42, opentelemetry-sdk 1.39.1, LangGraph 1.0.9, pydantic-settings ~2.13.1, psycopg[c] 3.3.3, pytest 9.0.2, pytest-asyncio 1.3.0, testcontainers 4.14.1, structlog 25.5.0, Ruff ~0.15.x)
**And** the `src/` layout follows the architecture-defined directory structure with hot_path, cold_path, outbox, contracts, config, and shared packages
**And** `uv run ruff check` passes with zero errors
**And** `uv run pytest` executes successfully (placeholder test passes)
**And** a Dockerfile exists with `--mode` entrypoint supporting hot-path, cold-path, and outbox-publisher modes

### Story 1.2: Event Contract Models

As a platform developer,
I want the 5 frozen event contracts defined as immutable Pydantic models,
So that every pipeline stage shares a single source of truth for event data structures and schema validation is enforced at creation and deserialization boundaries.

**Acceptance Criteria:**

**Given** the contracts package exists
**When** the 5 event contracts are implemented as Pydantic `frozen=True` models
**Then** the following event contracts exist: CaseHeaderEvent.v1, TriageExcerpt.v1, GateInput.v1, ActionDecision.v1, DiagnosisReport.v1
**And** attempting to mutate any field on a frozen model raises a `ValidationError`
**And** `model_dump_json()` produces valid JSON and `model_validate_json()` round-trips successfully for each contract
**And** each contract includes a `schema_version` field
**And** unit tests verify immutability, serialization round-trip, and schema validation for all 5 event contracts

### Story 1.3: Policy & Operational Contract Models

As a platform developer,
I want the 7 frozen policy and operational contracts defined as immutable Pydantic models,
So that policy versioning, TTL configuration, and operational rules are enforced consistently across the pipeline.

**Acceptance Criteria:**

**Given** the contracts package exists with event contracts from Story 1.2
**When** the 7 policy contracts are implemented as Pydantic `frozen=True` models
**Then** the following policy contracts exist: rulebook-v1, peak-policy-v1, prometheus-metrics-contract-v1, redis-ttl-policy-v1, outbox-policy-v1, servicenow-linkage-contract-v1, local-dev-no-external-integrations-contract-v1, topology-registry-loader-rules-v1
**And** attempting to mutate any field on a frozen model raises a `ValidationError`
**And** `model_dump_json()` produces valid JSON and `model_validate_json()` round-trips successfully for each contract
**And** each contract includes a `schema_version` field
**And** unit tests verify immutability, serialization round-trip, and schema validation for all 7 policy contracts

### Story 1.4: Configuration & Environment Management

As a platform developer,
I want environment-aware configuration with per-integration mode controls,
So that the pipeline loads the correct settings per environment and every outbound integration can be independently set to OFF/LOG/MOCK/LIVE mode (FR57).

**Acceptance Criteria:**

**Given** `APP_ENV` is set to `local`, `dev`, `uat`, or `prod`
**When** the application starts
**Then** `pydantic-settings` loads the corresponding `.env.{APP_ENV}` configuration file
**And** direct environment variables override `.env` file values (K8s injection precedence)
**And** per-integration mode variables are available: `INTEGRATION_MODE_{PD|SLACK|SN|LLM}` defaulting to LOG
**And** environment action caps are enforced: local=OBSERVE, dev=NOTIFY, uat=TICKET, prod=PAGE eligible
**And** `.env.local` and `.env.dev` are committed (no secrets), `.env.uat.template` and `.env.prod.template` exist as templates
**And** when `KAFKA_SECURITY_PROTOCOL=SASL_SSL`, startup validates that `KAFKA_KERBEROS_KEYTAB_PATH` and `KRB5_CONF_PATH` reference existing files; missing files cause fail-fast at boot
**And** active configuration is logged at startup per NFR-O4
**And** unit tests verify config loading, precedence, and startup validation

### Story 1.5: Exposure Denylist Foundation

As a platform developer,
I want a versioned exposure denylist loaded from YAML with a single shared enforcement function,
So that sensitive fields are consistently redacted at all 4 output boundaries (TriageExcerpt, Slack, SN, LLM narrative) with zero reimplementation.

**Acceptance Criteria:**

**Given** a versioned YAML denylist file exists in the repository
**When** the application starts
**Then** the denylist is loaded into a `frozen=True` Pydantic model with a `denylist_version` field
**And** a single `apply_denylist(fields: dict, denylist: DenylistModel) -> dict` function is available
**And** `apply_denylist` removes/redacts fields matching denylist patterns (sensitive sink endpoints, credentials, restricted hostnames, Ranger access groups)
**And** the function returns a clean dict with no denied fields present
**And** `denylist_version` is accessible for stamping into CaseFiles
**And** unit tests verify: denied fields are removed, non-denied fields pass through, empty input returns empty output, denylist version is captured

### Story 1.6: HealthRegistry & Degraded Mode Foundation

As an SRE/operator,
I want a centralized health registry that tracks per-component status and coordinates degraded-mode behavior,
So that the pipeline can safely degrade when individual components fail and I can query system health via a /health endpoint.

**Acceptance Criteria:**

**Given** the HealthRegistry singleton is initialized
**When** a component reports status change (HEALTHY/DEGRADED/UNAVAILABLE)
**Then** the registry updates that component's status using asyncio-safe primitives (no threading locks)
**And** pipeline stages can query the registry to apply degraded-mode caps (e.g., Redis DEGRADED -> NOTIFY-only)
**And** a lightweight `/health` HTTP endpoint returns current component statuses as JSON
**And** `DegradedModeEvent` is emittable when a component transitions to DEGRADED/UNAVAILABLE (containing: affected scope, reason, capped action level, estimated impact window)
**And** `TelemetryDegradedEvent` is emittable when Prometheus is unavailable (containing: affected scope, reason, recovery status)
**And** unit tests verify: status transitions, concurrent access safety, degraded-mode query behavior, event emission

### Story 1.7: Structured Logging Foundation

As a platform developer,
I want structured JSON logging with correlation_id propagation,
So that all pipeline events are consistently formatted and traceable across components per NFR-O3.

**Acceptance Criteria:**

**Given** structlog is configured as the logging framework
**When** any pipeline component emits a log event
**Then** the output is structured JSON with consistent fields: timestamp, correlation_id (case_id when available), component, event_type, severity
**And** log levels are used correctly: ERROR for failures requiring attention, WARN for degraded behavior, INFO for normal processing, DEBUG for diagnostic detail
**And** correlation_id propagates through async contexts (asyncio task-local)
**And** a logging factory/helper is available for components to create properly configured loggers
**And** unit tests verify: JSON output format, field presence, correlation_id propagation, log level filtering

### Story 1.8: Local Development Environment (docker-compose)

As a platform developer,
I want a complete local development environment via docker-compose,
So that I can run the full pipeline end-to-end locally with zero external integration calls (FR55) and validate durability invariants against real infrastructure (FR59).

**Acceptance Criteria:**

**Given** docker-compose is available on the developer's machine
**When** `docker-compose up` is executed
**Then** the following services are running: Kafka + ZooKeeper, Postgres, Redis, MinIO, Prometheus
**And** the pipeline application can connect to all local services using `.env.local` configuration
**And** MinIO is accessible as S3-compatible object storage via `S3_ENDPOINT_URL`
**And** Prometheus is configured to scrape harness metrics endpoints
**And** all external integrations (PD, Slack, SN) default to LOG mode with no outbound calls
**And** infrastructure supports testing Invariant A (CaseFile write-before-publish) against MinIO + Postgres locally
**And** infrastructure supports testing Invariant B2 (publish-after-crash) against Postgres outbox locally
**And** a smoke test script validates that all services are healthy and reachable

### Story 1.9: Harness Traffic Generation

As a platform developer,
I want a validation harness that generates real Prometheus signals for all three anomaly patterns,
So that I can prove the evidence pipeline works against real telemetry (FR58) using harness-specific stream naming that won't collide with production.

**Acceptance Criteria:**

**Given** the local docker-compose environment is running
**When** the harness traffic generator is executed
**Then** it produces real Prometheus metrics for: consumer lag buildup, throughput-constrained proxy, and volume drop patterns
**And** metrics use canonical metric names from prometheus-metrics-contract-v1
**And** harness stream naming is separate from production naming (no collision with prod stream identifiers)
**And** generated metrics are scrapeable by the local Prometheus instance
**And** the harness can produce both normal and anomalous metric patterns on demand
**And** the harness supports configurable duration and intensity for each pattern
**And** unit tests verify metric format compliance with prometheus-metrics-contract-v1

---

### Epic 2: Evidence Collection & Signal Validation
The system can observe Kafka infrastructure via Prometheus, detect three anomaly patterns (lag, constrained proxy, volume drop), compute peak/sustained status, and correctly handle missing telemetry — proving the signals are real.
**FRs covered:** FR1, FR2, FR3, FR4, FR5, FR6, FR7, FR8, FR67a
**Phase alignment:** Phase 0 signal validation

## Epic 2: Evidence Collection & Signal Validation

The system can observe Kafka infrastructure via Prometheus, detect three anomaly patterns (lag, constrained proxy, volume drop), compute peak/sustained status, and correctly handle missing telemetry — proving the signals are real.

### Story 2.1: Prometheus Metric Collection & Evaluation Cadence

As a platform operator,
I want the system to query Prometheus metrics at 5-minute evaluation intervals aligned to wall-clock boundaries,
So that evidence collection is consistent, predictable, and uses canonical metric names from prometheus-metrics-contract-v1 (FR1).

**Acceptance Criteria:**

**Given** the pipeline is running and Prometheus is available
**When** the evaluation scheduler fires
**Then** queries execute at 5-minute wall-clock boundaries (00, 05, 10, ...) with drift <= 30 seconds (NFR-P2)
**And** queries use canonical metric names defined in prometheus-metrics-contract-v1
**And** label normalization is applied (`cluster_id := cluster_name` exact string)
**And** metrics are collected per (env, cluster_id, topic/group) scope
**And** missed intervals are logged as operational warnings
**And** unit tests verify: wall-clock alignment, metric name compliance, label normalization

### Story 2.2: Anomaly Pattern Detection

As a platform operator,
I want the system to detect three anomaly patterns — consumer lag buildup, throughput-constrained proxy, and volume drop,
So that the pipeline identifies real infrastructure issues from Prometheus telemetry (FR2) with each finding declaring its own evidence requirements (FR8).

**Acceptance Criteria:**

**Given** Prometheus metrics have been collected for an evaluation interval
**When** the anomaly detection engine processes the metrics
**Then** it can detect consumer lag buildup patterns
**And** it can detect throughput-constrained proxy patterns
**And** it can detect volume drop patterns
**And** each Finding declares its own `evidence_required[]` list with no central required-evidence registry (FR8)
**And** each detected anomaly is associated with its (env, cluster_id, topic/group) key
**And** unit tests verify detection of each pattern using harness-generated metrics
**And** unit tests verify that findings with custom `evidence_required[]` lists are correctly constructed

### Story 2.3: Peak/Near-Peak Classification

As a platform operator,
I want the system to compute peak/near-peak classification per (env, cluster_id, topic) against historical baselines,
So that anomalies during peak traffic are distinguished from off-peak anomalies for accurate gating decisions (FR3).

**Acceptance Criteria:**

**Given** evidence metrics and historical baseline data are available
**When** peak classification is computed
**Then** each (env, cluster_id, topic) is classified as peak or near-peak based on p90/p95 of messages-in rate
**And** baseline computation uses >= 7 days of history when available for confidence
**And** peak profiles are recomputed weekly and are cacheable
**And** classification results are available for downstream gating (AG4, AG6) and postmortem predicate evaluation
**And** unit tests verify: peak classification against known baselines, near-peak boundary behavior, insufficient history handling

### Story 2.4: Sustained Status Computation

As a platform operator,
I want the system to compute sustained status requiring 5 consecutive anomalous buckets,
So that transient spikes are filtered out and only persistent anomalies trigger higher-severity actions (FR4).

**Acceptance Criteria:**

**Given** anomaly detection results across multiple evaluation intervals
**When** sustained status is computed for each anomaly
**Then** sustained=true requires 5 consecutive anomalous 5-minute buckets (25 minutes total)
**And** a gap in the anomalous sequence resets the sustained counter
**And** sustained status is tracked per anomaly key (env, cluster_id, topic/group, pattern)
**And** sustained status is available for downstream gating (AG4 requires sustained=true for PAGE/TICKET)
**And** unit tests verify: exactly 5 buckets triggers sustained, 4 buckets does not, gap resets counter, multiple independent anomalies track independently

### Story 2.5: UNKNOWN Evidence Propagation

As a platform operator,
I want missing Prometheus series mapped to EvidenceStatus=UNKNOWN and propagated through all computation layers,
So that missing data is never silently treated as zero and downstream decisions correctly reflect uncertainty (FR5, FR6).

**Acceptance Criteria:**

**Given** a Prometheus query returns missing series for a specific metric
**When** evidence is assembled
**Then** the missing series maps to `EvidenceStatus=UNKNOWN` — never treated as zero
**And** UNKNOWN propagates through peak classification (peak status becomes UNKNOWN)
**And** UNKNOWN propagates through sustained computation (sustained status reflects uncertainty)
**And** UNKNOWN propagates through confidence computation (confidence is reduced)
**And** an `evidence_status_map` is produced for each case mapping every evidence primitive to PRESENT/UNKNOWN/ABSENT/STALE (FR6)
**And** unit tests verify end-to-end UNKNOWN propagation: missing series -> evidence -> peak -> sustained -> confidence (NFR-T2)

### Story 2.6: Redis Evidence Caching

As a platform developer,
I want evidence windows, peak profiles, and per-interval findings cached in Redis with environment-specific TTLs,
So that repeated computations are avoided and cache behavior follows redis-ttl-policy-v1 (FR7).

**Acceptance Criteria:**

**Given** Redis is available and configured
**When** evidence, peak profiles, or findings are computed
**Then** results are cached in Redis using the key design: `evidence:{key}`, `peak:{key}`
**And** TTLs are set per environment as defined in redis-ttl-policy-v1
**And** cache hits return previously computed results without re-querying Prometheus
**And** cache misses trigger fresh computation and cache population
**And** cached data is treated as cache-only (not system-of-record) — loss of Redis data is recoverable
**And** unit tests verify: cache write/read round-trip, TTL expiration behavior, cache miss triggers computation

### Story 2.7: Prometheus Unavailability & TelemetryDegradedEvent

As an SRE/operator,
I want the system to detect total Prometheus unavailability and emit a TelemetryDegradedEvent,
So that the pipeline does not emit misleading all-UNKNOWN cases and actions are safely capped until Prometheus recovers (FR67a).

**Acceptance Criteria:**

**Given** the pipeline attempts to query Prometheus
**When** Prometheus is totally unavailable (not individual missing series — total source failure)
**Then** a `TelemetryDegradedEvent` is emitted containing: affected scope, reason, recovery status
**And** the pipeline does NOT emit normal cases with all-UNKNOWN evidence
**And** actions are capped to OBSERVE/NOTIFY until Prometheus recovers
**And** the HealthRegistry is updated with Prometheus status = UNAVAILABLE
**And** when Prometheus recovers, the TelemetryDegradedEvent clears and normal evaluation resumes on the next interval
**And** no backfill of missed intervals occurs after recovery
**And** unit tests verify: event emission on unavailability, no all-UNKNOWN cases emitted, action capping, recovery behavior (NFR-T2)

---

### Epic 3: Topology Resolution & Case Routing
The system can load topology registries (v0 + v1), resolve stream ownership and blast radius, and route cases to the correct team — ensuring anomalies reach the right responders.
**FRs covered:** FR9, FR10, FR11, FR12, FR13, FR14, FR15, FR16
**Phase alignment:** Phase 1A

## Epic 3: Topology Resolution & Case Routing

The system can load topology registries (v0 + v1), resolve stream ownership and blast radius, and route cases to the correct team — ensuring anomalies reach the right responders.

### Story 3.1: Topology Registry Loader (v0 + v1 Formats)

As a platform developer,
I want the system to load topology registries in both v0 (legacy) and v1 (instances-based) formats and canonicalize them to a single in-memory model,
So that the pipeline supports both registry versions during migration with strict validation on load (FR9, FR15).

**Acceptance Criteria:**

**Given** a topology registry file exists in v0 or v1 format
**When** the registry is loaded at startup
**Then** both v0 (legacy) and v1 (instances-based) formats are parsed and canonicalized to a single in-memory model
**And** the registry is loaded into memory for local lookups (no external calls at query time)
**And** loading fails fast on duplicate `topic_index` keys within the same (env, cluster_id) scope
**And** loading fails fast on duplicate consumer-group ownership keys
**And** loading fails fast on missing `routing_key` references
**And** registry reload on change completes within 5 seconds (NFR-P5)
**And** unit tests verify: v0 loading, v1 loading, canonicalization produces identical in-memory model, all three fail-fast validation scenarios

### Story 3.2: Stream Resolution & Topic Role Classification

As a platform operator,
I want the system to resolve stream_id, topic_role, criticality_tier, and source_system from the topology registry given an anomaly key,
So that each case is enriched with the context needed for routing and gating decisions (FR10, FR14).

**Acceptance Criteria:**

**Given** the topology registry is loaded in memory
**When** an anomaly key (env, cluster_id, topic/group) is resolved
**Then** the system returns: stream_id, topic_role, criticality_tier, and source_system
**And** topic_index lookups are scoped by (env, cluster_id) to prevent cross-cluster collisions (FR14)
**And** resolution latency is p99 <= 50ms (NFR-P5)
**And** unresolvable anomaly keys return a clear "unresolved" status (not a silent default)
**And** unit tests verify: successful resolution, cross-cluster scoping, unresolvable key handling, latency within bounds

### Story 3.3: Blast Radius & Downstream Impact Assessment

As a platform operator,
I want the system to compute blast radius classification and identify downstream components at risk,
So that responders understand the scope of impact when triaging an anomaly (FR11, FR12).

**Acceptance Criteria:**

**Given** an anomaly has been resolved to a stream with topic_role
**When** blast radius is computed
**Then** classification is either LOCAL_SOURCE_INGESTION or SHARED_KAFKA_INGESTION based on topic_role (FR11)
**And** downstream components are identified as AT_RISK with exposure_type: DOWNSTREAM_DATA_FRESHNESS_RISK, DIRECT_COMPONENT_RISK, or VISIBILITY_ONLY (FR12)
**And** blast radius and downstream impact are available for inclusion in CaseFile and TriageExcerpt
**And** unit tests verify: correct classification for each topic_role, downstream identification for each exposure_type, edge cases with no downstream components

### Story 3.4: Multi-Level Ownership Routing

As a platform operator,
I want cases routed to the correct owning team using a multi-level ownership lookup,
So that anomalies reach the right responders without manual intervention (FR13).

**Acceptance Criteria:**

**Given** an anomaly has been resolved to a stream
**When** ownership routing is computed
**Then** the system applies multi-level lookup in order: consumer_group_owner -> topic_owner -> stream_default_owner -> platform_default (FR13)
**And** the first non-null owner in the chain is selected as the routing target
**And** the routing_key for the selected owner is resolved from the registry
**And** cases with no owner at any level fall through to platform_default (never unrouted)
**And** unit tests verify: each level of the lookup chain, fallthrough behavior, platform_default catch-all, routing_key resolution

### Story 3.5: Legacy v0 Compatibility Views

As a platform developer,
I want backward-compatible compatibility views for legacy consumers during v0 to v1 migration,
So that existing v0 consumers receive identical field values and types with no breaking changes during the transition (FR16).

**Acceptance Criteria:**

**Given** the topology registry has been loaded and canonicalized from either v0 or v1 format
**When** a legacy consumer requests data through the compat view
**Then** v0 schema fields are returned with identical values, types, and semantics as the original v0 format
**And** no breaking changes exist in field names, types, or semantics for v0 consumers
**And** compat views are derived from the canonical in-memory model (single source of truth, not a parallel data path)
**And** unit tests verify: v0 compat output matches expected v0 schema exactly, field-by-field comparison against reference v0 data

---

### Epic 4: Durable Triage & Reliable Event Publishing
The system can assemble auditable CaseFiles with evidence snapshots and policy stamps, write them durably to object storage (Invariant A), and reliably publish event headers to Kafka via the durable outbox (Invariant B2) — ensuring no evidence or decision is ever lost.
**FRs covered:** FR17, FR18, FR19, FR20, FR21, FR22, FR23, FR24, FR25, FR26
**Phase alignment:** Phase 1A

## Epic 4: Durable Triage & Reliable Event Publishing

The system can assemble auditable CaseFiles with evidence snapshots and policy stamps, write them durably to object storage (Invariant A), and reliably publish event headers to Kafka via the durable outbox (Invariant B2) — ensuring no evidence or decision is ever lost.

### Story 4.1: CaseFile Triage Stage Assembly

As a platform operator,
I want the system to assemble a complete CaseFile triage stage containing evidence, gating inputs, action decisions, and policy version stamps,
So that every triage decision is captured as a self-contained, auditable artifact with tamper-evident hashing (FR17, FR20).

**Acceptance Criteria:**

**Given** evidence, topology, and gating results are available for a case
**When** the CaseFile triage stage is assembled
**Then** `triage.json` contains: evidence snapshot, gating inputs (GateInput.v1 fields), ActionDecision.v1, and policy version stamps (rulebook_version, peak_policy_version, prometheus_metrics_contract_version, exposure_denylist_version, diagnosis_policy_version)
**And** a SHA-256 content hash is computed over the serialized JSON bytes and included in the artifact
**And** data minimization is enforced: no PII, credentials, or secrets in the CaseFile (FR20)
**And** sensitive fields are redacted per the exposure denylist before inclusion
**And** the triage stage is serialized via Pydantic `.model_dump_json()` and validates via `model_validate_json()` round-trip
**And** unit tests verify: all required fields present, SHA-256 hash correctness, data minimization (no denied fields), round-trip serialization

### Story 4.2: Write-Once CaseFile to Object Storage (Invariant A)

As a platform operator,
I want CaseFile triage.json written to object storage as a write-once artifact before any Kafka header is published,
So that the durability guarantee (Invariant A) ensures no event reaches consumers without its backing evidence existing in storage (FR18).

**Acceptance Criteria:**

**Given** a CaseFile triage stage has been assembled
**When** the triage stage is persisted
**Then** `triage.json` is written to object storage at `cases/{case_id}/triage.json`
**And** the write completes successfully before any outbox record transitions to READY
**And** if object storage is unavailable, the pipeline halts for this case with explicit alerting (NFR-R2) — no silent degradation
**And** the write is idempotent — retrying the same case_id produces the same result
**And** the SHA-256 hash is stored in the outbox record for tamper-evidence verification
**And** integration tests verify Invariant A: CaseFile exists in object storage before Kafka header appears (NFR-T2)
**And** integration tests use MinIO via testcontainers

### Story 4.3: Append-Only CaseFile Stage Files

As a platform developer,
I want additional CaseFile stage files (diagnosis, linkage, labels) written to the same case directory without mutating prior stage files,
So that each stage is independently immutable and the hash integrity chain is preserved across stages (FR19).

**Acceptance Criteria:**

**Given** a CaseFile `triage.json` exists for a case
**When** a cold-path stage completes (diagnosis, linkage, or labels)
**Then** the new stage file is written to `cases/{case_id}/{stage}.json` (e.g., `diagnosis.json`, `linkage.json`, `labels.json`)
**And** the prior stage files are never read-modify-written — each stage writes its own file independently
**And** each new stage file includes SHA-256 hashes of prior stage files it depends on (hash chain)
**And** missing stage files indicate the stage did not complete (e.g., no `diagnosis.json` if LLM timed out) — not an error
**And** unit tests verify: independent stage writes, prior files unchanged after append, hash chain integrity, missing stage file handling

### Story 4.4: Postgres Durable Outbox State Machine

As a platform developer,
I want a Postgres-backed durable outbox managing state transitions from PENDING_OBJECT through SENT,
So that event publishing survives crashes and follows the outbox-policy-v1 retention rules (FR23, FR26).

**Acceptance Criteria:**

**Given** the outbox table exists in Postgres (hand-rolled DDL via SQLAlchemy Core)
**When** a CaseFile triage write is confirmed
**Then** an outbox record is created in PENDING_OBJECT state
**And** the record transitions to READY after CaseFile write confirmation
**And** the publisher transitions READY -> SENT after successful Kafka publish
**And** failed publishes transition to RETRY with exponential backoff
**And** records exceeding max retries transition to DEAD
**And** retention is enforced per outbox-policy-v1: SENT (14d prod), DEAD (90d prod), PENDING/READY/RETRY until resolved (FR26)
**And** if Postgres is unavailable, the pipeline halts with explicit alerting (NFR-R2)
**And** unit tests verify: all state transitions (PENDING_OBJECT -> READY -> SENT, RETRY, DEAD), retention policy application, Postgres unavailability handling

### Story 4.5: Outbox-to-Kafka Event Publishing (Invariant B2)

As a platform operator,
I want the outbox publisher to reliably publish CaseHeaderEvent.v1 and TriageExcerpt.v1 to Kafka with publish-after-crash guarantees,
So that no confirmed CaseFile is ever lost in transit and hot-path consumers need only header/excerpt for routing decisions (FR22, FR24).

**Acceptance Criteria:**

**Given** outbox records exist in READY state
**When** the outbox publisher runs
**Then** it publishes `CaseHeaderEvent.v1` + `TriageExcerpt.v1` to Kafka as JSON via confluent-kafka synchronous producer
**And** hot-path consumers receive only header/excerpt — no object-store reads required for routing/paging decisions (FR24)
**And** after a crash between CaseFile write and Kafka publish, the publisher recovers READY records and publishes them (Invariant B2)
**And** if Kafka is unavailable, outbox accumulates READY records and alerts on READY age thresholds
**And** the publisher runs as a separate entrypoint (`--mode outbox-publisher`)
**And** integration tests verify Invariant B2: simulate crash between CaseFile write and Kafka publish, verify publish occurs on recovery (NFR-T2)

### Story 4.6: TriageExcerpt Exposure Denylist Enforcement

As a platform operator,
I want the exposure denylist enforced on TriageExcerpt before it is published to Kafka,
So that no sensitive sink endpoints, credentials, restricted hostnames, or Ranger access groups appear in the hot-path event stream (FR25).

**Acceptance Criteria:**

**Given** a TriageExcerpt.v1 has been assembled from CaseFile data
**When** the excerpt is prepared for Kafka publishing
**Then** `apply_denylist()` is applied to the excerpt fields before serialization
**And** zero denied fields appear in the published TriageExcerpt
**And** the excerpt remains schema-valid after denylist application (no required fields removed that would break consumers)
**And** denylist enforcement is logged for audit traceability
**And** unit tests verify: denied fields removed, non-denied fields preserved, schema validity post-denylist, edge cases with nested fields matching denylist patterns (NFR-S5)

### Story 4.7: CaseFile Retention & Lifecycle Management

As a compliance officer,
I want CaseFile retention enforced at 25 months in prod via automated lifecycle policies with auditable purge operations,
So that regulatory examination windows are satisfied and purges are traceable (FR21).

**Acceptance Criteria:**

**Given** CaseFiles exist in object storage with known creation timestamps
**When** the retention lifecycle policy executes
**Then** CaseFiles older than 25 months in prod are purged
**And** purge operations are auditable: logged with timestamp, scope (case_ids affected), and policy reference
**And** no manual ad-hoc deletion is permitted without governance approval
**And** retention periods are configurable per environment
**And** lifecycle policies can be run as a scheduled operation
**And** unit tests verify: retention threshold calculation, purge logging, environment-specific retention configuration

---

### Epic 5: Deterministic Safety Gating & Action Execution
Operators can trust that every action (PAGE/TICKET/NOTIFY/OBSERVE) is safely gated through deterministic Rulebook evaluation (AG0-AG6), with storm control via deduplication and degraded-mode safety — preventing paging storms and ensuring auditable, reproducible action decisions.
**FRs covered:** FR27, FR28, FR29, FR30, FR31, FR32, FR33, FR34, FR35, FR43, FR44, FR45, FR51
**Phase alignment:** Phase 1A

## Epic 5: Deterministic Safety Gating & Action Execution

Operators can trust that every action (PAGE/TICKET/NOTIFY/OBSERVE) is safely gated through deterministic Rulebook evaluation (AG0-AG6), with storm control via deduplication and degraded-mode safety — preventing paging storms and ensuring auditable, reproducible action decisions.

### Story 5.1: Rulebook Gate Engine (AG0-AG6 Sequential Evaluation)

As a platform operator,
I want GateInput.v1 evaluated through Rulebook gates AG0-AG6 sequentially to produce an ActionDecision.v1,
So that every action decision is deterministic, auditable, and follows the exact gate sequence (FR27).

**Acceptance Criteria:**

**Given** a GateInput.v1 envelope is assembled from evidence, topology, and case context
**When** the Rulebook engine evaluates the gates
**Then** gates AG0 through AG6 execute sequentially in order — no gate is skipped
**And** the output is an ActionDecision.v1 containing: final_action, env_cap_applied, gate_rule_ids, gate_reason_codes, action_fingerprint, postmortem_required, postmortem_mode, postmortem_reason_codes
**And** each gate can reduce the action level but never escalate it (monotonic downward)
**And** the gate engine completes within p99 <= 500ms (NFR-P3) — deterministic policy evaluation with no external dependencies
**And** gate evaluation is pure computation with no I/O (except Redis dedupe check in AG5)
**And** unit tests verify: sequential gate execution order, ActionDecision.v1 field completeness, monotonic action reduction, latency bounds

### Story 5.2: Environment & Criticality Tier Caps (AG1)

As a platform operator,
I want actions capped by environment and criticality tier,
So that local/dev/uat environments cannot trigger production-level actions and only TIER_0 streams in prod are PAGE-eligible (FR28, FR29).

**Acceptance Criteria:**

**Given** the Rulebook engine reaches AG1
**When** environment and tier caps are evaluated
**Then** local environment caps to OBSERVE maximum (FR28)
**And** dev environment caps to NOTIFY maximum (FR28)
**And** uat environment caps to TICKET maximum (FR28)
**And** prod environment: TIER_0 = PAGE eligible (if all other gates pass), TIER_1 = TICKET, TIER_2/UNKNOWN = NOTIFY (FR29)
**And** the env_cap_applied field in ActionDecision.v1 reflects which cap was applied
**And** gate_rule_ids and gate_reason_codes record the AG1 evaluation
**And** unit tests verify: each environment cap, each prod tier cap, UNKNOWN tier treated as TIER_2

### Story 5.3: Evidence Sufficiency & Source Topic Gates (AG2, AG3)

As a platform operator,
I want actions downgraded when evidence is insufficient and PAGE denied for source topic anomalies,
So that the system never takes high-severity actions based on uncertain evidence or misclassified source-side issues (FR30, FR31).

**Acceptance Criteria:**

**Given** the Rulebook engine reaches AG2 and AG3
**When** AG2 evaluates evidence sufficiency
**Then** each finding's `evidence_required[]` is checked against the evidence_status_map
**And** evidence with status UNKNOWN/ABSENT/STALE is treated as insufficient unless the finding explicitly allows it (FR31)
**And** insufficient evidence downgrades the action — never assumes PRESENT
**When** AG3 evaluates anomaly type
**Then** PAGE is denied for SOURCE_TOPIC anomalies; final_action caps to TICKET or lower depending on env/tier/remaining gates (FR30)
**And** gate_reason_codes include the specific evidence insufficiency or source topic denial reason
**And** unit tests verify: evidence sufficiency downgrade for each status, SOURCE_TOPIC PAGE denial, combined AG2+AG3 interaction

### Story 5.4: Sustained & Confidence Threshold Gate (AG4)

As a platform operator,
I want PAGE and TICKET actions to require sustained=true and confidence >= 0.6,
So that only persistent, high-confidence anomalies trigger disruptive actions (FR32).

**Acceptance Criteria:**

**Given** the Rulebook engine reaches AG4
**When** sustained status and confidence are evaluated
**Then** PAGE requires sustained=true AND confidence >= 0.6
**And** TICKET requires sustained=true AND confidence >= 0.6
**And** if either condition fails, the action is downgraded to NOTIFY or lower
**And** gate_reason_codes record the specific AG4 failure (NOT_SUSTAINED, LOW_CONFIDENCE, or both)
**And** unit tests verify: sustained=false downgrades, confidence < 0.6 downgrades, both conditions failing, boundary case at confidence = 0.6 exactly

### Story 5.5: Action Deduplication & Redis Degraded Mode (AG5)

As a platform operator,
I want actions deduplicated by action_fingerprint with per-type TTLs and safe degraded behavior when Redis is unavailable,
So that repeat actions are suppressed (preventing paging storms) and Redis failure never causes unsafe escalation (FR33, FR34, FR51).

**Acceptance Criteria:**

**Given** the Rulebook engine reaches AG5
**When** dedupe is evaluated against Redis
**Then** actions are deduplicated by action_fingerprint with TTLs: PAGE 120m, TICKET 240m, NOTIFY 60m (FR33)
**And** a duplicate action within the TTL window is suppressed (action becomes OBSERVE)
**And** dedupe keys are stored in Redis using the `dedupe:{fingerprint}` key pattern
**When** Redis is unavailable
**Then** the system detects Redis unavailability and caps all actions to NOTIFY-only (FR34)
**And** a `DegradedModeEvent` is emitted containing: affected scope, reason, capped action level, estimated impact window (FR51)
**And** the DegradedModeEvent is sent to logs and Slack (if configured)
**And** when Redis recovers, dedupe state is rebuilt from scratch (cache-only, no persistent state lost) and normal behavior resumes
**And** unit tests verify: deduplication within TTL, TTL expiry allows new action, Redis unavailability -> NOTIFY-only cap, DegradedModeEvent emission, recovery behavior (NFR-T4)

### Story 5.6: Postmortem Predicate Evaluation (AG6)

As a platform operator,
I want the PM_PEAK_SUSTAINED predicate evaluated for selective postmortem obligation,
So that only high-impact cases (peak, sustained, TIER_0 in PROD) trigger postmortem tracking (FR35).

**Acceptance Criteria:**

**Given** the Rulebook engine reaches AG6
**When** the postmortem predicate is evaluated
**Then** `PM_PEAK_SUSTAINED` fires when: peak=true AND sustained=true AND criticality_tier=TIER_0 AND environment=PROD (FR35)
**And** when the predicate fires, ActionDecision.v1 sets: postmortem_required=true, postmortem_mode (SOFT for Phase 1A), and postmortem_reason_codes
**And** when the predicate does not fire, postmortem_required=false
**And** AG6 does not change the final_action — it only sets postmortem fields
**And** unit tests verify: predicate fires with all conditions met, does not fire when any condition is missing, postmortem fields correctly set

### Story 5.7: PagerDuty PAGE Trigger Execution

As a platform operator,
I want PAGE actions to trigger PagerDuty with a stable pd_incident_id,
So that high-severity incidents are routed to on-call responders and can be correlated with downstream ServiceNow records (FR43).

**Acceptance Criteria:**

**Given** the ActionDecision.v1 has final_action=PAGE
**When** the Action Executor processes the decision
**Then** a PAGE trigger is sent to PagerDuty with a stable `pd_incident_id` derived from the case
**And** the PD trigger includes routing_key for correct team routing
**And** the integration respects the INTEGRATION_MODE_PD setting (OFF/LOG/MOCK/LIVE)
**And** in LOG mode, the PD trigger payload is logged as structured JSON without making external calls
**And** in MOCK mode, the trigger is simulated with a success response
**And** PD API calls are logged with: timestamp, request_id, case_id, action, outcome, latency (NFR-S6)
**And** unit tests verify: trigger payload correctness, pd_incident_id stability, each integration mode behavior

### Story 5.8: Slack Notification & Structured Log Fallback

As a platform operator,
I want SOFT postmortem enforcement sent via Slack when PM_PEAK_SUSTAINED fires and structured log fallback when Slack is not configured,
So that postmortem obligations are communicated and no notification is silently lost (FR44, FR45).

**Acceptance Criteria:**

**Given** the ActionDecision.v1 has postmortem_required=true with postmortem_mode=SOFT
**When** the notification is dispatched
**Then** a postmortem enforcement notification is sent to Slack containing: case_id, final_action, routing_key, support_channel, postmortem_required, reason_codes (FR44)
**And** the Slack notification enforces the exposure denylist (no denied fields in message)
**When** Slack is not configured or unavailable
**Then** a structured `NotificationEvent` is emitted to logs (JSON) with the same fields (FR45)
**And** the pipeline continues without interruption — Slack unavailability never blocks processing (NFR-R1)
**And** the integration respects INTEGRATION_MODE_SLACK (OFF/LOG/MOCK/LIVE)
**And** unit tests verify: Slack notification content and denylist compliance, structured log fallback, Slack unavailability handling, each integration mode

### Story 5.9: End-to-End Hot-Path Pipeline Test

As a platform developer,
I want a single integration test that exercises the full hot-path pipeline end-to-end locally,
So that the complete flow from harness traffic to action execution is validated with zero external dependencies (NFR-T5).

**Acceptance Criteria:**

**Given** the local docker-compose environment is running (Mode A)
**When** the end-to-end pipeline test executes
**Then** a single test exercises the full hot-path: harness traffic -> evidence collection -> peak classification -> topology resolution -> CaseFile triage write -> outbox publish -> Kafka header/excerpt -> Rulebook gating (AG0-AG6) -> action execution
**And** the test runs locally with zero external dependencies (all infrastructure via docker-compose)
**And** Invariant A is verified: CaseFile exists in MinIO before Kafka header appears
**And** Invariant B2 is verified: outbox publishes after simulated crash recovery
**And** the CaseFile contains: all evidence, gate rule IDs + reason codes, policy version stamps, SHA-256 hash
**And** the ActionDecision.v1 output is deterministically correct given the test evidence and policy versions
**And** the test is runnable via `uv run pytest` with testcontainers infrastructure
**And** test execution completes within a reasonable time bound (< 2 minutes)

---

## Epic 6: LLM-Enriched Diagnosis

Cases are enriched with AI-generated diagnosis on the cold path, providing structured root cause hypotheses, evidence citations, and next-step recommendations — without ever blocking the hot-path triage pipeline.

### Story 6.1: LLM Stub & Failure-Injection Mode

As a platform developer,
I want the pipeline to run with LLM in stub and failure-injection modes for local and test environments,
So that end-to-end pipeline testing works without external LLM API calls while prod always uses live LLM (FR41).

**Acceptance Criteria:**

**Given** the pipeline is running in local or test environment
**When** LLM stub mode is active (INTEGRATION_MODE_LLM=MOCK)
**Then** the LLM stub produces a deterministic schema-valid DiagnosisReport with: verdict=UNKNOWN, confidence=LOW, reason_codes=[LLM_STUB]
**And** no external LLM API calls are made
**And** the full pipeline (hot path + cold path) executes end-to-end with stub output
**When** failure-injection mode is active
**Then** LLM timeout, unavailability, and malformed output scenarios can be simulated
**And** each scenario produces the corresponding deterministic fallback DiagnosisReport
**When** the environment is PROD
**Then** LLM stub mode is NOT permitted — INTEGRATION_MODE_LLM must be LIVE
**And** startup validation rejects MOCK/OFF mode for LLM in prod configuration
**And** unit tests verify: stub output schema validity, no external calls in stub mode, failure-injection scenarios, prod mode enforcement

### Story 6.2: Cold-Path LLM Invocation & Hot-Path Independence

As a platform operator,
I want LLM diagnosis invoked on the cold path as a non-blocking, fire-and-forget async task,
So that the hot-path triage pipeline (CaseFile write, outbox publish, Rulebook gating, action execution) completes without waiting on LLM and cases are conditionally enriched based on criteria (FR36, FR42, FR66).

**Acceptance Criteria:**

**Given** a case has completed hot-path processing (triage.json written, header published, action executed)
**When** the case qualifies for LLM diagnosis (environment=PROD, tier=TIER_0, state=sustained per FR42)
**Then** a fire-and-forget async LangGraph task is spawned consuming TriageExcerpt + structured evidence summary
**And** the hot path never waits on LLM completion — hot-path latency is unaffected by LLM invocation
**And** LLM input is bounded: TriageExcerpt + structured evidence summary only, not raw logs or full CaseFile (token budget per deployment config)
**And** LLM input is exposure-capped: denylist applied before sending to LLM (NFR-S8)
**And** the fire-and-forget task is registered with HealthRegistry with an in-flight gauge metric
**And** LLM invocation timeout is <= 60 seconds (NFR-P4)
**And** cases not meeting invocation criteria skip LLM diagnosis entirely (no wasted calls)
**And** unit tests verify: hot-path completes independently, conditional invocation criteria, fire-and-forget registration, exposure-capped inputs

### Story 6.3: Structured DiagnosisReport Output & Evidence Citation

As a platform operator,
I want the LLM to produce a structured DiagnosisReport with evidence citations and UNKNOWN propagation,
So that diagnosis output is machine-parseable, traceable to evidence, and never fabricates findings (FR37, FR38).

**Acceptance Criteria:**

**Given** the LLM has been invoked with TriageExcerpt and evidence summary
**When** the LLM produces its response
**Then** the output is a structured DiagnosisReport.v1 containing: verdict, fault_domain, confidence, evidence_pack (facts, missing_evidence, matched_rules), next_checks, gaps (FR37)
**And** the LLM cites evidence IDs/references from the structured evidence pack (FR38)
**And** the LLM explicitly propagates UNKNOWN for missing evidence — never invents metric values or fabricates findings (FR38)
**And** the DiagnosisReport is written to `cases/{case_id}/diagnosis.json` as a write-once stage file
**And** `diagnosis.json` includes SHA-256 hash of `triage.json` it depends on (hash chain)
**And** LLM uses only bank-sanctioned endpoints (NFR-S8)
**And** unit tests verify: DiagnosisReport field completeness, evidence citation presence, UNKNOWN propagation for missing evidence, hash chain to triage.json

### Story 6.4: LLM Output Schema Validation & Deterministic Fallback

As a platform operator,
I want invalid or unavailable LLM output to produce a deterministic schema-valid fallback DiagnosisReport,
So that the system is resilient to LLM failures and every case has a valid diagnosis stage regardless of LLM behavior (FR39, FR40).

**Acceptance Criteria:**

**Given** the LLM invocation completes (or fails)
**When** the LLM is unavailable
**Then** a fallback DiagnosisReport is emitted with: verdict=UNKNOWN, confidence=LOW, reason_codes=[LLM_UNAVAILABLE] (FR39)
**When** the LLM times out (> 60 seconds)
**Then** a fallback DiagnosisReport is emitted with: verdict=UNKNOWN, confidence=LOW, reason_codes=[LLM_TIMEOUT] (FR39)
**And** no retry occurs within the same evaluation cycle (NFR-P4)
**When** the LLM returns an error
**Then** a fallback DiagnosisReport is emitted with: verdict=UNKNOWN, confidence=LOW, reason_codes=[LLM_ERROR] (FR39)
**When** the LLM returns malformed or unparseable output
**Then** the output is validated against DiagnosisReport.v1 schema via `model_validate()` (FR40)
**And** invalid output triggers the deterministic fallback with a gap recorded
**And** all fallback DiagnosisReports are schema-valid and written to `diagnosis.json`
**And** the HealthRegistry is updated with LLM component status on failure/recovery
**And** unit tests verify: each failure scenario (unavailable, timeout, error, malformed), fallback schema validity, gap recording, no retry within cycle (NFR-T3)

---

### Epic 7: Governance, Audit & Operational Observability
Auditors can reproduce any historical gating decision, operators can monitor the AIOps system's own health (meta-monitoring), and the platform maintains compliance with banking regulatory requirements including MI-1 posture.
**FRs covered:** FR52, FR53, FR54, FR60, FR61, FR62, FR63, FR64, FR65, FR67b
**Phase alignment:** Phase 1A (cross-cutting)
**Note:** FR63-FR64 have schema support from Phase 1A; operator capture workflow deferred to Phase 2.

## Epic 7: Governance, Audit & Operational Observability

Auditors can reproduce any historical gating decision, operators can monitor the AIOps system's own health (meta-monitoring), and the platform maintains compliance with banking regulatory requirements including MI-1 posture.

### Story 7.1: Outbox Health Monitoring & DEAD=0 Posture

As an SRE/operator,
I want outbox health monitored with alerting thresholds and DEAD=0 enforced as a standing prod requirement,
So that I am immediately aware of publishing delays, stuck records, or critical DEAD accumulation (FR52, FR53, FR54).

**Acceptance Criteria:**

**Given** the outbox is operational with records in various states
**When** outbox health metrics are collected
**Then** the following are monitored: PENDING_OBJECT age (>5m warn, >15m crit), READY age (>2m warn, >10m crit), RETRY age (>30m crit), DEAD count (>0 crit in prod) (FR52)
**And** outbox delivery SLO is measured: p95 <= 1 min, p99 <= 5 min from CaseFile write to Kafka publish; p99 > 10 min is critical (FR53)
**And** DEAD=0 is enforced as a standing prod posture — any DEAD row triggers a critical alert (FR54)
**And** DEAD records require human investigation and explicit replay/resolution — no automatic retry
**And** outbox queue depth by state (PENDING_OBJECT, READY, RETRY, DEAD, SENT), age of oldest per state, and publish latency histogram are exposed as metrics
**And** unit tests verify: threshold breach detection for each state, DEAD>0 alerting, SLO measurement calculation

### Story 7.2: OpenTelemetry Instrumentation & OTLP Export

As an SRE/operator,
I want the AIOps system to expose health metrics for all its own components via OpenTelemetry SDK with OTLP export,
So that I can monitor the observer itself through Dynatrace and detect degradation before it impacts triage quality (NFR-O1).

**Acceptance Criteria:**

**Given** the pipeline components are running
**When** meta-monitoring metrics are collected
**Then** the following component metrics are exposed via OpenTelemetry SDK with OTLP export to Dynatrace:
- Outbox: queue depth by state, age of oldest per state, publish latency histogram
- Redis: connection status, cache hit/miss rate, dedupe key count
- LLM: invocation count, latency histogram, timeout/error rate, fallback rate
- Evidence Builder: evaluation interval adherence, cases produced per interval, UNKNOWN rate by metric
- Prometheus connectivity: scrape success/failure, TelemetryDegradedEvent active/cleared
- Pipeline: end-to-end compute latency histogram (NFR-P1a), delivery latency histogram (NFR-P1b), case throughput
**And** integration tests include an OpenTelemetry Collector container (via testcontainers) as OTLP receiver stub that asserts correct metric names, labels, and values
**And** unit tests verify: metric emission for each component, correct metric names and label structure

### Story 7.3: Alerting Rules & Component Health Thresholds

As an SRE/operator,
I want alerting rules defined for all monitored components with configurable thresholds,
So that I am proactively notified when any component degrades beyond acceptable bounds (NFR-O2).

**Acceptance Criteria:**

**Given** OpenTelemetry metrics are being exported from Story 7.2
**When** alerting rules are defined
**Then** alerting rules exist for: outbox age thresholds (per outbox-policy-v1), DEAD>0 (crit in prod), Redis connection loss, Prometheus unavailability (TelemetryDegradedEvent), LLM error rate spikes, evaluation interval drift, and pipeline latency breach
**And** alert definitions are versioned and reviewable as operational artifacts
**And** alerting thresholds are configurable per environment
**And** each alert rule includes: condition, severity (warn/crit), affected component, and recommended action
**And** unit tests verify: threshold breach detection for each alert rule, correct severity classification, configurable threshold overrides

### Story 7.4: Policy Version Stamping & Decision Reproducibility

As an auditor,
I want every CaseFile to record the exact policy versions used and historical gating decisions to be reproducible,
So that I can verify any past decision was correct given the evidence and policies active at that time (FR60, FR61).

**Acceptance Criteria:**

**Given** a CaseFile has been written with a gating decision
**When** the CaseFile is inspected
**Then** it records exact policy versions: rulebook_version, peak_policy_version, prometheus_metrics_contract_version, exposure_denylist_version, diagnosis_policy_version (FR60)
**And** given the same evidence snapshot + the same policy versions, re-evaluating the Rulebook produces an identical ActionDecision.v1 (FR61)
**And** a regression test suite exercises decision reproducibility for representative cases
**And** the audit flow is demonstrable: retrieve CaseFile -> trace evidence -> trace gating -> verify action was correct given policy (NFR-T6)
**And** CaseFile contains: all evidence used in the decision, all gate rule IDs + reason codes, policy version stamps, and SHA-256 hash (NFR-T6)
**And** unit tests verify: policy version presence in CaseFile, deterministic re-evaluation produces identical output, audit trail completeness

### Story 7.5: Exposure Denylist Governance & LLM Narrative Compliance

As a compliance officer,
I want the exposure denylist maintained as a versioned, reviewable artifact with LLM-generated narrative compliance enforced,
So that denylist changes follow controlled change management and no LLM output leaks sensitive information (FR62, FR65).

**Acceptance Criteria:**

**Given** the exposure denylist is a versioned YAML file in the repository
**When** a change to the denylist is proposed
**Then** changes require pull request review by at least one designated approver (FR62)
**And** an audit log entry records: author, reviewer, timestamp, and diff summary (FR62)
**And** denylist version is bumped on every change
**When** LLM-generated narrative appears in any surfaced output (excerpt, Slack, SN)
**Then** the narrative is filtered through `apply_denylist()` before surfacing (FR65)
**And** zero violations of the denylist in LLM-generated content
**And** unit tests verify: denylist version tracking, LLM narrative denylist enforcement, edge cases with LLM output containing denied patterns

### Story 7.6: Case Labeling Schema & MI-1 Posture Enforcement

As a platform developer,
I want the CaseFile schema to support case labeling fields and automated MI creation to be provably impossible,
So that Phase 2 labeling workflow has its schema foundation ready and the system maintains MI-1 posture at all times (FR63, FR64, FR67b).

**Acceptance Criteria:**

**Given** the CaseFile schema includes labeling fields
**When** labeling data is considered
**Then** the schema supports: owner_confirmed, resolution_category, false_positive, missing_evidence_reason (FR63)
**And** `labels.json` stage file can be written to `cases/{case_id}/labels.json` following the append-only pattern
**And** label data quality validation rules are defined: completion rate >= 70% for eligible cases, consistency checks for key labels (FR64)
**And** label validation is implementable but the operator capture workflow is explicitly deferred to Phase 2
**Given** the system interacts with ServiceNow
**When** any automated process executes
**Then** no automated process creates Major Incident (MI) objects in ServiceNow (FR67b)
**And** the system supports postmortem automation (Problem + PIR tasks) but never escalates into the bank's MI process autonomously
**And** an automated test verifies that MI creation is impossible through any code path
**And** unit tests verify: labeling schema field presence, labels.json write capability, MI-1 posture (no MI creation code paths exist)

---

## Epic 8: ServiceNow Postmortem Automation

PAGE cases are automatically correlated with PagerDuty-created ServiceNow Incidents via tiered correlation, and postmortem tracking (Problem + PIR tasks) is created idempotently — closing the loop on incident management.

### Story 8.1: Tiered ServiceNow Incident Correlation

As a platform operator,
I want PAGE cases correlated with PagerDuty-created ServiceNow Incidents using a three-tier search strategy,
So that the system reliably finds the correct SN Incident even when the primary correlation field is not populated (FR46).

**Acceptance Criteria:**

**Given** a PAGE action has been executed with a stable `pd_incident_id`
**When** SN Incident correlation is initiated
**Then** Tier 1 searches for the Incident using the PD correlation field on the SN Incident record
**And** if Tier 1 fails, Tier 2 searches using keyword matching against Incident short_description/description
**And** if Tier 2 fails, Tier 3 searches using time-window + routing heuristic (recent Incidents matching routing_key within a configurable time window)
**And** the tier that produced the match is recorded in the linkage result
**And** the integration respects INTEGRATION_MODE_SN (OFF/LOG/MOCK/LIVE)
**And** all SN API calls are logged with: timestamp, request_id, case_id, action, outcome, latency (NFR-S6)
**And** SN search uses least-privilege access: READ on incident only (NFR-S6)
**And** unit tests verify: Tier 1 match, Tier 1 miss -> Tier 2 match, Tier 2 miss -> Tier 3 match, all tiers miss, each integration mode behavior

### Story 8.2: Idempotent Problem & PIR Task Upsert

As a platform operator,
I want SN Problem and PIR tasks created or updated idempotently for correlated Incidents,
So that postmortem tracking is automated without creating duplicate records on retry (FR47).

**Acceptance Criteria:**

**Given** an SN Incident has been correlated via tiered search
**When** Problem and PIR task creation is triggered
**Then** a Problem record is created or updated using `external_id` keying — no duplicates on retry (FR47)
**And** PIR task(s) are created or updated under the Problem using `external_id` keying — no duplicates on retry
**And** Problem and PIR descriptions enforce the exposure denylist — no sensitive sink endpoints, credentials, or restricted hostnames (NFR-S5)
**And** SN integration uses least-privilege access: CRUD on problem/task only — no broad admin roles
**And** all SN API calls (create, update) are logged with: timestamp, request_id, case_id, sys_ids touched, action, outcome, latency (NFR-S6)
**And** linkage results are written to `cases/{case_id}/linkage.json` as a write-once stage file
**And** unit tests verify: idempotent create (first call creates, second call updates same record), denylist enforcement on descriptions, linkage.json write with hash chain

### Story 8.3: SN Linkage Retry & State Machine

As a platform operator,
I want SN linkage to retry with exponential backoff over a 2-hour window with FAILED_FINAL escalation,
So that transient SN unavailability is handled gracefully and persistent failures are escalated for human attention (FR48, FR49).

**Acceptance Criteria:**

**Given** an SN linkage attempt has been initiated
**When** the linkage state machine processes the case
**Then** state transitions follow: PENDING -> SEARCHING -> LINKED (success path) (FR49)
**And** on transient failure: SEARCHING -> FAILED_TEMP -> SEARCHING (retry path) (FR49)
**And** on permanent failure: SEARCHING -> FAILED_FINAL (after 2-hour retry window exhausted) (FR49)
**And** retries use exponential backoff with jitter over the 2-hour window (FR48)
**And** FAILED_FINAL triggers Slack escalation (exposure-safe — denylist enforced on escalation message) (FR48)
**And** FAILED_TEMP cases resume retry on next cycle; FAILED_FINAL cases remain terminal (human review required)
**And** linkage state is persisted — survives process restart
**And** SN linkage is deployable as an add-on to Phase 1A without redeploying the hot-path pipeline (NFR-O5)
**And** unit tests verify: each state transition, exponential backoff timing, jitter application, 2-hour window expiry -> FAILED_FINAL, Slack escalation content and denylist compliance, state persistence across restart

### Story 8.4: SN Correlation Fallback Rate Metrics

As an SRE/operator,
I want Tier 1 vs Tier 2/3 SN correlation fallback rates tracked as metrics,
So that I can detect when the primary correlation path is degraded and escalate to the PD/SN integration team (FR50).

**Acceptance Criteria:**

**Given** SN Incident correlations are being performed
**When** correlation results are recorded
**Then** a Prometheus-compatible gauge metric is exposed per correlation tier (Tier 1, Tier 2, Tier 3, No Match)
**And** metrics are available on the /metrics endpoint (via OpenTelemetry OTLP export)
**And** alerting threshold for Tier 2/3 fallback rate is configurable per deployment
**And** high Tier 2/3 fallback rate indicates PD is not populating the SN correlation field — actionable by the integration team
**And** SN linkage rate target is tracked: >= 90% of PAGE cases LINKED within 2-hour retry window
**And** unit tests verify: metric increment per tier, gauge accuracy after multiple correlations, configurable alerting threshold
