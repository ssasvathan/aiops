---
stepsCompleted:
  - step-01-document-discovery
  - step-02-prd-analysis
  - step-03-epic-coverage-validation
  - step-04-ux-alignment
  - step-05-epic-quality-review
  - step-06-final-assessment
selectedDocuments:
  prd: /home/sas/workspace/aiops/artifact/planning-artifacts/prd/
  architecture: /home/sas/workspace/aiops/artifact/planning-artifacts/architecture/
  epics: /home/sas/workspace/aiops/artifact/planning-artifacts/epics.md
  ux: none
---

# Implementation Readiness Assessment Report

**Date:** 2026-03-21
**Project:** aiOps

## Document Discovery

### PRD Files Found

**Whole Documents:**
- None retained (user removed duplicate whole-file variant)

**Sharded Documents:**
- Folder: `prd/`
  - index.md
  - domain-specific-requirements.md
  - event-driven-pipeline-specific-requirements.md
  - executive-summary.md
  - functional-requirements.md
  - non-functional-requirements.md
  - process-governance-requirements.md
  - product-scope.md
  - project-classification.md
  - success-criteria.md
  - user-journeys.md

### Architecture Files Found

**Whole Documents:**
- None found

**Sharded Documents:**
- Folder: `architecture/`
  - index.md
  - architecture-validation-results.md
  - core-architectural-decisions.md
  - implementation-patterns-consistency-rules.md
  - project-context-analysis.md
  - project-structure-boundaries.md
  - starter-template-evaluation.md

### Epics & Stories Files Found

**Whole Documents:**
- epics.md

**Sharded Documents:**
- None found

### UX Design Files Found

**Whole Documents:**
- None found

**Sharded Documents:**
- None found

### Discovery Outcome

- PRD source of truth confirmed as `prd/`.
- Duplicate whole PRD variant removed by user request.
- UX documentation confirmed as intentionally not present.

## PRD Analysis

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

Total FRs: 58

### Non-Functional Requirements

NFR-P1: Hot-path gate evaluation completes in p99 <= 500ms per cycle
NFR-P2: Outbox delivery SLO: p95 <= 1 minute, p99 <= 5 minutes from READY to SENT
NFR-P3: Hot-path cycle completion rate: 100% of scheduled intervals execute (per-case errors are caught without killing the loop; cycle-level errors are caught and logged, loop continues)
NFR-P4: Cold-path LLM invocation timeout: 60 seconds maximum per case
NFR-P5: Batched Redis key loading reduces sustained-window state retrieval from O(N) sequential round-trips to O(1) batched calls at scale
NFR-P6: Sustained status computation completes within 50% of the scheduler interval duration across large scope key sets as measured by OTLP histogram
NFR-P7: Peak profile historical window memory footprint grows proportionally with scope count, bounded by configurable retention depth with maximum memory budget per scope
NFR-S1: Secrets (credentials, tokens, webhook URLs) are never emitted in structured logs — masking/redaction patterns enforced for all credential fields
NFR-S2: Denylist enforcement applied at every outbound boundary before external payloads (PagerDuty, Slack, ServiceNow, Kafka, LLM) via shared denylist enforcement function — no boundary-specific reimplementations
NFR-S3: Kafka SASL_SSL keytab and krb5 config paths validated at startup with fail-fast behavior — system does not start with missing or invalid security configuration
NFR-S4: ServiceNow MI-1 guardrails prevent major-incident write scope — system cannot create or modify major incidents
NFR-S5: Integration safety modes default to LOG — no external calls in local/dev unless explicitly configured to MOCK or LIVE
NFR-S6: Prod enforcement rejects MOCK/OFF for critical integrations — prevents accidental non-operational configuration in production
NFR-SC1: Hot-path supports hot/hot 2-pod minimum deployment with zero duplicate dispatches across replicas
NFR-SC2: Scope sharding supports even distribution across pods with O(1) checkpoint writes per shard per interval instead of O(N) per scope
NFR-SC3: Outbox publisher supports concurrent instances with row locking preventing duplicate Kafka publication
NFR-SC4: All coordination mechanisms (cycle lock, sustained state, AG5 dedupe) use Redis as the single shared state layer — no in-process state assumed exclusive
NFR-R1: DEAD outbox rows: standing posture of 0 — any DEAD row triggers operational alerting
NFR-R2: Write-once casefile invariant: triage.json exists in S3 before any downstream event is published to Kafka (Invariant A)
NFR-R3: Outbox guarantees at-least-once Kafka delivery — hot-path continues unaffected during Kafka unavailability, cases accumulate in Postgres (Invariant B2)
NFR-R4: Distributed cycle lock fails open on Redis unavailability — system degrades to single-instance equivalent behavior, never halts
NFR-R5: Sustained window state falls back to None on Redis failure — conservative behavior (treats as first observation, no false sustained=true)
NFR-R6: Critical dependency failures halt processing with loud failure — no silent fallback for invariant violations
NFR-R7: Degradable dependency failures update HealthRegistry, emit degraded events, and continue with capped behavior
NFR-R8: Cold-path LLM failure produces a deterministic fallback DiagnosisReportV1 — the absence of diagnosis.json is explicit and observable, never silent
NFR-A1: All casefiles retained for 25 months with write-once semantics and SHA-256 hash chains
NFR-A2: Every casefile stamps active policy versions (rulebook, peak policy, denylist, anomaly detection policy) at decision time
NFR-A3: Schema envelope versioning enables perpetual read support — old casefiles remain deserializable across the 25-month retention window as schemas evolve
NFR-A4: Structured logs carry correlation_id (case_id) enabling field-level querying of the complete decision trail per case in Elastic
NFR-A5: Gate evaluation trail with full reason codes persisted in ActionDecisionV1 for every triage decision
NFR-A6: Pod identity (POD_NAME, POD_NAMESPACE) stamped in OTLP resource attributes and structured logs for per-instance traceability across replicas
NFR-I1: All external integrations implement OFF|LOG|MOCK|LIVE mode semantics consistently — no integration-specific mode behavior
NFR-I2: External integration failures in degradable mode (Slack, ServiceNow) do not block hot-path cycle execution
NFR-I3: PagerDuty deduplication uses action_fingerprint as dedup_key — duplicate pages for the same fingerprint within TTL are suppressed by PagerDuty
NFR-I4: Cold-path Kafka consumer commits offsets on graceful shutdown — no message loss or reprocessing beyond at-least-once semantics

