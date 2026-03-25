# Functional Requirements

**Environment enum (frozen):** `local | dev | uat | prod`

## Evidence Collection & Processing

- **FR1:** The system can collect Prometheus metrics at 5-minute evaluation intervals using canonical metric names from prometheus-metrics-contract-v1
- **FR2:** The system can detect three anomaly patterns: consumer lag buildup, throughput-constrained proxy, and volume drop
- **FR3:** The system can compute peak/near-peak classification per (env, cluster_id, topic) against historical baselines (p90/p95 of messages-in rate)
- **FR4:** The system can compute sustained status (5 consecutive anomalous buckets) for each anomaly
- **FR5:** The system can map missing Prometheus series to `EvidenceStatus=UNKNOWN` (never treated as zero) and propagate UNKNOWN through peak, sustained, and confidence computations
- **FR6:** The system can produce an evidence_status_map for each case mapping evidence primitives to PRESENT/UNKNOWN/ABSENT/STALE
- **FR7:** The system can cache evidence windows, peak profiles, and per-interval findings in Redis with environment-specific TTLs per redis-ttl-policy-v1
- **FR8:** Each Finding can declare its own `evidence_required[]` list (no central required-evidence registry)

## Topology & Ownership

- **FR9:** The system can load topology registry in both v0 (legacy) and v1 (instances-based) formats and canonicalize to a single in-memory model
- **FR10:** The system can resolve `stream_id`, `topic_role`, `criticality_tier`, and `source_system` from topology registry given an anomaly key (env, cluster_id, topic/group)
- **FR11:** The system can compute blast radius classification (LOCAL_SOURCE_INGESTION vs SHARED_KAFKA_INGESTION) based on topic_role
- **FR12:** The system can identify downstream components as AT_RISK with exposure_type (DOWNSTREAM_DATA_FRESHNESS_RISK, DIRECT_COMPONENT_RISK, VISIBILITY_ONLY)
- **FR13:** The system can route cases to the correct owning team using multi-level ownership lookup: consumer_group_owner → topic_owner → stream_default_owner → platform_default
- **FR14:** The system can scope topic_index by (env, cluster_id) to prevent cross-cluster collisions
- **FR15:** The system can validate registry on load: fail-fast on duplicate topic_index keys, duplicate consumer-group ownership keys, or missing routing_key references
- **FR16:** The system can provide backward-compatible compat views for legacy consumers during v0→v1 migration — backward-compatible means existing consumers reading v0 schema fields receive identical values and types with no breaking changes to field names, types, or semantics

## CaseFile Management

- **FR17:** The system can assemble a CaseFile triage stage (`triage.json`) containing: evidence snapshot, gating inputs (GateInput.v1 fields), ActionDecision.v1, policy version stamps (rulebook, peak, prometheus metrics, exposure denylist, diagnosis policy versions), and SHA-256 content hash
- **FR18:** The system can write CaseFile `triage.json` to object storage as a write-once artifact before any Kafka header publish (Invariant A)
- **FR19:** The system can write additional CaseFile stage files (diagnosis, linkage, labels) to the same case directory without mutating prior stage files, preserving hash integrity chain across stages
- **FR20:** The system can enforce data minimization: no PII, credentials, or secrets in CaseFiles; sensitive fields redacted per exposure denylist
- **FR21:** The system can enforce CaseFile retention (25 months prod) via automated lifecycle policies with auditable purge operations

## Event Publishing & Durability

- **FR22:** The system can publish `CaseHeaderEvent.v1` + `TriageExcerpt.v1` to Kafka via Postgres durable outbox after CaseFile `triage.json` write is confirmed
- **FR23:** The outbox can manage state transitions: PENDING_OBJECT → READY → SENT (+ RETRY, DEAD) with publish-after-crash guarantee (Invariant B2)
- **FR24:** The system can enforce that hot-path consumers receive only header/excerpt — no object-store reads required for routing/paging decisions
- **FR25:** The system can enforce exposure denylist on TriageExcerpt: no sensitive sink endpoints, credentials, restricted hostnames, or Ranger access groups
- **FR26:** The system can retain outbox records per outbox-policy-v1: SENT (14d prod), DEAD (90d prod), PENDING/READY/RETRY until resolved

