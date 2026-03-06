from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine
from testcontainers.postgres import PostgresContainer

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
from aiops_triage_pipeline.outbox.publisher import (
    CaseHeaderPublisherProtocol,
)
from aiops_triage_pipeline.outbox.repository import OutboxSqlRepository
from aiops_triage_pipeline.outbox.schema import OutboxReadyCasefileV1, create_outbox_table
from aiops_triage_pipeline.pipeline.stages.casefile import persist_casefile_and_prepare_outbox_ready
from aiops_triage_pipeline.pipeline.stages.outbox import (
    build_outbox_ready_record,
    publish_case_header_after_confirmed_casefile,
)
from aiops_triage_pipeline.storage.casefile_io import compute_casefile_triage_hash
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
        action_fingerprint="prod/cluster-a/stream-orders/SOURCE_TOPIC/orders/VOLUME_DROP/TIER_1",
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


class _RecordingHeaderPublisher(CaseHeaderPublisherProtocol):
    def __init__(self) -> None:
        self.published: list[CaseHeaderEventV1] = []

    def publish_case_header(self, *, event: CaseHeaderEventV1) -> None:
        self.published.append(event)


def _is_environment_prereq_error(exc: Exception) -> bool:
    text = f"{type(exc).__name__}: {exc}"
    return any(
        marker in text
        for marker in (
            "no pq wrapper available",
            "libpq library not found",
            "Error while fetching server API version",
            "DockerException",
            "Cannot connect to Docker daemon",
        )
    )


@pytest.mark.integration
def test_outbox_publish_after_crash_recovery_transitions_ready_to_sent() -> None:
    casefile = _sample_casefile()
    object_store = _InMemoryObjectStoreClient()
    publisher = _RecordingHeaderPublisher()
    ready_casefile = persist_casefile_and_prepare_outbox_ready(
        casefile=casefile,
        object_store_client=object_store,
    )
    try:
        with PostgresContainer("postgres:16") as postgres:
            connection_url = postgres.get_connection_url().replace(
                "postgresql+psycopg2://",
                "postgresql+psycopg://",
            )
            if connection_url.startswith("postgresql://"):
                connection_url = connection_url.replace("postgresql://", "postgresql+psycopg://")
            engine = create_engine(connection_url)
            create_outbox_table(engine)
            repository = OutboxSqlRepository(engine=engine)

            build_outbox_ready_record(
                confirmed_casefile=ready_casefile,
                outbox_repository=repository,
            )

            ready_rows = repository.select_publishable(limit=10)
            assert len(ready_rows) == 1
            assert ready_rows[0].status == "READY"

            publish_case_header_after_confirmed_casefile(
                confirmed_casefile=ready_casefile,
                case_header_event=_sample_case_header_event(casefile.case_id),
                object_store_client=object_store,
                publisher=publisher,
                outbox_repository=repository,
            )

            sent = repository.get_by_case_id(casefile.case_id)
            assert sent is not None
            assert sent.status == "SENT"
            assert sent.delivery_attempts == 1
            assert len(publisher.published) == 1
    except Exception as exc:  # noqa: BLE001
        if _is_environment_prereq_error(exc):
            pytest.skip(f"Docker/Postgres unavailable for integration test: {exc}")
        raise


@pytest.mark.integration
def test_outbox_stage_halts_when_postgres_unavailable() -> None:
    casefile = _sample_casefile()
    confirmed_casefile = OutboxReadyCasefileV1(
        case_id=casefile.case_id,
        object_path=f"cases/{casefile.case_id}/triage.json",
        triage_hash=casefile.triage_hash,
    )

    try:
        engine = create_engine("postgresql+psycopg://aiops:aiops@127.0.0.1:1/aiops")
    except Exception as exc:  # noqa: BLE001
        if _is_environment_prereq_error(exc):
            pytest.skip(f"Postgres driver unavailable for integration test: {exc}")
        raise
    repository = OutboxSqlRepository(engine=engine)

    with pytest.raises(CriticalDependencyError, match="outbox repository operation failed"):
        build_outbox_ready_record(
            confirmed_casefile=confirmed_casefile,
            outbox_repository=repository,
        )
