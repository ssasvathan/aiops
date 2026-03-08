from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import patch

from sqlalchemy import create_engine

from aiops_triage_pipeline.contracts.action_decision import ActionDecisionV1
from aiops_triage_pipeline.contracts.enums import (
    Action,
    CriticalityTier,
    Environment,
    EvidenceStatus,
)
from aiops_triage_pipeline.contracts.gate_input import Finding, GateInputV1
from aiops_triage_pipeline.contracts.sn_linkage import ServiceNowLinkageContractV1
from aiops_triage_pipeline.integrations.servicenow import ServiceNowLinkageWriteResult
from aiops_triage_pipeline.linkage.repository import ServiceNowLinkageRetrySqlRepository
from aiops_triage_pipeline.linkage.state_machine import (
    mark_linkage_failure,
    mark_linkage_searching,
    mark_linkage_success,
)
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


class _SequencedServiceNowClient:
    def __init__(
        self,
        *,
        results: tuple[ServiceNowLinkageWriteResult, ...],
        linkage_contract: ServiceNowLinkageContractV1,
    ) -> None:
        self._results = list(results)
        self._linkage_contract = linkage_contract
        self.calls: list[dict[str, object]] = []

    @property
    def linkage_contract(self) -> ServiceNowLinkageContractV1:
        return self._linkage_contract

    def upsert_problem_and_pir_tasks(self, **kwargs: object) -> ServiceNowLinkageWriteResult:
        self.calls.append(kwargs)
        if not self._results:
            raise AssertionError("No fake ServiceNow linkage results left")
        return self._results.pop(0)


class _FakeSlackClient:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def send_linkage_failed_final_escalation(self, **kwargs: object) -> None:
        self.calls.append(kwargs)


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


def test_execute_servicenow_linkage_and_persist_retries_failed_temp_then_links() -> None:
    object_store_client = _FakeObjectStoreClient()
    triage = _sample_casefile()
    persist_casefile_triage_write_once(
        object_store_client=object_store_client,
        casefile=triage,
    )
    repository = ServiceNowLinkageRetrySqlRepository(
        engine=create_engine("sqlite+pysqlite:///:memory:")
    )
    repository.ensure_schema()
    contract = ServiceNowLinkageContractV1(
        retry_window_minutes=120,
        retry_base_seconds=1,
        retry_max_seconds=2,
        retry_jitter_ratio=0.1,
    )
    servicenow_client = _SequencedServiceNowClient(
        linkage_contract=contract,
        results=(
            ServiceNowLinkageWriteResult(
                linkage_status="failed",
                linkage_reason="upsert_error",
                request_id="req-temp",
                incident_sys_id="inc-001",
                reason_metadata={
                    "error": "http_status=503",
                    "error_code": "http_5xx",
                },
            ),
            ServiceNowLinkageWriteResult(
                linkage_status="linked",
                linkage_reason="linked",
                request_id="req-linked",
                incident_sys_id="inc-001",
                problem_sys_id="prb-001",
                problem_external_id="aiops:problem:case:pd:hash",
                pir_task_sys_ids=("ptsk-001",),
                pir_task_external_ids=("aiops:pir-task:case:pd:hash:timeline",),
            ),
        ),
    )
    now = datetime(2026, 3, 8, 12, 0, tzinfo=UTC)

    first = execute_servicenow_linkage_and_persist(
        case_id=triage.case_id,
        pd_incident_id="pd-inc-001",
        incident_sys_id="inc-001",
        summary="link case",
        triage_hash=triage.triage_hash,
        object_store_client=object_store_client,
        servicenow_client=servicenow_client,  # type: ignore[arg-type]
        pir_task_types=("timeline",),
        linkage_retry_repository=repository,
        now=now,
    )
    assert first.linkage_result.linkage_state == "FAILED_TEMP"
    assert first.linkage_casefile is None
    assert first.linkage_object_path is None
    assert len(servicenow_client.calls) == 1

    scheduled = execute_servicenow_linkage_and_persist(
        case_id=triage.case_id,
        pd_incident_id="pd-inc-001",
        incident_sys_id="inc-001",
        summary="link case",
        triage_hash=triage.triage_hash,
        object_store_client=object_store_client,
        servicenow_client=servicenow_client,  # type: ignore[arg-type]
        pir_task_types=("timeline",),
        linkage_retry_repository=repository,
        now=now,
    )
    assert scheduled.linkage_result.linkage_reason == "retry_scheduled"
    assert len(servicenow_client.calls) == 1

    final = execute_servicenow_linkage_and_persist(
        case_id=triage.case_id,
        pd_incident_id="pd-inc-001",
        incident_sys_id="inc-001",
        summary="link case",
        triage_hash=triage.triage_hash,
        object_store_client=object_store_client,
        servicenow_client=servicenow_client,  # type: ignore[arg-type]
        pir_task_types=("timeline",),
        linkage_retry_repository=repository,
        now=now + timedelta(seconds=5),
    )
    assert final.linkage_result.linkage_state == "LINKED"
    assert final.linkage_object_path == f"cases/{triage.case_id}/linkage.json"
    assert final.linkage_casefile is not None
    assert len(servicenow_client.calls) == 2


