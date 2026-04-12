---
title: 'Demo data freshness — periodic in-process harness cleanup'
type: 'feature'
created: '2026-04-12'
status: 'done'
baseline_commit: 'ee27b41'
context:
  - 'artifact/project-context.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** During local/harness demos the Baseline Deviation overlay flatlines within ~2 minutes of app start. The harness loops four fixed scope tuples forever, and the S3-backed casefile dedup (`get_existing_casefile_triage` in `pipeline/stages/casefile.py`) returns the existing triage after cycle 1, so every subsequent cycle emits zero findings. `docker compose restart app` refreshes the signal briefly (the entrypoint chains `--mode harness-cleanup` before `--mode hot-path`) but the flatline returns ~2 minutes later. Reads as "broken" in demos even though dedup is working as designed for prod.

**Approach:** Add a **periodic in-process harness cleanup** to the hot-path scheduler loop. Every N seconds, when `APP_ENV in {local, harness}` and an operator-set interval is non-zero, invoke the already-tested `_delete_harness_casefiles` / `_delete_harness_outbox_rows` / `_delete_harness_redis_keys` helpers off the event loop via `asyncio.to_thread`. Mirrors the existing weekly baseline-recompute timer pattern in the scheduler loop. No registry, dashboard, or production code-path changes.

## Boundaries & Constraints

**Always:**
- Double-gate every cleanup invocation: `settings.HARNESS_PERIODIC_CLEANUP_INTERVAL_SECONDS > 0` AND `settings.APP_ENV.value in {AppEnv.local.value, AppEnv.harness.value}`.
- Reuse the existing `_delete_harness_*` helpers as-is (preserve their `case-harness-*` scoping, governance approval ref, and batch sizes).
- Default the new setting to `0` in `Settings` (disabled); only the local env file opts in.
- Keep the weekly baseline-recompute timer pattern (`__main__.py:818–834`) as the structural template.

**Ask First:**
- If a default interval ≠ 600s is desired.
- Any proposal to touch `get_existing_casefile_triage` or the hot-path dedup check itself — out of scope here.
- Enabling periodic cleanup in any env file other than `config/.env.docker`.

**Never:**
- Do not spawn cleanup in `prod`, `uat`, `dev`, or any env where `APP_ENV` is not `local` or `harness`.
- Do not allow overlapping cleanups — re-check `task.done()` before re-spawning.
- Do not block the scheduler event loop; all three helpers are sync and must run via `asyncio.to_thread`.
- Do not introduce a new cleanup code path — orchestrate the existing helpers only.
- Do not log LLM_API_KEY or other secrets; reuse the existing structured-logging fields.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|---|---|---|---|
| Interval=0 | `HARNESS_PERIODIC_CLEANUP_INTERVAL_SECONDS=0`, any APP_ENV | Branch never taken, no task spawned, no log | N/A |
| Prod env, interval>0 | `APP_ENV=prod`, interval=600 | Branch refuses (env gate fails), no task spawned, no log | N/A |
| Local env, first tick | `APP_ENV=local`, interval=600, `_last_harness_cleanup_at is None` | Spawn task immediately on first scheduler tick; stamp `_last_harness_cleanup_at` | Task exceptions logged via `asyncio` default handler, scheduler loop unaffected |
| Local env, interval elapsed | Last cleanup ≥ 600s ago, no in-flight task | Spawn task, stamp timestamp | As above |
| Local env, in-flight task | `_harness_cleanup_task` running | Do not spawn; wait for completion | N/A |
| Redis/S3/Postgres unavailable | Helper raises | Task fails, logger records failure event at warning level, next tick retries after interval | Do not crash hot-path loop |

</frozen-after-approval>

## Code Map

