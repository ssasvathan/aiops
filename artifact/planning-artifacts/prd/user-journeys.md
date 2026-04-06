# User Journeys

## Journey 1: On-Call Engineer — "The anomaly nobody expected"

**Priya, SRE on night rotation, 2:14 AM**

Priya's phone buzzes — a Slack NOTIFY from aiOps. Not a PAGE, so she checks it from bed rather than bolting to her laptop. The notification reads: `BASELINE_DEVIATION — 3 correlated metric deviations on topic orders.completed (env: prod, cluster: kafka-prod-east)`. The metrics: `kafka_consumer_group_lag` is 4.2× above its Tuesday-2AM baseline, `kafka_topic_bytes_in_per_sec` has dropped to 0.3× its expected value, and `kafka_consumer_group_members` is down from its usual 6 to 2.

None of the hand-coded detectors fired — lag isn't sustained enough for CONSUMER_LAG, throughput hasn't hit the constrained proxy threshold, and there's no volume drop detector for member count. But three metrics deviating together on the same topic is a signal.

She opens the case file. The LLM hypothesis reads: *"Possible consumer group partial failure — member count reduction correlates with lag increase and throughput decrease. Suggest checking consumer pod health in kafka-prod-east for orders.completed consumer group."* Two of the four consumer pods had OOMKilled 12 minutes ago. The remaining two are absorbing the load but falling behind.

Priya scales the deployment back to 4 pods. Lag recovers within 10 minutes. Without the baseline layer, this would have become a CONSUMER_LAG alert 45 minutes later — after order processing delays reached customer-visible impact.

**Requirements revealed:** BASELINE_DEVIATION finding with correlated metric context, LLM hypothesis in case file, Slack NOTIFY dispatch, topology-enriched routing to correct team.

## Journey 2: On-Call Engineer — "The noise that wasn't"

**Marcus, platform engineer, Tuesday morning**

Marcus reviews the aiOps dashboard after the weekend. He sees 47 single-metric deviations logged at DEBUG level — individual metrics that crossed the MAD threshold but had no correlated partner. Zero findings emitted, zero notifications sent. Three correlated BASELINE_DEVIATION findings were emitted over the weekend, all NOTIFY level: two turned out to be expected behavior during a planned maintenance window (Marcus notes this — context signals for maintenance windows would be a useful future feature), and one caught a genuine capacity imbalance that self-corrected after an autoscaler event.

The existing hand-coded detectors fired 6 times over the same period — all correctly, all unaffected by the new layer. The dedup logic worked: one scope had both a CONSUMER_LAG finding and a baseline deviation on the same cycle, and only the hand-coded finding was emitted.

**Requirements revealed:** Single-metric suppression with DEBUG logging, correlated deviation threshold, hand-coded detector dedup, OTLP metrics for suppression/emission counts, zero interference with existing detectors.

## Journey 3: SRE / Platform Engineer — "New metric, zero code"

**Aisha, platform team lead**

The team decides to monitor `kafka_topic_replication_factor` after a near-miss where under-replication went undetected. Aisha adds the metric to `config/policies/prometheus-metrics-contract-v1.yaml` with the appropriate PromQL query and label mappings. She merges the change and deploys to dev.

On the next startup, the cold-start backfill queries 30 days of history for the new metric across all scopes, populating 168 time buckets per scope in Redis. Within one 5-minute cycle, the baseline deviation stage is computing MAD scores for the new metric alongside the original 9. No detector code was authored. No threshold was tuned. The metric simply exists in the contract, and the baseline layer handles it.

A week later, a topic's replication factor drops from 3 to 2 during a broker restart. The deviation correlates with a spike in `kafka_topic_under_replicated_partitions`, triggering a BASELINE_DEVIATION finding. The LLM hypothesis correctly identifies broker health as the likely cause.

**Requirements revealed:** Contract-driven metric discovery, cold-start backfill for new metrics, automatic baseline population, zero-code onboarding path.

## Journey 4: SRE / Platform Engineer — "Tuning the safety net"

**Raj, SRE responsible for aiOps operations**

After the first month in dev, Raj reviews baseline deviation metrics in Dynatrace. He sees the MAD threshold of 4.0 is slightly too sensitive for consumer lag (spiky metric) and slightly too conservative for throughput (smooth metric). He'd like to tune per-metric-type, but that's a Growth feature. For now, he checks the constants in code — `MAD_THRESHOLD = 4.0`, `MIN_CORRELATED_DEVIATIONS = 2` — and confirms they're reasonable for the current deployment. If tuning becomes urgent, the constants are a single-line code change.

He also reviews the weekly recomputation job logs. All buckets were rebuilt successfully from Prometheus, correcting a baseline that had been polluted by a 3-day anomalous period the previous week. The recomputation took 4 minutes for 500 scopes × 10 metrics × 168 buckets.

**Requirements revealed:** OTLP observability for baseline stage, weekly recomputation job, code-level threshold constants (not YAML yet), monitoring of recomputation health.

## Journey Requirements Summary

| Capability | Revealed By Journey |
|---|---|
| BASELINE_DEVIATION finding with correlated context | Journey 1, 2 |
| LLM hypothesis in case file for baseline deviations | Journey 1 |
| Correlated deviation requirement (2+ metrics) | Journey 1, 2 |
| Single-metric suppression with DEBUG logging | Journey 2 |
| Hand-coded detector dedup | Journey 2 |
| Contract-driven metric discovery and auto-baselining | Journey 3 |
| Cold-start backfill for all metrics (including new) | Journey 3 |
| OTLP observability metrics for baseline stage | Journey 2, 4 |
| Weekly recomputation from Prometheus | Journey 4 |
| Code-level threshold constants | Journey 4 |
| NOTIFY cap on all baseline deviation findings | Journey 1, 2 |
| Slack dispatch for NOTIFY actions | Journey 1 |
