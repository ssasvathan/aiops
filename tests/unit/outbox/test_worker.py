from __future__ import annotations

from datetime import UTC, datetime

import pytest
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
from aiops_triage_pipeline.denylist.loader import DenylistV1
from aiops_triage_pipeline.errors.exceptions import CriticalDependencyError
from aiops_triage_pipeline.models.case_file import (
    TRIAGE_HASH_PLACEHOLDER,
    CaseFileEvidenceSnapshot,
    CaseFilePolicyVersions,
    CaseFileRoutingContext,
    CaseFileTopologyContext,
    CaseFileTriageV1,
)
from aiops_triage_pipeline.outbox.repository import OutboxHealthSnapshot, OutboxSqlRepository
from aiops_triage_pipeline.outbox.schema import (
    OutboxReadyCasefileV1,
    OutboxRecordV1,
    create_outbox_table,
)
from aiops_triage_pipeline.outbox.worker import OutboxPublisherWorker, _nearest_rank_percentile
from aiops_triage_pipeline.storage.casefile_io import (
    compute_casefile_triage_hash,
    serialize_casefile_triage,
)
from aiops_triage_pipeline.storage.client import ObjectStoreClientProtocol, PutIfAbsentResult


def _sample_casefile(case_id: str = "case-prod-cluster-a-orders-volume-drop") -> CaseFileTriageV1:
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
        case_id=case_id,
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
        case_id=case_id,
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
        self.excerpts: list[object] = []

    def publish_case_events(
        self,
        *,
        case_header_event: object,
        triage_excerpt_event: object,
    ) -> None:
        del case_header_event
        self.calls += 1
        self.excerpts.append(triage_excerpt_event)


class _FailingPublisher:
    def publish_case_events(
        self,
        *,
        case_header_event: object,
        triage_excerpt_event: object,
    ) -> None:
        del case_header_event, triage_excerpt_event
        raise CriticalDependencyError("kafka unavailable")


class _RecordingLogger:
    def __init__(self) -> None:
        self.events: list[tuple[str, str, dict[str, object]]] = []

    def info(self, event: str, **kwargs: object) -> None:
        self.events.append(("info", event, kwargs))

    def warning(self, event: str, **kwargs: object) -> None:
        self.events.append(("warning", event, kwargs))

    def critical(self, event: str, **kwargs: object) -> None:
        self.events.append(("critical", event, kwargs))


class _SnapshotOnlyRepository:
    def __init__(self, snapshot: OutboxHealthSnapshot) -> None:
        self._snapshot = snapshot

    def select_publishable(
        self,
        *,
        now: datetime | None = None,
        limit: int = 100,
    ) -> list[OutboxRecordV1]:
        del now, limit
        return []

    def transition_to_sent(
        self,
        *,
        case_id: str,
        now: datetime | None = None,
    ) -> OutboxRecordV1:
        del case_id, now
        raise AssertionError(
            "transition_to_sent should not be called for empty publishable snapshot"
        )

    def transition_publish_failure(
        self,
        *,
        case_id: str,
        policy: OutboxPolicyV1,
        app_env: str,
        error_message: str,
        error_code: str | None = None,
        now: datetime | None = None,
    ) -> OutboxRecordV1:
        del case_id, policy, app_env, error_message, error_code, now
        raise AssertionError(
            "transition_publish_failure should not be called for empty publishable snapshot"
        )

    def select_backlog_health(
        self,
        *,
        now: datetime | None = None,
    ) -> OutboxHealthSnapshot:
        del now
        return self._snapshot


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


def _denylist_for_tests(*, denied_field_names: tuple[str, ...] = ("password",)) -> DenylistV1:
    return DenylistV1(
        denylist_version="v1.0.0",
        denied_field_names=denied_field_names,
        denied_value_patterns=("(?i)bearer\\s+[A-Za-z0-9]{10,}",),
    )


