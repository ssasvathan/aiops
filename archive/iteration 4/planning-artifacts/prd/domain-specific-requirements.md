# Domain-Specific Requirements

## Statistical Validity

- **MAD robustness with sparse data** — Each time bucket has only 4-5 data points from 30-day history. MAD is chosen specifically because the median resists corruption from a single anomalous week (unlike mean/stddev). The `MIN_BUCKET_SAMPLES = 3` threshold prevents MAD computation on statistically meaningless data
- **Seasonality accuracy** — 168 buckets (24 hours × 7 days) capture business-hours vs. off-hours and weekday vs. weekend patterns. This is the minimum granularity that avoids false anomalies from daily traffic cycles — validated by Booking.com's production experience requiring same-weekday comparison
- **Baseline pollution recovery** — Persistent anomalies corrupt baselines over time. Weekly recomputation from Prometheus raw data is the correction mechanism. Cap stored values per bucket at 12 weeks to bound both storage and pollution window

## Operational Safety

- **Conservative-by-default posture** — Industry data shows anomaly detection adoption fails when false positives dominate (only 7.5% of SREs find vendor anomaly detection valuable). Design choices enforce conservatism: MAD threshold ±4.0, correlated deviation requirement, NOTIFY cap, `is_primary=False`
- **Hand-coded detector priority** — Generic baselines are a safety net, not a replacement. Dedup logic must ensure hand-coded detectors always take priority for scopes they cover. This preserves the causal domain knowledge encoded in existing detectors
- **NOTIFY ceiling is structural** — `BASELINE_DEVIATION` findings set `proposed_action=NOTIFY` at source. Existing gates can only lower (env caps), never raise. PAGE/TICKET from a generic baseline finding is structurally impossible — consistent with the project's zero-false-page invariant

## Pipeline Integration Constraints

- **Hot-path determinism preserved** — Baseline deviation stage is deterministic: Redis read → MAD computation → correlation check → finding emission. No LLM, no external calls, no non-deterministic behavior on the hot path
- **Stage ordering dependency** — Baseline deviation stage must run after anomaly stage (to access hand-coded detector output for dedup) and before topology stage (to emit findings that topology can enrich). This is a hard ordering constraint
- **Cold-path decoupling** — LLM diagnosis for BASELINE_DEVIATION cases follows the existing D6 invariant: async, advisory, no import path to hot path, no shared state, no conditional wait. The fallback diagnosis path handles LLM failures identically to existing case types

## Anti-Patterns to Avoid (from Industry Research)

- **"Detect all, filter later"** — Start with correlated deviations only. Single-metric detection is logged but not surfaced. Expand scope gradually based on operational experience
- **"One algorithm fits all"** — MAD is the Phase 1 default. Growth feature (metric personality auto-classification) addresses metric-type-specific tuning when data justifies it
- **"Batch-evaluated in streaming context"** — MAD with sliding window works natively in the 5-minute streaming cycle. No batch-only algorithms
- **"Ignoring cold-start"** — Explicit cold-start strategy: 30-day backfill seeds baselines, `MIN_BUCKET_SAMPLES` prevents computation on insufficient data, margin bands (minimum deviation threshold) prevent false positives during early population
