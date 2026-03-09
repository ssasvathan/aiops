# Deployment Configuration

## Container Build

- Build file: `Dockerfile`
- Strategy: multi-stage (`builder` + minimal runtime)
- Runtime entrypoint:

```bash
uv run python -m aiops_triage_pipeline --mode hot-path
```

## Runtime Dependencies

- Kafka (broker topics: `aiops-case-header`, `aiops-triage-excerpt`)
- PostgreSQL (durable outbox + linkage retry state)
- Redis (dedupe and evidence/peak cache)
- S3-compatible object store (MinIO in local)
- Prometheus (evidence source)

## Local Compose Topology

Defined in `docker-compose.yml`:

- `zookeeper`, `kafka`, `kafka-init`
- `postgres`, `redis`
- `minio`, `minio-init`
- `prometheus`
- `harness`
- `app`

## Environment Configuration Surface

- `.env` files under `config/`
- Key settings families:
  - Kafka connectivity + optional Kerberos paths
  - Postgres URL
  - Redis URL
  - S3 endpoint/bucket/credentials
  - Integration mode switches and optional secrets
  - OTLP endpoint/protocol/headers/interval/timeout

## Deployment Guardrails

- Integration modes default safe (`LOG`) in local/dev profiles.
- Settings validation enforces protocol and bounds for lifecycle/OTLP controls.
- SASL_SSL mode validates Kerberos file presence at startup.
- Write scope guardrails prevent ServiceNow major-incident table writes.

## CI/CD Artifacts

- No `.github/workflows/*` files detected in repository at scan time.
- Operational automation currently centers on compose + script workflows.
