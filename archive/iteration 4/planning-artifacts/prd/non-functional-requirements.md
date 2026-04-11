# Non-Functional Requirements

## Performance

- **NFR-P1:** Baseline deviation stage must complete within 40 seconds per cycle (< 15% of current p95 cycle duration of 263s), measured via OTLP histogram
- **NFR-P2:** Redis `mget` bulk reads for baseline buckets must complete within 50ms per scope batch (500 scopes × 9 metrics = 4,500 keys per cycle, batched by scope)
- **NFR-P3:** MAD computation per scope must complete within 1ms (O(n) with n ≤ 12 values — trivial but must not regress under pathological data)
- **NFR-P4:** Cold-start backfill must complete within 10 minutes for 500 scopes × 9 metrics × 168 buckets, measured from startup log event to pipeline-ready log event
- **NFR-P5:** Weekly recomputation must complete within 10 minutes for the full baseline keyspace without blocking pipeline cycles
- **NFR-P6:** Incremental bucket update (Redis write per scope/metric) must add < 5ms per scope to cycle duration

## Scalability

- **NFR-S1:** Redis memory for seasonal baselines must stay within 200 MB for up to 1,000 scopes × 15 metrics × 168 buckets (2.52M keys) — 3× current projected load
- **NFR-S2:** Baseline deviation stage must scale linearly with scope count — doubling scopes doubles stage duration, no superlinear growth
- **NFR-S3:** Adding a new metric to the Prometheus contract must not require any code changes to the baseline deviation stage — auto-discovery handles new metrics
- **NFR-S4:** Redis key count growth must not degrade `mget` performance beyond 100ms per batch at 3× projected key volume

## Reliability

- **NFR-R1:** Baseline deviation stage failure must not crash the pipeline cycle — per-scope errors are caught and logged; the cycle continues for remaining scopes
- **NFR-R2:** Redis unavailability must trigger fail-open behavior — baseline deviation stage skips detection and emits a degraded health event, existing detectors continue unaffected
- **NFR-R3:** Corrupted or missing baseline data for a specific bucket must not produce false findings — `MIN_BUCKET_SAMPLES` check prevents computation on insufficient data
- **NFR-R4:** Weekly recomputation failure must not corrupt existing baselines — recomputation writes to a staging key and swaps atomically, or writes are idempotent
- **NFR-R5:** The baseline deviation layer must be independently disableable without affecting any other pipeline stage or detector

## Auditability

- **NFR-A1:** BASELINE_DEVIATION case files must maintain SHA-256 hash-chain integrity identical to existing case file families — `triage_hash` links triage to diagnosis
- **NFR-A2:** Every emitted finding must include sufficient context for offline replay: metric_key, deviation_direction, deviation_magnitude, baseline_value (median), current_value, correlated_deviations list, time_bucket (dow:hour)
- **NFR-A3:** Every suppressed finding (single-metric or hand-coded dedup) must be traceable via structured log events with scope, metric, reason code, and cycle timestamp
- **NFR-A4:** Gate evaluations for BASELINE_DEVIATION findings must produce identical `ActionDecisionV1` records reproducible via `reproduce_gate_decision()` with matching rulebook version
