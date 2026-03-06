"""RedisTtlPolicyV1 — environment-specific TTLs for Redis caching."""

from typing import Literal

from pydantic import BaseModel, field_validator, model_validator

from aiops_triage_pipeline.contracts.enums import Action

_REQUIRED_ENVS: frozenset[str] = frozenset({"local", "dev", "uat", "prod"})
_REQUIRED_AG5_ACTION_KEYS: frozenset[str] = frozenset({"PAGE", "TICKET", "NOTIFY"})


class AG5DedupeTtlConfig(BaseModel, frozen=True):
    """Per-action deduplication TTLs for AG5 storm control (FR33).

    Defaults match FR33 exactly:
      PAGE   = 120 min (7200 s)
      TICKET = 240 min (14400 s)
      NOTIFY =  60 min (3600 s)
    """

    page_seconds: int = 7200
    ticket_seconds: int = 14400
    notify_seconds: int = 3600

    @field_validator("page_seconds", "ticket_seconds", "notify_seconds")
    @classmethod
    def _require_positive(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("AG5 dedupe TTL seconds must be positive")
        return v

    def ttl_for_action(self, action: Action) -> int:
        """Return dedupe TTL in seconds for the given action."""
        if action == Action.PAGE:
            return self.page_seconds
        if action == Action.TICKET:
            return self.ticket_seconds
        return self.notify_seconds


class RedisTtlsByEnv(BaseModel, frozen=True):
    evidence_window_seconds: int
    peak_profile_seconds: int
    dedupe_seconds: int
    dedupe_ttl_by_action: AG5DedupeTtlConfig = AG5DedupeTtlConfig()


class RedisTtlPolicyV1(BaseModel, frozen=True):
    schema_version: Literal["v1"] = "v1"
    ttls_by_env: dict[str, RedisTtlsByEnv]

    @model_validator(mode="after")
    def _require_all_envs(self) -> "RedisTtlPolicyV1":
        missing = _REQUIRED_ENVS - self.ttls_by_env.keys()
        if missing:
            raise ValueError(f"ttls_by_env is missing required environments: {sorted(missing)}")
        return self
