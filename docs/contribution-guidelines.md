# Contribution Guidelines

No dedicated `CONTRIBUTING.md` file was detected during this scan.

The following baseline contribution rules are inferred from repository behavior and docs.

## Change Discipline

- Keep contract changes explicit and test-backed.
- Include tests for behavioral changes in the same change set.
- Update documentation whenever runtime behavior, architecture, or developer workflows change.

## Verification Expectations

- Run unit tests before PR:

```bash
uv run pytest -q tests/unit
```

- Run integration tests with Docker available:

```bash
uv run pytest -q tests/integration -m integration
```

- Run full regression with Docker-enabled integration execution:

```bash
TESTCONTAINERS_RYUK_DISABLED=true DOCKER_HOST=unix://$HOME/.docker/desktop/docker.sock uv run pytest -q -rs
```

- Lint before PR:

```bash
uv run ruff check
```

## Ownership and Sensitive Changes

- `config/denylist.yaml` is protected by `CODEOWNERS` review (`@security-team` placeholder).
- Treat security and exposure-control changes as elevated-review modifications.
