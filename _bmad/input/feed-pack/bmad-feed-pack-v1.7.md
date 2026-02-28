# BMAD Feed Pack — AIOps Architecture — v1.1
Date: 2026-02-22

Purpose: Single place to reference **frozen** decisions + finalized artifacts so BMAD (Analyst/Architect/etc.) can consume them later without re-deriving.

## Golden rule
If a decision is marked **LOCKED/FROZEN**, it must be represented in at least one of:
1) A versioned artifact (YAML/MD) OR
2) The Locked Decisions section of the Handoff Package

…and this index must be updated.

## Frozen artifacts (authoritative inputs)
- /mnt/data/topology-registry.yaml (legacy; still source-of-truth for existing consumers)
- /mnt/data/diagnosis-policy.yaml (NOT frozen; reference only)
- /mnt/data/claude_aiops_mvp_architecture_v6.md (optional cues; may be outdated)

## Frozen artifacts (new canonical shapes)
- /mnt/data/topology-registry.instances-v2.ownership-v1.clusters.yaml
  - instances-based registry shape
  - includes ownership routing scaffolding
  - Phase 1A clusters: Business_Essential, Business_Critical
- /mnt/data/rulebook-v1.yaml
  - Action Guardrails AG0–AG6
  - PAGE only PROD+TIER_0; deny PAGE on SOURCE_TOPIC
  - AG2 reads findings[].evidence_required[]
  - missing-series ⇒ UNKNOWN
- /mnt/data/gateinput-v1.contract.yaml
  - deterministic envelope for feeding rulebook
- /mnt/data/redis-ttl-policy-v1.md
  - Redis TTL defaults for evidence cache + dedupe (and degraded-mode behavior)
- /mnt/data/outbox-policy-v1.md
  - Outbox v1 retention + SLO + alert thresholds
- /mnt/data/peak-policy-v1.md
  - PeakPolicy v1 (5-minute semantics, peak/near-peak, UNKNOWN handling)
- /mnt/data/prometheus-metrics-contract-v1.yaml
  - canonical metric names + roles + tolerated aliases

## Frozen decisions (must be treated as fixed)
- TRIAGE-first MVP; Prometheus is truth; no simulated telemetry
- Phase 1A includes clusters: Business_Essential, Business_Critical
- cluster_id := cluster_name (exact string; no transforms)
- Outbox v1 invariants, retention, SLO, alerts (see outbox-policy-v1.md)
- Redis TTL defaults for evidence + dedupe (see redis-ttl-policy-v1.md)
- PeakPolicy v1 + metric contract v1 (see peak-policy-v1.md, prometheus-metrics-contract-v1.yaml)
- CaseFile to object storage before Kafka header; Kafka forwards minimal header/excerpt only

## Pending (do not freeze into BMAD yet)
- diagnosis-policy.yaml content (draft; not frozen)
- Phase 1B ServiceNow linkage contract
- Registry migration plan details for legacy consumers (loader/back-compat specifics)
- Edge Fact schema (platform instrumentation; later)
- Sink Health Evidence Track specifics beyond primitive list (later)

## When BMAD artifacts are generated
Only after phase scopes are finalized. BMAD generation must ingest:
- This index
- The current Handoff Package
- All files under “Frozen artifacts” above

## Newly Frozen Since v1.1
- **Topology registry loader / backward-compat rules (v1)**: `/mnt/data/topology-registry-loader-rules-v1.md`
  - Locks v0→v1 canonicalization, instance scoping, topic_index collision prevention, compat view rules, and deprecation plan.

## Newly Frozen Since v1.3
- **ServiceNow linkage contract (v1) — FROZEN**: `/mnt/data/servicenow-linkage-contract-v1.md`
  - Tiered correlation (PD field → keyword → heuristic), 2-hour retry window, idempotent Problem+PIR task upsert rules, least privilege + exposure caps.

## Newly Frozen Since v1.6
- **Local-dev no-external-integrations contract (v1)**: `/mnt/data/local-dev-no-external-integrations-contract-v1.md`
  - Standard integration modes (LOG/MOCK/LIVE/OFF), local fallback behaviors (Slack/SN → logs), and required local infra options (MinIO/Postgres/Kafka/Redis/Prometheus).

## Newly Frozen Since v1.6
- **Phase 2 DoD (v1) — FROZEN**: `/mnt/data/phase-2-dod-v1.md`
  - Evidence expansion + runbook assistant + advisory boosters + labeling loop; still human-led; guardrails remain authoritative.
- **Phase 3 DoD (v1) — FROZEN**: `/mnt/data/phase-3-dod-v1.md`
  - Hybrid topology (YAML + Smartscape + edge facts) + Sink Health Evidence Track; instance-scoped; exposure-safe.
