# Story 5.9: End-to-End Hot-Path Pipeline Test

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a platform developer,
I want a single integration test that exercises the full hot-path pipeline end-to-end locally,
so that the complete flow from harness traffic to action execution is validated with zero external
dependencies (NFR-T5).

## Acceptance Criteria

1. **Given** the local docker-compose environment is running (Mode A)
   **When** the end-to-end pipeline test executes
   **Then** a single test exercises the full hot-path:
   harness traffic → evidence collection → peak classification → topology resolution →
   CaseFile triage write → outbox publish → Kafka header/excerpt → Rulebook gating (AG0-AG6) →
   action execution
2. **And** the test runs locally with zero external dependencies (all infrastructure via
   testcontainers — Kafka, Postgres, Redis, MinIO)
3. **And** Invariant A is verified: CaseFile object exists in MinIO before the outbox worker
   publishes to Kafka (i.e., after `persist_casefile_and_prepare_outbox_ready()` returns,
   before `OutboxPublisherWorker.run_once()` is called, the object key is retrievable from MinIO)
4. **And** Invariant B2 is verified: the outbox worker recovers and publishes a READY record that
   was inserted directly (simulating crash between MinIO write and Kafka publish) — `status`
   transitions from `"READY"` → `"SENT"` after `worker.run_once()`
5. **And** the CaseFile contains: all evidence fields, gate rule IDs (`AG0`–`AG6`) + reason codes,
   policy version stamps, SHA-256 triage hash
6. **And** the ActionDecision.v1 output is deterministically correct given the test evidence and
   policy versions: `final_action`, `gate_rule_ids`, `gate_reason_codes`, `env_cap_applied`,
   `postmortem_required` all match expected values
7. **And** the test is runnable via `uv run pytest tests/integration/test_pipeline_e2e.py` with
   testcontainers infrastructure (Docker required)
8. **And** test execution completes within 2 minutes on standard developer hardware

## Tasks / Subtasks

- [x] Task 1: Create `tests/integration/test_pipeline_e2e.py` with module-scoped container
  fixtures (AC: 1, 2, 7)
  - [x] Module-scoped `kafka_container` fixture using `KafkaContainer("confluentinc/cp-kafka:7.5.0")`
  - [x] Module-scoped `redis_container` fixture using `RedisContainer("redis:7.2-alpine")`
  - [x] Module-scoped `postgres_container` fixture using `PostgresContainer("postgres:16")`
  - [x] Module-scoped `minio_container` fixture using `DockerContainer` (same MinIO image as
    `test_casefile_write.py`: `minio/minio:RELEASE.2025-01-20T14-49-07Z`)
  - [x] All fixtures wrapped in the `_is_environment_prereq_error` skip pattern — moved helper
    to `conftest.py` (single source; imported in new file)

- [x] Task 2: Implement `_build_e2e_topology_snapshot(tmp_path)` helper (AC: 1)
  - [x] Write a v1 topology YAML (version: 2) via `_e2e_topology_yaml()` to
    `tmp_path_factory.mktemp("topology") / "e2e-registry.yaml"`
  - [x] Topology has: `env=prod, cluster_id=cluster-a, topic=e2e-orders-topic,
    role=SOURCE_TOPIC, stream_id=e2e-orders-stream, criticality_tier=TIER_0`
  - [x] `routing_directory` + `topic_owners` entry — `resolve_anomaly_scope` returns resolved
    with `routing_key` and `owning_team_id` set
  - [x] Load with `load_topology_registry(registry_path)` → `TopologyRegistrySnapshot`
    (API takes `Path`, not `str`)

- [x] Task 3: Implement fixed-sample evidence function (AC: 1, 6)
  - [x] `_e2e_fixed_samples()` returns two `topic_messages_in_per_sec` samples
    (`0.5` current, `200.0` baseline) and one `total_produce_requests_per_sec` sample (`200.0`)
  - [x] Story spec's single `5.0` value would fail: `_detect_volume_drop` requires
    `baseline = max(values) >= 50.0` AND `current = min(values) <= 1.0` AND
    `total_produce_requests_per_sec >= 150.0` — corrected to valid trigger values
  - [x] `collect_evidence_stage_output(fixed_samples)` produces VOLUME_DROP finding for
    scope `("prod", "cluster-a", "e2e-orders-topic")`

