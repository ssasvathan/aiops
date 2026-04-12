# Story 3.2: Action Distribution & Anomaly Family Breakdown

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As an SRE Director,
I want to see the distribution of actions over time and the breakdown of anomaly types,
so that I can confirm the platform maintains a stable, low-noise action profile and understand what types of anomalies the system detects.

## Acceptance Criteria

1. **Given** the main dashboard is scrolled to the credibility zone **When** the action distribution panel renders at rows 30-34 (12 cols, left) **Then** a stacked time-series panel displays OBSERVE, NOTIFY, TICKET, and PAGE counts over time (FR12) **And** each action type uses a consistent color from the muted palette **And** the query uses `rate(aiops_findings_total[$__rate_interval])` with `sum by(final_action)` aggregation

2. **Given** no PAGE actions occurred in the time window (expected in dev) **When** the panel renders **Then** the PAGE series shows as zero — a celebrated zero-state, not a missing series (UX-DR5, NFR9)

3. **Given** the main dashboard is scrolled to the credibility zone **When** the anomaly family breakdown panel renders at rows 30-34 (12 cols, right) **Then** a bar chart displays findings grouped by anomaly family: consumer lag, volume drop, throughput constrained proxy, baseline deviation (FR10) **And** bars are horizontal, sorted by value, with semantic color per anomaly family **And** the query uses `increase(aiops_findings_total[$__range])` with `sum by(anomaly_family)` aggregation

4. **Given** both panels are configured **When** the dashboard JSON is inspected **Then** both panels use transparent backgrounds, have one-sentence descriptions (UX-DR12), and panel IDs are within 1-99 range **And** both panels render within 5 seconds (NFR1)

## Tasks / Subtasks

- [x] Task 1: Add action distribution (timeseries panel) to `grafana/dashboards/aiops-main.json` (AC: 1, 2, 4)
  - [x] 1.1 Add timeseries panel: `type: "timeseries"`, `id: 8`, `gridPos: {h: 5, w: 12, x: 0, y: 30}`
  - [x] 1.2 Set panel `title: "Action distribution"` (sentence case per architecture convention)
  - [x] 1.3 Set `"transparent": true` on the panel (timeseries panels require explicit transparent — established in story 2-3 as H1 finding)
  - [x] 1.4 Add target `refId: "A"`: `sum by(final_action) (rate(aiops_findings_total[$__rate_interval]))` with `legendFormat: "{{final_action}}"`
  - [x] 1.5 Set `datasource: {type: "prometheus", uid: "prometheus"}` on both panel and target
  - [x] 1.6 Configure `fieldConfig.defaults.custom.stacking.mode: "normal"` for stacked time-series display
  - [x] 1.7 Configure color overrides mapping each `final_action` series to muted palette: OBSERVE→`#4F87DB`, NOTIFY→`#E8913A`, TICKET→`#D94452`, PAGE→`#6BAD64` (no-PAGE=celebrated-zero in green)
  - [x] 1.8 Set `fieldConfig.defaults.noValue: "0"` to show celebrated zeros (UX-DR5 / NFR9) — PAGE as zero, not missing series
  - [x] 1.9 Set panel `description` to one sentence explaining action distribution (UX-DR12)

- [x] Task 2: Add anomaly family breakdown (barchart panel) to `grafana/dashboards/aiops-main.json` (AC: 3, 4)
  - [x] 2.1 Add barchart panel: `type: "barchart"`, `id: 9`, `gridPos: {h: 5, w: 12, x: 12, y: 30}`
  - [x] 2.2 Set panel `title: "Anomaly family breakdown"` (sentence case)
  - [x] 2.3 Set `"transparent": true` on the panel
  - [x] 2.4 Set `options.orientation: "horizontal"` for horizontal bars (UX-DR3 / FR10 — sorted horizontal bars)
  - [x] 2.5 Add target `refId: "A"`: `sum by(anomaly_family) (increase(aiops_findings_total[$__range]))` with `legendFormat: "{{anomaly_family}}"`
  - [x] 2.6 Set `datasource: {type: "prometheus", uid: "prometheus"}` on both panel and target
  - [x] 2.7 Configure `options.text.titleSize: 14` and `options.text.valueSize: 14` to meet UX-DR2 (14px+ labels)
  - [x] 2.8 Set `fieldConfig.defaults.color.mode: "thresholds"` (avoids unauthorized named Grafana palettes — lesson from story 3-1 review)
  - [x] 2.9 Configure threshold steps using approved palette only: grey `#7A7A7A` (base), green `#6BAD64` for positive counts
  - [x] 2.10 Set `fieldConfig.defaults.noValue: "0"` for zero-state anomaly families (UX-DR5 / NFR9)
  - [x] 2.11 Set panel `description` to one sentence explaining anomaly family breakdown (UX-DR12)

