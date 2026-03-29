#!/usr/bin/env bash
set -euo pipefail

if ! command -v docker >/dev/null 2>&1; then
  echo "docker CLI not found in PATH" >&2
  exit 1
fi

if docker info >/dev/null 2>&1; then
  echo "Docker engine is reachable."
  exit 0
fi

echo "Docker engine is not reachable. Start Docker Desktop/daemon before running tests." >&2
exit 1
