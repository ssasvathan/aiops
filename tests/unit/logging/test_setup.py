import asyncio
import io
import json
import logging

import structlog

from aiops_triage_pipeline.logging.setup import (
    bind_correlation_id,
    clear_correlation_id,
    configure_logging,
    get_correlation_id,
    get_logger,
)


def _last_log(stream: io.StringIO) -> dict:
    """Parse last non-empty JSON log line from the stream."""
    lines = [line for line in stream.getvalue().strip().split("\n") if line.strip()]
    assert lines, f"Expected log output in stream, got empty. Stream value: {stream.getvalue()!r}"
    return json.loads(lines[-1])


def test_json_output_format(log_stream):
    """JSON renderer produces valid, parseable JSON on each log line."""
    get_logger("test").info("test_event")
    data = _last_log(log_stream)
    assert isinstance(data, dict)


def test_timestamp_field_present(log_stream):
    """Log output includes 'timestamp' field in ISO 8601 UTC format."""
    get_logger("test").info("test_event")
    data = _last_log(log_stream)
    assert "timestamp" in data
    assert "T" in data["timestamp"]  # ISO 8601 contains 'T' separator


def test_severity_field_present_and_uppercase(log_stream):
    """Log output has 'severity' (uppercase), not 'level' (NFR-O3)."""
    get_logger("test").info("test_event")
    data = _last_log(log_stream)
    assert data["severity"] == "INFO"
    assert "level" not in data


def test_component_field_present(log_stream):
    """Logger factory binds component name into each log event."""
    get_logger("pipeline.scheduler").info("test_event")
    data = _last_log(log_stream)
    assert data["component"] == "pipeline.scheduler"


def test_event_type_field_passthrough(log_stream):
    """Extra kwargs (event_type, case_id, etc.) are included in JSON output."""
    get_logger("test").info("test_event", event_type="evidence_collected", case_id="abc-123")
    data = _last_log(log_stream)
    assert data["event_type"] == "evidence_collected"
    assert data["case_id"] == "abc-123"


def test_correlation_id_appears_in_output(log_stream):
    """Bound correlation_id propagates into JSON via merge_contextvars processor."""
    bind_correlation_id("case-xyz-789")
    get_logger("test").info("test_event")
    data = _last_log(log_stream)
    assert data["correlation_id"] == "case-xyz-789"


def test_no_correlation_id_when_not_bound(log_stream):
    """'correlation_id' key is absent from output when not bound."""
    get_logger("test").info("test_event")
    data = _last_log(log_stream)
    assert "correlation_id" not in data


def test_correlation_id_cleared_after_clear(log_stream):
    """clear_correlation_id() removes correlation_id from subsequent log events."""
    bind_correlation_id("case-to-clear")
    clear_correlation_id()
    get_logger("test").info("test_event")
    data = _last_log(log_stream)
    assert "correlation_id" not in data


def test_get_correlation_id_returns_bound_value():
    """get_correlation_id() returns the currently bound correlation_id."""
    configure_logging("INFO")
    bind_correlation_id("test-correlation-abc")
    assert get_correlation_id() == "test-correlation-abc"


def test_get_correlation_id_returns_none_when_not_bound():
    """get_correlation_id() returns None when no correlation_id is bound."""
    configure_logging("INFO")
    assert get_correlation_id() is None


def test_debug_filtered_at_info_level(log_stream):
    """DEBUG messages produce no output when log_level=INFO (filter_by_level drops them)."""
    get_logger("test").debug("should_be_filtered")
    assert log_stream.getvalue().strip() == ""


def test_info_not_filtered_at_info_level(log_stream):
    """INFO messages are emitted when log_level=INFO."""
    get_logger("test").info("should_appear")
    lines = [line for line in log_stream.getvalue().strip().split("\n") if line.strip()]
    assert len(lines) == 1
    assert json.loads(lines[0])["event"] == "should_appear"


def test_warning_appears_at_info_level(log_stream):
    """WARNING messages are emitted at INFO level with severity='WARNING'."""
    get_logger("test").warning("warn_message")
    data = _last_log(log_stream)
    assert data["severity"] == "WARNING"


def test_error_appears_at_info_level(log_stream):
    """ERROR messages are emitted at INFO level with severity='ERROR' (AC2)."""
    get_logger("test").error("error_message")
    data = _last_log(log_stream)
    assert data["severity"] == "ERROR"


async def test_async_context_propagation():
    """correlation_id bound in parent propagates to child tasks via asyncio.create_task()."""
    configure_logging("INFO")
    bind_correlation_id("case-async-propagation-test")

    async def child_coroutine() -> str | None:
        return get_correlation_id()

    # asyncio.create_task() copies the current contextvars context to the child
    result = await asyncio.create_task(child_coroutine())
    assert result == "case-async-propagation-test"