- [x] Task 3: Finalize dashboard version bump (AC: 4)
  - [x] 3.1 Bump dashboard top-level `"version"` from `5` to `6`
  - [x] 3.2 Verify `"uid": "aiops-main"` unchanged, `"schemaVersion": 39` unchanged
  - [x] 3.3 Verify existing panels (id=1 through id=7) are not modified

- [x] Task 4: Add config-validation tests for both panels (AC: 1, 2, 3, 4)
  - [x] 4.1 Extend `tests/integration/test_dashboard_validation.py` with class `TestActionDistributionAnomalyBreakdown`
  - [x] 4.2 Test: action distribution panel (id=8) exists, type="timeseries"
  - [x] 4.3 Test: action distribution panel gridPos y=30, h=5, w=12, x=0
  - [x] 4.4 Test: action distribution panel has `transparent: true` (UX-DR4)
  - [x] 4.5 Test: action distribution panel target refId="A" PromQL uses `rate(` and `$__rate_interval` (timeseries panel convention)
  - [x] 4.6 Test: action distribution panel target PromQL uses `aiops_findings_total`
  - [x] 4.7 Test: action distribution panel target PromQL uses `sum by(` aggregation style (not `sum(` ... `by(`)
  - [x] 4.8 Test: action distribution panel target PromQL uses `sum by(final_action)` label
  - [x] 4.9 Test: action distribution panel target `legendFormat` contains `final_action` (so series labels render)
  - [x] 4.10 Test: action distribution panel has non-empty description (UX-DR12)
  - [x] 4.11 Test: action distribution panel has `noValue` field set (NFR5 / UX-DR5)
  - [x] 4.12 Test: no forbidden Grafana default palette colors in panel id=8 JSON (case-insensitive `.upper()`)
  - [x] 4.13 Test: anomaly family breakdown panel (id=9) exists, type="barchart"
  - [x] 4.14 Test: anomaly family breakdown panel gridPos y=30, h=5, w=12, x=12
  - [x] 4.15 Test: anomaly family breakdown panel has `transparent: true` (UX-DR4)
  - [x] 4.16 Test: anomaly family breakdown panel target refId="A" PromQL uses `increase(` and `$__range` (stat/bargauge/barchart convention)
  - [x] 4.17 Test: anomaly family breakdown panel target PromQL uses `aiops_findings_total`
  - [x] 4.18 Test: anomaly family breakdown panel target PromQL uses `sum by(anomaly_family)` label
  - [x] 4.19 Test: anomaly family breakdown panel target `legendFormat` contains `anomaly_family`
  - [x] 4.20 Test: anomaly family breakdown panel has non-empty description (UX-DR12)
  - [x] 4.21 Test: anomaly family breakdown panel has `noValue` field set (NFR5 / UX-DR5)
  - [x] 4.22 Test: no forbidden Grafana default palette colors in panel id=9 JSON (case-insensitive `.upper()`)
  - [x] 4.23 Test: anomaly family breakdown panel `options.text.titleSize` >= 14 (UX-DR2)
  - [x] 4.24 Test: dashboard version >= 6 after story 3-2 additions

## Dev Notes

### Critical Architecture Constraints (DO NOT DEVIATE)

