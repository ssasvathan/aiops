# Success Criteria

## User Success

**On-Call Engineer — "The anomaly I didn't know to look for"**
- Receives a NOTIFY-level notification for a correlated multi-metric deviation that no hand-coded detector was designed to catch — the system caught an unanticipated failure mode
- The notification includes an LLM-generated hypothesis ("possible interpretation") providing an investigation starting point, not just raw statistical data
- Zero increase in alert noise from the new layer — correlated deviation requirement and NOTIFY cap ensure the engineer's existing signal-to-noise ratio is preserved or improved

**SRE / Platform Engineer — "It just works for new metrics"**
- Adds a new metric to the Prometheus metrics contract YAML; on the next backfill cycle, that metric automatically has baselines, anomaly detection, and topology-enriched findings — zero detector code authored
- Monitors baseline deviation stage health via existing OTLP metrics (computation latency, deviations detected, findings emitted, findings suppressed by dedup)

## Business Success

- **Coverage gap closed:** All 9 metrics in the Prometheus contract have seasonal baselines. The current 8-metric blind spot is eliminated
- **Unknown-unknown detection:** System detects at least one anomaly pattern in the first 3 months of operation that no hand-coded detector would have caught — validated by manual post-incident review
- **Zero regression in existing detectors:** Hand-coded detectors (CONSUMER_LAG, VOLUME_DROP, THROUGHPUT_CONSTRAINED_PROXY) continue to operate identically; dedup logic ensures baseline deviation never duplicates their findings
- **Architecture validation:** The signal-agnostic baseline layer design is validated as extensible to non-Kafka signals without structural pipeline changes

## Technical Success

- **Pipeline integration:** BASELINE_DEVIATION findings flow through topology, gating (AG0-AG6), case file, outbox, and dispatch stages with zero structural changes to those stages
- **Redis scale:** 756K baseline keys (9 metrics × 500 scopes × 168 buckets) operate within Redis memory and latency budgets; `mget` bulk reads stay within cycle time budget
- **MAD computation:** Baseline deviation stage completes within the existing 5-minute cycle budget without extending p95 cycle duration beyond the current shard lease TTL calibration basis (263s p95)
- **Cold-start seeding:** 30-day Prometheus backfill populates all 168 time buckets with sufficient samples (minimum 3 per bucket) for MAD computation on first operational cycle
- **Dedup correctness:** Scopes where a hand-coded detector fired in the same cycle never receive a duplicate BASELINE_DEVIATION finding

## Measurable Outcomes

| Metric | Target | Measurement |
|---|---|---|
| Metrics with seasonal baselines | 9/9 (100%) | Contract YAML audit |
| False positive rate (generic layer) | < 20% of emitted findings | Manual review over first 3 months |
| Correlated deviation suppression | > 80% of raw single-metric deviations suppressed | OTLP counter ratio |
| Cycle duration impact | < 15% increase in p95 cycle duration | OTLP histogram comparison |
| Duplicate finding rate | 0 (hand-coded dedup) | OTLP counter |
