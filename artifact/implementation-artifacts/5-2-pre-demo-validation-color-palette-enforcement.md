# Story 5.2: Pre-Demo Validation & Color Palette Enforcement

Status: ready-for-dev

## Story

As a presenter preparing for a stakeholder demo,
I want automated validation scripts that confirm all panels use the approved muted palette,
So that I can catch visual regressions before the audience sees them.

## Acceptance Criteria

1. **Given** dashboard JSON files exist in `grafana/dashboards/` **When** `scripts/validate-colors.sh` is executed **Then** the script greps dashboard JSON for the approved muted palette hex values (`#6BAD64`, `#E8913A`, `#D94452`, `#7A7A7A`, `#4F87DB`) **And** the script rejects any Grafana default palette hex values (`#73BF69`, `#F2495C`, `#FF9830`, `#8E8E8E`, `#5794F2`) **And** the script reports pass/fail with any offending color values

2. **Given** `scripts/validate-colors.sh` is available **When** the script is run against both dashboard files **Then** it exits 0 (pass) if no forbidden colors are found, exits non-zero and reports the offending lines if forbidden colors exist

3. **Given** the integration test suite runs **When** `tests/integration/test_dashboard_validation.py` executes **Then** a test verifies `validate-colors.sh` exists at the expected path **And** a test verifies neither dashboard JSON contains any forbidden Grafana default palette colors (leveraging existing per-panel tests)

4. **Given** all scripts are in place **When** the dashboard JSON is inspected **Then** a summary test confirms the full forbidden palette check across both dashboard files

## Tasks / Subtasks

- [ ] Task 1: Create `scripts/validate-colors.sh` (AC: 1, 2)
  - [ ] 1.1 Create `scripts/` directory if not exists
  - [ ] 1.2 Write bash script that:
    - Accepts optional dashboard directory argument (default: `grafana/dashboards`)
    - Iterates over all `.json` files in the directory
    - Checks for forbidden colors (case-insensitive grep):
      `#73BF69`, `#F2495C`, `#FF9830`, `#8E8E8E`, `#5794F2`, `#B877D9`,
      `#37872D`, `#C4162A`, `#1F60C4`, `#8F3BB8`, `#FADE2A`
    - Reports file:line for each match
    - Exits non-zero if any forbidden colors found, exits 0 if clean
  - [ ] 1.3 Make script executable: `chmod +x scripts/validate-colors.sh`

- [ ] Task 2: Add config-validation tests (AC: 3, 4)
  - [ ] 2.1 Extend `tests/integration/test_dashboard_validation.py` with class `TestPreDemoValidation`
  - [ ] 2.2 Test: `scripts/validate-colors.sh` exists and is a file
  - [ ] 2.3 Test: `scripts/validate-colors.sh` is executable
  - [ ] 2.4 Test: full aiops-main.json has no forbidden Grafana default palette colors
  - [ ] 2.5 Test: full aiops-drilldown.json has no forbidden Grafana default palette colors

## Dev Notes

### Script Design

```bash
#!/usr/bin/env bash
# validate-colors.sh — Check dashboard JSON files for forbidden Grafana default palette colors.
# Usage: ./scripts/validate-colors.sh [dashboard_dir]
# Exit 0: clean. Exit 1: forbidden colors found.

set -euo pipefail

DASHBOARD_DIR="${1:-grafana/dashboards}"
FORBIDDEN=(
  "#73BF69" "#F2495C" "#FF9830" "#8E8E8E" "#5794F2"
  "#B877D9" "#37872D" "#C4162A" "#1F60C4" "#8F3BB8" "#FADE2A"
)

found=0
for json_file in "$DASHBOARD_DIR"/*.json; do
  for color in "${FORBIDDEN[@]}"; do
    if grep -qi "$color" "$json_file"; then
      echo "FAIL: $json_file contains forbidden color $color"
      grep -ni "$color" "$json_file" | head -5
      found=1
    fi
  done
done

if [ "$found" -eq 0 ]; then
  echo "PASS: No forbidden Grafana default palette colors found."
fi

exit "$found"
```

### Forbidden Color Set (verbatim from test files)

- `#73BF69` (Grafana green)
- `#F2495C` (Grafana red)
- `#FF9830` (Grafana orange)
- `#FADE2A` (Grafana yellow)
- `#5794F2` (Grafana blue)
- `#B877D9` (Grafana purple)
- `#37872D` (dark green)
- `#C4162A` (dark red)
- `#1F60C4` (dark blue)
- `#8F3BB8` (dark purple)
- `#8E8E8E` (Grafana grey — different from muted `#7A7A7A`)

### Architecture Source References

- [Source: artifact/planning-artifacts/epics.md#Story 5.2] — FR32, FR34, NFR15, UX-DR15
- [Source: artifact/planning-artifacts/architecture.md#Color Palette] — approved muted palette

## Dev Agent Record

### Agent Model Used

claude-sonnet-4-6

### Debug Log References

### Completion Notes List

### File List
