# Story 4.2: Evidence Status & Per-Topic Metrics

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As an SRE Lead,
I want to see evidence status per metric as a color-coded traffic light row and per-topic Prometheus metrics on a time-series panel,
So that I can instantly assess what the system can and can't see for this topic and review recent metric behavior.

## Acceptance Criteria

1. **Given** the drill-down dashboard is open with a topic selected **When** the evidence status row renders at rows 1-4 (16 cols, right — x=8) **Then** a stat panel (id=102) displays evidence status for the selected topic (FR18) **And** the panel uses color mode: background with value mapping: PRESENT=0 (green `#6BAD64`), STALE=1 (amber `#E8913A`), UNKNOWN=2 (grey `#7A7A7A`), ABSENT=3 (red `#D94452`) (UX-DR11) **And** ALL CAPS status label is the primary displayed value **And** the query filters by `{topic="$topic"}`

2. **Given** the drill-down dashboard is open with a topic selected **When** the per-topic time-series panel renders at rows 5-12 (24 cols) **Then** a timeseries panel (id=110) displays per-topic Prometheus metrics with the drill-down's 24h default time window (FR17) **And** the query filters by `{topic="$topic"}` using exact match **And** the time-series line uses accent-blue `#4F87DB`

3. **Given** the pipeline has not emitted evidence for a metric **When** the evidence panel renders **Then** the "no data" message is handled via `fieldConfig.defaults.noValue` set to a non-empty string (UX-DR5)

4. **Given** both panels are configured **When** the dashboard JSON is inspected **Then** panels use transparent backgrounds, one-sentence descriptions (UX-DR12), and panel IDs within 100-199 range **And** panels render within 5 seconds (NFR1)

## Tasks / Subtasks

- [ ] Task 1: Add evidence status stat panel to `grafana/dashboards/aiops-drilldown.json` (AC: 1, 3, 4)
  - [ ] 1.1 Add stat panel: `type: "stat"`, `id: 102`, `gridPos: {h: 4, w: 16, x: 8, y: 1}`
  - [ ] 1.2 Set panel `title: "Evidence status"` (sentence case)
  - [ ] 1.3 Set `"transparent": true` on the panel
  - [ ] 1.4 Add target `refId: "A"`: `aiops_evidence_status{topic="$topic"}` with `legendFormat: "{{metric_key}}"`
  - [ ] 1.5 Set `datasource: {type: "prometheus", uid: "prometheus"}` on both panel and target
  - [ ] 1.6 Configure value mappings for WCAG status display (UX-DR11):
    - `0 → "PRESENT"` (green `#6BAD64`)
    - `1 → "STALE"` (amber `#E8913A`)
    - `2 → "UNKNOWN"` (grey `#7A7A7A`)
    - `3 → "ABSENT"` (red `#D94452`)
  - [ ] 1.7 Set `fieldConfig.defaults.color.mode: "thresholds"` with `options.colorMode: "background"`
  - [ ] 1.8 Set `options.textMode: "value"` so status label (PRESENT/STALE/UNKNOWN/ABSENT) is primary
  - [ ] 1.9 Set `options.reduceOptions.values: true` and `options.reduceOptions.calcs: ["lastNotNull"]`
    so each metric_key renders as a separate tile
  - [ ] 1.10 Set `options.text.valueSize: 14` (UX-DR2 — status labels legible in 16-col width)
  - [ ] 1.11 Set `fieldConfig.defaults.noValue: "Awaiting data"` (UX-DR5, AC3)
  - [ ] 1.12 Set panel `description` to one sentence (UX-DR12)

