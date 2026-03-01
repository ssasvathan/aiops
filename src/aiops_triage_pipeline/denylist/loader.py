"""Exposure denylist model and YAML loader."""

import re
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class DenylistV1(BaseModel, frozen=True):
    """Versioned exposure denylist loaded from config/denylist.yaml at startup.

    Attributes:
        schema_version: Contract version — always "v1"
        denylist_version: Human-readable version string stamped into every CaseFile for audit
        denied_field_names: Exact field names (case-insensitive) to remove from output dicts
        denied_value_patterns: Regex patterns — if a field's string value matches, remove the field
        description: Human description of denylist purpose and changelog
    """

    schema_version: Literal["v1"] = "v1"
    denylist_version: str = Field(min_length=1)
    denied_field_names: tuple[str, ...]
    denied_value_patterns: tuple[str, ...] = ()
    description: str = ""

    @field_validator("denied_value_patterns")
    @classmethod
    def validate_regex_patterns(cls, patterns: tuple[str, ...]) -> tuple[str, ...]:
        for pattern in patterns:
            try:
                re.compile(pattern)
            except re.error as exc:
                raise ValueError(f"Invalid regex pattern {pattern!r}: {exc}") from exc
        return patterns


def load_denylist(path: Path) -> DenylistV1:
    """Load and validate the exposure denylist YAML file.

    Args:
        path: Path to config/denylist.yaml (or equivalent)

    Returns:
        Validated, frozen DenylistV1 instance

    Raises:
        FileNotFoundError: If path does not exist
        yaml.YAMLError: If YAML is malformed
        pydantic.ValidationError: If YAML structure does not match DenylistV1 schema
    """
    import yaml  # Lazy import — only needed at startup

    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    return DenylistV1.model_validate(raw)
