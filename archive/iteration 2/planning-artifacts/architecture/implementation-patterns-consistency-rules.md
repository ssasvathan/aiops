# Implementation Patterns & Consistency Rules

## Critical Conflict Points Identified

7 areas where AI agents could make different implementation choices during the revision phase, all resolved below.

## Redis Interaction Patterns

**Connection:** Singleton `Redis.from_url()` created in `__main__.py`, passed as constructor or function parameter. Never imported as a module-level singleton.

**Two-tier error handling:**
- **Critical consumers** (dedupe/AG5, cycle lock): catch → track health state → re-raise. Caller applies degraded-mode effects.
- **Cache consumers** (findings, peak, baselines, sustained state, shard checkpoint): catch → warn-log → continue with fallback value. Pipeline never halts for cache failures.

**Key construction:** Module-level builder functions in the consuming module, following D1 namespace convention (`aiops:{type}:{scope}`).

**Test doubles:** Per-file dict-backed fake implementations (`_FakeRedis`, `_StubRedis`). No shared Redis fixture across unit test files.

## Package & Module Naming

**`__init__.py`:** Re-exports the package's public API. Consumers import from the package, not internal modules. Internals stay hidden.

**Module names:** Specific and unambiguous — `cycle_lock.py` not `lock.py`, `sustained_state.py` not `state.py`.

**Protocols:** Live inside their owning package (`rule_engine/protocol.py`, `coordination/protocol.py`). No shared `protocols/` directory.

## Dependency Injection

**Stateful dependencies** (Redis client, stores) → constructor parameter when building a class.

**Per-call context** (gate inputs, current state) → function parameter.

**Composition root:** `__main__.py` — all wiring happens there. New components are instantiated and passed to consumers.

**No DI framework, no service locator, no module-level mutable singletons.**

## Configuration Variables

**No `AIOPS_` prefix.** The app owns its env namespace.

**Booleans:** `bool` fields — pydantic-settings handles parsing. No custom string conventions.

**Numeric vars:** Include units in the name (`_SECONDS`, `_COUNT`).

**Single flat `Settings` class.** New fields added there.

**Feature flags:** `FEATURE_ENABLED` pattern, `bool`, default `False` (e.g., `DISTRIBUTED_CYCLE_LOCK_ENABLED`).

## OTLP Metrics & Structured Logging

**Metrics:** Dotted namespace `aiops.{component}.{measurement}` with `aiops.` prefix. Counters end with `_total`. Gauges and histograms don't.

Examples:
- `aiops.coordination.cycle_lock_acquired`
- `aiops.baseline.computation_duration_seconds`
- `aiops.cache.sustained_state_hits_total`

**Log events:** snake_case, no prefix, action-oriented — `cycle_yielded`, `baseline_computation_started`.

**Log fields:** Reuse existing schema (`component`, `correlation_id`, `pod_name`, `pod_namespace`). New fields follow snake_case.

**All new metric functions** defined in `health/metrics.py`.

## Test Patterns

**Unit test fakes:** Per-file, tailored to what the test needs. No shared fake library.

**Integration test fixtures:** Shared in `tests/integration/conftest.py`. Session-scoped testcontainers for Redis, Kafka, Postgres.

**Fixture naming:** Noun describing what you get — `redis_client`, `kafka_consumer`, `postgres_engine`.

**Test function naming:** `test_{action}_{condition}_{expected}` — e.g., `test_cycle_lock_acquired_when_no_holder`.

**No test base classes.** Plain functions with fixtures.

## Async Patterns

**Sync Redis.** Keep `redis.Redis` (not `redis.asyncio`). No mid-revision migration.

**Background tasks:** `asyncio.create_task` for baseline computation scheduling.

**Cold-path consumer:** Sync poll-process-commit loop. No asyncio event loop — `confluent-kafka` is sync by design.

**Timeouts:** `asyncio.wait_for`. Don't mix with `asyncio.timeout` context manager within the same module.

**In-process concurrency:** `asyncio.Lock` for shared mutable state. Boolean flag for overlap prevention (baseline computation).

## Enforcement Guidelines

**All AI agents MUST:**

- Read `project-context.md` and this architecture document before implementing any CR
- Follow the two-tier Redis error handling distinction — never halt the pipeline for a cache miss
- Use the established naming conventions — no creative reinterpretation
- Add new metrics in `health/metrics.py`, not inline in consuming modules
- Wire new dependencies in `__main__.py`, not via module-level imports or singletons
- Write specific module names, specific test names, and per-file test doubles

**Anti-Patterns:**

- Creating a shared `RedisWrapper` or `RedisHelper` class
- Adding a DI container or service locator
- Introducing `redis.asyncio` for new Redis consumers
- Creating a `protocols/` or `interfaces/` shared directory
- Adding env var prefixes (`AIOPS_REDIS_URL`)
- Putting integration test fixtures in unit test conftest files
