---
stepsCompleted: [1, 2, 3]
inputDocuments: []
session_topic: 'AIOps platform roadmap — dashboard KPIs and strategic gap analysis'
session_goals: 'Actionable KPI list for Q2 Grafana dashboards + prioritized roadmap items to fill gaps across Q2-Q4'
selected_approach: 'AI-Recommended Techniques'
techniques_used: ['Morphological Analysis', 'Role Playing', 'Reverse Brainstorming']
ideas_generated: ['KPI-Framework #1-9', 'Roadmap #1-14']
context_file: ''
---

# Brainstorming Session Results

**Facilitator:** Sas
**Date:** 2026-04-07

## Session Overview

**Topic:** AIOps platform roadmap — dashboard KPIs and strategic gap analysis
**Goals:** Actionable KPI list for Q2 Grafana dashboards + prioritized roadmap items to fill gaps across Q2-Q4

### Session Setup

Two brainstorming topics:
- **Topic A:** Core Grafana Dashboard KPIs for Q2 — what metrics should the dashboard surface as aiOps moves from Dev to Private Preview to Prod
- **Topic B:** Roadmap gaps — what's missing from the Q2-Q4 plan given PRD Phase 2/3 items, operational readiness, and platform expansion

**Approach:** AI-Recommended Techniques

## Technique Selection

**Approach:** AI-Recommended Techniques
**Analysis Context:** AIOps platform roadmap with focus on Q2 dashboard KPIs and Q2-Q4 gap analysis

**Recommended Techniques:**

- **Morphological Analysis:** Systematically map KPI parameter space (metric type x audience x time horizon) to ensure comprehensive dashboard coverage beyond the 6 existing OTLP instruments
- **Role Playing:** Examine the full roadmap through stakeholder lenses (SRE on-call, VP, PE, ops team) to surface gaps invisible from the builder's perspective
- **Reverse Brainstorming:** Stress-test by engineering failure — "how could this dashboard/roadmap fail?" — to catch blind spots that systematic analysis misses

**AI Rationale:** Strategic planning with a technical platform requires systematic coverage (Morphological) to avoid missing KPI combinations, then perspective diversity (Role Playing) to find roadmap gaps across stakeholder needs, then adversarial thinking (Reverse Brainstorming) to stress-test the plan before committing to it

## Technique Execution Results

### Phase 1: Morphological Analysis — Q2 Grafana Dashboard KPIs

**Interactive Focus:** Systematically explored dashboard KPI space through SRE triage flow, audience needs, and time window design.

**Key Ideas Generated:**