- [ ] Task 2: Add per-topic time-series panel to `grafana/dashboards/aiops-drilldown.json` (AC: 2, 4)
  - [ ] 2.1 Add timeseries panel: `type: "timeseries"`, `id: 110`, `gridPos: {h: 8, w: 24, x: 0, y: 5}`
  - [ ] 2.2 Set panel `title: "Per-topic findings over time"` (sentence case)
  - [ ] 2.3 Set `"transparent": true` on the panel
  - [ ] 2.4 Add target `refId: "A"`: `sum by(final_action) (rate(aiops_findings_total{topic="$topic"}[$__rate_interval]))` with `legendFormat: "{{final_action}}"`
  - [ ] 2.5 Set `datasource: {type: "prometheus", uid: "prometheus"}` on both panel and target
  - [ ] 2.6 Set `fieldConfig.defaults.color.mode: "fixed"` with `fixedColor: "#4F87DB"` (accent-blue, AC2)
  - [ ] 2.7 Set `fieldConfig.defaults.noValue: "0"` (UX-DR5)
  - [ ] 2.8 Set panel `description` to one sentence (UX-DR12)

- [ ] Task 3: Finalize dashboard version bump (AC: 4)
  - [ ] 3.1 Bump `aiops-drilldown.json` version from `2` to `3`
  - [ ] 3.2 Verify `"uid": "aiops-drilldown"` unchanged, `"schemaVersion": 39` unchanged
  - [ ] 3.3 Verify existing panels (id=100, id=101) are NOT modified

- [ ] Task 4: Add config-validation tests (AC: 1, 2, 3, 4)
  - [ ] 4.1 Extend `tests/integration/test_dashboard_validation.py` with class `TestEvidenceStatusPerTopicMetrics`
  - [ ] 4.2 Test: evidence status panel (id=102) exists, type="stat"
  - [ ] 4.3 Test: evidence status panel gridPos y=1, h=4, w=16, x=8
  - [ ] 4.4 Test: evidence status panel has `transparent: true`
  - [ ] 4.5 Test: evidence status panel target PromQL uses `aiops_evidence_status`
  - [ ] 4.6 Test: evidence status panel target PromQL filters by `$topic`
  - [ ] 4.7 Test: evidence status panel has non-empty description
  - [ ] 4.8 Test: evidence status panel has `noValue` field set (AC3)
  - [ ] 4.9 Test: evidence status panel `options.colorMode` == "background"
  - [ ] 4.10 Test: evidence status panel has WCAG value mappings (0=PRESENT, 1=STALE, 2=UNKNOWN, 3=ABSENT)
  - [ ] 4.11 Test: no forbidden Grafana default palette colors in panel id=102 JSON
  - [ ] 4.12 Test: per-topic time-series panel (id=110) exists, type="timeseries"
  - [ ] 4.13 Test: per-topic time-series panel gridPos y=5, h=8, w=24, x=0
  - [ ] 4.14 Test: per-topic time-series panel has `transparent: true`
  - [ ] 4.15 Test: per-topic time-series panel target PromQL uses `aiops_findings_total`
  - [ ] 4.16 Test: per-topic time-series panel target PromQL filters by `$topic`
  - [ ] 4.17 Test: per-topic time-series panel has accent-blue `#4F87DB` in field config
  - [ ] 4.18 Test: per-topic time-series panel has non-empty description
  - [ ] 4.19 Test: per-topic time-series panel has `noValue` field set
  - [ ] 4.20 Test: no forbidden Grafana default palette colors in panel id=110 JSON
  - [ ] 4.21 Test: drilldown dashboard version >= 3

## Dev Notes

### Critical Architecture Constraints (DO NOT DEVIATE)

- **Dashboard file**: `grafana/dashboards/aiops-drilldown.json` — only file to modify.
- **Dashboard UID**: `"uid": "aiops-drilldown"` is a hardcoded constant. Do NOT modify.
- **Schema version**: `"schemaVersion": 39` is fixed — do NOT change.
- **Panel ID allocation** for this story:
  - `id: 102` → evidence status stat (rows 1-4, RIGHT 16 cols at x=8)
  - `id: 110` → per-topic timeseries (rows 5-12, 24 cols)
  - IDs 100-101 are in use from story 4-1. IDs 103-109 reserved for future story 4-x additions.
  - Never overlap with main dashboard (1-99).
