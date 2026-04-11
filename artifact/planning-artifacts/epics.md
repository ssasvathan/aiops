---
stepsCompleted: ['step-01-validate-prerequisites', 'step-02-design-epics', 'step-03-create-stories', 'step-04-final-validation']
inputDocuments:
  - artifact/planning-artifacts/prd.md
  - artifact/planning-artifacts/architecture.md
  - artifact/planning-artifacts/ux-design-specification.md
---

# aiOps - Epic Breakdown

## Overview

This document provides the complete epic and story breakdown for aiOps, decomposing the requirements from the PRD, UX Design, and Architecture requirements into implementable stories.

## Requirements Inventory

### Functional Requirements

FR1: The pipeline can emit a counter of findings with labels for anomaly family, final action, topic, routing key, and criticality tier after each gating decision
FR2: The pipeline can emit a counter of gating evaluations with labels for gate ID and outcome during rule engine evaluation
FR3: The pipeline can emit a gauge of evidence status with labels for scope, metric key, and status during evidence collection. High cardinality (~hundreds of series across 9 topics) — Grafana queries must handle efficiently
FR4: The pipeline can emit a counter of completed diagnoses with labels for confidence level and fault domain presence after cold-path completion
FR5: The dashboard can display an aggregate health status signal (green/amber/red) across all monitored pipeline components
FR6: The dashboard can display a single hero stat showing total anomalies detected and acted on within a configurable time window
FR7: The dashboard can display a topic health heatmap with one tile per monitored Kafka topic, color-coded by health status
FR8: The dashboard can display a time-series panel showing actual Kafka metrics from Prometheus with the seasonal baseline expected range as visual context
FR9: The dashboard can annotate Prometheus time-series panels with markers indicating when AIOps detected a deviation
FR10: The dashboard can display a breakdown of findings by anomaly family (consumer lag, volume drop, throughput constrained proxy, baseline deviation)
FR11: The dashboard can display a gating intelligence funnel showing total findings detected, findings suppressed by each gate rule, and final dispatched actions
FR12: The dashboard can display an action distribution over time as a stacked time-series showing OBSERVE, NOTIFY, TICKET, and PAGE counts
FR13: The dashboard can show which specific gate rules (AG0-AG6) contributed to suppression with per-gate outcome counts
FR14: The dashboard can display LLM diagnosis engine statistics including invocation count, success rate, and average latency
FR15: The dashboard can display diagnosis quality metrics showing confidence level distribution and fault domain identification rate
FR16: The dashboard can provide a drill-down view for a specific topic accessible from the main dashboard heatmap
FR17: The drill-down dashboard can display per-topic Prometheus metrics with a tighter time window than the main dashboard
FR18: The drill-down dashboard can display evidence status per metric for a scope showing PRESENT, UNKNOWN, ABSENT, and STALE states
FR19: The drill-down dashboard can display findings filtered by topic with action decision and gate rationale
FR20: The drill-down dashboard can filter by topic using a Grafana variable selector
FR21: The drill-down dashboard can trace a specific finding to its full action decision path including gate rule IDs, environment cap, and final action
FR22: The dashboard can display a capability stack showing each pipeline stage with live status and last-cycle latency
FR23: The dashboard can display pipeline throughput metrics including scopes evaluated and deviations detected per cycle
FR24: The dashboard can display outbox health status
FR25: The docker-compose stack can run a Grafana instance with auto-provisioned data sources and dashboards
FR26: The docker-compose stack can run Prometheus configured to scrape the pipeline's metrics endpoint with explicit retention settings sufficient for 7-day time windows
FR27: Dashboard definitions can be stored as JSON files in the repository and auto-loaded by Grafana on startup
FR28: The Grafana instance can verify connectivity to its configured Prometheus data source on startup
FR29: The main dashboard can enforce an above-the-fold / below-the-fold visual hierarchy separating stakeholder narrative from operational detail
FR30: The main dashboard can present above-the-fold panels in a fixed visual sequence: health banner, hero stat, topic heatmap, baseline deviation overlay
FR31: The main dashboard can link to the drill-down dashboard from heatmap tiles
FR32: The dashboard can display data across selectable time windows (1h, 24h, 7d, 30d) via a Grafana time picker
FR33: The dashboard can apply consistent color semantics across all panels (green=healthy/present, amber=warning/stale, red=critical/unknown)
FR34: The dashboard can be viewed in a presentation-friendly kiosk mode optimized for screen sharing or projector display

### NonFunctional Requirements

NFR1: All dashboard panels must render within 5 seconds on initial load, including Prometheus query execution
NFR2: Switching between time windows (1h/24h/7d/30d) must re-render all panels within 5 seconds
NFR3: Navigating from main dashboard to drill-down dashboard via heatmap link must complete within 3 seconds
NFR4: Prometheus queries for 7-day range windows across all instruments must complete within 10 seconds. Production 30-day range query performance to be tuned post-MVP when real data volumes are known
NFR5: All dashboard panels must display data (no "no data" or error states) when the pipeline has completed at least one cycle within the selected time window
NFR6: Grafana must start with all dashboards and data sources provisioned without manual configuration steps
NFR7: Docker-compose Prometheus must retain metric data for a minimum of 7 days for demo purposes. Production uses existing Prometheus infrastructure with 30-day retention
NFR8: The pipeline's OTLP instruments must emit metrics within the same cycle as the triggering event — no deferred or batched emission that would create data gaps during demo. Prometheus scrape interval must be shorter than cycle interval
NFR9: Dashboard panels must display meaningful zero-state representations when a metric has no occurrences (e.g., zero PAGE actions in dev), rather than error or empty states
NFR10: Dashboard data may lag up to 5 minutes behind the most recent pipeline cycle — near-real-time is not required
NFR11: Prometheus scrape_interval must be set to 15s or less
NFR12: Dashboard JSON files must be the single source of truth — any Grafana UI changes must be exportable back to JSON without manual reconstruction
NFR13: Dashboard JSON exports must preserve panel IDs and inter-dashboard link references across reimport
NFR14: Adding a new OTLP instrument must follow existing patterns in health/metrics.py with no new infrastructure dependencies
NFR15: A pre-demo validation procedure must confirm all panels render data after a single pipeline cycle against the docker-compose stack
NFR16: The complete docker-compose stack including Grafana and Prometheus must reach healthy state within 60 seconds

