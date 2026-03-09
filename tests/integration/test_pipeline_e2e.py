"""End-to-end hot-path pipeline integration test.

Exercises the full hot-path from fixed Prometheus samples through all pipeline stages:
  evidence → peak → topology → gate-input → gate-decision → casefile → outbox → Kafka → dispatch

All infrastructure is provided by testcontainers (Kafka, Postgres, Redis, MinIO).
Zero external dependencies required.
"""

from __future__ import annotations

import json
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path

import boto3
import pytest
import redis as redis_lib
from botocore.exceptions import ClientError
from confluent_kafka import Consumer, KafkaError, Producer
from confluent_kafka.admin import AdminClient, NewTopic
from sqlalchemy import create_engine
from testcontainers.core.container import DockerContainer
from testcontainers.kafka import KafkaContainer
from testcontainers.postgres import PostgresContainer

from aiops_triage_pipeline.cache.dedupe import RedisActionDedupeStore
from aiops_triage_pipeline.config.settings import load_policy_yaml
from aiops_triage_pipeline.contracts.case_header_event import CaseHeaderEventV1
from aiops_triage_pipeline.contracts.enums import Action
from aiops_triage_pipeline.contracts.outbox_policy import OutboxPolicyV1
from aiops_triage_pipeline.contracts.peak_policy import PeakPolicyV1
from aiops_triage_pipeline.contracts.prometheus_metrics import PrometheusMetricsContractV1
from aiops_triage_pipeline.contracts.rulebook import RulebookV1
from aiops_triage_pipeline.contracts.triage_excerpt import TriageExcerptV1
from aiops_triage_pipeline.denylist.loader import DenylistV1, load_denylist
from aiops_triage_pipeline.integrations.kafka import ConfluentKafkaCaseEventPublisher
from aiops_triage_pipeline.integrations.pagerduty import PagerDutyClient, PagerDutyIntegrationMode
from aiops_triage_pipeline.integrations.slack import SlackClient, SlackIntegrationMode
from aiops_triage_pipeline.outbox.repository import OutboxSqlRepository
from aiops_triage_pipeline.outbox.schema import create_outbox_table
from aiops_triage_pipeline.outbox.worker import OutboxPublisherWorker
from aiops_triage_pipeline.pipeline.scheduler import (
    run_gate_decision_stage_cycle,
    run_gate_input_stage_cycle,
    run_peak_stage_cycle,
    run_topology_stage_cycle,
)
from aiops_triage_pipeline.pipeline.stages.casefile import (
    assemble_casefile_triage_stage,
    persist_casefile_and_prepare_outbox_ready,
)
from aiops_triage_pipeline.pipeline.stages.dispatch import dispatch_action
from aiops_triage_pipeline.pipeline.stages.evidence import collect_evidence_stage_output
from aiops_triage_pipeline.pipeline.stages.outbox import build_outbox_ready_record
from aiops_triage_pipeline.pipeline.stages.peak import load_peak_policy, load_rulebook_policy
from aiops_triage_pipeline.registry.loader import load_topology_registry
from aiops_triage_pipeline.storage.casefile_io import (
    compute_casefile_triage_hash,
    validate_casefile_triage_json,
)
from aiops_triage_pipeline.storage.client import S3ObjectStoreClient
from tests.integration.conftest import (
    _is_environment_prereq_error,
    _wait_for_minio,
    _wait_for_redis,
)

# ── Constants ──────────────────────────────────────────────────────────────────

_MINIO_IMAGE = "minio/minio:RELEASE.2025-01-20T14-49-07Z"
_MINIO_ACCESS_KEY = "minioadmin"
_MINIO_SECRET_KEY = "minioadmin"
_MINIO_BUCKET = "aiops-cases-e2e"
_E2E_SCOPE = ("prod", "cluster-a", "e2e-orders-topic")
_CASE_HEADER_TOPIC = "aiops-case-header"
_TRIAGE_EXCERPT_TOPIC = "aiops-triage-excerpt"

_POLICY_DIR = Path("config/policies")
_DENYLIST_PATH = Path("config/denylist.yaml")


