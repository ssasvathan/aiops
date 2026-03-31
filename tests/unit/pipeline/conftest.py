import io
import logging

import pytest
import structlog

from aiops_triage_pipeline.logging.setup import configure_logging


@pytest.fixture(autouse=True)
def reset_structlog():
    """Reset structlog and stdlib root logger after each test to prevent state bleed."""
    yield
    structlog.reset_defaults()
    structlog.contextvars.clear_contextvars()
    root = logging.getLogger()
    root.setLevel(logging.WARNING)
    root.handlers.clear()


@pytest.fixture
def log_stream():
    """Configure logging to write to StringIO for test output inspection."""
    stream = io.StringIO()
    root = logging.getLogger()
    root.handlers.clear()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(logging.Formatter("%(message)s"))
    root.addHandler(handler)
    configure_logging("INFO", log_format="json")
    return stream
