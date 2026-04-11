---
stepsCompleted:
  - step-01-preflight-and-context
  - step-02-generation-mode
  - step-03-test-strategy
  - step-04-generate-tests
  - step-04c-aggregate
  - step-05-validate-and-complete
lastStep: step-05-validate-and-complete
lastSaved: '2026-04-11'
story_id: '2-1'
tdd_phase: RED
inputDocuments:
  - artifact/implementation-artifacts/2-1-hero-banner-p-l-stat-panels.md
  - tests/integration/test_dashboard_validation.py
  - grafana/dashboards/aiops-main.json
  - _bmad/tea/config.yaml
---

# ATDD Checklist: Story 2-1 — Hero Banner & P&L Stat Panels

## Step 1: Preflight & Context

- **Detected stack**: `backend` (Python/pytest, `pyproject.toml` present, no frontend framework)
- **Story status**: `ready-for-dev`
- **Test framework**: pytest 9.0.2
- **Test directory**: `tests/`
- **Existing test file**: `tests/integration/test_dashboard_validation.py` (7 tests, all passing)
- **TEA config**: `_bmad/tea/config.yaml`
  - `test_stack_type: auto` → resolved `backend`
  - `tea_execution_mode: auto` → resolved `sequential` (single-agent run)
  - `tea_capability_probe: true`
- **Prerequisites**: All satisfied. Story has clear ACs, `conftest.py` present, JSON shell exists.

---

## Step 2: Generation Mode

**Selected mode**: AI generation (backend stack, ACs clear, config-validation style — no browser recording needed).

---

## Step 3: Test Strategy

### Acceptance Criteria → Test Map

| AC | Description | Test(s) | Level | Priority |
|---|---|---|---|---|
| AC1 | Hero banner stat panel, gridPos y=0 h=5 w=24 | `test_hero_banner_panel_exists`, `test_hero_banner_grid_position` | Integration/Config | P0 |
| AC1 | graphMode=none (no sparkline) | `test_hero_banner_no_sparkline` | Integration/Config | P0 |
| AC1 | colorMode=background | `test_hero_banner_background_color_mode` | Integration/Config | P0 |
| AC1 | Threshold steps: green/amber/red approved hex | `test_hero_banner_thresholds` | Integration/Config | P0 |
| AC1 | color.mode=thresholds | `test_hero_banner_color_field_config` | Integration/Config | P0 |
| AC1 | reduceOptions.calcs=["lastNotNull"] | `test_hero_banner_reduce_calc_last_not_null` | Integration/Config | P0 |
| AC2 | P&L stat panel, gridPos y=5 h=3 w=24 | `test_pl_stat_panel_exists`, `test_pl_stat_panel_grid_position` | Integration/Config | P0 |
| AC2 | graphMode=area (sparkline on) | `test_pl_stat_panel_sparkline_enabled` | Integration/Config | P0 |
| AC2 | Query: increase(aiops_findings_total[$__range]) | `test_pl_stat_query_uses_increase_range` | Integration/Config | P0 |
| AC2 | reduceOptions.calcs=["sum"] | `test_pl_stat_reduce_calc_sum` | Integration/Config | P0 |
| AC3 (UX-DR5) | P&L stat fixedColor=#6BAD64 (celebrated zero) | `test_pl_stat_celebrated_zero_color` | Integration/Config | P0 |
| AC3 (UX-DR12) | Hero banner has non-empty description | `test_hero_banner_has_description` | Integration/Config | P1 |
| AC3 (UX-DR12) | P&L stat has non-empty description | `test_pl_stat_has_description` | Integration/Config | P1 |
| AC3 (UX-DR1) | No forbidden Grafana default palette colors | `test_no_grafana_default_palette_colors_in_new_panels` | Integration/Config | P0 |

**Total tests generated**: 16  
**Not covered directly** (NFR/runtime): AC4 (5s render time, no-data state) and AC5 (WCAG AA) — these are runtime/visual concerns not testable via JSON config validation.

