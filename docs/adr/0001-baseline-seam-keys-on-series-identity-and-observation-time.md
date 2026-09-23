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
