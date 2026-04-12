# Story 3.3: LLM Diagnosis Engine Statistics

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a stakeholder evaluating AI capabilities,
I want to see LLM diagnosis engine statistics including invocation count, success rate, latency, confidence distribution, and fault domain identification rate,
so that I can confirm the AI-powered diagnosis layer is live, performing well, and producing useful hypotheses.

## Acceptance Criteria

1. **Given** the main dashboard is scrolled to the operational zone **When** the diagnosis stats panels render at rows 36-40 (12 cols, right — paired with capability stack) **Then** grouped stat panels display: invocation count, success rate (percentage), and average latency (FR14) **And** the queries use `increase(aiops_diagnosis_completed_total[$__range])` for counts and appropriate aggregations for rate and latency

2. **Given** the diagnosis stats panels render **When** confidence distribution is displayed **Then** the distribution of confidence levels (from `aiops_diagnosis_completed_total` labels) is visible (FR15) **And** fault domain identification rate is displayed as a percentage of diagnoses where `fault_domain_present` is `"true"` (FR15)

3. **Given** no diagnoses have been completed in the time window **When** the panels render **Then** zero invocations display as a legitimate zero in semantic-grey with "No diagnoses this period" (UX-DR5)

4. **Given** all panels are configured **When** the dashboard JSON is inspected **Then** stat panel values use 28px+ text size for below-the-fold secondary values (UX-DR2) **And** panels use transparent backgrounds with one-sentence descriptions (UX-DR4, UX-DR12) **And** panel IDs are within 1-99 range

## Tasks / Subtasks

- [x] Task 1: Add invocation count stat panel to `grafana/dashboards/aiops-main.json` (AC: 1, 3, 4)
  - [x] 1.1 Add stat panel: `type: "stat"`, `id: 10`, `gridPos: {h: 2, w: 12, x: 12, y: 36}`
  - [x] 1.2 Set panel `title: "Diagnosis invocations"` (sentence case per architecture convention)
  - [x] 1.3 Set `"transparent": true` on the panel
  - [x] 1.4 Add target `refId: "A"`: `sum(increase(aiops_diagnosis_completed_total[$__range]))` with `legendFormat: "Invocations"`
  - [x] 1.5 Set `datasource: {type: "prometheus", uid: "prometheus"}` on both panel and target
  - [x] 1.6 Configure `options.colorMode: "none"` and `fieldConfig.defaults.color.mode: "fixed"` with `fixedColor: "#7A7A7A"` (semantic-grey for neutral count)
  - [x] 1.7 Set `options.textMode: "value"` and `options.text.valueSize: 28` (UX-DR2 — 28px+ for secondary values)
  - [x] 1.8 Set `fieldConfig.defaults.noValue: "0"` so zero invocations display as `0`, not blank (UX-DR5)
  - [x] 1.9 Set panel `description` to one sentence (UX-DR12)

- [x] Task 2: Add fault domain identification rate stat panel to `grafana/dashboards/aiops-main.json` (AC: 2, 4) — replaces "success rate" (no outcome label on metric)
  - [x] 2.1 Add stat panel: `type: "stat"`, `id: 11`, `gridPos: {h: 2, w: 12, x: 12, y: 38}`
  - [x] 2.2 Set panel `title: "Fault domain identification rate"` (sentence case)
  - [x] 2.3 Set `"transparent": true` on the panel
  - [x] 2.4 Add target `refId: "A"` for fault domain rate using `fault_domain_present="true"` filter with `legendFormat: "Fault domain rate"`
  - [x] 2.5 Set `datasource: {type: "prometheus", uid: "prometheus"}` on both panel and target
  - [x] 2.6 Configure `fieldConfig.defaults.unit: "percentunit"` to render as percentage
  - [x] 2.7 Configure thresholds: 0 → semantic-grey `#7A7A7A`, 0.5 → semantic-amber `#E8913A`, 0.8 → semantic-green `#6BAD64`
  - [x] 2.8 Set `fieldConfig.defaults.color.mode: "thresholds"` with `options.colorMode: "background"`
  - [x] 2.9 Set `options.text.valueSize: 28` (UX-DR2)
  - [x] 2.10 Set `fieldConfig.defaults.noValue: "0"` (UX-DR5)
  - [x] 2.11 Set panel `description` to one sentence (UX-DR12)

