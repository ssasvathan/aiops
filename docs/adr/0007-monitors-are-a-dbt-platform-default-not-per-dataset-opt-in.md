---
status: proposed
---

# DQ monitors ship as a dbt platform default, not as per-dataset opt-in

Elementary's monitors are declared in `schema.yml`, and the dbt jobs are written and owned by the data owners, one team per dataset. If coverage depends on each owner adding monitors, the datasets whose owners never get round to it are exactly the ones that fail unnoticed, and the proposal's value would be spread across dozens of separate conversations. The dbt platform, by contrast, is owned by one team inside our org, and we have influence there. We therefore propose the platform ships the Elementary package and a standard monitor set (volume, freshness, null rates on key columns) applied by convention, with opt-out per dataset, so a data owner gets monitoring without writing anything.

## Considered Options

- **Opt-in per dataset.** Rejected as the primary model: coverage would correlate with diligence rather than with risk. Kept as the way a data owner adds monitors beyond the default set.
- **Monitor only what we can reach without the platform team** (bronze sources and the hosting zone). Kept as the fallback if the platform team declines, and it still covers the v1 zones, bronze and hosting.

## Consequences

- This is the single place where our influence over the dbt platform is spent, and it belongs in the proposal's requests-of-other-platforms section with its fallback.
- The standard set is volume, freshness and `column_anomalies` on key columns. It excludes `all_columns_anomalies`, which issues two queries per column, and `dimension_anomalies`, which stores raw column values (ADR-0010).
- A monitored table without a `timestamp_column` is full-scanned on every run, and Elementary's bucket reuse applies only to dbt sources and incremental models, so a `table`-materialised model recomputes its whole training window each run. Cost is therefore bounded by the timestamp column and the materialisation, not by the monitor count alone.
- Monitors on bronze sources need a load timestamp column on the landing tables, which we add ourselves on the E2 repository tables and must request from IDP for its bronze loads. Without it a source gets volume only, one value per run, and no freshness.
