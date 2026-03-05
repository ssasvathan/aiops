# Local Development

## Prerequisites

- Python 3.13+
- `uv`
- Docker + Docker Compose

## Repository Setup

```bash
uv sync --dev
```

## Start Local Infrastructure

```bash
docker compose up -d --build
```

This starts:

- ZooKeeper
- Kafka
- Postgres
- Redis
- MinIO
- Prometheus
- Harness
- App container

## Validate Stack Health

Run the smoke script:

```bash
bash scripts/smoke-test.sh
```

It verifies Kafka topics, Postgres, Redis, MinIO bucket, Prometheus, and harness metrics.

## Run Pipeline Modes Manually

Use local config:

```bash
APP_ENV=local uv run python -m aiops_triage_pipeline --mode hot-path
APP_ENV=local uv run python -m aiops_triage_pipeline --mode cold-path
APP_ENV=local uv run python -m aiops_triage_pipeline --mode outbox-publisher
```

Current behavior note:

- `__main__.py` currently prints the selected mode and exits.
- Full mode-specific runtime execution is being implemented incrementally.

## Environment Configuration

`src/aiops_triage_pipeline/config/settings.py` loads `config/.env.<APP_ENV>`:

- `config/.env.local`
- `config/.env.dev`
- `config/.env.uat.template`
- `config/.env.prod.template`
- `config/.env.docker`

Integration modes (default-safe):

- `INTEGRATION_MODE_PD`
- `INTEGRATION_MODE_SLACK`
- `INTEGRATION_MODE_SN`
- `INTEGRATION_MODE_LLM`

Allowed values:

- `OFF`
- `LOG`
- `MOCK`
- `LIVE`

## Test Commands

Unit tests:

```bash
uv run pytest -q tests/unit
```

Integration tests:

```bash
uv run pytest -q tests/integration -m integration
```

Full suite:

```bash
uv run pytest -q
```

Lint:

```bash
uv run ruff check
```

## Common Troubleshooting

- If smoke tests fail immediately, ensure services are running:
  - `docker compose ps`
- If Python commands fail on env resolution, verify `APP_ENV` and matching `config/.env.<APP_ENV>` file.
- If integration tests fail, confirm Docker daemon is running and accessible to testcontainers.
