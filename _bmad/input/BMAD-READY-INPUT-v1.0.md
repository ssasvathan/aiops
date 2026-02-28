# BMAD-Ready Input Set — AIOps Architecture (Kafka Streaming Platform, Bank) — v1.0
**Date:** 2026-02-22  
**Status:** Phases/scopes finalized (Phase 0 → Phase 3 DoD frozen).  
**Use:** Feed this + the attached “BMAD Feed Pack Bundle” into BMAD to generate PRD/Architecture/Epics/Stories as needed.

---

## 1) Project summary
Build a bank-grade AIOps capability for a Kafka streaming platform:
- **MVP is TRIAGE-first**, later RCA and safe automation.
- **Truthful telemetry:** no simulated telemetry for MVP; **Prometheus is truth**.
- **Explainable & auditable:** deterministic guardrails + provenance + confidence + durable CaseFile.
- **Operationally usable:** ownership routing, reproducible cases, stable contracts, safe degraded modes.
- **Evolvable:** stable primitives; rulebook is pluggable; hybrid topology and sink health later.

---

## 2) North Star (non-negotiable)
1) TRIAGE-first MVP; later RCA + safe automation tiers  
2) Prometheus truth (no simulation for MVP)  
3) Explainable + auditable (provenance, confidence, deterministic safety gates)  
4) Operationally usable (routing, stable contracts, reproducible incident capture)  
5) Evolvable (rulebook pluggable; topology can become hybrid later)

---

## 3) Phase plan (final)
### Phase 0 — Local harness (NOT MVP)
Goal: generate real Kafka traffic + real Prometheus signals to prove:
- Lag buildup (`kafka_consumergroup_group_lag`)
- Throughput constrained proxy (lag + near-peak ingress + not volume drop)
- Volume drop (topic messages-in drop)
Plus: peak profile confidence, Redis cache behavior, ownership mapping validation.

### Phase 1A — MVP triage pipeline
Evidence builder → peak profile → topology+ownership enrichment → **CaseFile to object storage** → **Postgres outbox** publishes header/excerpt → deterministic rulebook gating → Action Executor (env caps + dedupe) → SOFT postmortem enforcement via Slack/log (Phase 1A).

### Phase 1B — SN postmortem automation (HARD)
Link to PD-created Incident; create/update **Problem + PIR tasks** via idempotent linkage contract.

### Phase 2 — DoD (Frozen)
See Phase 2 DoD artifact. Theme: better evidence + better triage quality (human-led; advisory boosters; labeling loop).

### Phase 3 — DoD (Frozen)
See Phase 3 DoD artifact. Theme: hybrid topology (YAML + Dynatrace + edge facts) + sink health evidence track.

---

## 4) Locked design decisions (high impact)
### 4.1 Telemetry & semantics
- Prometheus label normalization: `cluster_id := cluster_name` (exact string).
- Time semantics: 5-minute buckets; **sustained = 5 consecutive buckets**.
- Missing series ⇒ EvidenceStatus `UNKNOWN` (never treated as 0).

### 4.2 Storage & reliability invariants
- Redis = cache (evidence windows, findings, dedupe storm control).
- CaseFile stored in object storage (system-of-record). Prod retention: 25 months.
- Kafka forwards minimal: `CaseHeaderEvent.v1 + TriageExcerpt.v1` (no hot-path object-store reads).
- Reliability invariants:
  - A) write CaseFile to object storage **before** publishing Kafka header
  - B2) Postgres Durable Outbox ensures publish after crash
  - Outbox state: `PENDING_OBJECT → READY → SENT` (+ RETRY, DEAD)

### 4.3 Action gating (Rulebook)
- Rulebook is **guardrails only** (AG0–AG6), not a case library.
- PAGE only for **PROD + TIER_0**.
- Deny PAGE for `SOURCE_TOPIC` (cap to TICKET/NOTIFY).
- Evidence requirements declared per Finding: `finding.evidence_required[]` (no giant central list).
- Dedupe degraded mode: if Redis down → no PAGE/TICKET; NOTIFY only.

### 4.4 Topology registry semantics
- `stream_id` = logical end-to-end pipeline grouping key.
- Cluster/env are instance-scoped: `streams[].instances[]` keyed by `(env, cluster_id)`.
- `topic_index` scoped by `(env, cluster_id)` to prevent collisions.

### 4.5 Notification / SN
- PagerDuty creates SN Incidents; AIOps does not create Incidents.
- Phase 1A: SOFT postmortem enforcement (Slack/log + CaseFile obligation).
- Phase 1B: HARD automation (Problem + PIR tasks) after linkage confirmed.

### 4.6 Local dev
Local build must run end-to-end with **no external integrations**:
- Integrations support modes: `OFF | LOG | MOCK | LIVE`; local default is LOG/OFF.
- If Slack/SN not configured: emit structured log events.
- Local durability invariants must still be testable (MinIO + Postgres locally).

---

## 5) Key contracts/artifacts (authoritative inputs)
Use these as source-of-truth; do not re-derive:
- Topology registry (legacy): `/mnt/data/topology-registry.yaml`
- Topology registry (instances + ownership + clusters): `/mnt/data/topology-registry.instances-v2.ownership-v1.clusters.yaml`
- Registry loader/backward-compat rules: `/mnt/data/topology-registry-loader-rules-v1.md`
- Rulebook v1 (AG0–AG6): `/mnt/data/rulebook-v1.yaml`
- GateInput v1 contract: `/mnt/data/gateinput-v1.contract.yaml`
- Redis TTL policy v1: `/mnt/data/redis-ttl-policy-v1.md`
- Outbox policy v1: `/mnt/data/outbox-policy-v1.md`
- Peak policy v1: `/mnt/data/peak-policy-v1.md`
- Prometheus metrics contract v1: `/mnt/data/prometheus-metrics-contract-v1.yaml`
- ServiceNow linkage contract v1: `/mnt/data/servicenow-linkage-contract-v1.md`
- Local-dev no-external-integrations contract v1: `/mnt/data/local-dev-no-external-integrations-contract-v1.md`
- Phase 2 DoD v1: `/mnt/data/phase-2-dod-v1.md`
- Phase 3 DoD v1: `/mnt/data/phase-3-dod-v1.md`
- Diagnosis policy draft (not frozen): `/mnt/data/diagnosis-policy.yaml`
- Optional cues (may be outdated): `/mnt/data/claude_aiops_mvp_architecture_v6.md`

---

## 6) Open items (explicit placeholders, not blockers)
- Edge Fact schema for platform-layer instrumentation (Phase 3+).
- Deeper sink-to-stream mapping policy (must remain exposure-safe).

---

## 7) Ask of BMAD
Generate a coherent set of artifacts (PRD + Architecture + Epics/Stories) that:
- implements Phase 0 → Phase 1B as the “delivery critical path”
- keeps Phase 2/3 as planned increments using the frozen DoDs
- preserves all locked contracts and invariants above
- includes governance, auditability, operability, DR considerations as first-class

