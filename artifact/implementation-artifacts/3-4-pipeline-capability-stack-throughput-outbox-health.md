# Story 3.4: Pipeline Capability Stack, Throughput & Outbox Health

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a Platform Senior Director,
I want to see each pipeline stage with its live status and latency, overall throughput metrics, and outbox health,
so that I can confirm every pipeline layer is operational and the system is processing anomalies at expected volume.

## Acceptance Criteria

1. **Given** the main dashboard is scrolled to the operational zone **When** the capability stack panel renders at rows 36-40 (12 cols, left — paired with diagnosis stats) **Then** a table or stat panel row displays each pipeline stage (detection, enrichment, gating, dispatch, LLM diagnosis) with live status and last-cycle latency (FR22) **And** stage status uses semantic color tokens: green (operational), amber (degraded), red (down)

2. **Given** the main dashboard is scrolled further **When** the pipeline throughput panel renders at rows 41-44 (12 cols, left) **Then** a stat panel displays scopes evaluated and deviations detected per cycle (FR23) **And** sparkline is enabled to show throughput trend

3. **Given** the main dashboard is scrolled further **When** the outbox health panel renders at rows 41-44 (12 cols, right) **Then** a stat panel displays outbox health status (FR24) **And** status uses the same three-state health color mapping (green/amber/red)

4. **Given** all panels are configured **When** the dashboard JSON is inspected **Then** panels use 28px+ text size for secondary values (UX-DR2), transparent backgrounds (UX-DR4), one-sentence descriptions (UX-DR12) **And** panel IDs are within 1-99 range **And** all panels render within 5 seconds with 7-day queries completing within 10 seconds (NFR1, NFR4)

## Tasks / Subtasks

- [ ] Task 1: Add capability stack stat panel to `grafana/dashboards/aiops-main.json` (AC: 1, 4)
  - [ ] 1.1 Add stat panel: `type: "stat"`, `id: 14`, `gridPos: {h: 5, w: 12, x: 0, y: 36}`
  - [ ] 1.2 Set panel `title: "Pipeline capability stack"` (sentence case per architecture convention)
  - [ ] 1.3 Set `"transparent": true` on the panel
  - [ ] 1.4 Add target `refId: "A"`: `sum by(confidence) (increase(aiops_findings_total[$__range]))` as proxy for pipeline activity (see PromQL Design section for rationale)
  - [ ] 1.5 Set `datasource: {type: "prometheus", uid: "prometheus"}` on both panel and target
  - [ ] 1.6 Configure thresholds: 0 → semantic-grey `#7A7A7A`, 1 → semantic-green `#6BAD64` (operational when data flows)
  - [ ] 1.7 Set `fieldConfig.defaults.color.mode: "thresholds"` with `options.colorMode: "background"`
  - [ ] 1.8 Set `options.textMode: "value_and_name"` so stage label is visible alongside value
  - [ ] 1.9 Set `options.text.valueSize: 28` (UX-DR2 — 28px+ for secondary values)
  - [ ] 1.10 Set `fieldConfig.defaults.noValue: "0"` (UX-DR5 — celebrated zero, not blank)
  - [ ] 1.11 Set panel `description` to one sentence (UX-DR12)

- [ ] Task 2: Add pipeline throughput stat panel to `grafana/dashboards/aiops-main.json` (AC: 2, 4)
  - [ ] 2.1 Add stat panel: `type: "stat"`, `id: 15`, `gridPos: {h: 2, w: 12, x: 0, y: 41}`
  - [ ] 2.2 Set panel `title: "Pipeline throughput"` (sentence case)
  - [ ] 2.3 Set `"transparent": true` on the panel
  - [ ] 2.4 Add target `refId: "A"`: `sum(increase(aiops_findings_total[$__range]))` with `legendFormat: "Scopes evaluated"` — total findings as throughput proxy (see PromQL Design section)
  - [ ] 2.5 Set `datasource: {type: "prometheus", uid: "prometheus"}` on both panel and target
  - [ ] 2.6 Enable sparkline: set `options.graphMode: "area"` (Grafana stat panel sparkline option)
  - [ ] 2.7 Configure `fieldConfig.defaults.color.mode: "fixed"` with `fixedColor: "#7A7A7A"` (semantic-grey for neutral count)
  - [ ] 2.8 Set `options.colorMode: "none"` (no background color for throughput count)
  - [ ] 2.9 Set `options.text.valueSize: 28` (UX-DR2)
  - [ ] 2.10 Set `fieldConfig.defaults.noValue: "0"` (UX-DR5)
  - [ ] 2.11 Set panel `description` to one sentence (UX-DR12)