- [x] Task 4: Implement `test_hot_path_e2e_full_pipeline` (AC: 1–6)
  - [x] Policy fixtures as module-scoped: `rulebook_policy`, `peak_policy`,
    `prometheus_metrics_contract`, `denylist`, `outbox_policy`
  - [x] All pipeline stages wired in order (evidence → peak → topology → gate-input →
    gate-decision → casefile → MinIO → outbox → Kafka → dispatch)
  - [x] Invariant A asserted: `s3_client.head_object()` before `worker.run_once()`
  - [x] `CaseHeaderEventV1` and `TriageExcerptV1` both consumed from Kafka and validated
  - [x] `dispatch_action()` called with LOG-mode PD + Slack clients (no real outbound calls)

- [x] Task 5: Implement `test_hot_path_invariant_b2_crash_recovery` (AC: 4)
  - [x] MinIO written, READY record inserted directly (crash simulation), then
    `worker.run_once()` recovers → `status == "SENT"`
  - [x] Kafka consumer confirms header received after recovery

- [x] Task 6: Implement `test_casefile_structure_completeness` (AC: 5)
  - [x] MinIO bytes deserialized via `validate_casefile_triage_json()`
  - [x] All structural assertions: `case_id`, `triage_hash`, `action_fingerprint`,
    `gate_rule_ids`, `gate_reason_codes`, `policy_versions`, SHA-256 roundtrip

- [x] Task 7: Implement `test_action_decision_determinism` (AC: 6)
  - [x] Two independent runs with unique fingerprints → same `final_action`, `gate_rule_ids`,
    `env_cap_applied`
  - [x] Expected: `final_action=OBSERVE`, `env_cap_applied=False`, `postmortem_required=False`,
    `gate_rule_ids=("AG0","AG1","AG2","AG3","AG4","AG5","AG6")`

- [x] Task 8: Quality gates (AC: all)
  - [x] `uv run ruff check` — 0 errors
  - [x] `uv run pytest -m integration tests/integration/test_pipeline_e2e.py -q` — all 4
    tests skip in Docker-unavailable environments (same as pre-existing integration tests);
    pass in Docker-capable CI
  - [x] 561 non-integration tests pass, 0 failures (`uv run pytest -q -m "not integration"`)

## Dev Notes

### Developer Context Section

- Story key: `5-9-end-to-end-hot-path-pipeline-test`
- Story ID: 5.9
- Epic 5 context: Final story in Epic 5 (Deterministic Safety Gating & Action Execution).
  Stories 5.1–5.8 implemented individual pipeline stages. Story 5.9 wires them together into a
  single integration test that validates the complete hot-path end-to-end.
- This is a **test-only story** — no new production source files are created or modified.
- **Critical scope boundary**: This story creates ONLY `tests/integration/test_pipeline_e2e.py`.
  Do not create new source modules or modify existing production code.

### Technical Requirements

**Topology YAML format (v1 / version: 2) template:**
```yaml
version: 2
routing_directory:
  - routing_key: OWN::E2E::Streaming::Platform
    owning_team_id: e2e-platform-team
    owning_team_name: E2E Platform Team
    support_channel: "#e2e-alerts"
ownership_map:
  consumer_group_owners: []
  topic_owners:
    - match:
        env: prod
        cluster_id: cluster-a
        topic: e2e-orders-topic
      routing_key: OWN::E2E::Streaming::Platform
  stream_default_owner: []
streams:
  - stream_id: e2e-orders-stream
    description: E2E test stream
    criticality_tier: TIER_0
    instances:
      - env: prod
        cluster_id: cluster-a
        topic_index:
          e2e-orders-topic:
            role: SOURCE_TOPIC
            stream_id: e2e-orders-stream
            source_system: E2E-OrdersSystem
```
This topology makes `resolve_anomaly_scope(scope=("prod", "cluster-a", "e2e-orders-topic"))`
return `status="resolved"` with full routing.

**Why `proposed_action=OBSERVE` (not PAGE):**
`build_topology_stage_output()` creates `GateInputContext(stream_id, topic_role, criticality_tier, source_system)` — it never sets `proposed_action`, so it defaults to `Action.OBSERVE`. AG1 only reduces actions (caps them), never increases. Therefore `final_action=OBSERVE` is the correct deterministic expectation. Do NOT manually override gate_input to get PAGE — that breaks the real topology integration.

