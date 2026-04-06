---
stepsCompleted: [step-01-validate-prerequisites, step-02-design-epics, step-03-create-stories, step-04-final-validation]
inputDocuments:
  - artifact/planning-artifacts/prd/index.md (sharded - 11 files)
  - artifact/planning-artifacts/architecture/index.md (sharded - 6 files)
---

# aiOps - Epic Breakdown

## Overview

This document provides the complete epic and story breakdown for aiOps, decomposing the requirements from the PRD, UX Design if it exists, and Architecture requirements into implementable stories.

## Requirements Inventory

### Functional Requirements

FR1: The system can store per-scope, per-metric statistical baselines partitioned into 168 time buckets (24 hours x 7 days-of-week)
FR2: The system can seed all baseline time buckets from 30-day Prometheus historical data on startup before the pipeline begins cycling
FR3: The system can update the current time bucket with the latest observation at the end of each pipeline cycle
FR4: The system can recompute all baseline buckets from Prometheus raw data on a weekly schedule, replacing existing bucket contents
FR5: The system can cap stored observations per bucket at a configurable maximum (12 weeks) to bound storage and pollution window
FR6: The system can skip baseline computation for any bucket with fewer than a minimum sample count (MIN_BUCKET_SAMPLES)
FR7: The system can compute a modified z-score using MAD (Median Absolute Deviation) for each metric for each scope against the current time bucket's historical values
FR8: The system can classify a metric observation as deviating when the modified z-score exceeds the configured MAD threshold
FR9: The system can determine the deviation direction (HIGH or LOW) relative to the baseline median
FR10: The system can record the deviation magnitude (modified z-score), baseline value (median), and current observed value for each deviating metric
FR11: The system can collect all deviating metrics per scope within a single pipeline cycle and count them
FR12: The system can emit a finding only when the number of deviating metrics for a scope meets or exceeds the minimum correlated deviations threshold (MIN_CORRELATED_DEVIATIONS)
FR13: The system can suppress single-metric deviations without emitting a finding, logging them at DEBUG level for diagnostic purposes
FR14: The system can skip finding emission for any scope where a hand-coded detector (CONSUMER_LAG, VOLUME_DROP, THROUGHPUT_CONSTRAINED_PROXY) has already fired in the same cycle
FR15: The system can include the list of all correlated deviating metrics and their values in the emitted finding
FR16: The system can emit findings with anomaly family BASELINE_DEVIATION, severity LOW, and is_primary=False
FR17: The system can set proposed_action=NOTIFY on all baseline deviation findings at the source, ensuring the action can only be lowered by downstream gates
FR18: The system can pass baseline deviation findings through the topology stage for scope enrichment and ownership routing without topology stage modifications
FR19: The system can pass baseline deviation findings through the gating stage (AG0-AG6) for deterministic action decisions without gating stage modifications
FR20: The system can persist baseline deviation case files through the existing case file and outbox stages without structural changes
FR21: The system can dispatch NOTIFY actions (Slack webhook) for baseline deviation findings through the existing dispatch stage
FR22: The system can discover all metrics defined in the Prometheus metrics contract YAML and automatically create baseline storage for each
FR23: The system can baseline a newly added metric by querying its 30-day history during the next startup backfill cycle without any detector code changes
FR24: The system can detect and baseline metrics across all scopes discovered by the evidence stage, including new scopes that appear after initial deployment
FR25: The cold-path consumer can process BASELINE_DEVIATION case files and invoke LLM diagnosis asynchronously
FR26: The LLM diagnosis prompt can include all deviating metrics with their values, deviation directions, magnitudes, baseline values, and topology context (topic role, routing key)
FR27: The LLM diagnosis output can be framed as a hypothesis ("possible interpretation") and appended to the case file
FR28: The cold-path can fall back to deterministic fallback diagnosis when LLM invocation fails, preserving hash-chain integrity
FR29: The system can emit OTLP counters for: deviations detected, findings emitted, findings suppressed (single-metric), findings suppressed (hand-coded dedup)
FR30: The system can emit OTLP histograms for: baseline deviation stage computation latency, MAD computation time per scope
FR31: The system can emit structured log events for: baseline deviation stage start/complete, finding emission, suppression reasons, weekly recomputation start/complete/failure
FR32: The system can expose baseline deviation stage health through the existing HealthRegistry

### NonFunctional Requirements