- [ ] Task 3: Add outbox health stat panel to `grafana/dashboards/aiops-main.json` (AC: 3, 4)
  - [ ] 3.1 Add stat panel: `type: "stat"`, `id: 16`, `gridPos: {h: 2, w: 12, x: 0, y: 43}`
  - [ ] 3.2 Set panel `title: "Outbox health"` (sentence case)
  - [ ] 3.3 Set `"transparent": true` on the panel
  - [ ] 3.4 Add target `refId: "A"`: `sum(increase(aiops_gating_evaluations_total[$__range]))` with `legendFormat: "Outbox health"` — gating evaluations as outbox activity proxy (see PromQL Design section)
  - [ ] 3.5 Set `datasource: {type: "prometheus", uid: "prometheus"}` on both panel and target
  - [ ] 3.6 Configure thresholds: 0 → semantic-red `#D94452`, 1 → semantic-amber `#E8913A`, 10 → semantic-green `#6BAD64` (green when evaluations confirm outbox active)
  - [ ] 3.7 Set `fieldConfig.defaults.color.mode: "thresholds"` with `options.colorMode: "background"` (three-state health color mapping per AC3)
  - [ ] 3.8 Set `options.text.valueSize: 28` (UX-DR2)
  - [ ] 3.9 Set `fieldConfig.defaults.noValue: "0"` (UX-DR5)
  - [ ] 3.10 Set panel `description` to one sentence (UX-DR12)

- [ ] Task 4: Finalize dashboard version bump (AC: 4)
  - [ ] 4.1 Bump dashboard top-level `"version"` from `7` to `8`
  - [ ] 4.2 Verify `"uid": "aiops-main"` unchanged, `"schemaVersion": 39` unchanged
  - [ ] 4.3 Verify existing panels (id=1 through id=13) are NOT modified

- [ ] Task 5: Add config-validation tests for all panels (AC: 1, 2, 3, 4)
  - [ ] 5.1 Extend `tests/integration/test_dashboard_validation.py` with class `TestPipelineCapabilityStack`
  - [ ] 5.2 Test: capability stack panel (id=14) exists, type="stat"
  - [ ] 5.3 Test: capability stack panel gridPos y=36, h=5, w=12, x=0
  - [ ] 5.4 Test: capability stack panel has `transparent: true` (UX-DR4)
  - [ ] 5.5 Test: capability stack panel target refId="A" PromQL uses `aiops_findings_total`
  - [ ] 5.6 Test: capability stack panel has non-empty description (UX-DR12)
  - [ ] 5.7 Test: capability stack panel has `noValue` field set (NFR5 / UX-DR5)
  - [ ] 5.8 Test: capability stack panel `options.text.valueSize` >= 28 (UX-DR2)
  - [ ] 5.9 Test: no forbidden Grafana default palette colors in panel id=14 JSON (case-insensitive `.upper()`)
  - [ ] 5.10 Test: pipeline throughput panel (id=15) exists, type="stat"
  - [ ] 5.11 Test: pipeline throughput panel gridPos y=41, h=2, w=12, x=0
  - [ ] 5.12 Test: pipeline throughput panel has `transparent: true` (UX-DR4)
  - [ ] 5.13 Test: pipeline throughput panel target PromQL uses `aiops_findings_total`
  - [ ] 5.14 Test: pipeline throughput panel has non-empty description (UX-DR12)
  - [ ] 5.15 Test: pipeline throughput panel has `noValue` field set (NFR5 / UX-DR5)
  - [ ] 5.16 Test: pipeline throughput panel `options.text.valueSize` >= 28 (UX-DR2)
  - [ ] 5.17 Test: pipeline throughput panel `options.graphMode` == "area" (sparkline enabled, AC2)
  - [ ] 5.18 Test: no forbidden Grafana default palette colors in panel id=15 JSON (case-insensitive `.upper()`)
  - [ ] 5.19 Test: outbox health panel (id=16) exists, type="stat"
  - [ ] 5.20 Test: outbox health panel gridPos y=43, h=2, w=12, x=0
  - [ ] 5.21 Test: outbox health panel has `transparent: true` (UX-DR4)
  - [ ] 5.22 Test: outbox health panel target PromQL uses `aiops_gating_evaluations_total`
  - [ ] 5.23 Test: outbox health panel has non-empty description (UX-DR12)
  - [ ] 5.24 Test: outbox health panel has `noValue` field set (NFR5 / UX-DR5)
  - [ ] 5.25 Test: outbox health panel `options.text.valueSize` >= 28 (UX-DR2)
  - [ ] 5.26 Test: outbox health panel `options.colorMode` == "background" (three-state health mapping, AC3)
  - [ ] 5.27 Test: no forbidden Grafana default palette colors in panel id=16 JSON (case-insensitive `.upper()`)
  - [ ] 5.28 Test: dashboard version >= 8 after story 3-4 additions