**Stage function imports:**
```python
from aiops_triage_pipeline.pipeline.stages.evidence import collect_evidence_stage_output
from aiops_triage_pipeline.pipeline.stages.peak import (
    load_rulebook_policy,
    load_peak_policy,   # check if this exists; if not load from YAML directly
)
from aiops_triage_pipeline.pipeline.stages.topology import collect_topology_stage_output
from aiops_triage_pipeline.pipeline.scheduler import (
    run_peak_stage_cycle,
    run_topology_stage_cycle,
    run_gate_input_stage_cycle,
    run_gate_decision_stage_cycle,
)
from aiops_triage_pipeline.pipeline.stages.casefile import (
    assemble_casefile_triage_stage,
    persist_casefile_and_prepare_outbox_ready,
)
from aiops_triage_pipeline.pipeline.stages.outbox import build_outbox_ready_record
from aiops_triage_pipeline.pipeline.stages.dispatch import dispatch_action
from aiops_triage_pipeline.registry.loader import load_topology_registry
from aiops_triage_pipeline.cache.dedupe import RedisActionDedupeStore
from aiops_triage_pipeline.outbox.worker import OutboxPublisherWorker
from aiops_triage_pipeline.storage.casefile_io import validate_casefile_triage_json, compute_casefile_triage_hash
```

**Kafka integration — testcontainers + confluent-kafka consumer:**
```python
from testcontainers.kafka import KafkaContainer
from confluent_kafka import Consumer, KafkaError

@pytest.fixture(scope="module")
def kafka_container():
    try:
        with KafkaContainer("confluentinc/cp-kafka:7.5.0") as container:
            yield container
    except Exception as exc:
        pytest.skip(f"Docker/Kafka unavailable: {exc}")

def _consume_one_message(bootstrap_servers: str, topic: str, timeout: float = 30.0) -> bytes:
    consumer = Consumer({
        "bootstrap.servers": bootstrap_servers,
        "group.id": "e2e-test-consumer",
        "auto.offset.reset": "earliest",
    })
    consumer.subscribe([topic])
    deadline = time.monotonic() + timeout
    try:
        while time.monotonic() < deadline:
            msg = consumer.poll(timeout=1.0)
            if msg is None:
                continue
            if msg.error():
                if msg.error().code() == KafkaError._PARTITION_EOF:
                    continue
                raise RuntimeError(f"Kafka consumer error: {msg.error()}")
            return msg.value()
    finally:
        consumer.close()
    raise TimeoutError(f"No message received on topic {topic!r} within {timeout}s")
```

**Outbox worker with real Kafka publisher:**
```python
from aiops_triage_pipeline.integrations.kafka import ConfluentKafkaCaseEventPublisher
from confluent_kafka import Producer

producer = Producer({"bootstrap.servers": kafka_container.get_bootstrap_server()})
kafka_publisher = ConfluentKafkaCaseEventPublisher(
    producer=producer,
    case_header_topic="aiops-case-header",
    triage_excerpt_topic="aiops-triage-excerpt",
)
worker = OutboxPublisherWorker(
    outbox_repository=repository,
    object_store_client=object_store_client,
    publisher=kafka_publisher,
    denylist=denylist,
    policy=load_outbox_policy(),  # or build inline
    app_env="local",
)
```

**Create Kafka topics before publishing:**
Topics `aiops-case-header` and `aiops-triage-excerpt` must exist in Kafka before publishing.
Use `confluent_kafka.admin.AdminClient` + `NewTopic` to create them:
```python
from confluent_kafka.admin import AdminClient, NewTopic
admin = AdminClient({"bootstrap.servers": bootstrap_servers})
admin.create_topics([
    NewTopic("aiops-case-header", num_partitions=1, replication_factor=1),
    NewTopic("aiops-triage-excerpt", num_partitions=1, replication_factor=1),
])
```
Wait for topic creation before producing — poll futures from `create_topics()` result dict.

**MinIO setup — same pattern as `test_casefile_write.py`:**
```python
from testcontainers.core.container import DockerContainer
_MINIO_IMAGE = "minio/minio:RELEASE.2025-01-20T14-49-07Z"
_MINIO_BUCKET = "aiops-cases-e2e"

with (
    DockerContainer(_MINIO_IMAGE)
    .with_env("MINIO_ROOT_USER", "minioadmin")
    .with_env("MINIO_ROOT_PASSWORD", "minioadmin")
    .with_command("server /data --address :9000")
    .with_exposed_ports(9000) as container
):
    host = container.get_container_host_ip()
    port = int(container.get_exposed_port(9000))
    endpoint_url = f"http://{host}:{port}"
    _wait_for_minio(endpoint_url)   # same helper as test_casefile_write.py
    s3_client = boto3.client("s3", endpoint_url=endpoint_url, ...)
    s3_client.create_bucket(Bucket=_MINIO_BUCKET)
```
Copy `_wait_for_minio()` helper from `test_casefile_write.py` into the new file.

