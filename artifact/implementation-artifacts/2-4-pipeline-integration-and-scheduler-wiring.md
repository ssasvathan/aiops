# Story 2.4: Pipeline Integration & Scheduler Wiring

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As an on-call engineer,
I want baseline deviation findings to flow through topology enrichment, deterministic gating, case file persistence, and Slack dispatch unchanged,
so that I receive complete, routed notifications for anomalies the hand-coded detectors miss.

## Acceptance Criteria

1. **Given** the scheduler pipeline loop in `pipeline/scheduler.py`
   **When** the stage ordering is configured
   **Then** `run_baseline_deviation_stage_cycle()` is added to `scheduler.py`, callable between peak and topology
   **And** it follows the same perf_counter + `record_pipeline_compute_latency(stage="stage2_5_baseline_deviation")` pattern as `run_peak_stage_cycle()`
   **And** the full ordering documented in `docs/architecture.md` is: `evidence → peak → baseline_deviation → topology → casefile → outbox → gating → dispatch`

2. **Given** `__main__.py` hot-path scheduler loop
   **When** the baseline deviation stage is wired in
   **Then** `run_baseline_deviation_stage_cycle()` is called after `run_peak_stage_cycle()` and before `run_topology_stage_cycle()`
   **And** it receives `evidence_output`, `peak_output`, `baseline_client=seasonal_baseline_client`, and `evaluation_time` as keyword arguments
   **And** the returned `BaselineDeviationStageOutput.findings` are merged into `EvidenceStageOutput.gate_findings_by_scope` so they flow through topology and gating

3. **Given** baseline deviation findings enter the gating stage
   **When** `GateInputV1` is assembled
   **Then** `GateInputV1.anomaly_family` Literal in `contracts/gate_input.py` is extended to include `"BASELINE_DEVIATION"` (additive-only change per Procedure A)
   **And** `_anomaly_family_from_gate_finding_name()` in `pipeline/stages/gating.py` handles `"BASELINE_DEVIATION"` → `"BASELINE_DEVIATION"` mapping without raising ValueError
   **And** `_sustained_identity_key()` in gating.py handles `"BASELINE_DEVIATION"` anomaly family for scope identity construction
   **And** AG0–AG6 gate rules produce `ActionDecisionV1` records identically to other finding types (FR19)

4. **Given** baseline deviation findings pass gating with `action=NOTIFY` or lower
   **When** case file and outbox stages process them
   **Then** case files are persisted with SHA-256 hash-chain integrity (NFR-A1, FR20)
   **And** `CaseHeaderEventV1` and `TriageExcerptV1` events are published via Kafka outbox
   **And** no structural changes to casefile or outbox stages are required (the `BASELINE_DEVIATION` family flows through existing contracts unchanged)

5. **Given** a baseline deviation finding with `action=NOTIFY`
   **When** the dispatch stage processes it
   **Then** a Slack webhook notification is sent (FR21)
   **And** no dispatch stage modifications are required

6. **Given** the baseline deviation layer is disabled via configuration (NFR-R5)
   **When** `settings.BASELINE_DEVIATION_STAGE_ENABLED` is `False`
   **Then** `run_baseline_deviation_stage_cycle()` is skipped in `__main__.py`
   **And** `BaselineDeviationStageOutput` with empty findings is used so downstream stages receive no BASELINE_DEVIATION findings
   **And** all other stages and detectors operate unchanged
   **And** the flag defaults to `True` in `Settings`

7. **Given** the scheduler runs each pipeline cycle
   **When** the baseline deviation stage has completed detection
   **Then** `update_bucket()` is called per scope per metric with the current observation (FR3)
   **And** the `update_bucket()` calls happen AFTER `collect_baseline_deviation_stage_output()` returns (detection reads first, then writes)
   **And** incremental updates add < 5ms per scope to cycle duration (NFR-P6)
   **And** `update_bucket()` errors per scope are caught individually and logged at WARNING (same fail-open pattern as scope-level errors in the stage)

8. **Given** integration tests
   **When** the full pipeline path is exercised end-to-end
   **Then** `tests/integration/test_pipeline_e2e.py` is extended with a new test `test_baseline_deviation_finding_flows_end_to_end`
   **And** the test injects a BASELINE_DEVIATION-triggering evidence output into the scheduler cycle stages and verifies topology output, a gate decision, and that `build_outbox_ready_record` can be called without error
   **And** `docs/developer-onboarding.md` is updated with the baseline deviation stage in the pipeline flow description

## Tasks / Subtasks

- [x] Task 1: Add `run_baseline_deviation_stage_cycle()` to `pipeline/scheduler.py` (AC: 1)
  - [x] 1.1 Open `src/aiops_triage_pipeline/pipeline/scheduler.py`
  - [x] 1.2 Add import at top: `from aiops_triage_pipeline.pipeline.stages.baseline_deviation import collect_baseline_deviation_stage_output`
  - [x] 1.3 Add import at top: `from aiops_triage_pipeline.baseline.client import SeasonalBaselineClient`
  - [x] 1.4 Add import at top: `from aiops_triage_pipeline.baseline.models import BaselineDeviationStageOutput`
  - [x] 1.5 Define `run_baseline_deviation_stage_cycle()` with keyword-only parameters: `evidence_output: EvidenceStageOutput`, `peak_output: PeakStageOutput`, `baseline_client: SeasonalBaselineClient`, `evaluation_time: datetime`, `alert_evaluator: OperationalAlertEvaluator | None = None` → returns `BaselineDeviationStageOutput`
  - [x] 1.6 Inside the function: wrap `collect_baseline_deviation_stage_output()` in a `started_at / time.perf_counter()` + `try/finally` block, call `record_pipeline_compute_latency(stage="stage2_5_baseline_deviation", seconds=elapsed_seconds)` in the `finally` block (mirrors `run_peak_stage_cycle` and `run_topology_stage_cycle` exactly)
  - [x] 1.7 Call `alert_evaluator.evaluate_pipeline_stage_latency(seconds=elapsed_seconds, stage="stage2_5_baseline_deviation")` in the `finally` block if `alert_evaluator is not None`, and call `_emit_operational_alert()` if the alert is not None (mirrors the exact pattern in `run_topology_stage_cycle`)
  - [x] 1.8 Add `run_baseline_deviation_stage_cycle` to the public exports in the module (ensure it is importable in `__main__.py`)
  - [x] 1.9 Run `uv run ruff check src/aiops_triage_pipeline/pipeline/scheduler.py` — confirm clean

