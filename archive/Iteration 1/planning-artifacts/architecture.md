---
stepsCompleted: [1, 2, 3, 4, 5, 6, 7, 8]
lastStep: 8
status: 'complete'
completedAt: '2026-02-27'
stepProgress: |
  Step 4 - Core Architectural Decisions (COMPLETE)
  Category 1 (Data Architecture): COMPLETE
    - 1A: SQLAlchemy Core (not full ORM) — precise transactional control for outbox
    - 1B: Hand-rolled DDL (not Alembic) — single-table outbox, simple stable schema
    - 1C: Object storage layout — cases/{case_id}/{stage}.json (named stage files, no {env} prefix)
    - 1D: Redis key design — prefix by purpose (evidence:/peak:/dedupe:), no {env} prefix (dedicated infra per env)
  Category 2 (Security & Secrets): COMPLETE
    - 2A: Environment variables via pydantic-settings, file path validation for Kerberos auth artifacts at startup
    - 2B: Exposure denylist as versioned YAML, frozen Pydantic model, single shared apply_denylist() function
  Category 3 (Pipeline Communication & Serialization): COMPLETE
    - 3A: Direct Pydantic model passing in-memory, serialization only at I/O boundaries
    - 3B: Validate at creation (frozen=True) + re-validate on deserialization from external sources
    - 3C: JSON with Pydantic .model_dump_json() on Kafka, no schema registry
    - 3D: CaseFile stages as Pydantic JSON, SHA-256 hash for tamper-evidence, invariant test assertion
  Category 4 (Pipeline Orchestration): COMPLETE
    - 4A: Scheduler + asyncio.TaskGroup concurrent pipeline on 5-min wall-clock cadence
    - 4B: Fire-and-forget async LangGraph cold path, registered with HealthRegistry, in-flight gauge metric
    - 4C: Centralized HealthRegistry (asyncio-safe) + OpenTelemetry SDK with OTLP to Dynatrace, OTLP Collector stub in testcontainers
  Category 5 (Infrastructure & Deployment): COMPLETE
    - 5A: Single Docker image, multiple entrypoints (--mode hot-path|cold-path|outbox-publisher)
    - 5B: docker-compose with Kafka+ZooKeeper, Postgres, Redis, MinIO, Prometheus. APP_ENV selects .env.{APP_ENV}
    - 5C: CI/CD deferred, codebase structured CI-ready
    - 5D: Covered by 2A + 5B

  PRD corrections applied during previous session:
    - Deployment topology: all envs dedicated (Local/DEV/UAT/PROD), no shared infra
    - CaseFile naming: v1/v1.1/v1.2 → named stage files (triage/diagnosis/linkage/labels)
    - Schema evolution strategy documented in docs/schema-evolution-strategy.md
    - Mode B redefined: connection to dedicated remote env, not shared infra
    - Integration mode defaults: DEV=MOCK default, UAT=LIVE default

  Tech stack corrections applied (dependency audit 2026-02-27):
    - redis-py 7.1.1 → 7.2.1
    - LangGraph 1.0.7 → 1.0.9
    - pytest 9.1 → 9.0.2
    - prometheus-client removed, replaced by opentelemetry-sdk 1.39.1 + opentelemetry-exporter-otlp 1.39.1
    - psycopg pinned to psycopg[c] 3.3.3
    - pytest-asyncio pinned to 1.3.0
    - testcontainers pinned to 4.14.1
    - pydantic-settings pinned to ~2.13.1
inputDocuments:
  - artifact/planning-artifacts/prd/index.md
  - artifact/planning-artifacts/prd/executive-summary.md
  - artifact/planning-artifacts/prd/project-classification.md
  - artifact/planning-artifacts/prd/product-scope.md
  - artifact/planning-artifacts/prd/functional-requirements.md
  - artifact/planning-artifacts/prd/non-functional-requirements.md
  - artifact/planning-artifacts/prd/user-journeys.md
  - artifact/planning-artifacts/prd/success-criteria.md
  - artifact/planning-artifacts/prd/domain-specific-requirements.md
  - artifact/planning-artifacts/prd/innovation-novel-patterns.md
  - artifact/planning-artifacts/prd/project-scoping-phased-development.md
  - artifact/planning-artifacts/prd/event-driven-aiops-platform-specific-requirements.md
  - artifact/planning-artifacts/prd/open-items-deferred-design-decisions.md
  - artifact/planning-artifacts/prd/glossary-terminology.md
  - artifact/planning-artifacts/prd-validation-report.md
  - docs/schema-evolution-strategy.md
workflowType: 'architecture'
project_name: 'aiOps'
user_name: 'Sas'
date: '2026-02-26'
---

# Architecture Decision Document

_This document builds collaboratively through step-by-step discovery. Sections are appended as we work through each architectural decision together._

## Project Context Analysis

### Requirements Overview

**Functional Requirements:**

67 FRs organized into 10 architectural capability groups:

| Category | FRs | Architectural Implication |
|---|---|---|
| Evidence Collection & Processing | FR1–FR8 | Prometheus ingestion layer, 5-min evaluation cadence, UNKNOWN-not-zero propagation, Redis caching with env-specific TTLs |
| Topology & Ownership | FR9–FR16 | In-memory topology registry, v0/v1 schema support, instance-scoped (env, cluster_id) lookups, multi-level ownership resolution |
| CaseFile Management | FR17–FR21 | Write-once/append-only object storage, SHA-256 hash chain, data minimization, 25-month retention lifecycle |
| Event Publishing & Durability | FR22–FR26 | Postgres durable outbox (Invariant B2), Kafka header/excerpt publish, exposure denylist on TriageExcerpt |
| Action Gating & Safety | FR27–FR35 | Deterministic Rulebook engine (AG0–AG6), sequential gate evaluation, dedupe via Redis, degraded-mode caps |
| Diagnosis & Intelligence | FR36–FR42, FR66 | Cold-path LLM invocation, non-blocking, schema-validated output, deterministic fallback, stub/failure-injection modes |
| Notification & Action Execution | FR43–FR50 | PagerDuty PAGE triggers, Slack notifications, SN tiered correlation + idempotent upsert, structured log fallback |
| Operability & Monitoring | FR51–FR54, FR67 | DegradedModeEvent/TelemetryDegradedEvent emission, outbox health alerting, DEAD=0 prod posture |
| Local Development & Testing | FR55–FR59 | docker-compose Mode A (zero external), Mode B (opt-in shared), OFF/LOG/MOCK/LIVE integration modes |
| Governance & Audit | FR60–FR65, FR67 | Policy version stamping, decision reproducibility, exposure denylist governance, MI-1 posture (no automated MI creation) |

**Non-Functional Requirements:**

24 NFRs across 5 categories driving architectural decisions:

- **Performance (NFR-P1a–P6):** p95 ≤ 30s compute latency, p95 ≤ 1min outbox delivery SLO, sub-second Rulebook gating, 60s LLM timeout, 50ms registry lookup, 100 concurrent cases per interval
- **Security (NFR-S1–S8):** TLS 1.2+ in transit, SSE at rest, CaseFile access control, secrets manager for credentials, exposure denylist at every output boundary, LLM data handling constraints
- **Reliability (NFR-R1–R5):** Component-specific degraded modes (Redis/LLM/Slack/SN continue; Object Storage/Postgres/Kafka halt), recovery behaviors, DEAD=0 prod posture, infrastructure-level durability
- **Operability (NFR-O1–O6):** Meta-monitoring for all components, alerting thresholds, structured JSON logging, configuration transparency, deployment independence, graceful shutdown
- **Testability (NFR-T1–T6):** Decision reproducibility, invariant verification, LLM degradation testing, storm-control simulation, end-to-end pipeline test, audit trail completeness

