# Event-Driven Pipeline Specific Requirements

Where Domain-Specific Requirements define *what* guarantees the system maintains, this section defines *how* the pipeline's technical surface is structured — runtime topology, interface contracts, and implementation patterns that CR implementations must follow.

## Project-Type Overview

aiOps is an event-driven triage pipeline with integration adapters — not a conventional REST API backend. The system's technical surface comprises inbound telemetry ingestion, internal pipeline stage contracts, outbound integration adapters, and durable persistence boundaries. The revision phase activates unwired capabilities and adds new interfaces (cold-path Kafka consumer, distributed coordination).

## Technical Architecture Considerations

**Runtime Modes and Pod Topology:**

| Mode | Pod Deployment | Health Endpoint | Dependencies |
|---|---|---|---|
| `hot-path` | Hot/hot 2-pod minimum | Yes — includes coordination state | Redis, Postgres, S3, Prometheus, topology registry |
| `cold-path` | Independent consumer pod | Yes — dedicated endpoint required (CR-07) | Kafka (consumer), S3, LLM provider |
| `outbox-publisher` | Companion to hot-path | Yes | Postgres, Kafka (producer), S3 |
| `casefile-lifecycle` | Maintenance process | Yes | S3 |

**Inbound Interfaces:**
- Health endpoint per pod (raw asyncio TCP handler, `/health`) — returns component health registry status map
- Prometheus instant query API ingestion (`/api/v1/query`) — hot-path evidence collection
- Kafka consumer for CaseHeaderEventV1 — cold-path inbound (CR-07, new)

**Outbound Interfaces:**
- Kafka publication: `aiops-case-header`, `aiops-triage-excerpt` topics via outbox-publisher
- PagerDuty Events V2 trigger API (PAGE actions)
- Slack incoming webhook (NOTIFY actions, degraded-mode alerts, postmortem notifications)
- ServiceNow table API (TICKET actions — tiered incident correlation, Problem/PIR upserts)

**Contract and Data Format Strategy:**
- All inter-stage data flows through frozen Pydantic v1 contracts
- Schema envelope pattern for versioned persistence and Kafka events
- JSON serialization at all I/O boundaries via canonical Pydantic paths
- No ad-hoc serializers — contract models are the source of truth for payload shape

**Authentication and Security:**
- No end-user auth boundary (no user-facing REST auth routes)
- Integration-driven auth: ServiceNow bearer token, Slack webhook URL, PagerDuty routing key
- Kafka SASL_SSL with Kerberos — keytab and krb5 config paths validated at startup (fail-fast)
- Secrets never logged — masking patterns preserved for credentials and URLs
- Denylist enforcement at all outbound boundaries before external payloads

## Cold-Path Consumer Requirements (CR-07)

- Independent Kafka consumer pod with dedicated health endpoint reporting consumer group state
- Consumes CaseHeaderEventV1 from `aiops-case-header` topic
- Retrieves full case context from S3 (guaranteed by Invariant A — triage.json exists before header on Kafka)
- Reconstructs triage excerpt and evidence summary from persisted casefile data
- Delegates to existing `run_cold_path_diagnosis()` for LLM invocation and `diagnosis.json` persistence
- Graceful shutdown with consumer offset commit
- No eligibility criteria — LLM diagnosis runs for all cases (CR-08)

## Distributed Coordination Requirements (CR-05)

- Redis-based distributed cycle lock: one hot-path pod executes per scheduler interval, losers yield
- Coordination state exposed in health endpoint: lock holder status, lock expiry time, last cycle execution timestamp
- Informational only — coordination state does not affect K8s liveness/readiness probe health status
- Fail-open on Redis unavailability (preserves availability, worst case equals single-instance behavior)
- Feature-flagged: `DISTRIBUTED_CYCLE_LOCK_ENABLED` (default false) for incremental rollout
- OTLP counters: lock acquired, lock yielded, lock failed
- No manual lock-release API — TTL-based self-healing with direct Redis key deletion available for emergencies

## Topology Registry Deployment (CR-11)

- Topology registry YAML relocated to `config/` alongside other policy and configuration files
- Deployed as part of the deployment package within the project folder
- `TOPOLOGY_REGISTRY_PATH` default and Docker env references point to `config/` location
- Single format only (instances-based) — all legacy v0 format support removed
- Hot-path reload-on-change behavior preserved

## Implementation Considerations

- **Error taxonomy:** Critical invariant violations raise halt-class exceptions; degradable dependency failures raise degradable exceptions and continue with caps
- **Config as leaf:** `config/settings.py` must not import specific contract classes; `load_policy_yaml(path, model_class)` stays generic
- **Integration mode framework:** All external integrations implement OFF|LOG|MOCK|LIVE consistently; default LOG unless explicitly configured
- **Observability:** Pod identity (POD_NAME, POD_NAMESPACE) in OTLP resource attributes and structlog context for per-instance visibility across replicas
- **Policy loading:** All policies loaded once at startup (no per-cycle disk I/O); topology registry is the exception with reload-on-change