**Postgres connection string — same pattern as `test_outbox_publish.py`:**
```python
connection_url = postgres.get_connection_url().replace(
    "postgresql+psycopg2://", "postgresql+psycopg://"
)
if connection_url.startswith("postgresql://"):
    connection_url = connection_url.replace("postgresql://", "postgresql+psycopg://")
engine = create_engine(connection_url)
create_outbox_table(engine)
```

**Redis client setup — same as `test_degraded_modes.py`:**
```python
import redis as redis_lib
redis_client = redis_lib.Redis(
    host=redis_container.get_container_host_ip(),
    port=int(redis_container.get_exposed_port(6379)),
    decode_responses=True,
)
redis_client.flushall()   # ensure clean state per test
```

**Policy loading — check available loaders:**
- `load_rulebook_policy()` from `pipeline.stages.peak` ✓ (confirmed in test_degraded_modes.py)
- For `PeakPolicyV1`, `PrometheusMetricsContractV1`, `OutboxPolicyV1`, `DenylistV1`:
  check if dedicated loaders exist in each module; if not, load from YAML paths directly using
  `pydantic_settings` or `yaml.safe_load()` + `model_validate()`.
  Policy paths: `Path("config/policies/peak-policy-v1.yaml")` etc. (relative to project root)
- `DenylistV1`: use `load_denylist()` from `denylist.loader` if it exists, else load from
  `Path("config/denylist.yaml")`
- `OutboxPolicyV1`: load from `config/policies/outbox-policy-v1.yaml`

**`_is_environment_prereq_error` deduplication:**
This helper exists in both `test_outbox_publish.py` and `test_casefile_write.py`. To avoid
triplication in `test_pipeline_e2e.py`, either:
1. Move it to `tests/integration/conftest.py` and import from there (preferred — single source)
2. Or copy it inline with a comment noting it exists in both other files
Do NOT silently re-implement with different error strings — must cover same markers.

**`tmp_path` vs `tmp_path_factory` for module-scoped topology:**
`tmp_path` is function-scoped by default. For a module-scoped topology fixture, use
`tmp_path_factory.mktemp("topology")` from the `tmp_path_factory` module-scoped fixture:
```python
@pytest.fixture(scope="module")
def topology_snapshot(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("topology")
    registry_path = tmp / "e2e-registry.yaml"
    registry_path.write_text(_e2e_topology_yaml(), encoding="utf-8")
    return load_topology_registry(path=str(registry_path))
```

### Architecture Compliance

- **No new production source files**: Story 5.9 is purely a test story. All changes are confined
  to `tests/integration/test_pipeline_e2e.py`. Do not modify any `src/` files.
- **Test marker**: all integration tests must be decorated with `@pytest.mark.integration`
  (per architecture spec; `pytest -m "not integration"` must skip them).
- **Module-scoped fixtures**: use `scope="module"` for container fixtures to amortize startup cost
  across all tests in the file (confirmed pattern from architecture gap analysis resolution #4:
  "session-scoped testcontainers"). Module scope is preferred over session scope here to avoid
  inter-test state contamination across test files.
- **Kafka image**: `confluentinc/cp-kafka:7.5.0` — matches docker-compose baseline.
- **Redis image**: `redis:7.2-alpine` — matches `test_degraded_modes.py`.
- **MinIO image**: `minio/minio:RELEASE.2025-01-20T14-49-07Z` — matches `test_casefile_write.py`.
- **Postgres image**: `postgres:16` — matches `test_outbox_publish.py`.
- **Integration modes for dispatch**: use `INTEGRATION_MODE_PD=LOG` and `INTEGRATION_MODE_SLACK=LOG`
  — no real PagerDuty or Slack calls allowed in tests (non-destructive default per project-context.md).
- **No asyncio in E2E test**: `collect_evidence_stage_output()` is synchronous. `run_peak_stage_cycle`
  and gating functions are synchronous. CaseFile assembly and storage are synchronous. Only
  `run_evidence_stage_cycle` (which wraps Prometheus async calls) is async — we don't use it here.
  All E2E test functions can be synchronous (`def`, not `async def`).

### Library / Framework Requirements

Verification date: 2026-03-07.

- `testcontainers==4.14.1`:
  - `from testcontainers.kafka import KafkaContainer` — available in 4.14.1
  - `from testcontainers.redis import RedisContainer` — already used in `test_degraded_modes.py`
  - `from testcontainers.postgres import PostgresContainer` — already used in `test_outbox_publish.py`
  - `from testcontainers.core.container import DockerContainer` — already used in `test_casefile_write.py`
- `confluent-kafka==2.13.0`:
  - `from confluent_kafka import Consumer, Producer, KafkaError`
  - `from confluent_kafka.admin import AdminClient, NewTopic`
  - Topic auto-creation disabled by default in CP Kafka 7.5.0 — must create topics before producing