## Dev Notes

### Critical Architecture Constraints (DO NOT DEVIATE)

- **Dashboard file**: `grafana/dashboards/aiops-main.json` — single source of truth. Do NOT use Grafana UI without re-exporting.
- **Dashboard UID**: `"uid": "aiops-main"` is a hardcoded constant. Do NOT modify.
- **Schema version**: `"schemaVersion": 39` is fixed — do NOT change.
- **Panel ID allocation** for this story:
  - `id: 14` → capability stack stat (rows 36-40, LEFT half x=0)
  - `id: 15` → pipeline throughput stat (rows 41-42, LEFT half x=0)
  - `id: 16` → outbox health stat (rows 43-44, LEFT half x=0)
  - IDs 1-13 are in use; never overlap with drill-down (100-199).
- **Transparent backgrounds**: ALL panels require `"transparent": true`. Hard requirement established in stories 2-3, 3-1, 3-2, 3-3.
- **No live stack required**: All tests are static JSON parsing (config-validation style).
- **Color palette — ONLY these hex values**: `#6BAD64` (green), `#E8913A` (amber), `#D94452` (red), `#7A7A7A` (grey), `#4F87DB` (accent-blue). Grafana defaults are FORBIDDEN.
- **Ruff line-length = 100** for any Python files touched.

### Layout Design: Left Half Fill Pattern

Story 3-3 placed 4 panels (id=10–13) on the **RIGHT half** (`x=12, w=12`) at rows 36-44. This story fills the corresponding **LEFT half** (`x=0, w=12`) at the same rows.

**CRITICAL layout constraint**: The RIGHT half (x=12) at rows 41-44 is already occupied by story 3-3 panels (id=12 at y=40,h=3 and id=13 at y=43,h=2). Therefore, the outbox health panel (AC3) must be placed on the **LEFT half (x=0)** stacked below throughput — NOT at x=12. This avoids gridPos conflicts.

**Final panel grid positions** (all LEFT half, x=0):

| Panel | ID | type | y | h | w | x | Rows |
|-------|-----|------|---|---|---|---|------|
| Capability stack | 14 | stat | 36 | 5 | 12 | 0 | 36-40 |
| Pipeline throughput | 15 | stat | 41 | 2 | 12 | 0 | 41-42 |
| Outbox health | 16 | stat | 43 | 2 | 12 | 0 | 43-44 |

**`x == 0` assertion**: All story 3-4 panels use `x: 0, w: 12`. Tests MUST assert `x == 0` for id=14, 15, 16. (This is the OPPOSITE of story 3-3 which asserts `x == 12`.)

### UX Layout Reference (Complete Newspaper Direction C)

| Zone | Rows | Panel IDs | Story |
|---|---|---|---|
| Hero banner | 0-4 (h=5) | 1 | Story 2-1 (done) |
| P&L stat | 5-7 (h=3) | 2 | Story 2-1 (done) |
| Topic heatmap | 8-13 (h=6) | 3 | Story 2-2 (done) |
| Fold separator (text) | 14 (h=1) | 4 | Story 2-3 (done) |
| Baseline deviation overlay | 15-22 (h=8) | 5 | Story 2-3 (done) |
| Section separator (text) | 23 (h=1) | 6 | Story 3-1 (done) |
| Gating intelligence funnel | 24-29 (h=6) | 7 | Story 3-1 (done) |
| Action distribution | 30-34 (h=5, 12 cols left x=0) | 8 | Story 3-2 (done) |
| Anomaly family breakdown | 30-34 (h=5, 12 cols right x=12) | 9 | Story 3-2 (done) |
| **Capability stack** | **36-40 (h=5, 12 cols LEFT x=0)** | **14** | **This story** |
| Diagnosis invocations | 36-37 (h=2, 12 cols RIGHT x=12) | 10 | Story 3-3 (done) |
| Fault domain rate | 38-39 (h=2, 12 cols RIGHT x=12) | 11 | Story 3-3 (done) |
| Confidence distribution | 40-42 (h=3, 12 cols RIGHT x=12) | 12 | Story 3-3 (done) |
| High-confidence rate | 43-44 (h=2, 12 cols RIGHT x=12) | 13 | Story 3-3 (done) |
| **Pipeline throughput** | **41-42 (h=2, 12 cols LEFT x=0)** | **15** | **This story** |
| **Outbox health** | **43-44 (h=2, 12 cols LEFT x=0)** | **16** | **This story** |

