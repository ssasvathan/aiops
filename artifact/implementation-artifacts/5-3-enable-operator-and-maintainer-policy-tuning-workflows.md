# Story 5.3: Enable Operator and Maintainer Policy Tuning Workflows

Status: review

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As an application maintainer,
I want to tune topology and denylist/policy configuration via YAML promotion flow,
so that behavior changes can be tested in lower environments before production.

**Implements:** FR52, FR53

## Acceptance Criteria

1. **Given** maintainers update topology or denylist/policy YAML files
   **When** changes are deployed in lower environments
   **Then** pipeline behavior reflects new configuration without code modifications
   **And** outcomes are verifiable through casefile and structured telemetry inspection.

2. **Given** a validated configuration update
   **When** promotion proceeds to production
   **Then** policy version traces remain visible for audit/replay
   **And** operational behavior remains consistent with documented configuration authority.

## Tasks / Subtasks

- [x] Task 1: Wire `AnomalyDetectionPolicyV1` thresholds into the anomaly detector (AC: 1)
  - [x] In `src/aiops_triage_pipeline/pipeline/stages/anomaly.py`, add
        `from aiops_triage_pipeline.contracts.anomaly_detection_policy import AnomalyDetectionPolicyV1`
        import at the top of the file.
  - [x] Add `anomaly_detection_policy: AnomalyDetectionPolicyV1 | None = None` keyword-only parameter
        to `detect_anomaly_findings()` (after `baseline_values_by_scope`).
  - [x] Pass `anomaly_detection_policy=anomaly_detection_policy` in **both** `_compute_scope_findings()`
        call sites inside `detect_anomaly_findings()` (the cache path and the non-cache path).
  - [x] Add `anomaly_detection_policy: AnomalyDetectionPolicyV1 | None = None` keyword-only parameter
        to `_compute_scope_findings()`. Pass it to each of the three private `_detect_*` function calls.
  - [x] Update `_detect_consumer_lag_buildup(scope, scope_metrics)` signature to add
        `anomaly_detection_policy: AnomalyDetectionPolicyV1 | None = None`. At the top of the body,
        resolve three locals before use:
        ```python
        min_lag = anomaly_detection_policy.lag_buildup_min_lag if anomaly_detection_policy else _LAG_BUILDUP_MIN_LAG
        min_growth = anomaly_detection_policy.lag_buildup_min_growth if anomaly_detection_policy else _LAG_BUILDUP_MIN_GROWTH
        max_offset_progress = anomaly_detection_policy.lag_buildup_max_offset_progress if anomaly_detection_policy else _LAG_BUILDUP_MAX_OFFSET_PROGRESS
        ```
        Replace the three module-constant references (`_LAG_BUILDUP_MIN_LAG`, `_LAG_BUILDUP_MIN_GROWTH`,
        `_LAG_BUILDUP_MAX_OFFSET_PROGRESS`) with the resolved locals.
  - [x] Update `_detect_throughput_constrained_proxy(scope, scope_metrics)` signature to add
        `anomaly_detection_policy: AnomalyDetectionPolicyV1 | None = None`. Resolve three locals:
        ```python
        min_messages_per_sec = anomaly_detection_policy.throughput_min_messages_per_sec if anomaly_detection_policy else _THROUGHPUT_MIN_MESSAGES_PER_SEC
        min_total_produce_per_sec = anomaly_detection_policy.throughput_min_total_produce_requests_per_sec if anomaly_detection_policy else _THROUGHPUT_MIN_TOTAL_PRODUCE_REQUESTS_PER_SEC
        failure_ratio_min = anomaly_detection_policy.throughput_failure_ratio_min if anomaly_detection_policy else _THROUGHPUT_FAILURE_RATIO_MIN
        ```
        Replace the three module-constant references.
  - [x] Update `_detect_volume_drop(scope, scope_metrics, *, baseline_messages_in=None)` signature to add
        `anomaly_detection_policy: AnomalyDetectionPolicyV1 | None = None`. Resolve three locals:
        ```python
        max_current_messages_in = anomaly_detection_policy.volume_drop_max_current_messages_in_per_sec if anomaly_detection_policy else _VOLUME_DROP_MAX_CURRENT_MESSAGES_IN_PER_SEC
        min_baseline_messages_in = anomaly_detection_policy.volume_drop_min_baseline_messages_in_per_sec if anomaly_detection_policy else _VOLUME_DROP_MIN_BASELINE_MESSAGES_IN_PER_SEC
        min_expected_requests = anomaly_detection_policy.volume_drop_min_expected_requests_per_sec if anomaly_detection_policy else _VOLUME_DROP_MIN_EXPECTED_REQUESTS_PER_SEC
        ```
        Replace the three module-constant references.
  - [x] **Do NOT remove** the nine module-level constants (`_LAG_BUILDUP_MIN_LAG`, etc.) — they remain
        as documented defaults and are used when `anomaly_detection_policy is None`.

