import pytest
from pydantic import ValidationError

from aiops_triage_pipeline.models.anomaly import (
    AnomalyDetectionResult,
    AnomalyFinding,
    group_findings_by_scope,
)
from aiops_triage_pipeline.models.evidence import EvidenceRow
from aiops_triage_pipeline.pipeline.stages.anomaly import detect_anomaly_findings


def test_anomaly_finding_is_frozen() -> None:
    finding = AnomalyFinding(
        finding_id="f-1",
        anomaly_family="CONSUMER_LAG",
        scope=("prod", "cluster-1", "group-a", "topic-a"),
        severity="HIGH",
        reason_codes=("LAG_BUILDUP_DETECTED",),
        evidence_required=("consumer_group_lag", "consumer_group_offset"),
        is_primary=True,
    )

    with pytest.raises(ValidationError):
        finding.severity = "LOW"  # type: ignore[misc]


def test_group_findings_by_scope_is_deterministic() -> None:
    findings = (
        AnomalyFinding(
            finding_id="f-2",
            anomaly_family="VOLUME_DROP",
            scope=("prod", "cluster-1", "topic-a"),
            severity="MEDIUM",
            reason_codes=("VOLUME_DROP_DETECTED",),
            evidence_required=("topic_messages_in_per_sec", "total_produce_requests_per_sec"),
        ),
        AnomalyFinding(
            finding_id="f-3",
            anomaly_family="THROUGHPUT_CONSTRAINED_PROXY",
            scope=("prod", "cluster-1", "topic-a"),
            severity="HIGH",
            reason_codes=("HIGH_THROUGHPUT", "PRODUCE_FAILURE_RATIO_HIGH"),
            evidence_required=(
                "topic_messages_in_per_sec",
                "total_produce_requests_per_sec",
                "failed_produce_requests_per_sec",
            ),
        ),
    )

    grouped = group_findings_by_scope(findings)

    assert list(grouped.keys()) == [("prod", "cluster-1", "topic-a")]
    assert [f.finding_id for f in grouped[("prod", "cluster-1", "topic-a")]] == ["f-2", "f-3"]


def test_detection_result_keeps_findings_and_scope_map() -> None:
    finding = AnomalyFinding(
        finding_id="f-4",
        anomaly_family="CONSUMER_LAG",
        scope=("dev", "cluster-9", "group-x", "topic-z"),
        severity="MEDIUM",
        reason_codes=("LAG_BUILDUP_DETECTED",),
        evidence_required=("consumer_group_lag", "consumer_group_offset"),
    )

    # findings_by_scope is auto-derived; only findings needs to be supplied.
    result = AnomalyDetectionResult(findings=(finding,))

    assert len(result.findings) == 1
    assert (
        result.findings_by_scope[("dev", "cluster-9", "group-x", "topic-z")][0].anomaly_family
        == "CONSUMER_LAG"
    )


def test_detection_result_scope_map_is_immutable() -> None:
    finding = AnomalyFinding(
        finding_id="f-4",
        anomaly_family="CONSUMER_LAG",
        scope=("dev", "cluster-9", "group-x", "topic-z"),
        severity="MEDIUM",
        reason_codes=("LAG_BUILDUP_DETECTED",),
        evidence_required=("consumer_group_lag", "consumer_group_offset"),
    )
    result = AnomalyDetectionResult(findings=(finding,))

    with pytest.raises(TypeError):
        result.findings_by_scope[("dev", "cluster-9", "group-x", "topic-z")] = ()


def test_detection_result_derives_scope_map_from_findings_ignoring_caller_value() -> None:
    """AnomalyDetectionResult must always derive findings_by_scope from findings.

    Passing an inconsistent or empty findings_by_scope must be silently corrected so callers
    cannot construct a logically broken result.
    """
    finding = AnomalyFinding(
        finding_id="f-5",
        anomaly_family="VOLUME_DROP",
        scope=("prod", "cluster-1", "topic-x"),
        severity="MEDIUM",
        reason_codes=("VOLUME_DROP_VS_BASELINE",),
        evidence_required=("topic_messages_in_per_sec", "total_produce_requests_per_sec"),
    )

    # Pass a deliberately empty/inconsistent findings_by_scope — it must be overwritten.
    result = AnomalyDetectionResult(findings=(finding,), findings_by_scope={})

    assert ("prod", "cluster-1", "topic-x") in result.findings_by_scope
    assert result.findings_by_scope[("prod", "cluster-1", "topic-x")][0].finding_id == "f-5"


