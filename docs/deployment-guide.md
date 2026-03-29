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
  - `SHARD_LEASE_TTL_SECONDS` (code fallback default `270`, must be `>0`) — shard lease TTL in Redis
  - For named envs (`dev|uat|prod`), `SHARD_LEASE_TTL_SECONDS` must be explicitly set in env files (no implicit fallback)
  - Startup guardrail enforces `SHARD_LEASE_TTL_SECONDS < HOT_PATH_SCHEDULER_INTERVAL_SECONDS`
  - `SHARD_CHECKPOINT_TTL_SECONDS` (default `660`, must be `>0`) — checkpoint key TTL
  - Shard lease namespace: `aiops:shard:lease:<id>` (`SET NX EX`, no explicit unlock)
  - Checkpoint namespace: `aiops:shard:checkpoint:<id>:<interval_bucket>`
  - Shard coordination errors fall back to full-scope processing (D3 fail-open semantics)
  - Rollback: set `SHARD_REGISTRY_ENABLED=false` to revert instantly to full-scope mode

## Shard Lease TTL Calibration (Story 2.2)

Calibration basis captured on `2026-03-29`:
- UAT sample window: `2026-03-22` to `2026-03-29` UTC
- Sample size: `2016` scheduler cycles (5-minute cadence)
- Measured p95 cycle duration: `263s`
- Safety margin: `31s`
- Candidate TTL: `ceil(263 + 31) = 294s`
- Guardrail: `294 < 300` (`HOT_PATH_SCHEDULER_INTERVAL_SECONDS`) passes

Configured env values:
- `config/.env.dev`: `SHARD_LEASE_TTL_SECONDS=250`
- `config/.env.uat.template`: `SHARD_LEASE_TTL_SECONDS=294`
- `config/.env.prod.template`: `SHARD_LEASE_TTL_SECONDS=294` (aligned to UAT calibration basis)

## Distributed Coordination Rollout

Distributed coordination can be enabled incrementally using two independent feature flags.
All phases are fully reversible: rollback = set the flag back to `false`.
No Redis `DEL` commands, schema migration, or coordinated restarts are required.

### Phase 0 (default) — Single-instance semantics

Both flags are `false` (the safe default):

```
DISTRIBUTED_CYCLE_LOCK_ENABLED=false
SHARD_REGISTRY_ENABLED=false
```

- Zero Redis coordination keys are written during hot-path cycles (`aiops:lock:*` and `aiops:shard:*` namespaces remain empty).
- All pods process the full scope set independently (no lock contention, no shard filtering).
- Identical to pre-4.1 behaviour — safe for single-pod deployments.

### Phase 1 — Enable cycle lock

Enable distributed interval ownership coordination:

```
DISTRIBUTED_CYCLE_LOCK_ENABLED=true
SHARD_REGISTRY_ENABLED=false
```

**Verification:** Confirm the following OTLP counters appear in your metrics backend:
- `aiops.coordination.cycle_lock_acquired` — increments on the pod that wins the interval.
- `aiops.coordination.cycle_lock_yielded` — increments on pods that yield the interval.
- `aiops.coordination.cycle_lock_fail_open` — increments when Redis is unavailable (fail-open safety net; NFR-R4).

Startup log event `config_active` will include `DISTRIBUTED_CYCLE_LOCK_ENABLED=True` and `pod_identity` (NFR-A6).

**Rollback:** `DISTRIBUTED_CYCLE_LOCK_ENABLED=false` — the `aiops:lock:cycle` key expires via its TTL (`HOT_PATH_SCHEDULER_INTERVAL_SECONDS + CYCLE_LOCK_MARGIN_SECONDS`). No manual cleanup.

### Phase 2 — Enable shard coordination

Enable scope-level workload distribution across pods (requires Phase 1 to also be enabled for full coordination):

```
DISTRIBUTED_CYCLE_LOCK_ENABLED=true
SHARD_REGISTRY_ENABLED=true
```

**Verification:** Confirm these OTLP counters appear:
- `aiops.coordination.shard_checkpoint_written` — increments per shard acquired by this pod.
- `aiops.coordination.shard_lease_recovered` — increments when a pod recovers a previously held shard.

**Rollback:** `SHARD_REGISTRY_ENABLED=false` — `aiops:shard:*` keys expire via their TTL (`SHARD_LEASE_TTL_SECONDS` and `SHARD_CHECKPOINT_TTL_SECONDS`). No `DEL` commands. No data migration.

### Recommended rollout order

Enable Phase 1 first, observe metrics and logs for one full cycle, then enable Phase 2.
Each phase can be independently reversed without affecting the other.

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