- **Transparent backgrounds**: ALL panels require `"transparent": true`.
- **No live stack required**: All tests are static JSON parsing (config-validation style).
- **Color palette — ONLY these hex values**: `#6BAD64` (green), `#E8913A` (amber), `#D94452` (red),
  `#7A7A7A` (grey), `#4F87DB` (accent-blue). Grafana defaults are FORBIDDEN.
- **Ruff line-length = 100** for any Python files touched.

### Layout Reference (Story 4-2 fills right side of rows 1-4 and rows 5-12)

| Zone | Rows | Panel IDs | x | w | Story |
|---|---|---|---|---|---|
| Back navigation | 0 (h=1) | 100 (text) | 0 | 24 | 4-1 (done) |
| Topic health stat | 1-4 (h=4) | 101 (stat) | 0 | 8 | 4-1 (done) |
| **Evidence status** | **1-4 (h=4)** | **102 (stat)** | **8** | **16** | **This story** |
| **Per-topic time series** | **5-12 (h=8)** | **110 (timeseries)** | **0** | **24** | **This story** |
| Findings table | 13-18 (h=6) | 120 (table) | 0 | 24 | Story 4-3 |
| Diagnosis stats | 19-23 (h=5) | 130-131 (stat) | 0 | 12 | Story 4-3 |
| Action rationale | 19-23 (h=5) | 132 (text/stat) | 12 | 12 | Story 4-3 |

### Evidence Status Panel Design (UX-DR11)

The evidence status panel shows per-metric-key status for the selected topic.

**Value mappings** (must exactly match these values per UX-DR11):
```json
"mappings": [
  {
    "type": "value",
    "options": {
      "0": {"text": "PRESENT", "color": "#6BAD64"},
      "1": {"text": "STALE", "color": "#E8913A"},
      "2": {"text": "UNKNOWN", "color": "#7A7A7A"},
      "3": {"text": "ABSENT", "color": "#D94452"}
    }
  }
]
```

**Thresholds** (backing the colorMode=background):
```json
"thresholds": {
  "mode": "absolute",
  "steps": [
    {"color": "#6BAD64", "value": null},
    {"color": "#E8913A", "value": 1},
    {"color": "#7A7A7A", "value": 2},
    {"color": "#D94452", "value": 3}
  ]
}
```

**`options.reduceOptions.values: true`** — Required for stat panel to show one tile per series
(one tile per `metric_key` label value). Without this, the panel would aggregate all series.

### Per-Topic Time Series Panel Design (AC2)

Use `rate()` + `$__rate_interval` (timeseries panel convention, NOT `increase()` + `$__range`):

```promql
sum by(final_action) (rate(aiops_findings_total{topic="$topic"}[$__rate_interval]))
```

`legendFormat: "{{final_action}}"` — each action type becomes a distinct series.

**Color**: `fieldConfig.defaults.color.mode: "fixed"` + `fixedColor: "#4F87DB"` (accent-blue).
This applies uniform accent-blue to all series. Per-series color overrides are optional.

### Full Panel JSON Templates

