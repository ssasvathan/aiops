# Development Guide

## Prerequisites

- Python 3.13+
- `uv`
- Docker + Docker Compose

## Install

```bash
uv sync --dev
```

## Start Dependencies

```bash
docker compose up -d --build
bash scripts/smoke-test.sh
```

## Run Modes

```bash
APP_ENV=local uv run python -m aiops_triage_pipeline --mode hot-path
APP_ENV=local uv run python -m aiops_triage_pipeline --mode cold-path
APP_ENV=local uv run python -m aiops_triage_pipeline --mode outbox-publisher
APP_ENV=local uv run python -m aiops_triage_pipeline --mode casefile-lifecycle --once
```

## Build and Packaging

- Container build: `docker build -t aiops-triage-pipeline .`
- Python package metadata/build backend in `pyproject.toml`

## Test Strategy and Commands

```bash
uv run pytest -q tests/unit
uv run pytest -q tests/integration -m integration
TESTCONTAINERS_RYUK_DISABLED=true DOCKER_HOST=unix://$HOME/.docker/desktop/docker.sock uv run pytest -q -rs
uv run ruff check
```

## Common Tasks

- Verify compose health: `docker compose ps`
- Validate Kafka topics and service readiness: `bash scripts/smoke-test.sh`
- Inspect env config: `config/.env.*`
- Inspect runtime policy contracts: `config/policies/*.yaml`

## Notes

- Integration safety behavior is controlled by `INTEGRATION_MODE_*` settings.
- Preferred regression run expects integration tests to execute with Docker (no skips).
