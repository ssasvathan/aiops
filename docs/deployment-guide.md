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
