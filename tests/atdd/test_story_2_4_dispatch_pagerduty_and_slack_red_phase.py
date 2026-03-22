"""ATDD red-phase acceptance tests for Story 2.4 dispatch integration safety."""

from __future__ import annotations

import json
from unittest.mock import patch

from aiops_triage_pipeline.contracts.enums import Action
from aiops_triage_pipeline.denylist.loader import DenylistV1
from aiops_triage_pipeline.integrations.pagerduty import PagerDutyClient, PagerDutyIntegrationMode
from aiops_triage_pipeline.integrations.slack import SlackClient
from aiops_triage_pipeline.pipeline.stages.dispatch import dispatch_action
from tests.atdd.fixtures.story_2_4_test_data import (
    build_dispatch_decision,
    build_routing_context,
    build_strict_denylist,
)

_URLOPEN_PD_PATH = "aiops_triage_pipeline.integrations.pagerduty.urllib.request.urlopen"


class _PagerDutyProbe:
    def __init__(self) -> None:
        self.mode = PagerDutyIntegrationMode.MOCK
        self.page_calls: list[dict[str, str]] = []

    def send_page_trigger(
        self,
        *,
        case_id: str,
        action_fingerprint: str,
        routing_key: str,
        summary: str,
        denylist: DenylistV1 | None = None,
    ) -> None:
        self.page_calls.append(
            {
                "case_id": case_id,
                "action_fingerprint": action_fingerprint,
                "routing_key": routing_key,
                "summary": summary,
                "denylist": denylist,
            }
        )


class _SlackNotifyProbe:
    def __init__(self) -> None:
        self.notify_calls: list[dict[str, object]] = []

    def send_notification(self, **kwargs: object) -> None:
        self.notify_calls.append(kwargs)

    def send_postmortem_notification(self, **kwargs: object) -> None:  # pragma: no cover
        raise AssertionError("postmortem path is out of scope for this ATDD check")


def test_p0_notify_action_dispatches_regular_slack_notification_with_denylist() -> None:
    """Given NOTIFY final action, dispatch should invoke Slack notify API with denylist context."""
    decision = build_dispatch_decision(action=Action.NOTIFY)
    routing_context = build_routing_context()
    pd_client = _PagerDutyProbe()
    slack_client = _SlackNotifyProbe()
    denylist = build_strict_denylist()

    dispatch_action(
        case_id="case-secret-2-4",
        decision=decision,
        routing_context=routing_context,
        pd_client=pd_client,
        slack_client=slack_client,
        denylist=denylist,
    )

    assert slack_client.notify_calls == [
        {
            "case_id": "case-secret-2-4",
            "action_fingerprint": decision.action_fingerprint,
            "routing_key": routing_context.routing_key,
            "support_channel": routing_context.support_channel,
            "reason_codes": decision.gate_reason_codes,
            "denylist": denylist,
        }
    ]


def test_p0_pagerduty_live_payload_is_denylist_sanitized_before_outbound_send() -> None:
    """Given denylisted secrets, PagerDuty outbound payload must not leak denied values."""
    client = PagerDutyClient(mode=PagerDutyIntegrationMode.LIVE, pd_routing_key="pd-key")

    captured_request_body: dict[str, object] = {}

    class _Response:
        def __enter__(self) -> "_Response":
            return self

        def __exit__(self, exc_type, exc, tb) -> bool:  # noqa: ANN001
            return False

        def read(self) -> bytes:
            return b'{"status":"success","dedup_key":"fp-story-2-4-001"}'

    def _capture_urlopen(req: object, timeout: int = 5) -> _Response:  # noqa: ARG001
        body = json.loads(req.data.decode())  # type: ignore[attr-defined]
        captured_request_body.update(body)
        return _Response()

    with patch(_URLOPEN_PD_PATH, side_effect=_capture_urlopen):
        client.send_page_trigger(
            case_id="case-secret-2-4",
            action_fingerprint="fp-story-2-4-001",
            routing_key="OWN::secret::routing",
            summary="secret token should be redacted",
            denylist=build_strict_denylist(),
        )

    outbound = json.dumps(captured_request_body)
    assert "secret" not in outbound


def test_p1_slack_client_exposes_regular_notify_api() -> None:
    """Slack integration should expose dedicated API for non-postmortem NOTIFY actions."""
    assert hasattr(SlackClient, "send_notification")
