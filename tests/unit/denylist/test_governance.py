"""Unit tests for denylist version tracking and changelog governance (AC 2, 3, 6)."""

from __future__ import annotations

import re
from pathlib import Path

from aiops_triage_pipeline.denylist.loader import load_denylist

# Project root is 3 levels up from this file's directory:
# test_governance.py -> denylist -> unit -> tests -> project_root
_PROJECT_ROOT = Path(__file__).parents[3]
_REAL_DENYLIST_PATH = _PROJECT_ROOT / "config" / "denylist.yaml"


def test_denylist_yaml_has_non_empty_version() -> None:
    """load_denylist() returns denylist_version matching semver pattern vX.Y.Z."""
    denylist = load_denylist(_REAL_DENYLIST_PATH)
    assert denylist.denylist_version, "denylist_version must not be empty"
    assert re.match(r"v\d+\.\d+\.\d+", denylist.denylist_version), (
        f"denylist_version {denylist.denylist_version!r} does not match semver pattern vX.Y.Z"
    )


def test_denylist_changelog_has_initial_entry() -> None:
    """denylist.changelog is non-empty and the first entry has all required fields non-empty."""
    denylist = load_denylist(_REAL_DENYLIST_PATH)
    assert denylist.changelog, "changelog must have at least one entry"
    first = denylist.changelog[0]
    assert first.version, "changelog[0].version must not be empty"
    assert first.date, "changelog[0].date must not be empty"
    assert first.author, "changelog[0].author must not be empty"
    assert first.reviewer, "changelog[0].reviewer must not be empty"
    assert first.summary, "changelog[0].summary must not be empty"


def test_changelog_entry_version_matches_denylist_version() -> None:
    """Latest changelog entry's version matches the current denylist_version."""
    denylist = load_denylist(_REAL_DENYLIST_PATH)
    assert denylist.changelog, "changelog must have at least one entry"
    latest = denylist.changelog[-1]
    assert latest.version == denylist.denylist_version, (
        f"Latest changelog entry version {latest.version!r} does not match "
        f"denylist_version {denylist.denylist_version!r}"
    )
