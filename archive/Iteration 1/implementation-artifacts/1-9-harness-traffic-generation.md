# Story 1.9: Harness Traffic Generation

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a platform developer,
I want a validation harness that generates real Prometheus signals for all three anomaly patterns,
so that I can prove the evidence pipeline works against real telemetry (FR58) using harness-specific stream naming that won't collide with production.

## Acceptance Criteria

1. **Given** the local docker-compose environment is running
   **When** `docker compose up harness` is executed
   **Then** the harness exposes Prometheus metrics at `http://localhost:8000/metrics` in standard Prometheus text exposition format

2. **And** the harness emits metrics using ONLY the canonical names from `prometheus-metrics-contract-v1.yaml` — specifically:
   - `kafka_server_brokertopicmetrics_messagesinpersec`
   - `kafka_server_brokertopicmetrics_bytesinpersec`
   - `kafka_server_brokertopicmetrics_bytesoutpersec`
   - `kafka_server_brokertopicmetrics_failedproducerequestspersec`
   - `kafka_server_brokertopicmetrics_failedfetchrequestspersec`
   - `kafka_server_brokertopicmetrics_totalproducerequestspersec`
   - `kafka_server_brokertopicmetrics_totalfetchrequestspersec`
   - `kafka_consumergroup_group_lag`
   - `kafka_consumergroup_group_offset`

3. **And** all harness metrics carry `env=harness` and `cluster_name=harness-cluster` — values guaranteed never to collide with any production, dev, uat, or prod environment identifiers

4. **And** the harness produces the **consumer lag buildup** pattern: `kafka_consumergroup_group_lag` increases steadily while `kafka_consumergroup_group_offset` remains stationary (consumer stopped)

5. **And** the harness produces the **throughput-constrained proxy** pattern: `kafka_server_brokertopicmetrics_messagesinpersec` sustains a high rate while `kafka_server_brokertopicmetrics_failedproducerequestspersec` is elevated (throttling)

6. **And** the harness produces the **volume drop** pattern: `kafka_server_brokertopicmetrics_messagesinpersec` drops from a normal baseline to near-zero

7. **And** the harness produces a **normal baseline** pattern: all metrics at stable, non-anomalous values

8. **And** the active pattern is selectable via `HARNESS_PATTERN` env var: `consumer_lag`, `throughput_constrained`, `volume_drop`, `normal`, or `all` (cycles through all patterns in sequence; default: `all`)

9. **And** cycle duration is configurable via `HARNESS_CYCLE_SECONDS` (default: `60`) and intensity scaling via `HARNESS_INTENSITY` (0.0–1.0, default: `0.5`)

10. **And** the Prometheus instance at `http://localhost:9090` successfully scrapes the harness — the `aiops-harness` job shows target `harness:8000` as **UP** in the Prometheus targets UI (`http://localhost:9090/targets`)

11. **And** unit tests in `tests/unit/harness/test_harness_metrics.py` verify that every metric name defined in `harness/metrics.py` exactly matches a canonical name in `config/policies/prometheus-metrics-contract-v1.yaml`, and that label names match the contract's identity configuration

## Tasks / Subtasks

