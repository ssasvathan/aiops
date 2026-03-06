"""Kafka publisher adapter for durable outbox event emission."""

from __future__ import annotations

import os
from typing import Any, Protocol

from aiops_triage_pipeline.config.settings import Settings, get_settings
from aiops_triage_pipeline.contracts.case_header_event import CaseHeaderEventV1
from aiops_triage_pipeline.contracts.triage_excerpt import TriageExcerptV1
from aiops_triage_pipeline.errors.exceptions import CriticalDependencyError, InvariantViolation
from aiops_triage_pipeline.outbox.publisher import (
    CaseEventPublisherProtocol,
    CaseHeaderPublisherProtocol,
)

CASE_HEADER_CONTRACT_ID = "CaseHeaderEvent.v1"
TRIAGE_EXCERPT_CONTRACT_ID = "TriageExcerpt.v1"
DEFAULT_CASE_HEADER_TOPIC = "aiops-case-header"
DEFAULT_TRIAGE_EXCERPT_TOPIC = "aiops-triage-excerpt"


class KafkaProducerProtocol(Protocol):
    """Minimal Producer protocol for confluent-kafka compatible clients."""

    def produce(
        self,
        topic: str,
        *,
        key: bytes,
        value: bytes,
        on_delivery: Any | None = None,
    ) -> None: ...

    def poll(self, timeout: float) -> int: ...

    def flush(self, timeout: float) -> int: ...


class ConfluentKafkaCaseEventPublisher(CaseEventPublisherProtocol, CaseHeaderPublisherProtocol):
    """Synchronous Kafka publisher for CaseHeaderEvent.v1 and TriageExcerpt.v1."""

    def __init__(
        self,
        *,
        settings: Settings | None = None,
        producer: KafkaProducerProtocol | None = None,
        case_header_topic: str = DEFAULT_CASE_HEADER_TOPIC,
        triage_excerpt_topic: str = DEFAULT_TRIAGE_EXCERPT_TOPIC,
        flush_timeout_seconds: float = 10.0,
    ) -> None:
        if flush_timeout_seconds <= 0:
            raise ValueError("flush_timeout_seconds must be > 0")
        self._settings = settings or get_settings()
        self._case_header_topic = case_header_topic
        self._triage_excerpt_topic = triage_excerpt_topic
        self._flush_timeout_seconds = flush_timeout_seconds
        self._producer = producer or self._build_producer(self._settings)

    def publish_case_header(self, *, event: CaseHeaderEventV1) -> None:
        """Compatibility path for existing single-header publishing tests."""
        self._publish_one(
            topic=self._case_header_topic,
            key=event.case_id.encode("utf-8"),
            value=event.model_dump_json().encode("utf-8"),
            contract_id=CASE_HEADER_CONTRACT_ID,
        )

    def publish_case_events(
        self,
        *,
        case_header_event: CaseHeaderEventV1,
        triage_excerpt_event: TriageExcerptV1,
    ) -> None:
        if case_header_event.case_id != triage_excerpt_event.case_id:
            raise InvariantViolation("header/excerpt case_id mismatch for Kafka publish")

        self._publish_one(
            topic=self._case_header_topic,
            key=case_header_event.case_id.encode("utf-8"),
            value=case_header_event.model_dump_json().encode("utf-8"),
            contract_id=CASE_HEADER_CONTRACT_ID,
        )
        self._publish_one(
            topic=self._triage_excerpt_topic,
            key=triage_excerpt_event.case_id.encode("utf-8"),
            value=triage_excerpt_event.model_dump_json().encode("utf-8"),
            contract_id=TRIAGE_EXCERPT_CONTRACT_ID,
        )

    def _publish_one(
        self,
        *,
        topic: str,
        key: bytes,
        value: bytes,
        contract_id: str,
    ) -> None:
        delivery_error: str | None = None

        def _delivery_callback(err: Any, msg: Any) -> None:  # noqa: ANN401
            del msg
            nonlocal delivery_error
            if err is not None:
                delivery_error = str(err)

        try:
            self._producer.produce(
                topic,
                key=key,
                value=value,
                on_delivery=_delivery_callback,
            )
            self._producer.poll(0.0)
            pending_count = self._producer.flush(self._flush_timeout_seconds)
        except CriticalDependencyError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise CriticalDependencyError(
                f"kafka publish failed for {contract_id} on topic={topic}: {exc}"
            ) from exc

        if delivery_error is not None:
            raise CriticalDependencyError(
                f"kafka delivery failed for {contract_id} on topic={topic}: {delivery_error}"
            )
        if pending_count not in (0, None):
            raise CriticalDependencyError(
                f"kafka flush timeout for {contract_id} on topic={topic}; "
                f"pending_messages={pending_count}"
            )

    @staticmethod
    def _build_producer(settings: Settings) -> KafkaProducerProtocol:
        try:
            from confluent_kafka import Producer  # type: ignore[import-untyped]
        except Exception as exc:  # noqa: BLE001
            raise CriticalDependencyError(
                "confluent-kafka producer import failed; verify dependency installation"
            ) from exc

        config: dict[str, Any] = {
            "bootstrap.servers": settings.KAFKA_BOOTSTRAP_SERVERS,
            "security.protocol": settings.KAFKA_SECURITY_PROTOCOL,
        }
        if settings.KAFKA_SECURITY_PROTOCOL == "SASL_SSL":
            config["sasl.mechanism"] = "GSSAPI"
            if settings.KAFKA_KERBEROS_KEYTAB_PATH is not None:
                config["sasl.kerberos.keytab"] = settings.KAFKA_KERBEROS_KEYTAB_PATH
            if settings.KRB5_CONF_PATH is not None:
                os.environ.setdefault("KRB5_CONFIG", settings.KRB5_CONF_PATH)

        try:
            return Producer(config)
        except Exception as exc:  # noqa: BLE001
            raise CriticalDependencyError(f"failed to initialize kafka producer: {exc}") from exc
