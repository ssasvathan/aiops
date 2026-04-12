# Story 4.3: Findings Table & Action Decision Tracing

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As an SRE Lead,
I want a findings table filtered by topic showing action decisions with gate rationale, and the ability to trace a finding's full action decision path,
So that I can understand exactly why each decision was made and trust the system's reasoning during incident triage.

## Acceptance Criteria

1. **Given** the drill-down dashboard is open with a topic selected **When** the findings table renders at rows 13-18 (24 cols) **Then** a table panel (id=120) displays findings filtered by the selected topic (FR19) **And** the query filters by `{topic="$topic"}` **And** the PromQL aggregates by `anomaly_family` and `final_action` labels

2. **Given** a finding is displayed in the table **When** the action decision path is visible **Then** gate rule ID context is traceable by aggregating on `final_action` label from `aiops_findings_total` **And** the legend format surfaces the key decision labels

3. **Given** the drill-down dashboard is open with a topic selected **When** the diagnosis stats panels render at rows 19-23 (12 cols, left) **Then** a stat panel (id=130) displays per-topic LLM diagnosis invocation count for the selected topic **And** the query filters by `{topic="$topic"}`

4. **Given** the drill-down dashboard is open with a topic selected **When** the action rationale stat panel renders at rows 19-23 (12 cols, right) **Then** a stat panel (id=131) displays gating evaluation activity for the selected topic as action rationale proxy (FR21) **And** the query filters by `{topic="$topic"}`

5. **Given** no findings exist for the selected topic in the time window **When** the panels render **Then** meaningful zero-state displays via `fieldConfig.defaults.noValue` (UX-DR5, NFR9)

6. **Given** all panels are configured **When** the dashboard JSON is inspected **Then** panels use transparent backgrounds, one-sentence descriptions (UX-DR12), and panel IDs within 100-199 range **And** panels render within 5 seconds (NFR1)

## Tasks / Subtasks

- [ ] Task 1: Add findings table panel to `grafana/dashboards/aiops-drilldown.json` (AC: 1, 2, 5, 6)
  - [ ] 1.1 Add table panel: `type: "table"`, `id: 120`, `gridPos: {h: 6, w: 24, x: 0, y: 13}`
  - [ ] 1.2 Set panel `title: "Findings by topic"` (sentence case)
  - [ ] 1.3 Set `"transparent": true` on the panel
  - [ ] 1.4 Add target `refId: "A"`:
    `sum by(anomaly_family, final_action) (increase(aiops_findings_total{topic="$topic"}[$__range]))`
    with `legendFormat: "{{anomaly_family}} → {{final_action}}"`
  - [ ] 1.5 Set `datasource: {type: "prometheus", uid: "prometheus"}` on both panel and target
  - [ ] 1.6 Set `fieldConfig.defaults.noValue: "No findings this period"` (UX-DR5, NFR9, AC5)
  - [ ] 1.7 Set panel `description` to one sentence (UX-DR12)
  - [ ] 1.8 Set `fieldConfig.defaults.color.mode: "fixed"` with `fixedColor: "#4F87DB"` (neutral)
  - [ ] 1.9 Set `options.sortBy` on the table for sorted display

- [ ] Task 2: Add diagnosis stats panel to `grafana/dashboards/aiops-drilldown.json` (AC: 3, 5, 6)
  - [ ] 2.1 Add stat panel: `type: "stat"`, `id: 130`, `gridPos: {h: 5, w: 12, x: 0, y: 19}`
  - [ ] 2.2 Set panel `title: "Diagnosis count"` (sentence case)
  - [ ] 2.3 Set `"transparent": true` on the panel
  - [ ] 2.4 Add target `refId: "A"`:
    `sum(increase(aiops_diagnosis_completed_total{topic="$topic"}[$__range]))`
    with `legendFormat: "Diagnoses"`
  - [ ] 2.5 Set `datasource: {type: "prometheus", uid: "prometheus"}` on both panel and target
  - [ ] 2.6 Set `fieldConfig.defaults.color.mode: "fixed"` with `fixedColor: "#7A7A7A"` (neutral count)
  - [ ] 2.7 Set `options.colorMode: "none"` (plain count, no background health signal)
  - [ ] 2.8 Set `options.text.valueSize: 28` (UX-DR2)
  - [ ] 2.9 Set `fieldConfig.defaults.noValue: "0"` (UX-DR5)
  - [ ] 2.10 Set panel `description` to one sentence (UX-DR12)

