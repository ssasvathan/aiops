---
title: 'Bridge OTLP metrics to Prometheus via OpenTelemetry Collector'
type: 'bugfix'
created: '2026-04-11T00:00:00-00:00'
status: 'done'
baseline_commit: 'cb64f10cffdca93c3bee289ec8e62d0e7ac0bc10'
context:
  - 'artifact/project-context.md'
  - 'docs/deployment-guide.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** The Grafana dashboard at `localhost:3000` is empty because Prometheus has no data to serve. The app instruments metrics with the OpenTelemetry SDK (`health/metrics.py`), but `OTLP_METRICS_ENDPOINT` is unset in `config/.env.docker`, so `configure_otlp_metrics()` no-ops. Even if enabled, there is no OTLP receiver in the stack — Prometheus is configured to scrape `app:8080`, which only serves JSON health, not `/metrics`.

**Approach:** Add an OpenTelemetry Collector service to `docker-compose.yml` that receives OTLP from all Python workers and exposes a Prometheus scrape endpoint. Wire `OTLP_METRICS_ENDPOINT` in `.env.docker` to the collector and repoint the `aiops-pipeline` Prometheus job at the collector's exporter. No Python code changes.

## Boundaries & Constraints

**Always:**
- Keep the collector as an infrastructure-only service; do not change `health/metrics.py`, `health/otlp.py`, or any instrument definitions.
- Preserve existing OTLP naming convention — dotted names in Python convert to underscored names in PromQL (`aiops.findings.total` → `aiops_findings_total`). Dashboards must not need re-editing.
- Keep OTLP http/protobuf protocol (already the default in `config/.env.local`).
- Apply collector config to all three app services (`app`, `outbox-publisher`, `cold-path`) since they share `config/.env.docker`.
- Metrics emission remains advisory/degradable — a collector outage must not halt the pipeline.

**Ask First:**
- Any change to the instrument names, label schemas, or the Python OTLP bootstrap path.
- Adding authentication/TLS to the collector (local dev uses plaintext).

**Never:**
- Do not add `opentelemetry-exporter-prometheus` or any new Python dependency.
- Do not modify dashboard JSON panels or Prometheus metric naming.
- Do not expose `/metrics` from the existing health server on port 8080.
- Do not require the app to wait on the collector (depends_on with strict condition) — collector startup failure must not block the app.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Happy path | App emits OTel metric → OTLP HTTP export → collector → Prometheus scrape | Grafana panel populated within ~75s (60s export interval + 15s scrape) | N/A |
| Collector down at startup | `docker compose up` with collector failing | App logs OTLP export errors but continues; hot-path unaffected | Degradable — OTLP errors stay in app logs; no cascade |
| Prometheus scrape target returns empty | Collector up, app hasn't emitted yet | Prometheus shows target UP, zero samples | Dashboard panels render `No data` until first export |
| Histogram metric (e.g. `aiops.llm.latency_seconds`) | OTLP histogram data point | Exposed as `aiops_llm_latency_seconds_bucket` / `_sum` / `_count` | N/A |
| Up-down counter (gauge pattern, e.g. `aiops.evidence.status`) | Delta-accumulated value | Exported as Prometheus gauge with preserved labels | N/A |

</frozen-after-approval>

## Code Map

- `docker-compose.yml` -- add `otel-collector` service (new); `app`/`outbox-publisher`/`cold-path` services emit OTLP to it.
- `config/otel-collector.yaml` -- NEW: OTel Collector pipeline config (OTLP receiver → Prometheus exporter).
- `config/.env.docker` -- add `OTLP_METRICS_ENDPOINT` pointing at the collector's OTLP HTTP endpoint.
- `config/prometheus.yml` -- replace the `app:8080` target in the `aiops-pipeline` job with the collector's Prometheus exporter target; update the stale "scrape errors expected" comment.
- `src/aiops_triage_pipeline/health/otlp.py` -- read-only reference; `configure_otlp_metrics()` activates when endpoint is set.
- `src/aiops_triage_pipeline/__main__.py:475` -- read-only reference; confirms `configure_otlp_metrics(settings)` runs at startup for all modes.
- `scripts/verify-e2e.sh` -- already dirty; check whether it probes Grafana/Prometheus and update probes if needed.

## Tasks & Acceptance

**Execution:**
- [x] `config/otel-collector.yaml` -- Create collector config with OTLP receiver (HTTP :4318, gRPC :4317) and Prometheus exporter (:8889 at `/metrics`), plus batch processor. Namespace-strip disabled to preserve `aiops_*` names; resource attributes promoted to labels.
- [x] `docker-compose.yml` -- Add `otel-collector` service using `otel/opentelemetry-collector-contrib:0.96.0` (or latest pinned ≤ current), mount `config/otel-collector.yaml`, expose host port 8889 for debugging, add healthcheck against `:13133/`. Set `restart: unless-stopped`.
- [x] `docker-compose.yml` -- Add `otel-collector` to `depends_on` for `app`, `outbox-publisher`, and `cold-path` using `condition: service_started` (not `service_healthy`) so collector failures stay non-blocking.
- [x] `config/.env.docker` -- Add `OTLP_METRICS_ENDPOINT=http://otel-collector:4318/v1/metrics` and `OTLP_METRICS_PROTOCOL=http/protobuf`. Keep export interval at default (60000 ms).
- [x] `config/prometheus.yml` -- Replace target `app:8080` with `otel-collector:8889` in `aiops-pipeline` job; update stale comment referencing stories 1-2/1-3. Scrape interval stays 15s.
- [x] `scripts/verify-e2e.sh` -- Review existing edits; if it asserts dashboard/Prometheus health, extend probe to hit `curl http://localhost:9090/api/v1/query?query=up%7Bjob%3D%22aiops-pipeline%22%7D` and confirm target UP.

