from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from aiops_triage_pipeline.contracts.action_decision import ActionDecisionV1
from aiops_triage_pipeline.contracts.enums import Action
from aiops_triage_pipeline.contracts.peak_policy import PeakPolicyV1, PeakThresholdPolicy
from aiops_triage_pipeline.contracts.prometheus_metrics import (
    MetricDefinition,
    MetricIdentityConfig,
    PrometheusMetricsContractV1,
    TruthfulnessConfig,
)
from aiops_triage_pipeline.contracts.rulebook import (
    GateCheck,
    GateEffects,
    GateSpec,
    RulebookCaps,
    RulebookDefaults,
    RulebookV1,
)
from aiops_triage_pipeline.denylist.loader import DenylistV1
from aiops_triage_pipeline.errors.exceptions import CriticalDependencyError, InvariantViolation
from aiops_triage_pipeline.outbox.schema import OutboxReadyCasefileV1
from aiops_triage_pipeline.pipeline.stages.casefile import (
    assemble_casefile_triage_stage,
    persist_casefile_and_prepare_outbox_ready,
)
from aiops_triage_pipeline.pipeline.stages.evidence import collect_evidence_stage_output
from aiops_triage_pipeline.pipeline.stages.gating import (
    GateInputContext,
    collect_gate_inputs_by_scope,
)
from aiops_triage_pipeline.pipeline.stages.peak import collect_peak_stage_output
from aiops_triage_pipeline.pipeline.stages.topology import collect_topology_stage_output
from aiops_triage_pipeline.registry.loader import load_topology_registry
from aiops_triage_pipeline.storage.casefile_io import (
    build_casefile_triage_object_key,
    compute_casefile_triage_hash,
    has_valid_casefile_triage_hash,
)
from aiops_triage_pipeline.storage.client import ObjectStoreClientProtocol, PutIfAbsentResult


def _registry_yaml() -> str:
    return """
version: 2
routing_directory:
  - routing_key: OWN::Streaming::Payments::Topic
    owning_team_id: team-payments-topic
    owning_team_name: Payments Topic Team
ownership_map:
  topic_owners:
    - match:
        env: prod
        cluster_id: cluster-a
        topic: orders
      routing_key: OWN::Streaming::Payments::Topic
  platform_default: OWN::Streaming::Payments::Topic
streams:
  - stream_id: stream-orders
    criticality_tier: TIER_1
    instances:
      - env: prod
        cluster_id: cluster-a
        sources:
          - source_system: Payments
            source_topic: orders
            criticality_tier: TIER_1
        topic_index:
          orders:
            role: SOURCE_TOPIC
            stream_id: stream-orders
"""


def _peak_policy_for_tests() -> PeakPolicyV1:
    return PeakPolicyV1(
        metric="kafka_server_brokertopicmetrics_messagesinpersec",
        timezone="America/Toronto",
        recompute_frequency="weekly",
        defaults=PeakThresholdPolicy(
            peak_percentile=90,
            near_peak_percentile=95,
            bucket_minutes=15,
            min_baseline_windows=4,
        ),
    )


def _rulebook_policy_for_tests() -> RulebookV1:
    defaults = RulebookDefaults(
        missing_series_policy="UNKNOWN_NOT_ZERO",
        required_evidence_policy="PRESENT_ONLY",
        missing_confidence_policy="DOWNGRADE",
        missing_sustained_policy="DOWNGRADE",
    )
    caps = RulebookCaps(
        max_action_by_env={
            "local": "OBSERVE",
            "dev": "OBSERVE",
            "stage": "NOTIFY",
            "prod": "PAGE",
        },
        max_action_by_tier_in_prod={
            "TIER_0": "PAGE",
            "TIER_1": "TICKET",
            "TIER_2": "NOTIFY",
            "UNKNOWN": "NOTIFY",
        },
        paging_denied_topic_roles=("SOURCE_TOPIC",),
    )
    gates = tuple(
        GateSpec(
            id=gate_id,
            name=f"Gate {gate_id}",
            intent="test",
            effect=GateEffects(),
            checks=(GateCheck(check_id=f"{gate_id}_CHECK", type="always_pass"),),
        )
        for gate_id in ("AG0", "AG1", "AG2", "AG3", "AG4", "AG5", "AG6")
    )
    return RulebookV1(
        rulebook_id="rulebook.v1",
        version=1,
        evaluation_interval_minutes=5,
        sustained_intervals_required=5,
        defaults=defaults,
        caps=caps,
        gates=gates,
    )