- [ ] Task 3: Add action rationale stat panel to `grafana/dashboards/aiops-drilldown.json` (AC: 4, 5, 6)
  - [ ] 3.1 Add stat panel: `type: "stat"`, `id: 131`, `gridPos: {h: 5, w: 12, x: 12, y: 19}`
  - [ ] 3.2 Set panel `title: "Gating evaluations"` (sentence case)
  - [ ] 3.3 Set `"transparent": true` on the panel
  - [ ] 3.4 Add target `refId: "A"`:
    `sum(increase(aiops_gating_evaluations_total{topic="$topic"}[$__range]))`
    with `legendFormat: "Evaluations"`
  - [ ] 3.5 Set `datasource: {type: "prometheus", uid: "prometheus"}` on both panel and target
  - [ ] 3.6 Set `fieldConfig.defaults.color.mode: "thresholds"` with thresholds:
    - 0 → `#D94452` (red, no evaluations this window)
    - 1 → `#E8913A` (amber, low activity)
    - 10 → `#6BAD64` (green, healthy gating volume)
  - [ ] 3.7 Set `options.colorMode: "background"` (health signal for gating volume)
  - [ ] 3.8 Set `options.text.valueSize: 28` (UX-DR2)
  - [ ] 3.9 Set `fieldConfig.defaults.noValue: "0"` (UX-DR5)
  - [ ] 3.10 Set panel `description` to one sentence (UX-DR12)

- [ ] Task 4: Finalize dashboard version bump (AC: 6)
  - [ ] 4.1 Bump `aiops-drilldown.json` version from `3` to `4`
  - [ ] 4.2 Verify `"uid": "aiops-drilldown"` unchanged, `"schemaVersion": 39` unchanged
  - [ ] 4.3 Verify existing panels (id=100-102, 110) are NOT modified

- [ ] Task 5: Add config-validation tests (AC: 1-6)
  - [ ] 5.1 Extend `tests/integration/test_dashboard_validation.py` with class `TestFindingsTableActionDecisionTracing`
  - [ ] 5.2 Test: findings table panel (id=120) exists, type="table"
  - [ ] 5.3 Test: findings table panel gridPos y=13, h=6, w=24, x=0
  - [ ] 5.4 Test: findings table panel has `transparent: true`
  - [ ] 5.5 Test: findings table panel target PromQL uses `aiops_findings_total`
  - [ ] 5.6 Test: findings table panel target PromQL filters by `$topic`
  - [ ] 5.7 Test: findings table panel target PromQL aggregates by `anomaly_family`
  - [ ] 5.8 Test: findings table panel target PromQL aggregates by `final_action`
  - [ ] 5.9 Test: findings table panel has non-empty description
  - [ ] 5.10 Test: findings table panel has `noValue` field set (AC5)
  - [ ] 5.11 Test: no forbidden Grafana default palette colors in panel id=120 JSON
  - [ ] 5.12 Test: diagnosis count panel (id=130) exists, type="stat"
  - [ ] 5.13 Test: diagnosis count panel gridPos y=19, h=5, w=12, x=0
  - [ ] 5.14 Test: diagnosis count panel has `transparent: true`
  - [ ] 5.15 Test: diagnosis count panel target PromQL uses `aiops_diagnosis_completed_total`
  - [ ] 5.16 Test: diagnosis count panel target PromQL filters by `$topic`
  - [ ] 5.17 Test: diagnosis count panel has non-empty description
  - [ ] 5.18 Test: diagnosis count panel has `noValue` field set
  - [ ] 5.19 Test: diagnosis count panel `options.text.valueSize` >= 28
  - [ ] 5.20 Test: no forbidden Grafana default palette colors in panel id=130 JSON
  - [ ] 5.21 Test: gating evaluations panel (id=131) exists, type="stat"
  - [ ] 5.22 Test: gating evaluations panel gridPos y=19, h=5, w=12, x=12
  - [ ] 5.23 Test: gating evaluations panel has `transparent: true`
  - [ ] 5.24 Test: gating evaluations panel target PromQL uses `aiops_gating_evaluations_total`
  - [ ] 5.25 Test: gating evaluations panel target PromQL filters by `$topic`
  - [ ] 5.26 Test: gating evaluations panel has non-empty description
  - [ ] 5.27 Test: gating evaluations panel has `noValue` field set
  - [ ] 5.28 Test: gating evaluations panel `options.colorMode` == "background"
  - [ ] 5.29 Test: no forbidden Grafana default palette colors in panel id=131 JSON
  - [ ] 5.30 Test: drilldown dashboard version >= 4

