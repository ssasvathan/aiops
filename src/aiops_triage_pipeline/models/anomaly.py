"""Anomaly detection models for Stage 1 evidence analysis."""

from collections import defaultdict
from types import MappingProxyType
from typing import Literal, Mapping

from pydantic import BaseModel, model_validator

AnomalyFamily = Literal["CONSUMER_LAG", "VOLUME_DROP", "THROUGHPUT_CONSTRAINED_PROXY"]
AnomalySeverity = Literal["LOW", "MEDIUM", "HIGH"]


class AnomalyFinding(BaseModel, frozen=True):
    """Structured anomaly finding used for downstream gate input assembly."""

    finding_id: str
    anomaly_family: AnomalyFamily
    scope: tuple[str, ...]
    severity: AnomalySeverity
    reason_codes: tuple[str, ...]
    evidence_required: tuple[str, ...]
    is_primary: bool | None = None


def group_findings_by_scope(
    findings: tuple[AnomalyFinding, ...],
) -> dict[tuple[str, ...], tuple[AnomalyFinding, ...]]:
    """Group findings by normalized scope key preserving insertion order."""
    grouped: dict[tuple[str, ...], list[AnomalyFinding]] = defaultdict(list)
    for finding in findings:
        grouped[finding.scope].append(finding)
    return {scope: tuple(scope_findings) for scope, scope_findings in grouped.items()}


class AnomalyDetectionResult(BaseModel, frozen=True):
    """Anomaly detection result keyed by normalized identity scope."""

    findings: tuple[AnomalyFinding, ...]
    findings_by_scope: Mapping[tuple[str, ...], tuple[AnomalyFinding, ...]]

    @model_validator(mode="after")
    def _freeze_findings_by_scope(
        self,
    ) -> "AnomalyDetectionResult":
        # Freeze nested mapping so "frozen=True" cannot be bypassed through mutable dict APIs.
        object.__setattr__(
            self, "findings_by_scope", MappingProxyType(dict(self.findings_by_scope))
        )
        return self