**Scale & Complexity:**

- Primary domain: Backend event-driven pipeline / infrastructure operations tooling
- Complexity level: Enterprise/High
- Estimated architectural components: ~15–20 distinct components across hot path, cold path, stores, and integrations
- 12 frozen contracts constraining design space
- 5-phase delivery (Phase 0 → 1A → 1B → 2 → 3) with cross-phase data dependencies

### Technical Constraints & Dependencies

- **Frozen contracts (12):** Rulebook-v1, GateInput-v1, CaseHeaderEvent-v1, TriageExcerpt-v1, ActionDecision-v1, DiagnosisReport-v1, prometheus-metrics-contract-v1, redis-ttl-policy-v1, outbox-policy-v1, peak-policy-v1, servicenow-linkage-contract-v1, local-dev-no-external-integrations-contract-v1, topology-registry-loader-rules-v1
- **Durability invariants:** Invariant A (write-before-publish), Invariant B2 (publish-after-crash) — non-negotiable
- **Hot/cold path separation:** LLM never in the routing/paging path; hot path stages 1–7 must complete without LLM
- **Environment isolation:** local=OBSERVE cap, dev=NOTIFY cap, uat=TICKET cap, prod=PAGE eligible (TIER_0 only). All environments (DEV, UAT, PROD) have dedicated infrastructure — no shared clusters.
- **Deployment topology:** Local (docker-compose), DEV (dedicated), UAT (dedicated), PROD (dedicated). Mode B (not in MVP) connects to a specific dedicated environment, not shared infra.
- **Integration dependencies:** Prometheus (sole telemetry source), Kafka (event transport), Object Storage (CaseFile SoR), Postgres (outbox), Redis (cache-only, degradable)
- **Banking regulatory:** 25-month CaseFile retention, tamper-evident hashing, MI-1 posture, exposure controls, least-privilege integrations

### Cross-Cutting Concerns Identified

- **Exposure denylist enforcement:** Must be applied at every output boundary — TriageExcerpt assembly, Slack formatting, SN descriptions, LLM narrative surfacing. Requires a centralized, versioned denylist with boundary-specific enforcement points.
- **Evidence truthfulness (UNKNOWN-not-zero):** Missing Prometheus series → EvidenceStatus=UNKNOWN propagated through peak, sustained, confidence, and gating. Every layer must handle UNKNOWN as a first-class signal, not a default/zero.
- **Policy version stamping:** Every CaseFile records exact versions of all active policies. Enables decision replay for audit. Requires versioned policy loading with version capture at decision time.
- **Integration mode abstraction:** All 9 external integrations support OFF/LOG/MOCK/LIVE modes. Requires a uniform integration gateway/adapter pattern with mode-aware behavior.
- **Degraded-mode safety:** Component-specific failure modes with distinct behaviors (Redis → NOTIFY-only, Prometheus → cap OBSERVE/NOTIFY, LLM → deterministic fallback, Object Storage/Postgres → halt). Requires health-aware orchestration with per-component degradation strategies.
- **Storm control:** Dedupe across PAGE/TICKET/NOTIFY with per-type TTLs + degraded-mode caps. Prevents paging storms structurally.
- **Structured logging with correlation:** All events carry case_id as correlation_id, structured JSON, consistent fields. Requires a logging framework with contextual propagation.
- **Meta-monitoring:** The AIOps system must observe itself — outbox health, Redis status, LLM availability, evidence builder cadence, pipeline latency. Requires Prometheus metrics exposure from pipeline components.

## Starter Template Evaluation

### Primary Technology Domain

Backend event-driven pipeline (Python) — no frontend, no API consumers. Core is a data processing pipeline with Kafka, Postgres, Redis, Object Storage, and Prometheus integrations.

### Starter Options Considered

| Option | Verdict | Reason |
|---|---|---|
| `uv init` + manual structure | Selected | No generic template fits a 7-stage hot path + 5-stage cold path pipeline with 12 frozen contracts |
| Copier + `copier-uv` template | Rejected | Library/package oriented; includes irrelevant concerns (PyPI publishing, changelog) |
| Cookiecutter data science templates | Rejected | Wrong paradigm for event-driven triage pipeline |

### Selected Starter: `uv init`

**Rationale:** The project architecture is unique — deterministic safety gates, durability invariants, hot/cold path separation, 12 frozen contracts. No generic template provides value; a custom `src/` layout built on `uv init` is the pragmatic foundation.

**Initialization Command:**

```bash
uv init --python 3.13 --package --name aiops-triage-pipeline
```

### Architectural Decisions Provided by Starter

**Language & Runtime:** Python 3.13 (stable) with `pyproject.toml` (PEP 621), `src/` layout. Python 3.14 deferred for banking stability.

**Package Management:** uv 0.10.6 — fast dependency resolution, virtual environments, Python version management

**Linting/Formatting:** Ruff ~0.15.x — single tool replacing black+flake8+isort

**Testing:** pytest 9.0.2 + pytest-asyncio 1.3.0 + testcontainers 4.14.1 for programmatic test infrastructure

**Logging:** structlog 25.5.0 — structured JSON logging with correlation_id propagation

### Technology Stack

| Layer | Tool | Version | Rationale |
|---|---|---|---|
| Runtime | Python | 3.13 | Stable, asyncio TaskGroup, banking-appropriate |
| Package manager | uv | 0.10.6 | Fast, modern, replaces pip/poetry/virtualenv |
| Linting/Formatting | Ruff | ~0.15.4 | Single tool, Rust-backed speed |
| Kafka client | confluent-kafka | 2.13.0 | Production-grade, C-backed, synchronous producer for outbox pattern |
| Postgres | SQLAlchemy 2.0 + psycopg[c] | 2.0.47 + 3.3.3 | Async support, C-optimized driver, outbox state machine |
| Data validation | Pydantic v2 | 2.12.5 | Frozen contract enforcement engine + config management |
| Redis | redis-py | 7.2.1 | Async built-in, cache + dedupe |
| Object storage | boto3 | ~1.42 | Universal S3-compatible client — works with MinIO locally and NetApp S3 in prod |
| Metrics/Telemetry | opentelemetry-sdk + otlp exporter | 1.39.1 | OTLP export to Dynatrace, vendor-neutral meta-monitoring |
| LLM orchestration | LangGraph | 1.0.9 | Cold-path diagnosis state graph with retry/fallback. Bank-approved framework. Minimal single-node graph usage. |
| Testing | pytest + pytest-asyncio + testcontainers | 9.0.2 + 1.3.0 + 4.14.1 | Async tests, programmatic Docker infrastructure |
| Logging | structlog | 25.5.0 | Structured JSON, correlation_id, processor pipeline |
| Config | pydantic-settings | ~2.13.1 | Env-based config, APP_ENV file selection, pairs with Pydantic v2 |

### Key Design Decisions (Party Mode Review)

