"""Unit tests for cold-path Kafka consumer adapter boundary."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from aiops_triage_pipeline.errors.exceptions import CriticalDependencyError
from aiops_triage_pipeline.integrations.kafka_consumer import (
    ConfluentKafkaCaseHeaderConsumer,
    KafkaConsumerAdapterProtocol,
)


def _build_settings(**overrides: object) -> SimpleNamespace:
    base: dict[str, object] = {
        "KAFKA_BOOTSTRAP_SERVERS": "localhost:9092",
        "KAFKA_SECURITY_PROTOCOL": "PLAINTEXT",
        "KAFKA_KERBEROS_KEYTAB_PATH": None,
        "KRB5_CONF_PATH": None,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


class TestConfluentKafkaCaseHeaderConsumer:
    def test_construction_builds_consumer_with_correct_config(self, monkeypatch) -> None:
        """Consumer is built with group.id, bootstrap.servers, and auto-commit disabled."""
        built_configs: list[dict] = []

        class _CapturingConsumer:
            def __init__(self, config: dict) -> None:
                built_configs.append(config)

        fake_confluent = MagicMock()
        fake_confluent.Consumer = _CapturingConsumer
        monkeypatch.setitem(__import__("sys").modules, "confluent_kafka", fake_confluent)

        settings = _build_settings()
        ConfluentKafkaCaseHeaderConsumer(consumer_group="test-group", settings=settings)

        assert len(built_configs) == 1
        cfg = built_configs[0]
        assert cfg["bootstrap.servers"] == "localhost:9092"
        assert cfg["security.protocol"] == "PLAINTEXT"
        assert cfg["group.id"] == "test-group"
        assert cfg["enable.auto.commit"] is False

    def test_empty_consumer_group_raises(self, monkeypatch) -> None:
        """Empty or whitespace-only consumer_group raises ValueError before Kafka init."""
        settings = _build_settings()
        with pytest.raises(ValueError, match="consumer_group must be a non-empty string"):
            ConfluentKafkaCaseHeaderConsumer(consumer_group="", settings=settings)

    def test_whitespace_consumer_group_raises(self, monkeypatch) -> None:
        settings = _build_settings()
        with pytest.raises(ValueError, match="consumer_group must be a non-empty string"):
            ConfluentKafkaCaseHeaderConsumer(consumer_group="   ", settings=settings)

    def test_consumer_import_failure_raises_critical_dependency_error(
        self, monkeypatch
    ) -> None:
        """If confluent_kafka is unavailable, CriticalDependencyError is raised."""
        import sys

        real_confluent = sys.modules.pop("confluent_kafka", None)
        try:
            # Make the import fail
            monkeypatch.setitem(sys.modules, "confluent_kafka", None)  # type: ignore[arg-type]
            import importlib

            import aiops_triage_pipeline.integrations.kafka_consumer as mod
            importlib.reload(mod)

            settings = _build_settings()
            with pytest.raises(CriticalDependencyError):
                mod.ConfluentKafkaCaseHeaderConsumer(consumer_group="grp", settings=settings)
        finally:
            if real_confluent is not None:
                sys.modules["confluent_kafka"] = real_confluent
            importlib.reload(mod)

    def test_subscribe_delegates_to_consumer(self, monkeypatch) -> None:
        """subscribe() passes the topic list to the underlying consumer."""
        fake_consumer = MagicMock()
        fake_confluent = MagicMock()
        fake_confluent.Consumer.return_value = fake_consumer
        monkeypatch.setitem(__import__("sys").modules, "confluent_kafka", fake_confluent)

        adapter = ConfluentKafkaCaseHeaderConsumer(
            consumer_group="grp", settings=_build_settings()
        )
        adapter.subscribe(["aiops-case-header"])

        fake_consumer.subscribe.assert_called_once_with(["aiops-case-header"])

    def test_poll_delegates_to_consumer_with_timeout(self, monkeypatch) -> None:
        """poll() passes timeout kwarg and returns whatever the consumer returns."""
        fake_msg = MagicMock()
        fake_consumer = MagicMock()
        fake_consumer.poll.return_value = fake_msg
        fake_confluent = MagicMock()
        fake_confluent.Consumer.return_value = fake_consumer
        monkeypatch.setitem(__import__("sys").modules, "confluent_kafka", fake_confluent)

        adapter = ConfluentKafkaCaseHeaderConsumer(
            consumer_group="grp", settings=_build_settings()
        )
        result = adapter.poll(timeout=2.5)

        fake_consumer.poll.assert_called_once_with(timeout=2.5)
        assert result is fake_msg

    def test_poll_returns_none_when_no_message(self, monkeypatch) -> None:
        """poll() returns None when consumer returns None (timeout with no message)."""
        fake_consumer = MagicMock()
        fake_consumer.poll.return_value = None
        fake_confluent = MagicMock()
        fake_confluent.Consumer.return_value = fake_consumer
        monkeypatch.setitem(__import__("sys").modules, "confluent_kafka", fake_confluent)

        adapter = ConfluentKafkaCaseHeaderConsumer(
            consumer_group="grp", settings=_build_settings()
        )
        assert adapter.poll(timeout=1.0) is None

    def test_commit_is_synchronous(self, monkeypatch) -> None:
        """commit() calls consumer.commit with asynchronous=False (NFR-I4)."""
        fake_consumer = MagicMock()
        fake_confluent = MagicMock()
        fake_confluent.Consumer.return_value = fake_consumer
        monkeypatch.setitem(__import__("sys").modules, "confluent_kafka", fake_confluent)

        adapter = ConfluentKafkaCaseHeaderConsumer(
            consumer_group="grp", settings=_build_settings()
        )
        adapter.commit()

        fake_consumer.commit.assert_called_once_with(asynchronous=False)

    def test_close_delegates_to_consumer(self, monkeypatch) -> None:
        """close() calls consumer.close() to trigger rebalance."""
        fake_consumer = MagicMock()
        fake_confluent = MagicMock()
        fake_confluent.Consumer.return_value = fake_consumer
        monkeypatch.setitem(__import__("sys").modules, "confluent_kafka", fake_confluent)

        adapter = ConfluentKafkaCaseHeaderConsumer(
            consumer_group="grp", settings=_build_settings()
        )
        adapter.close()

        fake_consumer.close.assert_called_once()

    def test_sasl_ssl_adds_gssapi_config(self, monkeypatch) -> None:
        """SASL_SSL protocol adds gssapi mechanism to consumer config."""
        built_configs: list[dict] = []

        class _CapturingConsumer:
            def __init__(self, config: dict) -> None:
                built_configs.append(config)

        fake_confluent = MagicMock()
        fake_confluent.Consumer = _CapturingConsumer
        monkeypatch.setitem(__import__("sys").modules, "confluent_kafka", fake_confluent)

        settings = _build_settings(
            KAFKA_SECURITY_PROTOCOL="SASL_SSL",
            KAFKA_KERBEROS_KEYTAB_PATH="/etc/keytab",
            KRB5_CONF_PATH="/etc/krb5.conf",
        )
        ConfluentKafkaCaseHeaderConsumer(consumer_group="grp", settings=settings)

        cfg = built_configs[0]
        assert cfg["sasl.mechanism"] == "GSSAPI"
        assert cfg["sasl.kerberos.keytab"] == "/etc/keytab"

    def test_protocol_structural_subtype(self, monkeypatch) -> None:
        """ConfluentKafkaCaseHeaderConsumer satisfies KafkaConsumerAdapterProtocol."""
        fake_consumer = MagicMock()
        fake_confluent = MagicMock()
        fake_confluent.Consumer.return_value = fake_consumer
        monkeypatch.setitem(__import__("sys").modules, "confluent_kafka", fake_confluent)

        adapter = ConfluentKafkaCaseHeaderConsumer(
            consumer_group="grp", settings=_build_settings()
        )
        assert isinstance(adapter, KafkaConsumerAdapterProtocol)

    def test_commit_suppresses_no_offset_error(self, monkeypatch) -> None:
        """commit() silently swallows _NO_OFFSET (-168) errors (nothing to commit is normal)."""

        class _FakeKafkaError:
            def code(self) -> int:
                return -168  # _NO_OFFSET constant

        no_offset_exc = Exception("_NO_OFFSET")
        no_offset_exc.args = (_FakeKafkaError(),)

        fake_consumer = MagicMock()
        fake_consumer.commit.side_effect = no_offset_exc
        fake_confluent = MagicMock()
        fake_confluent.Consumer.return_value = fake_consumer
        monkeypatch.setitem(__import__("sys").modules, "confluent_kafka", fake_confluent)

        adapter = ConfluentKafkaCaseHeaderConsumer(
            consumer_group="grp", settings=_build_settings()
        )
        # Must not raise — _NO_OFFSET is a normal shutdown condition.
        adapter.commit()

    def test_commit_reraises_non_no_offset_errors(self, monkeypatch) -> None:
        """commit() re-raises exceptions that do not carry a _NO_OFFSET (-168) error code."""

        class _FakeKafkaError:
            def code(self) -> int:
                return -1  # Some other Kafka error code

        # Build an exception whose first arg has a .code() returning non-(-168)
        other_exc = Exception(_FakeKafkaError())

        fake_consumer = MagicMock()
        fake_consumer.commit.side_effect = other_exc
        fake_confluent = MagicMock()
        fake_confluent.Consumer.return_value = fake_consumer
        monkeypatch.setitem(__import__("sys").modules, "confluent_kafka", fake_confluent)

        adapter = ConfluentKafkaCaseHeaderConsumer(
            consumer_group="grp", settings=_build_settings()
        )
        with pytest.raises(Exception):
            adapter.commit()