def _prometheus_contract_for_tests() -> PrometheusMetricsContractV1:
    return PrometheusMetricsContractV1(
        version="v1.0.0",
        date="2026-03-04",
        status="FROZEN",
        identity=MetricIdentityConfig(
            cluster_id_rule="cluster_id := cluster_name",
            topic_identity_labels=("env", "cluster_name", "topic"),
            lag_identity_labels=("env", "cluster_name", "group", "topic"),
            ignore_labels_for_identity=("instance", "job"),
        ),
        metrics={
            "topic_messages_in_per_sec": MetricDefinition(
                canonical="topic_messages_in_per_sec",
                role="Primary throughput signal",
            ),
            "total_produce_requests_per_sec": MetricDefinition(
                canonical="total_produce_requests_per_sec",
                role="Secondary throughput signal",
            ),
        },
        truthfulness=TruthfulnessConfig(
            missing_series={"rule": "UNKNOWN"},
            partition={"rule": "aggregation_only"},
        ),
    )


def _denylist_for_tests() -> DenylistV1:
    return DenylistV1(
        denylist_version="v1.0.0",
        denied_field_names=("password", "token"),
        denied_value_patterns=("(?i)bearer\\s+[A-Za-z0-9._+/=\\-]{10,}",),
    )


def _build_scope_inputs(tmp_path: Path):
    topology_path = tmp_path / "topology.yaml"
    topology_path.write_text(_registry_yaml(), encoding="utf-8")
    snapshot = load_topology_registry(topology_path)

    evidence_output = collect_evidence_stage_output(
        {
            "topic_messages_in_per_sec": [
                {
                    "labels": {
                        "env": "prod",
                        "cluster_name": "cluster-a",
                        "topic": "orders",
                    },
                    "value": 180.0,
                },
                {
                    "labels": {
                        "env": "prod",
                        "cluster_name": "cluster-a",
                        "topic": "orders",
                    },
                    "value": 0.4,
                },
            ],
            "total_produce_requests_per_sec": [
                {
                    "labels": {
                        "env": "prod",
                        "cluster_name": "cluster-a",
                        "topic": "orders",
                    },
                    "value": 220.0,
                }
            ],
        }
    )

    scope = ("prod", "cluster-a", "orders")
    peak_output = collect_peak_stage_output(
        rows=evidence_output.rows,
        historical_windows_by_scope={scope: [float(x) for x in range(1, 21)]},
        anomaly_findings=evidence_output.anomaly_result.findings,
        evidence_status_map_by_scope=evidence_output.evidence_status_map_by_scope,
        evaluation_time=datetime(2026, 3, 4, 12, 0, tzinfo=UTC),
        peak_policy=_peak_policy_for_tests(),
        rulebook_policy=_rulebook_policy_for_tests(),
    )
    topology_output = collect_topology_stage_output(
        snapshot=snapshot,
        evidence_output=evidence_output,
    )

    gate_inputs = collect_gate_inputs_by_scope(
        evidence_output=evidence_output,
        peak_output=peak_output,
        context_by_scope={
            scope: GateInputContext(
                stream_id="stream-orders",
                topic_role="SOURCE_TOPIC",
                criticality_tier=topology_output.context_by_scope[scope].criticality_tier,
                source_system="Payments",
                proposed_action=Action.TICKET,
                diagnosis_confidence=0.77,
                decision_basis={
                    "safe_reason": "normal",
                    "password": "secret-will-be-removed",
                    "auth_header": "Bearer AbCdEfGhIjKlMnOpQrSt",
                },
            )
        },
    )
    gate_input = gate_inputs[scope][0]

    action_decision = ActionDecisionV1(
        final_action=Action.TICKET,
        env_cap_applied=False,
        gate_rule_ids=("AG0", "AG1", "AG2"),
        gate_reason_codes=("PASS", "PASS", "PASS"),
        action_fingerprint=gate_input.action_fingerprint,
        postmortem_required=False,
    )

    return scope, evidence_output, peak_output, topology_output, gate_input, action_decision


