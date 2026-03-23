"""ATDD red-phase acceptance tests for Story 3.1 cold-path Kafka consumer runtime mode."""

from __future__ import annotations

import importlib
from unittest.mock import MagicMock

import pytest

from aiops_triage_pipeline import __main__
from aiops_triage_pipeline.config.settings import Settings
from tests.atdd.fixtures.story_3_1_test_data import (
    RecordingAsyncHealthRegistry,
    build_cold_path_settings,
    expected_consumer_binding,
)


def _build_min_settings_for_validation(**overrides: object) -> Settings:
    base: dict[str, object] = {
        "_env_file": None,
        "KAFKA_BOOTSTRAP_SERVERS": "localhost:9092",
        "DATABASE_URL": "postgresql+psycopg://u:p@h/db",
        "REDIS_URL": "redis://localhost:6379/0",
        "S3_ENDPOINT_URL": "http://localhost:9000",
        "S3_ACCESS_KEY": "key",
        "S3_SECRET_KEY": "secret",
        "S3_BUCKET": "bucket",
    }
    base.update(overrides)
    return Settings(**base)


def test_p0_settings_expose_cold_path_consumer_defaults_and_validation() -> None:
    """Given cold-path runtime config, canonical group/topic and poll-timeout validation exist."""
    settings = _build_min_settings_for_validation()
    consumer_group, topic = expected_consumer_binding()

    assert settings.KAFKA_COLD_PATH_CONSUMER_GROUP == consumer_group
    assert settings.KAFKA_CASE_HEADER_TOPIC == topic
    assert settings.KAFKA_COLD_PATH_POLL_TIMEOUT_SECONDS > 0

    with pytest.raises(ValueError, match="KAFKA_COLD_PATH_POLL_TIMEOUT_SECONDS"):
        _build_min_settings_for_validation(KAFKA_COLD_PATH_POLL_TIMEOUT_SECONDS=0)


def test_p0_cold_path_runtime_logs_consumer_group_and_topic_on_start(monkeypatch) -> None:
    """Given cold-path mode starts, then startup log includes consumer group/topic wiring."""
    logger = MagicMock()
    settings = build_cold_path_settings()
    consumer_group, topic = expected_consumer_binding()

    monkeypatch.setattr(__main__, "_bootstrap_mode", lambda mode: (settings, logger, MagicMock()))
    monkeypatch.setattr(
        __main__, "build_s3_object_store_client_from_settings", lambda _: MagicMock()
    )

    __main__._run_cold_path()

    start_call = next(
        call
        for call in logger.info.call_args_list
        if call.args and call.args[0] == "cold_path_mode_started"
    )
    assert start_call.kwargs["consumer_group"] == consumer_group
    assert start_call.kwargs["topic"] == topic


def test_p1_cold_path_runtime_reports_connected_poll_and_commit_health_transitions(
    monkeypatch,
) -> None:
    """Given cold-path consumer lifecycle, then health transitions include connected/poll/commit."""
    logger = MagicMock()
    settings = build_cold_path_settings()
    health_registry = RecordingAsyncHealthRegistry()

    monkeypatch.setattr(__main__, "_bootstrap_mode", lambda mode: (settings, logger, MagicMock()))
    monkeypatch.setattr(__main__, "get_health_registry", lambda: health_registry, raising=False)
    monkeypatch.setattr(
        __main__, "build_s3_object_store_client_from_settings", lambda _: MagicMock()
    )

    __main__._run_cold_path()

    transition_components = {
        transition.component.lower() for transition in health_registry.transitions
    }
    assert any("connected" in component for component in transition_components)
    assert any("poll" in component for component in transition_components)
    assert any("commit" in component for component in transition_components)


def test_p1_kafka_consumer_adapter_module_exposes_protocol_and_confluent_adapter() -> None:
    """Given cold-path adapter boundary, module exposes protocol and confluent adapter types."""
    module = importlib.import_module("aiops_triage_pipeline.integrations.kafka_consumer")

    protocol_names = (
        "KafkaConsumerAdapterProtocol",
        "KafkaConsumerProtocol",
        "CaseHeaderConsumerProtocol",
    )
    adapter_names = (
        "ConfluentKafkaCaseHeaderConsumer",
        "ConfluentKafkaConsumerAdapter",
        "ConfluentKafkaCaseHeaderConsumerAdapter",
    )

    assert any(hasattr(module, name) for name in protocol_names)
    assert any(hasattr(module, name) for name in adapter_names)
