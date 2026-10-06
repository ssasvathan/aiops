---
status: proposed
---

# A metric finding is a deviation episode carrying a first and last observation time, not a single anomalous sample

Correlation compares a metric anomaly against a measurement's bucket interval (ADR-0008), which requires the metric side to have a time extent. Today it has none. The hot path reads Prometheus with instant queries only (`pipeline/stages/evidence.py`), groups by scope with no time dimension at all (`pipeline/stages/baseline_deviation.py`), and buckets on the scheduler's cycle time rather than the observation's own (ADR-0001). A stall lasting forty minutes therefore produces one finding per cycle, each an instant, none of them describing the stall. We collapse consecutive deviating cycles for a series into one **deviation episode** carrying `first_seen` and `last_seen`, and raise the finding on the episode.

The reason is the evidence bar, not elegance. With instants, a stall straddling a bucket boundary has some of its cycles inside the correlation window and some outside: a deviation from 02:40 to 03:20 against a window ending at 03:00 puts four cycles in and five out, so one incident becomes four correlated fragments and five orphans. The **correlated share** measured at Gate 2 counts findings and carries a real decision — above 30% correlation stays the headline claim, below 10% the case merge does not pay (ADR-0016) — so that number must count incidents rather than move with scheduler alignment. An episode also means what a responder assumes a finding means: the stall ran from here to here, not that we noticed at 02:15 and again at 02:20.

## Considered Options

- **Keep instants, test containment in the window.** Rejected: works, costs nothing, and makes the headline correlation metric an artifact of cycle alignment.
- **Keep instants, add a per-finding tolerance either side.** Rejected: this is the fixed-lookback option ADR-0008 already rejected, applied to the other side of the join.

## Consequences

- An episode needs a rule for when it closes — how many clean cycles end it rather than interrupt it. That rule is a property of the series kind and belongs in the registry (ADR-0018).
- An open episode has a `last_seen` that keeps moving. Correlation against an open episode is therefore provisional, and a case may gain a correlated cause after it opens. Recurrence handling already covers that shape (ADR-0009).
- The existing two-co-deviating-metrics gate (`MIN_CORRELATED_DEVIATIONS = 2`) now applies across episodes rather than within a cycle, which is a change in meaning as well as in code: two series deviating in overlapping episodes is a weaker claim than two deviating in the same instant, and a more realistic one.
