---
stepsCompleted: [1, 2, 3, 4]
inputDocuments: ['brainstorming-session-2026-04-07-001.md']
session_topic: 'Q1 MVP Stakeholder Dashboard — AIOps Grafana KPI dashboard that tells a compelling story in 60 seconds while showing SRE operational value'
session_goals: 'Panel hierarchy and aha-moment design, map available data to compelling panels, balance stakeholder wow-factor with SRE operational value, identify reusable components for full operational dashboard'
selected_approach: 'AI-Recommended Techniques'
techniques_used: ['Analogical Thinking', 'Role Playing', 'Constraint Mapping']
ideas_generated: ['Dashboard-Exec #1', 'Dashboard-Director #2', 'Dashboard-SREDir #3', 'Dashboard-SRELead #4', 'Dashboard-Zoom #5', 'Dashboard-ATC #6', 'Dashboard-Heatmap #7', 'Dashboard-PnL #8', 'Dashboard-Newspaper #9', 'Dashboard-Weather #10', 'Dashboard-Weather #11', 'Dashboard-Diagnosis #12', 'Dashboard-SRELead #13', 'Dashboard-SRELead #14', 'Dashboard-SRELead #15', 'Dashboard-SREDir #16', 'Dashboard-SREDir #17', 'Dashboard-SREDir #18', 'Dashboard-Director #19', 'Dashboard-Director #20', 'Dashboard-Constraint #21', 'Dashboard-Constraint #22', 'Dashboard-Constraint #23', 'Dashboard-Constraint #24', 'Dashboard-Constraint #25', 'Dashboard-Constraint #26']
context_file: ''
session_active: false
workflow_completed: true
---

# Brainstorming Session Results

**Facilitator:** Sas
**Date:** 2026-04-10

## Session Overview

**Topic:** Q1 MVP Stakeholder Dashboard — AIOps Grafana KPI dashboard that tells a compelling story in 60 seconds while showing SRE operational value
**Goals:** Panel hierarchy and aha-moment design, map available data to compelling panels, balance stakeholder wow-factor with SRE operational value, identify reusable components for full operational dashboard

### Context Guidance

_Building on the April 7th brainstorming session which defined a two-tier dashboard (SRE triage + value narrative) with 5 SRE panels and 4 value narrative panels. The dashboard is now being pulled forward from Q2 to Q1 MVP delivery to showcase AIOps capabilities to stakeholders. Key shift: this is the "fund us, trust us, give us scope" moment._

### Session Setup

**Available Capabilities to Showcase:**
- Hand-coded detectors (specific anomaly detection)
- Generic baseline metrics (seasonal baseline deviation)
- Topology enrichment (team/scope ownership mapping)
- Gating logic (deterministic AG0-AG6 guardrails)
- LLM diagnosis (cold-path hypothesis generation)

**Available Data at Q1 MVP:**
- 3 critical source topics + ~6 core pipeline topics (EDL data movement)
- Kafka metrics + seasonal baseline values

**Key Constraint:** Sas is an engineer on a platform team, needs SRE/operational perspective guidance for dashboard design.

**Input from Previous Session (April 7th):**
- SRE Triage Panels: Hero Tiles, Scope Table, Action Timeline, Team View, Top Noisy Scopes
- Value Narrative Panels: Findings for My Team, Coverage, Finding-to-Action Ratio, Notable Finding Highlight
- Key decisions: post-gating decisions only, no engine internals for SREs, hybrid time windows

## Technique Selection

**Approach:** AI-Recommended Techniques
**Analysis Context:** Q1 MVP Stakeholder Dashboard with focus on visual storytelling, SRE operational credibility, and buildability with early data

**Recommended Techniques:**

- **Analogical Thinking:** Learn from domains that have solved the "glance and understand in seconds" problem — mission control, Bloomberg, hospital monitors. Extract proven visual hierarchy patterns and map them to Grafana panels.
- **Role Playing:** Walk through the dashboard as VP (60 seconds), SRE on-call (3am triage), team lead (weekly review). Design panels from each persona's journey. Directly fills Sas's SRE perspective gap.
- **Constraint Mapping:** Map all real constraints (available OTLP instruments, Q1 data volume, Grafana panel types) and find creative pathways. Prevents designing panels that can't ship.

