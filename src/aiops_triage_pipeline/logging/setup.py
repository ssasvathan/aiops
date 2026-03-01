"""structlog configuration — structured JSON logging with correlation_id propagation.

This module configures structlog's processor pipeline for consistent JSON output
across all pipeline components. Call configure_logging() at application startup.

Correlation ID (case_id) propagates through asyncio task-local context using
Python's contextvars — asyncio.create_task() inherits the parent's context,
so correlation_id set in the scheduler propagates to all case-processing coroutines.

Required fields per NFR-O3: timestamp, correlation_id, component, event_type, severity
"""

import logging
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


def configure_logging(log_level: str = "INFO") -> None:
    """Configure structlog for structured JSON output with correlation_id propagation.

    Call once at application startup before any pipeline operations begin.
    Raises ValueError for unrecognized log_level values. Note: loggers already cached
    via cache_logger_on_first_use retain the prior processor chain until
    structlog.reset_defaults() is called.

    Processor pipeline:
    1. merge_contextvars — injects asyncio task-local fields (correlation_id)
    2. filter_by_level — drops events below configured level (stdlib-backed)
    3. add_log_level — adds 'level' field
    4. _add_severity — renames 'level' → 'severity', uppercased (NFR-O3)
    5. TimeStamper — adds ISO 8601 UTC 'timestamp' field (NFR-O3)
    6. StackInfoRenderer — formats stack_info if present
    7. JSONRenderer — renders event dict as JSON string

    Args:
        log_level: Minimum log level: CRITICAL, DEBUG, ERROR, INFO, WARNING. Default INFO.

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

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_log_level,
            _add_severity,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        cache_logger_on_first_use=True,
    )


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
