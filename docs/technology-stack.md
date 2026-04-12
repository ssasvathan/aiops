# Technology Stack

## Part: core

| Category | Technology | Version | Justification |
|---|---|---:|---|
| Language Runtime | Python | >=3.13 | Declared in `pyproject.toml` (`requires-python`) |
| Packaging / Build | uv, uv_build | uv_build>=0.9.21 | Locked dependency workflow and build backend |
| Data Validation | Pydantic, pydantic-settings | 2.12.5 / ~2.13.1 | Frozen contract models and environment-bound config |
| Message Bus | Kafka (Confluent client) | 7.5.0 infra / 2.13.0 client | Outbox publisher emits case events to Kafka topics |
| Database | PostgreSQL | 16 (compose) | Durable outbox and linkage retry state |
| Cache | Redis | 7.2 | Dedupe + evidence/peak TTL caches |
| Object Storage | MinIO (S3-compatible), boto3 | 2025-01-20 / ~1.42 | Casefile stage persistence with write-once semantics |
| HTTP Client | urllib, httpx | stdlib / 0.28.1 | Prometheus, Slack, PagerDuty, ServiceNow integrations |
| Orchestration | asyncio | stdlib | Scheduler loops, async health endpoint, async evidence collection |
| Observability | OpenTelemetry SDK + OTLP exporter | 1.39.1 | Metrics export and component health instrumentation |
| Logging | structlog | 25.5.0 | Structured runtime and integration event logs |
| Database Toolkit | SQLAlchemy | 2.0.47 | SQLAlchemy Core repositories and schema DDL |
| Test Framework | pytest + pytest-asyncio + testcontainers | 9.0.2 / 1.3.0 / 4.14.1 | Unit + integration testing with Docker-backed dependencies |
| Static Analysis | Ruff | ~0.15 | Lint and style enforcement |
| Dashboards | Grafana OSS | 12.4.2 | Auto-provisioned observability dashboards with Prometheus data source |
| Local Infra | docker-compose | v2+ | Kafka, Postgres, Redis, MinIO, Prometheus, Grafana, harness stack |

## Architecture Signals From Stack

- Contract-first domain model (Pydantic frozen contracts and model validators).
- Event-driven pipeline execution model (scheduler + stage composition + outbox worker).
- Durable integration boundary (database-backed outbox and retry-state tables).
- Strong local parity for integration dependencies via compose stack.
- Observability-first dashboard layer (Grafana + Prometheus auto-provisioned from JSON source of truth).
