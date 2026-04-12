# Deferred Work

## Deferred from: code review of demo-data-freshness (2026-04-12)

- **`config/.env.docker` contains a plaintext `LLM_API_KEY=sk-ant-api03-...` on disk.** Pre-existing (not introduced by this story; the file is gitignored). User should rotate the key and consider fetching it from an OS keychain or a gitignored secrets file loaded via `env_file` indirection. Pre-existing finding surfaced during review of demo-freshness diff.
- **`config/.env.docker` lines 22 and 29: `INTEGRATION_MODE_LLM=LOG` is immediately overridden to `LIVE` six lines below, contradicting the "all LOG for local — no outbound calls" comment.** Pre-existing local-only env drift. Harmless for this story but misleading for new operators — clean up the comment or drop the dead line during a future config-hygiene pass.
- **`_harness_cleanup_task` is not awaited/reaped on SIGTERM.** Mirrors the existing `_recompute_task` pattern in the scheduler loop — the whole loop has no graceful shutdown. Address as part of a systemic scheduler-lifecycle fix, not per-feature.
- **Theoretical race between periodic cleanup and in-cycle hot-path writes.** Cleanup spawns at the top of the scheduler tick and runs concurrently with the rest of the cycle's outbox INSERTs / Redis writes against the same `engine` and `redis_client`. For the demo-freshness goal this is benign (the race = the feature: wipe and re-accumulate). Revisit if the knob is ever enabled in a context where the harness runs alongside non-harness traffic.
- **No end-to-end scheduler-loop test for the spawn-site** (AC1, AC2, AC3, AC5 are covered by predicate/orchestrator/state-guard unit tests, but not by driving `_hot_path_scheduler_loop` with `APP_ENV=local` + interval>0 and asserting task creation). Heavy fixture setup for a demo-only feature; cover when the scheduler loop gets integration-test scaffolding for other concerns.
- **`_run_harness_cleanup_once` failure log lacks per-stage breakdown.** When any of the three helpers (`_delete_harness_casefiles`, `_delete_harness_outbox_rows`, `_delete_harness_redis_keys`) raises, the single `harness_periodic_cleanup_failed` warning carries no `stage=`/partial-count fields, so operators can't tell which helper failed or whether earlier helpers already succeeded. Spec-compliant (matrix only requires a warning log) but operationally thin. Address alongside any future observability pass on the harness pipeline.

## Deferred from: code review of fix-grafana-empty-dashboard (2026-04-11)

- `config/otel-collector.yaml` has no `memory_limiter` processor. Valid operational hardening for higher metric volumes or production-like stacks; not required for local dev. When stack is deployed beyond local Docker (dev/uat/prod), add `memory_limiter` as the first processor in the metrics pipeline with bounded `check_interval`/`limit_mib`.

## Deferred from: code review of 2-1-hero-banner-p-l-stat-panels (2026-04-11)

- `TestDashboardJsonShells::test_dashboards_have_no_panels_initially` test name is misleading — now that panels are populated in story 2-1, the test only asserts `isinstance(list)` vacuously. Pre-existing test from story 1-1; rename or strengthen in a future cleanup story.
- Hero banner proxy query `sum(aiops_findings_total)` returns total finding count (0..n), not a health state integer (0/1/2). With any findings present the panel turns amber/red, which is semantically incorrect. Explicitly acknowledged in dev notes as placeholder pending a dedicated health-gauge recording rule. Address in the recording-rule / health-gauge story.

## Deferred from: code review of 3-1-gating-intelligence-funnel-per-gate-suppression (2026-04-11)

- `test_dashboards_have_no_panels_initially` test name is misleading — aiops-main.json now has 7 panels; test only asserts `isinstance(list)` vacuously. Pre-existing from story 1-1; rename or strengthen in a future cleanup story.
- `reduceOptions.values=false` on the bargauge panel has no dedicated test coverage. The calcs=['sum'] assertion covers the aggregate intent but values=true would change bar-rendering semantics without failing any test. Acceptable within story 3-1 scope.

## Deferred from: code review of 3-3-llm-diagnosis-engine-statistics (2026-04-11)

- Row 35 in `grafana/dashboards/aiops-main.json` is uncovered (1-row visual gap between panels 8/9 ending at y=34 and panel 10 starting at y=36). Story 3-4 left-column panels will bound this row visually when the capability stack is implemented. No action needed until story 3-4 is built.

## Deferred from: code review of 1-3-evidence-diagnosis-otlp-instruments (2026-04-11)

- `_current_evidence_status` dict in `health/metrics.py` grows unbounded with topic churn — no pruning mechanism exists. Acceptable at current scale but should be addressed if topic cardinality grows significantly (hundreds of distinct topics cycling in/out). Consider LRU eviction or TTL-based cleanup in a future story.
