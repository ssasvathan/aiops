from __future__ import annotations

from datetime import UTC, datetime

import pytest

from aiops_triage_pipeline.contracts.case_header_event import CaseHeaderEventV1
from aiops_triage_pipeline.contracts.enums import (
    Action,
    CriticalityTier,
    Environment,
    EvidenceStatus,
)
from aiops_triage_pipeline.contracts.gate_input import Finding
from aiops_triage_pipeline.contracts.triage_excerpt import TriageExcerptV1
from aiops_triage_pipeline.errors.exceptions import CriticalDependencyError
from aiops_triage_pipeline.integrations.kafka import ConfluentKafkaCaseEventPublisher


class _RecordingProducer:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []
        self.polled: list[float] = []
        self.flush_calls: list[float] = []

    def produce(
        self,
        topic: str,
        *,
        key: bytes,
        value: bytes,
        on_delivery: object | None = None,
    ) -> None:
        self.calls.append(
            {
                "topic": topic,
                "key": key,
                "value": value,
                "on_delivery": on_delivery,
            }
        )

    def poll(self, timeout: float) -> int:
        self.polled.append(timeout)
        return 0

    def flush(self, timeout: float) -> int:
        self.flush_calls.append(timeout)
        return 0


class _FailingProducer(_RecordingProducer):
    def produce(
        self,
        topic: str,
        *,
        key: bytes,
        value: bytes,
        on_delivery: object | None = None,
    ) -> None:
        del topic, key, value, on_delivery
        raise RuntimeError("produce failed")


def _sample_case_header(case_id: str = "case-1") -> CaseHeaderEventV1:
    return CaseHeaderEventV1(
        case_id=case_id,
        env=Environment.PROD,
        cluster_id="cluster-a",
        stream_id="stream-orders",
        topic="orders",
        anomaly_family="VOLUME_DROP",
        criticality_tier=CriticalityTier.TIER_1,
        final_action=Action.TICKET,
        routing_key="OWN::Streaming::Payments::Topic",
        evaluation_ts=datetime(2026, 3, 6, 12, 0, tzinfo=UTC),
    )


def _sample_triage_excerpt(case_id: str = "case-1") -> TriageExcerptV1:
    return TriageExcerptV1(
        case_id=case_id,
        env=Environment.PROD,
        cluster_id="cluster-a",
        stream_id="stream-orders",
        topic="orders",
        anomaly_family="VOLUME_DROP",
        topic_role="SOURCE_TOPIC",
        criticality_tier=CriticalityTier.TIER_1,
        routing_key="OWN::Streaming::Payments::Topic",
        sustained=True,
        peak=False,
        evidence_status_map={"topic_messages_in_per_sec": EvidenceStatus.PRESENT},
        findings=(
            Finding(
                finding_id="f-volume-drop",
                name="VOLUME_DROP",
                is_anomalous=True,
                evidence_required=("topic_messages_in_per_sec",),
            ),
        ),
        triage_timestamp=datetime(2026, 3, 6, 12, 0, tzinfo=UTC),
    )


def test_publish_case_events_uses_deterministic_topics_keys_and_json_payloads() -> None:
    producer = _RecordingProducer()
    publisher = ConfluentKafkaCaseEventPublisher(producer=producer)
    case_header = _sample_case_header()
    triage_excerpt = _sample_triage_excerpt()

    publisher.publish_case_events(
        case_header_event=case_header,
        triage_excerpt_event=triage_excerpt,
    )

    assert [call["topic"] for call in producer.calls] == [
        "aiops-case-header",
        "aiops-triage-excerpt",
    ]
    assert producer.calls[0]["key"] == case_header.case_id.encode("utf-8")
    assert producer.calls[1]["key"] == triage_excerpt.case_id.encode("utf-8")
    assert producer.calls[0]["value"] == case_header.model_dump_json().encode("utf-8")
    assert producer.calls[1]["value"] == triage_excerpt.model_dump_json().encode("utf-8")
    assert producer.polled == [0.0, 0.0]
    assert producer.flush_calls == [10.0, 10.0]


def test_publish_case_events_wraps_producer_errors_as_critical_dependency() -> None:
    publisher = ConfluentKafkaCaseEventPublisher(producer=_FailingProducer())

    with pytest.raises(CriticalDependencyError, match="kafka publish failed"):
        publisher.publish_case_events(
            case_header_event=_sample_case_header(),
            triage_excerpt_event=_sample_triage_excerpt(),
        )