**Row 35**: 1-row gap between action distribution (y=30,h=5 → ends at y=35) and capability stack (y=36) is a pre-existing design gap noted in story 3-3 review. Do NOT add any filler panel.

### PromQL Query Design

**Aggregation style** (architecture mandate): `sum by(label) (metric)` — NEVER `sum(metric) by(label)`.

**Range vector rule for stat panels**: `$__range` — NEVER `$__rate_interval`.

**Available metrics** (established in stories 1-2 and 1-3):
- `aiops_findings_total` — counter, labels: `anomaly_family`, `final_action`, `topic`, `routing_key`, `criticality_tier`
- `aiops_gating_evaluations_total` — counter, labels: `gate_id`, `outcome`
- `aiops_evidence_status` — gauge, labels: `scope`, `metric_key`, `status`
- `aiops_diagnosis_completed_total` — counter, labels: `confidence`, `fault_domain_present`, `topic`

**FR22 (capability stack)** — No dedicated per-stage latency metric exists. Use `aiops_findings_total` as a proxy for pipeline activity. The stat panel shows total findings flow as evidence each stage is operational. One reasonable approach:

```promql
sum(increase(aiops_findings_total[$__range]))
```
`legendFormat: "Pipeline activity"`. Color: threshold green when > 0 (operational).

**FR23 (pipeline throughput)** — Total scopes evaluated and deviations detected:

```promql
sum(increase(aiops_findings_total[$__range]))
```
`legendFormat: "Findings processed"`. With sparkline (`graphMode: "area"`) to show trend over time window.

**FR24 (outbox health)** — Gating evaluations confirm the outbox is processing:

```promql
sum(increase(aiops_gating_evaluations_total[$__range]))
```
`legendFormat: "Outbox health"`. Color: threshold — red (0), amber (1-9), green (≥10).

**Zero-state handling** (UX-DR5, NFR9):
- All panels: `fieldConfig.defaults.noValue: "0"` so zero shows as `0`, not blank.
- Zero findings = celebrated zero in semantic-grey (pipeline ran but no anomalies — healthy).
- Zero gating evaluations = outbox inactive this window — red threshold.

### JSON Manipulation Pattern

Current `aiops-main.json` has **13 panels** (id=1 through id=13), version=**7**. Add panels as 14th–16th elements:

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
  { /* high-confidence rate, id: 13 */ },
  { /* capability stack, id: 14 */ },
  { /* pipeline throughput, id: 15 */ },
  { /* outbox health, id: 16 */ }
]
```

Increment `"version"` from `7` to `8`.

**Do NOT change**: `uid`, `schemaVersion`, `title`, `description`, `timezone`, `time`, `timepicker`, `refresh`, `tags`, `annotations`, or any existing panels (id=1 through id=13).

### Testing Pattern for Config-Validation Tests

**File to extend**: `tests/integration/test_dashboard_validation.py`

**New class**: `TestPipelineCapabilityStack`

**Current test count**: 145 tests. This story adds ~28 new tests → total ~173.

Follow exact conventions from `TestLLMDiagnosisEngineStatistics` (story 3-3) and `TestActionDistributionAnomalyBreakdown` (story 3-2):

```python
class TestPipelineCapabilityStack:
    """Config-validation tests for story 3-4: Pipeline capability stack, throughput, and
    outbox health panels (id=14 capability stack, id=15 pipeline throughput, id=16 outbox health).

    No live docker-compose stack required — all assertions are pure JSON parsing.
    """

    def _load_main_dashboard(self):
        path = REPO_ROOT / "grafana/dashboards/aiops-main.json"
        return json.loads(path.read_text())

    def _get_panel_by_id(self, dashboard, panel_id):
        panels = dashboard.get("panels", [])
        return next((p for p in panels if p.get("id") == panel_id), None)
