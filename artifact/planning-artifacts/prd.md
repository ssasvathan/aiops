---
stepsCompleted: ['step-01-init', 'step-02-discovery', 'step-02b-vision', 'step-02c-executive-summary', 'step-03-success', 'step-04-journeys', 'step-05-domain', 'step-06-innovation', 'step-07-project-type', 'step-08-scoping', 'step-09-functional', 'step-10-nonfunctional', 'step-11-polish', 'step-12-complete']
inputDocuments: ['artifact/project-context.md', 'docs/index.md', 'docs/project-overview.md', 'docs/architecture.md', 'docs/architecture-patterns.md', 'docs/technology-stack.md', 'docs/component-inventory.md', 'docs/project-structure.md', 'docs/api-contracts.md', 'docs/data-models.md', 'docs/contracts.md', 'docs/runtime-modes.md', 'docs/schema-evolution-strategy.md', 'docs/development-guide.md', 'docs/local-development.md', 'docs/deployment-guide.md', 'docs/contribution-guide.md', 'docs/developer-onboarding.md', 'artifact/brainstorming/brainstorming-session-2026-04-10-001.md', 'archive/iteration 4/roadmap-2026-q2-q4.md']
workflowType: 'prd'
documentCounts:
  briefs: 0
  research: 0
  brainstorming: 1
  projectDocs: 17
classification:
  projectType: 'internal_tool_dashboard'
  domain: 'it_operations_aiops'
  complexity: 'medium'
  projectContext: 'brownfield'
notes:
  - 'Grafana instance needed in docker-compose infrastructure'
---

# Product Requirements Document - aiOps Q1 MVP Stakeholder Dashboard

**Author:** Sas
**Date:** 2026-04-10

## Executive Summary

The Q1 MVP Stakeholder Dashboard is a Grafana-based KPI dashboard that makes the AIOps triage pipeline's intelligence visible to four stakeholder personas — from a 3-second executive confidence signal to a full SRE Lead triage workspace. It serves as the internal demo artifact for a competitive evaluation: AIOps vs. adopting an external framework. The dashboard must prove in 60 seconds that a purpose-built pipeline with deterministic noise suppression, team-aware routing, and LLM-powered diagnosis delivers more value than any off-the-shelf alternative.

The deliverable has two engineering components: (1) four new OTLP instruments added to the existing pipeline to emit business-level metrics (findings by anomaly family, gating evaluations, evidence status, diagnosis completions), and (2) a two-layer Grafana dashboard architecture — a main "front page" with above-the-fold stakeholder narrative panels and a per-topic drill-down detail page for SRE operational use. Infrastructure scope includes adding Grafana and Prometheus scrape configuration to the project's docker-compose stack.

### What Makes This Special

The AIOps pipeline already emits a complete triage story per anomaly — decision rationale (gate rule IDs), evidence status (PRESENT/UNKNOWN/ABSENT/STALE), team ownership (routing keys), and LLM-generated diagnostic hypotheses. No external framework ships with this level of contextual intelligence. The dashboard's job is to surface this existing richness, not generate new data.

Three panels deliver the competitive proof: the **baseline deviation overlay** (actual Kafka metrics against a seasonal expected-range band — proves AI understands "normal"), the **gating intelligence funnel** (detected → suppressed → dispatched — proves noise prevention), and the **LLM diagnosis engine stats** (invocations, success rate, latency — proves AI-powered hypothesis generation is live and working).

The "newspaper front page" architecture enforces ruthless prioritization: everything visible without scrolling is the stakeholder story (fund us), everything below the fold is operational credibility (trust us), and the drill-down dashboard is genuine SRE value (give us scope).

## Project Classification

- **Project Type:** Internal tool / Grafana KPI dashboard with backend OTLP instrumentation
- **Domain:** IT Operations / AIOps — SRE observability and anomaly triage
- **Complexity:** Medium — targeted instrumentation additions to a mature pipeline, plus Grafana dashboard configuration
- **Project Context:** Brownfield — extends the existing `aiops-triage-pipeline` with 4 new OTLP instruments and a new visualization layer

## Success Criteria

### User Success

- **VP/Executive (3-second test):** During live walkthrough, the hero banner and P&L stat communicate platform health and value without explanation — presenter confirms understanding with a single glance
- **Platform Senior Director (30-second test):** Capability stack panel visually confirms every pipeline layer (detection, enrichment, gating, dispatch, LLM diagnosis) is operational with live throughput
- **SRE Director (60-second test):** Gating intelligence funnel prompts a reaction of "this protects my team from noise" — detected-to-dispatched ratio is self-evident
- **SRE Lead (operational test):** Drill-down dashboard provides actionable triage context during a simulated incident walkthrough — anomaly family, evidence status, action decision rationale, and LLM diagnosis stats are immediately accessible