### Additional Requirements

- No starter template — brownfield project extends existing codebase with established patterns (72 rules)
- Grafana OSS 12.4.2 pinned in docker-compose image tag (`grafana/grafana-oss:12.4.2`)
- `topic` label added to all 4 OTLP instruments for drill-down filtering consistency; verify availability at each emission point and add propagation work if needed
- Prometheus scrape_interval: 15s, retention: 15d in docker-compose
- Evidence gauge: full label granularity, query-side PromQL aggregation in Grafana; define reset-and-set vs. incremental lifecycle pattern
- Dashboard JSON lifecycle: hybrid UI-first design → export → hand-maintain JSON as source of truth
- Dashboard UID stability: hardcoded stable UIDs (`aiops-main`, `aiops-drilldown`) that survive re-provisioning and re-export
- Muted color palette enforcement via grep validation — approves muted hex values, rejects Grafana default palette colors
- Zero-state pattern: `or vector(0)` for counters/gauges where zero is meaningful; Grafana `noDataMessage` for panels where absence means "pipeline hasn't run"
- Inter-dashboard navigation: data links on heatmap tiles (`var-topic=${__field.labels.topic}`) + dashboard header link fallback
- Pre-demo validation: scripted Grafana API check (panel returns at least one non-null data point) + manual 60-second visual walkthrough
- Panel IDs: 1-99 for main dashboard, 100-199 for drill-down dashboard
- OTLP naming convention: dotted in Python (`aiops.findings.total`), underscored in PromQL (`aiops_findings_total`)
- Label values: uppercase matching Python contract enums (`BASELINE_DEVIATION`, `PRESENT`, `OBSERVE`, `NOTIFY`, `TICKET`, `PAGE`)
- PromQL aggregation style: `sum by(label) (metric)`, never `sum(metric) by(label)`
- Counter query conventions: `increase(metric[$__range])` for stat panels, `rate(metric[$__rate_interval])` for time-series panels
- New Prometheus scrape job: `aiops-pipeline` targeting `app:8080` at 15s interval
- Grafana configuration via `GF_` environment variables in docker-compose, no separate `grafana.ini`
- Volume mounts: `./grafana/provisioning:/etc/grafana/provisioning`, `./grafana/dashboards:/var/lib/grafana/dashboards`
- Test patterns: unit tests for OTLP instruments in `tests/unit/health/test_metrics.py`, integration tests for Grafana validation in `tests/integration/test_dashboard_validation.py`
- Validation scripts: `scripts/validate-dashboards.sh` (Grafana API panel data check), `scripts/validate-colors.sh` (palette grep validation)
- Two parallel implementation tracks converging at dashboard panel creation: Track A (Infrastructure), Track B (Instrumentation)

### UX Design Requirements

