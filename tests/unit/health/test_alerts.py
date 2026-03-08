"""Unit tests for operational alert evaluator."""

from aiops_triage_pipeline.health.alerts import (
    OperationalAlertEvaluator,
    load_operational_alert_policy,
)


def test_outbox_state_age_thresholds_emit_warning_and_critical() -> None:
    evaluator = OperationalAlertEvaluator(
        policy=load_operational_alert_policy(),
        app_env="local",
    )

    warning_eval = evaluator.evaluate_outbox_state_age(
        state="READY",
        actual_age_seconds=121.0,
        warning_threshold_seconds=120.0,
        critical_threshold_seconds=600.0,
    )
    critical_eval = evaluator.evaluate_outbox_state_age(
        state="READY",
        actual_age_seconds=601.0,
        warning_threshold_seconds=120.0,
        critical_threshold_seconds=600.0,
    )

    assert warning_eval is not None
    assert warning_eval.rule_id == "ALERT_OUTBOX_READY_AGE_WARNING"
    assert warning_eval.severity == "warning"

    assert critical_eval is not None
    assert critical_eval.rule_id == "ALERT_OUTBOX_READY_AGE_CRITICAL"
    assert critical_eval.severity == "critical"


def test_outbox_dead_count_uses_env_sensitive_severity() -> None:
    policy = load_operational_alert_policy()
    local_evaluator = OperationalAlertEvaluator(policy=policy, app_env="local")
    prod_evaluator = OperationalAlertEvaluator(policy=policy, app_env="prod")

    local_eval = local_evaluator.evaluate_outbox_dead_count(
        dead_count=1,
        critical_threshold=0,
    )
    prod_eval = prod_evaluator.evaluate_outbox_dead_count(
        dead_count=1,
        critical_threshold=0,
    )

    assert local_eval is not None
    assert local_eval.rule_id == "ALERT_OUTBOX_DEAD_COUNT_WARNING"
    assert local_eval.severity == "warning"

    assert prod_eval is not None
    assert prod_eval.rule_id == "ALERT_OUTBOX_DEAD_COUNT_CRITICAL"
    assert prod_eval.severity == "critical"


def test_prometheus_unavailability_uses_configured_activation_cycles() -> None:
    evaluator = OperationalAlertEvaluator(
        policy=load_operational_alert_policy(),
        app_env="local",
    )

    first = evaluator.record_prometheus_unavailability(is_total_outage=True)
    second = evaluator.record_prometheus_unavailability(is_total_outage=True)

    assert first is None
    assert second is not None
    assert second.rule_id == "ALERT_PROMETHEUS_UNAVAILABLE"


def test_redis_connection_loss_emits_critical_alert() -> None:
    evaluator = OperationalAlertEvaluator(
        policy=load_operational_alert_policy(),
        app_env="dev",
    )

    alert_eval = evaluator.evaluate_redis_connection(healthy=False)

    assert alert_eval is not None
    assert alert_eval.rule_id == "ALERT_REDIS_CONNECTION_LOSS"
    assert alert_eval.severity == "critical"


def test_scheduler_and_latency_thresholds_support_env_overrides() -> None:
    policy = load_operational_alert_policy()
    local = OperationalAlertEvaluator(policy=policy, app_env="local")
    prod = OperationalAlertEvaluator(policy=policy, app_env="prod")

    local_drift = local.evaluate_scheduler_drift(drift_seconds=30)
    prod_drift = prod.evaluate_scheduler_drift(drift_seconds=30)

    local_latency = local.evaluate_pipeline_stage_latency(seconds=1.0, stage="stage1_evidence")
    prod_latency = prod.evaluate_pipeline_stage_latency(seconds=1.0, stage="stage1_evidence")

    assert local_drift is None
    assert prod_drift is not None
    assert prod_drift.rule_id == "ALERT_SCHEDULER_INTERVAL_DRIFT_WARNING"

    assert local_latency is None
    assert prod_latency is not None
    assert prod_latency.rule_id == "ALERT_PIPELINE_STAGE_LATENCY_WARNING"


def test_llm_error_rate_uses_window_thresholds() -> None:
    policy = load_operational_alert_policy()
    policy = policy.model_copy(
        update={
            "llm_error_rate": policy.llm_error_rate.model_copy(update={"window_size": 3}),
        }
    )
    evaluator = OperationalAlertEvaluator(policy=policy, app_env="local")

    assert evaluator.record_llm_invocation_result(result="fallback") is None
    assert evaluator.record_llm_invocation_result(result="fallback") is None
    third = evaluator.record_llm_invocation_result(result="success")

    assert third is not None
    assert third.rule_id == "ALERT_LLM_ERROR_RATE_SPIKE_CRITICAL"
    assert third.severity == "critical"
