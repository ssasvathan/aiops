"""CaseHeaderEventV1 — Kafka event published via durable outbox (small header payload)."""

from typing import Literal

from pydantic import AwareDatetime, BaseModel

from aiops_triage_pipeline.contracts.enums import Action, CriticalityTier, Environment


class CaseHeaderEventV1(BaseModel, frozen=True):
    schema_version: Literal["v1"] = "v1"
    case_id: str  # Stable case identifier
    env: Environment
    cluster_id: str
    stream_id: str
    topic: str
    anomaly_family: Literal["CONSUMER_LAG", "VOLUME_DROP", "THROUGHPUT_CONSTRAINED_PROXY"]
    criticality_tier: CriticalityTier
    final_action: Action  # Gated action decision
    routing_key: str  # Team routing key from topology registry
    evaluation_ts: AwareDatetime  # UTC-aware timestamp of the evaluation cycle
