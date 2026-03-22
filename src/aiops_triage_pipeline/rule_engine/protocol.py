"""Protocols and typed results for isolated AG0-AG3 rule-engine execution."""

from dataclasses import dataclass
from typing import Protocol

from aiops_triage_pipeline.contracts.enums import Action
from aiops_triage_pipeline.contracts.gate_input import GateInputV1
from aiops_triage_pipeline.contracts.rulebook import GateCheck, RulebookV1

EARLY_GATE_ORDER: tuple[str, ...] = ("AG0", "AG1", "AG2", "AG3")


class RuleEngineStartupError(ValueError):
    """Typed startup failure for rule-engine configuration errors."""


class UnknownCheckTypeStartupError(RuleEngineStartupError):
    """Raised when a configured check.type has no registered handler."""

    def __init__(self, *, gate_id: str, check_id: str, check_type: str) -> None:
        super().__init__(
            "Unsupported rule-engine check type "
            f"{check_type!r} in gate {gate_id!r} (check_id={check_id!r})"
        )
        self.gate_id = gate_id
        self.check_id = check_id
        self.check_type = check_type


class RuleEngineSafetyError(RuntimeError):
    """Raised when post-condition safety assertions fail."""


@dataclass(frozen=True)
class CheckResult:
    """Result returned by a check handler execution."""

    passed: bool
    next_action: Action | None = None
    env_cap_applied: bool = False


@dataclass(frozen=True)
class EarlyGateEvaluation:
    """Aggregate output from AG0-AG3 isolated evaluation."""

    current_action: Action
    input_valid: bool
    env_cap_applied: bool
    gate_reason_codes: tuple[str, ...]


class GateCheckHandler(Protocol):
    """Protocol for check-type handlers in the isolated rule engine."""

    def __call__(
        self,
        *,
        gate_input: GateInputV1,
        rulebook: RulebookV1,
        check: GateCheck,
        current_action: Action,
    ) -> CheckResult:
        ...