- [x] Task 1: Create `harness/` Python module with metric server and pattern generators (AC: #1, #2, #3, #4, #5, #6, #7, #8, #9)
  - [x] Create `harness/requirements.txt` — `prometheus-client~=0.21` (pinned minor, patch-flexible; check PyPI for latest 0.21.x)
  - [x] Create `harness/metrics.py` — define `prometheus_client.Gauge` objects using EXACT canonical names from contract; topic metrics use labels `[env, cluster_name, topic]`; lag metrics use labels `[env, cluster_name, group, topic]`
  - [x] Create `harness/patterns/__init__.py` (empty)
  - [x] Create `harness/patterns/normal.py` — `run(duration, intensity)`: sets all metrics to stable baseline; sleeps 1s per tick for `duration` seconds then returns
  - [x] Create `harness/patterns/consumer_lag.py` — `run(duration, intensity)`: `group_lag` grows from 0 to `10_000 * intensity` linearly; `group_offset` fixed at 1000; `messages_in` at `500 * intensity`
  - [x] Create `harness/patterns/throughput_proxy.py` — `run(duration, intensity)`: `messages_in` at `5000 * intensity`; `total_produce` at `1000 * intensity`; `failed_produce` at `50 * intensity` (5% error rate); `bytes_in` at `1_000_000 * intensity`
  - [x] Create `harness/patterns/volume_drop.py` — `run(duration, intensity)`: first 30% of duration: `messages_in = 500 * intensity` (normal); remaining 70%: `messages_in = 2.0` (near-zero); `bytes_in` proportional
  - [x] Create `harness/main.py` — reads env vars, calls `prometheus_client.start_http_server(8000)`, runs pattern loop in background daemon thread; main thread stays alive with `while True: time.sleep(1)`

- [x] Task 2: Create `harness/Dockerfile` (AC: #1, #10)
  - [x] Base: `python:3.13-slim`
  - [x] Install `curl` via apt for health check: `apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*`
  - [x] `WORKDIR /harness`
  - [x] `COPY requirements.txt .` → `RUN pip install --no-cache-dir -r requirements.txt`
  - [x] `COPY . .`
  - [x] `EXPOSE 8000`
  - [x] `CMD ["python", "main.py"]`

- [x] Task 3: Add `harness` service to `docker-compose.yml` (AC: #1, #10)
  - [x] Add `harness` service with `build: { context: harness }`, ports `8000:8000`, default env vars, health check (`curl -f http://localhost:8000/metrics`), `restart: unless-stopped`
  - [x] Do NOT add `harness` to `app.depends_on` — harness is a standalone dev tool, not a pipeline dependency

- [x] Task 4: Write unit tests for metric contract compliance (AC: #11)
  - [x] Create `tests/unit/harness/__init__.py` (empty)
  - [x] Create `tests/unit/harness/conftest.py` — inserts `harness/` into `sys.path` so `import metrics` works
  - [x] Create `tests/unit/harness/test_harness_metrics.py`:
    - Test: all harness `Gauge._name` values are present in `contract["metrics"][*]["canonical"]`
    - Test: topic-metric Gauge label names = `["env", "cluster_name", "topic"]` (matches contract `identity.topic_identity_labels`)
    - Test: lag-metric Gauge label names = `["env", "cluster_name", "group", "topic"]` (matches contract `identity.lag_identity_labels`)
    - Test: each pattern module's `run()` is callable with `(duration=1, intensity=0.5)` without error (smoke test)

- [x] Task 5: Extend `scripts/smoke-test.sh` — add harness health check (AC: #10)
  - [x] Add `--- Harness ---` section: check `curl -sf http://localhost:8000/metrics` returns 200
  - [x] Check canonical metric present: `curl -sf http://localhost:8000/metrics | grep -q 'kafka_server_brokertopicmetrics_messagesinpersec'`

- [x] Task 6: Quality gate
  - [x] `uv run ruff check harness/` — passes with zero errors
  - [x] `uv run pytest tests/unit/harness/ -v` — all tests pass (7/7)
  - [ ] `docker compose up --detach harness` — container starts and becomes healthy (requires Docker build; validated via Dockerfile structure and Story 1.8 patterns)
  - [ ] `curl -s http://localhost:8000/metrics | head -20` — requires running container
  - [ ] Prometheus targets UI at `http://localhost:9090/targets` — requires running stack
  - [ ] `bash scripts/smoke-test.sh` — requires running stack

## Dev Notes

### CRITICAL — Harness Is a Standalone Dev Tool, Not Part of the Main Package

The harness lives at `harness/` at the project root — it is NOT under `src/aiops_triage_pipeline/`. It has its own `Dockerfile` and `requirements.txt`. The main app Dockerfile is unchanged.

**Why standalone**: The harness generates synthetic Prometheus metrics to simulate real Kafka JMX exporter data. It has zero dependency on the pipeline package. Isolation prevents test infrastructure from contaminating the production image.

**Why `prometheus_client`, not OpenTelemetry**: The pipeline uses OTLP for its own meta-monitoring. The harness simulates EXTERNAL Kafka metrics that Prometheus scrapes from a JMX exporter in production. Those metrics must use the Prometheus text exposition format — not OTLP.

**The harness does NOT connect to Kafka**: It generates synthetic metric VALUES directly via `prometheus_client.Gauge.set()`. No Kafka producer/consumer is used. The harness is completely self-contained.

### CRITICAL — Canonical Metric Names (DO NOT INVENT NEW NAMES)

Source of truth: `config/policies/prometheus-metrics-contract-v1.yaml` (FROZEN — `status: FROZEN`)

```
kafka_server_brokertopicmetrics_messagesinpersec      # primary ingress rate
kafka_server_brokertopicmetrics_bytesinpersec          # bytes in (supplementary)
kafka_server_brokertopicmetrics_bytesoutpersec         # bytes out (supplementary)
kafka_server_brokertopicmetrics_failedproducerequestspersec
kafka_server_brokertopicmetrics_failedfetchrequestspersec
kafka_server_brokertopicmetrics_totalproducerequestspersec
kafka_server_brokertopicmetrics_totalfetchrequestspersec
kafka_consumergroup_group_lag                          # primary lag signal
kafka_consumergroup_group_offset                       # offset progress
```

ANY deviation from these exact strings breaks the evidence pipeline. The unit tests exist precisely to catch naming drift.

### CRITICAL — Label Compliance (from Contract `identity` Section)

```yaml
# From prometheus-metrics-contract-v1.yaml:
identity:
  topic_identity_labels: ["env", "cluster_name", "topic"]
  lag_identity_labels: ["env", "cluster_name", "group", "topic"]
  ignore_labels_for_identity: ["instance", "job", "nodes_group", "client_id", "consumer_id", "member_host", "partition"]
```

**Topic-level metrics** (`messagesinpersec`, `bytesinpersec`, etc.) → labels: `env`, `cluster_name`, `topic`
**Lag/offset metrics** (`group_lag`, `group_offset`) → labels: `env`, `cluster_name`, `group`, `topic`
Do NOT add `instance`, `job`, `partition` — Prometheus adds `instance` and `job` automatically at scrape time.

**Harness non-production label values:**
```
env          = "harness"           # NEVER "local", "dev", "uat", "prod"
cluster_name = "harness-cluster"   # NEVER a real cluster name
topic        = "harness-lag-topic"       # consumer lag pattern
             = "harness-proxy-topic"     # throughput-constrained pattern
             = "harness-vol-topic"       # volume drop pattern
             = "harness-normal-topic"    # normal baseline
group        = "harness-consumer"  # for lag/offset metrics only
```

### CRITICAL — File Structure

```
# CREATE (new harness dev tool):
harness/
├── Dockerfile
├── requirements.txt           # prometheus-client~=0.21
├── main.py                    # Entry point
├── metrics.py                 # Gauge definitions
└── patterns/
    ├── __init__.py
    ├── consumer_lag.py
    ├── throughput_proxy.py
    ├── volume_drop.py
    └── normal.py

tests/unit/harness/
├── __init__.py
├── conftest.py                # sys.path injection for harness/ imports
└── test_harness_metrics.py

# MODIFY:
docker-compose.yml             # Add harness service
scripts/smoke-test.sh          # Add harness checks

# NOT TOUCHED:
config/prometheus.yml          # Already has aiops-harness job (Story 1.8 placeholder)
config/policies/prometheus-metrics-contract-v1.yaml  # FROZEN
Dockerfile                     # Main app image — unchanged
src/aiops_triage_pipeline/     # No pipeline code changes
pyproject.toml                 # No changes needed (harness deps in harness/requirements.txt)
```

### Pattern Implementation Reference

Each pattern module exports `run(duration: int, intensity: float) -> None`. The function updates metric values in a 1-second tick loop for `duration` seconds, then returns.

**Pattern 1 — Consumer Lag Buildup** (`topic: harness-lag-topic`)
```python
import time, math
from metrics import messages_in, group_lag, group_offset

def run(duration: int, intensity: float) -> None:
    for tick in range(duration):
        progress = tick / max(duration - 1, 1)
        group_lag.labels(env="harness", cluster_name="harness-cluster",
                         group="harness-consumer", topic="harness-lag-topic").set(10_000 * intensity * progress)
        group_offset.labels(env="harness", cluster_name="harness-cluster",
                            group="harness-consumer", topic="harness-lag-topic").set(1000.0)
        messages_in.labels(env="harness", cluster_name="harness-cluster",
                           topic="harness-lag-topic").set(500 * intensity)
        time.sleep(1)
```

**Pattern 2 — Throughput-Constrained Proxy** (`topic: harness-proxy-topic`)
```python
def run(duration: int, intensity: float) -> None:
    for _ in range(duration):
        messages_in.labels(..., topic="harness-proxy-topic").set(5000 * intensity)
        bytes_in.labels(..., topic="harness-proxy-topic").set(1_000_000 * intensity)
        total_produce.labels(..., topic="harness-proxy-topic").set(1000 * intensity)
        failed_produce.labels(..., topic="harness-proxy-topic").set(50 * intensity)  # 5% error rate
        time.sleep(1)
```

**Pattern 3 — Volume Drop** (`topic: harness-vol-topic`)
```python
def run(duration: int, intensity: float) -> None:
    threshold = int(duration * 0.3)
    for tick in range(duration):
        if tick < threshold:
            rate = 500 * intensity  # normal
        else:
            rate = 2.0              # near-zero (not exactly 0 — UNKNOWN rule applies to missing series only)
        messages_in.labels(..., topic="harness-vol-topic").set(rate)
        bytes_in.labels(..., topic="harness-vol-topic").set(rate * 200)  # ~200 bytes/msg
        time.sleep(1)
```

**Normal Baseline** (`topic: harness-normal-topic`)
```python
def run(duration: int, intensity: float) -> None:
    for _ in range(duration):
        messages_in.labels(..., topic="harness-normal-topic").set(500 * intensity)
        bytes_in.labels(..., topic="harness-normal-topic").set(100_000 * intensity)
        group_lag.labels(..., group="harness-consumer", topic="harness-normal-topic").set(10.0)
        group_offset.labels(..., group="harness-consumer", topic="harness-normal-topic").set(50_000 * intensity)
        time.sleep(1)
```

### `harness/metrics.py` — Full Gauge Definitions

```python
"""Prometheus Gauge definitions for the aiOps traffic harness.

All metric names are EXACT canonical names from prometheus-metrics-contract-v1.yaml (FROZEN).
DO NOT rename these metrics without updating the contract and bumping its version.
"""
from prometheus_client import Gauge

_TOPIC_LABELS = ["env", "cluster_name", "topic"]
_LAG_LABELS = ["env", "cluster_name", "group", "topic"]

messages_in = Gauge(
    "kafka_server_brokertopicmetrics_messagesinpersec",
    "Harness: messages in per second (canonical: primary ingress rate signal)",
    _TOPIC_LABELS,
)
bytes_in = Gauge(
    "kafka_server_brokertopicmetrics_bytesinpersec",
    "Harness: bytes in per second",
    _TOPIC_LABELS,
)
bytes_out = Gauge(
    "kafka_server_brokertopicmetrics_bytesoutpersec",
    "Harness: bytes out per second",
    _TOPIC_LABELS,
)
failed_produce = Gauge(
    "kafka_server_brokertopicmetrics_failedproducerequestspersec",
    "Harness: failed produce requests per second",
    _TOPIC_LABELS,
)
failed_fetch = Gauge(
    "kafka_server_brokertopicmetrics_failedfetchrequestspersec",
    "Harness: failed fetch requests per second",
    _TOPIC_LABELS,
)
total_produce = Gauge(
    "kafka_server_brokertopicmetrics_totalproducerequestspersec",
    "Harness: total produce requests per second",
    _TOPIC_LABELS,
)
total_fetch = Gauge(
    "kafka_server_brokertopicmetrics_totalfetchrequestspersec",
    "Harness: total fetch requests per second",
    _TOPIC_LABELS,
)
group_lag = Gauge(
    "kafka_consumergroup_group_lag",
    "Harness: consumer group lag",
    _LAG_LABELS,
)
group_offset = Gauge(
    "kafka_consumergroup_group_offset",
    "Harness: consumer group offset",
    _LAG_LABELS,
)
```

### `harness/main.py` — Entry Point

```python
"""Harness entry point: start Prometheus HTTP server and run pattern loop."""
import os
import threading
import time

from prometheus_client import start_http_server

from patterns import consumer_lag, throughput_proxy, volume_drop, normal

PATTERN = os.environ.get("HARNESS_PATTERN", "all")
CYCLE_SECONDS = int(os.environ.get("HARNESS_CYCLE_SECONDS", "60"))
INTENSITY = float(os.environ.get("HARNESS_INTENSITY", "0.5"))

_ALL_PATTERNS = [consumer_lag, throughput_proxy, volume_drop, normal]
_PATTERN_MAP = {
    "consumer_lag": [consumer_lag],
    "throughput_constrained": [throughput_proxy],
    "volume_drop": [volume_drop],
    "normal": [normal],
    "all": _ALL_PATTERNS,
}


def _run_loop() -> None:
    sequence = _PATTERN_MAP.get(PATTERN, _ALL_PATTERNS)
    while True:
        for mod in sequence:
            mod.run(duration=CYCLE_SECONDS, intensity=INTENSITY)


if __name__ == "__main__":
    start_http_server(8000)
    print(
        f"Harness metrics server listening on :8000 | "
        f"pattern={PATTERN} cycle={CYCLE_SECONDS}s intensity={INTENSITY}"
    )
    t = threading.Thread(target=_run_loop, daemon=True)
    t.start()
    while True:
        time.sleep(1)
```

**Note**: `start_http_server(8000)` is non-blocking (starts a daemon thread internally). The `while True: time.sleep(1)` loop in main keeps the process alive. The pattern loop runs in a separate daemon thread — if main exits, the pattern thread exits with it.

### `harness/Dockerfile`

```dockerfile
FROM python:3.13-slim

# Install curl for health check (python:3.13-slim does not include curl or wget by default)
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /harness

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["python", "main.py"]
```

### `docker-compose.yml` Harness Service Addition

Add after the `prometheus` service block, before `volumes:`:

```yaml
  harness:
    build:
      context: harness
    ports:
      - "8000:8000"
    environment:
      HARNESS_PATTERN: all
      HARNESS_CYCLE_SECONDS: "60"
      HARNESS_INTENSITY: "0.5"
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/metrics"]
      interval: 10s
      timeout: 5s
      retries: 5
      start_period: 5s
    restart: unless-stopped
```

**Do NOT add `harness` to `app.depends_on`** — the pipeline application does not depend on the harness. The harness is independently started and Prometheus scrapes it at the 5s interval defined in `config/prometheus.yml`.

### Unit Test Reference

```python
# tests/unit/harness/conftest.py
import pathlib
import sys

_HARNESS_DIR = pathlib.Path(__file__).parents[3] / "harness"
if str(_HARNESS_DIR) not in sys.path:
    sys.path.insert(0, str(_HARNESS_DIR))
```

```python
# tests/unit/harness/test_harness_metrics.py
import pathlib
import yaml
import metrics  # importable via conftest sys.path injection

_CONTRACT_PATH = pathlib.Path(__file__).parents[3] / "config/policies/prometheus-metrics-contract-v1.yaml"

def _load_canonical_names() -> set[str]:
    with open(_CONTRACT_PATH) as f:
        contract = yaml.safe_load(f)
    return {defn["canonical"] for defn in contract["metrics"].values()}

def _load_contract_identity() -> dict:
    with open(_CONTRACT_PATH) as f:
        return yaml.safe_load(f)["identity"]

_TOPIC_GAUGES = [
    metrics.messages_in, metrics.bytes_in, metrics.bytes_out,
    metrics.failed_produce, metrics.failed_fetch,
    metrics.total_produce, metrics.total_fetch,
]
_LAG_GAUGES = [metrics.group_lag, metrics.group_offset]


def test_all_harness_metric_names_are_canonical():
    canonical = _load_canonical_names()
    for gauge in _TOPIC_GAUGES + _LAG_GAUGES:
        assert gauge._name in canonical, (
            f"Harness metric '{gauge._name}' is NOT in prometheus-metrics-contract-v1 canonical names. "
            f"Valid names: {sorted(canonical)}"
        )


def test_topic_metric_labels_match_contract():
    identity = _load_contract_identity()
    expected = sorted(identity["topic_identity_labels"])
    for gauge in _TOPIC_GAUGES:
        actual = sorted(gauge._labelnames)
        assert actual == expected, (
            f"Metric '{gauge._name}' has labels {actual}, expected {expected}"
        )


def test_lag_metric_labels_match_contract():
    identity = _load_contract_identity()
    expected = sorted(identity["lag_identity_labels"])
    for gauge in _LAG_GAUGES:
        actual = sorted(gauge._labelnames)
        assert actual == expected, (
            f"Metric '{gauge._name}' has labels {actual}, expected {expected}"
        )


def test_pattern_consumer_lag_is_callable():
    from patterns import consumer_lag
    consumer_lag.run(duration=1, intensity=0.5)  # must complete in ~1s without error


def test_pattern_throughput_proxy_is_callable():
    from patterns import throughput_proxy
    throughput_proxy.run(duration=1, intensity=0.5)


def test_pattern_volume_drop_is_callable():
    from patterns import volume_drop
    volume_drop.run(duration=1, intensity=0.5)


def test_pattern_normal_is_callable():
    from patterns import normal
    normal.run(duration=1, intensity=0.5)
```

**Note on `gauge._name` and `gauge._labelnames`**: These are internal `prometheus_client` attributes. They are stable across `prometheus_client` 0.x releases but are technically private. If a future `prometheus_client` version changes them, update the test to use `gauge.describe()[0].name` and inspect the `MetricFamilySamples` descriptor instead.

### `scripts/smoke-test.sh` Extension

Append to the existing smoke-test.sh after the Prometheus section:

```bash
echo "--- Harness ---"
check "Metrics endpoint (/metrics)" \
  curl -sf http://localhost:8000/metrics
check "Canonical metric present (messagesinpersec)" \
  bash -c "curl -sf http://localhost:8000/metrics | grep -q 'kafka_server_brokertopicmetrics_messagesinpersec'"
check "Harness label namespace (env=harness)" \
  bash -c "curl -sf http://localhost:8000/metrics | grep -q 'env=\"harness\"'"
```

### Previous Story Intelligence (Stories 1.1–1.8)

**From Story 1.8 (direct predecessor):**
- `config/prometheus.yml` already has `aiops-harness` scrape job targeting `harness:8000` — this was defined as a placeholder in Story 1.8. Adding the `harness` docker-compose service activates it.
- docker-compose patterns established: `restart: unless-stopped` for long-running services; `restart: on-failure` for one-shot init containers — harness uses `unless-stopped`
- `python:3.13-slim` does NOT include `curl` or `wget` — must `apt-get install curl` in `harness/Dockerfile` (same challenge as Prometheus health check in Story 1.8, which used `wget` from the prometheus image — harness image doesn't have it by default)
- Docker Compose v2 syntax: `docker compose` (with space), not `docker-compose`
- Story 1.8 debug note: minio-init command format issue — yaml block sequences with `|` are safer than `>-` for multi-line commands. Not relevant to harness but keep in mind for any multi-line shell blocks.

**From Story 1.7 (Structured Logging):**
- `structlog` and `configure_logging()` are wired in the main pipeline — harness uses `print()` only (dev tool, not production code)
- Do NOT import from `aiops_triage_pipeline.logging` in harness

**From Story 1.6 (HealthRegistry):**
- The `HealthRegistry` tracks pipeline component health — harness is not a pipeline component and does not register with it

**From Story 1.1 (Project Init):**
- `uv run ruff check` applies to all Python files checked in — including `harness/`. Run `uv run ruff check harness/` to confirm compliance.
- `asyncio_mode = "auto"` in pytest: unit tests in `tests/unit/harness/` that are NOT async do not need `@pytest.mark.asyncio`. Pattern smoke tests call `run(duration=1, ...)` which sleeps in a thread — they are synchronous functions, no asyncio needed.

**Git patterns from recent commits:**
- Code review fixes come as follow-up commits (`Story X.Y: Code review fixes — ...`)
- Story file receives Dev Agent Record entries (model used, completion notes, file list)
- `artifact/implementation-artifacts/sprint-status.yaml` is always updated on story completion

### Web Research Context — prometheus_client Library

The Python `prometheus_client` library (PyPI: `prometheus-client`) is the standard for exposing Prometheus metrics from Python services.

**Key API for this story:**
- `Gauge(name, documentation, labelnames)` — metric that can go up and down (correct for rates and lag values)
- `gauge.labels(**label_kwargs).set(value)` — set a specific label combination's value
- `start_http_server(port)` — non-blocking; starts a daemon thread serving `/metrics` on `port`
- The `/metrics` endpoint returns Prometheus text format (OpenMetrics-compatible)

**Gauge vs Counter vs Histogram**: Use `Gauge` for all harness metrics. `Counter` is for monotonically increasing values only. `Histogram` is for distributions. All the Kafka metrics being simulated (`messagesinpersec`, `group_lag`, etc.) are rate/current-value metrics → `Gauge` is correct.

**prometheus_client version**: `0.21.1` is the latest stable as of late 2024. In `requirements.txt`, pin as `prometheus-client~=0.21` to allow patch updates. Check [https://pypi.org/project/prometheus-client/](https://pypi.org/project/prometheus-client/) for the current 0.21.x release at implementation time.

**Default registry**: `prometheus_client` uses a default global registry. `start_http_server()` serves this default registry. All `Gauge` objects defined at module level are automatically registered. No explicit registry management needed.

### What Is NOT In Scope for Story 1.9

- **Pipeline reading harness metrics from Prometheus** — evidence collection (Story 2.1+)
- **Real Kafka connection** — harness generates synthetic values; no Kafka producer/consumer
- **OTLP telemetry** — harness uses `prometheus_client`, not OpenTelemetry SDK
- **Authentication/TLS** — harness is local dev only, plain HTTP
- **Multi-pattern parallel execution** — patterns run sequentially in a cycle
- **OTLP Collector in docker-compose** — Story 7.2 scope
- **Integration tests for harness** — unit tests only; docker-compose smoke test covers integration validation
- **Windows compatibility** — not required for this project

### Project Structure Notes

- **Alignment**: `harness/` at project root matches the `scripts/` dev-tool pattern established in Story 1.8. Both are non-`src/` dev utilities.
- **Conflict**: Architecture directory structure (from `architecture.md`) does not show a `harness/` entry — this is expected, as the architecture covers the production `src/` layout. The harness is a dev-only addition.
- **Ruff scope**: `uv run ruff check` with default config lints all Python files reachable from the project root. `harness/` Python files must comply. Set `line-length = 100` and `target-version = "py313"` (same as `pyproject.toml` ruff config).
- **pytest pythonpath**: Tests import from `harness/` via `conftest.py` sys.path injection (scoped to `tests/unit/harness/conftest.py`). This is preferred over modifying global `pyproject.toml` pythonpath to avoid unintended cross-contamination.

### References

- FR58: Harness traffic generation — Story 1.9 is the direct implementation: [Source: `artifact/planning-artifacts/epics.md#Story 1.9`]
- Prometheus metrics contract (FROZEN): all canonical metric names and identity labels: [Source: `config/policies/prometheus-metrics-contract-v1.yaml`]
- Prometheus scrape job already configured for `harness:8000`: [Source: `config/prometheus.yml#aiops-harness job`]
- docker-compose service name MUST be `harness` — exact match for Prometheus target `harness:8000`: [Source: `config/prometheus.yml`]
- Architecture Decision 5B: docker-compose Mode A topology: [Source: `artifact/planning-artifacts/architecture.md#Infrastructure & Deployment`]
- Epic 1 objective (final story — completes Phase 0 foundation): [Source: `artifact/planning-artifacts/epics.md#Epic 1`]
- Python 3.13 (`python:3.13-slim` base image): [Source: `pyproject.toml#requires-python`, `.python-version`]
- Ruff `line-length = 100`, `target-version = "py313"`: [Source: `pyproject.toml#tool.ruff`]
- `asyncio_mode = "auto"` (pattern run tests are synchronous — no async decorator needed): [Source: `pyproject.toml#tool.pytest.ini_options`]
- Story 1.9 is last in Epic 1; epic-1-retrospective status is `optional`: [Source: `artifact/implementation-artifacts/sprint-status.yaml`]

## Dev Agent Record

### Agent Model Used

claude-sonnet-4-6

### Debug Log References

- **prometheus-client not in project venv**: `uv run pytest` uses the project venv, not the harness venv. Added `prometheus-client~=0.21` to `pyproject.toml` dev dependency group. uv resolved to 0.24.1 which satisfies `~=0.21`. Tests pass with 0.24.1.
- **ruff I001 import sort**: `harness/main.py` had `from prometheus_client` before `from patterns` — ruff isort treats `patterns` as first-party and `prometheus_client` as third-party, so third-party must precede first-party. Fixed with `ruff --fix`.

### Completion Notes List

- Implemented standalone `harness/` Python module at project root (not under `src/`). All 9 canonical metric Gauges defined in `harness/metrics.py` using exact names from the FROZEN prometheus-metrics-contract-v1.yaml. Four pattern modules (`consumer_lag`, `throughput_proxy`, `volume_drop`, `normal`) implement the 1-second tick loop with configurable `duration` and `intensity`. Entry point `harness/main.py` reads env vars, starts Prometheus HTTP server on port 8000, runs pattern loop in a daemon thread.
- `harness/Dockerfile` uses `python:3.13-slim` with `curl` installed for health checks, matching the approach established in Story 1.8.
- `docker-compose.yml` extended with standalone `harness` service — NOT added to `app.depends_on`. Prometheus scrape job (`aiops-harness`) was already configured in `config/prometheus.yml` as a Story 1.8 placeholder; adding the service activates it.
- 7 unit tests added in `tests/unit/harness/test_harness_metrics.py` covering: all 9 metric names match contract canonical names; topic-metric label compliance; lag-metric label compliance; all 4 pattern modules callable smoke tests. All 7 tests pass. Full regression suite (149 total) passes with zero failures.
- `scripts/smoke-test.sh` extended with `--- Harness ---` section checking metrics endpoint, canonical metric presence, and env label namespace.
- Docker compose quality gates (container build, Prometheus scrape UP) require a running stack — these are integration-level checks not exercisable without Docker. All static/unit quality gates pass: ruff (0 errors), pytest (7/7 harness, 149/149 total).

### File List

- `harness/requirements.txt` (new)
- `harness/metrics.py` (new)
- `harness/patterns/__init__.py` (new)
- `harness/patterns/consumer_lag.py` (new)
- `harness/patterns/throughput_proxy.py` (new)
- `harness/patterns/volume_drop.py` (new)
- `harness/patterns/normal.py` (new)
- `harness/main.py` (new)
- `harness/Dockerfile` (new)
- `tests/unit/harness/__init__.py` (new)
- `tests/unit/harness/conftest.py` (new)
- `tests/unit/harness/test_harness_metrics.py` (new)
- `docker-compose.yml` (modified — added harness service)
- `scripts/smoke-test.sh` (modified — added Harness section)
- `pyproject.toml` (modified — added prometheus-client~=0.21 to dev dependencies)
- `artifact/implementation-artifacts/sprint-status.yaml` (modified — status: review)
- `uv.lock` (modified — lock file updated when prometheus-client was added to dev dependencies)

## Change Log

- Story 1.9 implemented: harness traffic generation module created, all 7 unit tests passing, docker-compose and smoke-test extended (Date: 2026-03-01)
- Story 1.9 code review fixes: exception handling added to `_run_loop` (silent daemon death); startup validation for HARNESS_PATTERN/HARNESS_INTENSITY/HARNESS_CYCLE_SECONDS; `normal` pattern extended to emit all 9 canonical metrics; `prometheus-client` version specifier corrected to `~=0.24.0` (minor-pinned, matches uv-resolved version); `harness/.dockerignore` added; smoke-test `env=harness` label check made retry-safe; `uv.lock` added to File List (Date: 2026-03-01)