UX-DR1: Implement muted professional color palette — 6 semantic color tokens with specific hex overrides replacing Grafana defaults: semantic-green `#6BAD64`, semantic-amber `#E8913A`, semantic-red `#D94452`, semantic-grey `#7A7A7A`, accent-blue `#4F87DB`, band-fill `#4F87DB` at 12% opacity
UX-DR2: Implement editorial typography system with minimum sizes — hero values 56px+, primary stat values 40px+, secondary stat values 28px+, panel titles 16px, supporting labels 14px, table body 14px
UX-DR3: Implement "The Newspaper" (Direction C) hybrid editorial layout — hero banner (rows 0-4, 24 cols), P&L stat (rows 5-7, 24 cols), topic heatmap (rows 8-13, 24 cols), fold separator (row 14), baseline overlay (rows 15-22, 24 cols), section separator (row 23), gating funnel (rows 24-29, 24 cols), action distribution + anomaly breakdown (rows 30-34, 12 cols each), capability stack + diagnosis stats (rows 36-40, 12 cols each), pipeline throughput + outbox health (rows 41-44, 12 cols each)
UX-DR4: Implement transparent panel backgrounds — no borders, no cards, no shadows; dark dashboard background (`#181b1f`) serves as visual separator between panels, creating magazine-style editorial spacing
UX-DR5: Implement three zero-state patterns — celebrated zeros displayed in semantic-green with positive framing ("0 false PAGEs this week"), legitimate zeros in semantic-grey with neutral framing ("No diagnoses this period"), no-data states with overridden `noDataMessage` in semantic-grey ("Awaiting data")
UX-DR6: Implement drill-down dashboard layout — topic variable selector (row 0), topic health stat (8 cols) + evidence status row (16 cols) at rows 1-4, per-topic time series (24 cols, rows 5-12), findings table (24 cols, rows 13-18), diagnosis stats (12 cols) + action rationale (12 cols) at rows 19-23
UX-DR7: Implement hero banner as stat panel — color mode: background (entire panel turns green/amber/red), sparkline disabled, threshold mapping 0=green (HEALTHY), 1=amber (DEGRADED), 2=red (UNAVAILABLE), text size extra-large 56px+
UX-DR8: Implement baseline deviation overlay as time series panel — actual value line in accent-blue, expected-range upper/lower bounds as transparent lines with band-fill between at 12% opacity, detection event annotations as vertical markers in semantic-amber
UX-DR9: Implement topic health heatmap — semantic color scheme (green→amber→red using muted tokens), cell labels with topic names + health status, data links to drill-down with `?var-topic=${__data.fields.topic}&${__url_time_range}` preserving temporal context
UX-DR10: Implement gating intelligence funnel as horizontal bar gauge — gradient from accent-blue (detected) through semantic-grey (suppressed) to semantic-green (dispatched), text mode showing gate rule name and count for each bar
UX-DR11: Implement evidence status row on drill-down as stat panel grid — horizontal arrangement, value mapping PRESENT=0 (green), STALE=1 (amber), UNKNOWN=2 (grey), ABSENT=3 (red), color mode: background, ALL CAPS status label as primary value
UX-DR12: Implement panel descriptions on every panel — one-sentence explanation visible on hover serving as in-dashboard documentation for maintainers and tooltip for unfamiliar viewers
UX-DR13: Implement kiosk mode support — dashboard viewable without Grafana chrome via `?kiosk` URL parameter for demo presentation; standard mode (with variable selector) for SRE daily triage on drill-down
UX-DR14: Implement WCAG AA compliance through design foundation — all foreground/background color combinations exceeding 4.5:1 contrast ratio, text labels accompanying all color-coded indicators (never color-only), keyboard navigation via Grafana native support
UX-DR15: Implement pre-demo visual validation — 720p readability check (1280x720), 1080p readability check (1920x1080), color semantics consistency scan, zero-state display verification, data link navigation test, time window re-render test, kiosk mode walkthrough, back navigation test

### FR Coverage Map

FR1: Epic 1 - Findings counter with business labels
FR2: Epic 1 - Gating evaluations counter
FR3: Epic 1 - Evidence status gauge
FR4: Epic 1 - Diagnosis completed counter
FR5: Epic 2 - Aggregate health status signal
FR6: Epic 2 - Hero stat (anomalies detected & acted on)
FR7: Epic 2 - Topic health heatmap
FR8: Epic 2 - Baseline deviation overlay with expected range
FR9: Epic 2 - Detection event annotations
FR10: Epic 3 - Anomaly family breakdown
FR11: Epic 3 - Gating intelligence funnel
FR12: Epic 3 - Action distribution over time
FR13: Epic 3 - Per-gate suppression counts
FR14: Epic 3 - Diagnosis engine statistics
FR15: Epic 3 - Diagnosis quality metrics
FR16: Epic 4 - Drill-down view from heatmap
FR17: Epic 4 - Per-topic Prometheus metrics
FR18: Epic 4 - Evidence status per metric
FR19: Epic 4 - Findings filtered by topic
FR20: Epic 4 - Topic variable selector
FR21: Epic 4 - Full action decision path tracing
FR22: Epic 3 - Capability stack with live status
FR23: Epic 3 - Pipeline throughput metrics
FR24: Epic 3 - Outbox health status
FR25: Epic 1 - Grafana in docker-compose with auto-provisioning
FR26: Epic 1 - Prometheus scrape config for pipeline
FR27: Epic 1 - Dashboard JSON files auto-loaded
FR28: Epic 1 - Grafana-Prometheus connectivity verification
FR29: Epic 2 - Above/below fold visual hierarchy
FR30: Epic 2 - Fixed above-the-fold panel sequence
FR31: Epic 4 - Heatmap-to-drill-down navigation links
FR32: Epic 5 - Selectable time windows via Grafana time picker
FR33: Epic 2 - Consistent color semantics across all panels
FR34: Epic 5 - Kiosk mode for demo presentation

## Epic List

### Epic 1: Pipeline Intelligence Foundation
The pipeline emits business-level intelligence metrics (findings, gating evaluations, evidence status, diagnosis completions) with rich labels, and the observability infrastructure (Grafana + Prometheus) is running with data flowing end-to-end from pipeline to dashboard.
**FRs covered:** FR1, FR2, FR3, FR4, FR25, FR26, FR27, FR28

## Epic 1: Pipeline Intelligence Foundation

The pipeline emits business-level intelligence metrics with rich labels, and the observability infrastructure (Grafana + Prometheus) is running with data flowing end-to-end from pipeline to dashboard.

### Story 1.1: Grafana & Prometheus Observability Infrastructure

As a platform engineer,
I want Grafana and Prometheus configured in the docker-compose stack with auto-provisioned data sources and empty dashboard shells,
So that the observability infrastructure is ready to visualize pipeline intelligence metrics as soon as instruments emit data.

**Acceptance Criteria:**

**Given** the docker-compose stack is started
**When** the Grafana service initializes
**Then** Grafana OSS 12.4.2 (`grafana/grafana-oss:12.4.2`) is running with anonymous auth enabled via `GF_` environment variables
**And** volume mounts map `./grafana/provisioning:/etc/grafana/provisioning` and `./grafana/dashboards:/var/lib/grafana/dashboards`