def test_outbox_worker_transitions_ready_to_sent_on_success() -> None:
    casefile = _sample_casefile()
    updated_gate_input = casefile.gate_input.model_copy(
        update={
            "evidence_status_map": {
                "topic_messages_in_per_sec": EvidenceStatus.PRESENT,
                "password": EvidenceStatus.UNKNOWN,
            }
        }
    )
    updated_snapshot = casefile.evidence_snapshot.model_copy(
        update={
            "evidence_status_map": {
                "topic_messages_in_per_sec": EvidenceStatus.PRESENT,
                "password": EvidenceStatus.UNKNOWN,
            }
        }
    )
    casefile = casefile.model_copy(
        update={
            "gate_input": updated_gate_input,
            "evidence_snapshot": updated_snapshot,
            "triage_hash": TRIAGE_HASH_PLACEHOLDER,
        }
    )
    casefile = casefile.model_copy(
        update={"triage_hash": compute_casefile_triage_hash(casefile)}
    )
    ready_casefile = _ready_casefile(casefile)
    object_store = _InMemoryObjectStoreClient()
    object_store.store[ready_casefile.object_path] = serialize_casefile_triage(casefile)
    engine = create_engine("sqlite+pysqlite:///:memory:")
    create_outbox_table(engine)
    repository = OutboxSqlRepository(engine=engine)
    repository.insert_pending_object(confirmed_casefile=ready_casefile)
    repository.transition_to_ready(case_id=casefile.case_id)
    publisher = _RecordingPublisher()

    worker = OutboxPublisherWorker(
        outbox_repository=repository,
        object_store_client=object_store,
        publisher=publisher,
        denylist=_denylist_for_tests(),
        policy=_policy_with_max_retry(max_retry_attempts=3),
        app_env="local",
    )

    worker.run_once(now=datetime(2026, 3, 6, 12, 0, tzinfo=UTC))
    persisted = repository.get_by_case_id(casefile.case_id)

    assert persisted is not None
    assert persisted.status == "SENT"
    assert persisted.delivery_attempts == 1
    assert publisher.calls == 1
    assert publisher.excerpts
    assert "password" not in publisher.excerpts[0].evidence_status_map


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
        denylist=_denylist_for_tests(),
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


def test_outbox_worker_logs_warning_for_old_ready_backlog() -> None:
    casefile = _sample_casefile(case_id="case-warning")
    ready_casefile = _ready_casefile(casefile)
    object_store = _InMemoryObjectStoreClient()
    object_store.store[ready_casefile.object_path] = serialize_casefile_triage(casefile)
    engine = create_engine("sqlite+pysqlite:///:memory:")
    create_outbox_table(engine)
    repository = OutboxSqlRepository(engine=engine)
    old_time = datetime(2026, 3, 6, 12, 0, tzinfo=UTC)
    repository.insert_pending_object(confirmed_casefile=ready_casefile, now=old_time)
    repository.transition_to_ready(case_id=casefile.case_id, now=old_time)

    worker = OutboxPublisherWorker(
        outbox_repository=repository,
        object_store_client=object_store,
        publisher=_RecordingPublisher(),
        denylist=_denylist_for_tests(),
        policy=_policy_with_max_retry(max_retry_attempts=3),
        app_env="local",
        batch_size=1,
    )
    logger = _RecordingLogger()
    worker._logger = logger  # noqa: SLF001

    worker.run_once(now=datetime(2026, 3, 6, 12, 3, tzinfo=UTC))

    backlog_events = [event for event in logger.events if event[1] == "outbox_backlog_health"]
    assert backlog_events
    level, _, fields = backlog_events[0]
    assert level == "warning"
    assert fields["threshold_state"] == "warning"
    assert fields["ready_count"] == 1


def test_outbox_worker_backlog_health_escalates_on_pending_object_critical_age() -> None:
    snapshot = OutboxHealthSnapshot(
        pending_object_count=1,
        ready_count=0,
        retry_count=0,
        dead_count=0,
        sent_count=0,
        oldest_pending_object_age_seconds=901.0,
        oldest_ready_age_seconds=0.0,
        oldest_retry_age_seconds=0.0,
        oldest_dead_age_seconds=0.0,
    )
    worker = OutboxPublisherWorker(
        outbox_repository=_SnapshotOnlyRepository(snapshot),
        object_store_client=_InMemoryObjectStoreClient(),
        publisher=_RecordingPublisher(),
        denylist=_denylist_for_tests(),
        policy=_policy_with_max_retry(max_retry_attempts=3),
        app_env="local",
    )
    logger = _RecordingLogger()
    worker._logger = logger  # noqa: SLF001

    worker.run_once(now=datetime(2026, 3, 6, 12, 3, tzinfo=UTC))

    backlog_events = [event for event in logger.events if event[1] == "outbox_backlog_health"]
    assert backlog_events
    level, _, fields = backlog_events[0]
    assert level == "critical"
    assert fields["threshold_state"] == "critical"