def test_execute_servicenow_linkage_records_page_slo_metric_on_terminal_state_transition() -> None:
    object_store_client = _FakeObjectStoreClient()
    triage = _sample_casefile()
    persist_casefile_triage_write_once(
        object_store_client=object_store_client,
        casefile=triage,
    )
    repository = ServiceNowLinkageRetrySqlRepository(
        engine=create_engine("sqlite+pysqlite:///:memory:")
    )
    repository.ensure_schema()
    contract = ServiceNowLinkageContractV1(
        retry_window_minutes=120,
        retry_base_seconds=1,
        retry_max_seconds=2,
        retry_jitter_ratio=0.1,
    )
    servicenow_client = _SequencedServiceNowClient(
        linkage_contract=contract,
        results=(
            ServiceNowLinkageWriteResult(
                linkage_status="linked",
                linkage_reason="linked",
                request_id="req-linked",
                incident_sys_id="inc-001",
            ),
        ),
    )
    now = datetime(2026, 3, 8, 12, 0, tzinfo=UTC)

    with patch(
        "aiops_triage_pipeline.pipeline.stages.linkage.record_sn_page_linkage_slo"
    ) as metric_recorder:
        execute_servicenow_linkage_and_persist(
            case_id=triage.case_id,
            pd_incident_id="pd-inc-001",
            incident_sys_id="inc-001",
            summary="link case",
            triage_hash=triage.triage_hash,
            object_store_client=object_store_client,
            servicenow_client=servicenow_client,  # type: ignore[arg-type]
            pir_task_types=("timeline",),
            linkage_retry_repository=repository,
            context={"final_action": "PAGE"},
            now=now,
        )

    metric_recorder.assert_called_once_with(
        linkage_state="LINKED",
        within_retry_window=True,
    )


def test_execute_servicenow_linkage_skipped_status_does_not_record_page_slo_metric() -> None:
    object_store_client = _FakeObjectStoreClient()
    triage = _sample_casefile()
    persist_casefile_triage_write_once(
        object_store_client=object_store_client,
        casefile=triage,
    )
    servicenow_client = _FakeServiceNowClient(
        result=ServiceNowLinkageWriteResult(
            linkage_status="skipped",
            linkage_reason="mode_off",
            request_id="req-skip",
            incident_sys_id="inc-001",
        )
    )

    with patch(
        "aiops_triage_pipeline.pipeline.stages.linkage.record_sn_page_linkage_slo"
    ) as metric_recorder:
        execute_servicenow_linkage_and_persist(
            case_id=triage.case_id,
            pd_incident_id="pd-inc-001",
            incident_sys_id="inc-001",
            summary="link case",
            triage_hash=triage.triage_hash,
            object_store_client=object_store_client,
            servicenow_client=servicenow_client,  # type: ignore[arg-type]
            context={"final_action": "PAGE"},
        )

    metric_recorder.assert_not_called()


