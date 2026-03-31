from __future__ import annotations

import asyncio
import sys
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from aiops_triage_pipeline import __main__
from aiops_triage_pipeline.__main__ import _HotPathCoordinationState
from aiops_triage_pipeline.contracts.enums import Action
from aiops_triage_pipeline.coordination.protocol import CycleLockStatus
from aiops_triage_pipeline.errors.exceptions import IntegrationError
from aiops_triage_pipeline.models.anomaly import AnomalyFinding


def test_main_dispatches_casefile_lifecycle_mode_once(monkeypatch) -> None:
    calls: list[bool] = []
    monkeypatch.setattr(__main__, "_run_casefile_lifecycle", lambda *, once: calls.append(once))
    monkeypatch.setattr(
        sys,
        "argv",
        ["aiops-triage-pipeline", "--mode", "casefile-lifecycle", "--once"],
    )

    __main__.main()

    assert calls == [True]


def test_main_dispatches_casefile_lifecycle_mode_forever(monkeypatch) -> None:
    calls: list[bool] = []
    monkeypatch.setattr(__main__, "_run_casefile_lifecycle", lambda *, once: calls.append(once))
    monkeypatch.setattr(
        sys,
        "argv",
        ["aiops-triage-pipeline", "--mode", "casefile-lifecycle"],
    )

    __main__.main()

    assert calls == [False]


def test_main_dispatches_outbox_publisher_mode_once(monkeypatch) -> None:
    calls: list[bool] = []
    monkeypatch.setattr(__main__, "_run_outbox_publisher", lambda *, once: calls.append(once))
    monkeypatch.setattr(
        sys,
        "argv",
        ["aiops-triage-pipeline", "--mode", "outbox-publisher", "--once"],
    )

    __main__.main()

    assert calls == [True]


def test_main_dispatches_hot_path_mode(monkeypatch) -> None:
    called = {"hot": False}

    def _mark_hot() -> None:
        called["hot"] = True

    monkeypatch.setattr(__main__, "_run_hot_path", _mark_hot)
    monkeypatch.setattr(sys, "argv", ["aiops-triage-pipeline", "--mode", "hot-path"])

    __main__.main()

    assert called["hot"] is True


def test_main_dispatches_cold_path_mode(monkeypatch) -> None:
    called = {"cold": False}

    def _mark_cold() -> None:
        called["cold"] = True

    monkeypatch.setattr(__main__, "_run_cold_path", _mark_cold)
    monkeypatch.setattr(sys, "argv", ["aiops-triage-pipeline", "--mode", "cold-path"])

    __main__.main()

    assert called["cold"] is True


def test_main_dispatches_harness_cleanup_mode(monkeypatch) -> None:
    called = {"cleanup": False}

    def _mark_cleanup() -> None:
        called["cleanup"] = True

    monkeypatch.setattr(__main__, "_run_harness_cleanup", _mark_cleanup)
    monkeypatch.setattr(sys, "argv", ["aiops-triage-pipeline", "--mode", "harness-cleanup"])

    __main__.main()

    assert called["cleanup"] is True


def _make_mock_bootstrap(mode_capture: list[str]):
    """Return a mock _bootstrap_mode that records mode and returns a stub triple."""
    logger = MagicMock()

    def _fake_bootstrap(mode: str):
        mode_capture.append(mode)
        return MagicMock(), logger, MagicMock()

    return _fake_bootstrap, logger


def _make_mock_hot_path_deps(monkeypatch) -> None:
    """Patch all hot-path startup dependencies so _run_hot_path() can reach asyncio.run."""
    monkeypatch.setattr(__main__, "load_peak_policy", lambda *a, **k: MagicMock())
    monkeypatch.setattr(__main__, "load_rulebook_policy", lambda *a, **k: MagicMock())
    monkeypatch.setattr(__main__, "load_redis_ttl_policy", lambda *a, **k: MagicMock())
    monkeypatch.setattr(__main__, "load_prometheus_metrics_contract", lambda *a, **k: MagicMock())
    monkeypatch.setattr(__main__, "build_metric_queries", lambda *a, **k: {})
    monkeypatch.setattr(__main__, "load_denylist", lambda *a, **k: MagicMock())
    monkeypatch.setattr(__main__, "PrometheusHTTPClient", MagicMock())
    monkeypatch.setattr(__main__, "redis_lib", MagicMock())
    monkeypatch.setattr(__main__, "RedisActionDedupeStore", MagicMock())
    monkeypatch.setattr(
        __main__, "build_s3_object_store_client_from_settings", lambda *a, **k: MagicMock()
    )
    monkeypatch.setattr(__main__, "create_engine", lambda *a, **k: MagicMock())
    monkeypatch.setattr(__main__, "OutboxSqlRepository", MagicMock())
    monkeypatch.setattr(__main__, "PagerDutyClient", MagicMock())
    monkeypatch.setattr(__main__, "SlackClient", MagicMock())
    topology_loader = MagicMock()
    monkeypatch.setattr(__main__, "TopologyRegistryLoader", lambda *a, **k: topology_loader)


def test_run_hot_path_bootstraps_and_starts_scheduler(monkeypatch) -> None:
    modes: list[str] = []
    fake_bootstrap, logger = _make_mock_bootstrap(modes)

    settings_mock = MagicMock()
    settings_mock.TOPOLOGY_REGISTRY_PATH = "/fake/topology.yaml"
    settings_mock.INTEGRATION_MODE_PD.value = "LOG"
    settings_mock.INTEGRATION_MODE_SLACK.value = "LOG"
    settings_mock.APP_ENV.value = "local"
    settings_mock.CYCLE_LOCK_MARGIN_SECONDS = 60

    def _fake_bootstrap_with_settings(mode: str):
        modes.append(mode)
        return settings_mock, logger, MagicMock()

    monkeypatch.setattr(__main__, "_bootstrap_mode", _fake_bootstrap_with_settings)
    _make_mock_hot_path_deps(monkeypatch)

    asyncio_run_calls: list = []

    def _capture_and_close(coro):
        asyncio_run_calls.append(coro)
        coro.close()

    monkeypatch.setattr(__main__.asyncio, "run", _capture_and_close)

    __main__._run_hot_path()

    assert modes == ["hot-path"]
    assert len(asyncio_run_calls) == 1
    info_events = [call[0][0] for call in logger.info.call_args_list]
    assert "hot_path_mode_started" in info_events


def test_run_hot_path_raises_when_topology_registry_not_configured(monkeypatch) -> None:
    settings_mock = MagicMock()
    settings_mock.TOPOLOGY_REGISTRY_PATH = None

    def _fake_bootstrap(mode: str):
        return settings_mock, MagicMock(), MagicMock()

    monkeypatch.setattr(__main__, "_bootstrap_mode", _fake_bootstrap)

    with pytest.raises(ValueError, match="TOPOLOGY_REGISTRY_PATH"):
        __main__._run_hot_path()


def test_run_harness_cleanup_rejects_non_local_or_harness_env(monkeypatch) -> None:
    settings = SimpleNamespace(
        APP_ENV=SimpleNamespace(value="dev"),
    )

    monkeypatch.setattr(
        __main__,
        "_bootstrap_mode",
        lambda mode: (settings, MagicMock(), MagicMock()),
    )

    with pytest.raises(ValueError, match="harness-cleanup mode is only allowed"):
        __main__._run_harness_cleanup()


def test_run_harness_cleanup_runs_sweep_and_logs_summary(monkeypatch) -> None:
    settings = SimpleNamespace(
        APP_ENV=__main__.AppEnv.local,
        DATABASE_URL="postgresql+psycopg://aiops:aiops@localhost:5432/aiops",
        REDIS_URL="redis://localhost:6379/0",
    )
    logger = MagicMock()
    object_store_client = MagicMock()
    engine = MagicMock()
    redis_client = MagicMock()

    monkeypatch.setattr(
        __main__,
        "_bootstrap_mode",
        lambda mode: (settings, logger, MagicMock()),
    )
    monkeypatch.setattr(
        __main__,
        "build_s3_object_store_client_from_settings",
        lambda _settings: object_store_client,
    )
    monkeypatch.setattr(__main__, "create_engine", lambda _url: engine)
    monkeypatch.setattr(
        __main__,
        "redis_lib",
        SimpleNamespace(
            Redis=SimpleNamespace(from_url=lambda _url: redis_client),
        ),
    )
    monkeypatch.setattr(
        __main__,
        "_collect_harness_casefile_keys",
        lambda **kwargs: ["cases/case-harness-a/triage.json", "cases/case-harness-b/triage.json"],
    )
    monkeypatch.setattr(
        __main__,
        "_delete_harness_casefiles",
        lambda **kwargs: (2, 0),
    )
    monkeypatch.setattr(
        __main__,
        "_delete_harness_outbox_rows",
        lambda **kwargs: 3,
    )
    monkeypatch.setattr(
        __main__,
        "_delete_harness_redis_keys",
        lambda **kwargs: (5, 5),
    )

    __main__._run_harness_cleanup()

    complete_log = next(
        (
            call
            for call in logger.info.call_args_list
            if call.args and call.args[0] == "harness_cleanup_completed"
        ),
        None,
    )
    assert complete_log is not None
    assert complete_log.kwargs["event_type"] == "harness.cleanup.complete"
    assert complete_log.kwargs["casefiles_found_count"] == 2
    assert complete_log.kwargs["casefiles_deleted_count"] == 2
    assert complete_log.kwargs["casefiles_failed_count"] == 0
    assert complete_log.kwargs["outbox_rows_deleted_count"] == 3
    assert complete_log.kwargs["redis_keys_matched_count"] == 5
    assert complete_log.kwargs["redis_keys_deleted_count"] == 5