def test_detect_consumer_lag_buildup_positive() -> None:
    rows = [
        EvidenceRow(
            metric_key="consumer_group_lag",
            value=120.0,
            labels={
                "env": "prod",
                "cluster_id": "cluster-a",
                "group": "payments-worker",
                "topic": "payments",
            },
            scope=("prod", "cluster-a", "payments-worker", "payments"),
        ),
        EvidenceRow(
            metric_key="consumer_group_lag",
            value=180.0,
            labels={
                "env": "prod",
                "cluster_id": "cluster-a",
                "group": "payments-worker",
                "topic": "payments",
            },
            scope=("prod", "cluster-a", "payments-worker", "payments"),
        ),
        EvidenceRow(
            metric_key="consumer_group_offset",
            value=2.0,
            labels={
                "env": "prod",
                "cluster_id": "cluster-a",
                "group": "payments-worker",
                "topic": "payments",
            },
            scope=("prod", "cluster-a", "payments-worker", "payments"),
        ),
        EvidenceRow(
            metric_key="consumer_group_offset",
            value=8.0,
            labels={
                "env": "prod",
                "cluster_id": "cluster-a",
                "group": "payments-worker",
                "topic": "payments",
            },
            scope=("prod", "cluster-a", "payments-worker", "payments"),
        ),
    ]

    result = detect_anomaly_findings(rows)

    lag_findings = [f for f in result.findings if f.anomaly_family == "CONSUMER_LAG"]
    assert len(lag_findings) == 1
    assert lag_findings[0].evidence_required == ("consumer_group_lag", "consumer_group_offset")
    assert "LAG_BUILDUP_DETECTED" in lag_findings[0].reason_codes


def test_detect_consumer_lag_buildup_negative_when_lag_low() -> None:
    rows = [
        EvidenceRow(
            metric_key="consumer_group_lag",
            value=12.0,
            labels={
                "env": "prod",
                "cluster_id": "cluster-a",
                "group": "payments-worker",
                "topic": "payments",
            },
            scope=("prod", "cluster-a", "payments-worker", "payments"),
        ),
        EvidenceRow(
            metric_key="consumer_group_offset",
            value=20.0,
            labels={
                "env": "prod",
                "cluster_id": "cluster-a",
                "group": "payments-worker",
                "topic": "payments",
            },
            scope=("prod", "cluster-a", "payments-worker", "payments"),
        ),
    ]

    result = detect_anomaly_findings(rows)

    assert all(f.anomaly_family != "CONSUMER_LAG" for f in result.findings)


def test_detect_consumer_lag_buildup_negative_when_lag_is_decreasing() -> None:
    rows = [
        EvidenceRow(
            metric_key="consumer_group_lag",
            value=200.0,
            labels={
                "env": "prod",
                "cluster_id": "cluster-a",
                "group": "payments-worker",
                "topic": "payments",
            },
            scope=("prod", "cluster-a", "payments-worker", "payments"),
        ),
        EvidenceRow(
            metric_key="consumer_group_lag",
            value=130.0,
            labels={
                "env": "prod",
                "cluster_id": "cluster-a",
                "group": "payments-worker",
                "topic": "payments",
            },
            scope=("prod", "cluster-a", "payments-worker", "payments"),
        ),
        EvidenceRow(
            metric_key="consumer_group_offset",
            value=1.0,
            labels={
                "env": "prod",
                "cluster_id": "cluster-a",
                "group": "payments-worker",
                "topic": "payments",
            },
            scope=("prod", "cluster-a", "payments-worker", "payments"),
        ),
        EvidenceRow(
            metric_key="consumer_group_offset",
            value=4.0,
            labels={
                "env": "prod",
                "cluster_id": "cluster-a",
                "group": "payments-worker",
                "topic": "payments",
            },
            scope=("prod", "cluster-a", "payments-worker", "payments"),
        ),
    ]

    result = detect_anomaly_findings(rows)

    assert all(f.anomaly_family != "CONSUMER_LAG" for f in result.findings)


def test_detect_consumer_lag_buildup_skips_missing_offset_as_unknown() -> None:
    rows = [
        EvidenceRow(
            metric_key="consumer_group_lag",
            value=250.0,
            labels={
                "env": "prod",
                "cluster_id": "cluster-a",
                "group": "payments-worker",
                "topic": "payments",
            },
            scope=("prod", "cluster-a", "payments-worker", "payments"),
        ),
    ]

    result = detect_anomaly_findings(rows)

    assert all(f.anomaly_family != "CONSUMER_LAG" for f in result.findings)


def test_detect_throughput_constrained_proxy_positive() -> None:
    rows = [
        EvidenceRow(
            metric_key="topic_messages_in_per_sec",
            value=1400.0,
            labels={"env": "prod", "cluster_id": "cluster-a", "topic": "orders"},
            scope=("prod", "cluster-a", "orders"),
        ),
        EvidenceRow(
            metric_key="total_produce_requests_per_sec",
            value=200.0,
            labels={"env": "prod", "cluster_id": "cluster-a", "topic": "orders"},
            scope=("prod", "cluster-a", "orders"),
        ),
        EvidenceRow(
            metric_key="failed_produce_requests_per_sec",
            value=30.0,
            labels={"env": "prod", "cluster_id": "cluster-a", "topic": "orders"},
            scope=("prod", "cluster-a", "orders"),
        ),
    ]

    result = detect_anomaly_findings(rows)

    proxy_findings = [
        f for f in result.findings if f.anomaly_family == "THROUGHPUT_CONSTRAINED_PROXY"
    ]
    assert len(proxy_findings) == 1
    assert proxy_findings[0].evidence_required == (
        "topic_messages_in_per_sec",
        "total_produce_requests_per_sec",
        "failed_produce_requests_per_sec",
    )
    assert "HIGH_THROUGHPUT" in proxy_findings[0].reason_codes
    assert "PRODUCE_FAILURE_RATIO_HIGH" in proxy_findings[0].reason_codes