NFR-P1: Baseline deviation stage must complete within 40 seconds per cycle (< 15% of current p95 cycle duration of 263s), measured via OTLP histogram
NFR-P2: Redis mget bulk reads for baseline buckets must complete within 50ms per scope batch (500 scopes x 9 metrics = 4,500 keys per cycle, batched by scope)
NFR-P3: MAD computation per scope must complete within 1ms (O(n) with n <= 12 values)
NFR-P4: Cold-start backfill must complete within 10 minutes for 500 scopes x 9 metrics x 168 buckets
NFR-P5: Weekly recomputation must complete within 10 minutes for the full baseline keyspace without blocking pipeline cycles
NFR-P6: Incremental bucket update (Redis write per scope/metric) must add < 5ms per scope to cycle duration
NFR-S1: Redis memory for seasonal baselines must stay within 200 MB for up to 1,000 scopes x 15 metrics x 168 buckets (2.52M keys)
NFR-S2: Baseline deviation stage must scale linearly with scope count
NFR-S3: Adding a new metric to the Prometheus contract must not require any code changes to the baseline deviation stage
NFR-S4: Redis key count growth must not degrade mget performance beyond 100ms per batch at 3x projected key volume
NFR-R1: Baseline deviation stage failure must not crash the pipeline cycle -- per-scope errors are caught and logged; the cycle continues for remaining scopes
NFR-R2: Redis unavailability must trigger fail-open behavior -- baseline deviation stage skips detection and emits a degraded health event
NFR-R3: Corrupted or missing baseline data for a specific bucket must not produce false findings -- MIN_BUCKET_SAMPLES check prevents computation on insufficient data
NFR-R4: Weekly recomputation failure must not corrupt existing baselines -- writes are idempotent or use staging key with atomic swap
NFR-R5: The baseline deviation layer must be independently disableable without affecting any other pipeline stage or detector
NFR-A1: BASELINE_DEVIATION case files must maintain SHA-256 hash-chain integrity identical to existing case file families
NFR-A2: Every emitted finding must include sufficient context for offline replay: metric_key, deviation_direction, deviation_magnitude, baseline_value, current_value, correlated_deviations list, time_bucket
NFR-A3: Every suppressed finding must be traceable via structured log events with scope, metric, reason code, and cycle timestamp
NFR-A4: Gate evaluations for BASELINE_DEVIATION findings must produce identical ActionDecisionV1 records reproducible via reproduce_gate_decision()

### Additional Requirements

**From Architecture -- Structural & Integration:**
- Brownfield project: no starter template. Baseline deviation extends existing architecture with zero new infrastructure dependencies
- Stage ordering is a hard constraint: evidence -> peak -> baseline_deviation -> topology -> casefile -> outbox -> gating -> dispatch
- Hot-path determinism must be preserved: no LLM, no external calls, no non-deterministic behavior in the baseline deviation stage
- Frozen contract models: AnomalyFinding extension must be additive only (new anomaly_family literal), following Procedure A from schema-evolution-strategy.md
- 4 explicit input sources for the stage: Prometheus observations, hand-coded detector findings (for dedup), Redis baseline data, current time bucket identifier
- Stage function signature must make all inputs explicit with no hidden dependencies for deterministic unit testing

**From Architecture -- Data & Storage:**
- Redis key schema: flat string keys `aiops:seasonal_baseline:{scope}:{metric_key}:{dow}:{hour}` with JSON-serialized float lists
- Dedicated SeasonalBaselineClient class encapsulates all Redis baseline I/O (read_buckets, update_bucket, seed_from_history, bulk_recompute)
- Weekly recomputation: background async coroutine, in-memory build + bulk write, triggered by hot-path timer check
- Cold-start backfill: extends existing peak history backfill, reuses same 30-day Prometheus query_range data

**From Architecture -- Implementation Patterns (P1-P7):**
- P1: Use tuple[str, ...] for scope identity -- no typed scope model, no joined strings
- P2: All constants in baseline/constants.py with SCREAMING_SNAKE_CASE -- no inline magic numbers
- P3: Single pure function time_to_bucket(dt) -> (dow, hour) as sole bucket derivation source
- P4: Single optional field baseline_context: BaselineDeviationContext | None on AnomalyFinding
- P5: BaselineDeviationStageOutput follows existing frozen Pydantic stage output pattern
- P6: Structured log events use baseline_deviation_ prefix (10 event types defined)
- P7: OTLP instruments use aiops.baseline_deviation. prefix (4 counters, 2 histograms)

**From Architecture -- Documentation:**
- Each implementation story must include corresponding documentation updates for affected docs (9 docs identified: architecture.md, architecture-patterns.md, component-inventory.md, data-models.md, contracts.md, runtime-modes.md, developer-onboarding.md, project-structure.md, project-context.md)

**From Architecture -- Project Structure:**
- New package: src/aiops_triage_pipeline/baseline/ (constants.py, client.py, computation.py, models.py)
- New stage file: pipeline/stages/baseline_deviation.py
- Modified: pipeline/scheduler.py, models/anomaly_finding.py
- New test files: tests/unit/baseline/, tests/unit/pipeline/stages/test_baseline_deviation.py, tests/integration/test_baseline_deviation.py

### FR Coverage Map

