"""Unit tests for diagnosis/context_retrieval.py — TDD RED PHASE.

These tests will FAIL until the production module
``src/aiops_triage_pipeline/diagnosis/context_retrieval.py`` is implemented
(Story 3.2, AC1).

Test IDs follow: 3.2-UNIT-{seq}
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest

from aiops_triage_pipeline.contracts.action_decision import ActionDecisionV1
from aiops_triage_pipeline.contracts.enums import (
    Action,
    CriticalityTier,
    Environment,
    EvidenceStatus,
)
from aiops_triage_pipeline.contracts.gate_input import Finding, GateInputV1
from aiops_triage_pipeline.contracts.triage_excerpt import TriageExcerptV1
from aiops_triage_pipeline.errors.exceptions import (
    ObjectNotFoundError,
)
from aiops_triage_pipeline.models.case_file import (
    TRIAGE_HASH_PLACEHOLDER,
    CaseFileEvidenceSnapshot,
    CaseFilePolicyVersions,
    CaseFileRoutingContext,
    CaseFileTopologyContext,
    CaseFileTriageV1,
)
from aiops_triage_pipeline.storage.casefile_io import compute_casefile_triage_hash
from aiops_triage_pipeline.storage.client import ObjectStoreClientProtocol

# ---------------------------------------------------------------------------
# RED PHASE — module does not exist yet; collected tests will fail with ImportError
# ---------------------------------------------------------------------------
_IMPORT_ERROR: ImportError | None = None
_CASE_TRIAGE_NOT_FOUND_ERROR_TYPE: type | None = None
try:
    from aiops_triage_pipeline.diagnosis.context_retrieval import (
        CaseTriageNotFoundError as _CaseTriageNotFoundError,
    )
    from aiops_triage_pipeline.diagnosis.context_retrieval import (
        retrieve_case_context,
        retrieve_case_context_with_hash,
    )
    _CASE_TRIAGE_NOT_FOUND_ERROR_TYPE = _CaseTriageNotFoundError
except ImportError as _err:
    _IMPORT_ERROR = _err
    _IMPORT_ERROR_MSG = str(_err)

    def retrieve_case_context(**kwargs):  # type: ignore[misc]  # noqa: F811
        raise ImportError(
            "aiops_triage_pipeline.diagnosis.context_retrieval not implemented yet "
            f"(Story 3.2 RED phase): {_IMPORT_ERROR_MSG}"
        )

    def retrieve_case_context_with_hash(**kwargs):  # type: ignore[misc]  # noqa: F811
        raise ImportError(
            "aiops_triage_pipeline.diagnosis.context_retrieval not implemented yet "
            f"(Story 3.2 RED phase): {_IMPORT_ERROR_MSG}"
        )

# ---------------------------------------------------------------------------
# Test data helpers
# ---------------------------------------------------------------------------

_CASE_ID = "case-prod-cluster-a-payments-lag-001"
_TRIAGE_TIMESTAMP = datetime(2026, 3, 22, 18, 0, 0, tzinfo=UTC)


def _make_finding(
    finding_id: str = "f-lag-001",
    name: str = "CONSUMER_LAG",
    severity: str = "HIGH",
    is_anomalous: bool = True,
    is_primary: bool = True,
    evidence_required: tuple[str, ...] = ("consumer_lag_max",),
    reason_codes: tuple[str, ...] = ("lag_exceeds_threshold",),
) -> Finding:
    return Finding(
        finding_id=finding_id,
        name=name,
        is_anomalous=is_anomalous,
        evidence_required=evidence_required,
        is_primary=is_primary,
        severity=severity,
        reason_codes=reason_codes,
    )


def _make_gate_input(
    case_id: str = _CASE_ID,
    sustained: bool = True,
    evidence_status_map: dict[str, EvidenceStatus] | None = None,
    findings: tuple[Finding, ...] | None = None,
    peak: bool | None = True,
) -> GateInputV1:
    if evidence_status_map is None:
        evidence_status_map = {
            "consumer_lag_max": EvidenceStatus.PRESENT,
            "consumer_lag_avg": EvidenceStatus.UNKNOWN,
            "topic_offset_delta": EvidenceStatus.ABSENT,
            "producer_rate": EvidenceStatus.STALE,
        }
    if findings is None:
        findings = (_make_finding(),)
    return GateInputV1(
        env=Environment.PROD,
        cluster_id="cluster-a",
        stream_id="stream-payments",
        topic="payments.events",
        topic_role="SOURCE_TOPIC",
        anomaly_family="CONSUMER_LAG",
        criticality_tier=CriticalityTier.TIER_0,
        proposed_action=Action.PAGE,
        diagnosis_confidence=0.92,
        sustained=sustained,
        findings=findings,
        evidence_status_map=evidence_status_map,
        action_fingerprint="prod/cluster-a/stream-payments/SOURCE_TOPIC/payments.events/CONSUMER_LAG/TIER_0",
        consumer_group="payments-consumer-group",
        peak=peak,
        case_id=case_id,
    )


def _make_topology_context() -> CaseFileTopologyContext:
    return CaseFileTopologyContext(
        stream_id="stream-payments",
        topic_role="SOURCE_TOPIC",
        criticality_tier=CriticalityTier.TIER_0,
        source_system="payments",
        blast_radius="SHARED_KAFKA_INGESTION",
        routing=CaseFileRoutingContext(
            lookup_level="consumer_group_owner",
            routing_key="OWN::Streaming::Payments",
            owning_team_id="team-payments-eng",
            owning_team_name="Payments Engineering",
            support_channel="#payments-oncall",
        ),
    )


def _make_casefile(
    case_id: str = _CASE_ID,
    gate_input: GateInputV1 | None = None,
    topology_context: CaseFileTopologyContext | None = None,
) -> CaseFileTriageV1:
    """Build a valid CaseFileTriageV1 with correct triage_hash."""
    if gate_input is None:
        gate_input = _make_gate_input(case_id=case_id)
    if topology_context is None:
        topology_context = _make_topology_context()

    from aiops_triage_pipeline.models.peak import PeakWindowContext

    casefile_no_hash = CaseFileTriageV1(
        case_id=case_id,
        scope=("prod", "cluster-a", "payments.events"),
        triage_timestamp=_TRIAGE_TIMESTAMP,
        evidence_snapshot=CaseFileEvidenceSnapshot(
            evidence_status_map={
                "consumer_lag_max": EvidenceStatus.PRESENT,
                "consumer_lag_avg": EvidenceStatus.UNKNOWN,
                "topic_offset_delta": EvidenceStatus.ABSENT,
                "producer_rate": EvidenceStatus.STALE,
            },
            peak_context=PeakWindowContext(
                classification="PEAK",
                is_peak_window=True,
                is_near_peak_window=False,
                confidence=0.95,
                reason_codes=("baseline_exceeded",),
            ),
        ),
        topology_context=topology_context,
        gate_input=gate_input,
        action_decision=ActionDecisionV1(
            final_action=Action.PAGE,
            env_cap_applied=False,
            gate_rule_ids=("AG0", "AG1", "AG2", "AG3"),
            gate_reason_codes=("AG0_PASS", "AG1_PASS"),
            action_fingerprint="prod/cluster-a/stream-payments/SOURCE_TOPIC/payments.events/CONSUMER_LAG/TIER_0",
            postmortem_required=False,
        ),
        policy_versions=CaseFilePolicyVersions(
            rulebook_version="v1",
            peak_policy_version="v1",
            prometheus_metrics_contract_version="v1",
            exposure_denylist_version="v1",
            diagnosis_policy_version="v1",
        ),
        triage_hash=TRIAGE_HASH_PLACEHOLDER,
    )
    # Compute real hash and rebuild with it
    real_hash = compute_casefile_triage_hash(casefile_no_hash)
    return CaseFileTriageV1.model_validate(
        {**casefile_no_hash.model_dump(mode="json"), "triage_hash": real_hash}
    )


def _make_mock_object_store(casefile: CaseFileTriageV1) -> MagicMock:
    """Return an object store stub that returns the given casefile's serialized JSON."""
    from aiops_triage_pipeline.storage.casefile_io import serialize_casefile_triage

    mock_store = MagicMock(spec=ObjectStoreClientProtocol)
    payload_bytes = serialize_casefile_triage(casefile)
    mock_store.get_object_bytes.return_value = payload_bytes
    return mock_store


