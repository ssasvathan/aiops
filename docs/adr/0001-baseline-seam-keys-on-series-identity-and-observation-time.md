---
status: proposed
---

# The baseline seam keys on series identity and observation time, not on the scheduler cycle and Prometheus labels

We checked whether our baseline deviation detector generalizes to DQ measurement series. The math (modified z-score over MAD, `baseline/computation.py`) is series-agnostic, but everything around it assumes metric series: buckets derive from the hot-path cycle time rather than the observation's own time (`pipeline/stages/baseline_deviation.py`), bucketing is fixed at hour-of-week for every series, so a daily run is compared only against the same weekday's history (`baseline/constants.py`, `baseline/client.py`), zero-variance series are silently skipped, findings require two co-deviating metrics per scope, scope identity is built from Prometheus labels and rejects anything without `env`/`cluster_id`/`topic` (`pipeline/stages/evidence.py`), and the finding vocabulary is a closed set of Kafka families. We therefore state openly that the abstraction was shaped by its only user, and place the seam one level lower: a baseline is computed over a series identity plus the observation's own timestamp, with cadence, bucketing, minimum history and gating treated as properties of the series kind.

## Considered Options

- **Claim the abstraction generalizes and add a DQ adapter.** Rejected: an adapter would have to fake Prometheus labels and would inherit cycle-time bucketing, the zero-variance skip and the two-metric gate, each of which is wrong for per-run measurements.
- **Give DQ its own detector and share only the finding contract.** Kept as a fallback, but it duplicates the one part that does generalize (the math).

## Consequences

Moving computation into ClickHouse changes where the baseline is computed, not what a baseline means for each series kind. That offload does not settle this decision.

The four properties named above are only real if a series kind is a thing somewhere rather than a phrase in this ADR. Gating is made concrete for DQ measurement series in ADR-0009; cadence, bucketing and minimum history are declared in the registry of ADR-0018, which is also what makes "registering a second series kind" an accurate description of the work rather than a figure of speech.

The seam is built in v1, on the metric path, even though v1 detects DQ anomalies in Snowflake (ADR-0006). Metric series move to ClickHouse in v1 regardless (ADR-0005), so the detector's storage layer is being touched anyway, and building the seam then is what turns Option A from a migration into the registration of a second series kind. Deferring it until an exit criterion fires would mean deciding to move detection at the moment we have the least appetite for a refactor.

Nothing is live and no one depends on the current hot path, so it is rebuilt against the new seam rather than migrated behind it. A future reader should not go looking for a migration that never happened, or for a compatibility shim that was never needed.
