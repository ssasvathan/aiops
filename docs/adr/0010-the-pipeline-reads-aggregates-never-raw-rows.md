---
status: proposed
---

# The triage pipeline reads counts, rates and timings about data, never field values

Elementary stores up to five whole raw failing rows per ordinary dbt test in `test_result_rows`, produced by re-running the test SQL with a limit. Those rows are real business data and may contain personal data. Our pipeline writes casefiles to MinIO outside Snowflake, so reading that table would move customer data into a system built for operational telemetry.

The claim we want to make in review is precise: **the pipeline holds counts, rates and timings about data, never field values.** Stating it as "aggregates, never the data" would be too loose to defend, because some of Elementary's column monitors are aggregates that are nonetheless field values — `min`/`max` on a column returns a value from a real record, and `min_length`/`max_length` leak shape. Four controls hold the line:

- Grant the pipeline's role `USAGE` on the database and schema and `SELECT` table by table, **excluding** `test_result_rows`.
- Propose `test_sample_row_count: 0` so samples are not collected at all.
- Exclude from the monitor set the anomaly tests that carry raw values: `dimension_anomalies`, which writes column values as `dimension_value`, and freshness's raw timestamp fields.
- Enumerate the enabled `column_anomalies` monitor types by name — null rate, null count, missing count, row count, average, and the like — and exclude `min`, `max`, `min_length` and `max_length` unless a key column is demonstrably non-identifying.

Designed in, this costs nothing; retrofitted, it costs an access review and a casefile purge. It also keeps Option A honest, since copying measurements into ClickHouse then stays a copy of counts, rates and timings.

On the multitenant platform the grant is not a single act. Each tenant's Elementary tables live in that tenant's own space, so `SELECT` belongs in the tenant template at provisioning time (ADR-0007) rather than in a conversation per team. Discovery must not depend on being told a tenant exists either: enumerate tenant schemas from `INFORMATION_SCHEMA` and reconcile against what we can actually read, so an ungranted tenant appears as a visible gap rather than as silent absence. v1 needs only E2's own space, so this is v2 machinery — but it determines what we ask for, and therefore is decided now.

## Considered Options

- **Read everything and redact downstream.** Rejected: redaction is a control that fails quietly, and the casefile store would still have held the data.
- **Claim "aggregates, never the data".** Rejected as imprecise: min/max are aggregates and are field values, and a reviewer who knows Elementary will say so.
- **Defer the decision.** Rejected: access grants and the monitor set are being specified now, and this is the cheapest moment to constrain them.

## Consequences

- Elementary's sample-gating flags are mostly undocumented on its site and were found in source (research-elementary-operations-2026-09-22.md), so the setting needs verifying against the version actually installed rather than trusted from the docs.
- Dropping min/max costs little detection power: the failures in the problem statement — short loads, columns going null, loads that never ran — are all counts, rates or timings.