def _make_mock_object_store_missing() -> MagicMock:
    """Return an object store stub that raises ObjectNotFoundError (triage.json absent)."""
    mock_store = MagicMock(spec=ObjectStoreClientProtocol)
    mock_store.get_object_bytes.side_effect = ObjectNotFoundError(
        "Object not found: cases/case-xxx/triage.json"
    )
    return mock_store


# ---------------------------------------------------------------------------
# 3.2-UNIT-001: Successful reconstruction from valid CaseFileTriageV1
# ---------------------------------------------------------------------------


class TestRetrieveCaseContextSuccess:
    """AC1: Given valid triage.json in object store, reconstruct TriageExcerptV1."""

    def test_retrieve_case_context_with_hash_returns_excerpt_and_validated_hash(self) -> None:
        """retrieve_case_context_with_hash exposes persisted triage_hash alongside excerpt."""
        casefile = _make_casefile()
        store = _make_mock_object_store(casefile)

        result = retrieve_case_context_with_hash(case_id=_CASE_ID, object_store_client=store)

        assert isinstance(result.excerpt, TriageExcerptV1)
        assert result.excerpt.case_id == _CASE_ID
        assert result.triage_hash == casefile.triage_hash

    def test_returns_triage_excerpt_v1_instance(self) -> None:
        """3.2-UNIT-001: retrieve_case_context returns TriageExcerptV1 on success."""
        casefile = _make_casefile()
        store = _make_mock_object_store(casefile)

        result = retrieve_case_context(case_id=_CASE_ID, object_store_client=store)

        assert isinstance(result, TriageExcerptV1)

    def test_case_id_mapped_correctly(self) -> None:
        """3.2-UNIT-002: case_id is forwarded unchanged from CaseFileTriageV1."""
        casefile = _make_casefile()
        store = _make_mock_object_store(casefile)

        result = retrieve_case_context(case_id=_CASE_ID, object_store_client=store)

        assert result.case_id == _CASE_ID

    def test_env_mapped_from_gate_input(self) -> None:
        """3.2-UNIT-003: env comes from gate_input.env."""
        casefile = _make_casefile()
        store = _make_mock_object_store(casefile)

        result = retrieve_case_context(case_id=_CASE_ID, object_store_client=store)

        assert result.env == Environment.PROD

    def test_cluster_id_mapped_from_gate_input(self) -> None:
        """3.2-UNIT-004: cluster_id comes from gate_input.cluster_id."""
        casefile = _make_casefile()
        store = _make_mock_object_store(casefile)

        result = retrieve_case_context(case_id=_CASE_ID, object_store_client=store)

        assert result.cluster_id == "cluster-a"

    def test_stream_id_mapped_from_gate_input(self) -> None:
        """3.2-UNIT-005: stream_id comes from gate_input.stream_id."""
        casefile = _make_casefile()
        store = _make_mock_object_store(casefile)

        result = retrieve_case_context(case_id=_CASE_ID, object_store_client=store)

        assert result.stream_id == "stream-payments"

    def test_topic_mapped_from_gate_input(self) -> None:
        """3.2-UNIT-006: topic comes from gate_input.topic."""
        casefile = _make_casefile()
        store = _make_mock_object_store(casefile)

        result = retrieve_case_context(case_id=_CASE_ID, object_store_client=store)

        assert result.topic == "payments.events"

    def test_anomaly_family_mapped_from_gate_input(self) -> None:
        """3.2-UNIT-007: anomaly_family comes from gate_input.anomaly_family."""
        casefile = _make_casefile()
        store = _make_mock_object_store(casefile)

        result = retrieve_case_context(case_id=_CASE_ID, object_store_client=store)

        assert result.anomaly_family == "CONSUMER_LAG"

    def test_topic_role_mapped_from_topology_context(self) -> None:
        """3.2-UNIT-008: topic_role comes from topology_context.topic_role (NOT gate_input)."""
        casefile = _make_casefile()
        store = _make_mock_object_store(casefile)

        result = retrieve_case_context(case_id=_CASE_ID, object_store_client=store)

        assert result.topic_role == "SOURCE_TOPIC"

    def test_criticality_tier_mapped_from_topology_context(self) -> None:
        """3.2-UNIT-009: criticality_tier comes from topology_context.criticality_tier."""
        casefile = _make_casefile()
        store = _make_mock_object_store(casefile)

        result = retrieve_case_context(case_id=_CASE_ID, object_store_client=store)

        assert result.criticality_tier == CriticalityTier.TIER_0

    def test_routing_key_mapped_from_topology_context_routing(self) -> None:
        """3.2-UNIT-010: routing_key comes from topology_context.routing.routing_key."""
        casefile = _make_casefile()
        store = _make_mock_object_store(casefile)

        result = retrieve_case_context(case_id=_CASE_ID, object_store_client=store)

        assert result.routing_key == "OWN::Streaming::Payments"

    def test_sustained_mapped_from_gate_input(self) -> None:
        """3.2-UNIT-011: sustained comes from gate_input.sustained."""
        casefile = _make_casefile(gate_input=_make_gate_input(sustained=True))
        store = _make_mock_object_store(casefile)

        result = retrieve_case_context(case_id=_CASE_ID, object_store_client=store)

        assert result.sustained is True

    def test_peak_mapped_from_evidence_snapshot_peak_context(self) -> None:
        """3.2-UNIT-012: peak comes from evidence_snapshot.peak_context.is_peak_window."""
        casefile = _make_casefile()
        store = _make_mock_object_store(casefile)

        result = retrieve_case_context(case_id=_CASE_ID, object_store_client=store)

        # evidence_snapshot.peak_context.is_peak_window is True in our fixture
        assert result.peak is True

    def test_evidence_status_map_mapped_correctly(self) -> None:
        """3.2-UNIT-013: evidence_status_map contains all four EvidenceStatus values."""
        casefile = _make_casefile()
        store = _make_mock_object_store(casefile)

        result = retrieve_case_context(case_id=_CASE_ID, object_store_client=store)

        assert result.evidence_status_map["consumer_lag_max"] == EvidenceStatus.PRESENT
        assert result.evidence_status_map["consumer_lag_avg"] == EvidenceStatus.UNKNOWN
        assert result.evidence_status_map["topic_offset_delta"] == EvidenceStatus.ABSENT
        assert result.evidence_status_map["producer_rate"] == EvidenceStatus.STALE

    def test_findings_mapped_from_gate_input(self) -> None:
        """3.2-UNIT-014: findings come from gate_input.findings as a tuple."""
        finding = _make_finding(finding_id="f-custom-001", name="MY_FINDING")
        casefile = _make_casefile(gate_input=_make_gate_input(findings=(finding,)))
        store = _make_mock_object_store(casefile)

        result = retrieve_case_context(case_id=_CASE_ID, object_store_client=store)

        assert len(result.findings) == 1
        assert result.findings[0].finding_id == "f-custom-001"
        assert result.findings[0].name == "MY_FINDING"

    def test_triage_timestamp_mapped_from_casefile(self) -> None:
        """3.2-UNIT-015: triage_timestamp matches CaseFileTriageV1.triage_timestamp."""
        casefile = _make_casefile()
        store = _make_mock_object_store(casefile)

        result = retrieve_case_context(case_id=_CASE_ID, object_store_client=store)

        assert result.triage_timestamp == _TRIAGE_TIMESTAMP

    def test_correct_object_key_requested(self) -> None:
        """3.2-UNIT-016: Object store is queried at cases/{case_id}/triage.json."""
        casefile = _make_casefile()
        store = _make_mock_object_store(casefile)

        retrieve_case_context(case_id=_CASE_ID, object_store_client=store)

        store.get_object_bytes.assert_called_once_with(
            key=f"cases/{_CASE_ID}/triage.json"
        )


