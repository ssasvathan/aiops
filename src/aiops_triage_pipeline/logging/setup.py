"""structlog configuration — structured logging with correlation_id propagation.

This module configures structlog's processor pipeline for consistent output
across all pipeline components. Call configure_logging() ONCE at application startup.
Calling it multiple times changes the pipeline for uncached loggers; loggers already
cached via cache_logger_on_first_use=True retain the first pipeline until
structlog.reset_defaults() is called.

Two output formats are supported:
- console (default): human-readable output via structlog.dev.ConsoleRenderer
- json: structured JSON output for log aggregation (set LOG_FORMAT=json or pass
  log_format="json" to configure_logging())

Correlation ID (case_id) propagates through asyncio task-local context using
Python's contextvars — asyncio.create_task() inherits the parent's context,
so correlation_id set in the scheduler propagates to all case-processing coroutines.

Required fields per NFR-O3: timestamp, correlation_id, component, event_type, severity
JSON format uses 'severity' (NFR-O3 field rename); console format uses 'level' natively.
"""

import logging
import os
import sys
from typing import Any

import structlog

_VALID_LOG_LEVELS = frozenset({"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"})


def _add_severity(
    logger: Any,
    method: str,
    event_dict: dict[str, Any],
) -> dict[str, Any]:
    """Rename 'level' to 'severity', uppercased, per NFR-O3 field schema.

    structlog.stdlib.add_log_level adds 'level' with lowercase values ("info", "warning").
    This processor renames it to 'severity' with uppercase values ("INFO", "WARNING").
    """
    event_dict["severity"] = event_dict.pop("level", method).upper()
    return event_dict


def configure_logging(log_level: str = "INFO", log_format: str | None = None) -> None:
    """Configure structlog with pod identity and correlation_id propagation.

    Call once at application startup before any pipeline operations begin.
    Raises ValueError for unrecognized log_level values. Note: loggers already cached
    via cache_logger_on_first_use retain the prior processor chain until
    structlog.reset_defaults() is called.

    Also binds pod_name and pod_namespace from POD_NAME/POD_NAMESPACE env vars to the
    structlog context (FR57/NFR-A6). When these env vars are present, every subsequent
    log event carries the pod identity automatically via merge_contextvars.

    Format selection (in precedence order):
    1. log_format argument if provided
    2. LOG_FORMAT environment variable
    3. "console" default (human-readable output for local development)
    Set LOG_FORMAT=json (or pass log_format="json") for production/log-aggregation use.

    Console processor pipeline (default):
    1. merge_contextvars — injects asyncio task-local fields (correlation_id, pod_name,
       pod_namespace)
    2. filter_by_level — drops events below configured level (stdlib-backed)
    3. add_log_level — adds 'level' field
    4. TimeStamper — adds ISO 8601 UTC 'timestamp' field
    5. StackInfoRenderer — formats stack_info if present
    6. format_exc_info — renders ``exc_info=True`` traceback into text
    7. ConsoleRenderer — renders human-readable colored output

    JSON processor pipeline (log_format="json" or LOG_FORMAT=json):
    1. merge_contextvars — injects asyncio task-local fields
    2. filter_by_level — drops events below configured level (stdlib-backed)
    3. add_log_level — adds 'level' field
    4. _add_severity — renames 'level' → 'severity', uppercased (NFR-O3)
    5. TimeStamper — adds ISO 8601 UTC 'timestamp' field (NFR-O3)
    6. StackInfoRenderer — formats stack_info if present
    7. format_exc_info — renders ``exc_info=True`` traceback into JSON-safe text
    8. JSONRenderer — renders event dict as JSON string

    Args:
        log_level: Minimum log level: CRITICAL, DEBUG, ERROR, INFO, WARNING. Default INFO.
        log_format: Output format override. "json" → JSON pipeline. "console" → console
            pipeline (suppresses LOG_FORMAT env var lookup). None → read LOG_FORMAT env
            var, default "console". Unrecognized values emit a warning and fall back to
            console.

    Raises:
        ValueError: If log_level is not a recognised stdlib logging level name.
    """
    normalized = log_level.upper()
    if normalized not in _VALID_LOG_LEVELS:
        raise ValueError(
            f"Invalid log_level {log_level!r}. Must be one of: "
            f"{', '.join(sorted(_VALID_LOG_LEVELS))}"
        )
    level = getattr(logging, normalized)
    root = logging.getLogger()
    root.setLevel(level)

    if not root.handlers:
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(logging.Formatter("%(message)s"))
        root.addHandler(handler)

    fmt = (log_format or os.getenv("LOG_FORMAT", "console")).lower()

    if fmt not in {"json", "console"}:
        logging.warning(
            "Unrecognized LOG_FORMAT value %r — falling back to console. "
            "Valid values: json, console.",
            fmt,
        )
        fmt = "console"

    if fmt == "json":
        processors = [
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_log_level,
            _add_severity,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ]
    else:
        processors = [
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.dev.ConsoleRenderer(colors=sys.stderr.isatty()),
        ]

    structlog.configure(
        processors=processors,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        cache_logger_on_first_use=True,
    )
    pod_name = os.getenv("POD_NAME")
    pod_namespace = os.getenv("POD_NAMESPACE")
    _pod_bindings: dict[str, str] = {}
    if pod_name:
        _pod_bindings["pod_name"] = pod_name
    if pod_namespace:
        _pod_bindings["pod_namespace"] = pod_namespace
    if _pod_bindings:
        structlog.contextvars.bind_contextvars(**_pod_bindings)


def get_logger(component: str) -> structlog.BoundLogger:
    """Return a structlog logger pre-bound with component name.

    Component names follow dot-notation package paths:
        logger = get_logger("pipeline.scheduler")
        logger = get_logger("health.registry")
        logger = get_logger("evidence.builder")

    The 'component' key appears in every JSON log event from this logger.
    Additional context (correlation_id) is injected automatically from
    asyncio task-local storage via the merge_contextvars processor.

    Args:
        component: Dot-notation module/service identifier

    Returns:
        structlog BoundLogger with component pre-bound
    """
    return structlog.get_logger(component).bind(component=component)


def bind_correlation_id(correlation_id: str) -> None:
    """Bind correlation_id to the current asyncio task context.

    The correlation_id (typically case_id) appears in all subsequent log events
    from the current coroutine and any child tasks created via asyncio.create_task().

    Args:
        correlation_id: Case ID or request ID for log correlation (e.g., "case-abc-123")
    """
    structlog.contextvars.bind_contextvars(correlation_id=correlation_id)


def clear_correlation_id() -> None:
    """Clear correlation_id from the current asyncio task context.

    Removes only the correlation_id key, leaving any other bound context vars intact.
    Call at the end of each case processing cycle to prevent stale correlation_ids
    from leaking into the next evaluation interval.
    """
    structlog.contextvars.unbind_contextvars("correlation_id")


def get_correlation_id() -> str | None:
    """Return the correlation_id from the current asyncio task context.

    Returns:
        The correlation_id string if set, None otherwise.
    """
    return structlog.contextvars.get_contextvars().get("correlation_id")