- **Dashboard file**: `grafana/dashboards/aiops-main.json` — single source of truth. Do NOT use Grafana UI without re-exporting.
- **Dashboard UID**: `"uid": "aiops-main"` is a hardcoded constant. Do NOT modify.
- **Schema version**: `"schemaVersion": 39` is fixed — do NOT change.
- **Panel ID allocation**:
  - `id: 8` → action distribution (timeseries, rows 30-34 left half)
  - `id: 9` → anomaly family breakdown (barchart, rows 30-34 right half)
  - IDs 1-7 are in use; never overlap with drill-down (100-199).
- **Grid positions** (UX-DR3 "The Newspaper" layout):
  - Action distribution: `{h: 5, w: 12, x: 0, y: 30}` — left 12 cols, rows 30-34
  - Anomaly family breakdown: `{h: 5, w: 12, x: 12, y: 30}` — right 12 cols, rows 30-34
  - NOTE: `x=0` for left panel, `x=12` for right panel. The `x=0` test assertion applies to the left panel only.
- **Transparent backgrounds**: BOTH panels require `"transparent": true`. This was an H1 review finding in story 2-3 and re-confirmed in 3-1. Timeseries and barchart panels need explicit `transparent: true` — stat panels handle transparency differently via colorMode.
- **No live stack required**: All tests are static JSON parsing (config-validation style).
- **Color palette — ONLY these hex values**: `#6BAD64` (green), `#E8913A` (amber), `#D94452` (red), `#7A7A7A` (grey), `#4F87DB` (accent-blue). Grafana defaults are FORBIDDEN.
- **Ruff line-length = 100** for any Python files touched.

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
| **Action distribution** | **30-34 (h=5, 12 cols left)** | **8** | **This story** |
| **Anomaly family breakdown** | **30-34 (h=5, 12 cols right)** | **9** | **This story** |
| Diagnosis stats | 36-40 (h=5, 12 cols right) | TBD | Story 3-3 |
| Capability stack | 36-40 (h=5, 12 cols left) | TBD | Story 3-4 |

**gridPos invariant for left panel**: `x: 0, w: 12`. For right panel: `x: 12, w: 12`.
Always assert `x == 0` in position test for id=8, `x == 12` for id=9.

### Panel Type Decision Rationale

**Action Distribution** — use `"timeseries"`:
- FR12 requires stacked time-series showing OBSERVE, NOTIFY, TICKET, PAGE counts over time.
- Use `fieldConfig.defaults.custom.stacking.mode: "normal"` for stack behavior in Grafana 12.x.
- PromQL: `rate(aiops_findings_total[$__rate_interval])` with `sum by(final_action)` — this is a **timeseries panel** so MUST use `$__rate_interval`, NEVER `$__range`.
- `legendFormat: "{{final_action}}"` produces series named `OBSERVE`, `NOTIFY`, `TICKET`, `PAGE`.
- Color overrides by series name map each action to the muted palette (use `fieldConfig.overrides` with `byName` matcher).

**Anomaly Family Breakdown** — use `"barchart"` (NOT `"bargauge"`):
- FR10 requires a bar chart of findings by anomaly family — this is a categorical breakdown, not a funnel.
- `"barchart"` is the correct panel type for bar charts in Grafana 12.x. Do NOT use `"bargauge"` (that is for the funnel — different visual semantics and config).
- `options.orientation: "horizontal"` for horizontal bars sorted by value.
- PromQL: `increase(aiops_findings_total[$__range])` with `sum by(anomaly_family)` — this is a **stat-family panel** so MUST use `$__range`, NEVER `$__rate_interval`.
- `legendFormat: "{{anomaly_family}}"` produces bars named `BASELINE_DEVIATION`, `CONSUMER_LAG`, `VOLUME_DROP`, `THROUGHPUT_CONSTRAINED_PROXY`.

### PromQL Query Design

**Aggregation style** (architecture mandate): `sum by(label) (metric)` — NEVER `sum(metric) by(label)`.

**Range vector rule**:
- `$__rate_interval` → timeseries panels only (action distribution panel)
- `$__range` → stat/bargauge/barchart panels (anomaly family breakdown panel)
- Mixing these is a critical anti-pattern that causes incorrect data in one panel type.