**Given** Grafana starts with provisioning configuration
**When** the datasource provisioning config (`grafana/provisioning/datasources/prometheus.yaml`) is loaded
**Then** Prometheus is auto-configured as the default data source pointing to `http://prometheus:9090`
**And** the Grafana instance can verify connectivity to Prometheus on startup (FR28)

**Given** Grafana starts with dashboard provisioning configuration
**When** the dashboard provisioning config (`grafana/provisioning/dashboards/dashboards.yaml`) is loaded
**Then** two empty dashboard JSON shells are auto-loaded: `grafana/dashboards/aiops-main.json` (UID: `aiops-main`) and `grafana/dashboards/aiops-drilldown.json` (UID: `aiops-drilldown`)
**And** dashboard UIDs are hardcoded constants that survive re-provisioning

**Given** the Prometheus service is running in docker-compose
**When** the scrape configuration is loaded
**Then** a scrape job `aiops-pipeline` targets `app:8080` with `scrape_interval: 15s`
**And** Prometheus retention is set to 15d (NFR7)

**Given** the full docker-compose stack is started (including Grafana and Prometheus)
**When** all services reach healthy state
**Then** the stack is healthy within 60 seconds (NFR16)

### Story 1.2: Findings & Gating OTLP Instruments

As a platform engineer,
I want the pipeline to emit OTLP counters for findings and gating evaluations with business-level labels,
So that Prometheus captures how many anomalies are detected, what actions are taken, and which gate rules evaluate each finding.

**Acceptance Criteria:**

**Given** the pipeline processes an anomaly through gating and dispatch
**When** an action decision is made (post-ActionDecisionV1)
**Then** the `aiops.findings.total` counter increments by 1 with labels: `anomaly_family`, `final_action`, `topic`, `routing_key`, `criticality_tier`
**And** label values use uppercase matching Python contract enums (e.g., `BASELINE_DEVIATION`, `NOTIFY`)
**And** the instrument is defined in `health/metrics.py` using `create_counter`

**Given** the rule engine evaluates a gate rule
**When** a gating evaluation completes
**Then** the `aiops.gating.evaluations_total` counter increments by 1 with labels: `gate_id`, `outcome`, `topic`
**And** the `topic` label is available at the emission point in `pipeline/stages/gating.py`
**And** the instrument is defined in `health/metrics.py` using `create_counter`

**Given** both instruments are defined
**When** metrics are emitted during a pipeline cycle
**Then** metrics are emitted within the same cycle as the triggering event — no deferred or batched emission (NFR8)
**And** the instruments follow existing patterns in `health/metrics.py` (NFR14)

**Given** the new instruments are defined
**When** unit tests in `tests/unit/health/test_metrics.py` are executed
**Then** each instrument emits the expected metric name and label set
**And** tests assert on metric name + label set, not raw string output

### Story 1.3: Evidence & Diagnosis OTLP Instruments

As a platform engineer,
I want the pipeline to emit an evidence status gauge and a diagnosis completion counter with business-level labels,
So that Prometheus captures the real-time evidence state per metric and tracks LLM diagnosis completions with confidence and fault domain data.

**Acceptance Criteria:**

**Given** the pipeline collects evidence during the evidence stage
**When** evidence status is determined for a metric
**Then** the `aiops.evidence.status` gauge is emitted with labels: `scope`, `metric_key`, `status`, `topic`
**And** status values are uppercase: `PRESENT`, `UNKNOWN`, `ABSENT`, `STALE`
**And** the instrument is defined in `health/metrics.py` using `create_up_down_counter` per project conventions
**And** the evidence gauge lifecycle (reset-and-set vs. incremental) is defined and documented

**Given** the evidence gauge has high cardinality (~hundreds of series across 9 topics)
**When** metrics are emitted
**Then** the full label granularity is preserved for query-side PromQL aggregation in Grafana (FR3 cardinality note)

**Given** the diagnosis cold-path completes for an anomaly
**When** a `DiagnosisResult` is produced
**Then** the `aiops.diagnosis.completed_total` counter increments by 1 with labels: `confidence`, `fault_domain_present`, `topic`
**And** the `topic` label is available at the emission point; if not naturally available, the story includes propagation work to thread it through

**Given** both instruments are defined
**When** unit tests in `tests/unit/health/test_metrics.py` are executed
**Then** each instrument emits the expected metric name and label set
**And** the evidence gauge test validates the correct label cardinality pattern
**And** both instruments follow existing patterns in `health/metrics.py` (NFR14)

### Epic 2: Stakeholder Narrative Dashboard (Above-the-Fold)
VP and Platform Director see platform health and AI intelligence at a glance — the "fund us" above-the-fold story. Hero banner communicates health in 3 seconds, P&L stat quantifies value, topic heatmap shows coverage, and baseline deviation overlay proves the AI understands "normal."
**FRs covered:** FR5, FR6, FR7, FR8, FR9, FR29, FR30, FR33

## Epic 2: Stakeholder Narrative Dashboard (Above-the-Fold)

VP and Platform Director see platform health and AI intelligence at a glance — the "fund us" above-the-fold story.

### Story 2.1: Hero Banner & P&L Stat Panels

As a VP or executive stakeholder,
I want the dashboard to show an aggregate health signal and a total anomalies-acted-on stat as the first things visible on the main dashboard,
So that I can confirm the platform is alive and valuable in a single 3-second glance.

