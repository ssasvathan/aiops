"""TriageExcerptV1 — Kafka event published alongside CaseHeaderEventV1; cold-path LLM input."""

from typing import Literal

from pydantic import AwareDatetime, BaseModel

from aiops_triage_pipeline.contracts.enums import CriticalityTier, Environment, EvidenceStatus
from aiops_triage_pipeline.contracts.gate_input import Finding


class TriageExcerptV1(BaseModel, frozen=True):
    schema_version: Literal["v1"] = "v1"
    case_id: str
    env: Environment
    cluster_id: str
    stream_id: str
    topic: str
    anomaly_family: Literal["CONSUMER_LAG", "VOLUME_DROP", "THROUGHPUT_CONSTRAINED_PROXY"]
    topic_role: Literal["SOURCE_TOPIC", "SHARED_TOPIC", "SINK_TOPIC"]
    criticality_tier: CriticalityTier
    routing_key: str  # Team routing key
    sustained: bool
    peak: bool | None = None  # None if peak computation unavailable
    evidence_status_map: dict[str, EvidenceStatus]  # UNKNOWN propagation is critical
    findings: tuple[Finding, ...]  # Structured findings (from gate_input)
    triage_timestamp: AwareDatetime  # UTC-aware triage assembly time
