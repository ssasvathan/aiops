"""Entry point for aiops-triage-pipeline."""

import argparse
import time
from pathlib import Path

from sqlalchemy import create_engine

from aiops_triage_pipeline.config.settings import get_settings, load_policy_yaml
from aiops_triage_pipeline.contracts.casefile_retention_policy import CasefileRetentionPolicyV1
from aiops_triage_pipeline.contracts.outbox_policy import OutboxPolicyV1
from aiops_triage_pipeline.denylist.loader import load_denylist
from aiops_triage_pipeline.health.alerts import (
    OperationalAlertEvaluator,
    load_operational_alert_policy,
)
from aiops_triage_pipeline.health.otlp import configure_otlp_metrics
from aiops_triage_pipeline.integrations.kafka import ConfluentKafkaCaseEventPublisher
from aiops_triage_pipeline.logging.setup import configure_logging, get_logger
from aiops_triage_pipeline.outbox.repository import OutboxSqlRepository
from aiops_triage_pipeline.outbox.worker import OutboxPublisherWorker
from aiops_triage_pipeline.storage.client import build_s3_object_store_client_from_settings
from aiops_triage_pipeline.storage.lifecycle import CasefileLifecycleRunner

_OUTBOX_POLICY_PATH = Path(__file__).resolve().parents[2] / "config/policies/outbox-policy-v1.yaml"
_CASEFILE_RETENTION_POLICY_PATH = (
    Path(__file__).resolve().parents[2] / "config/policies/casefile-retention-policy-v1.yaml"
)
_DENYLIST_PATH = Path(__file__).resolve().parents[2] / "config/denylist.yaml"
_OPERATIONAL_ALERT_POLICY_PATH = (
    Path(__file__).resolve().parents[2] / "config/policies/operational-alert-policy-v1.yaml"
)


def main() -> None:
    """Parse --mode argument and dispatch to the appropriate pipeline mode."""
    parser = argparse.ArgumentParser(description="AIOps Triage Pipeline")
    parser.add_argument(
        "--mode",
        choices=["hot-path", "cold-path", "outbox-publisher", "casefile-lifecycle"],
        required=True,
        help="Pipeline mode to run",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run a single iteration and exit (outbox-publisher and casefile-lifecycle modes).",
    )
    args = parser.parse_args()

    if args.mode == "hot-path":
        _run_hot_path()
        return
    if args.mode == "cold-path":
        _run_cold_path()
        return
    if args.mode == "outbox-publisher":
        _run_outbox_publisher(once=args.once)
        return
    if args.mode == "casefile-lifecycle":
        _run_casefile_lifecycle(once=args.once)
        return

    raise RuntimeError(f"Unsupported mode: {args.mode}")


def _bootstrap_mode(mode: str):
    settings = get_settings()
    configure_logging()
    logger = get_logger("__main__")
    settings.log_active_config(logger)
    operational_alert_policy = load_operational_alert_policy(_OPERATIONAL_ALERT_POLICY_PATH)
    alert_evaluator = OperationalAlertEvaluator(
        policy=operational_alert_policy,
        app_env=settings.APP_ENV.value,
    )
    logger.info(
        "operational_alert_policy_loaded",
        event_type="runtime.operational_alert_policy",
        policy_id=operational_alert_policy.policy_id,
        policy_schema_version=operational_alert_policy.schema_version,
        app_env_profile=settings.APP_ENV.value,
    )
    otlp_result = configure_otlp_metrics(settings)
    logger.info(
        "runtime_mode_bootstrap_completed",
        event_type="runtime.mode_bootstrap",
        mode=mode,
        otlp_configured=otlp_result.configured,
        otlp_reason=otlp_result.reason,
    )
    return settings, logger, alert_evaluator


def _run_hot_path() -> None:
    _bootstrap_mode("hot-path")
    raise RuntimeError(
        "hot-path mode runtime loop is not wired in __main__. "
        "Use dedicated pipeline orchestration entrypoint."
    )


