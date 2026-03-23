# Story 5.2: Enforce Security-Critical Integration Configuration

Status: review

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As an SRE/platform engineer,
I want integration security configuration validated before runtime,
so that deployments cannot start in insecure or unsupported states.

**Implements:** FR51

## Acceptance Criteria

1. **Given** Kafka SASL_SSL is configured
   **When** startup validation runs
   **Then** keytab and krb5 paths are validated with fail-fast behavior
   **And** service startup is blocked on missing/invalid required security artifacts.

2. **Given** integration modes are configured per environment
   **When** runtime mode enforcement applies
   **Then** prod guardrails reject disallowed safety modes for critical integrations (PD, Slack, SN)
   **And** local/dev defaults remain safe and non-destructive unless explicitly overridden.

## Tasks / Subtasks

- [x] Task 1: Extend prod integration mode guardrails to cover PD, Slack, and SN (AC: 2)
  - [x] In `src/aiops_triage_pipeline/config/settings.py`, add a new `@model_validator(mode="after")`
        named `validate_critical_integrations_prod_mode` that iterates over
        `INTEGRATION_MODE_PD`, `INTEGRATION_MODE_SLACK`, and `INTEGRATION_MODE_SN` and raises
        `ValueError` if any is `IntegrationMode.OFF` or `IntegrationMode.MOCK` when
        `APP_ENV == AppEnv.prod`.
  - [x] Follow the exact pattern of the existing `validate_llm_prod_mode` validator (lines 136–147).
  - [x] Error message should name the specific field and its current value, e.g.:
        `"INTEGRATION_MODE_PD must be LIVE or LOG in prod environment; got MOCK"`
  - [x] **Do NOT modify** `validate_llm_prod_mode` — it remains as a separate validator.
  - [x] **Do NOT add new settings fields** — no new env vars or defaults needed.
  - [x] **Do NOT modify** `log_active_config` — all four integration modes are already logged
        (lines 231–234 of settings.py).

- [x] Task 2: Write unit tests for new prod guardrails (AC: 2)
  - [x] Add the following tests to `tests/unit/config/test_settings.py`,
        following the `_PROD_SETTINGS_BASE` fixture pattern already established:
    - `test_prod_pd_mock_raises_validation_error`: `APP_ENV=prod + INTEGRATION_MODE_PD=MOCK` → `ValidationError`
    - `test_prod_pd_off_raises_validation_error`: `APP_ENV=prod + INTEGRATION_MODE_PD=OFF` → `ValidationError`
    - `test_prod_pd_live_succeeds`: `APP_ENV=prod + INTEGRATION_MODE_PD=LIVE` → succeeds
    - `test_prod_pd_log_succeeds`: `APP_ENV=prod + INTEGRATION_MODE_PD=LOG` → succeeds (LOG is always safe)
    - `test_prod_slack_mock_raises_validation_error`: `APP_ENV=prod + INTEGRATION_MODE_SLACK=MOCK` → `ValidationError`
    - `test_prod_slack_off_raises_validation_error`: `APP_ENV=prod + INTEGRATION_MODE_SLACK=OFF` → `ValidationError`
    - `test_prod_slack_live_succeeds`: `APP_ENV=prod + INTEGRATION_MODE_SLACK=LIVE` → succeeds
    - `test_prod_sn_mock_raises_validation_error`: `APP_ENV=prod + INTEGRATION_MODE_SN=MOCK` → `ValidationError`
    - `test_prod_sn_off_raises_validation_error`: `APP_ENV=prod + INTEGRATION_MODE_SN=OFF` → `ValidationError`
    - `test_prod_sn_live_succeeds`: `APP_ENV=prod + INTEGRATION_MODE_SN=LIVE` → succeeds
    - `test_local_pd_mock_succeeds`: `APP_ENV=local + INTEGRATION_MODE_PD=MOCK` → succeeds (non-prod)
  - [x] All new tests must use `_PROD_SETTINGS_BASE` dict (lines 267–277 of test_settings.py)
        and `pytest.raises((ValueError, ValidationError), match="INTEGRATION_MODE_PD")` pattern.

- [x] Task 3: Run full regression (AC: 1, 2)
  - [x] `uv run ruff check`
  - [x] `uv run pytest -q tests/unit`
  - [x] `TESTCONTAINERS_RYUK_DISABLED=true DOCKER_HOST=unix://$HOME/.docker/desktop/docker.sock uv run pytest -q -rs`

