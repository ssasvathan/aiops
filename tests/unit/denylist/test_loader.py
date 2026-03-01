from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from aiops_triage_pipeline.denylist.loader import DenylistV1, load_denylist


def test_load_denylist_returns_valid_model(denylist_yaml_path: Path) -> None:
    """load_denylist returns a validated DenylistV1 from a well-formed YAML."""
    denylist = load_denylist(denylist_yaml_path)
    assert isinstance(denylist, DenylistV1)
    assert denylist.denylist_version == "v1.0.0"
    assert "password" in denylist.denied_field_names
    assert "secret" in denylist.denied_field_names


def test_load_denylist_version_captured(denylist_yaml_path: Path) -> None:
    """denylist_version from YAML is accessible on the model."""
    denylist = load_denylist(denylist_yaml_path)
    assert denylist.denylist_version == "v1.0.0"


def test_load_denylist_is_frozen(denylist_yaml_path: Path) -> None:
    """Loaded DenylistV1 is immutable (frozen=True)."""
    denylist = load_denylist(denylist_yaml_path)
    with pytest.raises(ValidationError):
        denylist.denylist_version = "mutated"  # type: ignore[misc]


def test_load_denylist_missing_version_raises(tmp_path: Path) -> None:
    """Missing required denylist_version field raises ValidationError."""
    bad_yaml = tmp_path / "bad.yaml"
    bad_yaml.write_text(
        'schema_version: "v1"\n'
        "denied_field_names:\n"
        "  - password\n",
        encoding="utf-8",
    )
    with pytest.raises(ValidationError):
        load_denylist(bad_yaml)


def test_load_denylist_file_not_found() -> None:
    """load_denylist raises FileNotFoundError for non-existent path."""
    with pytest.raises(FileNotFoundError):
        load_denylist(Path("/nonexistent/denylist.yaml"))


def test_load_real_denylist_yaml() -> None:
    """The actual config/denylist.yaml loads successfully."""
    path = Path(__file__).parents[3] / "config" / "denylist.yaml"
    denylist = load_denylist(path)
    assert denylist.denylist_version  # Non-empty version
    assert len(denylist.denied_field_names) > 0


def test_load_denylist_malformed_yaml_raises(tmp_path: Path) -> None:
    """Syntactically invalid YAML raises yaml.YAMLError (not ValidationError)."""
    bad_yaml = tmp_path / "malformed.yaml"
    bad_yaml.write_text("}{: invalid: yaml syntax\n", encoding="utf-8")
    with pytest.raises(yaml.YAMLError):
        load_denylist(bad_yaml)


def test_denylist_invalid_regex_pattern_raises() -> None:
    """DenylistV1 with an invalid regex pattern raises ValidationError at construction time."""
    with pytest.raises(ValidationError):
        DenylistV1(
            denylist_version="v1.0.0",
            denied_field_names=(),
            denied_value_patterns=("[invalid",),  # dangling character class
        )
