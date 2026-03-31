from __future__ import annotations

from datetime import UTC, datetime

import boto3
import pytest
from botocore.client import BaseClient
from testcontainers.core.container import DockerContainer

from aiops_triage_pipeline.contracts.action_decision import ActionDecisionV1
from aiops_triage_pipeline.contracts.case_header_event import CaseHeaderEventV1
from aiops_triage_pipeline.contracts.diagnosis_report import DiagnosisReportV1, EvidencePack
from aiops_triage_pipeline.contracts.enums import (
    Action,
    CriticalityTier,
    DiagnosisConfidence,
    Environment,
    EvidenceStatus,
)
from aiops_triage_pipeline.contracts.gate_input import Finding, GateInputV1
from aiops_triage_pipeline.errors.exceptions import CriticalDependencyError
from aiops_triage_pipeline.models.case_file import (
    DIAGNOSIS_HASH_PLACEHOLDER,
    TRIAGE_HASH_PLACEHOLDER,
    CaseFileDiagnosisV1,
    CaseFileEvidenceSnapshot,
    CaseFilePolicyVersions,
    CaseFileRoutingContext,
    CaseFileTopologyContext,
    CaseFileTriageV1,
)
from aiops_triage_pipeline.pipeline.stages.casefile import (
    get_existing_casefile_triage,
    load_casefile_diagnosis_stage_if_present,
    persist_casefile_and_prepare_outbox_ready,
    persist_casefile_diagnosis_stage,
)
from aiops_triage_pipeline.pipeline.stages.outbox import (
    build_outbox_ready_record,
    build_outbox_ready_transition_payload,
    publish_case_header_after_confirmed_casefile,
)
from aiops_triage_pipeline.storage.casefile_io import (
    compute_casefile_diagnosis_hash,
    compute_casefile_triage_hash,
    persist_casefile_triage_write_once,
    validate_casefile_triage_json,
)
from aiops_triage_pipeline.storage.client import (
    ObjectStoreClientProtocol,
    PutIfAbsentResult,
    S3ObjectStoreClient,
)
from tests.integration.conftest import _wait_for_minio

_MINIO_IMAGE = "minio/minio:RELEASE.2025-01-20T14-49-07Z"
_MINIO_ACCESS_KEY = "minioadmin"
_MINIO_SECRET_KEY = "minioadmin"
_MINIO_BUCKET = "aiops-cases-integration"


def _sample_casefile() -> CaseFileTriageV1:
    gate_input = GateInputV1(
        env=Environment.PROD,
        cluster_id="cluster-a",
        stream_id="stream-orders",
        topic="orders",
        topic_role="SOURCE_TOPIC",
        anomaly_family="VOLUME_DROP",
        criticality_tier=CriticalityTier.TIER_1,
        proposed_action=Action.TICKET,
        diagnosis_confidence=0.75,
        sustained=True,
        findings=(
            Finding(
                finding_id="f-volume-drop",
                name="VOLUME_DROP",
                is_anomalous=True,
                evidence_required=("topic_messages_in_per_sec",),
            ),
        ),
        evidence_status_map={"topic_messages_in_per_sec": EvidenceStatus.PRESENT},
        action_fingerprint=(
            "prod/cluster-a/stream-orders/SOURCE_TOPIC/orders/VOLUME_DROP/TIER_1"
        ),
        case_id="case-prod-cluster-a-orders-volume-drop",
    )
    action_decision = ActionDecisionV1(
        final_action=Action.TICKET,
        env_cap_applied=False,
        gate_rule_ids=("AG0", "AG1", "AG2"),
        gate_reason_codes=("PASS", "PASS", "PASS"),
        action_fingerprint=gate_input.action_fingerprint,
        postmortem_required=False,
    )
    base = CaseFileTriageV1(
        case_id="case-prod-cluster-a-orders-volume-drop",
        scope=("prod", "cluster-a", "orders"),
        triage_timestamp=datetime(2026, 3, 4, 12, 0, tzinfo=UTC),
        evidence_snapshot=CaseFileEvidenceSnapshot(
            evidence_status_map={"topic_messages_in_per_sec": EvidenceStatus.PRESENT},
        ),
        topology_context=CaseFileTopologyContext(
            stream_id="stream-orders",
            topic_role="SOURCE_TOPIC",
            criticality_tier=CriticalityTier.TIER_1,
            source_system="Payments",
            blast_radius="LOCAL_SOURCE_INGESTION",
            routing=CaseFileRoutingContext(
                lookup_level="topic_owner",
                routing_key="OWN::Streaming::Payments::Topic",
                owning_team_id="team-payments-topic",
                owning_team_name="Payments Topic Team",
            ),
        ),
        gate_input=gate_input,
        action_decision=action_decision,
        policy_versions=CaseFilePolicyVersions(
            rulebook_version="1",
            peak_policy_version="v1",
            prometheus_metrics_contract_version="v1.0.0",
            exposure_denylist_version="v1.0.0",
            diagnosis_policy_version="v1",
        ),
        triage_hash=TRIAGE_HASH_PLACEHOLDER,
    )
    return base.model_copy(update={"triage_hash": compute_casefile_triage_hash(base)})


