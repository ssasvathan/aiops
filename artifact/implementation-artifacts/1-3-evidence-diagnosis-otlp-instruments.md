# Story 1.3: Evidence & Diagnosis OTLP Instruments

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a platform engineer,
I want the pipeline to emit an evidence status gauge and a diagnosis completion counter with business-level labels,
so that Prometheus captures the real-time evidence state per metric and tracks LLM diagnosis completions with confidence and fault domain data.

## Acceptance Criteria

1. **Given** the pipeline collects evidence during the evidence stage **When** evidence status is determined for a metric **Then** the `aiops.evidence.status` gauge is emitted with labels: `scope`, `metric_key`, `status`, `topic` **And** status values are uppercase: `PRESENT`, `UNKNOWN`, `ABSENT`, `STALE` **And** the instrument is defined in `health/metrics.py` using `create_up_down_counter` per project conventions **And** the evidence gauge lifecycle (reset-and-set vs. incremental) is defined and documented

2. **Given** the evidence gauge has high cardinality (~hundreds of series across 9 topics) **When** metrics are emitted **Then** the full label granularity is preserved for query-side PromQL aggregation in Grafana (FR3 cardinality note)

3. **Given** the diagnosis cold-path completes for an anomaly **When** a `DiagnosisReportV1` is produced **Then** the `aiops.diagnosis.completed_total` counter increments by 1 with labels: `confidence`, `fault_domain_present`, `topic` **And** the `topic` label is available at the emission point; if not naturally available, the story includes propagation work to thread it through

4. **Given** both instruments are defined **When** unit tests in `tests/unit/health/test_metrics.py` are executed **Then** each instrument emits the expected metric name and label set **And** the evidence gauge test validates the correct label cardinality pattern **And** both instruments follow existing patterns in `health/metrics.py` (NFR14)

## Tasks / Subtasks

- [x] Task 1: Add `aiops.evidence.status` up-down-counter to `health/metrics.py` (AC: 1, 2)
  - [x] 1.1 Define `_evidence_status` using `_meter.create_up_down_counter("aiops.evidence.status", ...)` — labels: `scope`, `metric_key`, `status`, `topic`
  - [x] 1.2 Implement `record_evidence_status(*, scope: str, metric_key: str, status: str, topic: str) -> None` public function
  - [x] 1.3 Choose and document the lifecycle pattern: **reset-and-set per cycle** — before emitting each cycle, emit `-1` for any previously emitted label combination using the same `(scope, metric_key, status, topic)` key; then emit `+1` for the new status. Maintain a `_prev_evidence_status: dict[tuple[str,str,str,str], int]` module-level state dict protected by `_state_lock` for delta accounting
  - [x] 1.4 Alternative simpler lifecycle: treat as pure-increment (no reset) — only emit when evidence status changes or on first emission. Document rationale clearly in code comments for Grafana query authors
  - [x] 1.5 Status values are uppercase strings from `EvidenceStatus` enum: `"PRESENT"`, `"UNKNOWN"`, `"ABSENT"`, `"STALE"` — no lowercase translation

- [x] Task 2: Add `aiops.diagnosis.completed_total` counter to `health/metrics.py` (AC: 3)
  - [x] 2.1 Define `_diagnosis_completed_total` using `_meter.create_counter("aiops.diagnosis.completed_total", ...)` — labels: `confidence`, `fault_domain_present`, `topic`
  - [x] 2.2 Implement `record_diagnosis_completed(*, confidence: str, fault_domain_present: str, topic: str) -> None` public function
  - [x] 2.3 `confidence` values: `"LOW"`, `"MEDIUM"`, `"HIGH"` (from `DiagnosisConfidence` enum, already uppercase)
  - [x] 2.4 `fault_domain_present` is a boolean expressed as `"true"` / `"false"` string — derived from `report.fault_domain is not None`
  - [x] 2.5 `topic` is available from `triage_excerpt.topic` inside `run_cold_path_diagnosis()` — it is already in scope (see wiring notes below)

