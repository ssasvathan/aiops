#!/usr/bin/env bash
# smoke-test.sh — validate all docker-compose services are healthy and reachable
# Usage: bash scripts/smoke-test.sh
# Exit code: 0 = all pass, 1 = one or more failures

set -euo pipefail

ERRORS=0

check() {
  local name="$1"
  shift
  printf "%-50s" "  Checking $name..."
  if "$@" > /dev/null 2>&1; then
    echo "OK"
  else
    echo "FAILED"
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

echo ""
if [ "$ERRORS" -eq 0 ]; then
  echo "All checks passed!"
  exit 0
else
  echo "$ERRORS check(s) failed."
  exit 1
fi