FR1: Epic 1 - Seasonal baseline storage (168 time buckets per scope/metric)
FR2: Epic 1 - Cold-start backfill seeding from 30-day Prometheus history
FR3: Epic 1 - Incremental bucket update per pipeline cycle
FR4: Epic 1 - Weekly recomputation from Prometheus raw data
FR5: Epic 1 - Cap stored observations per bucket at 12 weeks
FR6: Epic 1 - Minimum sample count guard (MIN_BUCKET_SAMPLES)
FR7: Epic 2 - MAD computation (modified z-score) per scope/metric/bucket
FR8: Epic 2 - Deviation classification when z-score exceeds MAD threshold
FR9: Epic 2 - Deviation direction determination (HIGH or LOW)
FR10: Epic 2 - Deviation magnitude, baseline value, and current value recording
FR11: Epic 2 - Per-scope deviating metric collection and counting
FR12: Epic 2 - Correlated deviation gate (MIN_CORRELATED_DEVIATIONS)
FR13: Epic 2 - Single-metric suppression with DEBUG logging
FR14: Epic 2 - Hand-coded detector dedup (skip if CONSUMER_LAG/VOLUME_DROP/THROUGHPUT_CONSTRAINED_PROXY fired)
FR15: Epic 2 - Correlated deviating metrics list in emitted finding
FR16: Epic 2 - BASELINE_DEVIATION finding model (severity LOW, is_primary=False)
FR17: Epic 2 - NOTIFY cap at source (proposed_action=NOTIFY)
FR18: Epic 2 - Topology stage passthrough (zero modifications)
FR19: Epic 2 - Gating stage passthrough (AG0-AG6, zero modifications)
FR20: Epic 2 - Case file and outbox stage passthrough (zero modifications)
FR21: Epic 2 - Dispatch stage passthrough (Slack webhook for NOTIFY)
FR22: Epic 1 - Prometheus contract YAML metric auto-discovery
FR23: Epic 1 - Zero-code new metric backfill on next startup
FR24: Epic 1 - Dynamic scope discovery from evidence stage
FR25: Epic 3 - Cold-path BASELINE_DEVIATION case file processing
FR26: Epic 3 - LLM prompt with full deviation context and topology
FR27: Epic 3 - Hypothesis-framed LLM output appended to case file
FR28: Epic 3 - Deterministic fallback diagnosis on LLM failure
FR29: Epic 4 - OTLP counters (deviations detected, findings emitted/suppressed)
FR30: Epic 4 - OTLP histograms (stage latency, MAD computation time)
FR31: Epic 4 - Structured log events (stage lifecycle, suppression, recomputation)
FR32: Epic 4 - HealthRegistry integration for baseline deviation stage

## Epic List

### Epic 1: Seasonal Baseline Foundation & Auto-Discovery
The system automatically discovers all metrics from the Prometheus contract, seeds 30 days of seasonal baselines across all scopes on startup, keeps baselines fresh through incremental updates and weekly recomputation, and onboards new metrics with zero code changes.
**FRs covered:** FR1, FR2, FR3, FR4, FR5, FR6, FR22, FR23, FR24

### Epic 2: Correlated Anomaly Detection & Pipeline Integration
On-call engineers receive Slack NOTIFY notifications when 2+ metrics deviate from seasonal baselines on the same scope in the same cycle. Single-metric noise is suppressed, hand-coded detector findings take priority, and findings flow through the full pipeline (topology enrichment, gating, case file, dispatch) with zero changes to existing stages.
**FRs covered:** FR7, FR8, FR9, FR10, FR11, FR12, FR13, FR14, FR15, FR16, FR17, FR18, FR19, FR20, FR21

### Epic 3: LLM-Powered Diagnosis
Each BASELINE_DEVIATION case file receives an asynchronous LLM-generated hypothesis explaining the likely cause of correlated deviations, giving on-call engineers an actionable investigation starting point rather than raw statistical data. Falls back to deterministic diagnosis when LLM is unavailable.
**FRs covered:** FR25, FR26, FR27, FR28

### Epic 4: Operational Observability & Health
SREs can monitor baseline deviation stage health and effectiveness through OTLP metrics (deviations detected, findings emitted/suppressed, computation latency), structured log events (stage lifecycle, suppression reasons, recomputation status), and the HealthRegistry — enabling data-driven tuning decisions and operational confidence.
**FRs covered:** FR29, FR30, FR31, FR32

---

## Epic 1: Seasonal Baseline Foundation & Auto-Discovery

The system automatically discovers all metrics from the Prometheus contract, seeds 30 days of seasonal baselines across all scopes on startup, keeps baselines fresh through incremental updates and weekly recomputation, and onboards new metrics with zero code changes.

### Story 1.1: Baseline Constants & Time Bucket Derivation

As a platform engineer,
I want baseline deviation constants and time bucket logic defined in a single source of truth,
So that all baseline components use consistent threshold values and bucket derivation logic.

