"""Entry point for aiops-triage-pipeline."""

import argparse
import asyncio
import os
import threading
import time
from collections import deque
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Mapping

import redis as redis_lib
import structlog
from sqlalchemy import create_engine, delete

from aiops_triage_pipeline.cache.dedupe import RedisActionDedupeStore
from aiops_triage_pipeline.cache.evidence_window import (
    load_sustained_window_states,
    persist_sustained_window_states,
)
from aiops_triage_pipeline.cache.findings_cache import set_shard_interval_checkpoint
from aiops_triage_pipeline.cache.peak_cache import (
    load_peak_profiles,
    persist_peak_profiles,
)
from aiops_triage_pipeline.config.settings import (
    AppEnv,
    IntegrationMode,
    Settings,
    get_settings,
    load_policy_yaml,
)
from aiops_triage_pipeline.contracts.anomaly_detection_policy import AnomalyDetectionPolicyV1
from aiops_triage_pipeline.contracts.case_header_event import CaseHeaderEventV1
from aiops_triage_pipeline.contracts.casefile_retention_policy import CasefileRetentionPolicyV1
from aiops_triage_pipeline.contracts.outbox_policy import OutboxPolicyV1
from aiops_triage_pipeline.coordination import RedisCycleLock
from aiops_triage_pipeline.coordination.protocol import CycleLockProtocol, CycleLockStatus
from aiops_triage_pipeline.coordination.shard_registry import (
    RedisShardCoordinator,
    ShardLeaseStatus,
    filter_scopes_by_shard_ids,
    scope_to_shard_id,
)
from aiops_triage_pipeline.denylist.loader import load_denylist
from aiops_triage_pipeline.diagnosis.context_retrieval import retrieve_case_context_with_hash
from aiops_triage_pipeline.diagnosis.evidence_summary import build_evidence_summary
from aiops_triage_pipeline.diagnosis.graph import run_cold_path_diagnosis
from aiops_triage_pipeline.health.alerts import (
    OperationalAlertEvaluator,
    load_operational_alert_policy,
)
from aiops_triage_pipeline.health.metrics import (
    record_cycle_lock_acquired,
    record_cycle_lock_fail_open,
    record_cycle_lock_yielded,
    record_pipeline_peak_history_evictions,
    record_pipeline_peak_history_scope_count,
    record_shard_assignment,
    record_shard_checkpoint_written,
    record_shard_lease_recovered,
)
from aiops_triage_pipeline.health.otlp import configure_otlp_metrics
from aiops_triage_pipeline.health.registry import get_health_registry
from aiops_triage_pipeline.health.server import start_health_server
from aiops_triage_pipeline.integrations.kafka import ConfluentKafkaCaseEventPublisher
from aiops_triage_pipeline.integrations.kafka_consumer import (
    ConfluentKafkaCaseHeaderConsumer,
    KafkaConsumerAdapterProtocol,
)
from aiops_triage_pipeline.integrations.llm import LLMClient
from aiops_triage_pipeline.integrations.pagerduty import PagerDutyClient, PagerDutyIntegrationMode
from aiops_triage_pipeline.integrations.prometheus import (
    MetricQueryDefinition,
    PrometheusHTTPClient,
    build_metric_queries,
    load_prometheus_metrics_contract,
)
from aiops_triage_pipeline.integrations.slack import SlackClient, SlackIntegrationMode
from aiops_triage_pipeline.logging.setup import configure_logging, get_logger
from aiops_triage_pipeline.models.evidence import EvidenceRow
from aiops_triage_pipeline.models.health import HealthStatus
from aiops_triage_pipeline.outbox.repository import OutboxSqlRepository
from aiops_triage_pipeline.outbox.schema import create_outbox_table, outbox_table
from aiops_triage_pipeline.outbox.worker import OutboxPublisherWorker
from aiops_triage_pipeline.pipeline.baseline_store import load_metric_baselines
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
    get_existing_casefile_triage,
    persist_casefile_and_prepare_outbox_ready,
)
from aiops_triage_pipeline.pipeline.stages.dispatch import dispatch_action
from aiops_triage_pipeline.pipeline.stages.outbox import build_outbox_ready_record
from aiops_triage_pipeline.pipeline.stages.peak import (
    build_sustained_identity_keys,
    build_sustained_window_state_by_key,
    load_peak_policy,
    load_redis_ttl_policy,
    load_rulebook_policy,
)
from aiops_triage_pipeline.registry.loader import TopologyRegistryLoader
from aiops_triage_pipeline.storage.casefile_io import read_casefile_stage_json_or_none
from aiops_triage_pipeline.storage.client import build_s3_object_store_client_from_settings
from aiops_triage_pipeline.storage.lifecycle import CasefileLifecycleRunner

_ANOMALY_DETECTION_POLICY_PATH = (
    Path(__file__).resolve().parents[2] / "config/policies/anomaly-detection-policy-v1.yaml"
)
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
_CASEFILE_TRIAGE_HASH_MISMATCH_ERROR = (
    "triage_hash does not match canonical serialized payload bytes"
)
_HARNESS_CASE_ID_PREFIX = "case-harness-"
_HARNESS_CASEFILE_PREFIX = f"cases/{_HARNESS_CASE_ID_PREFIX}"
_HARNESS_CLEANUP_GOVERNANCE_APPROVAL_REF = "DEV-HARNESS-STATE-SWEEP"
_HARNESS_REDIS_KEY_PATTERNS: tuple[str, ...] = (
    "dedupe:harness/*",
    "aiops:baseline:*:harness|harness-cluster|*",
    "aiops:peak:harness-cluster:*",
    "peak:harness|harness-cluster|*",
    "aiops:sustained:harness-cluster:*",
    "evidence:findings|harness|harness-cluster|*",
    "evidence:findings:harness|harness-cluster|*",
    "evidence:harness|harness-cluster|*",
    "evidence_window:harness|harness-cluster|*",
)
_HARNESS_REDIS_DELETE_BATCH_SIZE = 500
_HARNESS_OBJECT_DELETE_BATCH_SIZE = 1000