- [x] Task 2: Thread `anomaly_detection_policy` through the evidence pipeline (AC: 1)
  - [x] In `src/aiops_triage_pipeline/pipeline/stages/evidence.py`, add
        `from aiops_triage_pipeline.contracts.anomaly_detection_policy import AnomalyDetectionPolicyV1`
        import (place with the other `contracts.*` imports).
  - [x] Add `anomaly_detection_policy: AnomalyDetectionPolicyV1 | None = None` keyword-only parameter
        to `collect_evidence_stage_output()` (after `max_safe_action`).
  - [x] In the `detect_anomaly_findings(rows, ...)` call inside `collect_evidence_stage_output()`,
        pass `anomaly_detection_policy=anomaly_detection_policy`.
  - [x] In `src/aiops_triage_pipeline/pipeline/scheduler.py`, add
        `from aiops_triage_pipeline.contracts.anomaly_detection_policy import AnomalyDetectionPolicyV1`
        import (place with the other `contracts.*` imports).
  - [x] Add `anomaly_detection_policy: AnomalyDetectionPolicyV1 | None = None` keyword-only parameter
        to `run_evidence_stage_cycle()`.
  - [x] In the `collect_evidence_stage_output(...)` call inside `run_evidence_stage_cycle()`,
        pass `anomaly_detection_policy=anomaly_detection_policy`.
  - [x] In `src/aiops_triage_pipeline/__main__.py`, update the `run_evidence_stage_cycle(...)` call
        at line ~616 to add `anomaly_detection_policy=anomaly_detection_policy`. The `anomaly_detection_policy`
        variable is already in scope (loaded at line ~323 in the startup block and passed to
        `_hot_path_scheduler_loop()` as a parameter).

- [x] Task 3: Add `topology_registry_version` to casefile policy stamps (AC: 2)
  - [x] In `src/aiops_triage_pipeline/models/case_file.py`, add
        `topology_registry_version: str = Field(default="2", min_length=1)` to `CaseFilePolicyVersions`
        immediately after `anomaly_detection_policy_version` (line ~31).
  - [x] In `src/aiops_triage_pipeline/pipeline/stages/casefile.py`, add
        `topology_registry_version: str = "2"` as a keyword-only parameter to
        `assemble_casefile_triage_stage()` (after `anomaly_detection_policy_version`).
  - [x] In `assemble_casefile_triage_stage()`, add validation guard immediately after the existing
        `anomaly_detection_policy_version` guard:
        ```python
        if not topology_registry_version.strip():
            raise ValueError("topology_registry_version must not be empty")
        ```
  - [x] In the `CaseFilePolicyVersions(...)` construction inside `assemble_casefile_triage_stage()`
        (line ~103), add `topology_registry_version=topology_registry_version`.
  - [x] In `src/aiops_triage_pipeline/__main__.py`, update the `assemble_casefile_triage_stage(...)`
        call at line ~745 to add
        `topology_registry_version=str(snapshot.metadata.input_version)`.
        The `snapshot` variable is already in scope (set at line ~614: `snapshot = topology_loader.get_snapshot()`).