**Acceptance Criteria:**

**Given** the baseline package is created with baseline/__init__.py and baseline/constants.py
**When** constants.py is imported
**Then** the following constants are available as module-level SCREAMING_SNAKE_CASE values: MAD_CONSISTENCY_CONSTANT=0.6745, MAD_THRESHOLD=4.0, MIN_CORRELATED_DEVIATIONS=2, MIN_BUCKET_SAMPLES=3, MAX_BUCKET_VALUES=12
**And** no magic numbers are hardcoded anywhere outside this module (P2)

**Given** a UTC datetime for Wednesday at 14:00
**When** time_to_bucket() is called
**Then** it returns (2, 14) representing Wednesday (weekday()=2) and hour 14

**Given** a non-UTC datetime (e.g., UTC+5)
**When** time_to_bucket() is called
**Then** it converts to UTC before deriving the bucket
**And** returns the correct (dow, hour) tuple based on the UTC-normalized time

**Given** any datetime input
**When** time_to_bucket() is called
**Then** dow is in range 0-6 (Monday=0 through Sunday=6) and hour is in range 0-23
**And** this function is the sole source of truth for all datetime-to-bucket conversions across all components (P3)

**Given** the new files baseline/__init__.py, baseline/constants.py, and time_to_bucket() in baseline/computation.py
**When** unit tests in tests/unit/baseline/test_constants.py and tests/unit/baseline/test_computation.py are run
**Then** all constant values and time_to_bucket edge cases (midnight, end-of-week, timezone boundaries) pass
**And** docs/project-structure.md, docs/component-inventory.md, and docs/data-models.md are updated to reflect the new baseline package

### Story 1.2: SeasonalBaselineClient - Redis Baseline Storage

As a platform engineer,
I want seasonal baselines stored in Redis with per-scope, per-metric, per-time-bucket granularity,
So that the detection stage can read historical baselines for comparison and baselines stay bounded in size.

**Acceptance Criteria:**

**Given** a SeasonalBaselineClient instance with a Redis connection
**When** read_buckets(scope, metric_key, dow, hour) is called
**Then** it reads the key `aiops:seasonal_baseline:{scope}:{metric_key}:{dow}:{hour}` from Redis
**And** returns a list of float values deserialized from JSON

**Given** a SeasonalBaselineClient instance
**When** update_bucket(scope, metric_key, dow, hour, value) is called
**Then** it appends the new value to the existing list at the corresponding Redis key
**And** if the list length exceeds MAX_BUCKET_VALUES (12), the oldest value is removed to enforce the cap (FR5)

**Given** a scope with 9 metrics and a single time bucket
**When** read_buckets is called for all metrics
**Then** it uses Redis mget to batch the reads in a single round-trip (NFR-P2)
**And** completes within 50ms per scope batch

**Given** a Redis key that does not yet exist
**When** read_buckets is called for that key
**Then** it returns an empty list (no error)

**Given** Redis is unavailable
**When** any SeasonalBaselineClient method is called
**Then** it raises an appropriate exception for the caller to handle (fail-open at stage level)

**Given** unit tests in tests/unit/baseline/test_client.py
**When** tests are executed
**Then** they use a mock/fake Redis client with no real Redis dependency
**And** all read, write, mget batching, and cap enforcement behaviors are verified
**And** docs/data-models.md is updated with the Redis seasonal baseline key schema

### Story 1.3: Cold-Start Backfill Seeding with Metric Auto-Discovery

As a platform engineer,
I want seasonal baselines automatically seeded from 30-day Prometheus history on startup for all discovered metrics and scopes,
So that detection is ready on the first pipeline cycle without manual data population or code changes for new metrics.

**Acceptance Criteria:**

**Given** the pipeline starts with empty Redis baseline keys
**When** the startup backfill sequence runs
**Then** seed_from_history() on SeasonalBaselineClient is called with the same 30-day Prometheus query_range data already fetched for peak history (D5)
**And** each data point is partitioned into its (dow, hour) time bucket using time_to_bucket()
**And** partitioned values are written to Redis baseline keys for all scopes x all metrics x 168 buckets

**Given** a new metric is added to the Prometheus metrics contract YAML
**When** the pipeline restarts and backfill runs
**Then** the new metric receives baseline seeding alongside all existing metrics (FR22, FR23)
**And** no code changes are required (NFR-S3)

**Given** a new scope appears in evidence stage scope discovery
**When** the next startup backfill runs
**Then** the new scope receives baseline seeding for all contract metrics (FR24)

**Given** backfill is in progress
**When** the pipeline attempts to start cycling
**Then** the pipeline blocks until both peak history and baseline seeding complete (D5)
**And** a baseline_deviation_backfill_seeded structured log event is emitted with scope count, metric count, and bucket count