class _PeakHistoryRetention:
    """Maintain bounded in-process peak baseline windows per topic scope."""

    def __init__(
        self,
        *,
        max_depth: int,
        max_scopes: int,
        max_idle_cycles: int,
        logger: structlog.BoundLogger | None = None,
    ) -> None:
        if max_depth <= 0:
            raise ValueError("max_depth must be > 0")
        if max_scopes <= 0:
            raise ValueError("max_scopes must be > 0")
        if max_idle_cycles <= 0:
            raise ValueError("max_idle_cycles must be > 0")
        self._max_depth = max_depth
        self._max_scopes = max_scopes
        self._max_idle_cycles = max_idle_cycles
        self._logger = logger
        self._cycle = 0
        self._history_by_scope: dict[tuple[str, str, str], deque[float]] = {}
        self._last_seen_cycle_by_scope: dict[tuple[str, str, str], int] = {}

    def update(
        self,
        *,
        scopes: list[tuple[str, str, str]],
        baseline_values_by_scope: dict[tuple[str, str, str], float],
    ) -> dict[tuple[str, str, str], tuple[float, ...]]:
        self._cycle += 1
        active_scopes = sorted(set(scopes))
        active_scope_set = set(active_scopes)
        cap_evictions = 0
        skipped_scope_count = 0

        for scope in active_scopes:
            history = self._history_by_scope.get(scope)
            baseline_value = baseline_values_by_scope.get(scope)

            if history is None and baseline_value is None:
                continue
            if history is None:
                while len(self._history_by_scope) >= self._max_scopes:
                    if self._evict_oldest_scope(protected_scopes=active_scope_set) is None:
                        skipped_scope_count += 1
                        break
                    cap_evictions += 1
                if len(self._history_by_scope) >= self._max_scopes:
                    continue
                history = deque(maxlen=self._max_depth)
                self._history_by_scope[scope] = history

            if baseline_value is not None:
                history.append(float(baseline_value))
            self._last_seen_cycle_by_scope[scope] = self._cycle

        stale_evictions = self._evict_stale_scopes()
        total_evictions = cap_evictions + stale_evictions
        if (cap_evictions > 0 or skipped_scope_count > 0) and self._logger is not None:
            self._logger.warning(
                "peak_history_scope_cap_reached",
                event_type="peak.history_retention_warning",
                max_scopes=self._max_scopes,
                evicted_scope_count=cap_evictions,
                skipped_scope_count=skipped_scope_count,
            )

        record_pipeline_peak_history_scope_count(scope_count=len(self._history_by_scope))
        record_pipeline_peak_history_evictions(evicted_count=total_evictions)

        return {
            scope: tuple(self._history_by_scope[scope])
            for scope in active_scopes
            if scope in self._history_by_scope and self._history_by_scope[scope]
        }

    def _evict_oldest_scope(
        self,
        *,
        protected_scopes: set[tuple[str, str, str]] | None = None,
    ) -> tuple[str, str, str] | None:
        if not self._last_seen_cycle_by_scope:
            return None
        protected = protected_scopes or set()
        candidates = [scope for scope in self._last_seen_cycle_by_scope if scope not in protected]
        if not candidates:
            return None
        scope = min(candidates, key=lambda s: (self._last_seen_cycle_by_scope[s], s))
        self._history_by_scope.pop(scope, None)
        self._last_seen_cycle_by_scope.pop(scope, None)
        return scope

    def _evict_stale_scopes(self) -> int:
        stale_scopes = [
            scope
            for scope, last_seen in self._last_seen_cycle_by_scope.items()
            if self._cycle - last_seen > self._max_idle_cycles
        ]
        for scope in stale_scopes:
            self._history_by_scope.pop(scope, None)
            self._last_seen_cycle_by_scope.pop(scope, None)
        return len(stale_scopes)


