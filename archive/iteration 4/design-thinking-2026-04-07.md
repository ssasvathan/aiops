# Design Thinking Session: AIOps Triage Pipeline Architecture Diagram

**Date:** 2026-04-07
**Facilitator:** Sas
**Design Challenge:** Create architecture diagrams (current state + future state) that communicate the AIOps Triage Pipeline's components, data flow, and interactions to Principal Engineers.

---

## Design Challenge

### Challenge Statement

How do we visually communicate the end-to-end AIOps Triage Pipeline architecture — from telemetry ingestion through AI-powered diagnosis to incident response — in a way that Principal Engineers can quickly grasp the system's operational maturity, architectural boundaries, and evolution path?

### Key Constraints & Context

- **Audience:** Principal Engineers
- **Deliverables:** Two diagrams — Current State and Future State
- **No constraints** on tooling, time, or budget
- **Success Criteria:** AIOps clearly communicates proactive anomaly detection, productivity gains, noise reduction
- **Domain:** Observability with AI

---

## EMPATHIZE: Understanding the Audience

### User Insights

**Audience: Principal Engineers**
- They evaluate whether a system is *operable*, not just clever
- They trace every arrow, look for single points of failure, check async boundaries
- They respect systems that handle edge cases honestly
- They mentally diff current vs future state diagrams — consistent layout makes that easy
- They want to see real tech stack labels (Postgres, S3, Redis, Kafka, LiteLLM) not abstract boxes
- They want actual contract/event names on arrows (CaseHeaderEventV1, TriageExcerptV1)

### Key Observations

- **Use industry-standard terminology**, not internal jargon (e.g., "Alert Qualification & Noise Suppression" not "Gating")
- **Two diagrams with visual anchoring** — same layout, so the delta between current and future state is immediately visible
- **Group by functional layer** (not 9 sequential boxes): Telemetry Sources → Collection & Storage → Analysis & Detection → Decision & Routing → Intelligent Diagnosis → Incident Management
- **Show operational maturity signals**: safety modes (OFF|LOG|MOCK|LIVE), deterministic hot path, durable outbox
- **Diagnosis agent is the "hero moment"** — expand it in future state as a decision flow inset

### Empathy Map

| Dimension | Principal Engineer |
|---|---|
| **SAY** | "Show me the failure modes." "What's the blast radius?" "How does this scale?" |
| **THINK** | "Is this over-engineered or under-engineered?" "Would I want to be on-call for this?" |
| **DO** | Trace every arrow. Look for SPOFs. Check if async boundaries are real. Read arrow labels. |
| **FEEL** | Respect for honest edge case handling. Skepticism toward hand-wavy AI claims. |

### Component Naming (Industry-Standard)

**Current State (Production):**

| Internal Name | Industry-Standard Name |
|---|---|
| Evidence | Metric Collection & Ingestion |
| Peak | Threshold Classification |
| Baseline Deviation | Statistical Baseline Analysis (MAD) |
| Topology | Service Topology & Ownership Resolution |
| CaseFile | Incident Case Persistence (S3) |
| Outbox | Durable Event Outbox (Postgres) |
| Gating | Alert Qualification & Noise Suppression |
| Dispatch | Alert Routing & Notification |

**In Dev:**

| Internal Name | Industry-Standard Name |
|---|---|
| Diagnosis | AI-Powered RCA & Summary |

**Future State Only:**

| Internal Name | Industry-Standard Name |
|---|---|
| Linkage | Automated Postmortem & Incident Correlation |

### Diagram Layers

```
Layer 1 (top):     Telemetry Sources (Infrastructure Metrics — Kafka current source)
Layer 2:           Collection & Storage
Layer 3:           Analysis & Detection
Layer 4:           Decision & Routing
Layer 5:           Intelligent Diagnosis
Layer 6 (bottom):  Incident Management
```

---

## DEFINE: Frame the Problem

### Point of View Statement

A Principal Engineer reviewing an AIOps architecture needs to see operability, data flow integrity, and clear architectural boundaries using industry-standard language because they evaluate systems by asking "would I want to be on-call for this?" — and hand-wavy diagrams with internal jargon destroy credibility before the conversation starts.

