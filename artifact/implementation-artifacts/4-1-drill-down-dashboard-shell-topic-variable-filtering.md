# Story 4.1: Drill-Down Dashboard Shell & Topic Variable Filtering

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As an SRE Lead,
I want a per-topic drill-down dashboard with a single topic selector that drives all panels and accessible from the main dashboard heatmap,
So that I can instantly focus on a specific topic for triage without manual per-panel filtering.

## Acceptance Criteria

1. **Given** the drill-down dashboard (`aiops-drilldown.json`) is opened **When** the dashboard loads **Then** a Grafana template variable `$topic` is displayed as a dropdown selector at the top populated with all available topics (FR20) **And** the default time window is 24h (tighter than main dashboard's 7d)

2. **Given** the user selects a topic from the variable selector **When** the selection changes **Then** every panel on the drill-down updates simultaneously to show data for only the selected topic (FR20)

3. **Given** the user clicks a heatmap tile on the main dashboard **When** the data link navigates to the drill-down **Then** the drill-down opens with the clicked topic pre-selected in `$topic` via URL parameter `?var-topic=${__data.fields.topic}` (FR16, FR31) **And** the current time range is preserved via `${__url_time_range}`

4. **Given** the drill-down dashboard is open **When** the user wants to return to the main dashboard **Then** a text panel (id=100) at the top provides a markdown link "← Back to Overview" targeting UID `aiops-main` **And** browser back button also restores the main dashboard

5. **Given** the drill-down dashboard renders **When** the topic health stat panel renders at rows 1-4 (8 cols, left) **Then** a stat panel (id=101) displays the selected topic's health status with color mode: background using semantic tokens (green/amber/red)

6. **Given** the drill-down dashboard is configured **When** the dashboard JSON is inspected **Then** all panel IDs are within the 100-199 range **And** the dashboard UID is hardcoded as `aiops-drilldown` **And** schemaVersion is 39 (unchanged)

## Tasks / Subtasks

- [ ] Task 1: Configure `$topic` template variable in `grafana/dashboards/aiops-drilldown.json` (AC: 1, 2)
  - [ ] 1.1 Add Grafana template variable to `templating.list`:
    - `name: "topic"`, `type: "query"`, `label: "Topic"`
    - `datasource: {type: "prometheus", uid: "prometheus"}`
    - `query: "label_values(aiops_findings_total, topic)"` (all emitted topics)
    - `refresh: 2` (on time range change)
    - `sort: 1` (alphabetical)
    - `multi: false`, `includeAll: false` (single-select — triage focus)
    - `hide: 0` (always visible)
  - [ ] 1.2 Set dashboard default time window to 24h: `"time": {"from": "now-24h", "to": "now"}`

- [ ] Task 2: Add back-navigation text panel to `grafana/dashboards/aiops-drilldown.json` (AC: 4)
  - [ ] 2.1 Add text panel: `type: "text"`, `id: 100`, `gridPos: {h: 1, w: 24, x: 0, y: 0}`
  - [ ] 2.2 Set `options.mode: "markdown"` and `options.content: "[← Back to Overview](/d/aiops-main)"`
  - [ ] 2.3 Set `"transparent": true` on the panel
  - [ ] 2.4 Set panel `title: ""` (empty — navigation bar, no title needed)

- [ ] Task 3: Add topic health stat panel to `grafana/dashboards/aiops-drilldown.json` (AC: 5, 6)
  - [ ] 3.1 Add stat panel: `type: "stat"`, `id: 101`, `gridPos: {h: 4, w: 8, x: 0, y: 1}`
  - [ ] 3.2 Set panel `title: "Topic health"` (sentence case)
  - [ ] 3.3 Set `"transparent": true` on the panel
  - [ ] 3.4 Add target `refId: "A"`: `sum(increase(aiops_findings_total{topic="$topic"}[$__range]))` with `legendFormat: "{{topic}}"`
  - [ ] 3.5 Set `datasource: {type: "prometheus", uid: "prometheus"}` on both panel and target
  - [ ] 3.6 Configure thresholds: 0 → semantic-grey `#7A7A7A`, 1 → semantic-amber `#E8913A`, 10 → semantic-green `#6BAD64`
  - [ ] 3.7 Set `fieldConfig.defaults.color.mode: "thresholds"` with `options.colorMode: "background"`
  - [ ] 3.8 Set `options.text.valueSize: 28` (UX-DR2)
  - [ ] 3.9 Set `fieldConfig.defaults.noValue: "0"` (UX-DR5)
  - [ ] 3.10 Set panel `description` to one sentence (UX-DR12)

- [ ] Task 4: Add data link to heatmap panel in `grafana/dashboards/aiops-main.json` (AC: 3)
  - [ ] 4.1 In panel id=3 (topic heatmap), add `dataLinks` array under `options`:
    - `title: "Drill down → $topic"`
    - `url: "/d/aiops-drilldown?var-topic=${__data.fields.topic}&${__url_time_range}"`
    - `targetBlank: false` (same window — preserve browser back)
  - [ ] 4.2 Bump `aiops-main.json` version from `8` to `9`

- [ ] Task 5: Finalize drilldown dashboard version (AC: 6)
  - [ ] 5.1 Bump `aiops-drilldown.json` version from `1` to `2`
  - [ ] 5.2 Verify `"uid": "aiops-drilldown"` unchanged, `"schemaVersion": 39` unchanged

- [ ] Task 6: Add config-validation tests (AC: 1, 3, 4, 5, 6)
  - [ ] 6.1 Extend `tests/integration/test_dashboard_validation.py` with class `TestDrillDownDashboardShell`
  - [ ] 6.2 Test: `$topic` template variable exists in drilldown templating list
  - [ ] 6.3 Test: `$topic` variable type is `"query"` and datasource is prometheus
  - [ ] 6.4 Test: `$topic` variable query uses `aiops_findings_total` metric
  - [ ] 6.5 Test: drilldown default time window is `now-24h`
  - [ ] 6.6 Test: back navigation text panel (id=100) exists, type="text"
  - [ ] 6.7 Test: back navigation panel gridPos y=0, h=1, w=24, x=0
  - [ ] 6.8 Test: back navigation panel has `transparent: true`
  - [ ] 6.9 Test: back navigation panel content references "aiops-main"
  - [ ] 6.10 Test: topic health stat panel (id=101) exists, type="stat"
  - [ ] 6.11 Test: topic health stat panel gridPos y=1, h=4, w=8, x=0
  - [ ] 6.12 Test: topic health stat panel has `transparent: true`
  - [ ] 6.13 Test: topic health stat panel target PromQL uses `aiops_findings_total`
  - [ ] 6.14 Test: topic health stat panel target PromQL filters by `$topic`
  - [ ] 6.15 Test: topic health stat panel has non-empty description
  - [ ] 6.16 Test: topic health stat panel has `noValue` field set
  - [ ] 6.17 Test: topic health stat panel `options.text.valueSize` >= 28
  - [ ] 6.18 Test: topic health stat panel `options.colorMode` == "background"
  - [ ] 6.19 Test: no forbidden Grafana default palette colors in panel id=101 JSON
  - [ ] 6.20 Test: main dashboard panel id=3 (heatmap) has dataLinks array
  - [ ] 6.21 Test: heatmap dataLink URL references "aiops-drilldown"
  - [ ] 6.22 Test: heatmap dataLink URL includes `var-topic=` parameter
  - [ ] 6.23 Test: drilldown dashboard UID == "aiops-drilldown"
  - [ ] 6.24 Test: drilldown schemaVersion == 39
  - [ ] 6.25 Test: all drilldown panel IDs are within 100-199 range
  - [ ] 6.26 Test: drilldown dashboard version >= 2
  - [ ] 6.27 Test: main dashboard version >= 9 (after data link addition)

## Dev Notes

### Critical Architecture Constraints (DO NOT DEVIATE)

- **Dashboard files**: `grafana/dashboards/aiops-main.json` AND `grafana/dashboards/aiops-drilldown.json`
- **Dashboard UIDs**: `"uid": "aiops-drilldown"` is a hardcoded constant. Do NOT modify.
- **Schema version**: `"schemaVersion": 39` is fixed — do NOT change in either dashboard.
- **Panel ID allocation** for this story:
  - `id: 100` → back navigation text panel (drilldown row 0)
  - `id: 101` → topic health stat panel (drilldown rows 1-4, LEFT 8 cols)
  - IDs 1-99 are reserved for main dashboard; 100-199 for drill-down. Never overlap.
- **Transparent backgrounds**: ALL panels require `"transparent": true`.
- **No live stack required**: All tests are static JSON parsing (config-validation style).
- **Color palette — ONLY these hex values**: `#6BAD64` (green), `#E8913A` (amber), `#D94452` (red),
  `#7A7A7A` (grey), `#4F87DB` (accent-blue). Grafana defaults are FORBIDDEN.
- **Ruff line-length = 100** for any Python files touched.

### Drill-Down Dashboard Layout (UX-DR6)

Full layout for reference (story 4-1 delivers rows 0-4 only):

| Zone | Rows | Panel IDs | Story |
|---|---|---|---|
| Back navigation + variable | 0 (h=1) | 100 (text) | **This story** |
| Topic health stat | 1-4 (h=4, 8 cols LEFT x=0) | 101 (stat) | **This story** |
| Evidence status row | 1-4 (h=4, 16 cols RIGHT x=8) | 102-N (stat grid) | Story 4-2 |
| Per-topic time series | 5-12 (h=8, 24 cols) | 110 (timeseries) | Story 4-2 |
| Findings table | 13-18 (h=6, 24 cols) | 120 (table) | Story 4-3 |
| Diagnosis stats | 19-23 (h=5, 12 cols LEFT) | 130-131 (stat) | Story 4-3 |
| Action rationale | 19-23 (h=5, 12 cols RIGHT) | 132 (text/stat) | Story 4-3 |

### Template Variable Configuration

```json
{
  "name": "topic",
  "type": "query",
  "label": "Topic",
  "datasource": {"type": "prometheus", "uid": "prometheus"},
  "definition": "label_values(aiops_findings_total, topic)",
  "query": {
    "query": "label_values(aiops_findings_total, topic)",
    "refId": "StandardVariableQuery"
  },
  "refresh": 2,
  "sort": 1,
  "multi": false,
  "includeAll": false,
  "hide": 0,
  "options": [],
  "current": {}
}
```

`refresh: 2` = refresh on time range change. `sort: 1` = alphabetical A→Z.

### Back Navigation Text Panel (id=100)

```json
{
  "id": 100,
  "type": "text",
  "title": "",
  "transparent": true,
  "gridPos": {"h": 1, "w": 24, "x": 0, "y": 0},
  "options": {
    "mode": "markdown",
    "content": "[← Back to Overview](/d/aiops-main)"
  }
}
```

### Topic Health Stat Panel (id=101)

```json
{
  "id": 101,
  "type": "stat",
  "title": "Topic health",
  "description": "One-sentence description here.",
  "transparent": true,
  "datasource": {"type": "prometheus", "uid": "prometheus"},
  "gridPos": {"h": 4, "w": 8, "x": 0, "y": 1},
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
          {"color": "#E8913A", "value": 1},
          {"color": "#6BAD64", "value": 10}
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
      "expr": "sum(increase(aiops_findings_total{topic=\"$topic\"}[$__range]))",
      "legendFormat": "{{topic}}"
    }
  ]
}
```

### Data Link on Heatmap Panel (aiops-main.json panel id=3)

Add to panel id=3 `options` object:
```json
"dataLinks": [
  {
    "title": "Drill down → $topic",
    "url": "/d/aiops-drilldown?var-topic=${__data.fields.topic}&${__url_time_range}",
    "targetBlank": false
  }
]
```

**Architecture note** (line 206 in architecture.md): Data links deliver demo click-through narrative.
URL parameter: `var-topic=${__data.fields.topic}` passes the heatmap cell topic to the drilldown.

### Version Bumps

- `aiops-drilldown.json`: version `1` → `2` (template variable + panels added)
- `aiops-main.json`: version `8` → `9` (heatmap data link added)

### Testing Pattern for Config-Validation Tests

**File to extend**: `tests/integration/test_dashboard_validation.py`

**New class**: `TestDrillDownDashboardShell`

**Current test count**: 173 tests. This story adds ~27 new tests → total ~200.

```python
class TestDrillDownDashboardShell:
    """Config-validation tests for story 4-1: Drill-down dashboard shell, $topic template
    variable, back navigation panel (id=100), and topic health stat panel (id=101).

    No live docker-compose stack required — all assertions are pure JSON parsing.
    """

    def _load_main_dashboard(self):
        path = REPO_ROOT / "grafana/dashboards/aiops-main.json"
        return json.loads(path.read_text())

    def _load_drilldown_dashboard(self):
        path = REPO_ROOT / "grafana/dashboards/aiops-drilldown.json"
        return json.loads(path.read_text())

    def _get_panel_by_id(self, dashboard, panel_id):
        panels = dashboard.get("panels", [])
        return next((p for p in panels if p.get("id") == panel_id), None)
```

### PromQL Variable Filtering Convention

From architecture.md (line 320):
- Drill-down variable filtering: `{topic="$topic"}` (exact match)
- All topics with data: `{topic=~".+"}` (never `.*` which includes empty)

All panels in the drilldown MUST filter with `{topic="$topic"}`.

### Forbidden Color Set (verbatim from all prior stories)

```python
forbidden = {
    "#73BF69", "#F2495C", "#FF9830", "#FADE2A",
    "#5794F2", "#B877D9", "#37872D", "#C4162A", "#1F60C4", "#8F3BB8",
}
```

### Architecture Source References

- [Source: artifact/planning-artifacts/architecture.md#Inter-dashboard navigation] — data link format
- [Source: artifact/planning-artifacts/architecture.md#PromQL Style] — `{topic="$topic"}` exact match
- [Source: artifact/planning-artifacts/epics.md#Story 4.1] — FR16, FR20, FR31, UX-DR6, NFR3
- [Source: grafana/dashboards/aiops-drilldown.json] — current state: empty panels, version=1

## Dev Agent Record

### Agent Model Used

claude-sonnet-4-6

### Debug Log References

### Completion Notes List

### File List
