---
status: proposed
---

# Detect DQ anomalies in Snowflake now (Option C), with our own detector over ClickHouse as the target (Option A)

Two options differ only in where DQ detection runs (ADR-0005). In Option C, Elementary measures and judges inside the dbt run in Snowflake, and the triage pipeline receives verdicts. In Option A, measurements are copied into ClickHouse and our baseline detector judges them alongside metric series. We recommend C now because it needs no detector change and no measurement copy: Elementary already stores the series where the data lives. A is the target, and we move to it when any of these becomes true: Elementary's z-score proves too noisy to triage, correlation needs the raw curves rather than verdicts, or a producer of measurements outside dbt appears that Elementary can't see. Presenting both, with the criteria, gives the reviewer a concrete place to disagree instead of an open choice.

## Considered Options

- **A only.** Rejected for now: it requires the ADR-0001 seam change and a measurement copy pipeline before any DQ signal reaches a case.
- **C only.** Rejected as an end state: verdicts from inside the pipeline cannot be re-baselined, correlated on raw values, or extended to measurements dbt never sees.
- **Present both with no recommendation.** Rejected: it hands the decision to the reviewer without an opinion to push against.

## Consequences

- In C, detection runs only when dbt runs, so a job that never runs produces no verdict. The triage pipeline raises silence findings for series whose expected measurement has not arrived, which carries over unchanged to A.
- The finding vocabulary uses our own DQ families (volume, null rate, freshness, silence), not Elementary's test names, so moving to A doesn't change the contract.
