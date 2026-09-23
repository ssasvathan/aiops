---
status: proposed
---

# A DQ anomaly correlates with metric anomalies overlapping its measurement interval, plus a lead-in margin

Correlating the two signal kinds is the proposal's main claim, and their shapes do not match: a metric series is sampled every 300 s, while a measurement describes a whole bucket of loaded data (an hour, a day) and is written when the job finishes. A metric anomaly that caused a short load therefore sits well before the measurement's own timestamp. We correlate on the interval the measurement already carries (`bucket_start`/`bucket_end` in Elementary's `data_monitoring_metrics`) widened by a lead-in margin, rather than on a fixed lookback from the measurement's timestamp. The window is then a property of the series, consistent with ADR-0001, and the margin is a single number to defend rather than per-pair configuration.

## Considered Options

- **Fixed lookback of N hours before the measurement.** Rejected: N would have to be retuned for every bucket size, and it ignores information the measurement already carries.
- **Strict overlap with no margin.** Rejected: it misses the common case where ingestion stalls just before a window and the shortfall lands inside it.

## Consequences

Severity follows from the same case structure rather than being hard-coded as it is today (`severity="LOW"`, `pipeline/stages/baseline_deviation.py`): it is derived from how close the root dataset sits to consumers (a hosting root outranks a bronze root) and from the size of the blast radius, starting from a per-family table in which silence outranks drift.
