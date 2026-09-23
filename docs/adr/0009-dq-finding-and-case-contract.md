---
status: proposed
---

# A single anomalous measurement raises a finding, and its case carries the curve and lives until the series recovers

ADR-0001 treats gating as a property of the series kind. Made concrete for DQ measurement series: **one anomalous measurement raises a finding**. The metric path's requirement of two co-deviating series in a scope (`MIN_CORRELATED_DEVIATIONS = 2`) exists because a single noisy Prometheus series means little, but a dataset may carry only one monitor, and requiring corroboration would discard most of the signal the proposal exists to catch. Corroboration instead raises severity (ADR-0008): an anomaly confirmed by a second monitor on the same dataset, or by an infrastructure anomaly in the correlation window, outranks a lone one.

A DQ case carries three things, mirroring what the metric path already attaches: the verdict, the recent measurement curve from `data_monitoring_metrics` with the expected range, and the ordinary dbt checks that failed on the same dataset in the same run as context. A verdict alone is a notification, not something anyone can triage. Reading the curve in Option C is also a rehearsal of Option A, and if pulling curves dominates the polling cost, that is evidence for switching (ADR-0006).

While an anomaly persists, subsequent verdicts for the same series attach to the open case as recurrences rather than opening cases of their own, deduplicated on Elementary's own key (`test_unique_id`, `column_name`, `test_sub_type`). Elementary's suppression state lives in `alerts_v2` and is an `edr` CLI feature invisible to a table reader, so deduplication is ours. **A passing test does not close a case**: an anomaly test fires only while the bad bucket is inside `backfill_days` (default 2 days) and then returns to pass whether or not anything was fixed. A case closes when the series produces in-range measurements for several consecutive buckets, or when a human resolves it.

Silence (a measurement that never arrives) uses an expected cadence learned from the series' own observation history, with a declared override. Taking the cadence from the producing schedule would be more accurate but reintroduces a dependency on platforms we do not all own, which ADR-0004 just removed.

## Considered Options

- **Require two co-deviating measurements.** Rejected: most datasets will never have two monitors deviating at once.
- **Verdict-only cases.** Rejected: nothing for a responder to act on, and no path towards Option A.
- **A new case per failing run, or fixed-window suppression.** Rejected: both fragment one incident, and suppression hides recurrences rather than recording them.
- **Declared cadence per dataset for silence.** Kept only as an override: a hand-kept list across hundreds of datasets rots.

## Consequences

The anomaly score, bounds and training statistics are not flat columns in `elementary_test_results`; they sit in a JSON blob that we parse to build the finding. Option A holds those numbers directly, which is a point in its favour.