- [x] Task 3: Add confidence distribution barchart panel to `grafana/dashboards/aiops-main.json` (AC: 2, 4)
  - [x] 3.1 Add barchart panel: `type: "barchart"`, `id: 12`, `gridPos: {h: 3, w: 12, x: 12, y: 40}`
  - [x] 3.2 Set panel `title: "Confidence distribution"` (sentence case)
  - [x] 3.3 Set `"transparent": true` on the panel
  - [x] 3.4 Add target `refId: "A"`: `sum by(confidence) (increase(aiops_diagnosis_completed_total[$__range]))` with `legendFormat: "{{confidence}}"`
  - [x] 3.5 Set `datasource: {type: "prometheus", uid: "prometheus"}` on both panel and target
  - [x] 3.6 Configure `options.orientation: "horizontal"` for horizontal bars (UX-DR3)
  - [x] 3.7 Configure `options.sort: "desc"` (sorted by value per AC2 pattern)
  - [x] 3.8 Set `fieldConfig.defaults.color.mode: "thresholds"` — thresholds: grey `#7A7A7A` (base), green `#6BAD64` for positive counts
  - [x] 3.9 Set `options.text.titleSize: 14` and `options.text.valueSize: 14` (UX-DR2)
  - [x] 3.10 Set `fieldConfig.defaults.noValue: "0"` (UX-DR5, NFR9)
  - [x] 3.11 Set panel `description` to one sentence (UX-DR12)

- [x] Task 4: Add high-confidence rate stat panel to `grafana/dashboards/aiops-main.json` (AC: 2, 4)
  - [x] 4.1 Add stat panel: `type: "stat"`, `id: 13`, `gridPos: {h: 2, w: 12, x: 12, y: 43}`
  - [x] 4.2 Set panel `title: "High confidence rate"` (sentence case)
  - [x] 4.3 Set `"transparent": true` on the panel
  - [x] 4.4 Add target `refId: "A"` using `confidence="HIGH"` filter for high-confidence rate with `legendFormat: "High confidence rate"`
  - [x] 4.5 Set `datasource: {type: "prometheus", uid: "prometheus"}` on both panel and target
  - [x] 4.6 Configure `fieldConfig.defaults.unit: "percentunit"` to render as percentage
  - [x] 4.7 Configure thresholds: 0 → semantic-grey `#7A7A7A`, 0.5 → semantic-amber `#E8913A`, 0.7 → semantic-green `#6BAD64`
  - [x] 4.8 Set `fieldConfig.defaults.color.mode: "thresholds"` with `options.colorMode: "background"`
  - [x] 4.9 Set `options.text.valueSize: 28` (UX-DR2)
  - [x] 4.10 Set `fieldConfig.defaults.noValue: "0"` (UX-DR5)
  - [x] 4.11 Set panel `description` to one sentence (UX-DR12)

- [x] Task 5: Finalize dashboard version bump (AC: 4)
  - [x] 5.1 Bump dashboard top-level `"version"` from `6` to `7`
  - [x] 5.2 Verify `"uid": "aiops-main"` unchanged, `"schemaVersion": 39` unchanged
  - [x] 5.3 Verify existing panels (id=1 through id=9) are not modified