**Given** 500 scopes x 9 metrics x 168 buckets
**When** cold-start backfill runs
**Then** it completes within 10 minutes (NFR-P4)

**Given** unit and integration tests
**When** tests are executed
**Then** seed_from_history correctly partitions time-series data into 168 buckets
**And** integration tests in tests/integration/test_baseline_deviation.py verify Redis-backed seeding
**And** docs/runtime-modes.md and docs/developer-onboarding.md are updated to document the extended backfill

### Story 1.4: Weekly Baseline Recomputation

As an SRE,
I want baselines automatically recomputed weekly from Prometheus raw data,
So that baseline pollution from persistent anomalies is corrected without manual intervention.

**Acceptance Criteria:**

**Given** the hot-path scheduler checks `aiops:seasonal_baseline:last_recompute` each cycle
**When** 7+ days have elapsed since the last recomputation
**Then** it spawns a background asyncio coroutine to run bulk_recompute() on SeasonalBaselineClient (D4)

**Given** a weekly recomputation is triggered
**When** the background coroutine runs
**Then** it queries Prometheus query_range for 30-day history for all metrics and scopes
**And** partitions data into 168 time buckets entirely in memory
**And** writes all buckets via a bulk Redis pipeline write (mset or pipelined SET)
**And** updates `aiops:seasonal_baseline:last_recompute` timestamp
**And** caps each bucket at MAX_BUCKET_VALUES (12)

**Given** a weekly recomputation is in progress
**When** pipeline cycles run concurrently
**Then** cycles read existing (old) baselines without corruption or blocking (NFR-P5)
**And** the bulk write creates a negligible inconsistency window

**Given** a weekly recomputation fails mid-execution (e.g., pod restart, Prometheus timeout)
**When** the pod recovers
**Then** no partial writes exist in Redis — nothing was written before the bulk write phase (NFR-R4)
**And** recomputation retries on the next cycle that checks the timer

**Given** the recomputation lifecycle
**When** recomputation starts, completes, or fails
**Then** baseline_deviation_recompute_started, baseline_deviation_recompute_completed, or baseline_deviation_recompute_failed structured log events are emitted with duration, key count, or error info

**Given** 500 scopes x 9 metrics x 168 buckets
**When** weekly recomputation runs
**Then** it completes within 10 minutes (NFR-P5)

**Given** unit tests
**When** tests are executed
**Then** bulk_recompute is tested with mock Prometheus and mock Redis
**And** timer logic is verified to correctly detect 7-day expiry
**And** docs/runtime-modes.md is updated with the weekly recomputation background task documentation

---

## Epic 2: Correlated Anomaly Detection & Pipeline Integration

On-call engineers receive Slack NOTIFY notifications when 2+ metrics deviate from seasonal baselines on the same scope in the same cycle. Single-metric noise is suppressed, hand-coded detector findings take priority, and findings flow through the full pipeline (topology enrichment, gating, case file, dispatch) with zero changes to existing stages.

### Story 2.1: MAD Computation Engine

As a platform engineer,
I want a MAD-based statistical computation engine that calculates modified z-scores against seasonal baselines,
So that metric deviations can be identified with outlier-resistant statistics.

**Acceptance Criteria:**

**Given** a list of historical values for a time bucket and a current observation
**When** compute_modified_z_score() is called in baseline/computation.py
**Then** it computes the median of the historical values
**And** computes the MAD (Median Absolute Deviation) of the historical values
**And** applies MAD_CONSISTENCY_CONSTANT (0.6745) to estimate sigma
**And** returns the modified z-score: (current - median) / (MAD / MAD_CONSISTENCY_CONSTANT)

**Given** a modified z-score whose absolute value exceeds MAD_THRESHOLD (4.0)
**When** deviation classification is applied
**Then** the observation is classified as deviating (FR8)

**Given** a current value above the baseline median
**When** deviation direction is determined
**Then** direction is "HIGH" (FR9)
**And** given a current value below the baseline median
**Then** direction is "LOW"

**Given** a deviating observation
**When** the deviation result is constructed
**Then** it includes: deviation_magnitude (modified z-score), baseline_value (median), current_value (FR10)

**Given** a bucket with fewer than MIN_BUCKET_SAMPLES (3) values
**When** MAD computation is attempted
**Then** computation is skipped and no deviation is reported (FR6, NFR-R3)

**Given** historical values where all values are identical (MAD = 0)
**When** MAD computation is attempted
**Then** it handles the zero-MAD edge case without division by zero
**And** does not produce false deviations

**Given** unit tests in tests/unit/baseline/test_computation.py
**When** tests are executed
**Then** all MAD computation paths are verified: normal deviation, no deviation, sparse data skip, zero-MAD, HIGH/LOW direction, boundary threshold values
**And** computation completes within 1ms per scope (NFR-P3)