- **Dropped aiokafka** — confluent-kafka only for simpler dependency tree; outbox publisher is synchronous
- **boto3 over minio SDK** — universal S3 compatibility without code changes between local MinIO and prod object store
- **No FastAPI** — lightweight HTTP handler sufficient for /health endpoint; metrics exported via OTLP to Dynatrace
- **Added testcontainers-python** — programmatic test infrastructure in pytest fixtures for clean CI
- **Pydantic v2 as contract enforcement engine** — frozen contracts (GateInput.v1, ActionDecision.v1, etc.) map to `frozen=True` Pydantic models; schema validation on LLM DiagnosisReport output is `model_validate()`

**Note:** Project initialization using this command should be the first implementation story.

## Core Architectural Decisions

### Decision Priority Analysis

**Critical Decisions (Block Implementation):**

- Data architecture patterns (1A–1D): SQLAlchemy Core, hand-rolled DDL, object storage layout, Redis key design
- Secrets management (2A): Environment variables via pydantic-settings
- Exposure denylist enforcement (2B): Versioned YAML, single shared function
- Pipeline orchestration (4A–4C): Scheduler + asyncio.TaskGroup, fire-and-forget cold path, centralized HealthRegistry
- Contract enforcement (3B): Validate at creation + I/O boundaries
- Serialization format (3C–3D): JSON with Pydantic everywhere

**Important Decisions (Shape Architecture):**

- Container strategy (5A): Single image, multiple entrypoints
- Environment config (5B/5D): APP_ENV + .env files + pydantic-settings
- Meta-monitoring export (4C): OpenTelemetry SDK with OTLP to Dynatrace

**Deferred Decisions (Post-MVP):**

- CI/CD pipeline definitions (5C): Codebase structured CI-ready; bank Git Actions integration deferred
- Mode B implementation: Config supports it, not in MVP scope

### Data Architecture

_Decisions 1A–1D were completed in the prior session._

- **1A: Database access layer** — SQLAlchemy Core (not full ORM). Precise transactional control needed for outbox state machine. ORM abstractions would obscure the exact SQL semantics required for PENDING_OBJECT → READY → SENT transitions.
- **1B: Schema management** — Hand-rolled DDL (not Alembic). The outbox is a single stable table. Alembic adds migration infrastructure overhead for a schema that won't evolve frequently. Schema evolution strategy documented in `docs/schema-evolution-strategy.md`.
- **1C: Object storage layout** — `cases/{case_id}/{stage}.json` with named stage files (triage.json, diagnosis.json, linkage.json, labels.json). No environment prefix — each environment has dedicated infrastructure.
- **1D: Redis key design** — Prefix by purpose: `evidence:{key}`, `peak:{key}`, `dedupe:{key}`. No environment prefix — dedicated Redis instance per environment.

### Security & Secrets

- **2A: Secrets management** — Environment variables via `pydantic-settings`. Deployment platform (K8s) handles actual secret storage and injection. Rotation = redeploy (PRD allows pipeline restart for credential rotation per NFR-S4). Settings model supports file path references for Kerberos auth artifacts (`KAFKA_KERBEROS_KEYTAB_PATH`, `KRB5_CONF_PATH`). Startup validation asserts referenced files exist when `KAFKA_SECURITY_PROTOCOL=SASL_SSL` — fail-fast at boot, not mid-pipeline.
- **2B: Exposure denylist implementation** — Versioned YAML file in the repository (git-tracked, reviewable in PRs, security-sensitive changes require explicit approval). Loaded at startup into a `frozen=True` Pydantic model. Enforcement via a single shared function `apply_denylist(fields: dict, denylist: DenylistModel) -> dict` — all 4 output boundaries (TriageExcerpt assembly, Slack formatting, SN descriptions, LLM narrative surfacing) call this function. No per-boundary reimplementation. `denylist_version` stamped into every CaseFile for audit traceability.

### Pipeline Communication & Serialization

- **3A: Internal stage-to-stage data passing** — Direct Pydantic model passing in-memory between hot path stages. No serialization between stages. Serialization occurs only at true I/O boundaries (object storage writes, Kafka publishes, Redis cache operations).
- **3B: Frozen contract enforcement** — Validate at creation via Pydantic `frozen=True` models (immutable after construction). Re-validate on deserialization from external sources (`model_validate_json()`). No redundant mid-pipeline validation — frozen guarantees immutability between creation and I/O boundary.
- **3C: Kafka message format** — JSON with Pydantic `.model_dump_json()` serialization. No schema registry. Contracts are frozen — schema evolution features of Avro/Protobuf not needed. Human-readable messages simplify debugging and audit. Payload is small (header + excerpt, not raw telemetry).
- **3D: CaseFile serialization** — Each stage file (triage.json, diagnosis.json, etc.) serialized via Pydantic `.model_dump_json()`. SHA-256 hash computed over the serialized JSON bytes before writing to object storage. Hash stored in outbox record for tamper-evidence verification. On read-back, `model_validate_json()` deserializes + validates (per 3B). SHA-256 hash verification is an invariant assertion in every integration test run — recompute from stored bytes, compare to recorded hash. Failure = potential tamper event (regulatory incident).

### Pipeline Orchestration

- **4A: Hot path orchestration** — Scheduler fires on 5-minute wall-clock cadence (aligned to :00, :05, :10, etc. per NFR-P2). Each cycle collects evidence, then processes all qualifying cases concurrently via `asyncio.TaskGroup`. Each case flows through stages 1–7 as an independent async task. Handles 100 concurrent cases within p95 ≤ 30s latency target (NFR-P6). Natural fit for I/O-bound work (Prometheus queries, storage writes, Redis operations).
- **4B: Cold path orchestration** — Fire-and-forget async LangGraph invocation from the hot path. When a case qualifies for LLM diagnosis (PROD+TIER_0, sustained anomaly, etc.), the hot path spawns an async LangGraph task that writes `diagnosis.json` on completion. Hot path never waits on LLM. LangGraph handles the state graph (retry, timeout, fallback). On LLM timeout (60s per NFR-P4) or failure, deterministic fallback DiagnosisReport written immediately (verdict=UNKNOWN, confidence=LOW, reason_codes=[LLM_TIMEOUT]). Fire-and-forget tasks registered with HealthRegistry — in-flight diagnosis count exposed as an OTLP gauge metric. Alert threshold if in-flight count exceeds configurable max without draining.
- **4C: Error handling & degraded mode coordination** — Centralized `HealthRegistry` singleton tracking per-component status (HEALTHY/DEGRADED/UNAVAILABLE). Components update status on connection failure/recovery. Pipeline stages query registry to apply degraded-mode caps (e.g., Redis DEGRADED → NOTIFY-only per AG5). HealthRegistry uses asyncio-safe primitives (not threading locks). Single source of truth for `/health` endpoint and `DegradedModeEvent`/`TelemetryDegradedEvent` emission. Meta-monitoring metrics (outbox depth, pipeline latency, component health, LLM error rate, evaluation adherence) exported via OpenTelemetry SDK with OTLP protocol to Dynatrace. Integration test suite includes OpenTelemetry Collector container (via testcontainers) as OTLP receiver stub — tests assert correct metric names, labels, and values. Meta-monitoring is not deferred to UAT.

### Infrastructure & Deployment

