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
inputDocuments:
  - artifact/implementation-artifacts/2-2-topic-health-heatmap.md
  - tests/integration/test_dashboard_validation.py
  - grafana/dashboards/aiops-main.json
  - _bmad/tea/config.yaml
---

# ATDD Checklist: Story 2-2 — Topic Health Heatmap

## TDD Red Phase (Current)

All 14 new tests generated. 13 fail (RED phase confirmed), 1 passes vacuously
(forbidden-color exclusion on absent panel — correct behaviour).

- **Integration Tests**: 14 tests (RED phase — fail until panel id=3 is added)
- **Total tests collected**: 40 (26 original + 14 new)
- **Baseline preserved**: All 26 prior tests still PASS

## Acceptance Criteria Coverage

| AC | Test Method | Priority | Status |
|----|-------------|----------|--------|
| AC1: Panel id=3 exists, type=stat | `test_heatmap_panel_exists` | P0 | RED |
| AC1: gridPos y=8, h=6, w=24 | `test_heatmap_grid_position` | P0 | RED |
| AC1: colorMode=background | `test_heatmap_background_color_mode` | P0 | RED |
| AC1: graphMode=none | `test_heatmap_no_sparkline` | P0 | RED |
| AC1: values=true, limit=10 | `test_heatmap_values_mode_for_per_topic_tiles` | P1 | RED |
| AC1 (UX-DR9): Approved palette thresholds | `test_heatmap_thresholds_use_approved_palette` | P0 | RED |
| AC1: color.mode=thresholds | `test_heatmap_color_field_config_mode_is_thresholds` | P1 | RED |
| AC4 (UX-DR1): No forbidden colors | `test_no_grafana_default_palette_colors_in_heatmap` | P1 | vacuous PASS |
| AC4 (UX-DR12): Non-empty description | `test_heatmap_has_description` | P1 | RED |
| AC3: Data link → aiops-drilldown + var-topic | `test_heatmap_has_data_link_to_drilldown` | P0 | RED |
| AC3: ${__url_time_range} preserved | `test_heatmap_data_link_preserves_time_range` | P0 | RED |
| AC1 (UX-DR14): Value mappings for WCAG AA | `test_heatmap_has_value_mappings` | P1 | RED |
| AC4 (NFR5): noValue guard | `test_heatmap_has_no_value_message` | P2 | RED |
| Dashboard version = 3 (NFR12) | `test_dashboard_version_is_3` | P1 | RED |

## Test File

`tests/integration/test_dashboard_validation.py` — class `TestTopicHealthHeatmap`

## Execution Results (Red Phase)

```
13 FAILED (new TestTopicHealthHeatmap tests — panel id=3 not yet in aiops-main.json)
27 PASSED (26 original + 1 vacuous forbidden-color pass)
```

## Next Steps (TDD Green Phase)

After implementing the feature (adding panel id=3 to `grafana/dashboards/aiops-main.json`
and bumping version to 3), all 14 tests should PASS.

Implementation checklist from story tasks:
1. Add panel id=3 to `grafana/dashboards/aiops-main.json` (Tasks 1.1–1.11)
2. Run: `python3 -m pytest tests/integration/test_dashboard_validation.py -v`
3. Verify all 40 tests PASS (green phase)
4. Commit implementation

## Key Implementation Constraints

- Panel must use `type: "stat"` (NOT `type: "heatmap"`)
- `options.reduceOptions.values: true` + `limit: 10` for per-topic tiles
- Thresholds: `#6BAD64` (null/HEALTHY), `#E8913A` (1/WARNING), `#D94452` (2/CRITICAL)
- Data link in `fieldConfig.defaults.links` (NOT in `options.links`)
- Data link URL: `/d/aiops-drilldown?var-topic=${__field.labels.topic}&${__url_time_range}`
- Dashboard `version` incremented from 2 to 3

## Assumptions / Risks

- `test_no_grafana_default_palette_colors_in_heatmap` passes vacuously pre-implementation.
  It will catch color violations post-implementation (enforcement gate remains active).
- No ruff lint violations introduced — all lines ≤ 100 chars verified.