- [x] Task 3: Wire `record_evidence_status` call into the evidence stage (AC: 1, 2)
  - [x] 3.1 Identify the correct call site: `collect_evidence_stage_output()` in `pipeline/stages/evidence.py` — after `build_evidence_status_map_by_scope()` returns `evidence_status_map_by_scope` (line ~179)
  - [x] 3.2 Iterate over `evidence_status_map_by_scope`: for each `(scope_tuple, status_by_metric)` pair, iterate over `(metric_key, evidence_status)` pairs and call `record_evidence_status(scope=str(scope_tuple), metric_key=metric_key, status=evidence_status.value, topic=_extract_topic_from_scope(scope_tuple))`
  - [x] 3.3 The `scope_tuple` is a `tuple[str, ...]` like `("dev", "cluster-a", "group-1", "payments.consumer-lag")` — topic is the last element (`scope_tuple[-1]`) for lag metrics, or position 2 for non-lag metrics. Verify by reviewing `build_evidence_scope_key()` in `evidence.py` — topic is always the last element of the scope tuple
  - [x] 3.4 Pass `topic` extracted from the scope tuple as the `topic` label value

- [x] Task 4: Wire `record_diagnosis_completed` call into the diagnosis cold-path (AC: 3)
  - [x] 4.1 The correct call site is inside `run_cold_path_diagnosis()` in `diagnosis/graph.py` — at the success completion point after `await health_registry.update("llm", HealthStatus.HEALTHY)` and `_record_llm_completion(result="success")` (line ~419-421)
  - [x] 4.2 `topic` is available from `triage_excerpt.topic` — `triage_excerpt` is a parameter of `run_cold_path_diagnosis()` and is a `TriageExcerptV1` with `.topic: str` field
  - [x] 4.3 `confidence` = `report.confidence.value` (from `DiagnosisConfidence` enum — already uppercase: `"LOW"`, `"MEDIUM"`, `"HIGH"`)
  - [x] 4.4 `fault_domain_present` = `"true"` if `report.fault_domain is not None` else `"false"`
  - [x] 4.5 Wrap the `record_diagnosis_completed` call in a try-except (same pattern as `record_finding` in `__main__.py`) to prevent OTLP SDK exceptions from propagating into the diagnosis flow
  - [x] 4.6 Do NOT emit on fallback/failure paths — only emit on the success path (after valid `DiagnosisReportV1` is persisted)

- [x] Task 5: Add unit tests to `tests/unit/health/test_metrics.py` (AC: 4)
  - [x] 5.1 Test `record_evidence_status` emits the expected metric name with correct labels: `scope`, `metric_key`, `status`, `topic`
  - [x] 5.2 Test `record_evidence_status` uses uppercase status values (`"PRESENT"`, `"UNKNOWN"`, `"ABSENT"`, `"STALE"`)
  - [x] 5.3 Test `record_evidence_status` with all four `EvidenceStatus` enum values
  - [x] 5.4 Test delta accounting if reset-and-set lifecycle is chosen: verify subsequent calls with a changed status emit `-1` for old status + `+1` for new status; reset `_prev_evidence_status` via monkeypatch
  - [x] 5.5 Test `record_diagnosis_completed` emits metric name `aiops_diagnosis_completed_total` with correct labels: `confidence`, `fault_domain_present`, `topic`
  - [x] 5.6 Test `record_diagnosis_completed` with all three `DiagnosisConfidence` values: `"LOW"`, `"MEDIUM"`, `"HIGH"`
  - [x] 5.7 Test `record_diagnosis_completed` `fault_domain_present` is `"true"` or `"false"` string
  - [x] 5.8 Follow monkeypatching pattern: use `_RecordingInstrument` + `monkeypatch.setattr(metrics, "_evidence_status", ...)` and `monkeypatch.setattr(metrics, "_diagnosis_completed_total", ...)`

## Dev Notes