Total NFRs: 35

### Additional Requirements

#### Process & Governance
- PG1: Each CR must update affected documentation in `docs/` and `README.md` as part of the same change set, ensuring documentation accuracy for the operational deployment
- PG2: All documentation must reference only project-native concepts — no references to BMAD artifacts, story identifiers, epic numbers, or workflow methodology terminology

#### Domain Constraints and Invariants
- 25-month casefile retention with write-once semantics and SHA-256 hash chains ensuring tamper-evident artifact integrity
- Policy version stamping in every casefile — any historical decision can be replayed with the exact rulebook, peak policy, denylist, and anomaly detection policy versions active at decision time
- Schema envelope versioning with perpetual read support across the retention window — old casefiles remain deserializable as schema versions evolve
- Structured logs with correlation IDs (case_id) enabling field-level querying of the full decision trail in Elastic (LASS)
- PAGE is structurally impossible outside PROD+TIER_0 — enforced by environment caps and post-condition safety assertions independent of YAML correctness
- Actions only cap downward, never escalate — monotonic reduction is a design invariant, not a configuration choice
- Environment-based action caps: local=OBSERVE, dev=NOTIFY, uat=TICKET, prod=PAGE
- Hot/cold path separation — the LLM advisory path has no import path, no shared state, and no conditional wait on the deterministic hot path
- UNKNOWN evidence is never collapsed to PRESENT or zero — missing-evidence semantics propagate end-to-end through gate evaluation
- Degradable dependency failures update HealthRegistry and continue with capped behavior
- Critical dependency/invariant failures halt processing with loud failure (no silent fallback)
- Redis unavailability: cycle lock fails open (preserves availability, worst case equals single-instance behavior), sustained state falls back to None (conservative — no false sustained=true)
- All external integrations (PagerDuty, Slack, ServiceNow, LLM) implement OFF|LOG|MOCK|LIVE semantics
- Default-safe operation: LOG unless explicitly configured otherwise — prevents unintended outbound effects in local/dev
- Prod enforcement rejects MOCK/OFF for critical integrations
- Shared denylist enforcement (`apply_denylist()`) at all outbound boundaries — no boundary-specific reimplementations
- ServiceNow MI-1 guardrails prevent major-incident write scope
- Zero duplicate dispatches across pods via distributed cycle lock (one pod executes per interval, losers yield)
- Consistent sustained-window state across replicas via externalized Redis storage
- Atomic AG5 deduplication replacing two-step is_duplicate()+remember() with single SET NX EX
- Outbox row locking preventing concurrent publishers from selecting the same batch
- Pod identity in OTLP resource attributes and structlog context for per-instance observability
- Feature-flagged rollout (DISTRIBUTED_CYCLE_LOCK_ENABLED, default false) for incremental activation
- Write-once casefile stages — each stage file written exactly once by its owning pipeline component, no read-modify-write, no overwrites
- Durable outbox state machine with source-state-guarded SQL transitions (PENDING_OBJECT > READY > SENT/RETRY/DEAD)
- Hash chain verification — each casefile stage includes SHA-256 hash of prior stage files it depends on
- Outbox DEAD=0 standing posture with monitoring and alerting
- S3 put_if_absent enforces idempotent casefile persistence across replicas