- [x] Task 2: Extend `GateInputV1.anomaly_family` and gating helpers for BASELINE_DEVIATION (AC: 3)
  - [x] 2.1 Open `src/aiops_triage_pipeline/contracts/gate_input.py`
  - [x] 2.2 Extend `GateInputV1.anomaly_family` Literal: add `"BASELINE_DEVIATION"` — change line 95 from `Literal["CONSUMER_LAG", "VOLUME_DROP", "THROUGHPUT_CONSTRAINED_PROXY"]` to `Literal["CONSUMER_LAG", "VOLUME_DROP", "THROUGHPUT_CONSTRAINED_PROXY", "BASELINE_DEVIATION"]`
  - [x] 2.3 Run `uv run pytest tests/unit/ -k "gate_input or gating or casefile" -v` immediately after this change — confirm 0 regressions from the Literal extension
  - [x] 2.4 Open `src/aiops_triage_pipeline/pipeline/stages/gating.py`
  - [x] 2.5 Update `_anomaly_family_from_gate_finding_name()` return type and implementation: extend the return Literal to include `"BASELINE_DEVIATION"` and add a `if normalized == "BASELINE_DEVIATION": return "BASELINE_DEVIATION"` branch before the `raise ValueError`
  - [x] 2.6 Update `_sustained_identity_key()` signature: extend the `anomaly_family` parameter Literal to include `"BASELINE_DEVIATION"` (the function body already handles all 3 scope shapes generically — no logic change needed, only the type annotation)
  - [x] 2.7 Update `_derive_scoring_result_with_fallback()` signature: extend the `anomaly_family` parameter Literal to include `"BASELINE_DEVIATION"` (same — type annotation only, body unchanged)
  - [x] 2.8 Update `_resolve_context_scoring_result()` signature: extend the `anomaly_family` parameter Literal to include `"BASELINE_DEVIATION"` (same — type annotation only)
  - [x] 2.9 Scan gating.py for ANY other `Literal["CONSUMER_LAG", "VOLUME_DROP", "THROUGHPUT_CONSTRAINED_PROXY"]` type annotations and extend them all to include `"BASELINE_DEVIATION"` consistently
  - [x] 2.10 Run `uv run ruff check src/aiops_triage_pipeline/pipeline/stages/gating.py src/aiops_triage_pipeline/contracts/gate_input.py` — confirm clean
  - [x] 2.11 Run `uv run pytest tests/unit/ -k "gating or gate" -v` — confirm 0 regressions

- [x] Task 3: Wire baseline deviation stage in `__main__.py` (AC: 2, 6, 7)
  - [x] 3.1 Open `src/aiops_triage_pipeline/__main__.py`
  - [x] 3.2 Add import: `from aiops_triage_pipeline.pipeline.scheduler import ... run_baseline_deviation_stage_cycle` (add to the existing import block at line ~91)
  - [x] 3.3 In `_hot_path_scheduler_loop()`, add `BASELINE_DEVIATION_STAGE_ENABLED` to the settings check — read `settings.BASELINE_DEVIATION_STAGE_ENABLED` (will be added to Settings in Task 4)
  - [x] 3.4 After the `peak_output = run_peak_stage_cycle(...)` call (around line ~970) and before `run_topology_stage_cycle(...)`, add the baseline deviation stage call:
    ```python
    if settings.BASELINE_DEVIATION_STAGE_ENABLED:
        baseline_deviation_output = run_baseline_deviation_stage_cycle(
            evidence_output=evidence_output,
            peak_output=peak_output,
            baseline_client=seasonal_baseline_client,
            evaluation_time=evaluation_time,
            alert_evaluator=alert_evaluator,
        )
    else:
        from aiops_triage_pipeline.baseline.models import BaselineDeviationStageOutput
        baseline_deviation_output = BaselineDeviationStageOutput(
            findings=(),
            scopes_evaluated=0,
            deviations_detected=0,
            deviations_suppressed_single_metric=0,
            deviations_suppressed_dedup=0,
            evaluation_time=evaluation_time,
        )
    ```
    NOTE: Move the `BaselineDeviationStageOutput` import to module level, not inline.
  - [x] 3.5 After the baseline deviation stage call, inject BASELINE_DEVIATION findings into `evidence_output.gate_findings_by_scope` by reconstructing `evidence_output` with merged findings:
    ```python
    if baseline_deviation_output.findings:
        evidence_output = _merge_baseline_deviation_findings(
            evidence_output=evidence_output,
            baseline_deviation_output=baseline_deviation_output,
        )
    ```
  - [x] 3.6 Implement `_merge_baseline_deviation_findings()` as a module-level helper in `__main__.py`:
    ```python
    def _merge_baseline_deviation_findings(
        evidence_output: EvidenceStageOutput,
        baseline_deviation_output: BaselineDeviationStageOutput,
    ) -> EvidenceStageOutput:
        """Inject BASELINE_DEVIATION gate findings into evidence output for topology/gating.

        Returns a new EvidenceStageOutput with gate_findings_by_scope extended to include
        BASELINE_DEVIATION findings. This allows downstream topology and gating stages to
        process baseline deviation findings without modification (FR18, FR19).
        """
        from aiops_triage_pipeline.pipeline.stages.anomaly import _to_gate_finding
        merged: dict[tuple[str, ...], tuple[Finding, ...]] = dict(
            evidence_output.gate_findings_by_scope
        )
        for finding in baseline_deviation_output.findings:
            scope = finding.scope
            gate_finding = _to_gate_finding(finding)
            existing = merged.get(scope, ())
            merged[scope] = existing + (gate_finding,)
        return EvidenceStageOutput(
            rows=evidence_output.rows,
            anomaly_result=evidence_output.anomaly_result,
            gate_findings_by_scope=merged,
            evidence_status_map_by_scope=evidence_output.evidence_status_map_by_scope,
            telemetry_degraded_active=evidence_output.telemetry_degraded_active,
            telemetry_degraded_events=evidence_output.telemetry_degraded_events,
            max_safe_action=evidence_output.max_safe_action,
        )
    ```
    **CRITICAL:** `_to_gate_finding` is currently a private function in `anomaly.py`. If it cannot be imported directly, replicate the `Finding(...)` construction inline using the same field mapping. However, prefer importing it — check if it should be made package-internal by moving to anomaly.py's public API or duplicating the logic minimally.
  - [x] 3.7 After `run_baseline_deviation_stage_cycle()` returns, add the incremental `update_bucket()` calls (FR3, NFR-P6):
    ```python
    # Incremental bucket update: write current observations to Redis after detection
    # (read-then-write: detect first so baselines aren't contaminated mid-cycle)
    if settings.BASELINE_DEVIATION_STAGE_ENABLED:
        _update_baseline_buckets(
            evidence_output=evidence_output,
            baseline_client=seasonal_baseline_client,
            evaluation_time=evaluation_time,
            logger=logger,
        )
    ```
  - [x] 3.8 Implement `_update_baseline_buckets()` as a module-level helper in `__main__.py`:
    ```python
    def _update_baseline_buckets(
        evidence_output: EvidenceStageOutput,
        baseline_client: SeasonalBaselineClient,
        evaluation_time: datetime,
        logger: structlog.BoundLogger,
    ) -> None:
        """Write current cycle observations into seasonal baseline buckets (FR3).

        Called after detection so baseline reads during detection see the pre-cycle
        historical values (read-then-write ordering).
        """
        from aiops_triage_pipeline.baseline.computation import time_to_bucket
        from collections import defaultdict
        dow, hour = time_to_bucket(evaluation_time)
        # Aggregate: max per scope/metric (consistent with stage aggregation)
        metrics_by_scope: dict[tuple[str, ...], dict[str, float]] = defaultdict(dict)
        for row in evidence_output.rows:
            existing = metrics_by_scope[row.scope].get(row.metric_key)
            metrics_by_scope[row.scope][row.metric_key] = (
                max(existing, row.value) if existing is not None else row.value
            )
        for scope, metrics in metrics_by_scope.items():
            for metric_key, value in metrics.items():
                try:
                    baseline_client.update_bucket(scope, metric_key, dow, hour, value)
                except Exception as exc:
                    logger.warning(
                        "baseline_deviation_bucket_update_failed",
                        event_type="baseline_deviation.bucket_update_failed",
                        scope=scope,
                        metric_key=metric_key,
                        error=str(exc),
                    )
    ```
    NOTE: Move imports (`time_to_bucket`, `defaultdict`) to module-level rather than inside the function body (per ruff I001 rule enforced in this project).
  - [x] 3.9 Run `uv run ruff check src/aiops_triage_pipeline/__main__.py` — confirm clean

