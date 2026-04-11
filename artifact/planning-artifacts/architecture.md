---
stepsCompleted: [1, 2, 3, 4, 5, 6, 7, 8]
inputDocuments:
  - artifact/planning-artifacts/prd.md
  - artifact/planning-artifacts/ux-design-specification.md
  - artifact/project-context.md
  - docs/index.md
  - docs/project-overview.md
  - docs/architecture.md
  - docs/architecture-patterns.md
  - docs/technology-stack.md
  - docs/api-contracts.md
  - docs/data-models.md
  - docs/contracts.md
  - docs/component-inventory.md
  - docs/runtime-modes.md
  - docs/schema-evolution-strategy.md
workflowType: 'architecture'
project_name: 'aiOps'
user_name: 'Sas'
date: '2026-04-11'
lastStep: 8
status: 'complete'
completedAt: '2026-04-11'
---

# Architecture Decision Document

_This document builds collaboratively through step-by-step discovery. Sections are appended as we work through each architectural decision together._

## Project Context Analysis

### Requirements Overview

**Functional Requirements:**

34 functional requirements across 9 categories:

| Category | FRs | Architectural Implication |
|---|---|---|
| Pipeline Telemetry (FR1-4) | 4 new OTLP instruments | Touches existing pipeline code at 4 specific stages; follows established `health/metrics.py` patterns |
| Platform Health (FR5-7) | Hero banner, P&L stat, heatmap | Grafana stat + heatmap panels querying existing + new Prometheus metrics |
| Detection & Anomaly Visibility (FR8-10) | Baseline overlay, anomaly breakdown | Time-series panels with Prometheus queries; baseline band is visual-only in MVP |
| Noise Suppression (FR11-13) | Gating funnel, action distribution | Queries against `aiops.gating.evaluations_total` and `aiops.findings.total` |
| AI Diagnosis Proof (FR14-15) | Diagnosis stats panels | Queries against `aiops.diagnosis.completed_total` |
| Operational Triage (FR16-21) | Drill-down dashboard | Second Grafana dashboard with template variable filtering |
| Pipeline Visibility (FR22-24) | Capability stack, throughput, outbox | Queries against existing pipeline health metrics |
| Infrastructure (FR25-28) | Grafana + Prometheus in docker-compose | New docker-compose services and provisioning configuration |
| Presentation (FR29-34) | Layout, navigation, color semantics | Grafana dashboard JSON configuration governed by UX spec conventions |

**Non-Functional Requirements:**

16 NFRs across 5 categories driving architectural constraints:

| Category | Key Constraints |
|---|---|
| Performance (NFR1-4) | All panels render < 5s; Prometheus 7-day queries < 10s; drill-down navigation < 3s |
| Reliability (NFR5-9) | No "No data" states when pipeline has run; auto-provisioned Grafana; meaningful zero-states; scrape interval < cycle interval |
| Data Freshness (NFR10-11) | Up to 5-min lag acceptable; Prometheus scrape_interval <= 15s |
| Maintainability (NFR12-14) | Dashboard JSON as single source of truth; exportable panel IDs preserved; new instruments follow existing patterns |
| Operational Readiness (NFR15-16) | Pre-demo validation procedure; full stack healthy in < 60s |

**UX Architectural Implications:**

- Grafana native dark theme -- no custom plugins, no external CSS
- 6-color semantic token system enforced via panel-level threshold configuration
- Two dashboards: main "newspaper" layout (24-col grid with above/below fold zones) + per-topic drill-down
- Panel types limited to Grafana built-in library (stat, time series, bar gauge, bar chart, table, heatmap, text)
- Kiosk mode for demo presentation; standard mode for SRE daily triage
- Desktop-only viewport (1280x720 minimum, 1920x1080 optimal)
- Inter-dashboard navigation via Grafana data links from heatmap tiles
- Single template variable (`$topic`) drives all drill-down panels

**Scale & Complexity:**

- Primary domain: Backend instrumentation + observability infrastructure
- Complexity level: Medium
- Estimated architectural components: 3 (OTLP instrumentation layer, Grafana/Prometheus infrastructure, dashboard JSON configuration)

### Technical Constraints & Dependencies

