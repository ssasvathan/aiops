# Glossary & Terminology

Domain-specific terms, acronyms, and identifiers used in this PRD. Definitions reflect how each term is used within this system's architecture and contracts.

## Rulebook & Safety Gates

| Term | Definition |
|------|-----------|
| Rulebook | Frozen contract (`rulebook-v1.yaml`) containing deterministic safety gates AG0–AG6 that cap actions by environment, tier, evidence sufficiency, confidence, sustained state, and dedupe. Independent of diagnosis evolution; ML never overrides it in PROD/TIER_0. |
| AG0 | Gate 0: Schema validation. Ensures GateInput.v1 is structurally valid before downstream gates evaluate it. |
| AG1 | Gate 1: Environment + criticality tier caps. Caps maximum action by `(environment, criticality_tier)` — e.g., local=OBSERVE, dev=NOTIFY, uat=TICKET, prod TIER_0=PAGE eligible. Structurally prevents PAGE outside PROD+TIER_0. |
| AG2 | Gate 2: Evidence sufficiency. Evaluates each Finding's declared `evidence_required[]` against evidence_status_map. Insufficient evidence downgrades the action. |
| AG3 | Gate 3: SOURCE_TOPIC PAGE denial. Denies PAGE for anomalies on topics with `topic_role=SOURCE_TOPIC`; caps to TICKET or lower. |
| AG4 | Gate 4: Confidence + sustained threshold. Requires `sustained=true` and `confidence >= 0.6` for PAGE/TICKET. Cases below threshold are downgraded. |
| AG5 | Gate 5: Dedupe + degraded-mode storm control. Deduplicates actions by `action_fingerprint` with per-type TTLs (PAGE 120m, TICKET 240m, NOTIFY 60m). Redis unavailable → `DEGRADE_AND_ALLOW_NOTIFY` (deny PAGE/TICKET, allow NOTIFY only). |
| AG6 | Gate 6: Postmortem predicate evaluation. Evaluates `PM_PEAK_SUSTAINED` (peak && sustained && TIER_0 in PROD). On pass: sets `postmortem_required=true` with SOFT or HARD enforcement. |
| GateInput.v1 | Frozen event contract: deterministic envelope consumed by Rulebook evaluation. Contains all fields needed for AG0–AG6 decisions. |
| ActionDecision.v1 | Frozen event contract produced by Rulebook evaluation. Contains: `final_action`, `env_cap_applied`, `gate_rule_ids`, `gate_reason_codes`, `action_fingerprint`, `postmortem_required`, `postmortem_mode`. |

## Evidence & Telemetry

| Term | Definition |
|------|-----------|
| EvidenceStatus | Enum: `PRESENT`, `UNKNOWN`, `ABSENT`, `STALE`. Carried by every evidence primitive. Missing Prometheus series maps to UNKNOWN — never treated as zero. |
| evidence_status_map | Per-case mapping of evidence primitives to their EvidenceStatus values. Consumed by AG2 for sufficiency evaluation. |
| UNKNOWN-not-zero | Architectural invariant: missing Prometheus series produces `EvidenceStatus=UNKNOWN`, propagated through peak, sustained, confidence, and gating. Never silently treated as zero. |
| sustained | Boolean: anomaly has persisted for 5 consecutive anomalous 5-minute buckets (25 minutes). Required by AG4 for PAGE/TICKET and by AG6 for `PM_PEAK_SUSTAINED`. |
| peak / near-peak | Classification of current ingestion rate against historical baselines (p90/p95) per `(env, cluster_id, topic)`. Computed by Peak Profile stage; cached in Redis. Input to `PM_PEAK_SUSTAINED`. |
| anomaly family | Category of detected anomaly pattern. Phase 0/1A: consumer lag buildup, throughput-constrained proxy, volume drop. Each family defines its own `evidence_required[]` list. |
| evidence primitive | Atomic unit of collected evidence (e.g., a specific Prometheus metric value). Carries provenance, confidence, and EvidenceStatus. New evidence sources (Phase 2/3) plug into this abstraction. |
| Finding | Structured detection result from Evidence Builder. Declares its own `evidence_required[]` list evaluated by AG2. |
| evaluation interval | 5-minute time window aligned to wall-clock boundaries (00, 05, 10, ...). Sustained detection spans 5 consecutive intervals. |
| confidence | Numeric score (0.0–1.0) reflecting certainty. UNKNOWN evidence downgrades confidence. AG4 requires `>= 0.6` for PAGE/TICKET. |
| TelemetryDegradedEvent | Event emitted when Prometheus is totally unavailable. Pipeline caps actions to OBSERVE/NOTIFY and suppresses all-UNKNOWN cases until recovery. |
| DegradedModeEvent | Event emitted when Redis is unavailable. Contains affected scope, reason, capped action level. Provides transparency about why PAGE/TICKET is suppressed. |

