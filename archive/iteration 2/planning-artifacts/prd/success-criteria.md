# Success Criteria

## User Success

**On-Call Engineer — "The Responder":**
- Receives pre-triaged, deduplicated actions with ownership resolved, blast radius assessed, and severity determined — starts fixing instead of investigating
- Case IDs link to full evidence snapshots and gate evaluation trails, eliminating manual topology tracing
- Engineers voluntarily reference aiOps case IDs in incident channels as the authoritative context source
- Teams request their infrastructure be added to aiOps monitoring scope

**SRE / Platform Engineer — "The Operator":**
- Operates a self-monitoring triage platform with visible pipeline health via OTLP metrics (outbox age, Redis status, pipeline latency, coordination lock stats)
- Tunes behavior through versioned YAML policy changes that propagate predictably through environments
- Reviews casefile artifacts in lower environments to confirm policy changes produce expected gate decisions before promoting to prod

**Application Team Engineer — "The Maintainer":**
- Configuration changes (topology, denylist, policy) are testable in lower environments with real pipeline execution before promotion
- Policy version stamping in casefiles provides traceability for every config change

## Business Success

- **Prove the architecture under real conditions** — dev OpenShift deployment with hot/hot 2-pod minimum, real Prometheus data, all 11 revision changes activated
- **Build confidence for UAT/prod promotion** — stable operation in dev with documented triage quality evidence sufficient to justify UAT deployment
- **Establish the operational baseline** — first 3 months of real data establish measurement baselines for setting targets in subsequent phases

## Technical Success

**Activation Metrics (Binary Pass/Fail — each CR must pass):**

| CR | Activation Signal |
|---|---|
| CR-01: Wire Redis cache | Sustained window state loads from Redis across cycles; peak profiles use cached data |
| CR-02: DSL rulebook | Gates evaluate from YAML predicates; all 36 test functions pass unmodified |
| CR-03: Unified baselines | Peak classifications produce PEAK/NEAR_PEAK/OFF_PEAK (not UNKNOWN); AG6 fires for qualifying cases |
| CR-04: Sharded findings cache | Shard assignment produces even scope distribution; checkpoint replaces per-scope writes |
| CR-05: Distributed hot/hot | Two pods run with zero duplicate pages/tickets; cycle lock acquired/yielded visible in metrics |
| CR-06: Evidence summary | Builder produces stable text output for LLM consumption |
| CR-07: Cold-path consumer | Consumer processes CaseHeaderEventV1 from Kafka; diagnosis.json written to S3 |
| CR-08: Remove criteria | LLM diagnosis runs for all cases regardless of env/tier/sustained |
| CR-09: Prompt optimization | Enriched prompt includes full Finding fields, domain descriptions, few-shot example |
| CR-10: Redis bulk + memory | Batched Redis loads replace sequential GETs; sustained computation parallelized |
| CR-11: Topology simplify | v0 format code removed; topology YAML loads from config/; resolver tests green |

**Pipeline Health Metrics (Standing Targets):**

| Metric | Target |
|---|---|
| Cycle completion rate | 100% of intervals execute |
| Outbox delivery SLO | p95 <= 1 min, p99 <= 5 min |
| DEAD outbox rows | 0 (standing posture) |
| Gate evaluation latency | p99 <= 500ms |
| Multi-replica coordination | Zero duplicate dispatches |

## Measurable Outcomes

**Operational Metrics (3-Month Baseline Establishment — learning, not targets):**

| Metric | Measurement Method | Purpose |
|---|---|---|
| Mean cases per day | OTLP counter | Volume baseline |
| Action distribution | OTLP counters per action type | Calibration indicator — healthy systems show mostly OBSERVE/NOTIFY with rare PAGE |
| Deduplication suppression rate | OTLP counter (suppressed / total) | Page storm prevention effectiveness |
| Sustained detection rate | OTLP gauge (% anomalies reaching sustained=true) | Detection depth indicator |
| Mean detection-to-action latency | OTLP histogram | Responsiveness baseline |
| Cold-path diagnosis turnaround | OTLP histogram | LLM performance baseline |
| False positive rate | Manual review — actions dispatched vs. acknowledged as real | Trust indicator (critical) |
| Incident prevention rate | Manual review — aiOps cases that preceded manual incident creation | Proactive value indicator |