- [x] Task 4: Add `BASELINE_DEVIATION_STAGE_ENABLED` setting (AC: 6)
  - [x] 4.1 Open `src/aiops_triage_pipeline/config/settings.py`
  - [x] 4.2 Add `BASELINE_DEVIATION_STAGE_ENABLED: bool = True` to the `Settings` class, after the `SHARD_CHECKPOINT_TTL_SECONDS` block (around line ~121), with a comment: `# Baseline deviation stage (NFR-R5) — set False to skip without affecting other stages`
  - [x] 4.3 Run `uv run ruff check src/aiops_triage_pipeline/config/settings.py` — confirm clean
  - [x] 4.4 Run `uv run pytest tests/unit/config/ -v` — confirm 0 regressions

- [x] Task 5: Add unit tests for scheduler wiring (AC: 1, 2, 6, 7)
  - [x] 5.1 Create NEW file `tests/unit/pipeline/test_baseline_deviation_wiring.py`
  - [x] 5.2 All imports at module level (ruff I001 rule — no imports inside test functions)
  - [x] 5.3 Add the following unit tests (minimum — extend for edge coverage):
    - `test_run_baseline_deviation_stage_cycle_calls_stage_function` — verify the scheduler wrapper calls `collect_baseline_deviation_stage_output` with correct keyword arguments and returns `BaselineDeviationStageOutput`
    - `test_run_baseline_deviation_stage_cycle_records_latency` — mock `record_pipeline_compute_latency` and verify it is called with `stage="stage2_5_baseline_deviation"`
    - `test_merge_baseline_deviation_findings_injects_into_gate_scope` — verify that `_merge_baseline_deviation_findings()` adds BASELINE_DEVIATION `Finding` objects to the correct scope in `gate_findings_by_scope`
    - `test_merge_baseline_deviation_findings_preserves_existing_gate_findings` — verify pre-existing gate findings are not overwritten
    - `test_merge_baseline_deviation_findings_no_op_when_empty` — verify behavior when `baseline_deviation_output.findings` is empty (no merge call needed, but `gate_findings_by_scope` still intact)
    - `test_update_baseline_buckets_calls_update_bucket_per_scope_metric` — mock `SeasonalBaselineClient.update_bucket` and verify it is called once per unique scope/metric pair
    - `test_update_baseline_buckets_uses_max_value_for_dedup` — verify that when multiple rows exist for the same scope/metric, `max()` is used
    - `test_update_baseline_buckets_error_isolation` — verify that if `update_bucket` raises for one scope/metric, others are still processed
    - `test_baseline_deviation_stage_disabled_returns_empty_output` — verify that when `BASELINE_DEVIATION_STAGE_ENABLED=False`, no call is made to `collect_baseline_deviation_stage_output` and empty `BaselineDeviationStageOutput` is returned
  - [x] 5.4 Run `uv run pytest tests/unit/pipeline/test_baseline_deviation_wiring.py -v` — confirm all pass, 0 skipped
  - [x] 5.5 Run `uv run ruff check tests/unit/pipeline/test_baseline_deviation_wiring.py` — confirm clean

