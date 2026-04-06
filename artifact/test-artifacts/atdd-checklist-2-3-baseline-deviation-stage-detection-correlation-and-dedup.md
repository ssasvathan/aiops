---
stepsCompleted:
  - step-01-preflight-and-context
  - step-02-generation-mode
  - step-03-test-strategy
  - step-04-generate-tests
  - step-04c-aggregate
  - step-05-validate-and-complete
lastStep: step-05-validate-and-complete
lastSaved: '2026-04-05'
workflowType: testarch-atdd
inputDocuments:
  - artifact/implementation-artifacts/2-3-baseline-deviation-stage-detection-correlation-and-dedup.md
  - src/aiops_triage_pipeline/baseline/models.py
  - src/aiops_triage_pipeline/baseline/computation.py
  - src/aiops_triage_pipeline/baseline/constants.py
  - src/aiops_triage_pipeline/baseline/client.py
  - src/aiops_triage_pipeline/models/anomaly.py
  - src/aiops_triage_pipeline/models/evidence.py
  - src/aiops_triage_pipeline/models/peak.py
  - tests/unit/pipeline/stages/test_anomaly.py
  - tests/unit/pipeline/stages/test_peak.py
  - tests/unit/pipeline/conftest.py
  - _bmad/tea/config.yaml
---

# ATDD Checklist — Epic 2, Story 2.3: Baseline Deviation Stage — Detection, Correlation & Dedup

**Date:** 2026-04-05
**Author:** Sas
**Primary Test Level:** Unit (Python/pytest backend)
**TDD Phase:** RED (failing — implementation does not yet exist)

---

## Story Summary

Story 2.3 implements the `collect_baseline_deviation_stage_output()` pipeline stage function
in `src/aiops_triage_pipeline/pipeline/stages/baseline_deviation.py`. This stage reads
seasonal baselines from Redis via `SeasonalBaselineClient`, computes modified z-scores for
all metrics per scope, applies a correlation gate (`MIN_CORRELATED_DEVIATIONS=2`), deduplicates
against hand-coded detector families, and returns a frozen `BaselineDeviationStageOutput`.

**As a** on-call engineer
**I want** the system to detect correlated multi-metric baseline deviations per scope while suppressing single-metric noise and deferring to hand-coded detectors
**So that** I only receive findings for genuinely anomalous multi-metric patterns that existing detectors miss

---

## Stack Detection

- **Detected stack:** `backend` (Python — `pyproject.toml` present; no `package.json`)
- **Test framework:** pytest (asyncio_mode=auto, conftest fixtures available)
- **Generation mode:** AI Generation (no browser recording needed for backend)
- **TDD red-phase mechanism:** `ImportError` / `ModuleNotFoundError` at collection time

---

## Acceptance Criteria Coverage

1. **AC 1** — For each scope, read baselines and compute modified z-scores → covered by `test_correlated_deviations_emit_finding`
2. **AC 2** — >= `MIN_CORRELATED_DEVIATIONS` → emit `AnomalyFinding(anomaly_family="BASELINE_DEVIATION", severity="LOW", is_primary=False)` → covered by `test_correlated_deviations_emit_finding`, `test_finding_attributes`, `test_finding_baseline_context_populated`
3. **AC 3** — < `MIN_CORRELATED_DEVIATIONS` → no finding + DEBUG log → covered by `test_single_metric_suppressed`, `test_single_metric_suppressed_log_event`, `test_below_min_correlated_deviations_suppresses`
4. **AC 4** — Hand-coded dedup (exact scope match) → covered by `test_hand_coded_dedup_consumer_lag`, `test_hand_coded_dedup_volume_drop`, `test_hand_coded_dedup_throughput_constrained_proxy`, `test_dedup_only_for_exact_scope_match`, `test_dedup_suppression_log_event`
5. **AC 5** — Keyword-only signature, determinism → covered by `test_determinism_injected_evaluation_time`
6. **AC 6** — Per-scope error isolation → covered by `test_per_scope_error_isolation`
7. **AC 7** — Fail-open Redis unavailability → covered by `test_redis_unavailable_fail_open`, `test_redis_unavailable_log_event`
8. **AC 8** — Test coverage completeness → covered by all 18 tests

---

## Failing Tests Created (RED Phase)

### Unit Tests (18 tests)

**File:** `tests/unit/pipeline/stages/test_baseline_deviation.py`

- **Test:** `test_correlated_deviations_emit_finding`
  - **Status:** RED — `ModuleNotFoundError: No module named 'aiops_triage_pipeline.pipeline.stages.baseline_deviation'`
  - **Verifies:** AC 1+2 — 2 deviating metrics → 1 BASELINE_DEVIATION finding emitted