# ── Topology YAML ──────────────────────────────────────────────────────────────

def _e2e_topology_yaml() -> str:
    return """\
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
"""


# ── Fixed-sample evidence ──────────────────────────────────────────────────────

def _e2e_fixed_samples() -> dict[str, list[dict]]:
    """Fixed Prometheus samples that produce a deterministic VOLUME_DROP finding.

    Two topic_messages_in_per_sec samples are required:
      - max (200.0) serves as the baseline; must be >= _VOLUME_DROP_MIN_BASELINE (50.0)
      - min (0.5) serves as the current value; must be <= _VOLUME_DROP_MAX_CURRENT (1.0)
    total_produce_requests_per_sec must be present and >= _VOLUME_DROP_MIN_EXPECTED (150.0).
    """
    labels = {"env": "prod", "cluster_name": "cluster-a", "topic": "e2e-orders-topic"}
    return {
        "topic_messages_in_per_sec": [
            {"labels": labels, "value": 0.5},    # current (anomalously low)
            {"labels": labels, "value": 200.0},  # baseline (normal high)
        ],
        "total_produce_requests_per_sec": [
            {"labels": labels, "value": 200.0},
        ],
        "consumer_group_lag": [],
    }


# ── Kafka helpers ──────────────────────────────────────────────────────────────

def _create_kafka_topics(bootstrap_servers: str) -> None:
    """Create required Kafka topics and wait for completion."""
    admin = AdminClient({"bootstrap.servers": bootstrap_servers})
    fs = admin.create_topics(
        [
            NewTopic(_CASE_HEADER_TOPIC, num_partitions=1, replication_factor=1),
            NewTopic(_TRIAGE_EXCERPT_TOPIC, num_partitions=1, replication_factor=1),
        ]
    )
    for _topic, future in fs.items():
        try:
            future.result()
        except Exception:  # noqa: BLE001
            pass  # topic may already exist from a prior test in this module


def _consume_one_message(
    bootstrap_servers: str, topic: str, case_id: str, timeout: float = 30.0
) -> bytes:
    """Poll until a message matching case_id is received from the topic or timeout expires.

    Uses a unique consumer group with auto.offset.reset=earliest so it reads from
    the beginning of the partition. Filters by case_id to avoid consuming messages
    published by other tests sharing the same module-scoped Kafka container.
    """
    consumer = Consumer(
        {
            "bootstrap.servers": bootstrap_servers,
            "group.id": f"e2e-test-consumer-{uuid.uuid4().hex[:8]}",
            "auto.offset.reset": "earliest",
        }
    )
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
            payload = msg.value()
            try:
                if json.loads(payload).get("case_id") == case_id:
                    return payload
            except Exception:  # noqa: BLE001
                pass  # malformed message — skip
    finally:
        consumer.close()
    raise TimeoutError(
        f"No message with case_id={case_id!r} received on topic {topic!r} within {timeout}s"
    )


# ── Shared pipeline helper ────────────────────────────────────────────────────