def _build_cold_path_settings_for_unit() -> SimpleNamespace:
    """Minimal settings object for cold-path unit tests."""
    return SimpleNamespace(
        APP_ENV=SimpleNamespace(value="dev"),
        KAFKA_CASE_HEADER_TOPIC="aiops-case-header",
        KAFKA_COLD_PATH_CONSUMER_GROUP="aiops-cold-path-diagnosis",
        KAFKA_COLD_PATH_POLL_TIMEOUT_SECONDS=1.0,
        HEALTH_SERVER_HOST="127.0.0.1",
        HEALTH_SERVER_PORT=0,
    )


def _make_async_health_registry() -> MagicMock:
    """Return a MagicMock health registry with an async update method."""
    registry = MagicMock()
    registry.update = AsyncMock()
    return registry


def test_run_cold_path_is_no_longer_stub_and_logs_mode_started(monkeypatch) -> None:
    """_run_cold_path() no longer exits as a stub; it logs cold_path_mode_started."""
    modes: list[str] = []
    logger = MagicMock()
    settings = _build_cold_path_settings_for_unit()

    def _fake_bootstrap(mode: str):
        modes.append(mode)
        return settings, logger, MagicMock()

    monkeypatch.setattr(__main__, "_bootstrap_mode", _fake_bootstrap)
    monkeypatch.setattr(
        __main__, "get_health_registry", lambda: _make_async_health_registry(), raising=False
    )
    monkeypatch.setattr(
        __main__, "build_s3_object_store_client_from_settings", lambda _: MagicMock()
    )
    mock_server = MagicMock()
    mock_server.serve_forever = AsyncMock()
    monkeypatch.setattr(
        "aiops_triage_pipeline.__main__.start_health_server",
        AsyncMock(return_value=mock_server),
    )

    __main__._run_cold_path()

    assert modes == ["cold-path"]
    info_events = [c.args[0] for c in logger.info.call_args_list if c.args]
    assert "cold_path_mode_started" in info_events
    # Stub warning must NOT appear
    warning_events = [c.args[0] for c in logger.warning.call_args_list if c.args]
    assert "cold_path_mode_exiting" not in warning_events


def test_run_cold_path_startup_log_includes_consumer_group_and_topic(monkeypatch) -> None:
    """cold_path_mode_started log must include consumer_group and topic."""
    logger = MagicMock()
    settings = _build_cold_path_settings_for_unit()

    monkeypatch.setattr(__main__, "_bootstrap_mode", lambda mode: (settings, logger, MagicMock()))
    monkeypatch.setattr(
        __main__, "get_health_registry", lambda: _make_async_health_registry(), raising=False
    )
    monkeypatch.setattr(
        __main__, "build_s3_object_store_client_from_settings", lambda _: MagicMock()
    )
    mock_server = MagicMock()
    mock_server.serve_forever = AsyncMock()
    monkeypatch.setattr(
        "aiops_triage_pipeline.__main__.start_health_server",
        AsyncMock(return_value=mock_server),
    )

    __main__._run_cold_path()

    start_call = next(
        c for c in logger.info.call_args_list if c.args and c.args[0] == "cold_path_mode_started"
    )
    assert start_call.kwargs["consumer_group"] == "aiops-cold-path-diagnosis"
    assert start_call.kwargs["topic"] == "aiops-case-header"


def test_run_casefile_lifecycle_logs_policy_path_and_governance_ref(monkeypatch) -> None:
    logger = MagicMock()
    settings = SimpleNamespace(
        APP_ENV=SimpleNamespace(value="prod"),
        CASEFILE_RETENTION_GOVERNANCE_APPROVAL="CHG-TEST-9000",
        CASEFILE_LIFECYCLE_DELETE_BATCH_SIZE=250,
        CASEFILE_LIFECYCLE_LIST_PAGE_SIZE=250,
        CASEFILE_LIFECYCLE_POLL_INTERVAL_SECONDS=1800.0,
    )

    class _RunnerProbe:
        def run_once(self):
            return SimpleNamespace(
                scanned_count=1,
                eligible_count=1,
                purged_count=1,
                failed_count=0,
                case_ids=("case-old-a",),
            )

    monkeypatch.setattr(__main__, "_bootstrap_mode", lambda mode: (settings, logger, MagicMock()))
    monkeypatch.setattr(__main__, "build_s3_object_store_client_from_settings", lambda _: object())
    monkeypatch.setattr(
        __main__,
        "load_policy_yaml",
        lambda *_a, **_k: SimpleNamespace(schema_version="v1"),
    )
    monkeypatch.setattr(__main__, "CasefileLifecycleRunner", lambda **_kwargs: _RunnerProbe())

    __main__._run_casefile_lifecycle(once=True)

    start_call = next(
        call
        for call in logger.info.call_args_list
        if call.args and call.args[0] == "casefile_lifecycle_mode_started"
    )
    assert start_call.kwargs["governance_approval_ref"] == "CHG-TEST-9000"
    assert start_call.kwargs["retention_policy_path"].endswith(
        "config/policies/casefile-retention-policy-v1.yaml"
    )
    assert start_call.kwargs["policy_schema_version"] == "v1"


def test_run_outbox_publisher_starts_health_server_in_daemon_mode(monkeypatch) -> None:
    """_run_outbox_publisher(once=False) calls _start_health_server_background (FR54)."""
    settings = SimpleNamespace(
        APP_ENV=SimpleNamespace(value="dev"),
        DATABASE_URL="postgresql+psycopg://u:p@h/db",
        KAFKA_CASE_HEADER_TOPIC="aiops-case-header",
        KAFKA_TRIAGE_EXCERPT_TOPIC="aiops-triage-excerpt",
        OUTBOX_PUBLISHER_BATCH_SIZE=100,
        OUTBOX_PUBLISHER_POLL_INTERVAL_SECONDS=5.0,
        HEALTH_SERVER_HOST="127.0.0.1",
        HEALTH_SERVER_PORT=0,
    )
    monkeypatch.setattr(
        __main__, "_bootstrap_mode", lambda mode: (settings, MagicMock(), MagicMock())
    )
    monkeypatch.setattr(__main__, "load_policy_yaml", lambda *_a, **_k: MagicMock())
    monkeypatch.setattr(__main__, "load_denylist", lambda *_a: MagicMock())
    monkeypatch.setattr(__main__, "create_engine", lambda *_a, **_k: MagicMock())
    monkeypatch.setattr(__main__, "OutboxSqlRepository", lambda **_k: MagicMock())
    monkeypatch.setattr(__main__, "ConfluentKafkaCaseEventPublisher", lambda **_k: MagicMock())
    monkeypatch.setattr(
        __main__, "build_s3_object_store_client_from_settings", lambda _: MagicMock()
    )

    health_calls: list[tuple] = []
    monkeypatch.setattr(
        __main__, "_start_health_server_background", lambda h, p: health_calls.append((h, p))
    )

    worker = MagicMock()
    monkeypatch.setattr(__main__, "OutboxPublisherWorker", lambda **_k: worker)

    __main__._run_outbox_publisher(once=False)

    assert health_calls == [("127.0.0.1", 0)]
    worker.run_forever.assert_called_once()


