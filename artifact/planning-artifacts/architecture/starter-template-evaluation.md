# Starter Template Evaluation

## Primary Technology Domain

Python backend event-driven pipeline — established brownfield codebase with 8 delivered epics and comprehensive test coverage.

## Starter Template: Not Applicable (Brownfield)

This is a post-implementation revision phase against a mature, delivered codebase. No starter template evaluation is needed — the project structure, dependency graph, coding patterns, and tooling are established and stable.

## Established Technology Foundation

The following technology decisions are locked by the existing codebase and project context rules. These are not options to evaluate — they are constraints the architecture must work within.

**Language & Runtime:**
- Python >=3.13 with asyncio
- Type annotations using Python 3.13 style (`X | None`, built-in generics)
- `pyproject.toml` as source of truth for dependencies
- uv for package management and build

**Data Modeling & Validation:**
- Pydantic v2 (2.12.5) with frozen=True for all contract and policy models
- pydantic-settings ~2.13.1 for environment-bound configuration
- Validate at boundaries: on model creation and on deserialization from external I/O
- Schema envelope pattern for versioned persistence and Kafka events

**Persistence Layer:**
- PostgreSQL 16 via SQLAlchemy Core (2.0.47) — outbox and linkage retry tables
- Redis 7.2 (redis 7.2.1) — caching, coordination, deduplication
- MinIO / S3-compatible via boto3 ~1.42 — write-once casefile stages
- No ORM — SQLAlchemy Core for explicit SQL

**Messaging & Integration:**
- Kafka via confluent-kafka 2.13.0 — outbox publication and cold-path consumption
- Prometheus via HTTP client — instant query API for evidence collection
- PagerDuty Events V2, Slack webhook, ServiceNow table API — via adapter modules
- LangGraph 1.0.9 for cold-path LLM diagnosis orchestration

**Observability:**
- OpenTelemetry SDK 1.39.1 + OTLP exporter for metrics
- structlog 25.5.0 for structured JSON logging
- Correlation IDs (case_id) and pod identity in all telemetry

**Testing & Quality:**
- pytest 9.0.2 + pytest-asyncio 1.3.0 (asyncio_mode=auto)
- testcontainers 4.14.1 for Docker-backed integration tests
- ruff ~0.15 (line length 100, target py313, selection E,F,I,N,W)
- Unit tests under tests/unit/, integration tests under tests/integration/

**Local Infrastructure:**
- Docker Compose with Kafka/ZooKeeper 7.5.0, Postgres 16, Redis 7.2, MinIO, Prometheus v2.50.1

**Code Organization (Established):**
- `src/aiops_triage_pipeline/` — pipeline/, contracts/, models/, integrations/, storage/, outbox/, linkage/, health/, config/, denylist/, diagnosis/
- `tests/` — unit/ and integration/ mirroring domain packages
- `config/` — .env.* files, policies/*.yaml, denylist.yaml, topology registry
- Single entry point: `__main__.py` with --mode dispatch

**Note:** The revision phase adds new packages (coordination/, rule_engine/, cache/sustained_state.py) and new modules within existing packages but does not alter the established project structure or technology stack.
