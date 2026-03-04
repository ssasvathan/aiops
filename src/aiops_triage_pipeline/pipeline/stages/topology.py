"""Stage 3 topology assembly helpers."""

from __future__ import annotations

from types import MappingProxyType
from typing import Iterable, Mapping

from pydantic import BaseModel, Field, model_validator

from aiops_triage_pipeline.logging.setup import get_logger
from aiops_triage_pipeline.models.evidence import EvidenceStageOutput
from aiops_triage_pipeline.pipeline.stages.gating import GateInputContext
from aiops_triage_pipeline.registry.loader import TopologyRegistrySnapshot
from aiops_triage_pipeline.registry.resolver import (
    BlastRadiusClassification,
    DownstreamImpact,
    TopologyResolution,
    resolve_anomaly_scope,
)


class TopologyImpactContext(BaseModel, frozen=True):
    """Stage 3 impact metadata for downstream CaseFile/TriageExcerpt assembly paths."""

    blast_radius: BlastRadiusClassification
    downstream_impacts: tuple[DownstreamImpact, ...] = ()


class TopologyStageOutput(BaseModel, frozen=True):
    """Stage 3 output for downstream Stage 6 gate-input assembly."""

    context_by_scope: Mapping[tuple[str, ...], GateInputContext] = Field(default_factory=dict)
    impact_by_scope: Mapping[tuple[str, ...], TopologyImpactContext] = Field(default_factory=dict)
    unresolved_by_scope: Mapping[tuple[str, ...], TopologyResolution] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _freeze_nested_mappings(self) -> "TopologyStageOutput":
        object.__setattr__(self, "context_by_scope", MappingProxyType(dict(self.context_by_scope)))
        object.__setattr__(self, "impact_by_scope", MappingProxyType(dict(self.impact_by_scope)))
        object.__setattr__(
            self,
            "unresolved_by_scope",
            MappingProxyType(dict(self.unresolved_by_scope)),
        )
        return self


def collect_topology_stage_output(
    *,
    snapshot: TopologyRegistrySnapshot,
    evidence_output: EvidenceStageOutput,
) -> TopologyStageOutput:
    """Resolve topology context for all scopes produced by Stage 1 findings."""
    return build_topology_stage_output(
        snapshot=snapshot,
        scopes=evidence_output.gate_findings_by_scope.keys(),
    )


def build_topology_stage_output(
    *,
    snapshot: TopologyRegistrySnapshot,
    scopes: Iterable[tuple[str, ...]],
) -> TopologyStageOutput:
    """Resolve topology for the provided scopes and split resolved/unresolved outputs."""
    logger = get_logger("pipeline.stages.topology")
    context_by_scope: dict[tuple[str, ...], GateInputContext] = {}
    impact_by_scope: dict[tuple[str, ...], TopologyImpactContext] = {}
    unresolved_by_scope: dict[tuple[str, ...], TopologyResolution] = {}

    for scope in sorted(scopes):
        resolution = resolve_anomaly_scope(
            snapshot=snapshot,
            anomaly_scope=scope,
        )
        if resolution.status == "resolved":
            assert resolution.stream_id is not None
            assert resolution.topic_role is not None
            assert resolution.criticality_tier is not None
            assert resolution.blast_radius is not None
            context_by_scope[scope] = GateInputContext(
                stream_id=resolution.stream_id,
                topic_role=resolution.topic_role,
                criticality_tier=resolution.criticality_tier,
                source_system=resolution.source_system,
            )
            impact_by_scope[scope] = TopologyImpactContext(
                blast_radius=resolution.blast_radius,
                downstream_impacts=resolution.downstream_impacts,
            )
            continue

        unresolved_by_scope[scope] = resolution
        logger.warning(
            "topology_scope_unresolved",
            event_type="topology.scope_unresolved",
            scope=scope,
            reason_code=resolution.reason_code,
            diagnostics=dict(resolution.diagnostics),
        )

    return TopologyStageOutput(
        context_by_scope=context_by_scope,
        impact_by_scope=impact_by_scope,
        unresolved_by_scope=unresolved_by_scope,
    )
