"""Operational alerting policy contract."""

from typing import Literal

from pydantic import BaseModel, Field, model_validator


class AlertRuleDescriptor(BaseModel, frozen=True):
    """Reviewable operational alert rule metadata."""

    rule_id: str = Field(pattern=r"^ALERT_[A-Z0-9_]+$")
    component: str = Field(min_length=1)
    severity: Literal["warning", "critical"]
    condition: str = Field(min_length=1)
    recommended_action: str = Field(min_length=1)


class RuleBySeverity(BaseModel, frozen=True):
    """Rule metadata split by warning/critical severities."""

    warning: AlertRuleDescriptor | None = None
    critical: AlertRuleDescriptor

    @model_validator(mode="after")
    def _validate_severity_labels(self) -> "RuleBySeverity":
        if self.warning is not None and self.warning.severity != "warning":
            raise ValueError("warning rule severity must be 'warning'")
        if self.critical.severity != "critical":
            raise ValueError("critical rule severity must be 'critical'")
        return self


class ThresholdBySeverity(BaseModel, frozen=True):
    """Numeric thresholds for warning/critical alerts."""

    warning: float | None = Field(default=None, ge=0)
    critical: float = Field(ge=0)

    @model_validator(mode="after")
    def _validate_order(self) -> "ThresholdBySeverity":
        if self.warning is not None and self.warning >= self.critical:
            raise ValueError("warning must be less than critical")
        return self


class ThresholdsByEnv(BaseModel, frozen=True):
    """Per-environment numeric thresholds."""

    local: ThresholdBySeverity
    dev: ThresholdBySeverity
    uat: ThresholdBySeverity
    prod: ThresholdBySeverity


class ActivationCyclesByEnv(BaseModel, frozen=True):
    """Per-environment activation windows for outage alerts."""

    local: int = Field(ge=1)
    dev: int = Field(ge=1)
    uat: int = Field(ge=1)
    prod: int = Field(ge=1)


class OutboxAlertRules(BaseModel, frozen=True):
    """Outbox rule metadata referencing outbox-policy thresholds."""

    source_policy_ref: Literal["outbox-policy-v1"] = "outbox-policy-v1"
    pending_object_age: RuleBySeverity
    ready_age: RuleBySeverity
    retry_age: RuleBySeverity
    dead_count: RuleBySeverity


class PrometheusUnavailabilityAlertRule(BaseModel, frozen=True):
    """Prometheus total outage alert definition."""

    rule: AlertRuleDescriptor
    activation_cycles_by_env: ActivationCyclesByEnv


class ThresholdedAlertRule(BaseModel, frozen=True):
    """Alert definition with thresholds and severity-specific rule metadata."""

    thresholds_by_env: ThresholdsByEnv
    rules: RuleBySeverity


class LlmErrorRateAlertRule(ThresholdedAlertRule):
    """LLM error-rate spike alert configuration."""

    window_size: int = Field(ge=1)


class OperationalAlertPolicyV1(BaseModel, frozen=True):
    """Top-level operational alert policy contract."""

    schema_version: Literal["v1"] = "v1"
    policy_id: Literal["operational-alert-policy-v1"] = "operational-alert-policy-v1"

    outbox: OutboxAlertRules
    redis_connection_loss: AlertRuleDescriptor
    prometheus_unavailability: PrometheusUnavailabilityAlertRule
    llm_error_rate: LlmErrorRateAlertRule
    sn_correlation_fallback_rate: ThresholdedAlertRule
    scheduler_interval_drift_seconds: ThresholdedAlertRule
    pipeline_stage_latency_seconds: ThresholdedAlertRule

    @model_validator(mode="after")
    def _validate_unique_rule_ids(self) -> "OperationalAlertPolicyV1":
        rule_ids: list[str] = []
        rule_ids.extend(
            [
                self.outbox.pending_object_age.warning.rule_id
                if self.outbox.pending_object_age.warning is not None
                else "",
                self.outbox.pending_object_age.critical.rule_id,
                self.outbox.ready_age.warning.rule_id
                if self.outbox.ready_age.warning is not None
                else "",
                self.outbox.ready_age.critical.rule_id,
                self.outbox.retry_age.warning.rule_id
                if self.outbox.retry_age.warning is not None
                else "",
                self.outbox.retry_age.critical.rule_id,
                self.outbox.dead_count.warning.rule_id
                if self.outbox.dead_count.warning is not None
                else "",
                self.outbox.dead_count.critical.rule_id,
                self.redis_connection_loss.rule_id,
                self.prometheus_unavailability.rule.rule_id,
                self.llm_error_rate.rules.warning.rule_id
                if self.llm_error_rate.rules.warning is not None
                else "",
                self.llm_error_rate.rules.critical.rule_id,
                self.sn_correlation_fallback_rate.rules.warning.rule_id
                if self.sn_correlation_fallback_rate.rules.warning is not None
                else "",
                self.sn_correlation_fallback_rate.rules.critical.rule_id,
                self.scheduler_interval_drift_seconds.rules.warning.rule_id
                if self.scheduler_interval_drift_seconds.rules.warning is not None
                else "",
                self.scheduler_interval_drift_seconds.rules.critical.rule_id,
                self.pipeline_stage_latency_seconds.rules.warning.rule_id
                if self.pipeline_stage_latency_seconds.rules.warning is not None
                else "",
                self.pipeline_stage_latency_seconds.rules.critical.rule_id,
            ]
        )
        cleaned_rule_ids = [rule_id for rule_id in rule_ids if rule_id]
        if len(cleaned_rule_ids) != len(set(cleaned_rule_ids)):
            raise ValueError("rule_id values must be unique within operational alert policy")
        return self
