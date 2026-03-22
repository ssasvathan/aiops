---
stepsCompleted: [1, 2, 3, 4, 5, 6]
inputDocuments:
  - archive/project-context.md
  - artifact/revision-phase-1/baseline-summary.md
  - artifact/revision-phase-1/implementation-summary.md
  - artifact/revision-phase-1/bmad-revision-list.md
  - docs/index.md
  - docs/project-overview.md
  - docs/architecture.md
  - docs/technology-stack.md
  - docs/component-inventory.md
  - docs/architecture-patterns.md
  - docs/contracts.md
  - docs/runtime-modes.md
  - docs/api-contracts.md
  - docs/data-models.md
  - docs/schema-evolution-strategy.md
  - docs/development-guide.md
  - docs/deployment-guide.md
  - docs/local-development.md
  - docs/contribution-guide.md
  - docs/project-structure.md
date: 2026-03-21
author: Sas
---

# Product Brief: aiOps

## Executive Summary

aiOps is an event-driven AIOps triage platform designed to ingest telemetry (metrics, logs, traces) from across the infrastructure estate — VMs, OpenShift, databases, Kafka, applications — and produce deterministic, auditable operational decisions through safety-gated triage. Phase 1 focuses on Kafka infrastructure anomaly detection via Prometheus metrics as the proving ground for a telemetry-source-agnostic architecture: the pipeline's contracts, gating engine, casefile persistence, and dispatch layers are designed to support any anomaly source without structural changes.

The baseline implementation delivered all 8 epics covering foundation, evidence collection, topology, durable triage/outbox, deterministic gating, LLM diagnosis, governance/observability, and ServiceNow automation. However, several critical subsystems were built but not wired into production code paths, and the cold-path runtime remains a stub. This revision phase activates the delivered capabilities into operational readiness for the upcoming dev OpenShift deployment, with a mandatory hot/hot 2-pod minimum requiring multi-replica safety from day one.

---

## Core Vision

### Problem Statement

Operations teams currently rely on static alerting and monitoring for infrastructure health — threshold-based alerts that lack contextual awareness, produce alert fatigue, and require manual triage to determine severity, blast radius, and ownership routing. There is no automated system that detects anomaly patterns, correlates them with topology and ownership, and routes actionable, deduplicated operational decisions with safety guarantees and full audit traceability.

### Problem Impact

The status quo produces four specific failure modes:

- **Threshold rot** — static thresholds set during onboarding are never recalibrated. A topic handling 100 msg/s at alert creation now handles 10,000 msg/s. The original threshold is meaningless, but nobody adjusts it.
- **Blast radius blindness** — an alert fires on a consumer group. Is it a TIER_0 source topic feeding 12 critical downstream consumers, or a TIER_2 internal topic with zero dependents? The operator spends 15 minutes manually tracing topology before assessing severity.
- **Page storms** — a single infrastructure issue produces dozens of correlated alerts across consumer groups in the same cluster. Without fingerprint-based deduplication with TTLs, the on-call engineer's phone rings repeatedly for the same root cause.
- **Decision opacity** — when an auditor asks "why was a page sent for this incident but not for a similar one two days later?" there is no answer. Static alerting records threshold breaches, not the evidence evaluated, gates applied, or policy version active at decision time.

### Why Existing Solutions Fall Short

The real competition is the status quo: hand-maintained static alert rules in Prometheus AlertManager, a spreadsheet of escalation contacts, and a PagerDuty integration that pages whoever last edited the routing rule. Horizontal observability platforms (Datadog, PagerDuty AIOps) provide monitoring and alerting but lack topology-aware blast radius assessment, multi-level ownership routing with confidence scoring, deterministic safety-gated action decisions, and 25-month reproducible decision trails for regulatory compliance.

### Proposed Solution

aiOps replaces static alerting with a deterministic, evidence-driven triage pipeline:
- **Evidence collection** from Prometheus with per-scope statistical baselines, sustained anomaly tracking, and peak/near-peak classification
- **Topology resolution** with blast radius assessment, downstream impact identification, and multi-level ownership routing
- **Deterministic rulebook gating** (AG0-AG6) with environment caps, criticality-tier awareness, evidence sufficiency, fingerprint deduplication, and postmortem predicate evaluation
- **Durable case artifacts** with write-once semantics, SHA-256 hash chains, and policy version stamping for 25-month audit replay
- **Advisory LLM diagnosis** on a non-blocking cold path producing structured, schema-validated reports with evidence citation
- **Multi-replica Kubernetes deployment** with distributed cycle locking, externalized state, and atomic deduplication

### Key Differentiators

