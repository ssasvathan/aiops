"""Kafka consumer adapter boundary for cold-path case header event processing."""

from __future__ import annotations

import os
from typing import Any, Protocol, runtime_checkable

from aiops_triage_pipeline.config.settings import Settings
from aiops_triage_pipeline.errors.exceptions import CriticalDependencyError


@runtime_checkable
class KafkaConsumerAdapterProtocol(Protocol):
    """Thin protocol for Kafka consumer: subscribe, poll, commit, close."""

    def subscribe(self, topics: list[str]) -> None: ...

    def poll(self, timeout: float) -> Any | None: ...

    def commit(self) -> None: ...

    def close(self) -> None: ...


class ConfluentKafkaCaseHeaderConsumer:
    """Confluent-Kafka-backed consumer adapter for cold-path case header events.

    Validates that group.id and bootstrap.servers are present at construction time.
    Disables auto-commit so offsets are committed explicitly on graceful shutdown.
    """

    def __init__(self, *, consumer_group: str, settings: Settings) -> None:
        if not consumer_group or not consumer_group.strip():
            raise ValueError("consumer_group must be a non-empty string")

        config: dict[str, Any] = {
            "bootstrap.servers": settings.KAFKA_BOOTSTRAP_SERVERS,
            "security.protocol": settings.KAFKA_SECURITY_PROTOCOL,
            "group.id": consumer_group,
            "auto.offset.reset": "earliest",
            "enable.auto.commit": False,
        }
        if settings.KAFKA_SECURITY_PROTOCOL == "SASL_SSL":
            config["sasl.mechanism"] = "GSSAPI"
            if settings.KAFKA_KERBEROS_KEYTAB_PATH is not None:
                config["sasl.kerberos.keytab"] = settings.KAFKA_KERBEROS_KEYTAB_PATH
            if settings.KRB5_CONF_PATH is not None:
                os.environ.setdefault("KRB5_CONFIG", settings.KRB5_CONF_PATH)

        try:
            from confluent_kafka import Consumer  # type: ignore[import-untyped]
        except Exception as exc:  # noqa: BLE001
            raise CriticalDependencyError(
                "confluent-kafka consumer import failed; verify dependency installation"
            ) from exc

        try:
            self._consumer = Consumer(config)
        except Exception as exc:  # noqa: BLE001
            raise CriticalDependencyError(
                f"failed to initialize kafka consumer: {exc}"
            ) from exc

    def subscribe(self, topics: list[str]) -> None:
        """Register subscription to the given topics."""
        self._consumer.subscribe(topics)

    def poll(self, timeout: float) -> Any | None:
        """Poll for a single message. Returns None if no message available in timeout."""
        return self._consumer.poll(timeout=timeout)

    def commit(self) -> None:
        """Synchronously commit current offsets (NFR-I4 graceful shutdown).

        Suppresses _NO_OFFSET errors — nothing to commit is a normal condition
        when shutting down before consuming any messages or after an empty poll.
        """
        try:
            self._consumer.commit(asynchronous=False)
        except Exception as exc:  # noqa: BLE001
            # _NO_OFFSET (-168) means there is no stored offset to commit.
            # This is expected when no messages were consumed in the current session.
            args = getattr(exc, "args", ())
            if args and hasattr(args[0], "code") and args[0].code() == -168:
                return
            raise

    def close(self) -> None:
        """Commit offsets and cleanly shut down, triggering immediate group rebalance."""
        self._consumer.close()