- [x] Task 4: Write unit tests (AC: 1, 2)
  - [x] In `tests/unit/pipeline/stages/test_anomaly.py`, add two tests:
    - `test_detect_anomaly_findings_uses_policy_lag_threshold`: Construct
      `AnomalyDetectionPolicyV1(lag_buildup_min_lag=999999.0)` (impossibly high threshold).
      Create four `EvidenceRow` objects with `scope=("prod", "cluster-a", "group-a", "topic-a")`:
      lag rows `[150.0, 200.0]` and offset rows `[100.0, 105.0]` — which trigger detection with
      default thresholds (`lag_end=200 >= 100`, `lag_growth=50 >= 25`, `offset_progress=5 <= 10`).
      Call `detect_anomaly_findings(rows, anomaly_detection_policy=policy)`. Assert that
      `result.findings` is empty (the custom threshold of 999999 prevents detection). This proves
      the policy threshold overrides the module constant.
    - `test_detect_anomaly_findings_none_policy_uses_module_constants`: Use the same evidence rows
      as above, call `detect_anomaly_findings(rows, anomaly_detection_policy=None)`. Assert that
      one `CONSUMER_LAG` finding is returned (module-constant thresholds fire normally).
  - [x] In `tests/unit/pipeline/stages/test_evidence.py`, add one test:
    - `test_collect_evidence_stage_output_passes_anomaly_policy_to_detector`: Using `monkeypatch`
      (or `unittest.mock.patch`), replace `detect_anomaly_findings` in
      `aiops_triage_pipeline.pipeline.stages.evidence` with a `MagicMock` returning a valid
      `AnomalyDetectionResult(findings=())`. Call `collect_evidence_stage_output({}, anomaly_detection_policy=policy)`
      where `policy = AnomalyDetectionPolicyV1()`. Assert the mock was called with
      `anomaly_detection_policy=policy` as a keyword argument.
  - [x] In `tests/unit/pipeline/stages/test_casefile.py`, add one test and update one existing:
    - `test_assemble_casefile_stamps_topology_registry_version`: Call
      `assemble_casefile_triage_stage(...)` with `topology_registry_version="3"`. Assert
      `assembled.policy_versions.topology_registry_version == "3"`. This proves the parameter
      flows through to the stamped casefile.
    - Update `test_assemble_casefile_triage_stage_policy_versions_all_five_fields_non_empty` →
      rename to `test_assemble_casefile_triage_stage_policy_versions_all_six_fields_non_empty`.
      Add `"topology_registry_version"` to the tuple of field names being asserted (line ~1241).
      The updated test calls `assemble_casefile_triage_stage(...)` without `topology_registry_version`
      (it will use the default `"2"`) and then checks all six fields.
  - [x] In `tests/unit/storage/test_casefile_io.py`, add two tests after the existing
        `test_casefile_policy_versions_anomaly_detection_policy_version_rejects_empty`:
    - `test_casefile_policy_versions_topology_registry_version_field_present`: Construct
      `CaseFilePolicyVersions(topology_registry_version="2", ...)` and assert
      `pv.topology_registry_version == "2"`.
    - `test_casefile_policy_versions_topology_registry_version_rejects_empty`: Assert
      `ValidationError` when `topology_registry_version=""`.

- [x] Task 5: Run full regression (AC: 1, 2)
  - [x] `uv run ruff check`
  - [x] `uv run pytest -q tests/unit`
  - [x] `TESTCONTAINERS_RYUK_DISABLED=true DOCKER_HOST=unix://$HOME/.docker/desktop/docker.sock uv run pytest -q -rs`

## Dev Notes

### What Already Exists — Do NOT Reimplement

**Policy loading at startup is fully implemented (Stories 5.1 and 5.2):**
- All nine policies are loaded in `__main__.py` hot-path startup block (lines ~321–343).
- `anomaly_detection_policy` (`AnomalyDetectionPolicyV1`) is already loaded and passed to
  `_hot_path_scheduler_loop()` (line ~395), and its `schema_version` is already stamped in
  `CaseFilePolicyVersions.anomaly_detection_policy_version` (line ~757).
- Topology registry hot-reload: `topology_loader.reload_if_changed()` is already called at the
  top of each cycle (line ~613). Changing `config/topology-registry.yaml` and redeploying
  automatically picks up the new registry — no code change needed for this.
- Denylist reload: the denylist is loaded once at startup. Its version (`denylist_version` from the
  YAML) is already stamped as `exposure_denylist_version` in `CaseFilePolicyVersions`.
- Rulebook, peak policy, Redis TTL policy: all loaded and version-stamped. Changing these YAMLs
  and redeploying changes pipeline behavior — no code change needed.
- `startup_policies_loaded` structured log event (line ~334–342) already captures active policy
  versions at boot.

