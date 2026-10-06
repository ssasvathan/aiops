---
status: proposed
---

# A single anomalous measurement raises a finding, and its case lives until the series recovers

ADR-0001 treats gating as a property of the series kind. Made concrete for DQ measurement series: **one anomalous measurement raises a finding**. The metric path's requirement of two co-deviating series in a scope (`MIN_CORRELATED_DEVIATIONS = 2`) exists because a single noisy Prometheus series means little, but a dataset may carry only one monitor, and requiring corroboration would discard most of the signal the proposal exists to catch. Corroboration instead raises severity (ADR-0008): an anomaly confirmed by a second monitor on the same dataset, or by an infrastructure anomaly in the correlation window, outranks a lone one.

A DQ case carries three things: the verdict, the recent measurement curve from `data_monitoring_metrics` with its expected range, and the ordinary dbt checks that failed on the same dataset in the same run as context. A verdict alone is a notification, not something anyone can triage.

**Curve polling is not optional.** A case closes when the series produces in-range measurements for three consecutive buckets, or when a human resolves it — and past `backfill_days` (default 2) an Elementary anomaly test returns to pass and emits no verdict at all, whether or not anything was fixed. "In range" is therefore observable only from the measurement curve, never from verdicts, so the pipeline polls `data_monitoring_metrics` for every series with an open case. Auto-close never fires on a bucket Elementary did not write: an absent measurement is silence, not recovery. Three buckets means three of *that kind's* buckets (ADR-0018), so recovery takes about three hours on E2's hourly series and several days on a daily IDP one — which is correct in both cases, because the incident is not over until the data is.

**A bucket that has not closed is not evidence.** A measurement for the bucket currently filling describes a partial hour or a partial day, so Elementary scores it against complete buckets and finds a shortfall that does not exist: with hourly buckets and hourly test runs, that is one false verdict per series per run, every run, self-healing an hour later when `backfill_days` recomputes the completed bucket. The pipeline therefore ignores any verdict or measurement whose `bucket_end` lies in the future. The predicate sits in the bounded-window read (ADR-0013) and is safe there because `bucket_end`, unlike `created_at`, is timezone-stable. It is one rule serving three readers, which is why it lives with us rather than in Elementary's `detection_delay`: finding ingest would otherwise raise the false verdict, auto-close would otherwise count a half-filled bucket that happens to read in-range toward its three and close a live incident early, and silence would otherwise fire for every series for the duration of its current bucket. `detection_delay` can additionally stop Elementary *computing* the open bucket, which is a cost question for the probe rather than a correctness mechanism — its behaviour at bucket boundaries is undocumented and unverified.

That the recovery rule forces curve polling is also a fact about the options: reading curves is load-bearing rather than enriching, which moves the cost balance measurably toward Option A (ADR-0006).

While an anomaly persists, subsequent verdicts for the same series attach to the open case as recurrences, deduplicated on Elementary's own key (`test_unique_id`, `column_name`, `test_sub_type`). Elementary's own suppression state lives in `alerts_v2` and is an `edr` CLI feature invisible to a table reader, so deduplication is ours.

**Silence is derived from an expected series set, not from observed history.** The set of series that ought to produce is derived from the declared graph (ADR-0015) and the monitors we declare, and cadence for the v1 set is **declared**, with learning from observation history as the scaling path. Learned cadence was the original design and it fails exactly where silence matters most: there is no history during the first two weeks, which is the proving run's most fragile period, and a series that has never produced a measurement has no observations to learn from — so an onboarded dataset whose load never runs at all would be invisible. At v1's scale a declared list of tens of entries does not rot; across hundreds of datasets it would, which is when learning takes over.

## Considered Options

- **Require two co-deviating measurements.** Rejected: most datasets will never have two monitors deviating at once.
- **Verdict-only cases.** Rejected: nothing for a responder to act on, no way to compute recovery, and no path towards Option A.
- **Close a case when the test passes.** Rejected: anomaly tests return to pass on their own, so this would auto-resolve live incidents.
- **A new case per failing run, or fixed-window suppression.** Rejected: both fragment one incident, and suppression hides recurrences rather than recording them.
- **Learned cadence as the primary source for silence.** Deferred rather than rejected: right at scale, blind during cold start and blind to series that never produce.

## Consequences

- The anomaly score, bounds and training statistics are not flat columns in `elementary_test_results`; they sit in a JSON blob that we parse to build the finding. Option A holds those numbers directly, which is a point in its favour.
- Curve polling uses the same bounded-window read as verdict egress (ADR-0013), so there is one read pattern.
- Three consecutive buckets is a starting number, like the lead-in margin and the storm threshold: its value comes from the proving run.
