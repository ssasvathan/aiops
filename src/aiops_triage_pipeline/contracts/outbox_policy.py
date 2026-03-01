"""OutboxPolicyV1 — retention policy for outbox records by state and environment."""

from typing import Literal

from pydantic import BaseModel, model_validator

_REQUIRED_ENVS: frozenset[str] = frozenset({"local", "dev", "uat", "prod"})


class OutboxRetentionPolicy(BaseModel, frozen=True):
    sent_retention_days: int
    dead_retention_days: int
    max_retry_attempts: int = 3


class OutboxPolicyV1(BaseModel, frozen=True):
    schema_version: Literal["v1"] = "v1"
    retention_by_env: dict[str, OutboxRetentionPolicy]

    @model_validator(mode="after")
    def _require_all_envs(self) -> "OutboxPolicyV1":
        missing = _REQUIRED_ENVS - self.retention_by_env.keys()
        if missing:
            raise ValueError(
                f"retention_by_env is missing required environments: {sorted(missing)}"
            )
        return self
