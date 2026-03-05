from __future__ import annotations

from datetime import UTC, datetime

import pytest

from aiops_triage_pipeline.contracts.action_decision import ActionDecisionV1
from aiops_triage_pipeline.contracts.case_header_event import CaseHeaderEventV1
from aiops_triage_pipeline.contracts.enums import (
    Action,
    CriticalityTier,
    Environment,
    EvidenceStatus,
)
from aiops_triage_pipeline.contracts.gate_input import Finding, GateInputV1
from aiops_triage_pipeline.errors.exceptions import InvariantViolation
from aiops_triage_pipeline.models.case_file import (
    TRIAGE_HASH_PLACEHOLDER,
    CaseFileEvidenceSnapshot,
    CaseFilePolicyVersions,
    CaseFileRoutingContext,
    CaseFileTopologyContext,
    CaseFileTriageV1,
)
from aiops_triage_pipeline.outbox.publisher import (
    CaseHeaderPublisherProtocol,
    publish_case_header_after_invariant_a,
)
from aiops_triage_pipeline.outbox.schema import OutboxReadyCasefileV1
from aiops_triage_pipeline.outbox.state_machine import create_ready_outbox_record
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


def _ready_casefile(
    casefile: CaseFileTriageV1, triage_hash: str | None = None
) -> OutboxReadyCasefileV1:
    return OutboxReadyCasefileV1(
        case_id=casefile.case_id,
        object_path=f"cases/{casefile.case_id}/triage.json",
        triage_hash=triage_hash or casefile.triage_hash,
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


class _RecordingPublisher(CaseHeaderPublisherProtocol):
    def __init__(self) -> None:
        self.published: list[CaseHeaderEventV1] = []

    def publish_case_header(self, *, event: CaseHeaderEventV1) -> None:
        self.published.append(event)


def test_publish_case_header_after_invariant_a_requires_confirmed_object_readback() -> None:
    casefile = _sample_casefile()
    outbox_record = create_ready_outbox_record(confirmed_casefile=_ready_casefile(casefile))
    object_store = _InMemoryObjectStoreClient()
    object_store.store[outbox_record.casefile_object_path] = serialize_casefile_triage(casefile)
    publisher = _RecordingPublisher()

    evidence = publish_case_header_after_invariant_a(
        outbox_record=outbox_record,
        case_header_event=_sample_header_event(casefile.case_id),
        object_store_client=object_store,
        publisher=publisher,
    )

    assert len(publisher.published) == 1
    assert publisher.published[0].case_id == casefile.case_id
    assert evidence.triage_hash == casefile.triage_hash


def test_publish_case_header_after_invariant_a_blocks_publish_when_object_missing() -> None:
    casefile = _sample_casefile()
    outbox_record = create_ready_outbox_record(confirmed_casefile=_ready_casefile(casefile))
    publisher = _RecordingPublisher()

    with pytest.raises(InvariantViolation, match="before casefile object is readable"):
        publish_case_header_after_invariant_a(
            outbox_record=outbox_record,
            case_header_event=_sample_header_event(casefile.case_id),
            object_store_client=_InMemoryObjectStoreClient(),
            publisher=publisher,
        )

    assert publisher.published == []


def test_publish_case_header_after_invariant_a_blocks_hash_mismatch() -> None:
    casefile = _sample_casefile()
    outbox_record = create_ready_outbox_record(
        confirmed_casefile=_ready_casefile(casefile, triage_hash="f" * 64)
    )
    object_store = _InMemoryObjectStoreClient()
    object_store.store[outbox_record.casefile_object_path] = serialize_casefile_triage(casefile)
    publisher = _RecordingPublisher()

    with pytest.raises(InvariantViolation, match="triage_hash does not match"):
        publish_case_header_after_invariant_a(
            outbox_record=outbox_record,
            case_header_event=_sample_header_event(casefile.case_id),
            object_store_client=object_store,
            publisher=publisher,
        )

    assert publisher.published == []
