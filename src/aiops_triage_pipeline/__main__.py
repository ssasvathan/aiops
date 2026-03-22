"""Entry point for aiops-triage-pipeline."""

import argparse
import asyncio
import time
from datetime import UTC, datetime
from pathlib import Path

import redis as redis_lib
import structlog
from sqlalchemy import create_engine

from aiops_triage_pipeline.cache.dedupe import RedisActionDedupeStore
from aiops_triage_pipeline.config.settings import Settings, get_settings, load_policy_yaml
from aiops_triage_pipeline.contracts.casefile_retention_policy import CasefileRetentionPolicyV1
from aiops_triage_pipeline.contracts.outbox_policy import OutboxPolicyV1
from aiops_triage_pipeline.denylist.loader import load_denylist
from aiops_triage_pipeline.health.alerts import (
    OperationalAlertEvaluator,
    load_operational_alert_policy,
)
from aiops_triage_pipeline.health.otlp import configure_otlp_metrics
from aiops_triage_pipeline.integrations.kafka import ConfluentKafkaCaseEventPublisher
from aiops_triage_pipeline.integrations.pagerduty import PagerDutyClient, PagerDutyIntegrationMode
from aiops_triage_pipeline.integrations.prometheus import (
    MetricQueryDefinition,
    PrometheusHTTPClient,
    build_metric_queries,
    load_prometheus_metrics_contract,
)
from aiops_triage_pipeline.integrations.slack import SlackClient, SlackIntegrationMode
from aiops_triage_pipeline.logging.setup import configure_logging, get_logger
from aiops_triage_pipeline.outbox.repository import OutboxSqlRepository
from aiops_triage_pipeline.outbox.worker import OutboxPublisherWorker
from aiops_triage_pipeline.pipeline.scheduler import (
    emit_redis_degraded_mode_events,
    evaluate_scheduler_tick,
    next_interval_boundary,
    run_evidence_stage_cycle,
    run_gate_decision_stage_cycle,
    run_gate_input_stage_cycle,
    run_peak_stage_cycle,
    run_topology_stage_cycle,
)
from aiops_triage_pipeline.pipeline.stages.casefile import (
    assemble_casefile_triage_stage,
    persist_casefile_and_prepare_outbox_ready,
)
from aiops_triage_pipeline.pipeline.stages.dispatch import dispatch_action
from aiops_triage_pipeline.pipeline.stages.peak import (
    build_sustained_window_state_by_key,
    load_peak_policy,
    load_redis_ttl_policy,
    load_rulebook_policy,
)
from aiops_triage_pipeline.registry.loader import TopologyRegistryLoader
from aiops_triage_pipeline.storage.client import build_s3_object_store_client_from_settings
from aiops_triage_pipeline.storage.lifecycle import CasefileLifecycleRunner

_PEAK_POLICY_PATH = Path(__file__).resolve().parents[2] / "config/policies/peak-policy-v1.yaml"
_RULEBOOK_POLICY_PATH = Path(__file__).resolve().parents[2] / "config/policies/rulebook-v1.yaml"
_REDIS_TTL_POLICY_PATH = (
    Path(__file__).resolve().parents[2] / "config/policies/redis-ttl-policy-v1.yaml"
)
_PROMETHEUS_METRICS_CONTRACT_PATH = (
    Path(__file__).resolve().parents[2] / "config/policies/prometheus-metrics-contract-v1.yaml"
)
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