- `src/aiops_triage_pipeline/config/settings.py` -- Add `HARNESS_PERIODIC_CLEANUP_INTERVAL_SECONDS: int = 0` to `Settings` (around line 105, near `HOT_PATH_SCHEDULER_INTERVAL_SECONDS`). Add validation: must be `>= 0`.
- `src/aiops_triage_pipeline/__main__.py:530–870` -- `_run_hot_path` / `_run_hot_path_async` scheduler loop. Template pattern: weekly recompute at lines 818–834.
- `src/aiops_triage_pipeline/__main__.py:1881–1924` -- Existing `_delete_harness_casefiles`, `_delete_harness_outbox_rows`, `_delete_harness_redis_keys`, `_collect_harness_casefile_keys` — **reused as-is**.
- `src/aiops_triage_pipeline/__main__.py:1927–1969` -- `_run_harness_cleanup` — not modified; its env gate (`AppEnv.local`/`AppEnv.harness`) is the reference for ours.
- `config/.env.docker` -- Local demo env file; enable the knob here.
- `tests/unit/test_main.py` -- Home of the existing harness-cleanup unit tests (lines 1483–1787). Add new tests adjacent to them.

## Tasks & Acceptance

**Execution:**
- [x] `src/aiops_triage_pipeline/config/settings.py` -- Added `HARNESS_PERIODIC_CLEANUP_INTERVAL_SECONDS: int = 0` + `>= 0` validation.
- [x] `src/aiops_triage_pipeline/__main__.py` -- Added `async def _run_harness_cleanup_once` orchestrator (three helpers via `asyncio.to_thread`, `harness_periodic_cleanup_completed` log on success, `harness_periodic_cleanup_failed` warning on helper exception).
- [x] `src/aiops_triage_pipeline/__main__.py` -- Extracted predicate `_should_trigger_periodic_harness_cleanup`; hoisted engine local var; added state vars + gated spawn block in `_hot_path_scheduler_loop` mirroring the weekly recompute pattern; threaded `engine` kwarg through `_run_hot_path` → `_hot_path_scheduler_loop`.
- [x] `config/.env.docker` -- Added `HARNESS_PERIODIC_CLEANUP_INTERVAL_SECONDS=600` with explanatory comment.
- [x] `tests/unit/test_main.py` -- Added 7 new tests (4 predicate gate tests covering interval=0, non-local env, first-tick, elapsed-interval; 2 orchestrator tests covering happy-path logging + helper-exception swallowing; 1 state-guard test for in-flight task suppression). Backfilled `engine=MagicMock()` + new settings fields on existing scheduler-loop call sites.

## Spec Change Log

### 2026-04-12 · review loop 1 · patch findings
- **Blind Hunter #4**: test used `last_at.replace(minute=N)` which encodes absolute-minute arithmetic, not elapsed time. Amended `test_should_trigger_periodic_harness_cleanup_respects_interval_elapsed` to use `timedelta(minutes=N)` arithmetic. Known-bad avoided: silent test inversion if `last_at.minute` is changed to non-zero.
- **Acceptance Auditor #1**: AC4 ("no double-spawn while task in-flight") had no direct test evidence; only the predicate and orchestrator were tested. Added `test_periodic_harness_cleanup_not_respawned_while_task_in_flight` exercising the outer state guard directly.
- **Acceptance Auditor #5**: Task bullet said "5 new tests"; diff added 6. Corrected bullet to "7 new tests" (includes the new in-flight guard test).

**Acceptance Criteria:**
- Given `APP_ENV=local` and `HARNESS_PERIODIC_CLEANUP_INTERVAL_SECONDS=600`, when the hot-path scheduler runs for ≥ 10 minutes, then the Baseline Deviation overlay panel shows at least one new detection-annotation marker after the first bootstrap batch.
- Given `APP_ENV=prod` and `HARNESS_PERIODIC_CLEANUP_INTERVAL_SECONDS=600`, when the hot-path scheduler runs, then no periodic-cleanup task is ever spawned and no harness artifacts are deleted.
- Given `HARNESS_PERIODIC_CLEANUP_INTERVAL_SECONDS=0`, when the hot-path scheduler runs in any env, then the periodic-cleanup code path is not entered (no log line, no task).
- Given an in-flight periodic-cleanup task, when the next scheduler tick fires, then no second task is spawned until the first completes.
- Given a periodic-cleanup task that raises (e.g. Redis unreachable), when the scheduler continues, then the hot-path loop keeps running and the next interval re-attempts.

