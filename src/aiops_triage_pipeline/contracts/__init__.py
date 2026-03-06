"""Frozen contract models for aiops-triage-pipeline."""

# ── Event Contracts (Story 1.2) ─────────────────────────────────────────────
from aiops_triage_pipeline.contracts.action_decision import ActionDecisionV1
from aiops_triage_pipeline.contracts.case_header_event import CaseHeaderEventV1
from aiops_triage_pipeline.contracts.casefile_retention_policy import (
    CasefileRetentionPolicy,
    CasefileRetentionPolicyV1,
)
from aiops_triage_pipeline.contracts.diagnosis_report import DiagnosisReportV1, EvidencePack
from aiops_triage_pipeline.contracts.enums import (
    Action,
    CriticalityTier,
    DiagnosisConfidence,
    Environment,
    EvidenceStatus,
)
from aiops_triage_pipeline.contracts.gate_input import Finding, GateInputV1

# ── Policy Contracts (Story 1.3) ─────────────────────────────────────────────
from aiops_triage_pipeline.contracts.local_dev import LocalDevContractV1, LocalDevIntegrationModes
from aiops_triage_pipeline.contracts.outbox_policy import OutboxPolicyV1, OutboxRetentionPolicy
from aiops_triage_pipeline.contracts.peak_policy import PeakPolicyV1, PeakThresholdPolicy
from aiops_triage_pipeline.contracts.prometheus_metrics import (
    MetricDefinition,
    MetricIdentityConfig,
    PrometheusMetricsContractV1,
    TruthfulnessConfig,
)
from aiops_triage_pipeline.contracts.redis_ttl_policy import (
    AG5DedupeTtlConfig,
    RedisTtlPolicyV1,
    RedisTtlsByEnv,
)
from aiops_triage_pipeline.contracts.rulebook import (
    GateCheck,
    GateEffect,
    GateEffects,
    GateSpec,
    RulebookCaps,
    RulebookDefaults,
    RulebookV1,
)
from aiops_triage_pipeline.contracts.sn_linkage import ServiceNowLinkageContractV1
from aiops_triage_pipeline.contracts.topology_registry import TopologyRegistryLoaderRulesV1
from aiops_triage_pipeline.contracts.triage_excerpt import TriageExcerptV1

__all__ = [
    # Enums
    "Action",
    "CriticalityTier",
    "DiagnosisConfidence",
    "Environment",
    "EvidenceStatus",
    # Event contracts (Story 1.2)
    "ActionDecisionV1",
    "CasefileRetentionPolicy",
    "CasefileRetentionPolicyV1",
    "CaseHeaderEventV1",
    "DiagnosisReportV1",
    "EvidencePack",
    "Finding",
    "GateInputV1",
    "TriageExcerptV1",
    # Policy contracts (Story 1.3)
    "GateCheck",
    "GateEffect",
    "GateEffects",
    "GateSpec",
    "RulebookCaps",
    "RulebookDefaults",
    "RulebookV1",
    "PeakPolicyV1",
    "PeakThresholdPolicy",
    "MetricDefinition",
    "MetricIdentityConfig",
    "PrometheusMetricsContractV1",
    "TruthfulnessConfig",
    "AG5DedupeTtlConfig",
    "RedisTtlPolicyV1",
    "RedisTtlsByEnv",
    "OutboxPolicyV1",
    "OutboxRetentionPolicy",
    "ServiceNowLinkageContractV1",
    "LocalDevContractV1",
    "LocalDevIntegrationModes",
    "TopologyRegistryLoaderRulesV1",
]
