# Story 2.1: Configure Environment-Specific Peak History Depth and Loading

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a Platform Operations Engineer,
I want explicit peak-history depth values per environment,
so that scoring has sufficient baseline context without code changes.

## Acceptance Criteria

1. Given environment files are maintained for prod, uat, and dev, when peak depth configuration is applied, then each environment defines `STAGE2_PEAK_HISTORY_MAX_DEPTH` explicitly and values align with documented day conversions at 5-minute intervals (dev=2016/7d, uat=4320/15d, prod=8640/30d).

2. Given application startup selects env config through `APP_ENV`, when settings are loaded, then environment-specific depth values are used and no fallback to the legacy 12-sample default occurs when explicit values exist.

3. Given `STAGE2_PEAK_HISTORY_MAX_DEPTH` is missing or invalid for the selected `APP_ENV`, when configuration validation executes at startup, then the system emits an operator-visible validation warning or startup failure with the invalid key and environment and service startup does not continue with an implicit legacy default value.

## Tasks / Subtasks

- [x] Add Docker pre-check as first step (epic retro action item) (AC: all)
  - [x] Verify Docker engine reachability with `bash scripts/docker-precheck.sh` before executing testcontainers-backed tests.

- [x] Add `STAGE2_PEAK_HISTORY_MAX_DEPTH` to all three environment files with correct sample counts (AC: 1, 2)
  - [x] Set `STAGE2_PEAK_HISTORY_MAX_DEPTH=2016` in `config/.env.dev` (7 days × 288 samples/day).
  - [x] Set `STAGE2_PEAK_HISTORY_MAX_DEPTH=4320` in `config/.env.uat.template` (15 days × 288 samples/day).
  - [x] Set `STAGE2_PEAK_HISTORY_MAX_DEPTH=8640` in `config/.env.prod.template` (30 days × 288 samples/day).
  - [x] Add inline comment on each line explaining the day-conversion: `# N days × 288 samples/day (5-min intervals)`.

- [x] Add startup validation in `settings.py` that rejects absent or invalid depth when env-file is in use (AC: 2, 3)
  - [x] Add a `model_validator` (mode="after") that detects when `APP_ENV` is dev/uat/prod and `STAGE2_PEAK_HISTORY_MAX_DEPTH` still equals the class-level default (12), and raises `ValueError` naming the key and environment so operators see a clear failure message.
  - [x] Ensure existing positive-value validator (`STAGE2_PEAK_HISTORY_MAX_DEPTH must be > 0`) is preserved.
  - [x] Do NOT change the Python-level default of 12 — the validator catches the fallback case at runtime, preserving test isolation.

- [x] Update documentation to reflect environment-specific depth values and day-conversion rationale (AC: 1)
  - [x] Update `docs/development-guide.md` or equivalent ops reference with `STAGE2_PEAK_HISTORY_MAX_DEPTH` table (env, samples, days).
  - [x] Update `docs/runtime-modes.md` if it references peak depth configuration.
  - [x] Documentation must use project-native terminology only — no BMAD/workflow/story-ID references (NFR18).

- [x] Add targeted unit tests for new validation behavior (AC: 2, 3)
  - [x] Test: env-file depth value overrides default — Settings loads `dev` env file, `STAGE2_PEAK_HISTORY_MAX_DEPTH` resolves to 2016.
  - [x] Test: missing depth for `APP_ENV=dev` raises `ValueError` mentioning `STAGE2_PEAK_HISTORY_MAX_DEPTH` and the environment name.
  - [x] Test: missing depth for `APP_ENV=uat` raises similarly.
  - [x] Test: missing depth for `APP_ENV=prod` raises similarly.
  - [x] Test: `APP_ENV=local` with default 12 does NOT raise (local env is exempt — no env-file depth expectation).
  - [x] Test: `APP_ENV=harness` with default 12 does NOT raise (harness env is exempt).
  - [x] Test: explicit non-default value (e.g. `STAGE2_PEAK_HISTORY_MAX_DEPTH=100`) with any env passes validation.
  - [x] Preserve existing `test_stage2_parallel_and_retention_settings_have_safe_defaults` — it must still pass.
  - [x] Use `get_settings.cache_clear()` appropriately in singleton-affecting tests.