**Metric**: `aiops_findings_total` — counter emitted in Epic 1, story 1-2.
- Python name: `aiops.findings.total` (dotted)
- PromQL name: `aiops_findings_total` (underscored)
- Labels: `anomaly_family`, `final_action`, `topic`, `routing_key`, `criticality_tier`
- Label values use uppercase Python enum strings: `BASELINE_DEVIATION`, `CONSUMER_LAG`, `VOLUME_DROP`, `THROUGHPUT_CONSTRAINED_PROXY`, `OBSERVE`, `NOTIFY`, `TICKET`, `PAGE`

**Action distribution query** (timeseries, `id: 8`):
```
sum by(final_action) (rate(aiops_findings_total[$__rate_interval]))
```
legendFormat: `{{final_action}}`

**Anomaly family breakdown query** (barchart, `id: 9`):
```
sum by(anomaly_family) (increase(aiops_findings_total[$__range]))
```
legendFormat: `{{anomaly_family}}`

### Color Strategy

**Action Distribution Panel (id=8)** — use `fieldConfig.overrides` with `byName` matcher per series:
- `OBSERVE` → `#4F87DB` (accent-blue — informational)
- `NOTIFY` → `#E8913A` (semantic-amber — warning)
- `TICKET` → `#D94452` (semantic-red — escalation)
- `PAGE` → `#6BAD64` (semantic-green — celebrated zero; PAGE = rare/never in dev)

Override pattern:
```json
{
  "matcher": {"id": "byName", "options": "PAGE"},
  "properties": [{"id": "color", "value": {"mode": "fixed", "fixedColor": "#6BAD64"}}]
}
```

**Anomaly Family Breakdown Panel (id=9)** — use `fieldConfig.defaults.color.mode: "thresholds"` (avoids `continuous-BlPu` issue from story 3-1 review where unauthorized named palette leaked in). All bars should render in the approved palette only.

### Zero-State Handling

Both panels require `fieldConfig.defaults.noValue: "0"`:
- Action distribution: PAGE series renders as zero line, not missing (UX-DR5, NFR9)
- Anomaly breakdown: families with no occurrences show 0, not blank (NFR9)

### JSON Manipulation Pattern

Current `aiops-main.json` has 7 panels (id=1 through id=7). Add panels as 8th and 9th elements:

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
  { /* anomaly family breakdown, id: 9 */ }
]
```

Increment `"version"` from `5` to `6`.

**Do NOT change**: `uid`, `schemaVersion`, `title`, `description`, `timezone`, `time`, `timepicker`, `refresh`, `tags`, `annotations`, or any existing panels (id=1 through id=7).

### Color Palette Reference (Complete)

| Token | Hex | Usage in this story |
|---|---|---|
| semantic-green | `#6BAD64` | PAGE series (celebrated zero), barchart base threshold |
| semantic-amber | `#E8913A` | NOTIFY series |
| semantic-red | `#D94452` | TICKET series |
| semantic-grey | `#7A7A7A` | Barchart null threshold (base step) |
| accent-blue | `#4F87DB` | OBSERVE series (informational) |

**Forbidden Grafana defaults**: `#73BF69`, `#F2495C`, `#FF9830`, `#FADE2A`, `#5794F2`, `#B877D9`, `#37872D`, `#C4162A`, `#1F60C4`, `#8F3BB8`. Caught by `scripts/validate-colors.sh`.

### Testing Pattern for Config-Validation Tests

**File to extend**: `tests/integration/test_dashboard_validation.py`
**New class**: `TestActionDistributionAnomalyBreakdown`

