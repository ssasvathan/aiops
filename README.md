# AIOps Triage Pipeline

> Intelligent, multi-signal infrastructure triage — unified telemetry ingestion, AI-powered diagnosis, and deterministic safety gating across metrics, logs, and traces from any source.

**AIOps Triage Pipeline** is a production-grade AIOps platform that ingests infrastructure telemetry across metrics, logs, and traces — from multiple configurable sources — and automatically triages anomalies into auditable, coordinated incident responses. Platform engineering and SRE teams use it to detect infrastructure signals at scale, assemble durable evidence cases, and execute downstream actions — PagerDuty pages, Slack notifications, and ServiceNow postmortem workflows — without manual intervention on the hot path.

Designed from the ground up for multi-telemetry, multi-source observability: the platform's extensible signal layer abstracts individual data origins, with Prometheus metrics as the first production-grade telemetry integration. Every triage decision is AI-enriched, deterministically gated, and reproducibly traceable to the policy version that produced it.

## Table of Contents

- [What This Project Does](#what-this-project-does)
- [Architecture at a Glance](#architecture-at-a-glance)
- [Pipeline Stages](#pipeline-stages)
- [Cold Path — LLM Diagnosis](#cold-path--llm-diagnosis)
- [Durable Persistence Layer](#durable-persistence-layer)
- [Integration Boundaries](#integration-boundaries)
- [Observability and Governance](#observability-and-governance)
- [Contracts](#contracts)
- [Quick Start (Local)](#quick-start-local)
- [Runtime Modes](#runtime-modes)
- [Configuration](#configuration)
- [Testing and Quality Gates](#testing-and-quality-gates)
- [Project Structure](#project-structure)
- [Documentation](#documentation)
- [Contributing](#contributing)


---

## What This Project Does

AIOps Triage Pipeline automates the full incident triage lifecycle — from multi-signal telemetry ingestion to postmortem linkage — so platform and SRE teams respond faster, with richer context and stronger operational governance across any infrastructure layer.

### Signal Ingestion and Classification

- Ingests infrastructure telemetry across metrics, logs, and traces from multiple configurable sources; Prometheus metrics is the current production integration.
- Classifies anomaly signals as peak, near-peak, sustained, or unknown using configurable detection policies.
- Resolves topology context per anomaly scope: stream identity, ownership hierarchy, and blast radius.

### Durable Case Management

- Assembles a write-once `CaseFile` in object storage with hash-chain provenance (Invariant A).
- Publishes typed Kafka events (`CaseHeaderEventV1`, `TriageExcerptV1`) through a Postgres-backed durable outbox for at-least-once delivery (Invariant B2).

### Deterministic Safety Gating and Action Execution

- Evaluates a seven-gate Rulebook engine (AG0–AG6) to produce a deterministic `ActionDecisionV1`.
- Executes downstream actions: PagerDuty page trigger, Slack notification, or structured log fallback.

### AI-Enriched Diagnosis

- Runs asynchronous LLM-driven diagnosis (LangGraph) that enriches case artifacts without blocking the hot path.
- Produces a `DiagnosisReportV1` with structured evidence citations and a SHA-256 hash chain to `triage.json`.

### Postmortem Automation

- Correlates cases with ServiceNow Incidents, Problems, and PIR tasks via a tiered linkage state machine.
- Enforces idempotent upserts with durable retry semantics through the `sn_linkage_retry` table.

### Governance and Observability

- Exports OpenTelemetry metrics via OTLP and evaluates operational alert thresholds at runtime.
- Enforces exposure denylist, MI-1 posture, and policy version stamping for audit reproducibility.

---

## Architecture at a Glance

```mermaid
flowchart TD
    P[Prometheus] --> S1["Stage 1<br/>Evidence Collection"]
    S1 --> S2["Stage 2<br/>Peak Classification"]
    S2 --> S3["Stage 3<br/>Topology Resolution"]
    S3 --> S4["Stage 4<br/>CaseFile Assembly"]
    S4 --> S5["Stage 5<br/>Outbox Enqueue"]
    S5 --> S6["Stage 6<br/>Rulebook Gating<br/>AG0–AG6"]
    S6 --> S7["Stage 7<br/>Action Dispatch<br/>PD / Slack"]
    S4 -.->|async cold path| S8["Stage 8<br/>LLM Diagnosis"]
    S7 -.->|async cold path| S9["Stage 9<br/>SN Linkage"]
    S5 --> OB["Outbox Publisher<br/>READY → Kafka"]
    OB --> K["Kafka Topics<br/>case-header<br/>triage-excerpt"]
```

**Technology stack:**

| Layer | Technology |
|-------|-----------|
| Runtime | Python 3.13, asyncio |
| Modeling | Pydantic v2, pydantic-settings |
| SQL persistence | PostgreSQL (outbox state, SN linkage retry) |
| Cache | Redis (evidence window, peak, dedupe) |
| Object storage | S3-compatible (MinIO locally) |
| Messaging | Kafka via confluent-kafka |
| Observability | OpenTelemetry + OTLP, structlog |
| LLM cold path | LangGraph |
| Tooling | uv, pytest, testcontainers, ruff, Docker/Compose |

**Architecture principles:**

- **Durability first** — CaseFile written before any event is published (Invariant A). Outbox ensures at-least-once Kafka delivery (Invariant B2).
- **Hot-path determinism** — the LLM cold path fires and forgets; it never blocks or overrides gate decisions.
- **Explicit safety modes** — all external integrations operate in `OFF | LOG | MOCK | LIVE` mode.
- **UNKNOWN-not-zero** — missing or incomplete evidence propagates as UNKNOWN through all stages; it is never silently zeroed.

---

## Pipeline Stages

| Stage | Module | Responsibility |
|-------|--------|----------------|
| 1 — Evidence | `pipeline/stages/evidence.py` | Telemetry collection and evaluation cadence |
| 2 — Peak | `pipeline/stages/peak.py` | Anomaly pattern detection, peak/near-peak/sustained classification |
| 3 — Topology | `pipeline/stages/topology.py` | Registry resolution, blast radius, ownership routing |
| 4 — CaseFile | `pipeline/stages/casefile.py` | Write-once assembly to object storage |
| 5 — Outbox | `pipeline/stages/outbox.py` | Postgres outbox enqueue (`PENDING_OBJECT → READY`) |
| 6 — Gating | `pipeline/stages/gating.py` | Rulebook gate engine AG0–AG6 sequential evaluation |
| 7 — Dispatch | `pipeline/stages/dispatch.py` | PagerDuty, Slack, and structured log action execution |

Hot-path orchestration is in `pipeline/scheduler.py`.

**Gate engine (AG0–AG6):**

| Gate | Responsibility |
|------|----------------|
| AG0 | Environment and entry preconditions |
| AG1 | Environment and criticality tier caps |
| AG2 | Evidence sufficiency check |
| AG3 | Source topic validation |
| AG4 | Sustained threshold and confidence floor |
| AG5 | Action deduplication (Redis atomic SET NX EX) |
| AG6 | Postmortem predicate (MI-1 posture enforcement) |

---

## Cold Path — LLM Diagnosis

The cold path runs asynchronously after hot-path dispatch and does not block or influence gate decisions.

**Stage 8 (Diagnosis):** LangGraph graph invokes the configured LLM, produces a `DiagnosisReportV1` with structured evidence citations, and writes `cases/<case_id>/diagnosis.json` to object storage.
- **Failure semantics:** Timeout, unavailability, schema validation failure, and internal errors each produce a deterministic fallback. The absence of `diagnosis.json` is explicit and observable — it means the LLM did not complete for this case.
- **Hash chain:** `diagnosis.json` includes the SHA-256 hash of `triage.json` to establish tamper-evident provenance.

**Stage 9 (SN Linkage):**

- Tiered ServiceNow correlation: Tier 1 (Incident correlation) → Tier 2 (Problem upsert) → Tier 3 (PIR task upsert).
- Idempotent upsert via stable external identifiers.
- Durable retry state machine persisted in `sn_linkage_retry` SQL table with terminal escalation handling.
- Fallback-rate metrics and alert thresholds integrated into the `aiops.*` telemetry layer.

---

## Durable Persistence Layer

### SQL tables (PostgreSQL)

| Table | State machine | Purpose |
|-------|--------------|---------|
| `outbox` | `PENDING_OBJECT → READY → SENT / RETRY / DEAD` | Durable Kafka event publication |
| `sn_linkage_retry` | Attempt state + retry windows | ServiceNow linkage lifecycle |

### Object storage (S3-compatible)

Each case has an isolated directory. Each enrichment stage writes one immutable file.

```
cases/<case_id>/
    triage.json      ← Stage 4 (hot path): evidence, topology, gate inputs, action decision
    diagnosis.json   ← Stage 8 (cold path): LLM DiagnosisReportV1
    linkage.json     ← Stage 9 (cold path): SN correlation result
    labels.json      ← Operator annotations (Phase 2+)
```

**Write-once invariants:** hash and idempotency checks prevent overwrite. A missing file means that stage did not complete — not that it failed silently.

---

## Integration Boundaries

All external integrations are adapter modules under `integrations/`. Each supports four safety modes controlled by environment variable:

| Variable | Integration |
|----------|------------|
| `INTEGRATION_MODE_PD` | PagerDuty Events V2 |
| `INTEGRATION_MODE_SLACK` | Slack incoming webhook |
| `INTEGRATION_MODE_SN` | ServiceNow table API (GET/POST/PATCH) |
| `INTEGRATION_MODE_LLM` | LLM provider (LangGraph) |

**Mode behaviour:**

| Mode | Behaviour |
|------|----------|
| `OFF` | Integration disabled entirely |
| `LOG` | Logs the payload; no external call |
| `MOCK` | Returns a deterministic canned response |
| `LIVE` | Makes the real external call |

The exposure denylist (`config/denylist.yaml`) is enforced at every outbound publish and notification boundary.

**Inbound:** Lightweight asyncio TCP health endpoint (`health/server.py`) returns the component status registry map.

---

## Observability and Governance

### Telemetry (`health/`)

- **OTLP export** (`health/otlp.py`): OpenTelemetry metrics exported via OTLP on startup.
- **Prometheus metrics** (`health/metrics.py`): `aiops.*`-namespaced counters and gauges for outbox health, linkage state, LLM fallback rates, and component degraded posture.
- **Operational alert evaluation** (`health/alerts.py`): `OperationalAlertEvaluator` loads `operational-alert-policy-v1.yaml` at startup and evaluates thresholds at runtime against live metric state.
- **Health registry** (`health/registry.py`): Component-level status map; drives degraded-mode capping and action posture.

### Audit and reproducibility

- `audit/replay.py` provides utilities to replay gate decisions against policy versions stamped in CaseFile artifacts.
- CaseFiles stamp `rulebook_version`, `peak_policy_version`, and active denylist version at decision time.
- See [Schema Evolution Strategy](docs/schema-evolution-strategy.md) for versioning procedures.

---

## Contracts

All contracts are frozen Pydantic v2 models in `src/aiops_triage_pipeline/contracts/`. Contract changes must be explicit and test-backed.

### Event and decision contracts

| Contract | Module |
|----------|--------|
| `GateInputV1` | `contracts/gate_input.py` |
| `ActionDecisionV1` | `contracts/action_decision.py` |
| `CaseHeaderEventV1` | `contracts/case_header_event.py` |
| `TriageExcerptV1` | `contracts/triage_excerpt.py` |
| `DiagnosisReportV1` | `contracts/diagnosis_report.py` |

### Policy and operational contracts

| Contract | Module |
|----------|--------|
| `RulebookV1` | `contracts/rulebook.py` |
| `PeakPolicyV1` | `contracts/peak_policy.py` |
| `PrometheusMetricsContractV1` | `contracts/prometheus_metrics.py` |
| `RedisTtlPolicyV1` | `contracts/redis_ttl_policy.py` |
| `OutboxPolicyV1` | `contracts/outbox_policy.py` |
| `TopologyRegistryLoaderRulesV1` | `contracts/topology_registry.py` |
| `ServiceNowLinkageContractV1` | `contracts/sn_linkage.py` |
| `OperationalAlertPolicyV1` | `contracts/operational_alert_policy.py` |
| `CasefileRetentionPolicyV1` | `contracts/casefile_retention_policy.py` |
| `LocalDevContractV1` | `contracts/local_dev.py` |

See [Contracts](docs/contracts.md) for the full contract reference.

---

## Quick Start (Local)

### Prerequisites

- Python 3.13+
- `uv`
- Docker + Docker Compose

### 1. Install dependencies

```bash
uv sync --dev
```

### 2. Start local infrastructure

```bash
docker compose up -d --build
```

This starts: ZooKeeper, Kafka, Postgres, Redis, MinIO, Prometheus, Harness, and App containers.

### 3. Validate the stack

```bash
bash scripts/smoke-test.sh
```

Verifies Kafka topics, Postgres, Redis, MinIO bucket, Prometheus health, and harness metrics endpoint.

### 4. Run a pipeline mode

```bash
# Outbox publisher (fully wired)
APP_ENV=local uv run python -m aiops_triage_pipeline --mode outbox-publisher

# Casefile lifecycle worker (fully wired)
APP_ENV=local uv run python -m aiops_triage_pipeline --mode casefile-lifecycle

# Single-iteration variants
APP_ENV=local uv run python -m aiops_triage_pipeline --mode outbox-publisher --once
APP_ENV=local uv run python -m aiops_triage_pipeline --mode casefile-lifecycle --once
```

---

## Runtime Modes

The entry point (`__main__.py`) dispatches to one of four modes via `--mode`.

| Mode | Status | Description |
|------|--------|-------------|
| `hot-path` | Fully wired | Loads policies, connects to all runtime clients, runs the deterministic triage scheduler loop |
| `cold-path` | Fully wired | Subscribes to `aiops-case-header`, consumes `CaseHeaderEventV1` events sequentially, commits on shutdown |
| `outbox-publisher` | Fully wired | Polls the `outbox` table for `READY` records and publishes to Kafka |
| `casefile-lifecycle` | Fully wired | Runs the retention policy against object storage; purges expired CaseFiles |

See [Runtime Modes](docs/runtime-modes.md) for full startup initialisation details, per-cycle stage flow, dependency matrix, and `--once` flag behaviour.

---

## Configuration

Configuration is loaded by `src/aiops_triage_pipeline/config/settings.py` using `pydantic-settings`.

**Supported `APP_ENV` values:** `local`, `dev`, `uat`, `prod`

**Env files:**

```
config/.env.local
config/.env.dev
config/.env.uat.template
config/.env.prod.template
config/.env.docker
```

**Policy files** (loaded at startup from `config/policies/`):

| File | Contract |
|------|----------|
| `outbox-policy-v1.yaml` | `OutboxPolicyV1` |
| `casefile-retention-policy-v1.yaml` | `CasefileRetentionPolicyV1` |
| `operational-alert-policy-v1.yaml` | `OperationalAlertPolicyV1` |
| `rulebook-v1.yaml` | `RulebookV1` |
| `peak-policy-v1.yaml` | `PeakPolicyV1` |

**Denylist:** `config/denylist.yaml` — enforced at every outbound publish and notification boundary.

---

## Testing and Quality Gates

Run focused suites:

```bash
uv run pytest -q tests/unit
uv run pytest -q tests/integration -m integration
```

Run the full suite:

```bash
uv run pytest -q
```

Run the full suite with Docker-backed integration execution (recommended):

```bash
TESTCONTAINERS_RYUK_DISABLED=true DOCKER_HOST=unix://$HOME/.docker/desktop/docker.sock uv run pytest -q -rs
```

Lint:

```bash
uv run ruff check
```

**Notes:**

- `tests/integration/conftest.py` auto-configures `DOCKER_HOST` for common local socket paths when unset.
- Integration tests require a running Docker daemon. If Docker is unavailable, run `uv run pytest -q tests/unit` to execute pure unit tests only.
- The zero-skip regression posture is mandatory: every change must pass a full-suite run with no skipped tests.

---

## Project Structure

```text
src/aiops_triage_pipeline/
├── __main__.py              # Runtime mode dispatch
├── pipeline/
│   ├── scheduler.py         # Hot-path stage orchestration
│   └── stages/              # evidence, peak, topology, casefile,
│                            # outbox, gating, dispatch, linkage
├── outbox/                  # Durable outbox: state machine, repository, worker, metrics
├── linkage/                 # SN retry state machine, repository, schema
├── storage/                 # Write-once CaseFile IO, S3 client, lifecycle runner
├── registry/                # Topology loader (v0/v1), resolver
├── diagnosis/               # LangGraph graph, prompt builder, deterministic fallback
├── audit/                   # Decision replay utilities
├── contracts/               # Frozen v1 contract and policy models
├── models/                  # Domain payload models (anomaly, evidence, peak, casefile)
├── integrations/            # PagerDuty, Slack, ServiceNow, Kafka, Prometheus, LLM
├── health/                  # Status registry, OTLP export, alert evaluation, HTTP server
├── cache/                   # Evidence window, peak cache, dedupe (Redis)
├── denylist/                # Enforcement and loader
├── config/                  # Settings singleton (pydantic-settings)
├── logging/                 # structlog processor pipeline
└── errors/                  # Typed exceptions
```

Additional source:

```text
harness/                     # Traffic generation (separated from src/)
tests/
├── unit/                    # Contract, stage, repository, adapter tests
└── integration/             # Docker-backed end-to-end and dependency tests
config/
├── policies/                # Runtime policy YAML files
└── .env.*                   # Environment-specific settings files
scripts/
└── smoke-test.sh            # Stack health validation script
```

---

## Documentation

All documentation lives in [`docs/`](docs/index.md) and is updated with each material change to architecture, contracts, or developer workflows. Start with the [Documentation Index](docs/index.md) for a full map.

### Getting Started

| Document | Description |
|----------|-------------|
| [Local Development](docs/local-development.md) | Environment setup, run commands, Docker troubleshooting |
| [Development Guide](docs/development-guide.md) | Developer workflows, tooling, and regression posture |
| [Deployment Guide](docs/deployment-guide.md) | Deployment configuration and operational runbook |

### Architecture and Design

| Document | Description |
|----------|-------------|
| [Architecture](docs/architecture.md) | System topology, stage flow, component overview, and deployment architecture |
| [Architecture Patterns](docs/architecture-patterns.md) | Design patterns and structural decisions |
| [Technology Stack](docs/technology-stack.md) | Full technology stack reference |
| [Component Inventory](docs/component-inventory.md) | Component breakdown and responsibilities |

### Reference

| Document | Description |
|----------|-------------|
| [Contracts](docs/contracts.md) | Frozen contract catalog, validation rules, and compatibility policy |
| [API Contracts](docs/api-contracts.md) | API contract schemas and usage reference |
| [Data Models](docs/data-models.md) | Domain payload model reference |
| [Schema Evolution Strategy](docs/schema-evolution-strategy.md) | Versioning procedures for Kafka events, CaseFile schemas, and policies |

### Contributing

| Document | Description |
|----------|-------------|
| [Contribution Guide](docs/contribution-guide.md) | Contribution standards, change guidelines, and review expectations |

---

## Contributing

1. Keep contract changes explicit and test-backed.
2. Add or update tests in the same change for all behavioral changes.
3. Enforce the zero-skip regression posture: full suite must pass with no skipped tests before merging.
4. Update docs when runtime behavior, architecture, or developer workflows change.
5. All external integration code paths require a LIVE mode test asserting the Pydantic model is instantiated in the production serialization path.