# ---------------------------------------------------------------------------
# 3.2-UNIT-017: Missing triage.json must raise loudly
# ---------------------------------------------------------------------------


class TestRetrieveCaseContextMissingTriageJson:
    """AC1: When triage.json is absent, raise — do NOT silently skip."""

    def test_raises_when_object_not_found(self) -> None:
        """3.2-UNIT-017: Missing triage.json raises CaseTriageNotFoundError.

        RED PHASE: Will PASS once retrieve_case_context is implemented AND raises a
        domain-specific exception (not ImportError) when the object is missing.
        """
        store = _make_mock_object_store_missing()

        with pytest.raises(Exception) as exc_info:  # noqa: PT011
            retrieve_case_context(case_id="case-missing-001", object_store_client=store)

        # Must not be an ImportError — that would be a RED phase stub artifact
        assert not isinstance(exc_info.value, ImportError), (
            "Exception on missing triage.json must be a domain error, not ImportError. "
            "This failure indicates context_retrieval module is not implemented yet."
        )
        # Must be the specific domain exception type (CaseTriageNotFoundError)
        if _CASE_TRIAGE_NOT_FOUND_ERROR_TYPE is not None:
            assert isinstance(exc_info.value, _CASE_TRIAGE_NOT_FOUND_ERROR_TYPE), (
                f"Expected CaseTriageNotFoundError, got {type(exc_info.value).__name__}. "
                "retrieve_case_context must raise CaseTriageNotFoundError on missing triage.json."
            )

    def test_does_not_return_none_on_missing(self) -> None:
        """3.2-UNIT-018: Missing triage.json must never return None silently.

        RED PHASE: Will PASS once retrieve_case_context raises a domain-specific
        exception (not ImportError) when the object is missing.
        """
        store = _make_mock_object_store_missing()

        raised = False
        domain_error = False
        try:
            result = retrieve_case_context(
                case_id="case-missing-002", object_store_client=store
            )
            # If it didn't raise, it must not have returned None (worst failure mode)
            assert result is not None, (
                "retrieve_case_context must raise on missing artifact, not return None"
            )
        except ImportError:
            # ImportError means the module is not implemented yet (RED phase)
            raise AssertionError(
                "retrieve_case_context not implemented yet (ImportError). "
                "Must raise a domain exception on missing triage.json."
            )
        except Exception:
            raised = True
            domain_error = True

        assert raised and domain_error, (
            "retrieve_case_context must raise a domain exception when triage.json is absent"
        )


