# Story 1.2: Findings & Gating OTLP Instruments

Status: done

## Story

As a platform engineer,
I want the pipeline to emit OTLP counters for findings and gating evaluations with business-level labels,
so that Prometheus captures how many anomalies are detected, what actions are taken, and which gate rules evaluate each finding.

## Acceptance Criteria

1. **Given** the pipeline processes an anomaly through gating and dispatch **When** an action decision is made (post-`ActionDecisionV1`) **Then** the `aiops.findings.total` counter increments by 1 with labels: `anomaly_family`, `final_action`, `topic`, `routing_key`, `criticality_tier` **And** label values use uppercase matching Python contract enums (e.g., `BASELINE_DEVIATION`, `NOTIFY`) **And** the instrument is defined in `health/metrics.py` using `create_counter`

2. **Given** the rule engine evaluates a gate rule **When** a gating evaluation completes **Then** the `aiops.gating.evaluations_total` counter increments by 1 with labels: `gate_id`, `outcome`, `topic` **And** the `topic` label is available at the emission point in `pipeline/stages/gating.py` **And** the instrument is defined in `health/metrics.py` using `create_counter`

3. **Given** both instruments are defined **When** metrics are emitted during a pipeline cycle **Then** metrics are emitted within the same cycle as the triggering event — no deferred or batched emission (NFR8) **And** the instruments follow existing patterns in `health/metrics.py` (NFR14)

4. **Given** the new instruments are defined **When** unit tests in `tests/unit/health/test_metrics.py` are executed **Then** each instrument emits the expected metric name and label set **And** tests assert on metric name + label set, not raw string output

## Tasks / Subtasks

- [x] Task 1: Add `aiops.findings.total` counter to `health/metrics.py` (AC: 1, 3)
  - [x] 1.1 Define `_findings_total` counter using `_meter.create_counter("aiops.findings.total", ...)` following existing patterns
  - [x] 1.2 Implement `record_finding(*, anomaly_family: str, final_action: str, topic: str, routing_key: str, criticality_tier: str) -> None` function
  - [x] 1.3 Emit with uppercase label values: `anomaly_family` (e.g., `"BASELINE_DEVIATION"`), `final_action` (e.g., `"NOTIFY"`), `criticality_tier` (e.g., `"TIER_0"`)

- [x] Task 2: Add `aiops.gating.evaluations_total` counter to `health/metrics.py` (AC: 2, 3)
  - [x] 2.1 Define `_gating_evaluations_total` counter using `_meter.create_counter("aiops.gating.evaluations_total", ...)`
  - [x] 2.2 Implement `record_gating_evaluation(*, gate_id: str, outcome: str, topic: str) -> None` function
  - [x] 2.3 Verify that `outcome` values are defined: use `"pass"` / `"fail"` / `"skip"` (or the exact string available from the gate evaluation result — verify against `_apply_gate_effect` in `gating.py`)

- [x] Task 3: Wire `record_finding` call into the pipeline (AC: 1, 3)
  - [x] 3.1 Identify the correct call site — the post-`ActionDecisionV1` point where `topic`, `anomaly_family`, `routing_key`, and `criticality_tier` are simultaneously available; this is after `evaluate_rulebook_gate_inputs_by_scope` in the scheduler, where `gate_inputs_by_scope` and `decisions_by_scope` are both in scope
  - [x] 3.2 Loop over `decisions_by_scope` alongside `gate_inputs_by_scope` to emit one counter increment per `ActionDecisionV1` (one finding per input)
  - [x] 3.3 Extract `topic` from `gate_input.topic`, `anomaly_family` from `gate_input.anomaly_family`, `routing_key` from the `TopologyRoutingContext` (or dispatch routing key), and `criticality_tier` from `gate_input.criticality_tier.value`
  - [x] 3.4 Extract `final_action` from `decision.final_action.value` (already uppercase via `Action(str, Enum)`)