**The two gaps Story 5.3 closes:**
1. `detect_anomaly_findings()` uses nine module-level float constants (`_LAG_BUILDUP_MIN_LAG`, etc.)
   instead of the loaded `AnomalyDetectionPolicyV1` thresholds. Operators editing
   `config/policies/anomaly-detection-policy-v1.yaml` and redeploying currently have NO effect on
   detection behavior — the module constants are hard-coded. This is the FR52 gap.
2. `CaseFilePolicyVersions` does not stamp the topology registry version. Without it, a casefile
   cannot declare which topology version governed the routing/blast-radius context used when a
   decision was made. This is the FR53 audit gap.

### Anomaly Detector Threshold Wiring — Precise Change Description

**Current call chain:**
```
__main__._hot_path_scheduler_loop()
  └── run_evidence_stage_cycle()  [scheduler.py, line ~616]
        └── collect_evidence_stage_output()  [stages/evidence.py, line ~219]
              └── detect_anomaly_findings()  [stages/anomaly.py, line ~161]
                    └── _compute_scope_findings()
                          ├── _detect_consumer_lag_buildup()        ← uses _LAG_BUILDUP_MIN_LAG
                          ├── _detect_throughput_constrained_proxy()  ← uses _THROUGHPUT_*
                          └── _detect_volume_drop()                  ← uses _VOLUME_DROP_*
```

**After Story 5.3:** `anomaly_detection_policy` propagates down this chain. Each private
`_detect_*` function resolves its thresholds from the policy when provided, or falls back to the
module constant when `None`. **All new parameters are optional with `None` default** — backward
compatibility with all existing callers is preserved.

**The nine threshold mappings** (policy field → module constant):
| `detect_anomaly_findings` caller arg | Policy field | Module constant |
|---|---|---|
| `anomaly_detection_policy.lag_buildup_min_lag` | `lag_buildup_min_lag` | `_LAG_BUILDUP_MIN_LAG` (100.0) |
| `anomaly_detection_policy.lag_buildup_min_growth` | `lag_buildup_min_growth` | `_LAG_BUILDUP_MIN_GROWTH` (25.0) |
| `anomaly_detection_policy.lag_buildup_max_offset_progress` | `lag_buildup_max_offset_progress` | `_LAG_BUILDUP_MAX_OFFSET_PROGRESS` (10.0) |
| `anomaly_detection_policy.throughput_min_messages_per_sec` | `throughput_min_messages_per_sec` | `_THROUGHPUT_MIN_MESSAGES_PER_SEC` (1000.0) |
| `anomaly_detection_policy.throughput_min_total_produce_requests_per_sec` | `throughput_min_total_produce_requests_per_sec` | `_THROUGHPUT_MIN_TOTAL_PRODUCE_REQUESTS_PER_SEC` (100.0) |
| `anomaly_detection_policy.throughput_failure_ratio_min` | `throughput_failure_ratio_min` | `_THROUGHPUT_FAILURE_RATIO_MIN` (0.05) |
| `anomaly_detection_policy.volume_drop_max_current_messages_in_per_sec` | `volume_drop_max_current_messages_in_per_sec` | `_VOLUME_DROP_MAX_CURRENT_MESSAGES_IN_PER_SEC` (1.0) |
| `anomaly_detection_policy.volume_drop_min_baseline_messages_in_per_sec` | `volume_drop_min_baseline_messages_in_per_sec` | `_VOLUME_DROP_MIN_BASELINE_MESSAGES_IN_PER_SEC` (50.0) |
| `anomaly_detection_policy.volume_drop_min_expected_requests_per_sec` | `volume_drop_min_expected_requests_per_sec` | `_VOLUME_DROP_MIN_EXPECTED_REQUESTS_PER_SEC` (150.0) |

### Topology Registry Version — Precise Change Description

`TopologyRegistryLoader.get_snapshot()` returns a `TopologyRegistrySnapshot` with
`metadata: TopologyRegistryMetadata`. The metadata has `input_version: int` which is read from
the `version:` field at the top of `config/topology-registry.yaml` (currently `version: 2`).

The `snapshot` variable is already in scope at the `assemble_casefile_triage_stage()` call site
(line ~614: `snapshot = topology_loader.get_snapshot()`). Pass
`topology_registry_version=str(snapshot.metadata.input_version)`.