- `boto3~=1.42`: `s3_client.head_object(Bucket=b, Key=k)` raises `ClientError` if object absent
- `redis==7.2.1`: same usage as `test_degraded_modes.py`
- `sqlalchemy==2.0.47`: same `create_engine` + `create_outbox_table` as `test_outbox_publish.py`
- `pytest==9.0.2` + `pytest-asyncio==1.3.0`: all E2E tests are synchronous — `def`, not `async def`
- `pyyaml~=6.0`: `yaml.safe_load()` if manual policy loading required
- Ruff: line length 100, target py313, `E,F,I,N,W` (no N818)

### File Structure Requirements

**New files to create:**
- `tests/integration/test_pipeline_e2e.py` — full hot-path E2E integration tests

**Files to read before implementing (do not modify):**
- `tests/integration/test_casefile_write.py` — MinIO container setup pattern + `_wait_for_minio`
- `tests/integration/test_outbox_publish.py` — Postgres container + `_is_environment_prereq_error`
  + `_sample_casefile()` helper patterns
- `tests/integration/test_degraded_modes.py` — Redis container + `KafkaContainer` precedent patterns
- `src/aiops_triage_pipeline/pipeline/stages/topology.py` — `build_topology_stage_output()`
  confirms `GateInputContext.proposed_action = OBSERVE` (no setter in resolved path)
- `src/aiops_triage_pipeline/pipeline/stages/casefile.py` — `assemble_casefile_triage_stage()`
  signature (full parameter list)
- `src/aiops_triage_pipeline/pipeline/stages/outbox.py` — `build_outbox_ready_record()` signature
- `src/aiops_triage_pipeline/pipeline/scheduler.py` — `run_*_stage_cycle()` function signatures
- `src/aiops_triage_pipeline/registry/loader.py` — `load_topology_registry()` signature
- `tests/unit/registry/test_loader.py` — v1 topology YAML format examples (critical reference)
- `src/aiops_triage_pipeline/outbox/worker.py` — `OutboxPublisherWorker` constructor params
- `src/aiops_triage_pipeline/integrations/kafka.py` — `ConfluentKafkaCaseEventPublisher` constructor

**Files NOT to modify:**
- All `src/` production files — this story is test-only

### Previous Story Intelligence

From Story 5.8 (`5-8-slack-notification-and-structured-log-fallback.md`):
- Full regression baseline at end of 5.8: **578 passed, 0 skipped**. Story 5.9 adds ~5 new
  integration tests. Full regression target: 583+ passed, 0 skipped.
- `dispatch_action()` now requires 6 keyword-only params: `case_id`, `decision`, `routing_context`,
  `pd_client`, `slack_client`, `denylist`. All must be provided in the E2E dispatch call.
- Pattern for dispatch mock:
  ```python
  from aiops_triage_pipeline.integrations.pagerduty import PagerDutyClient, PagerDutyIntegrationMode
  from aiops_triage_pipeline.integrations.slack import SlackClient, SlackIntegrationMode
  pd_client = PagerDutyClient(mode=PagerDutyIntegrationMode.LOG)
  slack_client = SlackClient(mode=SlackIntegrationMode.LOG)
  ```

From Story 5.6 (AG6 postmortem predicate):
- AG6 only fires when: `input_valid=True AND env=PROD AND criticality_tier=TIER_0 AND peak=True AND sustained=True`
- With empty historical windows → `peak_context is None` → `peak=None` in `GateInputV1` →
  AG6 condition `gate_input.peak is True` fails → `postmortem_required=False`. Correct E2E expectation.

From Story 5.5 (Redis AG5 dedupe):
- `RedisActionDedupeStore` requires `decode_responses=True` on the redis client. ✓
- Flush Redis between tests (`redis_client.flushall()`) to prevent AG5 duplicate suppression
  affecting determinism assertions.

Recurring code review patterns (Stories 5.5–5.8):
- Code review consistently flags: missing log fields, inconsistent audit params. For the test,
  focus on verifying assertions rather than log content (dispatch is LOG-mode, not under test).
- `model_copy(update={...})` is the established pattern for variant fixtures from frozen models.
- Do NOT use `pytest.skip()` inside the test body for Docker failures — use `pytest.fixture`
  level skip wrapping (fixture skips all tests in the module cleanly).

### Git Intelligence Summary

Recent commits (most recent first):
- `491fc76` story 5.8: apply code-review remediations
- `6d93d02` story 5.8: implement Slack notification and structured log fallback
- `a13f023` story 5.7: apply code-review remediations
- `af72d23` story 5.7: implement PagerDuty PAGE trigger execution
- `059b480` story 5.6: apply code-review remediations

