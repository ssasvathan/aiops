# Non-Functional Requirements

## Performance

- **NFR-P1a: Compute latency.** Prometheus query start → CaseFile `triage.json` written to object storage (stages 1–4): p95 ≤ 30 seconds, p99 ≤ 60 seconds. Excludes outbox publish and external integration calls. Measured per evaluation cycle per (env, cluster_id). Targets are tuneable per environment.
- **NFR-P1b: Delivery latency (Outbox SLO).** CaseFile triage write confirmed → Kafka header published (stage 5): p95 ≤ 1 minute, p99 ≤ 5 minutes per outbox-policy-v1. Breach of p99 > 10 minutes is critical.
- **NFR-P1c: Action dispatch latency (informational).** Kafka header observed by consumer → PD trigger sent / Slack posted / log emitted (stages 6–7): tracked as a separate metric. Integration-dependent; no hard SLO initially — baseline established in Phase 1A.
- **NFR-P2: Evaluation interval adherence.** 5-minute evaluation intervals aligned to wall-clock boundaries (00, 05, 10, ...) must not drift by more than 30 seconds under normal load. Missed intervals must be logged as operational warnings with catch-up behavior documented.
- **NFR-P3: Rulebook gating latency.** GateInput.v1 → ActionDecision.v1: p99 ≤ 500ms. Gating is deterministic policy evaluation with no external dependencies — latency is bounded by computation, not I/O.
- **NFR-P4: LLM cold-path response bound.** LLM invocation timeout ≤ 60 seconds. If exceeded, emit DiagnosisReport fallback (verdict=UNKNOWN, confidence=LOW, reason_codes=[LLM_TIMEOUT]) and continue. No retry within the same evaluation cycle.
- **NFR-P5: Registry lookup latency.** Topology resolution (anomaly key → stream_id + ownership + tier): p99 ≤ 50ms. Registry is loaded into memory at startup; lookups are local. Reload on registry change ≤ 5 seconds.
- **NFR-P6: Concurrent case throughput.** The system must handle at least 100 concurrent active cases per evaluation interval without degrading hot-path compute latency (NFR-P1a) p95 target. This covers the top-N critical streams across Business_Essential + Business_Critical clusters.

## Security

- **NFR-S1: Encryption in transit.** All network communication between pipeline components, external integrations (PD, SN, Slack, Prometheus, object storage), and Kafka must use TLS 1.2+. Local-dev (Mode A) may use plaintext for docker-compose internal networks only.
- **NFR-S2: Encryption at rest.** CaseFiles in object storage must be encrypted at rest using server-side encryption (SSE). Outbox records in Postgres must use encrypted storage volumes. Redis cache data is ephemeral and does not require at-rest encryption, but transport must be TLS in prod.
- **NFR-S3: CaseFile access control.** Object storage access to CaseFiles must be restricted to: pipeline service accounts (read/write), authorized audit users (read-only), and lifecycle management (delete per retention policy only). No anonymous or broad-role access.
- **NFR-S4: Integration credential management.** Credentials for external integrations (PD, SN, Slack, Prometheus, object storage) must be stored in a secrets manager or injected via mounted secrets — never in config files, CaseFiles, or logs. Credential rotation must be supported via the secrets manager/mount mechanism; pipeline restart is allowed if required by the rotation mechanism but no code change is required to rotate.
- **NFR-S5: Exposure denylist enforcement coverage.** The exposure denylist must be applied at every output boundary: TriageExcerpt assembly, Slack notification formatting, SN Problem/PIR description composition, and LLM-generated narrative surfacing. Automated tests must verify denylist enforcement at each boundary. Zero violations is the target (per success criteria).
- **NFR-S6: Audit log completeness.** All SN API calls, PD triggers, Slack notifications, CaseFile writes, and outbox state transitions must be logged with: timestamp, request_id, case_id, action, outcome, latency. Logs must be retained for at least 90 days in prod (aligned with DEAD outbox retention for forensics).
- **NFR-S7: No privilege escalation via configuration.** Integration mode changes (e.g., LOG → LIVE) must be controlled by environment configuration — not runtime API or operator action. Changing from non-prod endpoints to prod endpoints must require a deployment, not a config toggle.
- **NFR-S8: LLM data handling.** LLM prompts and responses must comply with exposure caps (denylist enforced on inputs and outputs). LLM calls must use approved, bank-sanctioned endpoints only. The LLM vendor contract must prohibit training on submitted data. LLM prompt/response logging must meet bank data retention and classification policies — logs must not persist longer than the approved retention window and must be stored in bank-controlled infrastructure. Prompt content must not include PII, credentials, or denylist-excluded fields.

## Reliability

- **NFR-R1: Pipeline continuity under component failures.** The system must continue processing cases when any single non-critical component fails. Specifically:
  - Redis unavailable → pipeline continues; actions capped to NOTIFY-only (AG5 degraded mode); `DegradedModeEvent` emitted
  - LLM unavailable → hot path unaffected; cold-path emits fallback DiagnosisReport; CaseFile triage stage complete and actionable
  - Slack unavailable → notification degrades to structured log; no pipeline interruption
  - SN unavailable (Phase 1B) → linkage enters retry loop (2-hour window); FAILED_FINAL escalation via Slack/log
- **NFR-R2: Critical path failure = stop.** Failure of critical-path components must halt processing with explicit alerting (not silent degradation):
  - Object storage unavailable → cannot write CaseFile → pipeline halts (Invariant A non-negotiable)
  - Postgres unavailable → outbox cannot operate → pipeline halts (Invariant B2 non-negotiable)
  - Kafka unavailable → no publish possible → outbox accumulates READY; alerts on READY age thresholds
  - Prometheus unavailable → do NOT emit normal cases with all-UNKNOWN evidence; emit a `TelemetryDegradedEvent` (affected scope, reason, recovery status) and cap actions to OBSERVE/NOTIFY until Prometheus recovers. Individual missing series for specific metrics still map to `EvidenceStatus=UNKNOWN` per normal processing — this rule applies only to total Prometheus unavailability.
