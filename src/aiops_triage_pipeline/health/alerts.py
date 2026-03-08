"""Operational alert policy loading and deterministic alert evaluation."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from aiops_triage_pipeline.config.settings import load_policy_yaml
from aiops_triage_pipeline.contracts.operational_alert_policy import (
    AlertRuleDescriptor,
    OperationalAlertPolicyV1,
    RuleBySeverity,
    ThresholdBySeverity,
)

_DEFAULT_POLICY_PATH = (
    Path(__file__).resolve().parents[3] / "config/policies/operational-alert-policy-v1.yaml"
)
_SUPPORTED_ENVS = frozenset({"local", "dev", "uat", "prod"})


@dataclass(frozen=True)
class OperationalAlertEvaluation:
    """Normalized alert evaluation payload."""

    rule_id: str
    component: str
    severity: Literal["warning", "critical"]
    condition: str
    recommended_action: str
    observed_value: float | None = None
    threshold_value: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class OperationalAlertEvaluator:
    """Evaluate runtime signals against operational alert policy thresholds."""

    def __init__(self, *, policy: OperationalAlertPolicyV1, app_env: str) -> None:
        if app_env not in _SUPPORTED_ENVS:
            raise ValueError(f"Unsupported app_env for operational alerts: {app_env!r}")
        self._policy = policy
        self._app_env = app_env
        self._prometheus_outage_streak = 0
        self._llm_recent_failures: deque[bool] = deque(maxlen=policy.llm_error_rate.window_size)
        self._llm_last_alert_severity: Literal["warning", "critical"] | None = None

    @property
    def policy(self) -> OperationalAlertPolicyV1:
        return self._policy

    @property
    def app_env(self) -> str:
        return self._app_env

    def evaluate_outbox_state_age(
        self,
        *,
        state: str,
        actual_age_seconds: float,
        warning_threshold_seconds: float | None,
        critical_threshold_seconds: float,
    ) -> OperationalAlertEvaluation | None:
        state_key = state.upper()
        severity = self._resolve_severity(
            observed_value=actual_age_seconds,
            thresholds=ThresholdBySeverity(
                warning=warning_threshold_seconds,
                critical=critical_threshold_seconds,
            ),
        )
        if severity is None:
            return None
        rule_group = self._outbox_rule_group_for_state(state_key)
        rule = self._rule_for_severity(rule_group, severity)
        if rule is None:
            return None
        threshold = (
            critical_threshold_seconds if severity == "critical" else warning_threshold_seconds
        )
        return self._build_evaluation(
            rule=rule,
            severity=severity,
            observed_value=actual_age_seconds,
            threshold_value=threshold,
            state=state_key,
        )

    def evaluate_outbox_dead_count(
        self,
        *,
        dead_count: int,
        critical_threshold: int,
    ) -> OperationalAlertEvaluation | None:
        if dead_count <= critical_threshold:
            return None
        severity: Literal["warning", "critical"] = (
            "critical" if self._app_env == "prod" else "warning"
        )
        rule = self._rule_for_severity(self._policy.outbox.dead_count, severity)
        if rule is None:
            return None
        return self._build_evaluation(
            rule=rule,
            severity=severity,
            observed_value=float(dead_count),
            threshold_value=float(critical_threshold),
            state="DEAD",
        )

    def evaluate_redis_connection(self, *, healthy: bool) -> OperationalAlertEvaluation | None:
        if healthy:
            return None
        return self._build_evaluation(
            rule=self._policy.redis_connection_loss,
            severity="critical",
            observed_value=0.0,
            threshold_value=1.0,
        )

    def record_prometheus_unavailability(
        self, *, is_total_outage: bool
    ) -> OperationalAlertEvaluation | None:
        if not is_total_outage:
            self._prometheus_outage_streak = 0
            return None

        self._prometheus_outage_streak += 1
        activation_cycles = getattr(
            self._policy.prometheus_unavailability.activation_cycles_by_env,
            self._app_env,
        )
        if self._prometheus_outage_streak != activation_cycles:
            return None
        return self._build_evaluation(
            rule=self._policy.prometheus_unavailability.rule,
            severity="warning",
            observed_value=float(self._prometheus_outage_streak),
            threshold_value=float(activation_cycles),
        )

    def evaluate_scheduler_drift(self, *, drift_seconds: int) -> OperationalAlertEvaluation | None:
        thresholds = getattr(
            self._policy.scheduler_interval_drift_seconds.thresholds_by_env,
            self._app_env,
        )
        severity = self._resolve_severity(
            observed_value=float(drift_seconds),
            thresholds=thresholds,
        )
        if severity is None:
            return None
        rule = self._rule_for_severity(
            self._policy.scheduler_interval_drift_seconds.rules,
            severity,
        )
        if rule is None:
            return None
        return self._build_evaluation(
            rule=rule,
            severity=severity,
            observed_value=float(drift_seconds),
            threshold_value=thresholds.critical if severity == "critical" else thresholds.warning,
        )

    def evaluate_pipeline_stage_latency(
        self,
        *,
        seconds: float,
        stage: str,
    ) -> OperationalAlertEvaluation | None:
        thresholds = getattr(
            self._policy.pipeline_stage_latency_seconds.thresholds_by_env,
            self._app_env,
        )
        severity = self._resolve_severity(observed_value=seconds, thresholds=thresholds)
        if severity is None:
            return None
        rule = self._rule_for_severity(self._policy.pipeline_stage_latency_seconds.rules, severity)
        if rule is None:
            return None
        return self._build_evaluation(
            rule=rule,
            severity=severity,
            observed_value=seconds,
            threshold_value=thresholds.critical if severity == "critical" else thresholds.warning,
            stage=stage,
        )

    def record_llm_invocation_result(
        self,
        *,
        result: Literal["success", "fallback", "error"],
    ) -> OperationalAlertEvaluation | None:
        self._llm_recent_failures.append(result != "success")
        if len(self._llm_recent_failures) < self._policy.llm_error_rate.window_size:
            return None

        error_count = sum(1 for failed in self._llm_recent_failures if failed)
        error_rate = error_count / len(self._llm_recent_failures)
        thresholds = getattr(self._policy.llm_error_rate.thresholds_by_env, self._app_env)
        severity = self._resolve_severity(observed_value=error_rate, thresholds=thresholds)

        if severity is None:
            self._llm_last_alert_severity = None
            return None
        if self._llm_last_alert_severity == severity:
            return None
        self._llm_last_alert_severity = severity

        rule = self._rule_for_severity(self._policy.llm_error_rate.rules, severity)
        if rule is None:
            return None
        return self._build_evaluation(
            rule=rule,
            severity=severity,
            observed_value=error_rate,
            threshold_value=thresholds.critical if severity == "critical" else thresholds.warning,
            window_size=len(self._llm_recent_failures),
            error_count=error_count,
        )

    def _outbox_rule_group_for_state(self, state: str) -> RuleBySeverity:
        if state == "PENDING_OBJECT":
            return self._policy.outbox.pending_object_age
        if state == "READY":
            return self._policy.outbox.ready_age
        if state == "RETRY":
            return self._policy.outbox.retry_age
        raise ValueError(f"Unsupported outbox state for alert evaluation: {state!r}")

    @staticmethod
    def _rule_for_severity(
        rules: RuleBySeverity,
        severity: Literal["warning", "critical"],
    ) -> AlertRuleDescriptor | None:
        if severity == "warning":
            return rules.warning
        return rules.critical

    @staticmethod
    def _resolve_severity(
        *,
        observed_value: float,
        thresholds: ThresholdBySeverity,
    ) -> Literal["warning", "critical"] | None:
        if observed_value > thresholds.critical:
            return "critical"
        if thresholds.warning is not None and observed_value > thresholds.warning:
            return "warning"
        return None

    @staticmethod
    def _build_evaluation(
        *,
        rule: AlertRuleDescriptor,
        severity: Literal["warning", "critical"],
        observed_value: float | None = None,
        threshold_value: float | None = None,
        **metadata: Any,
    ) -> OperationalAlertEvaluation:
        return OperationalAlertEvaluation(
            rule_id=rule.rule_id,
            component=rule.component,
            severity=severity,
            condition=rule.condition,
            recommended_action=rule.recommended_action,
            observed_value=observed_value,
            threshold_value=threshold_value,
            metadata=metadata,
        )


def load_operational_alert_policy(
    path: Path = _DEFAULT_POLICY_PATH,
) -> OperationalAlertPolicyV1:
    """Load and validate the versioned operational alert policy artifact."""
    return load_policy_yaml(path, OperationalAlertPolicyV1)
