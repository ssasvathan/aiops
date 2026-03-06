from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine

from aiops_triage_pipeline.contracts.action_decision import ActionDecisionV1
from aiops_triage_pipeline.contracts.case_header_event import CaseHeaderEventV1
from aiops_triage_pipeline.contracts.enums import (
    Action,
    CriticalityTier,
    Environment,
    EvidenceStatus,
)
from aiops_triage_pipeline.contracts.gate_input import Finding, GateInputV1
from aiops_triage_pipeline.errors.exceptions import CriticalDependencyError
from aiops_triage_pipeline.models.case_file import (
    TRIAGE_HASH_PLACEHOLDER,
    CaseFileEvidenceSnapshot,
    CaseFilePolicyVersions,
    CaseFileRoutingContext,
    CaseFileTopologyContext,
    CaseFileTriageV1,
)
from aiops_triage_pipeline.outbox.publisher import CaseHeaderPublisherProtocol
from aiops_triage_pipeline.outbox.repository import OutboxSqlRepository
from aiops_triage_pipeline.outbox.schema import (
    OutboxReadyCasefileV1,
    OutboxRecordV1,
    create_outbox_table,
)
from aiops_triage_pipeline.outbox.state_machine import create_ready_outbox_record
from aiops_triage_pipeline.pipeline.stages.outbox import (
    build_outbox_ready_record,
    build_outbox_ready_transition_payload,
    publish_case_header_after_confirmed_casefile,
)
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


def _sample_header_event(case_id: str) -> CaseHeaderEventV1:
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


class _InMemoryObjectStoreClient(ObjectStoreClientProtocol):
    def __init__(self, *, payload: bytes) -> None:
        self._payload = payload

    def put_if_absent(
        self,
        *,
        key: str,
        body: bytes,
        content_type: str,
        checksum_sha256: str | None = None,
        metadata: dict[str, str] | None = None,
    ) -> PutIfAbsentResult:
        del key, body, content_type, checksum_sha256, metadata
        return PutIfAbsentResult.CREATED

    def get_object_bytes(self, *, key: str) -> bytes:
        del key
        return self._payload


class _RecordingPublisher(CaseHeaderPublisherProtocol):
    def __init__(self) -> None:
        self.call_count = 0

    def publish_case_header(self, *, event: CaseHeaderEventV1) -> None:
        del event
        self.call_count += 1


class _RecordingOutboxRepository:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []
        self._pending: OutboxRecordV1 | None = None
        self._ready: OutboxRecordV1 | None = None

    def insert_pending_object(
        self,
        *,
        confirmed_casefile: OutboxReadyCasefileV1,
    ) -> OutboxRecordV1:
        self.calls.append(("insert_pending_object", confirmed_casefile.case_id))
        self._pending = create_ready_outbox_record(
            confirmed_casefile=confirmed_casefile
        ).model_copy(update={"status": "PENDING_OBJECT"})
        return self._pending

    def transition_to_ready(
        self,
        *,
        case_id: str,
    ) -> OutboxRecordV1:
        self.calls.append(("transition_to_ready", case_id))
        if self._pending is None:
            raise AssertionError("pending record must exist before READY transition")
        self._ready = self._pending.model_copy(update={"status": "READY"})
        return self._ready

    def transition_to_sent(
        self,
        *,
        case_id: str,
    ) -> OutboxRecordV1:
        self.calls.append(("transition_to_sent", case_id))
        if self._ready is None:
            raise AssertionError("ready record must exist before SENT transition")
        return self._ready.model_copy(update={"status": "SENT", "delivery_attempts": 1})


class _FailingOutboxRepository:
    def insert_pending_object(
        self,
        *,
        confirmed_casefile: OutboxReadyCasefileV1,
    ) -> OutboxRecordV1:
        del confirmed_casefile
        raise CriticalDependencyError("postgres unavailable")

    def transition_to_ready(
        self,
        *,
        case_id: str,
    ) -> OutboxRecordV1:
        del case_id
        raise AssertionError("should not be called")

    def transition_to_sent(
        self,
        *,
        case_id: str,
    ) -> OutboxRecordV1:
        del case_id
        raise AssertionError("should not be called")


def test_build_outbox_ready_transition_payload_includes_triage_hash() -> None:
    ready_casefile = _ready_casefile(_sample_casefile())

    payload = build_outbox_ready_transition_payload(confirmed_casefile=ready_casefile)

    assert payload["status"] == "READY"
    assert payload["case_id"] == ready_casefile.case_id
    assert payload["casefile_object_path"] == ready_casefile.object_path
    assert payload["triage_hash"] == ready_casefile.triage_hash