```

**Test conventions** (apply consistently):
- `_load_main_dashboard()` and `_get_panel_by_id()` helpers in every class (as shown above)
- Case-insensitive forbidden palette check: `json.dumps([p for p in dashboard.get("panels", []) if p.get("id") == N]).upper()`
- All test methods have docstrings referencing the AC they cover (e.g., "AC1 (Task 5.3)")
- Dashboard version tests use `>= N` NEVER `== N` (forward-compatible convention)
- All position tests MUST assert all four gridPos keys: `x`, `y`, `w`, `h`
- `x == 0` for ALL story 3-4 panels (left half — opposite of story 3-3's `x == 12`)
- `transparent: true` tested for EVERY panel (stat panels require explicit transparent flag)

**Forbidden color set** (same across all stories — verbatim copy from TestLLMDiagnosisEngineStatistics):
```python
forbidden = {
    "#73BF69", "#F2495C", "#FF9830", "#FADE2A",
    "#5794F2", "#B877D9", "#37872D", "#C4162A", "#1F60C4", "#8F3BB8",
}
```

**Class docstring rule**: Must NOT contain TDD/red-phase language. Write clean production-quality docstrings.

**Test method naming convention** (follow pattern from story 3-3):
- `test_capability_stack_panel_exists`
- `test_capability_stack_panel_grid_position`
- `test_capability_stack_panel_is_transparent`
- `test_capability_stack_target_uses_aiops_findings_total`
- `test_capability_stack_panel_has_description`
- `test_capability_stack_panel_has_no_value_field`
- `test_capability_stack_panel_value_size_meets_minimum`
- `test_no_grafana_default_palette_colors_in_capability_stack_panel`
- (repeat pattern for pipeline_throughput and outbox_health)
- `test_pipeline_throughput_panel_sparkline_enabled` (graphMode == "area")
- `test_outbox_health_panel_colormode_is_background` (three-state health)
- `test_dashboard_version_is_at_least_8`

### Specific gridPos Tests (Must Match Exactly)

```python
# Capability stack panel (id=14)
assert panel["gridPos"]["y"] == 36
assert panel["gridPos"]["h"] == 5
assert panel["gridPos"]["w"] == 12
assert panel["gridPos"]["x"] == 0   # LEFT half — NOT 12

# Pipeline throughput panel (id=15)
assert panel["gridPos"]["y"] == 41
assert panel["gridPos"]["h"] == 2
assert panel["gridPos"]["w"] == 12
assert panel["gridPos"]["x"] == 0   # LEFT half

# Outbox health panel (id=16)
assert panel["gridPos"]["y"] == 43
assert panel["gridPos"]["h"] == 2
assert panel["gridPos"]["w"] == 12
assert panel["gridPos"]["x"] == 0   # LEFT half
```

### Color Strategy

**Capability stack panel (id=14)** — threshold background colors:
- 0 → `#7A7A7A` (grey, no data)
- 1 → `#6BAD64` (green, pipeline operational — any findings confirm stages running)

```json
"fieldConfig": {
  "defaults": {
    "color": {"mode": "thresholds"},
    "thresholds": {
      "mode": "absolute",
      "steps": [
        {"color": "#7A7A7A", "value": null},
        {"color": "#6BAD64", "value": 1}
      ]
    }
  }
}
```
Set `"options": {"colorMode": "background"}`.

**Pipeline throughput panel (id=15)** — fixed neutral grey (count, not health signal):
```json
"fieldConfig": {
  "defaults": {
    "color": {"mode": "fixed", "fixedColor": "#7A7A7A"}
  }
}
```
Set `"options": {"colorMode": "none", "graphMode": "area"}`.

**Outbox health panel (id=16)** — three-state health thresholds:
- 0 → `#D94452` (red, outbox inactive — no evaluations in window)
- 1 → `#E8913A` (amber, some activity but low)
- 10 → `#6BAD64` (green, healthy evaluation volume)

```json
"fieldConfig": {
  "defaults": {
    "color": {"mode": "thresholds"},
    "thresholds": {
      "mode": "absolute",
      "steps": [
        {"color": "#D94452", "value": null},
        {"color": "#E8913A", "value": 1},
        {"color": "#6BAD64", "value": 10}
      ]
    }
  }
}
```
Set `"options": {"colorMode": "background"}`.

### Full Panel JSON Structure Reference

Use this as the baseline for each stat panel (confirmed working from stories 3-1 through 3-3):

