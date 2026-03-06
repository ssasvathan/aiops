# Agent Instructions

## Test Execution

- When running the full pytest suite in this repository, prefer Docker-enabled execution so integration tests do not skip due to missing Docker host configuration.
- Default command:

```bash
TESTCONTAINERS_RYUK_DISABLED=true DOCKER_HOST=unix://$HOME/.docker/desktop/docker.sock uv run pytest -q -rs
```

- If a Linux engine socket is available at `/var/run/docker.sock`, that socket is also supported.
- Integration bootstrap in `tests/integration/conftest.py` auto-detects common socket paths when `DOCKER_HOST` is unset, but explicit env vars above are preferred for deterministic CI/local runs.
- Sprint quality gate: full regression runs must complete with **0 skipped tests**. Treat any skip as a failure and fix missing prerequisites/dependencies instead of bypassing execution.
