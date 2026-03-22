# Functional Requirements

## Evidence Collection & Anomaly Detection

- FR1: The hot-path can query Prometheus for infrastructure telemetry metrics on a configurable scheduler interval
- FR2: The hot-path can detect consumer lag anomalies, throughput constrained anomalies, and volume drop anomalies across all monitored scopes
- FR3: The hot-path can evaluate anomaly detection thresholds against per-scope statistical baselines computed from historical metric data, falling back to configured defaults when baseline history is insufficient
- FR4: The hot-path can compute and persist per-scope metric baselines to Redis with environment-specific TTLs
- FR5: The hot-path can load sustained window state from Redis before evidence evaluation and persist updated state after, enabling sustained anomaly tracking across cycles and pod restarts
- FR6: The hot-path can batch Redis key loading operations instead of sequential per-key round-trips for sustained window state and peak profile retrieval
- FR7: The hot-path can emit a TelemetryDegradedEvent when Prometheus is unavailable, propagating UNKNOWN evidence status through downstream stages

## Peak & Sustained Classification

- FR8: The hot-path can classify anomaly patterns as PEAK, NEAR_PEAK, or OFF_PEAK using cached peak profiles from Redis, replacing the previous always-UNKNOWN behavior
- FR9: The hot-path can compute sustained anomaly status per scope using externalized Redis state shared across all hot-path replicas
- FR10: The hot-path can parallelize sustained status computation across large scope key sets for performance at scale
- FR11: The hot-path can manage peak profile historical window memory efficiently with bounded retention to control per-process memory footprint

## Topology Resolution & Ownership Routing

- FR12: The hot-path can load topology registry from a single YAML format (instances-based) located in `config/`
- FR13: The hot-path can resolve stream identity, topic role (SOURCE_TOPIC/SHARED_TOPIC/SINK_TOPIC), and blast radius classification for each anomaly scope
- FR14: The hot-path can route ownership through multi-level lookup: consumer group > topic > stream > platform default, with confidence scoring
- FR15: The hot-path can reload the topology registry on file change without requiring process restart
- FR16: The hot-path can identify downstream consumer impact for blast radius assessment

## Deterministic Gating & Action Decisions

- FR17: The hot-path can evaluate gates AG0 through AG6 sequentially, driven by YAML-defined check types and predicates dispatched through a handler registry
- FR18: The hot-path can enforce environment-based action caps (local=OBSERVE, dev=NOTIFY, uat=TICKET, prod=PAGE) through AG1, with actions only capping downward, never escalating
- FR19: The hot-path can enforce that PAGE is structurally impossible outside PROD+TIER_0 via post-condition safety assertions independent of YAML correctness
- FR20: The hot-path can evaluate evidence sufficiency (AG2) with UNKNOWN evidence propagation — never collapsing missing evidence to PRESENT or zero
- FR21: The hot-path can validate source topic classification (AG3) against topology-resolved topic roles
- FR22: The hot-path can evaluate sustained threshold and confidence floor (AG4) using externalized sustained state
- FR23: The hot-path can perform atomic action deduplication (AG5) using atomic set-if-not-exists with TTL as a single authoritative check, eliminating the two-step race condition
- FR24: The hot-path can evaluate postmortem predicates (AG6) for qualifying cases during peak windows, now that peak classification produces real PEAK/NEAR_PEAK/OFF_PEAK states
- FR25: The hot-path can produce an ActionDecisionV1 with full reason codes and gate evaluation trail for every triage decision

## Case Management & Persistence

- FR26: The hot-path can assemble a write-once CaseFileTriageV1 in object storage with SHA-256 hash chain, ensuring triage.json exists before any downstream event is published (Invariant A)
- FR27: The hot-path can insert outbox rows with PENDING_OBJECT > READY state transitions, enforced by source-state-guarded transitions
- FR28: The outbox-publisher can drain READY rows and publish CaseHeaderEventV1 and TriageExcerptV1 to Kafka with at-least-once delivery (Invariant B2)
- FR29: The outbox-publisher can lock rows during selection to prevent concurrent publisher instances from publishing the same batch
- FR30: The casefile-lifecycle runner can scan object storage and purge expired casefiles according to the retention policy
- FR31: The system can stamp policy versions (rulebook, peak policy, denylist, anomaly detection policy) in every casefile for 25-month decision replay

