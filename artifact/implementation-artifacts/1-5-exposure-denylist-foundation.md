# Story 1.5: Exposure Denylist Foundation

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a platform developer,
I want a versioned exposure denylist loaded from YAML with a single shared enforcement function,
so that sensitive fields are consistently redacted at all 4 output boundaries (TriageExcerpt, Slack, SN, LLM narrative) with zero reimplementation.

## Acceptance Criteria

1. **Given** a versioned YAML denylist file exists at `config/denylist.yaml`, **When** the application starts, **Then** `load_denylist(path)` loads it into a `DenylistV1` model that is `frozen=True` and has a `denylist_version` field

2. **And** a single `apply_denylist(fields: dict, denylist: DenylistV1) -> dict` function is available that removes any field whose name (case-insensitively) matches `denied_field_names`, or whose string value matches any pattern in `denied_value_patterns`

3. **And** `apply_denylist` returns a clean dict containing only the non-denied fields — denied fields are absent from the output (not redacted to a placeholder; entirely removed)

4. **And** `denylist_version` is accessible as `denylist.denylist_version` for stamping into CaseFiles (FR62 audit requirement)

5. **And** `config/denylist.yaml` is replaced from its current stub to a real denylist containing meaningful `denied_field_names` and `denied_value_patterns` covering the four denial categories: sensitive sink endpoints, credentials, restricted hostnames, Ranger access groups

6. **And** unit tests in `tests/unit/denylist/` verify:
   - Denied fields (by name) are absent from `apply_denylist` output
   - Non-denied fields pass through unchanged
   - Empty input dict `{}` returns empty output `{}`
   - Field name matching is case-insensitive (`Password` matches `password` in denied list)
   - Fields whose string values match `denied_value_patterns` are removed
   - `denylist.denylist_version` equals the version in the YAML
   - `load_denylist` raises a meaningful error on malformed YAML

## Tasks / Subtasks