def test_run_casefile_lifecycle_starts_health_server_in_daemon_mode(monkeypatch) -> None:
    """_run_casefile_lifecycle(once=False) calls _start_health_server_background (FR54)."""
    settings = SimpleNamespace(
        APP_ENV=SimpleNamespace(value="dev"),
        CASEFILE_RETENTION_GOVERNANCE_APPROVAL=None,
        CASEFILE_LIFECYCLE_DELETE_BATCH_SIZE=500,
        CASEFILE_LIFECYCLE_LIST_PAGE_SIZE=500,
        CASEFILE_LIFECYCLE_POLL_INTERVAL_SECONDS=3600.0,
        HEALTH_SERVER_HOST="127.0.0.1",
        HEALTH_SERVER_PORT=0,
    )
    monkeypatch.setattr(
        __main__, "_bootstrap_mode", lambda mode: (settings, MagicMock(), MagicMock())
    )
    monkeypatch.setattr(
        __main__, "load_policy_yaml", lambda *_a, **_k: SimpleNamespace(schema_version="v1")
    )
    monkeypatch.setattr(
        __main__, "build_s3_object_store_client_from_settings", lambda _: MagicMock()
    )

    health_calls: list[tuple] = []
    monkeypatch.setattr(
        __main__, "_start_health_server_background", lambda h, p: health_calls.append((h, p))
    )

    runner = MagicMock()
    runner.run_once.side_effect = SystemExit(0)
    monkeypatch.setattr(__main__, "CasefileLifecycleRunner", lambda **_k: runner)

    with pytest.raises(SystemExit):
        __main__._run_casefile_lifecycle(once=False)

    assert health_calls == [("127.0.0.1", 0)]
    runner.run_once.assert_called_once()


def test_run_hot_path_emits_structured_error_on_bootstrap_failure(monkeypatch) -> None:
    mock_logger = MagicMock()
    monkeypatch.setattr(__main__, "get_logger", lambda _: mock_logger)
    monkeypatch.setattr(
        __main__,
        "_bootstrap_mode",
        MagicMock(side_effect=RuntimeError("bad config")),
    )

    try:
        __main__._run_hot_path()
    except RuntimeError:
        pass
    else:
        raise AssertionError("Expected RuntimeError to propagate")

    mock_logger.critical.assert_called_once()
    call_args = mock_logger.critical.call_args
    assert call_args[0][0] == "hot_path_bootstrap_failed"
    assert call_args[1]["event_type"] == "runtime.bootstrap_error"


def test_build_sustained_identity_key_candidates_includes_scope_and_prior_keys() -> None:
    finding = AnomalyFinding(
        finding_id="VOLUME_DROP:prod|cluster-a|orders",
        anomaly_family="VOLUME_DROP",
        scope=("prod", "cluster-a", "orders"),
        severity="MEDIUM",
        reason_codes=("DETECTED",),
        evidence_required=("topic_messages_in_per_sec",),
        is_primary=True,
    )
    keys = __main__._build_sustained_identity_key_candidates(
        anomaly_findings=(finding,),
        evidence_scopes={
            ("prod", "cluster-a", "orders"),
            ("prod", "cluster-a", "group-a", "orders"),
        },
        prior_identity_keys={("prod", "cluster-a", "topic:payments", "VOLUME_DROP")},
    )

    assert ("prod", "cluster-a", "topic:orders", "VOLUME_DROP") in keys
    assert ("prod", "cluster-a", "topic:orders", "THROUGHPUT_CONSTRAINED_PROXY") in keys
    assert ("prod", "cluster-a", "group:group-a", "CONSUMER_LAG") in keys
    assert ("prod", "cluster-a", "topic:payments", "VOLUME_DROP") in keys


def test_resolve_routing_context_for_scope_prefers_exact_scope_match() -> None:
    scope = ("prod", "cluster-a", "group-a", "orders")
    exact = object()
    topic_fallback = object()
    resolved = __main__._resolve_routing_context_for_scope(
        scope=scope,
        routing_by_scope={
            scope: exact,
            ("prod", "cluster-a", "orders"): topic_fallback,
        },
    )
    assert resolved is exact


def test_resolve_routing_context_for_scope_falls_back_to_topic_scope_for_group_scopes() -> None:
    resolved = __main__._resolve_routing_context_for_scope(
        scope=("prod", "cluster-a", "group-a", "orders"),
        routing_by_scope={
            ("prod", "cluster-a", "orders"): "topic-routing",
        },
    )
    assert resolved == "topic-routing"


def test_load_peak_baseline_windows_uses_cached_topic_baseline(monkeypatch) -> None:
    scope = ("prod", "cluster-a", "orders")
    monkeypatch.setattr(
        __main__,
        "load_metric_baselines",
        lambda **_: {scope: {"topic_messages_in_per_sec": 123.0}},
    )

    windows = __main__._load_peak_baseline_windows(redis_client=object(), scopes=[scope])

    assert windows == {scope: (123.0,)}


def test_peak_history_retention_bounds_depth_and_evicts_stale_scopes() -> None:
    retention = __main__._PeakHistoryRetention(
        max_depth=2,
        max_scopes=2,
        max_idle_cycles=1,
    )

    cycle1 = retention.update(
        scopes=[("prod", "cluster-a", "orders"), ("prod", "cluster-a", "payments")],
        baseline_values_by_scope={
            ("prod", "cluster-a", "orders"): 100.0,
            ("prod", "cluster-a", "payments"): 200.0,
        },
    )
    assert cycle1[("prod", "cluster-a", "orders")] == (100.0,)
    assert cycle1[("prod", "cluster-a", "payments")] == (200.0,)

    cycle2 = retention.update(
        scopes=[("prod", "cluster-a", "orders"), ("prod", "cluster-a", "inventory")],
        baseline_values_by_scope={
            ("prod", "cluster-a", "orders"): 110.0,
            ("prod", "cluster-a", "inventory"): 300.0,
        },
    )
    assert cycle2[("prod", "cluster-a", "orders")] == (100.0, 110.0)
    assert cycle2[("prod", "cluster-a", "inventory")] == (300.0,)
    assert ("prod", "cluster-a", "payments") not in cycle2

    cycle3 = retention.update(
        scopes=[("prod", "cluster-a", "inventory")],
        baseline_values_by_scope={("prod", "cluster-a", "inventory"): 305.0},
    )
    assert cycle3[("prod", "cluster-a", "inventory")] == (300.0, 305.0)
    assert ("prod", "cluster-a", "orders") not in cycle3


def test_load_peak_baseline_windows_advances_retention_on_empty_scope_cycles(monkeypatch) -> None:
    scope = ("prod", "cluster-a", "orders")
    retention = __main__._PeakHistoryRetention(
        max_depth=2,
        max_scopes=2,
        max_idle_cycles=1,
    )
    monkeypatch.setattr(
        __main__,
        "load_metric_baselines",
        lambda **_: {scope: {"topic_messages_in_per_sec": 100.0}},
    )

    cycle1 = __main__._load_peak_baseline_windows(
        redis_client=object(),
        scopes=[scope],
        history_retention=retention,
    )
    cycle2 = __main__._load_peak_baseline_windows(
        redis_client=object(),
        scopes=[],
        history_retention=retention,
    )
    cycle3 = __main__._load_peak_baseline_windows(
        redis_client=object(),
        scopes=[],
        history_retention=retention,
    )

    assert cycle1 == {scope: (100.0,)}
    assert cycle2 == {}
    assert cycle3 == {}
    assert retention._cycle == 3
    assert scope not in retention._history_by_scope


def test_peak_history_retention_skips_over_cap_scopes_without_active_scope_churn() -> None:
    retention = __main__._PeakHistoryRetention(
        max_depth=2,
        max_scopes=2,
        max_idle_cycles=3,
    )
    scope_a = ("prod", "cluster-a", "a")
    scope_b = ("prod", "cluster-a", "b")
    scope_c = ("prod", "cluster-a", "c")

    cycle1 = retention.update(
        scopes=[scope_a, scope_b, scope_c],
        baseline_values_by_scope={
            scope_a: 1.0,
            scope_b: 2.0,
            scope_c: 3.0,
        },
    )
    cycle2 = retention.update(
        scopes=[scope_a, scope_b, scope_c],
        baseline_values_by_scope={
            scope_a: 10.0,
            scope_b: 20.0,
            scope_c: 30.0,
        },
    )

    assert set(cycle1.keys()) == {scope_a, scope_b}
    assert set(cycle2.keys()) == {scope_a, scope_b}
    assert cycle2[scope_a] == (1.0, 10.0)
    assert cycle2[scope_b] == (2.0, 20.0)
    assert scope_c not in retention._history_by_scope


# ---------------------------------------------------------------------------
# Story 3.2/3.3 — _cold_path_process_event() wiring regression tests
# ---------------------------------------------------------------------------


