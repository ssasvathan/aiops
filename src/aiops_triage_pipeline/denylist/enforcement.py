"""Exposure denylist enforcement — single shared function for all 4 output boundaries."""

import re
from typing import Any

from aiops_triage_pipeline.denylist.loader import DenylistV1


def apply_denylist(fields: dict[str, Any], denylist: DenylistV1) -> dict[str, Any]:
    """Remove fields matching denylist patterns from the input mapping recursively.

    This is the ONLY enforcement function in the codebase. All 4 output boundaries
    (TriageExcerpt assembly, Slack formatting, SN descriptions, LLM narrative surfacing)
    MUST call this function — no per-boundary reimplementation (architecture decision 2B).

    Field removal rules (applied in order):
    1. Field name (case-insensitive) matches any entry in denylist.denied_field_names → remove
    2. Field value is a string and matches any pattern in denylist.denied_value_patterns → remove
    3. Otherwise → include in output unchanged

    Args:
        fields: Input dict of field name → value pairs (e.g., excerpt fields, Slack payload)
        denylist: Loaded and validated DenylistV1 instance

    Returns:
        New dict containing only non-denied fields. Ordering is preserved.
    """
    sanitized, _ = apply_denylist_with_removed_count(fields, denylist)
    return sanitized


def apply_denylist_with_removed_count(
    fields: dict[str, Any], denylist: DenylistV1
) -> tuple[dict[str, Any], int]:
    """Apply denylist recursively and return sanitized payload plus removed-field count."""
    denied_names_lower: frozenset[str] = frozenset(
        name.lower() for name in denylist.denied_field_names
    )
    compiled_patterns: list[re.Pattern[str]] = [
        re.compile(pattern) for pattern in denylist.denied_value_patterns
    ]
    return _sanitize_mapping(
        fields=fields,
        denied_names_lower=denied_names_lower,
        compiled_patterns=compiled_patterns,
    )


def _sanitize_mapping(
    *,
    fields: dict[str, Any],
    denied_names_lower: frozenset[str],
    compiled_patterns: list[re.Pattern[str]],
) -> tuple[dict[str, Any], int]:
    result: dict[str, Any] = {}
    removed_count = 0
    for key, value in fields.items():
        # Rule 1: Deny by field name (case-insensitive)
        if key.lower() in denied_names_lower:
            removed_count += 1
            continue

        keep_value, sanitized_value, nested_removed_count = _sanitize_value(
            value=value,
            denied_names_lower=denied_names_lower,
            compiled_patterns=compiled_patterns,
        )
        if not keep_value:
            removed_count += 1 + nested_removed_count
            continue

        result[key] = sanitized_value
        removed_count += nested_removed_count
    return result, removed_count


def _sanitize_value(
    *,
    value: Any,
    denied_names_lower: frozenset[str],
    compiled_patterns: list[re.Pattern[str]],
) -> tuple[bool, Any, int]:
    if isinstance(value, dict):
        sanitized_mapping, removed_count = _sanitize_mapping(
            fields=value,
            denied_names_lower=denied_names_lower,
            compiled_patterns=compiled_patterns,
        )
        return True, sanitized_mapping, removed_count

    if isinstance(value, list):
        sanitized_items: list[Any] = []
        removed_count = 0
        for item in value:
            keep_item, sanitized_item, nested_removed_count = _sanitize_value(
                value=item,
                denied_names_lower=denied_names_lower,
                compiled_patterns=compiled_patterns,
            )
            removed_count += nested_removed_count
            if not keep_item:
                removed_count += 1
                continue
            sanitized_items.append(sanitized_item)
        return True, sanitized_items, removed_count

    if isinstance(value, str) and any(pattern.search(value) for pattern in compiled_patterns):
        return False, None, 0

    return True, value, 0
