"""Slack integration for operational degraded-mode event notifications."""

import json
import urllib.request
from enum import Enum

from aiops_triage_pipeline.logging.setup import get_logger
from aiops_triage_pipeline.models.events import DegradedModeEvent


class SlackIntegrationMode(str, Enum):
    """Slack notification mode (mirrors LocalDev integration mode pattern).

    OFF  — No Slack activity; events are silently dropped.
    LOG  — Log the event only; no HTTP call is made.
    MOCK — Log the event, increment mock_send_count, and return; no HTTP call.
    LIVE — Log the event and POST to the configured webhook URL.
    """

    OFF = "OFF"
    LOG = "LOG"
    MOCK = "MOCK"
    LIVE = "LIVE"


class SlackClient:
    """Slack webhook client for degraded-mode operational notifications.

    All modes emit a structured log entry first (log fallback per FR51 AC6).
    HTTP calls only occur in LIVE mode.

    Args:
        mode:        Integration mode controlling notification behavior.
        webhook_url: Slack incoming-webhook URL required for LIVE mode.
    """

    def __init__(
        self,
        mode: SlackIntegrationMode = SlackIntegrationMode.OFF,
        webhook_url: str | None = None,
    ) -> None:
        self._mode = mode
        self._webhook_url = webhook_url
        self._mock_send_count: int = 0

    @property
    def mode(self) -> SlackIntegrationMode:
        return self._mode

    @property
    def mock_send_count(self) -> int:
        """Number of events dispatched in MOCK mode (simulating successful sends)."""
        return self._mock_send_count

    def send_degraded_mode_event(self, event: DegradedModeEvent) -> None:
        """Dispatch a DegradedModeEvent according to the configured integration mode.

        In OFF mode, the event is silently dropped with no log entry.
        In LOG and MOCK modes, a structured log entry is emitted; no HTTP call is made.
        In LIVE mode, a structured log entry is emitted and HTTP delivery is attempted.
        """
        if self._mode == SlackIntegrationMode.OFF:
            return

        logger = get_logger("integrations.slack")
        logger.warning(
            "degraded_mode_slack_dispatch",
            event_type="DegradedModeEvent",
            slack_mode=self._mode.value,
            affected_scope=event.affected_scope,
            reason=event.reason,
            capped_action_level=event.capped_action_level,
            estimated_impact_window=event.estimated_impact_window,
            timestamp=event.timestamp.isoformat(),
        )

        if self._mode == SlackIntegrationMode.LOG:
            return

        if self._mode == SlackIntegrationMode.MOCK:
            self._mock_send_count += 1
            return

        # LIVE mode — attempt webhook delivery
        self._send_live(event, logger)

    def _send_live(self, event: DegradedModeEvent, logger: object) -> None:
        if not self._webhook_url:
            get_logger("integrations.slack").warning(
                "degraded_mode_slack_no_webhook",
                event_type="integrations.slack.no_webhook",
                affected_scope=event.affected_scope,
            )
            return

        payload = {
            "text": (
                f":rotating_light: *Degraded Mode Alert* — `{event.affected_scope}`\n"
                f"Reason: {event.reason}\n"
                f"Capped action level: `{event.capped_action_level}`\n"
                f"Estimated impact: {event.estimated_impact_window or 'unknown'}"
            )
        }
        req = urllib.request.Request(
            self._webhook_url,
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=5):
                pass
        except Exception as exc:
            get_logger("integrations.slack").warning(
                "degraded_mode_slack_send_failed",
                event_type="integrations.slack.send_error",
                error=str(exc),
                affected_scope=event.affected_scope,
            )