def _make_case_header_event(
    case_id: str = "case-main-test-001",
    *,
    final_action: Action = Action.NOTIFY,
):
    """Minimal valid CaseHeaderEventV1 for cold-path processing tests."""
    from datetime import UTC, datetime

    from aiops_triage_pipeline.contracts.case_header_event import CaseHeaderEventV1
    from aiops_triage_pipeline.contracts.enums import CriticalityTier, Environment

    return CaseHeaderEventV1(
        case_id=case_id,
        env=Environment.DEV,
        cluster_id="cluster-unit-test",
        stream_id="stream-unit-test",
        topic="unit-test.events",
        anomaly_family="CONSUMER_LAG",
        criticality_tier=CriticalityTier.TIER_1,
        final_action=final_action,
        routing_key="OWN::Test::Team",
        evaluation_ts=datetime(2026, 3, 22, 18, 0, 0, tzinfo=UTC),
    )


class TestColdPathProcessEventWiring:
    """Story 3.2 AC1+AC2 and Story 3.3 wiring regression coverage."""

    def test_cold_path_process_event_accepts_object_store_client_parameter(
        self, monkeypatch
    ) -> None:
        """3.2-UNIT-201: _cold_path_process_event() accepts object_store_client kwarg."""
        import inspect

        sig = inspect.signature(__main__._cold_path_process_event)
        assert "object_store_client" in sig.parameters, (
            "_cold_path_process_event must accept 'object_store_client' parameter "
            "(Story 3.2 wiring task)"
        )

    def test_cold_path_process_event_calls_retrieve_case_context(
        self, monkeypatch
    ) -> None:
        """3.2-UNIT-202: _cold_path_process_event() calls retrieve_case_context_with_hash()."""
        from unittest.mock import MagicMock, patch

        event = _make_case_header_event(case_id="case-wiring-test-001")

        fake_store = MagicMock()
        logger = MagicMock()
        retrieve_calls: list = []

        with patch.object(
            __main__,
            "retrieve_case_context_with_hash",
            side_effect=lambda **kwargs: retrieve_calls.append(kwargs)
            or SimpleNamespace(excerpt=MagicMock(), triage_hash="a" * 64),
        ):
            __main__._cold_path_process_event(
                event, logger, object_store_client=fake_store
            )

        assert len(retrieve_calls) == 1, (
            "_cold_path_process_event must call retrieve_case_context_with_hash once per event"
        )
        assert retrieve_calls[0].get("case_id") == "case-wiring-test-001"

    def test_cold_path_process_event_calls_build_evidence_summary(
        self, monkeypatch
    ) -> None:
        """3.2-UNIT-203: _cold_path_process_event() calls build_evidence_summary()."""
        from unittest.mock import MagicMock, patch

        event = _make_case_header_event(case_id="case-summary-wiring-001")

        fake_store = MagicMock()
        logger = MagicMock()
        summary_calls: list = []

        fake_excerpt = MagicMock()

        with patch.object(
            __main__,
            "retrieve_case_context_with_hash",
            return_value=SimpleNamespace(excerpt=fake_excerpt, triage_hash="a" * 64),
        ):
            with patch.object(
                __main__,
                "build_evidence_summary",
                side_effect=lambda excerpt: summary_calls.append(excerpt) or "fake-summary",
            ):
                __main__._cold_path_process_event(
                    event, logger, object_store_client=fake_store
                )

        assert len(summary_calls) == 1, (
            "_cold_path_process_event must call build_evidence_summary once per event"
        )
        assert summary_calls[0] is fake_excerpt

    def test_cold_path_process_event_invokes_diagnosis_after_context_and_summary(
        self, monkeypatch
    ) -> None:
        """Story 3.3 wiring: diagnosis is invoked after retrieval + evidence summary."""
        from unittest.mock import MagicMock, patch

        event = _make_case_header_event(case_id="case-diagnosis-wiring-001")
        fake_store = MagicMock()
        logger = MagicMock()
        fake_excerpt = MagicMock()
        run_probe = AsyncMock(return_value=MagicMock())

        with patch.object(
            __main__,
            "retrieve_case_context_with_hash",
            return_value=SimpleNamespace(excerpt=fake_excerpt, triage_hash="b" * 64),
        ):
            with patch.object(__main__, "build_evidence_summary", return_value="summary"):
                with patch.object(__main__, "run_cold_path_diagnosis", run_probe):
                    __main__._cold_path_process_event(
                        event,
                        logger,
                        object_store_client=fake_store,
                    )

        assert run_probe.call_count == 1
        assert run_probe.call_args.kwargs["triage_hash"] == "b" * 64

    def test_cold_path_process_event_invokes_diagnosis_for_observe_case_headers(
        self, monkeypatch
    ) -> None:
        """OBSERVE actions still invoke cold-path diagnosis (all-case semantics)."""
        from unittest.mock import MagicMock, patch

        event = _make_case_header_event(
            case_id="case-observe-cold-path-001",
            final_action=Action.OBSERVE,
        )
        fake_store = MagicMock()
        logger = MagicMock()
        run_probe = AsyncMock(return_value=MagicMock())

        with patch.object(
            __main__,
            "retrieve_case_context_with_hash",
            return_value=SimpleNamespace(excerpt=MagicMock(), triage_hash="c" * 64),
        ):
            with patch.object(__main__, "build_evidence_summary", return_value="summary"):
                with patch.object(__main__, "run_cold_path_diagnosis", run_probe):
                    __main__._cold_path_process_event(
                        event,
                        logger,
                        object_store_client=fake_store,
                    )

        assert run_probe.call_count == 1
        start_log = next(
            (
                call
                for call in logger.info.call_args_list
                if call.args and call.args[0] == "cold_path_diagnosis_start"
            ),
            None,
        )
        assert start_log is not None
        assert start_log.kwargs["final_action"] == "OBSERVE"

    def test_cold_path_process_event_logs_warning_on_retrieval_failure(
        self, monkeypatch
    ) -> None:
        """3.2-UNIT-204: On retrieval failure, log warning + skip (do not raise)."""
        from unittest.mock import MagicMock, patch

        event = _make_case_header_event(case_id="case-failure-test-001")

        fake_store = MagicMock()
        logger = MagicMock()

        with patch.object(
            __main__,
            "retrieve_case_context_with_hash",
            side_effect=RuntimeError("triage.json missing"),
        ):
            # Must NOT raise — must log warning and skip
            __main__._cold_path_process_event(
                event, logger, object_store_client=fake_store
            )

        warning_events = [c.args[0] for c in logger.warning.call_args_list if c.args]
        assert "cold_path_context_retrieval_failed" in warning_events, (
            "Must log 'cold_path_context_retrieval_failed' on retrieval failure"
        )

    def test_cold_path_process_event_logs_warning_on_evidence_summary_failure(
        self, monkeypatch
    ) -> None:
        """3.2-UNIT-205: On evidence summary failure, log warning + skip (do not raise).

        Covers the build_evidence_summary() failure path in _cold_path_process_event.
        """
        from unittest.mock import MagicMock, patch

        event = _make_case_header_event(case_id="case-summary-failure-001")

        fake_store = MagicMock()
        logger = MagicMock()
        fake_excerpt = MagicMock()

        with patch.object(
            __main__,
            "retrieve_case_context_with_hash",
            return_value=SimpleNamespace(excerpt=fake_excerpt, triage_hash="a" * 64),
        ):
            with patch.object(
                __main__,
                "build_evidence_summary",
                side_effect=RuntimeError("summary build failed"),
            ):
                # Must NOT raise — must log warning and skip
                __main__._cold_path_process_event(
                    event, logger, object_store_client=fake_store
                )

        warning_events = [c.args[0] for c in logger.warning.call_args_list if c.args]
        assert "cold_path_evidence_summary_failed" in warning_events, (
            "Must log 'cold_path_evidence_summary_failed' on build_evidence_summary() failure"
        )

    def test_cold_path_process_event_skips_diagnosis_when_stage_already_exists_for_triage_hash(
        self, monkeypatch
    ) -> None:
        """Duplicate case headers should short-circuit when diagnosis.json already matches triage."""
        from unittest.mock import MagicMock, patch

        event = _make_case_header_event(case_id="case-duplicate-diagnosis-001")
        fake_store = MagicMock()
        logger = MagicMock()
        run_probe = AsyncMock(return_value=MagicMock())
        triage_hash = "d" * 64

        with patch.object(
            __main__,
            "retrieve_case_context_with_hash",
            return_value=SimpleNamespace(excerpt=MagicMock(), triage_hash=triage_hash),
        ):
            with patch.object(__main__, "build_evidence_summary", return_value="summary"):
                with patch.object(
                    __main__,
                    "read_casefile_stage_json_or_none",
                    return_value=SimpleNamespace(
                        triage_hash=triage_hash,
                        diagnosis_hash="e" * 64,
                    ),
                ):
                    with patch.object(__main__, "run_cold_path_diagnosis", run_probe):
                        __main__._cold_path_process_event(
                            event,
                            logger,
                            object_store_client=fake_store,
                        )

        assert run_probe.call_count == 0
        info_events = [c.args[0] for c in logger.info.call_args_list if c.args]
        assert "cold_path_diagnosis_already_present" in info_events


