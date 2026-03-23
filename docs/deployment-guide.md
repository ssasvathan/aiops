# Deployment Guide

## Build Artifact

- Docker image built from root `Dockerfile` (multi-stage).
- Final runtime image contains app code, policy files, and `uv` runtime launcher.

## Required Services

- Kafka broker
- PostgreSQL database
- Redis cache
- S3-compatible object storage
- Prometheus (for evidence collection path)

## Runtime Configuration

- Core env switch: `APP_ENV` (`local|dev|uat|prod`)
- Environment files: `config/.env.<APP_ENV>`
- Policy files: `config/policies/*.yaml`
- Integration controls: `INTEGRATION_MODE_PD`, `INTEGRATION_MODE_SLACK`, `INTEGRATION_MODE_SN`, `INTEGRATION_MODE_LLM`
- Hot-path coordination controls:
  - `DISTRIBUTED_CYCLE_LOCK_ENABLED` (default `false`)
  - `CYCLE_LOCK_MARGIN_SECONDS` (default `60`, must be `>0`)
  - Effective lock TTL = `HOT_PATH_SCHEDULER_INTERVAL_SECONDS + CYCLE_LOCK_MARGIN_SECONDS`
  - Lock key namespace: `aiops:lock:cycle` (`SET NX EX`, no explicit unlock)
  - Redis lock errors fail open by design (cycle still executes; coordination health is degraded)
- Shard coordination controls (Story 4.2, disabled by default):
  - `SHARD_REGISTRY_ENABLED` (default `false`) — enable to distribute scope workloads across pods
  - `SHARD_COORDINATION_SHARD_COUNT` (default `4`, must be `>0`) — number of shards
  - `SHARD_LEASE_TTL_SECONDS` (default `360`, must be `>0`) — shard lease TTL in Redis
  - `SHARD_CHECKPOINT_TTL_SECONDS` (default `660`, must be `>0`) — checkpoint key TTL
  - Shard lease namespace: `aiops:shard:lease:<id>` (`SET NX EX`, no explicit unlock)
  - Checkpoint namespace: `aiops:shard:checkpoint:<id>:<interval_bucket>`
  - Shard coordination errors fall back to full-scope processing (D3 fail-open semantics)
  - Rollback: set `SHARD_REGISTRY_ENABLED=false` to revert instantly to full-scope mode

## Startup Command

```bash
uv run python -m aiops_triage_pipeline --mode outbox-publisher
```

Use mode-specific startup for hot/cold/lifecycle as required by deployment topology.

## Local Deployment Reference

```bash
docker compose up -d --build
```

## Operational Readiness Checks

- Service dependency checks via `scripts/smoke-test.sh`
- Runtime health endpoint support via `health/server.py`
- Outbox and linkage durability tables ensured by repository schema bootstrap methods

## Guardrails

- Kerberos file checks for Kafka SASL_SSL paths are validated at startup.
- ServiceNow major-incident write paths are blocked by explicit guardrails.
- Denylist sanitization is applied before external notification payloads.
