# Starter Template Evaluation

## Primary Technology Domain

Backend event-driven pipeline (Python 3.13) — brownfield project with established technology stack across 3 prior iterations.

## Starter Template Assessment

**Not applicable.** This is a brownfield project with a mature, production-validated technology stack. No starter template evaluation is needed — the baseline deviation feature extends the existing architecture without introducing new technologies or infrastructure dependencies.

## Existing Architectural Foundation

**Language & Runtime:**
- Python >=3.13 with asyncio for scheduler loops, health endpoint, and evidence collection
- Type hints using Python 3.13 style (X | None, built-in generics)

**Data Modeling:**
- Pydantic v2 with frozen=True for all contract and event models
- Contract-first design: payload shapes defined by frozen models, not ad-hoc dictionaries

**Pipeline Architecture:**
- Sequential deterministic stage pipeline: evidence → peak → topology → casefile → outbox → gating → dispatch
- Durable outbox pattern for Kafka publication decoupling
- Hot-path (deterministic) / cold-path (async LLM diagnosis) separation

**Infrastructure:**
- Redis 7.2 — dedupe cache, coordination locks, shard leases (and now: seasonal baselines)
- PostgreSQL 16 — durable outbox and linkage retry state
- Kafka (confluent-kafka 2.13.0) — case header and triage excerpt event publication
- Prometheus v2.50.1 — telemetry ingestion via instant query API
- MinIO (S3-compatible) — write-once casefile persistence with hash-chain integrity

**Observability:**
- OpenTelemetry SDK 1.39.1 + OTLP exporter for metrics
- structlog 25.5.0 for structured logging with correlation context
- HealthRegistry for component health state tracking

**Build & Test:**
- uv for dependency management and build
- pytest 9.0.2 + pytest-asyncio for unit/integration/ATDD testing
- testcontainers 4.14.1 for Docker-backed integration tests
- ruff ~0.15 for linting and style enforcement

**New Technology Additions Required:** None. All baseline deviation feature dependencies are satisfied by the existing stack.