- [x] Task 6: Add config-validation tests for all panels (AC: 1, 2, 3, 4)
  - [x] 6.1 Extend `tests/integration/test_dashboard_validation.py` with class `TestLLMDiagnosisEngineStatistics`
  - [x] 6.2 Test: invocation count panel (id=10) exists, type="stat"
  - [x] 6.3 Test: invocation count panel gridPos y=36, h=2, w=12, x=12
  - [x] 6.4 Test: invocation count panel has `transparent: true` (UX-DR4)
  - [x] 6.5 Test: invocation count panel target refId="A" PromQL uses `increase(` and `$__range`
  - [x] 6.6 Test: invocation count panel target PromQL uses `aiops_diagnosis_completed_total`
  - [x] 6.7 Test: invocation count panel has non-empty description (UX-DR12)
  - [x] 6.8 Test: invocation count panel has `noValue` field set (NFR5 / UX-DR5)
  - [x] 6.9 Test: invocation count panel `options.text.valueSize` >= 28 (UX-DR2)
  - [x] 6.10 Test: no forbidden Grafana default palette colors in panel id=10 JSON (case-insensitive `.upper()`)
  - [x] 6.11 Test: fault domain rate panel (id=11) exists, type="stat"
  - [x] 6.12 Test: fault domain rate panel gridPos y=38, h=2, w=12, x=12
  - [x] 6.13 Test: fault domain rate panel has `transparent: true` (UX-DR4)
  - [x] 6.14 Test: fault domain rate panel target PromQL uses `aiops_diagnosis_completed_total`
  - [x] 6.15 Test: fault domain rate panel target PromQL uses `fault_domain_present` label filter
  - [x] 6.16 Test: fault domain rate panel has non-empty description (UX-DR12)
  - [x] 6.17 Test: fault domain rate panel has `noValue` field set (NFR5 / UX-DR5)
  - [x] 6.18 Test: no forbidden Grafana default palette colors in panel id=11 JSON (case-insensitive `.upper()`)
  - [x] 6.19 Test: confidence distribution panel (id=12) exists, type="barchart"
  - [x] 6.20 Test: confidence distribution panel gridPos y=40, h=3, w=12, x=12
  - [x] 6.21 Test: confidence distribution panel has `transparent: true` (UX-DR4)
  - [x] 6.22 Test: confidence distribution panel target PromQL uses `increase(` and `$__range`
  - [x] 6.23 Test: confidence distribution panel target PromQL uses `aiops_diagnosis_completed_total`
  - [x] 6.24 Test: confidence distribution panel target PromQL uses `sum by(confidence)` label
  - [x] 6.25 Test: confidence distribution panel target `legendFormat` contains `confidence`
  - [x] 6.26 Test: confidence distribution panel has non-empty description (UX-DR12)
  - [x] 6.27 Test: confidence distribution panel has `noValue` field set (NFR5 / UX-DR5)
  - [x] 6.28 Test: confidence distribution panel `options.text.titleSize` >= 14 (UX-DR2)
  - [x] 6.29 Test: confidence distribution panel `options.orientation` == "horizontal"
  - [x] 6.30 Test: confidence distribution panel `options.sort` == "desc"
  - [x] 6.31 Test: no forbidden Grafana default palette colors in panel id=12 JSON (case-insensitive `.upper()`)
  - [x] 6.32 Test: high-confidence rate panel (id=13) exists, type="stat"
  - [x] 6.33 Test: high-confidence rate panel gridPos y=43, h=2, w=12, x=12
  - [x] 6.34 Test: high-confidence rate panel has `transparent: true` (UX-DR4)
  - [x] 6.35 Test: high-confidence rate panel target PromQL uses `aiops_diagnosis_completed_total`
  - [x] 6.36 Test: high-confidence rate panel target PromQL uses `confidence` label filter
  - [x] 6.37 Test: high-confidence rate panel has non-empty description (UX-DR12)
  - [x] 6.38 Test: high-confidence rate panel has `noValue` field set (NFR5 / UX-DR5)
  - [x] 6.39 Test: no forbidden Grafana default palette colors in panel id=13 JSON (case-insensitive `.upper()`)
  - [x] 6.40 Test: dashboard version >= 7 after story 3-3 additions

## Dev Notes

### Critical Architecture Constraints (DO NOT DEVIATE)

- **Dashboard file**: `grafana/dashboards/aiops-main.json` — single source of truth. Do NOT use Grafana UI without re-exporting.
- **Dashboard UID**: `"uid": "aiops-main"` is a hardcoded constant. Do NOT modify.
- **Schema version**: `"schemaVersion": 39` is fixed — do NOT change.
- **Panel ID allocation** for this story:
  - `id: 10` → invocation count stat (rows 36-37, left half)
  - `id: 11` → success rate stat (rows 38-39, left half)
  - `id: 12` → confidence distribution barchart (rows 40-42, left half)
  - `id: 13` → fault domain identification rate stat (rows 43-44, left half)
  - IDs 1-9 are in use; never overlap with drill-down (100-199).
