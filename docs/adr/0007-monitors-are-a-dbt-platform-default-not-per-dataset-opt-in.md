---
status: proposed
---

# Monitors and grants ship in the platform's tenant template, requested once the proving run has evidence

The dbt platform is multitenanted and self-serve: each team provisions its own space, and Elementary's tables are built and its history accumulated inside that space. Coverage is therefore decided by what a tenant's space contains when it is provisioned. If monitors depend on each data owner adding them to `schema.yml`, the datasets whose owners never get round to it are exactly the ones that fail unnoticed, and coverage correlates with diligence rather than with risk.

The request is consequently about the **tenant template**, and it has two halves that must travel together:

1. the standard monitor set — volume, freshness, and `column_anomalies` on key columns — applied by convention with per-dataset opt-out;
2. `SELECT` for the triage pipeline's role on that space's Elementary tables, granted at provisioning (ADR-0010).

Without the second half, coverage simply relocates: instead of asking each team to add monitors we would be asking each team for a grant, which is the same diligence-correlated failure wearing a different hat.

Elementary is not a platform default today, and we are not asking for it yet. The proving run needs nothing from the platform team — it runs in E2's own space, from our own dbt project, monitoring E2's landing and consumer tables as sources (ADR-0011). The request goes in after Gate 2 (ADR-0016), carrying a measured per-table cost, a false-positive rate and a working system. Asking now would spend our influence at the moment we have the least evidence, and a "not yet" would poison the later ask.

## Considered Options

- **Ask for the platform default up front, as the proposal's headline request.** Rejected: the fallback (monitoring what we can reach ourselves) covers the whole proving run, so the ask is not needed to ship or to be judged — and an unevidenced ask is the weakest version of it.
- **Opt-in per dataset.** Rejected as the primary model: coverage would correlate with diligence. Kept as the way an owner adds monitors beyond the standard set.
- **Ask for monitors without asking for grants.** Rejected: it produces measured datasets we cannot read.

## Consequences

- v1 has no live cross-team dependency at all. What the reviewer is asked to sponsor is the direction, the evidence bar, and advance warning of this request — not the request itself.
- Because each tenant's Elementary history lives in its own space, a dataset picked up by the template starts its cold start then: roughly two weeks to a useful baseline, fourteen to seasonal comparison. Coverage arrives gradually rather than at once.
- The standard set excludes `all_columns_anomalies`, which issues two queries per column, and `dimension_anomalies`, which stores raw column values (ADR-0010).
- A monitored table without a `timestamp_column` is full-scanned on every run, and Elementary's bucket reuse applies only to dbt sources and incremental models, so a `table`-materialised model recomputes its whole training window each run. Cost is bounded by the timestamp column and the materialisation, not by monitor count alone.
