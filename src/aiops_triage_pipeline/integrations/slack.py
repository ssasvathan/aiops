"""Slack integration for operational degraded-mode event notifications."""

import json
import urllib.request
from enum import Enum
from typing import Any

from aiops_triage_pipeline.denylist.enforcement import apply_denylist
from aiops_triage_pipeline.denylist.loader import DenylistV1
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

    def send_postmortem_notification(
        self,
        *,
        case_id: str,
        final_action: str,
        routing_key: str,
        support_channel: str | None,
        postmortem_required: bool,
        reason_codes: tuple[str, ...],
        denylist: DenylistV1,
    ) -> None:
        """Dispatch a postmortem obligation notification per SOFT enforcement (FR44, FR45).

        Applies denylist sanitization before any output (architecture decision 2B).
        In OFF mode, the notification is silently dropped with no log entry.
        In LOG and MOCK modes, a structured log entry is emitted; no HTTP call is made.
        In LIVE mode, a structured log entry is emitted and HTTP delivery is attempted.
        Slack unavailability never blocks pipeline processing (NFR-R1).

        Args:
            case_id:              CaseFile identifier for audit traceability.
            final_action:         The finalized action string (e.g., "PAGE", "NOTIFY").
            routing_key:          Topology ownership routing key.
            support_channel:      Team support channel; may be None.
            postmortem_required:  Always True when called (guard is in dispatch_action).
            reason_codes:         Postmortem trigger reason codes.
            denylist:             Active exposure denylist for payload sanitization.
        """
        if self._mode == SlackIntegrationMode.OFF:
            return

        logger = get_logger("integrations.slack")

        raw_fields: dict[str, Any] = {
            "case_id": case_id,
            "final_action": final_action,
            "routing_key": routing_key,
            "support_channel": support_channel,
            "postmortem_required": postmortem_required,
            "reason_codes": list(reason_codes),  # serialize tuple → list for JSON
        }
        sanitized = apply_denylist(raw_fields, denylist)

        logger.info(
            "postmortem_notification_dispatch",
            slack_mode=self._mode.value,
            **sanitized,
        )

        if self._mode == SlackIntegrationMode.LOG:
            return

        if self._mode == SlackIntegrationMode.MOCK:
            self._mock_send_count += 1
            return

        # LIVE mode — attempt webhook delivery
        if not self._webhook_url:
            logger.warning(
                "postmortem_notification_no_webhook",
                slack_mode=self._mode.value,
            )
            return

        payload = {
            "text": (
                f":memo: *Postmortem Obligation \u2014 SOFT Enforcement*\n"
                f"Case: `{sanitized.get('case_id', '[redacted]')}`\n"
                f"Action: `{sanitized.get('final_action', '[redacted]')}`\n"
                f"Routing: `{sanitized.get('routing_key', '[redacted]')}`\n"
                f"Support Channel: {sanitized.get('support_channel') or 'N/A'}\n"
                f"Reason Codes: {sanitized.get('reason_codes', [])}"
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
            logger.warning(
                "postmortem_notification_send_failed",
                slack_mode=self._mode.value,
                error=str(exc),
            )

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
