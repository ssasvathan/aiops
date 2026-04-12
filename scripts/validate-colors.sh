#!/usr/bin/env bash
# validate-colors.sh — Check dashboard JSON files for forbidden Grafana default palette colors.
#
# Usage: ./scripts/validate-colors.sh [dashboard_dir]
#   dashboard_dir: path to directory containing .json dashboard files
#                  (default: grafana/dashboards)
#
# Exit 0: clean — no forbidden colors found.
# Exit 1: forbidden colors detected — offending lines reported to stdout.
#
# Approved muted palette: #6BAD64 #E8913A #D94452 #7A7A7A #4F87DB
# Forbidden (Grafana defaults): see FORBIDDEN array below.

set -uo pipefail

DASHBOARD_DIR="${1:-grafana/dashboards}"
FORBIDDEN=(
  "#73BF69"
  "#F2495C"
  "#FF9830"
  "#FADE2A"
  "#5794F2"
  "#B877D9"
  "#37872D"
  "#C4162A"
  "#1F60C4"
  "#8F3BB8"
  "#8E8E8E"
)

found=0

if [ ! -d "$DASHBOARD_DIR" ]; then
  echo "ERROR: Dashboard directory not found: $DASHBOARD_DIR"
  exit 1
fi

for json_file in "$DASHBOARD_DIR"/*.json; do
  if [ ! -f "$json_file" ]; then
    continue
  fi
  for color in "${FORBIDDEN[@]}"; do
    if grep -qi "$color" "$json_file"; then
      echo "FAIL: $json_file contains forbidden color $color"
      grep -ni "$color" "$json_file" | head -5
      found=1
    fi
  done
done

if [ "$found" -eq 0 ]; then
  echo "PASS: No forbidden Grafana default palette colors found in $DASHBOARD_DIR"
fi

exit "$found"