def test_execute_servicenow_linkage_and_persist_terminal_failed_final_skips_retries() -> None:
    object_store_client = _FakeObjectStoreClient()
    triage = _sample_casefile()
    persist_casefile_triage_write_once(
        object_store_client=object_store_client,
        casefile=triage,
    )
    repository = ServiceNowLinkageRetrySqlRepository(
        engine=create_engine("sqlite+pysqlite:///:memory:")
    )
    repository.ensure_schema()
    contract = ServiceNowLinkageContractV1(
        retry_window_minutes=1,
        retry_base_seconds=120,
        retry_max_seconds=120,
        retry_jitter_ratio=0.1,
    )
    servicenow_client = _SequencedServiceNowClient(
        linkage_contract=contract,
        results=(
            ServiceNowLinkageWriteResult(
                linkage_status="failed",
                linkage_reason="upsert_error",
                request_id="req-final",
                incident_sys_id="inc-001",
                reason_metadata={
                    "error": "http_status=503",
                    "error_code": "http_5xx",
                },
            ),
        ),
    )
    now = datetime(2026, 3, 8, 12, 0, tzinfo=UTC)

    first = execute_servicenow_linkage_and_persist(
        case_id=triage.case_id,
        pd_incident_id="pd-inc-001",
        incident_sys_id="inc-001",
        summary="link case",
        triage_hash=triage.triage_hash,
        object_store_client=object_store_client,
        servicenow_client=servicenow_client,  # type: ignore[arg-type]
        linkage_retry_repository=repository,
        now=now + timedelta(minutes=2),
    )
    assert first.linkage_result.linkage_state == "FAILED_FINAL"
    assert first.linkage_casefile is not None
    assert first.linkage_casefile.linkage_status == "failed"
    assert len(servicenow_client.calls) == 1

    second = execute_servicenow_linkage_and_persist(
        case_id=triage.case_id,
        pd_incident_id="pd-inc-001",
        incident_sys_id="inc-001",
        summary="link case",
        triage_hash=triage.triage_hash,
        object_store_client=object_store_client,
        servicenow_client=servicenow_client,  # type: ignore[arg-type]
        linkage_retry_repository=repository,
        now=now + timedelta(minutes=5),
    )
    assert second.linkage_result.linkage_reason == "failed_final_terminal"
    assert len(servicenow_client.calls) == 1


def test_execute_servicenow_linkage_and_persist_restores_missing_stage_for_linked_state() -> None:
    object_store_client = _FakeObjectStoreClient()
    triage = _sample_casefile()
    persist_casefile_triage_write_once(
        object_store_client=object_store_client,
        casefile=triage,
    )
    repository = ServiceNowLinkageRetrySqlRepository(
        engine=create_engine("sqlite+pysqlite:///:memory:")
    )
    repository.ensure_schema()
    now = datetime(2026, 3, 8, 12, 0, tzinfo=UTC)
    pending = repository.get_or_create_pending(
        case_id=triage.case_id,
        pd_incident_id="pd-inc-001",
        incident_sys_id="inc-001",
        retry_window_minutes=120,
        now=now,
    )
    searching = repository.persist_transition(
        case_id=triage.case_id,
        next_record=mark_linkage_searching(record=pending, now=now + timedelta(seconds=1)),
        expected_source_statuses={"PENDING"},
    )
    linked = repository.persist_transition(
        case_id=triage.case_id,
        next_record=mark_linkage_success(
            record=searching,
            request_id="req-linked-terminal",
            incident_sys_id="inc-001",
            reason_metadata={
                "problem_sys_id": "prb-001",
                "problem_external_id": "aiops:problem:case:pd:hash",
                "pir_task_sys_ids": ["ptsk-001"],
                "pir_task_external_ids": ["aiops:pir-task:case:pd:hash:timeline"],
            },
            now=now + timedelta(seconds=2),
        ),
        expected_source_statuses={"SEARCHING"},
    )
    assert linked.state == "LINKED"

    servicenow_client = _SequencedServiceNowClient(
        linkage_contract=ServiceNowLinkageContractV1(),
        results=(),
    )
    persisted = execute_servicenow_linkage_and_persist(
        case_id=triage.case_id,
        pd_incident_id="pd-inc-001",
        incident_sys_id="inc-001",
        summary="link case",
        triage_hash=triage.triage_hash,
        object_store_client=object_store_client,
        servicenow_client=servicenow_client,  # type: ignore[arg-type]
        linkage_retry_repository=repository,
        now=now + timedelta(minutes=1),
    )

    assert persisted.linkage_result.linkage_state == "LINKED"
    assert persisted.linkage_casefile is not None
    assert persisted.linkage_object_path == f"cases/{triage.case_id}/linkage.json"
    assert persisted.linkage_casefile.problem_sys_id == "prb-001"
    assert persisted.linkage_casefile.pir_task_sys_ids == ("ptsk-001",)
    assert len(servicenow_client.calls) == 0


