"""OutboxPolicyV1 — retention, monitoring, and SLO policy for outbox records."""

from typing import Literal

from pydantic import BaseModel, Field, model_validator

_REQUIRED_ENVS: frozenset[str] = frozenset({"local", "dev", "uat", "prod"})


class OutboxRetentionPolicy(BaseModel, frozen=True):
    sent_retention_days: int
    dead_retention_days: int
    max_retry_attempts: int = 3


class OutboxStateAgeThreshold(BaseModel, frozen=True):
    warning_seconds: float | None = Field(default=None, ge=0)
    critical_seconds: float = Field(ge=0)

    @model_validator(mode="after")
    def _validate_threshold_order(self) -> "OutboxStateAgeThreshold":
        if self.warning_seconds is not None and self.warning_seconds >= self.critical_seconds:
            raise ValueError("warning_seconds must be less than critical_seconds")
        return self


class OutboxStateAgeThresholds(BaseModel, frozen=True):
    pending_object: OutboxStateAgeThreshold = OutboxStateAgeThreshold(
        warning_seconds=300,
        critical_seconds=900,
    )
    ready: OutboxStateAgeThreshold = OutboxStateAgeThreshold(
        warning_seconds=120,
        critical_seconds=600,
    )
    retry: OutboxStateAgeThreshold = OutboxStateAgeThreshold(
        warning_seconds=None,
        critical_seconds=1800,
    )


class OutboxDeliverySLOThresholds(BaseModel, frozen=True):
    p95_target_seconds: float = Field(default=60, gt=0)
    p99_target_seconds: float = Field(default=300, gt=0)
    p99_critical_seconds: float = Field(default=600, gt=0)

    @model_validator(mode="after")
    def _validate_slo_order(self) -> "OutboxDeliverySLOThresholds":
        if self.p95_target_seconds > self.p99_target_seconds:
            raise ValueError("p95_target_seconds must be <= p99_target_seconds")
        if self.p99_target_seconds > self.p99_critical_seconds:
            raise ValueError("p99_target_seconds must be <= p99_critical_seconds")
        return self


def _default_dead_count_critical_threshold() -> dict[str, int]:
    return {
        "local": 1,
        "dev": 1,
        "uat": 1,
        "prod": 0,
    }


class OutboxPolicyV1(BaseModel, frozen=True):
    schema_version: Literal["v1"] = "v1"
    retention_by_env: dict[str, OutboxRetentionPolicy]
    state_age_thresholds: OutboxStateAgeThresholds = OutboxStateAgeThresholds()
    dead_count_critical_threshold: dict[str, int] = Field(
        default_factory=_default_dead_count_critical_threshold
    )
    delivery_slo: OutboxDeliverySLOThresholds = OutboxDeliverySLOThresholds()

    @model_validator(mode="after")
    def _require_all_envs(self) -> "OutboxPolicyV1":
        missing_retention = _REQUIRED_ENVS - self.retention_by_env.keys()
        if missing_retention:
            raise ValueError(
                "retention_by_env is missing required environments: "
                f"{sorted(missing_retention)}"
            )
        missing_dead_thresholds = _REQUIRED_ENVS - self.dead_count_critical_threshold.keys()
        if missing_dead_thresholds:
            raise ValueError(
                "dead_count_critical_threshold is missing required environments: "
                f"{sorted(missing_dead_thresholds)}"
            )
        for env, threshold in self.dead_count_critical_threshold.items():
            if threshold < 0:
                raise ValueError(
                    "dead_count_critical_threshold values must be >= 0 "
                    f"(invalid for env={env!r})"
                )
        return self
