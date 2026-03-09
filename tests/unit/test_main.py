from __future__ import annotations

import sys
from unittest.mock import MagicMock

import pytest

from aiops_triage_pipeline import __main__


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
