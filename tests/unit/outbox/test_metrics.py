from __future__ import annotations

from aiops_triage_pipeline.outbox.metrics import (
    record_outbox_delivery_slo_breach,
    record_outbox_health_snapshot,
    record_outbox_publish_latency,
)
from aiops_triage_pipeline.outbox.repository import OutboxHealthSnapshot


class _RecordingInstrument:
    def __init__(self) -> None:
        self.calls: list[tuple[float, dict[str, str] | None]] = []

    def add(self, value: float, attributes: dict[str, str] | None = None) -> None:
        self.calls.append((value, attributes))

    def record(self, value: float, attributes: dict[str, str] | None = None) -> None:
        self.calls.append((value, attributes))


def test_record_outbox_health_snapshot_uses_state_labels_and_no_counter_drift(monkeypatch) -> None:
    from aiops_triage_pipeline.outbox import metrics

    queue_depth = _RecordingInstrument()
    oldest_age = _RecordingInstrument()
    monkeypatch.setattr(metrics, "_queue_depth_by_state", queue_depth)
    monkeypatch.setattr(metrics, "_oldest_age_by_state", oldest_age)
    monkeypatch.setattr(
        metrics,
        "_prev_queue_depth_by_state",
        {state: 0 for state in ("PENDING_OBJECT", "READY", "RETRY", "DEAD", "SENT")},
    )

    snapshot = OutboxHealthSnapshot(
        pending_object_count=2,
        ready_count=3,
        retry_count=1,
        dead_count=0,
        sent_count=5,
        oldest_pending_object_age_seconds=10.0,
        oldest_ready_age_seconds=20.0,
        oldest_retry_age_seconds=30.0,
        oldest_dead_age_seconds=0.0,
    )
    record_outbox_health_snapshot(snapshot=snapshot)
    record_outbox_health_snapshot(snapshot=snapshot)

    by_state = {
        attrs["state"]: value
        for value, attrs in queue_depth.calls
        if attrs is not None
        and attrs.get("state") in {"PENDING_OBJECT", "READY", "RETRY", "DEAD", "SENT"}
    }
    assert by_state["PENDING_OBJECT"] == 0
    assert by_state["READY"] == 0
    assert by_state["RETRY"] == 0
    assert by_state["DEAD"] == 0
    assert by_state["SENT"] == 0
    assert len(oldest_age.calls) == 8


def test_record_outbox_publish_latency_clamps_negative_values(monkeypatch) -> None:
    from aiops_triage_pipeline.outbox import metrics

    latency_histogram = _RecordingInstrument()
    monkeypatch.setattr(metrics, "_publish_latency_histogram", latency_histogram)

    record_outbox_publish_latency(seconds=-3.0)
    assert latency_histogram.calls == [(0.0, None)]


def test_record_outbox_delivery_slo_breach_emits_counter_attributes(monkeypatch) -> None:
    from aiops_triage_pipeline.outbox import metrics

    breaches_counter = _RecordingInstrument()
    monkeypatch.setattr(metrics, "_delivery_slo_breach_total", breaches_counter)

    record_outbox_delivery_slo_breach(
        severity="warning",
        quantile="p99",
    )

    assert breaches_counter.calls == [
        (1, {"severity": "warning", "quantile": "p99"}),
    ]
