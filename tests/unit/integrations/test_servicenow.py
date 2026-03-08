"""Unit tests for ServiceNowClient tiered correlation and integration modes."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from email.message import Message
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlsplit

import structlog.testing

from aiops_triage_pipeline.config.settings import IntegrationMode
from aiops_triage_pipeline.contracts.sn_linkage import ServiceNowLinkageContractV1
from aiops_triage_pipeline.denylist.loader import DenylistV1
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
    linkage_contract: ServiceNowLinkageContractV1 | None = None,
) -> ServiceNowClient:
    return ServiceNowClient(
        mode=mode,
        base_url=_SN_BASE_URL,
        auth_token="test-token",
        linkage_contract=linkage_contract or ServiceNowLinkageContractV1(),
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


def test_live_mode_excludes_work_notes_field_by_default() -> None:
    client = _make_client(mode=IntegrationMode.LIVE)
    with patch(
        _URLOPEN_PATH,
        side_effect=[_make_sn_response([{"sys_id": "inc-sys-1", "number": "INC001"}])],
    ) as mock_urlopen:
        _correlate(client)

    request = mock_urlopen.call_args[0][0]
    params = parse_qs(urlsplit(request.full_url).query)
    assert (
        params["sysparm_fields"][0]
        == "sys_id,number,short_description,description,sys_created_on"
    )


def test_live_mode_includes_work_notes_field_when_enabled() -> None:
    contract = ServiceNowLinkageContractV1(
        tier2_text_fields=("short_description", "description", "work_notes"),
        tier2_include_work_notes=True,
    )
    client = _make_client(mode=IntegrationMode.LIVE, linkage_contract=contract)
    with patch(
        _URLOPEN_PATH,
        side_effect=[_make_sn_response([{"sys_id": "inc-sys-1", "number": "INC001"}])],
    ) as mock_urlopen:
        _correlate(client)

    request = mock_urlopen.call_args[0][0]
    params = parse_qs(urlsplit(request.full_url).query)
    assert "work_notes" in params["sysparm_fields"][0]


def test_tier3_query_uses_backward_looking_window() -> None:
    client = _make_client(mode=IntegrationMode.LIVE)
    with patch(
        _URLOPEN_PATH,
        side_effect=[
            _make_sn_response([]),
            _make_sn_response([]),
            _make_sn_response([{"sys_id": "inc-sys-3", "number": "INC003"}]),
        ],
    ) as mock_urlopen:
        _correlate(client)

    tier3_request = mock_urlopen.call_args_list[2][0][0]
    tier3_query = parse_qs(urlsplit(tier3_request.full_url).query)["sysparm_query"][0]
    assert "sys_created_on>=2026-03-08 10:00:00" in tier3_query
    assert "sys_created_on<=2026-03-08 12:00:00" in tier3_query
    assert "2026-03-08 14:00:00" not in tier3_query


def test_live_mode_picks_most_recent_incident_deterministically() -> None:
    client = _make_client(mode=IntegrationMode.LIVE)
    records = [
        {
            "sys_id": "inc-sys-old",
            "number": "INC001",
            "sys_created_on": "2026-03-08 10:00:00",
        },
        {
            "sys_id": "inc-sys-new",
            "number": "INC002",
            "sys_created_on": "2026-03-08 11:59:59",
        },
    ]
    with patch(_URLOPEN_PATH, side_effect=[_make_sn_response(records)]):
        result = _correlate(client)

    assert result.matched is True
    assert result.incident_sys_id == "inc-sys-new"
    assert result.reason_metadata["incident_number"] == "INC002"


def test_invalid_identifiers_return_invalid_input_without_http_calls() -> None:
    client = _make_client(mode=IntegrationMode.LIVE)
    with patch(_URLOPEN_PATH) as mock_urlopen:
        result = client.correlate_incident(
            case_id="",
            pd_incident_id=" ",
            routing_key="",
        )

    assert result.matched is False
    assert result.reason == "invalid_input"
    assert result.reason_metadata["missing_fields"] == (
        "case_id",
        "pd_incident_id",
        "routing_key",
    )
    mock_urlopen.assert_not_called()


def test_live_mode_respects_correlation_strategy_order_and_scope() -> None:
    contract = ServiceNowLinkageContractV1(correlation_strategy=("tier1",))
    client = _make_client(mode=IntegrationMode.LIVE, linkage_contract=contract)
    with patch(_URLOPEN_PATH, side_effect=[_make_sn_response([])]) as mock_urlopen:
        result = _correlate(client)

    assert result.matched is False
    assert result.matched_tier == "none"
    assert mock_urlopen.call_count == 1


def test_correlation_records_metric_once_for_live_tier2_match() -> None:
    client = _make_client(mode=IntegrationMode.LIVE)
    with (
        patch(
            _URLOPEN_PATH,
            side_effect=[
                _make_sn_response([]),
                _make_sn_response([{"sys_id": "inc-sys-2", "number": "INC002"}]),
            ],
        ),
        patch(
            "aiops_triage_pipeline.integrations.servicenow.record_sn_correlation_tier"
        ) as metric_recorder,
    ):
        _correlate(client)

    metric_recorder.assert_called_once_with(matched_tier="tier2")


def test_correlation_records_metric_once_for_non_live_modes() -> None:
    scenarios = (
        (IntegrationMode.OFF, "none"),
        (IntegrationMode.LOG, "none"),
        (IntegrationMode.MOCK, "tier2"),
    )
    for mode, expected_tier in scenarios:
        client = _make_client(mode=mode, mock_match_tier="tier2")
        with patch(
            "aiops_triage_pipeline.integrations.servicenow.record_sn_correlation_tier"
        ) as metric_recorder:
            _correlate(client)
        metric_recorder.assert_called_once_with(matched_tier=expected_tier)


def test_correlation_evaluates_fallback_alert_with_runtime_snapshot() -> None:
    evaluator = MagicMock()
    evaluator.evaluate_sn_correlation_fallback_rate.return_value = None
    client = ServiceNowClient(
        mode=IntegrationMode.OFF,
        base_url=_SN_BASE_URL,
        auth_token="test-token",
        alert_evaluator=evaluator,
    )
    with patch(
        "aiops_triage_pipeline.integrations.servicenow.record_sn_correlation_tier",
        return_value=MagicMock(
            fallback_rate=0.42,
            sample_size=12,
            fallback_tiers=("tier2", "tier3"),
        ),
    ):
        _correlate(client)

    evaluator.evaluate_sn_correlation_fallback_rate.assert_called_once_with(
        fallback_rate=0.42,
        fallback_tiers=("tier2", "tier3"),
        sample_size=12,
    )


def _decode_request_body(request: object) -> dict[str, object]:
    payload = getattr(request, "data", None)
    if payload is None:
        return {}
    return json.loads(payload.decode("utf-8"))


def test_problem_external_id_generation_is_deterministic() -> None:
    client = _make_client(mode=IntegrationMode.OFF)

    first = client.build_problem_external_id(case_id=_CASE_ID, pd_incident_id=_PD_INCIDENT_ID)
    second = client.build_problem_external_id(case_id=_CASE_ID, pd_incident_id=_PD_INCIDENT_ID)

    assert first == second
    assert first.startswith("aiops:problem:")


def test_pir_task_external_id_generation_is_deterministic() -> None:
    client = _make_client(mode=IntegrationMode.OFF)

    first = client.build_pir_task_external_id(
        case_id=_CASE_ID,
        pd_incident_id=_PD_INCIDENT_ID,
        task_type="timeline",
    )
    second = client.build_pir_task_external_id(
        case_id=_CASE_ID,
        pd_incident_id=_PD_INCIDENT_ID,
        task_type="timeline",
    )

    assert first == second
    assert first.endswith(":timeline")


def test_upsert_problem_is_idempotent_create_then_update() -> None:
    client = _make_client(mode=IntegrationMode.LIVE)
    with patch(
        _URLOPEN_PATH,
        side_effect=[
            _make_sn_response([]),
            _make_sn_response([{"sys_id": "prb-001"}]),
            _make_sn_response([{"sys_id": "prb-001"}]),
            _make_sn_response([{"sys_id": "prb-001"}]),
        ],
    ):
        created = client.upsert_problem(
            case_id=_CASE_ID,
            pd_incident_id=_PD_INCIDENT_ID,
            incident_sys_id="inc-001",
            summary="streaming lag case",
            context={"routing_key": _ROUTING_KEY},
        )
        updated = client.upsert_problem(
            case_id=_CASE_ID,
            pd_incident_id=_PD_INCIDENT_ID,
            incident_sys_id="inc-001",
            summary="streaming lag case",
            context={"routing_key": _ROUTING_KEY},
        )

    assert created.outcome == "created"
    assert updated.outcome == "updated"
    assert created.sys_id == updated.sys_id == "prb-001"


def test_upsert_pir_task_is_idempotent_create_then_update() -> None:
    client = _make_client(mode=IntegrationMode.LIVE)
    with patch(
        _URLOPEN_PATH,
        side_effect=[
            _make_sn_response([]),
            _make_sn_response([{"sys_id": "ptsk-001"}]),
            _make_sn_response([{"sys_id": "ptsk-001"}]),
            _make_sn_response([{"sys_id": "ptsk-001"}]),
        ],
    ):
        created = client.upsert_pir_task(
            case_id=_CASE_ID,
            pd_incident_id=_PD_INCIDENT_ID,
            problem_sys_id="prb-001",
            task_type="timeline",
            summary="build PIR timeline",
            context={"routing_key": _ROUTING_KEY},
        )
        updated = client.upsert_pir_task(
            case_id=_CASE_ID,
            pd_incident_id=_PD_INCIDENT_ID,
            problem_sys_id="prb-001",
            task_type="timeline",
            summary="build PIR timeline",
            context={"routing_key": _ROUTING_KEY},
        )

    assert created.outcome == "created"
    assert updated.outcome == "updated"
    assert created.sys_id == updated.sys_id == "ptsk-001"


def test_upsert_problem_applies_denylist_before_live_write() -> None:
    denylist = DenylistV1(
        denylist_version="v-test",
        denied_field_names=("secret",),
        denied_value_patterns=("Bearer\\s+[A-Za-z0-9\\-._~+/]+=*",),
    )
    client = ServiceNowClient(
        mode=IntegrationMode.LIVE,
        base_url=_SN_BASE_URL,
        auth_token="test-token",
        denylist=denylist,
    )
    with patch(
        _URLOPEN_PATH,
        side_effect=[
            _make_sn_response([]),
            _make_sn_response([{"sys_id": "prb-001"}]),
        ],
    ) as mock_urlopen:
        client.upsert_problem(
            case_id=_CASE_ID,
            pd_incident_id=_PD_INCIDENT_ID,
            incident_sys_id="inc-001",
            summary="Bearer secret-token should be removed",
            context={"secret": "value", "routing_key": _ROUTING_KEY},
        )

    create_request = mock_urlopen.call_args_list[1][0][0]
    payload = _decode_request_body(create_request)
    assert "secret" not in json.dumps(payload).lower()
    assert "Bearer secret-token" not in json.dumps(payload)


def test_sn_write_logs_include_required_fields() -> None:
    client = _make_client(mode=IntegrationMode.LOG)
    with structlog.testing.capture_logs() as cap_logs:
        client.upsert_problem_and_pir_tasks(
            case_id=_CASE_ID,
            pd_incident_id=_PD_INCIDENT_ID,
            incident_sys_id="inc-001",
            summary="link case",
            pir_task_types=("timeline",),
            context={"routing_key": _ROUTING_KEY},
        )

    write_logs = [entry for entry in cap_logs if entry.get("event") == "sn_write_attempt"]
    assert write_logs
    for entry in write_logs:
        assert "timestamp" in entry
        assert "request_id" in entry
        assert entry.get("case_id") == _CASE_ID
        assert "sys_ids_touched" in entry
        assert "action" in entry
        assert "outcome" in entry
        assert "latency_ms" in entry


def test_upsert_paths_do_not_write_incident_or_major_incident_tables() -> None:
    client = _make_client(mode=IntegrationMode.LIVE)
    with patch(
        _URLOPEN_PATH,
        side_effect=[
            _make_sn_response([]),
            _make_sn_response([{"sys_id": "prb-001"}]),
            _make_sn_response([]),
            _make_sn_response([{"sys_id": "ptsk-001"}]),
        ],
    ) as mock_urlopen:
        client.upsert_problem_and_pir_tasks(
            case_id=_CASE_ID,
            pd_incident_id=_PD_INCIDENT_ID,
            incident_sys_id="inc-001",
            summary="link case",
            pir_task_types=("timeline",),
            context={"routing_key": _ROUTING_KEY},
        )

    request_urls = [call[0][0].full_url for call in mock_urlopen.call_args_list]
    assert all(
        "/api/now/table/problem" in url or "/api/now/table/problem_task" in url
        for url in request_urls
    )
    assert all("/api/now/table/incident" not in url for url in request_urls)
    assert all("major_incident" not in url for url in request_urls)


def test_orchestration_returns_structured_failure_when_live_write_errors() -> None:
    client = _make_client(mode=IntegrationMode.LIVE)
    with patch(_URLOPEN_PATH, side_effect=RuntimeError("network down")):
        outcome = client.upsert_problem_and_pir_tasks(
            case_id=_CASE_ID,
            pd_incident_id=_PD_INCIDENT_ID,
            incident_sys_id="inc-001",
            summary="link case",
            pir_task_types=("timeline",),
            context={"routing_key": _ROUTING_KEY},
        )

    assert outcome.linkage_status == "failed"
    assert outcome.linkage_reason == "upsert_error"
    assert outcome.problem_sys_id is None


def test_upsert_orchestration_modes_off_log_mock_avoid_live_http_calls() -> None:
    off_client = _make_client(mode=IntegrationMode.OFF)
    log_client = _make_client(mode=IntegrationMode.LOG)
    mock_client = _make_client(mode=IntegrationMode.MOCK)

    with patch(_URLOPEN_PATH) as mock_urlopen:
        off_outcome = off_client.upsert_problem_and_pir_tasks(
            case_id=_CASE_ID,
            pd_incident_id=_PD_INCIDENT_ID,
            incident_sys_id="inc-001",
            summary="link case",
            pir_task_types=("timeline",),
            context={"routing_key": _ROUTING_KEY},
        )
        log_outcome = log_client.upsert_problem_and_pir_tasks(
            case_id=_CASE_ID,
            pd_incident_id=_PD_INCIDENT_ID,
            incident_sys_id="inc-001",
            summary="link case",
            pir_task_types=("timeline",),
            context={"routing_key": _ROUTING_KEY},
        )
        mock_outcome = mock_client.upsert_problem_and_pir_tasks(
            case_id=_CASE_ID,
            pd_incident_id=_PD_INCIDENT_ID,
            incident_sys_id="inc-001",
            summary="link case",
            pir_task_types=("timeline",),
            context={"routing_key": _ROUTING_KEY},
        )

    mock_urlopen.assert_not_called()
    assert off_outcome.linkage_status == "skipped"
    assert log_outcome.linkage_status == "skipped"
    assert mock_outcome.linkage_status == "linked"
    assert mock_outcome.problem_sys_id is not None


def test_upsert_problem_fails_when_lookup_returns_multiple_records_for_external_id() -> None:
    client = _make_client(mode=IntegrationMode.LIVE)
    with patch(
        _URLOPEN_PATH,
        side_effect=[
            _make_sn_response([{"sys_id": "prb-001"}, {"sys_id": "prb-002"}]),
        ],
    ) as mock_urlopen:
        result = client.upsert_problem(
            case_id=_CASE_ID,
            pd_incident_id=_PD_INCIDENT_ID,
            incident_sys_id="inc-001",
            summary="streaming lag case",
            context={"routing_key": _ROUTING_KEY},
        )

    assert result.outcome == "failed"
    assert result.reason == "lookup_error"
    assert "multiple existing records found for external_id" in result.reason_metadata["error"]
    assert mock_urlopen.call_count == 1


def test_upsert_pir_task_description_contains_problem_sys_id_not_incident_sys_id() -> None:
    client = _make_client(mode=IntegrationMode.LIVE)
    with patch(
        _URLOPEN_PATH,
        side_effect=[
            _make_sn_response([]),
            _make_sn_response([{"sys_id": "ptsk-001"}]),
        ],
    ) as mock_urlopen:
        client.upsert_pir_task(
            case_id=_CASE_ID,
            pd_incident_id=_PD_INCIDENT_ID,
            problem_sys_id="prb-001",
            task_type="timeline",
            summary="build PIR timeline",
            context={"routing_key": _ROUTING_KEY},
        )

    create_request = mock_urlopen.call_args_list[1][0][0]
    payload = _decode_request_body(create_request)
    description = json.loads(str(payload["description"]))
    assert description["problem_sys_id"] == "prb-001"
    assert "incident_sys_id" not in description


def test_upsert_problem_and_pir_tasks_rejects_empty_task_type_list() -> None:
    client = _make_client(mode=IntegrationMode.MOCK)

    outcome = client.upsert_problem_and_pir_tasks(
        case_id=_CASE_ID,
        pd_incident_id=_PD_INCIDENT_ID,
        incident_sys_id="inc-001",
        summary="link case",
        pir_task_types=(),
    )

    assert outcome.linkage_status == "failed"
    assert outcome.linkage_reason == "invalid_input"
    assert outcome.reason_metadata["missing_fields"] == ("pir_task_types",)


def test_upsert_orchestration_surfaces_http_429_error_code_and_retry_after() -> None:
    client = _make_client(mode=IntegrationMode.LIVE)
    headers = Message()
    headers["Retry-After"] = "7"
    http_429 = HTTPError(
        url=f"{_SN_BASE_URL}/api/now/table/problem",
        code=429,
        msg="Too Many Requests",
        hdrs=headers,
        fp=None,
    )
    with patch(_URLOPEN_PATH, side_effect=http_429):
        outcome = client.upsert_problem_and_pir_tasks(
            case_id=_CASE_ID,
            pd_incident_id=_PD_INCIDENT_ID,
            incident_sys_id="inc-001",
            summary="link case",
            pir_task_types=("timeline",),
            context={"routing_key": _ROUTING_KEY},
        )

    assert outcome.linkage_status == "failed"
    assert outcome.reason_metadata["problem_reason"] == "lookup_error"
    assert outcome.reason_metadata["error_code"] == "http_429"
    assert outcome.reason_metadata["retry_after_seconds"] == 7
