"""Entry point for aiops-triage-pipeline."""

import argparse
from pathlib import Path

from sqlalchemy import create_engine

from aiops_triage_pipeline.config.settings import get_settings, load_policy_yaml
from aiops_triage_pipeline.contracts.outbox_policy import OutboxPolicyV1
from aiops_triage_pipeline.integrations.kafka import ConfluentKafkaCaseEventPublisher
from aiops_triage_pipeline.logging.setup import configure_logging, get_logger
from aiops_triage_pipeline.outbox.repository import OutboxSqlRepository
from aiops_triage_pipeline.outbox.worker import OutboxPublisherWorker
from aiops_triage_pipeline.storage.client import build_s3_object_store_client_from_settings

_OUTBOX_POLICY_PATH = Path(__file__).resolve().parents[2] / "config/policies/outbox-policy-v1.yaml"


def main() -> None:
    """Parse --mode argument and dispatch to the appropriate pipeline mode."""
    parser = argparse.ArgumentParser(description="AIOps Triage Pipeline")
    parser.add_argument(
        "--mode",
        choices=["hot-path", "cold-path", "outbox-publisher"],
        required=True,
        help="Pipeline mode to run",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run a single outbox publisher iteration and exit (outbox-publisher mode only).",
    )
    args = parser.parse_args()

    if args.mode == "outbox-publisher":
        _run_outbox_publisher(once=args.once)
        return

    print(f"Starting {args.mode} mode...")


def _run_outbox_publisher(*, once: bool) -> None:
    settings = get_settings()
    configure_logging()
    logger = get_logger("__main__")
    settings.log_active_config(logger)

    policy = load_policy_yaml(_OUTBOX_POLICY_PATH, OutboxPolicyV1)
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
        policy=policy,
        app_env=settings.APP_ENV.value,
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


if __name__ == "__main__":
    main()