**Acceptance Criteria:**

**Given** the main dashboard (`aiops-main.json`) is opened
**When** the hero banner panel renders at rows 0-4 (24 cols, panel ID range 1-99)
**Then** a stat panel displays aggregate health status with color mode: background (entire panel turns green/amber/red)
**And** threshold mapping is 0=green (HEALTHY), 1=amber (DEGRADED), 2=red (UNAVAILABLE)
**And** sparkline is disabled for a clean, decisive signal
**And** text size is extra-large (56px+) for projector readability (UX-DR7)

**Given** the main dashboard is opened
**When** the P&L stat panel renders at rows 5-7 (24 cols)
**Then** a stat panel displays total anomalies detected and acted on within the dashboard time window
**And** the query uses `increase(aiops_findings_total[$__range])` for human-readable totals
**And** sparkline is enabled to show trend direction

**Given** both panels are configured
**When** the dashboard JSON is inspected
**Then** all colors use the muted professional palette: semantic-green `#6BAD64`, semantic-amber `#E8913A`, semantic-red `#D94452` (UX-DR1)
**And** panel backgrounds are transparent — no borders, no cards, no shadows (UX-DR4)
**And** both panels have a one-sentence description field visible on hover (UX-DR12)
**And** the above-the-fold / below-the-fold visual hierarchy is established with the Newspaper layout (FR29, FR30)

**Given** the pipeline has completed at least one cycle
**When** the panels render
**Then** both panels display data within 5 seconds (NFR1) with no "No data" error states (NFR5)
**And** zero-state values display meaningfully — celebrated zeros in semantic-green, neutral zeros in semantic-grey (UX-DR5)

**Given** the panels use color as a status indicator
**When** accessibility is evaluated
**Then** text labels accompany all color-coded indicators (never color-only) meeting WCAG AA (UX-DR14)

### Story 2.2: Topic Health Heatmap

As a Platform Senior Director,
I want a topic health heatmap showing one tile per monitored Kafka topic with color-coded health status,
So that I can see at a glance that all critical topics are covered and identify any topics needing attention.

**Acceptance Criteria:**

**Given** the main dashboard is opened
**When** the topic health heatmap panel renders at rows 8-13 (24 cols)
**Then** one tile is displayed per monitored Kafka topic
**And** tiles are color-coded using the semantic color scheme: green (healthy) → amber (warning) → red (critical) using muted palette tokens (UX-DR9)
**And** cell labels display topic name and health status text

**Given** a heatmap tile is hovered
**When** the user sees the tooltip
**Then** the tooltip shows topic name, health status, and last-updated timestamp
**And** the cursor changes to pointer indicating the tile is clickable

**Given** a heatmap tile is clicked
**When** the data link activates
**Then** the drill-down dashboard opens with the topic pre-selected via `?var-topic=${__data.fields.topic}&${__url_time_range}` (UX-DR9)
**And** the data link targets the stable UID `aiops-drilldown`
**And** the current time range is preserved across navigation

**Given** the heatmap panel is configured
**When** the dashboard JSON is inspected
**Then** the panel uses transparent background (UX-DR4)
**And** a one-sentence panel description is set (UX-DR12)
**And** the panel ID is within the 1-99 range for the main dashboard
**And** tile label font size is 14px+ for readability

### Story 2.3: Baseline Deviation Overlay with Detection Annotations

As a stakeholder viewing the dashboard,
I want a time-series panel showing actual Kafka metrics with a shaded expected-range band and detection event markers,
So that I can instantly see that the AI understands what "normal" looks like and when it detected a deviation.

**Acceptance Criteria:**

**Given** the main dashboard is opened
**When** the fold separator renders at row 14 (24 cols)
**Then** a visual spacer row separates above-the-fold from below-the-fold content (FR29)

**Given** the main dashboard is scrolled past the fold
**When** the baseline deviation overlay panel renders at rows 15-22 (24 cols)
**Then** a time-series panel displays the actual metric value as a solid line in accent-blue (`#4F87DB`)
**And** expected-range upper and lower bounds display as transparent lines with band-fill between at 12% opacity (`#4F87DB` at 12%) (UX-DR8)
**And** the shaded band is visually distinct from the actual-value line, creating the "it knows normal" moment

**Given** AIOps detected a deviation within the time window
**When** detection events are annotated on the time-series
**Then** vertical markers appear in semantic-amber (`#E8913A`) at the timestamps where deviations were detected (FR9, UX-DR8)

**Given** the panel is configured
**When** the dashboard JSON is inspected
**Then** the panel uses transparent background (UX-DR4)
**And** a one-sentence panel description is set explaining the baseline concept (UX-DR12)
**And** the PromQL query uses `rate(metric[$__rate_interval])` for time-series display
**And** the panel ID is within the 1-99 range

**Given** the pipeline has completed at least one cycle
**When** the panel renders
**Then** data displays within 5 seconds (NFR1) with no "No data" error states (NFR5)
**And** the "no data" message is overridden to "Awaiting data" in semantic-grey if no data exists (UX-DR5)

### Epic 3: Noise Suppression & Operational Credibility (Below-the-Fold)
SRE Director sees noise prevention proof — the gating funnel shows detected-to-dispatched ratio with named gate rules. Below-the-fold panels prove every pipeline layer is operational with live latency, diagnosis stats, throughput, and anomaly breakdowns.
**FRs covered:** FR10, FR11, FR12, FR13, FR14, FR15, FR22, FR23, FR24