- [ ] Task 1: Define `DenylistV1` frozen Pydantic model (AC: #1, #4, #5)
  - [ ] In `src/aiops_triage_pipeline/denylist/loader.py`, define `DenylistV1(BaseModel, frozen=True)` with fields:
    - `schema_version: Literal["v1"] = "v1"`
    - `denylist_version: str` — e.g., `"v1.0.0"` — stamped into CaseFiles
    - `denied_field_names: tuple[str, ...]` — case-insensitive exact field name matches
    - `denied_value_patterns: tuple[str, ...] = ()` — regex patterns for field values
    - `description: str = ""`
  - [ ] Confirm `DenylistV1` is NOT in `contracts/` — it belongs in `denylist/loader.py` (architecture decision)

- [ ] Task 2: Implement `load_denylist(path: Path) -> DenylistV1` (AC: #1)
  - [ ] In `src/aiops_triage_pipeline/denylist/loader.py`, implement `load_denylist(path: Path) -> DenylistV1`
  - [ ] Use `yaml.safe_load(path.read_text())` + `DenylistV1.model_validate(raw)` — same pattern as `load_policy_yaml` from Story 1.4
  - [ ] Let `model_validate` raise `ValidationError` for malformed YAML — no manual try/except needed at this layer
  - [ ] Note: `pyyaml` must be in `pyproject.toml` (added by Story 1.4 — if Story 1.4 is not complete, add `"pyyaml~=6.0"` here)

- [ ] Task 3: Implement `apply_denylist(fields: dict, denylist: DenylistV1) -> dict` (AC: #2, #3, #6)
  - [ ] In `src/aiops_triage_pipeline/denylist/enforcement.py`, implement `apply_denylist`
  - [ ] Compile `denylist.denied_value_patterns` to regex once per call using `re.compile`
  - [ ] Build `denied_names_lower: frozenset[str]` = `frozenset(n.lower() for n in denylist.denied_field_names)`
  - [ ] For each `(key, value)` in `fields.items()`:
    - If `key.lower() in denied_names_lower` → skip (deny by name)
    - Elif value is `str` and any compiled pattern matches → skip (deny by value pattern)
    - Else → include in result
  - [ ] Return `dict` of surviving fields (order preserved)
  - [ ] Handles flat dicts only — nested field enforcement is deferred to Story 4.6

- [ ] Task 4: Update `config/denylist.yaml` with real content (AC: #5)
  - [ ] Replace the current stub (`denied_fields: []`) with a real denylist (see Dev Notes for full YAML)
  - [ ] Set `denylist_version: "v1.0.0"`
  - [ ] Include `denied_field_names` for: credentials (password, secret, api_key, token…), sink endpoints (slack_webhook_url, pd_api_key, sn_password…), kerberos artifacts, connection strings
  - [ ] Include `denied_value_patterns` for: embedded passwords in URLs, bearer tokens, Ranger access group names

- [ ] Task 5: Update `denylist/__init__.py` exports
  - [ ] Export: `DenylistV1`, `load_denylist`, `apply_denylist`
  - [ ] Currently a 1-line stub — replace completely

- [ ] Task 6: Create unit tests (AC: #6)
  - [ ] Create `tests/unit/denylist/test_loader.py`:
    - Test `load_denylist` with a valid YAML file → returns `DenylistV1`
    - Test `denylist.denylist_version` equals YAML value
    - Test malformed YAML raises `ValidationError` or `yaml.YAMLError`
    - Test missing required field (`denylist_version` absent) raises `ValidationError`
  - [ ] Create `tests/unit/denylist/test_enforcement.py`:
    - Test denied field (exact name) is absent from output
    - Test non-denied field passes through
    - Test `{}` input → `{}` output
    - Test case-insensitive name match (`Password` denied when `password` is in list)
    - Test value pattern match (field with matching value is removed)
    - Test non-matching value passes through even if name is not in denied list
    - Test multiple denied fields in one call — all removed
    - Test `denied_value_patterns=()` (empty) → only name-based denial applies
  - [ ] Place shared fixtures (minimal `DenylistV1` instances) in `tests/unit/denylist/conftest.py`
  - [ ] Verify `tests/unit/denylist/__init__.py` exists (it does — from Story 1.1)

- [ ] Task 7: Verify quality gates
  - [ ] Run `uv run ruff check src/aiops_triage_pipeline/denylist/` — zero errors
  - [ ] Run `uv run pytest tests/unit/denylist/ -v` — all tests pass

## Dev Notes

### PREREQUISITE: Story 1.3 and 1.4 patterns established

- `frozen=True` Pydantic model pattern established in Stories 1.2 and 1.3 — follow exactly
- `yaml.safe_load()` + `model_validate()` loading pattern from Story 1.3 and Story 1.4's `load_policy_yaml`
- `pyyaml~=6.0` dependency should already be added by Story 1.4; if not, add it now

### `loader.py` — DenylistV1 Model and Loader

```python
"""Exposure denylist model and YAML loader."""

from pathlib import Path
from typing import Literal

from pydantic import BaseModel


class DenylistV1(BaseModel, frozen=True):
    """Versioned exposure denylist loaded from config/denylist.yaml at startup.

    Attributes:
        schema_version: Contract version — always "v1"
        denylist_version: Human-readable version string stamped into every CaseFile for audit
        denied_field_names: Exact field names (case-insensitive) to remove from output dicts
        denied_value_patterns: Regex patterns — if any field's string value matches, remove the field
        description: Human description of denylist purpose and changelog
    """

    schema_version: Literal["v1"] = "v1"
    denylist_version: str
    denied_field_names: tuple[str, ...]
    denied_value_patterns: tuple[str, ...] = ()
    description: str = ""


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
```

### `enforcement.py` — apply_denylist()

```python
"""Exposure denylist enforcement — single shared function for all 4 output boundaries."""

import re

from aiops_triage_pipeline.denylist.loader import DenylistV1


def apply_denylist(fields: dict, denylist: DenylistV1) -> dict:
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

    result: dict = {}
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
```

**Why enforcement.py imports from loader.py:**
`enforcement.py` imports `DenylistV1` from `denylist.loader` — this is an intra-package import, not a cross-package import. Both files are in `denylist/`, which is a cohesive package. This is acceptable and expected.

### `denylist/__init__.py` — Exports

```python
"""Exposure denylist — versioned YAML model, loader, and enforcement function."""

from aiops_triage_pipeline.denylist.enforcement import apply_denylist
from aiops_triage_pipeline.denylist.loader import DenylistV1, load_denylist

__all__ = [
    "DenylistV1",
    "apply_denylist",
    "load_denylist",
]
```

### `config/denylist.yaml` — Full Real Content (replace the stub completely)

```yaml
# Exposure Denylist v1.0.0 — aiOps Triage Pipeline
# Version: v1.0.0
# Status: ACTIVE
#
# Purpose: Prevent sensitive data from appearing at the 4 output boundaries:
#   1. TriageExcerpt (Kafka hot-path event)
#   2. Slack notification payloads
#   3. ServiceNow description/work notes
#   4. LLM narrative inputs/outputs
#
# Change management: This file is git-tracked. Changes require explicit security review.
# All denied_value_patterns are Python re-compatible regex strings.

schema_version: "v1"
denylist_version: "v1.0.0"
description: >
  Initial exposure denylist for aiOps pipeline v1.
  Covers credential field names, sink endpoint secrets,
  Kerberos auth artifacts, connection strings, and Ranger access groups.

# Exact field names to deny (case-insensitive, flat-key match).
# Any field with a name matching one of these (regardless of value) is removed.
denied_field_names:
  # --- Credentials & secrets ---
  - password
  - passwd
  - secret
  - secret_key
  - api_key
  - apikey
  - access_key
  - token
  - bearer_token
  - auth_token
  - credential
  - credentials
  - private_key
  - private_key_id
  - client_secret
  # --- Kerberos / auth artifacts ---
  - keytab_path
  - kerberos_keytab
  - kerberos_principal
  - krb5_conf_path
  - sasl_password
  - kafka_sasl_password
  # --- Sink endpoint secrets ---
  - slack_webhook_url
  - slack_bot_token
  - pd_api_key
  - pagerduty_api_key
  - sn_password
  - servicenow_password
  - llm_api_key
  - llm_bearer_token
  # --- Connection / DSN strings (often embed passwords) ---
  - database_url
  - db_url
  - connection_string
  - dsn
  - redis_url
  - s3_secret_key

# Regex patterns for field VALUES.
# Any field whose string value matches one of these patterns (re.search) is removed,
# regardless of its field name. Useful for catching credentials in unexpected fields.
denied_value_patterns:
  # Bearer tokens in values (e.g., Authorization header values)
  - "(?i)bearer\\s+[A-Za-z0-9._+/=\\-]{10,}"
  # Passwords embedded in URLs (e.g., postgresql://user:pass@host)
  - "(?i)://[^:@/]+:[^@/]{3,}@"
  # Apache Ranger access group names (common bank naming convention)
  - "(?i)\\bRANGER_[A-Z][A-Z0-9_]{2,}\\b"
  # Ranger-managed group prefixes
  - "(?i)\\b(rm|grp|acl)_[a-z][a-z0-9_]{2,}\\b"
```

### Import Boundary Rules (CRITICAL)

`denylist/` behaves as a **near-leaf package**:

- ✅ `from pydantic import BaseModel` (external library)
- ✅ `from typing import Literal`
- ✅ `from pathlib import Path`
- ✅ `import re`, `import yaml`
- ✅ Intra-package imports: `from aiops_triage_pipeline.denylist.loader import DenylistV1` (within `denylist/`)
- ❌ **NO** imports from `aiops_triage_pipeline.config`, `aiops_triage_pipeline.contracts`, `aiops_triage_pipeline.pipeline`, `aiops_triage_pipeline.models`, or any other package
- ❌ **NO** imports from `aiops_triage_pipeline.health`, `aiops_triage_pipeline.errors`, etc.

**Why the intra-package import in `enforcement.py` is OK:**
`enforcement.py` imports from `denylist.loader` — this is within the same `denylist/` package. It is NOT importing from another `aiops_triage_pipeline` sub-package. This is acceptable per the architecture's "each major component has clean import boundaries" rule.

**Callers of `apply_denylist`** (they import from `denylist/`, not the other way):
- `pipeline/stages/casefile.py` (Story 4.1)
- `integrations/slack.py` (Story 5.8)
- `integrations/servicenow.py` (Story 8.x)
- `diagnosis/prompt.py` (Story 6.1)

### Unit Test Pattern

**`tests/unit/denylist/conftest.py`** — shared fixtures:
```python
import pytest
from pathlib import Path

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
```

**`tests/unit/denylist/test_loader.py`**:
```python
import pytest
from pathlib import Path
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
    path = Path("config/denylist.yaml")
    denylist = load_denylist(path)
    assert denylist.denylist_version  # Non-empty version
    assert len(denylist.denied_field_names) > 0
```

**`tests/unit/denylist/test_enforcement.py`**:
```python
import pytest

from aiops_triage_pipeline.denylist.enforcement import apply_denylist
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
```

### What Is NOT In Scope for Story 1.5

- **Nested field enforcement** (Story 4.6): `apply_denylist` handles flat dicts only. Story 4.6 AC specifically calls out "edge cases with nested fields matching denylist patterns" — that's when TriageExcerpt fields are applied.
- **Denylist enforcement at specific boundaries** (Stories 4.1, 4.6, 5.8, 6.1, 8.x): This story builds the foundation (model + function + YAML). Wiring the function into each output boundary happens in the respective stories.
- **HealthRegistry** (Story 1.6): Component status tracking; separate story.
- **Structured logging setup** (Story 1.7): The denylist loader does not call `structlog` — logging of denylist application is the responsibility of the callers (casefile, slack, sn, llm stages).
- **`DenylistV1` in `contracts/`**: Intentionally NOT in contracts/. Architecture places denylist model in `denylist/loader.py`. The contracts package holds the 12 frozen event/policy contracts only.
- **Integration test** (`tests/integration/test_denylist_boundaries.py`): Integration test for all 4 output boundaries is part of Story 1.8 (docker-compose) / end-to-end. NFR-T2 calls out invariant verification for denylist — that's an integration test.

### Project Structure — Files to Create/Modify

```
src/aiops_triage_pipeline/denylist/
├── __init__.py               # UPDATE: export DenylistV1, load_denylist, apply_denylist
│                             # Currently a 1-line stub — replace completely
├── loader.py                 # IMPLEMENT: DenylistV1 model + load_denylist()
│                             # Currently an empty stub (0 bytes)
└── enforcement.py            # IMPLEMENT: apply_denylist()
                              # Currently an empty stub (0 bytes)

config/
└── denylist.yaml             # UPDATE: replace stub with real denylist v1.0.0

tests/unit/denylist/
├── __init__.py               # EXISTS: no changes
├── conftest.py               # CREATE: DenylistV1 fixtures
├── test_loader.py            # CREATE: loader unit tests
└── test_enforcement.py       # CREATE: enforcement unit tests
```

**Files NOT touched:**
- `contracts/` — DenylistV1 is NOT added here (architecture places it in `denylist/`)
- `config/policies/` — denylist.yaml lives in `config/`, not in `config/policies/`
- Any other source file — this story provides the foundation only

### Ruff Compliance Notes

Same rules as Stories 1.2–1.4:
- Python 3.13 native types: `dict`, `list`, `frozenset` — no `from typing import Dict, List, FrozenSet`
- `str | None` not `Optional[str]`
- Line length 100 chars max
- `import re` at top level in `enforcement.py` (it's always used)
- `import yaml` inside `load_denylist` (lazy — only used at startup, keeps pyyaml as optional-feeling)
- All imports used — no unused imports

**Note on `re.compile` inside `apply_denylist`:** Compiling patterns on every call is acceptable for Story 1.5 — the function is called at output boundaries (startup or per-case), not in tight loops. If this becomes a performance concern, a caching pattern can be added later. Do NOT prematurely optimize.

### Previous Story Intelligence (from Stories 1.2, 1.3, 1.4)

**Established patterns to follow exactly:**
- `frozen=True` on class declaration (not `model_config = ConfigDict(frozen=True)`)
- `tuple[str, ...]` for immutable sequences (not `list[str]`)
- `Literal["v1"] = "v1"` for schema_version field
- Fixtures in `conftest.py` — never in test files
- `uv run ruff check` must pass before review
- `str | None` not `Optional[str]`

**New patterns for Story 1.5 (not in previous stories):**
- `frozenset[str]` for O(1) membership testing of denied field names
- `re.compile(pattern)` + `pattern.search(value)` for regex value matching
- Intra-package imports within `denylist/` (enforcement.py imports from loader.py)
- `import yaml` inside function body (lazy import pattern — consistent with Story 1.4's `load_policy_yaml`)

**Critical difference from Story 1.4 `load_policy_yaml`:**
Story 1.5's `load_denylist` is NOT a generic function — it's specific to `DenylistV1`. This is intentional: the denylist is a singleton artifact with a fixed schema, not a polymorphic policy loader.

### Git Context

Recent commits:
- `8a581b9 Story 1.2: Code review fixes — contract validation hardening` — Story 1.2 complete
- `84a5b29 Story 1.2: Event Contract Models` — all event contracts implemented
- `328318d Story 1.1: Project Initialization & Repository Structure` — foundational structure in place

**Files confirmed to exist from Story 1.1 (all currently empty stubs):**
- `src/aiops_triage_pipeline/denylist/__init__.py` — 1-line stub
- `src/aiops_triage_pipeline/denylist/loader.py` — empty (0 bytes confirmed)
- `src/aiops_triage_pipeline/denylist/enforcement.py` — empty (0 bytes confirmed)
- `config/denylist.yaml` — stub with `denylist_version: "v1.0.0-stub"` and `denied_fields: []`
- `tests/unit/denylist/__init__.py` — empty

Story 1.3 (`ready-for-dev`) must be done before Story 1.5 to ensure pyyaml is available (if Story 1.4 hasn't been started). Story 1.5 does NOT depend on any Story 1.3 contract types — it's independent.

### References

- Architecture decision 2B (Versioned YAML, frozen Pydantic, single shared apply_denylist): [Source: `artifact/planning-artifacts/architecture.md#Security & Secrets`]
- FR25 (Exposure denylist on TriageExcerpt — denied categories): [Source: `artifact/planning-artifacts/epics.md#FR25`]
- FR62 (Exposure denylist as versioned reviewable artifact): [Source: `artifact/planning-artifacts/epics.md#FR62`]
- NFR-S5 (Denylist enforcement at every output boundary, zero violations): [Source: `artifact/planning-artifacts/epics.md#NFR-S5`]
- NFR-T2 (Invariant verification — includes denylist): [Source: `artifact/planning-artifacts/epics.md#NFR-T2`]
- 4 output boundary callers: [Source: `artifact/planning-artifacts/architecture.md#Cross-Cutting Concerns Mapping`]
- Story 4.6 (TriageExcerpt denylist enforcement — nested field extension): [Source: `artifact/planning-artifacts/epics.md#Story 4.6`]
- Complete project directory structure — denylist/ placement: [Source: `artifact/planning-artifacts/architecture.md#Complete Project Directory Structure`]
- Import rules table — denylist/ as provider package: [Source: `artifact/planning-artifacts/architecture.md#Import Rules`]

## Dev Agent Record

### Agent Model Used

claude-sonnet-4-6

### Debug Log References

### Completion Notes List

### File List
