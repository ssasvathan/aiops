# Non-Functional Requirements

## Performance

- NFR-P1: Hot-path gate evaluation completes in p99 <= 500ms per cycle
- NFR-P2: Outbox delivery SLO: p95 <= 1 minute, p99 <= 5 minutes from READY to SENT
- NFR-P3: Hot-path cycle completion rate: 100% of scheduled intervals execute (per-case errors are caught without killing the loop; cycle-level errors are caught and logged, loop continues)
- NFR-P4: Cold-path LLM invocation timeout: 60 seconds maximum per case
- NFR-P5: Batched Redis key loading reduces sustained-window state retrieval from O(N) sequential round-trips to O(1) batched calls at scale
- NFR-P6: Sustained status computation completes within 50% of the scheduler interval duration across large scope key sets as measured by OTLP histogram
- NFR-P7: Peak profile historical window memory footprint grows proportionally with scope count, bounded by configurable retention depth with maximum memory budget per scope

## Security

- NFR-S1: Secrets (credentials, tokens, webhook URLs) are never emitted in structured logs — masking/redaction patterns enforced for all credential fields
- NFR-S2: Denylist enforcement applied at every outbound boundary before external payloads (PagerDuty, Slack, ServiceNow, Kafka, LLM) via shared denylist enforcement function — no boundary-specific reimplementations
- NFR-S3: Kafka SASL_SSL keytab and krb5 config paths validated at startup with fail-fast behavior — system does not start with missing or invalid security configuration
- NFR-S4: ServiceNow MI-1 guardrails prevent major-incident write scope — system cannot create or modify major incidents
- NFR-S5: Integration safety modes default to LOG — no external calls in local/dev unless explicitly configured to MOCK or LIVE
- NFR-S6: Prod enforcement rejects MOCK/OFF for critical integrations — prevents accidental non-operational configuration in production

## Scalability

- NFR-SC1: Hot-path supports hot/hot 2-pod minimum deployment with zero duplicate dispatches across replicas
- NFR-SC2: Scope sharding supports even distribution across pods with O(1) checkpoint writes per shard per interval instead of O(N) per scope
- NFR-SC3: Outbox publisher supports concurrent instances with row locking preventing duplicate Kafka publication
- NFR-SC4: All coordination mechanisms (cycle lock, sustained state, AG5 dedupe) use Redis as the single shared state layer — no in-process state assumed exclusive

## Reliability

- NFR-R1: DEAD outbox rows: standing posture of 0 — any DEAD row triggers operational alerting
- NFR-R2: Write-once casefile invariant: triage.json exists in S3 before any downstream event is published to Kafka (Invariant A)
- NFR-R3: Outbox guarantees at-least-once Kafka delivery — hot-path continues unaffected during Kafka unavailability, cases accumulate in Postgres (Invariant B2)
- NFR-R4: Distributed cycle lock fails open on Redis unavailability — system degrades to single-instance equivalent behavior, never halts
- NFR-R5: Sustained window state falls back to None on Redis failure — conservative behavior (treats as first observation, no false sustained=true)
- NFR-R6: Critical dependency failures halt processing with loud failure — no silent fallback for invariant violations
- NFR-R7: Degradable dependency failures update HealthRegistry, emit degraded events, and continue with capped behavior
- NFR-R8: Cold-path LLM failure produces a deterministic fallback DiagnosisReportV1 — the absence of diagnosis.json is explicit and observable, never silent

## Auditability

- NFR-A1: All casefiles retained for 25 months with write-once semantics and SHA-256 hash chains
- NFR-A2: Every casefile stamps active policy versions (rulebook, peak policy, denylist, anomaly detection policy) at decision time
- NFR-A3: Schema envelope versioning enables perpetual read support — old casefiles remain deserializable across the 25-month retention window as schemas evolve
- NFR-A4: Structured logs carry correlation_id (case_id) enabling field-level querying of the complete decision trail per case in Elastic
- NFR-A5: Gate evaluation trail with full reason codes persisted in ActionDecisionV1 for every triage decision
- NFR-A6: Pod identity (POD_NAME, POD_NAMESPACE) stamped in OTLP resource attributes and structured logs for per-instance traceability across replicas

## Integration

- NFR-I1: All external integrations implement OFF|LOG|MOCK|LIVE mode semantics consistently — no integration-specific mode behavior
- NFR-I2: External integration failures in degradable mode (Slack, ServiceNow) do not block hot-path cycle execution
- NFR-I3: PagerDuty deduplication uses action_fingerprint as dedup_key — duplicate pages for the same fingerprint within TTL are suppressed by PagerDuty
- NFR-I4: Cold-path Kafka consumer commits offsets on graceful shutdown — no message loss or reprocessing beyond at-least-once semantics
