---
stepsCompleted: [1, 2, 3]
inputDocuments: []
session_topic: 'Universal metric-agnostic baseline and anomaly detection for all Kafka telemetry'
session_goals: 'Simple statistical approach for baselines, architecture to generalize current system, handling different metric types, pros/cons of current vs proposed, keep it pragmatic'
selected_approach: 'ai-recommended'
techniques_used: ['First Principles Thinking', 'Six Thinking Hats', 'Morphological Analysis']
ideas_generated: []
context_file: ''
---

# Brainstorming Session Results

**Facilitator:** Sas
**Date:** 2026-04-05

## Session Overview

**Topic:** Universal metric-agnostic baseline and anomaly detection for all Kafka telemetry (messages/sec, consumer lag, throughput, etc.), feeding anomalies into the existing topology resolution and rule gate pipeline

**Goals:**
- Best simple statistical approach for metric-agnostic baselines
- Architecture to generalize the current single-metric baseline system
- Handling different metric characteristics without overcomplicating things
- Expert analysis of pros/cons: current system vs. proposed universal approach
- Keeping it pragmatic — sophistication comes later, simplicity now

### Context Guidance

_Project currently baselines only topic messages/sec. Other metrics (consumer group lag, throughput) have no baseline. Vision: if all telemetry has baselines, anomaly detection becomes metric-agnostic — any deviation on any metric for a topic triggers the existing topology resolution and rule gate pipeline._

### Session Setup

_Sas wants to explore generalizing the anomaly detection system while keeping the approach simple and appropriate for the current project phase. Critical constraint: avoid sophisticated approaches._

## Technique Selection

**Approach:** AI-Recommended Techniques
**Analysis Context:** Universal metric-agnostic baseline & anomaly detection with focus on simplicity, pros/cons analysis, and pragmatic architecture

**Recommended Techniques:**

- **First Principles Thinking:** Strip away assumptions to identify what metric-agnostic baselining fundamentally requires — separate essential from accidental complexity
- **Six Thinking Hats:** Systematically examine current single-metric approach vs. proposed universal approach from all angles — facts, risks, benefits, creativity, process
- **Morphological Analysis:** Map the design space of parameters (metric types, statistical methods, thresholds, integration points) and find the simplest viable combinations

**AI Rationale:** This sequence moves from understanding (what do we actually need?) to critical analysis (what are we gaining/losing?) to concrete design (how do we build it simply?). All three techniques favor structured, analytical thinking over wild creativity — matching Sas's preference for pragmatism over sophistication.

## Technique Execution Results

### First Principles Thinking

**Industry Research Conducted:** Comprehensive analysis of Datadog, Dynatrace, New Relic, Elastic, Splunk, and Grafana LGTM stack approaches to anomaly detection across metrics, logs, and traces. Full research saved to `industry-research-anomaly-detection-2026-04-05.md`.

**Long-Term Vision Revealed:** Not just Kafka metrics — the goal is a universal anomaly detection platform across the full LGTM stack (metrics, logs, traces) with topology enrichment of anomaly origins.

**First Principles Established:**

1. **"Derive a number, baseline the number, detect deviation" IS the industry standard pattern** — every major platform converts logs and traces to numeric time series before applying statistical detection. The vision is architecturally sound.

2. **This is a complementary safety net, not a replacement for hand-coded detectors** — the three existing detectors (CONSUMER_LAG, VOLUME_DROP, THROUGHPUT_CONSTRAINED_PROXY) encode domain-specific causal understanding that generic baselines cannot replicate. The new layer catches "unknown unknowns" — anomalies we haven't anticipated.

3. **The foundation must be signal-agnostic from day one** — same abstraction handles Prometheus metrics today, Tempo traces and Loki logs tomorrow, without architectural rewrites.

4. **Conservative by default** — industry research shows false positives kill adoption (only 7.5% of SREs found vendor anomaly detection valuable; Google Cloud reports 53% false positive rate). Better to miss subtle anomalies than to drown in noise.

5. **"Metric-agnostic" does NOT mean "algorithm-agnostic"** — different metric types (seasonal vs. non-seasonal, spiky vs. smooth, bounded vs. unbounded) need different statistical treatment.

6. **Topology enrichment should be decoupled from detection** — detect first, enrich second. Only Dynatrace does topology-aware detection, everyone else enriches post-detection. Our existing pipeline already does this correctly.

**Proven Simple Statistical Methods (Tier 1):**
- Z-score with sliding window (mean + N stddev) — simplest, most common
- Median + MAD — robust to outliers and spikes
- Percentile bands (5th/95th from same-weekday history) — Booking.com's proven approach

**Key Reference:** Grafana's open-source `promql-anomaly-detection` framework implements exactly two strategies (adaptive = mean/stddev, robust = median/MAD) using pure PromQL — no external ML. This validates the simplicity-first approach.

### Six Thinking Hats Analysis