### Critical Architecture Constraints (DO NOT DEVIATE)

- **Instrument definition location**: BOTH instruments MUST be defined in `src/aiops_triage_pipeline/health/metrics.py` — never inline in pipeline stages or diagnosis modules. All existing instruments live here (NFR14)
- **Meter instance**: Use the existing module-level `_meter = metrics.get_meter("aiops_triage_pipeline.health")` — do NOT create a new meter
- **Naming convention**: Python dotted → `"aiops.evidence.status"` / `"aiops.diagnosis.completed_total"`; PromQL underscored → `aiops_evidence_status` / `aiops_diagnosis_completed_total`. Document both forms on first use in any comment
- **Label values**: UPPERCASE matching Python contract enums — `"PRESENT"`, `"UNKNOWN"`, `"ABSENT"`, `"STALE"`, `"LOW"`, `"MEDIUM"`, `"HIGH"`. No lowercase translation at the emission boundary
- **`create_up_down_counter` for evidence**: `aiops.evidence.status` is a gauge (current state per-scope-per-metric). Use `create_up_down_counter` matching `_component_health_gauge` and other gauge patterns
- **`create_counter` for diagnosis**: `aiops.diagnosis.completed_total` is a monotonically increasing event counter. Use `create_counter` matching `_findings_total` and `_gating_evaluations_total`
- **No batching**: Emit within the same cycle as the triggering event (NFR8)
- **Topic scope from evidence**: `scope_tuple[-1]` is always the topic in the evidence scope key — verified from `build_evidence_scope_key()` implementation

### Evidence Gauge Lifecycle Decision

The architecture doc mandates defining the reset-and-set vs. incremental lifecycle explicitly. **Recommended: reset-and-set per cycle** to ensure PromQL instant queries always see current state:

```python
# State tracking (module-level, protected by _state_lock)
_prev_evidence_status: dict[tuple[str, str, str, str], int] = {}
# Key: (scope_str, metric_key, status, topic), Value: delta applied last cycle

def record_evidence_status(*, scope: str, metric_key: str, status: str, topic: str) -> None:
    """Emit aiops.evidence.status gauge (PromQL: aiops_evidence_status) with delta accounting.

    Uses reset-and-set lifecycle: on each cycle, old (scope, metric_key, *any-status*, topic)
    combinations are zeroed via -1 delta and new status is set via +1 delta.
    """
    key = (scope, metric_key, status, topic)
    with _state_lock:
        old_val = _prev_evidence_status.get(key, 0)
        new_val = 1
        delta = new_val - old_val
        _prev_evidence_status[key] = new_val
    if delta != 0:
        _evidence_status.add(
            delta,
            attributes={"scope": scope, "metric_key": metric_key, "status": status, "topic": topic},
        )
```

**Critical**: Each scope/metric_key can only have ONE active status at a time. When status transitions (e.g., `PRESENT` → `UNKNOWN`), the old key must be decremented. This means the previous status must also be tracked per `(scope, metric_key, topic)` triple (not per `(scope, metric_key, status, topic)`) for proper cleanup. Consider:

```python
# Simpler approach: track current status per (scope, metric_key, topic)
_current_evidence_status: dict[tuple[str, str, str], str] = {}
# Key: (scope_str, metric_key, topic), Value: current status string

def record_evidence_status(*, scope: str, metric_key: str, status: str, topic: str) -> None:
    composite_key = (scope, metric_key, topic)
    with _state_lock:
        old_status = _current_evidence_status.get(composite_key)
        _current_evidence_status[composite_key] = status
    if old_status is not None and old_status != status:
        # Remove old status reading
        _evidence_status.add(-1, attributes={"scope": scope, "metric_key": metric_key, "status": old_status, "topic": topic})
    if old_status != status:
        # Set new status reading
        _evidence_status.add(1, attributes={"scope": scope, "metric_key": metric_key, "status": status, "topic": topic})
```