def _bootstrap_mode(mode: str) -> tuple[Settings, structlog.BoundLogger, OperationalAlertEvaluator]:
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
    try:
        settings, logger, alert_evaluator = _bootstrap_mode("hot-path")
    except Exception:
        get_logger("__main__").critical(
            "hot_path_bootstrap_failed",
            event_type="runtime.bootstrap_error",
            mode="hot-path",
            exc_info=True,
        )
        raise

    if settings.TOPOLOGY_REGISTRY_PATH is None:
        logger.critical(
            "hot_path_topology_registry_not_configured",
            event_type="runtime.startup_error",
            mode="hot-path",
            reason="TOPOLOGY_REGISTRY_PATH must be set for hot-path mode",
        )
        raise ValueError("TOPOLOGY_REGISTRY_PATH is required for hot-path mode")

    try:
        # Load policies once at startup — avoids per-cycle disk I/O.
        peak_policy = load_peak_policy(_PEAK_POLICY_PATH)
        rulebook_policy = load_rulebook_policy(_RULEBOOK_POLICY_PATH)
        redis_ttl_policy = load_redis_ttl_policy(_REDIS_TTL_POLICY_PATH)
        prometheus_metrics_contract = load_prometheus_metrics_contract(
            _PROMETHEUS_METRICS_CONTRACT_PATH
        )
        metric_queries = build_metric_queries(_PROMETHEUS_METRICS_CONTRACT_PATH)
        denylist = load_denylist(_DENYLIST_PATH)

        # Build runtime dependencies.
        prometheus_client = PrometheusHTTPClient(base_url=settings.PROMETHEUS_URL)
        redis_client = redis_lib.Redis.from_url(settings.REDIS_URL)
        dedupe_store = RedisActionDedupeStore(redis_client)
        object_store_client = build_s3_object_store_client_from_settings(settings)
        outbox_repository = OutboxSqlRepository(engine=create_engine(settings.DATABASE_URL))
        outbox_repository.ensure_schema()
        pd_client = PagerDutyClient(
            mode=PagerDutyIntegrationMode(settings.INTEGRATION_MODE_PD.value),
            pd_routing_key=settings.PD_ROUTING_KEY,
        )
        slack_client = SlackClient(
            mode=SlackIntegrationMode(settings.INTEGRATION_MODE_SLACK.value),
            webhook_url=settings.SLACK_WEBHOOK_URL,
        )
        topology_loader = TopologyRegistryLoader(Path(settings.TOPOLOGY_REGISTRY_PATH))
        topology_loader.load()
    except Exception:
        logger.critical(
            "hot_path_startup_failed",
            event_type="runtime.startup_error",
            mode="hot-path",
            exc_info=True,
        )
        raise

    logger.info(
        "hot_path_mode_started",
        event_type="hot_path.mode_start",
        app_env=settings.APP_ENV.value,
        scheduler_interval_seconds=settings.HOT_PATH_SCHEDULER_INTERVAL_SECONDS,
        prometheus_url=settings.PROMETHEUS_URL,
    )
    asyncio.run(
        _hot_path_scheduler_loop(
            settings=settings,
            logger=logger,
            alert_evaluator=alert_evaluator,
            prometheus_client=prometheus_client,
            metric_queries=metric_queries,
            peak_policy=peak_policy,
            rulebook_policy=rulebook_policy,
            redis_ttl_policy=redis_ttl_policy,
            prometheus_metrics_contract=prometheus_metrics_contract,
            denylist=denylist,
            redis_client=redis_client,
            dedupe_store=dedupe_store,
            object_store_client=object_store_client,
            outbox_repository=outbox_repository,
            pd_client=pd_client,
            slack_client=slack_client,
            topology_loader=topology_loader,
        )
    )