- **5A: Container strategy** — Single Docker image with multiple entrypoints via `--mode` flag: `hot-path`, `cold-path`, `outbox-publisher`. One codebase, one build, deployable as separate services. In Phase 0/1A, all modes can run as a single container. As scaling demands grow, split into separate K8s deployments of the same image.
- **5B: Local dev orchestration** — docker-compose Mode A topology: pipeline + Kafka + ZooKeeper + Postgres + Redis + MinIO + Prometheus. ZooKeeper retained for parity with production Kafka clusters. PagerDuty/Slack/ServiceNow default to LOG mode locally (no mock servers needed — Mode B available for real integration testing). Environment selection via `APP_ENV` variable: `APP_ENV=local|dev|uat|prod` loads corresponding `.env.{APP_ENV}` config file. `pydantic-settings` precedence: direct env vars (K8s injected) > `.env` file > safe defaults. `.env.local` and `.env.dev` committed to repo (no secrets). `.env.uat` and `.env.prod` are templates only — real values injected by K8s. Kafka auth: PLAINTEXT for local, SASL_SSL + GSSAPI/Kerberos for remote (DEV/UAT/PROD). Object storage: MinIO locally, NetApp S3 in higher environments — boto3 works with both via `S3_ENDPOINT_URL` config.
- **5C: CI/CD** — Deferred. Codebase structured to be CI-ready: standard lint command (`uv run ruff check`), test commands (`uv run pytest`), layered test structure (unit vs integration with testcontainers), clean Dockerfile. No pipeline definitions in repo. Bank's Git Actions integration handled separately when ready.
- **5D: Environment configuration** — Covered by decisions 2A and 5B. `pydantic-settings` with `APP_ENV` file selection. Per-environment action caps: local=OBSERVE, dev=NOTIFY, uat=TICKET, prod=PAGE. Per-integration mode vars: `INTEGRATION_MODE_{PD|SLACK|SN|LLM}` = OFF/LOG/MOCK/LIVE. Active configuration logged at startup per NFR-O4. Integration mode changes require deployment (NFR-S7) — config read at startup only, no runtime toggles.

### Decision Impact Analysis

**Implementation Sequence:**

1. Project initialization (`uv init`, directory structure, pyproject.toml with all pinned dependencies)
2. Pydantic contract models (frozen=True) for all 12 frozen contracts
3. Configuration layer (pydantic-settings, APP_ENV, .env files, Kerberos support)
4. Exposure denylist (YAML + Pydantic model + apply_denylist function)
5. HealthRegistry singleton (asyncio-safe, component status tracking)
6. Data layer (SQLAlchemy Core outbox, boto3 object storage, redis-py cache)
7. Hot path pipeline (scheduler, asyncio.TaskGroup, stages 1–7)
8. Cold path (LangGraph diagnosis, fire-and-forget integration with HealthRegistry)
9. Outbox publisher (Kafka JSON publish, confluent-kafka)
10. OpenTelemetry instrumentation (OTLP export, meta-monitoring metrics)
11. docker-compose topology (Kafka+ZooKeeper, Postgres, Redis, MinIO, Prometheus)
12. Integration test infrastructure (testcontainers + OTLP Collector stub)

**Cross-Component Dependencies:**

- HealthRegistry (4C) is consumed by hot path (4A), cold path (4B), and OTLP export — must be implemented early
- Pydantic contract models (3B) are used by every pipeline stage, serialization layer, and Kafka publisher — foundational
- Exposure denylist (2B) is enforced at 4 output boundaries — single function, multiple callers
- APP_ENV config (5B/5D) is consumed by every component for connection strings and integration modes — foundational
- SHA-256 hash (3D) couples CaseFile writes to outbox records — must be implemented together
- asyncio.TaskGroup (4A) and fire-and-forget (4B) share the same event loop — cold path tasks must not block the scheduler

## Implementation Patterns & Consistency Rules

### Pattern Categories Defined

**5 critical conflict areas** identified where AI agents could make different implementation choices, leading to incompatible code. Patterns below ensure consistency.

### Naming Patterns

**Python Code (PEP 8):**
- Modules/packages: `snake_case` (e.g., `evidence_builder`, `peak_detector`)
- Functions/variables: `snake_case` (e.g., `evaluate_case`, `case_id`)
- Classes: `PascalCase` (e.g., `HealthRegistry`, `OutboxPublisher`)
- Constants: `UPPER_SNAKE_CASE` (e.g., `MAX_LLM_TIMEOUT`, `DEFAULT_EVALUATION_INTERVAL`)

**Database:**
- Table names: `snake_case` (e.g., `outbox`)
- Column names: `snake_case` (e.g., `case_id`, `created_at`, `publish_state`)

**JSON Fields (Kafka messages, CaseFiles):**
- `snake_case` — Pydantic default serialization, no alias mapping required
- Example: `{"case_id": "...", "evidence_status": "UNKNOWN", "created_at": "2026-02-27T14:30:00Z"}`

**Kafka Topics:**
- `dash-separated`, no version suffix in topic name — org convention
- Examples: `aiops-case-header`, `aiops-triage-excerpt`

**Redis Keys:**
- `colon:separated` by purpose prefix
- Examples: `evidence:{case_id}`, `peak:{stream_id}`, `dedupe:{action_type}:{case_id}`

**Pydantic Contract Models:**
- `PascalCase` with version suffix matching frozen contract names
- Examples: `GateInputV1`, `CaseHeaderEventV1`, `ActionDecisionV1`, `DiagnosisReportV1`

### Structure Patterns

**Project Organization:**

```
src/aiops_triage_pipeline/
├── config/              # pydantic-settings, APP_ENV, .env loading
├── contracts/           # All 12 frozen Pydantic models (v1)
├── denylist/            # Exposure denylist YAML + model + apply_denylist()
├── health/              # HealthRegistry singleton, OTLP export
├── integrations/        # Integration adapters (kafka, pagerduty, slack, sn, llm)
│   └── each with OFF/LOG/MOCK/LIVE mode support
├── outbox/              # SQLAlchemy Core outbox, state machine, publisher
├── pipeline/            # Hot path orchestration
│   ├── scheduler.py     # 5-min cadence scheduler
│   └── stages/          # Stage 1-7 implementations
├── diagnosis/           # Cold path LangGraph invocation (minimal single-node graph)
├── storage/             # Object storage (boto3), CaseFile read/write + SHA-256 hash
├── cache/               # Redis operations, dedupe, evidence windows
├── registry/            # Topology registry, in-memory loader
├── logging/             # structlog config, correlation_id propagation
└── models/              # Internal (non-contract) domain models
```

```
tests/
├── unit/                # Fast, no containers, mirrors src/ structure
├── integration/         # testcontainers (Postgres, Redis, Kafka, MinIO, OTLP Collector)
└── conftest.py          # Shared universal fixtures
```

```
config/
├── .env.local           # Mode A defaults (committed, no secrets)
├── .env.dev             # DEV cluster connections (committed, no secrets)
├── .env.uat.template    # UAT template (not committed with real values)
├── .env.prod.template   # PROD template (not committed with real values)
├── denylist.yaml        # Versioned exposure denylist
└── policies/            # Rulebook, peak policy, etc. (versioned YAML)
```

**Key Boundaries:**
- `contracts/` (frozen v1) separate from `models/` (internal mutable)
- Each major component (`pipeline/`, `diagnosis/`, `outbox/`) has clean import boundaries — no cross-reaching into internals
- Shared code in explicit shared packages (`contracts/`, `config/`, `health/`, `models/`)
- Monolith with clean module boundaries — extractable into separate services if scaling demands it

### Format Patterns

**Datetime Representation:**
- ISO 8601 strings with UTC timezone: `"2026-02-27T14:30:00Z"`
- Pydantic serialization handles conversion automatically
- Human-readable in CaseFiles, audit-friendly