## Epic 3: Noise Suppression & Operational Credibility (Below-the-Fold)

SRE Director sees noise prevention proof and operational depth — the "trust us" below-the-fold credibility.

### Story 3.1: Gating Intelligence Funnel & Per-Gate Suppression

As an SRE Director,
I want a gating intelligence funnel showing how many findings were detected, how many were suppressed by each named gate rule, and how many were dispatched,
So that I can see at a glance that the platform prevents noise rather than creates it.

**Acceptance Criteria:**

**Given** the main dashboard is scrolled below the fold
**When** the section separator renders at row 23 (24 cols)
**Then** a visual spacer separates the baseline overlay zone from the credibility zone

**Given** the main dashboard is scrolled to the credibility zone
**When** the gating intelligence funnel panel renders at rows 24-29 (24 cols)
**Then** a horizontal bar gauge displays the funnel stages: Detected (total), Suppressed by AG1, Suppressed by AG2, Suppressed by AG3-AG6, Dispatched (FR11)
**And** the gradient runs from accent-blue `#4F87DB` (detected) through semantic-grey `#7A7A7A` (suppressed) to semantic-green `#6BAD64` (dispatched) (UX-DR10)
**And** text mode shows gate rule name and count for each bar
**And** the query uses `increase(aiops_gating_evaluations_total[$__range])` with `sum by(gate_id, outcome)` aggregation

**Given** the funnel panel is rendered
**When** per-gate outcome counts are displayed
**Then** each specific gate rule (AG0-AG6) shows its individual suppression count with the named gate ID visible (FR13)
**And** the suppression ratio (detected vs. dispatched) is the visual focal point

**Given** all findings were dispatched (zero suppressions)
**When** the funnel renders
**Then** zero suppression bars display as celebrated zeros in semantic-green with count "0" visible (UX-DR5)

**Given** the panel is configured
**When** the dashboard JSON is inspected
**Then** the panel uses transparent background, has a one-sentence description (UX-DR12), and panel ID is within 1-99 range

### Story 3.2: Action Distribution & Anomaly Family Breakdown

As an SRE Director,
I want to see the distribution of actions over time and the breakdown of anomaly types,
So that I can confirm the platform maintains a stable, low-noise action profile and understand what types of anomalies the system detects.

**Acceptance Criteria:**

**Given** the main dashboard is scrolled to the credibility zone
**When** the action distribution panel renders at rows 30-34 (12 cols, left)
**Then** a stacked time-series panel displays OBSERVE, NOTIFY, TICKET, and PAGE counts over time (FR12)
**And** each action type uses a consistent color from the muted palette
**And** the query uses `rate(aiops_findings_total[$__rate_interval])` with `sum by(final_action)` aggregation

**Given** no PAGE actions occurred in the time window (expected in dev)
**When** the panel renders
**Then** the PAGE series shows as zero — a celebrated zero-state, not a missing series (UX-DR5, NFR9)

**Given** the main dashboard is scrolled to the credibility zone
**When** the anomaly family breakdown panel renders at rows 30-34 (12 cols, right)
**Then** a bar chart displays findings grouped by anomaly family: consumer lag, volume drop, throughput constrained proxy, baseline deviation (FR10)
**And** bars are horizontal, sorted by value, with semantic color per anomaly family
**And** the query uses `increase(aiops_findings_total[$__range])` with `sum by(anomaly_family)` aggregation

**Given** both panels are configured
**When** the dashboard JSON is inspected
**Then** both panels use transparent backgrounds, have one-sentence descriptions (UX-DR12), and panel IDs are within 1-99 range
**And** both panels render within 5 seconds (NFR1)

### Story 3.3: LLM Diagnosis Engine Statistics

As a stakeholder evaluating AI capabilities,
I want to see LLM diagnosis engine statistics including invocation count, success rate, latency, confidence distribution, and fault domain identification rate,
So that I can confirm the AI-powered diagnosis layer is live, performing well, and producing useful hypotheses.

**Acceptance Criteria:**

**Given** the main dashboard is scrolled to the operational zone
**When** the diagnosis stats panels render at rows 36-40 (12 cols, right — paired with capability stack)
**Then** grouped stat panels display: invocation count, success rate (percentage), and average latency (FR14)
**And** the queries use `increase(aiops_diagnosis_completed_total[$__range])` for counts and appropriate aggregations for rate and latency

**Given** the diagnosis stats panels render
**When** confidence distribution is displayed
**Then** the distribution of confidence levels (from `aiops.diagnosis.completed_total` labels) is visible (FR15)
**And** fault domain identification rate is displayed as a percentage of diagnoses where `fault_domain_present` is true (FR15)

**Given** no diagnoses have been completed in the time window
**When** the panels render
**Then** zero invocations display as a legitimate zero in semantic-grey with "No diagnoses this period" (UX-DR5)

**Given** all panels are configured
**When** the dashboard JSON is inspected
**Then** stat panel values use 28px+ text size for below-the-fold secondary values (UX-DR2)
**And** panels use transparent backgrounds with one-sentence descriptions (UX-DR4, UX-DR12)
**And** panel IDs are within 1-99 range

### Story 3.4: Pipeline Capability Stack, Throughput & Outbox Health

