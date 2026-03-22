# Story 1.4: Configuration & Environment Management

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a platform developer,
I want environment-aware configuration with per-integration mode controls,
so that the pipeline loads the correct settings per environment and every outbound integration can be independently set to OFF/LOG/MOCK/LIVE mode (FR57).

## Acceptance Criteria

1. **Given** `APP_ENV` is set to `local`, `dev`, `uat`, or `prod`, **When** the application starts, **Then** `pydantic-settings` loads the corresponding `config/.env.{APP_ENV}` configuration file

2. **And** direct environment variables override `.env` file values (K8s injection precedence — native pydantic-settings behaviour)

3. **And** per-integration mode variables are available: `INTEGRATION_MODE_{PD|SLACK|SN|LLM}` with valid values `OFF/LOG/MOCK/LIVE`, defaulting to `LOG`

4. **And** the `Settings` model exposes the environment's maximum allowed action via a `max_action` property: `local=OBSERVE`, `dev=NOTIFY`, `uat=TICKET`, `prod=PAGE`

5. **And** `config/.env.local` and `config/.env.dev` are committed (no secrets), and `config/.env.uat.template` and `config/.env.prod.template` exist as templates — **these files already exist from Story 1.1 and must NOT be modified unless a required field is missing**

6. **And** when `KAFKA_SECURITY_PROTOCOL=SASL_SSL`, startup validation asserts that `KAFKA_KERBEROS_KEYTAB_PATH` and `KRB5_CONF_PATH` reference files that exist on disk; missing files cause a `ValueError` at `Settings` creation time (fail-fast at boot, not mid-pipeline)

7. **And** active configuration (excluding secret values) is logged at startup per NFR-O4 using structlog, with `S3_SECRET_KEY` and `DATABASE_URL` password masked as `[REDACTED]`

8. **And** unit tests in `tests/unit/config/test_settings.py` verify: env file loading, K8s env var override precedence, integration mode defaults and override, Kerberos validation pass and fail paths, `max_action` property correctness, and startup config logging

## Tasks / Subtasks