@pytest.mark.asyncio
async def test_process_cold_path_message_uses_async_processor_boundary(monkeypatch) -> None:
    """Consumer loop awaits the async processor boundary inside an active event loop."""
    event = _make_case_header_event(case_id="case-async-boundary-001")
    msg = MagicMock()
    msg.error.return_value = None
    msg.value.return_value = event.model_dump_json().encode("utf-8")
    logger = MagicMock()
    process_probe = AsyncMock(return_value=None)
    monkeypatch.setattr(__main__, "_cold_path_process_event_async", process_probe)

    await __main__._process_cold_path_message(
        msg,
        logger,
        object_store_client=MagicMock(),
        llm_client=MagicMock(),
        denylist=MagicMock(),
        health_registry=MagicMock(),
        llm_timeout_seconds=60.0,
        alert_evaluator=MagicMock(),
    )

    assert process_probe.await_count == 1


def _hot_path_settings_for_coordination_tests(*, lock_enabled: bool) -> SimpleNamespace:
    return SimpleNamespace(
        HOT_PATH_SCHEDULER_INTERVAL_SECONDS=300,
        STAGE2_PEAK_HISTORY_MAX_DEPTH=4,
        STAGE2_PEAK_HISTORY_MAX_SCOPES=8,
        STAGE2_PEAK_HISTORY_MAX_IDLE_CYCLES=2,
        STAGE2_SUSTAINED_PARALLEL_MIN_KEYS=64,
        STAGE2_SUSTAINED_PARALLEL_WORKERS=4,
        STAGE2_SUSTAINED_PARALLEL_CHUNK_SIZE=32,
        DISTRIBUTED_CYCLE_LOCK_ENABLED=lock_enabled,
        SHARD_REGISTRY_ENABLED=False,
        HEALTH_SERVER_HOST="127.0.0.1",
        HEALTH_SERVER_PORT=0,
    )


def _patch_hot_path_case_processing_dependencies(
    monkeypatch: pytest.MonkeyPatch,
    *,
    scope: tuple[str, str, str],
    gate_input: object,
    decision: object,
) -> MagicMock:
    tick = SimpleNamespace(
        expected_boundary=datetime(2026, 3, 23, 12, 0, tzinfo=UTC),
        drift_seconds=0,
        missed_intervals=0,
    )
    monkeypatch.setattr(__main__, "evaluate_scheduler_tick", lambda **_: tick)
    monkeypatch.setattr(
        __main__,
        "next_interval_boundary",
        lambda *_args, **_kwargs: datetime.now(UTC),
    )
    monkeypatch.setattr(
        __main__,
        "emit_redis_degraded_mode_events",
        AsyncMock(return_value=()),
    )
    monkeypatch.setattr(
        __main__.asyncio,
        "sleep",
        AsyncMock(side_effect=asyncio.CancelledError()),
    )
    registry = MagicMock()
    registry.update = AsyncMock()
    monkeypatch.setattr(__main__, "get_health_registry", lambda: registry)
    mock_server = MagicMock()
    mock_server.serve_forever = AsyncMock()
    monkeypatch.setattr(
        "aiops_triage_pipeline.__main__.start_health_server",
        AsyncMock(return_value=mock_server),
    )

    topology_loader = MagicMock()
    topology_loader.get_snapshot.return_value = SimpleNamespace(
        metadata=SimpleNamespace(input_version=2)
    )
    monkeypatch.setattr(
        __main__,
        "run_evidence_stage_cycle",
        AsyncMock(
            return_value=SimpleNamespace(
                rows=(),
                anomaly_result=SimpleNamespace(findings=()),
                evidence_status_map_by_scope={},
            )
        ),
    )
    monkeypatch.setattr(__main__, "load_sustained_window_states", lambda **_: {})
    monkeypatch.setattr(__main__, "load_peak_profiles", lambda **_: {})
    monkeypatch.setattr(
        __main__,
        "run_peak_stage_cycle",
        lambda **_: SimpleNamespace(
            sustained_by_key={},
            profiles_by_scope={},
        ),
    )
    monkeypatch.setattr(__main__, "persist_sustained_window_states", MagicMock())
    monkeypatch.setattr(__main__, "persist_peak_profiles", MagicMock())
    monkeypatch.setattr(
        __main__,
        "run_topology_stage_cycle",
        lambda **_: SimpleNamespace(
            context_by_scope={scope: object()},
            routing_by_scope={scope: object()},
        ),
    )
    monkeypatch.setattr(
        __main__,
        "run_gate_input_stage_cycle",
        lambda **_: {scope: (gate_input,)},
    )
    monkeypatch.setattr(
        __main__,
        "run_gate_decision_stage_cycle",
        lambda **_: {scope: (decision,)},
    )
    return topology_loader


@pytest.mark.asyncio
async def test_hot_path_scheduler_skips_stage_execution_when_cycle_lock_yielded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tick = SimpleNamespace(
        expected_boundary=datetime(2026, 3, 23, 12, 0, tzinfo=UTC),
        drift_seconds=0,
        missed_intervals=0,
    )
    monkeypatch.setattr(__main__, "evaluate_scheduler_tick", lambda **_: tick)
    monkeypatch.setattr(
        __main__,
        "next_interval_boundary",
        lambda *_args, **_kwargs: datetime.now(UTC),
    )
    monkeypatch.setattr(__main__, "record_cycle_lock_yielded", MagicMock())
    monkeypatch.setattr(__main__, "record_cycle_lock_acquired", MagicMock())
    monkeypatch.setattr(__main__, "record_cycle_lock_fail_open", MagicMock())
    monkeypatch.setattr(
        __main__,
        "emit_redis_degraded_mode_events",
        AsyncMock(return_value=()),
    )
    monkeypatch.setattr(
        __main__,
        "run_evidence_stage_cycle",
        AsyncMock(side_effect=AssertionError("yielded path must skip stage execution")),
    )
    monkeypatch.setattr(
        __main__.asyncio,
        "sleep",
        AsyncMock(side_effect=asyncio.CancelledError()),
    )
    registry = MagicMock()
    registry.update = AsyncMock()
    monkeypatch.setattr(__main__, "get_health_registry", lambda: registry)

    cycle_lock = MagicMock()
    cycle_lock.acquire.return_value = SimpleNamespace(
        status=CycleLockStatus.yielded,
        key="aiops:lock:cycle",
        ttl_seconds=360,
        holder_id="pod-b",
    )
    topology_loader = MagicMock()
    mock_server = MagicMock()
    mock_server.serve_forever = AsyncMock()
    monkeypatch.setattr(
        "aiops_triage_pipeline.__main__.start_health_server",
        AsyncMock(return_value=mock_server),
    )

    coordination_state = _HotPathCoordinationState(enabled=True)
    with pytest.raises(asyncio.CancelledError):
        await __main__._hot_path_scheduler_loop(
            settings=_hot_path_settings_for_coordination_tests(lock_enabled=True),
            logger=MagicMock(),
            alert_evaluator=MagicMock(),
            prometheus_client=MagicMock(),
            metric_queries={},
            anomaly_detection_policy=MagicMock(),
            peak_policy=MagicMock(),
            rulebook_policy=MagicMock(),
            redis_ttl_policy=MagicMock(),
            prometheus_metrics_contract=MagicMock(),
            denylist=MagicMock(),
            redis_client=MagicMock(),
            dedupe_store=MagicMock(),
            object_store_client=MagicMock(),
            outbox_repository=MagicMock(),
            pd_client=MagicMock(),
            slack_client=MagicMock(),
            topology_loader=topology_loader,
            cycle_lock=cycle_lock,
            cycle_lock_owner_id="pod-a",
            coordination_state=coordination_state,
        )

    cycle_lock.acquire.assert_called_once_with(interval_seconds=300, owner_id="pod-a")
    assert topology_loader.reload_if_changed.call_count == 0
    __main__.record_cycle_lock_yielded.assert_called_once()
    assert coordination_state.is_lock_holder is False
    assert coordination_state.lock_holder_id == "pod-b"
    assert coordination_state.lock_ttl_seconds == 360