async def _hot_path_scheduler_loop(
    *,
    settings: Settings,
    logger: structlog.BoundLogger,
    alert_evaluator: OperationalAlertEvaluator,
    prometheus_client: PrometheusHTTPClient,
    metric_queries: dict[str, MetricQueryDefinition],
    peak_policy,
    rulebook_policy,
    redis_ttl_policy,
    prometheus_metrics_contract,
    denylist,
    redis_client,
    dedupe_store: RedisActionDedupeStore,
    object_store_client,
    outbox_repository: OutboxSqlRepository,
    pd_client: PagerDutyClient,
    slack_client: SlackClient,
    topology_loader: TopologyRegistryLoader,
) -> None:
    """Async hot-path scheduler loop: evidence → peak → topology → gate → casefile → dispatch."""
    interval_seconds = settings.HOT_PATH_SCHEDULER_INTERVAL_SECONDS
    previous_boundary = None
    prior_sustained_window_state_by_key = None

    while True:
        evaluation_time = datetime.now(UTC)
        tick = evaluate_scheduler_tick(
            actual_fire_time=evaluation_time,
            previous_boundary=previous_boundary,
            interval_seconds=interval_seconds,
            alert_evaluator=alert_evaluator,
        )
        previous_boundary = tick.expected_boundary
        logger.info(
            "hot_path_cycle_started",
            event_type="hot_path.cycle_start",
            evaluation_time=evaluation_time.isoformat(),
            expected_boundary=tick.expected_boundary.isoformat(),
            drift_seconds=tick.drift_seconds,
            missed_intervals=tick.missed_intervals,
        )

        decisions_by_scope: dict = {}
        try:
            topology_loader.reload_if_changed()
            snapshot = topology_loader.get_snapshot()

            evidence_output = await run_evidence_stage_cycle(
                client=prometheus_client,
                metric_queries=metric_queries,
                evaluation_time=evaluation_time,
                findings_cache_client=redis_client,
                redis_ttl_policy=redis_ttl_policy,
                alert_evaluator=alert_evaluator,
            )
            peak_output = run_peak_stage_cycle(
                evidence_output=evidence_output,
                historical_windows_by_scope={},
                prior_sustained_window_state_by_key=prior_sustained_window_state_by_key,
                evaluation_time=evaluation_time,
                peak_policy=peak_policy,
                rulebook_policy=rulebook_policy,
                alert_evaluator=alert_evaluator,
            )
            prior_sustained_window_state_by_key = build_sustained_window_state_by_key(
                peak_output.sustained_by_key
            )
            topology_output = run_topology_stage_cycle(
                evidence_output=evidence_output,
                snapshot=snapshot,
                alert_evaluator=alert_evaluator,
            )
            gate_inputs_by_scope = run_gate_input_stage_cycle(
                evidence_output=evidence_output,
                peak_output=peak_output,
                context_by_scope=topology_output.context_by_scope,
                alert_evaluator=alert_evaluator,
            )
            decisions_by_scope = run_gate_decision_stage_cycle(
                gate_inputs_by_scope=gate_inputs_by_scope,
                rulebook_policy=rulebook_policy,
                dedupe_store=dedupe_store,
                alert_evaluator=alert_evaluator,
            )

            for scope, decisions in decisions_by_scope.items():
                routing_context = topology_output.routing_by_scope.get(scope)
                gate_inputs = gate_inputs_by_scope.get(scope, ())
                for decision in decisions:
                    gate_input = next(
                        (
                            gi
                            for gi in gate_inputs
                            if gi.action_fingerprint == decision.action_fingerprint
                        ),
                        None,
                    )
                    if gate_input is None:
                        logger.warning(
                            "hot_path_gate_input_not_found",
                            event_type="hot_path.gate_input_missing",
                            scope=scope,
                            action_fingerprint=decision.action_fingerprint,
                        )
                        continue
                    try:
                        casefile = assemble_casefile_triage_stage(
                            scope=scope,
                            evidence_output=evidence_output,
                            peak_output=peak_output,
                            topology_output=topology_output,
                            gate_input=gate_input,
                            action_decision=decision,
                            rulebook_policy=rulebook_policy,
                            peak_policy=peak_policy,
                            prometheus_metrics_contract=prometheus_metrics_contract,
                            denylist=denylist,
                            diagnosis_policy_version="v1",
                        )
                        outbox_ready = persist_casefile_and_prepare_outbox_ready(
                            casefile=casefile,
                            object_store_client=object_store_client,
                        )
                        outbox_repository.insert_pending_object(confirmed_casefile=outbox_ready)
                        dispatch_action(
                            case_id=casefile.case_id,
                            decision=decision,
                            routing_context=routing_context,
                            pd_client=pd_client,
                            slack_client=slack_client,
                            denylist=denylist,
                        )
                    except Exception:
                        logger.error(
                            "hot_path_case_processing_failed",
                            event_type="hot_path.case_error",
                            scope=scope,
                            action_fingerprint=decision.action_fingerprint,
                            exc_info=True,
                        )

        except Exception:
            logger.error(
                "hot_path_cycle_failed",
                event_type="hot_path.cycle_error",
                evaluation_time=evaluation_time.isoformat(),
                exc_info=True,
            )

        await emit_redis_degraded_mode_events(
            dedupe_store=dedupe_store,
            evaluation_time=evaluation_time,
            slack_client=slack_client,
            alert_evaluator=alert_evaluator,
        )

        produced_cases = sum(len(d) for d in decisions_by_scope.values())
        sleep_seconds = max(
            0.0,
            (
                next_interval_boundary(evaluation_time, interval_seconds=interval_seconds)
                - datetime.now(UTC)
            ).total_seconds(),
        )
        logger.info(
            "hot_path_cycle_completed",
            event_type="hot_path.cycle_complete",
            evaluation_time=evaluation_time.isoformat(),
            produced_cases=produced_cases,
            sleep_seconds=round(sleep_seconds, 1),
        )
        await asyncio.sleep(sleep_seconds)


def _run_cold_path() -> None:
    try:
        _, logger, _ = _bootstrap_mode("cold-path")
    except Exception:
        get_logger("__main__").critical(
            "cold_path_bootstrap_failed",
            event_type="runtime.bootstrap_error",
            mode="cold-path",
            exc_info=True,
        )
        raise
    logger.warning(
        "cold_path_mode_exiting",
        event_type="runtime.mode_stub",
        reason="cold-path diagnosis loop not yet wired in __main__",
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