**Evidence status panel (id=102)**:
```json
{
  "id": 102,
  "type": "stat",
  "title": "Evidence status",
  "description": "One-sentence description here.",
  "transparent": true,
  "datasource": {"type": "prometheus", "uid": "prometheus"},
  "gridPos": {"h": 4, "w": 16, "x": 8, "y": 1},
  "options": {
    "colorMode": "background",
    "graphMode": "none",
    "textMode": "value",
    "text": {"valueSize": 14},
    "reduceOptions": {
      "calcs": ["lastNotNull"],
      "fields": "",
      "values": true
    }
  },
  "fieldConfig": {
    "defaults": {
      "color": {"mode": "thresholds"},
      "thresholds": {
        "mode": "absolute",
        "steps": [
          {"color": "#6BAD64", "value": null},
          {"color": "#E8913A", "value": 1},
          {"color": "#7A7A7A", "value": 2},
          {"color": "#D94452", "value": 3}
        ]
      },
      "mappings": [
        {
          "type": "value",
          "options": {
            "0": {"text": "PRESENT", "color": "#6BAD64"},
            "1": {"text": "STALE", "color": "#E8913A"},
            "2": {"text": "UNKNOWN", "color": "#7A7A7A"},
            "3": {"text": "ABSENT", "color": "#D94452"}
          }
        }
      ],
      "noValue": "Awaiting data"
    },
    "overrides": []
  },
  "targets": [
    {
      "refId": "A",
      "datasource": {"type": "prometheus", "uid": "prometheus"},
      "expr": "aiops_evidence_status{topic=\"$topic\"}",
      "legendFormat": "{{metric_key}}"
    }
  ]
}
```

**Per-topic timeseries panel (id=110)**:
```json
{
  "id": 110,
  "type": "timeseries",
  "title": "Per-topic findings over time",
  "description": "One-sentence description here.",
  "transparent": true,
  "datasource": {"type": "prometheus", "uid": "prometheus"},
  "gridPos": {"h": 8, "w": 24, "x": 0, "y": 5},
  "options": {
    "tooltip": {"mode": "multi"},
    "legend": {"displayMode": "list", "placement": "bottom"}
  },
  "fieldConfig": {
    "defaults": {
      "color": {"mode": "fixed", "fixedColor": "#4F87DB"},
      "noValue": "0",
      "custom": {
        "lineWidth": 2,
        "fillOpacity": 10
      }
    },
    "overrides": []
  },
  "targets": [
    {
      "refId": "A",
      "datasource": {"type": "prometheus", "uid": "prometheus"},
      "expr": "sum by(final_action) (rate(aiops_findings_total{topic=\"$topic\"}[$__rate_interval]))",
      "legendFormat": "{{final_action}}"
    }
  ]
}
```

### Testing Pattern for Config-Validation Tests

**File to extend**: `tests/integration/test_dashboard_validation.py`

**New class**: `TestEvidenceStatusPerTopicMetrics`

**Current test count**: 199 tests. This story adds ~21 new tests → total ~220.

```python
class TestEvidenceStatusPerTopicMetrics:
    """Config-validation tests for story 4-2: evidence status stat panel (id=102) and
    per-topic timeseries panel (id=110) on the drill-down dashboard.

    No live docker-compose stack required — all assertions are pure JSON parsing.
    """

    def _load_drilldown_dashboard(self):
        path = REPO_ROOT / "grafana/dashboards/aiops-drilldown.json"
        return json.loads(path.read_text())

    def _get_panel_by_id(self, dashboard, panel_id):
        panels = dashboard.get("panels", [])
        return next((p for p in panels if p.get("id") == panel_id), None)
```

### Forbidden Color Set (verbatim from all prior stories)

```python
forbidden = {
    "#73BF69", "#F2495C", "#FF9830", "#FADE2A",
    "#5794F2", "#B877D9", "#37872D", "#C4162A", "#1F60C4", "#8F3BB8",
}
```

### Architecture Source References

- [Source: artifact/planning-artifacts/architecture.md#PromQL Style] — `{topic="$topic"}` exact match
- [Source: artifact/planning-artifacts/epics.md#Story 4.2] — FR17, FR18, UX-DR11, UX-DR12, NFR1
- [Source: grafana/dashboards/aiops-drilldown.json] — current state: 2 panels (id=100,101), version=2
- [Source: artifact/implementation-artifacts/4-1-drill-down-dashboard-shell-topic-variable-filtering.md]

## Dev Agent Record

### Agent Model Used

claude-sonnet-4-6

### Debug Log References

### Completion Notes List

### File List