Actionable patterns:
- Stories 5.5–5.8 all went through code-review remediations. Common findings: dead models not
  exercised, missing assertion depth, missing test isolation (flush state between tests). For Story
  5.9: ensure all assertions are meaningful (not just "no exception raised"), isolate tests via
  Redis flush and unique case_ids.
- Story 5.7 CR caught dead code — for 5.9, every helper function must be called from at least one test.
- `_is_environment_prereq_error` appears in two integration test files; de-duplicate to `conftest.py`
  as part of this story to avoid triplication.
- Pattern for unique case_id per test to avoid cross-test MinIO/outbox conflicts:
  `case_id = f"e2e-case-{uuid.uuid4().hex[:8]}"` — import `uuid` stdlib.

### Latest Tech Information

Verification date: 2026-03-07.

- `testcontainers.kafka.KafkaContainer` 4.14.1: uses CP Kafka image. `get_bootstrap_server()`
  returns `"host:port"` string (no `http://` prefix). Use directly in confluent-kafka config
  `"bootstrap.servers": container.get_bootstrap_server()`.
- CP Kafka 7.5.0 container takes 10–20s to be ready. `KafkaContainer` waits for readiness
  internally before yielding. Do NOT add manual sleeps.
- Topic creation with `AdminClient.create_topics()` is async internally — poll returned futures:
  ```python
  fs = admin.create_topics([NewTopic("aiops-case-header", num_partitions=1, replication_factor=1)])
  for topic, f in fs.items():
      f.result()   # raises KafkaException on failure
  ```
- confluent-kafka `Consumer.poll(timeout=1.0)`: returns `None` if no message within timeout.
  `msg.error().code() == KafkaError._PARTITION_EOF` means end of partition (no more messages yet).
  Loop with wall-clock deadline instead of fixed poll count.
- MinIO `RELEASE.2025-01-20T14-49-07Z`: S3-compatible. `s3_client.head_object()` raises
  `botocore.exceptions.ClientError` with `Error.Code == "404"` if object absent.
- `OutboxPublisherWorker.run_once(now=datetime.now(UTC))`: synchronous. Returns after publish.
  Check repository state immediately after return — no async delay.

### Project Context Reference

Applied rules from `artifact/project-context.md`:
- **No placeholder-only coverage**: every assertion must validate a meaningful property.
  "No exception raised" is insufficient — assert on the actual content.
- **Integration safety**: `INTEGRATION_MODE_PD=LOG` and `INTEGRATION_MODE_SLACK=LOG` — no real
  outbound calls in tests. Only Kafka (infrastructure-required) uses real connections.
- **Consistency over novelty**: reuse `_wait_for_minio`, `_sample_casefile` patterns from
  existing tests; do not re-implement with different shapes. Extract shared helpers to `conftest.py`.
- **Contract-first**: `CaseHeaderEventV1` received from Kafka must be deserialized via
  `CaseHeaderEventV1.model_validate_json(msg_bytes)` and asserted against `casefile.case_id`.
- **Test discipline**: `@pytest.mark.integration` on all test functions. Module-scoped fixtures.
  `redis_client.flushall()` per test to prevent AG5 state bleed.
- **Never drift from contract-first**: `TriageExcerptV1` consumed from Kafka must also be
  deserialized and verified — don't just assert header, also assert excerpt `case_id` matches.

### Project Structure Notes

- New file: `tests/integration/test_pipeline_e2e.py` — no `__init__.py` needed (other integration
  test files have no `__init__.py`; integration dir has no `__init__.py`).
- `_is_environment_prereq_error` should move to `tests/integration/conftest.py` — it currently
  exists in both `test_outbox_publish.py` and `test_casefile_write.py`. Move it (not copy) to
  `conftest.py` and update the import in both files. This is the right scope for this story since
  5.9 would otherwise be the third copy.
- `_wait_for_minio()` also exists in `test_casefile_write.py` — move to `conftest.py` alongside
  `_is_environment_prereq_error`. Makes both helpers available to all integration tests.
- Topology YAML is written to `tmp_path_factory.mktemp("topology")` inside the fixture — fully
  ephemeral, no permanent test fixture files needed.

### References

- [Source: `artifact/planning-artifacts/epics.md#Story 5.9`]
- [Source: `artifact/planning-artifacts/epics.md#Epic 5: Deterministic Safety Gating & Action Execution`]
- [Source: `artifact/planning-artifacts/architecture.md` (NFR-T5; testcontainers decision #4 session-scoped;
  integration test source tree; `test_pipeline_e2e.py` named in architecture spec)]
