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
    has_valid_casefile_linkage_hash,
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
    incident_sys_id: str | None = None,
    problem_sys_id: str | None = None,
    problem_external_id: str | None = None,
    pir_task_sys_ids: tuple[str, ...] = (),
    pir_task_external_ids: tuple[str, ...] = (),
) -> CaseFileLinkageV1:
    base = CaseFileLinkageV1(
        case_id="case-prod-cluster-a-orders-volume-drop",
        linkage_status="linked",
        linkage_reason="linked-to-problem",
        incident_sys_id=incident_sys_id,
        problem_sys_id=problem_sys_id,
        problem_external_id=problem_external_id,
        pir_task_sys_ids=pir_task_sys_ids,
        pir_task_external_ids=pir_task_external_ids,
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


def test_compute_casefile_linkage_hash_matches_stored_hash_with_sn_fields() -> None:
    triage_casefile = _sample_casefile()
    linkage_casefile = _sample_casefile_linkage(
        triage_hash=triage_casefile.triage_hash,
        incident_sys_id="inc-001",
        problem_sys_id="prb-001",
        problem_external_id="aiops:problem:case:pd:hash",
        pir_task_sys_ids=("ptsk-001", "ptsk-002"),
        pir_task_external_ids=("aiops:pir-task:a", "aiops:pir-task:b"),
    )

    assert linkage_casefile.linkage_hash == compute_casefile_linkage_hash(linkage_casefile)
    assert has_valid_casefile_linkage_hash(linkage_casefile)


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
    linkage_casefile = _sample_casefile_linkage(
        triage_hash=triage_casefile.triage_hash,
        incident_sys_id="inc-001",
        problem_sys_id="prb-001",
        problem_external_id="aiops:problem:case:pd:hash",
        pir_task_sys_ids=("ptsk-001",),
        pir_task_external_ids=("aiops:pir-task:case:pd:hash:timeline",),
    )

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
    assert client.last_metadata["incident_sys_id"] == "inc-001"
    assert client.last_metadata["problem_sys_id"] == "prb-001"
    assert client.last_metadata["problem_external_id"] == "aiops:problem:case:pd:hash"
    assert client.last_metadata["pir_task_sys_ids"] == "ptsk-001"
    assert (
        client.last_metadata["pir_task_external_ids"]
        == "aiops:pir-task:case:pd:hash:timeline"
    )


def test_validate_casefile_linkage_json_accepts_legacy_payload_without_sn_fields() -> None:
    triage_casefile = _sample_casefile()
    legacy_payload = _sample_casefile_linkage(triage_hash=triage_casefile.triage_hash)

    validated = validate_casefile_linkage_json(serialize_casefile_stage(legacy_payload))

    assert validated.incident_sys_id is None
    assert validated.problem_sys_id is None
    assert validated.problem_external_id is None
    assert validated.pir_task_sys_ids == ()
    assert validated.pir_task_external_ids == ()


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


# ---------------------------------------------------------------------------
# Story 2.1 ATDD — RED phase tests (AC: 1, 2)
# ---------------------------------------------------------------------------


def test_persist_casefile_triage_write_once_raises_invariant_violation_on_placeholder_hash() -> (
    None
):
    """AC: 1 — persist_casefile_triage_write_once must reject a casefile whose triage_hash has
    not been finalized (still set to TRIAGE_HASH_PLACEHOLDER).  The hash guard must fire before
    any object-store interaction to enforce write-once integrity."""
    client = _FakeObjectStoreClient()
    # Build a casefile with the placeholder hash still set (not yet finalized).
    raw = _sample_casefile().model_dump(mode="json")
    raw["triage_hash"] = TRIAGE_HASH_PLACEHOLDER
    unfinalized = CaseFileTriageV1.model_validate(raw)

    with pytest.raises(InvariantViolation):
        persist_casefile_triage_write_once(
            object_store_client=client,
            casefile=unfinalized,
        )


def test_persist_casefile_triage_write_once_idempotent_retry_raises_on_differing_payload() -> None:
    """AC: 1 — idempotent retry path must validate payload equality before returning 'idempotent'.
    An existing object with a different payload (even a structurally valid JSON with a different
    triage_hash) must cause InvariantViolation, not a silent idempotent acceptance."""
    client = _FakeObjectStoreClient()
    casefile = _sample_casefile()
    key = build_casefile_triage_object_key(casefile.case_id)

    # Pre-seed store with a structurally valid triage payload whose content differs from
    # the in-flight casefile (simulating a concurrent write of a different decision body).
    # Use a raw JSON payload that passes schema validation but has a mismatched triage_hash.
    import json as _json

    different_raw = _json.loads(serialize_casefile_triage(casefile).decode("utf-8"))
    different_raw["policy_versions"]["rulebook_version"] = "different-rulebook"
    # Recompute the hash for the modified payload so that it is internally consistent but
    # represents a different casefile (different decision content).
    from aiops_triage_pipeline.models.case_file import TRIAGE_HASH_PLACEHOLDER as _PH

    different_raw["triage_hash"] = _PH  # placeholder to allow model validation
    temp = CaseFileTriageV1.model_validate(different_raw)
    from aiops_triage_pipeline.storage.casefile_io import compute_casefile_triage_hash as _cth

    different_with_hash = temp.model_copy(update={"triage_hash": _cth(temp)})
    client.store[key] = serialize_casefile_triage(different_with_hash)

    # Idempotent branch triggers → existing payload differs → InvariantViolation expected.
    with pytest.raises(InvariantViolation, match="write-once"):
        persist_casefile_triage_write_once(
            object_store_client=client,
            casefile=casefile,
        )


def test_casefile_policy_versions_anomaly_detection_policy_version_field_present() -> None:
    """AC: 1 / FR31 — CaseFilePolicyVersions must stamp anomaly_detection_policy_version so that
    all active policies affecting triage decisions are covered for 25-month decision replay."""
    pv = CaseFilePolicyVersions(
        rulebook_version="1",
        peak_policy_version="v1",
        prometheus_metrics_contract_version="v1.0.0",
        exposure_denylist_version="v1.0.0",
        diagnosis_policy_version="v1",
        anomaly_detection_policy_version="v1",  # FR31 gap — field not yet in model
    )
    assert pv.anomaly_detection_policy_version == "v1"


def test_casefile_policy_versions_anomaly_detection_policy_version_rejects_empty() -> None:
    """AC: 1 / FR31 — anomaly_detection_policy_version must enforce min_length=1 to prevent
    silent empty-stamp persistence."""
    with pytest.raises(ValidationError):
        CaseFilePolicyVersions(
            rulebook_version="1",
            peak_policy_version="v1",
            prometheus_metrics_contract_version="v1.0.0",
            exposure_denylist_version="v1.0.0",
            diagnosis_policy_version="v1",
            anomaly_detection_policy_version="",  # must reject empty string
        )


def test_casefile_policy_versions_topology_registry_version_field_present() -> None:
    """AC: 2 / FR53 — CaseFilePolicyVersions must stamp topology_registry_version so that
    every casefile declares which topology registry version governed routing decisions."""
    pv = CaseFilePolicyVersions(
        rulebook_version="1",
        peak_policy_version="v1",
        prometheus_metrics_contract_version="v1.0.0",
        exposure_denylist_version="v1.0.0",
        diagnosis_policy_version="v1",
        topology_registry_version="2",
    )
    assert pv.topology_registry_version == "2"


def test_casefile_policy_versions_topology_registry_version_rejects_empty() -> None:
    """AC: 2 / FR53 — topology_registry_version must enforce min_length=1 to prevent
    silent empty-stamp persistence."""
    with pytest.raises(ValidationError):
        CaseFilePolicyVersions(
            rulebook_version="1",
            peak_policy_version="v1",
            prometheus_metrics_contract_version="v1.0.0",
            exposure_denylist_version="v1.0.0",
            diagnosis_policy_version="v1",
            topology_registry_version="",  # must reject empty string
        )


def test_hash_computation_excludes_raw_sensitive_fields_in_baseline() -> None:
    """AC: 1 / NFR-S1 — denylist sanitization must run before hash computation so that raw
    sensitive field values never appear in the hash payload baseline.
    Verifies that the canonical hash payload (with placeholder) does not contain raw token
    values that would appear in an unsanitized decision_basis."""
    import json

    casefile = _sample_casefile()
    # Inject a sensitive token into a copy of the casefile to simulate a pre-sanitize case.
    raw = casefile.model_dump(mode="json")
    raw["gate_input"]["decision_basis"] = {"auth": "Bearer SomeTokenValue"}
    raw["triage_hash"] = TRIAGE_HASH_PLACEHOLDER
    dirty = CaseFileTriageV1.model_validate(raw)
    # The canonical hash payload (placeholder substituted) should not contain the raw bearer
    # token since sanitization should have cleared it before this function is called.
    canonical_json = dirty.model_copy(
        update={"triage_hash": TRIAGE_HASH_PLACEHOLDER}
    ).model_dump_json()
    # This test documents the contract: the canonical payload passed to the hash function
    # must not contain unsanitized bearer tokens.
    # (In a correctly sanitized casefile produced by assemble_casefile_triage_stage, this
    # assertion always holds. The test serves as a regression guard for new code paths.)
    assert "Bearer SomeTokenValue" not in json.loads(canonical_json).get(
        "gate_input", {}
    ).get("decision_basis", {}).get("auth", ""), (
        "Raw sensitive token value must never appear in the canonical hash payload baseline"
    )
