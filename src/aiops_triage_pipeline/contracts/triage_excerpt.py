"""TriageExcerptV1 — Kafka event published alongside CaseHeaderEventV1; cold-path LLM input."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from aiops_triage_pipeline.contracts.enums import CriticalityTier, Environment, EvidenceStatus
from aiops_triage_pipeline.contracts.gate_input import Finding


class TriageExcerptV1(BaseModel, frozen=True):
    schema_version: Literal["v1"] = "v1"
    case_id: str
    env: Environment
    cluster_id: str
    stream_id: str
    topic: str
    anomaly_family: str
    topic_role: str  # SOURCE_TOPIC / SHARED_TOPIC / SINK_TOPIC
    criticality_tier: CriticalityTier
    routing_key: str  # Team routing key
    sustained: bool
    peak: bool | None = None  # None if peak computation unavailable
    evidence_status_map: dict[str, EvidenceStatus]  # UNKNOWN propagation is critical
    findings: tuple[Finding, ...]  # Structured findings (from gate_input)
    triage_timestamp: datetime  # UTC-aware triage assembly time