**Acceptance Criteria:**
- Given `docker compose up -d` on a clean environment, when the stack has been running for at least 90 seconds, then `curl http://localhost:9090/api/v1/targets` shows the `aiops-pipeline` job with state `up` pointing at `otel-collector:8889`.
- Given the harness is emitting traffic, when visiting `http://localhost:3000/d/aiops-main`, then at least one stat/heatmap/time-series panel on the main dashboard renders non-empty data within 90 seconds of first traffic.
- Given PromQL `sum by (final_action) (increase(aiops_findings_total[5m]))`, when executed against `http://localhost:9090/api/v1/query`, then it returns a non-empty result vector after traffic has flowed.
- Given the otel-collector container is stopped, when the app is already running, then hot-path cycles continue (verified in app logs) — no halt or crash.
- Given the full unit suite, when running `uv run pytest -q tests/unit`, then all tests pass unchanged (no Python code touched).

## Spec Change Log

## Design Notes

### Why collector over app-side Prometheus exporter

Two viable paths: (A) drop an OTel Collector as OTLP→Prometheus bridge, (B) add `opentelemetry-exporter-prometheus` to the app and expose a `/metrics` endpoint. Chose (A) because:
- Zero Python change, zero new Python deps → smallest blast radius and no unit-test risk.
- Matches the project's existing OTLP-first bootstrap (`configure_otlp_metrics()` already present, tested, and called from `__main__.py`).
- Keeps the app decoupled from Prometheus — same binary works in envs with a real OTLP backend (K8s prod).
- Works uniformly for `app`, `outbox-publisher`, and `cold-path` (all three export OTLP; all three flow through the same collector).

### Collector config skeleton

```yaml
receivers:
  otlp:
    protocols:
      http:
        endpoint: 0.0.0.0:4318
      grpc:
        endpoint: 0.0.0.0:4317
processors:
  batch: {}
exporters:
  prometheus:
    endpoint: 0.0.0.0:8889
    resource_to_telemetry_conversion:
      enabled: true
extensions:
  health_check:
    endpoint: 0.0.0.0:13133
service:
  extensions: [health_check]
  pipelines:
    metrics:
      receivers: [otlp]
      processors: [batch]
      exporters: [prometheus]
```

### Name translation

The OTel Prometheus exporter converts `.` to `_` by default, yielding `aiops_findings_total`, `aiops_gating_evaluations_total`, `aiops_evidence_status`, `aiops_diagnosis_completed_total` — the exact names dashboards already query. No dashboard JSON edits required.

## Verification

**Commands:**
- `docker compose down -v && docker compose up -d` -- expected: all services reach healthy/running; no restart loops.
- `curl -s http://localhost:8889/metrics | grep -E '^aiops_(findings|gating|evidence|diagnosis)'` -- expected: at least 1 matching line after ~90s of traffic.
- `curl -s 'http://localhost:9090/api/v1/targets' | grep -o 'aiops-pipeline' | head -1` -- expected: target present and `health=up`.
- `curl -s 'http://localhost:9090/api/v1/query?query=up%7Bjob%3D%22aiops-pipeline%22%7D' | grep -o '"value":\[[^]]*,"1"'` -- expected: non-empty match (target up).
- `uv run pytest -q tests/unit` -- expected: full green, same test count.

**Manual checks:**
- Open `http://localhost:3000/d/aiops-main` — panels must populate after ~90s of harness traffic.
- Open `http://localhost:9090/targets` — `aiops-pipeline` job row should show `otel-collector:8889` in state `UP`.
- `docker compose logs app | grep otlp_metrics_configured` — confirm the OTLP bootstrap fired at startup.

## Suggested Review Order

**Collector bridge (entry point)**

- Receives OTLP, exports Prometheus. Start here to grasp the whole bridge.
  [`otel-collector.yaml:1`](../../config/otel-collector.yaml#L1)

- Prometheus exporter + resource-to-label conversion — the name-translation seam.
  [`otel-collector.yaml:27`](../../config/otel-collector.yaml#L27)

**Infra wiring**

- New `otel-collector` service with healthcheck and port exposure.
  [`docker-compose.yml:161`](../../docker-compose.yml#L161)

- Non-blocking `depends_on` for `app` — collector outage must not halt hot-path.
  [`app:otel-collector`](../../docker-compose.yml#L248)

- Same non-blocking dependency applied uniformly to `outbox-publisher` and `cold-path`.
  [`outbox-publisher:otel-collector`](../../docker-compose.yml#L269)

**Scrape target repoint**

- `aiops-pipeline` job now scrapes the collector's Prometheus exporter (was `app:8080`, which served JSON).
  [`prometheus.yml:21`](../../config/prometheus.yml#L21)

**App-side activation (gitignored)**

- `OTLP_METRICS_ENDPOINT` set in `config/.env.docker` (gitignored). Activates the existing `configure_otlp_metrics()` bootstrap at `__main__.py:475`.

**E2E regression guard**

- New Prometheus-scrape health check in the E2E verify script — catches future pipeline regressions.
  [`verify-e2e.sh:150`](../../scripts/verify-e2e.sh#L150)