def test_detect_throughput_constrained_proxy_negative_for_normal_failure_ratio() -> None:
    rows = [
        EvidenceRow(
            metric_key="topic_messages_in_per_sec",
            value=1400.0,
            labels={"env": "prod", "cluster_id": "cluster-a", "topic": "orders"},
            scope=("prod", "cluster-a", "orders"),
        ),
        EvidenceRow(
            metric_key="total_produce_requests_per_sec",
            value=200.0,
            labels={"env": "prod", "cluster_id": "cluster-a", "topic": "orders"},
            scope=("prod", "cluster-a", "orders"),
        ),
        EvidenceRow(
            metric_key="failed_produce_requests_per_sec",
            value=2.0,
            labels={"env": "prod", "cluster_id": "cluster-a", "topic": "orders"},
            scope=("prod", "cluster-a", "orders"),
        ),
    ]

    result = detect_anomaly_findings(rows)

    assert all(f.anomaly_family != "THROUGHPUT_CONSTRAINED_PROXY" for f in result.findings)


def test_detect_throughput_constrained_proxy_threshold_boundary() -> None:
    rows = [
        EvidenceRow(
            metric_key="topic_messages_in_per_sec",
            value=1000.0,
            labels={"env": "prod", "cluster_id": "cluster-a", "topic": "orders"},
            scope=("prod", "cluster-a", "orders"),
        ),
        EvidenceRow(
            metric_key="total_produce_requests_per_sec",
            value=100.0,
            labels={"env": "prod", "cluster_id": "cluster-a", "topic": "orders"},
            scope=("prod", "cluster-a", "orders"),
        ),
        EvidenceRow(
            metric_key="failed_produce_requests_per_sec",
            value=5.0,
            labels={"env": "prod", "cluster_id": "cluster-a", "topic": "orders"},
            scope=("prod", "cluster-a", "orders"),
        ),
    ]

    result = detect_anomaly_findings(rows)

    assert any(f.anomaly_family == "THROUGHPUT_CONSTRAINED_PROXY" for f in result.findings)


def test_detect_volume_drop_positive_for_expected_ingress_with_near_zero_traffic() -> None:
    rows = [
        EvidenceRow(
            metric_key="topic_messages_in_per_sec",
            value=180.0,
            labels={"env": "prod", "cluster_id": "cluster-a", "topic": "inventory"},
            scope=("prod", "cluster-a", "inventory"),
        ),
        EvidenceRow(
            metric_key="topic_messages_in_per_sec",
            value=0.8,
            labels={"env": "prod", "cluster_id": "cluster-a", "topic": "inventory"},
            scope=("prod", "cluster-a", "inventory"),
        ),
        EvidenceRow(
            metric_key="total_produce_requests_per_sec",
            value=240.0,
            labels={"env": "prod", "cluster_id": "cluster-a", "topic": "inventory"},
            scope=("prod", "cluster-a", "inventory"),
        ),
    ]

    result = detect_anomaly_findings(rows)

    volume_findings = [f for f in result.findings if f.anomaly_family == "VOLUME_DROP"]
    assert len(volume_findings) == 1
    assert volume_findings[0].evidence_required == (
        "topic_messages_in_per_sec",
        "total_produce_requests_per_sec",
    )
    assert "EXPECTED_INGRESS_BUT_LOW_TRAFFIC" in volume_findings[0].reason_codes
    assert "VOLUME_DROP_VS_BASELINE" in volume_findings[0].reason_codes


def test_detect_volume_drop_negative_for_stable_low_volume_topic() -> None:
    rows = [
        EvidenceRow(
            metric_key="topic_messages_in_per_sec",
            value=0.8,
            labels={"env": "prod", "cluster_id": "cluster-a", "topic": "inventory"},
            scope=("prod", "cluster-a", "inventory"),
        ),
        EvidenceRow(
            metric_key="topic_messages_in_per_sec",
            value=0.7,
            labels={"env": "prod", "cluster_id": "cluster-a", "topic": "inventory"},
            scope=("prod", "cluster-a", "inventory"),
        ),
        EvidenceRow(
            metric_key="total_produce_requests_per_sec",
            value=200.0,
            labels={"env": "prod", "cluster_id": "cluster-a", "topic": "inventory"},
            scope=("prod", "cluster-a", "inventory"),
        ),
    ]

    result = detect_anomaly_findings(rows)

    assert all(f.anomaly_family != "VOLUME_DROP" for f in result.findings)


def test_detect_volume_drop_missing_series_is_unknown_not_zero() -> None:
    rows = [
        EvidenceRow(
            metric_key="total_produce_requests_per_sec",
            value=240.0,
            labels={"env": "prod", "cluster_id": "cluster-a", "topic": "inventory"},
            scope=("prod", "cluster-a", "inventory"),
        ),
    ]

    result = detect_anomaly_findings(rows)

    assert all(f.anomaly_family != "VOLUME_DROP" for f in result.findings)