## Dev Notes

### What Already Exists — Do NOT Reimplement

**AC1 (Kafka SASL_SSL validation) is fully implemented:**
- `validate_kerberos_files` model validator in `Settings` (lines 149–212 of `config/settings.py`):
  - Checks `KAFKA_KERBEROS_KEYTAB_PATH` is set and the file exists when `KAFKA_SECURITY_PROTOCOL=SASL_SSL`
  - Checks `KRB5_CONF_PATH` is set and the file exists when `KAFKA_SECURITY_PROTOCOL=SASL_SSL`
  - Raises `ValueError` with explicit field name for every missing/invalid artifact
- Tests exist in `tests/unit/config/test_settings.py`:
  - `test_kerberos_plaintext_no_error` (line 70)
  - `test_kerberos_sasl_ssl_missing_keytab_raises` (line 86)
  - `test_kerberos_sasl_ssl_missing_krb5_conf_raises` (line 104)
  - `test_kerberos_sasl_ssl_with_valid_files_succeeds` (line 124)
- **Do NOT add duplicate kerberos tests** — AC1 is already fully covered.

**NFR-S5 (Default LOG mode) is fully implemented:**
- All four integration modes default to `IntegrationMode.LOG` in `Settings` (lines 85–88):
  - `INTEGRATION_MODE_PD: IntegrationMode = IntegrationMode.LOG`
  - `INTEGRATION_MODE_SLACK: IntegrationMode = IntegrationMode.LOG`
  - `INTEGRATION_MODE_SN: IntegrationMode = IntegrationMode.LOG`
  - `INTEGRATION_MODE_LLM: IntegrationMode = IntegrationMode.LOG`
- Test exists: `test_integration_mode_default` (line 16)
- **Do NOT add another default-mode test** — already covered.

**NFR-S6 (LLM prod guardrail) is already implemented:**
- `validate_llm_prod_mode` validator (lines 136–147 of settings.py) rejects MOCK/OFF for LLM in prod.
- Tests exist: `test_prod_llm_mock_raises_validation_error`, `test_prod_llm_off_raises_validation_error`,
  `test_prod_llm_live_succeeds`, `test_prod_llm_log_succeeds`, `test_local_llm_mock_succeeds` (lines 280–326).

### The Actual Gap — What Story 5.2 Must Add

**NFR-S6 is only partial.** Currently only `INTEGRATION_MODE_LLM` has a prod guardrail. The three remaining
critical integrations have NO prod guardrail:
- `INTEGRATION_MODE_PD`: In prod, PAGE actions dispatch PagerDuty triggers. If set to OFF or MOCK,
  PAGE triggers are silently dropped — catastrophic for a prod-monitoring system.
- `INTEGRATION_MODE_SLACK`: In prod, NOTIFY/TICKET dispatch Slack notifications. OFF/MOCK causes silent failures.
- `INTEGRATION_MODE_SN`: In prod, TICKET/PAGE upsert ServiceNow incidents. OFF/MOCK prevents SN record creation.

**Exactly one new validator is needed** in `settings.py`. Add it immediately after `validate_llm_prod_mode`:

```python
@model_validator(mode="after")
def validate_critical_integrations_prod_mode(self) -> "Settings":
    """Reject MOCK and OFF for critical integrations in prod — PD, Slack, SN require LIVE (or LOG)."""
    if self.APP_ENV != AppEnv.prod:
        return self
    _critical: list[tuple[str, IntegrationMode]] = [
        ("INTEGRATION_MODE_PD", self.INTEGRATION_MODE_PD),
        ("INTEGRATION_MODE_SLACK", self.INTEGRATION_MODE_SLACK),
        ("INTEGRATION_MODE_SN", self.INTEGRATION_MODE_SN),
    ]
    for field_name, mode in _critical:
        if mode in (IntegrationMode.OFF, IntegrationMode.MOCK):
            raise ValueError(
                f"{field_name} must be LIVE or LOG in prod environment; "
                f"got {mode.value}"
            )
    return self
```

### Technical Requirements