## Action Gating & Safety

- **FR27:** The system can evaluate GateInput.v1 through Rulebook gates AG0–AG6 sequentially and produce an ActionDecision.v1 with: final_action, env_cap_applied, gate_rule_ids, gate_reason_codes, action_fingerprint, postmortem_required, postmortem_mode, postmortem_reason_codes
- **FR28:** The system can cap actions by environment per AG1: local=OBSERVE, dev=NOTIFY, uat=TICKET, prod=PAGE eligible (only when TIER_0 and all other gates pass; otherwise capped per tier/gates)
- **FR29:** The system can cap actions by criticality tier in prod per AG1: TIER_0=PAGE eligible (if all other gates pass), TIER_1=TICKET, TIER_2/UNKNOWN=NOTIFY
- **FR30:** The system can deny PAGE for SOURCE_TOPIC anomalies per AG3; final_action caps to TICKET or lower depending on env/tier/remaining gates (not always TICKET)
- **FR31:** The system can evaluate finding-declared `evidence_required[]` per AG2; evidence with status UNKNOWN/ABSENT/STALE is treated as insufficient unless a finding explicitly allows it; insufficient evidence downgrades action (never assumes PRESENT)
- **FR32:** The system can require sustained=true and confidence≥0.6 for PAGE/TICKET actions per AG4
- **FR33:** The system can deduplicate actions by action_fingerprint with TTLs per action type (PAGE 120m, TICKET 240m, NOTIFY 60m) per AG5
- **FR34:** The system can detect dedupe store (Redis) unavailability and cap to NOTIFY-only per AG5 degraded mode
- **FR35:** The system can evaluate `PM_PEAK_SUSTAINED` predicate (peak && sustained && TIER_0 in PROD) for selective postmortem obligation per AG6

## Diagnosis & Intelligence

- **FR36:** The system can invoke LLM diagnosis on the cold path (non-blocking) consuming TriageExcerpt + structured evidence summary to produce DiagnosisReport.v1
- **FR37:** The LLM can produce structured DiagnosisReport output: verdict, fault_domain, confidence, evidence_pack (facts, missing_evidence, matched_rules), next_checks, gaps
- **FR38:** The LLM can cite evidence IDs/references and explicitly propagate UNKNOWN for missing evidence — the system rejects any output that invents metric values or fabricates findings
- **FR39:** The system can fall back to a schema-valid DiagnosisReport when LLM is unavailable/timeout/error: verdict=UNKNOWN, confidence=LOW, reason_codes=[LLM_TIMEOUT | LLM_UNAVAILABLE | LLM_ERROR]
- **FR40:** The system can validate LLM output against DiagnosisReport schema; invalid/unparseable output triggers deterministic fallback with a gap recorded
- **FR41:** The system can run in LLM stub/failure-injection mode for local and test use, producing deterministic schema-valid DiagnosisReport fallback without external LLM API calls; LLM must run LIVE in prod — stub mode is not permitted in prod
- **FR42:** The system can conditionally invoke LLM based on case criteria (environment=PROD, tier=TIER_0, state=sustained) with bounded token input (TriageExcerpt only, not raw logs; max input token budget defined per deployment configuration)
- **FR66:** The system can execute CaseFile triage write, outbox header/excerpt publish, Rulebook gating, and action execution without waiting on LLM diagnosis completion (LLM diagnosis is cold-path and non-blocking)

## Notification & Action Execution