def test_assemble_casefile_triage_stage_builds_complete_payload(tmp_path: Path) -> None:
    (
        scope,
        evidence_output,
        peak_output,
        topology_output,
        gate_input,
        action_decision,
    ) = _build_scope_inputs(tmp_path)

    assembled = assemble_casefile_triage_stage(
        scope=scope,
        evidence_output=evidence_output,
        peak_output=peak_output,
        topology_output=topology_output,
        gate_input=gate_input,
        action_decision=action_decision,
        rulebook_policy=_rulebook_policy_for_tests(),
        peak_policy=_peak_policy_for_tests(),
        prometheus_metrics_contract=_prometheus_contract_for_tests(),
        denylist=_denylist_for_tests(),
        diagnosis_policy_version="v1",
        triage_timestamp=datetime(2026, 3, 4, 12, 0, tzinfo=UTC),
    )

    assert assembled.schema_version == "v1"
    assert assembled.scope == scope
    assert assembled.policy_versions.rulebook_version == "1"
    assert assembled.policy_versions.peak_policy_version == "v1"
    assert assembled.policy_versions.prometheus_metrics_contract_version == "v1.0.0"
    assert assembled.policy_versions.exposure_denylist_version == "v1.0.0"
    assert assembled.policy_versions.diagnosis_policy_version == "v1"
    assert len(assembled.triage_hash) == 64
    assert assembled.triage_hash == compute_casefile_triage_hash(assembled)
    assert has_valid_casefile_triage_hash(assembled)
    assert assembled.evidence_snapshot.evidence_status_map

    serialized = assembled.model_dump_json()
    assert "password" not in serialized
    assert "Bearer" not in serialized


def test_assemble_casefile_triage_stage_is_stable_for_same_input(tmp_path: Path) -> None:
    (
        scope,
        evidence_output,
        peak_output,
        topology_output,
        gate_input,
        action_decision,
    ) = _build_scope_inputs(tmp_path)

    first = assemble_casefile_triage_stage(
        scope=scope,
        evidence_output=evidence_output,
        peak_output=peak_output,
        topology_output=topology_output,
        gate_input=gate_input,
        action_decision=action_decision,
        rulebook_policy=_rulebook_policy_for_tests(),
        peak_policy=_peak_policy_for_tests(),
        prometheus_metrics_contract=_prometheus_contract_for_tests(),
        denylist=_denylist_for_tests(),
        diagnosis_policy_version="v1",
        triage_timestamp=datetime(2026, 3, 4, 12, 0, tzinfo=UTC),
    )
    second = assemble_casefile_triage_stage(
        scope=scope,
        evidence_output=evidence_output,
        peak_output=peak_output,
        topology_output=topology_output,
        gate_input=gate_input,
        action_decision=action_decision,
        rulebook_policy=_rulebook_policy_for_tests(),
        peak_policy=_peak_policy_for_tests(),
        prometheus_metrics_contract=_prometheus_contract_for_tests(),
        denylist=_denylist_for_tests(),
        diagnosis_policy_version="v1",
        triage_timestamp=datetime(2026, 3, 4, 12, 0, tzinfo=UTC),
    )

    assert first.case_id == second.case_id
    assert first.triage_hash == second.triage_hash