#### Event-Driven Pipeline Constraints
- Health endpoint per pod (raw asyncio TCP handler, `/health`) — returns component health registry status map
- Prometheus instant query API ingestion (`/api/v1/query`) — hot-path evidence collection
- Kafka consumer for CaseHeaderEventV1 — cold-path inbound (CR-07, new)
- Kafka publication: `aiops-case-header`, `aiops-triage-excerpt` topics via outbox-publisher
- PagerDuty Events V2 trigger API (PAGE actions)
- Slack incoming webhook (NOTIFY actions, degraded-mode alerts, postmortem notifications)
- ServiceNow table API (TICKET actions — tiered incident correlation, Problem/PIR upserts)
- All inter-stage data flows through frozen Pydantic v1 contracts
- Schema envelope pattern for versioned persistence and Kafka events
- JSON serialization at all I/O boundaries via canonical Pydantic paths
- No ad-hoc serializers — contract models are the source of truth for payload shape
- No end-user auth boundary (no user-facing REST auth routes)
- Integration-driven auth: ServiceNow bearer token, Slack webhook URL, PagerDuty routing key
- Kafka SASL_SSL with Kerberos — keytab and krb5 config paths validated at startup (fail-fast)
- Secrets never logged — masking patterns preserved for credentials and URLs
- Denylist enforcement at all outbound boundaries before external payloads
- Independent Kafka consumer pod with dedicated health endpoint reporting consumer group state
- Consumes CaseHeaderEventV1 from `aiops-case-header` topic
- Retrieves full case context from S3 (guaranteed by Invariant A — triage.json exists before header on Kafka)
- Reconstructs triage excerpt and evidence summary from persisted casefile data
- Delegates to existing `run_cold_path_diagnosis()` for LLM invocation and `diagnosis.json` persistence
- Graceful shutdown with consumer offset commit
- No eligibility criteria — LLM diagnosis runs for all cases (CR-08)
- Redis-based distributed cycle lock: one hot-path pod executes per scheduler interval, losers yield
- Coordination state exposed in health endpoint: lock holder status, lock expiry time, last cycle execution timestamp
- Informational only — coordination state does not affect K8s liveness/readiness probe health status
- Fail-open on Redis unavailability (preserves availability, worst case equals single-instance behavior)
- Feature-flagged: `DISTRIBUTED_CYCLE_LOCK_ENABLED` (default false) for incremental rollout
- OTLP counters: lock acquired, lock yielded, lock failed
- No manual lock-release API — TTL-based self-healing with direct Redis key deletion available for emergencies
- Topology registry YAML relocated to `config/` alongside other policy and configuration files
- Deployed as part of the deployment package within the project folder
- `TOPOLOGY_REGISTRY_PATH` default and Docker env references point to `config/` location
- Single format only (instances-based) — all legacy v0 format support removed
- Hot-path reload-on-change behavior preserved
- **Error taxonomy:** Critical invariant violations raise halt-class exceptions; degradable dependency failures raise degradable exceptions and continue with caps
- **Config as leaf:** `config/settings.py` must not import specific contract classes; `load_policy_yaml(path, model_class)` stays generic
- **Integration mode framework:** All external integrations implement OFF|LOG|MOCK|LIVE consistently; default LOG unless explicitly configured
- **Observability:** Pod identity (POD_NAME, POD_NAMESPACE) in OTLP resource attributes and structlog context for per-instance visibility across replicas
- **Policy loading:** All policies loaded once at startup (no per-cycle disk I/O); topology registry is the exception with reload-on-change

