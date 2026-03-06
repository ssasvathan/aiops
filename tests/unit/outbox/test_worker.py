from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import create_engine

from aiops_triage_pipeline.contracts.action_decision import ActionDecisionV1
from aiops_triage_pipeline.contracts.enums import (
    Action,
    CriticalityTier,
    Environment,
    EvidenceStatus,
)
from aiops_triage_pipeline.contracts.gate_input import Finding, GateInputV1
from aiops_triage_pipeline.contracts.outbox_policy import OutboxPolicyV1, OutboxRetentionPolicy
from aiops_triage_pipeline.errors.exceptions import CriticalDependencyError
from aiops_triage_pipeline.models.case_file import (
    TRIAGE_HASH_PLACEHOLDER,
    CaseFileEvidenceSnapshot,
    CaseFilePolicyVersions,
    CaseFileRoutingContext,
    CaseFileTopologyContext,
    CaseFileTriageV1,
)
from aiops_triage_pipeline.outbox.repository import OutboxSqlRepository
from aiops_triage_pipeline.outbox.schema import OutboxReadyCasefileV1, create_outbox_table
from aiops_triage_pipeline.outbox.worker import OutboxPublisherWorker
from aiops_triage_pipeline.storage.casefile_io import (
    compute_casefile_triage_hash,
    serialize_casefile_triage,
)
from aiops_triage_pipeline.storage.client import ObjectStoreClientProtocol, PutIfAbsentResult


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


def _ready_casefile(casefile: CaseFileTriageV1) -> OutboxReadyCasefileV1:
    return OutboxReadyCasefileV1(
        case_id=casefile.case_id,
        object_path=f"cases/{casefile.case_id}/triage.json",
        triage_hash=casefile.triage_hash,
    )


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


class _RecordingPublisher:
    def __init__(self) -> None:
        self.calls = 0

    def publish_case_events(
        self,
        *,
        case_header_event: object,
        triage_excerpt_event: object,
    ) -> None:
        del case_header_event, triage_excerpt_event
        self.calls += 1


class _FailingPublisher:
    def publish_case_events(
        self,
        *,
        case_header_event: object,
        triage_excerpt_event: object,
    ) -> None:
        del case_header_event, triage_excerpt_event
        raise CriticalDependencyError("kafka unavailable")


def _policy_with_max_retry(max_retry_attempts: int) -> OutboxPolicyV1:
    return OutboxPolicyV1(
        retention_by_env={
            "local": OutboxRetentionPolicy(
                sent_retention_days=1,
                dead_retention_days=7,
                max_retry_attempts=max_retry_attempts,
            ),
            "dev": OutboxRetentionPolicy(sent_retention_days=3, dead_retention_days=14),
            "uat": OutboxRetentionPolicy(sent_retention_days=7, dead_retention_days=30),
            "prod": OutboxRetentionPolicy(sent_retention_days=14, dead_retention_days=90),
        }
    )


def test_outbox_worker_transitions_ready_to_sent_on_success() -> None:
    casefile = _sample_casefile()
    ready_casefile = _ready_casefile(casefile)
    object_store = _InMemoryObjectStoreClient()
    object_store.store[ready_casefile.object_path] = serialize_casefile_triage(casefile)
    engine = create_engine("sqlite+pysqlite:///:memory:")
    create_outbox_table(engine)
    repository = OutboxSqlRepository(engine=engine)
    repository.insert_pending_object(confirmed_casefile=ready_casefile)
    repository.transition_to_ready(case_id=casefile.case_id)

    worker = OutboxPublisherWorker(
        outbox_repository=repository,
        object_store_client=object_store,
        publisher=_RecordingPublisher(),
        policy=_policy_with_max_retry(max_retry_attempts=3),
        app_env="local",
    )

    worker.run_once(now=datetime(2026, 3, 6, 12, 0, tzinfo=UTC))
    persisted = repository.get_by_case_id(casefile.case_id)

    assert persisted is not None
    assert persisted.status == "SENT"
    assert persisted.delivery_attempts == 1


def test_outbox_worker_transitions_retry_to_dead_after_max_retries() -> None:
    casefile = _sample_casefile()
    ready_casefile = _ready_casefile(casefile)
    object_store = _InMemoryObjectStoreClient()
    object_store.store[ready_casefile.object_path] = serialize_casefile_triage(casefile)
    engine = create_engine("sqlite+pysqlite:///:memory:")
    create_outbox_table(engine)
    repository = OutboxSqlRepository(engine=engine)
    repository.insert_pending_object(confirmed_casefile=ready_casefile)
    repository.transition_to_ready(case_id=casefile.case_id)
    policy = _policy_with_max_retry(max_retry_attempts=1)

    worker = OutboxPublisherWorker(
        outbox_repository=repository,
        object_store_client=object_store,
        publisher=_FailingPublisher(),
        policy=policy,
        app_env="local",
    )

    first_attempt_time = datetime(2026, 3, 6, 12, 0, tzinfo=UTC)
    worker.run_once(now=first_attempt_time)
    after_first = repository.get_by_case_id(casefile.case_id)
    assert after_first is not None
    assert after_first.status == "RETRY"
    assert after_first.next_attempt_at is not None

    worker.run_once(now=after_first.next_attempt_at)
    after_second = repository.get_by_case_id(casefile.case_id)
    assert after_second is not None
    assert after_second.status == "DEAD"
    assert after_second.delivery_attempts == 2
