"""Unit tests for Stage 7 dispatch — action routing to PagerDutyClient and SlackClient."""

from __future__ import annotations

from unittest.mock import MagicMock

from aiops_triage_pipeline.contracts.action_decision import ActionDecisionV1
from aiops_triage_pipeline.contracts.enums import Action
from aiops_triage_pipeline.denylist.loader import DenylistV1
from aiops_triage_pipeline.integrations.pagerduty import (
    PagerDutyClient,
    PagerDutyIntegrationMode,
)
from aiops_triage_pipeline.integrations.slack import SlackClient, SlackIntegrationMode
from aiops_triage_pipeline.pipeline.stages.dispatch import dispatch_action
from aiops_triage_pipeline.pipeline.stages.topology import TopologyRoutingContext

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_CASE_ID = "case-dispatch-test-001"
_FINGERPRINT = "fp-dispatch-test-xyz"
_TOPOLOGY_ROUTING_KEY = "OWN::Streaming::Payments::Topic"
_SUPPORT_CHANNEL = "#payments-oncall"


def _make_decision(
    final_action: Action,
    postmortem_required: bool = False,
    postmortem_reason_codes: tuple[str, ...] = (),
) -> ActionDecisionV1:
    return ActionDecisionV1(
        final_action=final_action,
        env_cap_applied=False,
        gate_rule_ids=("AG0", "AG1"),
        gate_reason_codes=("ENV_CAP_OK", "TIER_CAP_OK"),
        action_fingerprint=_FINGERPRINT,
        postmortem_required=postmortem_required,
        postmortem_reason_codes=postmortem_reason_codes,
    )


def _make_routing_context(support_channel: str | None = None) -> TopologyRoutingContext:
    return TopologyRoutingContext(
        lookup_level="topic_owner",
        routing_key=_TOPOLOGY_ROUTING_KEY,
        owning_team_id="team-payments",
        owning_team_name="Payments Engineering",
        support_channel=support_channel,
    )


def _make_mock_pd_client() -> MagicMock:
    """Create a mock PagerDutyClient with a controllable mode property."""
    mock = MagicMock(spec=PagerDutyClient)
    mock.mode = PagerDutyIntegrationMode.MOCK
    return mock


def _make_off_slack_client() -> SlackClient:
    """Real SlackClient in OFF mode — silent drop, no Slack side-effects in existing tests."""
    return SlackClient(mode=SlackIntegrationMode.OFF)


def _make_empty_denylist() -> DenylistV1:
    return DenylistV1(
        denylist_version="test-v0",
        denied_field_names=(),
        denied_value_patterns=(),
    )


_UNSET = object()  # Sentinel to distinguish "not provided" from explicit None


def _dispatch(
    *,
    case_id: str = _CASE_ID,
    decision: ActionDecisionV1,
    routing_context: TopologyRoutingContext | None | object = _UNSET,
    pd_client: PagerDutyClient | MagicMock | None = None,
    slack_client: SlackClient | MagicMock | None = None,
    denylist: DenylistV1 | None = None,
) -> None:
    """Helper to call dispatch_action with sensible test defaults.

    Uses a sentinel (_UNSET) for routing_context so callers can explicitly pass None
    to test the no-topology-context path.
    """
    resolved_routing_context: TopologyRoutingContext | None = (
        _make_routing_context() if routing_context is _UNSET else routing_context  # type: ignore[assignment]
    )
    dispatch_action(
        case_id=case_id,
        decision=decision,
        routing_context=resolved_routing_context,
        pd_client=pd_client if pd_client is not None else _make_mock_pd_client(),
        slack_client=slack_client if slack_client is not None else _make_off_slack_client(),
        denylist=denylist if denylist is not None else _make_empty_denylist(),
    )


# ---------------------------------------------------------------------------
# PAGE action → PD trigger called
# ---------------------------------------------------------------------------


def test_page_action_calls_send_page_trigger() -> None:
    """final_action=PAGE → pd_client.send_page_trigger called with correct args."""
    decision = _make_decision(Action.PAGE)
    routing_ctx = _make_routing_context()
    pd_client = _make_mock_pd_client()

    _dispatch(decision=decision, routing_context=routing_ctx, pd_client=pd_client)

    pd_client.send_page_trigger.assert_called_once()
    kwargs = pd_client.send_page_trigger.call_args.kwargs
    assert kwargs["case_id"] == _CASE_ID
    assert kwargs["action_fingerprint"] == _FINGERPRINT
    assert kwargs["routing_key"] == _TOPOLOGY_ROUTING_KEY


