# Deployment Guide

## Build Artifact

- Docker image built from root `Dockerfile` (multi-stage).
- Final runtime image contains app code, policy files, and `uv` runtime launcher.

## Required Services

- Kafka broker
- PostgreSQL database
- Redis cache
- S3-compatible object storage
- Prometheus (for evidence collection path and dashboard metrics)
- Grafana (for observability dashboards — auto-provisioned via docker-compose)

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

Evidence artifact:
- `artifact/implementation-artifacts/2-2-shard-lease-ttl-calibration-evidence-2026-03-29.md`

Operator recalibration procedure:
1. Export UAT cycle-duration samples for a representative window at 5-minute cadence.
2. Record `window_start_utc`, `window_end_utc`, `sample_count`, and `p95_seconds` in the evidence artifact.
3. Compute `candidate_ttl_seconds = ceil(p95_seconds + safety_margin_seconds)` where `safety_margin_seconds >= 30`.
4. Enforce guardrail `candidate_ttl_seconds < HOT_PATH_SCHEDULER_INTERVAL_SECONDS`; if violated, do not clamp silently.
5. Update UAT/Prod env templates, run full regression with zero skips, and commit both config and evidence updates.

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

## Grafana Observability Dashboards

The docker-compose stack includes Grafana OSS 12.4.2 with auto-provisioned dashboards and a Prometheus data source.

### Access

- Grafana: `http://localhost:3000` (anonymous admin, no login required)
- Prometheus: `http://localhost:9090`

### Dashboards

| Dashboard | UID | Description |
|-----------|-----|-------------|
| Main | `aiops-main` | Stakeholder narrative (hero banner, topic heatmap, baseline overlay) + operational intelligence (gating funnel, action distribution, LLM stats, pipeline capability stack) |
| Drill-Down | `aiops-drilldown` | Per-topic detail (evidence status, per-topic timeseries, findings table with action tracing). Linked from main dashboard heatmap tiles via `var-topic` |

### Time Window Presets

The main dashboard supports selectable time windows: **1h, 6h, 24h, 7d, 30d**. Default is **7d**.

### Kiosk Mode

For presentations and screen sharing, append `?kiosk` to the dashboard URL:

```
http://localhost:3000/d/aiops-main/aiops-main-dashboard?kiosk
```

### Dashboard JSON Lifecycle

Dashboard JSON files in `grafana/dashboards/` are the single source of truth. The provisioning config (`allowUiUpdates: true`) allows UI editing for iterative design, but the committed JSON files are authoritative.

### Pre-Demo Validation

After starting the stack and completing at least one pipeline cycle:

1. **Color palette enforcement** — verifies no forbidden Grafana default palette colors in dashboard JSON:
   ```bash
   bash scripts/validate-colors.sh
   ```

2. **Stack health** — verify all services are running:
   ```bash
   bash scripts/smoke-test.sh
   ```

### OTLP Instruments for Dashboards

The following instruments (defined in `health/metrics.py`) feed the Grafana dashboard panels:

| Instrument | Type | PromQL Name | Dashboard |
|-----------|------|-------------|-----------|
| `aiops.findings.total` | Counter | `aiops_findings_total` | Main (hero stat, anomaly family breakdown) |
| `aiops.gating.evaluations_total` | Counter | `aiops_gating_evaluations_total` | Main (gating funnel, per-gate suppression) |
| `aiops.evidence.status` | Gauge | `aiops_evidence_status` | Drill-down (evidence status panel) |
| `aiops.diagnosis.completed_total` | Counter | `aiops_diagnosis_completed_total` | Main (diagnosis count, quality metrics) |

## Guardrails

- Kerberos file checks for Kafka SASL_SSL paths are validated at startup.
- ServiceNow major-incident write paths are blocked by explicit guardrails.
- Denylist sanitization is applied before external notification payloads.
