# Component Inventory

## Runtime Components

| Component | Category | Location | Reusable | Notes |
|---|---|---|---|---|
| Scheduler | Orchestration | `pipeline/scheduler.py` | Yes | Coordinates stage execution cycle |
| Stage Modules | Pipeline | `pipeline/stages/*` | Yes | Evidence, peak, topology, casefile, outbox, gating, dispatch |
| Outbox Worker | Reliability | `outbox/worker.py` | Yes | Durable publish loop and health checks |
| Outbox Repository | Persistence | `outbox/repository.py` | Yes | State-guarded SQL transitions |
| Linkage Retry Repository | Persistence | `linkage/repository.py` | Yes | Durable ServiceNow linkage retry state |
| S3 Object Store Client | Storage | `storage/client.py` | Yes | Casefile object IO abstraction |
| Casefile IO | Storage | `storage/casefile_io.py` | Yes | Stage serialization, hash validation, write-once semantics |
| Prometheus Client | Integration | `integrations/prometheus.py` | Yes | Contract-driven metric query and label normalization |
| Kafka Publisher | Integration | `integrations/kafka.py` | Yes | CaseHeader/TriageExcerpt publication boundary |
| ServiceNow Client | Integration | `integrations/servicenow.py` | Yes | Correlation + Problem/PIR idempotent upserts |
| Slack Client | Integration | `integrations/slack.py` | Yes | Degraded and escalation notifications |
| PagerDuty Client | Integration | `integrations/pagerduty.py` | Yes | PAGE action trigger dispatch |
| Health Registry | Observability | `health/registry.py` | Yes | Component health state tracking |
| OTLP Metrics Bootstrap | Observability | `health/otlp.py` | Yes | Exporter setup and lifecycle |
| Denylist Enforcement | Security | `denylist/enforcement.py` | Yes | Field-level outbound data suppression |
| Baseline Constants | Configuration | `baseline/constants.py` | Yes | MAD_CONSISTENCY_CONSTANT, MAD_THRESHOLD, MIN_CORRELATED_DEVIATIONS, MIN_BUCKET_SAMPLES, MAX_BUCKET_VALUES |
| Baseline Computation | Computation | `baseline/computation.py` | Yes | time_to_bucket() — sole UTC-normalized (dow, hour) bucket derivation function |
| SeasonalBaselineClient | Storage | `baseline/client.py` | Yes | Placeholder — Redis I/O boundary for seasonal baseline read/write/seed/recompute (Story 1.2) |
| Baseline Deviation Stage | Pipeline | `pipeline/stages/baseline_deviation.py` | No | Correlated multi-metric baseline deviation detection with MAD z-score; emits BASELINE_DEVIATION findings; HealthRegistry key: `baseline_deviation` |

## Domain Model Components

- Contracts: `contracts/*` frozen schemas for policy and event interfaces
- Runtime models: `models/*` stage payloads, casefile entities, and health events

## Observability Dashboard Components

| Component | Category | Location | Notes |
|---|---|---|---|
| Main Dashboard | Grafana JSON | `grafana/dashboards/aiops-main.json` | Stakeholder narrative + operational intelligence panels (IDs 1–99) |
| Drill-Down Dashboard | Grafana JSON | `grafana/dashboards/aiops-drilldown.json` | Per-topic detail panels (IDs 100–199) |
| Dashboard Provisioning | Grafana Config | `grafana/provisioning/dashboards/dashboards.yaml` | Auto-loads JSON dashboards on startup |
| Prometheus Data Source | Grafana Config | `grafana/provisioning/datasources/prometheus.yaml` | UID `prometheus`, scrape interval 15s |
| Findings Instrument | OTLP Metric | `health/metrics.py` | `aiops.findings.total` — counter with anomaly_family, action, topic, routing_key, criticality_tier labels |
| Gating Instrument | OTLP Metric | `health/metrics.py` | `aiops.gating.evaluations_total` — counter with gate_id, outcome labels |
| Evidence Instrument | OTLP Metric | `health/metrics.py` | `aiops.evidence.status` — gauge with scope, metric_key, topic, status labels (delta accounting) |
| Diagnosis Instrument | OTLP Metric | `health/metrics.py` | `aiops.diagnosis.completed_total` — counter with confidence_level, fault_domain labels |
| Color Palette Validator | Script | `scripts/validate-colors.sh` | Enforces muted palette, rejects Grafana default colors |

## UI / Design System

- No frontend UI component library detected in this backend repository.
- Grafana dashboards serve as the observability UI — see Observability Dashboard Components above.