def test_page_action_uses_action_fingerprint_as_dedup_key() -> None:
    """final_action=PAGE → action_fingerprint and case_id are separate, distinct audit fields."""
    decision = _make_decision(Action.PAGE)
    pd_client = _make_mock_pd_client()

    _dispatch(decision=decision, routing_context=_make_routing_context(), pd_client=pd_client)

    kwargs = pd_client.send_page_trigger.call_args.kwargs
    assert kwargs["case_id"] == _CASE_ID
    assert kwargs["action_fingerprint"] == decision.action_fingerprint
    assert kwargs["case_id"] != kwargs["action_fingerprint"]


# ---------------------------------------------------------------------------
# Non-PAGE actions → PD adapter NOT called
# ---------------------------------------------------------------------------


def test_ticket_action_does_not_call_pd() -> None:
    """final_action=TICKET → PD adapter not called."""
    pd_client = _make_mock_pd_client()
    _dispatch(decision=_make_decision(Action.TICKET), pd_client=pd_client)
    pd_client.send_page_trigger.assert_not_called()


def test_notify_action_does_not_call_pd() -> None:
    """final_action=NOTIFY → PD adapter not called, Slack notify path called."""
    pd_client = _make_mock_pd_client()
    slack_client = MagicMock(spec=SlackClient)
    denylist = _make_empty_denylist()
    _dispatch(
        decision=_make_decision(Action.NOTIFY),
        pd_client=pd_client,
        slack_client=slack_client,
        denylist=denylist,
    )
    pd_client.send_page_trigger.assert_not_called()
    slack_client.send_notification.assert_called_once()
    kwargs = slack_client.send_notification.call_args.kwargs
    assert kwargs["case_id"] == _CASE_ID
    assert kwargs["action_fingerprint"] == _FINGERPRINT
    assert kwargs["routing_key"] == _TOPOLOGY_ROUTING_KEY
    assert kwargs["support_channel"] is None
    assert kwargs["reason_codes"] == ("ENV_CAP_OK", "TIER_CAP_OK")
    assert kwargs["denylist"] is denylist


def test_observe_action_does_not_call_pd() -> None:
    """final_action=OBSERVE → PD adapter not called."""
    pd_client = _make_mock_pd_client()
    _dispatch(decision=_make_decision(Action.OBSERVE), pd_client=pd_client)
    pd_client.send_page_trigger.assert_not_called()


# ---------------------------------------------------------------------------
# routing_context=None fallback
# ---------------------------------------------------------------------------


def test_page_action_with_no_routing_context_uses_unknown_fallback() -> None:
    """routing_context=None → dispatch still works; uses 'unknown' as routing_key."""
    decision = _make_decision(Action.PAGE)
    pd_client = _make_mock_pd_client()

    _dispatch(decision=decision, routing_context=None, pd_client=pd_client)

    pd_client.send_page_trigger.assert_called_once()
    kwargs = pd_client.send_page_trigger.call_args.kwargs
    assert kwargs["case_id"] == _CASE_ID
    assert kwargs["routing_key"] == "unknown"


def test_non_page_action_with_no_routing_context_does_not_call_pd() -> None:
    """routing_context=None + non-PAGE action → no PD trigger, no error."""
    pd_client = _make_mock_pd_client()
    _dispatch(decision=_make_decision(Action.OBSERVE), routing_context=None, pd_client=pd_client)
    pd_client.send_page_trigger.assert_not_called()


def test_notify_action_with_no_routing_context_uses_unknown_and_support_channel_none() -> None:
    """routing_context=None + NOTIFY → Slack notify uses unknown key and support_channel=None."""
    pd_client = _make_mock_pd_client()
    slack_client = MagicMock(spec=SlackClient)

    _dispatch(
        decision=_make_decision(Action.NOTIFY),
        routing_context=None,
        pd_client=pd_client,
        slack_client=slack_client,
    )

    pd_client.send_page_trigger.assert_not_called()
    slack_client.send_notification.assert_called_once()
    kwargs = slack_client.send_notification.call_args.kwargs
    assert kwargs["routing_key"] == "unknown"
    assert kwargs["support_channel"] is None


# ---------------------------------------------------------------------------
# Real PagerDutyClient integration (MOCK mode — no HTTP)
# ---------------------------------------------------------------------------


def test_page_action_real_mock_mode_client_increments_send_count() -> None:
    """PAGE + real PagerDutyClient in MOCK mode → mock_send_count == 1."""
    decision = _make_decision(Action.PAGE)
    real_client = PagerDutyClient(mode=PagerDutyIntegrationMode.MOCK, pd_routing_key="test-key")
    _dispatch(decision=decision, routing_context=_make_routing_context(), pd_client=real_client)
    assert real_client.mock_send_count == 1