def _run_pipeline_to_casefile(
    *,
    case_id: str,
    redis_client,
    topology_snapshot,
    rulebook_policy,
    peak_policy,
    prometheus_metrics_contract,
    denylist,
):
    """Run evidence → peak → topology → gate-input → gate-decision → casefile.

    Returns (casefile, action_decision, gate_input, topology_output).
    Used by tests that need a fully assembled CaseFile without repeating setup.
    """
    evidence_output = collect_evidence_stage_output(_e2e_fixed_samples())
    peak_output = run_peak_stage_cycle(
        evidence_output=evidence_output,
        historical_windows_by_scope={},
        evaluation_time=datetime.now(UTC),
        peak_policy=peak_policy,
        rulebook_policy=rulebook_policy,
    )
    topology_output = run_topology_stage_cycle(
        evidence_output=evidence_output,
        snapshot=topology_snapshot,
    )
    gate_inputs_by_scope = run_gate_input_stage_cycle(
        evidence_output=evidence_output,
        peak_output=peak_output,
        context_by_scope=topology_output.context_by_scope,
    )
    dedupe_store = RedisActionDedupeStore(redis_client)
    decisions_by_scope = run_gate_decision_stage_cycle(
        gate_inputs_by_scope=gate_inputs_by_scope,
        rulebook_policy=rulebook_policy,
        dedupe_store=dedupe_store,
    )
    gate_input = gate_inputs_by_scope[_E2E_SCOPE][0]
    action_decision = decisions_by_scope[_E2E_SCOPE][0]
    casefile = assemble_casefile_triage_stage(
        scope=_E2E_SCOPE,
        evidence_output=evidence_output,
        peak_output=peak_output,
        topology_output=topology_output,
        gate_input=gate_input,
        action_decision=action_decision,
        rulebook_policy=rulebook_policy,
        peak_policy=peak_policy,
        prometheus_metrics_contract=prometheus_metrics_contract,
        denylist=denylist,
        diagnosis_policy_version="v1",
        case_id=case_id,
    )
    return casefile, action_decision, gate_input, topology_output


# ── Module-scoped container fixtures ──────────────────────────────────────────

@pytest.fixture(scope="module")
def kafka_container():
    try:
        with KafkaContainer("confluentinc/cp-kafka:7.5.0") as container:
            yield container
    except Exception as exc:  # noqa: BLE001
        if _is_environment_prereq_error(exc):
            pytest.skip(f"Docker/Kafka unavailable: {exc}")
        raise


@pytest.fixture(scope="module")
def redis_container():
    try:
        with DockerContainer("redis:7.2-alpine").with_exposed_ports(6379) as container:
            host = container.get_container_host_ip()
            port = int(container.get_exposed_port(6379))
            _wait_for_redis(host, port)
            yield container
    except Exception as exc:  # noqa: BLE001
        if _is_environment_prereq_error(exc):
            pytest.skip(f"Docker/Redis unavailable: {exc}")
        raise


@pytest.fixture(scope="module")
def postgres_container():
    try:
        with PostgresContainer("postgres:16") as container:
            yield container
    except Exception as exc:  # noqa: BLE001
        if _is_environment_prereq_error(exc):
            pytest.skip(f"Docker/Postgres unavailable: {exc}")
        raise


@pytest.fixture(scope="module")
def minio_container():
    try:
        with (
            DockerContainer(_MINIO_IMAGE)
            .with_env("MINIO_ROOT_USER", _MINIO_ACCESS_KEY)
            .with_env("MINIO_ROOT_PASSWORD", _MINIO_SECRET_KEY)
            .with_command("server /data --address :9000")
            .with_exposed_ports(9000) as container
        ):
            host = container.get_container_host_ip()
            port = int(container.get_exposed_port(9000))
            endpoint_url = f"http://{host}:{port}"
            _wait_for_minio(endpoint_url)
            yield container
    except Exception as exc:  # noqa: BLE001
        if _is_environment_prereq_error(exc):
            pytest.skip(f"Docker/MinIO unavailable: {exc}")
        raise


# ── Module-scoped infrastructure fixtures ─────────────────────────────────────

@pytest.fixture(scope="module")
def minio_clients(minio_container):
    """Return (raw_s3_client, S3ObjectStoreClient) tuple with bucket pre-created."""
    host = minio_container.get_container_host_ip()
    port = int(minio_container.get_exposed_port(9000))
    endpoint_url = f"http://{host}:{port}"
    s3_client = boto3.client(
        "s3",
        endpoint_url=endpoint_url,
        aws_access_key_id=_MINIO_ACCESS_KEY,
        aws_secret_access_key=_MINIO_SECRET_KEY,
        region_name="us-east-1",
    )
    s3_client.create_bucket(Bucket=_MINIO_BUCKET)
    object_store_client = S3ObjectStoreClient(s3_client=s3_client, bucket=_MINIO_BUCKET)
    return s3_client, object_store_client