### Business Success

- **Primary outcome:** Stakeholder confidence in AIOps as the preferred path over adopting an external framework
- **Signal:** Stakeholders express willingness to continue investment and expand scope after the live demo
- **Competitive proof:** Dashboard demonstrates at least 3 capabilities no off-the-shelf framework provides out of the box (deterministic gating funnel, team-aware routing, LLM-powered diagnosis)

### Technical Success

- **OTLP instruments:** 4 new instruments (`aiops.findings.total`, `aiops.gating.evaluations_total`, `aiops.evidence.status`, `aiops.diagnosis.completed_total`) emitting correctly with business-level labels
- **Data source:** Pipeline running against real dev Kafka data — no simulated or mocked data
- **Infrastructure:** Grafana added to docker-compose stack with Prometheus configured as data source, dashboard panels rendering live data
- **Dashboard architecture:** Two-layer Grafana setup — main front page (above/below fold) and per-topic drill-down — both functional and linked

### Measurable Outcomes

- All above-the-fold panels (hero banner, P&L stat, topic heatmap, baseline deviation overlay) render with live dev data
- All below-the-fold panels (gating funnel, action distribution, anomaly breakdown, capability stack, diagnosis stats, pipeline throughput) render with live dev data
- Drill-down dashboard accessible from heatmap tiles with per-topic filtering
- Full live walkthrough completable in under 5 minutes covering all 4 persona perspectives
- Zero manual data manipulation required — all panels driven by pipeline OTLP instruments and Prometheus queries

## Product Scope & Strategy

### MVP Strategy

**MVP Approach:** Demo-driven MVP — the minimum deliverable is a live dashboard walkthrough that earns stakeholder confidence. Every feature is justified by its role in the 5-minute demo narrative. If it doesn't serve a persona's question during the walkthrough, it's post-MVP.

**Resource Requirements:** Solo developer (Sas). Instrumentation and dashboard work are sequential — instruments must emit data before panels can visualize it.

**Core Journey Supported:** Live Demo Walkthrough (Journey 1)

### MVP Feature Set (Phase 1)

| Capability | Demo Role | Risk Level |
|---|---|---|
| 4 OTLP instruments with business labels | Data foundation — nothing works without this | Low — follows existing patterns |
| Grafana + Prometheus in docker-compose | Infrastructure foundation | Low — standard setup |
| Prometheus scrape config for pipeline | Connects data flow | Low — configuration only |
| Above-the-fold panels (hero banner, P&L stat, heatmap, baseline overlay) | "Fund us" — 3-second to 30-second story | **High — visual design is the risk** |
| Below-the-fold panels (gating funnel, action distribution, anomaly breakdown, capability stack, diagnosis stats, pipeline throughput) | "Trust us" — operational credibility | Medium — more panels, but simpler individually |
| Drill-down dashboard with topic filtering | "Give us scope" — SRE operational proof | Medium — template duplication pattern |
| Dashboard JSON files committed to repo | Reproducible demo environment | Low — Grafana export |

### Phase 2: Growth (Post-Demo)

- Team-based filtering via `routing_key` label (label already ships with MVP, meaningful after multi-team onboarding)
- SRE Lead day-to-day operational use of drill-down dashboard
- Grafana alerting rules on key panels
- Dashboard JSON provisioning for repeatable deployment to shared environments
- Lightweight diagnosis API endpoint for LLM verdict text on dashboard before Loki

### Phase 3: Expansion (Q3+ with LGTM)

- Full LLM diagnosis verdict text panels via Loki (Q3 LGTM integration)
- True seasonal baseline band overlay queried from Redis
- Multi-topic baseline sparkline panels
- Structured log events as dashboard data source (free when Loki lands)
- Full operational SRE dashboard extending beyond stakeholder narrative

### Risk Mitigation Strategy

**Technical Risk — Visual Compelling Design (HIGH):**
The OTLP instrumentation and infrastructure setup follow established patterns. The real risk is making Grafana panels visually compelling enough to land the "aha" moment in a live demo. Mitigations:
- Start with the baseline deviation overlay panel — the single most visually compelling panel. Get this right first and use it as the visual quality bar.
- Use Grafana's built-in stat, gauge, and heatmap panel types for above-the-fold panels — designed for at-a-glance readability.
- Iterate on panel titles, color schemes, and thresholds with the demo narrative in mind — every panel should answer its persona's question without explanation.
- Do a dry-run walkthrough before the stakeholder demo to identify panels that need visual tuning.