@pytest.mark.asyncio
async def test_hot_path_scheduler_fail_open_continues_to_pipeline_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tick = SimpleNamespace(
        expected_boundary=datetime(2026, 3, 23, 12, 0, tzinfo=UTC),
        drift_seconds=0,
        missed_intervals=0,
    )
    monkeypatch.setattr(__main__, "evaluate_scheduler_tick", lambda **_: tick)
    monkeypatch.setattr(__main__, "record_cycle_lock_fail_open", MagicMock())
    monkeypatch.setattr(__main__, "record_cycle_lock_yielded", MagicMock())
    monkeypatch.setattr(__main__, "record_cycle_lock_acquired", MagicMock())

    registry = MagicMock()
    registry.update = AsyncMock()
    monkeypatch.setattr(__main__, "get_health_registry", lambda: registry)

    cycle_lock = MagicMock()
    cycle_lock.acquire.return_value = SimpleNamespace(
        status=CycleLockStatus.fail_open,
        key="aiops:lock:cycle",
        ttl_seconds=360,
        reason="redis unavailable",
    )
    topology_loader = MagicMock()
    topology_loader.reload_if_changed.side_effect = asyncio.CancelledError()
    mock_server = MagicMock()
    mock_server.serve_forever = AsyncMock()
    monkeypatch.setattr(
        "aiops_triage_pipeline.__main__.start_health_server",
        AsyncMock(return_value=mock_server),
    )

    coordination_state = _HotPathCoordinationState(enabled=True)
    with pytest.raises(asyncio.CancelledError):
        await __main__._hot_path_scheduler_loop(
            settings=_hot_path_settings_for_coordination_tests(lock_enabled=True),
            logger=MagicMock(),
            alert_evaluator=MagicMock(),
            prometheus_client=MagicMock(),
            metric_queries={},
            anomaly_detection_policy=MagicMock(),
            peak_policy=MagicMock(),
            rulebook_policy=MagicMock(),
            redis_ttl_policy=MagicMock(),
            prometheus_metrics_contract=MagicMock(),
            denylist=MagicMock(),
            redis_client=MagicMock(),
            dedupe_store=MagicMock(),
            object_store_client=MagicMock(),
            outbox_repository=MagicMock(),
            pd_client=MagicMock(),
            slack_client=MagicMock(),
            topology_loader=topology_loader,
            cycle_lock=cycle_lock,
            cycle_lock_owner_id="pod-a",
            coordination_state=coordination_state,
        )

    cycle_lock.acquire.assert_called_once_with(interval_seconds=300, owner_id="pod-a")
    assert topology_loader.reload_if_changed.call_count == 1
    __main__.record_cycle_lock_fail_open.assert_called_once_with(reason="redis unavailable")
    assert coordination_state.is_lock_holder is True
    assert coordination_state.lock_holder_id is None
    assert coordination_state.lock_ttl_seconds is None


@pytest.mark.asyncio
async def test_hot_path_scheduler_does_not_attempt_lock_when_feature_flag_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tick = SimpleNamespace(
        expected_boundary=datetime(2026, 3, 23, 12, 0, tzinfo=UTC),
        drift_seconds=0,
        missed_intervals=0,
    )
    monkeypatch.setattr(__main__, "evaluate_scheduler_tick", lambda **_: tick)
    topology_loader = MagicMock()
    topology_loader.reload_if_changed.side_effect = asyncio.CancelledError()

    cycle_lock = MagicMock()
    mock_server = MagicMock()
    mock_server.serve_forever = AsyncMock()
    monkeypatch.setattr(
        "aiops_triage_pipeline.__main__.start_health_server",
        AsyncMock(return_value=mock_server),
    )

    with pytest.raises(asyncio.CancelledError):
        await __main__._hot_path_scheduler_loop(
            settings=_hot_path_settings_for_coordination_tests(lock_enabled=False),
            logger=MagicMock(),
            alert_evaluator=MagicMock(),
            prometheus_client=MagicMock(),
            metric_queries={},
            anomaly_detection_policy=MagicMock(),
            peak_policy=MagicMock(),
            rulebook_policy=MagicMock(),
            redis_ttl_policy=MagicMock(),
            prometheus_metrics_contract=MagicMock(),
            denylist=MagicMock(),
            redis_client=MagicMock(),
            dedupe_store=MagicMock(),
            object_store_client=MagicMock(),
            outbox_repository=MagicMock(),
            pd_client=MagicMock(),
            slack_client=MagicMock(),
            topology_loader=topology_loader,
            cycle_lock=cycle_lock,
            cycle_lock_owner_id="pod-a",
            coordination_state=_HotPathCoordinationState(),
        )

    cycle_lock.acquire.assert_not_called()