@pytest.fixture(scope="module")
def outbox_engine(postgres_container):
    """SQLAlchemy engine with outbox table created once per module."""
    connection_url = postgres_container.get_connection_url().replace(
        "postgresql+psycopg2://",
        "postgresql+psycopg://",
    )
    if connection_url.startswith("postgresql://"):
        connection_url = connection_url.replace("postgresql://", "postgresql+psycopg://")
    engine = create_engine(connection_url)
    create_outbox_table(engine)
    return engine


@pytest.fixture(scope="module")
def topology_snapshot(tmp_path_factory):
    """Load topology registry from E2E YAML written to a temp directory."""
    tmp = tmp_path_factory.mktemp("topology")
    registry_path = tmp / "e2e-registry.yaml"
    registry_path.write_text(_e2e_topology_yaml(), encoding="utf-8")
    return load_topology_registry(registry_path)


@pytest.fixture(scope="module")
def kafka_bootstrap(kafka_container):
    """Bootstrap server string with Kafka topics pre-created."""
    bootstrap = kafka_container.get_bootstrap_server()
    _create_kafka_topics(bootstrap)
    return bootstrap


# ── Module-scoped policy fixtures ─────────────────────────────────────────────

@pytest.fixture(scope="module")
def rulebook_policy() -> RulebookV1:
    return load_rulebook_policy()


@pytest.fixture(scope="module")
def peak_policy() -> PeakPolicyV1:
    return load_peak_policy()


@pytest.fixture(scope="module")
def prometheus_metrics_contract() -> PrometheusMetricsContractV1:
    return load_policy_yaml(
        _POLICY_DIR / "prometheus-metrics-contract-v1.yaml",
        PrometheusMetricsContractV1,
    )


@pytest.fixture(scope="module")
def denylist() -> DenylistV1:
    return load_denylist(_DENYLIST_PATH)


@pytest.fixture(scope="module")
def outbox_policy() -> OutboxPolicyV1:
    return load_policy_yaml(_POLICY_DIR / "outbox-policy-v1.yaml", OutboxPolicyV1)


# ── Function-scoped fixtures ──────────────────────────────────────────────────

@pytest.fixture()
def redis_client(redis_container):
    """Fresh Redis client with database flushed before each test."""
    client = redis_lib.Redis(
        host=redis_container.get_container_host_ip(),
        port=int(redis_container.get_exposed_port(6379)),
        decode_responses=True,
    )
    client.flushall()
    return client


# ── Tests ─────────────────────────────────────────────────────────────────────