- FR51: Validate Kafka SASL_SSL configuration at startup with fail-fast behavior — **already done**.
- NFR-S3: Kafka SASL_SSL keytab and krb5 config paths validated at startup — **already done**.
- NFR-S5: Integration safety modes default to LOG — **already done**.
- NFR-S6: Prod enforcement rejects MOCK/OFF for critical integrations — **LLM done, PD/Slack/SN is the delta**.
- NFR-I1: All external integrations implement OFF|LOG|MOCK|LIVE mode semantics consistently — PD, Slack, SN
  each have their own local enum (`PagerDutyIntegrationMode`, `SlackIntegrationMode`, `IntegrationMode`),
  but `Settings` uses `IntegrationMode` for all four mode fields uniformly.

### Architecture Compliance

- **Composition root**: All wiring stays in `__main__.py`. This story makes no changes there.
- **Single flat `Settings` class**: Add validator to existing `Settings` — no new subclass, no new fields.
- **`validate_kerberos_files` method name is misleading** (it validates many things beyond kerberos — outbox batch
  sizes, shard TTLs, OTLP protocol, etc.) but **do NOT refactor it** — only add the new validator.
- **No new policy files**: Story 5.2 is purely `Settings` validation logic; no new YAML policy files needed.
- **Package dependency rules**: `config/settings.py` imports from `pydantic_settings` and `pydantic` only —
  zero imports from integrations/. The new validator stays within the same `settings.py` boundaries.

### Library / Framework Requirements

- Locked stack (do not change):
  - Python `>=3.13`
  - `pydantic==2.12.5` — `@model_validator(mode="after")` is the correct v2 API
  - `pydantic-settings~=2.13.1`
  - `pytest==9.0.2`
- `@model_validator(mode="after")` receives the fully-constructed `Settings` instance — all fields are
  already resolved when the validator runs. Use `self.APP_ENV`, `self.INTEGRATION_MODE_PD`, etc. directly.
- `(ValueError, ValidationError)` is the correct pytest.raises pattern for pydantic v2 model validators.

### File Structure Requirements

**Modified files:**
- `src/aiops_triage_pipeline/config/settings.py` — add `validate_critical_integrations_prod_mode` validator
- `tests/unit/config/test_settings.py` — add 11 new tests for PD/Slack/SN prod guardrails

**Do NOT create or modify:**
- `src/aiops_triage_pipeline/__main__.py` — no new policy loads or wiring needed
- `src/aiops_triage_pipeline/integrations/*.py` — integration clients unchanged
- `config/policies/` — no new policy files
- Any contracts file — no new Pydantic contract models

### Testing Requirements

- **Test patterns to follow** (from existing tests in `test_settings.py`):
  - Use `_PROD_SETTINGS_BASE` dict (defined at line 267) as base kwargs for all prod tests.
  - Use `Settings(**{**_PROD_SETTINGS_BASE, "INTEGRATION_MODE_PD": "MOCK"})` pattern.
  - Use `pytest.raises((ValueError, ValidationError), match="INTEGRATION_MODE_PD")` to assert both
    the exception type and the field name in the error message.
  - For "succeeds" tests: instantiate `Settings` directly and assert the mode value.
  - For non-prod test: use `APP_ENV="local"` to confirm MOCK is allowed outside prod.
- **Per-file test doubles**: No shared fixtures — all new tests are standalone functions.
- **No pytest.skip anywhere** — use `pytest.fail` if you encounter unexpected behavior.
- **Quality gate**: zero skipped tests across all test suites.
- **Preferred regression command:**
  - `TESTCONTAINERS_RYUK_DISABLED=true DOCKER_HOST=unix://$HOME/.docker/desktop/docker.sock uv run pytest -q -rs`

### Reference: Existing `_PROD_SETTINGS_BASE` and LLM Test Pattern

Copy this exact pattern for PD/Slack/SN tests (from lines 267–308 of test_settings.py):

