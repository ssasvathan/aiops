# Executive Summary

This platform delivers bank-grade AIOps triage for a shared Kafka streaming infrastructure. The immediate goal (Phase 0 → Phase 1B) is a triage-first pipeline: collect evidence from Prometheus, build durable CaseFiles, route incidents to the correct owning team with full provenance, and gate all actions through deterministic safety guardrails (Rulebook AG0–AG6). The system never simulates telemetry for MVP — Prometheus is the sole source of truth, and missing data is explicitly UNKNOWN, never treated as zero.

**Phase 0** is NOT MVP — it is a local harness that must prove three real-signal patterns (lag buildup, throughput-constrained proxy, volume drop) using real Prometheus metrics, plus validate Redis TTL behavior, peak profile confidence, ownership mapping, and outbox state-machine transitions locally. Harness stream naming is separate from prod naming.

**Phase 1A** delivers the MVP triage pipeline: Evidence Builder → Peak Profile → Topology+Ownership Enrichment → CaseFile to object storage → Postgres durable outbox publishes `CaseHeaderEvent.v1` + `TriageExcerpt.v1` to Kafka → deterministic Rulebook gating → Action Executor (env caps + dedupe) → SOFT postmortem enforcement via Slack/log. The Kafka hot path forwards only the minimal header and excerpt — no object-store reads in the routing/paging path. CaseFile is the system-of-record but is not fetched by hot-path consumers.

**Phase 1B** adds HARD ServiceNow postmortem automation: link to PD-created Incident, create/update Problem + PIR tasks via idempotent linkage contract with tiered correlation and 2-hour retry window.

**Phase 2** expands evidence coverage (client-level telemetry, runbook assistant, advisory ML boosters) and adds a labeling feedback loop, while keeping Rulebook guardrails authoritative. ML may propose top-N hypotheses and adjust diagnosis confidence weights using learned patterns, but never directly triggers actions in PROD/TIER_0.

**Phase 3** adds coverage-weighted hybrid topology (YAML as governed logical truth + Dynatrace Smartscape as best-effort observed graph + platform edge facts that emit even without app instrumentation) and a Sink Health Evidence Track with standardized primitives (`SINK_CONNECTIVITY`, `SINK_ERROR_RATE`, etc.).

**Exposure controls** are enforced throughout: TriageExcerpt and Slack outputs must be executive-safe, applying a denylist that excludes sensitive sink identifiers/endpoints, restricted access paths, credentials, and internal hostnames. CaseFile may contain richer operational detail, but excerpts are always capped.

**Postmortem policy** is selective (predicate `PM_PEAK_SUSTAINED` := peak && sustained && TIER_0 in PROD, per AG6). Phase 1A enforces via Slack/log (SOFT); Phase 1B via SN Problem + PIR tasks (HARD). MI posture: the system does NOT create Major Incident objects (MI-1 policy).

**Outbox operability** is a first-class requirement: delivery SLO (p95 ≤ 1 min, p99 ≤ 5 min), alerting on PENDING_OBJECT/READY/RETRY age thresholds, and a prod posture of DEAD=0 (any DEAD row in prod is critical).

Target users are Kafka platform operations engineers, data stewards, and incident responders at a bank. The system must be explainable to auditors, safe enough that a wrong-page-at-2-AM scenario is structurally prevented, and evolvable without breaking frozen contracts.

## What Makes This Special

- **Truthful telemetry as a structural guarantee.** Missing Prometheus series maps to `EvidenceStatus=UNKNOWN` — never faked as zero. Every evidence primitive carries provenance and confidence. Enforced by contract (prometheus-metrics-contract-v1, peak-policy-v1), not convention.
- **Deterministic safety guardrails decoupled from diagnosis.** The Rulebook (AG0–AG6) is a frozen contract that caps actions by environment, tier, evidence sufficiency, confidence, sustained state, and dedupe — independent of how diagnosis evolves. PAGE is structurally impossible outside PROD+TIER_0.
- **Minimal hot-path contract.** Kafka forwards only `CaseHeaderEvent.v1` + `TriageExcerpt.v1`. No object-store reads in the routing/paging path. CaseFile is system-of-record, written before publish (Invariant A), but hot-path consumers never fetch it.
- **Durable, reproducible CaseFiles.** Every triage case is written to object storage before any Kafka publish (Invariant A). A Postgres durable outbox (Invariant B2) guarantees publish-after-crash. Outbox SLOs and DEAD=0 prod posture are operability requirements, not aspirations. Cases are reproducible and auditable for 25 months in prod.
- **Executive-safe exposure controls.** TriageExcerpt and Slack outputs enforce a denylist — no sensitive sink endpoints, credentials, restricted hostnames. CaseFile stores richer detail; excerpts are always capped.
- **Ownership-aware routing from day one.** The topology registry encodes ownership at consumer-group, topic, stream, and platform-default levels. Routing is deterministic, not ad-hoc.
- **Safe degraded modes.** Redis unavailable → deny PAGE/TICKET, allow NOTIFY only. Dedupe store error → same. The system never generates paging storms when infrastructure degrades.
- **Selective postmortem enforcement (`PM_PEAK_SUSTAINED`).** Triggered by AG6 predicate (peak && sustained && TIER_0 in PROD). SOFT (Slack/log) in Phase 1A, HARD (SN Problem + PIR) in Phase 1B. No automated MI creation (MI-1).
- **Zero-external-integration local development.** The full pipeline runs locally via docker-compose (Kafka + Postgres + Redis + MinIO + Prometheus). All external integrations are pluggable via `OFF | LOG | MOCK | LIVE` modes with LOG/OFF as local defaults.
- **Instance-scoped multi-cluster topology.** Streams declare `instances[]` keyed by `(env, cluster_id)`, with `topic_index` scoped per instance. Prevents cross-cluster collisions and supports DR/multi-cluster natively. Backward-compatible loader migrates legacy v0 registries.
- **Coverage-weighted hybrid topology (Phase 3).** YAML is governed logical truth; Smartscape provides best-effort observed graph; platform edge facts emit even without app-level instrumentation. Instance-scoped, exposure-safe.