@pytest.mark.integration
def test_hot_path_e2e_full_pipeline(
    kafka_bootstrap,
    redis_client,
    outbox_engine,
    minio_clients,
    topology_snapshot,
    rulebook_policy,
    peak_policy,
    prometheus_metrics_contract,
    denylist,
    outbox_policy,
) -> None:
    """Full hot-path from fixed evidence samples through Kafka publish and action dispatch."""
    s3_client, object_store_client = minio_clients
    case_id = f"e2e-case-{uuid.uuid4().hex[:8]}"

    # Stage 1: Evidence
    evidence_output = collect_evidence_stage_output(_e2e_fixed_samples())
    assert _E2E_SCOPE in evidence_output.gate_findings_by_scope, (
        "VOLUME_DROP finding expected for E2E scope"
    )

    # Stage 2: Peak (empty historical windows → peak=None, sustained=False)
    peak_output = run_peak_stage_cycle(
        evidence_output=evidence_output,
        historical_windows_by_scope={},
        evaluation_time=datetime.now(UTC),
        peak_policy=peak_policy,
        rulebook_policy=rulebook_policy,
    )

    # Stage 3: Topology
    topology_output = run_topology_stage_cycle(
        evidence_output=evidence_output,
        snapshot=topology_snapshot,
    )
    assert _E2E_SCOPE in topology_output.context_by_scope, "Topology scope must resolve"

    # Stage 6a: Gate-input assembly
    gate_inputs_by_scope = run_gate_input_stage_cycle(
        evidence_output=evidence_output,
        peak_output=peak_output,
        context_by_scope=topology_output.context_by_scope,
    )
    assert _E2E_SCOPE in gate_inputs_by_scope
    gate_input = gate_inputs_by_scope[_E2E_SCOPE][0]

    # Stage 6b: Gate-decision evaluation
    dedupe_store = RedisActionDedupeStore(redis_client)
    decisions_by_scope = run_gate_decision_stage_cycle(
        gate_inputs_by_scope=gate_inputs_by_scope,
        rulebook_policy=rulebook_policy,
        dedupe_store=dedupe_store,
    )
    assert _E2E_SCOPE in decisions_by_scope
    action_decision = decisions_by_scope[_E2E_SCOPE][0]

    assert action_decision.final_action == Action.OBSERVE
    assert action_decision.env_cap_applied is False
    assert action_decision.postmortem_required is False
    assert action_decision.gate_rule_ids == ("AG0", "AG1", "AG2", "AG3", "AG4", "AG5", "AG6")

    # Stage 4: CaseFile assembly
    casefile = assemble_casefile_triage_stage(
        scope=_E2E_SCOPE,
        evidence_output=evidence_output,
        peak_output=peak_output,
        topology_output=topology_output,
        gate_input=gate_input,
        action_decision=action_decision,
        rulebook_policy=rulebook_policy,
        peak_policy=peak_policy,
        prometheus_metrics_contract=prometheus_metrics_contract,
        denylist=denylist,
        diagnosis_policy_version="v1",
        case_id=case_id,
    )
    assert casefile.case_id == case_id
    assert casefile.triage_hash != "PLACEHOLDER"

    # Persist CaseFile to MinIO
    confirmed_casefile = persist_casefile_and_prepare_outbox_ready(
        casefile=casefile,
        object_store_client=object_store_client,
    )

    # Assert Invariant A: object exists in MinIO BEFORE outbox publish
    try:
        s3_client.head_object(Bucket=_MINIO_BUCKET, Key=confirmed_casefile.object_path)
    except ClientError as exc:
        pytest.fail(
            f"Invariant A violated: object {confirmed_casefile.object_path!r} "
            f"not found in MinIO before outbox publish: {exc}"
        )

    # Build READY outbox record
    repository = OutboxSqlRepository(engine=outbox_engine)
    build_outbox_ready_record(
        confirmed_casefile=confirmed_casefile,
        outbox_repository=repository,
    )
    ready_rows = repository.select_publishable(limit=10)
    assert any(r.case_id == case_id for r in ready_rows)

    # Create Kafka publisher and outbox worker
    producer = Producer({"bootstrap.servers": kafka_bootstrap})
    kafka_publisher = ConfluentKafkaCaseEventPublisher(
        producer=producer,
        case_header_topic=_CASE_HEADER_TOPIC,
        triage_excerpt_topic=_TRIAGE_EXCERPT_TOPIC,
    )
    worker = OutboxPublisherWorker(
        outbox_repository=repository,
        object_store_client=object_store_client,
        publisher=kafka_publisher,
        denylist=denylist,
        policy=outbox_policy,
        app_env="local",
    )

    result = worker.run_once(now=datetime.now(UTC))
    assert result.sent_count >= 1

    sent = repository.get_by_case_id(case_id)
    assert sent is not None
    assert sent.status == "SENT"

    # Consume CaseHeaderEventV1 from Kafka
    header_bytes = _consume_one_message(kafka_bootstrap, _CASE_HEADER_TOPIC, case_id=case_id)
    header_event = CaseHeaderEventV1.model_validate_json(header_bytes)
    assert header_event.case_id == case_id

    # Consume TriageExcerptV1 from Kafka
    excerpt_bytes = _consume_one_message(kafka_bootstrap, _TRIAGE_EXCERPT_TOPIC, case_id=case_id)
    excerpt_event = TriageExcerptV1.model_validate_json(excerpt_bytes)
    assert excerpt_event.case_id == case_id

    # Stage 7: Action dispatch (LOG mode — no real outbound calls)
    routing_context = topology_output.routing_by_scope.get(_E2E_SCOPE)
    assert routing_context is not None, (
        "routing_by_scope missing E2E scope — topology routing failed"
    )
    pd_client = PagerDutyClient(mode=PagerDutyIntegrationMode.LOG)
    slack_client = SlackClient(mode=SlackIntegrationMode.LOG)
    dispatch_action(
        case_id=case_id,
        decision=action_decision,
        routing_context=routing_context,
        pd_client=pd_client,
        slack_client=slack_client,
        denylist=denylist,
    )


