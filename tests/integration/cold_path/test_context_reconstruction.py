"""Integration tests for cold-path context reconstruction via real MinIO.

Story 3.2, AC1: Write CaseFileTriageV1 to MinIO testcontainer, call
retrieve_case_context(), assert reconstructed TriageExcerptV1 field values
match the written casefile.

Requires Docker. Mark: pytestmark = pytest.mark.integration
Test IDs follow: 3.2-INT-{seq}
"""

from __future__ import annotations

from datetime import UTC, datetime

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
from aiops_triage_pipeline.models.case_file import (
    TRIAGE_HASH_PLACEHOLDER,
    CaseFileEvidenceSnapshot,
    CaseFilePolicyVersions,
    CaseFileRoutingContext,
    CaseFileTopologyContext,
    CaseFileTriageV1,
)
from aiops_triage_pipeline.models.peak import PeakWindowContext
from aiops_triage_pipeline.storage.casefile_io import (
    compute_casefile_triage_hash,
    persist_casefile_triage_write_once,
)

# RED PHASE — module does not exist yet; collected tests will fail with ImportError
_IMPORT_ERROR: ImportError | None = None
try:
    from aiops_triage_pipeline.diagnosis.context_retrieval import retrieve_case_context
except ImportError as _err:
    _IMPORT_ERROR = _err
    _IMPORT_ERROR_MSG = str(_err)

    def retrieve_case_context(**kwargs):  # type: ignore[misc]  # noqa: F811
        raise ImportError(
            "aiops_triage_pipeline.diagnosis.context_retrieval not implemented yet "
            f"(Story 3.2 RED phase): {_IMPORT_ERROR_MSG}"
        )

pytestmark = pytest.mark.integration

_MINIO_IMAGE = "minio/minio:RELEASE.2025-01-20T14-49-07Z"
_MINIO_ACCESS_KEY = "minioadmin"
_MINIO_SECRET_KEY = "minioadmin"
_MINIO_BUCKET = "aiops-cases-integration-3-2"

_CASE_ID = "case-int-3-2-context-reconstruction-001"
_TRIAGE_TIMESTAMP = datetime(2026, 3, 22, 20, 0, 0, tzinfo=UTC)


# ---------------------------------------------------------------------------
# Helper: detect Docker environment issues
# ---------------------------------------------------------------------------


def _is_environment_prereq_error(exc: Exception) -> bool:
    text = f"{type(exc).__name__}: {exc}"
    return any(
        marker in text
        for marker in (
            "Error while fetching server API version",
            "DockerException",
            "Cannot connect to Docker daemon",
            "ConnectionError",
            "no pq wrapper available",
        )
    )


# ---------------------------------------------------------------------------
# MinIO testcontainer fixture
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def minio_container():
    """Module-scoped MinIO testcontainer."""
    import time
    from urllib.error import URLError
    from urllib.request import urlopen

    try:
        from testcontainers.core.container import DockerContainer
    except ImportError:
        pytest.skip("testcontainers not installed")

    try:
        container = (
            DockerContainer(_MINIO_IMAGE)
            .with_exposed_ports(9000)
            .with_env("MINIO_ROOT_USER", _MINIO_ACCESS_KEY)
            .with_env("MINIO_ROOT_PASSWORD", _MINIO_SECRET_KEY)
            .with_command("server /data")
        )
        with container:
            host = container.get_container_host_ip()
            port = int(container.get_exposed_port(9000))
            endpoint = f"http://{host}:{port}"

            # Wait for MinIO to be ready
            deadline = time.monotonic() + 30.0
            while time.monotonic() < deadline:
                try:
                    with urlopen(f"{endpoint}/minio/health/live", timeout=1.0) as resp:  # noqa: S310
                        if resp.status == 200:
                            break
                except (URLError, TimeoutError, ConnectionError):
                    time.sleep(0.25)
            else:
                pytest.skip("MinIO did not become healthy within 30s")

            yield {
                "endpoint_url": endpoint,
                "access_key": _MINIO_ACCESS_KEY,
                "secret_key": _MINIO_SECRET_KEY,
                "bucket": _MINIO_BUCKET,
            }
    except Exception as exc:
        if _is_environment_prereq_error(exc):
            pytest.skip(f"Docker not available: {exc}")
        raise


@pytest.fixture(scope="module")
def s3_client(minio_container):
    """boto3 S3 client pointed at the MinIO testcontainer."""
    import boto3

    client = boto3.client(
        "s3",
        endpoint_url=minio_container["endpoint_url"],
        aws_access_key_id=minio_container["access_key"],
        aws_secret_access_key=minio_container["secret_key"],
        region_name="us-east-1",
    )
    client.create_bucket(Bucket=_MINIO_BUCKET)
    return client