**White Hat (Facts):**
- Current: 3 hand-coded detectors, 1 baseline (max-based), 9 metrics in contract, 8 unbaselined
- Proposed: Generic baseline layer + existing detectors coexisting (two-layer architecture)
- Cold-start backfill already being built — 30-day query_range() for all 9 metrics
- Peak classification has timezone and bucket_minutes in policy but implements flat history (no time-of-day segmentation)

**Red Hat (Gut Feelings):**
- Anxiety about noise from generic approach — valid, confirmed by research
- Hard to imagine topology mapping for non-Kafka signals (logs, traces have different scope shapes) — real architectural gap: baseline layer can be signal-agnostic but topology resolution cannot
- Uncertainty about statistical method — resolved: MAD is the robust safe default

**Black Hat (Risks — Prioritized):**
1. **Risk 2 (Highest): Generic findings are less actionable** — Mitigation: Option C — LLM diagnosis agent provides hypothesis asynchronously, framed as "possible interpretation" not diagnosis. Safe because generic findings capped at NOTIFY.
2. **Risk 3: Scope explosion for logs/traces** — Mitigation: Baseline at service-level for logs/traces, topic-level for Kafka. Don't baseline at pod/endpoint granularity.
3. **Risk 1: Noise overwhelming gate pipeline** — Mitigation: Route BASELINE_DEVIATION through gates capped at OBSERVE/NOTIFY, never TICKET/PAGE. Consider correlated-deviation escalation.
4. Risk 4: Baseline pollution from persistent shifts — self-corrects with weekly recomputation from Prometheus
5. Risk 5: YAGNI if logs/traces never materialize — mitigated by low implementation cost and value for Kafka unknown-unknowns alone

**Yellow Hat (Benefits):**
1. Stop being blind to unanticipated failure modes on 8 currently unbaselined metrics
2. Cold-start backfill does most of the hard work already
3. Zero-code monitoring for new metrics added to contract YAML
4. Proven pattern extends to traces/logs when ready
5. LLM hypothesis → graduation pipeline → system discovers new detector rules over time
6. Conservative threshold + NOTIFY cap = low-risk deployment alongside existing detectors

**Green Hat (Creative Ideas):**
1. **Correlated deviation as escalation trigger** — fire NOTIFY only when 2+ metrics for same scope deviate in same cycle. Single-metric deviations logged silently.
2. **Metric personality auto-classification** — analyze 30-day history on backfill to auto-select method per metric (smooth → z-score, spiky → MAD, near-zero → static threshold)
3. **Graduation pipeline** — when LLM produces same hypothesis 3+ times, surface it as candidate hand-coded detector rule

**Blue Hat (Process):** Proceed to Morphological Analysis for concrete architecture decisions.

### Seasonality Design Decision

**Problem:** Flat baselines produce false anomalies twice daily (business-hours-vs-night pattern). Current peak classification has timezone/bucket_minutes in policy but implementation uses flat `Sequence[float]` with no time segmentation.

**Decision:** 168 time-bucketed baselines (hour-of-day × day-of-week). Redis key becomes `aiops:baseline:{source}:{scope}:{metric_key}:{day_of_week}:{hour}`. Cold-start backfill provides ~4-5 data points per bucket from 30 days history.

### Statistical Method Decision: MAD

**Rationale:**
- Outlier resistant: single spikes don't corrupt baseline (median barely moves vs. mean being dragged)
- Critical with only 4-5 points per time bucket — one anomalous week would poison z-score
- No distribution assumptions — Kafka metrics are often right-skewed (especially consumer lag)
- Less sensitive by design — aligns with conservative safety-net philosophy
- Formula: `modified_z = 0.6745 × (value - median) / MAD`, threshold ±3.5 to ±5.0
- Downside: slow to adapt to genuine shifts, mitigated by weekly recomputation from Prometheus

### Morphological Analysis — Architecture Design Decisions

#### Parameter 1: Baseline Storage
**Decision:** Separate Redis keyspace with individual keys per time bucket.
- Key format: `aiops:seasonal_baseline:{scope}:{metric_key}:{dow}:{hour}`
- Clean separation from existing `aiops:baseline:` keys used by VOLUME_DROP detector
- Individual keys: only read/write current bucket per cycle, `mget` for bulk reads when needed
- 756K keys (9 metrics × 500 scopes × 168 buckets) is trivial for Redis

#### Parameter 2: Baseline Computation
**Decision:** Backfill on startup + incremental each cycle + weekly recompute.
- Cold-start backfill seeds all 168 buckets from 30-day Prometheus query_range() (already being built)
- Each 5-min cycle appends current observation to current time bucket (baseline stays fresh)
- Weekly job re-queries Prometheus and rebuilds all buckets (corrects drift/pollution)
- Cap stored values per bucket at 12 weeks to bound storage

#### Parameter 3: Pipeline Position
**Decision:** New stage after anomaly stage, before topology.
- Receives anomaly stage output to enable deduplication
- Dedup logic: skip scopes where hand-coded detector already fired (hand-coded has priority)
- Generic layer only fills the gaps the specific detectors don't cover

