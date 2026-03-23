# Story 5.1: Load and Validate Policies at Startup

Status: review

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a platform operator,
I want all policy/config artifacts loaded and validated on startup,
so that runtime behavior is deterministic and fails fast on invalid configuration.

**Implements:** FR49, FR50

## Acceptance Criteria

1. **Given** policy files are present in `config/`
   **When** application startup initializes configuration
   **Then** rulebook, peak, anomaly-detection, Redis TTL, Prometheus contract, outbox, retention,
   denylist, and topology policies are loaded once
   **And** startup fails fast on invalid schema or missing required policy artifacts.

2. **Given** environment configuration is supplied
   **When** settings resolution executes
   **Then** environment-specific configuration follows defined precedence and env file selection rules
   **And** resolved environment identifier is available to downstream policy enforcement.

## Tasks / Subtasks

- [x] Task 1: Create `AnomalyDetectionPolicyV1` contract (AC: 1)
  - [x] Create `src/aiops_triage_pipeline/contracts/anomaly_detection_policy.py` with frozen Pydantic v2
        `AnomalyDetectionPolicyV1` model containing all anomaly detector threshold fields (see Dev Notes
        for exact field names and default values from existing module-level constants in `stages/anomaly.py`).
  - [x] Fields: `schema_version: Literal["v1"] = "v1"`, `policy_id: Literal["anomaly-detection-policy-v1"] = "anomaly-detection-policy-v1"`, and all nine threshold fields with `float` type and positive validators (`lag_buildup_min_lag`, `lag_buildup_min_growth`, `lag_buildup_max_offset_progress`, `throughput_min_messages_per_sec`, `throughput_min_total_produce_requests_per_sec`, `throughput_failure_ratio_min`, `volume_drop_max_current_messages_in_per_sec`, `volume_drop_min_baseline_messages_in_per_sec`, `volume_drop_min_expected_requests_per_sec`).
  - [x] Add `field_validator` enforcing all float thresholds are `> 0` (except `throughput_failure_ratio_min` which must be in `(0.0, 1.0]`).
  - [x] Export from `contracts/__init__.py` if the package has an `__init__.py` with re-exports (check pattern in existing contracts).

- [x] Task 2: Create `config/policies/anomaly-detection-policy-v1.yaml` (AC: 1)
  - [x] Create the YAML file at `config/policies/anomaly-detection-policy-v1.yaml` with `schema_version: v1`,
        `policy_id: anomaly-detection-policy-v1`, and threshold values set to the current constant values
        from `stages/anomaly.py` (see Dev Notes for exact values).
  - [x] Verify `load_policy_yaml(Path("config/policies/anomaly-detection-policy-v1.yaml"), AnomalyDetectionPolicyV1)`
        succeeds without error.

- [x] Task 3: Wire anomaly detection policy at hot-path startup (AC: 1)
  - [x] Add `_ANOMALY_DETECTION_POLICY_PATH` module-level constant to `__main__.py` (alongside existing
        `_PEAK_POLICY_PATH`, `_RULEBOOK_POLICY_PATH`, etc.).
  - [x] Load `anomaly_detection_policy` in the hot-path startup `try` block at line ~319 (existing policies
        block), using `load_policy_yaml(_ANOMALY_DETECTION_POLICY_PATH, AnomalyDetectionPolicyV1)`.
  - [x] Update the `assemble_casefile_triage_stage(...)` call (line ~727) to pass
        `anomaly_detection_policy_version=anomaly_detection_policy.schema_version` explicitly, removing
        the implicit default `"v1"`.
  - [x] Add `startup_policies_loaded` log event immediately after all policies are loaded in the hot-path
        startup block, listing all loaded policy versions (see Dev Notes for exact log fields).