- [x] Task 4: Wire `record_gating_evaluation` call into gate evaluation (AC: 2, 3)
  - [x] 4.1 Confirm `topic` availability inside `evaluate_rulebook_gates` — it is on `gate_input.topic` (confirmed: `GateInputV1.topic: str` field present)
  - [x] 4.2 Emit `record_gating_evaluation` once per gate evaluation per gate ID after each gate's effect is applied inside `evaluate_rulebook_gates` in `gating.py`
  - [x] 4.3 The `outcome` should reflect whether the gate fired/suppressed (map from `_apply_gate_effect` behavior) — determine the canonical outcome string values before implementing
  - [x] 4.4 Alternatively (if gating.py is too complex to instrument inline): emit after `evaluate_rulebook_gate_inputs_by_scope` returns by diffing `gate_reason_codes` on each `ActionDecisionV1` against the expected gate IDs

- [x] Task 5: Add unit tests to `tests/unit/health/test_metrics.py` (AC: 4)
  - [x] 5.1 Test `record_finding` emits metric name `aiops_findings_total` with correct labels: `anomaly_family`, `final_action`, `topic`, `routing_key`, `criticality_tier`
  - [x] 5.2 Test `record_finding` uses uppercase label values (assert exact string values match enum `.value` output)
  - [x] 5.3 Test `record_gating_evaluation` emits metric name `aiops_gating_evaluations_total` with labels: `gate_id`, `outcome`, `topic`
  - [x] 5.4 Follow monkeypatching pattern from existing tests (patch private counter instrument, verify `.calls` list)

## Dev Notes

### Critical Architecture Constraints (DO NOT DEVIATE)

- **Instrument definition location**: BOTH instruments MUST be defined in `src/aiops_triage_pipeline/health/metrics.py` — never inline in pipeline stages. All existing instruments live here (NFR14)
- **Meter instance**: Use the existing module-level `_meter = metrics.get_meter("aiops_triage_pipeline.health")` — do NOT create a new meter
- **Naming convention**: Python dotted → `"aiops.findings.total"` / `"aiops.gating.evaluations_total"`; PromQL underscored → `aiops_findings_total` / `aiops_gating_evaluations_total`. Document both forms on first use in any comment
- **Label values**: UPPERCASE matching Python `Action`, `CriticalityTier`, and `_AnomalyFamily` contract values — no lowercase translation at the emission boundary. Grafana queries reference identical values: `{final_action="NOTIFY"}`
- **`create_counter` ONLY**: Both instruments are counters (monotonically increasing totals). Never use `create_up_down_counter` for these — that is reserved for gauges like `aiops.evidence.status` (story 1-3)
- **No batching**: Emit within the same cycle as the triggering event. Do not accumulate and flush (NFR8)

### Key Data Sources at Emission Points

**For `aiops.findings.total`** (emit post-`ActionDecisionV1`):

The correct call site is inside `run_gate_decision_stage_cycle` in `scheduler.py` (after `evaluate_rulebook_gate_inputs_by_scope` returns `decisions_by_scope`). At that point both `gate_inputs_by_scope` and `decisions_by_scope` are available. Label extraction:

```python
# GateInputV1 fields (gate_input.topic, .anomaly_family, .criticality_tier):
gate_input.topic           # str — Kafka topic name (e.g., "payments.consumer-lag")
gate_input.anomaly_family  # Literal["CONSUMER_LAG", "VOLUME_DROP", "THROUGHPUT_CONSTRAINED_PROXY", "BASELINE_DEVIATION"]
gate_input.criticality_tier.value  # str — "TIER_0" or "TIER_1"

# ActionDecisionV1 fields (decision.final_action):
decision.final_action.value  # str — "OBSERVE", "NOTIFY", "TICKET", or "PAGE"
```

`routing_key` is NOT on `GateInputV1` directly — it is on `TopologyRoutingContext` (available in the dispatch call). Two options:
1. Thread `routing_key` through by pairing `gate_inputs_by_scope` with the routing context map in the scheduler — preferred if routing context is available at the same scope
2. Emit `record_finding` from `dispatch_action` in `dispatch.py` where `topology_routing_key` is already extracted — this is clean and co-located with the dispatch event

Option 2 is likely cleaner but requires passing additional args (`anomaly_family`, `topic`, `criticality_tier`) to `dispatch_action`. Verify what's available and choose the minimal-change approach. If `dispatch_action` receives `gate_input` or a subset, that's the right hook.

**For `aiops.gating.evaluations_total`** (emit per gate evaluation):

Inside `evaluate_rulebook_gates` in `gating.py`, the `gate_input.topic` is directly available. Emit once per gate ID at each relevant gate evaluation point:

```python
# gate_id examples: "AG0", "AG1", "AG2", "AG3", "AG4", "AG5", "AG6"
# outcome: define as "pass" or "fail" (or "skip" if gate is skipped)
# topic: gate_input.topic
```

The `_EXPECTED_GATE_ORDER` tuple defines all gate IDs. The early gates (AG0–AG3) are evaluated via `evaluate_gates` from `rule_engine`. Per-gate outcome visibility inside `evaluate_rulebook_gates` may be limited for AG0–AG3; consider emitting on each late-gate branch (AG4/AG5/AG6) for the inline gates, and using a post-evaluation diff approach for AG0–AG3 (compare `gate_reason_codes` against expected gate IDs to determine which fired).

Alternative simpler approach: emit `record_gating_evaluation` from within `evaluate_rulebook_gate_inputs_by_scope` once per (scope, gate_input) pair, after `evaluate_rulebook_gates` returns, using the `ActionDecisionV1.gate_reason_codes` to infer per-gate outcomes. This keeps the emission point clean and avoids instrumenting the inner gate evaluation loop.

### Existing Patterns to Follow

From `health/metrics.py` — instrument definition pattern (counter):

```python
_findings_total = _meter.create_counter(
    name="aiops.findings.total",
    description="Total findings by anomaly family, final action, topic, routing key, and criticality tier",
    unit="1",
)
```

Public function pattern (no state tracking needed for simple counters):

```python
def record_finding(
    *,
    anomaly_family: str,
    final_action: str,
    topic: str,
    routing_key: str,
    criticality_tier: str,
) -> None:
    _findings_total.add(
        1,
        attributes={
            "anomaly_family": anomaly_family,
            "final_action": final_action,
            "topic": topic,
            "routing_key": routing_key,
            "criticality_tier": criticality_tier,
        },
    )
```

No delta accounting, no `_state_lock`, no `_prev_*` tracking needed — these are simple event counters (unlike `_component_health_gauge` which uses delta accounting for up-down-counter semantics).

### Testing Pattern

Follow `tests/unit/health/test_metrics.py` monkeypatching convention:

```python
class _RecordingInstrument:
    def __init__(self) -> None:
        self.calls: list[tuple[float, dict[str, str] | None]] = []

    def add(self, value: float, attributes: dict[str, str] | None = None) -> None:
        self.calls.append((value, attributes))
```

Test example for `record_finding`:

```python
def test_record_finding_emits_expected_labels(monkeypatch) -> None:
    from aiops_triage_pipeline.health import metrics

    counter = _RecordingInstrument()
    monkeypatch.setattr(metrics, "_findings_total", counter)

    metrics.record_finding(
        anomaly_family="BASELINE_DEVIATION",
        final_action="NOTIFY",
        topic="payments.consumer-lag",
        routing_key="payments-team",
        criticality_tier="TIER_0",
    )

    assert counter.calls == [
        (
            1,
            {
                "anomaly_family": "BASELINE_DEVIATION",
                "final_action": "NOTIFY",
                "topic": "payments.consumer-lag",
                "routing_key": "payments-team",
                "criticality_tier": "TIER_0",
            },
        )
    ]
```

Test that uppercase label values are emitted as-is (no lowercasing). Test both instruments. Test that `record_gating_evaluation` includes `gate_id`, `outcome`, and `topic`.

### Source Tree Components to Touch

**Modify:**
- `src/aiops_triage_pipeline/health/metrics.py` — add 2 new instruments + 2 new public functions
- `src/aiops_triage_pipeline/pipeline/scheduler.py` OR `src/aiops_triage_pipeline/pipeline/stages/gating.py` — wire `record_finding` and `record_gating_evaluation` call sites
- `tests/unit/health/test_metrics.py` — add 4+ new unit tests

**Do NOT create:**
- New metrics files — everything stays in `health/metrics.py`
- New test files — extend existing `test_metrics.py`
- Any evidence or diagnosis instruments — those are story 1-3

### PromQL Reference (for Grafana stories downstream)

These instruments will be queried as:

```promql
# Findings total (stat panel — human-readable count over time window)
increase(aiops_findings_total[$__range])

# Findings by action (for gating funnel panels in stories 3-x)
sum by(final_action) (increase(aiops_findings_total[$__range]))

# Gating evaluations by gate and outcome (gating funnel in story 3-1)
sum by(gate_id, outcome) (increase(aiops_gating_evaluations_total[$__range]))

# Gating evaluations per topic (for drill-down in story 4-x)
sum by(gate_id, outcome) (increase(aiops_gating_evaluations_total{topic="$topic"}[$__range]))
```