# ---------------------------------------------------------------------------
# 3.2-UNIT-019: Hash mismatch raises loudly
# ---------------------------------------------------------------------------


class TestRetrieveCaseContextHashMismatch:
    """AC1: Hash chain integrity check must reject tampered casefile."""

    def test_raises_on_hash_mismatch(self) -> None:
        """3.2-UNIT-019: If triage_hash does not match computed hash, raise."""
        casefile = _make_casefile()
        # Tamper: serialize with a wrong hash (placeholder = all zeros, which won't match)
        payload = casefile.model_dump(mode="json")
        payload["triage_hash"] = "b" * 64  # wrong hash — won't match computed hash
        # Re-validate bypassing our hash check (pydantic only checks format, not content)
        tampered_casefile = CaseFileTriageV1.model_validate(payload)

        from aiops_triage_pipeline.storage.casefile_io import serialize_casefile_triage

        tampered_bytes = serialize_casefile_triage(tampered_casefile)

        mock_store = MagicMock(spec=ObjectStoreClientProtocol)
        mock_store.get_object_bytes.return_value = tampered_bytes

        with pytest.raises(Exception):  # noqa: PT011
            retrieve_case_context(case_id=_CASE_ID, object_store_client=mock_store)

    def test_valid_hash_does_not_raise(self) -> None:
        """3.2-UNIT-020: Valid triage_hash must NOT raise."""
        casefile = _make_casefile()
        store = _make_mock_object_store(casefile)

        # Should not raise — valid hash
        result = retrieve_case_context(case_id=_CASE_ID, object_store_client=store)
        assert result is not None