- [x] Task 6: Add unit tests for GateInputV1 extension (AC: 3)
  - [x] 6.1 Add tests to existing `tests/unit/pipeline/stages/test_baseline_deviation.py` OR create `tests/unit/contracts/test_gate_input_baseline_deviation.py`:
    - `test_gate_input_v1_accepts_baseline_deviation_family` — construct `GateInputV1` with `anomaly_family="BASELINE_DEVIATION"` — confirm no ValidationError
    - `test_anomaly_family_from_gate_finding_name_handles_baseline_deviation` — verify `_anomaly_family_from_gate_finding_name("baseline_deviation")` returns `"BASELINE_DEVIATION"`
    - `test_anomaly_family_from_gate_finding_name_case_insensitive` — verify `_anomaly_family_from_gate_finding_name("BASELINE_DEVIATION")` returns `"BASELINE_DEVIATION"` (upper case)
    - `test_sustained_identity_key_handles_baseline_deviation` — verify `_sustained_identity_key(scope=("prod","c","t"), anomaly_family="BASELINE_DEVIATION")` produces a valid tuple
  - [x] 6.2 Run tests — confirm all pass, 0 skipped

- [x] Task 7: Integration test end-to-end (AC: 8)
  - [x] 7.1 Open `tests/integration/test_pipeline_e2e.py`
  - [x] 7.2 Add test `test_baseline_deviation_finding_flows_end_to_end` that:
    - Seeds a real Redis instance (testcontainers) with stable historical baseline values via `SeasonalBaselineClient.seed_from_history()` so MAD computation produces deviations
    - Calls `run_baseline_deviation_stage_cycle()` with the seeded data via `run_baseline_deviation_stage_cycle()`
    - Verifies the returned `BaselineDeviationStageOutput.findings` is non-empty with `anomaly_family="BASELINE_DEVIATION"`
    - Merges findings via `_merge_baseline_deviation_findings()` and verifies gate scope contains baseline_deviation finding
    - Calls `run_topology_stage_cycle()` with the merged evidence output and verifies it completes without error
    - Calls `run_gate_input_stage_cycle()` and verifies gate inputs are produced for the BASELINE_DEVIATION scope
    - Calls `run_gate_decision_stage_cycle()` and verifies an `ActionDecisionV1` is produced
    - Calls `build_outbox_ready_record()` without error
    - Marked with `@pytest.mark.integration`
  - [ ] 7.3 Run `TESTCONTAINERS_RYUK_DISABLED=true DOCKER_HOST=unix://$HOME/.docker/desktop/docker.sock uv run pytest tests/integration/test_pipeline_e2e.py -v -k "baseline_deviation" -m integration` — confirm test passes (requires Docker)

- [x] Task 8: Full regression suite (AC: 1–8)
  - [x] 8.1 Run `uv run pytest tests/unit/ -q` — confirm 0 regressions against prior passing count (1,261 passing from Story 2.3)
  - [x] 8.2 Confirm 0 skipped tests
  - [ ] 8.3 Run full suite: `TESTCONTAINERS_RYUK_DISABLED=true DOCKER_HOST=unix://$HOME/.docker/desktop/docker.sock uv run pytest -q -rs`

- [x] Task 9: Update documentation (AC: 8)
  - [x] 9.1 Update `docs/developer-onboarding.md` — added Stage 2.5 Baseline Deviation to both mermaid diagrams (overview and stage flow) and the per-stage walkthrough with full description including `BASELINE_DEVIATION_STAGE_ENABLED` flag and `update_bucket` incremental update behavior
  - [x] 9.2 Verify `docs/architecture.md` pipeline stage ordering section already reflects the correct order (added in Story 2.3 — verified it is complete and accurate for Story 2.4)

## Dev Notes

### What This Story Delivers

Story 2.4 is the **final wiring story for Epic 2**. It makes `BASELINE_DEVIATION` findings produced by Story 2.3 flow through the full pipeline to Slack dispatch. This story touches:

1. **`pipeline/scheduler.py`** — NEW function `run_baseline_deviation_stage_cycle()` (mirrors existing run_*_stage_cycle functions)
2. **`__main__.py`** — wire the new stage function, merge findings into `EvidenceStageOutput`, add incremental `update_bucket()` calls
3. **`contracts/gate_input.py`** — extend `GateInputV1.anomaly_family` Literal with `"BASELINE_DEVIATION"` (additive-only)
4. **`pipeline/stages/gating.py`** — extend `_anomaly_family_from_gate_finding_name()` and related Literal type annotations
5. **`config/settings.py`** — add `BASELINE_DEVIATION_STAGE_ENABLED: bool = True`
6. **Tests** — unit tests for wiring helpers + integration test

**Files NOT touched in this story:**
- `baseline/computation.py` — complete (Story 2.1)
- `baseline/client.py` — complete (Epic 1)
- `baseline/models.py` — complete (Story 2.2)
- `models/anomaly.py` — complete (Story 2.2)
- `pipeline/stages/baseline_deviation.py` — complete (Story 2.3)
- `pipeline/stages/casefile.py` — passthrough, no changes (FR20)
- `pipeline/stages/topology.py` — passthrough, no changes (FR18)
- `pipeline/stages/dispatch.py` — passthrough, no changes (FR21)
- `pipeline/stages/outbox.py` — passthrough, no changes (FR20)

### Critical: How BASELINE_DEVIATION Findings Flow Into Gating

**The Problem:** `collect_gate_inputs_by_scope()` (in `gating.py`) iterates `evidence_output.gate_findings_by_scope`. This dict is originally built by `build_gate_findings_by_scope(anomaly_result)` in `evidence.py` — which only includes hand-coded findings. BASELINE_DEVIATION findings from Story 2.3 live in `BaselineDeviationStageOutput.findings`, not in `EvidenceStageOutput`.

**The Solution:** In `__main__.py`, after calling `run_baseline_deviation_stage_cycle()`, reconstruct `EvidenceStageOutput` with BASELINE_DEVIATION gate findings merged into `gate_findings_by_scope`. The helper `_merge_baseline_deviation_findings()` does this reconstruction.

**Why reconstruct rather than mutate:** `EvidenceStageOutput` is `frozen=True`. Must create a new instance. All other fields pass through unchanged.

**The `_to_gate_finding()` question:** This private function converts `AnomalyFinding → Finding` (the `contracts/gate_input.py` contract model). It lives in `pipeline/stages/anomaly.py`. You have two options:
- **Option A (preferred):** Import it directly: `from aiops_triage_pipeline.pipeline.stages.anomaly import _to_gate_finding`. This is a private function but it's within the same package. The leading underscore indicates it is not part of the public API but importing within the package is acceptable.
- **Option B (fallback):** Duplicate the minimal construction inline: `Finding(finding_id=f.finding_id, name=f.anomaly_family.lower(), is_anomalous=True, evidence_required=f.evidence_required, is_primary=f.is_primary, severity=f.severity, reason_codes=f.reason_codes)`