| Constraint | Source | Impact |
|---|---|---|
| Existing OTLP patterns | Project context (72 rules) | New instruments must use `create_counter` / `create_up_down_counter` from established helpers |
| Prometheus already in docker-compose | `docker-compose.yml` | Scrape config addition, not service addition |
| Pipeline metrics endpoint | `health/` module | Grafana scrapes what the pipeline already exposes via OTLP -> Prometheus |
| Dashboard JSON as code | NFR12-13 | `grafana/dashboards/` and `grafana/provisioning/` directories committed to repo |
| No custom Grafana plugins | UX spec constraint | All visualization via built-in panel types |
| Evidence gauge cardinality | FR3 / PRD note | ~hundreds of series across 9 topics; Grafana queries must handle efficiently |
| MVP baseline band is visual-only | PRD Phase 1/3 split | Baseline overlay uses Prometheus metrics, not Redis seasonal data |
| Environment action caps | Project context | Dashboard displays OBSERVE/NOTIFY/TICKET/PAGE but cannot PAGE outside PROD+TIER_0 |

### Cross-Cutting Concerns Identified

1. **OTLP label consistency** -- All 4 instruments share labels like `topic` and must use consistent label naming across instruments for Grafana query reuse
2. **Prometheus query efficiency** -- 7-day range queries across all instruments must complete < 10s (NFR4); evidence gauge cardinality requires attention
3. **Dashboard JSON lifecycle** -- Export from Grafana UI must preserve panel IDs and data link references (NFR13); provisioning config must auto-load on startup
4. **Color semantic enforcement** -- 6 muted color tokens must be consistent across both dashboards; no Grafana default colors permitted
5. **Zero-state design** -- Every panel needs a meaningful zero-state (celebrated zeros in green, neutral zeros in grey, "Awaiting data" for no-data); no Grafana default "No data" errors
6. **Scrape interval alignment** -- Prometheus scrape_interval (< 15s per NFR11) must be shorter than pipeline cycle interval to avoid partial-snapshot reads (NFR8)

## Starter Template Evaluation

### Primary Technology Domain

Backend instrumentation (Python) + observability infrastructure (Grafana/Prometheus) -- extending an established brownfield codebase.

### Starter Template Assessment: Not Applicable (Brownfield)

This project extends an existing, mature codebase with well-documented patterns and 72 AI agent implementation rules. No starter template evaluation is needed because:

1. **Python pipeline codebase** -- fully established with `pyproject.toml`, `uv.lock`, source tree under `src/aiops_triage_pipeline/`, and comprehensive test suite
2. **OTLP instrumentation patterns** -- `create_counter`, `create_up_down_counter`, `create_histogram` helpers already exist in `health/metrics.py`
3. **Docker-compose infrastructure** -- Kafka, PostgreSQL, Redis, MinIO, Prometheus already running; Grafana is an additive service
4. **Testing infrastructure** -- unit + integration + ATDD test framework with testcontainers already in place

### New Technology Addition: Grafana

**Version:** Grafana OSS (latest stable -- to be pinned in docker-compose image tag)

**Integration Pattern:**
- Grafana runs as a docker-compose service alongside existing Prometheus
- Provisioning configuration auto-loads data sources and dashboards from repository files
- Dashboard JSON files are the single source of truth (NFR12)

**Repository Structure Additions:**

```
grafana/
  provisioning/
    datasources/
      prometheus.yaml       # Auto-configure Prometheus as data source
    dashboards/
      dashboards.yaml       # Dashboard provisioning config
  dashboards/
    aiops-main.json         # Main "newspaper" dashboard
    aiops-drilldown.json    # Per-topic drill-down dashboard
```

### Architectural Decisions Already Established by Existing Codebase

| Decision Area | Established Choice | Source |
|---|---|---|
| Language & runtime | Python 3.13, asyncio | `pyproject.toml` |
| Package management | uv with uv_build backend | `pyproject.toml` |
| Data validation | Pydantic v2 (frozen models) | Project context |
| Observability export | OpenTelemetry SDK 1.39.1, OTLP exporter | Project context |
| Metrics ingestion | Prometheus v2.50.1 | docker-compose |
| Logging | structlog 25.5.0 | Project context |
| Linting | ruff ~0.15 (E, F, I, N, W rules) | `pyproject.toml` |
| Testing | pytest + pytest-asyncio + testcontainers | Project context |
| Local infrastructure | Docker Compose v2+ | Existing stack |
| Code organization | Domain packages by responsibility | Project context |
| Integration safety | `OFF\|LOG\|MOCK\|LIVE` adapter modes | Project context |

**Note:** No project initialization step is needed. The first implementation story begins with OTLP instrument additions to existing pipeline code.

## Core Architectural Decisions

### Decision Priority Analysis

**Critical Decisions (Block Implementation):**

1. Grafana OSS 12.4.x — pinned in docker-compose image tag
2. `topic` label added to all 4 OTLP instruments for drill-down filtering consistency
3. Prometheus scrape_interval: 15s, retention: 15d in docker-compose
4. Evidence gauge: full label granularity, query-side PromQL aggregation in Grafana

**Important Decisions (Shape Architecture):**