def _sample_case_header_event(case_id: str) -> CaseHeaderEventV1:
    return CaseHeaderEventV1(
        case_id=case_id,
        env=Environment.PROD,
        cluster_id="cluster-a",
        stream_id="stream-orders",
        topic="orders",
        anomaly_family="VOLUME_DROP",
        criticality_tier=CriticalityTier.TIER_1,
        final_action=Action.TICKET,
        routing_key="OWN::Streaming::Payments::Topic",
        evaluation_ts=datetime(2026, 3, 4, 12, 0, tzinfo=UTC),
    )


def _sample_diagnosis_casefile(triage_casefile: CaseFileTriageV1) -> CaseFileDiagnosisV1:
    report = DiagnosisReportV1(
        case_id=triage_casefile.case_id,
        verdict="UNKNOWN",
        fault_domain=None,
        confidence=DiagnosisConfidence.LOW,
        evidence_pack=EvidencePack(
            facts=("lag trend elevated",),
            missing_evidence=("PRIMARY_DIAGNOSIS_ABSENT",),
            matched_rules=(),
        ),
        next_checks=("Inspect consumer group lag trend",),
        gaps=("PRIMARY_DIAGNOSIS_ABSENT",),
        reason_codes=("LLM_TIMEOUT",),
        triage_hash=triage_casefile.triage_hash,
    )
    base = CaseFileDiagnosisV1(
        case_id=triage_casefile.case_id,
        diagnosis_report=report,
        triage_hash=triage_casefile.triage_hash,
        diagnosis_hash=DIAGNOSIS_HASH_PLACEHOLDER,
    )
    return base.model_copy(update={"diagnosis_hash": compute_casefile_diagnosis_hash(base)})


@pytest.fixture
def minio_object_store() -> tuple[BaseClient, S3ObjectStoreClient]:
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

            s3_client = boto3.client(
                "s3",
                endpoint_url=endpoint_url,
                aws_access_key_id=_MINIO_ACCESS_KEY,
                aws_secret_access_key=_MINIO_SECRET_KEY,
                region_name="us-east-1",
            )
            s3_client.create_bucket(Bucket=_MINIO_BUCKET)

            yield s3_client, S3ObjectStoreClient(
                s3_client=s3_client,
                bucket=_MINIO_BUCKET,
            )
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"Docker/MinIO unavailable for integration test: {exc}")


class _FailFirstPutObjectStoreClient(ObjectStoreClientProtocol):
    def __init__(self, delegate: ObjectStoreClientProtocol) -> None:
        self._delegate = delegate
        self._failed_once = False

    def put_if_absent(
        self,
        *,
        key: str,
        body: bytes,
        content_type: str,
        checksum_sha256: str | None = None,
        metadata: dict[str, str] | None = None,
    ) -> PutIfAbsentResult:
        if not self._failed_once:
            self._failed_once = True
            raise CriticalDependencyError("transient object store unavailability")
        return self._delegate.put_if_absent(
            key=key,
            body=body,
            content_type=content_type,
            checksum_sha256=checksum_sha256,
            metadata=metadata,
        )

    def get_object_bytes(self, *, key: str) -> bytes:
        return self._delegate.get_object_bytes(key=key)


class _InMemoryObjectStoreClient(ObjectStoreClientProtocol):
    def __init__(self) -> None:
        self.store: dict[str, bytes] = {}

    def put_if_absent(
        self,
        *,
        key: str,
        body: bytes,
        content_type: str,
        checksum_sha256: str | None = None,
        metadata: dict[str, str] | None = None,
    ) -> PutIfAbsentResult:
        del content_type, checksum_sha256, metadata
        if key in self.store:
            return PutIfAbsentResult.EXISTS
        self.store[key] = body
        return PutIfAbsentResult.CREATED

    def get_object_bytes(self, *, key: str) -> bytes:
        return self.store[key]


class _RecordingHeaderPublisher:
    def __init__(self) -> None:
        self.published: list[CaseHeaderEventV1] = []

    def publish_case_header(self, *, event: CaseHeaderEventV1) -> None:
        self.published.append(event)