**Enum Serialization:**
- String values in JSON: `"HEALTHY"`, `"DEGRADED"`, `"UNKNOWN"`, `"PENDING_OBJECT"`, `"READY"`, `"SENT"`
- Self-documenting — no lookup table required
- Python enums use `str, Enum` mixin for automatic string serialization

**Null Handling:**
- Explicit `null` in JSON — never omit null fields
- A missing field and a `null` field are semantically different
- Prevents ambiguity for agents and systems parsing CaseFiles
- Pydantic: use `Optional[T] = None`, never exclude from serialization

### Error Handling Patterns

**Custom Exception Hierarchy:**

```python
class PipelineError(Exception): ...

# Critical path — halt pipeline (NFR-R2)
class InvariantViolation(PipelineError): ...       # Invariant A/B2 broken — NEVER catch
class CriticalDependencyError(PipelineError): ...  # Postgres/Object Storage down

# Degradable — HealthRegistry update, continue with caps (NFR-R1)
class DegradableError(PipelineError): ...
class RedisUnavailable(DegradableError): ...
class LLMUnavailable(DegradableError): ...
class SlackUnavailable(DegradableError): ...

# Integration errors
class IntegrationError(PipelineError): ...         # PD/SN/Slack call failures
```

**Rules:**
- `InvariantViolation` → always halt, never catch — regulatory concern
- `CriticalDependencyError` → pipeline halts with explicit alerting
- `DegradableError` → HealthRegistry updated, pipeline continues with degraded-mode caps
- Integration boundaries wrap built-in Python exceptions (`ConnectionError`, `TimeoutError`) into appropriate custom types
- No raw exceptions leaking through pipeline stages

### Testing Patterns

**Test File Naming:**
- Mirror source file names with `test_` prefix
- `src/.../stages/evidence.py` → `tests/unit/pipeline/stages/test_evidence.py`
- Predictable — agents cannot invent their own naming

**Fixture Organization:**
- `tests/conftest.py` — universal fixtures (mock config, test constants)
- `tests/integration/conftest.py` — testcontainers setup (Postgres, Redis, Kafka, MinIO, OTLP Collector)
- No reusable fixtures defined inside individual test files — always in `conftest.py`

**Assertions:**
- Plain `assert` — pytest rewrites for readable failure output
- Pydantic model comparison via `==` (models support equality)
- No external assertion/matcher libraries

**Test Markers:**
- `@pytest.mark.integration` on all testcontainer-based tests
- `pytest -m "not integration"` runs fast unit tests only
- CI can run unit and integration separately

### Enforcement Guidelines

**All AI Agents MUST:**

- Follow PEP 8 naming without exception — Ruff enforces automatically
- Place new files in the correct package per the structure above — no ad-hoc directories
- Use `snake_case` for all JSON fields — no camelCase aliases
- Wrap integration errors in custom exception types — no raw exceptions in pipeline stages
- Write tests that mirror source structure with `test_` prefix
- Use `@pytest.mark.integration` on any test that requires Docker containers
- Serialize datetimes as ISO 8601 UTC, enums as string values, nulls as explicit `null`
- Keep module boundaries clean — `pipeline/` does not import from `diagnosis/` internals and vice versa

**Pattern Enforcement:**
- Ruff handles code style automatically
- PR review should verify structural patterns (file placement, naming, exception usage)
- Integration test suite validates cross-component consistency at runtime

## Project Structure & Boundaries

### Complete Project Directory Structure

