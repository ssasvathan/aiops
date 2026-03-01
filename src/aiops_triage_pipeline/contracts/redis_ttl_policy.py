"""RedisTtlPolicyV1 — environment-specific TTLs for Redis caching."""

from typing import Literal

from pydantic import BaseModel, model_validator

_REQUIRED_ENVS: frozenset[str] = frozenset({"local", "dev", "uat", "prod"})


class RedisTtlsByEnv(BaseModel, frozen=True):
    evidence_window_seconds: int
    peak_profile_seconds: int
    dedupe_seconds: int


class RedisTtlPolicyV1(BaseModel, frozen=True):
    schema_version: Literal["v1"] = "v1"
    ttls_by_env: dict[str, RedisTtlsByEnv]

    @model_validator(mode="after")
    def _require_all_envs(self) -> "RedisTtlPolicyV1":
        missing = _REQUIRED_ENVS - self.ttls_by_env.keys()
        if missing:
            raise ValueError(f"ttls_by_env is missing required environments: {sorted(missing)}")
        return self