def _run_cold_path() -> None:
    _bootstrap_mode("cold-path")
    raise RuntimeError(
        "cold-path mode runtime loop is not wired in __main__. "
        "Use dedicated diagnosis orchestration entrypoint."
    )


def _run_outbox_publisher(*, once: bool) -> None:
    settings, logger, alert_evaluator = _bootstrap_mode("outbox-publisher")

    policy = load_policy_yaml(_OUTBOX_POLICY_PATH, OutboxPolicyV1)
    denylist = load_denylist(_DENYLIST_PATH)
    repository = OutboxSqlRepository(engine=create_engine(settings.DATABASE_URL))
    repository.ensure_schema()
    publisher = ConfluentKafkaCaseEventPublisher(
        settings=settings,
        case_header_topic=settings.KAFKA_CASE_HEADER_TOPIC,
        triage_excerpt_topic=settings.KAFKA_TRIAGE_EXCERPT_TOPIC,
    )
    worker = OutboxPublisherWorker(
        outbox_repository=repository,
        object_store_client=build_s3_object_store_client_from_settings(settings),
        publisher=publisher,
        denylist=denylist,
        policy=policy,
        app_env=settings.APP_ENV.value,
        alert_evaluator=alert_evaluator,
        batch_size=settings.OUTBOX_PUBLISHER_BATCH_SIZE,
        poll_interval_seconds=settings.OUTBOX_PUBLISHER_POLL_INTERVAL_SECONDS,
    )
    logger.info(
        "outbox_publisher_mode_started",
        event_type="outbox.mode_start",
        once=once,
        app_env=settings.APP_ENV.value,
        batch_size=settings.OUTBOX_PUBLISHER_BATCH_SIZE,
        poll_interval_seconds=settings.OUTBOX_PUBLISHER_POLL_INTERVAL_SECONDS,
    )
    if once:
        worker.run_once()
        return
    worker.run_forever()


def _run_casefile_lifecycle(*, once: bool) -> None:
    settings, logger, _ = _bootstrap_mode("casefile-lifecycle")

    policy = load_policy_yaml(_CASEFILE_RETENTION_POLICY_PATH, CasefileRetentionPolicyV1)
    runner = CasefileLifecycleRunner(
        object_store_client=build_s3_object_store_client_from_settings(settings),
        policy=policy,
        app_env=settings.APP_ENV.value,
        policy_ref="casefile-retention-policy-v1",
        governance_approval_ref=settings.CASEFILE_RETENTION_GOVERNANCE_APPROVAL,
        delete_batch_size=settings.CASEFILE_LIFECYCLE_DELETE_BATCH_SIZE,
        list_page_size=settings.CASEFILE_LIFECYCLE_LIST_PAGE_SIZE,
    )
    logger.info(
        "casefile_lifecycle_mode_started",
        event_type="casefile.lifecycle.mode_start",
        once=once,
        app_env=settings.APP_ENV.value,
        policy_ref="casefile-retention-policy-v1",
        poll_interval_seconds=settings.CASEFILE_LIFECYCLE_POLL_INTERVAL_SECONDS,
        delete_batch_size=settings.CASEFILE_LIFECYCLE_DELETE_BATCH_SIZE,
        list_page_size=settings.CASEFILE_LIFECYCLE_LIST_PAGE_SIZE,
    )
    if once:
        result = runner.run_once()
        logger.info(
            "casefile_lifecycle_mode_completed",
            event_type="casefile.lifecycle.mode_complete",
            scanned_count=result.scanned_count,
            eligible_count=result.eligible_count,
            purged_count=result.purged_count,
            failed_count=result.failed_count,
            case_ids=result.case_ids,
        )
        return

    while True:
        runner.run_once()
        time.sleep(settings.CASEFILE_LIFECYCLE_POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