- **Pairing with story 3-4**: The epic positions diagnosis stats at rows 36-40 (12 cols, right) paired with capability stack (12 cols, left). However, the capability stack is story 3-4 (not yet built). For this story, place all panels in the LEFT 12 cols (x=0, w=12) at the assigned rows. When story 3-4 is built, it will occupy the RIGHT 12 cols (x=12). This avoids gridPos conflicts between the stories.

  **IMPORTANT layout note from epics.md**: The epic AC states "rows 36-40 (12 cols, right)" for diagnosis stats. However, since story 3-4 (capability stack, left) is not yet implemented, use the LEFT position (x=0) for these panels and story 3-4 will use RIGHT (x=12). This keeps story 3-3 independent. Alternatively if the Scrum Master or architect has specified otherwise, follow that. The current layout table in story 3-2 shows "Diagnosis stats | 36-40 (h=5, 12 cols right)" and "Capability stack | 36-40 (h=5, 12 cols left)" — so RIGHT x=12 is the correct final position. Place diagnosis stats panels with x=12, w=12.

  **CORRECTED panel grid positions** (12 cols RIGHT, x=12, paired with 3-4 which will use x=0):
  - `id: 10`: `{h: 2, w: 12, x: 12, y: 36}`
  - `id: 11`: `{h: 2, w: 12, x: 12, y: 38}`
  - `id: 12`: `{h: 3, w: 12, x: 12, y: 40}`
  - `id: 13`: `{h: 2, w: 12, x: 12, y: 43}`

  **`x == 0` test assertion** applies ONLY to left-column panels. For id=10–13, assert `x == 12`.

- **Transparent backgrounds**: ALL panels require `"transparent": true`. This is a hard requirement established in stories 2-3, 3-1, 3-2. Stat panels also need explicit `transparent: true` in this project.
- **No live stack required**: All tests are static JSON parsing (config-validation style).
- **Color palette — ONLY these hex values**: `#6BAD64` (green), `#E8913A` (amber), `#D94452` (red), `#7A7A7A` (grey), `#4F87DB` (accent-blue). Grafana defaults are FORBIDDEN.
- **Ruff line-length = 100** for any Python files touched.

### Metric Definition: aiops_diagnosis_completed_total

Defined in story 1-3 (`health/metrics.py`). Counter. Emitted in `src/aiops_triage_pipeline/diagnosis/graph.py` via `record_diagnosis_completed()`.

- **Python dotted name**: `aiops.diagnosis.completed_total`
- **PromQL underscored name**: `aiops_diagnosis_completed_total`
- **Labels**:
  - `confidence`: `"LOW"`, `"MEDIUM"`, `"HIGH"` (from `DiagnosisConfidence` enum — uppercase strings)
  - `fault_domain_present`: `"true"` or `"false"` (string, not boolean — derived from `report.fault_domain is not None`)
  - `topic`: topic string (e.g., `"payments.consumer-lag"`)
- **Note**: There is NO `outcome` label on `aiops_diagnosis_completed_total`. The metric only tracks completions. Success rate cannot be filtered by `outcome="SUCCESS"` because that label does not exist on this metric. Instead, interpret all completions as successes (the counter only increments on successful diagnosis). Task 2 above shows a placeholder; adjust to: `sum(increase(aiops_diagnosis_completed_total[$__range]))` for the invocation total, and there is no native success/failure distinction — the stat should reflect total completed diagnoses as the "success" proxy (remove the explicit success rate panel or use 100% as constant — see PromQL query design below).

### PromQL Query Design

**Aggregation style** (architecture mandate): `sum by(label) (metric)` — NEVER `sum(metric) by(label)`.

**Range vector rule for stat/barchart panels**: `$__range` — NEVER `$__rate_interval`.

**Metric**: `aiops_diagnosis_completed_total` — counter, labels: `confidence`, `fault_domain_present`, `topic`.

**No `outcome` or `latency` labels exist on this metric.** The metric has no latency information (it is a counter, not a histogram). Design panels around what is actually available.

**Available panels given the metric**:

1. **Invocation count** (stat, `id: 10`):
   ```
   sum(increase(aiops_diagnosis_completed_total[$__range]))
   ```
   No `by()` needed — aggregate everything to a single count. legendFormat: `"Invocations"`.

2. **Fault domain identification rate** (stat, `id: 11`):
   ```
   sum(increase(aiops_diagnosis_completed_total{fault_domain_present="true"}[$__range])) / sum(increase(aiops_diagnosis_completed_total[$__range]))
   ```
   legendFormat: `"Fault domain rate"`. Unit: `percentunit`.

3. **Confidence distribution** (barchart, `id: 12`):
   ```
   sum by(confidence) (increase(aiops_diagnosis_completed_total[$__range]))
   ```
   legendFormat: `"{{confidence}}"`. Produces 3 bars: LOW, MEDIUM, HIGH.