**AI Rationale:** Previous session defined WHAT metrics belong on the dashboard. This session tackles HOW to present them compellingly. Analogical Thinking provides borrowed design expertise, Role Playing fills the SRE perspective gap, Constraint Mapping keeps the design buildable.

## Technique Execution Results

### Phase 1: Analogical Thinking — "Steal from the Best"

**Interactive Focus:** Explored four analogy domains (ICU patient monitoring, air traffic control, Bloomberg terminal, weather forecast) to extract proven visual hierarchy principles for dashboard design.

**Key Ideas Generated:**

**[Dashboard-Exec #1]**: The 3-Second Confidence Signal
_Concept_: Top-of-dashboard hero banner — single aggregate health status (green/amber/red) across all monitored critical pipelines. Executive sees platform posture before reading a single word.
_Novelty_: Most platform dashboards lead with metrics. This leads with a verdict — like a hospital's "all patients stable" board.

**[Dashboard-Director #2]**: The Capability Layer Stack (Revised)
_Concept_: Visual showing each AIOps capability layer (detection -> enrichment -> gating -> action) with live throughput counts. Director sees detection quality, pipeline throughput, and the full system working — NOT coverage/adoption metrics.
_Novelty_: Pure "is my platform smart and running" view. No growth/onboarding vanity metrics diluting the signal.

**[Dashboard-SREDir #3]**: The Signal Quality Scoreboard
_Concept_: Finding-to-action funnel showing raw detections -> gated decisions -> dispatched actions. SRE Director sees how aggressively the gating logic filters noise BEFORE it reaches their team.
_Novelty_: Flips the narrative from "look how many anomalies we found" to "look how much noise we PREVENTED."

**[Dashboard-SRELead #4]**: The Triage Command Center
_Concept_: Real-time anomaly board — active findings sorted by severity, filterable by owning team, with 1-hour context window. SRE Lead opens dashboard and immediately knows: what, where, whose, how bad.
_Novelty_: The only panel set that's truly "real-time operational." The other persona views are evaluative.

**[Dashboard-Zoom #5]**: The Aggregate-to-Individual Zoom Pattern
_Concept_: Dashboard defaults to AGGREGATE view (all 9 topics rolled up). SRE Lead uses a Grafana variable dropdown to break into INDIVIDUAL topic view. Same panels, different granularity.
_Novelty_: Exec sees "3 anomalies across critical pipelines." SRE Lead clicks one dropdown and sees "consumer-group-lag on payments-topic is spiking." Zero dashboard sprawl.

**[Dashboard-ATC #6]**: Simple Aggregate + Drill-Down Navigation (Revised)
_Concept_: Main dashboard shows aggregate view across all topics. Each panel/tile links to a detail dashboard for individual topic deep-dive. No auto-magic — clean separation between overview and detail.
_Novelty_: Two-layer architecture: "front page" dashboard for all stakeholders, "detail page" dashboard for SRE Leads. Simple to build, simple to navigate.

**[Dashboard-Heatmap #7]**: Topic Health Heatmap
_Concept_: Grid of tiles — one per monitored topic (9 topics). Color = health status (green/amber/red based on active findings). Stakeholder sees entire platform health posture as a visual pattern, not a table of numbers.
_Novelty_: A heatmap is readable at ANY stakeholder level — exec sees "mostly green, one red," SRE Lead sees WHICH tile is red. Same panel, different depth of reading.

**[Dashboard-PnL #8]**: The "P&L Number" for AIOps
_Concept_: Single hero stat — "Anomalies Detected & Acted On: 47 this week across 9 topics." The Bloomberg P&L equivalent. One number that says "the platform is working and delivering value." Below it: sparkline trend showing week-over-week trajectory.
_Novelty_: Execs think in single numbers. This gives them one to remember and quote in meetings.

**[Dashboard-Newspaper #9]**: The Above-the-Fold Principle
_Concept_: Dashboard has a hard "fold" — everything visible without scrolling is the stakeholder story (hero stat, heatmap, capability stack). Everything below the fold is operational context (timelines, tables, trends). Executive never scrolls. SRE Lead scrolls or clicks through.
_Novelty_: Forces ruthless prioritization — if it's not above the fold, it's not the headline.

**[Dashboard-Weather #10]**: Baseline Deviation Overlay — The "Aha" Panel
_Concept_: Time-series panel showing actual Kafka metric (e.g., consumer lag) as a line, with the seasonal baseline expected range as a shaded band behind it. When the line breaks out of the band, the anomaly is VISUALLY self-evident.
_Novelty_: The single most compelling panel for stakeholders. It shows AI in action — "the system KNOWS what normal looks like, and it caught when things went abnormal."

**[Dashboard-Weather #11]**: Multi-Topic Baseline Sparklines
_Concept_: Row of small sparkline panels — one per critical topic — each showing actual-vs-baseline-band. At a glance: which topics are inside expected range, which are deviating.
_Novelty_: Compact enough for above-the-fold. Shows coverage AND detection simultaneously.

**[Dashboard-Diagnosis #12]**: LLM Hypothesis Spotlight
_Concept_: Panel showing the most recent LLM-generated diagnosis for the most critical active anomaly. Verdict, fault_domain, confidence level, and next_checks (recommended follow-up actions).
_Novelty_: The "aha moment" panel. Every other monitoring tool shows graphs. This one shows REASONING.

#### Cross-Domain Design Principles Extracted

| Principle | ICU | ATC | Bloomberg | AIOps Dashboard |
|---|---|---|---|---|
| Instant status | Patient stable/critical | Flight normal/danger | P&L green/red | Hero banner health signal |
| Problems self-surface | Alarming patient jumps out | Descending flight escalates | Big red heatmap square | Topic heatmap color change |
| Detail on demand | Walk up to monitor | Click aircraft | Click position | Grafana drill-down link |
| Aggregate default | "All stable" board | Radar overview | Portfolio summary | 9 topics rolled up |

---

### Phase 2: Role Playing — "Walk the Dashboard"

**Interactive Focus:** Walked through the dashboard as four stakeholder personas grounded in actual pipeline contracts (ActionDecisionV1, TriageExcerptV1, DiagnosisReportV1, BaselineDeviationStageOutput).

**Key Pipeline Data Discovery:**

The AIOps pipeline emits a complete triage story per anomaly:
- **AnomalyFinding**: anomaly_family (CONSUMER_LAG, VOLUME_DROP, THROUGHPUT_CONSTRAINED_PROXY, BASELINE_DEVIATION)
- **ActionDecisionV1**: final_action (OBSERVE/NOTIFY/TICKET/PAGE), gate_rule_ids, env_cap_applied
- **CaseHeaderEventV1**: case_id, topic, anomaly_family, criticality_tier, final_action, routing_key (team ownership)
- **TriageExcerptV1**: topic_role, sustained, peak, evidence_status_map, findings
- **DiagnosisReportV1**: verdict, fault_domain, confidence (LOW/MEDIUM/HIGH), evidence_pack, next_checks

**Persona Mapping:**

| Persona | Question | Time Budget | Dashboard Depth |
|---|---|---|---|
| Executive (VP/SVP) | "Is my investment working?" | 3 seconds | Hero banner only |
| Platform Senior Director | "Is the platform smart and running?" | 30 seconds | Hero + capability stack + throughput |
| SRE Director | "Is this protecting my team from noise?" | 60 seconds | Signal quality funnel + action trends |
| SRE Lead | "What needs my attention RIGHT NOW?" | Stays and works | Triage panels + drill-down detail |

**Key Ideas Generated:**

**[Dashboard-SRELead #13]**: The Scope Detail Drill-Down Dashboard
_Concept_: Linked from the main dashboard heatmap tile. Shows for ONE topic: active findings list (anomaly_family + severity), evidence status map (PRESENT/UNKNOWN/ABSENT/STALE per metric), sustained/peak flags, and the ActionDecisionV1 outcome with gate rule IDs explaining WHY this action level was chosen.
_Novelty_: SRE doesn't just see "lag is high" — they see the full decision rationale. Transparency builds trust.

**[Dashboard-SRELead #14]**: The LLM Diagnosis Card
_Concept_: On the drill-down dashboard, a text panel shows the DiagnosisReportV1: verdict, fault_domain, confidence level, and next_checks. The "doctor's note" next to the patient monitor.
_Novelty_: SRE Lead at 3am gets a starting hypothesis for WHY and WHAT TO CHECK NEXT. No other Kafka monitoring tool does this.

**[Dashboard-SRELead #15]**: The Evidence Status Traffic Light
_Concept_: Simple grid showing each evidence metric for the scope with color-coded status: green (PRESENT), grey (ABSENT), yellow (STALE), red (UNKNOWN). UNKNOWN means "we literally can't see this metric right now."
_Novelty_: Shows what the system CAN'T see, not just what it can. Radical transparency.

**[Dashboard-SREDir #16]**: The Gating Intelligence Funnel
_Concept_: Visual funnel: Total findings detected -> Gated down (by which AG rules) -> Final actions by type. "200 anomalies detected. AG1 suppressed 120 (non-sustained). AG2 capped 50 (peak hours). 30 dispatched as NOTIFY."
_Novelty_: The "signal-to-noise proof" panel. Detected-to-dispatched ratio IS the quality metric.

**[Dashboard-SREDir #17]**: Action Distribution Over Time
_Concept_: Stacked time-series (24h or 7d) showing final_action counts: OBSERVE (grey), NOTIFY (blue), TICKET (amber), PAGE (red). Trend shows signal quality trajectory.
_Novelty_: Downward NOTIFY trend = signal improving. Stable low PAGE = gating working.

**[Dashboard-SREDir #18]**: Anomaly Family Breakdown
_Concept_: Pie or bar chart showing finding distribution by anomaly_family. Shows which detector types are producing the most findings.
_Novelty_: If BASELINE_DEVIATION dominates, generic detection leads. If hand-coded dominates, precision detection leads. Informs investment.

**[Dashboard-Director #19]**: The Live Pipeline Throughput Gauge
_Concept_: Real-time counter showing events processed per cycle — scopes_evaluated, deviations_detected, deviations_suppressed. Shows the engine is RUNNING and PROCESSING.
_Novelty_: The "heartbeat" panel. Numbers ticking = platform alive. Flatline = something's wrong.

**[Dashboard-Director #20]**: The Capability Stack — LIVE
_Concept_: Vertical stack showing each pipeline stage with live status indicators: Evidence (collecting), Peak (classifying), Baseline (deviating), Topology (enriching), Gating (deciding), Dispatch (notifying), LLM Diagnosis (hypothesizing). Each stage shows last-cycle latency.
_Novelty_: The "capability proof" panel. Every layer lit up = full platform investment paying off.

---

### Phase 3: Constraint Mapping — "What Can We Actually Build?"

**Interactive Focus:** Mapped all data source constraints, audited the full OTLP instrument inventory from the codebase, and identified the minimal infrastructure needed to unlock the MVP dashboard.

**OTLP Instrument Audit Results:**

Current instrumentation (30+ instruments across 4 metric modules) is **engine-health-only**. Missing business-level labels:

| Label Needed | Purpose | Exists in Current OTLP? |
|---|---|---|
| `anomaly_family` | Break down by detection type | NO |
| `final_action` | Count OBSERVE/NOTIFY/TICKET/PAGE | NO |
| `routing_key` | Filter by owning team | NO |
| `topic` | Identify affected Kafka topic | NO |
| `criticality_tier` | Show TIER_0 vs TIER_1 vs TIER_2 | NO |

**Key Ideas Generated:**

**[Dashboard-Constraint #21]**: The Four-Instrument MVP Strategy
_Concept_: Add 4 new OTLP instruments to unlock the entire stakeholder dashboard: (1) `aiops.findings.total` with labels `{anomaly_family, final_action, topic, routing_key, criticality_tier}`, (2) `aiops.gating.evaluations_total` with labels `{gate_id, outcome}`, (3) `aiops.evidence.status` gauge with labels `{scope, metric_key, status}`, (4) `aiops.diagnosis.completed_total` with labels `{confidence, fault_domain_present}`.
_Novelty_: 4 counters, minimal code, maximum dashboard unlock. Follows existing metrics pattern exactly.

**[Dashboard-Constraint #22]**: The Baseline Overlay via Prometheus
_Concept_: Instead of querying Redis baseline values, query the SAME Prometheus metrics the evidence stage queries. Grafana already talks to Prometheus. Show raw Kafka metrics directly, use Grafana annotations to mark when AIOps detected a deviation.
_Novelty_: Reuse the data source AIOps ALREADY reads from. Zero new infrastructure. The visual "aha moment" panel uses existing data.

**[Dashboard-Constraint #23]**: The LLM Diagnosis "Teaser" Panel
_Concept_: Can't show full DiagnosisReportV1 text from S3, but CAN show LLM capability proof via existing `aiops.llm.*` instruments: invocations, success rate, avg latency. Panel title: "AI Diagnosis Engine — 142 diagnoses, 94% success, avg 2.3s."
_Novelty_: Proves the AI engine exists and runs without needing verdict text. For MVP, engine liveness > specific verdicts.

**[Dashboard-Constraint #24]**: Structured Logs as Dashboard Data Source (Deferred)
_Concept_: Existing `structlog` pipeline events become dashboard panels for free when Loki lands in Q3 via LGTM integration. No work needed now — design for it later.
_Novelty_: Structured log events already being emitted become queryable dashboard data automatically.

**[Dashboard-Constraint #25]**: Lightweight Diagnosis API Endpoint (Optional Accelerator)
_Concept_: Add a simple HTTP endpoint to existing health server (`health/server.py`) that returns N most recent DiagnosisReportV1 summaries from S3/cache. Grafana queries via Infinity plugin. Gets verdict text on dashboard before Q3 Loki.
_Novelty_: Minimal code on existing infrastructure. One endpoint turns S3 casefiles into dashboard-queryable data.

**[Dashboard-Constraint #26]**: MVP "Diagnosis Exists" Indicator
_Concept_: New OTLP counter `aiops.diagnosis.completed_total{confidence, fault_domain_present}` — confidence level and whether fault domain was identified as labels. Panel shows diagnosis quality stats without needing text.
_Novelty_: Trades "what did the AI say?" for "is the AI producing useful results?" — more compelling for stakeholders at MVP stage.

#### Panel Buildability Matrix

**Buildable TODAY with existing OTLP:**
- Health banner (`aiops.component.health_status`)
- Capability stack (`aiops.pipeline.compute_latency_seconds` by stage)
- LLM engine stats (`aiops.llm.*` instruments)
- Pipeline heartbeat (baseline deviation aggregate counters + `aiops.pipeline.cases_per_interval`)
- Outbox health (`aiops.outbox.*` instruments)

**Buildable with 4 new OTLP instruments:**
- Hero stat, topic heatmap, action distribution, anomaly breakdown, gating funnel, team filtering, evidence traffic light, diagnosis proof

**Deferred to post-MVP (needs Loki/API/sink):**
- Full LLM verdict text, true seasonal baseline band overlay, full structured drill-down data

---

## Idea Organization and Prioritization

### Thematic Organization

#### Theme 1: Dashboard Architecture & Navigation

- **[#9] Above-the-Fold Principle** — Hard fold line separating stakeholder story from operational depth
- **[#5] Aggregate-to-Individual Zoom** — Grafana variable dropdown for topic-level breakout
- **[#6] Simple Aggregate + Drill-Down** — Two-layer: main "front page" + per-topic "detail page"

**Pattern:** Newspaper front page -> article detail page. One main dashboard, one drill-down dashboard, connected by links.

#### Theme 2: Above-the-Fold Panels (The 60-Second Story)

| Panel | Purpose | Data Source |
|---|---|---|
| **[#1] 3-Second Confidence Signal** | Aggregate health banner (green/amber/red) | Existing `aiops.component.health_status` |
| **[#8] The P&L Number** | "47 anomalies detected & acted on this week" | NEW `aiops.findings.total` |
| **[#7] Topic Health Heatmap** | 9-tile grid, color by health | NEW `aiops.findings.total{topic}` |
| **[#22] Baseline Overlay via Prometheus** | Kafka metrics time-series + anomaly annotations | Existing Prometheus + annotation from findings counter |

**This is the "fund us" section.**

#### Theme 3: Below-the-Fold Panels (Operational Credibility)

| Panel | Purpose | Data Source |
|---|---|---|
| **[#16] Gating Intelligence Funnel** | Detected -> gated -> dispatched | NEW `aiops.gating.evaluations_total{gate_id, outcome}` |
| **[#17] Action Distribution Over Time** | OBSERVE/NOTIFY/TICKET/PAGE stacked time-series | NEW `aiops.findings.total{final_action}` |
| **[#18] Anomaly Family Breakdown** | Finding distribution by detector type | NEW `aiops.findings.total{anomaly_family}` |
| **[#20] Capability Stack LIVE** | Pipeline stage latency indicators | Existing `aiops.pipeline.compute_latency_seconds{stage}` |
| **[#26] AI Diagnosis Engine Stats** | "142 diagnoses, 94% success, avg 2.3s" | NEW `aiops.diagnosis.completed_total` + existing `aiops.llm.*` |
| **[#19] Pipeline Throughput Gauge** | Scopes evaluated, deviations detected per cycle | Existing baseline deviation counters |

**This is the "trust us" section.**

#### Theme 4: Drill-Down Dashboard (SRE Lead Workspace)

| Panel | Purpose | Data Source |
|---|---|---|
| **[#13] Scope Detail View** | Active findings with anomaly_family, action decision, gate rationale | NEW `aiops.findings.total` filtered by topic |
| **[#15] Evidence Status Traffic Light** | Per-metric evidence status grid (PRESENT/UNKNOWN/ABSENT/STALE) | NEW `aiops.evidence.status{scope, metric_key, status}` |
| **[#22] Per-Topic Prometheus Metrics** | Topic-specific Kafka metrics with tighter time window | Existing Prometheus |
| **[#23/#26] LLM Diagnosis Teaser** | Confidence + fault domain stats (full text deferred) | NEW `aiops.diagnosis.completed_total{confidence}` |

**This is the "give us scope" section.**

#### Theme 5: New OTLP Instruments Required

| # | Instrument | Type | Labels | Pipeline Location | Unlocks |
|---|---|---|---|---|---|
| 1 | `aiops.findings.total` | Counter | `anomaly_family`, `final_action`, `topic`, `routing_key`, `criticality_tier` | Gating/dispatch stage (post-ActionDecisionV1) | Hero stat, heatmap, action distribution, anomaly breakdown, gating funnel, team filtering |
| 2 | `aiops.gating.evaluations_total` | Counter | `gate_id`, `outcome` | Rule engine evaluation | Gating funnel detail (which AG rules doing the work) |
| 3 | `aiops.evidence.status` | Gauge | `scope`, `metric_key`, `status` | Evidence stage | Evidence traffic light on drill-down |
| 4 | `aiops.diagnosis.completed_total` | Counter | `confidence`, `fault_domain_present` | Diagnosis cold-path completion handler | AI diagnosis engine proof panel |

#### Theme 6: Deferred to Post-MVP

| Item | Dependency | When |
|---|---|---|
| **[#12/#14] Full LLM Diagnosis Verdict Text** | Loki (Q3 LGTM) or API endpoint (#25) | Q3 or earlier with optional API accelerator |
| **[#24] Structured Logs as Dashboard Source** | Loki integration | Q3 — free when Loki lands |
| **[#10] True Seasonal Baseline Band** | Redis-to-Grafana query path | Post-MVP — workaround #22 covers MVP |
| **[#11] Multi-Topic Baseline Sparklines** | Per-topic baseline data in queryable form | Post-MVP |
| **Team-based filtering** | Multiple teams onboarded | Label exists on findings counter — works day one, meaningful post-onboarding |

### Prioritization Results

**P0 — MVP Must-Ship:**

| What | Why |
|---|---|
| 4 new OTLP instruments | Unlocks 80% of dashboard panels. Small code change, huge payoff |
| Above-the-fold panels (hero stat + health banner + heatmap + Prometheus overlay) | The 60-second story IS the MVP |
| Below-the-fold panels (gating funnel + action distribution + capability stack) | Operational credibility for Directors |

**P1 — MVP Should-Ship:**

| What | Why |
|---|---|
| Drill-down dashboard (per-topic Prometheus + evidence status + findings detail) | Proves genuine SRE operational value |
| AI diagnosis engine stats panel | Differentiator proof without needing full text |

**Quick Wins (zero new code):**

| Panel | Existing Data Source |
|---|---|
| Health banner | `aiops.component.health_status` |
| Capability stack | `aiops.pipeline.compute_latency_seconds` by stage |
| LLM engine stats | `aiops.llm.*` instruments |
| Pipeline heartbeat | Baseline deviation counters + `aiops.pipeline.cases_per_interval` |
| Outbox health | `aiops.outbox.*` instruments |

**Breakthrough Concepts:**

| What | Why It Matters |
|---|---|
| Prometheus-as-dashboard-source with anomaly annotations (#22) | Most visually compelling panel uses data that already exists |
| Single findings counter with 5 labels (#21) | One counter powers 6+ panels — maximum leverage |
| Newspaper front page architecture (#9) | Forces ruthless prioritization, prevents Grafana wall-of-graphs |

### Action Plan

**Step 1: Add 4 OTLP instruments**
- Follow existing pattern in `health/metrics.py` and `baseline/metrics.py`
- Wire into gating stage, rule engine, evidence stage, diagnosis handler
- Resource: 1 developer, small effort

**Step 2: Build main dashboard (above + below fold)**
- 4 panels above the fold: health banner, hero stat, heatmap, Prometheus overlay with annotations
- 6 panels below the fold: gating funnel, action distribution, anomaly breakdown, capability stack, AI diagnosis stats, pipeline throughput
- Configure Grafana annotations from `aiops.findings.total` on Prometheus time-series panels

**Step 3: Build drill-down dashboard**
- Per-topic detail linked from heatmap tiles
- Prometheus queries for topic-specific Kafka metrics
- Evidence status gauge panels
- Findings detail filtered by topic

**Step 4: Validate with stakeholder walkthrough**
- VP/Executive: sees dashboard for 3 seconds — can they describe what AIOps does?
- SRE Director: sees gating funnel — do they say "this protects my team"?
- SRE Lead: opens drill-down during simulated incident — is it genuinely useful?
- Platform Director: points at capability stack — can they say "every layer is operational"?

## Session Summary and Insights

**Key Achievements:**
- 26 ideas generated across 3 creative techniques, grounded in actual pipeline contracts and OTLP instrumentation audit
- Dashboard architecture defined: newspaper front page (aggregate) + drill-down detail (per-topic), with hard "above the fold" line
- Complete panel-to-data-source mapping with buildability validation against existing codebase
- Identified that just 4 new OTLP instruments unlock 80% of the dashboard panels
- Discovered that the most compelling visual panel (baseline deviation overlay) uses data that already exists in Prometheus

**Key Decisions:**
- Aggregate view for all stakeholders except SRE Lead (individual topics via drill-down)
- Platform Director does NOT care about capacity/coverage metrics — detection quality, throughput, and capability proof only
- No auto-escalation complexity in MVP — simple drill-down navigation
- 9-topic heatmap works as a clean grid
- LLM verdict text deferred — diagnosis engine STATS prove AI capability for MVP
- Prometheus + annotations replaces true baseline band overlay for MVP

### Creative Facilitation Narrative

This session moved through three distinct phases that built on each other. Analogical Thinking (ICU, air traffic control, Bloomberg, newspaper, weather forecast) gave Sas — a platform engineer without deep SRE experience — a set of proven visual hierarchy principles borrowed from domains where dashboard storytelling is life-or-death. The ICU analogy established the "problems self-surface, detail on demand" principle. The Bloomberg analogy delivered the "P&L number" concept. The newspaper analogy gave us the "above the fold" architecture. The weather forecast analogy unlocked the baseline deviation overlay as the single most compelling "aha" panel.

Role Playing walked through the dashboard as four personas (Executive, Platform Director, SRE Director, SRE Lead) and grounded each panel idea in actual pipeline contracts (ActionDecisionV1, TriageExcerptV1, DiagnosisReportV1), revealing the pipeline's extraordinary richness as a dashboard data source. The most impactful discovery was that the pipeline emits a complete triage STORY per anomaly — not just metrics — with decision rationale, evidence status, team ownership, and LLM-generated hypotheses.

Constraint Mapping delivered the honest reality check. A full audit of the OTLP instrumentation revealed that current metrics are engine-health-only with no business-level labels. But the gap is small: 4 new counters following existing patterns unlock 80% of the dashboard. The single most impactful insight was that `aiops.findings.total` with 5 labels powers 6+ panels — maximum leverage from minimal code. The second breakthrough was reframing the baseline deviation overlay from "needs Redis query infrastructure" to "just query Prometheus directly and annotate with detections" — turning an infrastructure blocker into a zero-new-code visual.