`CaseFilePolicyVersions.topology_registry_version` stores the string representation of the
registry version integer. The field default `"2"` matches the current topology registry YAML value.
Adding a new field with a default means all existing code constructing `CaseFilePolicyVersions`
without this field will continue to work (Pydantic uses the default).

**NFR-A3 compatibility**: Adding a new field with a default to `CaseFilePolicyVersions` means old
casefiles persisted before this story (which lack the field in JSON) will deserialize correctly —
Pydantic v2 uses the field default for missing keys. No migration needed.

### Technical Requirements

- FR52: Wire `AnomalyDetectionPolicyV1` thresholds into the anomaly detector so that editing
  `config/policies/anomaly-detection-policy-v1.yaml` and redeploying changes detection behavior.
- FR53: Stamp `topology_registry_version` in `CaseFilePolicyVersions` so that every casefile
  declares which topology registry version governed its routing decisions — enabling audit replay.
- NFR-A2: Every casefile now stamps 7 policy version fields: `rulebook_version`,
  `peak_policy_version`, `prometheus_metrics_contract_version`, `exposure_denylist_version`,
  `diagnosis_policy_version`, `anomaly_detection_policy_version`, `topology_registry_version`.
- NFR-A3: New field with default preserves backward-compatible deserialization of old casefiles.

### Architecture Compliance

- **Composition root**: All wiring changes propagate from `__main__.py` (top) down. No new
  module-level singletons or imports of policy objects outside of the affected modules.
- **D4 (Rule engine isolation)**: `stages/anomaly.py` imports `AnomalyDetectionPolicyV1` from
  `contracts/` only. No pipeline imports enter the detector. ✓
- **Package dependency rules**: The direction is `contracts/ → external` only. `stages/anomaly.py`,
  `stages/evidence.py`, `pipeline/scheduler.py` importing from `contracts/` is the established
  and correct pattern (matches all other policy contract imports in those files).
- **Single flat `Settings` class**: No new settings fields. The policy threshold values are loaded
  from YAML policy files, not from environment variables.
- **Do NOT refactor** `validate_kerberos_files`, `validate_llm_prod_mode`, or any other
  existing validator — only the described changes.
- **Do NOT wire** any policy into the cold-path consumer (diagnosis) — this story is hot-path only.

### Library / Framework Requirements

- Locked stack (do not change):
  - Python `>=3.13` — use `X | None` union syntax (not `Optional[X]`)
  - `pydantic==2.12.5` — `Field(default="2", min_length=1)` for the new model field
  - `pydantic-settings~=2.13.1`
  - `pytest==9.0.2`

### File Structure Requirements

**Modified files:**
- `src/aiops_triage_pipeline/pipeline/stages/anomaly.py` — add policy param + threshold resolution
- `src/aiops_triage_pipeline/pipeline/stages/evidence.py` — import + pass policy through
- `src/aiops_triage_pipeline/pipeline/scheduler.py` — import + pass policy through
- `src/aiops_triage_pipeline/__main__.py` — pass policy to evidence cycle; pass topology version to casefile assembly
- `src/aiops_triage_pipeline/models/case_file.py` — add `topology_registry_version` field
- `src/aiops_triage_pipeline/pipeline/stages/casefile.py` — add `topology_registry_version` param + validation + CaseFilePolicyVersions construction
- `tests/unit/pipeline/stages/test_anomaly.py` — add 2 tests
- `tests/unit/pipeline/stages/test_evidence.py` — add 1 test
- `tests/unit/pipeline/stages/test_casefile.py` — add 1 test, rename+update 1 existing test
- `tests/unit/storage/test_casefile_io.py` — add 2 tests

**Do NOT modify:**
- `src/aiops_triage_pipeline/config/settings.py` — no new fields needed
- `src/aiops_triage_pipeline/__main__.py` startup block — policy loading is unchanged; only add
  `anomaly_detection_policy=anomaly_detection_policy` to `run_evidence_stage_cycle()` call, and
  `topology_registry_version=str(snapshot.metadata.input_version)` to `assemble_casefile_triage_stage()` call