4. **High-confidence rate** (stat, `id: 13` — replaces "latency" since no histogram exists):
   ```
   sum(increase(aiops_diagnosis_completed_total{confidence="HIGH"}[$__range])) / sum(increase(aiops_diagnosis_completed_total[$__range]))
   ```
   legendFormat: `"High confidence rate"`. Unit: `percentunit`.
   Title: `"High confidence rate"`.

**REVISED panel layout** (4 stat/barchart panels, right half x=12):
- `id: 10` stat invocation count → `{h: 2, w: 12, x: 12, y: 36}`
- `id: 11` stat fault domain rate → `{h: 2, w: 12, x: 12, y: 38}`
- `id: 12` barchart confidence distribution → `{h: 3, w: 12, x: 12, y: 40}`
- `id: 13` stat high-confidence rate → `{h: 2, w: 12, x: 12, y: 43}`

### Panel Type Decision Rationale

**Invocation count** — use `"stat"`:
- Single scalar value: total diagnosis invocations over the selected time window.
- PromQL: `sum(increase(aiops_diagnosis_completed_total[$__range]))` — stat panel convention, uses `$__range`.
- Color: semantic-grey `#7A7A7A` (fixed, neutral count — not a threshold-based metric).
- Must NOT use a timeseries panel for this — `increase` over `$__range` produces a single point, not a trend.

**Fault domain identification rate** — use `"stat"`:
- Ratio: diagnoses with non-null fault domain / total diagnoses.
- PromQL: fraction query using label filter `{fault_domain_present="true"}`.
- Color: threshold-based (green = high, amber = medium, red = low).
- Unit: `percentunit` so Grafana renders as percentage.

**Confidence distribution** — use `"barchart"` (NOT `"bargauge"`):
- Three categorical bars: LOW, MEDIUM, HIGH confidence.
- `"barchart"` is the correct Grafana 12.x type for categorical bar charts.
- Horizontal orientation, sorted desc, thresholds color mode.

**High-confidence rate** — use `"stat"`:
- Ratio: HIGH confidence diagnoses / total diagnoses.
- Uses same fraction pattern as fault domain rate.
- Unit: `percentunit`.

### Color Strategy

**Invocation count panel (id=10)** — fixed neutral grey:
```json
"fieldConfig": {
  "defaults": {
    "color": {"mode": "fixed", "fixedColor": "#7A7A7A"}
  }
}
```
Use `options.colorMode: "none"` (no background color for neutral count stat).

**Fault domain rate panel (id=11)** — threshold colors:
- 0 → `#7A7A7A` (grey, no data / zero)
- 0.5 → `#E8913A` (amber, acceptable)
- 0.8 → `#6BAD64` (green, healthy)

**Confidence distribution panel (id=12)** — `fieldConfig.defaults.color.mode: "thresholds"`:
- Base threshold: `#7A7A7A` (grey)
- Positive step: `#6BAD64` (green)
- This avoids any named Grafana palette (same pattern as id=9 in story 3-2).

**High-confidence rate panel (id=13)** — threshold colors:
- 0 → `#7A7A7A` (grey)
- 0.5 → `#E8913A` (amber)
- 0.7 → `#6BAD64` (green, majority of diagnoses are high-confidence)

### Zero-State Handling

All panels require `fieldConfig.defaults.noValue: "0"`:
- Zero invocations shows `0` in semantic-grey, not blank or "No data" (UX-DR5).
- Zero fault domain rate shows `0` (no diagnoses with fault domain in window).
- Zero confidence values show `0` per bar (celebrated zero for each confidence tier).

### JSON Manipulation Pattern

Current `aiops-main.json` has 9 panels (id=1 through id=9), version=6. Add panels as 10th–13th elements:

```json
"panels": [
  { /* hero banner, id: 1 */ },
  { /* P&L stat, id: 2 */ },
  { /* topic heatmap, id: 3 */ },
  { /* fold separator, id: 4 */ },
  { /* baseline overlay, id: 5 */ },
  { /* section separator, id: 6 */ },
  { /* gating funnel, id: 7 */ },
  { /* action distribution, id: 8 */ },
  { /* anomaly family breakdown, id: 9 */ },
  { /* diagnosis invocations, id: 10 */ },
  { /* fault domain rate, id: 11 */ },
  { /* confidence distribution, id: 12 */ },
  { /* high-confidence rate, id: 13 */ }
]
```

Increment `"version"` from `6` to `7`.

