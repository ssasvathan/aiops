from __future__ import annotations

import sys

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
