#!/usr/bin/env bash
# smoke-test.sh — validate all docker-compose services are healthy and reachable
# Usage: bash scripts/smoke-test.sh
# Exit code: 0 = all pass, 1 = one or more failures

set -euo pipefail

# Preflight: abort early with a clear message if the stack is not running.
# Without this check, `docker compose exec` errors are readable but the MinIO
# bucket check (which uses `docker compose run --no-deps`) creates a fresh
# network and produces a confusing DNS-resolution failure.
running=$(docker compose ps --services --filter status=running 2>/dev/null || true)
if [ -z "$running" ]; then
  echo "ERROR: No services are running. Start the stack first:" >&2
  echo "  docker compose up --detach --wait" >&2
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

echo "=== aiOps Local Dev Smoke Test ==="
echo ""
echo "--- Kafka ---"
check "Broker reachable (list topics)" \
  docker compose exec -T kafka kafka-topics --bootstrap-server localhost:9092 --list
check "Topic: aiops-case-header exists" \
  docker compose exec -T kafka kafka-topics --bootstrap-server localhost:9092 --describe --topic aiops-case-header
check "Topic: aiops-triage-excerpt exists" \
  docker compose exec -T kafka kafka-topics --bootstrap-server localhost:9092 --describe --topic aiops-triage-excerpt

echo "--- Postgres ---"
check "pg_isready" \
  docker compose exec -T postgres pg_isready -U aiops -d aiops

echo "--- Redis ---"
check "PING returns PONG" \
  docker compose exec -T redis redis-cli ping

echo "--- MinIO ---"
check "Health endpoint (/minio/health/live)" \
  curl -sf http://localhost:9000/minio/health/live
check "Bucket: aiops-cases exists" \
  docker compose run --rm --no-deps --entrypoint /bin/sh minio-init \
    -c "mc alias set local http://minio:9000 minioadmin minioadmin && mc ls local/aiops-cases"

echo "--- Prometheus ---"
check "Health endpoint (/-/healthy)" \
  curl -sf http://localhost:9090/-/healthy

echo "--- Harness ---"
check "Metrics endpoint (/metrics)" \
  curl -sf http://localhost:8000/metrics
check "Canonical metric present (messagesinpersec)" \
  bash -c "curl -sf http://localhost:8000/metrics | grep -q 'kafka_server_brokertopicmetrics_messagesinpersec'"
check "Harness label namespace (env=harness)" \
  bash -c "for i in 1 2 3; do curl -sf http://localhost:8000/metrics | grep -q 'env=\"harness\"' && exit 0; sleep 1; done; exit 1"

echo "--- E2E Happy Path ---"
echo "  (Waiting up to 120s for hot-path cycles — this is expected)"
check "E2E happy path (verify-e2e.sh)" \
  bash scripts/verify-e2e.sh

echo ""
if [ "$ERRORS" -eq 0 ]; then
  echo "All checks passed!"
  exit 0
else
  echo "$ERRORS check(s) failed."
  exit 1
fi