**Do NOT change**: `uid`, `schemaVersion`, `title`, `description`, `timezone`, `time`, `timepicker`, `refresh`, `tags`, `annotations`, or any existing panels (id=1 through id=9).

### UX Layout Reference (Newspaper Direction C)

| Zone | Rows | Panel IDs | Story |
|---|---|---|---|
| Hero banner | 0-4 (h=5) | 1 | Story 2-1 (done) |
| P&L stat | 5-7 (h=3) | 2 | Story 2-1 (done) |
| Topic heatmap | 8-13 (h=6) | 3 | Story 2-2 (done) |
| Fold separator (text) | 14 (h=1) | 4 | Story 2-3 (done) |
| Baseline deviation overlay | 15-22 (h=8) | 5 | Story 2-3 (done) |
| Section separator (text) | 23 (h=1) | 6 | Story 3-1 (done) |
| Gating intelligence funnel | 24-29 (h=6) | 7 | Story 3-1 (done) |
| Action distribution | 30-34 (h=5, 12 cols left) | 8 | Story 3-2 (done) |
| Anomaly family breakdown | 30-34 (h=5, 12 cols right) | 9 | Story 3-2 (done) |
| **Capability stack** | **36-40 (h=5, 12 cols LEFT x=0)** | **TBD** | **Story 3-4** |
| **Diagnosis invocations** | **36-37 (h=2, 12 cols RIGHT x=12)** | **10** | **This story** |
| **Fault domain rate** | **38-39 (h=2, 12 cols RIGHT x=12)** | **11** | **This story** |
| **Confidence distribution** | **40-42 (h=3, 12 cols RIGHT x=12)** | **12** | **This story** |
| **High-confidence rate** | **43-44 (h=2, 12 cols RIGHT x=12)** | **13** | **This story** |

**gridPos invariant**: All diagnosis panels use `x: 12, w: 12` (right half). Story 3-4 will fill `x: 0, w: 12` (left half) in the same row range. Position tests must assert `x == 12` for all id=10–13.

### Testing Pattern for Config-Validation Tests

**File to extend**: `tests/integration/test_dashboard_validation.py`
**New class**: `TestLLMDiagnosisEngineStatistics`
**Current test count**: 100 tests. This story adds ~28 new tests → total ~128.

Follow the exact conventions from `TestActionDistributionAnomalyBreakdown` (story 3-2):
- `_load_main_dashboard()` helper reads `grafana/dashboards/aiops-main.json`
- `_get_panel_by_id(dashboard, panel_id)` helper extracts panel by ID
- Case-insensitive forbidden palette check: `json.dumps(panel_json).upper()` before asserting on hex colors
- All test methods have docstrings referencing the AC they cover
- Dashboard version tests use `>= N` NEVER `== N` (forward-compatible convention)
- All position tests must assert `x`, `y`, `w`, and `h`

### Review Findings

- [x] [Review][Patch] Missing test for `options.text.valueSize >= 14` on barchart panel (id=12) [tests/integration/test_dashboard_validation.py] — fixed: added `test_confidence_distribution_panel_value_size_meets_minimum`
- [x] [Review][Patch] Missing test for `unit=percentunit` on panels 11 and 13 [tests/integration/test_dashboard_validation.py] — fixed: added `test_fault_domain_rate_panel_uses_percentunit` and `test_high_confidence_rate_panel_uses_percentunit`
- [x] [Review][Patch] Missing test for `options.colorMode=background` on panels 11 and 13 [tests/integration/test_dashboard_validation.py] — fixed: added `test_fault_domain_rate_panel_colormode_is_background` and `test_high_confidence_rate_panel_colormode_is_background`
- [x] [Review][Patch] Missing test for `color.mode=fixed`, `fixedColor=#7A7A7A`, and `options.colorMode=none` on invocation count panel (id=10) [tests/integration/test_dashboard_validation.py] — fixed: added `test_invocation_count_panel_color_mode_is_fixed_semantic_grey`
- [x] [Review][Defer] Row 35 is uncovered (1-row gap between panels 8/9 at y=30-34 and panel 10 at y=36) [grafana/dashboards/aiops-main.json] — deferred, pre-existing layout gap; story 3-4 left-column panels will bound this row visually
- `transparent: true` must be tested for ALL panels (stat, barchart, timeseries all require it)
- `options.text.titleSize >= 14` must be tested for barchart panel id=12 (UX-DR2)
- `options.text.valueSize >= 28` must be tested for stat panels id=10, 11, 13 (UX-DR2 — 28px+ for secondary values)
- `legendFormat` must be tested for barchart id=12 (confidence label)
- `orientation == "horizontal"` must be tested for id=12
- `sort == "desc"` must be tested for id=12 (learned from story 3-2 review finding)
- No `displayMode` test for barchart panel id=12 (barchart does not use displayMode — only bargauge does)

