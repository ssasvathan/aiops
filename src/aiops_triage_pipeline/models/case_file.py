"""CaseFile triage-stage models for Story 4.1."""

from __future__ import annotations

import re
from typing import Literal

from pydantic import AwareDatetime, BaseModel, Field, field_validator

from aiops_triage_pipeline.contracts.action_decision import ActionDecisionV1
from aiops_triage_pipeline.contracts.enums import Action, CriticalityTier, EvidenceStatus
from aiops_triage_pipeline.contracts.gate_input import GateInputV1
from aiops_triage_pipeline.models.peak import PeakWindowContext

_HEX_64 = re.compile(r"^[0-9a-f]{64}$")
TRIAGE_HASH_PLACEHOLDER = "0" * 64


class CaseFilePolicyVersions(BaseModel, frozen=True):
    """Version stamps required for deterministic replay and audit trails."""

    rulebook_version: str = Field(min_length=1)
    peak_policy_version: str = Field(min_length=1)
    prometheus_metrics_contract_version: str = Field(min_length=1)
    exposure_denylist_version: str = Field(min_length=1)
    diagnosis_policy_version: str = Field(min_length=1)


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