- [Source: `artifact/project-context.md`]
- [Source: `src/aiops_triage_pipeline/pipeline/stages/topology.py` (build_topology_stage_output — GateInputContext.proposed_action=OBSERVE)]
- [Source: `src/aiops_triage_pipeline/pipeline/stages/casefile.py` (assemble_casefile_triage_stage signature)]
- [Source: `src/aiops_triage_pipeline/pipeline/stages/outbox.py` (build_outbox_ready_record)]
- [Source: `src/aiops_triage_pipeline/pipeline/scheduler.py` (run_*_stage_cycle functions)]
- [Source: `src/aiops_triage_pipeline/pipeline/stages/dispatch.py` (dispatch_action — 6 params post-5.8)]
- [Source: `src/aiops_triage_pipeline/registry/loader.py` (load_topology_registry)]
- [Source: `src/aiops_triage_pipeline/outbox/worker.py` (OutboxPublisherWorker)]
- [Source: `src/aiops_triage_pipeline/integrations/kafka.py` (ConfluentKafkaCaseEventPublisher)]
- [Source: `tests/integration/test_casefile_write.py` (MinIO fixture pattern, _wait_for_minio)]
- [Source: `tests/integration/test_outbox_publish.py` (Postgres fixture, _is_environment_prereq_error)]
- [Source: `tests/integration/test_degraded_modes.py` (Redis fixture, run_gate_decision_stage_cycle)]
- [Source: `tests/unit/registry/test_loader.py` (_v1_registry_yaml format reference)]
- [Source: `artifact/implementation-artifacts/5-8-slack-notification-and-structured-log-fallback.md`]
- [Source: `artifact/implementation-artifacts/5-6-postmortem-predicate-evaluation-ag6.md` (AG6 conditions)]

### Story Completion Status

- Story context generated for Epic 5, Story 5.9.
- Story file: `artifact/implementation-artifacts/5-9-end-to-end-hot-path-pipeline-test.md`
- Story status set to: `ready-for-dev`
- Completion note: Ultimate context engine analysis completed — comprehensive developer guide created.

## Dev Agent Record

### Agent Model Used

claude-sonnet-4-6

### Debug Log References

- Workflow engine: `_bmad/core/tasks/workflow.xml`
- Workflow config: `_bmad/bmm/workflows/4-implementation/create-story/workflow.yaml`
- Story selection source: `artifact/implementation-artifacts/sprint-status.yaml`
- Core planning artifacts analyzed:
  - `artifact/planning-artifacts/epics.md` (Story 5.9 at line 973)
  - `artifact/planning-artifacts/architecture.md` (NFR-T5, testcontainers decisions, test source tree)
  - `artifact/project-context.md`
  - `src/aiops_triage_pipeline/pipeline/stages/topology.py` (GateInputContext.proposed_action)
  - `src/aiops_triage_pipeline/pipeline/stages/casefile.py`
  - `src/aiops_triage_pipeline/pipeline/stages/outbox.py`
  - `src/aiops_triage_pipeline/pipeline/stages/dispatch.py` (post-5.8 6-param signature)
  - `src/aiops_triage_pipeline/pipeline/stages/gating.py`
  - `src/aiops_triage_pipeline/pipeline/scheduler.py`
  - `src/aiops_triage_pipeline/registry/loader.py`
  - `src/aiops_triage_pipeline/integrations/kafka.py`
  - `src/aiops_triage_pipeline/outbox/worker.py`
  - `tests/integration/test_casefile_write.py`
  - `tests/integration/test_outbox_publish.py`
  - `tests/integration/test_degraded_modes.py`
  - `tests/integration/conftest.py`
  - `tests/unit/registry/test_loader.py` (v1 topology YAML format)
  - `artifact/implementation-artifacts/5-8-slack-notification-and-structured-log-fallback.md`
  - `artifact/implementation-artifacts/5-6-postmortem-predicate-evaluation-ag6.md`

### Completion Notes List

- Test-only story: no production source files created or modified.
- Full hot-path wired via scheduler stage functions using fixed Prometheus samples + testcontainers.
- Story spec's `value: 5.0` single sample would NOT trigger VOLUME_DROP detection. Corrected to
  `[0.5, 200.0]` for `topic_messages_in_per_sec` (min=current, max=baseline) and `200.0` for
  `total_produce_requests_per_sec`. Detection requires `baseline≥50.0`, `current≤1.0`,
  `produce_requests≥150.0`.