- [x] Task 4: Write unit tests (AC: 1, 2)
  - [x] Create `tests/unit/contracts/test_anomaly_detection_policy.py` with:
    - `test_default_values_match_anomaly_stage_constants`: instantiate `AnomalyDetectionPolicyV1()` and assert
      all default values match the current module-level constants in `stages/anomaly.py`.
    - `test_invalid_threshold_raises`: assert negative or zero thresholds raise `ValidationError`.
    - `test_failure_ratio_out_of_range_raises`: assert `throughput_failure_ratio_min > 1.0` raises `ValidationError`.
    - `test_load_policy_yaml_roundtrip`: use `load_policy_yaml` to load the real
      `config/policies/anomaly-detection-policy-v1.yaml` and assert the result is an `AnomalyDetectionPolicyV1`
      instance with the expected default values.
  - [x] Add `test_env_file_selection_uses_app_env` to `tests/unit/config/test_settings.py`:
    verify that `Settings(APP_ENV="dev", _env_file=None, ...)` resolves `APP_ENV` to `AppEnv.dev` and
    `max_action` returns `"NOTIFY"` (FR50 precedence coverage).

- [x] Task 5: Run full regression (AC: 1, 2)
  - [x] `uv run ruff check`
  - [x] `uv run pytest -q tests/unit`
  - [x] `TESTCONTAINERS_RYUK_DISABLED=true DOCKER_HOST=unix://$HOME/.docker/desktop/docker.sock uv run pytest -q -rs`

## Dev Notes

### Developer Context Section

- **Epic 4 (done)** implemented distributed coordination with feature flags. This story starts Epic 5.
- **The central gap this story closes**: `AnomalyDetectionPolicyV1` does not exist yet. The anomaly detector
  uses nine module-level float constants in `stages/anomaly.py` instead of a loaded policy. `CaseFilePolicyVersions`
  has an `anomaly_detection_policy_version` field that defaults to `"v1"` (hardcoded in `casefile.py` and in
  the `assemble_casefile_triage_stage` call in `__main__.py` line ~738), but no actual policy is loaded.
- **Do NOT wire policy thresholds into the anomaly detector in this story.** The existing module-level constants
  in `stages/anomaly.py` remain unchanged. Threshold wiring is Story 5.3 (FR52). This story's job is: define
  the contract, create the YAML, load at startup, stamp the version.
- **All other required policies** (rulebook, peak, redis-ttl, prometheus-contract, denylist) are already loaded
  at hot-path startup in the `try` block at line ~317-326 of `__main__.py`. The outbox policy is loaded in
  `_run_outbox_publisher` and casefile retention policy in `_run_casefile_lifecycle` — both already loaded.
  The only missing startup load is the anomaly detection policy.
- **Fail-fast is already wired** — the hot-path startup `try` block (line ~317) logs critical and re-raises on
  any exception from policy loading. Adding the anomaly detection policy to that block is sufficient; no new
  error-handling code is needed.
- **NFR-A2** requires every casefile stamps active policy versions for 25-month audit replay. The
  `CaseFilePolicyVersions.anomaly_detection_policy_version` field already exists in `models/case_file.py`
  (line 31, default "v1"). Story 5.1 replaces the implicit default with `anomaly_detection_policy.schema_version`
  from the loaded policy.

### Technical Requirements

- FR49: Load all policies from YAML at startup — anomaly detection policy is the missing piece.
- FR50: Environment config resolution via `APP_ENV`-driven env file selection — already implemented, needs test coverage.
- NFR-A2: Casefile stamps anomaly detection policy version — replace hardcoded `"v1"` with loaded version.
- NFR-S1: Policy files do not contain secrets — no masking needed in startup log.

### Architecture Compliance

- **D4 (Rule engine isolation)**: `contracts/` is the only shared import target for policy models. `anomaly_detection_policy.py` imports from `pydantic` only — no pipeline imports.
- **Composition root**: New policy loading goes in `__main__.py` — not in a module-level singleton.
- **Single flat `Settings` class**: No new settings fields for this story. The policy path is a hardcoded module-level constant following the existing pattern (`_PEAK_POLICY_PATH`, etc.).
- **Package dependency rules**: `contracts/` → external libraries only. `anomaly_detection_policy.py` imports only from `pydantic`.

### Library / Framework Requirements

- Locked stack (do not change):
  - Python `>=3.13`
  - `pydantic==2.12.5` — frozen=True BaseModel, `Literal["v1"]` schema_version pattern (matches all existing contracts)
  - `pydantic-settings~=2.13.1`
  - `pytest==9.0.2`
