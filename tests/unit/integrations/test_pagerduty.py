"""Unit tests for PagerDutyClient — OFF/LOG/MOCK/LIVE mode coverage."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import structlog.testing

from aiops_triage_pipeline.integrations.pagerduty import (
    PagerDutyClient,
    PagerDutyIntegrationMode,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_CASE_ID = "case-abc-123"
_FINGERPRINT = "fp-stable-xyz"
_ROUTING_KEY = "OWN::Streaming::Payments::Topic"
_SUMMARY = "AIOps PAGE alert — test"
_PD_KEY = "pd-service-key-test"

_URLOPEN_PATH = "aiops_triage_pipeline.integrations.pagerduty.urllib.request.urlopen"


def _make_client(
    mode: PagerDutyIntegrationMode = PagerDutyIntegrationMode.OFF,
    pd_routing_key: str | None = _PD_KEY,
) -> PagerDutyClient:
    return PagerDutyClient(mode=mode, pd_routing_key=pd_routing_key)


def _trigger(client: PagerDutyClient) -> None:
    client.send_page_trigger(
        case_id=_CASE_ID,
        action_fingerprint=_FINGERPRINT,
        routing_key=_ROUTING_KEY,
        summary=_SUMMARY,
    )


# ---------------------------------------------------------------------------
# OFF mode
# ---------------------------------------------------------------------------


def test_off_mode_produces_no_log_and_no_http() -> None:
    """OFF mode: send_page_trigger silently drops — no log entries, no HTTP call."""
    client = _make_client(mode=PagerDutyIntegrationMode.OFF)
    with structlog.testing.capture_logs() as cap_logs:
        with patch(_URLOPEN_PATH) as mock_urlopen:
            _trigger(client)
            mock_urlopen.assert_not_called()
    assert client.mock_send_count == 0
    assert cap_logs == [], f"Expected no log entries in OFF mode, got: {cap_logs}"


# ---------------------------------------------------------------------------
# LOG mode
# ---------------------------------------------------------------------------


def test_log_mode_emits_structured_log_no_http() -> None:
    """LOG mode: structured log emitted, no HTTP call, mock_send_count stays 0."""
    client = _make_client(mode=PagerDutyIntegrationMode.LOG)
    with structlog.testing.capture_logs() as cap_logs:
        with patch(_URLOPEN_PATH) as mock_urlopen:
            _trigger(client)
            mock_urlopen.assert_not_called()
    assert client.mock_send_count == 0
    assert len(cap_logs) >= 1, f"Expected at least one log entry in LOG mode, got: {cap_logs}"


def test_log_mode_log_contains_case_id_and_fingerprint() -> None:
    """LOG mode: log entry contains case_id and action_fingerprint."""
    client = _make_client(mode=PagerDutyIntegrationMode.LOG)
    with structlog.testing.capture_logs() as cap_logs:
        _trigger(client)
    entry = cap_logs[0]
    assert entry.get("case_id") == _CASE_ID
    assert entry.get("action_fingerprint") == _FINGERPRINT


# ---------------------------------------------------------------------------
# MOCK mode
# ---------------------------------------------------------------------------


def test_mock_mode_increments_send_count() -> None:
    """MOCK mode: mock_send_count incremented, no HTTP call."""
    client = _make_client(mode=PagerDutyIntegrationMode.MOCK)
    with structlog.testing.capture_logs():
        with patch(_URLOPEN_PATH) as mock_urlopen:
            _trigger(client)
            mock_urlopen.assert_not_called()
    assert client.mock_send_count == 1


def test_mock_mode_accumulates_multiple_sends() -> None:
    """MOCK mode: each call increments mock_send_count independently."""
    client = _make_client(mode=PagerDutyIntegrationMode.MOCK)
    _trigger(client)
    _trigger(client)
    assert client.mock_send_count == 2


def test_mock_mode_emits_log() -> None:
    """MOCK mode: structured log entry is emitted."""
    client = _make_client(mode=PagerDutyIntegrationMode.MOCK)
    with structlog.testing.capture_logs() as cap_logs:
        _trigger(client)
    assert cap_logs, "Expected at least one log record in MOCK mode"


# ---------------------------------------------------------------------------
# LIVE mode — happy path
# ---------------------------------------------------------------------------


def _make_live_response(dedup_key: str = _FINGERPRINT) -> MagicMock:
    """Create a mock urllib response returning a PD 202 body."""
    resp_body = json.dumps(
        {"status": "success", "message": "Event processed", "dedup_key": dedup_key}
    ).encode()
    mock_resp = MagicMock()
    mock_resp.read.return_value = resp_body
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)
    return mock_resp


def test_live_mode_posts_to_correct_url() -> None:
    """LIVE mode: HTTP POST sent to PD Events V2 endpoint."""
    client = _make_client(mode=PagerDutyIntegrationMode.LIVE)
    with structlog.testing.capture_logs():
        with patch(_URLOPEN_PATH, return_value=_make_live_response()) as mock_urlopen:
            _trigger(client)
    assert mock_urlopen.called
    req = mock_urlopen.call_args[0][0]
    assert req.full_url == "https://events.pagerduty.com/v2/enqueue"
    assert req.method == "POST"


def test_live_mode_payload_contains_dedup_key_as_action_fingerprint() -> None:
    """LIVE mode: payload dedup_key equals action_fingerprint (stable pd_incident_id)."""
    client = _make_client(mode=PagerDutyIntegrationMode.LIVE)
    with structlog.testing.capture_logs():
        with patch(_URLOPEN_PATH, return_value=_make_live_response()) as mock_urlopen:
            _trigger(client)
    req = mock_urlopen.call_args[0][0]
    body: dict = json.loads(req.data.decode())
    assert body["dedup_key"] == _FINGERPRINT


def test_live_mode_payload_structure() -> None:
    """LIVE mode: payload has correct routing_key, event_action, and nested payload."""
    client = _make_client(mode=PagerDutyIntegrationMode.LIVE, pd_routing_key=_PD_KEY)
    with structlog.testing.capture_logs():
        with patch(_URLOPEN_PATH, return_value=_make_live_response()) as mock_urlopen:
            _trigger(client)
    req = mock_urlopen.call_args[0][0]
    body: dict = json.loads(req.data.decode())
    assert body["routing_key"] == _PD_KEY
    assert body["event_action"] == "trigger"
    assert body["payload"]["severity"] == "critical"
    assert body["payload"]["source"] == "aiops-triage-pipeline"
    assert body["payload"]["custom_details"]["case_id"] == _CASE_ID
    assert body["payload"]["custom_details"]["topology_routing_key"] == _ROUTING_KEY
    assert body["payload"]["custom_details"]["action_fingerprint"] == _FINGERPRINT


def test_live_mode_emits_log() -> None:
    """LIVE mode: API-call result log emitted with outcome, mode, and action (AC6)."""
    client = _make_client(mode=PagerDutyIntegrationMode.LIVE)
    with structlog.testing.capture_logs() as cap_logs:
        with patch(_URLOPEN_PATH, return_value=_make_live_response()):
            _trigger(client)
    assert cap_logs, "Expected at least one log entry in LIVE mode"
    # Find the API-call result entry (pd_page_trigger_sent)
    result_entries = [e for e in cap_logs if e.get("event") == "pd_page_trigger_sent"]
    assert result_entries, f"Expected pd_page_trigger_sent log entry; got: {cap_logs}"
    result = result_entries[0]
    assert result.get("outcome") == "success"
    assert result.get("mode") == "LIVE", f"Expected mode=LIVE in API result log; got: {result}"
    assert result.get("action") == "trigger", (
        f"Expected action=trigger in API result log; got: {result}"
    )


# ---------------------------------------------------------------------------
# LIVE mode — missing pd_routing_key
# ---------------------------------------------------------------------------


def test_live_mode_with_no_routing_key_logs_warning_and_skips_http() -> None:
    """LIVE mode with pd_routing_key=None: warning logged, HTTP call skipped."""
    client = _make_client(mode=PagerDutyIntegrationMode.LIVE, pd_routing_key=None)
    with structlog.testing.capture_logs() as cap_logs:
        with patch(_URLOPEN_PATH) as mock_urlopen:
            _trigger(client)
            mock_urlopen.assert_not_called()
    warning_entries = [e for e in cap_logs if e.get("log_level") == "warning"]
    assert warning_entries, f"Expected a warning log for missing pd_routing_key; got: {cap_logs}"


# ---------------------------------------------------------------------------
# LIVE mode — HTTP error handling
# ---------------------------------------------------------------------------


def test_live_mode_http_error_is_caught_and_logged_not_propagated() -> None:
    """LIVE mode HTTP error: exception caught, warning logged, does not propagate."""
    client = _make_client(mode=PagerDutyIntegrationMode.LIVE)
    with structlog.testing.capture_logs() as cap_logs:
        with patch(_URLOPEN_PATH, side_effect=OSError("connection refused")):
            _trigger(client)  # Must not raise
    error_entries = [e for e in cap_logs if e.get("log_level") == "warning"]
    assert error_entries, f"Expected a warning log for HTTP error; got: {cap_logs}"


def test_live_mode_timeout_error_does_not_propagate() -> None:
    """LIVE mode timeout: TimeoutError caught, does not propagate."""
    client = _make_client(mode=PagerDutyIntegrationMode.LIVE)
    with structlog.testing.capture_logs():
        with patch(_URLOPEN_PATH, side_effect=TimeoutError("timeout")):
            _trigger(client)  # Must not raise


# ---------------------------------------------------------------------------
# dedup_key stability
# ---------------------------------------------------------------------------


def test_dedup_key_stability_across_calls() -> None:
    """Same action_fingerprint always produces same dedup_key in payload (idempotent)."""
    client = _make_client(mode=PagerDutyIntegrationMode.LIVE)
    captured_bodies: list[dict] = []

    def capture_urlopen(req: object, timeout: int = 5) -> MagicMock:
        import urllib.request as _urllib_req

        if isinstance(req, _urllib_req.Request):
            captured_bodies.append(json.loads(req.data.decode()))  # type: ignore[attr-defined]
        return _make_live_response()

    with structlog.testing.capture_logs():
        with patch(_URLOPEN_PATH, side_effect=capture_urlopen):
            _trigger(client)
            _trigger(client)

    assert len(captured_bodies) == 2
    assert captured_bodies[0]["dedup_key"] == _FINGERPRINT
    assert captured_bodies[1]["dedup_key"] == _FINGERPRINT
    assert captured_bodies[0]["dedup_key"] == captured_bodies[1]["dedup_key"]