```python
_PROD_SETTINGS_BASE: dict = dict(
    _env_file=None,
    APP_ENV="prod",
    KAFKA_BOOTSTRAP_SERVERS="localhost:9092",
    DATABASE_URL="postgresql+psycopg://u:p@h/db",
    REDIS_URL="redis://localhost:6379/0",
    S3_ENDPOINT_URL="http://localhost:9000",
    S3_ACCESS_KEY="key",
    S3_SECRET_KEY="secret",
    S3_BUCKET="bucket",
)

def test_prod_pd_mock_raises_validation_error() -> None:
    """APP_ENV=prod + INTEGRATION_MODE_PD=MOCK raises ValidationError at startup."""
    with pytest.raises((ValueError, ValidationError), match="INTEGRATION_MODE_PD"):
        Settings(**{**_PROD_SETTINGS_BASE, "INTEGRATION_MODE_PD": "MOCK"})

def test_prod_pd_off_raises_validation_error() -> None:
    """APP_ENV=prod + INTEGRATION_MODE_PD=OFF raises ValidationError at startup."""
    with pytest.raises((ValueError, ValidationError), match="INTEGRATION_MODE_PD"):
        Settings(**{**_PROD_SETTINGS_BASE, "INTEGRATION_MODE_PD": "OFF"})

def test_prod_pd_live_succeeds() -> None:
    """APP_ENV=prod + INTEGRATION_MODE_PD=LIVE creates Settings successfully."""
    settings = Settings(**{**_PROD_SETTINGS_BASE, "INTEGRATION_MODE_PD": "LIVE"})
    assert settings.INTEGRATION_MODE_PD.value == "LIVE"

def test_prod_pd_log_succeeds() -> None:
    """APP_ENV=prod + INTEGRATION_MODE_PD=LOG is allowed (safe non-destructive default)."""
    settings = Settings(**{**_PROD_SETTINGS_BASE, "INTEGRATION_MODE_PD": "LOG"})
    assert settings.INTEGRATION_MODE_PD.value == "LOG"

# Repeat same pattern for SLACK and SN
```

### Previous Story Intelligence

**From Story 5.1 (done — policy startup loading):**
- File list in Dev Agent Record must include ALL changed files including sprint-status.yaml.
- No `pytest.skip` anywhere — use `pytest.fail` if needed.
- `uv run ruff check` runs clean — fix any linting issues before claiming done.
- `log_active_config` already logs all four integration modes (lines 231–234); the new validator
  requires no `log_active_config` changes — `validate_kerberos_files` confirmed this discipline.
- Full regression: 1027 unit tests passed at last check.

**From Story 4.3 (done — rollout testing):**
- Integration tests: no `pytest.skip`, use `pytest.fail`.
- Unit tests: per-file test doubles, no shared infra fixtures.

### Git Intelligence Summary

Recent commits (most relevant to this story):
- `c9dc3b1`: bmad(epic-5/5-1): mark story done after code review — story 5.1 complete
- `ab47837`: fix(epic-5/5-1): resolve code review findings — contracts/__init__.py cleanup
- `3eaf9e3`: bmad(epic-5/5-1): story dev done — 1121 unit tests passed
- `0a69630`: bmad(epic-4/retrospective): epic-5 status set to in-progress

The most recent integration-relevant change was in Epic 2/3 when SASL_SSL support and integration modes
were added. The kerberos validation has been stable since then. No integration-mode-related code changed
in Epics 4 or 5.1 — Story 5.2 is purely additive (one new validator + tests).

### Latest Tech Information

External verification date: 2026-03-23.

- `pydantic==2.12.5`: `@model_validator(mode="after")` API is stable. Multiple `@model_validator` decorators
  on the same class are all called in definition order — adding a second validator after `validate_llm_prod_mode`
  is the correct pattern (do NOT combine into a single validator).
- `pydantic-settings~=2.13.1`: `BaseSettings` model validators run after all field values are resolved from
  env files and env vars — the validator receives the fully-constructed instance.
- `pytest==9.0.2`: `pytest.raises((ValueError, ValidationError), match=...)` — `match` applies to the
  string representation of the exception, which for pydantic v2 ValidationError includes the field name
  from the `ValueError` message.

### Project Context Reference

Applied `archive/project-context.md` and implementation patterns:
- Python 3.13 typing — no `Optional[X]`, use `X | None`.
- No DI container, no service locator — validators live in `Settings` class only.
- Single flat `Settings` class — no new subclasses or settings sub-models.
- Feature flags follow `FEATURE_ENABLED: bool = False` pattern — not applicable to this story.
- Full regression policy expects zero skipped tests.
- This story's scope is minimal: 1 new validator (~15 lines) + 11 new tests (~110 lines).

### References

