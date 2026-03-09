# Contribution Guide

## Current State

A root `CONTRIBUTING.md` file is not present. This guide reflects active contribution practices from repository docs and policies.

## Pull Request Expectations

- Keep behavioral changes paired with tests.
- Keep contract/schema changes explicit and version-aware.
- Keep documentation in sync when architecture or runbooks change.

## Validation Before PR

```bash
uv run pytest -q tests/unit
uv run pytest -q tests/integration -m integration
TESTCONTAINERS_RYUK_DISABLED=true DOCKER_HOST=unix://$HOME/.docker/desktop/docker.sock uv run pytest -q -rs
uv run ruff check
```

## Security and Ownership

- `config/denylist.yaml` is governed by `CODEOWNERS` review.
- Treat integration and policy files as high-sensitivity review surfaces.

## Style and Safety

- Preserve deterministic behavior in stage/state-machine code paths.
- Preserve source-state guards and invariant checks in persistence transitions.
- Prefer additive, test-backed refactors over broad rewrites.