5. Dashboard JSON lifecycle: hybrid UI-first design → export → hand-maintain JSON as source of truth
6. Color semantic enforcement: documented hex palette + JSON grep validation (including Grafana default color absence check)
7. Zero-state pattern: hybrid `or vector(0)` for meaningful zeros, `noDataMessage` for missing data
8. Inter-dashboard navigation: data links on heatmap tiles + dashboard header link fallback
9. Pre-demo validation: scripted Grafana API health check (with defined contract) + visual walkthrough

**Deferred Decisions (Post-MVP):**

- Multi-environment dashboard deployment (Phase 2)
- Grafana alerting rules on key panels (Phase 2)
- Loki integration for LLM diagnosis verdict text (Phase 3)
- True seasonal baseline from Redis (Phase 3)

### Data & Metrics Architecture

| Decision | Choice | Rationale |
|---|---|---|
| Grafana version | OSS 12.4.x (docker: `grafana/grafana-oss:12.4.2`) | Latest stable; fresh install with no migration cost |
| OTLP label convention | `topic` label on all 4 instruments; evidence retains `scope` alongside `topic` | Enables per-topic drill-down filtering across every panel; `scope` preserved for domain semantics |
| Prometheus scrape_interval | 15s | Meets NFR11 ceiling; Prometheus default; shorter than pipeline cycle interval (NFR8) |
| Prometheus retention | 15d (docker-compose) | Headroom above 7-day NFR minimum; production uses existing 30-day infrastructure |
| Evidence cardinality strategy | Full label granularity; PromQL `sum by()` / `count by()` at query time | ~hundreds of series well within Prometheus comfort zone; preserves per-metric-key detail; recording rules available as future optimization if needed |

**Implementation Note — `topic` Label Propagation:** Verify `topic` is accessible at all 4 emission points before writing implementation stories. Specifically: (1) `aiops.findings.total` — available on casefile at gating/dispatch stage, (2) `aiops.gating.evaluations_total` — confirm availability in `evaluate_rulebook_gates` context, (3) `aiops.evidence.status` — confirm availability in evidence stage context, (4) `aiops.diagnosis.completed_total` — must be threaded through `DiagnosisResult` or the completion callback closure. If `topic` is not naturally available at any emission point, the story for that instrument must include the propagation work.

**Implementation Note — Evidence Gauge Lifecycle:** The evidence status gauge uses `create_up_down_counter` per project context conventions. The implementation must define whether the lifecycle follows a reset-and-set pattern per cycle or incremental add/subtract on state transitions. This choice affects whether PromQL queries use `last_over_time()` or instant queries.

### Dashboard Architecture

| Decision | Choice | Rationale |
|---|---|---|
| Dashboard JSON lifecycle | Hybrid: UI-first design → export → hand-maintain JSON | Fast visual iteration in Grafana UI; exported JSON becomes source of truth (NFR12); panel IDs preserved (NFR13) |
| Dashboard UID stability | Hardcoded stable UIDs in JSON files (e.g., `"uid": "aiops-main"`, `"uid": "aiops-drilldown"`) | Data links from heatmap tiles embed the drill-down dashboard UID; UIDs must survive re-provisioning and re-export. Mandate: UIDs are constants, never auto-generated |
| Color semantic enforcement | Documented 6-color hex palette in architecture doc; pre-demo grep validation against dashboard JSON — checks both presence of approved palette AND absence of Grafana default colors (`#73BF69`, `#F2495C`, etc.) | No runtime complexity; catches drift and leaked defaults before demo |
| Zero-state pattern | `or vector(0)` for counters/gauges where zero is meaningful; Grafana `noDataMessage` for panels where absence means "pipeline hasn't run" | Preserves semantic distinction: celebrated zeros (green), neutral zeros (grey), genuinely missing data ("Awaiting first pipeline cycle") |
| Inter-dashboard navigation | Grafana data links on heatmap tiles (`var-topic=${__field.labels.topic}`) + dashboard-level header link as fallback | Data links deliver demo click-through narrative; header link supports direct navigation for daily operational use |
| Pre-demo validation | Scripted Grafana API check + manual 60-second visual walkthrough | Script catches data gaps across 20+ panels; visual scan catches color/layout regressions the API can't detect |

**Validation Contract:** "Panel returns data" is defined as: Grafana API `/api/ds/query` returns at least one non-null data point for each panel's configured query after a single pipeline cycle. This is the testable, automatable contract for the pre-demo validation script.

### Authentication & Security

Not applicable for MVP — internal demo context only, no authentication required (PRD deployment considerations). Post-MVP security decisions deferred to shared environment deployment phase.

### API & Communication Patterns

No custom APIs introduced. Data flows through established pipeline:

```
Pipeline (Python) → OTLP exporter → Prometheus (scrape @ 15s) → Grafana (PromQL queries)
```

Inter-dashboard communication via Grafana-native data links and template variables only.

### Infrastructure & Deployment

| Decision | Choice | Rationale |
|---|---|---|
| Grafana docker image | `grafana/grafana-oss:12.4.2` | Latest stable OSS; pinned for reproducibility |
| Provisioning approach | File-based: `grafana/provisioning/datasources/` and `grafana/provisioning/dashboards/` | Auto-loads on startup (NFR6); committed to repo as config-as-code |
| Dashboard file location | `grafana/dashboards/aiops-main.json` + `grafana/dashboards/aiops-drilldown.json` | Matches provisioning config path; two files for two dashboards |
| Grafana environment config | Anonymous auth enabled, default org, provisioned Prometheus datasource | Zero-config startup for demo; no manual Grafana UI setup required |
| Validation tooling | Shell script querying Grafana API post-startup | Supports NFR15 pre-demo validation; runnable as part of docker-compose health check |

### Decision Impact Analysis

**Implementation Sequence:**

Two parallel tracks converging at dashboard panel creation:

*Track A — Infrastructure (no instrument dependency):*
1. Grafana docker-compose service + provisioning config
2. Prometheus scrape config addition
3. Empty dashboard JSON shells with stable UIDs

*Track B — Instrumentation:*
1. OTLP instruments (4 new instruments with `topic` label on all) — data foundation
2. Verify `topic` availability at each emission point; add propagation if needed

*Convergence:*
3. Main dashboard JSON (above-fold → below-fold panels) — visualization layer
4. Drill-down dashboard JSON with `$topic` variable + data links — navigation layer
5. Color palette validation script + pre-demo check script — quality assurance layer

**Cross-Component Dependencies:**

- Instruments → Prometheus: scrape_interval (15s) must be shorter than pipeline cycle
- Instruments → Grafana: `topic` label consistency enables `$topic` variable filtering across all panels
- Dashboard JSON → Provisioning config: file paths must match provisioning YAML
- Dashboard JSON → UIDs: `aiops-main` and `aiops-drilldown` UIDs are hardcoded constants; data links reference `aiops-drilldown` by UID
- Color palette doc → Dashboard JSON → Grep validation: all three must reference identical hex values; grep also rejects Grafana default palette colors
- Data links → Dashboard UIDs: main dashboard heatmap links embed drill-down dashboard UID; UID must be stable across re-provisioning

## Implementation Patterns & Consistency Rules

### Pattern Categories Defined

**Critical Conflict Points Identified:** 6 areas where AI agents could make different choices, all specific to this iteration's OTLP instrumentation and Grafana dashboard work. General Python patterns are governed by the existing project context (72 rules).

### OTLP Instrument Patterns

**Instrument Naming:**
- In Python code: dotted OTLP name → `"aiops.findings.total"`
- In PromQL / Grafana: underscored Prometheus name → `aiops_findings_total`
- In documentation: reference both forms on first use

**Label Value Convention:**
- Emit enum values as uppercase strings matching Python contract models
- `BASELINE_DEVIATION`, `PRESENT`, `OBSERVE`, `NOTIFY`, `TICKET`, `PAGE`
- No lowercase translation at the emission boundary
- Grafana queries reference identical values: `{status="PRESENT"}`

**Examples:**
```python
# Good — matches contract enum, no translation
findings_counter.add(1, {
    "topic": scope.topic,
    "anomaly_family": "BASELINE_DEVIATION",
    "final_action": "NOTIFY",
    "routing_key": scope.routing_key,
    "criticality_tier": scope.criticality_tier,
})

# Bad — lowercase translation diverges from code enums
findings_counter.add(1, {"anomaly_family": "baseline_deviation"})
```

### Grafana Dashboard JSON Patterns

**Panel IDs:**
- Main dashboard panels: IDs 1–99
- Drill-down dashboard panels: IDs 100–199
- Document allocation in a comment block at top of each JSON file

**Panel Titles:**
- Sentence case: "Gating intelligence funnel", not "Gating Intelligence Funnel"

**PromQL `refId` Values:**
- Single-query panels: `A`
- Multi-query panels: `A` (primary), `B` (secondary, e.g., baseline band)
- Alphabetical order matches visual layer order

**Panel Descriptions:**
- Populate for above-the-fold panels (demo narrative context)
- Skip for below-the-fold and drill-down panels where title is self-explanatory

### PromQL Query Patterns

**Label Matchers:**
- Drill-down variable filtering: `{topic="$topic"}` (exact match)
- All topics with data: `{topic=~".+"}` (never `.*` which includes empty)