- `src/aiops_triage_pipeline/pipeline/stages/casefile.py` beyond the described changes
- `tests/unit/test_main.py` — `_hot_path_scheduler_loop()` tests mock `run_evidence_stage_cycle`
  and raise `CancelledError` at `topology_loader.reload_if_changed()` before the casefile path,
  so no changes are needed
- `tests/unit/pipeline/test_scheduler.py` — `run_evidence_stage_cycle()` tests pass no
  `anomaly_detection_policy` (defaults to `None`); existing tests remain valid unchanged
- Any integration test files — no cold-path or integration changes in this story

### Testing Requirements

- **Unit test for threshold wiring** (most important):
  ```python
  def test_detect_anomaly_findings_uses_policy_lag_threshold() -> None:
      from aiops_triage_pipeline.contracts.anomaly_detection_policy import AnomalyDetectionPolicyV1
      from aiops_triage_pipeline.models.evidence import EvidenceRow
      from aiops_triage_pipeline.pipeline.stages.anomaly import detect_anomaly_findings

      _SCOPE = ("prod", "cluster-a", "group-a", "topic-a")
      rows = [
          EvidenceRow(metric_key="consumer_group_lag", value=150.0, labels={}, scope=_SCOPE),
          EvidenceRow(metric_key="consumer_group_lag", value=200.0, labels={}, scope=_SCOPE),
          EvidenceRow(metric_key="consumer_group_offset", value=100.0, labels={}, scope=_SCOPE),
          EvidenceRow(metric_key="consumer_group_offset", value=105.0, labels={}, scope=_SCOPE),
      ]
      # These rows trigger CONSUMER_LAG with default thresholds:
      # lag_end=200 >= 100, lag_growth=50 >= 25, offset_progress=5 <= 10

      # Policy with impossibly high threshold — no finding should be produced.
      policy = AnomalyDetectionPolicyV1(lag_buildup_min_lag=999999.0)
      result = detect_anomaly_findings(rows, anomaly_detection_policy=policy)

      assert result.findings == (), "Policy lag_buildup_min_lag=999999 must suppress CONSUMER_LAG"
  ```
- **Existing `test_scheduler.py` tests**: All call `run_evidence_stage_cycle()` without
  `anomaly_detection_policy` — the new optional parameter (default `None`) means these tests
  remain valid and require no changes.
- **No pytest.skip anywhere** — use `pytest.fail` if unexpected behavior is encountered.
- **Per-file test doubles**: Any fake Redis, fake object store, or fake prometheus client in new
  tests must be defined in the same test file, not shared fixtures.
- **Preferred regression command:**
  ```
  TESTCONTAINERS_RYUK_DISABLED=true DOCKER_HOST=unix://$HOME/.docker/desktop/docker.sock uv run pytest -q -rs
  ```

### Previous Story Intelligence

**From Story 5.2 (done — prod integration guardrails):**
- Full regression: 1042 unit tests pass, 0 skipped, after code review fixes. Unit test count is
  the baseline for this story's delta.
- File list in Dev Agent Record must include ALL changed files including `sprint-status.yaml`.
- No `pytest.skip` anywhere — use `pytest.fail`.
- `uv run ruff check` must run clean before claiming done.
- `get_settings.cache_clear()` in any test that instantiates `Settings` directly.

**From Story 5.1 (done — policy startup loading):**
- Story 5.1 explicitly deferred threshold wiring: "Do NOT wire policy thresholds into the anomaly
  detector in this story. The existing module-level constants in `stages/anomaly.py` remain
  unchanged. Threshold wiring is Story 5.3 (FR52)."
- `anomaly_detection_policy` is already loaded in `__main__.py` and passed to
  `_hot_path_scheduler_loop()` — no new loading code needed in Story 5.3.
- The `AnomalyDetectionPolicyV1` contract and YAML are complete; no schema changes needed.
- `contracts/__init__.py` already exports `AnomalyDetectionPolicyV1`.

### Git Intelligence Summary

Recent commits (most relevant to this story):
- `0df61f4`: fix(epic-5/5-2): resolve code review findings — prod integration guardrails complete
- `0c0dd45`: feat(epic-5/5-2): story dev done — 1042 unit tests after review
- `c9dc3b1`: bmad(epic-5/5-1): mark story done — 1027 unit tests
- `3eaf9e3`: bmad(epic-5/5-1): dev done — anomaly policy loaded, NOT yet wired to detector