- **Test:** `test_finding_attributes`
  - **Status:** RED — `ModuleNotFoundError`
  - **Verifies:** AC 2 (FR16) — anomaly_family, severity, is_primary values

- **Test:** `test_finding_baseline_context_populated`
  - **Status:** RED — `ModuleNotFoundError`
  - **Verifies:** AC 2 (FR15, P4) — baseline_context set with correct fields

- **Test:** `test_single_metric_suppressed`
  - **Status:** RED — `ModuleNotFoundError`
  - **Verifies:** AC 3 — 1 deviating metric → no finding

- **Test:** `test_single_metric_suppressed_log_event`
  - **Status:** RED — `ModuleNotFoundError`
  - **Verifies:** AC 3 (NFR-A3) — DEBUG suppression log event emitted

- **Test:** `test_hand_coded_dedup_consumer_lag`
  - **Status:** RED — `ModuleNotFoundError`
  - **Verifies:** AC 4 — CONSUMER_LAG scope → no BASELINE_DEVIATION

- **Test:** `test_hand_coded_dedup_volume_drop`
  - **Status:** RED — `ModuleNotFoundError`
  - **Verifies:** AC 4 — VOLUME_DROP scope → no BASELINE_DEVIATION

- **Test:** `test_hand_coded_dedup_throughput_constrained_proxy`
  - **Status:** RED — `ModuleNotFoundError`
  - **Verifies:** AC 4 — THROUGHPUT_CONSTRAINED_PROXY → no BASELINE_DEVIATION

- **Test:** `test_dedup_only_for_exact_scope_match`
  - **Status:** RED — `ModuleNotFoundError`
  - **Verifies:** AC 4 (D6) — scope A deduped, scope B still emits

- **Test:** `test_dedup_suppression_log_event`
  - **Status:** RED — `ModuleNotFoundError`
  - **Verifies:** AC 4 (NFR-A3) — `baseline_deviation_suppressed_dedup` log event

- **Test:** `test_determinism_injected_evaluation_time`
  - **Status:** RED — `ModuleNotFoundError`
  - **Verifies:** AC 5 — same inputs + injected time → identical outputs

- **Test:** `test_per_scope_error_isolation`
  - **Status:** RED — `ModuleNotFoundError`
  - **Verifies:** AC 6 (NFR-R1) — exception in one scope, others continue

- **Test:** `test_redis_unavailable_fail_open`
  - **Status:** RED — `ModuleNotFoundError`
  - **Verifies:** AC 7 (NFR-R2) — ConnectionError → empty output, all counters = 0

- **Test:** `test_redis_unavailable_log_event`
  - **Status:** RED — `ModuleNotFoundError`
  - **Verifies:** AC 7 (NFR-A3) — `baseline_deviation_redis_unavailable` event emitted

- **Test:** `test_empty_evidence_output`
  - **Status:** RED — `ModuleNotFoundError`
  - **Verifies:** AC 8 — no rows → empty output, no exceptions

- **Test:** `test_stage_output_counters`
  - **Status:** RED — `ModuleNotFoundError`
  - **Verifies:** AC 8 — scopes_evaluated, suppressed_single_metric, suppressed_dedup counts

- **Test:** `test_reason_codes_contain_all_deviating_metrics`
  - **Status:** RED — `ModuleNotFoundError`
  - **Verifies:** AC 2 — 3 deviating metrics → 3 reason_codes with BASELINE_DEV:{key}:{dir} format

- **Test:** `test_mad_returns_none_skips_metric`
  - **Status:** RED — `ModuleNotFoundError`
  - **Verifies:** AC 1 — sparse history (< MIN_BUCKET_SAMPLES) → metric skipped

- **Test:** `test_exactly_min_correlated_deviations_emits_finding`
  - **Status:** RED — `ModuleNotFoundError`
  - **Verifies:** AC 2 — boundary: exactly MIN_CORRELATED_DEVIATIONS → finding emitted

- **Test:** `test_below_min_correlated_deviations_suppresses`
  - **Status:** RED — `ModuleNotFoundError`
  - **Verifies:** AC 3 — 1 deviation out of 2 metrics → single-metric suppression

- **Test:** `test_finding_id_is_deterministic_for_scope`
  - **Status:** RED — `ModuleNotFoundError`
  - **Verifies:** AC 5 — finding_id = `BASELINE_DEVIATION:{scope_key}` format

**Total tests collected:** 0 (collection fails at import — all 21 tests are RED)

---

## TDD Red Phase Verification

**Command:**
```bash
uv run pytest tests/unit/pipeline/stages/test_baseline_deviation.py -v
```

