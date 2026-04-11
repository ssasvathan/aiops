---
stepsCompleted:
  - step-01-preflight-and-context
  - step-02-generation-mode
  - step-03-test-strategy
  - step-04-generate-tests
  - step-05-validate-and-complete
lastStep: step-05-validate-and-complete
lastSaved: 2026-04-11
inputDocuments:
  - artifact/implementation-artifacts/2-3-baseline-deviation-overlay-with-detection-annotations.md
  - tests/integration/test_dashboard_validation.py
  - grafana/dashboards/aiops-main.json
  - pyproject.toml
  - .claude/skills/bmad-testarch-atdd/resources/knowledge/test-levels-framework.md
  - .claude/skills/bmad-testarch-atdd/resources/knowledge/test-quality.md
---

# ATDD Checklist — Story 2-3: Baseline Deviation Overlay with Detection Annotations

## Step 1: Preflight & Context

### Stack Detection
- **Detected stack**: `backend`
  - Indicator: `pyproject.toml` present
  - No frontend indicators (no `package.json`, `playwright.config.*`, `vite.config.*`)
  - Result: Pure Python backend project

### Prerequisites
- [x] Story 2-3 approved with clear acceptance criteria (5 ACs, 11 required tests)
- [x] Test framework configured: `conftest.py` + `pyproject.toml` pytest config
- [x] Development environment available

### Story Context (AC Summary)
| AC | Given / When / Then |
|----|---------------------|
| AC1 | Fold separator panel at row 14, h=1, w=24 (FR29) |
| AC2 | Baseline overlay panel (id=5), timeseries, rows 15-22, actual line accent-blue, band-fill 12% |
| AC3 | Detection event markers in semantic-amber #E8913A via dashboard annotations |
| AC4 | Transparent background, description set, PromQL uses rate([$__rate_interval]), ID 1-99 |
| AC5 | Data within 5s, noValue="Awaiting data", no "No data" errors |

### Framework & Existing Patterns
- Test file: `tests/integration/test_dashboard_validation.py`
- Pattern: config-validation (static JSON parsing, no live stack)
- Existing classes: `TestPrometheusConfig`, `TestGrafanaDatasourceConfig`, `TestDashboardProvisioningConfig`, `TestDashboardJsonShells`, `TestHeroBannerPanels`, `TestTopicHealthHeatmap`
- Prior count: 41 tests, 1496 suite-wide passing

---

## Step 2: Generation Mode

**Mode selected**: AI generation (sequential)
**Reason**: Backend stack, no browser recording needed, all ACs are pure JSON-structure assertions.

---

## Step 3: Test Strategy

### AC → Test Level Mapping

| AC | Test Level | Justification |
|----|-----------|---------------|
| AC1 (fold separator existence) | Integration (config-validation) | Static JSON parsing of dashboard file |
| AC1 (fold separator type) | Integration (config-validation) | Static JSON parsing |
| AC2 (overlay existence + type) | Integration (config-validation) | Static JSON parsing |
| AC2 (overlay grid position) | Integration (config-validation) | Static JSON parsing |
| AC2 (multi-query targets) | Integration (config-validation) | Static JSON parsing |
| AC4 (primary PromQL convention) | Integration (config-validation) | Validate rate/$__rate_interval |
| AC4 (description present) | Integration (config-validation) | UX-DR12 compliance |
| AC2/UX-DR8 (accent-blue color) | Integration (config-validation) | Palette compliance |
| AC3/UX-DR8 (amber annotations) | Integration (config-validation) | Palette + annotation presence |
| AC4/UX-DR1 (no forbidden colors) | Integration (config-validation) | Regression guard |
| AC5/NFR5 (noValue field) | Integration (config-validation) | Zero-state guard |
| AC3/FR9 (annotations non-empty) | Integration (config-validation) | Dashboard-level annotation presence |
| NFR12 (version bump to 4) | Integration (config-validation) | Dashboard versioning |

### Priority Assignment

