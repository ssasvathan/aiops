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

## Documentation Style
Write the way an experienced engineer explains something to a colleague: plain, complete sentences that state facts and consequences directly. My readers are technical and want the point, not the performance of a point.

Specifically:
- State what something is. Only contrast it with something else if someone actually proposed that other thing.
  Instead of "This is a proving run, not a pilot", write "This run only shows the pipeline works. We can't call it a pilot because nothing reads the output yet."
- Don't announce that something matters ("and the difference matters", "here's the key point"). Say what the consequence is.
- Use commas, periods, or parentheses instead of em dashes.
- Avoid quotable one-liners, dramatic sentence fragments, rhetorical questions, and grouping things in threes by habit.
- Use ordinary words (use, help, show) over inflated ones (leverage, underscore, crucial).

If a sentence sounds like it was written to be quoted, rewrite it as a plain explanation.

