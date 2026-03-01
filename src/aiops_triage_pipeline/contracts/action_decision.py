"""ActionDecisionV1 — output of Rulebook gate evaluation (AG0–AG6)."""

from typing import Literal

from pydantic import BaseModel

from aiops_triage_pipeline.contracts.enums import Action


class ActionDecisionV1(BaseModel, frozen=True):
    schema_version: Literal["v1"] = "v1"
    final_action: Action  # Final gated action (monotonically reduced from proposed)
    env_cap_applied: bool  # True if environment cap reduced the action
    gate_rule_ids: tuple[str, ...]  # IDs of rules that evaluated (for audit)
    gate_reason_codes: tuple[str, ...]  # Reason codes from gate evaluation
    action_fingerprint: str  # Same fingerprint as GateInputV1 (for dedupe)
    postmortem_required: bool  # True if PM_PEAK_SUSTAINED predicate fired (AG6)
    postmortem_mode: str | None = None  # "SOFT" for Phase 1A when postmortem_required=True
    postmortem_reason_codes: tuple[str, ...] = ()  # Reason codes for postmortem trigger