@pytest.mark.integration
def test_hot_path_invariant_b2_crash_recovery(
    kafka_bootstrap,
    outbox_engine,
    minio_clients,
    topology_snapshot,
    rulebook_policy,
    peak_policy,
    prometheus_metrics_contract,
    denylist,
    outbox_policy,
    redis_client,
) -> None:
    """Invariant B2: outbox worker recovers a READY record inserted after simulated crash."""
    _, object_store_client = minio_clients
    case_id = f"e2e-b2-{uuid.uuid4().hex[:8]}"

    casefile, _, _, _ = _run_pipeline_to_casefile(
        case_id=case_id,
        redis_client=redis_client,
        topology_snapshot=topology_snapshot,
        rulebook_policy=rulebook_policy,
        peak_policy=peak_policy,
        prometheus_metrics_contract=prometheus_metrics_contract,
        denylist=denylist,
    )

    # Write MinIO (simulate crash after write, before Kafka publish)
    confirmed_casefile = persist_casefile_and_prepare_outbox_ready(
        casefile=casefile,
        object_store_client=object_store_client,
    )

    # Directly insert READY record without calling Kafka — simulates crash scenario
    repository = OutboxSqlRepository(engine=outbox_engine)
    build_outbox_ready_record(
        confirmed_casefile=confirmed_casefile,
        outbox_repository=repository,
    )

    record = repository.get_by_case_id(case_id)
    assert record is not None
    assert record.status == "READY"

    # Worker recovers: reads CaseFile from MinIO, publishes to Kafka
    producer = Producer({"bootstrap.servers": kafka_bootstrap})
    kafka_publisher = ConfluentKafkaCaseEventPublisher(
        producer=producer,
        case_header_topic=_CASE_HEADER_TOPIC,
        triage_excerpt_topic=_TRIAGE_EXCERPT_TOPIC,
    )
    worker = OutboxPublisherWorker(
        outbox_repository=repository,
        object_store_client=object_store_client,
        publisher=kafka_publisher,
        denylist=denylist,
        policy=outbox_policy,
        app_env="local",
    )
    result = worker.run_once(now=datetime.now(UTC))
    assert result.sent_count >= 1

    sent = repository.get_by_case_id(case_id)
    assert sent is not None
    assert sent.status == "SENT"

    # Verify header received on Kafka
    header_bytes = _consume_one_message(kafka_bootstrap, _CASE_HEADER_TOPIC, case_id=case_id)
    header_event = CaseHeaderEventV1.model_validate_json(header_bytes)
    assert header_event.case_id == case_id

    # Verify triage excerpt also published as part of recovery (both events must be present)
    excerpt_bytes = _consume_one_message(kafka_bootstrap, _TRIAGE_EXCERPT_TOPIC, case_id=case_id)
    excerpt_event = TriageExcerptV1.model_validate_json(excerpt_bytes)
    assert excerpt_event.case_id == case_id