def test_outbox_worker_backlog_health_escalates_on_dead_count_in_prod() -> None:
    snapshot = OutboxHealthSnapshot(
        pending_object_count=0,
        ready_count=0,
        retry_count=0,
        dead_count=1,
        sent_count=0,
        oldest_pending_object_age_seconds=0.0,
        oldest_ready_age_seconds=0.0,
        oldest_retry_age_seconds=0.0,
        oldest_dead_age_seconds=0.0,
    )
    worker = OutboxPublisherWorker(
        outbox_repository=_SnapshotOnlyRepository(snapshot),
        object_store_client=_InMemoryObjectStoreClient(),
        publisher=_RecordingPublisher(),
        denylist=_denylist_for_tests(),
        policy=_policy_with_max_retry(max_retry_attempts=3),
        app_env="prod",
    )
    logger = _RecordingLogger()
    worker._logger = logger  # noqa: SLF001

    worker.run_once(now=datetime(2026, 3, 6, 12, 3, tzinfo=UTC))

    backlog_events = [event for event in logger.events if event[1] == "outbox_backlog_health"]
    assert backlog_events
    level, _, fields = backlog_events[0]
    assert level == "critical"
    assert fields["threshold_state"] == "critical"


def test_outbox_worker_backlog_health_uses_full_backlog_not_batch_slice() -> None:
    ready_casefile = _ready_casefile(_sample_casefile(case_id="case-ready"))
    retry_casefile = _ready_casefile(_sample_casefile(case_id="case-retry"))
    object_store = _InMemoryObjectStoreClient()
    object_store.store[ready_casefile.object_path] = serialize_casefile_triage(
        _sample_casefile(case_id="case-ready")
    )
    object_store.store[retry_casefile.object_path] = serialize_casefile_triage(
        _sample_casefile(case_id="case-retry")
    )
    engine = create_engine("sqlite+pysqlite:///:memory:")
    create_outbox_table(engine)
    repository = OutboxSqlRepository(engine=engine)
    base_time = datetime(2026, 3, 6, 12, 0, tzinfo=UTC)
    repository.insert_pending_object(confirmed_casefile=ready_casefile, now=base_time)
    repository.transition_to_ready(case_id="case-ready", now=base_time)
    repository.insert_pending_object(confirmed_casefile=retry_casefile, now=base_time)
    repository.transition_to_ready(case_id="case-retry", now=base_time)
    repository.transition_publish_failure(
        case_id="case-retry",
        policy=_policy_with_max_retry(max_retry_attempts=3),
        app_env="local",
        error_message="kafka unavailable",
        now=base_time,
    )

    worker = OutboxPublisherWorker(
        outbox_repository=repository,
        object_store_client=object_store,
        publisher=_RecordingPublisher(),
        denylist=_denylist_for_tests(),
        policy=_policy_with_max_retry(max_retry_attempts=3),
        app_env="local",
        batch_size=1,
    )
    logger = _RecordingLogger()
    worker._logger = logger  # noqa: SLF001

    # Retry row may fill the batch window first; READY must still be counted in backlog health.
    worker.run_once(now=datetime(2026, 3, 6, 12, 3, tzinfo=UTC))

    backlog_events = [event for event in logger.events if event[1] == "outbox_backlog_health"]
    assert backlog_events
    _, _, fields = backlog_events[0]
    assert fields["ready_count"] == 1
    assert fields["retry_count"] >= 1


