"""Unit tests for operational alert policy contract and artifact loading."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from aiops_triage_pipeline.config.settings import load_policy_yaml
from aiops_triage_pipeline.contracts.operational_alert_policy import (
    OperationalAlertPolicyV1,
    ThresholdBySeverity,
)


def test_operational_alert_policy_artifact_loads_and_has_required_env_coverage() -> None:
    policy_path = (
        Path(__file__).resolve().parents[3]
        / "config/policies/operational-alert-policy-v1.yaml"
    )
    policy = load_policy_yaml(policy_path, OperationalAlertPolicyV1)

    assert policy.schema_version == "v1"
    assert policy.policy_id == "operational-alert-policy-v1"

    assert policy.prometheus_unavailability.activation_cycles_by_env.prod >= 1

    for thresholds_by_env in (
        policy.llm_error_rate.thresholds_by_env,
        policy.scheduler_interval_drift_seconds.thresholds_by_env,
        policy.pipeline_stage_latency_seconds.thresholds_by_env,
    ):
        assert set(thresholds_by_env.model_dump().keys()) == {
            "local",
            "dev",
            "uat",
            "prod",
        }


def test_threshold_by_severity_rejects_warning_ge_critical() -> None:
    with pytest.raises(ValidationError):
        ThresholdBySeverity(warning=10, critical=10)


def test_operational_alert_policy_requires_non_empty_rule_metadata() -> None:
    with pytest.raises(ValidationError):
        OperationalAlertPolicyV1.model_validate(
            {
                "schema_version": "v1",
                "policy_id": "operational-alert-policy-v1",
                "outbox": {
                    "source_policy_ref": "outbox-policy-v1",
                    "pending_object_age": {
                        "warning": {
                            "rule_id": "ALERT_OUTBOX_PENDING_OBJECT_AGE_WARNING",
                            "component": "outbox",
                            "severity": "warning",
                            "condition": "pending_object_age_seconds > threshold",
                            "recommended_action": "triage backlog",
                        },
                        "critical": {
                            "rule_id": "ALERT_OUTBOX_PENDING_OBJECT_AGE_CRITICAL",
                            "component": "outbox",
                            "severity": "critical",
                            "condition": "pending_object_age_seconds > threshold",
                            "recommended_action": "page on-call",
                        },
                    },
                    "ready_age": {
                        "warning": {
                            "rule_id": "ALERT_OUTBOX_READY_AGE_WARNING",
                            "component": "outbox",
                            "severity": "warning",
                            "condition": "ready_age_seconds > threshold",
                            "recommended_action": "triage backlog",
                        },
                        "critical": {
                            "rule_id": "ALERT_OUTBOX_READY_AGE_CRITICAL",
                            "component": "outbox",
                            "severity": "critical",
                            "condition": "ready_age_seconds > threshold",
                            "recommended_action": "page on-call",
                        },
                    },
                    "retry_age": {
                        "critical": {
                            "rule_id": "ALERT_OUTBOX_RETRY_AGE_CRITICAL",
                            "component": "outbox",
                            "severity": "critical",
                            "condition": "retry_age_seconds > threshold",
                            "recommended_action": "investigate retry loop",
                        }
                    },
                    "dead_count": {
                        "warning": {
                            "rule_id": "ALERT_OUTBOX_DEAD_COUNT_WARNING",
                            "component": "outbox",
                            "severity": "warning",
                            "condition": "dead_count > threshold",
                            "recommended_action": "investigate dead records",
                        },
                        "critical": {
                            "rule_id": "ALERT_OUTBOX_DEAD_COUNT_CRITICAL",
                            "component": "outbox",
                            "severity": "critical",
                            "condition": "dead_count > threshold",
                            "recommended_action": "page on-call",
                        },
                    },
                },
                "redis_connection_loss": {
                    "rule_id": "ALERT_REDIS_CONNECTION_LOSS",
                    "component": "redis",
                    "severity": "critical",
                    "condition": "redis_connection_status == 0",
                    "recommended_action": "",
                },
                "prometheus_unavailability": {
                    "rule": {
                        "rule_id": "ALERT_PROMETHEUS_UNAVAILABLE",
                        "component": "prometheus",
                        "severity": "warning",
                        "condition": "telemetry_degraded_active == true",
                        "recommended_action": "investigate prometheus connectivity",
                    },
                    "activation_cycles_by_env": {
                        "local": 1,
                        "dev": 1,
                        "uat": 1,
                        "prod": 1,
                    },
                },
                "llm_error_rate": {
                    "window_size": 20,
                    "thresholds_by_env": {
                        "local": {"warning": 0.25, "critical": 0.5},
                        "dev": {"warning": 0.2, "critical": 0.4},
                        "uat": {"warning": 0.15, "critical": 0.3},
                        "prod": {"warning": 0.1, "critical": 0.2},
                    },
                    "rules": {
                        "warning": {
                            "rule_id": "ALERT_LLM_ERROR_RATE_SPIKE_WARNING",
                            "component": "llm",
                            "severity": "warning",
                            "condition": "llm_error_rate > warning_threshold",
                            "recommended_action": "investigate llm failures",
                        },
                        "critical": {
                            "rule_id": "ALERT_LLM_ERROR_RATE_SPIKE_CRITICAL",
                            "component": "llm",
                            "severity": "critical",
                            "condition": "llm_error_rate > critical_threshold",
                            "recommended_action": "engage incident response",
                        },
                    },
                },
                "scheduler_interval_drift_seconds": {
                    "thresholds_by_env": {
                        "local": {"warning": 45, "critical": 90},
                        "dev": {"warning": 40, "critical": 75},
                        "uat": {"warning": 30, "critical": 60},
                        "prod": {"warning": 20, "critical": 45},
                    },
                    "rules": {
                        "warning": {
                            "rule_id": "ALERT_SCHEDULER_INTERVAL_DRIFT_WARNING",
                            "component": "scheduler",
                            "severity": "warning",
                            "condition": "scheduler_drift_seconds > warning_threshold",
                            "recommended_action": "inspect scheduler load",
                        },
                        "critical": {
                            "rule_id": "ALERT_SCHEDULER_INTERVAL_DRIFT_CRITICAL",
                            "component": "scheduler",
                            "severity": "critical",
                            "condition": "scheduler_drift_seconds > critical_threshold",
                            "recommended_action": "page platform on-call",
                        },
                    },
                },
                "pipeline_stage_latency_seconds": {
                    "thresholds_by_env": {
                        "local": {"warning": 2, "critical": 5},
                        "dev": {"warning": 1.5, "critical": 4},
                        "uat": {"warning": 1.0, "critical": 3},
                        "prod": {"warning": 0.75, "critical": 2},
                    },
                    "rules": {
                        "warning": {
                            "rule_id": "ALERT_PIPELINE_STAGE_LATENCY_WARNING",
                            "component": "pipeline",
                            "severity": "warning",
                            "condition": "pipeline_stage_latency_seconds > warning_threshold",
                            "recommended_action": "inspect stage latency",
                        },
                        "critical": {
                            "rule_id": "ALERT_PIPELINE_STAGE_LATENCY_CRITICAL",
                            "component": "pipeline",
                            "severity": "critical",
                            "condition": "pipeline_stage_latency_seconds > critical_threshold",
                            "recommended_action": "engage incident response",
                        },
                    },
                },
            }
        )
