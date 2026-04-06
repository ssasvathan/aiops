# Functional Requirements

## Seasonal Baseline Management

- **FR1:** The system can store per-scope, per-metric statistical baselines partitioned into 168 time buckets (24 hours × 7 days-of-week)
- **FR2:** The system can seed all baseline time buckets from 30-day Prometheus historical data on startup before the pipeline begins cycling
- **FR3:** The system can update the current time bucket with the latest observation at the end of each pipeline cycle
- **FR4:** The system can recompute all baseline buckets from Prometheus raw data on a weekly schedule, replacing existing bucket contents
- **FR5:** The system can cap stored observations per bucket at a configurable maximum (12 weeks) to bound storage and pollution window
- **FR6:** The system can skip baseline computation for any bucket with fewer than a minimum sample count (MIN_BUCKET_SAMPLES)

## Anomaly Detection

- **FR7:** The system can compute a modified z-score using MAD (Median Absolute Deviation) for each metric for each scope against the current time bucket's historical values
- **FR8:** The system can classify a metric observation as deviating when the modified z-score exceeds the configured MAD threshold
- **FR9:** The system can determine the deviation direction (HIGH or LOW) relative to the baseline median
- **FR10:** The system can record the deviation magnitude (modified z-score), baseline value (median), and current observed value for each deviating metric

## Correlation & Noise Suppression

- **FR11:** The system can collect all deviating metrics per scope within a single pipeline cycle and count them
- **FR12:** The system can emit a finding only when the number of deviating metrics for a scope meets or exceeds the minimum correlated deviations threshold (MIN_CORRELATED_DEVIATIONS)
- **FR13:** The system can suppress single-metric deviations without emitting a finding, logging them at DEBUG level for diagnostic purposes
- **FR14:** The system can skip finding emission for any scope where a hand-coded detector (CONSUMER_LAG, VOLUME_DROP, THROUGHPUT_CONSTRAINED_PROXY) has already fired in the same cycle
- **FR15:** The system can include the list of all correlated deviating metrics and their values in the emitted finding

## Finding & Pipeline Integration

- **FR16:** The system can emit findings with anomaly family `BASELINE_DEVIATION`, severity `LOW`, and `is_primary=False`
- **FR17:** The system can set `proposed_action=NOTIFY` on all baseline deviation findings at the source, ensuring the action can only be lowered by downstream gates
- **FR18:** The system can pass baseline deviation findings through the topology stage for scope enrichment and ownership routing without topology stage modifications
- **FR19:** The system can pass baseline deviation findings through the gating stage (AG0-AG6) for deterministic action decisions without gating stage modifications
- **FR20:** The system can persist baseline deviation case files through the existing case file and outbox stages without structural changes
- **FR21:** The system can dispatch NOTIFY actions (Slack webhook) for baseline deviation findings through the existing dispatch stage

## Metric Discovery & Onboarding

- **FR22:** The system can discover all metrics defined in the Prometheus metrics contract YAML and automatically create baseline storage for each
- **FR23:** The system can baseline a newly added metric by querying its 30-day history during the next startup backfill cycle without any detector code changes
- **FR24:** The system can detect and baseline metrics across all scopes discovered by the evidence stage, including new scopes that appear after initial deployment

## LLM Diagnosis

- **FR25:** The cold-path consumer can process BASELINE_DEVIATION case files and invoke LLM diagnosis asynchronously
- **FR26:** The LLM diagnosis prompt can include all deviating metrics with their values, deviation directions, magnitudes, baseline values, and topology context (topic role, routing key)
- **FR27:** The LLM diagnosis output can be framed as a hypothesis ("possible interpretation") and appended to the case file
- **FR28:** The cold-path can fall back to deterministic fallback diagnosis when LLM invocation fails, preserving hash-chain integrity

## Observability & Operations

- **FR29:** The system can emit OTLP counters for: deviations detected, findings emitted, findings suppressed (single-metric), findings suppressed (hand-coded dedup)
- **FR30:** The system can emit OTLP histograms for: baseline deviation stage computation latency, MAD computation time per scope
- **FR31:** The system can emit structured log events for: baseline deviation stage start/complete, finding emission, suppression reasons, weekly recomputation start/complete/failure
- **FR32:** The system can expose baseline deviation stage health through the existing HealthRegistry