## Event Contracts & Data

| Term | Definition |
|------|-----------|
| CaseHeaderEvent.v1 | Frozen: minimal Kafka header for routing/paging on the hot path. Published after CaseFile triage write (Invariant A). No object-store reads required by consumers. |
| TriageExcerpt.v1 | Frozen: executive-safe case summary published alongside CaseHeaderEvent.v1. Enforces exposure denylist — no sensitive endpoints, credentials, or restricted hostnames. |
| DiagnosisReport.v1 | Schema-locked cold-path output from LLM. Contains: `verdict`, `fault_domain`, `confidence`, `evidence_pack`, `next_checks`, `gaps`. Schema locked; content evolves. |
| CaseFile | System-of-record for every triage case. Directory of independently immutable stage files: `triage.json` (hot path), `diagnosis.json` (LLM), `linkage.json` (SN), `labels.json` (human). Object storage with SHA-256 hash chain across stages. 25-month prod retention. See `docs/schema-evolution-strategy.md`. |
| action_fingerprint | Stable dedupe key (anomaly key + action type). Used by AG5 to suppress repeat actions within TTL windows. |
| PM_PEAK_SUSTAINED | Postmortem predicate: `peak && sustained && TIER_0 in PROD`. SOFT (Slack/log) Phase 1A; HARD (SN Problem + PIR) Phase 1B. |
| NotificationEvent | Structured log fallback when Slack is not configured. Contains case_id, final_action, routing_key, reason_codes. |
| pd_incident_id | Stable PagerDuty identifier in PAGE payloads. Used for SN Tier 1 correlation. |
| external_id | Idempotency key for SN upserts. Format: `aiops_case_id` (Problem), `aiops_case_id:task_type` (PIR tasks). |
| policy version stamps | Set of version IDs in every CaseFile: `rulebook_version`, `peak_policy_version`, `prometheus_metrics_contract_version`, `exposure_denylist_version`, `diagnosis_policy_version`. Enables decision replay. |

## Topology & Routing

| Term | Definition |
|------|-----------|
| stream_id | Canonical identifier for a logical data stream. Groups related topics, consumer groups, and downstream components into a named, ownable unit. |
| topic_role | Topic classification: `SOURCE_TOPIC` (ingestion from external source) or other roles. AG3 uses topic_role to deny PAGE for SOURCE_TOPIC anomalies. |
| criticality_tier | `TIER_0` (PAGE eligible in prod), `TIER_1` (TICKET max), `TIER_2`/`UNKNOWN` (NOTIFY max). Enforced by AG1. |
| blast_radius | Downstream impact scope: `LOCAL_SOURCE_INGESTION` (scoped to source) or `SHARED_KAFKA_INGESTION` (shared pipeline). Derived from topic_role. |
| routing_key | Maps a case to the correct owning team's notification channel via multi-level ownership lookup. |
| topology registry | YAML-based configuration defining streams, instances, topics, consumer groups, ownership, tiers, and downstream components. Two schema versions: v0 (legacy), v1 (instance-scoped). |
| instance-scoped | Architecture pattern: streams declare `instances[]` keyed by `(env, cluster_id)` with `topic_index` per instance. Prevents cross-cluster collisions. |
| topic_index | Per-instance mapping of topic names to stream context. Scoped by `(env, cluster_id)`. |
| edge fact | Platform-level topology observation (producer→topic, consumer→topic). Phase 3 supplementary source below YAML and Smartscape in governance hierarchy. |
| multi-level ownership lookup | Resolution chain: `consumer_group_owner → topic_owner → stream_default_owner → platform_default`. First match wins. |
| hybrid topology | Phase 3: YAML (governed) + Smartscape (observed) + edge facts. Governance hierarchy ensures YAML is never overridden by observed data. |
| compat views | Backward-compatible views for v0 consumers during migration. Deprecated Phase 1B/2; removed Phase 2+. |

## Pipeline Infrastructure

| Term | Definition |
|------|-----------|
| Invariant A | Write-before-publish: CaseFile `triage.json` written to object storage BEFORE CaseHeaderEvent.v1 appears on Kafka. Non-negotiable durability guarantee. |
| Invariant B2 | Publish-after-crash: Postgres outbox ensures that if CaseFile `triage.json` is written but process crashes before Kafka publish, the outbox completes the publish on recovery. |
| hot path | Stages 1–7: latency-critical synchronous pipeline. No LLM calls; no object-store reads by downstream consumers. |
| cold path | Stages 8–12: asynchronous enrichment (LLM diagnosis, SN linkage, labeling). Non-blocking — hot path does not wait. |
| outbox | Postgres-backed durable publish queue. State machine: `PENDING_OBJECT → READY → SENT` (+ `RETRY`, `DEAD`). Guarantees Invariant B2. |
| DEAD=0 | Standing prod posture: any DEAD outbox row is a critical alert. DEAD records require human investigation — never automatically retried. 90-day retention. |
| SHA-256 hash chain | CaseFile integrity mechanism. Each version includes a SHA-256 hash for tamper-evidence during regulatory examination. |
| write-once / append-only | CaseFile immutability: v1 is write-once; subsequent versions append without mutating prior content. |