def main() -> None:
    """Parse --mode argument and dispatch to the appropriate pipeline mode."""
    parser = argparse.ArgumentParser(description="AIOps Triage Pipeline")
    parser.add_argument(
        "--mode",
        choices=[
            "hot-path",
            "cold-path",
            "outbox-publisher",
            "casefile-lifecycle",
            "harness-cleanup",
        ],
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
    if args.mode == "harness-cleanup":
        _run_harness_cleanup()
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


class _HotPathCoordinationState:
    """Coordination state snapshot for the hot-path health endpoint (FR55).

    Written from the asyncio event loop each cycle. Read by the health server
    handler on the same event loop — no concurrent mutation.
    Field semantics match the cycle-lock protocol outcomes.
    """

    def __init__(self, *, enabled: bool = False) -> None:
        self.enabled = enabled
        self.is_lock_holder: bool = False
        self.lock_holder_id: str | None = None
        self.lock_ttl_seconds: int | None = None
        self.last_cycle_time_utc: str | None = None

    def snapshot(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "is_lock_holder": self.is_lock_holder,
            "lock_holder_id": self.lock_holder_id,
            "lock_ttl_seconds": self.lock_ttl_seconds,
            "last_cycle_time_utc": self.last_cycle_time_utc,
        }


def _start_health_server_background(host: str, port: int) -> None:
    """Start health server in a background daemon thread (for sync runtime modes).

    Uses a new event loop in a daemon thread — exits when the main thread exits.
    Not used for async modes (hot-path, cold-path) which use asyncio.create_task.
    """
    async def _serve() -> None:
        server = await start_health_server(host=host, port=port)
        async with server:
            await server.serve_forever()

    t = threading.Thread(
        target=lambda: asyncio.run(_serve()),
        daemon=True,
        name="health-server",
    )
    t.start()


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

    if (
        settings.TOPOLOGY_REGISTRY_PATH is None
        or not settings.TOPOLOGY_REGISTRY_PATH.strip()
    ):
        logger.critical(
            "hot_path_topology_registry_not_configured",
            event_type="runtime.startup_error",
            mode="hot-path",
            reason="TOPOLOGY_REGISTRY_PATH must be set for hot-path mode",
        )
        raise ValueError("TOPOLOGY_REGISTRY_PATH is required for hot-path mode")

    try:
        # Load policies once at startup — avoids per-cycle disk I/O.
        anomaly_detection_policy = load_policy_yaml(
            _ANOMALY_DETECTION_POLICY_PATH, AnomalyDetectionPolicyV1
        )
        peak_policy = load_peak_policy(_PEAK_POLICY_PATH)
        rulebook_policy = load_rulebook_policy(_RULEBOOK_POLICY_PATH)
        redis_ttl_policy = load_redis_ttl_policy(_REDIS_TTL_POLICY_PATH)
        prometheus_metrics_contract = load_prometheus_metrics_contract(
            _PROMETHEUS_METRICS_CONTRACT_PATH
        )
        metric_queries = build_metric_queries(_PROMETHEUS_METRICS_CONTRACT_PATH)
        denylist = load_denylist(_DENYLIST_PATH)
        logger.info(
            "startup_policies_loaded",
            event_type="runtime.startup_policies_loaded",
            rulebook_policy_version=rulebook_policy.schema_version,
            peak_policy_version=peak_policy.schema_version,
            anomaly_detection_policy_version=anomaly_detection_policy.schema_version,
            redis_ttl_policy_version=redis_ttl_policy.schema_version,
            prometheus_metrics_contract_version=prometheus_metrics_contract.schema_version,
        )

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
    cycle_lock = RedisCycleLock(
        redis_client=redis_client,
        margin_seconds=settings.CYCLE_LOCK_MARGIN_SECONDS,
    )
    pod_id = _resolve_cycle_lock_owner_id()
    shard_coordinator: RedisShardCoordinator | None = None
    if settings.SHARD_REGISTRY_ENABLED:
        shard_coordinator = RedisShardCoordinator(
            redis_client=redis_client,
            pod_id=pod_id,
        )
    coordination_state = _HotPathCoordinationState(
        enabled=settings.DISTRIBUTED_CYCLE_LOCK_ENABLED
    )
    asyncio.run(
        _hot_path_scheduler_loop(
            settings=settings,
            logger=logger,
            alert_evaluator=alert_evaluator,
            prometheus_client=prometheus_client,
            metric_queries=metric_queries,
            anomaly_detection_policy=anomaly_detection_policy,
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
            cycle_lock=cycle_lock,
            cycle_lock_owner_id=pod_id,
            shard_coordinator=shard_coordinator,
            coordination_state=coordination_state,
        )
    )


async def _hot_path_scheduler_loop(
    *,
    settings: Settings,
    logger: structlog.BoundLogger,
    alert_evaluator: OperationalAlertEvaluator,
    prometheus_client: PrometheusHTTPClient,
    metric_queries: dict[str, MetricQueryDefinition],
    anomaly_detection_policy: AnomalyDetectionPolicyV1,
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
    cycle_lock: CycleLockProtocol,
    cycle_lock_owner_id: str,
    shard_coordinator: RedisShardCoordinator | None = None,
    coordination_state: _HotPathCoordinationState,
) -> None:
    """Async hot-path scheduler loop: evidence → peak → topology → gate → casefile → dispatch."""
    interval_seconds = settings.HOT_PATH_SCHEDULER_INTERVAL_SECONDS
    previous_boundary = None
    previous_sustained_identity_keys: set[tuple[str, str, str, str]] = set()
    peak_history_retention = _PeakHistoryRetention(
        max_depth=settings.STAGE2_PEAK_HISTORY_MAX_DEPTH,
        max_scopes=settings.STAGE2_PEAK_HISTORY_MAX_SCOPES,
        max_idle_cycles=settings.STAGE2_PEAK_HISTORY_MAX_IDLE_CYCLES,
        logger=logger,
    )
    coordination_registry = get_health_registry()
    _previous_shard_holders: dict[int, str] = {}  # shard_id → holder_id when this pod last yielded

    # Wire health server (FR54/FR55) — runs concurrently with the scheduler loop.
    _health_server = await start_health_server(
        host=settings.HEALTH_SERVER_HOST,
        port=settings.HEALTH_SERVER_PORT,
        coordination_info_fn=coordination_state.snapshot,
    )
    asyncio.create_task(_health_server.serve_forever(), name="health-server")

    while True:
        evaluation_time = datetime.now(UTC)
        coordination_state.last_cycle_time_utc = evaluation_time.isoformat()
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

        if settings.DISTRIBUTED_CYCLE_LOCK_ENABLED:
            lock_outcome = cycle_lock.acquire(
                interval_seconds=interval_seconds,
                owner_id=cycle_lock_owner_id,
            )
            if lock_outcome.status == CycleLockStatus.acquired:
                record_cycle_lock_acquired()
                await coordination_registry.update(
                    "coordination",
                    HealthStatus.HEALTHY,
                )
                logger.info(
                    "hot_path_cycle_lock_acquired",
                    event_type="hot_path.coordination_lock_acquired",
                    owner_id=cycle_lock_owner_id,
                    lock_key=lock_outcome.key,
                    lock_ttl_seconds=lock_outcome.ttl_seconds,
                )
                coordination_state.is_lock_holder = True
                coordination_state.lock_holder_id = cycle_lock_owner_id
                coordination_state.lock_ttl_seconds = lock_outcome.ttl_seconds
            elif lock_outcome.status == CycleLockStatus.yielded:
                record_cycle_lock_yielded()
                await coordination_registry.update(
                    "coordination",
                    HealthStatus.HEALTHY,
                )
                logger.info(
                    "hot_path_cycle_lock_yielded",
                    event_type="hot_path.coordination_lock_yielded",
                    owner_id=cycle_lock_owner_id,
                    lock_key=lock_outcome.key,
                    lock_ttl_seconds=lock_outcome.ttl_seconds,
                    holder_id=lock_outcome.holder_id,
                )
                coordination_state.is_lock_holder = False
                coordination_state.lock_holder_id = lock_outcome.holder_id
                coordination_state.lock_ttl_seconds = lock_outcome.ttl_seconds
                await emit_redis_degraded_mode_events(
                    dedupe_store=dedupe_store,
                    evaluation_time=evaluation_time,
                    slack_client=slack_client,
                    alert_evaluator=alert_evaluator,
                )
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
                    produced_cases=0,
                    sleep_seconds=round(sleep_seconds, 1),
                )
                await asyncio.sleep(sleep_seconds)
                continue
            elif lock_outcome.status == CycleLockStatus.fail_open:
                record_cycle_lock_fail_open(reason=lock_outcome.reason)
                await coordination_registry.update(
                    "coordination",
                    HealthStatus.DEGRADED,
                    reason=lock_outcome.reason,
                )
                logger.warning(
                    "hot_path_cycle_lock_fail_open",
                    event_type="hot_path.coordination_lock_fail_open",
                    owner_id=cycle_lock_owner_id,
                    lock_key=lock_outcome.key,
                    lock_ttl_seconds=lock_outcome.ttl_seconds,
                    reason=lock_outcome.reason,
                )
                coordination_state.is_lock_holder = True  # fail-open: proceed as if lock held
                coordination_state.lock_holder_id = None
                coordination_state.lock_ttl_seconds = None

        # ── Shard coordination gate (Story 4.2, disabled-by-default) ──────────
        # When SHARD_REGISTRY_ENABLED is True, each pod acquires a shard lease
        # and processes only the scopes mapped to its shard set.  On any shard
        # coordination failure the pod falls back to full_scope processing (D3
        # fail-open semantics) rather than halting the cycle.
        acquired_shard_ids: set[int] = set()
        shard_coordination_degraded = False
        shard_scopes_filter: list[tuple[str, str, str]] | None = None
        if settings.SHARD_REGISTRY_ENABLED and shard_coordinator is not None:
            interval_bucket = int(evaluation_time.astimezone(UTC).timestamp()) - (
                int(evaluation_time.astimezone(UTC).timestamp()) % interval_seconds
            )
            try:
                for shard_id in range(settings.SHARD_COORDINATION_SHARD_COUNT):
                    lease_outcome = shard_coordinator.acquire_lease(
                        shard_id=shard_id,
                        owner_id=cycle_lock_owner_id,
                        lease_ttl_seconds=settings.SHARD_LEASE_TTL_SECONDS,
                    )
                    if lease_outcome.status == ShardLeaseStatus.acquired:
                        acquired_shard_ids.add(shard_id)
                        prev_holder = _previous_shard_holders.pop(shard_id, None)
                        if prev_holder is not None and prev_holder != cycle_lock_owner_id:
                            record_shard_lease_recovered(
                                shard_id=shard_id, new_owner_id=cycle_lock_owner_id
                            )
                        record_shard_checkpoint_written(shard_id=shard_id)
                        set_shard_interval_checkpoint(
                            redis_client=redis_client,
                            shard_id=shard_id,
                            interval_bucket=interval_bucket,
                            ttl_seconds=settings.SHARD_CHECKPOINT_TTL_SECONDS,
                        )
                        logger.info(
                            "hot_path_shard_lease_acquired",
                            event_type="hot_path.shard_lease_acquired",
                            shard_id=shard_id,
                            owner_id=cycle_lock_owner_id,
                        )
                    elif lease_outcome.status == ShardLeaseStatus.yielded:
                        if lease_outcome.holder_id is not None:
                            _previous_shard_holders[shard_id] = lease_outcome.holder_id
                        logger.info(
                            "hot_path_shard_lease_yielded",
                            event_type="hot_path.shard_lease_yielded",
                            shard_id=shard_id,
                            holder_id=lease_outcome.holder_id,
                        )
                    elif lease_outcome.status == ShardLeaseStatus.fail_open:
                        shard_coordination_degraded = True
                        await coordination_registry.update(
                            "coordination",
                            HealthStatus.DEGRADED,
                            reason=lease_outcome.reason,
                        )
                        logger.warning(
                            "hot_path_shard_lease_fail_open",
                            event_type="hot_path.shard_coordination_degraded",
                            shard_id=shard_id,
                            reason=lease_outcome.reason,
                        )
            except Exception:  # noqa: BLE001 - shard failure degrades to full-scope (D3)
                shard_coordination_degraded = True
                acquired_shard_ids.clear()
                logger.warning(
                    "hot_path_shard_coordination_failed",
                    event_type="hot_path.shard_coordination_degraded",
                    reason="falling back to full_scope processing",
                    exc_info=True,
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
                baseline_cache_client=redis_client,
                redis_ttl_policy=redis_ttl_policy,
                alert_evaluator=alert_evaluator,
                anomaly_detection_policy=anomaly_detection_policy,
            )
            peak_scopes = _peak_scopes_from_rows(evidence_output.rows)
            if (
                settings.SHARD_REGISTRY_ENABLED
                and acquired_shard_ids
                and not shard_coordination_degraded
            ):
                shard_scopes_filter = filter_scopes_by_shard_ids(
                    scopes=peak_scopes,
                    acquired_shard_ids=acquired_shard_ids,
                    shard_count=settings.SHARD_COORDINATION_SHARD_COUNT,
                )
                _shard_scope_counts: dict[int, int] = {sid: 0 for sid in acquired_shard_ids}
                for _s in shard_scopes_filter:
                    _sid = scope_to_shard_id(_s, settings.SHARD_COORDINATION_SHARD_COUNT)
                    if _sid in _shard_scope_counts:
                        _shard_scope_counts[_sid] += 1
                for _sid, _cnt in _shard_scope_counts.items():
                    record_shard_assignment(
                        shard_id=_sid, pod_id=cycle_lock_owner_id, scope_count=_cnt
                    )
                peak_scopes = shard_scopes_filter
                logger.info(
                    "hot_path_shard_scope_filter_applied",
                    event_type="hot_path.shard_scope_assigned",
                    acquired_shard_count=len(acquired_shard_ids),
                    assigned_scope_count=len(peak_scopes),
                )
            prior_sustained_window_state_by_key = load_sustained_window_states(
                redis_client=redis_client,
                identity_keys=_build_sustained_identity_key_candidates(
                    anomaly_findings=evidence_output.anomaly_result.findings,
                    evidence_scopes=evidence_output.evidence_status_map_by_scope.keys(),
                    prior_identity_keys=previous_sustained_identity_keys,
                ),
            )
            cached_peak_profiles_by_scope = load_peak_profiles(
                redis_client=redis_client,
                scopes=peak_scopes,
            )
            peak_output = run_peak_stage_cycle(
                evidence_output=evidence_output,
                historical_windows_by_scope=_load_peak_baseline_windows(
                    redis_client=redis_client,
                    scopes=peak_scopes,
                    history_retention=peak_history_retention,
                ),
                prior_sustained_window_state_by_key=prior_sustained_window_state_by_key,
                cached_peak_profiles_by_scope=cached_peak_profiles_by_scope,
                evaluation_time=evaluation_time,
                peak_policy=peak_policy,
                rulebook_policy=rulebook_policy,
                sustained_parallel_min_keys=settings.STAGE2_SUSTAINED_PARALLEL_MIN_KEYS,
                sustained_parallel_workers=settings.STAGE2_SUSTAINED_PARALLEL_WORKERS,
                sustained_parallel_chunk_size=settings.STAGE2_SUSTAINED_PARALLEL_CHUNK_SIZE,
                alert_evaluator=alert_evaluator,
            )
            persist_sustained_window_states(
                redis_client=redis_client,
                states_by_key=build_sustained_window_state_by_key(peak_output.sustained_by_key),
                redis_ttl_policy=redis_ttl_policy,
            )
            persist_peak_profiles(
                redis_client=redis_client,
                profiles_by_scope=peak_output.profiles_by_scope,
                redis_ttl_policy=redis_ttl_policy,
            )
            previous_sustained_identity_keys = set(peak_output.sustained_by_key.keys())
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

            _shard_scope_set = set(shard_scopes_filter) if shard_scopes_filter is not None else None
            for scope, decisions in decisions_by_scope.items():
                if _shard_scope_set is not None:
                    # Normalize scope to 3-tuple for shard membership check
                    if len(scope) == 3:
                        _norm: tuple[str, str, str] | None = (scope[0], scope[1], scope[2])
                    elif len(scope) == 4:
                        _norm = (scope[0], scope[1], scope[3])
                    else:
                        _norm = None
                    if _norm is None or _norm not in _shard_scope_set:
                        continue
                routing_context = _resolve_routing_context_for_scope(
                    scope=scope,
                    routing_by_scope=topology_output.routing_by_scope,
                )
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
                        try:
                            existing_casefile = get_existing_casefile_triage(
                                gate_input=gate_input,
                                object_store_client=object_store_client,
                            )
                        except ValueError as exc:
                            if _CASEFILE_TRIAGE_HASH_MISMATCH_ERROR not in str(exc):
                                raise
                            logger.warning(
                                "hot_path_existing_casefile_triage_invalid",
                                event_type="casefile.invalid_existing_triage",
                                scope=scope,
                                action_fingerprint=decision.action_fingerprint,
                                error=str(exc),
                            )
                            continue
                        if existing_casefile is not None:
                            logger.info(
                                "casefile_triage_already_exists",
                                event_type="casefile.triage_already_exists",
                                case_id=existing_casefile.case_id,
                                scope=scope,
                            )
                            continue
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
                            anomaly_detection_policy_version=anomaly_detection_policy.schema_version,
                            topology_registry_version=str(snapshot.metadata.input_version),
                        )
                        outbox_ready = persist_casefile_and_prepare_outbox_ready(
                            casefile=casefile,
                            object_store_client=object_store_client,
                        )
                        build_outbox_ready_record(
                            confirmed_casefile=outbox_ready,
                            outbox_repository=outbox_repository,
                        )
                        raw_gate_reason_codes = getattr(decision, "gate_reason_codes", ()) or ()
                        gate_reason_codes = tuple(raw_gate_reason_codes)
                        final_action = getattr(decision, "final_action", None)
                        final_action_value = (
                            final_action.value if hasattr(final_action, "value") else final_action
                        )
                        logger.info(
                            "hot_path_case_outbox_enqueued",
                            event_type="hot_path.case_outbox_enqueued",
                            case_id=casefile.case_id,
                            scope=scope,
                            final_action=final_action_value,
                            gate_reason_codes=gate_reason_codes,
                            includes_insufficient_history=(
                                "INSUFFICIENT_HISTORY" in gate_reason_codes
                            ),
                            includes_not_sustained=("NOT_SUSTAINED" in gate_reason_codes),
                        )
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