**Result:**
```
ERROR collecting tests/unit/pipeline/stages/test_baseline_deviation.py
ModuleNotFoundError: No module named 'aiops_triage_pipeline.pipeline.stages.baseline_deviation'
```

**Status:** RED phase verified. Tests fail at collection because the implementation module
`src/aiops_triage_pipeline/pipeline/stages/baseline_deviation.py` does not exist yet.

This is the correct Python TDD red-phase behaviour. No `@pytest.mark.xfail` is used — the
failure is genuine (import error), not a decorated skip.

---

## Fixtures / Helpers Used

All helpers are defined within the test file itself (no external fixture files needed):

- `_make_evidence_output(rows, findings)` — builds minimal `EvidenceStageOutput`
- `_make_peak_output()` — builds minimal `PeakStageOutput`
- `_make_mock_client(history_by_metric)` — wraps `MagicMock(spec=SeasonalBaselineClient)`
- `_make_deviating_row(scope, metric_key, value)` — builds `EvidenceRow` with high deviation value
- `_make_hand_coded_finding(scope, anomaly_family)` — builds hand-coded `AnomalyFinding`
- `FIXED_EVAL_TIME` — `datetime(2026, 4, 5, 14, 0, tzinfo=UTC)` — Wednesday bucket (2, 14)
- `log_stream` fixture — from `tests/unit/pipeline/conftest.py` (autouse + structlog reset)

---

## Running Tests

```bash
# Run failing tests for this story (red phase)
uv run pytest tests/unit/pipeline/stages/test_baseline_deviation.py -v

# Run with ruff check
uv run ruff check tests/unit/pipeline/stages/test_baseline_deviation.py

# After implementation: run full unit suite
uv run pytest tests/unit/ -q
```

---

## Red-Green-Refactor Workflow

### RED Phase (Complete) ✅

- ✅ 21 tests written covering all 8 acceptance criteria
- ✅ All tests fail with `ModuleNotFoundError` (correct red phase — no `xfail`)
- ✅ Ruff check passes — zero linting errors
- ✅ No `@pytest.mark.xfail` or `@pytest.mark.skip` used
- ✅ Injected dependencies only (no wall clock, no global state)
- ✅ Structured log events verified in `test_*_log_event` tests via `log_stream` fixture

### GREEN Phase (Dev Team — Next Steps)

1. Create `src/aiops_triage_pipeline/pipeline/stages/baseline_deviation.py`
2. Implement `collect_baseline_deviation_stage_output()` (exact canonical signature from Dev Notes)
3. Run: `uv run pytest tests/unit/pipeline/stages/test_baseline_deviation.py -v`
4. Fix any failures (implementation bugs, not test bugs)
5. Run full regression: `uv run pytest tests/unit/ -q`
6. Verify 0 regressions (baseline: 1261 passing from Story 2.2)

### Key Implementation Guidance

- Signature: `collect_baseline_deviation_stage_output(*, evidence_output, peak_output, baseline_client, evaluation_time)`
- Helpers to implement: `_build_hand_coded_dedup_set()`, `_evaluate_scope()`, `_build_baseline_deviation_finding()`
- Constants: `HAND_CODED_FAMILIES = frozenset({"CONSUMER_LAG", "VOLUME_DROP", "THROUGHPUT_CONSTRAINED_PROXY"})`
- Log events (all with `baseline_deviation_` prefix): `stage_started`, `stage_completed`, `suppressed_single_metric`, `suppressed_dedup`, `finding_emitted`, `redis_unavailable`
- `finding_id` format: `f"BASELINE_DEVIATION:{scope_key}"` where `scope_key = "|".join(scope)` — never uuid

---

## Knowledge Fragments Applied

- **data-factories.md** — Helper factory functions for test data (`_make_evidence_output`, `_make_peak_output`, `_make_mock_client`)
- **test-quality.md** — Isolation, determinism, one-behaviour-per-test rules
- **test-levels-framework.md** — Unit level appropriate for pure function pipeline stages
- **error-handling.md** — Testing scoped exception handling and fail-open paths
- **test-healing-patterns.md** — Structured log event assertion pattern via `log_stream` fixture

---

## Notes

- `MIN_CORRELATED_DEVIATIONS = 2` is from `baseline/constants.py` — verified in test with assertion
- `_STABLE_HISTORY = [8.0, 9.0, 10.0, 11.0, 12.0]` (5 values) produces a clear deviation for `current=5000.0` (z-score >> 4.0 threshold)
- `test_below_min_correlated_deviations_suppresses` uses `value=10.0` (near baseline median of 10.0) to ensure only 1 of 2 metrics deviates
- Pre-existing 4 failures in `tests/unit/integrations/test_llm.py` are NOT regressions

---

**Generated by BMad TEA Agent** — 2026-04-05