### PRD Completeness Assessment

- PRD structure is complete and internally consistent for implementation planning: functional requirements, non-functional requirements, governance constraints, and domain invariants are explicitly documented.
- Requirement traceability anchors are strong: FR1-FR58 and NFR-P1..NFR-I4 are explicitly enumerated with implementation-oriented wording.
- Cross-cutting operational constraints (safety invariants, degraded-mode behavior, integration mode semantics, distributed coordination rules) are sufficiently explicit for epic-level coverage validation.
- Known limitation noted from discovery: no UX specification document exists, so UX validation scope is intentionally not applicable for this assessment.

## Epic Coverage Validation

### Epic FR Coverage Extracted

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

Total FRs in epics: 58

### Coverage Matrix

| FR Number | PRD Requirement | Epic Coverage | Status |
| --------- | --------------- | ------------- | ------ |
| FR1 | The hot-path can query Prometheus for infrastructure telemetry metrics on a configurable scheduler interval | Epic 1 - Deterministic anomaly triage for responders | Covered |
| FR2 | The hot-path can detect consumer lag anomalies, throughput constrained anomalies, and volume drop anomalies across all monitored scopes | Epic 1 - Deterministic anomaly triage for responders | Covered |
| FR3 | The hot-path can evaluate anomaly detection thresholds against per-scope statistical baselines computed from historical metric data, falling back to configured defaults when baseline history is insufficient | Epic 1 - Deterministic anomaly triage for responders | Covered |
| FR4 | The hot-path can compute and persist per-scope metric baselines to Redis with environment-specific TTLs | Epic 1 - Deterministic anomaly triage for responders | Covered |
| FR5 | The hot-path can load sustained window state from Redis before evidence evaluation and persist updated state after, enabling sustained anomaly tracking across cycles and pod restarts | Epic 1 - Deterministic anomaly triage for responders | Covered |
| FR6 | The hot-path can batch Redis key loading operations instead of sequential per-key round-trips for sustained window state and peak profile retrieval | Epic 1 - Deterministic anomaly triage for responders | Covered |
| FR7 | The hot-path can emit a TelemetryDegradedEvent when Prometheus is unavailable, propagating UNKNOWN evidence status through downstream stages | Epic 1 - Deterministic anomaly triage for responders | Covered |
| FR8 | The hot-path can classify anomaly patterns as PEAK, NEAR_PEAK, or OFF_PEAK using cached peak profiles from Redis, replacing the previous always-UNKNOWN behavior | Epic 1 - Deterministic anomaly triage for responders | Covered |
| FR9 | The hot-path can compute sustained anomaly status per scope using externalized Redis state shared across all hot-path replicas | Epic 1 - Deterministic anomaly triage for responders | Covered |
| FR10 | The hot-path can parallelize sustained status computation across large scope key sets for performance at scale | Epic 1 - Deterministic anomaly triage for responders | Covered |
| FR11 | The hot-path can manage peak profile historical window memory efficiently with bounded retention to control per-process memory footprint | Epic 1 - Deterministic anomaly triage for responders | Covered |
| FR12 | The hot-path can load topology registry from a single YAML format (instances-based) located in `config/` | Epic 1 - Deterministic anomaly triage for responders | Covered |
| FR13 | The hot-path can resolve stream identity, topic role (SOURCE_TOPIC/SHARED_TOPIC/SINK_TOPIC), and blast radius classification for each anomaly scope | Epic 1 - Deterministic anomaly triage for responders | Covered |
| FR14 | The hot-path can route ownership through multi-level lookup: consumer group > topic > stream > platform default, with confidence scoring | Epic 1 - Deterministic anomaly triage for responders | Covered |
| FR15 | The hot-path can reload the topology registry on file change without requiring process restart | Epic 1 - Deterministic anomaly triage for responders | Covered |
| FR16 | The hot-path can identify downstream consumer impact for blast radius assessment | Epic 1 - Deterministic anomaly triage for responders | Covered |
| FR17 | The hot-path can evaluate gates AG0 through AG6 sequentially, driven by YAML-defined check types and predicates dispatched through a handler registry | Epic 1 - Deterministic anomaly triage for responders | Covered |
| FR18 | The hot-path can enforce environment-based action caps (local=OBSERVE, dev=NOTIFY, uat=TICKET, prod=PAGE) through AG1, with actions only capping downward, never escalating | Epic 1 - Deterministic anomaly triage for responders | Covered |
| FR19 | The hot-path can enforce that PAGE is structurally impossible outside PROD+TIER_0 via post-condition safety assertions independent of YAML correctness | Epic 1 - Deterministic anomaly triage for responders | Covered |
| FR20 | The hot-path can evaluate evidence sufficiency (AG2) with UNKNOWN evidence propagation — never collapsing missing evidence to PRESENT or zero | Epic 1 - Deterministic anomaly triage for responders | Covered |
| FR21 | The hot-path can validate source topic classification (AG3) against topology-resolved topic roles | Epic 1 - Deterministic anomaly triage for responders | Covered |
| FR22 | The hot-path can evaluate sustained threshold and confidence floor (AG4) using externalized sustained state | Epic 1 - Deterministic anomaly triage for responders | Covered |
| FR23 | The hot-path can perform atomic action deduplication (AG5) using atomic set-if-not-exists with TTL as a single authoritative check, eliminating the two-step race condition | Epic 1 - Deterministic anomaly triage for responders | Covered |
| FR24 | The hot-path can evaluate postmortem predicates (AG6) for qualifying cases during peak windows, now that peak classification produces real PEAK/NEAR_PEAK/OFF_PEAK states | Epic 1 - Deterministic anomaly triage for responders | Covered |
| FR25 | The hot-path can produce an ActionDecisionV1 with full reason codes and gate evaluation trail for every triage decision | Epic 1 - Deterministic anomaly triage for responders | Covered |
| FR26 | The hot-path can assemble a write-once CaseFileTriageV1 in object storage with SHA-256 hash chain, ensuring triage.json exists before any downstream event is published (Invariant A) | Epic 2 - Durable case artifacts and reliable action dispatch | Covered |
| FR27 | The hot-path can insert outbox rows with PENDING_OBJECT > READY state transitions, enforced by source-state-guarded transitions | Epic 2 - Durable case artifacts and reliable action dispatch | Covered |
| FR28 | The outbox-publisher can drain READY rows and publish CaseHeaderEventV1 and TriageExcerptV1 to Kafka with at-least-once delivery (Invariant B2) | Epic 2 - Durable case artifacts and reliable action dispatch | Covered |
| FR29 | The outbox-publisher can lock rows during selection to prevent concurrent publisher instances from publishing the same batch | Epic 2 - Durable case artifacts and reliable action dispatch | Covered |
| FR30 | The casefile-lifecycle runner can scan object storage and purge expired casefiles according to the retention policy | Epic 2 - Durable case artifacts and reliable action dispatch | Covered |
| FR31 | The system can stamp policy versions (rulebook, peak policy, denylist, anomaly detection policy) in every casefile for 25-month decision replay | Epic 2 - Durable case artifacts and reliable action dispatch | Covered |
| FR32 | The hot-path can trigger PagerDuty pages via Events V2 API for PAGE action decisions with action fingerprint as dedup key | Epic 2 - Durable case artifacts and reliable action dispatch | Covered |
| FR33 | The hot-path can send Slack notifications for NOTIFY actions, degraded-mode alerts, and postmortem candidacy notifications | Epic 2 - Durable case artifacts and reliable action dispatch | Covered |
| FR34 | The hot-path can fall back to structured log output when Slack is unavailable | Epic 2 - Durable case artifacts and reliable action dispatch | Covered |
| FR35 | The system can enforce denylist at all outbound boundaries before any external payload is dispatched | Epic 2 - Durable case artifacts and reliable action dispatch | Covered |
| FR36 | The cold-path can consume CaseHeaderEventV1 from Kafka as an independent consumer pod | Epic 3 - LLM-enriched diagnosis on the cold path | Covered |
| FR37 | The cold-path can retrieve full case context from S3, reconstruct triage excerpt and evidence summary from persisted casefile data | Epic 3 - LLM-enriched diagnosis on the cold path | Covered |
| FR38 | The cold-path can produce a deterministic text evidence summary rendering a case's evidence state for LLM consumption, distinguishing PRESENT/UNKNOWN/ABSENT/STALE evidence and including anomaly findings, temporal context, and topic role | Epic 3 - LLM-enriched diagnosis on the cold path | Covered |
| FR39 | The cold-path can invoke LLM diagnosis for every case regardless of environment, criticality tier, or sustained status | Epic 3 - LLM-enriched diagnosis on the cold path | Covered |
| FR40 | The cold-path can submit an enriched prompt including full Finding fields (severity, reason_codes, evidence_required, is_primary), topic_role, routing_key, anomaly family domain descriptions, confidence calibration guidance, fault domain examples, and a few-shot example | Epic 3 - LLM-enriched diagnosis on the cold path | Covered |
| FR41 | The cold-path can produce a schema-validated DiagnosisReportV1 with structured evidence citations, verdict, fault domain, confidence, next checks, and evidence gaps | Epic 3 - LLM-enriched diagnosis on the cold path | Covered |
| FR42 | The cold-path can produce a deterministic fallback report when LLM invocation fails (timeout, unavailability, schema validation failure) | Epic 3 - LLM-enriched diagnosis on the cold path | Covered |
| FR43 | The cold-path can write diagnosis.json to object storage with SHA-256 hash chain linking to triage.json | Epic 3 - LLM-enriched diagnosis on the cold path | Covered |
| FR44 | The hot-path can acquire a distributed cycle lock so only one pod executes per scheduler interval, with losers yielding and retrying next interval | Epic 4 - Multi-replica coordination and throughput safety | Covered |
| FR45 | The hot-path can fail open on Redis unavailability for cycle lock (preserving availability, worst case equals single-instance behavior) | Epic 4 - Multi-replica coordination and throughput safety | Covered |
| FR46 | The hot-path can assign scope-level shards to pods for findings cache coordination, with batch checkpoint per shard per interval replacing per-scope writes | Epic 4 - Multi-replica coordination and throughput safety | Covered |
| FR47 | The hot-path can recover shards from a failed pod via lease expiry, allowing another pod to safely resume | Epic 4 - Multi-replica coordination and throughput safety | Covered |
| FR48 | The system can enable distributed coordination incrementally via feature flag (DISTRIBUTED_CYCLE_LOCK_ENABLED, default false) | Epic 4 - Multi-replica coordination and throughput safety | Covered |
| FR49 | The system can load all policies from YAML at startup (rulebook, peak policy, anomaly detection policy, Redis TTL policy, Prometheus metrics contract, outbox policy, retention policy, denylist, topology registry) | Epic 5 - Policy-driven operations and observability | Covered |
| FR50 | The system can resolve environment configuration through environment-identifier-driven env file selection with environment variable override precedence | Epic 5 - Policy-driven operations and observability | Covered |
| FR51 | The system can validate Kafka SASL_SSL configuration at startup with fail-fast behavior for missing keytab or krb5 config paths | Epic 5 - Policy-driven operations and observability | Covered |
| FR52 | Operators can tune anomaly detection sensitivity, rulebook thresholds, peak policy, and denylist through versioned YAML changes without code modifications | Epic 5 - Policy-driven operations and observability | Covered |
| FR53 | Application teams can edit topology registry and denylist YAML, deploy to lower environments, verify behavior through casefile inspection, and promote to production | Epic 5 - Policy-driven operations and observability | Covered |
| FR54 | Each runtime mode pod can expose a health endpoint reporting component health registry status | Epic 5 - Policy-driven operations and observability | Covered |
| FR55 | The hot-path health endpoint can report distributed coordination state (lock holder status, lock expiry time, last cycle execution) as informational data that does not affect K8s probe health status | Epic 5 - Policy-driven operations and observability | Covered |
| FR56 | The system can export OTLP metrics for pipeline health (cycle completion, outbox delivery, gate evaluation latency, deduplication, coordination lock stats) | Epic 5 - Policy-driven operations and observability | Covered |
| FR57 | The system can emit structured logs with correlation IDs (case_id), pod identity (POD_NAME, POD_NAMESPACE), and consistent field naming for field-level querying in Elastic | Epic 5 - Policy-driven operations and observability | Covered |
| FR58 | The system can evaluate operational alert thresholds at runtime against live metric state | Epic 5 - Policy-driven operations and observability | Covered |

