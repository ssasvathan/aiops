"""Global pytest hooks and shared fixtures."""

from __future__ import annotations

import pytest


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    """Treat skipped tests as a suite failure.

    Sprint quality gates require full execution coverage (no silent skips).
    """
    del exitstatus
    terminal_reporter = session.config.pluginmanager.get_plugin("terminalreporter")
    if terminal_reporter is None:
        return

    skipped_reports = terminal_reporter.stats.get("skipped", [])
    if not skipped_reports:
        return

    skipped_count = len(skipped_reports)
    terminal_reporter.write_sep(
        "=",
        f"NO-SKIP POLICY VIOLATION: {skipped_count} test(s) were skipped. "
        "Fix prerequisites or test setup instead of skipping.",
    )
    session.exitstatus = int(pytest.ExitCode.TESTS_FAILED)
