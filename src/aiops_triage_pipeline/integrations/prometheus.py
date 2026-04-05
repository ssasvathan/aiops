"""Prometheus contract-driven query and label normalization helpers."""

import json
import math
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Mapping, Protocol
from urllib.parse import urlencode
from urllib.request import urlopen

from aiops_triage_pipeline.config.settings import load_policy_yaml
from aiops_triage_pipeline.contracts.prometheus_metrics import PrometheusMetricsContractV1

DEFAULT_PROMETHEUS_METRICS_CONTRACT_PATH = (
    Path(__file__).resolve().parents[3] / "config/policies/prometheus-metrics-contract-v1.yaml"
)


class PrometheusClientProtocol(Protocol):
    """Structural protocol for Prometheus query clients used in evidence collection."""

    def query_instant(self, metric_name: str, at_time: datetime) -> list[dict[str, object]]:
        """Query an instant vector and return normalized sample records."""
        ...

    def query_range(
        self,
        metric_name: str,
        start: datetime,
        end: datetime,
        step_seconds: int,
        *,
        timeout: int = 60,
    ) -> list[dict[str, object]]:
        """Query a range vector and return normalized matrix records."""
        ...


@dataclass(frozen=True)
class MetricQueryDefinition:
    """Canonical metric query definition loaded from frozen policy contract."""

    metric_key: str
    metric_name: str
    role: str


class PrometheusHTTPClient:
    """Minimal Prometheus HTTP API client for instant vector queries."""

    def __init__(self, base_url: str = "http://localhost:9090") -> None:
        self.base_url = base_url.rstrip("/")

    def query_instant(self, metric_name: str, at_time: datetime) -> list[dict[str, object]]:
        """Query Prometheus /api/v1/query and return normalized sample records."""
        params = urlencode({"query": metric_name, "time": at_time.isoformat()})
        endpoint = f"{self.base_url}/api/v1/query?{params}"

        with urlopen(endpoint, timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))

        if payload.get("status") != "success":
            raise ValueError(f"Prometheus query failed for {metric_name}: {payload}")

        result_type = payload.get("data", {}).get("resultType")
        if result_type != "vector":
            raise ValueError(f"Expected vector resultType, got {result_type!r} for {metric_name}")

        samples: list[dict[str, object]] = []
        for item in payload.get("data", {}).get("result", []):
            metric_labels = {k: str(v) for k, v in item.get("metric", {}).items()}
            value_pair = item.get("value")
            if not value_pair or len(value_pair) < 2 or value_pair[1] is None:
                continue  # skip samples with no value — preserve UNKNOWN semantics
            value_float = float(value_pair[1])
            if not math.isfinite(value_float):
                continue  # skip NaN/Inf — preserve UNKNOWN semantics rather than propagating
            samples.append({"labels": metric_labels, "value": value_float})
        return samples

    def query_range(
        self,
        metric_name: str,
        start: datetime,
        end: datetime,
        step_seconds: int,
        *,
        timeout: int = 60,
    ) -> list[dict[str, object]]:
        """Query Prometheus /api/v1/query_range and return normalized matrix records.

        Returns a list of records, each with:
          - "labels": dict[str, str] of metric labels
          - "values": list of (unix_timestamp, metric_value) tuples (NaN/Inf filtered)
        """
        params = urlencode({
            "query": metric_name,
            "start": start.isoformat(),
            "end": end.isoformat(),
            "step": f"{step_seconds}s",
        })
        endpoint = f"{self.base_url}/api/v1/query_range?{params}"

        with urlopen(endpoint, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))

        if payload.get("status") != "success":
            raise ValueError(f"Prometheus range query failed for {metric_name}: {payload}")

        result_type = payload.get("data", {}).get("resultType")
        if result_type != "matrix":
            raise ValueError(
                f"Expected matrix resultType, got {result_type!r} for {metric_name}"
            )

        records: list[dict[str, object]] = []
        for item in payload.get("data", {}).get("result", []):
            metric_labels = {k: str(v) for k, v in item.get("metric", {}).items()}
            raw_values = item.get("values", [])
            values: list[tuple[float, float]] = []
            for ts_raw, val_raw in raw_values:
                try:
                    val_float = float(val_raw)
                except (TypeError, ValueError):
                    continue  # skip unparseable values — preserve UNKNOWN semantics
                if not math.isfinite(val_float):
                    continue  # skip NaN/Inf — preserve UNKNOWN semantics
                values.append((float(ts_raw), val_float))
            records.append({"labels": metric_labels, "values": values})
        return records


def load_prometheus_metrics_contract(
    contract_path: Path = DEFAULT_PROMETHEUS_METRICS_CONTRACT_PATH,
) -> PrometheusMetricsContractV1:
    """Load and validate Prometheus metrics contract from policy YAML."""
    return load_policy_yaml(contract_path, PrometheusMetricsContractV1)


def build_metric_queries(
    contract_path: Path = DEFAULT_PROMETHEUS_METRICS_CONTRACT_PATH,
) -> dict[str, MetricQueryDefinition]:
    """Build canonical query definitions keyed by contract metric key."""
    contract = load_prometheus_metrics_contract(contract_path)
    return {
        metric_key: MetricQueryDefinition(
            metric_key=metric_key,
            metric_name=definition.canonical,
            role=definition.role,
        )
        for metric_key, definition in contract.metrics.items()
    }


def normalize_labels(labels: Mapping[str, str]) -> dict[str, str]:
    """Normalize labels to internal identity, enforcing cluster_id := cluster_name."""
    cluster_name = labels.get("cluster_name")
    if cluster_name is None:
        raise ValueError("Prometheus label 'cluster_name' is required for cluster_id normalization")

    normalized = dict(labels)
    normalized["cluster_id"] = cluster_name
    return normalized