@pytest.mark.integration
def test_casefile_exists_before_outbox_ready_payload(
    minio_object_store: tuple[BaseClient, S3ObjectStoreClient],
) -> None:
    s3_client, object_store_client = minio_object_store
    casefile = _sample_casefile()
    existing_before_write = get_existing_casefile_triage(
        gate_input=casefile.gate_input,
        object_store_client=object_store_client,
    )

    assert existing_before_write is None
    ready_payload = persist_casefile_and_prepare_outbox_ready(
        casefile=casefile,
        object_store_client=object_store_client,
    )
    persisted_object = s3_client.get_object(Bucket=_MINIO_BUCKET, Key=ready_payload.object_path)
    persisted_payload = persisted_object["Body"].read()

    reconstructed = validate_casefile_triage_json(persisted_payload)
    assert reconstructed.case_id == casefile.case_id
    assert reconstructed.triage_hash == ready_payload.triage_hash

    outbox_payload = build_outbox_ready_transition_payload(
        confirmed_casefile=ready_payload,
    )
    outbox_record = build_outbox_ready_record(confirmed_casefile=ready_payload)
    publisher = _RecordingHeaderPublisher()
    publish_evidence = publish_case_header_after_confirmed_casefile(
        confirmed_casefile=ready_payload,
        case_header_event=_sample_case_header_event(casefile.case_id),
        object_store_client=object_store_client,
        publisher=publisher,
    )

    assert outbox_payload["status"] == "READY"
    assert outbox_payload["casefile_object_path"] == ready_payload.object_path
    assert outbox_record.triage_hash == ready_payload.triage_hash
    assert publish_evidence.case_id == casefile.case_id
    assert publish_evidence.triage_hash == ready_payload.triage_hash
    assert len(publisher.published) == 1


@pytest.mark.integration
def test_retry_after_transient_failure_remains_idempotent(
    minio_object_store: tuple[BaseClient, S3ObjectStoreClient],
) -> None:
    _, object_store_client = minio_object_store
    casefile = _sample_casefile()
    fail_once_client = _FailFirstPutObjectStoreClient(object_store_client)

    with pytest.raises(CriticalDependencyError, match="transient"):
        persist_casefile_and_prepare_outbox_ready(
            casefile=casefile,
            object_store_client=fail_once_client,
        )

    ready_payload = persist_casefile_and_prepare_outbox_ready(
        casefile=casefile,
        object_store_client=fail_once_client,
    )
    retry_result = persist_casefile_triage_write_once(
        object_store_client=object_store_client,
        casefile=casefile,
    )

    assert ready_payload.case_id == casefile.case_id
    assert ready_payload.triage_hash == casefile.triage_hash
    assert retry_result.write_result == "idempotent"


@pytest.mark.integration
def test_existing_triage_guard_preserves_existing_payload_without_rewrite(
    minio_object_store: tuple[BaseClient, S3ObjectStoreClient],
) -> None:
    s3_client, object_store_client = minio_object_store
    casefile = _sample_casefile()

    persisted = persist_casefile_triage_write_once(
        object_store_client=object_store_client,
        casefile=casefile,
    )
    original_payload = s3_client.get_object(Bucket=_MINIO_BUCKET, Key=persisted.object_path)[
        "Body"
    ].read()

    existing_casefile = get_existing_casefile_triage(
        gate_input=casefile.gate_input,
        object_store_client=object_store_client,
    )

    assert existing_casefile is not None
    assert existing_casefile.case_id == casefile.case_id
    assert existing_casefile.triage_hash == casefile.triage_hash

    reloaded_payload = s3_client.get_object(Bucket=_MINIO_BUCKET, Key=persisted.object_path)[
        "Body"
    ].read()
    assert reloaded_payload == original_payload


@pytest.mark.integration
def test_invariant_a_publish_guardrail_runs_without_docker() -> None:
    casefile = _sample_casefile()
    object_store_client = _InMemoryObjectStoreClient()
    publisher = _RecordingHeaderPublisher()

    ready_payload = persist_casefile_and_prepare_outbox_ready(
        casefile=casefile,
        object_store_client=object_store_client,
    )
    publish_evidence = publish_case_header_after_confirmed_casefile(
        confirmed_casefile=ready_payload,
        case_header_event=_sample_case_header_event(casefile.case_id),
        object_store_client=object_store_client,
        publisher=publisher,
    )

    assert publish_evidence.case_id == casefile.case_id
    assert publish_evidence.triage_hash == casefile.triage_hash
    assert len(publisher.published) == 1


@pytest.mark.integration
def test_diagnosis_stage_round_trip_reloads_with_valid_hash(
    minio_object_store: tuple[BaseClient, S3ObjectStoreClient],
) -> None:
    _, object_store_client = minio_object_store
    triage_casefile = _sample_casefile()
    persist_casefile_triage_write_once(
        object_store_client=object_store_client,
        casefile=triage_casefile,
    )
    diagnosis_casefile = _sample_diagnosis_casefile(triage_casefile)

    object_path = persist_casefile_diagnosis_stage(
        casefile=diagnosis_casefile,
        object_store_client=object_store_client,
    )
    loaded = load_casefile_diagnosis_stage_if_present(
        case_id=triage_casefile.case_id,
        object_store_client=object_store_client,
    )

    assert object_path.endswith("/diagnosis.json")
    assert loaded is not None
    assert loaded.case_id == triage_casefile.case_id
    assert loaded.triage_hash == triage_casefile.triage_hash
    assert loaded.diagnosis_hash == diagnosis_casefile.diagnosis_hash
    assert compute_casefile_diagnosis_hash(loaded) == loaded.diagnosis_hash