def test_outbox_worker_logs_denylist_outcome_for_successful_publish() -> None:
    casefile = _sample_casefile()
    updated_gate_input = casefile.gate_input.model_copy(
        update={
            "evidence_status_map": {
                "topic_messages_in_per_sec": EvidenceStatus.PRESENT,
                "password": EvidenceStatus.UNKNOWN,
            }
        }
    )
    updated_snapshot = casefile.evidence_snapshot.model_copy(
        update={
            "evidence_status_map": {
                "topic_messages_in_per_sec": EvidenceStatus.PRESENT,
                "password": EvidenceStatus.UNKNOWN,
            }
        }
    )
    casefile = casefile.model_copy(
        update={
            "gate_input": updated_gate_input,
            "evidence_snapshot": updated_snapshot,
            "triage_hash": TRIAGE_HASH_PLACEHOLDER,
        }
    )
    casefile = casefile.model_copy(update={"triage_hash": compute_casefile_triage_hash(casefile)})
    ready_casefile = _ready_casefile(casefile)
    object_store = _InMemoryObjectStoreClient()
    object_store.store[ready_casefile.object_path] = serialize_casefile_triage(casefile)
    engine = create_engine("sqlite+pysqlite:///:memory:")
    create_outbox_table(engine)
    repository = OutboxSqlRepository(engine=engine)
    repository.insert_pending_object(confirmed_casefile=ready_casefile)
    repository.transition_to_ready(case_id=casefile.case_id)
    logger = _RecordingLogger()

    worker = OutboxPublisherWorker(
        outbox_repository=repository,
        object_store_client=object_store,
        publisher=_RecordingPublisher(),
        denylist=_denylist_for_tests(),
        policy=_policy_with_max_retry(max_retry_attempts=3),
        app_env="local",
    )
    worker._logger = logger  # noqa: SLF001

    worker.run_once(now=datetime(2026, 3, 6, 12, 0, tzinfo=UTC))

    denylist_events = [event for event in logger.events if event[1] == "outbox_denylist_applied"]
    assert denylist_events
    level, _, fields = denylist_events[0]
    assert level == "info"
    assert fields["event_type"] == "outbox.denylist_applied"
    assert fields["case_id"] == casefile.case_id
    assert fields["component"] == "outbox.worker"
    assert fields["outcome"] == "success"
    assert fields["removed_field_count"] >= 1


def test_outbox_worker_logs_denylist_outcome_when_publish_fails_after_sanitization() -> None:
    casefile = _sample_casefile()
    updated_gate_input = casefile.gate_input.model_copy(
        update={
            "evidence_status_map": {
                "topic_messages_in_per_sec": EvidenceStatus.PRESENT,
                "password": EvidenceStatus.UNKNOWN,
            }
        }
    )
    updated_snapshot = casefile.evidence_snapshot.model_copy(
        update={
            "evidence_status_map": {
                "topic_messages_in_per_sec": EvidenceStatus.PRESENT,
                "password": EvidenceStatus.UNKNOWN,
            }
        }
    )
    casefile = casefile.model_copy(
        update={
            "gate_input": updated_gate_input,
            "evidence_snapshot": updated_snapshot,
            "triage_hash": TRIAGE_HASH_PLACEHOLDER,
        }
    )
    casefile = casefile.model_copy(update={"triage_hash": compute_casefile_triage_hash(casefile)})
    ready_casefile = _ready_casefile(casefile)
    object_store = _InMemoryObjectStoreClient()
    object_store.store[ready_casefile.object_path] = serialize_casefile_triage(casefile)
    engine = create_engine("sqlite+pysqlite:///:memory:")
    create_outbox_table(engine)
    repository = OutboxSqlRepository(engine=engine)
    repository.insert_pending_object(confirmed_casefile=ready_casefile)
    repository.transition_to_ready(case_id=casefile.case_id)
    logger = _RecordingLogger()

    worker = OutboxPublisherWorker(
        outbox_repository=repository,
        object_store_client=object_store,
        publisher=_FailingPublisher(),
        denylist=_denylist_for_tests(),
        policy=_policy_with_max_retry(max_retry_attempts=3),
        app_env="local",
    )
    worker._logger = logger  # noqa: SLF001

    worker.run_once(now=datetime(2026, 3, 6, 12, 0, tzinfo=UTC))

    denylist_events = [event for event in logger.events if event[1] == "outbox_denylist_applied"]
    assert denylist_events
    level, _, fields = denylist_events[0]
    assert level == "warning"
    assert fields["event_type"] == "outbox.denylist_applied"
    assert fields["case_id"] == casefile.case_id
    assert fields["component"] == "outbox.worker"
    assert fields["outcome"] == "applied_publish_failed"
    assert fields["removed_field_count"] >= 1
    assert fields["error_code"] == "CriticalDependencyError"


