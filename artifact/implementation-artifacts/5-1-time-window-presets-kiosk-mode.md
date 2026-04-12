# Story 5.1: Time Window Presets & Kiosk Mode

Status: ready-for-dev

## Story

As a presenter delivering a stakeholder demo,
I want configurable time window presets and a presentation-friendly kiosk mode,
So that I can control the narrative time context and present without Grafana chrome distracting the audience.

## Acceptance Criteria

1. **Given** the main dashboard is opened **When** the Grafana time picker is configured **Then** quick range presets are available for 1h, 6h, 24h, 7d, and 30d (FR32) **And** the default time window is 7d for the main dashboard

2. **Given** the drill-down dashboard is opened **When** the time picker is used **Then** the same quick range presets are available **And** the default time window is 24h for the drill-down (already set in story 4-1) **And** time window changes apply to ALL panels simultaneously

3. **Given** kiosk mode is documented **When** the presenter appends `?kiosk` to the dashboard URL **Then** this is a Grafana built-in feature that hides navigation chrome (FR34) — documented in dashboard description field

4. **Given** all panels are configured **When** dashboard JSON is inspected **Then** `time.from` is `"now-7d"` for main, `"now-24h"` for drill-down **And** both dashboards have `timepicker.time_options` with required presets **And** main dashboard version incremented

## Tasks / Subtasks

- [ ] Task 1: Update main dashboard time defaults (AC: 1, 4)
  - [ ] 1.1 Set `aiops-main.json` `"time": {"from": "now-7d", "to": "now"}` (default 7d)
  - [ ] 1.2 Set `aiops-main.json` `"timepicker": {"time_options": ["1h", "6h", "24h", "7d", "30d"]}` (FR32)
  - [ ] 1.3 Bump `aiops-main.json` version from `8` to `9`

- [ ] Task 2: Update drill-down dashboard timepicker presets (AC: 2, 4)
  - [ ] 2.1 Set `aiops-drilldown.json` `"timepicker": {"time_options": ["1h", "6h", "24h", "7d", "30d"]}` (FR32)
  - [ ] 2.2 Verify `time.from` is already `"now-24h"` (set in story 4-1) — do NOT change
  - [ ] 2.3 Bump `aiops-drilldown.json` version from `4` to `5`

- [ ] Task 3: Add config-validation tests (AC: 1, 2, 4)
  - [ ] 3.1 Extend `tests/integration/test_dashboard_validation.py` with class `TestTimeWindowPresetsKioskMode`
  - [ ] 3.2 Test: main dashboard `time.from` == `"now-7d"`
  - [ ] 3.3 Test: main dashboard `timepicker.time_options` contains `"1h"`
  - [ ] 3.4 Test: main dashboard `timepicker.time_options` contains `"6h"`
  - [ ] 3.5 Test: main dashboard `timepicker.time_options` contains `"24h"`
  - [ ] 3.6 Test: main dashboard `timepicker.time_options` contains `"7d"`
  - [ ] 3.7 Test: main dashboard `timepicker.time_options` contains `"30d"`
  - [ ] 3.8 Test: drilldown dashboard `time.from` == `"now-24h"`
  - [ ] 3.9 Test: drilldown dashboard `timepicker.time_options` contains `"1h"`
  - [ ] 3.10 Test: drilldown dashboard `timepicker.time_options` contains `"7d"`
  - [ ] 3.11 Test: main dashboard version >= 9
  - [ ] 3.12 Test: drilldown dashboard version >= 5

## Dev Notes

### Critical Architecture Constraints (DO NOT DEVIATE)

- **Files to modify**: `grafana/dashboards/aiops-main.json` AND `grafana/dashboards/aiops-drilldown.json`
- **Kiosk mode**: Built-in Grafana feature via `?kiosk` URL parameter — NO code changes needed.
- **No panel changes**: Only `time`, `timepicker`, and `version` fields are modified.
- **Ruff line-length = 100** for any Python files touched.

### Timepicker Configuration

```json
"timepicker": {
  "time_options": ["1h", "6h", "24h", "7d", "30d"]
}
```

The `time_options` array populates Grafana's quick-range dropdown.

### Version Bumps

- `aiops-main.json`: version `8` → `9`
- `aiops-drilldown.json`: version `4` → `5`

## Dev Agent Record

### Agent Model Used

claude-sonnet-4-6

### Debug Log References

### Completion Notes List

### File List