def _resolve_cycle_lock_owner_id() -> str:
    """Resolve process identity used as Redis lock owner value."""
    pod_name = os.getenv("POD_NAME")
    if pod_name:
        return pod_name
    host_name = os.getenv("HOSTNAME")
    if host_name:
        return host_name
    return "unknown-pod"


def _peak_scopes_from_rows(rows: tuple[EvidenceRow, ...]) -> list[tuple[str, str, str]]:
    scopes: set[tuple[str, str, str]] = set()
    for row in rows:
        if len(row.scope) == 3:
            scopes.add((row.scope[0], row.scope[1], row.scope[2]))
            continue
        if len(row.scope) == 4:
            scopes.add((row.scope[0], row.scope[1], row.scope[3]))
    return sorted(scopes)


def _resolve_routing_context_for_scope(
    *,
    scope: tuple[str, ...],
    routing_by_scope: Mapping[tuple[str, ...], object],
):
    """Resolve Stage 3 routing context with deterministic topic-scope fallback."""
    routing_context = routing_by_scope.get(scope)
    if routing_context is not None:
        return routing_context
    if len(scope) == 4:
        topic_scope = (scope[0], scope[1], scope[3])
        return routing_by_scope.get(topic_scope)
    return None


def _build_sustained_identity_key_candidates(
    *,
    anomaly_findings: tuple,
    evidence_scopes,
    prior_identity_keys: set[tuple[str, str, str, str]],
) -> list[tuple[str, str, str, str]]:
    """Build sustained-state lookup keys from findings, observed scopes, and prior keys."""
    keys: set[tuple[str, str, str, str]] = set(prior_identity_keys)
    keys.update(build_sustained_identity_keys(anomaly_findings))
    for scope in evidence_scopes:
        if len(scope) == 3:
            env, cluster_id, topic = scope
            keys.add((env, cluster_id, f"topic:{topic}", "VOLUME_DROP"))
            keys.add((env, cluster_id, f"topic:{topic}", "THROUGHPUT_CONSTRAINED_PROXY"))
            continue
        if len(scope) == 4:
            env, cluster_id, group, _ = scope
            keys.add((env, cluster_id, f"group:{group}", "CONSUMER_LAG"))
    return sorted(keys)