Follow the exact conventions from `TestGatingIntelligenceFunnel` (story 3-1):
- `_load_main_dashboard()` helper reads `grafana/dashboards/aiops-main.json`
- `_get_panel_by_id(dashboard, panel_id)` helper extracts panel by ID
- Case-insensitive forbidden palette check: `json.dumps(...).upper()` before asserting on hex colors
- All test methods have docstrings referencing the AC they cover
- Dashboard version tests use `>= N` NEVER `== N` (forward-compatible convention — established in epics 1-3)
- All position tests must assert `x`, `y`, `w`, and `h`
- `transparent: true` must be tested for timeseries and barchart panels (non-stat panel transparency)
- Font size (`options.text.titleSize`) must be asserted for barchart panel (bargauge pattern — UX-DR2)
- `legendFormat` must be tested for both panels (queries use labels; format could silently degrade)
- `displayMode` must be tested for bargauge panels only — barchart does not use displayMode

**Class docstring** must NOT contain TDD red-phase language (this was a review finding in story 3-1 that required a patch fix).

**Test class template**:
```python
class TestActionDistributionAnomalyBreakdown:
    """Config-validation tests for story 3-2: action distribution timeseries (id=8)
    and anomaly family breakdown barchart (id=9).

    No live docker-compose stack required — all assertions are pure JSON parsing.
    """

    def _load_main_dashboard(self):
        path = REPO_ROOT / "grafana/dashboards/aiops-main.json"
        return json.loads(path.read_text())

    def _get_panel_by_id(self, dashboard, panel_id):
        panels = dashboard.get("panels", [])
        return next((p for p in panels if p.get("id") == panel_id), None)
```

### Learnings from Previous Stories (Apply Upfront)

The following patterns are **mandatory** — deviating causes review findings:

1. **`transparent: true`** on ALL non-stat panels — timeseries, bargauge, barchart all require explicit `"transparent": true`. Stat panels use colorMode instead.
2. **Version tests use `>= N`** pattern, never `== N`.
3. **Font size `options.text.titleSize >= 14`** must be tested for barchart/bargauge panels (UX-DR2).
4. **`gridPos.x == 0`** must be asserted in position test for id=8 (left panel). For id=9, assert `x == 12`.
5. **Case-insensitive palette check**: `json.dumps(panel).upper()` before checking forbidden colors.
6. **No TDD red-phase comments** in class docstring — clean up before submitting.
7. **`displayMode` test** for bargauge panels — but `barchart` is NOT a bargauge; do not add displayMode test for id=9.
8. **`legendFormat` test** for queries with labels — both id=8 and id=9 use label-based legendFormat; test both.
9. **Avoid `continuous-BlPu`** or any named Grafana color mode — use `"mode": "thresholds"` or `"mode": "fixed"` with approved hex values only.
10. **PromQL aggregation style**: `sum by(label) (metric)` — NEVER `sum(metric) by(label)`.

### Current State of aiops-main.json

```
version: 5
panels (7 total):
  id=1 type=stat     title="Pipeline health"                  gridPos={h:5, w:24, x:0, y:0}
  id=2 type=stat     title="Anomalies detected & acted on"    gridPos={h:3, w:24, x:0, y:5}
  id=3 type=stat     title="Topic health"                     gridPos={h:6, w:24, x:0, y:8}
  id=4 type=text     title=""                                 gridPos={h:1, w:24, x:0, y:14}
  id=5 type=timeseries title="Baseline deviation overlay"     gridPos={h:8, w:24, x:0, y:15}
  id=6 type=text     title=""                                 gridPos={h:1, w:24, x:0, y:23}
  id=7 type=bargauge title="Gating intelligence funnel"       gridPos={h:6, w:24, x:0, y:24}
```

Next available panel ID: 8 (action distribution), 9 (anomaly family breakdown).
After this story: 10 panels, version=6.

### File Change Summary

| File | Change |
|---|---|
| `grafana/dashboards/aiops-main.json` | Add panels id=8 and id=9; version 5→6 |
| `tests/integration/test_dashboard_validation.py` | Append class `TestActionDistributionAnomalyBreakdown` (~24 tests) |

No changes to: `health/metrics.py`, `docker-compose.yml`, provisioning YAML files, or any panel id=1–7.

### References

