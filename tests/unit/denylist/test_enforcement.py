
from aiops_triage_pipeline.denylist.enforcement import (
    apply_denylist,
    apply_denylist_with_removed_count,
)
from aiops_triage_pipeline.denylist.loader import DenylistV1


def test_denied_field_by_name_is_absent(minimal_denylist: DenylistV1) -> None:
    """Field whose name matches denied_field_names is removed from output."""
    result = apply_denylist({"password": "hunter2", "topic": "my-topic"}, minimal_denylist)
    assert "password" not in result
    assert result == {"topic": "my-topic"}


def test_non_denied_field_passes_through(minimal_denylist: DenylistV1) -> None:
    """Field not in denied list is preserved exactly."""
    result = apply_denylist({"case_id": "abc-123", "topic": "payments"}, minimal_denylist)
    assert result == {"case_id": "abc-123", "topic": "payments"}


def test_empty_input_returns_empty(minimal_denylist: DenylistV1) -> None:
    """Empty input dict returns empty output dict."""
    assert apply_denylist({}, minimal_denylist) == {}


def test_field_name_match_is_case_insensitive(minimal_denylist: DenylistV1) -> None:
    """Field name matching is case-insensitive: 'Password' matches 'password' in denied list."""
    result = apply_denylist({"Password": "hunter2", "topic": "my-topic"}, minimal_denylist)
    assert "Password" not in result
    assert result["topic"] == "my-topic"


def test_field_removed_by_value_pattern(minimal_denylist: DenylistV1) -> None:
    """Field whose string value matches denied_value_patterns is removed."""
    result = apply_denylist(
        {"auth_header": "Bearer AbCdEfGhIjKlMnOpQrSt", "case_id": "x"},
        minimal_denylist,
    )
    assert "auth_header" not in result
    assert "case_id" in result


def test_non_matching_value_passes_through(minimal_denylist: DenylistV1) -> None:
    """Field with non-matching value is preserved even if name is not in denied list."""
    result = apply_denylist(
        {"description": "Normal text with no secrets", "count": 42},
        minimal_denylist,
    )
    assert result == {"description": "Normal text with no secrets", "count": 42}


def test_multiple_denied_fields_all_removed(minimal_denylist: DenylistV1) -> None:
    """All fields matching denied criteria are removed in one call."""
    result = apply_denylist(
        {"password": "x", "secret": "y", "topic": "z"},
        minimal_denylist,
    )
    assert "password" not in result
    assert "secret" not in result
    assert result == {"topic": "z"}


def test_empty_denylist_passes_all_fields(empty_denylist: DenylistV1) -> None:
    """With no denied names or patterns, all fields pass through unchanged."""
    fields = {"a": "1", "b": "2", "password": "actual_password"}
    result = apply_denylist(fields, empty_denylist)
    assert result == fields


def test_non_string_value_not_pattern_matched(minimal_denylist: DenylistV1) -> None:
    """Non-string values (int, bool, None) are never matched by value patterns."""
    result = apply_denylist(
        {"count": 42, "active": True, "nullable": None, "topic": "ok"},
        minimal_denylist,
    )
    # None of these are string values, so value-pattern matching is skipped
    assert "count" in result
    assert "active" in result
    assert "nullable" in result


def test_empty_patterns_name_denial_still_fires() -> None:
    """With denied_value_patterns=(), name-based denial applies; suspicious values pass through."""
    denylist = DenylistV1(
        denylist_version="v1.0.0",
        denied_field_names=("password",),
        denied_value_patterns=(),
    )
    result = apply_denylist(
        {
            "password": "hunter2",  # denied by name
            "auth_header": "Bearer AbCdEfGhIjKlMnOpQrSt",  # NOT denied — no patterns to match
        },
        denylist,
    )
    assert "password" not in result
    assert "auth_header" in result


def test_nested_mapping_fields_are_sanitized(minimal_denylist: DenylistV1) -> None:
    """Nested dict keys and values are enforced recursively."""
    result = apply_denylist(
        {
            "topic": "orders",
            "nested": {
                "Password": "hunter2",
                "token_like": "Bearer AbCdEfGhIjKlMnOpQrSt",
                "safe": "ok",
            },
        },
        minimal_denylist,
    )
    assert result["topic"] == "orders"
    assert result["nested"] == {"safe": "ok"}


def test_nested_list_values_are_sanitized(minimal_denylist: DenylistV1) -> None:
    """List items matching denied value patterns are removed recursively."""
    result = apply_denylist(
        {
            "findings": [
                "safe-message",
                "Bearer AbCdEfGhIjKlMnOpQrSt",
                {"secret": "x", "note": "kept"},
            ]
        },
        minimal_denylist,
    )
    assert result["findings"] == ["safe-message", {"note": "kept"}]


def test_removed_count_tracks_nested_list_removals_without_index_shift_loss(
    minimal_denylist: DenylistV1,
) -> None:
    sanitized, removed_count = apply_denylist_with_removed_count(
        {
            "findings": [
                "Bearer AbCdEfGhIjKlMnOpQrSt",
                {"secret": "x", "note": "kept"},
            ]
        },
        minimal_denylist,
    )
    assert sanitized["findings"] == [{"note": "kept"}]
    assert removed_count == 2