def _load_peak_baseline_windows(
    *,
    redis_client,
    scopes: list[tuple[str, str, str]],
    history_retention: _PeakHistoryRetention | None = None,
) -> dict[tuple[str, str, str], tuple[float, ...]]:
    """Hydrate peak historical windows from persisted per-scope baselines."""
    if not scopes:
        if history_retention is None:
            return {}
        return history_retention.update(scopes=[], baseline_values_by_scope={})
    loaded_baselines_by_scope = load_metric_baselines(
        redis_client=redis_client,
        source="prometheus",
        scope_metric_pairs=[(scope, "topic_messages_in_per_sec") for scope in scopes],
    )
    baseline_values_by_scope: dict[tuple[str, str, str], float] = {}
    for scope in scopes:
        baseline_value = loaded_baselines_by_scope.get(scope, {}).get("topic_messages_in_per_sec")
        if baseline_value is not None:
            baseline_values_by_scope[scope] = baseline_value
    if history_retention is None:
        return {scope: (value,) for scope, value in baseline_values_by_scope.items()}
    return history_retention.update(
        scopes=scopes,
        baseline_values_by_scope=baseline_values_by_scope,
    )


def _run_cold_path() -> None:
    try:
        settings, logger, alert_evaluator = _bootstrap_mode("cold-path")
    except Exception:
        get_logger("__main__").critical(
            "cold_path_bootstrap_failed",
            event_type="runtime.bootstrap_error",
            mode="cold-path",
            exc_info=True,
        )
        raise

    registry = get_health_registry()
    consumer_group = settings.KAFKA_COLD_PATH_CONSUMER_GROUP
    topic = settings.KAFKA_CASE_HEADER_TOPIC

    logger.info(
        "cold_path_mode_started",
        event_type="cold_path.mode_start",
        consumer_group=consumer_group,
        topic=topic,
        poll_timeout_seconds=settings.KAFKA_COLD_PATH_POLL_TIMEOUT_SECONDS,
        app_env=settings.APP_ENV.value,
    )

    object_store_client = build_s3_object_store_client_from_settings(settings)
    llm_mode = getattr(settings, "INTEGRATION_MODE_LLM", IntegrationMode.LOG)
    if not isinstance(llm_mode, IntegrationMode):
        llm_mode = IntegrationMode(str(llm_mode))
    llm_client = LLMClient(
        mode=llm_mode,
        base_url=getattr(settings, "LLM_BASE_URL", None),
        api_key=getattr(settings, "LLM_API_KEY", None),
        model=getattr(settings, "LLM_MODEL", "claude-sonnet-4-6"),
    )
    denylist = load_denylist(_DENYLIST_PATH)
    llm_timeout_seconds = float(getattr(settings, "LLM_TIMEOUT_SECONDS", 60.0))
    if llm_timeout_seconds <= 0:
        logger.warning(
            "cold_path_invalid_llm_timeout_config",
            event_type="cold_path.config_warning",
            configured_timeout_seconds=llm_timeout_seconds,
            fallback_timeout_seconds=60.0,
        )
        llm_timeout_seconds = 60.0

    asyncio.run(
        _cold_path_consumer_loop(
            settings=settings,
            logger=logger,
            registry=registry,
            consumer_group=consumer_group,
            topic=topic,
            object_store_client=object_store_client,
            llm_client=llm_client,
            denylist=denylist,
            llm_timeout_seconds=llm_timeout_seconds,
            alert_evaluator=alert_evaluator,
        )
    )