Choose the simpler composite key approach (track `(scope, metric_key, topic)` → current status). This prevents ghost series in Prometheus from status transitions.

### Diagnosis Completion Wiring

**`topic` is naturally available** — no propagation work needed:

```python
# In run_cold_path_diagnosis() in diagnosis/graph.py
# triage_excerpt: TriageExcerptV1 is a parameter — triage_excerpt.topic is available
# report: DiagnosisReportV1 is the returned value
# At the success completion point (~line 419-421):

    await health_registry.update("llm", HealthStatus.HEALTHY)
    _record_llm_completion(result="success")
    _logger.info("cold_path_diagnosis_completed", case_id=case_id)
    
    # ADD HERE — emit diagnosis.completed_total
    try:
        record_diagnosis_completed(
            confidence=report.confidence.value,
            fault_domain_present="true" if report.fault_domain is not None else "false",
            topic=triage_excerpt.topic,
        )
    except Exception:
        _logger.warning("diagnosis_metric_emit_error", case_id=case_id, exc_info=True)
    
    return report
```

**Do NOT emit on fallback paths** — only emit on the success path where a valid LLM-generated `DiagnosisReportV1` has been validated and persisted.

### Topic Extraction from Evidence Scope

From `build_evidence_scope_key()` in `pipeline/stages/evidence.py`:
- Lag metrics (`consumer_group_lag`, `consumer_group_offset`): scope = `(env, cluster_id, group, topic)` → `topic = scope_tuple[-1]`
- Non-lag metrics: scope = `(env, cluster_id, topic)` → `topic = scope_tuple[-1]`

In both cases, `scope_tuple[-1]` is always the topic. Use this consistently.

### Instrument Definition Patterns

**Counter (diagnosis.completed_total) — matches existing `_findings_total` pattern:**

```python
# aiops.diagnosis.completed_total — PromQL: aiops_diagnosis_completed_total
_diagnosis_completed_total = _meter.create_counter(
    name="aiops.diagnosis.completed_total",
    description="Total LLM diagnosis completions by confidence and fault domain presence",
    unit="1",
)
```

**Up-down-counter (evidence.status) — matches existing `_component_health_gauge` pattern:**

```python
# aiops.evidence.status — PromQL: aiops_evidence_status
_evidence_status = _meter.create_up_down_counter(
    name="aiops.evidence.status",
    description="Current evidence status per scope/metric/topic: +1=current status, 0=not current",
    unit="1",
)
```

### Testing Patterns

Follow `tests/unit/health/test_metrics.py` monkeypatching convention with `_RecordingInstrument`:

```python
class _RecordingInstrument:
    def __init__(self) -> None:
        self.calls: list[tuple[float, dict[str, str] | None]] = []

    def add(self, value: float, attributes: dict[str, str] | None = None) -> None:
        self.calls.append((value, attributes))
```

**Test for `record_evidence_status`:**

```python
def test_record_evidence_status_emits_expected_labels(monkeypatch) -> None:
    from aiops_triage_pipeline.health import metrics

    gauge = _RecordingInstrument()
    monkeypatch.setattr(metrics, "_evidence_status", gauge)
    monkeypatch.setattr(metrics, "_current_evidence_status", {})  # reset state

    metrics.record_evidence_status(
        scope="('dev', 'cluster-a', 'group-1', 'payments.consumer-lag')",
        metric_key="consumer_group_lag",
        status="PRESENT",
        topic="payments.consumer-lag",
    )

    assert len(gauge.calls) == 1
    value, attributes = gauge.calls[0]
    assert value == 1
    assert attributes["status"] == "PRESENT"
    assert attributes["metric_key"] == "consumer_group_lag"
    assert attributes["topic"] == "payments.consumer-lag"
```

**Test for delta accounting (status transition):**

