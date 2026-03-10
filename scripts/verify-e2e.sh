#!/usr/bin/env bash
# verify-e2e.sh — verify end-to-end happy path: harness → evidence → gate → casefile → dispatch
# Usage: bash scripts/verify-e2e.sh
# Exit code: 0 = all E2E checks passed, 1 = one or more failures
#
# Requires: docker compose stack running with app and all services healthy.
# Run `docker compose up --detach --wait` first.

set -euo pipefail

# Preflight: abort early with a clear message if the stack is not running.
running=$(docker compose ps --services --filter status=running 2>/dev/null || true)
if [ -z "$running" ]; then
  echo "ERROR: No services are running. Start the stack first:" >&2
  echo "  docker compose up --detach --wait" >&2
  exit 1
fi
if ! echo "$running" | grep -q "^app$"; then
  echo "ERROR: 'app' service is not running (may have crashed). Diagnose with:" >&2
  echo "  docker compose logs app --tail=50" >&2
  echo "  docker compose ps app" >&2
  exit 1
fi

ERRORS=0

check() {
  local name="$1"
  shift
  printf "%-50s" "  Checking $name..."
  local output
  if output=$("$@" 2>&1); then
    echo "OK"
  else
    echo "FAILED"
    echo "    ↳ $output" >&2
    ERRORS=$((ERRORS + 1))
  fi
}

echo "=== aiOps E2E Happy Path Verification ==="
echo ""
echo "--- Waiting for ≥2 hot-path cycles (max 120s) ---"

# Wait for at least 2 hot_path_cycle_completed entries in the last 90s of logs.
CYCLE_WAIT_MAX=12
CYCLE_WAIT_SLEEP=10
cycle_count=0
waited=0
while [ "$waited" -lt "$CYCLE_WAIT_MAX" ]; do
  cycle_count=$(docker compose logs app --since=90s 2>/dev/null | grep -c 'hot_path_cycle_completed' || true)
  if [ "$cycle_count" -ge 2 ]; then
    echo "  ✓ $cycle_count hot_path_cycle_completed entries found"
    break
  fi
  echo "  ... $cycle_count cycle(s) so far, waiting ${CYCLE_WAIT_SLEEP}s (attempt $((waited + 1))/${CYCLE_WAIT_MAX})"
  sleep "$CYCLE_WAIT_SLEEP"
  waited=$((waited + 1))
done

if [ "$cycle_count" -lt 2 ]; then
  echo "FAILED — only $cycle_count hot_path_cycle_completed entries found after $((CYCLE_WAIT_MAX * CYCLE_WAIT_SLEEP))s" >&2
  echo "  Check: docker compose logs app | grep hot_path_cycle_completed" >&2
  echo "  Ensure HOT_PATH_SCHEDULER_INTERVAL_SECONDS=30 in .env.docker" >&2
  exit 1
fi

echo ""
echo "--- E2E Pipeline Checks ---"

# Check 1: produced_cases > 0 in at least one cycle
check_produced_cases() {
  local log_lines
  log_lines=$(docker compose logs app --since=90s 2>/dev/null | grep 'hot_path_cycle_completed' || true)
  if [ -z "$log_lines" ]; then
    echo "FAILED — no hot_path_cycle_completed entries found in last 90s"
    return 1
  fi
  local max_cases=0
  while IFS= read -r line; do
    local count
    # Extract produced_cases value from JSON log line
    count=$(echo "$line" | python3 -c "import sys,json; d=json.loads(sys.stdin.read().strip()); print(d.get('produced_cases', 0))" 2>/dev/null || echo "0")
    if [ "$count" -gt "$max_cases" ] 2>/dev/null; then
      max_cases="$count"
    fi
  done <<< "$log_lines"

  # Fallback: simpler grep if python3 parsing produced no result
  if [ "$max_cases" -eq 0 ]; then
    if echo "$log_lines" | grep -qE '"produced_cases": *[1-9]'; then
      echo "OK (produced_cases > 0 confirmed via grep fallback)"
      return 0
    fi
  fi

  if [ "$max_cases" -gt 0 ]; then
    echo "OK (max produced_cases=$max_cases)"
    return 0
  else
    echo "FAILED — all cycles show produced_cases=0 (topology or TTL policy fix needed)"
    return 1
  fi
}
check "produced_cases > 0 in hot-path cycle" check_produced_cases

# Check 2: MinIO aiops-cases bucket has at least one object
check_minio_casefile() {
  local result
  result=$(docker compose run --rm --no-deps --entrypoint /bin/sh minio-init \
    -c "mc alias set local http://minio:9000 minioadmin minioadmin 2>/dev/null && mc ls local/aiops-cases/ 2>/dev/null" 2>&1 || true)
  if [ -z "$result" ]; then
    echo "FAILED — MinIO aiops-cases bucket is empty (no casefile written)"
    return 1
  fi
  echo "OK (casefile(s) found in aiops-cases)"
  return 0
}
check "MinIO aiops-cases has ≥1 casefile" check_minio_casefile

# Check 3: Postgres outbox table has at least one row
check_outbox_row() {
  # First verify table exists
  local table_check
  table_check=$(docker compose exec -T postgres psql -U aiops -d aiops -c "\dt outbox" 2>&1 || true)
  if ! echo "$table_check" | grep -q "outbox"; then
    echo "FAILED — outbox table does not exist (app may not have started cleanly)"
    return 1
  fi
  local count
  count=$(docker compose exec -T postgres psql -U aiops -d aiops -t -c "SELECT COUNT(*) FROM outbox;" 2>&1 | tr -d ' \n' || echo "0")
  if [ "$count" -gt 0 ] 2>/dev/null; then
    echo "OK (outbox row count=$count)"
    return 0
  else
    echo "FAILED — outbox table is empty (count=$count); casefile write or outbox insert failed"
    return 1
  fi
}
check "Postgres outbox has ≥1 row" check_outbox_row

echo ""
if [ "$ERRORS" -eq 0 ]; then
  echo "All E2E checks passed!"
  exit 0
else
  echo "$ERRORS E2E check(s) failed."
  exit 1
fi
