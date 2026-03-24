"""CaseFile triage-stage models."""

from __future__ import annotations

import re
from typing import Literal

from pydantic import AwareDatetime, BaseModel, Field, field_validator

from aiops_triage_pipeline.contracts.action_decision import ActionDecisionV1
from aiops_triage_pipeline.contracts.diagnosis_report import DiagnosisReportV1
from aiops_triage_pipeline.contracts.enums import Action, CriticalityTier, EvidenceStatus
from aiops_triage_pipeline.contracts.gate_input import GateInputV1
from aiops_triage_pipeline.models.peak import PeakWindowContext

_HEX_64 = re.compile(r"^[0-9a-f]{64}$")
TRIAGE_HASH_PLACEHOLDER = "0" * 64
DIAGNOSIS_HASH_PLACEHOLDER = "0" * 64
LINKAGE_HASH_PLACEHOLDER = "0" * 64
LABELS_HASH_PLACEHOLDER = "0" * 64


class CaseFilePolicyVersions(BaseModel, frozen=True):
    """Version stamps required for deterministic replay and audit trails."""

    rulebook_version: str = Field(min_length=1)
    peak_policy_version: str = Field(min_length=1)
    prometheus_metrics_contract_version: str = Field(min_length=1)
    exposure_denylist_version: str = Field(min_length=1)
    diagnosis_policy_version: str = Field(min_length=1)
    anomaly_detection_policy_version: str = Field(default="v1", min_length=1)
    topology_registry_version: str = Field(default="2", min_length=1)


class CaseFileDownstreamImpact(BaseModel, frozen=True):
    """Downstream impact marker derived from topology resolution."""

    component_type: Literal["shared_component", "sink", "source"]
    component_id: str
    exposure_type: Literal[
        "DOWNSTREAM_DATA_FRESHNESS_RISK",
        "DIRECT_COMPONENT_RISK",
        "VISIBILITY_ONLY",
    ]
    risk_status: Literal["AT_RISK"] = "AT_RISK"


class CaseFileRoutingContext(BaseModel, frozen=True):
    """Routing ownership context required for audit traceability."""

    lookup_level: Literal[
        "consumer_group_owner",
        "topic_owner",
        "stream_default_owner",
        "platform_default",
    ]
    routing_key: str
    owning_team_id: str
    owning_team_name: str
    support_channel: str | None = None
    escalation_policy_ref: str | None = None
    service_now_assignment_group: str | None = None


class CaseFileTopologyContext(BaseModel, frozen=True):
    """Topology and blast-radius context for the assembled triage artifact."""

    stream_id: str
    topic_role: Literal["SOURCE_TOPIC", "SHARED_TOPIC", "SINK_TOPIC"]
    criticality_tier: CriticalityTier
    source_system: str | None = None
    blast_radius: Literal["LOCAL_SOURCE_INGESTION", "SHARED_KAFKA_INGESTION"]
    downstream_impacts: tuple[CaseFileDownstreamImpact, ...] = ()
    routing: CaseFileRoutingContext


class CaseFileEvidenceRow(BaseModel, frozen=True):
    """Serializable evidence row snapshot for CaseFile payloads."""

    metric_key: str
    value: float
    labels: dict[str, str]
    scope: tuple[str, ...]


class CaseFileEvidenceSnapshot(BaseModel, frozen=True):
    """Evidence snapshot required to replay and inspect triage decisions."""

    scope: tuple[str, ...] | None = None
    rows: tuple[CaseFileEvidenceRow, ...] = ()
    evidence_status_map: dict[str, EvidenceStatus] = Field(default_factory=dict)
    telemetry_degraded_active: bool = False
    max_safe_action: Action | None = None
    peak_context: PeakWindowContext | None = None


class CaseFileTriageV1(BaseModel, frozen=True):
    """CaseFile triage.json payload with deterministic hash metadata."""

    schema_version: Literal["v1"] = "v1"
    case_id: str
    scope: tuple[str, ...]
    triage_timestamp: AwareDatetime
    evidence_snapshot: CaseFileEvidenceSnapshot
    topology_context: CaseFileTopologyContext
    gate_input: GateInputV1
    action_decision: ActionDecisionV1
    policy_versions: CaseFilePolicyVersions
    triage_hash: str

    @field_validator("triage_hash")
    @classmethod
    def _validate_triage_hash(cls, value: str) -> str:
        if not _HEX_64.fullmatch(value):
            raise ValueError("triage_hash must be a 64-char lowercase SHA-256 hex string")
        return value