- `PyYAML` is already a project dependency — loaded lazily in `load_policy_yaml()` via `import yaml` (keep this pattern, do not add top-level import).

### File Structure Requirements

**New files:**
- `src/aiops_triage_pipeline/contracts/anomaly_detection_policy.py`
- `config/policies/anomaly-detection-policy-v1.yaml`
- `tests/unit/contracts/test_anomaly_detection_policy.py`

**Modified files:**
- `src/aiops_triage_pipeline/__main__.py` — add path constant, load policy in startup block, update casefile call, add startup log event
- `tests/unit/config/test_settings.py` — add env file selection test

**Do NOT modify:**
- `src/aiops_triage_pipeline/pipeline/stages/anomaly.py` — constants remain unchanged (threshold wiring is story 5.3)
- `src/aiops_triage_pipeline/pipeline/stages/evidence.py` — no new policy parameter (threshold wiring is story 5.3)
- `src/aiops_triage_pipeline/pipeline/scheduler.py` — no changes needed
- `src/aiops_triage_pipeline/config/settings.py` — no new fields

### Testing Requirements

- **Unit tests must verify:**
  - `AnomalyDetectionPolicyV1` default values match the nine constants in `stages/anomaly.py`.
  - All threshold fields enforce positive-value constraint via `ValidationError`.
  - `throughput_failure_ratio_min` rejects values outside `(0.0, 1.0]`.
  - `load_policy_yaml` can round-trip the real YAML file into `AnomalyDetectionPolicyV1`.
  - `Settings` resolves `APP_ENV` to correct env file (FR50 precedence).
- **Test patterns to follow** (from `tests/unit/contracts/test_operational_alert_policy.py` and `test_policy_models.py`):
  - Per-file, no shared fixtures.
  - Use `load_policy_yaml(Path("config/policies/..."), ModelClass)` with the real project YAML for round-trip tests.
  - Use `pytest.raises(ValidationError)` for schema violation tests.
- **Preferred regression command:**
  - `TESTCONTAINERS_RYUK_DISABLED=true DOCKER_HOST=unix://$HOME/.docker/desktop/docker.sock uv run pytest -q -rs`
- **Quality gate:** zero skipped tests across all test suites.

### AnomalyDetectionPolicyV1 Threshold Reference

These nine threshold constants in `src/aiops_triage_pipeline/pipeline/stages/anomaly.py` (lines 22-30) are
the canonical source. The policy fields use snake_case versions of the same names, minus the leading underscore:

| Module constant | Policy field | Default value |
|---|---|---|
| `_LAG_BUILDUP_MIN_LAG` | `lag_buildup_min_lag` | `100.0` |
| `_LAG_BUILDUP_MIN_GROWTH` | `lag_buildup_min_growth` | `25.0` |
| `_LAG_BUILDUP_MAX_OFFSET_PROGRESS` | `lag_buildup_max_offset_progress` | `10.0` |
| `_THROUGHPUT_MIN_MESSAGES_PER_SEC` | `throughput_min_messages_per_sec` | `1000.0` |
| `_THROUGHPUT_MIN_TOTAL_PRODUCE_REQUESTS_PER_SEC` | `throughput_min_total_produce_requests_per_sec` | `100.0` |
| `_THROUGHPUT_FAILURE_RATIO_MIN` | `throughput_failure_ratio_min` | `0.05` |
| `_VOLUME_DROP_MAX_CURRENT_MESSAGES_IN_PER_SEC` | `volume_drop_max_current_messages_in_per_sec` | `1.0` |
| `_VOLUME_DROP_MIN_BASELINE_MESSAGES_IN_PER_SEC` | `volume_drop_min_baseline_messages_in_per_sec` | `50.0` |
| `_VOLUME_DROP_MIN_EXPECTED_REQUESTS_PER_SEC` | `volume_drop_min_expected_requests_per_sec` | `150.0` |

### Startup Log Event for Policy Audit Trail

After loading all policies in the hot-path startup block, add a single structured log call:

```python
logger.info(
    "startup_policies_loaded",
    event_type="runtime.startup_policies_loaded",
    rulebook_policy_version=rulebook_policy.schema_version,
    peak_policy_version=peak_policy.schema_version,
    anomaly_detection_policy_version=anomaly_detection_policy.schema_version,
    redis_ttl_policy_version=redis_ttl_policy.schema_version,
    prometheus_metrics_contract_version=prometheus_metrics_contract.schema_version,
)
```

Note: denylist does not have a schema_version (it's a plain dict); outbox and retention policies
are logged in their respective runtime modes. Topology is logged by `TopologyRegistryLoader`.

### Previous Story Intelligence

**From Story 4.3 (done — rollout testing):**
- File list in Dev Agent Record must include ALL changed files including sprint-status.yaml.
- Integration tests that used `pytest.skip` were changed to `pytest.fail` — do NOT use skip anywhere.
- Unit tests: per-file test doubles, no shared Redis or infra fixtures.
- `uv run ruff check` runs clean; fix any linting issues before claiming done.

**From Story 4.2 (done — shard coordination):**
- `SHARD_REGISTRY_ENABLED` was added to `settings.py` (line 110) and `log_active_config` (line 247) — follow
  the same discipline: any new settings field must be in `log_active_config`.
- Story 5.1 adds no new settings fields; confirm `log_active_config` does not need changes.

### Git Intelligence Summary

Recent commits (most relevant to this story):
- `2e55a32`: fix(epic-4) acceptance note — no source changes
- `0a69630`: bmad(epic-4/retrospective) — sprint-status.yaml updated, epic-5 status set to `in-progress`
- `6eaa63a`: fix(epic-4/4-3): story marked done
- `aa19ea3`: bmad(epic-4/4-3): test files, docs, and policy version plumbing
- `3447ce6`: bmad(epic-4/4-1): established test patterns under `tests/unit/coordination/` and
  `tests/integration/coordination/`

The existing `tests/unit/contracts/` directory has `test_frozen_models.py`, `test_operational_alert_policy.py`,
and `test_policy_models.py` — add `test_anomaly_detection_policy.py` there (sibling), no new `__init__.py` needed.

### Latest Tech Information

External verification date: 2026-03-23.

- `pydantic==2.12.5` — `Literal["v1"]` for `schema_version` is the correct frozen discriminator pattern
  (matches all existing policy contracts: `PeakPolicyV1`, `OperationalAlertPolicyV1`). Use `field_validator`
  (not `validator`) for the threshold range checks — pydantic v2 API.
- `PyYAML` safe_load: handles `float` fields in YAML natively; `0.05` in YAML becomes Python `float(0.05)`.
  No special handling needed.

### Project Context Reference

Applied `archive/project-context.md` and implementation patterns:
- Python 3.13 typing and frozen contract discipline: `BaseModel, frozen=True`.
- No DI container, no service locator — load policy in `__main__.py` composition root.
- Single flat `Settings` class — no new settings sub-classes.
- Feature flags follow `FEATURE_ENABLED: bool = False` pattern — not applicable to this story.
- Full regression policy expects zero skipped tests.
- Module-level constants in `stages/anomaly.py` remain unchanged (this story does not touch the detector).

### References

- [Source: `artifact/planning-artifacts/epics.md` — Epic 5 / Story 5.1]
- [Source: `artifact/planning-artifacts/prd/functional-requirements.md` — FR49, FR50]
- [Source: `artifact/planning-artifacts/prd/non-functional-requirements.md` — NFR-A2, NFR-S1]
- [Source: `artifact/planning-artifacts/architecture/core-architectural-decisions.md` — D4]
- [Source: `artifact/planning-artifacts/architecture/implementation-patterns-consistency-rules.md`]
- [Source: `artifact/planning-artifacts/architecture/project-structure-boundaries.md`]
- [Source: `src/aiops_triage_pipeline/config/settings.py` — `load_policy_yaml()` at line 294, `Settings` class]
- [Source: `src/aiops_triage_pipeline/__main__.py` — startup block lines 317-352, `_*_PATH` constants lines 109-123, casefile call line ~738]
- [Source: `src/aiops_triage_pipeline/pipeline/stages/anomaly.py` — threshold constants lines 22-30]
- [Source: `src/aiops_triage_pipeline/pipeline/stages/casefile.py` — `assemble_casefile_triage_stage` signature lines 70-71]
- [Source: `src/aiops_triage_pipeline/models/case_file.py` — `CaseFilePolicyVersions.anomaly_detection_policy_version` line 31]
- [Source: `src/aiops_triage_pipeline/contracts/peak_policy.py` — frozen model pattern]
- [Source: `src/aiops_triage_pipeline/contracts/operational_alert_policy.py` — `policy_id` Literal pattern lines 97-98]
- [Source: `tests/unit/contracts/test_operational_alert_policy.py` — test patterns to follow]
- [Source: `config/policies/peak-policy-v1.yaml` — YAML structure reference]

## Dev Agent Record

### Agent Model Used

claude-sonnet-4-6

### Debug Log References

- create-story workflow for story key `5-1-load-and-validate-policies-at-startup`
- artifact analysis: sprint-status.yaml (story selection), epics.md (Epic 5 / Story 5.1 full context), architecture shards (core-architectural-decisions, implementation-patterns-consistency-rules, project-structure-boundaries), PRD FR49/FR50/NFR-A2
- source analysis: settings.py (load_policy_yaml at line 294, Settings env-file pattern), __main__.py (startup block lines 317-352, path constants lines 109-123, casefile call line ~738, assemble_casefile_triage_stage parameter), stages/anomaly.py (nine threshold constants lines 22-30), casefile.py (anomaly_detection_policy_version param lines 70-71), models/case_file.py (CaseFilePolicyVersions line 31), contracts/ (peak_policy.py and operational_alert_policy.py for model pattern)
- config/policies/ directory listing: confirmed anomaly-detection-policy-v1.yaml does not exist
- contracts/ directory listing: confirmed anomaly_detection_policy.py does not exist
- previous story analysis: 4-3 (done) — loaded for test pattern and review feedback
- git log: confirmed Epic 5 started, test infrastructure already established

### Completion Notes List

- Created `AnomalyDetectionPolicyV1` frozen Pydantic v2 model with nine float threshold fields, two `field_validator`s (positive constraint + `(0.0, 1.0]` range for failure ratio), and `Literal["v1"]` schema_version pattern matching all existing contracts.
- Created `config/policies/anomaly-detection-policy-v1.yaml` with values matching the nine module-level constants in `stages/anomaly.py`.
- Wired anomaly detection policy into `__main__.py`: added `_ANOMALY_DETECTION_POLICY_PATH` constant, loaded in hot-path startup `try` block, passed `anomaly_detection_policy` as parameter to `_hot_path_scheduler_loop`, updated `assemble_casefile_triage_stage` call to pass explicit `anomaly_detection_policy_version=anomaly_detection_policy.schema_version`, added `startup_policies_loaded` structured log event.
- Exported `AnomalyDetectionPolicyV1` from `contracts/__init__.py` following existing pattern.
- Added 4 unit tests in `test_anomaly_detection_policy.py` (default values, invalid threshold, failure ratio range, YAML round-trip) and 1 test in `test_settings.py` (FR50 env file selection).
- Updated 5 existing `test_main.py` tests that call `_hot_path_scheduler_loop` to pass the new `anomaly_detection_policy` parameter.
- Full regression: 1121 tests passed, 0 skipped, 0 failed.

### File List

- `src/aiops_triage_pipeline/contracts/anomaly_detection_policy.py` (new)
- `src/aiops_triage_pipeline/contracts/__init__.py` (modified)
- `src/aiops_triage_pipeline/__main__.py` (modified)
- `config/policies/anomaly-detection-policy-v1.yaml` (new)
- `tests/unit/contracts/test_anomaly_detection_policy.py` (new)
- `tests/unit/config/test_settings.py` (modified)
- `tests/unit/test_main.py` (modified)
- `artifact/implementation-artifacts/sprint-status.yaml` (modified)
- `artifact/implementation-artifacts/5-1-load-and-validate-policies-at-startup.md` (modified)

### Story Completion Status