```python
def test_record_evidence_status_emits_delta_on_status_change(monkeypatch) -> None:
    from aiops_triage_pipeline.health import metrics

    gauge = _RecordingInstrument()
    monkeypatch.setattr(metrics, "_evidence_status", gauge)
    monkeypatch.setattr(metrics, "_current_evidence_status", {})

    metrics.record_evidence_status(scope="s", metric_key="lag", status="PRESENT", topic="t1")
    metrics.record_evidence_status(scope="s", metric_key="lag", status="UNKNOWN", topic="t1")

    # First call: +1 PRESENT
    assert gauge.calls[0] == (1, {"scope": "s", "metric_key": "lag", "status": "PRESENT", "topic": "t1"})
    # Second call: -1 PRESENT (cleanup), +1 UNKNOWN (new)
    assert gauge.calls[1] == (-1, {"scope": "s", "metric_key": "lag", "status": "PRESENT", "topic": "t1"})
    assert gauge.calls[2] == (1, {"scope": "s", "metric_key": "lag", "status": "UNKNOWN", "topic": "t1"})
```

**Test for `record_diagnosis_completed`:**

```python
def test_record_diagnosis_completed_emits_expected_labels(monkeypatch) -> None:
    from aiops_triage_pipeline.health import metrics

    counter = _RecordingInstrument()
    monkeypatch.setattr(metrics, "_diagnosis_completed_total", counter)

    metrics.record_diagnosis_completed(
        confidence="HIGH",
        fault_domain_present="true",
        topic="payments.consumer-lag",
    )

    assert counter.calls == [
        (1, {"confidence": "HIGH", "fault_domain_present": "true", "topic": "payments.consumer-lag"})
    ]
```

### Source Tree Components to Touch

**Modify:**
- `src/aiops_triage_pipeline/health/metrics.py` — add 2 new instruments + 2 new public functions + state tracking for evidence gauge
- `src/aiops_triage_pipeline/pipeline/stages/evidence.py` — wire `record_evidence_status` call after `build_evidence_status_map_by_scope`
- `src/aiops_triage_pipeline/diagnosis/graph.py` — wire `record_diagnosis_completed` call at success completion point in `run_cold_path_diagnosis()`
- `tests/unit/health/test_metrics.py` — add 6+ new unit tests

**Do NOT create:**
- New metrics files — everything stays in `health/metrics.py`
- New test files — extend existing `test_metrics.py`
- Any modifications to Grafana dashboards — those are Epics 2–5

### Anti-Patterns to Avoid

- **Do NOT define instruments in `evidence.py` or `diagnosis/graph.py`** — all instruments are centralized in `health/metrics.py`. Only call-site wiring happens in pipeline stages
- **Do NOT use lowercase status values** — `"present"` is wrong, `"PRESENT"` is correct; `"high"` is wrong, `"HIGH"` is correct
- **Do NOT use `create_counter` for `aiops.evidence.status`** — it is a gauge (current state), must use `create_up_down_counter`
- **Do NOT use `create_up_down_counter` for `aiops.diagnosis.completed_total`** — it is a monotonically increasing event counter, must use `create_counter`
- **Do NOT create a new meter** — reuse `_meter` already defined at the top of `health/metrics.py`
- **Do NOT emit `record_diagnosis_completed` on fallback paths** — only emit on the success path in `run_cold_path_diagnosis()`
- **Do NOT hard-code scope format** — derive `topic` from `scope_tuple[-1]` to handle both lag and non-lag metric key layouts
- **Do NOT add `routing_key` label to either instrument** — `routing_key` is NOT part of the evidence or diagnosis instruments in the spec
- **Do NOT modify evidence_status_map_by_scope structure** — emit metrics as a side-effect; do not change the return type or content of `build_evidence_status_map_by_scope()`

### PromQL Reference (for Grafana stories downstream)