def test_failed_final_escalates_for_non_failed_linkage_status() -> None:
    object_store_client = _FakeObjectStoreClient()
    triage = _sample_casefile()
    persist_casefile_triage_write_once(
        object_store_client=object_store_client,
        casefile=triage,
    )
    repository = ServiceNowLinkageRetrySqlRepository(
        engine=create_engine("sqlite+pysqlite:///:memory:")
    )
    repository.ensure_schema()
    contract = ServiceNowLinkageContractV1(
        retry_window_minutes=120,
        retry_base_seconds=30,
        retry_max_seconds=900,
        retry_jitter_ratio=0.2,
    )
    servicenow_client = _SequencedServiceNowClient(
        linkage_contract=contract,
        results=(
            ServiceNowLinkageWriteResult(
                linkage_status="not-linked",
                linkage_reason="missing_incident_sys_id",
                request_id="req-not-linked",
                incident_sys_id=None,
            ),
        ),
    )
    slack_client = _FakeSlackClient()
    now = datetime(2026, 3, 8, 12, 0, tzinfo=UTC)

    persisted = execute_servicenow_linkage_and_persist(
        case_id=triage.case_id,
        pd_incident_id="pd-inc-001",
        incident_sys_id=None,
        summary="link case",
        triage_hash=triage.triage_hash,
        object_store_client=object_store_client,
        servicenow_client=servicenow_client,  # type: ignore[arg-type]
        linkage_retry_repository=repository,
        slack_client=slack_client,  # type: ignore[arg-type]
        now=now,
    )

    assert persisted.linkage_result.linkage_state == "FAILED_FINAL"
    assert persisted.linkage_casefile is not None
    assert persisted.linkage_casefile.linkage_status == "not-linked"
    assert len(slack_client.calls) == 1


def test_execute_servicenow_linkage_and_persist_restores_missing_stage_for_failed_final_state(
) -> None:
    object_store_client = _FakeObjectStoreClient()
    triage = _sample_casefile()
    persist_casefile_triage_write_once(
        object_store_client=object_store_client,
        casefile=triage,
    )
    repository = ServiceNowLinkageRetrySqlRepository(
        engine=create_engine("sqlite+pysqlite:///:memory:")
    )
    repository.ensure_schema()
    now = datetime(2026, 3, 8, 12, 0, tzinfo=UTC)
    pending = repository.get_or_create_pending(
        case_id=triage.case_id,
        pd_incident_id="pd-inc-001",
        incident_sys_id="inc-001",
        retry_window_minutes=120,
        now=now,
    )
    searching = repository.persist_transition(
        case_id=triage.case_id,
        next_record=mark_linkage_searching(record=pending, now=now + timedelta(seconds=1)),
        expected_source_statuses={"PENDING"},
    )
    failed_final = repository.persist_transition(
        case_id=triage.case_id,
        next_record=mark_linkage_failure(
            record=searching,
            transient=False,
            error_code="invalid_input",
            error_message="missing_incident_sys_id",
            request_id="req-final-terminal",
            retry_base_seconds=30,
            retry_max_seconds=900,
            retry_jitter_ratio=0.2,
            reason_metadata={"linkage_status": "not-linked"},
            now=now + timedelta(seconds=2),
        ),
        expected_source_statuses={"SEARCHING"},
    )
    assert failed_final.state == "FAILED_FINAL"

    servicenow_client = _SequencedServiceNowClient(
        linkage_contract=ServiceNowLinkageContractV1(),
        results=(),
    )
    persisted = execute_servicenow_linkage_and_persist(
        case_id=triage.case_id,
        pd_incident_id="pd-inc-001",
        incident_sys_id="inc-001",
        summary="link case",
        triage_hash=triage.triage_hash,
        object_store_client=object_store_client,
        servicenow_client=servicenow_client,  # type: ignore[arg-type]
        linkage_retry_repository=repository,
        now=now + timedelta(minutes=1),
    )

    assert persisted.linkage_result.linkage_state == "FAILED_FINAL"
    assert persisted.linkage_casefile is not None
    assert persisted.linkage_object_path == f"cases/{triage.case_id}/linkage.json"
    assert persisted.linkage_casefile.linkage_status == "not-linked"
    assert len(servicenow_client.calls) == 0
