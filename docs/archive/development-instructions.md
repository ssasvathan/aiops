# Development Instructions

## Prerequisites

- Python 3.13+
- `uv`
- Docker + Docker Compose

## Setup

```bash
uv sync --dev
docker compose up -d --build
bash scripts/smoke-test.sh
```

## Runtime Commands

```bash
APP_ENV=local uv run python -m aiops_triage_pipeline --mode hot-path
APP_ENV=local uv run python -m aiops_triage_pipeline --mode cold-path
APP_ENV=local uv run python -m aiops_triage_pipeline --mode outbox-publisher
APP_ENV=local uv run python -m aiops_triage_pipeline --mode casefile-lifecycle --once
```

## Testing Commands

```bash
uv run pytest -q tests/unit
uv run pytest -q tests/integration -m integration
TESTCONTAINERS_RYUK_DISABLED=true DOCKER_HOST=unix://$HOME/.docker/desktop/docker.sock uv run pytest -q -rs
uv run ruff check
```

## Environment Model

- Active environment selected by `APP_ENV` (`local|dev|uat|prod`)
- Settings source: `config/.env.<APP_ENV>`
- Policy contracts source: `config/policies/*.yaml`
- Integration safety modes per integration: `OFF|LOG|MOCK|LIVE`

## Common Operational Checks

```bash
docker compose ps
docker info
docker ps
```

## Quality Gate Note

- Full regression expectation for this project is **0 skipped tests**.
- Preferred full regression command keeps Docker-backed integration tests active.
