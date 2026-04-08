# AIOps Platform Roadmap — Q2-Q4 2026

## Presentation Roadmap Diagram

```mermaid
timeline
    title AIOps Platform Roadmap 2026

    section Q2 — Ship & Prove Value
        Kafka Anomaly Detection : Slack Notification
                                : Kafka Metrics
                                : Private preview with team leads
        Grafana Core KPI Dashboards : SRE triage panels (hero tiles, scope table, timeline)
                                    : Value narrative panels (team-filtered findings, coverage)
        LLM Diagnosis to Prod : Cold-path hypothesis generation goes live

    section Q3 — Telemetry Platform
        LGTM Integration : Establish Telemetry Collection Layer
        Core Service Telemetry : Instrument services to emit into LGTM stack
        Grafana Dashboard Enhancement : New LGTM signal visualizations
        PagerDuty Integration : Lightweight dispatch adapter
        Smartscape Discovery Spike : PoC mapping to topology contract

    section Q4 — Modernization + AI Evolution
        Dynatrace Smartscape Cutover : Replace YAML with dynamic topology discovery
        Agent-to-Agent RCA : Integrate with iO Agent for RCA
                           : Multi-agent diagnosis architecture
        ServiceNow Postmortem : Extends pipeline to Automate Incident Postmortems
```

## AI Evolution Thread

```mermaid
graph LR
    Q2["Q2: Ship LLM to Prod<br/><i>Gather quality data</i>"]
    Q3["Q3: Observe & Collect<br/><i>Focus on telemetry platform</i>"]
    Q4["Q4: Agent-to-Agent RCA<br/><i>Multi-agent architecture</i>"]

    Q2 -->|"signal maturity<br/>data"| Q3
    Q3 -->|"production<br/>evidence"| Q4

    style Q2 fill:#4a90d9,stroke:#2c5f8a,color:#fff
    style Q3 fill:#f5a623,stroke:#c47d0e,color:#fff
    style Q4 fill:#7ed321,stroke:#5a9e18,color:#fff
```

## Quarterly Themes

```mermaid
graph TB
    subgraph Q2["Q2: Ship & Prove Value"]
        direction TB
        A1[Kafka Anomaly Detection<br/>Slack NOTIFY → Prod]
        A2[Grafana Core KPI<br/>Dashboards]
        A3[LLM Diagnosis<br/>Ships to Prod]
    end

    subgraph Q3["Q3: Telemetry Platform + Earned Escalation"]
        direction TB
        B1[LGTM Integration]
        B2[Core Service<br/>Telemetry]
        B3[Grafana Dashboard<br/>Enhancement]
        B4[PagerDuty<br/>Integration]
        B5[Smartscape<br/>Discovery Spike]
    end

    subgraph Q4["Q4: Modernization + AI Evolution"]
        direction TB
        C1[Smartscape Topology<br/>Cutover]
        C2[Agent-to-Agent<br/>RCA Integration]
        C3[ServiceNow Postmortem<br/>Automation]
    end

    A1 -->|"proven signal"| B4
    A3 -->|"quality data"| C2
    B1 -->|"ingestion ready"| B2
    B2 -->|"new signals"| B3
    B5 -->|"mapping validated"| C1

    style Q2 fill:#e8f0fe,stroke:#4a90d9
    style Q3 fill:#fef3e0,stroke:#f5a623
    style Q4 fill:#e8f8e0,stroke:#7ed321
    style C3 stroke-dasharray: 5 5
```

## Key Decisions

- **PagerDuty:** Deferred from Q2 to Q3 — earned after signal maturity proof
- **Smartscape:** De-risked with Q3 discovery spike before Q4 cutover
- **ServiceNow:** Release valve if Q4 squeezed (dashed border) — can slip to Q1
- **AI Thread:** Ship → Observe → Agent-to-Agent (skip incremental improvements)
- **LGTM:** Leverages existing org infrastructure — integrate, not build
- **Dashboard:** Post-gating decisions only, hybrid time windows, team-filterable
