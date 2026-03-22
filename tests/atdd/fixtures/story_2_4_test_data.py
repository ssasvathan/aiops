"""ATDD fixture builders for Story 2.4 dispatch integration coverage."""

from __future__ import annotations

from aiops_triage_pipeline.contracts.action_decision import ActionDecisionV1
from aiops_triage_pipeline.contracts.enums import Action
from aiops_triage_pipeline.denylist.loader import DenylistV1
from aiops_triage_pipeline.pipeline.stages.topology import TopologyRoutingContext


def build_dispatch_decision(*, action: Action = Action.NOTIFY) -> ActionDecisionV1:
    return ActionDecisionV1(
        final_action=action,
        env_cap_applied=False,
        gate_rule_ids=("AG0", "AG1", "AG2", "AG3", "AG4", "AG5", "AG6"),
        gate_reason_codes=("AG0_PASS", "AG1_PASS"),
        action_fingerprint="fp-story-2-4-001",
        postmortem_required=False,
        postmortem_reason_codes=(),
    )


def build_routing_context() -> TopologyRoutingContext:
    return TopologyRoutingContext(
        lookup_level="topic_owner",
        routing_key="OWN::Streaming::Payments::Topic",
        owning_team_id="team-payments",
        owning_team_name="Payments Engineering",
        support_channel="#payments-oncall",
    )


def build_strict_denylist() -> DenylistV1:
    return DenylistV1(
        denylist_version="story-2.4-red",
        denied_field_names=("case_id",),
        denied_value_patterns=(r"secret",),
    )