def test_outbox_worker_dead_failures_log_manual_replay_requirement() -> None:
    casefile = _sample_casefile(case_id="case-dead-log")
    ready_casefile = _ready_casefile(casefile)
    object_store = _InMemoryObjectStoreClient()
    object_store.store[ready_casefile.object_path] = serialize_casefile_triage(casefile)
    engine = create_engine("sqlite+pysqlite:///:memory:")
    create_outbox_table(engine)
    repository = OutboxSqlRepository(engine=engine)
    repository.insert_pending_object(confirmed_casefile=ready_casefile)
    repository.transition_to_ready(case_id=casefile.case_id)
    logger = _RecordingLogger()

    worker = OutboxPublisherWorker(
        outbox_repository=repository,
        object_store_client=object_store,
        publisher=_FailingPublisher(),
        denylist=_denylist_for_tests(),
        policy=_policy_with_max_retry(max_retry_attempts=1),
        app_env="local",
    )
    worker._logger = logger  # noqa: SLF001

    first_attempt = datetime(2026, 3, 6, 12, 0, tzinfo=UTC)
    worker.run_once(now=first_attempt)
    retried = repository.get_by_case_id(casefile.case_id)
    assert retried is not None
    assert retried.next_attempt_at is not None

    worker.run_once(now=retried.next_attempt_at)

    dead_failure_events = [
        event
        for event in logger.events
        if event[2].get("event_type") == "outbox.publish_failed"
        and event[2].get("status") == "DEAD"
    ]
    assert dead_failure_events
    _, _, fields = dead_failure_events[0]
    assert fields["human_investigation_required"] is True
    assert fields["manual_replay_required"] is True
    assert "human investigation" in fields["resolution_guidance"]


@pytest.mark.parametrize(
    ("state", "age_field", "age_value", "expected_severity", "expected_level"),
    [
        ("PENDING_OBJECT", "oldest_pending_object_age_seconds", 301.0, "warning", "warning"),
        ("PENDING_OBJECT", "oldest_pending_object_age_seconds", 901.0, "critical", "critical"),
        ("READY", "oldest_ready_age_seconds", 121.0, "warning", "warning"),
        ("READY", "oldest_ready_age_seconds", 601.0, "critical", "critical"),
        ("RETRY", "oldest_retry_age_seconds", 1801.0, "critical", "critical"),
    ],
)
def test_outbox_worker_emits_threshold_breach_by_state_age(
    state: str,
    age_field: str,
    age_value: float,
    expected_severity: str,
    expected_level: str,
) -> None:
    base_snapshot = {
        "pending_object_count": 0,
        "ready_count": 0,
        "retry_count": 0,
        "dead_count": 0,
        "sent_count": 0,
        "oldest_pending_object_age_seconds": 0.0,
        "oldest_ready_age_seconds": 0.0,
        "oldest_retry_age_seconds": 0.0,
        "oldest_dead_age_seconds": 0.0,
    }
    base_snapshot[age_field] = age_value
    snapshot = OutboxHealthSnapshot(**base_snapshot)

    worker = OutboxPublisherWorker(
        outbox_repository=_SnapshotOnlyRepository(snapshot),
        object_store_client=_InMemoryObjectStoreClient(),
        publisher=_RecordingPublisher(),
        denylist=_denylist_for_tests(),
        policy=_policy_with_max_retry(max_retry_attempts=3),
        app_env="local",
    )
    logger = _RecordingLogger()
    worker._logger = logger  # noqa: SLF001

    worker.run_once(now=datetime(2026, 3, 6, 12, 3, tzinfo=UTC))

    threshold_events = [
        event
        for event in logger.events
        if event[2].get("event_type") == "outbox.health.threshold_breach"
        and event[2].get("state") == state
    ]
    assert threshold_events
    level, _, fields = threshold_events[0]
    assert level == expected_level
    assert fields["severity"] == expected_severity
    assert fields["actual_value"] == age_value
    assert fields["app_env"] == "local"