### Missing Requirements

No missing FR coverage identified. All PRD functional requirements have epic-level coverage.

### Coverage Statistics

- Total PRD FRs: 58
- FRs covered in epics: 58
- Coverage percentage: 100.00%

## UX Alignment Assessment

### UX Document Status

- Not Found

### Alignment Issues

- No product UX/UI alignment issue identified: project scope and epic definitions describe a backend event-driven pipeline with no user-facing UI component.
- Existing user interactions are operational integrations and observability tooling (PagerDuty/Slack/ServiceNow, Dynatrace, Kibana), not a first-party application interface requiring UX specifications.

### Warnings

- No warning raised for missing UX document because UX is not implied by the defined product surface.

## Epic Quality Review

### Best-Practice Checklist

| Epic | User Value | Independent Value | No Forward Dependencies | Story Sizing | AC Quality | Traceability |
| ---- | ---------- | ----------------- | ----------------------- | ------------ | ---------- | ------------ |
| Epic 1 | Pass | Pass | Pass | Concern | Pass | Pass |
| Epic 2 | Pass | Pass | Pass | Pass | Pass | Pass |
| Epic 3 | Pass | Pass | Pass | Concern | Concern | Pass |
| Epic 4 | Pass | Pass | Pass | Pass | Concern | Pass |
| Epic 5 | Pass | Pass | Pass | Concern | Concern | Pass |