The anomaly module-level constants have been stable since Epic 1. No other Epic 5 story touches
`stages/anomaly.py`, `stages/evidence.py`, or `pipeline/scheduler.py`. All three files are
cleanly separable from the settings-layer changes made in Stories 5.1 and 5.2.

### Latest Tech Information

External verification date: 2026-03-23.

- `pydantic==2.12.5`: `Field(default="2", min_length=1)` — `Field` with both `default` and
  `min_length` is standard v2 usage (same pattern as all other `CaseFilePolicyVersions` fields
  except `anomaly_detection_policy_version` which also uses `Field(default="v1", min_length=1)`).
- Python 3.13: `X | None` is the preferred union syntax over `Optional[X]`. Use throughout.
- `pytest==9.0.2`: No mock library changes. `unittest.mock.patch` (or `monkeypatch.setattr`) for
  patching `detect_anomaly_findings` in the evidence test.

### Project Context Reference

Applied `archive/project-context.md` and implementation patterns:
- Python 3.13 typing — `X | None`, no `Optional`.
- No DI container — `anomaly_detection_policy` propagates as function parameters through the
  call chain; it is NOT stored as a module-level singleton anywhere.
- Single flat `Settings` class — no new env vars added (policy thresholds live in YAML policy).
- Feature flags follow `FEATURE_ENABLED: bool = False` — not applicable; no flag needed since the
  policy is always loaded and all parameters are optional with backward-compatible defaults.
- Zero skipped tests required for full regression gate.

### References

- [Source: `artifact/planning-artifacts/epics.md` — Epic 5 / Story 5.3]
- [Source: `artifact/planning-artifacts/prd/functional-requirements.md` — FR52, FR53]
- [Source: `artifact/planning-artifacts/prd/non-functional-requirements.md` — NFR-A2, NFR-A3]
- [Source: `artifact/planning-artifacts/architecture/implementation-patterns-consistency-rules.md`
  — Configuration Variables, Enforcement Guidelines, Dependency Injection]
- [Source: `artifact/planning-artifacts/architecture/core-architectural-decisions.md`
  — D4 (rule engine isolation), Standing Architectural Principle]
- [Source: `src/aiops_triage_pipeline/pipeline/stages/anomaly.py`
  — Nine module-level constants (lines 22–30), `detect_anomaly_findings()` (line 33),
  `_compute_scope_findings()` (line 95), three private `_detect_*` functions (lines 135, 188, 227)]
- [Source: `src/aiops_triage_pipeline/pipeline/stages/evidence.py`
  — `collect_evidence_stage_output()` (line 140), `detect_anomaly_findings()` call (line 161)]
- [Source: `src/aiops_triage_pipeline/pipeline/scheduler.py`
  — `run_evidence_stage_cycle()` (line 151), `collect_evidence_stage_output()` call (line 219)]
- [Source: `src/aiops_triage_pipeline/__main__.py`
  — `run_evidence_stage_cycle()` call (line ~616), `assemble_casefile_triage_stage()` call (line ~745),
  `snapshot = topology_loader.get_snapshot()` (line ~614)]
- [Source: `src/aiops_triage_pipeline/models/case_file.py`
  — `CaseFilePolicyVersions` (line 23), `anomaly_detection_policy_version` field (line 31)]
- [Source: `src/aiops_triage_pipeline/pipeline/stages/casefile.py`
  — `assemble_casefile_triage_stage()` signature (lines 58–74),
  `CaseFilePolicyVersions(...)` construction (lines 103–110)]
- [Source: `src/aiops_triage_pipeline/registry/loader.py`
  — `TopologyRegistrySnapshot` (line 327), `TopologyRegistryMetadata.input_version` (line 321)]
- [Source: `src/aiops_triage_pipeline/contracts/anomaly_detection_policy.py`
  — `AnomalyDetectionPolicyV1` field names (lines 12–20)]
- [Source: `artifact/implementation-artifacts/5-1-load-and-validate-policies-at-startup.md`
  — "threshold wiring is Story 5.3 (FR52)" deferral note in Dev Notes]
- [Source: `tests/unit/pipeline/stages/test_anomaly.py`
  — existing test patterns (per-file, no shared fixtures)]
