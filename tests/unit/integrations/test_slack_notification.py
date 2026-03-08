"""Unit tests for SlackClient.send_postmortem_notification — OFF/LOG/MOCK/LIVE mode coverage."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import structlog.testing

from aiops_triage_pipeline.denylist.loader import DenylistV1
from aiops_triage_pipeline.integrations.slack import SlackClient, SlackIntegrationMode
from aiops_triage_pipeline.models.events import NotificationEvent

# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

_CASE_ID = "case-pm-test-001"
_FINAL_ACTION = "PAGE"
_ROUTING_KEY = "OWN::Streaming::Payments::Topic"
_SUPPORT_CHANNEL = "#payments-oncall"
_REASON_CODES: tuple[str, ...] = ("PM_PEAK_SUSTAINED",)

_URLOPEN_PATH = "aiops_triage_pipeline.integrations.slack.urllib.request.urlopen"
_WEBHOOK_URL = "https://hooks.slack.com/services/TEST/HOOK/URL"


def _make_empty_denylist() -> DenylistV1:
    return DenylistV1(
        denylist_version="test-v0",
        denied_field_names=(),
        denied_value_patterns=(),
    )


def _make_client(
    mode: SlackIntegrationMode = SlackIntegrationMode.OFF,
    webhook_url: str | None = _WEBHOOK_URL,
) -> SlackClient:
    return SlackClient(mode=mode, webhook_url=webhook_url)


def _notify(client: SlackClient, denylist: DenylistV1 | None = None) -> None:
    client.send_postmortem_notification(
        case_id=_CASE_ID,
        final_action=_FINAL_ACTION,
        routing_key=_ROUTING_KEY,
        support_channel=_SUPPORT_CHANNEL,
        postmortem_required=True,
        reason_codes=_REASON_CODES,
        denylist=denylist or _make_empty_denylist(),
    )


def _make_live_response() -> MagicMock:
    mock_resp = MagicMock()
    mock_resp.read.return_value = b"ok"
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)
    return mock_resp


# ---------------------------------------------------------------------------
# OFF mode
# ---------------------------------------------------------------------------


def test_off_mode_silent_drop_no_log_no_http() -> None:
    """OFF mode: silent drop — no log entries, no HTTP call, mock_send_count=0."""
    client = _make_client(mode=SlackIntegrationMode.OFF)
    with structlog.testing.capture_logs() as cap_logs:
        with patch(_URLOPEN_PATH) as mock_urlopen:
            _notify(client)
            mock_urlopen.assert_not_called()
    assert client.mock_send_count == 0
    assert cap_logs == [], f"Expected no log entries in OFF mode, got: {cap_logs}"


def test_off_mode_postmortem_required_false_still_silently_drops() -> None:
    """OFF mode: even when postmortem_required=False in payload fields, still silent drop."""
    client = _make_client(mode=SlackIntegrationMode.OFF)
    with structlog.testing.capture_logs() as cap_logs:
        with patch(_URLOPEN_PATH) as mock_urlopen:
            client.send_postmortem_notification(
                case_id=_CASE_ID,
                final_action=_FINAL_ACTION,
                routing_key=_ROUTING_KEY,
                support_channel=_SUPPORT_CHANNEL,
                postmortem_required=False,
                reason_codes=_REASON_CODES,
                denylist=_make_empty_denylist(),
            )
            mock_urlopen.assert_not_called()
    assert cap_logs == []


# ---------------------------------------------------------------------------
# LOG mode
# ---------------------------------------------------------------------------


def test_log_mode_emits_structured_log_no_http() -> None:
    """LOG mode: structured log 'postmortem_notification_dispatch' emitted, no HTTP call."""
    client = _make_client(mode=SlackIntegrationMode.LOG)
    with structlog.testing.capture_logs() as cap_logs:
        with patch(_URLOPEN_PATH) as mock_urlopen:
            _notify(client)
            mock_urlopen.assert_not_called()
    assert client.mock_send_count == 0
    dispatch_entries = [e for e in cap_logs if e.get("event") == "postmortem_notification_dispatch"]
    assert dispatch_entries, f"Expected postmortem_notification_dispatch log; got: {cap_logs}"


def test_log_mode_log_contains_all_six_fields() -> None:
    """LOG mode: log entry contains all six AC-required fields."""
    client = _make_client(mode=SlackIntegrationMode.LOG)
    with structlog.testing.capture_logs() as cap_logs:
        _notify(client)
    entry = next(e for e in cap_logs if e.get("event") == "postmortem_notification_dispatch")
    assert entry.get("case_id") == _CASE_ID
    assert entry.get("final_action") == _FINAL_ACTION
    assert entry.get("routing_key") == _ROUTING_KEY
    assert entry.get("support_channel") == _SUPPORT_CHANNEL
    assert entry.get("postmortem_required") is True
    assert entry.get("reason_codes") == list(_REASON_CODES)
    assert entry.get("slack_mode") == SlackIntegrationMode.LOG.value


# ---------------------------------------------------------------------------
# MOCK mode
# ---------------------------------------------------------------------------


def test_mock_mode_emits_log_and_increments_send_count() -> None:
    """MOCK mode: structured log emitted, mock_send_count incremented to 1, no HTTP call."""
    client = _make_client(mode=SlackIntegrationMode.MOCK)
    with structlog.testing.capture_logs() as cap_logs:
        with patch(_URLOPEN_PATH) as mock_urlopen:
            _notify(client)
            mock_urlopen.assert_not_called()
    assert client.mock_send_count == 1
    dispatch_entries = [e for e in cap_logs if e.get("event") == "postmortem_notification_dispatch"]
    assert dispatch_entries, f"Expected postmortem_notification_dispatch log; got: {cap_logs}"


# ---------------------------------------------------------------------------
# LIVE mode — happy path
# ---------------------------------------------------------------------------


def test_live_mode_posts_http_and_emits_log() -> None:
    """LIVE mode (mocked urllib): HTTP POST sent, log emitted, mock_send_count stays 0."""
    client = _make_client(mode=SlackIntegrationMode.LIVE)
    with structlog.testing.capture_logs() as cap_logs:
        with patch(_URLOPEN_PATH, return_value=_make_live_response()) as mock_urlopen:
            _notify(client)
    assert mock_urlopen.called
    assert client.mock_send_count == 0
    dispatch_entries = [e for e in cap_logs if e.get("event") == "postmortem_notification_dispatch"]
    assert dispatch_entries, f"Expected postmortem_notification_dispatch log; got: {cap_logs}"


def test_live_mode_posts_to_configured_webhook_url() -> None:
    """LIVE mode: HTTP POST sent to the configured webhook URL."""
    client = _make_client(mode=SlackIntegrationMode.LIVE, webhook_url=_WEBHOOK_URL)
    with structlog.testing.capture_logs():
        with patch(_URLOPEN_PATH, return_value=_make_live_response()) as mock_urlopen:
            _notify(client)
    req = mock_urlopen.call_args[0][0]
    assert req.full_url == _WEBHOOK_URL
    assert req.method == "POST"


def test_live_mode_payload_contains_sanitized_fields() -> None:
    """LIVE mode: webhook body is JSON with 'text' key containing sanitized fields."""
    client = _make_client(mode=SlackIntegrationMode.LIVE, webhook_url=_WEBHOOK_URL)
    with structlog.testing.capture_logs():
        with patch(_URLOPEN_PATH, return_value=_make_live_response()) as mock_urlopen:
            _notify(client)
    req = mock_urlopen.call_args[0][0]
    body = json.loads(req.data.decode())
    assert "text" in body
    assert _CASE_ID in body["text"]
    assert _FINAL_ACTION in body["text"]


# ---------------------------------------------------------------------------
# LIVE mode — missing webhook
# ---------------------------------------------------------------------------


def test_live_mode_no_webhook_logs_warning_no_http_no_crash() -> None:
    """LIVE mode with webhook_url=None: warning 'postmortem_notification_no_webhook' logged,
    no HTTP call, no exception raised."""
    client = _make_client(mode=SlackIntegrationMode.LIVE, webhook_url=None)
    with structlog.testing.capture_logs() as cap_logs:
        with patch(_URLOPEN_PATH) as mock_urlopen:
            _notify(client)  # Must not raise
            mock_urlopen.assert_not_called()
    warning_entries = [
        e for e in cap_logs if e.get("event") == "postmortem_notification_no_webhook"
    ]
    assert warning_entries, f"Expected postmortem_notification_no_webhook warning; got: {cap_logs}"


# ---------------------------------------------------------------------------
# LIVE mode — HTTP error handling
# ---------------------------------------------------------------------------


def test_live_mode_http_error_is_caught_logged_not_propagated() -> None:
    """LIVE mode HTTP error: exception caught, warning logged, does not propagate."""
    client = _make_client(mode=SlackIntegrationMode.LIVE)
    with structlog.testing.capture_logs() as cap_logs:
        with patch(_URLOPEN_PATH, side_effect=OSError("connection refused")):
            _notify(client)  # Must not raise
    error_entries = [
        e for e in cap_logs if e.get("event") == "postmortem_notification_send_failed"
    ]
    assert error_entries, f"Expected postmortem_notification_send_failed warning; got: {cap_logs}"
    assert error_entries[0].get("log_level") == "warning"


# ---------------------------------------------------------------------------
# reason_codes serialization
# ---------------------------------------------------------------------------


def test_reason_codes_appear_as_list_not_tuple_in_log() -> None:
    """reason_codes must be serialized as list (not tuple) in log output (JSON compatibility)."""
    client = _make_client(mode=SlackIntegrationMode.LOG)
    with structlog.testing.capture_logs() as cap_logs:
        _notify(client)
    entry = next(e for e in cap_logs if e.get("event") == "postmortem_notification_dispatch")
    reason_codes_value = entry.get("reason_codes")
    assert isinstance(reason_codes_value, list), (
        f"Expected reason_codes to be list, got {type(reason_codes_value)}"
    )
    assert reason_codes_value == list(_REASON_CODES)


# ---------------------------------------------------------------------------
# Denylist enforcement
# ---------------------------------------------------------------------------


def test_denylist_field_name_denied_field_absent_from_log() -> None:
    """Denylist field name denial: denied field absent from log event fields."""
    denylist = DenylistV1(
        denylist_version="test-deny-field",
        denied_field_names=("routing_key",),
        denied_value_patterns=(),
    )
    client = _make_client(mode=SlackIntegrationMode.LOG)
    with structlog.testing.capture_logs() as cap_logs:
        _notify(client, denylist=denylist)
    entry = next(e for e in cap_logs if e.get("event") == "postmortem_notification_dispatch")
    assert "routing_key" not in entry, (
        f"Expected 'routing_key' to be absent from log after denylist; got entry: {entry}"
    )


def test_denylist_value_pattern_denied_field_absent_from_log() -> None:
    """Denylist value pattern denial: field with matching value absent from log event fields."""
    denylist = DenylistV1(
        denylist_version="test-deny-value",
        denied_field_names=(),
        denied_value_patterns=(r"OWN::Streaming",),  # matches _ROUTING_KEY
    )
    client = _make_client(mode=SlackIntegrationMode.LOG)
    with structlog.testing.capture_logs() as cap_logs:
        _notify(client, denylist=denylist)
    entry = next(e for e in cap_logs if e.get("event") == "postmortem_notification_dispatch")
    assert "routing_key" not in entry, (
        f"Expected 'routing_key' to be absent from log due to value pattern; got entry: {entry}"
    )


# ---------------------------------------------------------------------------
# NotificationEvent schema contract
# ---------------------------------------------------------------------------


def test_notification_event_model_fields_match_log_output() -> None:
    """NotificationEvent schema can be instantiated from actual log output fields.

    Ensures the model definition stays in sync with what send_postmortem_notification
    actually emits — catching any future field-name drift between model and log.
    """
    client = _make_client(mode=SlackIntegrationMode.LOG)
    with structlog.testing.capture_logs() as cap_logs:
        _notify(client)
    entry = next(e for e in cap_logs if e.get("event") == "postmortem_notification_dispatch")
    event = NotificationEvent(
        case_id=entry["case_id"],
        final_action=entry["final_action"],
        routing_key=entry["routing_key"],
        support_channel=entry.get("support_channel"),
        postmortem_required=entry["postmortem_required"],
        reason_codes=tuple(entry["reason_codes"]),
    )
    assert event.event_type == "NotificationEvent"
    assert event.case_id == _CASE_ID
    assert event.final_action == _FINAL_ACTION
    assert event.routing_key == _ROUTING_KEY


# ---------------------------------------------------------------------------
# Denylist enforcement — LIVE mode webhook payload (AC2)
# ---------------------------------------------------------------------------


def test_live_mode_denylist_field_denied_absent_from_webhook_payload() -> None:
    """LIVE mode: denied field is redacted in webhook body text (AC2 on Slack payload)."""
    denylist = DenylistV1(
        denylist_version="test-deny-field-live",
        denied_field_names=("case_id",),
        denied_value_patterns=(),
    )
    client = _make_client(mode=SlackIntegrationMode.LIVE, webhook_url=_WEBHOOK_URL)
    with structlog.testing.capture_logs():
        with patch(_URLOPEN_PATH, return_value=_make_live_response()) as mock_urlopen:
            _notify(client, denylist=denylist)
    req = mock_urlopen.call_args[0][0]
    body = json.loads(req.data.decode())
    assert _CASE_ID not in body["text"], (
        f"Expected denied case_id to be absent from webhook text; got: {body['text']}"
    )
    assert "[redacted]" in body["text"]