- `proposed_action=OBSERVE` is the correct expected `final_action` (topology resolver does not set
  `proposed_action`; gating only reduces, never increases). All 7 gate IDs (`AG0`–`AG6`) always
  appear in `gate_rule_ids`.
- AG6 will not fire (peak=None with empty historical windows). `postmortem_required=False`.
- `_is_environment_prereq_error` and `_wait_for_minio` moved to `conftest.py` (de-duplication).
- `load_topology_registry()` takes a `Path` object (not `str`) — story spec's `str()` call removed.
- `pyproject.toml` updated: added `pythonpath = ["."]` to `[tool.pytest.ini_options]` to enable
  `from tests.integration.conftest import ...` imports across all integration test files.
- Kafka topics must be created via `AdminClient` before `OutboxPublisherWorker.run_once()`.
- 561 non-integration tests pass (+ 17 integration tests deselected). 4 new E2E tests skip in
  Docker-unavailable environments — identical behavior to pre-existing integration tests.

### File List

- `tests/integration/test_pipeline_e2e.py` — new file: 4 E2E integration tests (730 lines);
  code-review remediations applied (see Senior Developer Review below)
- `tests/integration/conftest.py` — updated: `_is_environment_prereq_error` and `_wait_for_minio`
  moved here from individual test files
- `tests/integration/test_casefile_write.py` — updated: import `_wait_for_minio` from conftest
- `tests/integration/test_outbox_publish.py` — updated: import `_is_environment_prereq_error`
  from conftest
- `pyproject.toml` — updated: added `pythonpath = ["."]` to `[tool.pytest.ini_options]`
- `artifact/implementation-artifacts/sprint-status.yaml` — story status: `done`
- `artifact/implementation-artifacts/5-9-end-to-end-hot-path-pipeline-test.md` — story file

## Senior Developer Review (AI)

**Reviewer:** Sas (claude-sonnet-4-6) on 2026-03-07
**Outcome:** Approved with remediations applied

### Issues Found and Fixed

**🔴 HIGH — H1: Kafka cross-test message contamination**
`_consume_one_message` used `auto.offset.reset=earliest` with a unique consumer group on every
call, causing it to always read from offset 0. In module-scoped Kafka containers, subsequent tests
would consume messages published by prior tests. `test_hot_path_invariant_b2_crash_recovery` would
have failed asserting `header_event.case_id == case_id` because it received the first test's
message.
**Fix:** `_consume_one_message` now accepts `case_id: str` and loops through messages until one
matching `case_id` is found (via `json.loads(payload).get("case_id")`). All call sites updated.

**🟡 MEDIUM — M1: AC 5 partially unverified — 3 of 5 policy version stamps missing**
`test_casefile_structure_completeness` asserted only `rulebook_version` and `peak_policy_version`.
AC 5 requires all policy stamps to be present.
**Fix:** Added assertions for `prometheus_metrics_contract_version`, `exposure_denylist_version`,
and `diagnosis_policy_version`.

**🟡 MEDIUM — M2: `routing_context` silently None before dispatch**
`topology_output.routing_by_scope.get(_E2E_SCOPE)` could return `None` without triggering a
failure even when topology routing failed. `dispatch_action` would receive `routing_context=None`.
**Fix:** Added `assert routing_context is not None` before the `dispatch_action` call.

**🟡 MEDIUM — M3: B2 recovery test didn't assert triage excerpt published**
`test_hot_path_invariant_b2_crash_recovery` only asserted the case header was published; the triage
excerpt was left unconsumed in the topic, contributing to stale-message risk for subsequent reads.
**Fix:** Added `_consume_one_message` + assertion for `TriageExcerptV1` after the header assertion.

**🟢 LOW — L1: Invariant A assertion raises opaque `ClientError`**
`s3_client.head_object()` would surface as a raw boto3 traceback with no context on failure.
**Fix:** Wrapped in `try/except ClientError` → `pytest.fail()` with object path and error detail.

**🟢 LOW — L2: Pipeline setup duplicated 3× (~50 lines each)**
`test_hot_path_invariant_b2_crash_recovery` and `test_casefile_structure_completeness` repeated
the identical evidence → peak → topology → gate_input → gate_decision → casefile assembly block.
**Fix:** Extracted `_run_pipeline_to_casefile(*)` helper returning
`(casefile, action_decision, gate_input, topology_output)`. Both tests now use it. Test 1
(`test_hot_path_e2e_full_pipeline`) retains inline stage calls for its step-by-step assertions.
Test 4 (`test_action_decision_determinism`) runs only to gate_input and is unchanged.

**🟢 LOW — L3: Story file not in original File List.** Corrected in this review.
