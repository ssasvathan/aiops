"""Unit tests for Stage 7 dispatch — action routing to PagerDutyClient."""

from __future__ import annotations

from unittest.mock import MagicMock

from aiops_triage_pipeline.contracts.action_decision import ActionDecisionV1
from aiops_triage_pipeline.contracts.enums import Action
from aiops_triage_pipeline.integrations.pagerduty import (
    PagerDutyClient,
    PagerDutyIntegrationMode,
)
from aiops_triage_pipeline.pipeline.stages.dispatch import dispatch_action
from aiops_triage_pipeline.pipeline.stages.topology import TopologyRoutingContext

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_FINGERPRINT = "fp-dispatch-test-xyz"
_TOPOLOGY_ROUTING_KEY = "OWN::Streaming::Payments::Topic"


def _make_decision(final_action: Action) -> ActionDecisionV1:
    return ActionDecisionV1(
        final_action=final_action,
        env_cap_applied=False,
        gate_rule_ids=("AG0", "AG1"),
        gate_reason_codes=("ENV_CAP_OK", "TIER_CAP_OK"),
        action_fingerprint=_FINGERPRINT,
        postmortem_required=False,
    )


def _make_routing_context() -> TopologyRoutingContext:
    return TopologyRoutingContext(
        lookup_level="topic_owner",
        routing_key=_TOPOLOGY_ROUTING_KEY,
        owning_team_id="team-payments",
        owning_team_name="Payments Engineering",
    )


def _make_mock_pd_client() -> MagicMock:
    """Create a mock PagerDutyClient with a controllable mode property."""
    mock = MagicMock(spec=PagerDutyClient)
    mock.mode = PagerDutyIntegrationMode.MOCK
    return mock


# ---------------------------------------------------------------------------
# PAGE action → PD trigger called
# ---------------------------------------------------------------------------


def test_page_action_calls_send_page_trigger() -> None:
    """final_action=PAGE → pd_client.send_page_trigger called with correct args."""
    decision = _make_decision(Action.PAGE)
    routing_ctx = _make_routing_context()
    pd_client = _make_mock_pd_client()

    dispatch_action(decision=decision, routing_context=routing_ctx, pd_client=pd_client)

    pd_client.send_page_trigger.assert_called_once()
    kwargs = pd_client.send_page_trigger.call_args.kwargs
    assert kwargs["action_fingerprint"] == _FINGERPRINT
    assert kwargs["routing_key"] == _TOPOLOGY_ROUTING_KEY


def test_page_action_uses_action_fingerprint_as_dedup_key() -> None:
    """final_action=PAGE → action_fingerprint passed as action_fingerprint kwarg."""
    decision = _make_decision(Action.PAGE)
    pd_client = _make_mock_pd_client()

    dispatch_action(decision=decision, routing_context=_make_routing_context(), pd_client=pd_client)

    kwargs = pd_client.send_page_trigger.call_args.kwargs
    assert kwargs["action_fingerprint"] == decision.action_fingerprint


# ---------------------------------------------------------------------------
# Non-PAGE actions → PD adapter NOT called
# ---------------------------------------------------------------------------


def test_ticket_action_does_not_call_pd() -> None:
    """final_action=TICKET → PD adapter not called."""
    pd_client = _make_mock_pd_client()
    dispatch_action(
        decision=_make_decision(Action.TICKET),
        routing_context=_make_routing_context(),
        pd_client=pd_client,
    )
    pd_client.send_page_trigger.assert_not_called()


def test_notify_action_does_not_call_pd() -> None:
    """final_action=NOTIFY → PD adapter not called."""
    pd_client = _make_mock_pd_client()
    dispatch_action(
        decision=_make_decision(Action.NOTIFY),
        routing_context=_make_routing_context(),
        pd_client=pd_client,
    )
    pd_client.send_page_trigger.assert_not_called()


def test_observe_action_does_not_call_pd() -> None:
    """final_action=OBSERVE → PD adapter not called."""
    pd_client = _make_mock_pd_client()
    dispatch_action(
        decision=_make_decision(Action.OBSERVE),
        routing_context=_make_routing_context(),
        pd_client=pd_client,
    )
    pd_client.send_page_trigger.assert_not_called()


# ---------------------------------------------------------------------------
# routing_context=None fallback
# ---------------------------------------------------------------------------


def test_page_action_with_no_routing_context_uses_unknown_fallback() -> None:
    """routing_context=None → dispatch still works; uses 'unknown' as routing_key."""
    decision = _make_decision(Action.PAGE)
    pd_client = _make_mock_pd_client()

    dispatch_action(decision=decision, routing_context=None, pd_client=pd_client)

    pd_client.send_page_trigger.assert_called_once()
    kwargs = pd_client.send_page_trigger.call_args.kwargs
    assert kwargs["routing_key"] == "unknown"


def test_non_page_action_with_no_routing_context_does_not_call_pd() -> None:
    """routing_context=None + non-PAGE action → no PD trigger, no error."""
    pd_client = _make_mock_pd_client()
    dispatch_action(
        decision=_make_decision(Action.OBSERVE),
        routing_context=None,
        pd_client=pd_client,
    )
    pd_client.send_page_trigger.assert_not_called()


# ---------------------------------------------------------------------------
# Real PagerDutyClient integration (MOCK mode — no HTTP)
# ---------------------------------------------------------------------------


def test_page_action_real_mock_mode_client_increments_send_count() -> None:
    """PAGE + real PagerDutyClient in MOCK mode → mock_send_count == 1."""
    decision = _make_decision(Action.PAGE)
    real_client = PagerDutyClient(
        mode=PagerDutyIntegrationMode.MOCK, pd_routing_key="test-key"
    )
    dispatch_action(
        decision=decision, routing_context=_make_routing_context(), pd_client=real_client
    )
    assert real_client.mock_send_count == 1


def test_non_page_real_mock_mode_client_send_count_stays_zero() -> None:
    """TICKET + real PagerDutyClient in MOCK mode → mock_send_count == 0."""
    real_client = PagerDutyClient(
        mode=PagerDutyIntegrationMode.MOCK, pd_routing_key="test-key"
    )
    dispatch_action(
        decision=_make_decision(Action.TICKET),
        routing_context=_make_routing_context(),
        pd_client=real_client,
    )
    assert real_client.mock_send_count == 0