class CaseFileDiagnosisV1(BaseModel, frozen=True):
    """CaseFile diagnosis.json payload with hash-chain dependency on triage.json."""

    schema_version: Literal["v1"] = "v1"
    case_id: str
    diagnosis_report: DiagnosisReportV1
    triage_hash: str
    diagnosis_hash: str

    @field_validator("triage_hash", "diagnosis_hash")
    @classmethod
    def _validate_hash_fields(cls, value: str) -> str:
        if not _HEX_64.fullmatch(value):
            raise ValueError("hash fields must be 64-char lowercase SHA-256 hex strings")
        return value


class CaseFileLinkageV1(BaseModel, frozen=True):
    """CaseFile linkage.json payload with hash-chain dependencies."""

    schema_version: Literal["v1"] = "v1"
    case_id: str
    linkage_status: Literal["linked", "not-linked", "skipped", "failed"]
    linkage_reason: str
    incident_sys_id: str | None = None
    problem_sys_id: str | None = None
    problem_external_id: str | None = None
    pir_task_sys_ids: tuple[str, ...] = ()
    pir_task_external_ids: tuple[str, ...] = ()
    triage_hash: str
    diagnosis_hash: str | None = None
    linkage_hash: str

    @field_validator("triage_hash", "linkage_hash")
    @classmethod
    def _validate_required_hash_fields(cls, value: str) -> str:
        if not _HEX_64.fullmatch(value):
            raise ValueError("hash fields must be 64-char lowercase SHA-256 hex strings")
        return value

    @field_validator("diagnosis_hash")
    @classmethod
    def _validate_optional_diagnosis_hash(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if not _HEX_64.fullmatch(value):
            raise ValueError("diagnosis_hash must be a 64-char lowercase SHA-256 hex string")
        return value

    @field_validator("incident_sys_id", "problem_sys_id", "problem_external_id")
    @classmethod
    def _validate_optional_non_empty(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("optional linkage identifiers must be non-empty when provided")
        return normalized

    @field_validator("pir_task_sys_ids", "pir_task_external_ids")
    @classmethod
    def _validate_identifier_collections(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(item.strip() for item in value if item.strip())
        if len(normalized) != len(value):
            raise ValueError("linkage identifier collections cannot contain empty values")
        return normalized


# Label data quality thresholds (FR64) - enforcement deferred to Phase 2.
LABEL_COMPLETION_RATE_THRESHOLD: float = 0.70
LABEL_ELIGIBLE_FIELDS: tuple[str, ...] = (
    "owner_confirmed",
    "resolution_category",
    "false_positive",
)
LABEL_CONSISTENCY_RULES: tuple[str, ...] = (
    "false_positive=True requires resolution_category to be None or 'FALSE_POSITIVE'",
    "owner_confirmed=True requires missing_evidence_reason to be None",
    "resolution_category='FALSE_POSITIVE' cannot pair with false_positive=False",
)


class CaseFileLabelDataV1(BaseModel, frozen=True):
    """Typed label fields for CaseFile labels.json payloads."""

    owner_confirmed: bool | None = None
    resolution_category: str | None = None
    false_positive: bool | None = None
    missing_evidence_reason: str | None = None


def evaluate_label_consistency_issues(label_data: CaseFileLabelDataV1) -> tuple[str, ...]:
    """Evaluate FR64 label consistency checks without enforcing them at runtime."""
    issues: list[str] = []
    if label_data.false_positive is True and label_data.resolution_category not in (
        None,
        "FALSE_POSITIVE",
    ):
        issues.append(
            "false_positive=True requires resolution_category to be None or 'FALSE_POSITIVE'"
        )
    if label_data.owner_confirmed is True and label_data.missing_evidence_reason is not None:
        issues.append("owner_confirmed=True requires missing_evidence_reason to be None")
    if (
        label_data.resolution_category == "FALSE_POSITIVE"
        and label_data.false_positive is False
    ):
        issues.append(
            "resolution_category='FALSE_POSITIVE' cannot pair with false_positive=False"
        )
    return tuple(issues)


class CaseFileLabelsV1(BaseModel, frozen=True):
    """CaseFile labels.json payload with hash-chain dependencies."""

    schema_version: Literal["v1"] = "v1"
    case_id: str
    label_data: CaseFileLabelDataV1
    triage_hash: str
    diagnosis_hash: str | None = None
    labels_hash: str

    @field_validator("triage_hash", "labels_hash")
    @classmethod
    def _validate_required_hash_fields(cls, value: str) -> str:
        if not _HEX_64.fullmatch(value):
            raise ValueError("hash fields must be 64-char lowercase SHA-256 hex strings")
        return value

    @field_validator("diagnosis_hash")
    @classmethod
    def _validate_optional_diagnosis_hash(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if not _HEX_64.fullmatch(value):
            raise ValueError("diagnosis_hash must be a 64-char lowercase SHA-256 hex string")
        return value
