"""Unit tests for ServiceNowClient tiered correlation and integration modes."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import structlog.testing

from aiops_triage_pipeline.config.settings import IntegrationMode
from aiops_triage_pipeline.contracts.sn_linkage import ServiceNowLinkageContractV1
from aiops_triage_pipeline.integrations.servicenow import ServiceNowClient

_CASE_ID = "case-sn-001"
_PD_INCIDENT_ID = "pd-inc-001"
_ROUTING_KEY = "OWN::Streaming::Payments::Topic"
_SN_BASE_URL = "https://servicenow.example.internal"
_URLOPEN_PATH = "aiops_triage_pipeline.integrations.servicenow.urllib.request.urlopen"


def _make_sn_response(records: list[dict[str, object]]) -> MagicMock:
    response = MagicMock()
    response.read.return_value = json.dumps({"result": records}).encode()
    response.__enter__ = lambda s: s
    response.__exit__ = MagicMock(return_value=False)
    return response


def _make_client(
    *,
    mode: IntegrationMode,
    mock_match_tier: str = "none",
) -> ServiceNowClient:
    return ServiceNowClient(
        mode=mode,
        base_url=_SN_BASE_URL,
        auth_token="test-token",
        linkage_contract=ServiceNowLinkageContractV1(),
        mock_match_tier=mock_match_tier,
    )


def _correlate(client: ServiceNowClient) -> object:
    return client.correlate_incident(
        case_id=_CASE_ID,
        pd_incident_id=_PD_INCIDENT_ID,
        routing_key=_ROUTING_KEY,
        keywords=("aiops_case_id", "stream-payments"),
        case_timestamp=datetime(2026, 3, 8, 12, 0, 0, tzinfo=timezone.utc),
    )


def test_tier1_match_returns_tier1() -> None:
    client = _make_client(mode=IntegrationMode.LIVE)
    with patch(
        _URLOPEN_PATH,
        side_effect=[_make_sn_response([{"sys_id": "inc-sys-1", "number": "INC001"}])],
    ) as mock_urlopen:
        result = _correlate(client)

    assert result.matched is True
    assert result.matched_tier == "tier1"
    assert result.incident_sys_id == "inc-sys-1"
    assert mock_urlopen.call_count == 1


def test_tier1_miss_tier2_match_returns_tier2() -> None:
    client = _make_client(mode=IntegrationMode.LIVE)
    with patch(
        _URLOPEN_PATH,
        side_effect=[
            _make_sn_response([]),
            _make_sn_response([{"sys_id": "inc-sys-2", "number": "INC002"}]),
        ],
    ) as mock_urlopen:
        result = _correlate(client)

    assert result.matched is True
    assert result.matched_tier == "tier2"
    assert result.incident_sys_id == "inc-sys-2"
    assert mock_urlopen.call_count == 2


def test_tier2_miss_tier3_match_returns_tier3() -> None:
    client = _make_client(mode=IntegrationMode.LIVE)
    with patch(
        _URLOPEN_PATH,
        side_effect=[
            _make_sn_response([]),
            _make_sn_response([]),
            _make_sn_response([{"sys_id": "inc-sys-3", "number": "INC003"}]),
        ],
    ) as mock_urlopen:
        result = _correlate(client)

    assert result.matched is True
    assert result.matched_tier == "tier3"
    assert result.incident_sys_id == "inc-sys-3"
    assert mock_urlopen.call_count == 3


def test_all_tiers_miss_returns_none() -> None:
    client = _make_client(mode=IntegrationMode.LIVE)
    with patch(
        _URLOPEN_PATH,
        side_effect=[_make_sn_response([]), _make_sn_response([]), _make_sn_response([])],
    ) as mock_urlopen:
        result = _correlate(client)

    assert result.matched is False
    assert result.matched_tier == "none"
    assert result.incident_sys_id is None
    assert mock_urlopen.call_count == 3


def test_off_mode_has_no_outbound_calls() -> None:
    client = _make_client(mode=IntegrationMode.OFF)
    with patch(_URLOPEN_PATH) as mock_urlopen:
        result = _correlate(client)

    assert result.matched is False
    assert result.reason == "mode_off"
    mock_urlopen.assert_not_called()


def test_log_mode_has_no_outbound_calls() -> None:
    client = _make_client(mode=IntegrationMode.LOG)
    with patch(_URLOPEN_PATH) as mock_urlopen:
        result = _correlate(client)

    assert result.matched is False
    assert result.reason == "mode_log_noop"
    mock_urlopen.assert_not_called()


def test_mock_mode_has_no_outbound_calls_and_deterministic_tier() -> None:
    client = _make_client(mode=IntegrationMode.MOCK, mock_match_tier="tier2")
    with patch(_URLOPEN_PATH) as mock_urlopen:
        result = _correlate(client)

    assert result.matched is True
    assert result.matched_tier == "tier2"
    assert result.reason == "mock_match"
    mock_urlopen.assert_not_called()


def test_tier_attempt_logs_include_required_fields() -> None:
    client = _make_client(mode=IntegrationMode.LOG)
    with structlog.testing.capture_logs() as cap_logs:
        _correlate(client)

    tier_logs = [entry for entry in cap_logs if entry.get("event") == "sn_correlation_tier_attempt"]
    assert len(tier_logs) == 3
    for entry in tier_logs:
        assert "timestamp" in entry
        assert "request_id" in entry
        assert entry.get("case_id") == _CASE_ID
        assert entry.get("action") == "incident_search"
        assert "outcome" in entry
        assert "latency_ms" in entry
        assert entry.get("tier") in {"tier1", "tier2", "tier3"}


def test_live_mode_uses_get_only_incident_reads() -> None:
    client = _make_client(mode=IntegrationMode.LIVE)
    with patch(
        _URLOPEN_PATH,
        side_effect=[_make_sn_response([{"sys_id": "inc-sys-1", "number": "INC001"}])],
    ) as mock_urlopen:
        _correlate(client)

    request = mock_urlopen.call_args[0][0]
    assert request.method == "GET"
    assert "/api/now/table/incident" in request.full_url