def test_build_outbox_ready_record_sets_ready_state() -> None:
    ready_casefile = _ready_casefile(_sample_casefile())

    outbox_record = build_outbox_ready_record(confirmed_casefile=ready_casefile)

    assert outbox_record.status == "READY"
    assert outbox_record.case_id == ready_casefile.case_id
    assert outbox_record.casefile_object_path == ready_casefile.object_path
    assert outbox_record.triage_hash == ready_casefile.triage_hash


def test_build_outbox_ready_record_persists_pending_then_ready_with_repository() -> None:
    ready_casefile = _ready_casefile(_sample_casefile())
    repository = _RecordingOutboxRepository()

    outbox_record = build_outbox_ready_record(
        confirmed_casefile=ready_casefile,
        outbox_repository=repository,
    )

    assert outbox_record.status == "READY"
    assert repository.calls == [
        ("insert_pending_object", ready_casefile.case_id),
        ("transition_to_ready", ready_casefile.case_id),
    ]


def test_build_outbox_ready_record_raises_halt_error_on_repository_failure() -> None:
    ready_casefile = _ready_casefile(_sample_casefile())

    with pytest.raises(CriticalDependencyError, match="postgres unavailable"):
        build_outbox_ready_record(
            confirmed_casefile=ready_casefile,
            outbox_repository=_FailingOutboxRepository(),
        )


def test_build_outbox_ready_record_persists_with_sql_repository() -> None:
    ready_casefile = _ready_casefile(_sample_casefile())
    engine = create_engine("sqlite+pysqlite:///:memory:")
    create_outbox_table(engine)
    repository = OutboxSqlRepository(engine=engine)

    outbox_record = build_outbox_ready_record(
        confirmed_casefile=ready_casefile,
        outbox_repository=repository,
    )
    persisted = repository.get_by_case_id(ready_casefile.case_id)

    assert outbox_record.status == "READY"
    assert persisted is not None
    assert persisted.status == "READY"
    assert persisted.case_id == ready_casefile.case_id


def test_sql_repository_transition_to_ready_is_idempotent() -> None:
    ready_casefile = _ready_casefile(_sample_casefile())
    engine = create_engine("sqlite+pysqlite:///:memory:")
    create_outbox_table(engine)
    repository = OutboxSqlRepository(engine=engine)

    repository.insert_pending_object(confirmed_casefile=ready_casefile)
    first = repository.transition_to_ready(case_id=ready_casefile.case_id)
    second = repository.transition_to_ready(case_id=ready_casefile.case_id)

    assert first.status == "READY"
    assert second.status == "READY"
    assert second.delivery_attempts == first.delivery_attempts


def test_sql_repository_transition_to_sent_is_idempotent() -> None:
    ready_casefile = _ready_casefile(_sample_casefile())
    engine = create_engine("sqlite+pysqlite:///:memory:")
    create_outbox_table(engine)
    repository = OutboxSqlRepository(engine=engine)

    repository.insert_pending_object(confirmed_casefile=ready_casefile)
    repository.transition_to_ready(case_id=ready_casefile.case_id)
    first = repository.transition_to_sent(case_id=ready_casefile.case_id)
    second = repository.transition_to_sent(case_id=ready_casefile.case_id)

    assert first.status == "SENT"
    assert first.delivery_attempts == 1
    assert second.status == "SENT"
    assert second.delivery_attempts == 1


def test_publish_case_header_after_confirmed_casefile_uses_ready_record_guardrail() -> None:
    casefile = _sample_casefile()
    ready_casefile = _ready_casefile(casefile)
    publisher = _RecordingPublisher()

    publish_case_header_after_confirmed_casefile(
        confirmed_casefile=ready_casefile,
        case_header_event=_sample_header_event(casefile.case_id),
        object_store_client=_InMemoryObjectStoreClient(payload=serialize_casefile_triage(casefile)),
        publisher=publisher,
    )

    assert publisher.call_count == 1


def test_publish_case_header_after_confirmed_casefile_transitions_to_sent_with_repository() -> None:
    casefile = _sample_casefile()
    ready_casefile = _ready_casefile(casefile)
    publisher = _RecordingPublisher()
    repository = _RecordingOutboxRepository()

    publish_case_header_after_confirmed_casefile(
        confirmed_casefile=ready_casefile,
        case_header_event=_sample_header_event(casefile.case_id),
        object_store_client=_InMemoryObjectStoreClient(payload=serialize_casefile_triage(casefile)),
        publisher=publisher,
        outbox_repository=repository,
    )

    assert publisher.call_count == 1
    assert repository.calls == [
        ("insert_pending_object", ready_casefile.case_id),
        ("transition_to_ready", ready_casefile.case_id),
        ("transition_to_sent", ready_casefile.case_id),
    ]
