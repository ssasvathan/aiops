"""PrometheusMetricsContractV1 — canonical metric names and alias resolution."""

from typing import Literal

from pydantic import BaseModel


class MetricIdentityConfig(BaseModel, frozen=True):
    cluster_id_rule: str
    topic_identity_labels: tuple[str, ...]
    lag_identity_labels: tuple[str, ...]
    ignore_labels_for_identity: tuple[str, ...]


class MetricDefinition(BaseModel, frozen=True):
    canonical: str
    role: str
    aliases: tuple[str, ...] = ()


class TruthfulnessConfig(BaseModel, frozen=True):
    missing_series: dict[str, str]
    partition: dict[str, str]


class PrometheusMetricsContractV1(BaseModel, frozen=True):
    schema_version: Literal["v1"] = "v1"
    version: str
    date: str
    status: str
    identity: MetricIdentityConfig
    metrics: dict[str, MetricDefinition]
    truthfulness: TruthfulnessConfig
    notes: tuple[str, ...] = ()