| Priority | Tests |
|----------|-------|
| P0 | fold separator exists, overlay exists, version is 4, annotations non-empty |
| P1 | overlay grid position, multi-query, primary PromQL rate |
| P2 | accent-blue, amber annotations, noValue, description |
| P3 | fold separator type, no forbidden palette colors |

### Red Phase Confirmation

All tests designed to fail before implementation because:
- Panels id=4 and id=5 do not exist in `aiops-main.json` (currently 3 panels)
- Dashboard version is currently 3 (must be 4)
- Annotations list is currently empty (must have detection event annotation)

---

## Step 4: Generated Tests

### File Modified
`tests/integration/test_dashboard_validation.py` — new class `TestBaselineDeviationOverlay` appended

### Test Inventory

| Test ID | Method | AC | Priority | Red Phase |
|---------|--------|-----|----------|-----------|
| 2.3-INT-001 | `test_fold_separator_panel_exists` | AC1 | P0 | FAIL (id=4 absent) |
| 2.3-INT-002 | `test_fold_separator_panel_type` | AC1 | P3 | FAIL (id=4 absent) |
| 2.3-INT-003 | `test_baseline_overlay_panel_exists` | AC2 | P0 | FAIL (id=5 absent) |
| 2.3-INT-004 | `test_baseline_overlay_grid_position` | AC2 | P1 | FAIL (id=5 absent) |
| 2.3-INT-005 | `test_baseline_overlay_has_multi_query` | AC2 | P1 | FAIL (id=5 absent) |
| 2.3-INT-006 | `test_baseline_overlay_primary_query_uses_rate` | AC4 | P1 | FAIL (id=5 absent) |
| 2.3-INT-007 | `test_baseline_overlay_has_description` | AC4/UX-DR12 | P2 | FAIL (id=5 absent) |
| 2.3-INT-008 | `test_baseline_overlay_uses_accent_blue` | AC2/UX-DR8 | P2 | FAIL (id=5 absent) |
| 2.3-INT-009 | `test_detection_annotations_use_semantic_amber` | AC3/UX-DR8 | P2 | FAIL (no amber in panel or annotations) |
| 2.3-INT-010 | `test_no_grafana_default_palette_colors_in_overlay` | AC4/UX-DR1 | P3 | PASS (vacuous — empty list) |
| 2.3-INT-011 | `test_baseline_overlay_has_no_value_message` | AC5/NFR5 | P2 | FAIL (id=5 absent) |
| 2.3-INT-012 | `test_dashboard_annotations_list_is_non_empty` | AC3/FR9 | P0 | FAIL (annotations.list=[]) |
| 2.3-INT-013 | `test_dashboard_version_is_4` | NFR12 | P0 | FAIL (version=3) |

### Red Phase Results (confirmed)
```
12 failed, 42 passed in 0.28s
```

- 12 new tests FAIL (correct: red phase)
- 1 new test passes vacuously (`test_no_grafana_default_palette_colors_in_overlay` — palette guard has no panel to check, so no forbidden colors found; this is correct regression-guard behavior)
- 41 pre-existing tests all PASS (no regressions introduced)
- Ruff: all checks passed (line-length ≤ 100)

---

## Step 5: Validation & Completion

### Checklist
- [x] Prerequisites satisfied
- [x] Test file modified correctly (new class appended, no existing tests broken)
- [x] All 5 ACs covered by tests
- [x] Tests designed to fail before implementation (12/13 fail in red phase)
- [x] 1 test passes vacuously (palette guard — correct and expected behavior)
- [x] No temp artifacts left in random locations
- [x] Ruff compliance: all checks passed

### Key Risks / Assumptions
1. `test_no_grafana_default_palette_colors_in_overlay` passes vacuously now but will become a meaningful regression guard once id=5 exists — this is intentional and correct.
2. The `TestTopicHealthHeatmap::test_dashboard_version_is_3` assertion will continue to pass until implementation bumps the version to 4; both tests coexist correctly.
3. All tests are pure JSON parsing — zero infrastructure dependencies.

### Next Recommended Workflow
**bmad-dev-story** — implement story 2-3 by adding panels id=4 and id=5 to `grafana/dashboards/aiops-main.json`, updating the annotations list, and bumping version to 4.