- FR10, FR12: Anomaly family breakdown and action distribution requirements [epics.md]
- UX-DR3: "The Newspaper" layout — rows 30-34 split 12 cols each [epics.md]
- UX-DR4: Transparent panel backgrounds [epics.md]
- UX-DR5: Zero-state patterns — celebrated zeros in semantic-green [epics.md]
- UX-DR12: One-sentence panel descriptions on every panel [epics.md]
- NFR1, NFR9: 5-second render, meaningful zero-states [epics.md]
- PromQL aggregation style and range vector conventions [architecture.md — PromQL Query Patterns]
- Panel ID allocation 1-99 main dashboard [architecture.md — Grafana Dashboard JSON Patterns]
- Color palette (6 tokens + forbidden Grafana defaults) [architecture.md — Color semantic enforcement]
- Story 3-1 review findings: transparent, displayMode, legendFormat, no red-phase docstring [artifact/implementation-artifacts/3-1-gating-intelligence-funnel-per-gate-suppression.md]

## Review Findings

- [x] [Review][Patch] Panel id=8 missing `fieldConfig.defaults.color` fallback — violates architecture pattern established in story 2-3 (panel id=5 sets `"color": {"mode": "fixed", "fixedColor": "#4F87DB"}`); without it, any series not matched by a byName override falls back to Grafana classic palette which contains forbidden colors [grafana/dashboards/aiops-main.json:318] — **FIXED**: added `"color": {"mode": "fixed", "fixedColor": "#4F87DB"}` to fieldConfig.defaults
- [x] [Review][Patch] Panel id=9 missing `options.sort: "desc"` — AC3 explicitly requires bars "sorted by value" but the barchart panel had no sort key, defaulting to data-order rendering [grafana/dashboards/aiops-main.json:376] — **FIXED**: added `"sort": "desc"` to options
- [x] [Review][Patch] Test class missing test for `stacking.mode = "normal"` on panel id=8 — AC1 (FR12) requires stacked time-series; stacking config was present but untested [tests/integration/test_dashboard_validation.py] — **FIXED**: added `test_action_distribution_panel_uses_stacking_normal`
- [x] [Review][Patch] Test class missing test for `options.orientation = "horizontal"` on panel id=9 — AC3 / UX-DR3 requires horizontal bars; orientation was present but untested [tests/integration/test_dashboard_validation.py] — **FIXED**: added `test_anomaly_family_breakdown_panel_uses_horizontal_orientation`
- [x] [Review][Patch] Test class missing test for `options.sort = "desc"` on panel id=9 — AC3 requires sorted-by-value bars; sort option was absent and untested [tests/integration/test_dashboard_validation.py] — **FIXED**: added `test_anomaly_family_breakdown_panel_is_sorted_desc`

## Dev Agent Record

### Agent Model Used

claude-sonnet-4-6

### Debug Log References

None — implementation completed in first pass without issues.

### Completion Notes List

- Implemented panel id=8 (timeseries, "Action distribution") with `sum by(final_action) (rate(aiops_findings_total[$__rate_interval]))`, stacking mode "normal", per-series color overrides using approved muted palette (OBSERVE:#4F87DB, NOTIFY:#E8913A, TICKET:#D94452, PAGE:#6BAD64), noValue="0", transparent=true.
- Implemented panel id=9 (barchart, "Anomaly family breakdown") with `sum by(anomaly_family) (increase(aiops_findings_total[$__range]))`, horizontal orientation, thresholds color mode (grey base → green), options.text.titleSize=14, noValue="0", transparent=true.
- Bumped dashboard version from 5 to 6. uid="aiops-main" and schemaVersion=39 unchanged. Panels id=1–7 unmodified.
- All 23 TestActionDistributionAnomalyBreakdown ATDD tests pass. Full regression suite: 97/97 passing.

### File List

- grafana/dashboards/aiops-main.json
- artifact/implementation-artifacts/3-2-action-distribution-anomaly-family-breakdown.md
- artifact/implementation-artifacts/sprint-status.yaml

### Change Log

- 2026-04-11: Added panel id=8 (action distribution timeseries) and id=9 (anomaly family breakdown barchart) to aiops-main.json; bumped dashboard version 5→6. All 23 ATDD tests pass, 97/97 regression tests pass.