As a Platform Senior Director,
I want to see each pipeline stage with its live status and latency, overall throughput metrics, and outbox health,
So that I can confirm every pipeline layer is operational and the system is processing anomalies at expected volume.

**Acceptance Criteria:**

**Given** the main dashboard is scrolled to the operational zone
**When** the capability stack panel renders at rows 36-40 (12 cols, left — paired with diagnosis stats)
**Then** a table or stat panel row displays each pipeline stage (detection, enrichment, gating, dispatch, LLM diagnosis) with live status and last-cycle latency (FR22)
**And** stage status uses semantic color tokens: green (operational), amber (degraded), red (down)

**Given** the main dashboard is scrolled further
**When** the pipeline throughput panel renders at rows 41-44 (12 cols, left)
**Then** a stat panel displays scopes evaluated and deviations detected per cycle (FR23)
**And** sparkline is enabled to show throughput trend

**Given** the main dashboard is scrolled further
**When** the outbox health panel renders at rows 41-44 (12 cols, right)
**Then** a stat panel displays outbox health status (FR24)
**And** status uses the same three-state health color mapping (green/amber/red)

**Given** all panels are configured
**When** the dashboard JSON is inspected
**Then** panels use 28px+ text size for secondary values (UX-DR2), transparent backgrounds (UX-DR4), one-sentence descriptions (UX-DR12)
**And** panel IDs are within 1-99 range
**And** all panels render within 5 seconds with 7-day queries completing within 10 seconds (NFR1, NFR4)

### Epic 4: SRE Triage Drill-Down
SRE Lead can triage incidents from a single per-topic screen — select a topic, scan evidence status, read action rationale, check diagnosis confidence. One click from the main heatmap delivers full per-topic context.
**FRs covered:** FR16, FR17, FR18, FR19, FR20, FR21, FR31

### Epic 5: Demo-Ready Presentation & Validation
Presenter can deliver a confident, zero-fumble 5-minute stakeholder walkthrough with time window control, kiosk mode for clean presentation, and validated dashboards confirming all panels render data.
**FRs covered:** FR32, FR34

## Epic 4: SRE Triage Drill-Down

SRE Lead can triage incidents from a single per-topic screen — select a topic, scan evidence status, read action rationale, check diagnosis confidence.

### Story 4.1: Drill-Down Dashboard Shell & Topic Variable Filtering

As an SRE Lead,
I want a per-topic drill-down dashboard with a single topic selector that drives all panels and accessible from the main dashboard heatmap,
So that I can instantly focus on a specific topic for triage without manual per-panel filtering.

**Acceptance Criteria:**