**Aggregation Style:**
- Always: `sum by(label) (metric{filter})`
- Never: `sum(metric{filter}) by(label)`

**Counter Query Conventions:**
- Human-readable totals (stat panels): `increase(metric[$__range])`
- Per-second throughput (time-series panels): `rate(metric[$__rate_interval])`
- Never mix increase/rate within the same panel type

**Range Vectors:**
- Stat panels: `[$__range]` — matches Grafana time picker
- Time-series panels: `[$__rate_interval]` — Grafana-recommended for rate/increase with scrape interval awareness

### Test Patterns for New Components

**OTLP Instrument Tests:**
- Location: `tests/unit/health/` — mirrors `health/metrics.py` source
- Pattern: verify each instrument emits expected metric name and label set
- Use existing `prometheus-client` test harness from dev dependencies
- Assert on metric name + label set, not raw string output

**Grafana Validation Tests:**
- Location: `tests/integration/` — requires live docker-compose stack
- Pattern: start stack → run one pipeline cycle → execute validation script → assert all panels return non-null data
- Not unit tests: never mock Grafana or Prometheus for panel data validation

### Docker-Compose & Configuration Patterns

**Service Naming:**
- `grafana` — lowercase single-word, matches existing convention (`kafka`, `postgres`, `redis`, `prometheus`)

**Grafana Configuration:**
- Use `GF_` environment variables in docker-compose (e.g., `GF_AUTH_ANONYMOUS_ENABLED=true`)
- No separate `grafana.ini` file — env vars are sufficient for MVP and visible in one place

**Volume Mounts:**
- `./grafana/provisioning:/etc/grafana/provisioning`
- `./grafana/dashboards:/var/lib/grafana/dashboards`
- `grafana/` directory is the single root for all Grafana artifacts

### Enforcement Guidelines

**All AI Agents MUST:**
- Reference project context (72 rules) for all general Python patterns before implementing
- Follow OTLP naming patterns exactly — dotted in Python, underscored in PromQL
- Use uppercase enum values for all OTLP label values with no translation
- Assign panel IDs from the allocated range (1–99 main, 100–199 drill-down)
- Use the specified PromQL aggregation style and range vector conventions
- Place new tests in the correct scope (unit for instruments, integration for Grafana validation)

**Anti-Patterns:**
- Lowercase OTLP label values that diverge from Python enum names
- Grafana default colors leaking into dashboard JSON (use approved palette only)
- `sum(metric) by(label)` instead of `sum by(label) (metric)`
- Using `[$__range]` in time-series rate panels or `[$__rate_interval]` in stat panels
- Mocking Grafana/Prometheus in panel data validation tests
- Creating `grafana.ini` instead of using `GF_` environment variables

## Project Structure & Boundaries

### Complete Project Directory Structure

Existing directories shown in context; **new files and directories marked with NEW**.

```
aiops/
├── docker-compose.yml                          # Add grafana service, update prometheus scrape config
├── src/aiops_triage_pipeline/
│   ├── health/
│   │   ├── metrics.py                          # Add 4 new OTLP instruments here
│   │   ├── otlp.py                             # Existing OTLP bootstrap (no changes expected)
│   │   ├── registry.py                         # Existing health registry
│   │   ├── alerts.py
│   │   └── server.py
│   ├── pipeline/stages/                        # Instrument emission call sites
│   │   ├── gating.py                           # Emit aiops.findings.total, aiops.gating.evaluations_total
│   │   ├── evidence.py                         # Emit aiops.evidence.status
│   │   └── ...                                 # Other stages unchanged
│   ├── diagnosis/                              # Emit aiops.diagnosis.completed_total
│   │   └── ...                                 # Cold-path completion handler
│   ├── contracts/                              # Existing frozen models (no changes)
│   ├── models/                                 # Existing runtime models (no changes)
│   └── ...                                     # Other packages unchanged
├── grafana/                                    # NEW — all Grafana artifacts
│   ├── provisioning/                           # NEW
│   │   ├── datasources/
│   │   │   └── prometheus.yaml                 # NEW — auto-configure Prometheus datasource
│   │   └── dashboards/
│   │       └── dashboards.yaml                 # NEW — dashboard provisioning config
│   └── dashboards/
│       ├── aiops-main.json                     # NEW — main "newspaper" dashboard (uid: aiops-main)
│       └── aiops-drilldown.json                # NEW — per-topic drill-down dashboard (uid: aiops-drilldown)
├── scripts/
│   ├── validate-dashboards.sh                  # NEW — pre-demo validation script (Grafana API check)
│   ├── validate-colors.sh                      # NEW — color palette grep validation
│   ├── smoke-test.sh                           # Existing
│   └── ...
├── tests/
│   ├── unit/
│   │   ├── health/
│   │   │   ├── test_metrics.py                 # Extend with tests for 4 new instruments
│   │   │   └── ...                             # Existing tests unchanged
│   │   └── ...
│   ├── integration/
│   │   ├── test_dashboard_validation.py        # NEW — Grafana panel data validation
│   │   └── ...                                 # Existing integration tests unchanged
│   └── atdd/                                   # ATDD tests (cardinality canary test lives here)
├── config/                                     # Existing config (no changes)
├── docs/                                       # Existing docs (no changes)
└── artifact/                                   # Planning artifacts
```