- **Zero false pages outside production critical infrastructure** — PAGE is structurally impossible outside PROD+TIER_0; actions can only be capped downward, never escalated
- **Instant ownership resolution** — the system resolves the owning team through multi-level lookup (consumer group > topic > stream > platform default) before the action fires, eliminating manual runbook lookups
- **Every decision reproducible for 25 months** — hand an auditor the case ID and they can replay the exact gate evaluations with the exact policy versions, evidence snapshot, and reason codes
- **LLM-enriched diagnosis that structurally cannot cause an outage** — the hot path has no import path, no shared state, and no conditional wait on the cold path; this is a design invariant, not a deployment choice
- **Telemetry-source-agnostic architecture** — the gating engine evaluates `GateInputV1` without knowing whether the anomaly originated from Kafka lag, VM CPU, or database connection exhaustion. Adding new infrastructure sources means extending evidence collectors and topology registry, not rewriting the triage pipeline

### Future Vision

**Multi-infrastructure telemetry expansion** — Phase 1 proves the architecture against Kafka + Prometheus. Future phases extend evidence collection to VMs, OpenShift, databases, and applications, ingesting metrics, logs, and traces through additional evidence collectors that produce the same Finding and GateInput contracts.

**Hard postmortem enforcement** — Phase 1A implements soft postmortem detection (AG6 identifies qualifying cases, Slack notification nudges review). Future phases evolve to a three-layer hard postmortem lifecycle:
- **Mandatory creation** — qualifying cases automatically generate PIR artifacts with deadlines; missed deadlines trigger escalation
- **Quality gates** — required sections (root cause classification, evidence citations, owned action items), LLM-assisted draft from existing DiagnosisReportV1, completeness validation before closure
- **Follow-through tracking** — action item deadline monitoring, escalation on overdue items, completion rate metrics as an operational health signal

This represents the system's evolution from operational triage (detect and act) to operational learning (detect, act, learn, and verify improvement) — closing the full incident lifecycle loop with auditable enforcement at every stage.

---

## Target Users

### Primary Users

**On-Call Engineer — "The Responder"**

Role: Application or platform engineer on pager rotation, responsible for initial incident response across Kafka infrastructure.

Current pain: Receives raw static alerts with no context — manually traces topology to assess blast radius, checks spreadsheets for ownership, and triages severity by gut feel. Page storms during cluster-wide issues flood their phone with dozens of alerts for the same root cause. Spends more time figuring out *who should care* and *how bad is it* than actually resolving the issue.

How aiOps helps: Receives pre-triaged, deduplicated actions with ownership resolved, blast radius assessed, and severity determined by deterministic gates. A single PAGE for a sustained TIER_0 anomaly replaces 40 raw alerts. The case ID links to a full evidence snapshot and gate evaluation trail.

Success moment: A sustained consumer lag anomaly on a critical source topic fires a single PAGE to the correct team with full context — the on-call engineer starts fixing instead of investigating.

**SRE / Platform Engineer — "The Operator"**

Role: Owns the aiOps platform itself. Maintains the running deployment, monitors system health (outbox, Redis, OTLP), tunes operational parameters, and ensures the pipeline is functioning correctly across environments.

Current pain: Today, maintains static AlertManager rules that rot over time. No visibility into whether alerting thresholds are still relevant. No systematic way to track which anomalies were acted on and why.

How aiOps helps: Operates a self-monitoring triage platform with meta-health metrics (outbox age, Redis status, pipeline latency, coordination lock metrics). Tunes behavior through YAML policy artifacts (rulebook thresholds, anomaly detection sensitivity, peak policy, denylist) that propagate through environments. Has full audit trail of every operational decision the system made.

Success moment: Adjusts a rulebook threshold in YAML, deploys to dev, verifies gate behavior changes in casefile artifacts, and promotes to prod — confident the change does exactly what was intended because the YAML is authoritative.

**Application Team Engineer — "The Maintainer"**

Role: Engineers who own the topology registry, denylist, and policy configurations. They make changes and propagate them through dev > UAT > prod.

Current pain: Configuration changes to alerting rules are scattered, undocumented, and hard to verify. No way to test a threshold change before it hits production.

How aiOps helps: All configuration is versioned YAML with frozen Pydantic contract validation. Changes are tested in lower environments with real pipeline execution before promotion. Policy version stamping in casefiles provides traceability for every config change.

### Secondary Users

**Kafka Consumer/Producer Stakeholders — "The Recipients"**

Role: Application teams whose Kafka consumer groups and topics are monitored by aiOps. They do not interact with aiOps directly.

Interaction: Receive PagerDuty pages, Slack notifications, or ServiceNow tickets when anomalies affect their infrastructure. From their perspective, aiOps is invisible — they experience better alerting with ownership pre-resolved, deduplicated actions, and contextual evidence attached to notifications.

**Senior Management — "The KPI Consumers"**

Role: Engineering leadership tracking operational health and incident management effectiveness.