async def _cold_path_consumer_loop(
    *,
    settings: Any,
    logger: structlog.BoundLogger,
    registry: Any,
    consumer_group: str,
    topic: str,
    object_store_client: Any,
    llm_client: LLMClient,
    denylist: Any,
    llm_timeout_seconds: float,
    alert_evaluator: OperationalAlertEvaluator,
) -> None:
    """Sequential cold-path consume loop: subscribe → poll → process → commit on shutdown."""
    poll_timeout: float = settings.KAFKA_COLD_PATH_POLL_TIMEOUT_SECONDS
    adapter: KafkaConsumerAdapterProtocol | None = None

    # Wire health server (FR54) — runs concurrently with the consume loop.
    _health_server = await start_health_server(
        host=settings.HEALTH_SERVER_HOST,
        port=settings.HEALTH_SERVER_PORT,
    )
    asyncio.create_task(_health_server.serve_forever(), name="health-server")

    # Signal connecting state before attempting consumer construction.
    await registry.update(
        "kafka_cold_path_connected",
        HealthStatus.DEGRADED,
        reason="connecting",
    )

    try:
        adapter = _build_cold_path_consumer_adapter(settings, consumer_group)
        adapter.subscribe([topic])
        await registry.update("kafka_cold_path_connected", HealthStatus.HEALTHY)

        while True:
            msg = adapter.poll(timeout=poll_timeout)
            await registry.update("kafka_cold_path_poll", HealthStatus.HEALTHY)
            if msg is None:
                continue
            await _process_cold_path_message(
                msg,
                logger,
                object_store_client=object_store_client,
                llm_client=llm_client,
                denylist=denylist,
                health_registry=registry,
                llm_timeout_seconds=llm_timeout_seconds,
                alert_evaluator=alert_evaluator,
            )

    except (KeyboardInterrupt, SystemExit):
        logger.info(
            "cold_path_shutdown_requested",
            event_type="cold_path.shutdown",
        )

    except Exception as exc:  # noqa: BLE001
        await registry.update(
            "kafka_cold_path_connected",
            HealthStatus.UNAVAILABLE,
            reason=str(exc),
        )
        await registry.update(
            "kafka_cold_path_poll",
            HealthStatus.UNAVAILABLE,
            reason=str(exc),
        )
        logger.error(
            "cold_path_consumer_error",
            event_type="cold_path.consumer_error",
            exc_info=True,
        )

    finally:
        if adapter is not None:
            try:
                adapter.commit()
                await registry.update("kafka_cold_path_commit", HealthStatus.HEALTHY)
            except Exception as commit_exc:  # noqa: BLE001
                await registry.update(
                    "kafka_cold_path_commit",
                    HealthStatus.UNAVAILABLE,
                    reason=str(commit_exc),
                )
                logger.warning(
                    "cold_path_commit_failed",
                    event_type="cold_path.commit_error",
                    exc_info=True,
                )
            try:
                adapter.close()
            except Exception:  # noqa: BLE001
                pass
        else:
            await registry.update(
                "kafka_cold_path_commit",
                HealthStatus.UNAVAILABLE,
                reason="consumer not initialized",
            )