#### Parameter 4: Finding Model
**Decision:** Extend existing `AnomalyFinding` with `BASELINE_DEVIATION` family.
- `anomaly_family="BASELINE_DEVIATION"` added to existing Literal type
- `severity="LOW"`, `is_primary=False` always
- Additional context fields: `metric_key`, `deviation_direction` (HIGH/LOW), `deviation_magnitude` (modified z-score), `baseline_value` (median), `current_value`, `correlated_deviations` (other deviating metrics for same scope)
- Uniform pipeline — topology, gates, case file need no structural changes

#### Parameter 5: Correlation Requirement
**Decision:** Require 2+ metrics deviating for same scope to emit finding.
- Single-metric deviations logged silently (debug/metrics), no finding emitted
- Correlated deviations (2+ metrics, same scope, same cycle) emit `BASELINE_DEVIATION` finding
- Dramatically reduces noise; correlation pattern enriches LLM diagnosis context
- Cluster-level alert grouping explicitly out of scope for Phase 1

#### Parameter 6: Threshold Configuration
**Decision:** Constants in code, no policy YAML.
```python
MAD_THRESHOLD = 4.0
MIN_CORRELATED_DEVIATIONS = 2
MAX_ACTION = Action.NOTIFY
MIN_BUCKET_SAMPLES = 3
```
- Extract to YAML only when operators demonstrate need to tune without code changes
- Avoids premature configuration surface area

#### Parameter 7: Gate Pipeline Integration
**Decision:** Near-zero gate changes.
- Baseline deviation stage sets `proposed_action=NOTIFY` on GateInputV1
- Existing gates can only lower (env caps), never raise — NOTIFY cap enforced at source
- AG0-AG6 process BASELINE_DEVIATION identically to other families
- No new gate rules needed

#### Parameter 8: LLM Diagnosis
**Decision:** Included in Phase 1 (stakeholder value).
- Async invocation after case file creation
- Context provided to LLM: deviating metrics + values + topology + metric contract descriptions
- Hypothesis appended to case file, framed as "possible interpretation"
- Non-blocking — finding and NOTIFY dispatch don't wait for LLM response

#### Parameter 9: Scope and Case File Model
**Decision:** One finding per scope, separate case files. Same as existing detectors.
- If 15 topics deviate on same cluster, 15 separate case files
- Cluster-level grouping explicitly out of scope
- Address if noisy in practice as a future feature

### Full Pipeline Architecture

```
COLD-START BACKFILL (startup, blocking)
  query_range() 30 days → populate 168 buckets per (scope, metric) in Redis
  + existing peak history + existing baseline cache

5-MINUTE PIPELINE CYCLE:
  Evidence Stage → Anomaly Stage (3 hand-coded, unchanged)
    → Baseline Deviation Stage (NEW)
        1. Read current time bucket per (scope, metric) from Redis
        2. Compute modified z-score via MAD
        3. Collect deviations per scope
        4. Skip scopes where hand-coded detector already fired
        5. Emit finding only if 2+ metrics deviate (correlated)
        6. Update current bucket with new observation
    → Peak Stage → Topology Stage → Gate Input + Decision
        BASELINE_DEVIATION enters with proposed_action=NOTIFY, is_primary=False
    → Case File + Async LLM Diagnosis
        1. Create case file
        2. Async: invoke LLM with full context
        3. Append hypothesis to case file

WEEKLY: Recompute all buckets from Prometheus query_range()
```

### Future Signal Expansion (Out of Scope, Architecture Ready)

- **Traces:** Derive RED metrics (rate, errors, p99 duration) per service from Tempo → feed through same baseline layer with scope = (env, service_name)
- **Logs:** Derive rate metrics (error count, pattern frequency) per service from Loki → same baseline layer with scope = (env, service_name)
- **Topology:** Each signal domain needs its own scope-to-topology mapping. Baseline layer is signal-agnostic; topology resolution is not.

### Session Highlights

**Breakthrough Insight:** The two-layer architecture (hand-coded detectors for known failure modes + generic baseline safety net for unknown unknowns) mirrors the Datadog Watchdog + Monitors pattern — industry-validated.

**Critical Constraint Honored:** No sophisticated ML, no premature YAML, no over-engineering. MAD + time bucketing + correlation requirement is the simplest viable architecture that catches real anomalies conservatively.

**Key Risk Mitigations:**
- Noise → correlated deviation requirement + NOTIFY cap
- Actionability → LLM diagnosis provides hypothesis
- Scope explosion → service-level for future signals
- False positives → MAD threshold ±4.0, conservative by design
- Cold start → solved by backfill already in progress

**Research Asset Created:** `industry-research-anomaly-detection-2026-04-05.md` — comprehensive vendor/practitioner analysis reusable for stakeholder conversations and future design decisions.