Interaction: Consume KPIs derived from aiOps operational data — case volumes, action distribution (PAGE/TICKET/NOTIFY/OBSERVE), deduplication rates, mean time from anomaly detection to action dispatch, postmortem compliance rates. Dashboard tooling is future scope; initial KPI extraction is available through OTLP metrics and structured log queries.

### User Journey

**On-Call Engineer journey:**
1. **Trigger** — PagerDuty page arrives with case ID, anomaly summary, ownership, and blast radius classification
2. **Context** — Opens case artifact to see full evidence snapshot, gate evaluations with reason codes, and action decision rationale
3. **Action** — Begins remediation with topology context already provided — knows which downstream consumers are at risk
4. **Resolution** — Case diagnosis (if available from cold path) provides LLM-generated root cause hypothesis and next checks
5. **Learning** — Postmortem notification (soft, Phase 1) prompts review for qualifying cases

**SRE / Platform Engineer journey:**
1. **Deploy** — Deploys aiOps to OpenShift with hot/hot 2-pod minimum, feature flags for distributed coordination
2. **Monitor** — Watches system health via OTLP metrics: pipeline latency, outbox age, Redis status, coordination lock stats
3. **Tune** — Adjusts anomaly detection policy, rulebook thresholds, or topology registry through versioned YAML changes
4. **Verify** — Reviews casefile artifacts in lower environments to confirm policy changes produce expected gate decisions
5. **Promote** — Propagates validated configuration to production with confidence

---

## Success Metrics

### Activation Metrics (Revision Phase — Binary Pass/Fail)

Each revision change has a verifiable activation signal:

| Change | Activation signal |
|---|---|
| CR-01: Wire Redis cache | Sustained window state loads from Redis across cycles; peak profiles use cached data |
| CR-02: DSL rulebook | Gates evaluate from YAML predicates; all 36 test functions pass unmodified |
| CR-03: Unified baselines | Peak classifications produce PEAK/NEAR_PEAK/OFF_PEAK (not UNKNOWN); AG6 fires for qualifying cases |
| CR-04: Sharded findings cache | Shard assignment produces even scope distribution; checkpoint replaces per-scope writes |
| CR-05: Distributed hot/hot | Two pods run with zero duplicate pages/tickets; cycle lock acquired/yielded visible in metrics |
| CR-06: Evidence summary | Builder produces stable text output for LLM consumption |
| CR-07: Cold-path consumer | Consumer processes CaseHeaderEventV1 from Kafka; diagnosis.json written to S3 |
| CR-08: Remove criteria | LLM diagnosis runs for all cases regardless of env/tier/sustained |
| CR-09: Prompt optimization | Enriched prompt includes full Finding fields, domain descriptions, few-shot example |
| CR-10: Redis bulk + memory | Batched Redis loads replace sequential GETs; sustained computation parallelized |
| CR-11: Topology simplify | v0 format code removed; topology YAML loads from config/; resolver tests green |

### Operational Metrics (3-Month Baseline Establishment)

The first 3 months of real operation establish the measurement baseline. These are numbers we're *learning*, not targets we're hitting.

| Metric | Measurement method | Purpose |
|---|---|---|
| Mean cases per day | OTLP counter | Volume baseline |
| Action distribution | OTLP counters per action type | Calibration indicator — healthy systems show mostly OBSERVE/NOTIFY with rare PAGE |
| Deduplication suppression rate | OTLP counter (suppressed / total) | Page storm prevention effectiveness |
| Sustained detection rate | OTLP gauge (% anomalies reaching sustained=true) | Detection depth indicator |
| Mean detection-to-action latency | OTLP histogram | Responsiveness baseline |
| Cold-path diagnosis turnaround | OTLP histogram | LLM performance baseline |
| False positive rate | Manual review — actions dispatched vs. actions acknowledged as real | Trust indicator (critical) |
| Incident prevention rate | Manual review — aiOps cases that preceded manual incident creation | Proactive value indicator |

### Operational Success (3-Month Goals)

- **Proactive detection** — aiOps identifies anomalies and triggers actions before they escalate to user-reported incidents, measured by incident-to-case correlation during manual reviews
- **Cleaner triage** — on-call engineers receive pre-triaged actions with ownership, blast radius, and severity already determined, reducing time-to-context
- **Earlier detection** — sustained anomaly tracking and per-scope baselines catch degradation patterns that static thresholds miss

### Pipeline Health Metrics

| Metric | Target | Emission | Viewed in |
|---|---|---|---|
| Cycle completion rate | 100% of intervals execute | OTLP counter | Dynatrace |
| Outbox delivery SLO | p95 <= 1 min, p99 <= 5 min | OTLP histogram | Dynatrace |
| DEAD outbox rows | 0 (standing posture) | OTLP gauge | Dynatrace |
| Gate evaluation latency | p99 <= 500ms | OTLP histogram | Dynatrace |
| Multi-replica coordination | Zero duplicate dispatches | OTLP counters (lock acquired/yielded/failed) | Dynatrace |