def test_assemble_casefile_triage_stage_removes_denylisted_list_values(tmp_path: Path) -> None:
    (
        scope,
        evidence_output,
        peak_output,
        topology_output,
        gate_input,
        action_decision,
    ) = _build_scope_inputs(tmp_path)
    gate_input = gate_input.model_copy(
        update={
            "decision_basis": {
                "headers": ["Bearer AbCdEfGhIjKlMnOpQrSt", "safe-header-value"],
                "nested": {"token_list": ["Bearer ZzYyXxWwVvUuTtSsRrQq"]},
            }
        }
    )

    assembled = assemble_casefile_triage_stage(
        scope=scope,
        evidence_output=evidence_output,
        peak_output=peak_output,
        topology_output=topology_output,
        gate_input=gate_input,
        action_decision=action_decision,
        rulebook_policy=_rulebook_policy_for_tests(),
        peak_policy=_peak_policy_for_tests(),
        prometheus_metrics_contract=_prometheus_contract_for_tests(),
        denylist=_denylist_for_tests(),
        diagnosis_policy_version="v1",
        triage_timestamp=datetime(2026, 3, 4, 12, 0, tzinfo=UTC),
    )

    serialized = assembled.model_dump_json()
    assert "Bearer " not in serialized
    assert "safe-header-value" in serialized


