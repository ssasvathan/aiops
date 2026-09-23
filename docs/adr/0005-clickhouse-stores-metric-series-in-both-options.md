---
status: proposed
---

# ClickHouse is the store for metric series in both proposed options

The system is greenfield, so replacing Prometheus as the metric store is a platform choice, not a migration. ClickHouse, which is already an available platform, holds metric series in both options put to review. In Option A it also holds DQ measurement series copied out of Snowflake. That leaves the two options differing on a single axis: where DQ detection runs (our detector reading ClickHouse, or Elementary in Snowflake sending verdicts). This decision stands on its own merits: history lives in the table, so the weekly Prometheus rebuild of Redis buckets goes away, and dense-side rollups can use materialized views.

## Consequences

- The OTel Collector moves from the pinned `0.96.0` to a release with the current ClickHouse exporter schema. Breaking schema changes landed along the way (research doc §1.4).
- Baselines computed at query time must be materialised with a version to stay replayable, because `quantileTDigest` is documented as nondeterministic.
