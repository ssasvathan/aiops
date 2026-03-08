from __future__ import annotations

from datetime import UTC, datetime

from aiops_triage_pipeline.contracts.action_decision import ActionDecisionV1
from aiops_triage_pipeline.contracts.enums import (
    Action,
    CriticalityTier,
    Environment,
    EvidenceStatus,
)
from aiops_triage_pipeline.contracts.gate_input import Finding, GateInputV1
from aiops_triage_pipeline.integrations.servicenow import ServiceNowLinkageWriteResult
from aiops_triage_pipeline.models.case_file import (
    TRIAGE_HASH_PLACEHOLDER,
    CaseFileEvidenceSnapshot,
    CaseFilePolicyVersions,
    CaseFileRoutingContext,
    CaseFileTopologyContext,
    CaseFileTriageV1,
)
from aiops_triage_pipeline.pipeline.stages.linkage import (
    execute_servicenow_linkage_and_persist,
)
from aiops_triage_pipeline.storage.casefile_io import (
    compute_casefile_triage_hash,
    persist_casefile_triage_write_once,
    read_casefile_stage_json_or_none,
    serialize_casefile_triage,
)
from aiops_triage_pipeline.storage.client import ObjectStoreClientProtocol, PutIfAbsentResult


class _FakeObjectStoreClient(ObjectStoreClientProtocol):
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


class _FakeServiceNowClient:
    def __init__(self, *, result: ServiceNowLinkageWriteResult) -> None:
        self.result = result
        self.calls: list[dict[str, object]] = []

    def upsert_problem_and_pir_tasks(self, **kwargs: object) -> ServiceNowLinkageWriteResult:
        self.calls.append(kwargs)
        return self.result


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


def test_execute_servicenow_linkage_and_persist_writes_linkage_stage() -> None:
    object_store_client = _FakeObjectStoreClient()
    triage = _sample_casefile()
    persist_casefile_triage_write_once(
        object_store_client=object_store_client,
        casefile=triage,
    )
    servicenow_client = _FakeServiceNowClient(
        result=ServiceNowLinkageWriteResult(
            linkage_status="linked",
            linkage_reason="linked",
            request_id="req-1",
            incident_sys_id="inc-001",
            problem_sys_id="prb-001",
            problem_external_id="aiops:problem:case:pd:hash",
            pir_task_sys_ids=("ptsk-001",),
            pir_task_external_ids=("aiops:pir-task:case:pd:hash:timeline",),
        )
    )

    persisted = execute_servicenow_linkage_and_persist(
        case_id=triage.case_id,
        pd_incident_id="pd-inc-001",
        incident_sys_id="inc-001",
        summary="link case",
        triage_hash=triage.triage_hash,
        object_store_client=object_store_client,
        servicenow_client=servicenow_client,  # type: ignore[arg-type]
        pir_task_types=("timeline",),
    )

    assert persisted.linkage_object_path == f"cases/{triage.case_id}/linkage.json"
    loaded = read_casefile_stage_json_or_none(
        object_store_client=object_store_client,
        case_id=triage.case_id,
        stage="linkage",
    )
    assert loaded is not None
    assert loaded.problem_sys_id == "prb-001"
    assert loaded.pir_task_external_ids == ("aiops:pir-task:case:pd:hash:timeline",)
    assert len(servicenow_client.calls) == 1


def test_execute_servicenow_linkage_and_persist_records_failed_linkage_result() -> None:
    object_store_client = _FakeObjectStoreClient()
    triage = _sample_casefile()
    persist_casefile_triage_write_once(
        object_store_client=object_store_client,
        casefile=triage,
    )
    servicenow_client = _FakeServiceNowClient(
        result=ServiceNowLinkageWriteResult(
            linkage_status="failed",
            linkage_reason="upsert_error",
            request_id="req-2",
            incident_sys_id="inc-001",
            reason_metadata={"problem_reason": "lookup_error"},
        )
    )

    persisted = execute_servicenow_linkage_and_persist(
        case_id=triage.case_id,
        pd_incident_id="pd-inc-001",
        incident_sys_id="inc-001",
        summary="link case",
        triage_hash=triage.triage_hash,
        object_store_client=object_store_client,
        servicenow_client=servicenow_client,  # type: ignore[arg-type]
    )

    loaded = read_casefile_stage_json_or_none(
        object_store_client=object_store_client,
        case_id=triage.case_id,
        stage="linkage",
    )
    assert loaded is not None
    assert loaded.linkage_status == "failed"
    assert loaded.linkage_reason == "upsert_error"
    assert persisted.linkage_casefile.linkage_status == "failed"
    assert serialize_casefile_triage(triage) == object_store_client.store[
        f"cases/{triage.case_id}/triage.json"
    ]