- [Source: `tests/unit/pipeline/stages/test_casefile.py`
  — `test_assemble_casefile_triage_stage_policy_versions_all_five_fields_non_empty` (line 1211)]
- [Source: `tests/unit/storage/test_casefile_io.py`
  — `test_casefile_policy_versions_anomaly_detection_policy_version_field_present` (line 669)]

## Dev Agent Record

### Agent Model Used

claude-sonnet-4-6

### Debug Log References

- create-story workflow for story key `5-3-enable-operator-and-maintainer-policy-tuning-workflows`
- sprint-status.yaml: story 5-3 status=backlog confirmed; epic-5 already in-progress
- epics.md (line 704): Story 5.3 full AC text and FR52/FR53 mapping
- prd/functional-requirements.md: FR52 (anomaly sensitivity tuning), FR53 (topology+denylist YAML promotion)
- prd/non-functional-requirements.md: NFR-A2 (casefile policy stamps), NFR-A3 (schema backward compat)
- architecture/implementation-patterns-consistency-rules.md: dependency injection rules, config variable pattern
- architecture/core-architectural-decisions.md: D4 isolation, D6 cold-path architecture (not touched)
- source analysis: stages/anomaly.py (nine constants lines 22-30, detect_anomaly_findings line 33, four private functions), stages/evidence.py (collect_evidence_stage_output line 140, detect_anomaly_findings call line 161), scheduler.py (run_evidence_stage_cycle line 151), __main__.py (evidence cycle call ~616, snapshot ~614, assemble call ~745)
- models/case_file.py: CaseFilePolicyVersions (line 23) — confirmed no topology_registry_version field
- registry/loader.py: TopologyRegistryMetadata.input_version (line 321) — source for topology version
- previous story analysis: 5-1 (deferral note confirmed), 5-2 (1042 unit test baseline confirmed)
- git log: no anomaly/evidence/scheduler changes since Epic 1; clean surface for Story 5.3
- test analysis: test_anomaly.py patterns, test_casefile.py "all_five_fields" test at line 1211, test_casefile_io.py anomaly_detection_policy_version pattern at line 669, test_main.py confirms CancelledError before casefile path (no test_main.py changes needed)

### Completion Notes List

- FR52 (anomaly threshold wiring): Added `anomaly_detection_policy: AnomalyDetectionPolicyV1 | None = None` parameter to `detect_anomaly_findings()`, `_compute_scope_findings()`, and all three private `_detect_*` functions in `stages/anomaly.py`. Each detector resolves thresholds from the policy when provided, falling back to module constants when `None`. The nine module-level constants are preserved as defaults. The parameter propagates from `__main__._hot_path_scheduler_loop()` → `run_evidence_stage_cycle()` → `collect_evidence_stage_output()` → `detect_anomaly_findings()` → private detectors.
- FR53 (topology registry version stamp): Added `topology_registry_version: str = Field(default="2", min_length=1)` to `CaseFilePolicyVersions`. Added matching parameter to `assemble_casefile_triage_stage()` with empty-string guard. Updated `__main__.py` to pass `topology_registry_version=str(snapshot.metadata.input_version)`.
- All ACs satisfied: editing anomaly YAML + redeploy now changes detection behavior; every casefile stamps topology registry version for audit replay.
- Tests: 6 new unit tests added. Full regression: 1144 passed, 0 skipped (baseline was 1042 unit / ~1144 full-suite).
- Ruff check clean on all modified files (pre-existing E501 in atdd file not introduced by this story).

### File List

- `src/aiops_triage_pipeline/pipeline/stages/anomaly.py`
- `src/aiops_triage_pipeline/pipeline/stages/evidence.py`
- `src/aiops_triage_pipeline/pipeline/scheduler.py`
- `src/aiops_triage_pipeline/__main__.py`
- `src/aiops_triage_pipeline/models/case_file.py`
- `src/aiops_triage_pipeline/pipeline/stages/casefile.py`
- `tests/unit/pipeline/stages/test_anomaly.py`
- `tests/unit/pipeline/stages/test_evidence.py`
- `tests/unit/pipeline/stages/test_casefile.py`
- `tests/unit/storage/test_casefile_io.py`
- `artifact/implementation-artifacts/5-3-enable-operator-and-maintainer-policy-tuning-workflows.md`
- `artifact/implementation-artifacts/sprint-status.yaml`

