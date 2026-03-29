# Starter Template Evaluation

## Primary Technology Domain

Python backend event-driven pipeline — established brownfield codebase with two completed iteration cycles.

## Starter Template: Not Applicable (Brownfield)

This is a surgical fix release against a mature, delivered codebase. No starter template evaluation is needed — the project structure, dependency graph, coding patterns, and tooling are established and stable.

## Established Technology Foundation

The following technology decisions are locked by the existing codebase and `project-context.md`. These are constraints, not choices:

- **Language & Runtime:** Python >=3.13 with asyncio
- **Data Modeling:** Pydantic v2 (2.12.5) with `frozen=True` for contracts; pydantic-settings ~2.13.1
- **Persistence:** PostgreSQL 16 (SQLAlchemy Core), Redis 7.2, MinIO/S3 (boto3 ~1.42)
- **Messaging:** Kafka via confluent-kafka 2.13.0
- **Observability:** OpenTelemetry SDK 1.39.1 + OTLP; structlog 25.5.0
- **Testing:** pytest 9.0.2 + pytest-asyncio 1.3.0; testcontainers 4.14.1; ruff ~0.15
- **Build:** uv (uv_build>=0.9.21)
- **Local Infra:** Docker Compose (Kafka 7.5.0, Postgres 16, Redis 7.2, MinIO, Prometheus v2.50.1)

This release adds no new dependencies or technology choices.