## Integration & Actions

| Term | Definition |
|------|-----------|
| PAGE | Highest-urgency action: PagerDuty alert. Structurally impossible outside PROD+TIER_0 (AG1). Dedupe TTL: 120m. |
| TICKET | Mid-urgency: investigation ticket. Max for TIER_1 in prod. Dedupe TTL: 240m. |
| NOTIFY | Low-urgency: Slack or structured log. Max for TIER_2/UNKNOWN in prod and degraded mode. Dedupe TTL: 60m. |
| OBSERVE | Lowest: internal logging only. Max for local environment. Also the cap during total Prometheus unavailability. |
| exposure denylist | Versioned security artifact excluding sensitive identifiers from all human-visible outputs. Enforced at every output boundary: TriageExcerpt, Slack, SN, LLM narratives. |
| SN linkage | Phase 1B: correlating PAGE cases to PD-created SN Incidents, then creating idempotent Problem + PIR tasks. Tiered correlation with 2-hour retry. |
| tiered correlation | Tier 1 (PD field lookup) → Tier 2 (keyword search) → Tier 3 (time-window + routing heuristic). Fallback rates tracked; Tier 2/3 usage should trend down. |
| MI-1 | Major Incident posture: system does NOT create MI objects. MI creation is a human decision boundary. |
| FAILED_FINAL | Terminal SN linkage state after 2-hour retry exhaustion. Triggers Slack escalation (exposure-safe). |
| integration mode | Per-integration: `OFF`, `LOG` (safe default), `MOCK` (simulated), `LIVE` (real calls). LIVE requires explicit endpoint+credential configuration. |
| SOFT / HARD postmortem | SOFT (Phase 1A): Slack/log obligation. HARD (Phase 1B): SN Problem + PIR tasks auto-created via idempotent linkage. |

## Environment & Classification

| Term | Definition |
|------|-----------|
| Business_Essential | Highest Kafka cluster classification. TIER_0 streams on these clusters are PAGE-eligible in prod. |
| Business_Critical | High-criticality cluster classification. Second tier. |
| environment enum | Frozen: `local`, `dev`, `uat`, `prod`. Each has distinct action caps (AG1), TTLs, retention policies, and integration mode defaults. |
| Mode A | Default local dev: docker-compose (Kafka + Postgres + Redis + MinIO + Prometheus). Zero external calls. All integrations LOG mode. |
| Mode B | Opt-in local dev: connects to a dedicated remote environment's infrastructure (e.g., DEV). LIVE mode only for approved non-prod endpoints. |

## Sink Health Evidence (Phase 3)

| Term | Definition |
|------|-----------|
| Sink Health Evidence Track | Phase 3 evidence expansion: standardized primitives for downstream sink health. Enables Kafka vs sink symptom attribution. |
| SINK_CONNECTIVITY | Sink reachability. ABSENT suggests sink unreachability as root cause. |
| SINK_ERROR_RATE | Error rate at downstream sink. |
| SINK_LATENCY | Response time at downstream sink. |
| SINK_BACKLOG | Queued/pending work at downstream sink. |
| SINK_THROTTLE | Active throttling by downstream sink. |
| SINK_AUTH_FAILURE | Authentication/authorization failures at downstream sink. |

## Frozen Contracts & Policy Artifacts

| Term | Definition |
|------|-----------|
| frozen contract | Versioned specification that cannot change without formal version bump and review. 12 frozen contracts constrain this system. |
| prometheus-metrics-contract-v1 | Locks canonical metric names and label normalization rules. Missing series → UNKNOWN. |
| redis-ttl-policy-v1 | Per-environment TTLs for evidence cache, peak profiles, and dedupe keys. Redis is cache-only. |
| outbox-policy-v1 | Outbox state machine, SLO thresholds, alerting thresholds, and retention policies. |
| peak-policy-v1 | Peak/near-peak classification rules, baseline computation, recomputation cadence. |
| servicenow-linkage-contract-v1 | SN integration scope: tiered correlation, idempotent upsert, retry schedule, FAILED_FINAL behavior, least-privilege permissions. |
| local-dev-no-external-integrations-contract-v1 | Local dev (Mode A) requires zero external calls. Defines integration mode defaults and LIVE restrictions. |
| diagnosis-policy.yaml | Draft (not frozen) diagnosis rules. Can evolve independently of Rulebook. Changes must be versioned and traceable. |
| topology-registry-loader-rules-v1 | How topology YAML is loaded, validated, and canonicalized. Covers v0→v1 migration, fail-fast validation, compat view generation. |