def _build_cold_path_consumer_adapter(
    settings: Any,
    consumer_group: str,
) -> KafkaConsumerAdapterProtocol:
    """Build and return the confluent-kafka consumer adapter for cold-path."""
    return ConfluentKafkaCaseHeaderConsumer(
        consumer_group=consumer_group,
        settings=settings,
    )


async def _process_cold_path_message(
    msg: Any,
    logger: structlog.BoundLogger,
    *,
    object_store_client: Any,
    llm_client: LLMClient,
    denylist: Any,
    health_registry: Any,
    llm_timeout_seconds: float,
    alert_evaluator: OperationalAlertEvaluator,
) -> None:
    """Decode and validate a cold-path Kafka message; route to processor boundary."""
    if msg.error():
        logger.warning(
            "cold_path_message_error",
            event_type="cold_path.message_error",
            error=str(msg.error()),
        )
        return
    try:
        event = CaseHeaderEventV1.model_validate_json(msg.value())
        await _cold_path_process_event_async(
            event,
            logger,
            object_store_client=object_store_client,
            llm_client=llm_client,
            denylist=denylist,
            health_registry=health_registry,
            llm_timeout_seconds=llm_timeout_seconds,
            alert_evaluator=alert_evaluator,
        )
    except Exception:  # noqa: BLE001
        logger.warning(
            "cold_path_message_validation_failed",
            event_type="cold_path.validation_error",
            exc_info=True,
        )