### Architectural Boundaries

**Data Flow Boundary:**
```
Pipeline Code (Python)
    ↓ (OTLP instruments emit in health/metrics.py)
OTLP Exporter (health/otlp.py)
    ↓ (push to collector / Prometheus remote write)
Prometheus (docker-compose service, scrape @ 15s)
    ↓ (PromQL queries)
Grafana (docker-compose service, provisioned dashboards)
```

**Instrument Emission Boundary:**
- Instruments are **defined** in `health/metrics.py` (single source of truth for all metric definitions)
- Instruments are **called** at their respective pipeline stage locations
- No instrument definition outside `health/metrics.py`
- No direct Prometheus client usage — always go through OTLP

**Dashboard Boundary:**
- All Grafana configuration lives under `grafana/` — nothing scattered elsewhere
- Dashboard JSON files are the single source of truth for panel layout, queries, and thresholds
- Provisioning YAML files are the single source of truth for datasource and dashboard loader config
- Grafana runtime state (preferences, annotations) is ephemeral — not persisted to repo

**Validation Boundary:**
- `scripts/validate-dashboards.sh` — queries Grafana API, verifies panel data presence
- `scripts/validate-colors.sh` — greps dashboard JSON for approved palette + absence of Grafana defaults
- `tests/integration/test_dashboard_validation.py` — programmatic integration test wrapping the validation logic

### Requirements to Structure Mapping

**FR Category: Pipeline Telemetry (FR1–FR4)**
- Instrument definitions: `src/aiops_triage_pipeline/health/metrics.py`
- Emission call sites: `pipeline/stages/gating.py`, `pipeline/stages/evidence.py`, `diagnosis/` completion handler
- Tests: `tests/unit/health/test_metrics.py`

**FR Category: Platform Health (FR5–FR7), Detection (FR8–FR10), Noise Suppression (FR11–FR13), AI Diagnosis (FR14–FR15), Pipeline Visibility (FR22–FR24)**
- All visualization FRs: `grafana/dashboards/aiops-main.json`
- Panel queries, thresholds, color config embedded in dashboard JSON

**FR Category: Operational Triage (FR16–FR21)**
- Drill-down dashboard: `grafana/dashboards/aiops-drilldown.json`
- Topic variable + data links configured in JSON

**FR Category: Infrastructure (FR25–FR28)**
- Grafana service: `docker-compose.yml` (grafana service block)
- Prometheus scrape config: `docker-compose.yml` (prometheus command/config)
- Datasource provisioning: `grafana/provisioning/datasources/prometheus.yaml`
- Dashboard provisioning: `grafana/provisioning/dashboards/dashboards.yaml`

**FR Category: Presentation (FR29–FR34)**
- Layout, navigation, color semantics: `grafana/dashboards/aiops-main.json` panel grid positions, data links, threshold colors
- Kiosk mode: Grafana URL parameter (`?kiosk`), no file change needed

**Cross-Cutting: Validation (NFR15)**
- Pre-demo script: `scripts/validate-dashboards.sh`
- Color validation: `scripts/validate-colors.sh`
- Integration test: `tests/integration/test_dashboard_validation.py`

### Integration Points

**Internal — Pipeline to Prometheus:**
- OTLP instruments → OTLP exporter → Prometheus scrape endpoint
- Scrape target configured in docker-compose Prometheus config
- Pipeline's existing `/metrics` health endpoint is the scrape target

**Internal — Prometheus to Grafana:**
- Grafana provisioned datasource points to `http://prometheus:9090`
- All panel queries use PromQL against this single datasource
- No additional datasources needed for MVP

**External — Inter-Dashboard Navigation:**
- Main dashboard heatmap → drill-down dashboard via Grafana data link
- Data link passes `var-topic=${__field.labels.topic}` to drill-down UID `aiops-drilldown`
- Dashboard header link provides fallback navigation

### File Organization Patterns

