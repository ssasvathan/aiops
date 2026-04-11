# Deferred Work

## Deferred from: code review of 2-1-hero-banner-p-l-stat-panels (2026-04-11)

- `TestDashboardJsonShells::test_dashboards_have_no_panels_initially` test name is misleading — now that panels are populated in story 2-1, the test only asserts `isinstance(list)` vacuously. Pre-existing test from story 1-1; rename or strengthen in a future cleanup story.
- Hero banner proxy query `sum(aiops_findings_total)` returns total finding count (0..n), not a health state integer (0/1/2). With any findings present the panel turns amber/red, which is semantically incorrect. Explicitly acknowledged in dev notes as placeholder pending a dedicated health-gauge recording rule. Address in the recording-rule / health-gauge story.

## Deferred from: code review of 3-1-gating-intelligence-funnel-per-gate-suppression (2026-04-11)

- `test_dashboards_have_no_panels_initially` test name is misleading — aiops-main.json now has 7 panels; test only asserts `isinstance(list)` vacuously. Pre-existing from story 1-1; rename or strengthen in a future cleanup story.
- `reduceOptions.values=false` on the bargauge panel has no dedicated test coverage. The calcs=['sum'] assertion covers the aggregate intent but values=true would change bar-rendering semantics without failing any test. Acceptable within story 3-1 scope.

## Deferred from: code review of 1-3-evidence-diagnosis-otlp-instruments (2026-04-11)

- `_current_evidence_status` dict in `health/metrics.py` grows unbounded with topic churn — no pruning mechanism exists. Acceptable at current scale but should be addressed if topic cardinality grows significantly (hundreds of distinct topics cycling in/out). Consider LRU eviction or TTL-based cleanup in a future story.