- [x] Execute quality gate with zero skipped tests (AC: all)
  - [x] Run targeted config suite: `uv run pytest -q tests/unit/config/test_settings.py`.
  - [x] Run full regression: `TESTCONTAINERS_RYUK_DISABLED=true DOCKER_HOST=unix://$HOME/.docker/desktop/docker.sock uv run pytest -q -rs`.
  - [x] Confirm `0 skipped` before marking done.

## Dev Notes

### Story Context and Constraints

- Story scope is FR12, FR13, FR14 only — do not implement FR15/FR16/FR17 (shard lease TTL — Story 2.2).
- Fix dependency: Peak depth must be correct before the tier-3 peak amplifier (Epic 1 scoring) can produce statistically meaningful results. This is Fix 2 in the architecture's Fix 2 → Fix 3 causal chain.
- Epic 1 scoring function (in `pipeline/stages/gating.py`) is already implemented and consuming `STAGE2_PEAK_HISTORY_MAX_DEPTH` via `get_settings()`. This story does not touch `gating.py`.
- No contract/schema changes. Frozen contract posture (`GateInputV1`, `ActionDecisionV1`, `CaseFileTriageV1`) remains untouched.
- D6 invariant preserved: scoring logic stays module-local to `gating.py`; no changes to `diagnosis/` package.
- Configuration values are non-secret operational data, safe for version-controlled env files (NFR-S2).
- NFR-P3: peak profile memory scales linearly with depth — increasing to prod=8640 is expected behavior, not a defect.

### Current Code Reality (Build on Existing)

**Env files: STAGE2_PEAK_HISTORY_MAX_DEPTH is currently ABSENT from all three env files.**
- `config/.env.dev` — does not contain `STAGE2_PEAK_HISTORY_MAX_DEPTH`. Running with Settings default of `12`.
- `config/.env.uat.template` — does not contain `STAGE2_PEAK_HISTORY_MAX_DEPTH`. Running with Settings default of `12`.
- `config/.env.prod.template` — does not contain `STAGE2_PEAK_HISTORY_MAX_DEPTH`. Running with Settings default of `12`.

**Settings class (line 118): `STAGE2_PEAK_HISTORY_MAX_DEPTH: int = 12`** — this is the legacy default this story eliminates for dev/uat/prod environments.

**`_APP_ENV` resolution in `settings.py` (line 13):** `os.getenv("APP_ENV", "local")` — read before class definition. Env file is selected as `config/.env.{_APP_ENV}`. Direct env var overrides env file (K8s injection pattern). This is the existing APP_ENV-driven selection mechanism for FR13.

**Existing validator to preserve (line 218):** `if self.STAGE2_PEAK_HISTORY_MAX_DEPTH <= 0: raise ValueError(...)`.

**No startup validator currently exists** that detects a missing/defaulted depth value for named environments. Adding this closes the NFR-R3 / AC-3 gap.

**`log_active_config` (line 281):** already logs `STAGE2_PEAK_HISTORY_MAX_DEPTH` — no change needed there.

### Technical Requirements

- **Day-to-sample conversion rate:** 5-minute intervals → 12 samples/hour → 288 samples/day.
  - dev: 7 days × 288 = 2016 samples.
  - uat: 15 days × 288 = 4320 samples.
  - prod: 30 days × 288 = 8640 samples.
  - These values come from architectural decision D-R5 and PRD FR14.