```json
{
  "id": 14,
  "type": "stat",
  "title": "Pipeline capability stack",
  "description": "One-sentence description here.",
  "transparent": true,
  "datasource": {"type": "prometheus", "uid": "prometheus"},
  "gridPos": {"h": 5, "w": 12, "x": 0, "y": 36},
  "options": {
    "colorMode": "background",
    "graphMode": "none",
    "textMode": "value_and_name",
    "text": {"valueSize": 28}
  },
  "fieldConfig": {
    "defaults": {
      "color": {"mode": "thresholds"},
      "thresholds": {
        "mode": "absolute",
        "steps": [
          {"color": "#7A7A7A", "value": null},
          {"color": "#6BAD64", "value": 1}
        ]
      },
      "noValue": "0"
    },
    "overrides": []
  },
  "targets": [
    {
      "refId": "A",
      "datasource": {"type": "prometheus", "uid": "prometheus"},
      "expr": "sum(increase(aiops_findings_total[$__range]))",
      "legendFormat": "Pipeline activity"
    }
  ]
}
```

Adapt `id`, `title`, `description`, `gridPos`, `options`, `fieldConfig`, and `targets` for each panel.

### Datasource Configuration

Every panel and every target must specify:
```json
"datasource": {"type": "prometheus", "uid": "prometheus"}
```
This is mandatory in Grafana 10+ and has been confirmed in every prior story (2-1 through 3-3).

### Previous Story Intelligence (from Story 3-3)

**Mandatory learnings — apply these exactly**:

1. **`transparent: true` is required on stat panels** — not just timeseries. Must be a top-level panel field. Add `"transparent": true` at the panel root level alongside `"id"`, `"type"`, etc.

2. **`options.text.valueSize >= 28`** for all stat panels showing secondary values (UX-DR2). This was a review finding in story 3-3 (test added retroactively).

3. **`fieldConfig.defaults.noValue: "0"`** — Required on ALL panels. Zero invocations/findings should render as `"0"`, not blank (UX-DR5, NFR5).

4. **Case-insensitive palette check** — `json.dumps(panel_json).upper()` before checking forbidden colors. Color hex codes are case-insensitive and Grafana sometimes returns uppercase.

5. **Dashboard version** — Test with `>= N` not `== N`. Version after this story is `8`. Test: `assert dashboard.get("version", 0) >= 8`.

6. **Do NOT modify panels id=1 through id=13** — verify task 4.3 explicitly.

7. **Barchart vs bargauge** — barchart panels do NOT use `displayMode`. Only bargauge uses `displayMode`. (Not relevant for this story — all panels are stat type, but keep in mind.)

8. **`sum by(label) (metric)`** — NOT `sum(metric) by(label)`. Architecture mandate. Wrong aggregation style was a common error in early stories.

9. **Review findings from 3-3 deferred item**: "Row 35 is uncovered (1-row gap between y=30-34 panels and y=36 panel) — story 3-4 left-column panels will bound this row visually." The capability stack panel at y=36 serves this visual bounding role. Do NOT add a filler at y=35.

### Architecture Source References

- [Source: artifact/planning-artifacts/architecture.md#Color Palette] — 6-color muted palette, forbidden Grafana defaults
- [Source: artifact/planning-artifacts/architecture.md#PromQL Style] — `sum by(label) (metric)`, `$__range` for stat panels
- [Source: artifact/planning-artifacts/architecture.md#Zero-state Pattern] — `noValue: "0"` for celebrated zeros
- [Source: artifact/planning-artifacts/epics.md#Story 3.4] — FR22, FR23, FR24, UX-DR2, UX-DR4, UX-DR12, NFR1, NFR4
- [Source: artifact/implementation-artifacts/3-3-llm-diagnosis-engine-statistics.md#Dev Notes] — Panel patterns, review findings, layout constraints
- [Source: grafana/dashboards/aiops-main.json] — Current dashboard state: 13 panels, version=7, id=10–13 at x=12

### Project Structure Notes

- **Only file to modify**: `grafana/dashboards/aiops-main.json` (add 3 panels, bump version 7→8)
- **Only test file to modify**: `tests/integration/test_dashboard_validation.py` (append class `TestPipelineCapabilityStack`)
- **No Python source changes**: No metrics, no health module changes. All panels use existing PromQL metrics from stories 1-2 and 1-3.
- **No new dependencies**: No new Python packages or Grafana plugins needed.
- **Ruff compliance**: If any Python is touched, line-length = 100 (pyproject.toml setting).

## Dev Agent Record

### Agent Model Used

claude-sonnet-4-6

### Debug Log References

### Completion Notes List

### File List