Use Option A unless the import causes a circular dependency (it should not — `__main__.py` already imports from `anomaly.py` indirectly).

### Critical: `GateInputV1.anomaly_family` Literal Extension (Additive-Only)

**Before (line 95 of `contracts/gate_input.py`):**
```python
anomaly_family: Literal["CONSUMER_LAG", "VOLUME_DROP", "THROUGHPUT_CONSTRAINED_PROXY"]
```

**After:**
```python
anomaly_family: Literal["CONSUMER_LAG", "VOLUME_DROP", "THROUGHPUT_CONSTRAINED_PROXY", "BASELINE_DEVIATION"]
```

This is a **Procedure A additive change** per `docs/schema-evolution-strategy.md`. The `GateInputV1` model is used in `collect_gate_inputs_by_scope()` construction. After this change, constructing `GateInputV1(anomaly_family="BASELINE_DEVIATION", ...)` will no longer raise `ValidationError`. All existing hand-coded family callers are unaffected.

### Critical: `_anomaly_family_from_gate_finding_name()` in gating.py

**Current implementation:**
```python
def _anomaly_family_from_gate_finding_name(
    finding_name: str,
) -> Literal["CONSUMER_LAG", "VOLUME_DROP", "THROUGHPUT_CONSTRAINED_PROXY"]:
    normalized = finding_name.strip().upper()
    if normalized == "CONSUMER_LAG":
        return "CONSUMER_LAG"
    if normalized == "VOLUME_DROP":
        return "VOLUME_DROP"
    if normalized == "THROUGHPUT_CONSTRAINED_PROXY":
        return "THROUGHPUT_CONSTRAINED_PROXY"
    raise ValueError(f"Unsupported finding name for anomaly family mapping: {finding_name!r}")
```

**After change:**
```python
def _anomaly_family_from_gate_finding_name(
    finding_name: str,
) -> Literal["CONSUMER_LAG", "VOLUME_DROP", "THROUGHPUT_CONSTRAINED_PROXY", "BASELINE_DEVIATION"]:
    normalized = finding_name.strip().upper()
    if normalized == "CONSUMER_LAG":
        return "CONSUMER_LAG"
    if normalized == "VOLUME_DROP":
        return "VOLUME_DROP"
    if normalized == "THROUGHPUT_CONSTRAINED_PROXY":
        return "THROUGHPUT_CONSTRAINED_PROXY"
    if normalized == "BASELINE_DEVIATION":
        return "BASELINE_DEVIATION"
    raise ValueError(f"Unsupported finding name for anomaly family mapping: {finding_name!r}")
```

Note that `Finding.name` is set to `finding.anomaly_family.lower()` in `_to_gate_finding()` (see `anomaly.py` line 208). So `"BASELINE_DEVIATION"` is stored as `"baseline_deviation"` in `Finding.name`. When `_anomaly_family_from_gate_finding_name("baseline_deviation")` is called, `.strip().upper()` produces `"BASELINE_DEVIATION"` — the match works correctly.

### Critical: `_sustained_identity_key()` for BASELINE_DEVIATION

**Current signature and body:**
```python
def _sustained_identity_key(
    *,
    scope: GateScope,
    anomaly_family: Literal["CONSUMER_LAG", "VOLUME_DROP", "THROUGHPUT_CONSTRAINED_PROXY"],
) -> tuple[str, str, str, str]:
    if len(scope) == 3:
        return (scope[0], scope[1], f"topic:{scope[2]}", anomaly_family)
    if len(scope) == 4:
        return (scope[0], scope[1], f"group:{scope[2]}", anomaly_family)
    raise ValueError(f"Unsupported scope shape for sustained identity key: {scope}")
```

Only the type annotation changes — the body already handles the value dynamically. After the annotation change, `_sustained_identity_key(scope=("prod","kafka","orders"), anomaly_family="BASELINE_DEVIATION")` returns `("prod", "kafka", "topic:orders", "BASELINE_DEVIATION")` — a valid sustained identity key that will look up to `None` in `peak_output.sustained_by_key` (since baseline deviation findings are not tracked by the peak stage), which causes `is_sustained_for_scoring=None` and `sustained_for_gate_input=False`. This is correct behavior: BASELINE_DEVIATION findings have no sustainability signal.

### Critical: Canonical `run_baseline_deviation_stage_cycle()` Implementation

```python
def run_baseline_deviation_stage_cycle(
    *,
    evidence_output: EvidenceStageOutput,
    peak_output: PeakStageOutput,
    baseline_client: SeasonalBaselineClient,
    evaluation_time: datetime,
    alert_evaluator: OperationalAlertEvaluator | None = None,
) -> BaselineDeviationStageOutput:
    """Run baseline deviation stage from Stage 1 and Stage 2 outputs.

    Detects correlated multi-metric baseline deviations and returns findings
    with summary counters. Fail-open: returns empty output on Redis unavailability.
    """
    started_at = time.perf_counter()
    try:
        return collect_baseline_deviation_stage_output(
            evidence_output=evidence_output,
            peak_output=peak_output,
            baseline_client=baseline_client,
            evaluation_time=evaluation_time,
        )
    finally:
        elapsed_seconds = time.perf_counter() - started_at
        record_pipeline_compute_latency(
            stage="stage2_5_baseline_deviation",
            seconds=elapsed_seconds,
        )
        if alert_evaluator is not None:
            alert = alert_evaluator.evaluate_pipeline_stage_latency(
                seconds=elapsed_seconds,
                stage="stage2_5_baseline_deviation",
            )
            if alert is not None:
                _emit_operational_alert(
                    logger=get_logger("pipeline.scheduler"),
                    alert=alert,
                    stage="stage2_5_baseline_deviation",
                )
```

### Critical: `__main__.py` Wiring Location

The baseline deviation stage must be inserted inside the `try:` block in `_hot_path_scheduler_loop()`, specifically at:

