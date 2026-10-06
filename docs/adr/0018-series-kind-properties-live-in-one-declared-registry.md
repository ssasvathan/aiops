---
status: proposed
---

# The properties of a series kind live in one declared registry, not scattered across the tools that consume them

ADR-0001 places the baseline seam at a series identity plus the observation's own time, with **cadence, bucketing, minimum history and gating treated as properties of the series kind**. ADR-0009 made gating concrete for DQ measurement series; the other three were left as prose. They are now decided somewhere in three different places — `time_bucket` in a dbt `meta` block, expected cadence in pipeline config, gating in code — which means a series kind is a phrase in an ADR rather than a thing anyone can read. We declare them in one registry owned by the pipeline, and generate or validate the dbt `meta` blocks from it.

The properties a kind carries are bucket width, expected cadence, minimum history, gating, and the correlation margin — the last derived from bucket width rather than stored (ADR-0008). The registry is what makes the seam real: registering a second series kind becomes adding a row, which is the claim the Option A exit path rests on (ADR-0006).

## Bucket width follows from load cadence

Bucket width is not a preference. The smallest shortfall a volume monitor can see is roughly one load unit spread over the bucket, so the bucket should hold a small number of load units:

| Series kind | Loads per day | Bucket | Units per bucket | Smallest detectable shortfall |
| --- | --- | --- | --- | --- |
| E2 landing table — continuous | n/a | hour | n/a | arrival rate is itself the series |
| E2 consumer table — 15-minute copy | 96 | hour | 4 | one failed copy, a ~25% drop |
| IDP bronze — daily batch | 1 | day | 1 | a partial load only |

Hourly buckets on E2's two tables are therefore not a tuning choice: daily buckets would render one failed copy a ~1% shortfall and invisible. The same rule gives IDP bronze daily buckets when it arrives, by the rule rather than by exception.

Two consequences of the rule are worth stating because they divide labour between detectors. On a **daily** kind a volume anomaly can only catch a *partial* load, since a missing load writes no bucket at all and is silence's case (ADR-0009); on E2's consumer table a missing copy *is* catchable as volume, because the bucket's other three copies still filled it. And Elementary's finest `time_bucket` is `hour`, with no sub-hourly period available — so a kind loading every minute would carry 60 units per bucket and a single failure would be invisible. E2 at 15 minutes sits well inside that ceiling; anything faster does not, and would need detection in our own store (ADR-0006) rather than a smaller bucket.

## One dbt project, one schedule per tier

Because bucket width differs by kind, test cadence has to as well. A single hourly invocation over everything would revisit daily-bucketed series hourly and, since `backfill_days` recomputes recent buckets regardless of whether anything changed, recompute two daily buckets twenty-four times a day for no new information. So the project carries one scheduled invocation per cadence tier, selected by tag — `dbt test --select tag:hourly`, `tag:daily` — and **the tags are generated from this registry rather than maintained beside it**, because a series bucketed daily and tested hourly is a drift that no tool would report. A separate dbt project per tier was rejected: it duplicates the Elementary install and splits its result schema, which breaks the single egress path ADR-0013 assumes.

Two facts this rests on are **unverified** and need checking against the installed versions before Gate 1: dbt's selector semantics over sources, and whether Elementary's `on-run-end` hook writes results correctly when only a subset is selected. The research covers tags only for PII sampling. A tier that silently stops being tested is the failure mode to rule out.

## Considered Options

- **Leave each property where its consuming tool wants it.** Rejected: nothing to build, but nothing to read either, and the seam ADR-0001 describes stays rhetorical.
- **A registry for pipeline-side properties only**, leaving bucket width in dbt `meta`. Rejected as the worst of the three: bucket width is the one property both sides need, since the pipeline derives the correlation margin from it.

## Consequences

- Changing a kind's bucket width is not a config tweak. `time_bucket` is part of the identity Elementary keys its stored history on, so changing it forks that history and forces a full `days_back` recompute. Bucket width is settled before the cost probe, not after.
- The registry is the natural home for the declared cadence silence reads from, so the expected-series set and the bucket grid stop being two independent declarations that can disagree.