```
aiops-triage-pipeline/
├── pyproject.toml                     # PEP 621, uv, all pinned dependencies
├── uv.lock                            # Locked dependency resolution
├── Dockerfile                         # Single image, multi-entrypoint
├── docker-compose.yml                 # Mode A: full local stack
├── .gitignore
├── .python-version                    # 3.13 (uv managed)
│
├── config/
│   ├── .env.local                     # Mode A defaults (committed)
│   ├── .env.dev                       # DEV connections (committed, no secrets)
│   ├── .env.uat.template              # UAT template (not committed with real values)
│   ├── .env.prod.template             # PROD template (not committed with real values)
│   ├── denylist.yaml                  # Versioned exposure denylist
│   └── policies/                      # Versioned policy artifacts
│       ├── rulebook-v1.yaml
│       ├── peak-policy-v1.yaml
│       ├── redis-ttl-policy-v1.yaml
│       ├── outbox-policy-v1.yaml
│       └── prometheus-metrics-contract-v1.yaml
│
├── src/aiops_triage_pipeline/
│   ├── __init__.py
│   ├── __main__.py                    # Entrypoint: --mode hot-path|cold-path|outbox-publisher
│   │
│   ├── config/
│   │   ├── __init__.py
│   │   └── settings.py               # pydantic-settings, APP_ENV, .env loading, Kerberos validation
│   │
│   ├── contracts/                     # All 12 frozen Pydantic models
│   │   ├── __init__.py
│   │   ├── gate_input.py              # GateInputV1
│   │   ├── action_decision.py         # ActionDecisionV1
│   │   ├── case_header_event.py       # CaseHeaderEventV1
│   │   ├── triage_excerpt.py          # TriageExcerptV1
│   │   ├── diagnosis_report.py        # DiagnosisReportV1
│   │   ├── rulebook.py               # RulebookV1
│   │   ├── peak_policy.py            # PeakPolicyV1
│   │   ├── redis_ttl_policy.py       # RedisTtlPolicyV1
│   │   ├── outbox_policy.py          # OutboxPolicyV1
│   │   ├── prometheus_metrics.py     # PrometheusMetricsContractV1
│   │   ├── sn_linkage.py             # ServiceNowLinkageContractV1
│   │   └── topology_registry.py      # TopologyRegistryLoaderRulesV1
│   │
│   ├── models/                        # Internal (non-contract) domain models
│   │   ├── __init__.py
│   │   ├── case_file.py              # CaseFile stage models (triage, diagnosis, etc.)
│   │   ├── evidence.py               # EvidenceSnapshot, EvidenceStatus enum
│   │   ├── peak.py                   # PeakResult, SustainedStatus
│   │   ├── health.py                 # HealthStatus enum, ComponentHealth
│   │   └── events.py                 # DegradedModeEvent, TelemetryDegradedEvent
│   │
│   ├── errors/                        # Custom exception hierarchy
│   │   ├── __init__.py
│   │   └── exceptions.py             # PipelineError, InvariantViolation, DegradableError, etc.
│   │
│   ├── denylist/                      # Exposure denylist enforcement
│   │   ├── __init__.py
│   │   ├── loader.py                 # YAML → frozen Pydantic model at startup
│   │   └── enforcement.py            # apply_denylist() — single shared function
│   │
│   ├── health/                        # HealthRegistry + telemetry
│   │   ├── __init__.py
│   │   ├── registry.py               # HealthRegistry singleton (asyncio-safe)
│   │   ├── metrics.py                # OTLP metric definitions and export
│   │   └── server.py                 # /health HTTP endpoint
│   │
│   ├── pipeline/                      # Hot path orchestration
│   │   ├── __init__.py
│   │   ├── scheduler.py              # 5-min wall-clock cadence, asyncio.TaskGroup
│   │   └── stages/
│   │       ├── __init__.py
│   │       ├── evidence.py           # Stage 1: Prometheus query, evidence snapshot
│   │       ├── peak.py               # Stage 2: Peak detection against policy
│   │       ├── topology.py           # Stage 3: Registry lookup, ownership resolution
│   │       ├── casefile.py           # Stage 4: CaseFile assembly, object storage write, SHA-256
│   │       ├── outbox.py             # Stage 5: Outbox insert, trigger publish
│   │       ├── gating.py             # Stage 6: Rulebook AG0-AG6, ActionDecision
│   │       └── dispatch.py           # Stage 7: Action execution via integration adapters
│   │
│   ├── diagnosis/                     # Cold path LLM
│   │   ├── __init__.py
│   │   ├── graph.py                  # LangGraph single-node diagnosis graph
│   │   ├── prompt.py                 # Prompt construction from excerpt + evidence
│   │   └── fallback.py              # Deterministic fallback DiagnosisReport
│   │
│   ├── outbox/                        # Durable outbox
│   │   ├── __init__.py
│   │   ├── schema.py                 # SQLAlchemy Core table definition (hand-rolled DDL)
│   │   ├── state_machine.py          # PENDING_OBJECT → READY → SENT (+ RETRY, DEAD)
│   │   └── publisher.py             # Kafka publish from outbox, confluent-kafka
│   │
│   ├── storage/                       # Object storage
│   │   ├── __init__.py
│   │   ├── client.py                 # boto3 S3 client (MinIO local, NetApp S3 prod)
│   │   └── casefile_io.py            # CaseFile read/write, SHA-256 hash computation
│   │
│   ├── cache/                         # Redis operations
│   │   ├── __init__.py
│   │   ├── client.py                 # redis-py async client
│   │   ├── evidence_window.py        # Evidence window caching
│   │   ├── peak_cache.py             # Peak profile caching
│   │   └── dedupe.py                 # Storm control deduplication
│   │
│   ├── registry/                      # Topology registry
│   │   ├── __init__.py
│   │   ├── loader.py                 # In-memory topology load at startup
│   │   └── resolver.py              # Anomaly key → stream_id, ownership, tier
│   │
│   ├── integrations/                  # External integration adapters
│   │   ├── __init__.py
│   │   ├── base.py                   # Base adapter with OFF/LOG/MOCK/LIVE mode support
│   │   ├── prometheus.py             # Prometheus query client
│   │   ├── kafka.py                  # Kafka producer/consumer (confluent-kafka)
│   │   ├── pagerduty.py              # PD trigger adapter
│   │   ├── slack.py                  # Slack notification adapter
│   │   ├── servicenow.py             # SN tiered correlation adapter (Phase 1B)
│   │   └── llm.py                    # LLM endpoint adapter (bank-sanctioned)
│   │
│   └── logging/                       # Structured logging
│       ├── __init__.py
│       └── setup.py                  # structlog config, correlation_id propagation
│
├── tests/
│   ├── conftest.py                    # Universal fixtures (mock config, test constants)
│   ├── unit/
│   │   ├── conftest.py
│   │   ├── config/
│   │   │   └── test_settings.py
│   │   ├── contracts/
│   │   │   └── test_frozen_models.py  # Validate all 12 contracts are frozen, schema-correct
│   │   ├── denylist/
│   │   │   ├── test_loader.py
│   │   │   └── test_enforcement.py    # Negative tests: denied fields absent at all boundaries
│   │   ├── health/
│   │   │   └── test_registry.py
│   │   ├── errors/
│   │   │   └── test_exceptions.py
│   │   ├── pipeline/
│   │   │   └── stages/
│   │   │       ├── test_evidence.py
│   │   │       ├── test_peak.py
│   │   │       ├── test_topology.py
│   │   │       ├── test_casefile.py
│   │   │       ├── test_outbox.py
│   │   │       ├── test_gating.py
│   │   │       └── test_dispatch.py
│   │   ├── diagnosis/
│   │   │   ├── test_graph.py
│   │   │   └── test_fallback.py
│   │   ├── outbox/
│   │   │   └── test_state_machine.py
│   │   ├── storage/
│   │   │   └── test_casefile_io.py    # SHA-256 hash computation tests
│   │   ├── cache/
│   │   │   └── test_dedupe.py
│   │   └── integrations/
│   │       └── test_base_adapter.py   # Mode switching tests
│   └── integration/
│       ├── conftest.py                # testcontainers setup (Postgres, Redis, Kafka, MinIO, OTLP)
│       ├── test_outbox_publish.py     # Invariant B2: publish-after-crash
│       ├── test_casefile_write.py     # Invariant A: write-before-publish + hash verification
│       ├── test_pipeline_e2e.py       # Full hot path: evidence → action (NFR-T5)
│       ├── test_degraded_modes.py     # Redis down → NOTIFY-only, storm control (NFR-T4)
│       ├── test_denylist_boundaries.py # All 4 output boundaries enforce denylist (NFR-S5)
│       ├── test_otlp_export.py        # OTLP Collector stub validates metric export
│       └── test_audit_trail.py        # Auditor persona: CaseFile → evidence → gating → action (NFR-T6)
│
└── docs/
    └── schema-evolution-strategy.md   # Already exists
```

### FR Categories → Structure Mapping

| FR Category | Primary Package | Key Files |
|---|---|---|
| Evidence Collection (FR1–FR8) | `pipeline/stages/`, `integrations/prometheus.py`, `cache/` | `evidence.py`, `evidence_window.py` |
| Topology & Ownership (FR9–FR16) | `registry/` | `loader.py`, `resolver.py` |
| CaseFile Management (FR17–FR21) | `storage/`, `models/case_file.py` | `casefile_io.py`, `casefile.py` |
| Event Publishing (FR22–FR26) | `outbox/`, `integrations/kafka.py` | `state_machine.py`, `publisher.py` |
| Action Gating (FR27–FR35) | `pipeline/stages/`, `contracts/` | `gating.py`, `gate_input.py`, `rulebook.py` |
| Diagnosis (FR36–FR42, FR66) | `diagnosis/`, `integrations/llm.py` | `graph.py`, `fallback.py` |
| Notifications (FR43–FR50) | `pipeline/stages/`, `integrations/` | `dispatch.py`, `pagerduty.py`, `slack.py`, `servicenow.py` |
| Operability (FR51–FR54, FR67) | `health/`, `logging/` | `registry.py`, `metrics.py` |
| Local Dev (FR55–FR59) | `config/`, `docker-compose.yml` | `settings.py`, `.env.*` |
| Governance (FR60–FR65) | `denylist/`, `contracts/`, `config/policies/` | `enforcement.py`, versioned policy YAMLs |

### Cross-Cutting Concerns Mapping

| Concern | Where It Lives | Consumed By |
|---|---|---|
| Exposure denylist | `denylist/enforcement.py` | `pipeline/stages/casefile.py`, `integrations/slack.py`, `integrations/servicenow.py`, `diagnosis/prompt.py` |
| Policy version stamping | `config/policies/` + `models/case_file.py` | `pipeline/stages/casefile.py`, `pipeline/stages/gating.py` |
| UNKNOWN propagation | `models/evidence.py` (EvidenceStatus enum) | All pipeline stages |
| Integration mode abstraction | `integrations/base.py` | All integration adapters |
| HealthRegistry | `health/registry.py` | `pipeline/scheduler.py`, `pipeline/stages/dispatch.py`, `health/metrics.py` |
| Correlation ID | `logging/setup.py` | Every module via structlog context |

### Architectural Boundaries

**Import Rules (enforced by code review):**