**Class docstring** must NOT contain TDD red-phase language. Write clean production-quality docstring:

```python
class TestLLMDiagnosisEngineStatistics:
    """Config-validation tests for story 3-3: LLM diagnosis engine statistics panels
    (id=10 invocation count, id=11 fault domain rate, id=12 confidence distribution,
    id=13 high-confidence rate).

    No live docker-compose stack required — all assertions are pure JSON parsing.
    """

    def _load_main_dashboard(self):
        path = REPO_ROOT / "grafana/dashboards/aiops-main.json"
        return json.loads(path.read_text())

    def _get_panel_by_id(self, dashboard, panel_id):
        panels = dashboard.get("panels", [])
        return next((p for p in panels if p.get("id") == panel_id), None)
```

### Color Palette Reference (Complete)

| Token | Hex | Usage in this story |
|---|---|---|
| semantic-green | `#6BAD64` | Thresholds (healthy rate values) |
| semantic-amber | `#E8913A` | Thresholds (acceptable rate values) |
| semantic-red | `#D94452` | Thresholds (poor rate values, if used) |
| semantic-grey | `#7A7A7A` | Invocation count fixed color; barchart base threshold; zero-state |
| accent-blue | `#4F87DB` | Not used in this story |

**Forbidden Grafana defaults**: `#73BF69`, `#F2495C`, `#FF9830`, `#FADE2A`, `#5794F2`, `#B877D9`, `#37872D`, `#C4162A`, `#1F60C4`, `#8F3BB8`. Caught by `scripts/validate-colors.sh`.

### Learnings from Previous Stories (Apply Upfront — These Caused Review Findings)

1. **`transparent: true`** on ALL panels — stat, timeseries, barchart all require explicit `"transparent": true`. This was an H1 finding in story 2-3, re-confirmed in 3-1, re-confirmed in 3-2. Do not skip it.
2. **Version tests use `>= N`** pattern, never `== N` (forward-compatible).
3. **`options.text.valueSize >= 28`** for stat panels — 28px minimum for secondary below-the-fold values (UX-DR2). This is separate from `titleSize`.
4. **`options.text.titleSize >= 14`** for barchart id=12 (UX-DR2).
5. **`gridPos.x == 12`** for all panels in this story (right half, paired with story 3-4 left half). Do not assert `x == 0` for these panels.
6. **Case-insensitive palette check**: `json.dumps(panel).upper()` before checking forbidden hex colors (catches lowercase variants).
7. **No TDD red-phase comments** in class docstring — clean production docstring from the start.
8. **`options.sort: "desc"`** on barchart id=12 — AC2 requires confidence distribution bars visible; sorting by value is standard (learned from story 3-2 review: id=9 was missing sort=desc).
9. **`options.orientation: "horizontal"`** on barchart id=12 — consistent with story 3-2 pattern for categorical breakdowns.
10. **`fieldConfig.defaults.color` fallback on stat panels** — set a concrete `color.mode` (fixed or thresholds) on ALL stat panels to prevent Grafana classic palette from leaking (learned from story 3-2 review finding on panel id=8).
11. **`noValue: "0"` on all panels** — prevents blank/missing-series rendering for zero-state periods (UX-DR5, NFR9).
12. **`sum by(label) (metric)` aggregation style** — NEVER `sum(metric) by(label)` (architecture mandate, checked in tests for barchart panel).
13. **`$__range` for stat/barchart panels** — NEVER `$__rate_interval` (that is timeseries-only).
14. **No `outcome` or `latency` labels on `aiops_diagnosis_completed_total`** — this is a plain counter with only `confidence`, `fault_domain_present`, `topic` labels. Do not attempt label filters for non-existent labels.

### Current State of aiops-main.json