@pytest.mark.integration
def test_casefile_structure_completeness(
    minio_clients,
    topology_snapshot,
    rulebook_policy,
    peak_policy,
    prometheus_metrics_contract,
    denylist,
    redis_client,
) -> None:
    """CaseFile persisted to MinIO contains all required structural fields."""
    _, object_store_client = minio_clients
    case_id = f"e2e-struct-{uuid.uuid4().hex[:8]}"

    casefile, _, _, _ = _run_pipeline_to_casefile(
        case_id=case_id,
        redis_client=redis_client,
        topology_snapshot=topology_snapshot,
        rulebook_policy=rulebook_policy,
        peak_policy=peak_policy,
        prometheus_metrics_contract=prometheus_metrics_contract,
        denylist=denylist,
    )

    # Persist to MinIO and deserialize back
    confirmed_casefile = persist_casefile_and_prepare_outbox_ready(
        casefile=casefile,
        object_store_client=object_store_client,
    )
    raw_bytes = object_store_client.get_object_bytes(key=confirmed_casefile.object_path)
    deserialized = validate_casefile_triage_json(raw_bytes)

    # Structural completeness assertions
    assert deserialized.case_id == case_id
    assert deserialized.triage_hash != "PLACEHOLDER"
    assert deserialized.gate_input.action_fingerprint != ""
    assert deserialized.action_decision.gate_rule_ids == (
        "AG0",
        "AG1",
        "AG2",
        "AG3",
        "AG4",
        "AG5",
        "AG6",
    )
    assert isinstance(deserialized.action_decision.gate_reason_codes, tuple)
    assert deserialized.policy_versions.rulebook_version != ""
    assert deserialized.policy_versions.peak_policy_version != ""
    assert deserialized.policy_versions.prometheus_metrics_contract_version != ""
    assert deserialized.policy_versions.exposure_denylist_version != ""
    assert deserialized.policy_versions.diagnosis_policy_version != ""

    # SHA-256 hash roundtrip
    assert compute_casefile_triage_hash(deserialized) == deserialized.triage_hash


@pytest.mark.integration
def test_action_decision_determinism(
    topology_snapshot,
    rulebook_policy,
    peak_policy,
    prometheus_metrics_contract,
    denylist,
    redis_client,
) -> None:
    """Gate-decision evaluation is deterministic across two independent runs."""
    evidence_output = collect_evidence_stage_output(_e2e_fixed_samples())
    peak_output = run_peak_stage_cycle(
        evidence_output=evidence_output,
        historical_windows_by_scope={},
        evaluation_time=datetime.now(UTC),
        peak_policy=peak_policy,
        rulebook_policy=rulebook_policy,
    )
    topology_output = run_topology_stage_cycle(
        evidence_output=evidence_output,
        snapshot=topology_snapshot,
    )
    gate_inputs_by_scope = run_gate_input_stage_cycle(
        evidence_output=evidence_output,
        peak_output=peak_output,
        context_by_scope=topology_output.context_by_scope,
    )
    gate_input = gate_inputs_by_scope[_E2E_SCOPE][0]

    # Run evaluation twice with a freshly-flushed Redis instance.
    # Unique fingerprints prevent AG5 suppression across runs.
    fp_first = f"e2e-det-{uuid.uuid4().hex[:8]}"
    fp_second = f"e2e-det-{uuid.uuid4().hex[:8]}"
    gate_input_first = gate_input.model_copy(update={"action_fingerprint": fp_first})
    gate_input_second = gate_input.model_copy(update={"action_fingerprint": fp_second})

    store = RedisActionDedupeStore(redis_client)

    result_first = run_gate_decision_stage_cycle(
        gate_inputs_by_scope={_E2E_SCOPE: (gate_input_first,)},
        rulebook_policy=rulebook_policy,
        dedupe_store=store,
    )
    result_second = run_gate_decision_stage_cycle(
        gate_inputs_by_scope={_E2E_SCOPE: (gate_input_second,)},
        rulebook_policy=rulebook_policy,
        dedupe_store=store,
    )

    decision_first = result_first[_E2E_SCOPE][0]
    decision_second = result_second[_E2E_SCOPE][0]

    # Determinism assertions
    assert decision_first.final_action == decision_second.final_action
    assert decision_first.gate_rule_ids == decision_second.gate_rule_ids
    assert decision_first.env_cap_applied == decision_second.env_cap_applied

    # Expected values for the E2E OBSERVE path
    assert decision_first.final_action == Action.OBSERVE
    assert decision_first.env_cap_applied is False
    assert decision_first.postmortem_required is False
    assert decision_first.gate_rule_ids == ("AG0", "AG1", "AG2", "AG3", "AG4", "AG5", "AG6")