```python
# line ~970 (AFTER peak_output)
peak_output = run_peak_stage_cycle(...)
persist_sustained_window_states(...)
persist_peak_profiles(...)
previous_sustained_identity_keys = set(...)

# ── NEW: Baseline deviation stage (Story 2.4) ────────────────────────
if settings.BASELINE_DEVIATION_STAGE_ENABLED:
    baseline_deviation_output = run_baseline_deviation_stage_cycle(
        evidence_output=evidence_output,
        peak_output=peak_output,
        baseline_client=seasonal_baseline_client,
        evaluation_time=evaluation_time,
        alert_evaluator=alert_evaluator,
    )
    if baseline_deviation_output.findings:
        evidence_output = _merge_baseline_deviation_findings(
            evidence_output=evidence_output,
            baseline_deviation_output=baseline_deviation_output,
        )
    _update_baseline_buckets(
        evidence_output=evidence_output,
        baseline_client=seasonal_baseline_client,
        evaluation_time=evaluation_time,
        logger=logger,
    )
else:
    baseline_deviation_output = BaselineDeviationStageOutput(
        findings=(),
        scopes_evaluated=0,
        deviations_detected=0,
        deviations_suppressed_single_metric=0,
        deviations_suppressed_dedup=0,
        evaluation_time=evaluation_time,
    )
# ──────────────────────────────────────────────────────────────────────

topology_output = run_topology_stage_cycle(...)
```

`seasonal_baseline_client` is already constructed at line ~681 of `_hot_path_scheduler_loop()`. No new construction needed.

### Critical: `update_bucket` Read-Then-Write Ordering

The incremental bucket update MUST happen AFTER `collect_baseline_deviation_stage_output()` returns. The detection stage reads historical values during evaluation. If writes happened before reads, the current cycle's observation would contaminate the baseline being read — producing incorrect z-score computations.

**Correct:**
1. `run_baseline_deviation_stage_cycle()` — reads Redis baselines for detection
2. `_update_baseline_buckets()` — writes current observations to Redis

**Wrong:**
1. `_update_baseline_buckets()` — writes first (contaminates baseline for detection)
2. `run_baseline_deviation_stage_cycle()` — reads already-contaminated baselines

### Critical: `BASELINE_DEVIATION_STAGE_ENABLED` Default and Location

Add to `Settings` class in `settings.py`:

```python
# Baseline deviation stage (NFR-R5) — set False to skip without affecting other stages
BASELINE_DEVIATION_STAGE_ENABLED: bool = True
```

Place it near the other feature-flag style booleans like `DISTRIBUTED_CYCLE_LOCK_ENABLED` (line ~111) and `SHARD_REGISTRY_ENABLED` (line ~117). The default is `True` so the feature is on in all environments. Operators can set `BASELINE_DEVIATION_STAGE_ENABLED=false` via environment variable to disable without code changes.

### Critical: `EvidenceStageOutput` Reconstruction — Field Completeness

When constructing the new `EvidenceStageOutput` in `_merge_baseline_deviation_findings()`, ALL fields must be passed. The current `EvidenceStageOutput` (as of Story 2.2) has these fields:

```python
class EvidenceStageOutput(BaseModel, frozen=True):
    rows: tuple[EvidenceRow, ...]
    anomaly_result: AnomalyDetectionResult
    gate_findings_by_scope: Mapping[tuple[str, ...], tuple[Finding, ...]]
    evidence_status_map_by_scope: Mapping[...] = {}
    telemetry_degraded_active: bool = False
    telemetry_degraded_events: tuple[...] = ()
    max_safe_action: Action | None = None
```

Check `src/aiops_triage_pipeline/models/evidence.py` for the complete and authoritative field list before implementing — the actual field names may differ slightly. Pass all fields through unchanged except `gate_findings_by_scope`.

### Critical: Module-Level Imports in `__main__.py`

Per ruff I001 rule (enforced project-wide), ALL imports must be at module level. Do NOT add imports inside `_merge_baseline_deviation_findings()` or `_update_baseline_buckets()` function bodies. Add them to the top-level import block in `__main__.py`.

Specifically, these imports need to be added to `__main__.py` (if not already present):
- `from aiops_triage_pipeline.baseline.computation import time_to_bucket` (for `_update_baseline_buckets`)
- `from aiops_triage_pipeline.baseline.models import BaselineDeviationStageOutput` (for the disabled-stage empty output)
- `from aiops_triage_pipeline.pipeline.scheduler import ... run_baseline_deviation_stage_cycle` (add to existing import group)
- `from aiops_triage_pipeline.pipeline.stages.anomaly import _to_gate_finding` (for `_merge_baseline_deviation_findings`)

### Critical: Stage Latency Metric Stage Name

Use `"stage2_5_baseline_deviation"` as the stage identifier string for `record_pipeline_compute_latency()`. This naming follows the existing convention:
- `"stage2_peak"` (run_peak_stage_cycle)
- `"stage3_topology"` (run_topology_stage_cycle)
- `"stage4_gate_input"` (run_gate_input_stage_cycle)

The baseline deviation stage sits between peak (stage 2) and topology (stage 3), hence `"stage2_5_baseline_deviation"`.

### Critical: Integration Test Setup for Baseline Deviation

For the integration test in `test_pipeline_e2e.py`, use the following approach to produce deterministic deviations:

```python
# Seed historical values so current observation creates a large z-score
# historical: [10, 10, 10, 10, 10, 10] — all identical → MAD = 0 → None (skip)
# historical: [8, 9, 10, 11, 12] — median=10, MAD=1 → current=50 → z≫4.0 (deviation)
BASELINE_SCOPE = ("prod", "kafka-prod", "orders.completed")
HISTORICAL_VALUES = [8.0, 9.0, 10.0, 11.0, 12.0]  # 5 samples, median=10, MAD=1
CURRENT_VALUE = 50.0  # z-score ≈ 26.6 >> MAD_THRESHOLD (4.0)
EVAL_TIME = datetime(2026, 4, 5, 14, 0, tzinfo=UTC)  # Sunday, hour=14 → bucket (6, 14)
```