### Story 2.2: BASELINE_DEVIATION Finding Model

As a platform engineer,
I want a BASELINE_DEVIATION finding model that carries deviation context through the pipeline,
So that downstream stages can process baseline deviations identically to existing finding types with full replay context.

**Acceptance Criteria:**

**Given** the baseline/models.py module
**When** BaselineDeviationContext is defined
**Then** it is a frozen Pydantic model with fields: metric_key (str), deviation_direction (Literal["HIGH", "LOW"]), deviation_magnitude (float), baseline_value (float), current_value (float), time_bucket (tuple[int, int])
**And** follows the frozen=True Pydantic model pattern (P4)

**Given** the baseline/models.py module
**When** BaselineDeviationStageOutput is defined
**Then** it is a frozen Pydantic model with fields: findings (tuple[AnomalyFinding, ...]), scopes_evaluated (int), deviations_detected (int), deviations_suppressed_single_metric (int), deviations_suppressed_dedup (int), evaluation_time (datetime)
**And** follows the existing stage output pattern (P5)

**Given** the models/anomaly_finding.py module
**When** the AnomalyFinding model is extended
**Then** it has a new optional field: baseline_context: BaselineDeviationContext | None = None
**And** the anomaly_family Literal type includes "BASELINE_DEVIATION"
**And** this is an additive-only change following Procedure A from schema-evolution-strategy.md

**Given** a BASELINE_DEVIATION AnomalyFinding is constructed
**When** severity, is_primary, and proposed_action are set
**Then** severity is LOW, is_primary is False, and proposed_action is NOTIFY (FR16, FR17)
**And** every emitted finding includes sufficient context for offline replay: metric_key, deviation_direction, deviation_magnitude, baseline_value, current_value, correlated_deviations list, time_bucket (NFR-A2)

**Given** existing AnomalyFinding instances for other anomaly families
**When** baseline_context is not provided
**Then** it defaults to None and no existing functionality is affected

**Given** unit tests in tests/unit/baseline/test_models.py
**When** tests are executed
**Then** frozen model immutability, serialization round-trip, and field validation are verified
**And** docs/data-models.md and docs/contracts.md are updated with the new models and additive BASELINE_DEVIATION literal

### Story 2.3: Baseline Deviation Stage - Detection, Correlation & Dedup

As an on-call engineer,
I want the system to detect correlated multi-metric baseline deviations per scope while suppressing single-metric noise and deferring to hand-coded detectors,
So that I only receive findings for genuinely anomalous multi-metric patterns that existing detectors miss.

**Acceptance Criteria:**

**Given** evidence stage output with Prometheus observations for multiple scopes
**When** collect_baseline_deviation_stage_output() runs in pipeline/stages/baseline_deviation.py
**Then** for each scope, it reads the current time bucket baselines from SeasonalBaselineClient
**And** computes modified z-scores for all metrics using the MAD computation engine (FR7)
**And** collects all deviating metrics per scope (FR11)

**Given** a scope with 3 metrics deviating (>= MIN_CORRELATED_DEVIATIONS)
**When** correlation is evaluated (FR12)
**Then** a BASELINE_DEVIATION finding is emitted with all 3 deviating metrics in the correlated context (FR15)
**And** the finding has anomaly_family="BASELINE_DEVIATION", severity=LOW, is_primary=False, proposed_action=NOTIFY

**Given** a scope with only 1 metric deviating (< MIN_CORRELATED_DEVIATIONS)
**When** correlation is evaluated
**Then** no finding is emitted (FR13)
**And** a baseline_deviation_suppressed_single_metric DEBUG log event is emitted with scope, metric, and reason code (NFR-A3)

**Given** a scope where a hand-coded detector (CONSUMER_LAG, VOLUME_DROP, or THROUGHPUT_CONSTRAINED_PROXY) has already fired in the same cycle
**When** baseline deviation evaluation runs for that scope
**Then** no BASELINE_DEVIATION finding is emitted for that exact scope tuple (FR14, D6 exact match)
**And** a baseline_deviation_suppressed_dedup log event is emitted (NFR-A3)

**Given** the stage function signature
**When** collect_baseline_deviation_stage_output() is defined
**Then** all 4 inputs are explicit parameters: evidence_output, peak_output, baseline_client, evaluation_time
**And** no hidden dependencies exist (no wall clock, no global state)
**And** the function is deterministic: same inputs produce same outputs

**Given** a per-scope error during MAD computation or Redis read
**When** the error is caught
**Then** the cycle continues processing remaining scopes (NFR-R1)
**And** the error is logged with scope context

**Given** Redis is unavailable when the stage attempts to read baselines
**When** fail-open is triggered
**Then** the stage skips detection entirely and returns an empty stage output (NFR-R2)
**And** a baseline_deviation_redis_unavailable log event is emitted

