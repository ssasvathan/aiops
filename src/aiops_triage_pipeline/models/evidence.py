"""Evidence-stage data model for normalized Prometheus samples."""

from types import MappingProxyType
from typing import Mapping

from pydantic import BaseModel, model_validator

from aiops_triage_pipeline.contracts.gate_input import Finding
from aiops_triage_pipeline.models.anomaly import AnomalyDetectionResult


class EvidenceRow(BaseModel, frozen=True):
    """A normalized evidence row scoped for downstream processing."""

    metric_key: str
    value: float
    labels: Mapping[str, str]
    scope: tuple[str, ...]

    @model_validator(mode="after")
    def _freeze_labels(self) -> "EvidenceRow":
        # Freeze nested mapping so rows remain immutable end-to-end.
        object.__setattr__(self, "labels", MappingProxyType(dict(self.labels)))
        return self


class EvidenceStageOutput(BaseModel, frozen=True):
    """Evidence stage output with normalized rows and anomaly findings."""

    rows: tuple[EvidenceRow, ...]
    anomaly_result: AnomalyDetectionResult
    gate_findings_by_scope: Mapping[tuple[str, ...], tuple[Finding, ...]]

    @model_validator(mode="after")
    def _freeze_gate_findings(
        self,
    ) -> "EvidenceStageOutput":
        # Freeze nested mapping so stage output cannot be mutated after creation.
        object.__setattr__(
            self, "gate_findings_by_scope", MappingProxyType(dict(self.gate_findings_by_scope))
        )
        return self