**Given** the drill-down dashboard (`aiops-drilldown.json`) is opened
**When** the dashboard loads
**Then** a Grafana template variable `$topic` is displayed as a dropdown selector at the top (row 0) populated with all available topics (FR20)
**And** the default time window is 24h (tighter than main dashboard's 7d)

**Given** the user selects a topic from the variable selector
**When** the selection changes
**Then** every panel on the drill-down updates simultaneously to show data for only the selected topic (FR20)

**Given** the user clicks a heatmap tile on the main dashboard
**When** the data link navigates to the drill-down
**Then** the drill-down opens with the clicked topic pre-selected in `$topic` via URL parameter `?var-topic=${__data.fields.topic}` (FR16, FR31)
**And** navigation completes within 3 seconds (NFR3)
**And** the current time range is preserved via `${__url_time_range}`

**Given** the drill-down dashboard is open
**When** the user wants to return to the main dashboard
**Then** a text panel at the top provides a markdown link "← Back to Overview" targeting UID `aiops-main`
**And** browser back button also restores the main dashboard

**Given** the drill-down dashboard renders
**When** the topic health stat panel renders at rows 1-4 (8 cols, left)
**Then** a stat panel displays the selected topic's health status with color mode: background using semantic tokens

**Given** the drill-down dashboard is configured
**When** the dashboard JSON is inspected
**Then** all panel IDs are within the 100-199 range
**And** the dashboard UID is hardcoded as `aiops-drilldown`

### Story 4.2: Evidence Status & Per-Topic Metrics

As an SRE Lead,
I want to see evidence status per metric as a color-coded traffic light row and per-topic Prometheus metrics on a time-series panel,
So that I can instantly assess what the system can and can't see for this topic and review recent metric behavior.

**Acceptance Criteria:**

**Given** the drill-down dashboard is open with a topic selected
**When** the evidence status row renders at rows 1-4 (16 cols, right)
**Then** a horizontal grid of stat panels displays one panel per evidence metric for the selected topic (FR18)
**And** each panel uses color mode: background with value mapping: PRESENT=0 (green `#6BAD64`), STALE=1 (amber `#E8913A`), UNKNOWN=2 (grey `#7A7A7A`), ABSENT=3 (red `#D94452`) (UX-DR11)
**And** ALL CAPS status label is the primary displayed value
**And** the query filters by `{topic="$topic"}`

**Given** the drill-down dashboard is open with a topic selected
**When** the per-topic time-series panel renders at rows 5-12 (24 cols)
**Then** a time-series panel displays per-topic Prometheus metrics with the drill-down's 24h default time window (FR17)
**And** the query filters by `{topic="$topic"}` using exact match
**And** the time-series line uses accent-blue `#4F87DB`

**Given** the pipeline has not emitted evidence for a metric
**When** the evidence panel renders
**Then** the "no data" message is overridden to "Awaiting data" in semantic-grey (UX-DR5)

**Given** both panels are configured
**When** the dashboard JSON is inspected
**Then** panels use transparent backgrounds, one-sentence descriptions (UX-DR12), and panel IDs within 100-199 range
**And** panels render within 5 seconds (NFR1)

### Story 4.3: Findings Table & Action Decision Tracing

As an SRE Lead,
I want a findings table filtered by topic showing action decisions with gate rationale, and the ability to trace a finding's full action decision path,
So that I can understand exactly why each decision was made and trust the system's reasoning during incident triage.

**Acceptance Criteria:**

**Given** the drill-down dashboard is open with a topic selected
**When** the findings table renders at rows 13-18 (24 cols)
**Then** a table panel displays findings filtered by the selected topic with columns for: anomaly family, action decision, gate rationale, and timestamp (FR19)
**And** the query filters by `{topic="$topic"}`
**And** table supports sorting by column

**Given** a finding is displayed in the table
**When** the action decision path is visible
**Then** the full decision path is traceable: gate rule IDs evaluated, environment cap applied, and final action taken (FR21)
**And** gate rule IDs (AG0-AG6) are shown by name, not as opaque codes

**Given** the drill-down dashboard is open with a topic selected
**When** the diagnosis stats panels render at rows 19-23 (12 cols, left)
**Then** stat panels display per-topic diagnosis statistics: LLM confidence level and fault domain presence
**And** the query filters by `{topic="$topic"}`

**Given** the drill-down dashboard is open with a topic selected
**When** the action rationale panel renders at rows 19-23 (12 cols, right)
**Then** a panel displays action decision rationale for recent findings on the selected topic

**Given** no findings exist for the selected topic in the time window
**When** the table renders
**Then** a meaningful zero-state displays: "No findings this period" in semantic-grey (UX-DR5, NFR9)

**Given** all panels are configured
**When** the dashboard JSON is inspected
**Then** table text uses 14px+ font size (UX-DR2), panels use transparent backgrounds with one-sentence descriptions (UX-DR12)
**And** panel IDs are within 100-199 range
**And** panels render within 5 seconds (NFR1)

## Epic 5: Demo-Ready Presentation & Validation

Presenter can deliver a confident, zero-fumble 5-minute stakeholder walkthrough with time window control, kiosk mode, and validated dashboards.

### Story 5.1: Time Window Presets & Kiosk Mode

As a presenter delivering a stakeholder demo,
I want configurable time window presets and a presentation-friendly kiosk mode,
So that I can control the narrative time context and present without Grafana chrome distracting the audience.

**Acceptance Criteria:**

**Given** the main dashboard is opened
**When** the Grafana time picker is configured
**Then** quick range presets are available for 1h, 6h, 24h, 7d, and 30d (FR32)
**And** the default time window is 7d for the main dashboard
**And** switching between time windows re-renders all panels within 5 seconds (NFR2)

**Given** the drill-down dashboard is opened
**When** the time picker is used
**Then** the same quick range presets are available
**And** the default time window is 24h for the drill-down
**And** time window changes apply to ALL panels simultaneously — no per-panel time overrides

**Given** the presenter appends `?kiosk` to the dashboard URL
**When** kiosk mode activates
**Then** all Grafana navigation chrome is hidden (FR34)
**And** the dashboard fills the full viewport for projector or screen-sharing display (UX-DR13)
**And** scroll and click interactions continue to work normally in kiosk mode

**Given** the SRE Lead uses the drill-down for daily triage
**When** the dashboard is opened in standard mode (no `?kiosk`)
**Then** the Grafana variable selector and time picker are visible and accessible (UX-DR13)

### Story 5.2: Pre-Demo Validation & Color Palette Enforcement

As a presenter preparing for a stakeholder demo,
I want automated validation scripts that confirm all panels render data and all colors use the approved muted palette,
So that I can catch data gaps and visual regressions before the audience sees them.

**Acceptance Criteria:**

**Given** the docker-compose stack is running and the pipeline has completed at least one cycle
**When** `scripts/validate-dashboards.sh` is executed
**Then** the script queries the Grafana API (`/api/ds/query`) for each panel's configured query
**And** the script asserts that every panel returns at least one non-null data point (NFR15)
**And** the script reports pass/fail per panel with clear output identifying any failing panels

**Given** dashboard JSON files exist in `grafana/dashboards/`
**When** `scripts/validate-colors.sh` is executed
**Then** the script greps dashboard JSON for the approved muted palette hex values (`#6BAD64`, `#E8913A`, `#D94452`, `#7A7A7A`, `#4F87DB`)
**And** the script rejects any Grafana default palette hex values (`#73BF69`, `#F2495C`, `#FF9830`, `#8E8E8E`, `#5794F2`)
**And** the script reports pass/fail with any offending color values and their panel locations

**Given** the validation scripts pass
**When** the pre-demo visual validation checklist is followed
**Then** 720p readability (1280x720) confirms all above-the-fold panel titles and values are legible (UX-DR15)
**And** 1080p readability (1920x1080) confirms above-the-fold content fills viewport naturally (UX-DR15)
**And** data link navigation from every heatmap tile opens the correct drill-down topic (UX-DR15)
**And** kiosk mode walkthrough completes without visual issues (UX-DR15)

**Given** the integration test suite runs
**When** `tests/integration/test_dashboard_validation.py` executes
**Then** the test starts the docker-compose stack, runs one pipeline cycle, executes the validation script, and asserts all panels return non-null data