**Market Risk — Competitive Evaluation (MEDIUM):**
Stakeholders may compare the dashboard to polished commercial AIOps tool demos. Mitigation: lead with differentiation, not aesthetics — show 3 capabilities no commercial tool provides (deterministic gating transparency, environment-aware action caps, LLM diagnosis).

**Resource Risk — Solo Developer (LOW-MEDIUM):**
Single point of failure if blocked. Mitigation: the work is modular — instruments, infrastructure, main dashboard, drill-down dashboard are independent deliverables. If time is tight, the drill-down dashboard is the first candidate to simplify (fewer panels, not cut entirely).

## User Journeys

### Journey 1: The Live Demo Walkthrough (Primary — MVP)

**Persona:** Sas, Platform Engineer and AIOps champion
**Situation:** Stakeholders are evaluating whether to continue investing in AIOps or adopt an external framework. Sas has 5 minutes to make the case.
**Goal:** Walk four stakeholder personas through the dashboard in a single fluid narrative that builds from "it works" to "it's smart" to "it's valuable" to "it's operationally real."

**Opening Scene:** Sas opens the main dashboard in Grafana. The room sees the hero banner — a single aggregate health signal across all monitored pipelines. Green. The P&L stat reads "47 anomalies detected & acted on this week across 9 topics." The VP nods — the platform is alive and producing value. Three seconds, first impression landed.

**Rising Action:** Sas gestures to the topic health heatmap — 9 tiles, mostly green, one amber. "Each tile is a critical Kafka topic we monitor." Then to the baseline deviation overlay — a time-series line with a shaded expected-range band. "This is consumer lag on our payments topic. The shaded band is what the AI learned is normal for this time of day and day of week. When the line breaks out of the band — that's a detection." The Platform Director sees the capability stack below the fold — every pipeline stage lit up with live latency. Detection, enrichment, gating, dispatch, LLM diagnosis — all operational.

**Climax:** Sas scrolls to the gating intelligence funnel. "We detected 200 anomalies this week. AG1 suppressed 120 because they weren't sustained. AG2 capped 50 during peak hours. Only 30 reached your team as NOTIFY actions. Zero false PAGEs." The SRE Director leans forward — the platform is *preventing* noise, not creating it. The action distribution chart shows a stable, low NOTIFY trend over 7 days. The anomaly family breakdown shows BASELINE_DEVIATION leading — generic detection is working.

**Resolution:** Sas clicks a heatmap tile and opens the drill-down dashboard. Per-topic Prometheus metrics with tighter time windows. Evidence status traffic light showing what the system can and can't see. Findings filtered by topic with action decision rationale. AI diagnosis stats showing confidence levels. "This is where your SRE Lead would work during an incident — not just graphs, but the full decision story." The room understands: this isn't another monitoring dashboard. This is an intelligent triage system that no off-the-shelf framework provides.

### Journey 2: The Skeptical Stakeholder (Edge Case — Demo Failure Recovery)

**Persona:** A senior director who has evaluated external AIOps frameworks
**Situation:** Mid-demo, they challenge: "Our vendor's tool does anomaly detection too. What's different here?"
**Goal:** The presenter uses the dashboard itself to answer — no slides, no hand-waving.

**Opening Scene:** The question lands during the gating funnel section. The presenter doesn't break stride.

**Rising Action:** Sas points to the funnel: "Their tool would show you 200 anomalies. Ours shows you the 30 that matter, and tells you exactly which guardrail rules filtered the other 170 — AG1, AG2, AG3, by name." Then to the action distribution: "We cap actions by environment — dev can only NOTIFY, only prod TIER_0 can PAGE. That's structural, not configurable per-alert." Then to the diagnosis stats: "And our cold-path LLM generates a starting hypothesis for every significant anomaly — fault domain, confidence level, recommended next checks."

**Resolution:** The skeptic sees three capabilities demonstrated live with real data that their vendor cannot replicate out of the box: deterministic multi-rule gating with transparency, environment-aware action caps, and LLM-powered diagnostic reasoning. The dashboard answered the objection without leaving the screen.

### Journey 3: Dashboard Maintainer (Post-MVP — Operational)

**Persona:** Platform team engineer responsible for dashboard upkeep
**Situation:** A new Kafka topic is onboarded to AIOps monitoring. The dashboard needs to reflect the expanded coverage.
**Goal:** Add the new topic to the dashboard with minimal effort.

**Opening Scene:** The new topic starts flowing through the pipeline. The 4 OTLP instruments automatically emit metrics with the new topic label — no code change needed.