- **NFR-R3: Recovery behavior.** After component recovery:
  - Redis: dedupe state rebuilt from scratch (cache-only, no persistent state lost); no catch-up required
  - Outbox: RETRY records resume exponential backoff automatically; no manual intervention for RETRY
  - SN linkage: FAILED_TEMP cases resume retry on next cycle; FAILED_FINAL cases remain terminal (human review required)
  - LLM: next evaluation cycle includes LLM diagnosis normally; no backfill of missed diagnoses for prior cases
  - Prometheus: `TelemetryDegradedEvent` clears; normal evaluation resumes on next interval; no backfill of missed intervals
- **NFR-R4: DEAD=0 prod posture.** Any DEAD outbox row in prod is a critical operational event. Recovery from DEAD requires human investigation and explicit replay/resolution — no automatic retry of DEAD records.
- **NFR-R5: Data durability.** CaseFile in object storage must survive single-node failures (object store replication or equivalent). Outbox in Postgres must survive single-node failures (WAL + replication or equivalent). These are infrastructure-level requirements — the pipeline assumes durable storage and does not implement its own replication.

## Operability

- **NFR-O1: Meta-monitoring (observability of the observer).** The AIOps system must expose health metrics for its own components:
  - Outbox: queue depth by state (PENDING_OBJECT, READY, RETRY, DEAD, SENT), age of oldest per state, publish latency histogram
  - Redis: connection status, cache hit/miss rate, dedupe key count
  - LLM: invocation count, latency histogram, timeout/error rate, fallback rate
  - Evidence Builder: evaluation interval adherence, cases produced per interval, UNKNOWN rate by metric
  - Prometheus connectivity: scrape success/failure, `TelemetryDegradedEvent` active/cleared
  - Pipeline: end-to-end compute latency histogram (NFR-P1a), delivery latency histogram (NFR-P1b), case throughput
- **NFR-O2: Alerting thresholds defined.** Alerting rules must exist for: outbox age thresholds (per outbox-policy-v1), DEAD>0 (crit in prod), Redis connection loss, Prometheus unavailability (`TelemetryDegradedEvent`), LLM error rate spikes, evaluation interval drift, and pipeline latency breach. Alert definitions must be versioned and reviewed as operational artifacts.
- **NFR-O3: Structured logging.** All pipeline events must use structured logging (JSON) with consistent fields: timestamp, correlation_id (case_id), component, event_type, severity, and contextual fields. Log levels: ERROR for failures requiring attention, WARN for degraded behavior, INFO for normal processing, DEBUG for diagnostic detail.
- **NFR-O4: Configuration transparency.** Active configuration (integration modes, environment, LLM endpoint, feature flags) must be logged at startup and queryable at runtime. Configuration changes that affect behavior (e.g., integration mode switches via deployment) must be logged as operational events.
- **NFR-O5: Deployment independence.** Each phase must be independently deployable without requiring coordinated deployment of unrelated components. Phase 1B (SN linkage) must be deployable as an add-on to Phase 1A without redeploying the hot-path pipeline. Cold-path components (LLM, SN linkage) must be independently restartable.
- **NFR-O6: Graceful shutdown.** Pipeline shutdown must: complete in-flight evaluation cycles (or mark them interrupted), flush outbox READY records to Kafka before exit (best-effort), and log shutdown state. No silent data loss on controlled shutdown.

## Testability & Auditability

- **NFR-T1: Decision reproducibility.** Given a CaseFile (evidence snapshot + policy version stamps), any historical gating decision must be reproducible by loading the referenced policy versions and re-evaluating the Rulebook. A regression test suite must exercise this for representative cases.
- **NFR-T2: Invariant verification.** Automated tests must verify:
  - Invariant A: CaseFile exists in object storage before Kafka header appears (write-before-publish)
  - Invariant B2: Outbox publishes after crash recovery (simulate crash between CaseFile write and Kafka publish)
  - UNKNOWN propagation: missing Prometheus series → UNKNOWN through evidence → peak → confidence → gating
  - Exposure denylist: no denied fields in TriageExcerpt, Slack, SN outputs
  - `TelemetryDegradedEvent`: Prometheus unavailability → no normal all-UNKNOWN cases emitted; actions capped to OBSERVE/NOTIFY
- **NFR-T3: LLM degradation testing.** The pipeline must be testable with LLM in stub/failure-injection mode (local and test environments only — produces deterministic fallback DiagnosisReport without external API calls), LLM simulated timeout, and LLM returning malformed output. Each scenario must produce a valid CaseFile `triage.json` + header/excerpt + safely-gated action. LLM must run LIVE in prod — stub mode is not permitted in prod.
- **NFR-T4: Storm-control simulation.** Tests must verify: Redis failure → NOTIFY-only cap + `DegradedModeEvent`; rapid duplicate cases → dedupe suppression; rapid recovery → normal behavior resumes.
- **NFR-T5: End-to-end pipeline test.** A single test must exercise the full hot-path: harness traffic → evidence collection → peak → topology → CaseFile write → outbox → Kafka publish → gating → action. Runnable locally (Mode A, docker-compose) with no external dependencies.
- **NFR-T6: Audit trail completeness verification.** Tests must verify that a CaseFile contains: all evidence used in the decision, all gate rule IDs + reason codes, policy version stamps, and SHA-256 hash. An auditor persona test must demonstrate: retrieve CaseFile → trace evidence → trace gating → verify action was correct given policy.