### Previous Story Intelligence (from Story 1-1)

- The `aiops-pipeline` Prometheus scrape job targeting `app:8080` at 15s interval is **already configured** in `config/prometheus.yml` — story 1-1 added it. The scrape will produce "no data" errors until these instruments emit, which is expected and was documented.
- The health server (`health/server.py`) already binds to `0.0.0.0:8080` — the `/metrics` endpoint will activate as soon as the OTLP SDK initializes with these new instruments.
- Integration test file `tests/integration/test_dashboard_validation.py` already exists from story 1-1. Do not modify it — the panel validation tests there require live-stack data from stories 2–5.
- No `grafana/` or docker-compose changes needed — infrastructure is done.
- Pattern for module-level `importlib` reloading in tests: existing `test_metrics.py` does NOT reload the module — it uses monkeypatching on the already-imported module. Follow this pattern.
- All 1395 tests were passing after story 1-1. Do not break existing tests.
- Test suite uses `pytest` with `pytest-asyncio`. The health metrics tests are synchronous (no async needed).

### Anti-Patterns to Avoid

- **Do NOT define instruments in `gating.py` or `dispatch.py`** — all instruments are centralized in `health/metrics.py`. Only call-site wiring happens in pipeline stages.
- **Do NOT use lowercase label values** — `"notify"` is wrong, `"NOTIFY"` is correct. Grafana queries downstream reference uppercase values.
- **Do NOT add `routing_key` to the `aiops.gating.evaluations_total` instrument** — it is only on `aiops.findings.total`. The gating instrument labels are: `gate_id`, `outcome`, `topic` only.
- **Do NOT create a new meter** — reuse `_meter` already defined at the top of `health/metrics.py`.
- **Do NOT emit the `aiops.evidence.status` or `aiops.diagnosis.completed_total` instruments** — those are story 1-3.
- **Do NOT use `create_up_down_counter` for these instruments** — they are monotonically increasing event counters.

### Project Structure — Files to Modify

```
src/aiops_triage_pipeline/health/metrics.py       ← MODIFY (add 2 instruments + 2 functions)
src/aiops_triage_pipeline/pipeline/scheduler.py   ← MODIFY (wire record_finding call site)
  OR
src/aiops_triage_pipeline/pipeline/stages/gating.py ← MODIFY (wire record_gating_evaluation)
tests/unit/health/test_metrics.py                 ← MODIFY (add new test cases)
```

Do NOT create new files for this story.

### References

- Instrument definition patterns: `src/aiops_triage_pipeline/health/metrics.py` (all existing counters follow the same create_counter pattern)
- GateInputV1 contract with all available fields including `topic`, `anomaly_family`, `criticality_tier`: `src/aiops_triage_pipeline/contracts/gate_input.py`
- ActionDecisionV1 contract with `final_action` and `gate_reason_codes`: `src/aiops_triage_pipeline/contracts/action_decision.py`
- Gate evaluation entry point and `_EXPECTED_GATE_ORDER`: `src/aiops_triage_pipeline/pipeline/stages/gating.py:96` (`evaluate_rulebook_gates`)
- Dispatch stage with `topology_routing_key` extraction: `src/aiops_triage_pipeline/pipeline/stages/dispatch.py:44`
- Gate inputs wired in scheduler: `src/aiops_triage_pipeline/pipeline/scheduler.py:459` (`evaluate_rulebook_gate_inputs_by_scope` loop)
- Action enum values (OBSERVE/NOTIFY/TICKET/PAGE): `src/aiops_triage_pipeline/contracts/enums.py:21`
- CriticalityTier values (TIER_0/TIER_1): `src/aiops_triage_pipeline/contracts/enums.py:14`
- Test monkeypatching pattern: `tests/unit/health/test_metrics.py` (all tests use `_RecordingInstrument` + `monkeypatch.setattr`)
- OTLP naming convention (dotted in Python, underscored in PromQL): `artifact/planning-artifacts/architecture.md#OTLP Instrument Patterns`
- Label value convention (uppercase): `artifact/planning-artifacts/architecture.md#OTLP Instrument Patterns`
- FR1 (findings counter) and FR2 (gating evaluations counter): `artifact/planning-artifacts/epics.md#Story 1.2`
- NFR8 (emit within same cycle): `artifact/planning-artifacts/prd.md#Non-Functional Requirements`
- NFR14 (follow existing patterns): `artifact/planning-artifacts/prd.md#Non-Functional Requirements`

