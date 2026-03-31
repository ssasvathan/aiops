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
- App container (`hot-path`)
- Outbox publisher container (`outbox-publisher`)
- Cold-path container (`cold-path`)

`app` startup now performs a harness-state sweep before entering hot-path mode:

1. runs `--mode harness-cleanup` (clears harness casefiles/outbox/cache residue)
2. then starts `--mode hot-path`

## Harness — Traffic Generation

The `harness` service is a local-only dev tool that generates synthetic Prometheus metrics simulating real Kafka JMX exporter data. It starts automatically with `docker compose up`.

The harness exposes metrics at `http://localhost:8000/metrics`. Prometheus scrapes it via the `aiops-harness` job, making the signals available to the pipeline's evidence stage.

### Traffic patterns

| `HARNESS_PATTERN` value | What it simulates |
|---|---|
| `consumer_lag` | Consumer group lag grows while offset stays fixed (consumer stopped) |
| `throughput_constrained` | High message rate with elevated failed produce requests (throttling) |
| `volume_drop` | Normal rate for 30% of the cycle, then near-zero |
| `normal` | Stable baseline — no anomaly |
| `all` | Cycles through all four patterns in sequence (default) |

### Environment variables

| Variable | Default | Description |
|---|---|---|
| `HARNESS_PATTERN` | `all` | Active traffic pattern. See table above for valid values. |
| `HARNESS_CYCLE_SECONDS` | `60` | Seconds each pattern runs before cycling to the next. Each pattern emits on a 1-second tick loop for this many ticks. Must be `> 0`. |
| `HARNESS_INTENSITY` | `0.5` | Scaling multiplier for metric values. Range: `0.0` (near-zero) to `1.0` (full-scale). Values outside this range are accepted but may produce nonsensical metric values. |

**Example at `HARNESS_INTENSITY=0.5`:**

- `consumer_lag`: lag builds from `0` to `5,000` over the cycle
- `throughput_constrained`: `messages_in = 2,500/s`, `failed_produce = 25/s`
- `volume_drop`: normal phase at `250 msg/s`, drops to `2.0 msg/s`

Override defaults by setting env vars in `docker-compose.yml` under the `harness` service, or by passing them directly:

```bash
HARNESS_PATTERN=consumer_lag HARNESS_CYCLE_SECONDS=30 docker compose up harness
```

The harness has no dependency on Kafka or the pipeline app. It generates metric values directly via `prometheus_client.Gauge.set()` and is completely self-contained.

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

For end-to-end diagnosis output, all three long-lived modes must be running together:

1. `hot-path` creates casefiles and enqueues outbox records.
2. `outbox-publisher` publishes case header/excerpt events to Kafka.
3. `cold-path` consumes case headers and writes diagnosis artifacts.

`docker compose up -d --build` starts all three as dedicated services by default.

`APP_ENV=local` and `APP_ENV=harness` can legitimately cap actions to `OBSERVE`; this does not
block outbox publication or cold-path diagnosis.

Runtime mode status:

| Mode | Status | Notes |
|------|--------|-------|
| `outbox-publisher` | Fully wired | Runs `OutboxPublisherWorker` with policy, denylist, and alert evaluation |
| `casefile-lifecycle` | Fully wired | Runs `CasefileLifecycleRunner` against object storage |
| `hot-path` | Fully wired | Loads all policies and runtime clients; runs the complete `_hot_path_scheduler_loop` async triage cycle |
| `cold-path` | Fully wired | Subscribes to `aiops-case-header`, consumes `CaseHeaderEventV1` events sequentially. Per-event: retrieves `triage.json` from S3 (`retrieve_case_context`), builds deterministic evidence summary (`build_evidence_summary`), and invokes LLM diagnosis for every case (no env/tier/sustained gating). Commits offsets on shutdown. |

To run the cold-path consumer locally (requires Kafka and MinIO from `docker compose up`):

```bash
APP_ENV=local uv run python -m aiops_triage_pipeline --mode cold-path
```

The cold-path mode now requires S3/MinIO in addition to Kafka. Ensure MinIO is running and
the `S3_ENDPOINT_URL`, `S3_ACCESS_KEY`, `S3_SECRET_KEY`, and `S3_BUCKET` settings are
configured in `config/.env.local` before running cold-path locally.

Local diagnosis behavior by `INTEGRATION_MODE_LLM`:

- Across all modes, diagnosis persistence is deterministic: success and fallback outcomes both write `diagnosis.json` with hash-chain fields; fallback reports include explicit `PRIMARY_DIAGNOSIS_ABSENT` observability semantics.

- `LOG`: cold-path invokes diagnosis for all cases, but returns deterministic stub reports (no outbound LLM call).
- `MOCK`: cold-path invokes diagnosis for all cases with deterministic mock outputs/failure modes.
- `LIVE`: cold-path invokes diagnosis for all cases and calls the configured `LLM_BASE_URL`.

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

### Harness Residue Cleanup (Recommended Between Repeated Local Runs)

If you repeatedly run harness/local cycles, stale `outbox` rows and casefile objects can drift out of sync and cause hot-path `hot_path_case_processing_failed` errors.

Run the built-in cleanup sweep (safe-scoped to harness artifacts only):

```bash
APP_ENV=local uv run python -m aiops_triage_pipeline --mode harness-cleanup
```

When you use `docker compose up`, this sweep runs automatically for the `app` service.

What it removes:

- MinIO objects under `cases/case-harness-*/`
- Postgres `outbox` rows where `case_id LIKE 'case-harness-%'`
- Harness-related Redis dedupe/cache keys

### Harness Cases Show OBSERVE But No Cold-Path Summary

Use this checklist before treating the behavior as suppression:

1. Confirm all modes are running: `hot-path`, `outbox-publisher`, and `cold-path`.
2. Check outbox backlog health logs for `ready_count`/`retry_count` growth in `outbox.backlog_health`.
3. Look for `outbox.publish_succeeded` events for the case ID.
4. Verify cold-path receives the case header (`cold_path.event_received`) and starts diagnosis
   (`cold_path.diagnosis_start`).