**Given** unit tests in tests/unit/pipeline/stages/test_baseline_deviation.py
**When** tests are executed
**Then** all paths are verified: correlated finding emission, single-metric suppression, hand-coded dedup, per-scope error isolation, fail-open, and determinism with injected evaluation_time
**And** docs/architecture.md and docs/architecture-patterns.md are updated with the new stage

### Story 2.4: Pipeline Integration & Scheduler Wiring

As an on-call engineer,
I want baseline deviation findings to flow through topology enrichment, deterministic gating, case file persistence, and Slack dispatch unchanged,
So that I receive complete, routed notifications for anomalies the hand-coded detectors miss.

**Acceptance Criteria:**

**Given** the scheduler pipeline loop in pipeline/scheduler.py
**When** the stage ordering is configured
**Then** baseline deviation stage runs after peak stage and before topology stage
**And** the full ordering is: evidence -> peak -> baseline_deviation -> topology -> casefile -> outbox -> gating -> dispatch

**Given** baseline deviation findings are emitted
**When** they pass through the topology stage
**Then** scope enrichment and ownership routing are applied without any topology stage code modifications (FR18)

**Given** baseline deviation findings enter the gating stage
**When** AG0-AG6 rules are evaluated
**Then** ActionDecisionV1 records are produced identically to other finding types (FR19)
**And** the NOTIFY cap means only AG1 environment cap can lower (never raise) the action
**And** gate decisions are reproducible via reproduce_gate_decision() (NFR-A4)

**Given** baseline deviation findings pass gating with action=NOTIFY or lower
**When** case file and outbox stages process them
**Then** case files are persisted with SHA-256 hash-chain integrity (NFR-A1, FR20)
**And** CaseHeaderEventV1 and TriageExcerptV1 events are published via Kafka outbox
**And** no structural changes to casefile or outbox stages are required

**Given** a baseline deviation finding with action=NOTIFY
**When** the dispatch stage processes it
**Then** a Slack webhook notification is sent (FR21)
**And** no dispatch stage modifications are required

**Given** the baseline deviation layer is disabled via configuration (NFR-R5)
**When** the pipeline runs
**Then** the baseline deviation stage is skipped entirely
**And** all other stages and detectors operate unchanged

**Given** the scheduler startup sequence
**When** SeasonalBaselineClient is constructed
**Then** it is injected into run_baseline_deviation_stage_cycle()
**And** each cycle passes the client, evidence output, peak output, and evaluation time to the stage function
**And** incremental bucket updates (FR3) are performed via update_bucket() after detection completes each cycle
**And** incremental updates add < 5ms per scope to cycle duration (NFR-P6)

**Given** integration tests
**When** the full pipeline path is exercised
**Then** BASELINE_DEVIATION findings are verified end-to-end from emission through topology, gating, casefile, and dispatch
**And** docs/developer-onboarding.md is updated with the new stage in the pipeline flow

---

## Epic 3: LLM-Powered Diagnosis

Each BASELINE_DEVIATION case file receives an asynchronous LLM-generated hypothesis explaining the likely cause of correlated deviations, giving on-call engineers an actionable investigation starting point rather than raw statistical data. Falls back to deterministic diagnosis when LLM is unavailable.

### Story 3.1: BASELINE_DEVIATION LLM Diagnosis Prompt & Processing

As an on-call engineer,
I want each baseline deviation case file to include an LLM-generated hypothesis explaining the likely cause of correlated deviations,
So that I have an actionable investigation starting point rather than raw statistics.

**Acceptance Criteria:**

**Given** a BASELINE_DEVIATION case file arrives in the cold-path consumer
**When** the cold-path processes it
**Then** it invokes LLM diagnosis asynchronously following the existing cold-path pattern (FR25)
**And** follows the D6 invariant: async, advisory, no import path to hot path, no shared state, no conditional wait

**Given** the LLM diagnosis prompt for a BASELINE_DEVIATION case
**When** the prompt is constructed
**Then** it includes all deviating metrics with their: values, deviation directions, magnitudes, and baseline values (FR26)
**And** includes topology context: topic role, routing key
**And** includes the time bucket (day-of-week, hour) for seasonal context

**Given** the LLM returns a diagnosis
**When** the output is formatted
**Then** it is framed as a hypothesis ("possible interpretation") (FR27)
**And** is appended to the case file following existing case file append patterns

**Given** the case file with LLM diagnosis appended
**When** hash-chain integrity is verified
**Then** triage_hash correctly links triage to diagnosis (NFR-A1)
**And** the DiagnosisReportV1 record is valid and complete

**Given** unit tests
**When** tests are executed
**Then** prompt construction is verified to include all required deviation context fields
**And** hypothesis framing is verified in the output format

### Story 3.2: Deterministic Fallback Diagnosis

As an on-call engineer,
I want a deterministic fallback diagnosis when LLM is unavailable,
So that case file completeness and hash-chain integrity are preserved regardless of LLM availability.

