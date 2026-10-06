---
status: proposed
---

# A table built by copying another carries the source row's load timestamp through, rather than stamping its own

Every monitored dataset buckets its measurements on a load timestamp (ADR-0008). Where one table is built by copying another — E2's consumer table from its landing table, and every medallion hop above bronze — the copy has to choose whether each row keeps the load timestamp it arrived with upstream or receives a fresh one at build time. We propagate. The obvious instinct is to restamp, because `current_timestamp()` in the copying job is the cheaper thing to write, so a reader finding propagation deserves to know it was deliberate.

Restamping breaks the late-arriving backfill. If the copy job stalls over the 02:00 bucket and catches up at 03:10, propagated rows carry their original arrival times and fill the 02:00 bucket — the one that was short — so Elementary's `backfill_days` recompute revisits it and the shortfall self-heals. Restamped rows land in the 03:00 bucket instead, leaving 02:00 permanently short *and* 03:00 a spike: one incident becomes two anomalies, neither of which describes what happened. That is scenario 4 of the proving run — a late-arriving backfill must produce no case (ADR-0016) — failing by construction, because restamping is what manufactures the spike.

Propagation also makes `bucket_start`/`bucket_end` comparable along the whole declared graph (ADR-0015), so a root dataset and the datasets below it are anomalous in the *same* buckets. Under restamping, correlating a landing table against the consumer table built from it would be a second correlation problem with its own window, invented for ourselves on the three-node path v1 exists to prove.

## Considered Options

- **Restamp at build time.** Rejected: turns every catch-up into a spike, and puts each hop on its own clock.
- **Carry both columns**, bucketing on the propagated one and keeping the build time for diagnostics. Not rejected — the build time is cheap to keep and useful when the question is "when did this copy run". Only the bucketing column is decided here.

## Consequences

- A fully stopped copy job produces no rows and therefore no bucket under either option, so it remains silence's case (ADR-0009) rather than volume's. Propagation changes the partial-failure behaviour, not the total-failure behaviour.
- Monitors on a copied table measure when data *arrived upstream*, not when the copy ran. A copy that runs late but completely is invisible to volume, by design; its lateness is a job-level fact, not a dataset-level one.
