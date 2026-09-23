---
status: proposed
---

# OpenLineage is the convergence path for lineage, not a v1 input and not the transport for DQ measurements

The research began with OpenLineage as the carrier for data-quality signal, but it carries less than we need. Column-level distributions (null percentage, distinct count, min/max) have no first-party producer except Great Expectations, streaming ingestion emits no DQ or statistics facets, and the dbt test magnitudes it does carry are treated as check context, not baselined. It is not a volume source for IDP loads into bronze either: Spark `outputStatistics` is emitted for file and JDBC writes, but the Spark-Snowflake connector probably never fills the counters it reads (research-medallion-path-facts-2026-09-22.md). Elementary produces richer DQ measurement series directly in Snowflake, where the dbt data already lives, and measures rows landed in bronze without anyone else's cooperation.

That leaves lineage, and v1 does not need OpenLineage for it either: dbt's `manifest.json` covers every hop from the landing table onward, and the one hop it misses is declared in the source mapping (ADR-0002). We therefore take no OpenLineage dependency in v1, so nothing in the proposal waits on another team, and treat OpenLineage as the convergence path. It is the standard that eventually replaces the declared hop, on our own schedule for E2, which we own, and as an ask for IDP. It is also the format we can publish our declared mapping in, so the org's lineage tooling sees the same link.

## Considered Options

- **OpenLineage as the DQ transport into the store.** Rejected for v1: it would throw away the column monitors that are the main v1 signal, and it adds an ingestion path to build.
- **OpenLineage for the IDP feed → bronze hop in v1.** Rejected as a dependency: it needs IDP to enable the Airflow provider and a Spark listener. Kept as an improvement, requested with a declared fallback.
- **Emitting the facets we want ourselves.** Possible, and cheaper than expected at platform level: a Spark `ServiceLoader` facet builder or Airflow's `custom_run_facets` applies to every job from one config change. But dbt has no such extension point (`openlineage-dbt` is a post-hoc wrapper over `run_results.json` with no plugin mechanism), and emitting a measurement means measuring it ourselves, which is Elementary's job. See research-manual-openlineage-emission-2026-09-22.md.

## Consequences

- Publishing our declared source mapping as OpenLineage events is a stated bonus, not a v1 deliverable: it is emitted from our side alone, and it fills the ingestion hop the org's lineage tooling also lacks.
- Anything we emit uses its own facet key. Events sharing a run id merge additively, but facets overwrite by key with last-writer-wins and no ordering guarantee.
- An OpenLineage client with no transport configured silently falls back to console output with only a log warning, so any emission path needs a check that events arrive.