# ---------------------------------------------------------------------------
# 3.2-UNIT-021: Peak is None when peak_context is absent
# ---------------------------------------------------------------------------


class TestRetrieveCaseContextPeakAbsent:
    """AC1: peak field is None when evidence_snapshot has no peak_context."""

    def test_peak_is_none_when_peak_context_absent(self) -> None:
        """3.2-UNIT-021: TriageExcerptV1.peak is None when peak_context is absent."""
        casefile_no_peak_no_hash = CaseFileTriageV1(
            case_id=_CASE_ID,
            scope=("prod", "cluster-a", "payments.events"),
            triage_timestamp=_TRIAGE_TIMESTAMP,
            evidence_snapshot=CaseFileEvidenceSnapshot(
                evidence_status_map={"consumer_lag_max": EvidenceStatus.PRESENT},
                peak_context=None,  # No peak context
            ),
            topology_context=_make_topology_context(),
            gate_input=_make_gate_input(peak=None),
            action_decision=ActionDecisionV1(
                final_action=Action.PAGE,
                env_cap_applied=False,
                gate_rule_ids=("AG0", "AG1"),
                gate_reason_codes=("AG0_PASS",),
                action_fingerprint="prod/cluster-a/stream-payments/SOURCE_TOPIC/payments.events/CONSUMER_LAG/TIER_0",
                postmortem_required=False,
            ),
            policy_versions=CaseFilePolicyVersions(
                rulebook_version="v1",
                peak_policy_version="v1",
                prometheus_metrics_contract_version="v1",
                exposure_denylist_version="v1",
                diagnosis_policy_version="v1",
            ),
            triage_hash=TRIAGE_HASH_PLACEHOLDER,
        )
        real_hash = compute_casefile_triage_hash(casefile_no_peak_no_hash)
        casefile_no_peak = CaseFileTriageV1.model_validate(
            {**casefile_no_peak_no_hash.model_dump(mode="json"), "triage_hash": real_hash}
        )
        from aiops_triage_pipeline.storage.casefile_io import serialize_casefile_triage

        mock_store = MagicMock(spec=ObjectStoreClientProtocol)
        mock_store.get_object_bytes.return_value = serialize_casefile_triage(casefile_no_peak)

        result = retrieve_case_context(case_id=_CASE_ID, object_store_client=mock_store)

        assert result.peak is None
