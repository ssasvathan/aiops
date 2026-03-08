from __future__ import annotations

import base64
import hashlib
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from aiops_triage_pipeline.contracts.action_decision import ActionDecisionV1
from aiops_triage_pipeline.contracts.diagnosis_report import DiagnosisReportV1, EvidencePack
from aiops_triage_pipeline.contracts.enums import (
    Action,
    CriticalityTier,
    DiagnosisConfidence,
    Environment,
    EvidenceStatus,
)
from aiops_triage_pipeline.contracts.gate_input import Finding, GateInputV1
from aiops_triage_pipeline.errors.exceptions import (
    CriticalDependencyError,
    InvariantViolation,
    ObjectNotFoundError,
)
from aiops_triage_pipeline.models.case_file import (
    DIAGNOSIS_HASH_PLACEHOLDER,
    LABELS_HASH_PLACEHOLDER,
    LINKAGE_HASH_PLACEHOLDER,
    TRIAGE_HASH_PLACEHOLDER,
    CaseFileDiagnosisV1,
    CaseFileEvidenceSnapshot,
    CaseFileLabelDataV1,
    CaseFileLabelsV1,
    CaseFileLinkageV1,
    CaseFilePolicyVersions,
    CaseFileRoutingContext,
    CaseFileTopologyContext,
    CaseFileTriageV1,
)
from aiops_triage_pipeline.storage.casefile_io import (
    build_casefile_stage_object_key,
    build_casefile_triage_object_key,
    compute_casefile_diagnosis_hash,
    compute_casefile_labels_hash,
    compute_casefile_linkage_hash,
    compute_casefile_triage_hash,
    compute_sha256_hex,
    has_valid_casefile_triage_hash,
    list_present_casefile_stages,
    persist_casefile_diagnosis_write_once,
    persist_casefile_labels_write_once,
    persist_casefile_linkage_write_once,
    persist_casefile_triage_write_once,
    read_casefile_stage_json_or_none,
    serialize_casefile_stage,
    serialize_casefile_triage,
    validate_casefile_diagnosis_json,
    validate_casefile_labels_json,
    validate_casefile_linkage_json,
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


def _sample_casefile_diagnosis(*, triage_hash: str) -> CaseFileDiagnosisV1:
    base = CaseFileDiagnosisV1(
        case_id="case-prod-cluster-a-orders-volume-drop",
        diagnosis_report=DiagnosisReportV1(
            case_id="case-prod-cluster-a-orders-volume-drop",
            verdict="UNKNOWN",
            fault_domain=None,
            confidence=DiagnosisConfidence.LOW,
            evidence_pack=EvidencePack(
                facts=("topic_messages_in_per_sec dropped sharply",),
                missing_evidence=("consumer_group_lag",),
                matched_rules=("AG2",),
            ),
            next_checks=("validate producer health",),
            reason_codes=("LLM_TIMEOUT",),
            triage_hash=triage_hash,
        ),
        triage_hash=triage_hash,
        diagnosis_hash=DIAGNOSIS_HASH_PLACEHOLDER,
    )
    return base.model_copy(update={"diagnosis_hash": compute_casefile_diagnosis_hash(base)})


def _sample_casefile_linkage(
    *,
    triage_hash: str,
    diagnosis_hash: str | None = None,
) -> CaseFileLinkageV1:
    base = CaseFileLinkageV1(
        case_id="case-prod-cluster-a-orders-volume-drop",
        linkage_status="linked",
        linkage_reason="linked-to-problem",
        triage_hash=triage_hash,
        diagnosis_hash=diagnosis_hash,
        linkage_hash=LINKAGE_HASH_PLACEHOLDER,
    )
    return base.model_copy(update={"linkage_hash": compute_casefile_linkage_hash(base)})


def _sample_casefile_labels(
    *,
    triage_hash: str,
    diagnosis_hash: str | None = None,
) -> CaseFileLabelsV1:
    base = CaseFileLabelsV1(
        case_id="case-prod-cluster-a-orders-volume-drop",
        label_data=CaseFileLabelDataV1(
            owner_confirmed=True,
            resolution_category="UNKNOWN",
        ),
        triage_hash=triage_hash,
        diagnosis_hash=diagnosis_hash,
        labels_hash=LABELS_HASH_PLACEHOLDER,
    )
    return base.model_copy(update={"labels_hash": compute_casefile_labels_hash(base)})


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
        self.last_checksum: str | None = None
        self.last_metadata: dict[str, str] | None = None
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
        del content_type
        if self.fail_put is not None:
            raise self.fail_put
        self.last_put = (key, body)
        self.last_checksum = checksum_sha256
        self.last_metadata = dict(metadata or {})
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


def test_build_casefile_stage_object_key_uses_required_layout() -> None:
    assert (
        build_casefile_stage_object_key("case-prod-cluster-a-orders", stage="diagnosis")
        == "cases/case-prod-cluster-a-orders/diagnosis.json"
    )


def test_build_casefile_stage_object_key_rejects_invalid_stage_name() -> None:
    with pytest.raises(ValueError, match="Unsupported casefile stage"):
        build_casefile_stage_object_key("case-prod-cluster-a-orders", stage="unexpected")


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
    payload_sha256 = hashlib.sha256(serialize_casefile_triage(casefile)).digest()
    assert client.last_checksum == base64.b64encode(payload_sha256).decode("ascii")
    assert client.last_metadata == {
        "triage_hash": casefile.triage_hash,
        "payload_sha256": hashlib.sha256(serialize_casefile_triage(casefile)).hexdigest(),
    }


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


def test_persist_casefile_diagnosis_write_once_creates_object() -> None:
    client = _FakeObjectStoreClient()
    triage_casefile = _sample_casefile()
    diagnosis_casefile = _sample_casefile_diagnosis(triage_hash=triage_casefile.triage_hash)

    persisted = persist_casefile_diagnosis_write_once(
        object_store_client=client,
        casefile=diagnosis_casefile,
    )

    expected_key = build_casefile_stage_object_key(diagnosis_casefile.case_id, stage="diagnosis")
    assert persisted.stage == "diagnosis"
    assert persisted.object_path == expected_key
    assert persisted.stage_hash == diagnosis_casefile.diagnosis_hash
    assert persisted.write_result == "created"
    assert client.last_put is not None
    assert client.last_put[1] == serialize_casefile_stage(diagnosis_casefile)
    assert client.last_metadata is not None
    assert client.last_metadata["triage_hash"] == triage_casefile.triage_hash
    assert client.last_metadata["diagnosis_hash"] == diagnosis_casefile.diagnosis_hash


def test_persist_casefile_diagnosis_write_once_rejects_overwrite_payload_mismatch() -> None:
    client = _FakeObjectStoreClient()
    triage_casefile = _sample_casefile()
    diagnosis_casefile = _sample_casefile_diagnosis(triage_hash=triage_casefile.triage_hash)
    key = build_casefile_stage_object_key(diagnosis_casefile.case_id, stage="diagnosis")
    client.store[key] = b'{"schema_version":"v1","diagnosis_hash":"%s"}' % (
        "0" * 64
    ).encode("utf-8")

    with pytest.raises(InvariantViolation, match="write-once"):
        persist_casefile_diagnosis_write_once(
            object_store_client=client,
            casefile=diagnosis_casefile,
        )


def test_persist_casefile_linkage_write_once_creates_object() -> None:
    client = _FakeObjectStoreClient()
    triage_casefile = _sample_casefile()
    linkage_casefile = _sample_casefile_linkage(triage_hash=triage_casefile.triage_hash)

    persisted = persist_casefile_linkage_write_once(
        object_store_client=client,
        casefile=linkage_casefile,
    )

    expected_key = build_casefile_stage_object_key(linkage_casefile.case_id, stage="linkage")
    assert persisted.stage == "linkage"
    assert persisted.object_path == expected_key
    assert persisted.stage_hash == linkage_casefile.linkage_hash
    assert persisted.write_result == "created"
    assert client.last_put is not None
    assert client.last_put[1] == serialize_casefile_stage(linkage_casefile)
    assert client.last_metadata is not None
    assert client.last_metadata["triage_hash"] == triage_casefile.triage_hash
    assert client.last_metadata["linkage_hash"] == linkage_casefile.linkage_hash


def test_persist_casefile_labels_write_once_creates_object() -> None:
    client = _FakeObjectStoreClient()
    triage_casefile = _sample_casefile()
    labels_casefile = _sample_casefile_labels(triage_hash=triage_casefile.triage_hash)

    persisted = persist_casefile_labels_write_once(
        object_store_client=client,
        casefile=labels_casefile,
    )

    expected_key = build_casefile_stage_object_key(labels_casefile.case_id, stage="labels")
    assert persisted.stage == "labels"
    assert persisted.object_path == expected_key
    assert persisted.stage_hash == labels_casefile.labels_hash
    assert persisted.write_result == "created"
    assert client.last_put is not None
    assert client.last_put[1] == serialize_casefile_stage(labels_casefile)
    assert client.last_metadata is not None
    assert client.last_metadata["triage_hash"] == triage_casefile.triage_hash
    assert client.last_metadata["labels_hash"] == labels_casefile.labels_hash


def test_read_casefile_stage_json_or_none_returns_none_for_missing_stage() -> None:
    client = _FakeObjectStoreClient()

    loaded = read_casefile_stage_json_or_none(
        object_store_client=client,
        case_id="case-prod-cluster-a-orders-volume-drop",
        stage="diagnosis",
    )

    assert loaded is None


def test_read_casefile_stage_json_or_none_round_trips_diagnosis_payload() -> None:
    client = _FakeObjectStoreClient()
    triage_casefile = _sample_casefile()
    diagnosis_casefile = _sample_casefile_diagnosis(triage_hash=triage_casefile.triage_hash)
    key = build_casefile_stage_object_key(diagnosis_casefile.case_id, stage="diagnosis")
    client.store[key] = serialize_casefile_stage(diagnosis_casefile)

    loaded = read_casefile_stage_json_or_none(
        object_store_client=client,
        case_id=diagnosis_casefile.case_id,
        stage="diagnosis",
    )

    assert loaded is not None
    assert validate_casefile_diagnosis_json(serialize_casefile_stage(diagnosis_casefile)) == loaded


def test_read_casefile_stage_json_or_none_round_trips_linkage_payload() -> None:
    client = _FakeObjectStoreClient()
    triage_casefile = _sample_casefile()
    linkage_casefile = _sample_casefile_linkage(triage_hash=triage_casefile.triage_hash)
    key = build_casefile_stage_object_key(linkage_casefile.case_id, stage="linkage")
    client.store[key] = serialize_casefile_stage(linkage_casefile)

    loaded = read_casefile_stage_json_or_none(
        object_store_client=client,
        case_id=linkage_casefile.case_id,
        stage="linkage",
    )

    assert loaded is not None
    assert validate_casefile_linkage_json(serialize_casefile_stage(linkage_casefile)) == loaded


def test_read_casefile_stage_json_or_none_round_trips_labels_payload() -> None:
    client = _FakeObjectStoreClient()
    triage_casefile = _sample_casefile()
    labels_casefile = _sample_casefile_labels(triage_hash=triage_casefile.triage_hash)
    key = build_casefile_stage_object_key(labels_casefile.case_id, stage="labels")
    client.store[key] = serialize_casefile_stage(labels_casefile)

    loaded = read_casefile_stage_json_or_none(
        object_store_client=client,
        case_id=labels_casefile.case_id,
        stage="labels",
    )

    assert loaded is not None
    assert validate_casefile_labels_json(serialize_casefile_stage(labels_casefile)) == loaded


def test_read_casefile_stage_json_or_none_returns_none_for_typed_not_found_error() -> None:
    client = _FakeObjectStoreClient()
    client.fail_get = ObjectNotFoundError("object not found key=cases/case-123/diagnosis.json")

    loaded = read_casefile_stage_json_or_none(
        object_store_client=client,
        case_id="case-123",
        stage="diagnosis",
    )

    assert loaded is None


def test_read_casefile_stage_json_or_none_reraises_unrelated_keyerror() -> None:
    client = _FakeObjectStoreClient()
    client.fail_get = KeyError("unexpected")

    with pytest.raises(KeyError, match="unexpected"):
        read_casefile_stage_json_or_none(
            object_store_client=client,
            case_id="case-123",
            stage="diagnosis",
        )


def test_list_present_casefile_stages_returns_written_stages_only() -> None:
    client = _FakeObjectStoreClient()
    triage_casefile = _sample_casefile()
    diagnosis_casefile = _sample_casefile_diagnosis(triage_hash=triage_casefile.triage_hash)
    triage_key = build_casefile_triage_object_key(triage_casefile.case_id)
    client.store[triage_key] = serialize_casefile_triage(triage_casefile)
    client.store[
        build_casefile_stage_object_key(diagnosis_casefile.case_id, stage="diagnosis")
    ] = serialize_casefile_stage(diagnosis_casefile)

    present = list_present_casefile_stages(
        object_store_client=client,
        case_id=triage_casefile.case_id,
    )

    assert present == ("triage", "diagnosis")
