"""ATDD red-phase acceptance tests for Story 2.5 casefile lifecycle retention purge."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

from aiops_triage_pipeline import __main__, health
from aiops_triage_pipeline.storage.lifecycle import (
    CasefileLifecycleRunner,
    CasefileLifecycleRunResult,
)
from tests.atdd.fixtures.story_2_5_test_data import (
    InMemoryLifecycleObjectStore,
    RecordingLogger,
    build_retention_policy,
)


def test_p0_casefile_lifecycle_runner_emits_metrics_for_purge_outcomes(monkeypatch) -> None:
    """Given lifecycle runner executes, then purge outcome counters should be emitted."""
    now = datetime(2026, 3, 6, 12, 0, tzinfo=UTC)
    client = InMemoryLifecycleObjectStore(
        inventory={
            "cases/case-old-1/triage.json": datetime(2023, 1, 1, 1, 0, tzinfo=UTC),
            "cases/case-fresh-1/triage.json": datetime(2025, 8, 1, 1, 0, tzinfo=UTC),
        }
    )
    runner = CasefileLifecycleRunner(
        object_store_client=client,
        policy=build_retention_policy(),
        app_env="prod",
        policy_ref="casefile-retention-policy-v1",
        governance_approval_ref="CHG-2-5-METRICS",
        delete_batch_size=100,
        list_page_size=100,
    )

    metric_calls: list[tuple[int, int, int, int]] = []

    def _record(
        *,
        scanned_count: int,
        eligible_count: int,
        purged_count: int,
        failed_count: int,
    ) -> None:
        metric_calls.append((scanned_count, eligible_count, purged_count, failed_count))

    # Story 2.5 expectation: dedicated lifecycle metric hook exists and is called per run.
    monkeypatch.setattr(health.metrics, "record_casefile_lifecycle_purge_outcome", _record)

    runner.run_once(now=now)

    assert metric_calls == [(2, 1, 1, 0)]


def test_p0_casefile_lifecycle_audit_logs_include_failed_object_keys_for_followup() -> None:
    """Given partial delete failure, lifecycle audit should include failed keys."""
    now = datetime(2026, 3, 6, 12, 0, tzinfo=UTC)
    failing_key = "cases/case-old-2/triage.json"
    client = InMemoryLifecycleObjectStore(
        inventory={
            "cases/case-old-1/triage.json": datetime(2023, 1, 1, 1, 0, tzinfo=UTC),
            failing_key: datetime(2023, 1, 2, 1, 0, tzinfo=UTC),
        },
        fail_delete_keys={failing_key},
    )
    runner = CasefileLifecycleRunner(
        object_store_client=client,
        policy=build_retention_policy(),
        app_env="prod",
        policy_ref="casefile-retention-policy-v1",
        governance_approval_ref="CHG-2-5-PARTIAL",
        delete_batch_size=100,
        list_page_size=100,
    )
    logger = RecordingLogger()
    runner._logger = logger  # noqa: SLF001

    runner.run_once(now=now)

    assert logger.events
    _, fields = logger.events[0]
    assert fields["failed_count"] == 1
    assert fields["failed_keys"] == (failing_key,)


def test_p1_casefile_lifecycle_mode_start_log_exposes_governance_and_policy_path(
    monkeypatch,
) -> None:
    """Given lifecycle mode startup, logs should surface policy path and governance metadata."""
    logger = MagicMock()
    settings = SimpleNamespace(
        APP_ENV=SimpleNamespace(value="prod"),
        CASEFILE_RETENTION_GOVERNANCE_APPROVAL="CHG-ATDD-2-5",
        CASEFILE_LIFECYCLE_DELETE_BATCH_SIZE=250,
        CASEFILE_LIFECYCLE_LIST_PAGE_SIZE=250,
        CASEFILE_LIFECYCLE_POLL_INTERVAL_SECONDS=1800.0,
    )

    class _RunnerProbe:
        def __init__(self, **kwargs: object) -> None:
            self.kwargs = kwargs

        def run_once(self) -> CasefileLifecycleRunResult:
            return CasefileLifecycleRunResult(
                scanned_count=4,
                eligible_count=2,
                purged_count=2,
                failed_count=0,
                case_ids=("case-old-a",),
            )

    monkeypatch.setattr(
        __main__,
        "_bootstrap_mode",
        lambda mode: (settings, logger, MagicMock()),
    )
    monkeypatch.setattr(__main__, "build_s3_object_store_client_from_settings", lambda _: object())
    monkeypatch.setattr(__main__, "load_policy_yaml", lambda *a, **k: build_retention_policy())
    monkeypatch.setattr(__main__, "CasefileLifecycleRunner", _RunnerProbe)

    __main__._run_casefile_lifecycle(once=True)

    start_call = next(
        call
        for call in logger.info.call_args_list
        if call.args and call.args[0] == "casefile_lifecycle_mode_started"
    )
    start_fields = start_call.kwargs
    assert start_fields["governance_approval_ref"] == "CHG-ATDD-2-5"
    assert start_fields["retention_policy_path"].endswith("casefile-retention-policy-v1.yaml")