@pytest.mark.asyncio
async def test_hot_path_scheduler_skips_casefile_pipeline_when_existing_triage_found(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scope = ("prod", "cluster-a", "orders")
    gate_input = SimpleNamespace(action_fingerprint="fp-existing")
    decision = SimpleNamespace(action_fingerprint="fp-existing")
    topology_loader = _patch_hot_path_case_processing_dependencies(
        monkeypatch,
        scope=scope,
        gate_input=gate_input,
        decision=decision,
    )
    existing_lookup = MagicMock(return_value=SimpleNamespace(case_id="case-existing"))
    assemble_stage = MagicMock()
    persist_stage = MagicMock()
    dispatch_stage = MagicMock()
    monkeypatch.setattr(__main__, "get_existing_casefile_triage", existing_lookup)
    monkeypatch.setattr(__main__, "assemble_casefile_triage_stage", assemble_stage)
    monkeypatch.setattr(__main__, "persist_casefile_and_prepare_outbox_ready", persist_stage)
    monkeypatch.setattr(__main__, "dispatch_action", dispatch_stage)

    outbox_repository = MagicMock()
    logger = MagicMock()

    with pytest.raises(asyncio.CancelledError):
        await __main__._hot_path_scheduler_loop(
            settings=_hot_path_settings_for_coordination_tests(lock_enabled=False),
            logger=logger,
            alert_evaluator=MagicMock(),
            prometheus_client=MagicMock(),
            metric_queries={},
            anomaly_detection_policy=SimpleNamespace(schema_version="v1"),
            peak_policy=MagicMock(),
            rulebook_policy=MagicMock(),
            redis_ttl_policy=MagicMock(),
            prometheus_metrics_contract=MagicMock(),
            denylist=MagicMock(),
            redis_client=MagicMock(),
            dedupe_store=MagicMock(),
            object_store_client=MagicMock(),
            outbox_repository=outbox_repository,
            pd_client=MagicMock(),
            slack_client=MagicMock(),
            topology_loader=topology_loader,
            cycle_lock=MagicMock(),
            cycle_lock_owner_id="pod-a",
            coordination_state=_HotPathCoordinationState(),
        )

    existing_lookup.assert_called_once()
    assemble_stage.assert_not_called()
    persist_stage.assert_not_called()
    outbox_repository.insert_pending_object.assert_not_called()
    dispatch_stage.assert_not_called()
    skip_log = next(
        (
            call
            for call in logger.info.call_args_list
            if call.args and call.args[0] == "casefile_triage_already_exists"
        ),
        None,
    )
    assert skip_log is not None
    assert skip_log.kwargs["event_type"] == "casefile.triage_already_exists"
    assert skip_log.kwargs["case_id"] == "case-existing"
    assert skip_log.kwargs["scope"] == scope


@pytest.mark.asyncio
async def test_hot_path_scheduler_skips_casefile_pipeline_for_invalid_existing_triage_value_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scope = ("prod", "cluster-a", "orders")
    gate_input = SimpleNamespace(action_fingerprint="fp-invalid-triage")
    decision = SimpleNamespace(action_fingerprint="fp-invalid-triage")
    topology_loader = _patch_hot_path_case_processing_dependencies(
        monkeypatch,
        scope=scope,
        gate_input=gate_input,
        decision=decision,
    )
    monkeypatch.setattr(
        __main__,
        "get_existing_casefile_triage",
        MagicMock(side_effect=ValueError(__main__._CASEFILE_TRIAGE_HASH_MISMATCH_ERROR)),
    )
    assemble_stage = MagicMock()
    persist_stage = MagicMock()
    dispatch_stage = MagicMock()
    monkeypatch.setattr(__main__, "assemble_casefile_triage_stage", assemble_stage)
    monkeypatch.setattr(__main__, "persist_casefile_and_prepare_outbox_ready", persist_stage)
    monkeypatch.setattr(__main__, "dispatch_action", dispatch_stage)

    outbox_repository = MagicMock()
    logger = MagicMock()

    with pytest.raises(asyncio.CancelledError):
        await __main__._hot_path_scheduler_loop(
            settings=_hot_path_settings_for_coordination_tests(lock_enabled=False),
            logger=logger,
            alert_evaluator=MagicMock(),
            prometheus_client=MagicMock(),
            metric_queries={},
            anomaly_detection_policy=SimpleNamespace(schema_version="v1"),
            peak_policy=MagicMock(),
            rulebook_policy=MagicMock(),
            redis_ttl_policy=MagicMock(),
            prometheus_metrics_contract=MagicMock(),
            denylist=MagicMock(),
            redis_client=MagicMock(),
            dedupe_store=MagicMock(),
            object_store_client=MagicMock(),
            outbox_repository=outbox_repository,
            pd_client=MagicMock(),
            slack_client=MagicMock(),
            topology_loader=topology_loader,
            cycle_lock=MagicMock(),
            cycle_lock_owner_id="pod-a",
            coordination_state=_HotPathCoordinationState(),
        )

    assemble_stage.assert_not_called()
    persist_stage.assert_not_called()
    outbox_repository.insert_pending_object.assert_not_called()
    dispatch_stage.assert_not_called()
    invalid_triage_log = next(
        (
            call
            for call in logger.warning.call_args_list
            if call.args and call.args[0] == "hot_path_existing_casefile_triage_invalid"
        ),
        None,
    )
    assert invalid_triage_log is not None
    assert invalid_triage_log.kwargs["event_type"] == "casefile.invalid_existing_triage"
    assert invalid_triage_log.kwargs["scope"] == scope
    assert invalid_triage_log.kwargs["action_fingerprint"] == "fp-invalid-triage"
    assert __main__._CASEFILE_TRIAGE_HASH_MISMATCH_ERROR in invalid_triage_log.kwargs["error"]
    case_error_log = next(
        (
            call
            for call in logger.error.call_args_list
            if call.args and call.args[0] == "hot_path_case_processing_failed"
        ),
        None,
    )
    assert case_error_log is None


@pytest.mark.asyncio
async def test_hot_path_scheduler_logs_outbox_audit_signal_for_observe_cases(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scope = ("harness", "cluster-a", "orders")
    gate_input = SimpleNamespace(action_fingerprint="fp-observe")
    decision = SimpleNamespace(
        action_fingerprint="fp-observe",
        final_action=Action.OBSERVE,
        gate_reason_codes=("INSUFFICIENT_HISTORY", "NOT_SUSTAINED", "AG4_CAP"),
    )
    topology_loader = _patch_hot_path_case_processing_dependencies(
        monkeypatch,
        scope=scope,
        gate_input=gate_input,
        decision=decision,
    )
    monkeypatch.setattr(__main__, "get_existing_casefile_triage", MagicMock(return_value=None))
    casefile = SimpleNamespace(case_id="case-observe-audit-001")
    outbox_ready = SimpleNamespace(case_id="case-observe-audit-001")
    assemble_stage = MagicMock(return_value=casefile)
    persist_stage = MagicMock(return_value=outbox_ready)
    dispatch_stage = MagicMock()
    monkeypatch.setattr(__main__, "assemble_casefile_triage_stage", assemble_stage)
    monkeypatch.setattr(__main__, "persist_casefile_and_prepare_outbox_ready", persist_stage)
    monkeypatch.setattr(__main__, "dispatch_action", dispatch_stage)

    outbox_repository = MagicMock()
    logger = MagicMock()

    with pytest.raises(asyncio.CancelledError):
        await __main__._hot_path_scheduler_loop(
            settings=_hot_path_settings_for_coordination_tests(lock_enabled=False),
            logger=logger,
            alert_evaluator=MagicMock(),
            prometheus_client=MagicMock(),
            metric_queries={},
            anomaly_detection_policy=SimpleNamespace(schema_version="v1"),
            peak_policy=MagicMock(),
            rulebook_policy=MagicMock(),
            redis_ttl_policy=MagicMock(),
            prometheus_metrics_contract=MagicMock(),
            denylist=MagicMock(),
            redis_client=MagicMock(),
            dedupe_store=MagicMock(),
            object_store_client=MagicMock(),
            outbox_repository=outbox_repository,
            pd_client=MagicMock(),
            slack_client=MagicMock(),
            topology_loader=topology_loader,
            cycle_lock=MagicMock(),
            cycle_lock_owner_id="pod-a",
            coordination_state=_HotPathCoordinationState(),
        )

    assemble_stage.assert_called_once()
    persist_stage.assert_called_once()
    outbox_repository.insert_pending_object.assert_called_once_with(confirmed_casefile=outbox_ready)
    outbox_repository.transition_to_ready.assert_called_once_with(case_id=outbox_ready.case_id)
    dispatch_stage.assert_called_once()
    audit_log = next(
        (
            call
            for call in logger.info.call_args_list
            if call.args and call.args[0] == "hot_path_case_outbox_enqueued"
        ),
        None,
    )
    assert audit_log is not None
    assert audit_log.kwargs["event_type"] == "hot_path.case_outbox_enqueued"
    assert audit_log.kwargs["case_id"] == "case-observe-audit-001"
    assert audit_log.kwargs["scope"] == scope
    assert audit_log.kwargs["final_action"] == "OBSERVE"
    assert audit_log.kwargs["includes_insufficient_history"] is True
    assert audit_log.kwargs["includes_not_sustained"] is True


@pytest.mark.asyncio
async def test_hot_path_scheduler_logs_case_error_for_non_targeted_lookup_value_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scope = ("prod", "cluster-a", "orders")
    gate_input = SimpleNamespace(action_fingerprint="fp-non-targeted-value-error")
    decision = SimpleNamespace(action_fingerprint="fp-non-targeted-value-error")
    topology_loader = _patch_hot_path_case_processing_dependencies(
        monkeypatch,
        scope=scope,
        gate_input=gate_input,
        decision=decision,
    )
    monkeypatch.setattr(
        __main__,
        "get_existing_casefile_triage",
        MagicMock(side_effect=ValueError("unexpected lookup value error")),
    )
    assemble_stage = MagicMock()
    persist_stage = MagicMock()
    dispatch_stage = MagicMock()
    monkeypatch.setattr(__main__, "assemble_casefile_triage_stage", assemble_stage)
    monkeypatch.setattr(__main__, "persist_casefile_and_prepare_outbox_ready", persist_stage)
    monkeypatch.setattr(__main__, "dispatch_action", dispatch_stage)

    logger = MagicMock()

    with pytest.raises(asyncio.CancelledError):
        await __main__._hot_path_scheduler_loop(
            settings=_hot_path_settings_for_coordination_tests(lock_enabled=False),
            logger=logger,
            alert_evaluator=MagicMock(),
            prometheus_client=MagicMock(),
            metric_queries={},
            anomaly_detection_policy=SimpleNamespace(schema_version="v1"),
            peak_policy=MagicMock(),
            rulebook_policy=MagicMock(),
            redis_ttl_policy=MagicMock(),
            prometheus_metrics_contract=MagicMock(),
            denylist=MagicMock(),
            redis_client=MagicMock(),
            dedupe_store=MagicMock(),
            object_store_client=MagicMock(),
            outbox_repository=MagicMock(),
            pd_client=MagicMock(),
            slack_client=MagicMock(),
            topology_loader=topology_loader,
            cycle_lock=MagicMock(),
            cycle_lock_owner_id="pod-a",
            coordination_state=_HotPathCoordinationState(),
        )

    assemble_stage.assert_not_called()
    persist_stage.assert_not_called()
    dispatch_stage.assert_not_called()
    invalid_triage_log = next(
        (
            call
            for call in logger.warning.call_args_list
            if call.args and call.args[0] == "hot_path_existing_casefile_triage_invalid"
        ),
        None,
    )
    assert invalid_triage_log is None
    case_error_log = next(
        (
            call
            for call in logger.error.call_args_list
            if call.args and call.args[0] == "hot_path_case_processing_failed"
        ),
        None,
    )
    assert case_error_log is not None
    assert case_error_log.kwargs["event_type"] == "hot_path.case_error"
    assert case_error_log.kwargs["scope"] == scope
    assert case_error_log.kwargs["action_fingerprint"] == "fp-non-targeted-value-error"
    assert case_error_log.kwargs["exc_info"] is True


@pytest.mark.asyncio
async def test_hot_path_scheduler_logs_case_error_when_lookup_raises_integration_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scope = ("prod", "cluster-a", "orders")
    gate_input = SimpleNamespace(action_fingerprint="fp-error")
    decision = SimpleNamespace(action_fingerprint="fp-error")
    topology_loader = _patch_hot_path_case_processing_dependencies(
        monkeypatch,
        scope=scope,
        gate_input=gate_input,
        decision=decision,
    )
    monkeypatch.setattr(
        __main__,
        "get_existing_casefile_triage",
        MagicMock(side_effect=IntegrationError("minio read failed")),
    )
    assemble_stage = MagicMock()
    persist_stage = MagicMock()
    dispatch_stage = MagicMock()
    monkeypatch.setattr(__main__, "assemble_casefile_triage_stage", assemble_stage)
    monkeypatch.setattr(__main__, "persist_casefile_and_prepare_outbox_ready", persist_stage)
    monkeypatch.setattr(__main__, "dispatch_action", dispatch_stage)

    logger = MagicMock()

    with pytest.raises(asyncio.CancelledError):
        await __main__._hot_path_scheduler_loop(
            settings=_hot_path_settings_for_coordination_tests(lock_enabled=False),
            logger=logger,
            alert_evaluator=MagicMock(),
            prometheus_client=MagicMock(),
            metric_queries={},
            anomaly_detection_policy=SimpleNamespace(schema_version="v1"),
            peak_policy=MagicMock(),
            rulebook_policy=MagicMock(),
            redis_ttl_policy=MagicMock(),
            prometheus_metrics_contract=MagicMock(),
            denylist=MagicMock(),
            redis_client=MagicMock(),
            dedupe_store=MagicMock(),
            object_store_client=MagicMock(),
            outbox_repository=MagicMock(),
            pd_client=MagicMock(),
            slack_client=MagicMock(),
            topology_loader=topology_loader,
            cycle_lock=MagicMock(),
            cycle_lock_owner_id="pod-a",
            coordination_state=_HotPathCoordinationState(),
        )

    assemble_stage.assert_not_called()
    persist_stage.assert_not_called()
    dispatch_stage.assert_not_called()
    case_error_log = next(
        (
            call
            for call in logger.error.call_args_list
            if call.args and call.args[0] == "hot_path_case_processing_failed"
        ),
        None,
    )
    assert case_error_log is not None
    assert case_error_log.kwargs["event_type"] == "hot_path.case_error"
    assert case_error_log.kwargs["scope"] == scope
    assert case_error_log.kwargs["action_fingerprint"] == "fp-error"
    assert case_error_log.kwargs["exc_info"] is True


def _hot_path_settings_for_shard_tests(*, shard_enabled: bool) -> SimpleNamespace:
    """Settings fixture for shard-flag gate tests in test_main.py."""
    return SimpleNamespace(
        HOT_PATH_SCHEDULER_INTERVAL_SECONDS=300,
        STAGE2_PEAK_HISTORY_MAX_DEPTH=4,
        STAGE2_PEAK_HISTORY_MAX_SCOPES=8,
        STAGE2_PEAK_HISTORY_MAX_IDLE_CYCLES=2,
        STAGE2_SUSTAINED_PARALLEL_MIN_KEYS=64,
        STAGE2_SUSTAINED_PARALLEL_WORKERS=4,
        STAGE2_SUSTAINED_PARALLEL_CHUNK_SIZE=32,
        DISTRIBUTED_CYCLE_LOCK_ENABLED=False,
        SHARD_REGISTRY_ENABLED=shard_enabled,
        SHARD_COORDINATION_SHARD_COUNT=2,
        SHARD_LEASE_TTL_SECONDS=270,
        SHARD_CHECKPOINT_TTL_SECONDS=660,
        HEALTH_SERVER_HOST="127.0.0.1",
        HEALTH_SERVER_PORT=0,
    )


def _make_shard_loop_call(monkeypatch, settings, shard_coordinator):
    """Shared helper: run _hot_path_scheduler_loop up to the topology reload (after shard gate)."""
    tick = SimpleNamespace(
        expected_boundary=datetime(2026, 3, 23, 12, 0, tzinfo=UTC),
        drift_seconds=0,
        missed_intervals=0,
    )
    monkeypatch.setattr(__main__, "evaluate_scheduler_tick", lambda **_: tick)
    topology_loader = MagicMock()
    topology_loader.reload_if_changed.side_effect = asyncio.CancelledError()
    cycle_lock = MagicMock()
    cycle_lock.acquire.return_value = SimpleNamespace(
        status=CycleLockStatus.acquired,
        key="aiops:lock:cycle",
        ttl_seconds=360,
    )
    registry = MagicMock()
    registry.update = AsyncMock()
    monkeypatch.setattr(__main__, "get_health_registry", lambda: registry)
    monkeypatch.setattr(__main__, "record_cycle_lock_acquired", MagicMock())
    monkeypatch.setattr(__main__, "set_shard_interval_checkpoint", MagicMock())
    mock_server = MagicMock()
    mock_server.serve_forever = AsyncMock()
    monkeypatch.setattr(
        "aiops_triage_pipeline.__main__.start_health_server",
        AsyncMock(return_value=mock_server),
    )

    return dict(
        settings=settings,
        logger=MagicMock(),
        alert_evaluator=MagicMock(),
        prometheus_client=MagicMock(),
        metric_queries={},
        anomaly_detection_policy=MagicMock(),
        peak_policy=MagicMock(),
        rulebook_policy=MagicMock(),
        redis_ttl_policy=MagicMock(),
        prometheus_metrics_contract=MagicMock(),
        denylist=MagicMock(),
        redis_client=MagicMock(),
        dedupe_store=MagicMock(),
        object_store_client=MagicMock(),
        outbox_repository=MagicMock(),
        pd_client=MagicMock(),
        slack_client=MagicMock(),
        topology_loader=topology_loader,
        cycle_lock=cycle_lock,
        cycle_lock_owner_id="pod-a",
        shard_coordinator=shard_coordinator,
        coordination_state=_HotPathCoordinationState(),
    )


@pytest.mark.asyncio
async def test_hot_path_scheduler_does_not_call_acquire_lease_when_shard_flag_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """SHARD_REGISTRY_ENABLED=False → shard_coordinator.acquire_lease never called (AC 1).

    Passes a non-None shard_coordinator so the test exercises the flag-guard condition
    ``if settings.SHARD_REGISTRY_ENABLED and shard_coordinator is not None`` in
    ``_hot_path_scheduler_loop``, not just the None-coordinator short-circuit.
    """
    shard_coordinator = MagicMock()
    kwargs = _make_shard_loop_call(
        monkeypatch,
        _hot_path_settings_for_shard_tests(shard_enabled=False),
        shard_coordinator,
    )

    with pytest.raises(asyncio.CancelledError):
        await __main__._hot_path_scheduler_loop(**kwargs)

    shard_coordinator.acquire_lease.assert_not_called()


@pytest.mark.asyncio
async def test_hot_path_scheduler_calls_acquire_lease_for_each_shard_when_flag_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """SHARD_REGISTRY_ENABLED=True → acquire_lease called once per configured shard (AC 2)."""
    from aiops_triage_pipeline.coordination.shard_registry import (  # noqa: PLC0415
        ShardLeaseOutcome,
        ShardLeaseStatus,
    )

    shard_coordinator = MagicMock()
    shard_coordinator.acquire_lease.return_value = ShardLeaseOutcome(
        status=ShardLeaseStatus.acquired,
        shard_id=0,
        owner_id="pod-a",
        ttl_seconds=270,
    )
    monkeypatch.setattr(__main__, "record_shard_checkpoint_written", MagicMock())
    kwargs = _make_shard_loop_call(
        monkeypatch,
        _hot_path_settings_for_shard_tests(shard_enabled=True),
        shard_coordinator,
    )

    with pytest.raises(asyncio.CancelledError):
        await __main__._hot_path_scheduler_loop(**kwargs)

    # SHARD_COORDINATION_SHARD_COUNT=2, so acquire_lease is called twice (once per shard)
    assert shard_coordinator.acquire_lease.call_count == 2


@pytest.mark.asyncio
async def test_hot_path_scheduler_wires_shard_lease_ttl_from_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """acquire_lease receives lease_ttl_seconds from settings, not a hardcoded constant."""
    from aiops_triage_pipeline.coordination.shard_registry import (  # noqa: PLC0415
        ShardLeaseOutcome,
        ShardLeaseStatus,
    )

    shard_coordinator = MagicMock()
    shard_coordinator.acquire_lease.return_value = ShardLeaseOutcome(
        status=ShardLeaseStatus.acquired,
        shard_id=0,
        owner_id="pod-a",
        ttl_seconds=211,
    )

    settings = _hot_path_settings_for_shard_tests(shard_enabled=True)
    settings.SHARD_LEASE_TTL_SECONDS = 211

    monkeypatch.setattr(__main__, "record_shard_checkpoint_written", MagicMock())
    kwargs = _make_shard_loop_call(monkeypatch, settings, shard_coordinator)

    with pytest.raises(asyncio.CancelledError):
        await __main__._hot_path_scheduler_loop(**kwargs)

    for call in shard_coordinator.acquire_lease.call_args_list:
        assert call.kwargs["lease_ttl_seconds"] == 211