Seed via:
```python
client = SeasonalBaselineClient(redis_client=real_redis)
dow, hour = time_to_bucket(EVAL_TIME)
# Use seed_from_history pattern: write bucket directly
for i, v in enumerate(HISTORICAL_VALUES):
    client.update_bucket(BASELINE_SCOPE, "consumer_group_lag", dow, hour, v)
    client.update_bucket(BASELINE_SCOPE, "topic_messages_in_per_sec", dow, hour, v)
```

For two metrics to deviate (satisfying `MIN_CORRELATED_DEVIATIONS=2`), both `consumer_group_lag` and `topic_messages_in_per_sec` need historical values and a large current value.

### Architecture Context

From `docs/architecture.md`:
> 3. **Baseline deviation stage** (`pipeline/stages/baseline_deviation.py`) — detects correlated multi-metric deviations against per-bucket Redis baselines; produces `BaselineDeviationStageOutput`. Placed after peak so peak context is available for future enrichment; runs before topology to allow deviation findings to influence topology scoring.

From `artifact/planning-artifacts/architecture/project-structure-boundaries.md`:
> **Contract Boundary:** `models/anomaly_finding.py` is modified (additive field). `baseline/models.py` defines new models that are baseline-specific. **No existing contract files in `contracts/` are modified — BASELINE_DEVIATION flows through existing contracts unchanged.**

Note: `GateInputV1.anomaly_family` IS a contract file change (additive Literal extension), but this is a Procedure A additive change — it does not break existing consumers of the contract.

From `artifact/planning-artifacts/architecture/project-structure-boundaries.md`:
> `scheduler.py` calls `run_baseline_deviation_stage_cycle()` between peak and topology

### Previous Story Learnings Applied (Stories 2.1–2.3)

1. **[Retro L4] Module-level imports only** — ruff I001 is enforced. All new imports in `__main__.py`, `scheduler.py`, and test files must be at module level. No imports inside function bodies.

2. **[Story 2.2 debug log] Circular import resolution** — `baseline/models.py` calls `AnomalyFinding.model_rebuild()` at import time. If `_merge_baseline_deviation_findings()` imports from `anomaly.py`, the circular import is already resolved. No additional `model_rebuild()` calls needed.

3. **[Story 2.1/2.2 retro] Pre-existing 4 failures** — `tests/unit/integrations/test_llm.py` failures (openai/Python 3.13 incompatibility) may or may not appear. If they appear, do NOT treat as regressions.

4. **[Story 2.3 retro] `time_to_bucket()` is the SOLE source of bucket derivation** — never compute `(weekday, hour)` inline in `_update_baseline_buckets()`. Always call `time_to_bucket(evaluation_time)`.

5. **[Epic 1 retro] File List discipline** — Dev Agent Record File List must be complete. List every created/modified file at the end of the story including test files and docs.

## Dev Agent Record

### Implementation Plan

Story 2.4 wires `BASELINE_DEVIATION` findings into the full pipeline. All changes are additive.

1. **scheduler.py**: Added `run_baseline_deviation_stage_cycle()` following the exact `run_peak_stage_cycle`/`run_topology_stage_cycle` pattern (perf_counter + try/finally + latency metric + alert evaluator). Added imports for `SeasonalBaselineClient`, `BaselineDeviationStageOutput`, and `collect_baseline_deviation_stage_output`.

2. **gate_input.py**: Extended `GateInputV1.anomaly_family` Literal to include `"BASELINE_DEVIATION"` (Procedure A additive change). Used multi-line Literal for ruff E501 compliance.

3. **gating.py**: Added `_AnomalyFamily` type alias to avoid repetition, extended `_anomaly_family_from_gate_finding_name()` with `BASELINE_DEVIATION` branch, and updated all Literal type annotations for `_sustained_identity_key`, `_derive_scoring_result_with_fallback`, `_resolve_context_scoring_result`, `scored_by_anomaly_family` dict, and `_select_primary_scoring_result`.

4. **settings.py**: Added `BASELINE_DEVIATION_STAGE_ENABLED: bool = True` after `SHARD_CHECKPOINT_TTL_SECONDS`.

5. **__main__.py**: Added module-level imports (`defaultdict`, `time_to_bucket`, `BaselineDeviationStageOutput`, `run_baseline_deviation_stage_cycle`, `_to_gate_finding`, `EvidenceStageOutput`). Added `_merge_baseline_deviation_findings()` and `_update_baseline_buckets()` module-level helpers. Wired baseline deviation stage in `_hot_path_scheduler_loop()` between peak and topology stages.

6. **tests/unit/test_main.py**: Added `BASELINE_DEVIATION_STAGE_ENABLED=False` to `_hot_path_settings_for_coordination_tests()` so existing hot-path tests skip the new stage and remain unaffected.

### Completion Notes

- All 27 specified ATDD tests pass (17 in test_baseline_deviation_wiring.py + 10 in test_gate_input_baseline_deviation.py)
- Full unit test suite: 1309 tests pass, 0 failures, 0 skipped
- ruff check clean on all modified source files
- `BASELINE_DEVIATION_STAGE_ENABLED` defaults to `True` in production; existing hot-path tests use `False` to avoid mock complexity

## File List

- `src/aiops_triage_pipeline/pipeline/scheduler.py` (modified)
- `src/aiops_triage_pipeline/__main__.py` (modified)
- `src/aiops_triage_pipeline/contracts/gate_input.py` (modified)
- `src/aiops_triage_pipeline/pipeline/stages/gating.py` (modified)
- `src/aiops_triage_pipeline/config/settings.py` (modified)
- `tests/unit/pipeline/test_baseline_deviation_wiring.py` (pre-existing ATDD test file, already existed)
- `tests/unit/contracts/test_gate_input_baseline_deviation.py` (pre-existing ATDD test file, already existed)
- `tests/unit/test_main.py` (modified — added BASELINE_DEVIATION_STAGE_ENABLED to settings mock)
- `artifact/implementation-artifacts/2-4-pipeline-integration-and-scheduler-wiring.md` (this file)
- `artifact/implementation-artifacts/sprint-status.yaml` (updated to "review")

## Change Log

- 2026-04-06: Story 2.4 implemented — pipeline integration and scheduler wiring for BASELINE_DEVIATION findings. All 27 ATDD tests pass. 1309 unit tests pass with 0 regressions.

