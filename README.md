# aiops-triage-pipeline

A Python 3.13 event-driven AIOps triage pipeline for Kafka infrastructure signals.

## What This Project Does

- Collects and classifies telemetry-driven anomalies.
- Resolves topology context (stream, ownership, blast radius) for each anomaly scope.
- Applies deterministic gating inputs and prepares downstream actioning.
- Uses a durability-first architecture for CaseFile and outbox-based publishing.

## Current Status

This repository is actively under implementation.

- Epic 1 complete: foundation, contracts, config, local stack, harness.
- Epic 2 complete: evidence collection and signal validation pipeline.
- Epic 3 complete: topology loading, resolution, routing, and legacy compat views.
- Epic 4 in progress: CaseFile/outbox stages are scaffolded; several files are intentionally placeholders.

## Architecture At A Glance

High-level flow:

```text
Prometheus -> Stage 1 Evidence -> Stage 2 Peak -> Stage 3 Topology
            -> Stage 4 CaseFile -> Stage 5 Outbox -> Stage 6 Gating -> Stage 7 Dispatch

Cold path (async): diagnosis enrichment
Outbox publisher: READY records -> Kafka
```

Primary implementation packages are under `src/aiops_triage_pipeline/`:

- `pipeline/` hot-path scheduler and stage orchestration
- `registry/` topology loading, resolution, ownership routing, compat views
- `contracts/` frozen v1 contract and policy models
- `outbox/` durable publishing state machine and publisher
- `diagnosis/` cold-path diagnosis graph and fallback
- `cache/`, `storage/`, `integrations/`, `health/`, `denylist/`, `logging/`

For deeper detail:

- [Architecture](docs/architecture.md)
- [Contracts](docs/contracts.md)
- [Local Development](docs/local-development.md)

## Contracts

Contract and policy models are treated as stable interfaces and are defined in:

- `src/aiops_triage_pipeline/contracts/`

They include event-shape contracts (`GateInputV1`, `ActionDecisionV1`, `CaseHeaderEventV1`, `TriageExcerptV1`, `DiagnosisReportV1`) and policy contracts (`RulebookV1`, `PeakPolicyV1`, `RedisTtlPolicyV1`, `OutboxPolicyV1`, `PrometheusMetricsContractV1`, `TopologyRegistryLoaderRulesV1`, `ServiceNowLinkageContractV1`, `LocalDevContractV1`).

## Quick Start (Local)

### Prerequisites

- Python 3.13+
- `uv`
- Docker + Docker Compose

### 1) Install dependencies

```bash
uv sync --dev
```

### 2) Start local infrastructure

```bash
docker compose up -d --build
```

### 3) Smoke-test the stack

```bash
bash scripts/smoke-test.sh
```

### 4) Run pipeline mode locally

```bash
APP_ENV=local uv run python -m aiops_triage_pipeline --mode hot-path
```

Other modes:

```bash
APP_ENV=local uv run python -m aiops_triage_pipeline --mode cold-path
APP_ENV=local uv run python -m aiops_triage_pipeline --mode outbox-publisher
```

Note: today, `__main__.py` is intentionally minimal and prints the selected mode. Full runtime wiring continues as implementation stories progress.

## Configuration

Environment-aware config is handled by `pydantic-settings` in:

- `src/aiops_triage_pipeline/config/settings.py`

Supported `APP_ENV` values:

- `local`, `dev`, `uat`, `prod`

Repo config files:

- `config/.env.local`
- `config/.env.dev`
- `config/.env.uat.template`
- `config/.env.prod.template`
- `config/.env.docker`

Integration safety modes:

- `INTEGRATION_MODE_PD`
- `INTEGRATION_MODE_SLACK`
- `INTEGRATION_MODE_SN`
- `INTEGRATION_MODE_LLM`

Each supports: `OFF | LOG | MOCK | LIVE`.

## Testing And Quality Gates

Run focused suites:

```bash
uv run pytest -q tests/unit
uv run pytest -q tests/integration -m integration
```

Run full suite:

```bash
uv run pytest -q
```

Lint:

```bash
uv run ruff check
```

## Documentation Plan

Project onboarding docs are intentionally repo-native and tool-agnostic. They live in `docs/` and should be updated with each material architecture, contract, or local-run change.

## Contributing

1. Keep contract changes explicit and test-backed.
2. Add or update tests in the same change for behavioral changes.
3. Keep docs current when runtime behavior, architecture, or developer workflows change.