def test_outbox_worker_emits_dead_count_critical_in_prod_with_manual_resolution_message() -> None:
    snapshot = OutboxHealthSnapshot(
        pending_object_count=0,
        ready_count=0,
        retry_count=0,
        dead_count=1,
        sent_count=0,
        oldest_pending_object_age_seconds=0.0,
        oldest_ready_age_seconds=0.0,
        oldest_retry_age_seconds=0.0,
        oldest_dead_age_seconds=0.0,
    )
    worker = OutboxPublisherWorker(
        outbox_repository=_SnapshotOnlyRepository(snapshot),
        object_store_client=_InMemoryObjectStoreClient(),
        publisher=_RecordingPublisher(),
        denylist=_denylist_for_tests(),
        policy=_policy_with_max_retry(max_retry_attempts=3),
        app_env="prod",
    )
    logger = _RecordingLogger()
    worker._logger = logger  # noqa: SLF001

    worker.run_once(now=datetime(2026, 3, 6, 12, 3, tzinfo=UTC))

    dead_threshold_events = [
        event
        for event in logger.events
        if event[2].get("event_type") == "outbox.health.threshold_breach"
        and event[2].get("state") == "DEAD"
    ]
    assert dead_threshold_events
    level, _, fields = dead_threshold_events[0]
    assert level == "critical"
    assert fields["severity"] == "critical"
    assert fields["actual_value"] == 1.0
    assert fields["threshold_value"] == 0.0

    dead_manual_events = [
        event
        for event in logger.events
        if event[2].get("event_type") == "outbox.dead.manual_resolution_required"
    ]
    assert dead_manual_events
    assert "human investigation" in dead_manual_events[0][2]["message"]


def test_outbox_worker_p99_critical_breach_when_latency_exceeds_ten_minutes(monkeypatch) -> None:
    snapshot = OutboxHealthSnapshot(
        pending_object_count=0,
        ready_count=0,
        retry_count=0,
        dead_count=0,
        sent_count=0,
        oldest_pending_object_age_seconds=0.0,
        oldest_ready_age_seconds=0.0,
        oldest_retry_age_seconds=0.0,
        oldest_dead_age_seconds=0.0,
    )
    worker = OutboxPublisherWorker(
        outbox_repository=_SnapshotOnlyRepository(snapshot),
        object_store_client=_InMemoryObjectStoreClient(),
        publisher=_RecordingPublisher(),
        denylist=_denylist_for_tests(),
        policy=_policy_with_max_retry(max_retry_attempts=3),
        app_env="local",
    )
    logger = _RecordingLogger()
    worker._logger = logger  # noqa: SLF001
    worker._delivery_latency_samples_seconds = [601.0]  # noqa: SLF001

    breach_calls: list[tuple[str, str]] = []
    monkeypatch.setattr(
        "aiops_triage_pipeline.outbox.worker.record_outbox_delivery_slo_breach",
        lambda *, severity, quantile: breach_calls.append((severity, quantile)),
    )

    worker._evaluate_delivery_slo(now=datetime(2026, 3, 6, 12, 3, tzinfo=UTC))  # noqa: SLF001

    p99_events = [
        event
        for event in logger.events
        if event[2].get("event_type") == "outbox.health.threshold_breach"
        and event[2].get("state") == "DELIVERY_SLO_P99"
    ]
    assert p99_events
    level, _, fields = p99_events[0]
    assert level == "critical"
    assert fields["severity"] == "critical"
    assert fields["actual_value"] == 601.0
    assert fields["threshold_value"] == 600.0
    assert ("critical", "p99") in breach_calls


def test_nearest_rank_percentile_supports_p95_and_p99_window_calculations() -> None:
    values = list(range(1, 101))
    assert _nearest_rank_percentile(values, 0.95) == 95
    assert _nearest_rank_percentile(values, 0.99) == 99
    assert _nearest_rank_percentile([1, 100], 0.95) == 100
    assert _nearest_rank_percentile([1, 100], 0.99) == 100
