"""CasefileRetentionPolicyV1 — retention policy for casefile lifecycle by environment."""

from typing import Literal

from pydantic import BaseModel, Field, model_validator

_REQUIRED_ENVS: frozenset[str] = frozenset({"local", "dev", "uat", "prod"})


class CasefileRetentionPolicy(BaseModel, frozen=True):
    retention_months: int = Field(ge=1)


class CasefileRetentionPolicyV1(BaseModel, frozen=True):
    schema_version: Literal["v1"] = "v1"
    retention_by_env: dict[str, CasefileRetentionPolicy]

    @model_validator(mode="after")
    def _require_all_envs(self) -> "CasefileRetentionPolicyV1":
        missing = _REQUIRED_ENVS - self.retention_by_env.keys()
        if missing:
            raise ValueError(
                f"retention_by_env is missing required environments: {sorted(missing)}"
            )
        return self