---

## Step 4: Test Generation (TDD RED PHASE)

### Execution Context

- Mode: `sequential` (single-agent capability)
- Phase: **RED** — all tests assert expected behavior against the current `aiops-main.json` shell which has `"panels": []`

### Files Modified

| File | Change |
|---|---|
| `tests/integration/test_dashboard_validation.py` | Added `TestHeroBannerPanels` class with 16 tests |

### Test Class Added

```
TestHeroBannerPanels (16 tests)
├── test_hero_banner_panel_exists           [P0] FAIL ✓
├── test_hero_banner_grid_position          [P0] FAIL ✓
├── test_hero_banner_no_sparkline           [P0] FAIL ✓
├── test_hero_banner_background_color_mode  [P0] FAIL ✓
├── test_hero_banner_thresholds             [P0] FAIL ✓
├── test_hero_banner_color_field_config     [P0] FAIL ✓
├── test_hero_banner_has_description        [P1] FAIL ✓
├── test_hero_banner_reduce_calc_last_not_null [P0] FAIL ✓
├── test_pl_stat_panel_exists               [P0] FAIL ✓
├── test_pl_stat_panel_grid_position        [P0] FAIL ✓
├── test_pl_stat_panel_sparkline_enabled    [P0] FAIL ✓
├── test_pl_stat_query_uses_increase_range  [P0] FAIL ✓
├── test_pl_stat_has_description            [P1] FAIL ✓
├── test_pl_stat_reduce_calc_sum            [P0] FAIL ✓
├── test_pl_stat_celebrated_zero_color      [P0] FAIL ✓
└── test_no_grafana_default_palette_colors_in_new_panels [P0] PASS* ✓
```

*`test_no_grafana_default_palette_colors_in_new_panels` trivially passes on empty panels array — this is correct and expected behavior; it will continue passing once panels are added (they must use approved palette only).

---

## Step 5: Validation & Completion

### Checklist

- [x] Prerequisites satisfied (story ready-for-dev, ACs clear, framework present)
- [x] Test file extended correctly (class added to existing file, no new files created)
- [x] All 16 tests cover the acceptance criteria
- [x] 15 tests fail before implementation (TDD red phase confirmed)
- [x] 1 test trivially passes on empty panels (palette enforcement — correct behavior)
- [x] No ruff violations (line-length 100 enforced)
- [x] No new test dependencies (stdlib `json` + `pathlib` only)
- [x] Pattern matches existing tests in same file
- [x] Pre-existing 7 tests continue to pass (no regressions)
- [x] Temp artifacts: N/A (sequential mode, no subagents)

### Summary Statistics

| Metric | Value |
|---|---|
| TDD Phase | RED |
| New tests added | 16 |
| Tests failing (expected) | 15 |
| Tests passing (trivially correct) | 1 |
| Pre-existing tests passing | 7 |
| Regressions introduced | 0 |
| New files created | 0 |
| Files modified | 1 |
| Ruff compliance | PASS |

### Next Steps (TDD Green Phase)

After implementing the story (adding panels to `grafana/dashboards/aiops-main.json`):

1. Run `pytest tests/integration/test_dashboard_validation.py -v`
2. All 16 `TestHeroBannerPanels` tests should PASS
3. All 7 pre-existing tests should continue to PASS
4. Expected total: 23 passing in this file
5. If any fail: either fix the JSON (implementation bug) or fix the test (spec interpretation)
6. Commit the dashboard JSON and confirm CI green

### Key Risks / Assumptions

- `test_dashboards_have_no_panels_initially` in `TestDashboardJsonShells` will need updating (or removal) once panels are added — it asserts panels is a list (still true), so it will keep passing.
- AC4 (NFR1: render <5s) and AC5 (WCAG AA) are not covered by these config-validation tests. They require a live Grafana instance or visual testing tool — out of scope per story dev notes.
- The palette test passes trivially today but provides a hard guard against accidentally using Grafana default colors once implementation happens.