### How Might We Questions

1. HMW show the deterministic hot path and async diagnosis path as distinct architectural boundaries so a PE immediately sees that AI never blocks alerting?
2. HMW use consistent visual layout across both diagrams so PEs can instantly spot the delta between current and future state?
3. HMW represent the diagnosis agent's evolution (simple webhook today → synthesis/confidence/RCA/tool-call flow in future) without overstating current capabilities?
4. HMW show durability guarantees (S3 write-before-publish, hash chains, at-least-once delivery) without cluttering the primary data flow?
5. HMW represent the telemetry source layer as extensible (Infrastructure Metrics) while being honest that only Kafka metrics exist today?
6. HMW label components with enough technical detail (contract names, tech stack) to satisfy PE scrutiny without turning the diagram into a wall of text?
7. HMW visually communicate the noise suppression story — raw metrics in, qualified alerts out — so the value proposition is embedded in the architecture itself?

### Key Insights & Opportunity Areas

| Insight | Opportunity |
|---|---|
| PEs diff current vs future mentally | Visual anchoring — same positions, highlight what changes |
| Hot path / cold path separation is the strongest architectural argument | Make this the primary visual boundary in the diagram |
| "Noise suppression" resonates emotionally with PEs | The funnel from many metrics to few qualified alerts should be visually obvious |
| The diagnosis agent is the differentiator | Give it a zoomed inset in future state, not just a box |
| PEs read arrow labels, not just box labels | Invest in naming the data contracts on every flow arrow |
| All 8 prod stages are real and running | Current state diagram is a credibility artifact — accuracy is everything |

---

## IDEATE: Generate Solutions

### Selected Methods

- SCAMPER Design, Analogous Inspiration, Brainstorming

### Generated Ideas

30 ideas generated across layout/structure, rendering/tooling, annotation/detail, and narrative categories.

### Top Concept: C4 Container Diagram

**Selected: Concept C — C4 Model Level 2 (Container Diagram)**

Rationale:
- Industry-standard notation PEs already know — zero learning curve
- Containers map naturally to the pipeline components
- Relationships labeled with protocol and contract names
- Separate current/future state views with consistent layout
- Clean, professional, no visual gimmicks — lets the architecture speak

Enhanced with elements from other concepts:
- Solid vs dashed lines for deterministic vs async flows
- PROD/DEV status annotations on containers
- Contract names on relationship arrows
- Functional layer grouping via C4 boundary boxes
- Diagnosis agent expanded as sub-diagram in future state

---

## PROTOTYPE: Make Ideas Tangible

### Prototype Approach

- **Format:** Mermaid C4 Container diagrams — version-controllable, renders in GitHub
- **Artifact:** `artifact/architecture-diagram-prototype.md`
- **Two diagrams:** Current State and Future State with consistent spatial layout
- **Testing goal:** Validate component grouping, flow clarity, and detail level for PE audience

### Prototype Description

Both diagrams use C4 Container notation with:
- **Container_Boundary** boxes for runtime processes (Hot Path, Outbox Publisher, Cold Path, Postmortem)
- **ContainerDb/ContainerQueue** for stateful infrastructure (S3, PostgreSQL, Redis, Kafka)
- **System_Ext** for external integrations (Prometheus, PagerDuty, Slack, ServiceNow)
- **Rel** arrows labeled with contract names and protocols
- **[DEV] annotation** on components not yet in production

Current state shows 8 production containers + 1 dev container across 3 runtime processes.
Future state expands the diagnosis agent into a 4-step flow (Summarize → Confidence → RCA Enhancement → Tool Call) and adds the Automated Postmortem & Incident Correlation boundary.

### Features to Test

1. Is the hot path / cold path boundary visually distinct?
2. Does the 4-step diagnosis flow read correctly?
3. Is arrow label detail right for PEs — too much or too little?
4. Should data infrastructure sit inside or outside the AIOps boundary?
5. Does the current → future delta jump out when comparing diagrams side by side?

---

_Generated using BMAD Creative Intelligence Suite - Design Thinking Workflow_
