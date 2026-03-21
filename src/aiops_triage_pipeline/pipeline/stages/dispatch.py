"""Stage 7: Action dispatch — routes finalized ActionDecisionV1 to integration adapters."""

from aiops_triage_pipeline.contracts.action_decision import ActionDecisionV1
from aiops_triage_pipeline.contracts.enums import Action
from aiops_triage_pipeline.denylist.loader import DenylistV1
from aiops_triage_pipeline.integrations.pagerduty import PagerDutyClient
from aiops_triage_pipeline.integrations.slack import SlackClient
from aiops_triage_pipeline.logging.setup import get_logger
from aiops_triage_pipeline.pipeline.stages.topology import TopologyRoutingContext


def dispatch_action(
    *,
    case_id: str,
    decision: ActionDecisionV1,
    routing_context: TopologyRoutingContext | None,
    pd_client: PagerDutyClient,
    slack_client: SlackClient,
    denylist: DenylistV1,
) -> None:
    """Dispatch the finalized action to the appropriate integration adapter.

    Stage 7 is the final stage in the hot-path pipeline:
        Evidence → Peak → Topology → CaseFile → Outbox → Gating → Dispatch

    Only PAGE actions invoke the PagerDuty adapter. All other actions (TICKET,
    NOTIFY, OBSERVE) are logged for audit completeness but do not trigger external
    calls from this stage.

    When postmortem_required=True on the decision, a postmortem obligation notification
    is dispatched via Slack (or structured log fallback) independently of the PAGE action
    (architecture decision 2B; FR44, FR45; NFR-R1).

    Args:
        case_id:         CaseFile identifier for audit traceability (NFR-S6).
        decision:        Final gated ActionDecisionV1 from Stage 6.
        routing_context: Topology routing metadata from Stage 3; may be None if
                         topology resolution was unsuccessful.
        pd_client:       PagerDutyClient configured with the active integration mode.
        slack_client:    SlackClient configured with the active integration mode.
        denylist:        Active exposure denylist for Slack payload sanitization.
    """
    logger = get_logger("pipeline.stages.dispatch")
    topology_routing_key = routing_context.routing_key if routing_context else "unknown"

    if decision.final_action == Action.PAGE:
        try:
            pd_client.send_page_trigger(
                case_id=case_id,
                action_fingerprint=decision.action_fingerprint,
                routing_key=topology_routing_key,
                summary=(
                    f"AIOps PAGE alert — fingerprint={decision.action_fingerprint} "
                    f"routing_key={topology_routing_key}"
                ),
            )
        except Exception as exc:
            logger.error(
                "action_dispatch_pd_failed",
                event_type="pipeline.stages.dispatch.pd_dispatch_failed",
                case_id=case_id,
                final_action=decision.final_action.value,
                action_fingerprint=decision.action_fingerprint,
                topology_routing_key=topology_routing_key,
                mode=pd_client.mode.value,
                error=str(exc),
            )
        else:
            logger.info(
                "action_dispatched",
                event_type="pipeline.stages.dispatch.action_dispatched",
                case_id=case_id,
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
            case_id=case_id,
            final_action=decision.final_action.value,
            action_fingerprint=decision.action_fingerprint,
            topology_routing_key=topology_routing_key,
            mode=pd_client.mode.value,
            outcome="no_pd_trigger",
        )

    # Postmortem obligation dispatch — orthogonal to PAGE/non-PAGE.
    # Only fires when AG6 set postmortem_required=True; never blocks pipeline (NFR-R1).
    if decision.postmortem_required:
        try:
            slack_client.send_postmortem_notification(
                case_id=case_id,
                final_action=decision.final_action.value,
                routing_key=topology_routing_key,
                support_channel=routing_context.support_channel if routing_context else None,
                postmortem_required=decision.postmortem_required,
                reason_codes=decision.postmortem_reason_codes,
                denylist=denylist,
            )
        except Exception as exc:
            logger.error(
                "action_dispatch_postmortem_failed",
                event_type="pipeline.stages.dispatch.postmortem_dispatch_failed",
                case_id=case_id,
                final_action=decision.final_action.value,
                action_fingerprint=decision.action_fingerprint,
                topology_routing_key=topology_routing_key,
                mode=slack_client.mode.value,
                error=str(exc),
            )
        else:
            logger.info(
                "action_dispatch_postmortem_sent",
                event_type="pipeline.stages.dispatch.postmortem_dispatched",
                case_id=case_id,
                final_action=decision.final_action.value,
                action_fingerprint=decision.action_fingerprint,
                topology_routing_key=topology_routing_key,
                mode=slack_client.mode.value,
            )
