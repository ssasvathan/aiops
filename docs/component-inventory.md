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

## Domain Model Components

- Contracts: `contracts/*` frozen schemas for policy and event interfaces
- Runtime models: `models/*` stage payloads, casefile entities, and health events

## UI / Design System

- No frontend UI component library detected in this backend repository.