def _cold_path_process_event(
    event: CaseHeaderEventV1,
    logger: structlog.BoundLogger,
    *,
    object_store_client: Any,
    llm_client: LLMClient | None = None,
    denylist: Any | None = None,
    health_registry: Any | None = None,
    llm_timeout_seconds: float = 60.0,
    alert_evaluator: OperationalAlertEvaluator | None = None,
) -> None:
    """Sync compatibility wrapper around the async cold-path processor boundary.

    This keeps sync test call sites stable while the runtime path awaits the
    async implementation directly from the active event loop.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        asyncio.run(
            _cold_path_process_event_async(
                event,
                logger,
                object_store_client=object_store_client,
                llm_client=llm_client,
                denylist=denylist,
                health_registry=health_registry,
                llm_timeout_seconds=llm_timeout_seconds,
                alert_evaluator=alert_evaluator,
            )
        )
        return

    raise RuntimeError(
        "_cold_path_process_event() cannot be used from an active asyncio loop; "
        "await _cold_path_process_event_async() instead."
    )


async def _cold_path_process_event_async(
    event: CaseHeaderEventV1,
    logger: structlog.BoundLogger,
    *,
    object_store_client: Any,
    llm_client: LLMClient | None = None,
    denylist: Any | None = None,
    health_registry: Any | None = None,
    llm_timeout_seconds: float = 60.0,
    alert_evaluator: OperationalAlertEvaluator | None = None,
) -> None:
    """Processor boundary: reconstruct context, build summary, and invoke diagnosis."""
    logger.debug(
        "cold_path_event_received",
        event_type="cold_path.event_received",
        case_id=event.case_id,
        schema_version=event.schema_version,
        env=event.env.value,
        topic=event.topic,
        anomaly_family=event.anomaly_family,
        final_action=event.final_action.value,
        criticality_tier=event.criticality_tier.value,
    )

    # Step (a): Reconstruct TriageExcerptV1 from persisted triage artifact
    try:
        retrieved_context = retrieve_case_context_with_hash(
            case_id=event.case_id,
            object_store_client=object_store_client,
        )
        triage_excerpt = retrieved_context.excerpt
        triage_hash = retrieved_context.triage_hash
    except Exception:  # noqa: BLE001
        logger.warning(
            "cold_path_context_retrieval_failed",
            event_type="cold_path.context_retrieval_failed",
            case_id=event.case_id,
            exc_info=True,
        )
        return

    # Duplicate case-header events are expected; keep diagnosis write-once by short-circuiting
    # when diagnosis.json already exists for the same triage hash.
    existing_diagnosis = None
    try:
        existing_diagnosis = read_casefile_stage_json_or_none(
            object_store_client=object_store_client,
            case_id=event.case_id,
            stage="diagnosis",
        )
    except Exception:  # noqa: BLE001
        logger.warning(
            "cold_path_existing_diagnosis_probe_failed",
            event_type="cold_path.existing_diagnosis_probe_failed",
            case_id=event.case_id,
            exc_info=True,
        )

    if existing_diagnosis is not None:
        if existing_diagnosis.triage_hash == triage_hash:
            logger.info(
                "cold_path_diagnosis_already_present",
                event_type="cold_path.diagnosis_already_present",
                case_id=event.case_id,
                triage_hash=triage_hash,
                diagnosis_hash=existing_diagnosis.diagnosis_hash,
            )
            return
        logger.warning(
            "cold_path_existing_diagnosis_triage_hash_mismatch",
            event_type="cold_path.existing_diagnosis_triage_hash_mismatch",
            case_id=event.case_id,
            triage_hash=triage_hash,
            existing_triage_hash=existing_diagnosis.triage_hash,
            diagnosis_hash=existing_diagnosis.diagnosis_hash,
        )
        return

    # Step (b): Build deterministic evidence summary
    try:
        evidence_summary = build_evidence_summary(triage_excerpt)
    except Exception:  # noqa: BLE001
        logger.warning(
            "cold_path_evidence_summary_failed",
            event_type="cold_path.evidence_summary_failed",
            case_id=event.case_id,
            exc_info=True,
        )
        return

    if llm_client is None:
        llm_client = LLMClient(mode=IntegrationMode.LOG)
    if denylist is None:
        denylist = load_denylist(_DENYLIST_PATH)
    if health_registry is None:
        health_registry = get_health_registry()
    if llm_timeout_seconds <= 0:
        llm_timeout_seconds = 60.0

    logger.info(
        "cold_path_diagnosis_start",
        event_type="cold_path.diagnosis_start",
        case_id=event.case_id,
        env=event.env.value,
        topic=event.topic,
        anomaly_family=event.anomaly_family,
        final_action=event.final_action.value,
        criticality_tier=event.criticality_tier.value,
    )

    try:
        await run_cold_path_diagnosis(
            case_id=event.case_id,
            triage_excerpt=triage_excerpt,
            evidence_summary=evidence_summary,
            llm_client=llm_client,
            denylist=denylist,
            health_registry=health_registry,
            object_store_client=object_store_client,
            triage_hash=triage_hash,
            timeout_seconds=llm_timeout_seconds,
            alert_evaluator=alert_evaluator,
        )
    except Exception:  # noqa: BLE001
        logger.warning(
            "cold_path_diagnosis_invocation_failed",
            event_type="cold_path.diagnosis_invocation_failed",
            case_id=event.case_id,
            exc_info=True,
        )
        return

    logger.debug(
        "cold_path_diagnosis_invoked",
        event_type="cold_path.diagnosis_invoked",
        case_id=event.case_id,
        final_action=event.final_action.value,
        evidence_summary_length=len(evidence_summary),
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
    _start_health_server_background(settings.HEALTH_SERVER_HOST, settings.HEALTH_SERVER_PORT)
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
        policy_schema_version=policy.schema_version,
        retention_policy_path=str(_CASEFILE_RETENTION_POLICY_PATH),
        governance_approval_ref=settings.CASEFILE_RETENTION_GOVERNANCE_APPROVAL,
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

    _start_health_server_background(settings.HEALTH_SERVER_HOST, settings.HEALTH_SERVER_PORT)
    while True:
        runner.run_once()
        time.sleep(settings.CASEFILE_LIFECYCLE_POLL_INTERVAL_SECONDS)


def _chunk_keys(keys: list[str], chunk_size: int) -> list[list[str]]:
    return [keys[index : index + chunk_size] for index in range(0, len(keys), chunk_size)]


def _collect_harness_casefile_keys(*, object_store_client) -> list[str]:
    keys: list[str] = []
    continuation_token: str | None = None
    while True:
        page = object_store_client.list_objects_page(
            prefix=_HARNESS_CASEFILE_PREFIX,
            continuation_token=continuation_token,
            max_keys=_HARNESS_OBJECT_DELETE_BATCH_SIZE,
        )
        keys.extend(obj.key for obj in page.objects)
        continuation_token = page.next_continuation_token
        if continuation_token is None:
            return sorted(set(keys))


def _delete_harness_casefiles(*, object_store_client, keys: list[str]) -> tuple[int, int]:
    deleted_count = 0
    failed_count = 0
    if not keys:
        return deleted_count, failed_count

    for batch in _chunk_keys(keys, _HARNESS_OBJECT_DELETE_BATCH_SIZE):
        delete_result = object_store_client.delete_objects_batch(
            keys=batch,
            governance_approval_ref=_HARNESS_CLEANUP_GOVERNANCE_APPROVAL_REF,
        )
        deleted_count += len(delete_result.deleted_keys)
        failed_count += len(delete_result.failed_keys)
    return deleted_count, failed_count


def _delete_harness_outbox_rows(*, engine) -> int:
    with engine.begin() as conn:
        create_outbox_table(conn)
        result = conn.execute(
            delete(outbox_table).where(outbox_table.c.case_id.like(f"{_HARNESS_CASE_ID_PREFIX}%"))
        )
    return int(result.rowcount or 0)


def _delete_harness_redis_keys(*, redis_client) -> tuple[int, int]:
    discovered_keys: set[str] = set()
    for pattern in _HARNESS_REDIS_KEY_PATTERNS:
        for raw_key in redis_client.scan_iter(
            match=pattern,
            count=_HARNESS_REDIS_DELETE_BATCH_SIZE,
        ):
            if isinstance(raw_key, bytes):
                decoded = raw_key.decode("utf-8", errors="ignore").strip()
            else:
                decoded = str(raw_key).strip()
            if decoded:
                discovered_keys.add(decoded)

    deleted_count = 0
    sorted_keys = sorted(discovered_keys)
    for batch in _chunk_keys(sorted_keys, _HARNESS_REDIS_DELETE_BATCH_SIZE):
        deleted_count += int(redis_client.delete(*batch))
    return len(sorted_keys), deleted_count


def _run_harness_cleanup() -> None:
    settings, logger, _ = _bootstrap_mode("harness-cleanup")
    app_env_value = (
        settings.APP_ENV.value if hasattr(settings.APP_ENV, "value") else str(settings.APP_ENV)
    )
    if app_env_value not in {AppEnv.local.value, AppEnv.harness.value}:
        raise ValueError(
            "harness-cleanup mode is only allowed for APP_ENV in {local, harness}; "
            f"got {app_env_value}"
        )

    logger.info(
        "harness_cleanup_started",
        event_type="harness.cleanup.start",
        app_env=app_env_value,
        case_id_prefix=_HARNESS_CASE_ID_PREFIX,
        casefile_prefix=_HARNESS_CASEFILE_PREFIX,
        redis_patterns=_HARNESS_REDIS_KEY_PATTERNS,
    )

    object_store_client = build_s3_object_store_client_from_settings(settings)
    engine = create_engine(settings.DATABASE_URL)
    redis_client = redis_lib.Redis.from_url(settings.REDIS_URL)

    harness_casefile_keys = _collect_harness_casefile_keys(object_store_client=object_store_client)
    casefiles_deleted_count, casefiles_failed_count = _delete_harness_casefiles(
        object_store_client=object_store_client,
        keys=harness_casefile_keys,
    )
    outbox_deleted_count = _delete_harness_outbox_rows(engine=engine)
    redis_matched_count, redis_deleted_count = _delete_harness_redis_keys(redis_client=redis_client)

    logger.info(
        "harness_cleanup_completed",
        event_type="harness.cleanup.complete",
        app_env=app_env_value,
        casefiles_found_count=len(harness_casefile_keys),
        casefiles_deleted_count=casefiles_deleted_count,
        casefiles_failed_count=casefiles_failed_count,
        outbox_rows_deleted_count=outbox_deleted_count,
        redis_keys_matched_count=redis_matched_count,
        redis_keys_deleted_count=redis_deleted_count,
    )


if __name__ == "__main__":
    main()