## Action Dispatch

- FR32: The hot-path can trigger PagerDuty pages via Events V2 API for PAGE action decisions with action fingerprint as dedup key
- FR33: The hot-path can send Slack notifications for NOTIFY actions, degraded-mode alerts, and postmortem candidacy notifications
- FR34: The hot-path can fall back to structured log output when Slack is unavailable
- FR35: The system can enforce denylist at all outbound boundaries before any external payload is dispatched

## LLM Diagnosis (Cold Path)

- FR36: The cold-path can consume CaseHeaderEventV1 from Kafka as an independent consumer pod
- FR37: The cold-path can retrieve full case context from S3, reconstruct triage excerpt and evidence summary from persisted casefile data
- FR38: The cold-path can produce a deterministic text evidence summary rendering a case's evidence state for LLM consumption, distinguishing PRESENT/UNKNOWN/ABSENT/STALE evidence and including anomaly findings, temporal context, and topic role
- FR39: The cold-path can invoke LLM diagnosis for every case regardless of environment, criticality tier, or sustained status
- FR40: The cold-path can submit an enriched prompt including full Finding fields (severity, reason_codes, evidence_required, is_primary), topic_role, routing_key, anomaly family domain descriptions, confidence calibration guidance, fault domain examples, and a few-shot example
- FR41: The cold-path can produce a schema-validated DiagnosisReportV1 with structured evidence citations, verdict, fault domain, confidence, next checks, and evidence gaps
- FR42: The cold-path can produce a deterministic fallback report when LLM invocation fails (timeout, unavailability, schema validation failure)
- FR43: The cold-path can write diagnosis.json to object storage with SHA-256 hash chain linking to triage.json

## Distributed Operations

- FR44: The hot-path can acquire a distributed cycle lock so only one pod executes per scheduler interval, with losers yielding and retrying next interval
- FR45: The hot-path can fail open on Redis unavailability for cycle lock (preserving availability, worst case equals single-instance behavior)
- FR46: The hot-path can assign scope-level shards to pods for findings cache coordination, with batch checkpoint per shard per interval replacing per-scope writes
- FR47: The hot-path can recover shards from a failed pod via lease expiry, allowing another pod to safely resume
- FR48: The system can enable distributed coordination incrementally via feature flag (DISTRIBUTED_CYCLE_LOCK_ENABLED, default false)

## Configuration & Policy Management

- FR49: The system can load all policies from YAML at startup (rulebook, peak policy, anomaly detection policy, Redis TTL policy, Prometheus metrics contract, outbox policy, retention policy, denylist, topology registry)
- FR50: The system can resolve environment configuration through environment-identifier-driven env file selection with environment variable override precedence
- FR51: The system can validate Kafka SASL_SSL configuration at startup with fail-fast behavior for missing keytab or krb5 config paths
- FR52: Operators can tune anomaly detection sensitivity, rulebook thresholds, peak policy, and denylist through versioned YAML changes without code modifications
- FR53: Application teams can edit topology registry and denylist YAML, deploy to lower environments, verify behavior through casefile inspection, and promote to production

## Observability & Health

- FR54: Each runtime mode pod can expose a health endpoint reporting component health registry status
- FR55: The hot-path health endpoint can report distributed coordination state (lock holder status, lock expiry time, last cycle execution) as informational data that does not affect K8s probe health status
- FR56: The system can export OTLP metrics for pipeline health (cycle completion, outbox delivery, gate evaluation latency, deduplication, coordination lock stats)
- FR57: The system can emit structured logs with correlation IDs (case_id), pod identity (POD_NAME, POD_NAMESPACE), and consistent field naming for field-level querying in Elastic
- FR58: The system can evaluate operational alert thresholds at runtime against live metric state
