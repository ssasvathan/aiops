---
status: proposed
---

# Verdict egress re-reads a bounded window and deduplicates, rather than advancing a watermark

The obvious way to poll Elementary's result tables is a watermark over `created_at`. Three verified facts break it: the tables are append-only with no purge, `created_at` is recorded in *session* timezone rather than UTC unlike its sibling columns, and `id` values repeat so they cannot serve as a cursor. A watermark over a column that is neither monotonic nor timezone-stable drops rows whenever a dbt run's session timezone differs from the previous one, or whenever a long run commits rows stamped behind the cursor — and it drops them **silently**, which is the worst available failure mode for a system whose purpose is catching quiet failures.

We therefore do not advance a watermark. The pipeline re-reads a bounded window (the last 48 hours by a UTC-stable column) on every poll and deduplicates on the key ADR-0009 already defines: `test_unique_id`, `column_name`, `test_sub_type`. Ingestion is idempotent by construction, so re-reading is free correctness rather than wasted work. Poll cadence is 15 minutes, which the bounded window makes cheap; a case exists within an hour of a verdict being written. End-to-end latency is set by bucket width and test cadence rather than by this pipeline, and neither is the load cadence: on E2's hourly-bucketed series tested hourly, a shortfall becomes a case **within 75 minutes of the end of the hour it occurred in**, the spread depending on where the bucket boundary falls relative to the test schedule — the bucket must close, the next `dbt test` must run, and the poll must come round. On a daily-bucketed IDP series the same chain takes a day, because a daily bucket cannot close sooner. The first draft stated this as "within an hour of the load finishing" on the assumption that the E2 path was a daily batch; it is not (ADR-0011).

Because we cannot detect our own silence, a daily reconciliation compares the count of verdicts present in Snowflake against findings ingested, and alerts on drift.

## Considered Options

- **Watermark on `created_at`.** Rejected: silent loss, for the reasons above.
- **Watermark on a UTC-stable column with a safety lag.** Viable, and strictly more complex than re-reading a window for the same guarantee, since deduplication is required either way.
- **A Snowflake Python stored procedure writing to Kafka directly.** Removes the poller, the cursor and the timezone trap entirely; the Snowflake Kafka connector is ingest-only, so this is the only outbound-to-Kafka shape available. Kept as a spike and an optimisation, not a dependency.

## Consequences

- The same window-and-deduplicate shape covers curve polling for open cases (ADR-0009), so there is one read pattern rather than two.
- Reconciliation needs read access to a count, which the grants in ADR-0010 already allow.
