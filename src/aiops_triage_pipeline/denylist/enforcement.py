"""Exposure denylist enforcement — single shared function for all 4 output boundaries."""

import re
from typing import Any

from aiops_triage_pipeline.denylist.loader import DenylistV1


def apply_denylist(fields: dict[str, Any], denylist: DenylistV1) -> dict[str, Any]:
    """Remove fields matching denylist patterns from the input dict.

    This is the ONLY enforcement function in the codebase. All 4 output boundaries
    (TriageExcerpt assembly, Slack formatting, SN descriptions, LLM narrative surfacing)
    MUST call this function — no per-boundary reimplementation (architecture decision 2B).

    Field removal rules (applied in order):
    1. Field name (case-insensitive) matches any entry in denylist.denied_field_names → remove
    2. Field value is a string and matches any pattern in denylist.denied_value_patterns → remove
    3. Otherwise → include in output unchanged

    Note: Only flat dicts are handled. Nested field enforcement is deferred to Story 4.6.

    Args:
        fields: Input dict of field name → value pairs (e.g., excerpt fields, Slack payload)
        denylist: Loaded and validated DenylistV1 instance

    Returns:
        New dict containing only non-denied fields. Ordering is preserved.
    """
    denied_names_lower: frozenset[str] = frozenset(
        name.lower() for name in denylist.denied_field_names
    )
    compiled_patterns: list[re.Pattern[str]] = [
        re.compile(pattern) for pattern in denylist.denied_value_patterns
    ]

    result: dict[str, Any] = {}
    for key, value in fields.items():
        # Rule 1: Deny by field name (case-insensitive)
        if key.lower() in denied_names_lower:
            continue

        # Rule 2: Deny by value pattern (strings only)
        if compiled_patterns and isinstance(value, str):
            if any(pattern.search(value) for pattern in compiled_patterns):
                continue

        result[key] = value

    return result
