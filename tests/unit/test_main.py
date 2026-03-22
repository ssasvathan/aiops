from __future__ import annotations

import sys
from unittest.mock import MagicMock

import pytest

from aiops_triage_pipeline import __main__
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


def test_run_cold_path_bootstraps_and_logs_warning(monkeypatch) -> None:
    modes: list[str] = []
    fake_bootstrap, logger = _make_mock_bootstrap(modes)
    monkeypatch.setattr(__main__, "_bootstrap_mode", fake_bootstrap)

    __main__._run_cold_path()

    assert modes == ["cold-path"]
    logger.warning.assert_called_once()
    call_args = logger.warning.call_args
    assert call_args[0][0] == "cold_path_mode_exiting"
    assert call_args[1]["event_type"] == "runtime.mode_stub"


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