- [x] Task 1: Define `AppEnv` and `IntegrationMode` enums (AC: #3, #4)
  - [x] In `src/aiops_triage_pipeline/config/settings.py`, define `AppEnv(str, Enum)` with values: `local`, `dev`, `uat`, `prod`
  - [x] Define `IntegrationMode(str, Enum)` with values: `OFF`, `LOG`, `MOCK`, `LIVE`
  - [x] Define `ENV_ACTION_CAPS: dict[str, str]` mapping each `AppEnv` value to its maximum action cap string

- [x] Task 2: Implement `Settings` class (AC: #1, #2, #3, #4)
  - [x] Read `_APP_ENV = os.getenv("APP_ENV", "local")` at **module level** (before class body) to select the correct env file
  - [x] Create `Settings(BaseSettings)` with `model_config = SettingsConfigDict(env_file=f"config/.env.{_APP_ENV}", env_file_encoding="utf-8", extra="ignore")`
  - [x] Define all fields: `APP_ENV`, `KAFKA_BOOTSTRAP_SERVERS`, `KAFKA_SECURITY_PROTOCOL`, `KAFKA_KERBEROS_KEYTAB_PATH`, `KRB5_CONF_PATH`, `DATABASE_URL`, `REDIS_URL`, `S3_ENDPOINT_URL`, `S3_ACCESS_KEY`, `S3_SECRET_KEY`, `S3_BUCKET`, `INTEGRATION_MODE_PD`, `INTEGRATION_MODE_SLACK`, `INTEGRATION_MODE_SN`, `INTEGRATION_MODE_LLM`
  - [x] Add `max_action` computed property returning `ENV_ACTION_CAPS.get(self.APP_ENV.value, "OBSERVE")`

- [x] Task 3: Implement Kerberos startup validation (AC: #6)
  - [x] Add `@model_validator(mode="after")` method `validate_kerberos_files(self) -> "Settings"` to `Settings`
  - [x] If `KAFKA_SECURITY_PROTOCOL == "SASL_SSL"`: check `KAFKA_KERBEROS_KEYTAB_PATH` is set and `Path(path).exists()`; check `KRB5_CONF_PATH` is set and `Path(path).exists()`
  - [x] Raise `ValueError` with descriptive message if any check fails

- [x] Task 4: Implement startup config logging (AC: #7)
  - [x] Add `log_active_config(self, logger: structlog.BoundLogger) -> None` method to `Settings`
  - [x] Log all non-secret fields via `logger.info("active_configuration", ...)` — mask `S3_SECRET_KEY="[REDACTED]"` and replace DATABASE_URL password with `***`
  - [x] Add static helper `_mask_url(url: str) -> str` for URL password masking

- [x] Task 5: Add `get_settings()` singleton factory
  - [x] Define `get_settings() -> Settings` function decorated with `@functools.cache` (thread-safe, Python 3.9+)
  - [x] Update `src/aiops_triage_pipeline/config/__init__.py` to export: `Settings`, `get_settings`, `IntegrationMode`, `AppEnv`, `ENV_ACTION_CAPS`

- [x] Task 6: Add `pyyaml` dependency and policy loader (AC: from Story 1.3 dev notes)
  - [x] Add `"pyyaml~=6.0"` to `[project.dependencies]` in `pyproject.toml`
  - [x] Run `uv add pyyaml` to regenerate `uv.lock`
  - [x] Add `load_policy_yaml(path: Path, model_class: type[T]) -> T` helper function in `settings.py` using `TypeVar` bound to `BaseModel` — DO NOT import specific contract classes (leaf package rule)

- [x] Task 7: Create unit tests (AC: #8)
  - [x] Create `tests/unit/config/test_settings.py`
  - [x] Test integration mode defaults (no env vars set → `INTEGRATION_MODE_PD == IntegrationMode.LOG`)
  - [x] Test integration mode override (`INTEGRATION_MODE_PD=MOCK` env var → `IntegrationMode.MOCK`)
  - [x] Test `max_action` property for all four environments
  - [x] Test Kerberos pass: `KAFKA_SECURITY_PROTOCOL=PLAINTEXT` → Settings creates without error
  - [x] Test Kerberos fail: `KAFKA_SECURITY_PROTOCOL=SASL_SSL` with non-existent keytab path → raises `ValueError` or `ValidationError`
  - [x] Test Kerberos pass with real temp files: use `tmp_path` fixture to create real keytab + krb5.conf files → Settings creates successfully
  - [x] Test `log_active_config`: verify `S3_SECRET_KEY` does not appear in logged output
  - [x] Test `get_settings()` caching: two calls return the same instance; `get_settings.cache_clear()` allows fresh instantiation
  - [x] Place shared Settings construction helpers in `tests/unit/config/conftest.py` (NOT in the test file)

- [x] Task 8: Verify quality gates
  - [x] Run `uv run ruff check src/aiops_triage_pipeline/config/` — zero errors
  - [x] Run `uv run pytest tests/unit/config/test_settings.py -v` — all tests pass

## Dev Notes

### PREREQUISITE: Story 1.3 MUST be complete first

Story 1.4 references patterns from Story 1.3:
- `LocalDevContractV1` (in `contracts/local_dev.py`) specifies integration modes for local dev — understand its OFF/LOG/MOCK/LIVE values
- Policy YAML stubs in `config/policies/` must be fully populated by Story 1.3 before the policy loader in Story 1.4 is meaningful
- `pydantic-settings ~2.13.1` is already in `pyproject.toml` (added in Story 1.1); no version change needed

**DO NOT implement Story 1.4 unless Story 1.3 is done and `uv run pytest tests/unit/contracts/` passes.**

### Full `settings.py` Implementation Pattern

```python
import functools
import os
from enum import Enum
from pathlib import Path
from typing import TypeVar

import structlog
from pydantic import BaseModel, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Read APP_ENV BEFORE class definition to select the correct .env file.
# Direct env var takes precedence over any .env file value (K8s injection pattern).
_APP_ENV = os.getenv("APP_ENV", "local")


class AppEnv(str, Enum):
    local = "local"
    dev = "dev"
    uat = "uat"
    prod = "prod"


class IntegrationMode(str, Enum):
    OFF = "OFF"
    LOG = "LOG"
    MOCK = "MOCK"
    LIVE = "LIVE"


# Maps APP_ENV to maximum allowed action — consumed by pipeline gate engine (Story 5.1).
# Mirrors RulebookV1.caps.max_action_by_env from architecture decision 5D.
ENV_ACTION_CAPS: dict[str, str] = {
    "local": "OBSERVE",
    "dev": "NOTIFY",
    "uat": "TICKET",
    "prod": "PAGE",
}

T = TypeVar("T", bound=BaseModel)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=f"config/.env.{_APP_ENV}",
        env_file_encoding="utf-8",
        extra="ignore",  # Ignore unknown env vars (process environment has many unrelated vars)
    )

    # Environment identification
    APP_ENV: AppEnv = AppEnv.local

    # Kafka
    KAFKA_BOOTSTRAP_SERVERS: str = "localhost:9092"
    KAFKA_SECURITY_PROTOCOL: str = "PLAINTEXT"
    KAFKA_KERBEROS_KEYTAB_PATH: str | None = None
    KRB5_CONF_PATH: str | None = None

    # Postgres
    DATABASE_URL: str = "postgresql+psycopg://aiops:aiops@localhost:5432/aiops"

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # Object Storage (S3/MinIO)
    S3_ENDPOINT_URL: str = "http://localhost:9000"
    S3_ACCESS_KEY: str = "minioadmin"
    S3_SECRET_KEY: str = "minioadmin"
    S3_BUCKET: str = "aiops-cases"

    # Integration modes — default LOG to prevent accidental outbound calls
    INTEGRATION_MODE_PD: IntegrationMode = IntegrationMode.LOG
    INTEGRATION_MODE_SLACK: IntegrationMode = IntegrationMode.LOG
    INTEGRATION_MODE_SN: IntegrationMode = IntegrationMode.LOG
    INTEGRATION_MODE_LLM: IntegrationMode = IntegrationMode.LOG

    @property
    def max_action(self) -> str:
        """Maximum allowed action for this environment (architecture decision 5D)."""
        return ENV_ACTION_CAPS.get(self.APP_ENV.value, "OBSERVE")

    @model_validator(mode="after")
    def validate_kerberos_files(self) -> "Settings":
        """Fail-fast at boot if SASL_SSL is configured but Kerberos files are missing."""
        if self.KAFKA_SECURITY_PROTOCOL == "SASL_SSL":
            if not self.KAFKA_KERBEROS_KEYTAB_PATH:
                raise ValueError(
                    "KAFKA_KERBEROS_KEYTAB_PATH is required when KAFKA_SECURITY_PROTOCOL=SASL_SSL"
                )
            if not Path(self.KAFKA_KERBEROS_KEYTAB_PATH).exists():
                raise ValueError(
                    f"Kerberos keytab file not found: {self.KAFKA_KERBEROS_KEYTAB_PATH}"
                )
            if not self.KRB5_CONF_PATH:
                raise ValueError(
                    "KRB5_CONF_PATH is required when KAFKA_SECURITY_PROTOCOL=SASL_SSL"
                )
            if not Path(self.KRB5_CONF_PATH).exists():
                raise ValueError(f"KRB5 config file not found: {self.KRB5_CONF_PATH}")
        return self

    def log_active_config(self, logger: structlog.BoundLogger) -> None:
        """Log active configuration at startup (NFR-O4). Masks secret values."""
        logger.info(
            "active_configuration",
            APP_ENV=self.APP_ENV.value,
            KAFKA_BOOTSTRAP_SERVERS=self.KAFKA_BOOTSTRAP_SERVERS,
            KAFKA_SECURITY_PROTOCOL=self.KAFKA_SECURITY_PROTOCOL,
            DATABASE_URL=self._mask_url(self.DATABASE_URL),
            REDIS_URL=self.REDIS_URL,
            S3_ENDPOINT_URL=self.S3_ENDPOINT_URL,
            S3_ACCESS_KEY=self.S3_ACCESS_KEY,
            S3_SECRET_KEY="[REDACTED]",
            S3_BUCKET=self.S3_BUCKET,
            INTEGRATION_MODE_PD=self.INTEGRATION_MODE_PD.value,
            INTEGRATION_MODE_SLACK=self.INTEGRATION_MODE_SLACK.value,
            INTEGRATION_MODE_SN=self.INTEGRATION_MODE_SN.value,
            INTEGRATION_MODE_LLM=self.INTEGRATION_MODE_LLM.value,
            max_action=self.max_action,
        )

    @staticmethod
    def _mask_url(url: str) -> str:
        """Mask password in a connection URL for safe logging."""
        # postgresql+psycopg://user:password@host:port/db → postgresql+psycopg://user:***@host:port/db
        if "://" in url and "@" in url:
            scheme, rest = url.split("://", 1)
            if "@" in rest:
                credentials, host_part = rest.rsplit("@", 1)
                if ":" in credentials:
                    user, _ = credentials.split(":", 1)
                    return f"{scheme}://{user}:***@{host_part}"
        return url


@functools.cache
def get_settings() -> Settings:
    """Return the singleton Settings instance. Cached after first call.

    For testing, call get_settings.cache_clear() between tests to reset state.
    """
    return Settings()


def load_policy_yaml(path: Path, model_class: type[T]) -> T:
    """Load a YAML policy file and validate it as a frozen Pydantic model.

    Used by pipeline stages to load policy contracts at startup:
        rulebook = load_policy_yaml(Path("config/policies/rulebook-v1.yaml"), RulebookV1)

    config/ is a leaf package — do NOT import specific contract classes here.
    Callers supply the model_class.
    """
    import yaml  # Lazy import — only loaded when policy loading is requested

    raw = yaml.safe_load(path.read_text())
    return model_class.model_validate(raw)
```

### Import Boundary Rules (CRITICAL)

`config/` is a **LEAF package** — the import rules table explicitly prohibits all inbound imports:

- ✅ `from pydantic import BaseModel, model_validator`
- ✅ `from pydantic_settings import BaseSettings, SettingsConfigDict`
- ✅ `from pathlib import Path`
- ✅ `from enum import Enum`
- ✅ `import os`, `import functools`
- ✅ `import structlog` (external library, not aiops package)
- ✅ `import yaml` (external library — pyyaml, not aiops package)
- ❌ **NO** `from aiops_triage_pipeline.*` imports of any kind
- ❌ **NO** imports from `contracts/`, `models/`, `pipeline/`, `health/`, etc.

**Strictly enforced in code review.** [Source: `artifact/planning-artifacts/architecture.md#Import Rules`]

### pydantic-settings 2.x Key Behaviors

**Precedence (highest → lowest):**
1. Direct OS environment variables (K8s injected secrets — always win)
2. `.env` file values (from `config/.env.{APP_ENV}`)
3. Python default values in the `Settings` class body

**The `_APP_ENV` module-level read pattern:**
`_APP_ENV = os.getenv("APP_ENV", "local")` runs at module import time. This reads APP_ENV from the direct OS environment ONLY — not from any .env file. This is intentional: the env var at OS level controls which file is loaded. If APP_ENV only appears inside `.env.local`, setting it there has no effect on file selection (the .env.local file is already the default).

**`extra="ignore"`:** Prevents `ValidationError` from unknown env vars. The process environment may contain hundreds of unrelated variables from the shell, IDE, or OS.

**`@functools.cache` on `get_settings()`:** Returns the same `Settings` instance across all callers in the same process. Safe because `Settings` fields are immutable (pydantic-settings does not use `frozen=True`, but the fields are not mutated by convention). For testing, use `get_settings.cache_clear()` to reset between tests.

### Unit Test Pattern

```python
# tests/unit/config/test_settings.py
import pytest
from pathlib import Path
from pydantic import ValidationError

from aiops_triage_pipeline.config.settings import (
    AppEnv,
    ENV_ACTION_CAPS,
    IntegrationMode,
    Settings,
    get_settings,
)


def test_integration_mode_default() -> None:
    """INTEGRATION_MODE_PD defaults to LOG when not set in environment."""
    settings = Settings(
        _env_file=None,  # Disable file loading in unit tests
        KAFKA_BOOTSTRAP_SERVERS="localhost:9092",
        DATABASE_URL="postgresql+psycopg://u:p@h/db",
        REDIS_URL="redis://localhost:6379/0",
        S3_ENDPOINT_URL="http://localhost:9000",
        S3_ACCESS_KEY="key",
        S3_SECRET_KEY="secret",
        S3_BUCKET="bucket",
    )
    assert settings.INTEGRATION_MODE_PD == IntegrationMode.LOG
    assert settings.INTEGRATION_MODE_LLM == IntegrationMode.LOG


def test_integration_mode_override(monkeypatch: pytest.MonkeyPatch) -> None:
    """Direct env var INTEGRATION_MODE_PD=MOCK overrides default LOG."""
    monkeypatch.setenv("INTEGRATION_MODE_PD", "MOCK")
    settings = Settings(
        _env_file=None,
        KAFKA_BOOTSTRAP_SERVERS="localhost:9092",
        DATABASE_URL="postgresql+psycopg://u:p@h/db",
        REDIS_URL="redis://localhost:6379/0",
        S3_ENDPOINT_URL="http://localhost:9000",
        S3_ACCESS_KEY="key",
        S3_SECRET_KEY="secret",
        S3_BUCKET="bucket",
    )
    assert settings.INTEGRATION_MODE_PD == IntegrationMode.MOCK


def test_max_action_for_all_environments() -> None:
    """max_action returns correct cap per APP_ENV value."""
    for env_value, expected in [
        ("local", "OBSERVE"),
        ("dev", "NOTIFY"),
        ("uat", "TICKET"),
        ("prod", "PAGE"),
    ]:
        settings = Settings(
            _env_file=None,
            APP_ENV=env_value,
            KAFKA_BOOTSTRAP_SERVERS="localhost:9092",
            DATABASE_URL="postgresql+psycopg://u:p@h/db",
            REDIS_URL="redis://localhost:6379/0",
            S3_ENDPOINT_URL="http://localhost:9000",
            S3_ACCESS_KEY="key",
            S3_SECRET_KEY="secret",
            S3_BUCKET="bucket",
        )
        assert settings.max_action == expected, f"APP_ENV={env_value}"


def test_kerberos_plaintext_no_error() -> None:
    """KAFKA_SECURITY_PROTOCOL=PLAINTEXT does not trigger Kerberos validation."""
    settings = Settings(
        _env_file=None,
        KAFKA_BOOTSTRAP_SERVERS="localhost:9092",
        KAFKA_SECURITY_PROTOCOL="PLAINTEXT",
        DATABASE_URL="postgresql+psycopg://u:p@h/db",
        REDIS_URL="redis://localhost:6379/0",
        S3_ENDPOINT_URL="http://localhost:9000",
        S3_ACCESS_KEY="key",
        S3_SECRET_KEY="secret",
        S3_BUCKET="bucket",
    )
    assert settings.KAFKA_SECURITY_PROTOCOL == "PLAINTEXT"


def test_kerberos_sasl_ssl_missing_keytab_raises(tmp_path: Path) -> None:
    """SASL_SSL with non-existent keytab path raises ValueError at boot."""
    with pytest.raises((ValueError, ValidationError)):
        Settings(
            _env_file=None,
            KAFKA_BOOTSTRAP_SERVERS="kafka.internal:9092",
            KAFKA_SECURITY_PROTOCOL="SASL_SSL",
            KAFKA_KERBEROS_KEYTAB_PATH=str(tmp_path / "nonexistent.keytab"),
            KRB5_CONF_PATH=str(tmp_path / "krb5.conf"),
            DATABASE_URL="postgresql+psycopg://u:p@h/db",
            REDIS_URL="redis://localhost:6379/0",
            S3_ENDPOINT_URL="http://localhost:9000",
            S3_ACCESS_KEY="key",
            S3_SECRET_KEY="secret",
            S3_BUCKET="bucket",
        )


def test_kerberos_sasl_ssl_with_valid_files_succeeds(tmp_path: Path) -> None:
    """SASL_SSL with existing keytab and KRB5 files creates Settings successfully."""
    keytab = tmp_path / "service.keytab"
    krb5_conf = tmp_path / "krb5.conf"
    keytab.write_bytes(b"dummy keytab content")
    krb5_conf.write_text("[libdefaults]\n    default_realm = TEST.INTERNAL\n")

    settings = Settings(
        _env_file=None,
        KAFKA_BOOTSTRAP_SERVERS="kafka.internal:9092",
        KAFKA_SECURITY_PROTOCOL="SASL_SSL",
        KAFKA_KERBEROS_KEYTAB_PATH=str(keytab),
        KRB5_CONF_PATH=str(krb5_conf),
        DATABASE_URL="postgresql+psycopg://u:p@h/db",
        REDIS_URL="redis://localhost:6379/0",
        S3_ENDPOINT_URL="http://localhost:9000",
        S3_ACCESS_KEY="key",
        S3_SECRET_KEY="secret",
        S3_BUCKET="bucket",
    )
    assert settings.KAFKA_SECURITY_PROTOCOL == "SASL_SSL"


def test_log_active_config_masks_secret(capsys: pytest.CaptureFixture[str]) -> None:
    """log_active_config does not expose S3_SECRET_KEY in log output."""
    import structlog

    structlog.configure(
        processors=[structlog.dev.ConsoleRenderer()],
        wrapper_class=structlog.BoundLogger,
        logger_factory=structlog.PrintLoggerFactory(),
    )
    logger = structlog.get_logger()
    settings = Settings(
        _env_file=None,
        KAFKA_BOOTSTRAP_SERVERS="localhost:9092",
        DATABASE_URL="postgresql+psycopg://u:secret_password@localhost/db",
        REDIS_URL="redis://localhost:6379/0",
        S3_ENDPOINT_URL="http://localhost:9000",
        S3_ACCESS_KEY="access",
        S3_SECRET_KEY="super_secret",
        S3_BUCKET="bucket",
    )
    settings.log_active_config(logger)
    captured = capsys.readouterr()
    assert "super_secret" not in captured.out
    assert "secret_password" not in captured.out
    assert "[REDACTED]" in captured.out


def test_get_settings_returns_same_instance() -> None:
    """get_settings() caches and returns the same Settings instance."""
    get_settings.cache_clear()
    s1 = get_settings()
    s2 = get_settings()
    assert s1 is s2
    get_settings.cache_clear()
```

**Fixtures in `tests/unit/config/conftest.py`** — add a minimal Settings factory:
```python
import pytest
from pathlib import Path
from aiops_triage_pipeline.config.settings import Settings

@pytest.fixture
def minimal_settings(tmp_path: Path) -> Settings:
    """A minimal Settings instance with no env file and safe defaults."""
    return Settings(
        _env_file=None,
        KAFKA_BOOTSTRAP_SERVERS="localhost:9092",
        DATABASE_URL="postgresql+psycopg://aiops:aiops@localhost:5432/aiops",
        REDIS_URL="redis://localhost:6379/0",
        S3_ENDPOINT_URL="http://localhost:9000",
        S3_ACCESS_KEY="minioadmin",
        S3_SECRET_KEY="minioadmin",
        S3_BUCKET="aiops-cases",
    )
```

### Policy YAML Loading (from Story 1.3 Dev Notes)

Story 1.3's dev notes explicitly state: *"YAML loading at startup (Story 1.4): `config/settings.py` will load policy YAMLs using `pydantic-settings` or `yaml.safe_load()`"* and *"pyyaml dependency (Story 1.4): If YAML loading requires pyyaml, it will be added to `pyproject.toml` in Story 1.4."*

**Add to `pyproject.toml` `[project.dependencies]`:**
```toml
"pyyaml~=6.0",
```

**How pipeline stages will use `load_policy_yaml`** (not implemented in this story, but the helper enables it):
```python
# In pipeline/stages/gating.py (Story 5.1) — NOT in this story:
from aiops_triage_pipeline.config.settings import load_policy_yaml
from aiops_triage_pipeline.contracts import RulebookV1
from pathlib import Path

rulebook = load_policy_yaml(Path("config/policies/rulebook-v1.yaml"), RulebookV1)
```

The `config/` package exposes the loader; consumers inject the model class. This keeps `config/` as a true leaf package.

### What Is NOT In Scope for Story 1.4

- **Exposure denylist** (Story 1.5): `denylist/enforcement.py` + `apply_denylist()` function — separate story
- **HealthRegistry** (Story 1.6): Component health tracking singleton
- **Structured logging setup** (Story 1.7): `logging/setup.py` and structlog pipeline configuration — Story 1.4 only CALLS `structlog.get_logger()` for startup logging without configuring the full structlog pipeline
- **Docker-compose infrastructure** (Story 1.8): The `.env.docker` file already exists (for container-to-container networking) and must NOT be modified
- **Integration adapters** (Stories 2.x+): `integrations/base.py` will consume `IntegrationMode` from `config/settings.py`; that wiring happens per-integration story
- **Gate enforcement** (Story 5.1): The gate engine reads `max_action` and `ENV_ACTION_CAPS` from settings but the enforcement logic lives in the gate engine, not here
- **Policy YAML content**: Policy YAML files in `config/policies/` were populated in Story 1.3; this story only adds the `load_policy_yaml` helper and `pyyaml` dependency

### Project Structure — Files to Create/Modify

```
src/aiops_triage_pipeline/config/
├── __init__.py               # UPDATE: export Settings, get_settings, IntegrationMode, AppEnv, ENV_ACTION_CAPS
│                             # Currently a 1-line stub — replace completely
└── settings.py               # IMPLEMENT: currently a 1-line stub — replace completely

pyproject.toml                # UPDATE: add "pyyaml~=6.0" to [project.dependencies]
uv.lock                       # REGENERATE: run `uv add pyyaml`

tests/unit/config/
├── __init__.py               # EXISTS: no changes
├── conftest.py               # CREATE: minimal_settings fixture
└── test_settings.py          # CREATE: unit tests per AC #8
```

**Files explicitly NOT touched:**
- `config/.env.local` — already has all required fields (INTEGRATION_MODE_* are present)
- `config/.env.dev` — already has all required fields
- `config/.env.docker` — docker-compose networking variant; do not modify
- `config/.env.uat.template` — exists from Story 1.1
- `config/.env.prod.template` — exists from Story 1.1
- `config/policies/*.yaml` — fully populated by Story 1.3
- `contracts/` — no changes; this story is consumer-only

### Ruff Compliance Notes

Same rules as Stories 1.2 and 1.3 apply:
- Python 3.13 native generics: `dict[str, str]`, `type[T]` — no `from typing import Dict, Type`
- `str | None` not `Optional[str]`
- Line length 100 chars max
- All imports used (no unused imports)
- `from __future__ import annotations` NOT needed
- `lazy import yaml` inside `load_policy_yaml` is acceptable — avoids top-level import for optional feature

**Note on `import yaml` placement:** Putting `import yaml` inside the function body is intentional — it avoids making pyyaml a hard startup dependency for callers who never use policy loading. Ruff's `E402` (module level import not at top) may flag this but it's inside a function body, which is acceptable.

### Previous Story Intelligence (from Stories 1.2 and 1.3)

**Established patterns to follow exactly:**
- `str | None` for optional fields (not `Optional[str]`)
- Ruff line-length: 100 chars max
- `uv run ruff check` must pass with zero errors before review
- Python 3.13 native types — no `from typing import Dict, Tuple, Optional`
- Fixtures go in `conftest.py`, never in test files

**New patterns for Story 1.4 (not in 1.2/1.3):**
- `from pydantic_settings import BaseSettings, SettingsConfigDict` — pydantic-settings 2.x API
- `@model_validator(mode="after")` — post-init validation (different from `model_config = ConfigDict(...)`)
- `@functools.cache` — singleton factory pattern, thread-safe in Python 3.9+
- `monkeypatch.setenv` / `monkeypatch.delenv` — control env vars in pytest
- `Settings(_env_file=None, field=value)` — bypass file loading in unit tests; pydantic-settings allows constructor injection
- `get_settings.cache_clear()` — reset singleton between tests

**Pattern warning — `model_validator` import:**
```python
# Correct for pydantic v2 (2.12.5):
from pydantic import BaseModel, model_validator  # model_validator is in pydantic, not pydantic_settings
from pydantic_settings import BaseSettings, SettingsConfigDict
```

### Git Context

Recent commits (from `git log --oneline`):
- `8a581b9 Story 1.2: Code review fixes — contract validation hardening` — Story 1.2 complete, review feedback applied
- `84a5b29 Story 1.2: Event Contract Models` — 5 event contracts + `contracts/__init__.py` fully populated
- `328318d Story 1.1: Project Initialization & Repository Structure` — foundational files in place

Story 1.3 is currently `ready-for-dev` — dev agent must complete Story 1.3 and pass `uv run pytest tests/unit/contracts/test_policy_models.py` before starting Story 1.4.

**Files confirmed to exist from Story 1.1:**
- `src/aiops_triage_pipeline/config/__init__.py` (1-line stub)
- `src/aiops_triage_pipeline/config/settings.py` (1-line stub)
- `config/.env.local`, `config/.env.dev`, `config/.env.docker`
- `config/.env.uat.template`, `config/.env.prod.template`
- `tests/unit/config/__init__.py` (empty)
- All `config/policies/*.yaml` stub files (will be populated by Story 1.3)

### References

- Architecture decisions 2A, 5B, 5D: [Source: `artifact/planning-artifacts/architecture.md#Security & Secrets`, `#Infrastructure & Deployment`]
- NFR-O4 (Active config logged at startup): [Source: `artifact/planning-artifacts/epics.md#NFR-O4`]
- NFR-S7 (Integration mode changes require deployment): [Source: `artifact/planning-artifacts/epics.md#NFR-S7`]
- FR57 (Integration OFF/LOG/MOCK/LIVE mode configuration): [Source: `artifact/planning-artifacts/epics.md#FR57`]
- `config/` as leaf package import rules: [Source: `artifact/planning-artifacts/architecture.md#Import Rules`]
- Complete project directory structure: [Source: `artifact/planning-artifacts/architecture.md#Complete Project Directory Structure`]
- `LocalDevContractV1` integration modes (reference for mode values): [Source: `artifact/implementation-artifacts/1-3-policy-and-operational-contract-models.md#Contract 7`]
- YAML loading pattern deferred from Story 1.3: [Source: `artifact/implementation-artifacts/1-3-policy-and-operational-contract-models.md#What Is NOT In Scope`]
- pydantic-settings version: ~2.13.1 [Source: `pyproject.toml`]
- Pydantic version: 2.12.5 [Source: `pyproject.toml`]

## Dev Agent Record

### Agent Model Used

claude-sonnet-4-6

### Debug Log References

None — implementation proceeded cleanly using exact patterns from Dev Notes.

### Completion Notes List

- Implemented `settings.py` from scratch (was a 1-line stub): `AppEnv`, `IntegrationMode`, `ENV_ACTION_CAPS`, `Settings` class, `get_settings()` singleton, `load_policy_yaml()` helper.
- `_APP_ENV` read at module level before class definition — correct K8s injection precedence.
- Kerberos fail-fast validation via `@model_validator(mode="after")` raises `ValueError` at `Settings()` creation time.
- `log_active_config()` masks `S3_SECRET_KEY` as `[REDACTED]` and rewrites DATABASE_URL password as `***`.
- `get_settings()` decorated with `@functools.cache` for thread-safe singleton; `cache_clear()` used in tests.
- `load_policy_yaml()` uses lazy `import yaml` inside function body to keep `config/` a leaf package.
- `__init__.py` updated to re-export all public symbols; ruff auto-fixed import sort order.
- `pyyaml~=6.0` added to `pyproject.toml` dependencies; `uv add pyyaml` confirmed pyyaml 6.0.3 present.
- 8 unit tests created in `tests/unit/config/test_settings.py`; shared fixture in `conftest.py`.
- All 83 unit tests pass (8 new + 75 existing); zero ruff errors; no regressions.

### File List

- `src/aiops_triage_pipeline/config/settings.py` (implemented — was 1-line stub)
- `src/aiops_triage_pipeline/config/__init__.py` (updated — exports Settings, get_settings, IntegrationMode, AppEnv, ENV_ACTION_CAPS, load_policy_yaml)
- `pyproject.toml` (updated — added pyyaml~=6.0 to dependencies)
- `uv.lock` (regenerated — pyyaml 6.0.3 confirmed)
- `tests/unit/config/conftest.py` (created — minimal_settings fixture)
- `tests/unit/config/test_settings.py` (updated — 12 unit tests, +4 from code review)

## Change Log

- 2026-03-01: Story 1.4 implemented — environment-aware Settings with pydantic-settings 2.x, per-integration OFF/LOG/MOCK/LIVE modes, Kerberos fail-fast validation, startup config logging with secret masking, `get_settings()` singleton, `load_policy_yaml()` helper, and pyyaml dependency added. 8 unit tests; all 83 unit tests pass; zero ruff errors.
- 2026-03-01: Code review fixes — H1: removed unused `AppEnv`/`ENV_ACTION_CAPS` imports and fixed import sort order in test files (ruff now clean on both `src/` and `tests/`); H2: added 3 tests for `load_policy_yaml` (happy path, file-not-found, schema-mismatch); M1: replaced `structlog.configure()` global mutation with `structlog.testing.capture_logs()` context manager for test isolation; M2: added `test_kerberos_sasl_ssl_missing_krb5_conf_raises` covering the KRB5_CONF_PATH failure branch; M3: wrapped `load_policy_yaml` body in try/except to include file path and model name in error messages. 12 unit tests; all 87 unit tests pass; zero ruff errors.
