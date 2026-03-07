"""RulebookV1 — deterministic action guardrails (AG0–AG6)."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator

from aiops_triage_pipeline.contracts.enums import Action

_REQUIRED_GATE_IDS: frozenset[str] = frozenset({"AG0", "AG1", "AG2", "AG3", "AG4", "AG5", "AG6"})
_REQUIRED_ENV_CAP_KEYS: frozenset[str] = frozenset({"local", "dev", "prod"})
_REQUIRED_PROD_TIER_CAP_KEYS: frozenset[str] = frozenset(
    {"TIER_0", "TIER_1", "TIER_2", "UNKNOWN"}
)


class RulebookDefaults(BaseModel, frozen=True):
    missing_series_policy: str
    required_evidence_policy: str
    missing_confidence_policy: str
    missing_sustained_policy: str


class RulebookCaps(BaseModel, frozen=True):
    max_action_by_env: dict[str, str]
    max_action_by_tier_in_prod: dict[str, str]
    paging_denied_topic_roles: tuple[str, ...]

    @field_validator("max_action_by_env")
    @classmethod
    def _validate_max_action_by_env(cls, env_caps: dict[str, str]) -> dict[str, str]:
        missing = _REQUIRED_ENV_CAP_KEYS - set(env_caps)
        if missing:
            raise ValueError(
                "max_action_by_env is missing required env keys: "
                f"{sorted(missing)}"
            )
        if "uat" not in env_caps and "stage" not in env_caps:
            raise ValueError(
                "max_action_by_env must define either 'uat' (canonical) or "
                "'stage' (legacy alias)"
            )
        for env_key, action_value in env_caps.items():
            _validate_action_policy_value(
                action_value,
                context=f"max_action_by_env[{env_key!r}]",
            )
        return env_caps

    @field_validator("max_action_by_tier_in_prod")
    @classmethod
    def _validate_max_action_by_tier_in_prod(
        cls, tier_caps: dict[str, str]
    ) -> dict[str, str]:
        missing = _REQUIRED_PROD_TIER_CAP_KEYS - set(tier_caps)
        if missing:
            raise ValueError(
                "max_action_by_tier_in_prod is missing required tier keys: "
                f"{sorted(missing)}"
            )
        for tier_key, action_value in tier_caps.items():
            _validate_action_policy_value(
                action_value,
                context=f"max_action_by_tier_in_prod[{tier_key!r}]",
            )
        return tier_caps


class GateEffect(BaseModel, frozen=True):
    cap_action_to: str | None = None
    set_reason_codes: tuple[str, ...] = ()
    set_reason_text: tuple[str, ...] = ()
    confidence_floor: float | None = None  # reserved; no-op at runtime — NOT the LLM confidence input
    force_postmortem_mode: str | None = None
    set_postmortem_required: bool | None = None
    set_postmortem_reason_codes: tuple[str, ...] = ()


class GateEffects(BaseModel, frozen=True):
    on_fail: GateEffect | None = None
    on_cap_applied: GateEffect | None = None
    on_duplicate: GateEffect | None = None
    on_store_error: GateEffect | None = None
    on_pass: GateEffect | None = None


class GateCheck(BaseModel):
    model_config = ConfigDict(frozen=True, extra="allow")
    check_id: str
    type: str


class GateSpec(BaseModel):
    model_config = ConfigDict(frozen=True, extra="allow")
    id: str
    name: str
    intent: str
    effect: GateEffects
    checks: tuple[GateCheck, ...] = ()


class RulebookV1(BaseModel, frozen=True):
    schema_version: Literal["v1"] = "v1"
    rulebook_id: str
    version: int
    evaluation_interval_minutes: int
    sustained_intervals_required: int
    defaults: RulebookDefaults
    caps: RulebookCaps
    gates: tuple[GateSpec, ...]

    @field_validator("gates")
    @classmethod
    def _require_all_gate_ids(cls, gates: tuple[GateSpec, ...]) -> tuple[GateSpec, ...]:
        found = {gate.id for gate in gates}
        missing = _REQUIRED_GATE_IDS - found
        if missing:
            raise ValueError(f"gates is missing required gate IDs: {sorted(missing)}")
        return gates


def _validate_action_policy_value(value: str, *, context: str) -> None:
    try:
        Action(value)
    except ValueError as exc:
        raise ValueError(f"Invalid action value {value!r} in {context}") from exc
