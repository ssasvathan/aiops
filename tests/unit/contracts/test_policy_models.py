"""Unit tests for Story 1.3 policy contract models."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from aiops_triage_pipeline.config.settings import load_policy_yaml
from aiops_triage_pipeline.contracts import (
    AG5DedupeTtlConfig,
    CasefileRetentionPolicyV1,
    GateEffects,
    GateSpec,
    LocalDevContractV1,
    OutboxPolicyV1,
    PeakPolicyV1,
    PrometheusMetricsContractV1,
    RedisTtlPolicyV1,
    RulebookV1,
    ServiceNowLinkageContractV1,
    TopologyRegistryLoaderRulesV1,
)

# ── Immutability tests ────────────────────────────────────────────────────────


def test_rulebook_is_frozen(minimal_rulebook: RulebookV1) -> None:
    with pytest.raises(ValidationError):
        minimal_rulebook.version = 2  # type: ignore[misc]


def test_peak_policy_is_frozen(minimal_peak_policy: PeakPolicyV1) -> None:
    with pytest.raises(ValidationError):
        minimal_peak_policy.timezone = "UTC"  # type: ignore[misc]


def test_prometheus_metrics_is_frozen(
    minimal_prometheus_metrics: PrometheusMetricsContractV1,
) -> None:
    with pytest.raises(ValidationError):
        minimal_prometheus_metrics.status = "DRAFT"  # type: ignore[misc]


def test_redis_ttl_is_frozen(minimal_redis_ttl: RedisTtlPolicyV1) -> None:
    with pytest.raises(ValidationError):
        minimal_redis_ttl.ttls_by_env = {}  # type: ignore[misc]


def test_outbox_policy_is_frozen(minimal_outbox_policy: OutboxPolicyV1) -> None:
    with pytest.raises(ValidationError):
        minimal_outbox_policy.retention_by_env = {}  # type: ignore[misc]


def test_casefile_retention_policy_is_frozen(
    minimal_casefile_retention_policy: CasefileRetentionPolicyV1,
) -> None:
    with pytest.raises(ValidationError):
        minimal_casefile_retention_policy.retention_by_env = {}  # type: ignore[misc]


def test_sn_linkage_is_frozen(minimal_sn_linkage: ServiceNowLinkageContractV1) -> None:
    with pytest.raises(ValidationError):
        minimal_sn_linkage.enabled = True  # type: ignore[misc]


def test_local_dev_is_frozen(minimal_local_dev: LocalDevContractV1) -> None:
    with pytest.raises(ValidationError):
        minimal_local_dev.use_testcontainers = True  # type: ignore[misc]


def test_topology_registry_is_frozen(
    minimal_topology_registry: TopologyRegistryLoaderRulesV1,
) -> None:
    with pytest.raises(ValidationError):
        minimal_topology_registry.prefer_v2_format = False  # type: ignore[misc]


# ── Round-trip serialization tests ────────────────────────────────────────────


def test_rulebook_round_trip(minimal_rulebook: RulebookV1) -> None:
    json_str = minimal_rulebook.model_dump_json()
    reconstructed = RulebookV1.model_validate_json(json_str)
    assert minimal_rulebook == reconstructed


def test_peak_policy_round_trip(minimal_peak_policy: PeakPolicyV1) -> None:
    json_str = minimal_peak_policy.model_dump_json()
    reconstructed = PeakPolicyV1.model_validate_json(json_str)
    assert minimal_peak_policy == reconstructed


def test_prometheus_metrics_round_trip(
    minimal_prometheus_metrics: PrometheusMetricsContractV1,
) -> None:
    json_str = minimal_prometheus_metrics.model_dump_json()
    reconstructed = PrometheusMetricsContractV1.model_validate_json(json_str)
    assert minimal_prometheus_metrics == reconstructed


def test_redis_ttl_round_trip(minimal_redis_ttl: RedisTtlPolicyV1) -> None:
    json_str = minimal_redis_ttl.model_dump_json()
    reconstructed = RedisTtlPolicyV1.model_validate_json(json_str)
    assert minimal_redis_ttl == reconstructed


def test_outbox_policy_round_trip(minimal_outbox_policy: OutboxPolicyV1) -> None:
    json_str = minimal_outbox_policy.model_dump_json()
    reconstructed = OutboxPolicyV1.model_validate_json(json_str)
    assert minimal_outbox_policy == reconstructed


def test_casefile_retention_policy_round_trip(
    minimal_casefile_retention_policy: CasefileRetentionPolicyV1,
) -> None:
    json_str = minimal_casefile_retention_policy.model_dump_json()
    reconstructed = CasefileRetentionPolicyV1.model_validate_json(json_str)
    assert minimal_casefile_retention_policy == reconstructed


def test_sn_linkage_round_trip(minimal_sn_linkage: ServiceNowLinkageContractV1) -> None:
    json_str = minimal_sn_linkage.model_dump_json()
    reconstructed = ServiceNowLinkageContractV1.model_validate_json(json_str)
    assert minimal_sn_linkage == reconstructed


def test_local_dev_round_trip(minimal_local_dev: LocalDevContractV1) -> None:
    json_str = minimal_local_dev.model_dump_json()
    reconstructed = LocalDevContractV1.model_validate_json(json_str)
    assert minimal_local_dev == reconstructed


def test_topology_registry_round_trip(
    minimal_topology_registry: TopologyRegistryLoaderRulesV1,
) -> None:
    json_str = minimal_topology_registry.model_dump_json()
    reconstructed = TopologyRegistryLoaderRulesV1.model_validate_json(json_str)
    assert minimal_topology_registry == reconstructed


# ── Schema version tests ──────────────────────────────────────────────────────


def test_all_policy_contracts_have_schema_version_v1(
    minimal_rulebook: RulebookV1,
    minimal_peak_policy: PeakPolicyV1,
    minimal_prometheus_metrics: PrometheusMetricsContractV1,
    minimal_redis_ttl: RedisTtlPolicyV1,
    minimal_outbox_policy: OutboxPolicyV1,
    minimal_casefile_retention_policy: CasefileRetentionPolicyV1,
    minimal_sn_linkage: ServiceNowLinkageContractV1,
    minimal_local_dev: LocalDevContractV1,
    minimal_topology_registry: TopologyRegistryLoaderRulesV1,
) -> None:
    contracts = [
        minimal_rulebook,
        minimal_peak_policy,
        minimal_prometheus_metrics,
        minimal_redis_ttl,
        minimal_outbox_policy,
        minimal_casefile_retention_policy,
        minimal_sn_linkage,
        minimal_local_dev,
        minimal_topology_registry,
    ]
    for contract in contracts:
        assert contract.schema_version == "v1"


# ── Semantic field tests ──────────────────────────────────────────────────────


def test_rulebook_caps_paging_denied_roles(minimal_rulebook: RulebookV1) -> None:
    assert "SOURCE_TOPIC" in minimal_rulebook.caps.paging_denied_topic_roles


def test_rulebook_policy_artifact_enforces_fr28_env_caps() -> None:
    policy_path = Path(__file__).resolve().parents[3] / "config/policies/rulebook-v1.yaml"
    policy = load_policy_yaml(policy_path, RulebookV1)

    assert set(policy.caps.max_action_by_env) >= {"local", "dev", "uat", "prod"}
    assert policy.caps.max_action_by_env["local"] == "OBSERVE"
    assert policy.caps.max_action_by_env["dev"] == "NOTIFY"
    assert policy.caps.max_action_by_env["uat"] == "TICKET"
    assert policy.caps.max_action_by_env["prod"] == "PAGE"
    if "stage" in policy.caps.max_action_by_env:
        assert policy.caps.max_action_by_env["stage"] == policy.caps.max_action_by_env["uat"]


def test_rulebook_policy_artifact_enforces_fr29_prod_tier_caps() -> None:
    policy_path = Path(__file__).resolve().parents[3] / "config/policies/rulebook-v1.yaml"
    policy = load_policy_yaml(policy_path, RulebookV1)

    assert policy.caps.max_action_by_tier_in_prod == {
        "TIER_0": "PAGE",
        "TIER_1": "TICKET",
        "TIER_2": "NOTIFY",
        "UNKNOWN": "NOTIFY",
    }


def test_rulebook_policy_artifact_ag4_reason_codes_are_explicit() -> None:
    policy_path = Path(__file__).resolve().parents[3] / "config/policies/rulebook-v1.yaml"
    policy = load_policy_yaml(policy_path, RulebookV1)

    ag4_gate = next(gate for gate in policy.gates if gate.id == "AG4")
    checks_by_id = {check.check_id: check for check in ag4_gate.checks}
    confidence_check_extra = checks_by_id["AG4_CONFIDENCE_MIN"].model_extra or {}
    sustained_check_extra = (
        checks_by_id["AG4_SUSTAINED_REQUIRED_FOR_HIGH_URGENCY"].model_extra or {}
    )

    assert confidence_check_extra.get("reason_code_on_fail") == "LOW_CONFIDENCE"
    assert sustained_check_extra.get("reason_code_on_fail") == "NOT_SUSTAINED"


def test_redis_ttl_prod_dedupe_accessible(minimal_redis_ttl: RedisTtlPolicyV1) -> None:
    assert minimal_redis_ttl.ttls_by_env["prod"].dedupe_seconds > 0


def test_redis_ttl_policy_artifact_enforces_fr33_per_action_ttls() -> None:
    policy_path = Path(__file__).resolve().parents[3] / "config/policies/redis-ttl-policy-v1.yaml"
    policy = load_policy_yaml(policy_path, RedisTtlPolicyV1)

    for env in ("local", "dev", "uat", "prod"):
        ttl_config = policy.ttls_by_env[env].dedupe_ttl_by_action
        assert ttl_config.page_seconds == 7200, f"{env}: PAGE TTL must be 7200s (FR33)"
        assert ttl_config.ticket_seconds == 14400, f"{env}: TICKET TTL must be 14400s (FR33)"
        assert ttl_config.notify_seconds == 3600, f"{env}: NOTIFY TTL must be 3600s (FR33)"


def test_ag5_dedupe_ttl_config_defaults_match_fr33_spec() -> None:
    config = AG5DedupeTtlConfig()
    assert config.page_seconds == 7200    # FR33: PAGE = 120 min
    assert config.ticket_seconds == 14400  # FR33: TICKET = 240 min
    assert config.notify_seconds == 3600   # FR33: NOTIFY = 60 min


def test_redis_ttl_by_env_has_dedupe_ttl_by_action_with_fr33_defaults(
    minimal_redis_ttl: RedisTtlPolicyV1,
) -> None:
    ttls = minimal_redis_ttl.ttls_by_env["prod"]
    assert ttls.dedupe_ttl_by_action.page_seconds == 7200
    assert ttls.dedupe_ttl_by_action.ticket_seconds == 14400
    assert ttls.dedupe_ttl_by_action.notify_seconds == 3600


def test_outbox_prod_retention(minimal_outbox_policy: OutboxPolicyV1) -> None:
    assert minimal_outbox_policy.retention_by_env["prod"].sent_retention_days == 14
    assert minimal_outbox_policy.retention_by_env["prod"].dead_retention_days == 90


def test_outbox_policy_default_monitoring_thresholds(minimal_outbox_policy: OutboxPolicyV1) -> None:
    pending_object = minimal_outbox_policy.state_age_thresholds.pending_object
    ready = minimal_outbox_policy.state_age_thresholds.ready
    retry = minimal_outbox_policy.state_age_thresholds.retry

    assert pending_object.warning_seconds == 300
    assert pending_object.critical_seconds == 900
    assert ready.warning_seconds == 120
    assert ready.critical_seconds == 600
    assert retry.warning_seconds is None
    assert retry.critical_seconds == 1800

    assert minimal_outbox_policy.dead_count_critical_threshold == {
        "local": 0,
        "dev": 0,
        "uat": 0,
        "prod": 0,
    }
    assert minimal_outbox_policy.delivery_slo.p95_target_seconds == 60
    assert minimal_outbox_policy.delivery_slo.p99_target_seconds == 300
    assert minimal_outbox_policy.delivery_slo.p99_critical_seconds == 600


def test_outbox_policy_artifact_enforces_fr52_fr53_thresholds() -> None:
    policy_path = Path(__file__).resolve().parents[3] / "config/policies/outbox-policy-v1.yaml"
    policy = load_policy_yaml(policy_path, OutboxPolicyV1)

    assert policy.state_age_thresholds.pending_object.warning_seconds == 300
    assert policy.state_age_thresholds.pending_object.critical_seconds == 900
    assert policy.state_age_thresholds.ready.warning_seconds == 120
    assert policy.state_age_thresholds.ready.critical_seconds == 600
    assert policy.state_age_thresholds.retry.warning_seconds is None
    assert policy.state_age_thresholds.retry.critical_seconds == 1800

    assert set(policy.dead_count_critical_threshold.keys()) == {"local", "dev", "uat", "prod"}
    assert policy.dead_count_critical_threshold == {
        "local": 0,
        "dev": 0,
        "uat": 0,
        "prod": 0,
    }

    assert policy.delivery_slo.p95_target_seconds == 60
    assert policy.delivery_slo.p99_target_seconds == 300
    assert policy.delivery_slo.p99_critical_seconds == 600


def test_casefile_retention_prod_months(
    minimal_casefile_retention_policy: CasefileRetentionPolicyV1,
) -> None:
    assert minimal_casefile_retention_policy.retention_by_env["prod"].retention_months == 25


def test_casefile_retention_policy_artifact_matches_expected_contract() -> None:
    policy_path = (
        Path(__file__).resolve().parents[3] / "config/policies/casefile-retention-policy-v1.yaml"
    )
    policy = load_policy_yaml(policy_path, CasefileRetentionPolicyV1)
    assert set(policy.retention_by_env.keys()) == {"local", "dev", "uat", "prod"}
    assert policy.retention_by_env["prod"].retention_months == 25


def test_sn_mi_creation_not_allowed(minimal_sn_linkage: ServiceNowLinkageContractV1) -> None:
    # FR67b: MI-1 posture — automated MI creation must never be allowed
    assert minimal_sn_linkage.mi_creation_allowed is False


def test_sn_linkage_policy_artifact_contains_tiered_correlation_defaults() -> None:
    policy_path = (
        Path(__file__).resolve().parents[3] / "config/policies/servicenow-linkage-contract-v1.yaml"
    )
    policy = load_policy_yaml(policy_path, ServiceNowLinkageContractV1)

    assert policy.incident_table == "incident"
    assert policy.tier1_correlation_fields == (
        "u_pagerduty_incident_id",
        "correlation_id",
        "u_correlation_id",
    )
    assert "short_description" in policy.tier2_text_fields
    assert "description" in policy.tier2_text_fields
    assert policy.tier2_include_work_notes is False
    assert policy.tier3_window_minutes == 120
    assert policy.live_timeout_seconds == 5.0
    assert policy.max_results_per_tier == 25


def test_prometheus_metrics_keys_accessible(
    minimal_prometheus_metrics: PrometheusMetricsContractV1,
) -> None:
    assert "consumer_group_lag" in minimal_prometheus_metrics.metrics
    metric = minimal_prometheus_metrics.metrics["consumer_group_lag"]
    assert metric.canonical == "kafka_consumergroup_group_lag"


def test_rulebook_model_validate_from_dict() -> None:
    data = {
        "rulebook_id": "rulebook.v1",
        "version": 1,
        "evaluation_interval_minutes": 5,
        "sustained_intervals_required": 5,
        "defaults": {
            "missing_series_policy": "UNKNOWN_NOT_ZERO",
            "required_evidence_policy": "PRESENT_ONLY",
            "missing_confidence_policy": "DOWNGRADE",
            "missing_sustained_policy": "DOWNGRADE",
        },
        "caps": {
            "max_action_by_env": {
                "local": "OBSERVE",
                "dev": "NOTIFY",
                "uat": "TICKET",
                "prod": "PAGE",
            },
            "max_action_by_tier_in_prod": {
                "TIER_0": "PAGE",
                "TIER_1": "TICKET",
                "TIER_2": "NOTIFY",
                "UNKNOWN": "NOTIFY",
            },
            "paging_denied_topic_roles": ["SOURCE_TOPIC"],
        },
        "gates": [
            {"id": gid, "name": gid, "intent": "Gate.", "effect": {}}
            for gid in ("AG0", "AG1", "AG2", "AG3", "AG4", "AG5", "AG6")
        ],
    }
    rulebook = RulebookV1.model_validate(data)
    assert rulebook.rulebook_id == "rulebook.v1"
    assert rulebook.evaluation_interval_minutes == 5
    assert len(rulebook.gates) == 7


def test_rulebook_caps_paging_denied_type(minimal_rulebook: RulebookV1) -> None:
    assert isinstance(minimal_rulebook.caps.paging_denied_topic_roles, tuple)


def test_gate_spec_applies_when_extra_field_round_trip() -> None:
    """GateSpec extra='allow' for applies_when — verify extra fields survive a JSON round-trip."""
    spec = GateSpec(
        id="AG2",
        name="Evidence sufficiency",
        intent="Downgrade on missing evidence.",
        effect=GateEffects(),
        checks=(),
        applies_when={
            "any": ["proposed_action in [PAGE, TICKET]", "diagnosis_confidence is UNKNOWN"]
        },
    )
    json_str = spec.model_dump_json()
    reconstructed = GateSpec.model_validate_json(json_str)
    assert spec == reconstructed
    assert reconstructed.model_extra.get("applies_when") == {
        "any": ["proposed_action in [PAGE, TICKET]", "diagnosis_confidence is UNKNOWN"]
    }


def test_gate_spec_applies_when_string_extra_field_round_trip() -> None:
    """GateSpec applies_when as plain string (e.g. 'always') also survives round-trip."""
    spec = GateSpec(
        id="AG0",
        name="Schema invariants",
        intent="Never page on malformed inputs.",
        effect=GateEffects(),
        checks=(),
        applies_when="always",
    )
    json_str = spec.model_dump_json()
    reconstructed = GateSpec.model_validate_json(json_str)
    assert spec == reconstructed
    assert reconstructed.model_extra.get("applies_when") == "always"
