---
status: proposed
---

# The triage pipeline reads aggregates about data, never the data itself

Elementary stores up to five whole raw failing rows per ordinary dbt test in `test_result_rows`, produced by re-running the test SQL with a limit. Those rows are real business data and may contain personal data. Our pipeline polls Elementary's tables and writes casefiles to MinIO outside Snowflake, so reading that table would move customer data into a system built for operational telemetry. We grant the pipeline's Snowflake role `USAGE` on the database and schema and `SELECT` table by table, excluding `test_result_rows`, and propose `test_sample_row_count: 0` so the samples are not collected at all. The v1 monitor set also avoids the two anomaly tests that carry raw values: `dimension_anomalies`, which writes column values as `dimension_value`, and freshness's raw timestamp fields.

The claim we want to be able to make in review is simple: the triage pipeline holds aggregates about data, never the data. It is far cheaper to design in than to retrofit, and it keeps Option A honest, since copying measurements to ClickHouse stays a copy of aggregates.

## Considered Options

- **Read everything and redact downstream.** Rejected: redaction is a control that fails quietly, and the casefile store would still have held the data.
- **Defer the decision.** Rejected: access grants and the monitor set are being specified now, and this is the cheapest moment to constrain them.

## Consequences

Elementary's sample-gating flags are mostly undocumented on its site and were found in source (research-elementary-operations-2026-09-22.md), so the setting needs verifying against the version actually installed rather than trusted from the docs.