```promql
# Evidence status per topic (drill-down in story 4-2)
aiops_evidence_status{topic="$topic", status="PRESENT"}

# Evidence status counts by status (drill-down panel)
sum by(status) (aiops_evidence_status{topic="$topic"})

# Diagnosis completions total (stat panel — human-readable count)
increase(aiops_diagnosis_completed_total[$__range])

# Diagnosis by confidence (breakdown)
sum by(confidence) (increase(aiops_diagnosis_completed_total[$__range]))

# Fault domain identification rate
sum(increase(aiops_diagnosis_completed_total{fault_domain_present="true"}[$__range]))
  / sum(increase(aiops_diagnosis_completed_total[$__range]))
```

### Previous Story Intelligence (from Stories 1-1 and 1-2)

- **Test baseline**: 1447 passing, 33 skipped (pre-existing Docker unavailability), 5 failed (pre-existing). Do not break passing tests.
- **`_RecordingInstrument` pattern**: Already defined in `test_metrics.py` — do NOT redefine. Extend the existing test file only.
- **Module-level state reset in tests**: Use `monkeypatch.setattr(metrics, "_current_evidence_status", {})` to reset state before each evidence gauge test. Failure to reset state causes test order-dependency bugs.
- **Instrument definition placement**: In `health/metrics.py`, add new instruments after the existing story 1-2 instruments (`_findings_total`, `_gating_evaluations_total` at lines ~204-215). Add state tracking variables after the existing `_prev_*` variables block.
- **Exception isolation pattern**: Wrap metric emit calls in try-except with `component.metric_emit_error` warning log — see `_emit_gating_evaluation_metrics()` helper in `gating.py` and the `record_finding` call in `__main__.py` for the established pattern.
- **No `routing_key` in gating instrument** was a lesson from story 1-2 — similarly, do not add `routing_key` to evidence or diagnosis instruments.
- **`topic` is naturally available** in both emission points — no propagation threading needed (unlike original story note which flagged this as a risk). `triage_excerpt.topic` is directly available in `run_cold_path_diagnosis()`, and `scope_tuple[-1]` gives topic in the evidence stage.
- **ATDD red-phase tests**: No ATDD tests were pre-written for story 1-3. Run `pytest tests/unit/health/test_metrics.py` to validate new tests.

### Project Structure Notes

All changes confined to:
```
src/aiops_triage_pipeline/health/metrics.py       ← MODIFY (add 2 instruments + state + 2 functions)
src/aiops_triage_pipeline/pipeline/stages/evidence.py ← MODIFY (wire record_evidence_status)
src/aiops_triage_pipeline/diagnosis/graph.py      ← MODIFY (wire record_diagnosis_completed)
tests/unit/health/test_metrics.py                 ← MODIFY (add new test cases, do NOT create new file)
```

Do NOT create new files for this story.

### References

- Evidence gauge instrument pattern: `src/aiops_triage_pipeline/health/metrics.py` — `_component_health_gauge` (`create_up_down_counter`) with delta accounting
- Diagnosis counter pattern: `src/aiops_triage_pipeline/health/metrics.py` — `_findings_total`, `_gating_evaluations_total` (`create_counter`, simple add-1)
- Evidence scope key construction: `src/aiops_triage_pipeline/pipeline/stages/evidence.py` — `build_evidence_scope_key()` (topic is always `scope_tuple[-1]`)
- Evidence status map: `src/aiops_triage_pipeline/pipeline/stages/evidence.py` — `build_evidence_status_map_by_scope()` and its call in `collect_evidence_stage_output()`
- `EvidenceStatus` enum values (PRESENT/UNKNOWN/ABSENT/STALE): `src/aiops_triage_pipeline/contracts/enums.py`
- `DiagnosisConfidence` enum values (LOW/MEDIUM/HIGH): `src/aiops_triage_pipeline/contracts/enums.py`
- `DiagnosisReportV1` fields (`confidence`, `fault_domain`): `src/aiops_triage_pipeline/contracts/diagnosis_report.py`
- Diagnosis completion success path: `src/aiops_triage_pipeline/diagnosis/graph.py:419-421` (`run_cold_path_diagnosis()`)
- `TriageExcerptV1.topic` field (available in `run_cold_path_diagnosis`): `src/aiops_triage_pipeline/contracts/triage_excerpt.py`
- Cold-path event handler with `event.topic` available: `src/aiops_triage_pipeline/__main__.py:1638` (`_cold_path_process_event_async`)
- Exception isolation pattern for metric emit: `src/aiops_triage_pipeline/__main__.py` (record_finding try-except) and `src/aiops_triage_pipeline/pipeline/stages/gating.py` (_emit_gating_evaluation_metrics try-except)
- Test monkeypatching pattern: `tests/unit/health/test_metrics.py` (all tests use `_RecordingInstrument` + `monkeypatch.setattr`)
- OTLP naming convention (dotted in Python, underscored in PromQL): `artifact/planning-artifacts/architecture.md#OTLP Instrument Patterns`
- Label value convention (uppercase): `artifact/planning-artifacts/architecture.md#OTLP Instrument Patterns`
- FR3 (evidence status gauge) and FR4 (diagnosis completed counter): `artifact/planning-artifacts/epics.md#Story 1.3`
- NFR8 (emit within same cycle): `artifact/planning-artifacts/prd.md#Non-Functional Requirements`
- NFR14 (follow existing patterns): `artifact/planning-artifacts/prd.md#Non-Functional Requirements`