| Package | Can Import From | Cannot Import From |
|---|---|---|
| `pipeline/stages/` | `contracts/`, `models/`, `config/`, `health/`, `denylist/`, `errors/`, `logging/` | `diagnosis/`, `outbox/publisher.py` |
| `diagnosis/` | `contracts/`, `models/`, `config/`, `health/`, `errors/`, `logging/` | `pipeline/`, `outbox/` |
| `outbox/` | `contracts/`, `config/`, `health/`, `errors/`, `logging/`, `integrations/kafka.py` | `pipeline/`, `diagnosis/` |
| `integrations/` | `contracts/`, `config/`, `errors/`, `logging/` | `pipeline/`, `diagnosis/`, `outbox/` |
| `contracts/` | (none — leaf package) | Everything |
| `config/` | (none — leaf package) | Everything |

### Data Flow

```
Prometheus → [Stage 1: Evidence] → [Stage 2: Peak] → [Stage 3: Topology]
    → [Stage 4: CaseFile Write + Hash] → Object Storage
    → [Stage 5: Outbox Insert] → Postgres
    → [Stage 6: Rulebook Gating] → ActionDecision
    → [Stage 7: Dispatch] → PagerDuty / Slack / Log

Outbox Publisher (separate loop):
    Postgres (READY rows) → Kafka (CaseHeaderEvent + TriageExcerpt)

Cold Path (fire-and-forget):
    TriageExcerpt + Evidence → LangGraph → DiagnosisReport → Object Storage (diagnosis.json)
```

### Development Workflow

**Local development (Mode A):**
```bash
docker-compose up                          # Start all infrastructure
APP_ENV=local uv run python -m aiops_triage_pipeline --mode hot-path
```

**Connect to DEV (Mode B):**
```bash
APP_ENV=dev uv run python -m aiops_triage_pipeline --mode hot-path
```

**Run tests:**
```bash
uv run pytest -m "not integration"         # Fast unit tests
uv run pytest -m integration               # Integration tests (requires Docker)
uv run pytest                              # All tests
uv run ruff check                          # Lint
uv run ruff format --check                 # Format check
```

**Build Docker image:**
```bash
docker build -t aiops-triage-pipeline .
docker run aiops-triage-pipeline --mode hot-path
docker run aiops-triage-pipeline --mode cold-path
docker run aiops-triage-pipeline --mode outbox-publisher
```

## Architecture Validation Results

### Coherence Validation

**Decision Compatibility:**

All technology choices are compatible and work together without conflicts:
- Python 3.13 + uv 0.10.6 + SQLAlchemy Core 2.0.47 + psycopg[c] 3.3.3 — native async support, C-optimized driver
- Pydantic v2 2.12.5 + pydantic-settings ~2.13.1 — same ecosystem, config + contract enforcement unified
- confluent-kafka 2.13.0 — synchronous producer aligns with outbox publisher pattern (no aiokafka complexity)
- redis-py 7.2.1 with async built-in — fits asyncio.TaskGroup hot path
- opentelemetry-sdk 1.39.1 + OTLP exporter — vendor-neutral, Dynatrace compatible via OTLP protocol
- LangGraph 1.0.9 — async-native, fits fire-and-forget cold path pattern
- structlog 25.5.0 — JSON logging with correlation_id propagation pairs naturally with OTLP trace context
- No version conflicts detected across the dependency tree

**Pattern Consistency:**

- Naming conventions consistently defined across all layers (Python PEP 8, database snake_case, JSON snake_case, Kafka dash-separated, Redis colon-separated, Pydantic PascalCase+version)
- Error handling hierarchy (InvariantViolation → CriticalDependencyError → DegradableError → IntegrationError) maps directly to the HealthRegistry component status model and NFR-R1/R2 degraded mode rules
- Frozen Pydantic models (`frozen=True`) consistently enforce 12 contracts and align with the validate-at-creation + re-validate-on-deserialization pattern (3B)
- Serialization is JSON everywhere — no format switching between Kafka, object storage, or Redis

**Structure Alignment:**

- Project directory structure directly supports all architectural decisions — every decision maps to a specific package
- Import rules table prevents cross-component coupling (pipeline cannot import from diagnosis, and vice versa)
- Shared packages (contracts/, config/, health/, models/, errors/) are explicitly identified as leaf dependencies
- Monolith with extractable boundaries — single image + multiple entrypoints enables future service extraction

No contradictions found across decisions, patterns, or structure.

### Requirements Coverage Validation

**Functional Requirements Coverage (67 FRs across 10 categories):**

| FR Category | FRs | Architectural Support | Coverage |
|---|---|---|---|
| Evidence Collection (FR1–FR8) | 8 | `pipeline/stages/evidence.py`, `cache/evidence_window.py`, `integrations/prometheus.py`, `models/evidence.py` (EvidenceStatus enum for UNKNOWN) | FULL |
| Topology & Ownership (FR9–FR16) | 8 | `registry/loader.py` (v0/v1 canonicalization), `registry/resolver.py` (multi-level ownership lookup) | FULL |
| CaseFile Management (FR17–FR21) | 5 | `storage/casefile_io.py` (SHA-256 hash), `pipeline/stages/casefile.py`, `denylist/enforcement.py`, lifecycle via infrastructure | FULL |
| Event Publishing (FR22–FR26) | 5 | `outbox/state_machine.py` (PENDING_OBJECT→READY→SENT), `outbox/publisher.py`, `integrations/kafka.py` | FULL |
| Action Gating (FR27–FR35) | 9 | `pipeline/stages/gating.py` (AG0–AG6 sequential), `contracts/gate_input.py`, `cache/dedupe.py` | FULL |
| Diagnosis (FR36–FR42, FR66) | 8 | `diagnosis/graph.py` (LangGraph), `diagnosis/fallback.py` (deterministic fallback), fire-and-forget pattern (4B) | FULL |
| Notifications (FR43–FR50) | 8 | `pipeline/stages/dispatch.py`, `integrations/pagerduty.py`, `integrations/slack.py`, `integrations/servicenow.py` | FULL |
| Operability (FR51–FR54, FR67) | 5 | `health/registry.py` (HealthRegistry), `health/metrics.py` (OTLP export), `models/events.py` (DegradedModeEvent, TelemetryDegradedEvent) | FULL |
| Local Dev (FR55–FR59) | 5 | `config/settings.py` (APP_ENV), docker-compose, `integrations/base.py` (OFF/LOG/MOCK/LIVE) | FULL |
| Governance (FR60–FR65, FR67) | 7 | `denylist/`, `config/policies/`, policy version stamping in CaseFile, MI-1 posture explicit | FULL |

All 67 FRs have explicit architectural support. No missing capabilities.

**Non-Functional Requirements Coverage (24 NFRs across 5 categories):**

| NFR Category | NFRs | Architectural Support | Coverage |
|---|---|---|---|
| Performance (NFR-P1a–P6) | 6 | asyncio.TaskGroup (100 concurrent cases), in-memory registry (50ms p99), deterministic gating (500ms p99), 60s LLM timeout, 5-min wall-clock scheduler | FULL |
| Security (NFR-S1–S8) | 8 | TLS via infrastructure config, pydantic-settings for secrets, exposure denylist (4 boundaries), structured audit logging, LLM data handling controls | FULL |
| Reliability (NFR-R1–R5) | 5 | HealthRegistry per-component status, InvariantViolation (never catch), DegradableError hierarchy, DEAD=0 posture, infrastructure durability delegated | FULL |
| Operability (NFR-O1–O6) | 6 | OpenTelemetry OTLP (meta-monitoring), structlog JSON, startup config logging, deployment independence, graceful shutdown | FULL |
| Testability (NFR-T1–T6) | 6 | Policy version stamping (replay), invariant tests, LLM stub mode, storm simulation, e2e pipeline test, audit trail test | FULL |