**Acceptance Criteria:**

**Given** an LLM invocation fails (timeout, error, service unavailable)
**When** the cold-path processes the BASELINE_DEVIATION case
**Then** it falls back to deterministic fallback diagnosis (FR28)
**And** the fallback produces a valid DiagnosisReportV1 that preserves hash-chain integrity

**Given** the fallback diagnosis path
**When** it generates a diagnosis for a BASELINE_DEVIATION case
**Then** it follows the identical fallback pattern used for existing anomaly families (CONSUMER_LAG, VOLUME_DROP, THROUGHPUT_CONSTRAINED_PROXY)
**And** the case file remains complete and structurally valid

**Given** LLM failure occurs
**When** the fallback is triggered
**Then** no import path to the hot path exists (D6 invariant)
**And** no shared state is accessed
**And** no conditional wait occurs

**Given** unit tests
**When** tests are executed
**Then** fallback diagnosis is verified for LLM timeout, error, and unavailability scenarios
**And** hash-chain integrity is verified on the fallback path

---

## Epic 4: Operational Observability & Health

SREs can monitor baseline deviation stage health and effectiveness through OTLP metrics (deviations detected, findings emitted/suppressed, computation latency), structured log events (stage lifecycle, suppression reasons, recomputation status), and the HealthRegistry — enabling data-driven tuning decisions and operational confidence.

### Story 4.1: OTLP Counters & Histograms

As an SRE,
I want OTLP counters and histograms tracking baseline deviation detection effectiveness and performance,
So that I can monitor detection rates, suppression ratios, and computation latency in Dynatrace.

**Acceptance Criteria:**

**Given** the baseline deviation stage runs a cycle
**When** deviations are detected
**Then** the counter aiops.baseline_deviation.deviations_detected is incremented by the number of deviations found (FR29)

**Given** findings are emitted or suppressed during a cycle
**When** the stage completes
**Then** aiops.baseline_deviation.findings_emitted is incremented for each emitted finding (FR29)
**And** aiops.baseline_deviation.suppressed_single_metric is incremented for each single-metric suppression (FR29)
**And** aiops.baseline_deviation.suppressed_dedup is incremented for each hand-coded dedup suppression (FR29)

**Given** the stage execution is timed
**When** the stage completes
**Then** aiops.baseline_deviation.stage_duration_seconds histogram records the total stage duration (FR30)
**And** aiops.baseline_deviation.mad_computation_seconds histogram records per-scope MAD computation time (FR30)

**Given** the OTLP instruments are created
**When** they are initialized
**Then** they use the existing create_counter and create_histogram shared helpers
**And** follow the aiops.baseline_deviation. naming prefix (P7)

**Given** unit tests
**When** tests are executed
**Then** counter increments and histogram recordings are verified with mock OTLP instruments
**And** instrument names match the P7 naming convention exactly

### Story 4.2: Structured Logging & Health Registration

As an SRE,
I want structured log events for the baseline deviation stage lifecycle and HealthRegistry integration,
So that I can troubleshoot issues, trace suppression decisions, and verify system health via the health endpoint.

**Acceptance Criteria:**

**Given** the baseline deviation stage starts execution
**When** the stage begins
**Then** a baseline_deviation_stage_started structured log event is emitted (FR31)

**Given** the stage completes
**When** results are available
**Then** a baseline_deviation_stage_completed log event is emitted with scopes_evaluated and findings count (FR31)

**Given** a finding is emitted
**When** the finding passes correlation and dedup checks
**Then** a baseline_deviation_finding_emitted log event is emitted with scope and metric context (FR31)

**Given** suppression occurs
**When** a single-metric deviation is suppressed
**Then** a baseline_deviation_suppressed_single_metric DEBUG log is emitted with scope, metric, reason code, and cycle timestamp (NFR-A3)
**And** when a hand-coded dedup suppression occurs
**Then** a baseline_deviation_suppressed_dedup log is emitted with scope, metric, reason code, and cycle timestamp (NFR-A3)

**Given** Redis is unavailable during stage execution
**When** fail-open is triggered
**Then** a baseline_deviation_redis_unavailable log event is emitted (FR31)

**Given** the HealthRegistry
**When** baseline deviation stage health is registered (FR32)
**Then** it reports healthy/degraded status through the existing health endpoint
**And** Redis unavailability triggers a degraded health event (NFR-R2)

**Given** all structured log events
**When** they are emitted
**Then** they use the baseline_deviation_ prefix (P6)
**And** include correlation context via structlog bindings
**And** all 10 event types defined in P6 are implemented

**Given** unit tests
**When** tests are executed
**Then** all log event emissions are verified with captured log output
**And** HealthRegistry integration is verified
**And** docs/component-inventory.md is updated with the HealthRegistry component entry
