# Architecture

## Executive Summary

`aiops-triage-pipeline` is a Python backend service that processes telemetry-driven anomalies through deterministic pipeline stages, persists durable case artifacts, and publishes downstream event contracts through an outbox reliability boundary.

## Technology Stack

- Runtime: Python 3.13, asyncio
- Data/modeling: Pydantic v2, pydantic-settings
- Persistence: PostgreSQL (durable outbox + linkage retry state), Redis (caches), S3-compatible object store (casefile stages)
- Messaging: Kafka via confluent-kafka
- Observability: OpenTelemetry + OTLP, Prometheus metrics ingestion
- Tooling: uv, pytest, testcontainers, ruff, Docker/Compose

## Architecture Pattern

- Primary style: layered backend service with event-driven pipeline core.
- Reliability style: durable outbox + source-state-guarded SQL transitions.
- Integration style: adapter modules with explicit runtime safety modes (`OFF|LOG|MOCK|LIVE`).
- Coordination style: optional distributed hot-path cycle ownership with Redis `SET NX EX`
  (`aiops:lock:cycle`), TTL expiry only (no unlock), and mandatory fail-open execution on
  Redis lock failures.

## Data Architecture

### Durable SQL entities

- `outbox` table: tracks `PENDING_OBJECT -> READY -> SENT/RETRY/DEAD` lifecycle for Kafka publication.
- `sn_linkage_retry` table: tracks ServiceNow linkage attempt state and retry windows.

### Object-storage entities

- Stage JSON payloads under `cases/<case_id>/<stage>.json`
- Stage models: `CaseFileTriageV1`, `CaseFileDiagnosisV1`, `CaseFileLinkageV1`, `CaseFileLabelsV1`
- Hash and write-once checks enforce idempotent persistence invariants.

## API Design

### Inbound

- Lightweight HTTP health endpoint from `health/server.py` (returns registry status map).

### Outbound

- Prometheus instant query API (`/api/v1/query`)
- PagerDuty Events V2 trigger API
- Slack incoming webhook API
- ServiceNow table API (`GET/POST/PATCH`)
- Kafka topic publication (`aiops-case-header`, `aiops-triage-excerpt`)

## Component Overview

- `pipeline/stages/`: stage computation and gating decisions
- `coordination/`: distributed coordination — cycle lock (Story 4.1) and shard registry with lease/checkpoint primitives (Story 4.2)
- `outbox/`: durable publish sequencing and worker
- `linkage/`: ServiceNow retry state and transition safety
- `storage/`: casefile serialization, validation, object-store writes
- `integrations/`: external side-effect boundaries
- `contracts/` + `models/`: frozen interfaces and domain payloads
- `health/`: status registry, alerts, metrics export setup

## Source Tree (Annotated)

- `src/aiops_triage_pipeline/__main__.py` - runtime mode dispatch
- `src/aiops_triage_pipeline/pipeline/scheduler.py` - hot-path orchestration
- `src/aiops_triage_pipeline/pipeline/stages/*` - deterministic stage modules
- `src/aiops_triage_pipeline/outbox/*` - durable outbox state machine and repository
- `src/aiops_triage_pipeline/linkage/*` - ServiceNow retry state machine + persistence
- `src/aiops_triage_pipeline/storage/*` - write-once casefile persistence

## Development Workflow

1. Sync deps (`uv sync --dev`)
2. Start local infra (`docker compose up -d --build`)
3. Validate stack (`bash scripts/smoke-test.sh`)
4. Run tests (unit/integration/full with Docker-backed path)
5. Lint (`uv run ruff check`)

## Deployment Architecture

- Containerized runtime via multi-stage Dockerfile.
- Local deployment topology via compose services: Kafka, Postgres, Redis, MinIO, Prometheus, harness, app.
- Runtime configuration and policy behavior controlled by `config/.env.*` + `config/policies/*.yaml`.

## Testing Strategy

- Unit tests validate contracts, stage behavior, repositories, and integration adapters.
- Integration tests validate end-to-end and dependency-backed flows.
- Preferred full regression command enforces Docker-backed integration execution with no skips.