All 24 NFRs have architectural support.

**Domain-Specific Requirements Coverage:**

- Compliance & regulatory: 25-month retention, MI-1 posture, postmortem selectivity — all architecturally supported
- Evidence integrity: Write-once stage files, SHA-256 hash chain, SchemaEnvelope pattern (in `docs/schema-evolution-strategy.md`) — covered
- Data minimization: Denylist enforcement at 4 boundaries, no PII in CaseFiles — covered
- Policy governance: Versioned YAML artifacts, policy version stamping in CaseFiles — covered
- LLM role boundaries: Cold-path only, deterministic fallback, schema validation, provenance-aware — covered
- 12 frozen contracts: All mapped to `contracts/` package with `PascalCaseV1` naming — covered

### Implementation Readiness Validation

**Decision Completeness:**

- All 15 architectural decisions (1A–1D, 2A–2B, 3A–3D, 4A–4C, 5A–5D) documented with specific technology choices, versions, and rationale
- Implementation patterns comprehensive across 5 categories (naming, structure, format, error handling, testing)
- Enforcement guidelines specify what AI agents MUST do — clear and actionable

**Structure Completeness:**

- Complete directory tree with every file named and its purpose documented
- FR-to-package mapping table enables agents to find where each requirement is implemented
- Cross-cutting concerns mapping shows exactly where shared patterns are consumed
- Import rules table prevents agents from creating inappropriate cross-component dependencies

**Pattern Completeness:**

- All 5 identified conflict areas have explicit resolution patterns
- Examples provided for error handling hierarchy, naming conventions, and testing patterns
- Data flow diagram clearly traces hot path, cold path, and outbox publisher loop

### Gap Analysis Results

**Critical Gaps:** None. All blocking implementation decisions are documented.

**Important Gaps (resolved during Party Mode review):**

1. **SchemaEnvelope cross-reference (resolved):** The `contracts/` package contains current frozen v1 models. Schema evolution infrastructure (SchemaEnvelope, version registry, legacy model retention) lives in a separate `schemas/` package per `docs/schema-evolution-strategy.md`. `schemas/` is a leaf package — importable by all packages, imports from nothing. Added to import rules table.

2. **Phase 0 docker-compose topology (resolved):** docker-compose starts 3 services of the same image with different `--mode` flags: `hot-path`, `cold-path`, `outbox-publisher`. No special `--mode all` entrypoint — the local topology mirrors production from Phase 0 onward.

3. **Integration mode semantics (resolved):** The OFF/LOG/MOCK/LIVE mode abstraction in `integrations/base.py` applies to outbound integrations (PagerDuty, Slack, ServiceNow, LLM). Kafka is infrastructure-required (LIVE always). Prometheus is inbound (LIVE or MOCK-replay for testing). The base adapter pattern does not force-fit all integrations into the same 4-mode model.

4. **Session-scoped testcontainers (resolved):** All testcontainers (Postgres, Redis, Kafka, MinIO, OTLP Collector) are started once per test session via session-scoped fixtures in `tests/integration/conftest.py`. Individual integration tests share the same container instances.

5. **OTLP Collector test config (resolved):** The OTLP Collector testcontainer uses a `debug` or `file` exporter configuration so tests can read back received metrics for assertion.

6. **Cross-stage hash chain test (resolved):** Added `test_hash_chain.py` to integration tests — verifies `diagnosis.json` includes SHA-256 hash of `triage.json`, validated on read-back.

7. **Decision replay test (resolved):** `test_audit_trail.py` includes decision replay scenario: load historical CaseFile, load referenced policy versions, re-evaluate Rulebook, assert identical ActionDecision (NFR-T1).

**Nice-to-Have Gaps (not blocking):**

- Docker HEALTHCHECK instruction in Dockerfile (pairs with `/health` endpoint)
- Explicit `.gitignore` patterns for the project
- Policy artifact archive formalization (git history serves this purpose implicitly)

### Validation Issues Addressed

All 7 issues identified during Party Mode review have been incorporated into the architecture. No unresolved issues remain.

### Architecture Completeness Checklist

**Requirements Analysis**

- [x] Project context thoroughly analyzed (67 FRs, 24 NFRs, 12 frozen contracts, 5 phases)
- [x] Scale and complexity assessed (enterprise/high, ~15-20 components)
- [x] Technical constraints identified (durability invariants, hot/cold separation, env isolation)
- [x] Cross-cutting concerns mapped (8 concerns with package-level ownership)

**Architectural Decisions**

- [x] Critical decisions documented with versions (15 decisions across 5 categories)
- [x] Technology stack fully specified (14 tools with pinned versions)
- [x] Integration patterns defined (9 integrations with mode support)
- [x] Performance considerations addressed (asyncio concurrency, in-memory registry, wall-clock scheduler)

**Implementation Patterns**

- [x] Naming conventions established (6 layers: Python, DB, JSON, Kafka, Redis, Pydantic)
- [x] Structure patterns defined (complete directory tree with import rules)
- [x] Format patterns specified (datetime ISO 8601, enum string, explicit null)
- [x] Error handling documented (custom exception hierarchy with clear rules)
- [x] Testing patterns documented (naming, fixtures, assertions, markers)

**Project Structure**

- [x] Complete directory structure defined (every file named)
- [x] Component boundaries established (import rules table + schemas/ leaf package)
- [x] Integration points mapped (FR-to-package + cross-cutting concerns tables)
- [x] Requirements to structure mapping complete (10-category FR table)

### Architecture Readiness Assessment

**Overall Status:** READY FOR IMPLEMENTATION

**Confidence Level:** HIGH — based on comprehensive decision coverage, zero critical gaps, strong pattern consistency, and peer review validation.

**Key Strengths:**

- Complete FR/NFR coverage with explicit package-level mapping — agents know exactly where to implement each requirement
- 12 frozen contracts as Pydantic `frozen=True` models provide compile-time-like enforcement in a dynamic language
- HealthRegistry + custom exception hierarchy creates a deterministic degraded-mode system — every failure mode has a defined response
- Import rules table prevents the most common AI agent error: inappropriate cross-component coupling
- Schema evolution strategy (separate document) is thorough and production-grade for 25-month regulatory retention
- Party Mode peer review resolved 7 implementation clarity issues before they could become agent divergence points

**Areas for Future Enhancement:**

- CI/CD pipeline definitions (deferred per 5C) when bank Git Actions integration is ready
- Policy artifact archive formalization when decision replay tooling is built
- Docker HEALTHCHECK instruction when Dockerfile is authored

### Implementation Handoff

**AI Agent Guidelines:**

- Follow all architectural decisions exactly as documented
- Use implementation patterns consistently across all components
- Respect project structure and boundaries — import rules are non-negotiable
- Refer to this document for all architectural questions
- Reference `docs/schema-evolution-strategy.md` for any versioning concerns

**First Implementation Priority:**

```bash
uv init --python 3.13 --package --name aiops-triage-pipeline
```

Then: Pydantic contract models (frozen=True) for all 12 frozen contracts → Configuration layer → HealthRegistry → Data layer → Pipeline stages

**Project Rename Note:** Project name updated from "bmad-demo" to "aiOps" during this session. PRD artifact titles may still reference the old name — update separately.
