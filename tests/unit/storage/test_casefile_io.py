from __future__ import annotations

import hashlib
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from aiops_triage_pipeline.contracts.action_decision import ActionDecisionV1
from aiops_triage_pipeline.contracts.enums import (
    Action,
    CriticalityTier,
    Environment,
    EvidenceStatus,
)
from aiops_triage_pipeline.contracts.gate_input import Finding, GateInputV1
from aiops_triage_pipeline.errors.exceptions import CriticalDependencyError, InvariantViolation
from aiops_triage_pipeline.models.case_file import (
    TRIAGE_HASH_PLACEHOLDER,
    CaseFileEvidenceSnapshot,
    CaseFilePolicyVersions,
    CaseFileRoutingContext,
    CaseFileTopologyContext,
    CaseFileTriageV1,
)
from aiops_triage_pipeline.storage.casefile_io import (
    build_casefile_triage_object_key,
    compute_casefile_triage_hash,
    compute_sha256_hex,
    has_valid_casefile_triage_hash,
    persist_casefile_triage_write_once,
    serialize_casefile_triage,
    validate_casefile_triage_json,
)
from aiops_triage_pipeline.storage.client import (
    ObjectStoreClientProtocol,
    PutIfAbsentResult,
)


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


def test_serialize_casefile_triage_is_deterministic_bytes() -> None:
    casefile = _sample_casefile()

    first = serialize_casefile_triage(casefile)
    second = serialize_casefile_triage(casefile)

    assert first == second
    assert isinstance(first, bytes)


def test_compute_sha256_hex_matches_hashlib() -> None:
    payload = serialize_casefile_triage(_sample_casefile())

    expected = hashlib.sha256(payload).hexdigest()
    observed = compute_sha256_hex(payload)

    assert observed == expected
    assert len(observed) == 64


def test_compute_casefile_triage_hash_matches_stored_hash() -> None:
    casefile = _sample_casefile()

    assert casefile.triage_hash == compute_casefile_triage_hash(casefile)
    assert has_valid_casefile_triage_hash(casefile)


def test_model_validate_json_round_trip_helper() -> None:
    original = _sample_casefile()
    serialized = serialize_casefile_triage(original)

    reconstructed = validate_casefile_triage_json(serialized)

    assert reconstructed == original


def test_model_validate_json_raises_on_malformed_json() -> None:
    with pytest.raises(ValidationError):
        validate_casefile_triage_json(b"{not-json")


def test_model_validate_json_raises_on_invalid_hash() -> None:
    tampered = _sample_casefile().model_copy(update={"triage_hash": "a" * 64})
    payload = serialize_casefile_triage(tampered)

    with pytest.raises(ValueError, match="triage_hash"):
        validate_casefile_triage_json(payload)


def test_missing_policy_version_field_fails_validation() -> None:
    payload = _sample_casefile().model_dump(mode="json")
    del payload["policy_versions"]["diagnosis_policy_version"]

    with pytest.raises(ValidationError):
        CaseFileTriageV1.model_validate(payload)


class _FakeObjectStoreClient(ObjectStoreClientProtocol):
    def __init__(self) -> None:
        self.store: dict[str, bytes] = {}
        self.last_put: tuple[str, bytes] | None = None
        self.fail_put: Exception | None = None
        self.fail_get: Exception | None = None

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
        if self.fail_put is not None:
            raise self.fail_put
        self.last_put = (key, body)
        if key in self.store:
            return PutIfAbsentResult.EXISTS
        self.store[key] = body
        return PutIfAbsentResult.CREATED

    def get_object_bytes(self, *, key: str) -> bytes:
        if self.fail_get is not None:
            raise self.fail_get
        return self.store[key]


def test_build_casefile_triage_object_key_uses_required_layout() -> None:
    assert (
        build_casefile_triage_object_key("case-prod-cluster-a-orders")
        == "cases/case-prod-cluster-a-orders/triage.json"
    )


def test_persist_casefile_triage_write_once_creates_object() -> None:
    client = _FakeObjectStoreClient()
    casefile = _sample_casefile()

    persisted = persist_casefile_triage_write_once(
        object_store_client=client,
        casefile=casefile,
    )

    expected_key = build_casefile_triage_object_key(casefile.case_id)
    assert persisted.case_id == casefile.case_id
    assert persisted.object_path == expected_key
    assert persisted.triage_hash == casefile.triage_hash
    assert persisted.write_result == "created"
    assert client.last_put is not None
    assert client.last_put[0] == expected_key
    assert client.last_put[1] == serialize_casefile_triage(casefile)


def test_persist_casefile_triage_write_once_is_idempotent_on_duplicate() -> None:
    client = _FakeObjectStoreClient()
    casefile = _sample_casefile()
    key = build_casefile_triage_object_key(casefile.case_id)
    client.store[key] = serialize_casefile_triage(casefile)

    persisted = persist_casefile_triage_write_once(
        object_store_client=client,
        casefile=casefile,
    )

    assert persisted.write_result == "idempotent"
    assert client.store[key] == serialize_casefile_triage(casefile)


def test_persist_casefile_triage_write_once_raises_on_duplicate_content_mismatch() -> None:
    client = _FakeObjectStoreClient()
    casefile = _sample_casefile()
    key = build_casefile_triage_object_key(casefile.case_id)
    client.store[key] = b'{"schema_version":"v1","triage_hash":"%s"}' % ("0" * 64).encode("utf-8")

    with pytest.raises(InvariantViolation, match="write-once"):
        persist_casefile_triage_write_once(
            object_store_client=client,
            casefile=casefile,
        )


def test_persist_casefile_triage_write_once_fails_fast_when_object_store_unavailable() -> None:
    client = _FakeObjectStoreClient()
    casefile = _sample_casefile()
    client.fail_put = CriticalDependencyError("object storage unavailable")

    with pytest.raises(CriticalDependencyError, match="object storage unavailable"):
        persist_casefile_triage_write_once(
            object_store_client=client,
            casefile=casefile,
        )