@pytest.fixture(scope="module")
def object_store_client(minio_container, s3_client):
    """S3ObjectStoreClient pointed at the MinIO testcontainer bucket."""
    from aiops_triage_pipeline.storage.client import S3ObjectStoreClient

    return S3ObjectStoreClient(
        s3_client=s3_client,
        bucket=_MINIO_BUCKET,
    )


# ---------------------------------------------------------------------------
# Test data helpers
# ---------------------------------------------------------------------------


def _make_finding() -> Finding:
    return Finding(
        finding_id="f-int-lag-001",
        name="CONSUMER_LAG_SUSTAINED",
        is_anomalous=True,
        evidence_required=("consumer_lag_max", "consumer_lag_avg"),
        is_primary=True,
        severity="HIGH",
        reason_codes=("lag_exceeds_threshold", "sustained_condition"),
    )


def _make_valid_casefile(case_id: str = _CASE_ID) -> CaseFileTriageV1:
    """Build CaseFileTriageV1 with correct hash for integration round-trip tests."""
    gate_input = GateInputV1(
        env=Environment.PROD,
        cluster_id="cluster-integration",
        stream_id="stream-payments-int",
        topic="payments.events.int",
        topic_role="SOURCE_TOPIC",
        anomaly_family="CONSUMER_LAG",
        criticality_tier=CriticalityTier.TIER_0,
        proposed_action=Action.PAGE,
        diagnosis_confidence=0.95,
        sustained=True,
        findings=(_make_finding(),),
        evidence_status_map={
            "consumer_lag_max": EvidenceStatus.PRESENT,
            "consumer_lag_avg": EvidenceStatus.UNKNOWN,
            "topic_offset_delta": EvidenceStatus.ABSENT,
            "producer_rate": EvidenceStatus.STALE,
        },
        action_fingerprint=(
            "prod/cluster-integration/stream-payments-int/"
            "SOURCE_TOPIC/payments.events.int/CONSUMER_LAG/TIER_0"
        ),
        peak=True,
        case_id=case_id,
    )
    topology_context = CaseFileTopologyContext(
        stream_id="stream-payments-int",
        topic_role="SOURCE_TOPIC",
        criticality_tier=CriticalityTier.TIER_0,
        source_system="payments",
        blast_radius="SHARED_KAFKA_INGESTION",
        routing=CaseFileRoutingContext(
            lookup_level="consumer_group_owner",
            routing_key="OWN::Streaming::PaymentsInt",
            owning_team_id="team-payments-eng",
            owning_team_name="Payments Engineering",
            support_channel="#payments-oncall",
        ),
    )
    casefile_no_hash = CaseFileTriageV1(
        case_id=case_id,
        scope=("prod", "cluster-integration", "payments.events.int"),
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
                confidence=0.98,
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
            action_fingerprint=(
                "prod/cluster-integration/stream-payments-int/"
                "SOURCE_TOPIC/payments.events.int/CONSUMER_LAG/TIER_0"
            ),
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
    real_hash = compute_casefile_triage_hash(casefile_no_hash)
    return CaseFileTriageV1.model_validate(
        {**casefile_no_hash.model_dump(mode="json"), "triage_hash": real_hash}
    )


# ---------------------------------------------------------------------------
# 3.2-INT-001: Full round-trip: persist → retrieve → assert fields
# ---------------------------------------------------------------------------


class TestContextReconstructionRoundTrip:
    """AC1: Write to MinIO, retrieve, verify TriageExcerptV1 fields match casefile."""

    def test_retrieve_case_context_returns_triage_excerpt_v1(
        self, object_store_client
    ) -> None:
        """3.2-INT-001: retrieve_case_context returns TriageExcerptV1 after MinIO write."""
        casefile = _make_valid_casefile()
        persist_casefile_triage_write_once(
            object_store_client=object_store_client, casefile=casefile
        )

        result = retrieve_case_context(
            case_id=_CASE_ID, object_store_client=object_store_client
        )

        assert isinstance(result, TriageExcerptV1)

    def test_case_id_matches(self, object_store_client) -> None:
        """3.2-INT-002: Reconstructed case_id matches persisted casefile."""
        casefile = _make_valid_casefile()
        persist_casefile_triage_write_once(
            object_store_client=object_store_client, casefile=casefile
        )

        result = retrieve_case_context(
            case_id=_CASE_ID, object_store_client=object_store_client
        )

        assert result.case_id == _CASE_ID

    def test_env_matches_gate_input_env(self, object_store_client) -> None:
        """3.2-INT-003: Reconstructed env matches gate_input.env."""
        casefile = _make_valid_casefile()
        persist_casefile_triage_write_once(
            object_store_client=object_store_client, casefile=casefile
        )

        result = retrieve_case_context(
            case_id=_CASE_ID, object_store_client=object_store_client
        )

        assert result.env == Environment.PROD

    def test_topic_matches_gate_input_topic(self, object_store_client) -> None:
        """3.2-INT-004: Reconstructed topic matches gate_input.topic."""
        casefile = _make_valid_casefile()
        persist_casefile_triage_write_once(
            object_store_client=object_store_client, casefile=casefile
        )

        result = retrieve_case_context(
            case_id=_CASE_ID, object_store_client=object_store_client
        )

        assert result.topic == "payments.events.int"

    def test_routing_key_matches_topology_context(self, object_store_client) -> None:
        """3.2-INT-005: Reconstructed routing_key matches topology_context.routing.routing_key."""
        casefile = _make_valid_casefile()
        persist_casefile_triage_write_once(
            object_store_client=object_store_client, casefile=casefile
        )

        result = retrieve_case_context(
            case_id=_CASE_ID, object_store_client=object_store_client
        )

        assert result.routing_key == "OWN::Streaming::PaymentsInt"

    def test_evidence_status_map_all_four_statuses(self, object_store_client) -> None:
        """3.2-INT-006: All four EvidenceStatus variants reconstructed correctly."""
        casefile = _make_valid_casefile()
        persist_casefile_triage_write_once(
            object_store_client=object_store_client, casefile=casefile
        )

        result = retrieve_case_context(
            case_id=_CASE_ID, object_store_client=object_store_client
        )

        assert result.evidence_status_map["consumer_lag_max"] == EvidenceStatus.PRESENT
        assert result.evidence_status_map["consumer_lag_avg"] == EvidenceStatus.UNKNOWN
        assert result.evidence_status_map["topic_offset_delta"] == EvidenceStatus.ABSENT
        assert result.evidence_status_map["producer_rate"] == EvidenceStatus.STALE

    def test_findings_reconstructed_with_correct_fields(self, object_store_client) -> None:
        """3.2-INT-007: Reconstructed findings match casefile gate_input.findings."""
        casefile = _make_valid_casefile()
        persist_casefile_triage_write_once(
            object_store_client=object_store_client, casefile=casefile
        )

        result = retrieve_case_context(
            case_id=_CASE_ID, object_store_client=object_store_client
        )

        assert len(result.findings) == 1
        f = result.findings[0]
        assert f.finding_id == "f-int-lag-001"
        assert f.name == "CONSUMER_LAG_SUSTAINED"
        assert f.severity == "HIGH"
        assert f.is_anomalous is True
        assert f.is_primary is True
        assert "consumer_lag_max" in f.evidence_required
        assert "lag_exceeds_threshold" in f.reason_codes

    def test_triage_timestamp_matches(self, object_store_client) -> None:
        """3.2-INT-008: Reconstructed triage_timestamp matches casefile."""
        casefile = _make_valid_casefile()
        persist_casefile_triage_write_once(
            object_store_client=object_store_client, casefile=casefile
        )

        result = retrieve_case_context(
            case_id=_CASE_ID, object_store_client=object_store_client
        )

        assert result.triage_timestamp == _TRIAGE_TIMESTAMP

    def test_sustained_flag_matches(self, object_store_client) -> None:
        """3.2-INT-009: Reconstructed sustained flag matches gate_input.sustained."""
        casefile = _make_valid_casefile()
        persist_casefile_triage_write_once(
            object_store_client=object_store_client, casefile=casefile
        )

        result = retrieve_case_context(
            case_id=_CASE_ID, object_store_client=object_store_client
        )

        assert result.sustained is True

    def test_peak_flag_from_peak_context(self, object_store_client) -> None:
        """3.2-INT-010: peak flag derived from evidence_snapshot.peak_context.is_peak_window."""
        casefile = _make_valid_casefile()
        persist_casefile_triage_write_once(
            object_store_client=object_store_client, casefile=casefile
        )

        result = retrieve_case_context(
            case_id=_CASE_ID, object_store_client=object_store_client
        )

        # Our fixture has is_peak_window=True
        assert result.peak is True


# ---------------------------------------------------------------------------
# 3.2-INT-011: Missing object raises (invariant violation)
# ---------------------------------------------------------------------------


class TestContextReconstructionMissingObject:
    """AC1: If triage.json is absent in MinIO, retrieve_case_context must raise."""

    def test_raises_on_nonexistent_case_id(self, object_store_client) -> None:
        """3.2-INT-011: Non-existent case raises — never silently returns None."""
        with pytest.raises(Exception):  # noqa: PT011
            retrieve_case_context(
                case_id="case-does-not-exist-xyz-123",
                object_store_client=object_store_client,
            )