def test_non_page_real_mock_mode_client_send_count_stays_zero() -> None:
    """TICKET + real PagerDutyClient in MOCK mode → mock_send_count == 0."""
    real_client = PagerDutyClient(mode=PagerDutyIntegrationMode.MOCK, pd_routing_key="test-key")
    _dispatch(
        decision=_make_decision(Action.TICKET),
        routing_context=_make_routing_context(),
        pd_client=real_client,
    )
    assert real_client.mock_send_count == 0


# ---------------------------------------------------------------------------
# Postmortem notification dispatch — AC1, AC4, AC7
# ---------------------------------------------------------------------------


def test_postmortem_required_true_calls_slack_send_postmortem_notification() -> None:
    """postmortem_required=True → slack_client.send_postmortem_notification called correctly."""
    decision = _make_decision(
        Action.NOTIFY,
        postmortem_required=True,
        postmortem_reason_codes=("PM_PEAK_SUSTAINED",),
    )
    routing_ctx = _make_routing_context(support_channel=_SUPPORT_CHANNEL)
    slack_client = MagicMock(spec=SlackClient)
    denylist = _make_empty_denylist()

    _dispatch(
        decision=decision,
        routing_context=routing_ctx,
        slack_client=slack_client,
        denylist=denylist,
    )

    slack_client.send_postmortem_notification.assert_called_once()
    kwargs = slack_client.send_postmortem_notification.call_args.kwargs
    assert kwargs["case_id"] == _CASE_ID
    assert kwargs["final_action"] == Action.NOTIFY.value
    assert kwargs["routing_key"] == _TOPOLOGY_ROUTING_KEY
    assert kwargs["support_channel"] == _SUPPORT_CHANNEL
    assert kwargs["postmortem_required"] is True
    assert kwargs["reason_codes"] == ("PM_PEAK_SUSTAINED",)
    assert kwargs["denylist"] is denylist


def test_postmortem_required_false_slack_not_called() -> None:
    """postmortem_required=False → Slack client NOT called."""
    decision = _make_decision(Action.NOTIFY, postmortem_required=False)
    slack_client = MagicMock(spec=SlackClient)

    _dispatch(decision=decision, slack_client=slack_client)

    slack_client.send_postmortem_notification.assert_not_called()


def test_page_with_postmortem_required_calls_both_pd_and_slack() -> None:
    """final_action=PAGE with postmortem_required=True → both PD trigger AND Slack dispatched."""
    decision = _make_decision(
        Action.PAGE,
        postmortem_required=True,
        postmortem_reason_codes=("PM_PEAK_SUSTAINED",),
    )
    pd_client = _make_mock_pd_client()
    slack_client = MagicMock(spec=SlackClient)

    _dispatch(
        decision=decision,
        routing_context=_make_routing_context(),
        pd_client=pd_client,
        slack_client=slack_client,
    )

    pd_client.send_page_trigger.assert_called_once()
    slack_client.send_postmortem_notification.assert_called_once()


def test_notify_with_postmortem_required_calls_slack_not_pd() -> None:
    """final_action=NOTIFY + postmortem_required=True → notify + postmortem Slack paths."""
    decision = _make_decision(
        Action.NOTIFY,
        postmortem_required=True,
        postmortem_reason_codes=("PM_PEAK_SUSTAINED",),
    )
    pd_client = _make_mock_pd_client()
    slack_client = MagicMock(spec=SlackClient)

    _dispatch(decision=decision, pd_client=pd_client, slack_client=slack_client)

    pd_client.send_page_trigger.assert_not_called()
    slack_client.send_notification.assert_called_once()
    slack_client.send_postmortem_notification.assert_called_once()


def test_routing_context_none_with_postmortem_required_passes_support_channel_none() -> None:
    """routing_context=None with postmortem_required=True → support_channel=None, no crash."""
    decision = _make_decision(
        Action.NOTIFY,
        postmortem_required=True,
        postmortem_reason_codes=("PM_PEAK_SUSTAINED",),
    )
    slack_client = MagicMock(spec=SlackClient)

    _dispatch(decision=decision, routing_context=None, slack_client=slack_client)

    slack_client.send_postmortem_notification.assert_called_once()
    kwargs = slack_client.send_postmortem_notification.call_args.kwargs
    assert kwargs["support_channel"] is None
