"""Shared fixtures for denylist unit tests."""

from pathlib import Path

import pytest

from aiops_triage_pipeline.denylist.loader import DenylistV1


@pytest.fixture
def minimal_denylist() -> DenylistV1:
    """Minimal DenylistV1 with one denied name and one denied pattern."""
    return DenylistV1(
        denylist_version="v1.0.0",
        denied_field_names=("password", "secret"),
        denied_value_patterns=("(?i)bearer\\s+[A-Za-z0-9]{10,}",),
        description="Test denylist",
    )


@pytest.fixture
def empty_denylist() -> DenylistV1:
    """DenylistV1 with no denied names or patterns — everything passes through."""
    return DenylistV1(
        denylist_version="v0.0.0",
        denied_field_names=(),
    )


@pytest.fixture
def denylist_yaml_path(tmp_path: Path) -> Path:
    """Write a minimal denylist YAML to a temp file and return its path."""
    content = (
        'schema_version: "v1"\n'
        'denylist_version: "v1.0.0"\n'
        "denied_field_names:\n"
        "  - password\n"
        "  - secret\n"
        "denied_value_patterns:\n"
        '  - "(?i)bearer\\\\s+[A-Za-z0-9]{10,}"\n'
    )
    path = tmp_path / "denylist.yaml"
    path.write_text(content, encoding="utf-8")
    return path