## Dev Agent Record

### Agent Model Used

claude-sonnet-4-6

### Debug Log References

None — implementation was straightforward following existing patterns.

### Completion Notes List

- Implemented `_findings_total` counter and `record_finding()` in `health/metrics.py` using `create_counter` following existing counter patterns. Labels: `anomaly_family`, `final_action`, `topic`, `routing_key`, `criticality_tier` (all uppercase as-is from enum contracts).
- Implemented `_gating_evaluations_total` counter and `record_gating_evaluation()` in `health/metrics.py`. Labels: `gate_id`, `outcome`, `topic`. No `routing_key` (per AC2/anti-patterns).
- Wired `record_finding` in `__main__.py` (line ~1235) immediately after `dispatch_action` call, where `gate_input`, `decision`, and `routing_context` are all in scope. Extracts `routing_key` from `routing_context.routing_key` (falls back to `"unknown"` if None).
- Wired `record_gating_evaluation` in `gating.py` via new `_emit_gating_evaluation_metrics()` helper called from `evaluate_rulebook_gate_inputs_by_scope` after each `evaluate_rulebook_gates` returns. Emits once per gate ID (AG0–AG6) per gate input, inferring outcome from `gate_reason_codes` prefixes: `"fail"` if matching prefix in reason codes, `"skip"` for action-priority guards (AG4/AG5/AG6), `"pass"` otherwise.
- All 12 ATDD red-phase tests now pass. All 1397 unit+non-integration tests pass (no regressions). Integration test failures are pre-existing (require external services: Redis, Kafka, Prometheus).

### File List

- `src/aiops_triage_pipeline/health/metrics.py` — added `_findings_total` counter, `_gating_evaluations_total` counter, `record_finding()`, `record_gating_evaluation()`
- `src/aiops_triage_pipeline/__main__.py` — added `record_finding` import; wired `record_finding` call after `dispatch_action`
- `src/aiops_triage_pipeline/pipeline/stages/gating.py` — added `record_gating_evaluation` import; refactored `evaluate_rulebook_gate_inputs_by_scope` to emit per-gate metrics via `_emit_gating_evaluation_metrics()` helper

### Review Findings

- [x] [Review][Patch] AG6 outcome always emits "skip" — `on_pass`/`on_fail` write to `postmortem_reason_codes` not `gate_reason_codes`, so `startswith("AG6")` check always false [gating.py:314-316] — **FIXED**: rewrote AG6 branch to use `decision.postmortem_required` + `ag6_eligible` (derived from `gate_input.env`, `gate_input.criticality_tier`, and AG0 firing status)
- [x] [Review][Patch] `record_finding` inside broad try-except — OTLP raise triggers false `hot_path_case_processing_failed` error log [__main__.py:1236-1244] — **FIXED**: wrapped `record_finding` in its own try-except with `hot_path.finding_metric_error` warning
- [x] [Review][Patch] `_emit_gating_evaluation_metrics` unguarded — OTLP SDK exception propagates to caller and disrupts gate evaluation loop [gating.py:320] — **FIXED**: wrapped `record_gating_evaluation` call in per-gate try-except with `gating.metric_emit_error` warning
- [x] [Review][Patch] `_gate_reason_prefixes` dict rebuilt on every call (7 per gate_input) — should be module-level constant [gating.py:288-293] — **FIXED**: extracted to module-level `_EARLY_GATE_REASON_PREFIXES` constant

## Change Log

- 2026-04-11: Implemented story 1-2 — added `aiops.findings.total` and `aiops.gating.evaluations_total` OTLP counters to `health/metrics.py`, wired call sites in `__main__.py` and `gating.py`. All 12 ATDD tests pass.
- 2026-04-11: Code review (bmad-code-review) — 4 findings fixed: AG6 outcome logic corrected, `record_finding` metric-emit exception isolation, `_emit_gating_evaluation_metrics` exception guard, `_gate_reason_prefixes` extracted to module-level constant. 1347 unit tests pass.