**[KPI-Framework #1]**: Anomaly-First Dashboard Priority
_Concept_: Q2 dashboard leads with "what's happening in Kafka" — active anomalies, severity, affected scopes. AIOps engine health is secondary.
_Novelty_: Resists the builder's instinct to showcase the engine; prioritizes the consumer's need to act.

**[KPI-Framework #2]**: Proven-First, Evaluate-Second Layout
_Concept_: Hero section shows hand-coded detector findings only. Baseline deviation gets a separate evaluation section/tab during private preview.
_Novelty_: Mirrors the two-layer detection architecture in the UI — specific detectors are authoritative, generic detection is advisory.

**[KPI-Framework #3]**: Post-Gating Action View
_Concept_: Dashboard shows only final ActionDecisionV1 outcomes. Gating funnel details belong in the Layer B ops dashboard.
_Novelty_: Prevents the SRE from second-guessing gating logic at 3am. They see decisions, not deliberations.

**[KPI-Framework #4]**: Decision-Only, Trust Dispatch
_Concept_: Dashboard shows action decisions without dispatch delivery status. Slack/PagerDuty delivery failures surface through their own monitoring.
_Novelty_: Keeps the anomaly dashboard focused on "what's happening in Kafka" not "is our notification plumbing working."

**[KPI-Framework #5]**: Team-Scoped Anomaly View
_Concept_: Findings filterable/groupable by owning team from topology enrichment. Team leads can filter to their scopes instantly.
_Novelty_: Transforms a platform-wide anomaly dashboard into a team-relevant triage tool without separate dashboards per team.

**[KPI-Framework #6]**: Hybrid Time Window Split
_Concept_: Hero tiles = last cycle ("now"), scope table = last 1h (recent context), action timeline = 24h (trend). Each panel optimized for the question it answers.
_Novelty_: Prevents the "got the Slack alert but dashboard is empty" gap without cluttering real-time view.

**[KPI-Framework #7]**: Value Demonstration for Private Preview
_Concept_: Dashboard needs a value narrative layer — not just "what's happening" but "what AIOps caught that you wouldn't have seen."
_Novelty_: Same dashboard serves SRE triage AND stakeholder persuasion.

**[KPI-Framework #8]**: Team Lead Value Narrative
_Concept_: Value KPIs filtered by owning team. "For your 30 consumer groups, AIOps detected 12 anomalies this week." Team leads evaluate whether it's worth their attention.
_Novelty_: Transforms generic platform pitch into personalized team-level value demonstration.

**[KPI-Framework #9]**: Complete Q2 Dashboard KPI Summary
_Concept_: Two-tier dashboard — SRE triage panels (5 panels with hybrid time windows) + value narrative panels (4 panels for private preview).
_Novelty_: Single dashboard serves both operational and persuasion purposes.

#### Q2 Dashboard KPI Specification

**SRE Triage Panels (Layer A):**

| Panel | Time Window | KPIs |
|---|---|---|
| Hero Tiles | Last cycle | Active NOTIFY/TICKET/PAGE counts by detector type |
| Scope Table | Last 1h | Scope, detector, action level, owning team, timestamp — filterable |
| Action Timeline | Last 24h | Dispatched actions time-series, stacked by action level |
| Team View | Last 24h | Findings grouped by owning team |
| Top Noisy Scopes | Last 24h | Top-N scopes by finding frequency |

**Value Narrative Panels (Private Preview):**

| Panel | Time Window | KPIs |
|---|---|---|
| Findings for My Team | Weekly/Monthly | Team-filtered finding count and detector breakdown |
| Coverage | Current | Scopes monitored per team |
| Finding-to-Action Ratio | Weekly | Signal quality — how much was actionable vs suppressed |
| Notable Finding Highlight | Manual/curated | Concrete anecdote-ready detection story |

**Parked for Later:**
- Baseline deviation evaluation KPIs (separate tab/dashboard)
- AIOps engine health (Layer B ops dashboard)
- Dispatch delivery confirmation

---

### Phase 2: Role Playing — Roadmap Gap Discovery

**Interactive Focus:** Examined roadmap through three stakeholder personas — SRE Team Lead, Principal Engineer, VP/Director.

**Key Ideas Generated:**

**[Roadmap #1]**: Defer PagerDuty to Post-Maturity
_Concept_: PagerDuty moves out of Q2. Private preview runs Slack NOTIFY only. PAGE capability earned after signal quality proof.
_Novelty_: Prevents "one bad page kills adoption." Roadmap mirrors the graduated trust model.

**[Roadmap #2]**: Maintenance Window Suppression — Implicit Q2 Requirement
_Concept_: Ships as part of Q2 prod readiness, not a separate roadmap item. Table stakes for production.
_Novelty_: Keeps roadmap strategic rather than cluttered with implementation details.

**[Roadmap #3]**: LGTM Before Service Instrumentation
_Concept_: Q3 dependency: LGTM ingestion first → then service telemetry. Can't collect what you have nowhere to store.
_Novelty_: Makes implicit dependency explicit — prevents parallel work with integration friction.

**[Roadmap #4]**: ServiceNow Linkage Extends Existing Pipeline
_Concept_: Additive to existing contracts and stage architecture. Not greenfield.
_Novelty_: Lower risk than it appears because it follows established pipeline patterns.

**[Roadmap #5]**: Rebalanced Q3/Q4 — Data Layer Then Visualize
_Concept_: Q3 = build ingestion + instrument + enhance dashboards. Q4 = external integrations + modernization. Coherent quarterly themes.
_Novelty_: Grafana enhancement moves to Q3 because the data it needs lands in Q3.

**[Roadmap #6]**: PagerDuty Earned in Q3
_Concept_: Lands Q3 after full quarter of production Slack data. Activation is data-driven, not calendar-driven.
_Novelty_: PagerDuty isn't "delayed" — it's "earned." Better VP story.

**[Roadmap #7]**: PagerDuty as Lightweight Q3 Integration
_Concept_: Dispatch adapter following existing integration mode pattern. Small effort, big milestone optics.
_Novelty_: Pairs with Q3 narrative: proved signal in Q2, now trust it enough to page.

---

### Phase 3: Reverse Brainstorming — Roadmap Stress Test

**Interactive Focus:** Engineered failure scenarios to find blind spots and hidden risks.

**Key Ideas Generated:**

**[Roadmap #8]**: LGTM Leverages Existing Org Infrastructure
_Concept_: Other team already runs LGTM stack. Q3 is integrate, not build. Significantly de-risks Q3.
_Novelty_: Changes effort from infrastructure provisioning to pipeline integration.

**[Roadmap #9]**: Smartscape Mapping Gap — Hidden Complexity
_Concept_: Dynatrace Smartscape doesn't map 1:1 to topology contract. Q4 includes building mapping automation — not just a data source swap.
_Novelty_: What looks like a simple swap is actually a data model translation layer. Riskiest roadmap item.

**[Roadmap #10]**: Smartscape Discovery Spike in Q3
_Concept_: Start mapping proof-of-concept in Q3. Q4 becomes cutover, not discovery + build + cutover. Front-loads uncertainty.
_Novelty_: If mapping gap is worse than expected, find out in Q3 when there's still time to adjust.

**[Roadmap #11]**: Smartscape Over ServiceNow If Q4 Squeezed
_Concept_: ServiceNow is the release valve. Smartscape can't slip because it touches the pipeline foundation.
_Novelty_: Priority decision made calmly now rather than under Q4 pressure.

**[Roadmap #12]**: AI/LLM Evolution — The Missing Thread
_Concept_: System's differentiator is AI-powered diagnosis but roadmap had zero AI improvement items. Every quarter needs an AI thread.
_Novelty_: Maintains the narrative that this is an AI platform getting smarter, not a rules engine with a chatbot.

**[Roadmap #13]**: Agent-to-Agent RCA Integration in Q4
_Concept_: Integrate AIOps pipeline with internal RCA agent for enhanced root cause analysis. Multi-agent architecture replaces single-LLM diagnosis.
_Novelty_: AIOps becomes a producer of structured evidence for downstream AI agents.

**[Roadmap #14]**: Simplified AI Thread — Ship, Observe, Integrate
_Concept_: Q2 ships LLM to prod. Q3 observes. Q4 leapfrogs to agent-to-agent RCA. Skip incremental AI improvements that Q4 replaces.
_Novelty_: Avoids building intermediate improvements made obsolete by multi-agent architecture.

---

## Final Roadmap

### Q2: Ship & Prove Value

| Item | Details |
|---|---|
| Kafka Anomaly Detection → Prod | Slack NOTIFY only. Hand-coded detectors. Private preview with team leads |
| Grafana Core KPI Dashboards | SRE triage panels + value narrative panels (see KPI specification above) |
| LLM Diagnosis Ships to Prod | Cold-path hypothesis generation goes live. Gather quality data during preview |
| _Implicit_ | Maintenance window suppression, environment promotion (dev → prod) |

### Q3: Telemetry Platform + Earned Escalation

| Item | Details |
|---|---|
| LGTM Integration | Connect to existing org Loki/Tempo/Mimir infrastructure |
| Core Service Telemetry Instrumentation | Instrument services to emit into LGTM stack (depends on LGTM) |
| Grafana Dashboard Enhancement | Enhance dashboards with new LGTM signals |
| PagerDuty Integration | Lightweight dispatch adapter. Earned by Q2 signal quality data |
| Smartscape Discovery Spike | PoC: map Smartscape data model to topology contract, identify gaps, prototype translation |

### Q4: Topology Modernization + Integrations + AI Evolution

| Item | Details |
|---|---|
| Dynatrace Smartscape Topology Cutover | Replace YAML with dynamic discovery. Cannot slip |
| Agent-to-Agent RCA Integration | Integrate with internal RCA agent for enhanced diagnosis |
| ServiceNow Postmortem Automation | Extends pipeline Linkage stage. Can slip to Q1 if squeezed |

### Key Decisions

- PagerDuty deferred from Q2 to Q3 — earned after signal maturity proof
- Baseline deviation KPIs parked — separate evaluation dashboard later
- Dashboard shows post-gating decisions only — no engine internals for SREs
- LGTM leverages existing org infrastructure — integrate, not build
- Smartscape de-risked with Q3 spike before Q4 cutover
- ServiceNow is the release valve if Q4 gets tight
- AI thread: ship → observe → agent-to-agent (skip incremental improvements that Q4 replaces)

### AI Evolution Thread

| Quarter | AI Thread | Description |
|---|---|---|
| Q2 | LLM diagnosis ships to prod | Gather real hypothesis quality data during preview |
| Q3 | Observe and collect data | Let the system run while focusing on telemetry platform |
| Q4 | Agent-to-agent RCA integration | AIOps feeds internal RCA agent for enhanced diagnosis |

---

### Creative Facilitation Narrative

This session moved through three distinct phases. Morphological Analysis systematically mapped the Q2 dashboard KPI space, uncovering a clean two-tier design (SRE triage + value narrative) with hybrid time windows. Role Playing through three personas — SRE Team Lead, Principal Engineer, VP — surfaced the PagerDuty timing risk, the Q3 overload, and the missing AI thread. Reverse Brainstorming stress-tested the roadmap and uncovered the Smartscape mapping gap as the highest-risk item, leading to the Q3 discovery spike that de-risks Q4.

The most impactful moment was the SRE Team Lead persona asking about PagerDuty — it immediately shifted PagerDuty from Q2 to Q3 and reframed it as "earned" rather than "scheduled." The second major insight was rebalancing Q3/Q4 by moving Grafana enhancement earlier (it follows the data) and pulling Smartscape discovery into Q3 (front-load uncertainty).
