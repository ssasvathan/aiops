from __future__ import annotations

from typing import get_args, get_type_hints

import pytest
from pydantic import ValidationError

import aiops_triage_pipeline.integrations.servicenow as servicenow_module
from aiops_triage_pipeline.contracts.sn_linkage import ServiceNowLinkageContractV1
from aiops_triage_pipeline.models.case_file import (
    LABEL_COMPLETION_RATE_THRESHOLD,
    LABEL_ELIGIBLE_FIELDS,
    LABELS_HASH_PLACEHOLDER,
    CaseFileLabelDataV1,
    CaseFileLabelsV1,
)
from aiops_triage_pipeline.storage.casefile_io import (
    compute_casefile_labels_hash,
    persist_casefile_labels_write_once,
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


def _make_labels_casefile(*, case_id: str = "case-abc-123") -> CaseFileLabelsV1:
    base = CaseFileLabelsV1(
        case_id=case_id,
        label_data=CaseFileLabelDataV1(
            owner_confirmed=True,
            resolution_category="FALSE_POSITIVE",
        ),
        triage_hash="a" * 64,
        labels_hash=LABELS_HASH_PLACEHOLDER,
    )
    return base.model_copy(update={"labels_hash": compute_casefile_labels_hash(base)})


def test_label_data_has_required_fields() -> None:
    assert {
        "owner_confirmed",
        "resolution_category",
        "false_positive",
        "missing_evidence_reason",
    }.issubset(set(CaseFileLabelDataV1.model_fields))


def test_label_data_fields_typed_correctly() -> None:
    hints = get_type_hints(CaseFileLabelDataV1)

    owner_args = set(get_args(hints["owner_confirmed"]))
    false_positive_args = set(get_args(hints["false_positive"]))
    resolution_args = set(get_args(hints["resolution_category"]))
    missing_reason_args = set(get_args(hints["missing_evidence_reason"]))

    assert owner_args == {bool, type(None)}
    assert false_positive_args == {bool, type(None)}
    assert resolution_args == {str, type(None)}
    assert missing_reason_args == {str, type(None)}


def test_label_data_is_frozen() -> None:
    label_data = CaseFileLabelDataV1(owner_confirmed=True)

    with pytest.raises(ValidationError):
        label_data.owner_confirmed = False  # type: ignore[misc]


def test_labels_v1_uses_label_data_model() -> None:
    field = CaseFileLabelsV1.model_fields["label_data"]
    assert field.annotation is CaseFileLabelDataV1


def test_labels_v1_is_frozen() -> None:
    labels_casefile = _make_labels_casefile()

    with pytest.raises(ValidationError):
        labels_casefile.case_id = "new-case-id"  # type: ignore[misc]


def test_label_completion_rate_threshold_is_seventy_percent() -> None:
    assert LABEL_COMPLETION_RATE_THRESHOLD == 0.70


def test_label_eligible_fields_are_defined() -> None:
    assert "owner_confirmed" in LABEL_ELIGIBLE_FIELDS
    assert "resolution_category" in LABEL_ELIGIBLE_FIELDS
    assert "false_positive" in LABEL_ELIGIBLE_FIELDS


def test_labels_json_write_once_creates_file() -> None:
    client = _FakeObjectStoreClient()
    casefile = _make_labels_casefile()

    persisted = persist_casefile_labels_write_once(
        object_store_client=client,
        casefile=casefile,
    )

    assert persisted.object_path == f"cases/{casefile.case_id}/labels.json"
    assert persisted.write_result == "created"


def test_labels_json_idempotent_write_returns_idempotent() -> None:
    client = _FakeObjectStoreClient()
    casefile = _make_labels_casefile()

    persist_casefile_labels_write_once(
        object_store_client=client,
        casefile=casefile,
    )
    persisted = persist_casefile_labels_write_once(
        object_store_client=client,
        casefile=casefile,
    )

    assert persisted.write_result == "idempotent"


def test_mi_creation_not_allowed_by_default() -> None:
    assert ServiceNowLinkageContractV1().mi_creation_allowed is False


def test_mi_creation_contract_is_frozen() -> None:
    linkage = ServiceNowLinkageContractV1()

    with pytest.raises(ValidationError):
        linkage.mi_creation_allowed = True  # type: ignore[misc]


def test_servicenow_integration_has_no_create_major_incident() -> None:
    assert not hasattr(servicenow_module, "create_major_incident")
