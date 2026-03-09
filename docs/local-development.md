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
# Outbox publisher — polls outbox table for READY records and publishes to Kafka
APP_ENV=local uv run python -m aiops_triage_pipeline --mode outbox-publisher

# Casefile lifecycle worker — applies retention policy and purges expired CaseFiles
APP_ENV=local uv run python -m aiops_triage_pipeline --mode casefile-lifecycle

# Single-iteration variants (run once and exit)
APP_ENV=local uv run python -m aiops_triage_pipeline --mode outbox-publisher --once
APP_ENV=local uv run python -m aiops_triage_pipeline --mode casefile-lifecycle --once
```

Runtime mode status:

| Mode | Status | Notes |
|------|--------|-------|
| `outbox-publisher` | Fully wired | Runs `OutboxPublisherWorker` with policy, denylist, and alert evaluation |
| `casefile-lifecycle` | Fully wired | Runs `CasefileLifecycleRunner` against object storage |
| `hot-path` | Bootstrap only | Loads settings, OTLP, and alert policy; runtime scheduler loop uses dedicated orchestration entrypoint |
| `cold-path` | Bootstrap only | Same bootstrap; cold-path invocation uses dedicated entrypoint |

## Environment Configuration

`src/aiops_triage_pipeline/config/settings.py` loads `config/.env.<APP_ENV>`:

- `config/.env.local`
- `config/.env.dev`
- `config/.env.uat.template`
- `config/.env.prod.template`
- `config/.env.docker`

Integration safety modes (default-safe):

| Variable | Integration |
|----------|------------|
| `INTEGRATION_MODE_PD` | PagerDuty Events V2 |
| `INTEGRATION_MODE_SLACK` | Slack incoming webhook |
| `INTEGRATION_MODE_SN` | ServiceNow table API |
| `INTEGRATION_MODE_LLM` | LLM provider (LangGraph) |

Allowed values for each: `OFF` (disabled) | `LOG` (log only, no call) | `MOCK` (canned response) | `LIVE` (real call)

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

### Docker Daemon Not Running

**Symptom:** Tests in `tests/integration/` (e.g. `test_degraded_modes.py`) error at setup with:

```text
docker.errors.DockerException: Error while fetching server API version:
  ('Connection aborted.', FileNotFoundError(2, 'No such file or directory'))
```

This surfaces even when running `uv run pytest -q -m "not integration"` because some tests in
`tests/integration/` use testcontainers but lack the `@pytest.mark.integration` marker — they are
not excluded by the marker filter and will error at fixture setup if Docker is unavailable.

**Triage steps:**

1. **Check daemon status:**
   ```bash
   docker info
   ```
   If this fails, the daemon is not running.

2. **Start Docker:**
   - macOS/Windows: Open Docker Desktop and wait for the whale icon to stabilise.
   - Linux (systemd): `sudo systemctl start docker`
   - Linux (rootless): `systemctl --user start docker`

3. **Verify daemon is accessible:**
   ```bash
   docker ps
   ```
   Should list containers (even if empty) without error.

4. **Re-run tests:**
   ```bash
   uv run pytest -q -m "not integration"
   ```
   Expected: all tests pass, 0 errors.

**Note:** If you intentionally want to skip Docker-dependent tests while the daemon is down,
run only the pure unit tests:
```bash
uv run pytest -q tests/unit
```

### Other Issues

- If smoke tests fail immediately, ensure services are running: `docker compose ps`
- If Python commands fail on env resolution, verify `APP_ENV` and the matching `config/.env.<APP_ENV>` file exists.