- [Source: `artifact/planning-artifacts/epics.md` — Epic 5 / Story 5.2]
- [Source: `artifact/planning-artifacts/prd/functional-requirements.md` — FR51]
- [Source: `artifact/planning-artifacts/prd/non-functional-requirements.md` — NFR-S3, NFR-S5, NFR-S6, NFR-I1]
- [Source: `artifact/planning-artifacts/architecture/implementation-patterns-consistency-rules.md`
  — Configuration Variables, Enforcement Guidelines]
- [Source: `artifact/planning-artifacts/architecture/core-architectural-decisions.md`
  — D6 integration modes table (local/docker LOG, dev/uat/prod LIVE)]
- [Source: `src/aiops_triage_pipeline/config/settings.py`
  — `IntegrationMode` enum (line 24), `Settings.validate_llm_prod_mode` (lines 136–147),
  `Settings.validate_kerberos_files` (lines 149–212), `log_active_config` (lines 214–269)]
- [Source: `tests/unit/config/test_settings.py`
  — `_PROD_SETTINGS_BASE` (line 267), LLM prod tests (lines 280–326), kerberos tests (lines 70–144)]
- [Source: `src/aiops_triage_pipeline/integrations/pagerduty.py`
  — `PagerDutyIntegrationMode` (line 18), `PagerDutyClient` (line 42)]
- [Source: `src/aiops_triage_pipeline/integrations/slack.py`
  — `SlackIntegrationMode` (line 20), `SlackClient` (line 35)]
- [Source: `src/aiops_triage_pipeline/integrations/servicenow.py`
  — `ServiceNowClient` uses `IntegrationMode` directly (line 18)]

## Dev Agent Record

### Agent Model Used

claude-sonnet-4-6

### Debug Log References

- create-story workflow for story key `5-2-enforce-security-critical-integration-configuration`
- artifact analysis: sprint-status.yaml (story selection, status=backlog confirmed), epics.md (Epic 5 / Story 5.2 acceptance criteria), prd/functional-requirements.md (FR51), prd/non-functional-requirements.md (NFR-S3/S5/S6, NFR-I1)
- architecture analysis: core-architectural-decisions.md (D6 integration mode table, D4 package isolation), implementation-patterns-consistency-rules.md (configuration variables pattern, enforcement guidelines), project-structure-boundaries.md (settings.py as leaf config package)
- source analysis: config/settings.py (full read — validate_kerberos_files lines 149-212, validate_llm_prod_mode lines 136-147, IntegrationMode enum line 24, log_active_config lines 214-269), tests/unit/config/test_settings.py (full read — _PROD_SETTINGS_BASE line 267, LLM prod tests lines 280-326, kerberos tests lines 70-144)
- integrations scan: integrations/pagerduty.py (PagerDutyIntegrationMode enum), integrations/slack.py (SlackIntegrationMode enum), integrations/servicenow.py (uses IntegrationMode directly from settings)
- gap analysis: confirmed validate_llm_prod_mode covers only LLM; PD, Slack, SN have no prod guardrails
- previous story analysis: 5-1 (done) — test regression at 1027 unit tests, file list discipline confirmed
- git log: epic-5 in-progress, story 5-1 complete, no integration-mode code changed since Epic 2/3

### Completion Notes List

- Added `validate_critical_integrations_prod_mode` model validator to `Settings` class in `config/settings.py`, immediately after `validate_llm_prod_mode`. Validator iterates over PD, Slack, and SN integration modes and raises `ValueError` if any is `OFF` or `MOCK` in `prod` environment.
- Added 11 unit tests to `tests/unit/config/test_settings.py` following the `_PROD_SETTINGS_BASE` fixture pattern: 6 raises tests (MOCK/OFF for PD, Slack, SN), 4 succeeds tests (LIVE/LOG for PD and SN, LIVE for Slack), 1 non-prod succeeds test.
- Full regression: 1134 tests pass, 0 skipped, 0 failures. Unit suite: 1038 tests (+11 new). Ruff lint clean.
- `validate_llm_prod_mode`, `validate_kerberos_files`, and `log_active_config` left unmodified per story constraints.

### File List

- `src/aiops_triage_pipeline/config/settings.py`
- `tests/unit/config/test_settings.py`
- `artifact/implementation-artifacts/sprint-status.yaml`
- `artifact/implementation-artifacts/5-2-enforce-security-critical-integration-configuration.md`

