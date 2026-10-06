---
status: proposed
---

# A DQ anomaly correlates with metric anomalies overlapping its measurement interval, plus a lead-in margin

Correlating the two signal kinds is the proposal's main claim, and their shapes do not match: a metric series is sampled every 300 s, while a measurement describes a whole bucket of loaded data (an hour, a day) and is written when the job finishes. A metric anomaly that caused a short load therefore sits well before the measurement's own timestamp. We correlate on the interval the measurement already carries (`bucket_start`/`bucket_end` in Elementary's `data_monitoring_metrics`) widened by a lead-in margin, rather than on a fixed lookback from the measurement's timestamp. The window is then a property of the series, consistent with ADR-0001, and the margin is **derived from the bucket width** — half a bucket — rather than carried as configuration.

**The margin is derived, not tuned.** Its only job is a deviation that straddles a bucket boundary: on a load timestamp the ingestion failure that shortened a bucket almost always falls *inside* that bucket, and plain overlap catches it, so the margin covers the stall at 01:52 that damaged the 02:00 bucket and nothing more. Its natural scale is therefore the bucket, and deriving it obeys ADR-0001's rule that bucketing is a property of the series kind without introducing a per-kind number to tune. A single global margin was the first draft's answer and it only looked right because the whole path was assumed daily: against a 15-minute consumer-table copy on hourly buckets and a once-daily IDP batch on daily buckets (ADR-0011, ADR-0018), no one number serves both. The proving run therefore *validates* the formula rather than discovering a value.

**This holds only where `timestamp_column` is a load timestamp, so every series v1 correlates on buckets on a loader-stamped column** (ADR-0011). The direction of the margin depends on it. On a load timestamp the bucket describes when data *arrived*, so an ingestion failure lands at or just before the window it damaged and a lead-in margin on `bucket_start` points at the cause. On an event timestamp the bucket describes when the business event *happened*, so the ingestion failure that shortened the load sits **after `bucket_end`** and a lead-in margin widens the window away from the cause; a volume shortfall there is also frequently a business fact rather than a defect, which would feed the benign-real disposition continuously (ADR-0016). Elementary offers no default for `timestamp_column`, and with none set it writes `bucket_start` as `NULL` and `bucket_end` as the run timestamp — leaving this ADR's mechanism nothing to key on at all.

## Considered Options

- **Fixed lookback of N hours before the measurement.** Rejected: N would have to be retuned for every bucket size, and it ignores information the measurement already carries.
- **Strict overlap with no margin.** Rejected: it misses the common case where ingestion stalls just before a window and the shortfall lands inside it.
- **A single global margin.** Rejected once E2's real cadences were known: an hourly series and a daily one carry different boundary risk, so one number is wrong for one of them. Deriving the margin from bucket width keeps the virtue the single number had — one thing to defend — without the error.
- **A margin declared per series kind.** Viable, and the fallback if the proving run shows boundary straddles behaving differently by kind. Not chosen now because it adds a knob where a formula suffices.

## Consequences

Severity follows from the same case structure rather than being hard-coded as it is today (`severity="LOW"`, `pipeline/stages/baseline_deviation.py`): it is derived from how close the root dataset sits to consumers (a hosting root outranks a bronze root) and from the size of the blast radius, starting from a per-family table in which silence outranks drift.