**Rising Action:** The topic heatmap panel, driven by `aiops.findings.total{topic}`, already shows a new tile. Below-the-fold panels automatically include the new topic's data in their aggregates.

**Resolution:** The maintainer duplicates the existing drill-down template and updates the topic filter variable. Zero-effort on the main dashboard, low-effort on drill-down. The label-driven OTLP design pays dividends.

### Journey Requirements Summary

| Journey | Capabilities Revealed |
|---|---|
| **Live Demo Walkthrough** | Above-the-fold narrative panels, below-the-fold credibility panels, drill-down navigation, all panels rendering live dev data, fluid top-to-bottom scroll + click-through flow |
| **Skeptical Stakeholder** | Gating funnel with named rule IDs, environment action cap visibility, LLM diagnosis stats — all visible on-screen without navigation |
| **Dashboard Maintainer** | Label-driven OTLP design for automatic topic inclusion, drill-down template duplication, Grafana variable-based filtering |

## Technical Architecture

### Data Flow

Pipeline (Python) → OTLP exporter → Prometheus (scrape) → Grafana (query + visualize)

### Infrastructure Additions to docker-compose

- Grafana service with provisioned data sources (Prometheus) and dashboard JSON files
- Prometheus scrape configuration targeting the pipeline's metrics endpoint

### Dashboard Provisioning

- Dashboard definitions stored as JSON files in the repository (`grafana/dashboards/`)
- Grafana provisioning config (`grafana/provisioning/`) auto-loads dashboards on startup
- Two dashboard JSON files: main front page + per-topic drill-down
- Grafana variables for topic filtering on drill-down dashboard

### Deployment Considerations

- **Local development:** Grafana + Prometheus in docker-compose, pipeline running against dev Kafka data, dashboards auto-provisioned from repo JSON files
- **Demo instance:** Shared Grafana instance accessible to stakeholders, connected to a running pipeline with real dev data — not localhost
- **Production:** Dashboard deployed against existing Prometheus with 30-day retention — no dashboard changes required
- **No authentication required** for MVP — internal demo context only

## Functional Requirements

### Pipeline Telemetry

| Instrument | Type | Labels | Pipeline Location |
|---|---|---|---|
| `aiops.findings.total` | Counter | `anomaly_family`, `final_action`, `topic`, `routing_key`, `criticality_tier` | Gating/dispatch stage (post-ActionDecisionV1) |
| `aiops.gating.evaluations_total` | Counter | `gate_id`, `outcome` | Rule engine evaluation |
| `aiops.evidence.status` | Gauge | `scope`, `metric_key`, `status` | Evidence stage |
| `aiops.diagnosis.completed_total` | Counter | `confidence`, `fault_domain_present` | Diagnosis cold-path completion handler |

All instruments follow existing patterns in `health/metrics.py` and `baseline/metrics.py`. Use `create_counter` for totals, `create_up_down_counter` for the evidence status gauge, per project context conventions.

- FR1: The pipeline can emit a counter of findings with labels for anomaly family, final action, topic, routing key, and criticality tier after each gating decision
- FR2: The pipeline can emit a counter of gating evaluations with labels for gate ID and outcome during rule engine evaluation
- FR3: The pipeline can emit a gauge of evidence status with labels for scope, metric key, and status during evidence collection. *Note: high cardinality (~hundreds of series across 9 topics) — Grafana queries must handle this efficiently.*
- FR4: The pipeline can emit a counter of completed diagnoses with labels for confidence level and fault domain presence after cold-path completion

### Platform Health Overview

- FR5: The dashboard can display an aggregate health status signal (green/amber/red) across all monitored pipeline components
- FR6: The dashboard can display a single hero stat showing total anomalies detected and acted on within a configurable time window
- FR7: The dashboard can display a topic health heatmap with one tile per monitored Kafka topic, color-coded by health status

### Detection & Anomaly Visibility

- FR8: The dashboard can display a time-series panel showing actual Kafka metrics from Prometheus with the seasonal baseline expected range as visual context
- FR9: The dashboard can annotate Prometheus time-series panels with markers indicating when AIOps detected a deviation
- FR10: The dashboard can display a breakdown of findings by anomaly family (consumer lag, volume drop, throughput constrained proxy, baseline deviation)

### Noise Suppression Transparency

- FR11: The dashboard can display a gating intelligence funnel showing total findings detected, findings suppressed by each gate rule, and final dispatched actions
- FR12: The dashboard can display an action distribution over time as a stacked time-series showing OBSERVE, NOTIFY, TICKET, and PAGE counts
- FR13: The dashboard can show which specific gate rules (AG0-AG6) contributed to suppression with per-gate outcome counts