**New files follow existing conventions:**
- Python source: added to existing packages, no new top-level packages
- Tests: extend existing test files where possible; new test files only for new test domains
- Scripts: added to existing `scripts/` directory
- Config: Grafana config under `grafana/` (new top-level dir, consistent with how `config/` and `harness/` are organized)

**Decision guide for AI agents:**

| "I need to..." | File |
|---|---|
| Define a new OTLP instrument | `health/metrics.py` |
| Emit an instrument at a pipeline stage | The stage file (e.g., `pipeline/stages/gating.py`) |
| Add a Grafana panel | The appropriate dashboard JSON (`aiops-main.json` or `aiops-drilldown.json`) |
| Configure Grafana datasource | `grafana/provisioning/datasources/prometheus.yaml` |
| Change Prometheus scrape config | `docker-compose.yml` prometheus service block |
| Add Grafana to docker-compose | `docker-compose.yml` grafana service block |
| Test an OTLP instrument | `tests/unit/health/test_metrics.py` |
| Test dashboard data presence | `tests/integration/test_dashboard_validation.py` |
| Validate before demo | Run `scripts/validate-dashboards.sh` + visual walkthrough |

## Architecture Validation Results

### Coherence Validation

**Decision Compatibility:** All technology choices are compatible:
- Grafana OSS 12.4.x natively supports Prometheus v2.50.1 as a datasource
- OTLP SDK 1.39.1 exports metrics that Prometheus scrapes via the pipeline's health server
- Docker Compose services communicate over the default bridge network — no custom networking needed
- All existing library versions unchanged; Grafana is purely additive

**Pattern Consistency:** Implementation patterns align with decisions:
- OTLP naming convention (dotted in Python, underscored in PromQL) is consistent across instrument definitions and Grafana query patterns
- Uppercase label values match Python contract enums end-to-end through to Grafana queries
- Panel ID allocation (1–99 main, 100–199 drill-down) prevents collision between dashboards
- PromQL style rules (`sum by(label) (metric)`, `increase` vs `rate`) apply uniformly

**Structure Alignment:** Project structure supports all decisions:
- `health/metrics.py` is the single source of truth for instrument definitions (matches existing pattern)
- `grafana/` directory cleanly isolates all Grafana artifacts from pipeline code
- Test locations (unit/health for instruments, integration for Grafana validation) follow established conventions
- Validation scripts in `scripts/` follow existing utility script pattern

### Requirements Coverage Validation

**Functional Requirements (34 FRs):**

| FR Category | FRs | Architectural Support | Status |
|---|---|---|---|
| Pipeline Telemetry | FR1–4 | 4 instruments in `health/metrics.py`, emission at pipeline stages, `topic` on all | Covered |
| Platform Health | FR5–7 | `aiops-main.json` stat, heatmap panels with PromQL queries | Covered |
| Detection & Anomaly | FR8–10 | `aiops-main.json` time-series with baseline band, anomaly breakdown | Covered |
| Noise Suppression | FR11–13 | `aiops-main.json` funnel, action distribution, per-gate panels | Covered |
| AI Diagnosis | FR14–15 | `aiops-main.json` diagnosis stat panels | Covered |
| Operational Triage | FR16–21 | `aiops-drilldown.json` with `$topic` variable, data links from heatmap | Covered |
| Pipeline Visibility | FR22–24 | `aiops-main.json` capability stack, throughput, outbox panels | Covered |
| Infrastructure | FR25–28 | `docker-compose.yml` grafana service, provisioning config, scrape config | Covered |
| Presentation | FR29–34 | Panel grid positions, color thresholds, data links, kiosk via URL param | Covered |

**Non-Functional Requirements (16 NFRs):**

| NFR Category | NFRs | Architectural Support | Status |
|---|---|---|---|
| Performance | NFR1–4 | Query-side aggregation, cardinality canary test, Prometheus handles scale | Covered |
| Reliability | NFR5–9 | Hybrid zero-state pattern, auto-provisioning, scrape < cycle interval | Covered |
| Data Freshness | NFR10–11 | Scrape interval 15s, 5-min lag acceptable | Covered |
| Maintainability | NFR12–14 | Dashboard JSON as source of truth, hybrid lifecycle, existing OTLP patterns | Covered |
| Operational Readiness | NFR15–16 | Validation script + visual walkthrough, full stack in docker-compose | Covered |

### Implementation Readiness Validation

**Decision Completeness:** All critical decisions documented with specific versions (Grafana 12.4.2, Prometheus v2.50.1, OTLP SDK 1.39.1). Implementation patterns include concrete code examples and anti-patterns.

**Structure Completeness:** Every new file and directory is named and located. Decision guide table maps "I need to..." to specific files. Integration boundaries clearly defined.