- **Startup validation logic:** The validator must detect the "fallback to default" scenario. The most reliable approach is: if `APP_ENV in {dev, uat, prod}` and `STAGE2_PEAK_HISTORY_MAX_DEPTH == 12` (the class-level default), raise `ValueError`. This avoids any external file reads inside the validator.
  - Do NOT test for `== 0` (already handled by existing validator).
  - Do NOT raise for `APP_ENV in {local, harness}` — those environments run on default depth intentionally (local dev, test harness).
  - Raise `ValueError` with a message that includes both the key name and the environment value for operator clarity.

- **Pydantic model validator pattern (existing style, see lines 139, 152, 173):** Add a new `@model_validator(mode="after")` method. Name it `validate_peak_depth_not_default_for_named_envs` or similar. Return `self` on success, raise `ValueError` on failure. Follow the existing pattern exactly.

- **No changes to `Settings` field definitions or existing validators** — only ADD a new validator method.

- **No new imports required** — `AppEnv` is already available within the class.

### Architecture Compliance

- **Primary change surface:** `config/.env.dev`, `config/.env.uat.template`, `config/.env.prod.template`, `src/aiops_triage_pipeline/config/settings.py`.
- **Test surface:** `tests/unit/config/test_settings.py`.
- **Protected zones remain untouched:**
  - `src/aiops_triage_pipeline/contracts/*`
  - `src/aiops_triage_pipeline/diagnosis/*`
  - `src/aiops_triage_pipeline/integrations/*`
  - `src/aiops_triage_pipeline/pipeline/stages/gating.py` (Epic 1 scoring — do not touch)
- **Documentation surface (broad refresh approved):** `docs/development-guide.md`, `docs/runtime-modes.md`, and related ops docs.
- Keep `config` package as a leaf — `settings.py` must not import specific contract classes (existing rule).
- `pydantic-settings` env-file resolution pattern: preserve `APP_ENV`-driven `.env.{APP_ENV}` selection; direct env vars override `.env` values (K8s injection pattern).

### Library / Framework Requirements

Latest checks executed on 2026-03-29 from official PyPI package indexes:

- `pydantic` latest: `2.12.5` (project pinned `2.12.5`) — no change needed.
- `pydantic-settings` latest: `2.13.1` (project range `~=2.13.1`) — no change needed.
- `pytest` latest: `9.0.2` (project pinned `9.0.2`) — no change needed.

Story guidance: do not perform dependency upgrades in Story 2.1. The scope is configuration-only plus a settings validator addition. Epic retro tech debt items (`confluent-kafka` 2.13.0→2.13.2, `opentelemetry-sdk` 1.39.1→1.40.0) are tracked separately and must not be bundled into this story.

### File Structure Requirements

Primary implementation surface:

- `config/.env.dev` — add `STAGE2_PEAK_HISTORY_MAX_DEPTH=2016` with comment.
- `config/.env.uat.template` — add `STAGE2_PEAK_HISTORY_MAX_DEPTH=4320` with comment.
- `config/.env.prod.template` — add `STAGE2_PEAK_HISTORY_MAX_DEPTH=8640` with comment.
- `src/aiops_triage_pipeline/config/settings.py` — add `model_validator` for startup detection.

Primary verification surface:

- `tests/unit/config/test_settings.py` — new tests for FR12/FR13/FR14 validation behavior.

Documentation surface (update, do not skip):

- `docs/development-guide.md` — add `STAGE2_PEAK_HISTORY_MAX_DEPTH` env-specific table.
- `docs/runtime-modes.md` — update if it references peak depth (check before editing).

Do NOT create new files in `pipeline/stages/`, `contracts/`, `models/`, `audit/`, or `coordination/` — this story has zero production code changes outside `config/settings.py`.

### Testing Requirements

Required behavioral coverage for `tests/unit/config/test_settings.py`:

1. **FR12 — explicit depth in all env files:** Test that `config/.env.dev` contains `STAGE2_PEAK_HISTORY_MAX_DEPTH=2016` (file-content assertion, not settings-object test).
2. **FR13 — no fallback when env value is present:** Test that Settings loaded with `STAGE2_PEAK_HISTORY_MAX_DEPTH=2016` (simulating dev env-file load) resolves to exactly 2016, not 12.
3. **AC-3 / NFR-R3 — validator catches missing depth for named envs:** Test ValueError is raised when `APP_ENV=dev/uat/prod` and depth is 12 (default/unset).
4. **AC-3 — local/harness envs are exempt:** Test `APP_ENV=local` and `APP_ENV=harness` with depth=12 do not raise.
5. **Regression — existing tests must still pass:** All 625+ existing `test_settings.py` tests must remain green.

Test helper pattern (already established in `test_settings.py` — reuse):

```python
def _base_settings_kwargs() -> dict:
    return {
        "_env_file": None,
        "KAFKA_BOOTSTRAP_SERVERS": "localhost:9092",
        "DATABASE_URL": "postgresql+psycopg://u:p@h/db",
        "REDIS_URL": "redis://localhost:6379/0",
        "S3_ENDPOINT_URL": "http://localhost:9000",
        "S3_ACCESS_KEY": "key",
        "S3_SECRET_KEY": "secret",
        "S3_BUCKET": "bucket",
    }
```

Required commands:

```bash
uv run pytest -q tests/unit/config/test_settings.py
```

```bash
TESTCONTAINERS_RYUK_DISABLED=true DOCKER_HOST=unix://$HOME/.docker/desktop/docker.sock uv run pytest -q -rs
```

Acceptance gate: full regression must finish with `0 skipped`.

### Previous Story Intelligence (Story 1.3 / Epic 1)

From Epic 1 Retrospective and Story 1.3 artifact:

- **Docker pre-check is a standard first task** — Epic 1 retro action item #1: "Add 'Docker pre-check: start docker-desktop.service' as standard first dev task in story kickoff checklist." Apply this before running any testcontainers-backed regression.
- **Scoring payload validation checklist** — Epic 1 retro action item #2 applies to Epic 2 stories that touch scoring metadata. Story 2.1 does NOT touch scoring metadata — this item is N/A for this story.
- **Story 3.x ATDD fixtures** — Epic 1 retro action item #3: verify `uv run pytest tests/atdd/` baseline is clean before stories touching `audit/` or `casefile/`. Story 2.1 does not touch those modules, but run the ATDD check as good practice.
- **Strict payload parsing from day one** — not applicable here (no scoring payloads), but note the pattern: defensive validation goes in the initial implementation pass, not deferred to code review.
- **Verify `.env.prod`, `.env.uat`, `.env.dev` current state** — retro prep item confirmed: `STAGE2_PEAK_HISTORY_MAX_DEPTH` is absent from all three files. Story 2.1 adds it.
- **`get_settings.cache_clear()` discipline** — always call before and after any test that invokes `get_settings()` as a singleton. Pattern established in existing `test_settings.py`.
- **Frozen contracts and D6 invariant** — continue the Epic 1 posture: no contract changes, no `diagnosis/` imports.
- **Story 3.1 ATDD fixtures were latently broken** — previously fixed during Story 1.1. Do not assume ATDD suite is clean without verifying.

### Git Intelligence Summary

Recent relevant commit patterns:

- `27cc38c` (`retro(epic-1)`): Epic 1 complete, sprint-status updated, epic-2 set to `in-progress`. Epic 2 Story 2.1 is the immediate next story.
- `585b4d8` (`fix(review)`): Story 1.3 review resolution — tightened audit/casefile/replay coverage.
- `f1ac89f` (Story 1.2 completion): enriched gate inputs, AG4 enforcement implemented.
- `45c87fc` (`fix(review)`): scoring payload safety fixes — pattern to apply to any future Settings validators.
- `33b9007` (`feat(gating)`): scoring core implementation — `STAGE2_PEAK_HISTORY_MAX_DEPTH` now consumed at runtime.

Actionable implication for Story 2.1:

- Changes are configuration-only plus one `model_validator` addition — smallest possible surface.
- No changes to `gating.py`, `casefile.py`, `audit/replay.py`, or any contract files.
- Commit style observed in project: `feat(config):` or `fix(config):` would be appropriate.
- Keep changes tightly scoped: 3 env files + 1 settings validator + tests + docs.

### Latest Tech Information (Step 4 Research)

Research source: official PyPI JSON package metadata (checked 2026-03-29).

- No library upgrades required for Story 2.1.
- `pydantic-settings 2.13.1` fully supports the `model_config = SettingsConfigDict(env_file=...)` pattern already in use.
- `pydantic 2.12.5` `model_validator(mode="after")` is the correct decorator for post-init field cross-validation (already used in `settings.py` for other validators).
- Epic retro-tracked tech debt (`confluent-kafka` 2.13.0→2.13.2, `opentelemetry-sdk` 1.39.1→1.40.0) must NOT be bundled into this story.

### Project Context Reference

Critical rules from `artifact/project-context.md` applied to this story:

- `APP_ENV` is read before `Settings` class creation (`_APP_ENV = os.getenv("APP_ENV", "local")`); env file is selected as `config/.env.{_APP_ENV}`. Direct env var overrides `.env` values.
- `config` package is a leaf — `settings.py` must not import specific contract classes. The new validator must not introduce any such imports.
- All `.env.*` files must define explicit depth values with no fallback to legacy 12-sample defaults (NFR8).
- Configuration values are non-secret and version-control safe (NFR-S2).
- Full regression quality gate requires zero skipped tests.
- Use `get_settings.cache_clear()` between tests that rely on singleton state.
- Naming: `snake_case` for functions, `UPPER_SNAKE_CASE` for settings fields. Follow existing validator naming in `settings.py`.
- Ruff: line length 100, target py313, lint selection E,F,I,N,W. Run `uv run ruff check` before commit.

### References

- `artifact/planning-artifacts/epics.md` (Epic 2 / Story 2.1 acceptance criteria)
- `artifact/planning-artifacts/prd.md` (FR12, FR13, FR14; NFR-P3, NFR-R3, NFR-S2, NFR8)
- `artifact/planning-artifacts/architecture/core-architectural-decisions.md` (D-R5: depth values per env)
- `artifact/planning-artifacts/architecture/project-structure-boundaries.md` (FR12-FR14 structure mapping)
- `artifact/planning-artifacts/architecture/project-context-analysis.md` (fix dependency graph: Fix 2 → Fix 3)
- `artifact/planning-artifacts/architecture/implementation-patterns-consistency-rules.md`
- `artifact/project-context.md`
- `artifact/implementation-artifacts/1-3-persist-differentiated-confidence-and-reason-code-audit-outcomes.md`
- `artifact/implementation-artifacts/epic-1-retro-2026-03-29.md`
- `src/aiops_triage_pipeline/config/settings.py`
- `config/.env.dev`
- `config/.env.uat.template`
- `config/.env.prod.template`
- `tests/unit/config/test_settings.py`
- `docs/development-guide.md`
- `docs/runtime-modes.md`

## Story Completion Status

- Story analysis type: exhaustive artifact-based context build
- Previous-story intelligence: applied from Story 1.3 artifact and Epic 1 retrospective
- Git-intelligence dependency: completed
- Web research dependency: completed (no dependency upgrades warranted)
- Completion note: Ultimate context engine analysis completed - comprehensive developer guide created

## Dev Agent Record

### Agent Model Used

gpt-5 (Codex)

### Implementation Plan

- Add explicit environment depth entries in `config/.env.dev`, `config/.env.uat.template`, and `config/.env.prod.template`.
- Add a post-init `Settings` validator that rejects legacy depth default for `APP_ENV` in `dev/uat/prod`.
- Keep the existing positive-value depth validator unchanged.
- Update runtime/development docs with the environment depth conversion table and startup validation behavior.
- Run targeted and full regression gates, then close the story artifacts/status updates.