### 🔴 Critical Violations

- None identified.

### 🟠 Major Issues

- Story granularity is oversized in several places, reducing independent completable scope: Story 1.5 (AG0-AG3 + handler registry + cap logic assertions), Story 1.6 (AG4-AG6 + atomic dedupe + decision trail), Story 3.3 (unconditional invocation + enriched prompt + schema validation), Story 5.1 (load and validate all policy classes in one story).
- Acceptance criteria are uneven on failure-mode specificity for some high-risk stories: Story 3.3 (provider timeouts/retries and provider error classes), Story 4.2 (lease contention/recovery race), Story 5.1 (partial or conflicting policy artifact states), Story 5.3 (promotion rollback/verification gates).

### 🟡 Minor Concerns

- Epics frontmatter input documents still reference `artifact/planning-artifacts/prd-validation-report.md`, which is no longer part of the selected source set.
- Story titles in Epics 4 and 5 are strongly technical; user-value framing is present in story statements but should be reinforced in story titles for consistency.

### Remediation Guidance

- Split oversized stories into narrower deliverables with hard acceptance boundaries (for example, split Story 1.5 into AG0-AG1 policy evaluation and AG2-AG3 evidence/source validation).
- Add explicit negative-path acceptance criteria to high-risk stories covering timeout, malformed payload/schema, lock contention, and rollback outcomes.
- Update epics metadata to remove stale artifact references and keep traceability inputs aligned with active planning sources.
- Keep epic/story titles outcome-oriented by naming operator/on-call benefit directly where feasible.

## Summary and Recommendations

### Overall Readiness Status

NEEDS WORK

### Critical Issues Requiring Immediate Action

- No FR coverage gaps were found, but implementation-readiness quality risks remain in story granularity and acceptance criteria precision for several high-risk stories.
- Stale artifact reference remains in `epics.md` frontmatter (`prd-validation-report.md`), creating potential traceability confusion during implementation.

### Recommended Next Steps

1. Split oversized stories (1.5, 1.6, 3.3, 5.1) into independently completable units with narrower acceptance boundaries.
2. Strengthen acceptance criteria with explicit negative-path and failure-mode checks for lock contention, Redis/Kafka/LLM failures, schema rejection, and policy conflict conditions.
3. Update epics metadata and planning references to align with current source-of-truth artifacts (`prd/`, `architecture/`, `epics.md`) and remove stale references.

### Final Note

This assessment identified 4 issues across 2 categories (major quality issues and minor documentation hygiene). Address these issues before implementation for stronger execution reliability; otherwise proceed with explicit risk acceptance.

### Assessment Metadata

- Assessment date: 2026-03-22
- Assessor: Codex (bmad-bmm-check-implementation-readiness workflow)