**Pattern Completeness:** All 6 conflict areas addressed with explicit conventions. Enforcement guidelines and anti-patterns documented. AI agents have unambiguous guidance for every implementation choice in scope.

### Validation Issues Found & Resolved

**Issue 1: Muted Color Palette Specification**

The UX spec defines two color palettes — Grafana defaults and muted professional variants. The architecture specifies the **muted variants** as the implementation palette:

| Token | Implementation Hex (Muted) | Reject (Grafana Default) |
|---|---|---|
| `semantic-green` | `#6BAD64` | `#73BF69` |
| `semantic-amber` | `#E8913A` | `#FF9830` |
| `semantic-red` | `#D94452` | `#F2495C` |
| `semantic-grey` | `#7A7A7A` | `#8E8E8E` |
| `accent-blue` | `#4F87DB` | `#5794F2` |
| `band-fill` | `#4F87DB` at 12% opacity | `#5794F2` at 15% opacity |

The `validate-colors.sh` script must:
1. Approve only the muted hex values in the left column
2. Reject the Grafana default hex values in the right column (these are the specific "leaked defaults" to catch)

**Issue 2: Prometheus Scrape Target for Pipeline**

The current `config/prometheus.yml` has scrape jobs for `prometheus` (self) and `aiops-harness` but no job for the pipeline app. The pipeline health server runs on port 8080 (`health/server.py`). A new scrape job must be added:

```yaml
- job_name: 'aiops-pipeline'
  scrape_interval: 15s
  static_configs:
    - targets: ['app:8080']
```

This is an implementation requirement for the infrastructure story (FR25–28). The `app` service name matches the docker-compose service definition.

### Architecture Completeness Checklist

**Requirements Analysis**
- [x] Project context thoroughly analyzed (72 rules, 29 existing patterns)
- [x] Scale and complexity assessed (medium — 3 architectural components)
- [x] Technical constraints identified (8 constraints from PRD/UX/project context)
- [x] Cross-cutting concerns mapped (6 concerns identified)

**Architectural Decisions**
- [x] Critical decisions documented with versions (4 critical, 5 important)
- [x] Technology stack fully specified (Grafana 12.4.2 added to existing stack)
- [x] Integration patterns defined (OTLP → Prometheus → Grafana)
- [x] Performance considerations addressed (cardinality strategy, query patterns)

**Implementation Patterns**
- [x] Naming conventions established (OTLP, labels, panels, PromQL)
- [x] Structure patterns defined (dashboard JSON, docker-compose, Grafana config)
- [x] Communication patterns specified (data links, template variables)
- [x] Process patterns documented (validation, testing, export lifecycle)

**Project Structure**
- [x] Complete directory structure defined (all new files named and located)
- [x] Component boundaries established (instrument, dashboard, validation)
- [x] Integration points mapped (pipeline → Prometheus → Grafana)
- [x] Requirements to structure mapping complete (all 9 FR categories mapped)

### Architecture Readiness Assessment

**Overall Status:** READY FOR IMPLEMENTATION

**Confidence Level:** High

**Key Strengths:**
- Builds entirely on established patterns (72 rules, existing OTLP helpers, existing docker-compose stack)
- No new Python packages or architectural paradigms introduced
- Clear separation: pipeline code changes are minimal (4 instruments + emission calls), infrastructure is additive (Grafana service + provisioning), dashboards are pure configuration (JSON files)
- Every decision has a concrete rationale tied to PRD requirements or NFR constraints
- Party mode review surfaced 5 refinements that strengthened the architecture (UID stability, parallel tracks, propagation verification, validation contract, default color checking)

**Areas for Future Enhancement:**
- Recording rules for evidence gauge if cardinality grows beyond MVP scale
- Grafana alerting rules on key panels (Phase 2)
- Loki datasource integration for LLM diagnosis text (Phase 3)
- True seasonal baseline from Redis replacing MVP Prometheus-only band (Phase 3)
- Multi-environment dashboard deployment and authentication (post-MVP)

### Implementation Handoff

**AI Agent Guidelines:**
- Read `artifact/project-context.md` (72 rules) before implementing any code
- Follow this architecture document for all decisions specific to this iteration
- Use the "Decision guide for AI agents" table in Project Structure for file placement
- Respect the muted color palette — never use Grafana default hex values
- Verify `topic` label availability at each emission point before coding

**First Implementation Priority:**

Two parallel tracks as defined in Decision Impact Analysis:
- **Track A (Infrastructure):** Add Grafana service to docker-compose, add pipeline scrape job to prometheus.yml, create provisioning config, create empty dashboard JSON shells with stable UIDs
- **Track B (Instrumentation):** Add 4 OTLP instruments to `health/metrics.py` with `topic` label, wire emission calls at pipeline stages