### Debug Log References

- Added reusable Docker pre-check script (`scripts/docker-precheck.sh`) and verified Docker reachability before regression runs.
- Added `STAGE2_PEAK_HISTORY_MAX_DEPTH` to all named env files with explicit day-to-sample comments.
- Added `validate_peak_depth_type_for_named_envs` + `validate_peak_depth_not_default_for_named_envs` in `Settings` so named envs fail with env-aware errors for invalid or legacy-default depth values.
- Added AC2 env-file loading test coverage and removed stale RED-phase comments from Story 2.1 tests.
- Updated runtime/development docs with depth mapping, Docker pre-check command, and corrected `SHARD_LEASE_TTL_SECONDS` default (`270`).
- Quality gates executed:
  - `uv run pytest -q tests/unit/config/test_settings.py` -> `62 passed`.
  - `TESTCONTAINERS_RYUK_DISABLED=true DOCKER_HOST=unix://$HOME/.docker/desktop/docker.sock uv run pytest -q -rs` -> `1196 passed`, `0 skipped`.
  - Scoped lint on changed files passed: `uv run ruff check src/aiops_triage_pipeline/config/settings.py tests/unit/config/test_settings.py docs/development-guide.md docs/runtime-modes.md`.

### Completion Notes List

- Implemented FR12/FR13/FR14 with minimal surface area: env config values, one startup validator, docs, and test updates.
- Preserved existing `STAGE2_PEAK_HISTORY_MAX_DEPTH > 0` validation and retained Python default `12` for local/harness test isolation.
- Confirmed no contract, gating stage, diagnosis, audit, or integration module changes.
- Story status moved to `done` after resolving all review findings and re-running quality gates.

### File List

- config/.env.dev
- config/.env.uat.template
- config/.env.prod.template
- src/aiops_triage_pipeline/config/settings.py
- tests/unit/config/test_settings.py
- docs/development-guide.md
- docs/runtime-modes.md
- scripts/docker-precheck.sh
- artifact/implementation-artifacts/sprint-status.yaml
- artifact/implementation-artifacts/2-1-configure-environment-specific-peak-history-depth-and-loading.md

### Change Log

- 2026-03-29: Added explicit `STAGE2_PEAK_HISTORY_MAX_DEPTH` values for `dev/uat/prod` env files with day conversion comments.
- 2026-03-29: Added startup validator in `Settings` to reject legacy depth fallback (`12`) for named environments.
- 2026-03-29: Updated settings tests and docs; executed full regression with zero skipped tests.
- 2026-03-29: Resolved code-review findings: added env-aware invalid depth validation, strengthened AC2 env-file loading tests, added reusable Docker pre-check script, corrected runtime TTL docs, and revalidated full regression (`1196 passed`, `0 skipped`).

## Senior Developer Review (AI)

### Outcome

- Approved after fixes.

### Findings Addressed

- Added env-aware validation for non-integer `STAGE2_PEAK_HISTORY_MAX_DEPTH` in named environments (`APP_ENV in {dev, uat, prod}`).
- Added direct env-file loading coverage for FR13/AC2 (`config/.env.dev` path, no constructor override fallback path).
- Removed stale RED-phase statements from Story 2.1 test docstrings/comments.
- Corrected runtime documentation drift for `SHARD_LEASE_TTL_SECONDS` default (`270`).
- Added reusable Docker readiness pre-check (`bash scripts/docker-precheck.sh`) and documented usage.

### Verification

- `uv run ruff check src/aiops_triage_pipeline/config/settings.py tests/unit/config/test_settings.py`
- `uv run pytest -q tests/unit/config/test_settings.py` (`62 passed`)
- `TESTCONTAINERS_RYUK_DISABLED=true DOCKER_HOST=unix://$HOME/.docker/desktop/docker.sock uv run pytest -q -rs` (`1196 passed`, `0 skipped`)
