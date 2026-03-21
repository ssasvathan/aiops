# Project Structure

- Scan timestamp: 2026-03-08T20:04:10-04:00 (America/Toronto)
- Repository root: /home/sas/workspace/aiops
- Repository type: monolith
- Part count: 1
- Primary part: core (backend)

## Top-Level Layout

- `src/aiops_triage_pipeline/` - application code (pipeline, contracts, integrations, storage, health)
- `tests/` - unit and integration suites
- `config/` - environment and policy configuration
- `harness/` - test/load harness and synthetic patterns
- `docs/` - architecture and local development documentation
- `scripts/` - utility scripts (for example smoke tests)
- `artifact/` - planning and implementation artifacts

## Classification Rationale

- Python backend markers present: `pyproject.toml`, `src/` package, backend-oriented modules.
- Operational and service architecture markers present: Docker assets, integration adapters, health endpoints.
- No separate frontend client application detected.