```
version: 6
panels (9 total):
  id=1  type=stat        title="Pipeline health"               gridPos={h:5, w:24, x:0, y:0}
  id=2  type=stat        title="Anomalies detected & acted on" gridPos={h:3, w:24, x:0, y:5}
  id=3  type=stat        title="Topic health"                  gridPos={h:6, w:24, x:0, y:8}
  id=4  type=text        title=""                              gridPos={h:1, w:24, x:0, y:14}
  id=5  type=timeseries  title="Baseline deviation overlay"    gridPos={h:8, w:24, x:0, y:15}
  id=6  type=text        title=""                              gridPos={h:1, w:24, x:0, y:23}
  id=7  type=bargauge    title="Gating intelligence funnel"    gridPos={h:6, w:24, x:0, y:24}
  id=8  type=timeseries  title="Action distribution"          gridPos={h:5, w:12, x:0, y:30}
  id=9  type=barchart    title="Anomaly family breakdown"      gridPos={h:5, w:12, x:12, y:30}
```

Next available panel IDs: 10, 11, 12, 13 (this story).
After this story: 13 panels, version=7.

### File Change Summary

| File | Change |
|---|---|
| `grafana/dashboards/aiops-main.json` | Add panels id=10, 11, 12, 13; version 6→7 |
| `tests/integration/test_dashboard_validation.py` | Append class `TestLLMDiagnosisEngineStatistics` (~28 tests) |

No changes to: `health/metrics.py` (metric already defined in story 1-3), `docker-compose.yml`, provisioning YAML files, or any panel id=1–9.

### References

- FR14, FR15: Diagnosis engine statistics and quality metrics requirements [epics.md]
- UX-DR2: Text size minimum 28px for secondary stat values [epics.md]
- UX-DR3: "The Newspaper" layout — rows 36-40 split 12 cols each [epics.md]
- UX-DR4: Transparent panel backgrounds [epics.md]
- UX-DR5: Zero-state patterns — celebrated zeros in semantic-green, neutral in grey [epics.md]
- UX-DR12: One-sentence panel descriptions on every panel [epics.md]
- NFR1, NFR9: 5-second render, meaningful zero-states [epics.md]
- `aiops_diagnosis_completed_total` metric definition: labels `confidence`, `fault_domain_present`, `topic` [artifact/implementation-artifacts/1-3-evidence-diagnosis-otlp-instruments.md]
- PromQL aggregation style and range vector conventions [architecture.md — PromQL Query Patterns]
- Panel ID allocation 1-99 main dashboard [architecture.md — Grafana Dashboard JSON Patterns]
- Color palette (6 tokens + forbidden Grafana defaults) [architecture.md — Validation Issues Found & Resolved]
- Story 3-2 review findings: transparent, sort=desc, stacking.mode, orientation, color fallback [artifact/implementation-artifacts/3-2-action-distribution-anomaly-family-breakdown.md]
- Story 3-1 review findings: transparent, displayMode, legendFormat, no red-phase docstring [artifact/implementation-artifacts/3-1-gating-intelligence-funnel-per-gate-suppression.md]

## Dev Agent Record

### Agent Model Used

claude-sonnet-4-6

### Debug Log References

None — implementation completed without issues.

### Completion Notes List

- Implemented 4 new Grafana panels (id=10–13) in `grafana/dashboards/aiops-main.json`.
- Panel id=10 (stat): Diagnosis invocations — `sum(increase(aiops_diagnosis_completed_total[$__range]))`, fixed grey color, valueSize=28, transparent.
- Panel id=11 (stat): Fault domain identification rate — fraction query using `fault_domain_present="true"` filter, percentunit, threshold thresholds, transparent.
- Panel id=12 (barchart): Confidence distribution — `sum by(confidence) (increase(aiops_diagnosis_completed_total[$__range]))`, horizontal, sort=desc, thresholds color, transparent.
- Panel id=13 (stat): High confidence rate — fraction query using `confidence="HIGH"` filter, percentunit, threshold thresholds, transparent.
- Bumped dashboard version from 6 to 7. uid, schemaVersion, and all existing panels (id=1–9) unchanged.
- All 39 ATDD tests in `TestLLMDiagnosisEngineStatistics` pass (previously 35 failing). Full suite: 139 passed, 0 failures.
- All panels placed at x=12, w=12 (right half, paired with future story 3-4 at x=0).
- No forbidden Grafana palette colors used. All panels have noValue="0", descriptions, and transparent=true.

### File List

- `grafana/dashboards/aiops-main.json` — added panels id=10, 11, 12, 13; bumped version 6→7
- `artifact/implementation-artifacts/3-3-llm-diagnosis-engine-statistics.md` — updated tasks, status, dev agent record