- **FR43:** The system can send PAGE triggers to PagerDuty with stable `pd_incident_id` for downstream SN correlation
- **FR44:** The system can send SOFT postmortem enforcement notifications to Slack/log when `PM_PEAK_SUSTAINED` fires (Phase 1A)
- **FR45:** The system can emit structured `NotificationEvent` to logs (JSON) when Slack is not configured, containing case_id, final_action, routing_key, support_channel, postmortem_required, reason_codes
- **FR46:** The system can search for PD-created SN Incidents using tiered correlation: Tier 1 (PD field) → Tier 2 (keyword) → Tier 3 (time-window + routing heuristic) (Phase 1B)
- **FR47:** The system can create/update SN Problem + PIR tasks idempotently via external_id keying (Phase 1B)
- **FR48:** The system can retry SN linkage with exponential backoff + jitter over 2-hour window, transitioning to FAILED_FINAL with Slack escalation if unresolved (Phase 1B)
- **FR49:** The system can track SN linkage state: PENDING → SEARCHING → LINKED or SEARCHING → FAILED_TEMP → SEARCHING or SEARCHING → FAILED_FINAL (Phase 1B)
- **FR50:** The system can track Tier 1 vs Tier 2/3 SN correlation fallback rates as Prometheus metrics (gauge per tier), exposed on the /metrics endpoint with alerting threshold configurable per deployment (Phase 1B)

## Operability & Monitoring

- **FR51:** The system can emit `DegradedModeEvent` to logs and Slack (if configured) when Redis is unavailable, containing: affected scope, reason, capped action level, estimated impact window
- **FR67:** The system can emit `TelemetryDegradedEvent` when Prometheus is unavailable (total source failure, not individual missing series), containing: affected scope, reason, recovery status; pipeline caps actions to OBSERVE/NOTIFY and does NOT emit normal cases with all-UNKNOWN evidence until Prometheus recovers
- **FR52:** The system can monitor and alert on outbox health: PENDING_OBJECT age (>5m warn, >15m crit), READY age (>2m warn, >10m crit), RETRY age (>30m crit), DEAD count (>0 crit in prod)
- **FR53:** The system can measure outbox delivery SLO: p95 ≤ 1 min, p99 ≤ 5 min (CaseFile write → Kafka publish)
- **FR54:** The system can enforce DEAD=0 prod posture as a standing operational requirement

## Local Development & Testing

- **FR55:** The system can run end-to-end locally via docker-compose (Mode A) with Kafka, Postgres, Redis, MinIO, Prometheus — zero external integration calls
- **FR56:** The system can optionally connect to a dedicated remote environment's infrastructure (Mode B) when endpoints and credentials are explicitly configured, restricted to approved non-prod endpoints — no accidental prod calls
- **FR57:** Every outbound integration can be configured in OFF/LOG/MOCK/LIVE modes with LOG as default; LIVE requires explicit endpoint+credential configuration
- **FR58:** The system can generate harness traffic (Phase 0) producing real Prometheus signals for lag, constrained proxy, and volume drop patterns with harness-specific stream naming
- **FR59:** The system can validate all durability invariants (Invariant A, Invariant B2) locally using MinIO + Postgres

## Governance & Audit

- **FR60:** Every CaseFile can record the exact policy versions used to make its decisions (rulebook_version, peak_policy_version, prometheus_metrics_contract_version, exposure_denylist_version, diagnosis_policy_version)
- **FR61:** Auditors can reproduce any historical gating decision given the same evidence + same policy versions and verify identical outcomes
- **FR62:** The exposure denylist can be maintained as a versioned, reviewable artifact with controlled change management — changes require pull request review by at least one designated approver, with an audit log entry recording author, reviewer, timestamp, and diff summary
- **FR63:** Operators can label cases with: owner_confirmed, resolution_category, false_positive, missing_evidence_reason (Phase 2 capture workflow; CaseFile schema supports from Phase 1A)
- **FR64:** The system can validate label data quality: completion rate ≥ 70% for eligible cases, consistency checks for key labels before ML consumption (Phase 2)
- **FR65:** The system can enforce that LLM-generated narrative in any surfaced output (excerpt, Slack, SN) complies with the exposure denylist
- **FR67:** The system can guarantee that no automated process creates Major Incident (MI) objects in ServiceNow — MI creation is a human decision boundary; the system supports postmortem automation (Problem + PIR tasks) but never escalates into the bank's MI process autonomously (MI-1 posture)
