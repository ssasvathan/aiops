"""Stage 7: Action dispatch — routes finalized ActionDecisionV1 to integration adapters."""

from aiops_triage_pipeline.contracts.action_decision import ActionDecisionV1
from aiops_triage_pipeline.contracts.enums import Action
from aiops_triage_pipeline.integrations.pagerduty import PagerDutyClient
from aiops_triage_pipeline.logging.setup import get_logger
from aiops_triage_pipeline.pipeline.stages.topology import TopologyRoutingContext


def dispatch_action(
    *,
    decision: ActionDecisionV1,
    routing_context: TopologyRoutingContext | None,
    pd_client: PagerDutyClient,
) -> None:
    """Dispatch the finalized action to the appropriate integration adapter.

    Stage 7 is the final stage in the hot-path pipeline:
        Evidence → Peak → Topology → CaseFile → Outbox → Gating → Dispatch

    Only PAGE actions invoke the PagerDuty adapter. All other actions (TICKET,
    NOTIFY, OBSERVE) are logged for audit completeness but do not trigger external
    calls from this stage.

    Args:
        decision:        Final gated ActionDecisionV1 from Stage 6.
        routing_context: Topology routing metadata from Stage 3; may be None if
                         topology resolution was unsuccessful.
        pd_client:       PagerDutyClient configured with the active integration mode.
    """
    logger = get_logger("pipeline.stages.dispatch")
    topology_routing_key = routing_context.routing_key if routing_context else "unknown"

    if decision.final_action == Action.PAGE:
        pd_client.send_page_trigger(
            case_id=decision.action_fingerprint,
            action_fingerprint=decision.action_fingerprint,
            routing_key=topology_routing_key,
            summary=(
                f"AIOps PAGE alert — fingerprint={decision.action_fingerprint} "
                f"routing_key={topology_routing_key}"
            ),
        )
        logger.info(
            "action_dispatched",
            event_type="pipeline.stages.dispatch.action_dispatched",
            final_action=decision.final_action.value,
            action_fingerprint=decision.action_fingerprint,
            topology_routing_key=topology_routing_key,
            mode=pd_client.mode.value,
            outcome="pd_trigger_sent",
        )
    else:
        # Non-PAGE actions: log for audit completeness; no external call at this stage.
        logger.info(
            "action_dispatched",
            event_type="pipeline.stages.dispatch.action_dispatched",
            final_action=decision.final_action.value,
            action_fingerprint=decision.action_fingerprint,
            topology_routing_key=topology_routing_key,
            outcome="no_pd_trigger",
        )