### AI Diagnosis Proof

- FR14: The dashboard can display LLM diagnosis engine statistics including invocation count, success rate, and average latency
- FR15: The dashboard can display diagnosis quality metrics showing confidence level distribution and fault domain identification rate

### Operational Triage

- FR16: The dashboard can provide a drill-down view for a specific topic accessible from the main dashboard heatmap
- FR17: The drill-down dashboard can display per-topic Prometheus metrics with a tighter time window than the main dashboard
- FR18: The drill-down dashboard can display evidence status per metric for a scope showing PRESENT, UNKNOWN, ABSENT, and STALE states
- FR19: The drill-down dashboard can display findings filtered by topic with action decision and gate rationale
- FR20: The drill-down dashboard can filter by topic using a Grafana variable selector
- FR21: The drill-down dashboard can trace a specific finding to its full action decision path including gate rule IDs, environment cap, and final action

### Pipeline Operational Visibility

- FR22: The dashboard can display a capability stack showing each pipeline stage with live status and last-cycle latency
- FR23: The dashboard can display pipeline throughput metrics including scopes evaluated and deviations detected per cycle
- FR24: The dashboard can display outbox health status

### Dashboard Infrastructure & Provisioning

- FR25: The docker-compose stack can run a Grafana instance with auto-provisioned data sources and dashboards
- FR26: The docker-compose stack can run Prometheus configured to scrape the pipeline's metrics endpoint with explicit retention settings sufficient for 7-day time windows
- FR27: Dashboard definitions can be stored as JSON files in the repository and auto-loaded by Grafana on startup
- FR28: The Grafana instance can verify connectivity to its configured Prometheus data source on startup

### Dashboard Presentation & Narrative

- FR29: The main dashboard can enforce an above-the-fold / below-the-fold visual hierarchy separating stakeholder narrative from operational detail
- FR30: The main dashboard can present above-the-fold panels in a fixed visual sequence: health banner, hero stat, topic heatmap, baseline deviation overlay
- FR31: The main dashboard can link to the drill-down dashboard from heatmap tiles
- FR32: The dashboard can display data across selectable time windows (1h, 24h, 7d, 30d) via a Grafana time picker
- FR33: The dashboard can apply consistent color semantics across all panels (green=healthy/present, amber=warning/stale, red=critical/unknown)
- FR34: The dashboard can be viewed in a presentation-friendly kiosk mode optimized for screen sharing or projector display

## Non-Functional Requirements

### Performance

- NFR1: All dashboard panels must render within 5 seconds on initial load, including Prometheus query execution
- NFR2: Switching between time windows (1h/24h/7d/30d) must re-render all panels within 5 seconds
- NFR3: Navigating from main dashboard to drill-down dashboard via heatmap link must complete within 3 seconds
- NFR4: Prometheus queries for 7-day range windows across all instruments must complete within 10 seconds. Production 30-day range query performance to be tuned post-MVP when real data volumes are known

### Reliability

- NFR5: All dashboard panels must display data (no "no data" or error states) when the pipeline has completed at least one cycle within the selected time window
- NFR6: Grafana must start with all dashboards and data sources provisioned without manual configuration steps
- NFR7: Docker-compose Prometheus must retain metric data for a minimum of 7 days for demo purposes. Production uses existing Prometheus infrastructure with 30-day retention — no dashboard changes required
- NFR8: The pipeline's OTLP instruments must emit metrics within the same cycle as the triggering event — no deferred or batched emission that would create data gaps during demo. Prometheus scrape interval must be shorter than cycle interval to avoid partial-snapshot reads
- NFR9: Dashboard panels must display meaningful zero-state representations when a metric has no occurrences (e.g., zero PAGE actions in dev), rather than error or empty states

### Data Freshness

- NFR10: Dashboard data may lag up to 5 minutes behind the most recent pipeline cycle — near-real-time is not required
- NFR11: Prometheus scrape_interval must be set to 15s or less

### Maintainability

- NFR12: Dashboard JSON files must be the single source of truth — any Grafana UI changes must be exportable back to JSON without manual reconstruction
- NFR13: Dashboard JSON exports must preserve panel IDs and inter-dashboard link references across reimport
- NFR14: Adding a new OTLP instrument must follow existing patterns in `health/metrics.py` with no new infrastructure dependencies

### Operational Readiness

- NFR15: A pre-demo validation procedure must confirm all panels render data after a single pipeline cycle against the docker-compose stack
- NFR16: The complete docker-compose stack including Grafana and Prometheus must reach healthy state within 60 seconds
