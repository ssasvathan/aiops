"""RulebookV1 — deterministic action guardrails (AG0–AG6)."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator

_REQUIRED_GATE_IDS: frozenset[str] = frozenset({"AG0", "AG1", "AG2", "AG3", "AG4", "AG5", "AG6"})


class RulebookDefaults(BaseModel, frozen=True):
    missing_series_policy: str
    required_evidence_policy: str
    missing_confidence_policy: str
    missing_sustained_policy: str


class RulebookCaps(BaseModel, frozen=True):
    max_action_by_env: dict[str, str]
    max_action_by_tier_in_prod: dict[str, str]
    paging_denied_topic_roles: tuple[str, ...]


class GateEffect(BaseModel, frozen=True):
    cap_action_to: str | None = None
    set_reason_codes: tuple[str, ...] = ()
    set_reason_text: tuple[str, ...] = ()
    confidence_floor: float | None = None
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