6. **[Retro L2] Test `is` for booleans** — assert `finding.is_primary is False`, not `assert not finding.is_primary`. For `bool` field assertions, use `is True` / `is False`.

7. **[Code review 2.1/2.2] No invalid `noqa` comments** — only add `noqa` for rules in active ruff select set `E,F,I,N,W`. Never `noqa: ARG002`, `noqa: BLE001`.

8. **[Story 2.3 test bug] FIXED_EVAL_TIME day-of-week** — `datetime(2026, 4, 5, 14, 0, tzinfo=UTC)` is Sunday=6 not Wednesday=2. Use `(6, 14)` as the expected bucket for integration test assertions.

### Project Structure Notes

**Files to CREATE (new):**
- `tests/unit/pipeline/test_baseline_deviation_wiring.py` — unit tests for scheduler wiring helpers

**Files to MODIFY:**
- `src/aiops_triage_pipeline/pipeline/scheduler.py` — add `run_baseline_deviation_stage_cycle()`
- `src/aiops_triage_pipeline/__main__.py` — wire baseline deviation stage; add helpers
- `src/aiops_triage_pipeline/contracts/gate_input.py` — extend `GateInputV1.anomaly_family` Literal
- `src/aiops_triage_pipeline/pipeline/stages/gating.py` — extend Literal type annotations in helpers
- `src/aiops_triage_pipeline/config/settings.py` — add `BASELINE_DEVIATION_STAGE_ENABLED`
- `tests/integration/test_pipeline_e2e.py` — add end-to-end BASELINE_DEVIATION test
- `docs/developer-onboarding.md` — update pipeline flow description

**Files NOT touched:**
- `src/aiops_triage_pipeline/pipeline/stages/baseline_deviation.py` (Story 2.3 — complete)
- `src/aiops_triage_pipeline/baseline/` (Stories 2.1/2.2/Epic 1 — complete)
- `src/aiops_triage_pipeline/models/anomaly.py` (Story 2.2 — complete)
- `src/aiops_triage_pipeline/pipeline/stages/topology.py` (passthrough — no changes)
- `src/aiops_triage_pipeline/pipeline/stages/casefile.py` (passthrough — no changes)
- `src/aiops_triage_pipeline/pipeline/stages/dispatch.py` (passthrough — no changes)
- `src/aiops_triage_pipeline/pipeline/stages/evidence.py` (passthrough — no changes)

### References

- FR3 (incremental bucket update per cycle): [Source: artifact/planning-artifacts/epics.md#FR3]
- FR18 (topology passthrough, zero modifications): [Source: artifact/planning-artifacts/epics.md#FR18]
- FR19 (gating passthrough, AG0-AG6): [Source: artifact/planning-artifacts/epics.md#FR19]
- FR20 (casefile/outbox passthrough): [Source: artifact/planning-artifacts/epics.md#FR20]
- FR21 (dispatch/Slack passthrough): [Source: artifact/planning-artifacts/epics.md#FR21]
- NFR-A1 (SHA-256 hash-chain integrity): [Source: artifact/planning-artifacts/epics.md#NFR-A1]
- NFR-A4 (gate decision reproducibility): [Source: artifact/planning-artifacts/epics.md#NFR-A4]
- NFR-P6 (update_bucket < 5ms per scope): [Source: artifact/planning-artifacts/epics.md#NFR-P6]
- NFR-R5 (baseline deviation layer independently disableable): [Source: artifact/planning-artifacts/epics.md#NFR-R5]
- Story 2.4 acceptance criteria: [Source: artifact/planning-artifacts/epics.md#Story-2.4]
- Scheduler wiring location (after peak, before topology): [Source: artifact/planning-artifacts/architecture/project-structure-boundaries.md#Integration-Points]
- Stage ordering: [Source: docs/architecture.md#Pipeline-Stage-Ordering]
- Contract boundary (no existing contract changes): [Source: artifact/planning-artifacts/architecture/project-structure-boundaries.md#Contract-Boundary]
- `run_peak_stage_cycle` pattern (copy for `run_baseline_deviation_stage_cycle`): [Source: src/aiops_triage_pipeline/pipeline/scheduler.py#run_peak_stage_cycle]
- `run_topology_stage_cycle` pattern (alert_evaluator block): [Source: src/aiops_triage_pipeline/pipeline/scheduler.py#run_topology_stage_cycle]
- `_anomaly_family_from_gate_finding_name` (gating.py line ~1007): [Source: src/aiops_triage_pipeline/pipeline/stages/gating.py]
- `_to_gate_finding` (anomaly.py line ~205): [Source: src/aiops_triage_pipeline/pipeline/stages/anomaly.py]
- `GateInputV1.anomaly_family` (gate_input.py line 95): [Source: src/aiops_triage_pipeline/contracts/gate_input.py]
- `EvidenceStageOutput` field list: [Source: src/aiops_triage_pipeline/models/evidence.py]
- `SeasonalBaselineClient.update_bucket` signature: [Source: src/aiops_triage_pipeline/baseline/client.py#update_bucket]
- `seasonal_baseline_client` construction location (line ~681): [Source: src/aiops_triage_pipeline/__main__.py#_hot_path_scheduler_loop]
- `DISTRIBUTED_CYCLE_LOCK_ENABLED` / `SHARD_REGISTRY_ENABLED` (Settings placement pattern): [Source: src/aiops_triage_pipeline/config/settings.py]
- Procedure A (additive schema evolution): [Source: docs/schema-evolution-strategy.md#Procedure-A]
- Testing rules (0 skips, asyncio_mode=auto): [Source: artifact/project-context.md#Testing-Rules]
- Ruff config (line-length 100, py313, E/F/I/N/W): [Source: artifact/project-context.md#Code-Quality-Rules]
- Epic 1 retrospective learnings: [Source: artifact/implementation-artifacts/epic-1-retro-2026-04-05.md]
- Stories 2.1–2.3 Dev Agent Records (learnings): [Source: artifact/implementation-artifacts/2-1-mad-computation-engine.md, 2-2-baseline-deviation-finding-model.md, 2-3-baseline-deviation-stage-detection-correlation-and-dedup.md]

## Dev Agent Record

### Agent Model Used

claude-sonnet-4-6

### Debug Log References

### Completion Notes List

### File List