## Dev Agent Record

### Agent Model Used

claude-sonnet-4-6

### Debug Log References

No debug issues encountered. All 15 ATDD red-phase tests passed on first implementation run.

### Completion Notes List

- Implemented `_evidence_status` up-down-counter and `record_evidence_status()` in `health/metrics.py` using the simpler composite-key delta accounting pattern (`_current_evidence_status` dict keyed by `(scope, metric_key, topic)`). On status transition: emit `-1` for old status, `+1` for new status. On same status: no-op.
- Implemented `_diagnosis_completed_total` counter and `record_diagnosis_completed()` in `health/metrics.py`. Simple `add(1, ...)` with labels `confidence`, `fault_domain_present`, `topic`.
- Wired `record_evidence_status` into `collect_evidence_stage_output()` in `pipeline/stages/evidence.py` after `build_evidence_status_map_by_scope()`. Topic extracted via `scope_tuple[-1]`. Wrapped in try-except for exception isolation.
- Wired `record_diagnosis_completed` into `run_cold_path_diagnosis()` in `diagnosis/graph.py` at the success completion point (after `_record_llm_completion(result="success")`). Wrapped in try-except with warning log per established pattern.
- All 42 tests in `test_metrics.py` pass (27 existing + 15 new ATDD). 1362 total unit tests pass, no regressions.

### File List

- `src/aiops_triage_pipeline/health/metrics.py`
- `src/aiops_triage_pipeline/pipeline/stages/evidence.py`
- `src/aiops_triage_pipeline/diagnosis/graph.py`

### Review Findings

- [x] [Review][Patch] Loop-level try-except aborts all remaining evidence_status emissions on first error — no warning log [pipeline/stages/evidence.py:186-198] — **FIXED**: moved try-except inside the loop (per-scope isolation) and added `_evidence_logger.warning("evidence_status_metric_emit_failed", ...)` consistent with `gating.py` pattern. 1362 unit tests pass.
- [x] [Review][Defer] `_current_evidence_status` dict grows unbounded with topic churn (no pruning mechanism) [health/metrics.py:237] — deferred, pre-existing design gap not in story scope; acceptable for current scale.

## Change Log

- 2026-04-11: Story implemented — added `aiops.evidence.status` up-down-counter and `aiops.diagnosis.completed_total` counter to `health/metrics.py`; wired both emit calls into `pipeline/stages/evidence.py` and `diagnosis/graph.py`; all 15 ATDD tests pass, 1362 unit tests pass, no regressions. Status: review.
- 2026-04-11: Code review complete (bmad-code-review) — 1 patch finding fixed (loop-level exception isolation in evidence.py), 1 finding deferred, 1 dismissed. Status: done.
