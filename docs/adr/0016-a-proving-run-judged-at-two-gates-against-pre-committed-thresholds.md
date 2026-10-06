---
status: proposed
---

# v1 is a proving run judged at two gates against thresholds committed before the numbers exist

v1 runs inside E2's own Snowflake space, on a path no downstream consumer reads (ADR-0011). It therefore cannot measure the outcome the proposal exists to improve — incidents caught before a consumer reported them — and claiming that metric would be claiming evidence we cannot produce. We call it a proving run rather than a pilot and judge it on what it can actually show: that the mechanism works, what it costs, and how often it is wrong.

Because we control both ends of the path, the headline measure is **scenario coverage**: a fixed list of injected failures, each with an expected case shape, pass or fail. Six scenarios, of which the last two matter most, because a detector is proven as much by what it declines to raise as by what it raises.

1. Consumer group stalls; the hour's rows land short. Expect one case, infrastructure root, dataset anomaly merged.
2. A monitored column starts arriving null. Expect one case, dataset root, no correlated infrastructure anomaly.
3. The copy job stops entirely. Expect a silence finding, not a freshness anomaly. On E2's 15-minute copy the related case is a *single* missed copy, which an hourly bucket sees as a volume shortfall rather than as silence (ADR-0018) — the two are worth injecting separately, because they exercise different detectors.
4. A late-arriving backfill. Expect **no** case.
5. A legitimate business volume spike. Expect a case dispositioned benign-real, not wrong.
6. A cluster-wide stall across more than five scopes. Expect one storm case with children attached (ADR-0014).

The remaining measures are the false-positive rate by disposition (ADR-0012), the share of data-quality cases arriving already correlated with an infrastructure anomaly, the share of cases that are transform-suspected, and warehouse cost.

Thresholds are committed now, before the numbers have a face:

- **Correlated share.** Above 30%, correlation stays the headline claim. Between 10% and 30%, the claim is reframed as one triage surface for both signal kinds, with correlation where it exists. Below 10%, the case merge does not pay for the declared graph's upkeep and v1 becomes verdicts landing as cases with no merge.
- **Cost.** Measured as a fraction of the warehouse's existing daily credits for the proving run's table set: under 2%, proceed and present it as noise; 2–10%, proceed, and the later platform ask carries a per-table cost table and coverage tiering; above 10%, the standard monitor set is wrong — retune the timestamp column, materialisation and monitor set, and re-probe before asking anyone for anything.
- **False positives.** No more than one *wrong* case per dataset per week, sustained.

Judgement happens at two gates, because the two halves of Elementary's cold start are weeks apart. Hourly buckets (ADR-0018) shorten the first half considerably: a non-seasonal baseline gates on `min_training_set_size` (default 7), which on an hourly series is seven complete hours rather than the two weeks a daily series would need. Seasonal comparison still needs roughly fourteen weeks, because `hour_of_week` seasonality multiplies `days_back` by seven and each seasonal bucket gains one sample per week. Waiting fourteen weeks to learn the cost would be indefensible, so cost is judged at the first gate.

- **Gate 1, around four weeks:** cost number, scenario coverage, case mechanism end to end, ADR-0001 seam built. This is the go/no-go for continuing, and it is what goes back to the reviewer.
- **Gate 2, around sixteen weeks:** sustained false-positive rate, correlated share and transform-suspected share, with seasonal comparison live. This is what backs the tenant-template request (ADR-0007) and the move to owner routing (ADR-0012).

Any false-positive number before Gate 2 is indicative, not deciding.

## Considered Options

- **A single gate at sixteen weeks.** Rejected: it spends a quarter before learning the cost, which is the cheapest thing to learn and the largest political risk.
- **Wait and observe rather than inject failures.** Rejected: the failures we care about are rare by construction, and a proving run that waits for them produces no evidence at Gate 1.
- **Set thresholds after seeing the data.** Rejected: thresholds chosen after the fact are rationalisations. The numbers are arguable; committing before measuring is the part that makes them worth anything.

## Consequences

- Scenario injection needs a way to produce each failure safely on the E2 path. Scenarios 1, 3 and 6 act on E2 infrastructure; 2, 4 and 5 act on the data written to the landing table.
- If the proving run's path later acquires real consumers, the consumer-impact metric becomes measurable and should be added rather than retrofitted into the Gate 2 evidence.