### Business Objectives

- **Prove the architecture under real conditions** — dev OpenShift deployment with hot/hot 2-pod minimum, real Prometheus data, all 11 revision changes activated
- **Build confidence for UAT/prod promotion** — stable operation in dev with documented triage quality evidence
- **Establish the operational baseline** — first 3 months of real data establish measurement baselines for setting targets in subsequent phases

### Metrics Infrastructure

| Channel | Emission | Collection | Viewing |
|---|---|---|---|
| Quantitative metrics | OTLP counters, histograms, gauges | Dynatrace OTLP ingest | Dynatrace Dashboards |
| Structured event logs | JSON to stdout (structlog) | OpenShift log collection → Elastic (LASS) | Kibana / Elastic queries |
| Case-level audit trails | Structured logs with correlation_id (case_id) | Elastic (LASS) | Kibana filtered by correlation_id |
| Casefile artifacts | S3 object storage | Direct S3 inspection | S3 client / script-assisted |

**Prerequisite:** Verify Elastic (LASS) index parses structured JSON fields for field-level querying (not raw blob storage).

**Operational setup:** Dynatrace dashboard (pipeline heartbeat, action distribution, deduplication, outbox health, coordination stats) and Kibana saved searches (case trail, gate decisions, action events) are deployment-time deliverables, not code changes.

---

## Revision Phase Scope

### Core Scope (All-or-Nothing — 11 Changes)

All 11 revision changes must land for the dev OpenShift deployment. No partial delivery.

| # | Change | Category |
|---|---|---|
| CR-01 | Wire Redis cache layer (sustained state + peak profiles + batch ops) | Activation |
| CR-02 | DSL-driven rulebook gate engine (YAML-authoritative evaluation) | Refactor |
| CR-03 | Unified per-scope metric baselines (replace hardcoded thresholds) | New capability |
| CR-04 | Sharded findings cache for hot/hot K8s deployment | New capability |
| CR-05 | Distributed hot/hot Phase 1 — multi-replica safety | New capability |
| CR-06 | Evidence summary builder for LLM consumption | Activation |
| CR-07 | Cold-path Kafka consumer pod (implement runtime mode) | Activation |
| CR-08 | Remove cold-path invocation criteria (unconditional LLM diagnosis) | Simplification |
| CR-09 | Optimize cold-path LLM prompt for higher quality output | Enhancement |
| CR-10 | Redis bulk load & peak stage memory efficiency | Performance |
| CR-11 | Topology registry simplify to single format | Simplification |

### Operational Setup (Separate from Code Changes)

- Dynatrace dashboard: pipeline heartbeat, action distribution, deduplication, outbox health, coordination stats
- Kibana/Elastic saved searches: case trail by correlation_id, gate decisions, action dispatch events
- OpenShift deployment manifests and pod configuration
- OTLP exporter endpoint configuration for dev Dynatrace tenant
- Verify Elastic (LASS) JSON field parsing for structured log queries

### Out of Scope for This Revision Phase

- New anomaly families beyond consumer lag, throughput constrained, volume drop
- Multi-infrastructure telemetry sources (VMs, OCP, databases, applications)
- KPI dashboards for senior management
- Hard postmortem enforcement lifecycle
- CI/CD pipeline definitions
- Cross-pod HealthRegistry synchronization
- Cold-path distributed coordination
- Runtime/dynamic rule loading (handlers are code, not plugins)

### Future Vision

**Multi-infrastructure telemetry expansion** — extend evidence collection beyond Kafka + Prometheus to VMs, OpenShift, databases, and applications. Requires understanding how log and trace triage pipelines differ from metric-based pipelines — log triage involves pattern matching and anomaly detection over unstructured/semi-structured text; trace triage involves latency analysis, error propagation, and service dependency mapping. Each requires purpose-built evidence collectors that produce the same Finding and GateInput contracts.

**Application telemetry instrumentation** — existing applications in the estate lack telemetry instrumentation. A prerequisite for broader triage coverage is instrumenting these applications with metrics, structured logging, and distributed tracing so they produce the signals aiOps can ingest.

**ML-enhanced root cause analysis** — evolve beyond the current single-LLM cold-path diagnosis toward a dedicated ML-based RCA model. The organization has an existing enterprise RCA agent; future phases would implement agent-to-agent invocation where aiOps triggers the enterprise RCA agent after anomaly detection, combining aiOps's structured evidence context with the RCA agent's diagnostic capabilities for higher accuracy root cause identification.

**Hard postmortem enforcement** — three-layer lifecycle (mandatory creation, quality gates, follow-through tracking) as described in the Core Vision section.