## Design Notes

**Why this shape:** `_run_harness_cleanup` already encodes the correct state-clearing (S3 `cases/case-harness-*`, Postgres `outbox` rows with `case_id LIKE 'case-harness-%'`, Redis keys under harness scopes). Reusing its helpers keeps one source of truth for "what counts as harness state" and avoids divergence. The weekly baseline-recompute timer at `__main__.py:818–834` is the established pattern for "check wall-clock, spawn asyncio task, keep handle, don't double-fire" — copying its shape means reviewers only need to verify env-gating and interval math, not the concurrency primitives.

**Expected demo behavior (interval=600s, local scheduler tick=30s, harness cycle=60s):** Cleanup fires every 10 min → within one scheduler tick (~30s) the next harness cycle writes 4 fresh casefiles → counter jumps by 4 → Grafana's `sum(rate(aiops_findings_total[$__rate_interval]))` panel and `increase(...) > 0` annotation show a spike. On the "Last 24h" range (`$__rate_interval` ≈ 5 min) this yields a ~50% duty-cycle non-zero line; on "Last 1h" (~15–30s rate window) it yields a clean sawtooth of 6 spikes per hour.

## Verification

**Commands:**
- `uv run pytest tests/unit/test_main.py -k harness_periodic_cleanup` -- expected: 4 new tests pass.
- `uv run pytest tests/unit/test_main.py -k harness_cleanup` -- expected: existing `_run_harness_cleanup` tests remain green (no regression in the shared helpers).
- `uv run ruff check src/aiops_triage_pipeline/__main__.py src/aiops_triage_pipeline/config/settings.py` -- expected: no new lint violations.
- `docker compose restart app && sleep 900 && docker compose logs app --since=15m | grep harness_periodic_cleanup_completed` -- expected: at least one completion log entry after 15 min of runtime.

**Manual checks:**
- Open Grafana → Baseline Deviation overlay → "Last 1h" range → confirm orange detection annotations appear roughly every 10 minutes after the initial bootstrap spike.

## Suggested Review Order

**Design intent — what the timer does**

- Orchestrator that fans out to the existing three helpers off the event loop; single source of truth for a cleanup "round".
  [`__main__.py:1977`](../../src/aiops_triage_pipeline/__main__.py#L1977)

- Pure double-gate predicate (interval>0 AND local/harness) — the one place to audit env safety.
  [`__main__.py:169`](../../src/aiops_triage_pipeline/__main__.py#L169)

**Scheduler integration — where it fires**

- State vars: `_harness_cleanup_task` handle for the in-flight guard, mirroring the weekly-recompute timer shape.
  [`__main__.py:824`](../../src/aiops_triage_pipeline/__main__.py#L824)

- Gated spawn block: `done()` guard + predicate + `create_task` stamped with `_last_harness_cleanup_at`.
  [`__main__.py:868`](../../src/aiops_triage_pipeline/__main__.py#L868)

**Configuration surface**

- New setting defaulted to `0` (disabled); the only non-frozen opt-in lives in `config/.env.docker`.
  [`settings.py:119`](../../src/aiops_triage_pipeline/config/settings.py#L119)

- Validator enforces `>= 0` so a negative value fails fast at bootstrap.
  [`settings.py:297`](../../src/aiops_triage_pipeline/config/settings.py#L297)

**Tests**

- Predicate gate — covers AC2 (prod refused), AC3 (interval=0), first-tick, and elapsed-interval boundary.
  [`test_main.py:268`](../../tests/unit/test_main.py#L268)

- AC4 in-flight guard — asserts the `done()` check would suppress a second spawn.
  [`test_main.py:330`](../../tests/unit/test_main.py#L330)

- Orchestrator happy-path — verifies the summary log fields and helper wiring.
  [`test_main.py:355`](../../tests/unit/test_main.py#L355)

- AC5 exception swallowing — helper raises, warning logged, loop keeps running.
  [`test_main.py:394`](../../tests/unit/test_main.py#L394)