def test_assemble_casefile_triage_stage_requires_matching_fingerprint(tmp_path: Path) -> None:
    (
        scope,
        evidence_output,
        peak_output,
        topology_output,
        gate_input,
        action_decision,
    ) = _build_scope_inputs(tmp_path)
    mismatched = action_decision.model_copy(update={"action_fingerprint": "different-fingerprint"})

    with pytest.raises(ValueError, match="action_fingerprint"):
        assemble_casefile_triage_stage(
            scope=scope,
            evidence_output=evidence_output,
            peak_output=peak_output,
            topology_output=topology_output,
            gate_input=gate_input,
            action_decision=mismatched,
            rulebook_policy=_rulebook_policy_for_tests(),
            peak_policy=_peak_policy_for_tests(),
            prometheus_metrics_contract=_prometheus_contract_for_tests(),
            denylist=_denylist_for_tests(),
            diagnosis_policy_version="v1",
            triage_timestamp=datetime(2026, 3, 4, 12, 0, tzinfo=UTC),
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


class _UnavailableObjectStoreClient(ObjectStoreClientProtocol):
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
        raise CriticalDependencyError("object storage unavailable")

    def get_object_bytes(self, *, key: str) -> bytes:
        del key
        raise CriticalDependencyError("object storage unavailable")


class _WriteOnceConflictObjectStoreClient(ObjectStoreClientProtocol):
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
        return PutIfAbsentResult.EXISTS

    def get_object_bytes(self, *, key: str) -> bytes:
        del key
        return b'{"schema_version":"v1","triage_hash":"' + ("0" * 64).encode("utf-8") + b'"}'


class _RecordingLogger:
    def __init__(self) -> None:
        self.errors: list[dict[str, object]] = []
        self.criticals: list[dict[str, object]] = []
        self.infos: list[dict[str, object]] = []

    def error(self, message: str, **kwargs: object) -> None:
        self.errors.append({"message": message, **kwargs})

    def critical(self, message: str, **kwargs: object) -> None:
        self.criticals.append({"message": message, **kwargs})

    def info(self, message: str, **kwargs: object) -> None:
        self.infos.append({"message": message, **kwargs})


def test_persist_casefile_and_prepare_outbox_ready_requires_confirmed_write(tmp_path: Path) -> None:
    (
        scope,
        evidence_output,
        peak_output,
        topology_output,
        gate_input,
        action_decision,
    ) = _build_scope_inputs(tmp_path)

    assembled = assemble_casefile_triage_stage(
        scope=scope,
        evidence_output=evidence_output,
        peak_output=peak_output,
        topology_output=topology_output,
        gate_input=gate_input,
        action_decision=action_decision,
        rulebook_policy=_rulebook_policy_for_tests(),
        peak_policy=_peak_policy_for_tests(),
        prometheus_metrics_contract=_prometheus_contract_for_tests(),
        denylist=_denylist_for_tests(),
        diagnosis_policy_version="v1",
        triage_timestamp=datetime(2026, 3, 4, 12, 0, tzinfo=UTC),
    )
    object_store_client = _InMemoryObjectStoreClient()

    ready_payload = persist_casefile_and_prepare_outbox_ready(
        casefile=assembled,
        object_store_client=object_store_client,
    )

    assert isinstance(ready_payload, OutboxReadyCasefileV1)
    assert ready_payload.case_id == assembled.case_id
    assert ready_payload.triage_hash == assembled.triage_hash
    assert ready_payload.object_path == build_casefile_triage_object_key(assembled.case_id)
    assert ready_payload.object_path in object_store_client.store


def test_persist_casefile_and_prepare_outbox_ready_fails_fast_when_store_unavailable(
    tmp_path: Path,
) -> None:
    (
        scope,
        evidence_output,
        peak_output,
        topology_output,
        gate_input,
        action_decision,
    ) = _build_scope_inputs(tmp_path)
    assembled = assemble_casefile_triage_stage(
        scope=scope,
        evidence_output=evidence_output,
        peak_output=peak_output,
        topology_output=topology_output,
        gate_input=gate_input,
        action_decision=action_decision,
        rulebook_policy=_rulebook_policy_for_tests(),
        peak_policy=_peak_policy_for_tests(),
        prometheus_metrics_contract=_prometheus_contract_for_tests(),
        denylist=_denylist_for_tests(),
        diagnosis_policy_version="v1",
        triage_timestamp=datetime(2026, 3, 4, 12, 0, tzinfo=UTC),
    )

    with pytest.raises(CriticalDependencyError, match="object storage unavailable"):
        persist_casefile_and_prepare_outbox_ready(
            casefile=assembled,
            object_store_client=_UnavailableObjectStoreClient(),
        )


def test_persist_casefile_and_prepare_outbox_ready_emits_explicit_halt_alert(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (
        scope,
        evidence_output,
        peak_output,
        topology_output,
        gate_input,
        action_decision,
    ) = _build_scope_inputs(tmp_path)
    assembled = assemble_casefile_triage_stage(
        scope=scope,
        evidence_output=evidence_output,
        peak_output=peak_output,
        topology_output=topology_output,
        gate_input=gate_input,
        action_decision=action_decision,
        rulebook_policy=_rulebook_policy_for_tests(),
        peak_policy=_peak_policy_for_tests(),
        prometheus_metrics_contract=_prometheus_contract_for_tests(),
        denylist=_denylist_for_tests(),
        diagnosis_policy_version="v1",
        triage_timestamp=datetime(2026, 3, 4, 12, 0, tzinfo=UTC),
    )
    logger = _RecordingLogger()
    monkeypatch.setattr(
        "aiops_triage_pipeline.pipeline.stages.casefile.get_logger",
        lambda _: logger,
    )

    with pytest.raises(CriticalDependencyError, match="object storage unavailable"):
        persist_casefile_and_prepare_outbox_ready(
            casefile=assembled,
            object_store_client=_UnavailableObjectStoreClient(),
        )

    assert len(logger.criticals) == 1
    assert logger.criticals[0]["event_type"] == "DegradedModeEvent"
    assert logger.criticals[0]["affected_scope"] == "object_storage"


def test_persist_casefile_and_prepare_outbox_ready_raises_on_write_once_violation(
    tmp_path: Path,
) -> None:
    (
        scope,
        evidence_output,
        peak_output,
        topology_output,
        gate_input,
        action_decision,
    ) = _build_scope_inputs(tmp_path)
    assembled = assemble_casefile_triage_stage(
        scope=scope,
        evidence_output=evidence_output,
        peak_output=peak_output,
        topology_output=topology_output,
        gate_input=gate_input,
        action_decision=action_decision,
        rulebook_policy=_rulebook_policy_for_tests(),
        peak_policy=_peak_policy_for_tests(),
        prometheus_metrics_contract=_prometheus_contract_for_tests(),
        denylist=_denylist_for_tests(),
        diagnosis_policy_version="v1",
        triage_timestamp=datetime(2026, 3, 4, 12, 0, tzinfo=UTC),
    )

    with pytest.raises(InvariantViolation, match="write-once"):
        persist_casefile_and_prepare_outbox_ready(
            casefile=assembled,
            object_store_client=_WriteOnceConflictObjectStoreClient(),
        )