## Dev Notes

### Critical Architecture Constraints (DO NOT DEVIATE)

- **Dashboard file**: `grafana/dashboards/aiops-drilldown.json` — only file to modify.
- **Dashboard UID**: `"uid": "aiops-drilldown"` is hardcoded. Do NOT modify.
- **Schema version**: `"schemaVersion": 39` is fixed — do NOT change.
- **Panel ID allocation** for this story:
  - `id: 120` → findings table (rows 13-18, 24 cols)
  - `id: 130` → diagnosis count stat (rows 19-23, 12 cols LEFT x=0)
  - `id: 131` → gating evaluations stat (rows 19-23, 12 cols RIGHT x=12)
  - IDs 100-102 and 110 are in use from stories 4-1 and 4-2.
- **Transparent backgrounds**: ALL panels require `"transparent": true`.
- **No live stack required**: All tests are static JSON parsing.
- **Color palette**: Only `#6BAD64`, `#E8913A`, `#D94452`, `#7A7A7A`, `#4F87DB`. Grafana defaults FORBIDDEN.
- **Ruff line-length = 100** for any Python files touched.

### Layout Reference (complete drill-down after story 4-3)

| Zone | Rows | Panel IDs | x | w | Story |
|---|---|---|---|---|---|
| Back navigation | 0 (h=1) | 100 (text) | 0 | 24 | 4-1 (done) |
| Topic health stat | 1-4 (h=4) | 101 (stat) | 0 | 8 | 4-1 (done) |
| Evidence status | 1-4 (h=4) | 102 (stat) | 8 | 16 | 4-2 (done) |
| Per-topic time series | 5-12 (h=8) | 110 (timeseries) | 0 | 24 | 4-2 (done) |
| **Findings table** | **13-18 (h=6)** | **120 (table)** | **0** | **24** | **This story** |
| **Diagnosis count** | **19-23 (h=5)** | **130 (stat)** | **0** | **12** | **This story** |
| **Gating evaluations** | **19-23 (h=5)** | **131 (stat)** | **12** | **12** | **This story** |

### Findings Table Design

Table panels use `type: "table"`. The PromQL query aggregates by both `anomaly_family` and
`final_action` to show the decision breakdown per finding family for the selected topic.

```promql
sum by(anomaly_family, final_action) (increase(aiops_findings_total{topic="$topic"}[$__range]))
```

This gives one row per (anomaly_family, final_action) pair — the closest proxy for action
decision tracing available from the existing metrics.

**noValue**: `"No findings this period"` — more descriptive than "0" for a table that shows
per-family decision rows (NFR9 / UX-DR5).

### Architecture Source References

- [Source: artifact/planning-artifacts/architecture.md#PromQL Style] — `{topic="$topic"}` exact match
- [Source: artifact/planning-artifacts/epics.md#Story 4.3] — FR19, FR21, UX-DR5, UX-DR12, NFR1, NFR9
- [Source: grafana/dashboards/aiops-drilldown.json] — current: 4 panels (100,101,102,110), version=3

## Dev Agent Record

### Agent Model Used

claude-sonnet-4-6

### Debug Log References

### Completion Notes List

### File List
