
### Requirement 1: Fully wire the reddis cache layeer

## Current 
Three Redis cache modules exist in cache/. Only findings_cache is integrated. The other two (evidence_window, peak_cache) are fully implemented and tested but never called from production code.

## Change

Wire sustained window state persistence — The scheduler should load prior streak state from Redis via load_sustained_window_states before running the peak stage, and persist results via persist_sustained_window_states after. Currently prior_sustained_window_state_by_key is always None, making sustained anomaly detection inert.
Wire peak profile caching — The pipeline should use get_or_compute_peak_profile from peak_cache.py to cache/retrieve peak profiles instead of recomputing from scratch every run. Currently historical_windows_by_scope={} is hardcoded empty.
Batch Redis operations — load_sustained_window_states issues one Redis GET per key sequentially. At scale this becomes a bottleneck. Switch to Redis pipeline or MGET for bulk operations.


### Requirement 2: DSL-Driven Rulebook Gate Engine — Change Proposal

## Current
The gating module (pipeline/stages/gating.py) evaluates 7 sequential gates (AG0–AG6) that determine operational actions (OBSERVE, NOTIFY, TICKET, PAGE) for detected anomalies. Actions can only be capped downward, never escalated.

The YAML rulebook (config/policies/rulebook-v1.yaml) defines gate structure — checks, effects, thresholds, and applies_when predicates. However, the Python code re-implements each gate's logic as hard-coded if gate_id == "AGx" branches. The YAML and Python contain parallel implementations that can silently drift.

Developers may change YAML thresholds or predicates believing the change is live, when Python ignores those fields entirely. Specifically: applies_when predicates are decorative and never evaluated. AG0, AG2, AG3, AG6 check logic is fully hard-coded — YAML check definitions are documentation only. AG1 reads thresholds from YAML but skip conditions and flag logic live in Python. Only AG4 is semi-dynamic, already dispatching by check.type for min_value and equals.

Two things are already generic: _apply_gate_effect() applies any GateEffect to state without knowing which gate called it, and GateCheck uses Pydantic extra="allow" for dynamic field storage.

Constraints that must be preserved: Determinism (same inputs + same policy = same outputs, with 25-month CaseFile audit replay). Safety (PAGE must be structurally impossible outside PROD+TIER_0, monotonic reduction only). Auditability (every gate decision traceable with reason codes). Performance (gate evaluation p99 ≤ 500ms). No parallel evaluators (single centralized evaluation path).

## Change
Make the YAML rulebook the authoritative execution specification. Gate evaluation should be driven by YAML-defined check types and predicates, dispatched through a handler registry, rather than hard-coded per-gate Python branches.

Each YAML check.type (e.g., min_value, required_evidence_present, dedupe_check) maps to a registered handler function. applies_when YAML predicates become executable using structured YAML (not string expressions). Adding a new gate that uses existing check types requires only YAML changes. Adding a new check type requires one new handler function plus a YAML definition. Post-condition safety assertions provide defense-in-depth independent of YAML correctness.

What does NOT change: GateInputV1 input contract, ActionDecisionV1 output contract, evaluate_rulebook_gates() public function signature, gate-input assembly (collect_gate_inputs_by_scope), _apply_gate_effect(), monotonic action reduction mechanics, and all downstream consumers (dispatch, outbox, CaseFile assembly).

## Scope
In Scope
Evaluation engine refactor. Replace the if gate_id == dispatch chain in evaluate_rulebook_gates() with a generic loop: evaluate predicates, dispatch checks by type, select effect outcome. Extract 9 check-type handlers from existing private functions and inline logic. Define the handler protocol (context with input + state + rulebook + dedupe store, returning outcome + reason codes). Define effect outcome mapping so handler outcomes (PASS, FAIL, CAP_APPLIED, DUPLICATE, STORE_ERROR) select the correct GateEffects attribute.

Predicate evaluator. Make applies_when YAML predicates executable using structured YAML, not string expressions. Required predicate types: field equality, field membership, numeric comparison, current action priority check, state field check, and always. Migrate applies_when from decorative strings to structured evaluable format. Add applies_when as a typed field on the GateSpec contract (currently in untyped model_extra).

Safety layer. Post-condition safety assertions after the evaluation loop: PAGE requires PROD+TIER_0, invalid input requires OBSERVE. Handler registry immutability (frozen at import time). Handler exhaustiveness validation (every YAML check.type must have a registered handler).

Regression validation. All existing 36 test functions (60+ parametrized cases) must pass with zero modifications. Audit replay reproducibility must produce identical output for pre-migration CaseFiles. Performance must stay within the p99 ≤ 500ms budget.

## Out of Scope
Changes to GateInputV1 or ActionDecisionV1 contracts. Changes to gate-input assembly. Changes to downstream consumers (dispatch, outbox, CaseFile). New gates or new check types beyond the current AG0–AG6 set. Runtime/dynamic rule loading (handlers are code, not plugins). Changes to YAML rulebook thresholds or policy values. Integration tests requiring Docker infrastructure changes.

## Key Risks
AG1's multi-step cap logic is uniquely complex — env cap, then conditional tier cap, plus the env_cap_applied flag and on_cap_applied effect. Incorrect extraction breaks PROD tier gating. Mitigated by dedicated handler with explicit multi-outcome return, validated by existing AG1 test matrix (7 parametrized cases).

AG5 requires external I/O (Redis dedupe) which can't be expressed as pure predicates. Mitigated by the handler protocol supporting dependency injection via the check context; the AG5 handler remains procedural with try/except.

Safety invariants shift from structural (visible in code) to behavioral (YAML + engine correctness). Mitigated by post-condition safety assertions that catch violations regardless of YAML content.

25-month CaseFile replay with the new engine must produce byte-identical output for historical inputs. Mitigated by one-time regression validation against existing test vectors.

## Dependencies
GateCheck already uses extra="allow" for dynamic fields. _apply_gate_effect() is already generic and works for any gate. The 973-line test suite exercises the public API and serves as the regression safety net. reproduce_gate_decision() in audit/replay.py validates determinism end-to-end.


# Requirement 3: Unified Per-Scope Metric Baselines

## Current

- Anomaly detectors use 9 hardcoded absolute thresholds (`anomaly.py:20-28`) applied uniformly to all scopes.
- Peak stage accepts `historical_windows_by_scope` but scheduler always passes `{}` (`__main__.py:282`), making peak classification permanently UNKNOWN for every scope.
- `peak_cache.py` is fully implemented but never wired into the scheduler.
- AG6 (postmortem selector) is implemented but never fires because `peak` is always False.

## Change

Replace both with a unified baseline collection: `Mapping[scope, Mapping[metric_key, Sequence[float]]]`.

- Background job computes historical values for all metrics across all scopes, stored in Redis.
- Both peak and anomaly stages consume from the same store.
- New `anomaly-detection-policy-v1.yaml` defines per-detector sensitivity. Current hardcoded values become cold-start fallbacks.
- Wire existing `peak_cache.py` into scheduler rather than building parallel cache.

## Scope

## In scope

- New runtime mode or scheduling mechanism for baseline computation job.
- New anomaly detection policy contract supporting **both** absolute floors and percentile-relative thresholds (not all constants are percentile-compatible — ratios and upper bounds remain absolute).
- Redis baseline store with env-specific TTLs, integrated with existing `peak_cache.py`.
- Refactor peak stage to read from unified baselines instead of `{}`.
- Refactor anomaly detectors to read per-scope thresholds, falling back to constants when history is insufficient.
- Scope key normalization: consumer lag uses 4-tuple `(env, cluster, group, topic)`, everything else uses 3-tuple. Baseline store must define canonical key shape and lookup strategy.
- Volume drop detector: preserve intra-sample comparison logic (`anomaly.py:218-219`); only replace absolute floor thresholds from baselines.

## Out of scope

- Detection logic structure, `AnomalyFinding` contract, gate evaluation code (AG0–AG6), casefile assembly, outbox, dispatch, topology.

## Expected behavioral effects

- AG6 activates for PROD+TIER_0 during peak windows (completing dormant implementation).
- Sustained streaks may shift as per-scope thresholds produce different finding sets.
- Peak classifications go from always-UNKNOWN to real PEAK/NEAR_PEAK/OFF_PEAK states.


# Requirement 5: Sharded Findings Cache Coordination for Hot/Hot Kubernetes Deployment

## Current

- Single-process hot-path assumes exclusive ownership of all scopes per cycle.
- Findings cache (`findings_cache.py`) provides per-scope-per-interval idempotency via Redis read-through, but was designed for single-writer crash recovery — not multi-writer coordination.
- No lease, partition assignment, or scope sharding mechanism exists.
- Overlap between two instances produces duplicate findings computation and duplicate downstream side effects (casefile writes, outbox inserts, dispatch actions).
- AG5 dedupe (`RedisActionDedupeStore`) partially mitigates duplicate dispatch but is a storm-control gate, not a coordination primitive.

## Change

Introduce scope-level shard assignment and coordination so multiple hot-path pods can run concurrently in a hot/hot Kubernetes deployment without duplicating work or producing conflicting side effects.

- Define a shard assignment strategy: scope partitioning (e.g., consistent hash of scope key to pod) or leader-elected range assignment.
- Replace per-scope findings cache writes with a batch checkpoint per shard per interval — O(1) write per shard instead of O(N) per scope.
- Add distributed lease or fence mechanism so that if a pod dies mid-cycle, another pod can safely resume its shard after lease expiry.
- Ensure casefile persistence and outbox insertion remain exactly-once per scope per interval across pods (current write-once semantics in `casefile_io.py` help but don't cover the full path).

## Scope

## In scope

- Shard assignment strategy and pod-to-scope mapping.
- Checkpoint primitive replacing per-scope findings cache for sharded execution.
- Lease/fence mechanism for mid-cycle failover between pods.
- Audit of downstream side effects (casefile write-once, outbox insert, PagerDuty/Slack dispatch) for multi-writer safety.
- Redis key namespace design that supports sharded access without cross-pod contention.

## Out of scope

- Anomaly detection logic, gate evaluation, casefile contract — unchanged.
- Requirement 3 (unified baselines) — independent; either can land first.
- Cold-path, outbox-publisher, casefile-lifecycle modes — single-instance for now.

## Dependencies

- Kubernetes deployment manifests and pod scaling configuration.
- Redis cluster topology (single instance vs Redis Cluster) decision.
- Requirement 3 baseline store design should account for sharded readers but is not blocked by this.


### Requirement 6: Distributed Hot/Hot Phase 1 — Multi-Replica Safety
## Current
The application assumes single-instance execution for each runtime mode. Running multiple replicas causes:

Duplicate processing — Multiple hot-path instances query the same Prometheus scopes on the same interval, producing duplicate findings, duplicate CaseFiles (handled by S3 put_if_absent), duplicate PagerDuty pages, and duplicate Slack notifications (not handled).
Divergent sustained-window state — Each instance maintains an independent in-process Python dict for sustained-window progression. Instance A may evaluate sustained=True while Instance B evaluates sustained=False for the same anomaly key, causing inconsistent AG4/AG6 gate decisions.
AG5 dedupe race condition — Two-step is_duplicate() then remember() has a race window where both instances pass the duplicate check before either writes. The SET NX return value from remember() is discarded, so both proceed to dispatch.
Duplicate outbox publishing — select_publishable() uses plain SELECT without row locking. Multiple outbox-publisher instances select and publish the same batch, causing duplicate Kafka messages.
Indistinguishable observability — OTLP metrics and structured logs carry no pod identity. Per-instance latency, throughput, and error visibility is lost when aggregated.
Requested Change
Enable the application to run as multiple concurrent replicas (hot/hot) in Kubernetes without duplicate processing, divergent decisions, or duplicate external side effects. Strategy: distributed cycle locking — all pods run the same loop, one wins execution per interval. Losers yield and retry next interval.

## Change

Distributed cycle lock — Only one hot-path pod executes per scheduler interval. Resolves duplicate processing and duplicate dispatches. Fail-open on Redis unavailability (preserves availability, worst case equals current single-instance behavior). Feature-flagged for backward-compatible rollout.

Externalized sustained-window state — Move sustained-window progression from in-process dict to Redis so all instances share a single consistent view. Resolves divergent AG4/AG6 gate decisions. Falls back to None on Redis failure (conservative — treats as first observation, no false sustained=True).

Atomic AG5 dedupe — Replace two-step is_duplicate() + remember() with single atomic remember() using existing SET NX EX return value as authoritative duplicate check. Resolves the race window.

Outbox publisher row locking — Prevent concurrent outbox-publisher instances from selecting the same batch. Resolves duplicate Kafka event publication.

Pod identity in observability — Add pod name/namespace to OTLP resource attributes and structlog context. Resolves indistinguishable metrics and logs across replicas.

Coordination operational metrics — Counters for cycle lock acquired/yielded/failed and sustained-state Redis hit/miss for operational visibility into the new coordination layer.

## Scope
Functional requirements served:

Hot-path duplicate suppression across replicas
Sustained-window state consistency across replicas
AG5 dedupe correctness under concurrency
Outbox publisher at-least-once without duplication across replicas
Per-pod observability attribution

## Code surface:

coordination/ — new package (cycle lock protocol + Redis implementation)
cache/sustained_state.py — new module (Redis-backed sustained window state)
__main__.py — cycle lock gate in scheduler loop, Redis sustained state read/write replacing local dict
pipeline/stages/gating.py — AG5 atomic dedupe (single-step replace of two-step pattern)
outbox/repository.py — row locking on select_publishable()
outbox/schema.py + outbox/state_machine.py — if CLAIMED status approach chosen
config/settings.py — new fields (POD_NAME, POD_NAMESPACE, feature flag, lock margin)
health/otlp.py — pod identity in OTLP resource attributes
health/metrics.py — coordination counters
logging/setup.py — pod_name in structlog context
config/.env.* — new env vars

## Invariants preserved (no changes needed):

Outbox durability (Invariant B2) — cycle lock gates whether cycle runs, not internal write semantics
Write-once CaseFile (S3 put_if_absent) — already multi-instance safe
AG0-AG6 gate determinism — pure-functional given same GateInputV1; only AG5 interaction changes
Outbox state machine source-state guards — all transitions remain guarded
Schema envelope versioning — no contract or schema changes
Redis findings cache — deterministic computation + last-writer-wins already correct
Topology registry — threading.Lock already guards snapshot swap

## Out of scope (Phase 2+):

Scope-based partitioning / consistent hashing for horizontal throughput scaling
Cold-path distributed coordination (cold-path is still a stub)
Cross-pod HealthRegistry synchronization (pod-local is correct for K8s probes)
Casefile lifecycle runner coordination (S3 delete is idempotent)
Outbox worker SLO sample aggregation across pods (observability gap, not correctness)

## Operational impact:

New Redis dependency for cycle lock and sustained state (Redis already required for AG5 dedupe and findings cache)
Feature flag DISTRIBUTED_CYCLE_LOCK_ENABLED (default false) enables incremental rollout: deploy at 1 replica first, verify, then scale


### Requirement 7: Evidence Summary Builder
## Current
The cold-path diagnosis chain accepts an evidence_summary: str parameter at every layer — from spawn through LLM prompt injection. No function exists to produce this string. The data it would summarize (metric values, evidence statuses, anomaly findings, temporal context) is already persisted in CaseFileTriageV1 by the hot path. The entire diagnosis infrastructure (LangGraph graph, prompt builder, LLM client, fallback reports, hash chain, write-once persistence) is built and tested but cannot operate without this input.

## Change
Provide a deterministic text rendering of a case's evidence state suitable for LLM consumption. The rendering must faithfully represent what is known (PRESENT metrics with values), what is missing (UNKNOWN/ABSENT/STALE and why), what anomalies were detected (findings with IDs), and the temporal context (sustained, peak, degraded telemetry). Output must be stable for identical input and compatible with the existing prompt's evidence citation rules — the LLM is instructed to cite only PRESENT evidence and propagate UNKNOWN, so the summary must make that distinction unambiguous.

## Scope
In: Builder function, unit tests across evidence status variants and metric families.
Out: No changes to the existing diagnosis chain, prompt template, or denylist enforcement — all already accept the string. Prompt quality improvements (verdict vocabulary, confidence criteria, few-shot examples) are a separate concern.
Depends on: Nothing. Depended on by: CR-02.
Refs: FR65, NFR-S8, _SYSTEM_INSTRUCTION evidence citation rules in prompt.py.

### Requirement 8: Cold-Path Kafka Consumer Pod
## Current
The cold-path runtime mode (--mode cold-path) is a stub that logs a warning and exits. The existing in-process design (spawn_cold_path_diagnosis_task) assumes diagnosis runs as a fire-and-forget asyncio task inside the hot-path process. This conflicts with the upcoming K8s pod split where hot path and cold path run as independent deployments. The hot path already publishes CaseHeaderEventV1 to Kafka and persists triage.json to S3 before publish (Invariant A), so everything the cold path needs is already available.

## Change
Implement the cold-path as an independent Kafka consumer that reacts to case header events. The consumer determines eligibility (production, highest criticality, sustained anomaly), retrieves the full case context from object storage (guaranteed to exist by Invariant A), reconstructs the triage excerpt and evidence summary (CR-01) from persisted data, and delegates to the existing run_cold_path_diagnosis() for LLM invocation and diagnosis.json persistence. This avoids wiring TriageExcerptV1 Kafka publishing in the outbox — one S3 read per eligible case is acceptable since the cold path already writes to S3 and is not latency-critical.

## Scope
In: Kafka consumer loop, triage excerpt reconstruction from persisted casefile, wiring _run_cold_path() into a real consumer, integration tests in MOCK mode, graceful shutdown.
Out: No changes to run_cold_path_diagnosis() or the diagnosis chain. No outbox publisher changes. No hot-path modifications. The in-process spawn_cold_path_diagnosis_task is retained for testing but not used by this consumer.
Depends on: CR-01.
Refs: FR24 (hot-path consumer independence — this is cold-path, not constrained), FR22 (CaseHeaderEventV1 publish), Invariant A (triage.json exists before header on Kafka), architecture decision 4B (cold-path orchestration), runtime-modes.md.

### Requirement 8: Remove PROD/TIER_0/Sustained Invocation Criteria for Cold-Path LLM Diagnosis

## Current
Cold-path LLM diagnosis is gated by meets_invocation_criteria() requiring ALL three conditions:

Environment = PROD
Criticality tier = TIER_0
Sustained = true
All other cases are silently skipped — no diagnosis task, no diagnosis.json.

Requested Change
Remove all invocation criteria. LLM diagnosis runs for every case regardless of environment, tier, or sustained status.

## Scope
Functional requirements affected:

FR42 — currently mandates conditional invocation (PROD/TIER_0/sustained). Must be updated to unconditional invocation.
Story 6.2 AC7 — "cases not meeting criteria skip entirely" — voided.

## Code surface:

diagnosis/graph.py — meets_invocation_criteria() function and its usage in spawn_cold_path_diagnosis_task()
tests/unit/diagnosis/test_graph.py — criteria tests and all spawn_cold_path_diagnosis_task() call sites
Safety boundaries unchanged (no changes needed):

INTEGRATION_MODE_LLM (OFF/LOG/MOCK/LIVE) already controls whether real LLM calls happen per environment
Prod enforcement in settings.py rejects MOCK/OFF in prod
60s timeout (NFR-P4) still applies
Fire-and-forget pattern preserved — hot-path never blocked
Denylist enforcement (NFR-S8) still applied before LLM input


### Requirement 9: Optimize Cold-Path LLM Diagnosis Prompt for Higher Quality Output
## Current
The LLM prompt in diagnosis/prompt.py was built as a minimum viable implementation in Story 6.3. It provides:

A system instruction requiring JSON-only output matching DiagnosisReportV1 schema
Anti-fabrication and UNKNOWN propagation rules
Evidence citation rules mapping to EvidencePack fields
Case context with 8 of 13 available TriageExcerptV1 fields
Findings rendered with only 3 of 7 available Finding fields (finding_id, name, is_anomalous)
Raw evidence_status_map key-value pairs without semantic context
No domain knowledge, no confidence calibration, no fault domain guidance, no examples
Requested Change
Enrich the prompt to maximize diagnostic quality by exposing all available structured data and providing domain guidance, without changing contracts, output schema, or the cold-path architecture.

## Change (validated against architecture — no conflicts):

Render full Finding fields — Include severity, reason_codes, evidence_required, and is_primary alongside the existing three fields. These are the most diagnostic-relevant data in the input; without them the LLM reasons with incomplete evidence context.

Include topic_role and routing_key in case context — Both are first-class TriageExcerptV1 fields omitted from the original template. topic_role (SOURCE_TOPIC/SHARED_TOPIC/SINK_TOPIC) determines blast radius interpretation and fault domain reasoning. routing_key provides team ownership context relevant to fault domain identification.

Add anomaly family domain descriptions — The prompt passes anomaly_family: CONSUMER_LAG as a raw string. The LLM needs concise definitions of what each family detects operationally (lag buildup, volume drop, throughput constraint) to produce domain-specific diagnoses rather than generic verdicts. Keep descriptions brief to respect FR42 token budget.

Add generic confidence calibration guidance — The prompt provides no criteria for choosing LOW/MEDIUM/HIGH. Provide calibration: LOW = evidence gaps or contradictions, MEDIUM = partial evidence consistent with hypothesis, HIGH = all required evidence PRESENT and consistent. Must NOT reference rulebook gate thresholds (AG2/AG4) — DiagnosisReportV1.confidence is LLM-domain only, separate from the gate engine per architectural decision.

Add fault domain guidance with examples — fault_domain is intentionally free-text (str | None) but the prompt gives zero guidance, leading to inconsistent values across invocations. Provide example domains tied to the Kafka pipeline topology (e.g., consumer-group, topic-partition, broker, upstream-producer, network) without constraining to a closed set.

Add a concise reasoning hint — Instruct the LLM to internally verify evidence consistency before generating JSON (which evidence is PRESENT vs UNKNOWN, whether findings align with anomaly_family, most likely fault domain). This guides reasoning quality without changing the JSON-only output format.

Add a single few-shot example — One concise example of a well-formed DiagnosisReportV1 for a CONSUMER_LAG case to anchor output format, verdict style, and evidence citation patterns. Keep minimal to respect FR42 token budget.

## Scope
Functional requirements served:

FR37 — structured DiagnosisReport quality (verdict, fault_domain, confidence, evidence_pack, next_checks, gaps)
FR38 — evidence citation and UNKNOWN propagation (improvements 1, 6 strengthen this)
FR42 — token budget constraint applies to all additions (keep concise)
Code surface:

diagnosis/prompt.py — _SYSTEM_INSTRUCTION constant and build_llm_prompt() function
tests/unit/diagnosis/test_prompt.py — new/updated assertions for added prompt content

## unchanged (no changes needed):

DiagnosisReportV1 contract — output schema is frozen
TriageExcerptV1 contract — input schema is frozen (we're reading more fields, not changing the contract)
diagnosis/graph.py — invocation flow, denylist enforcement, fallback logic, hash chain all unchanged
integrations/llm.py — LLM client, LIVE mode HTTP call unchanged
Hot-path stages — no imports or modifications


### Requirement 10: Redis Bulk Load and Peak Stage Memory Efficiency
## Current
Three performance bottlenecks exist that are negligible at current scale but will degrade as scope count grows:

Sequential Redis key loading — evidence_window.py:100 loads sustained-window keys one at a time in a loop. Each key is a separate Redis round-trip. At 750k keys this becomes 750k sequential network calls, dominated by network latency rather than Redis processing time.

Single-threaded sustained status computation — compute_sustained_status_by_key in peak.py:179 iterates all keys sequentially. Pure CPU with no I/O, but not parallelized. Acceptable today but linear scaling wall as scope count grows.

Peak profile historical windows memory — historical_windows_by_scope stores full history arrays per scope (not single counters). This is the heavier memory concern — memory grows proportionally with scope count multiplied by history window depth.

## Change
Optimize the three bottlenecks to support higher scope counts without architectural changes.

Batch Redis key loading — Replace sequential per-key Redis round-trips with batched MGET or Redis pipeline in evidence_window.py:100 bulk_load path. Reduces 750k round-trips to a small number of batched calls.

Parallel sustained status computation — Parallelize the compute_sustained_status_by_key loop in peak.py:179 for CPU-bound sustained status evaluation across large key sets.

Peak profile memory efficiency — Reduce memory footprint of historical_windows_by_scope which stores full history arrays per scope. Evaluate whether rolling aggregation or bounded window depth can replace full history retention.

## Scope
Code surface:

cache/evidence_window.py — bulk_load method (sequential → batched Redis calls)
pipeline/stages/peak.py — compute_sustained_status_by_key loop parallelization
pipeline/stages/peak.py — historical_windows_by_scope data structure / retention strategy
Boundaries unchanged:

No contract or schema changes
No changes to sustained-window semantics or peak classification logic
No changes to Redis key format or TTL policy
Hot-path stage ordering and scheduler cadence unchanged

## Operational impact:

Reduced Redis connection pressure under high scope counts
Reduced hot-path cycle latency at scale (bulk load is the primary bottleneck)
Reduced per-process memory footprint for peak stage history


### Requirement 11: Topology Registry: Simplify to Single Format
## Current
The topology registry supports two YAML formats — a legacy flat format (no cluster awareness, no scoped ownership routing, global topic index) and an instances-based format (multi-cluster deployments, per-instance topic index, ownership routing with confidence scoring). The system auto-detects which format is provided, parses both through separate code paths, and produces a shared canonical model. A compatibility view API exists to project canonical state back into the legacy shape for hypothetical downstream consumers. Contract and policy configuration carry version-negotiation fields to govern this dual-format behavior. The topology registry YAML file is currently referenced from _bmad/input/feed-pack/ rather than config/, which is inconsistent with how all other policy and configuration YAML files are loaded in this project.

## Change
This project is greenfield with no production consumers of the legacy format. All multi-version support is unnecessary complexity. The instances-based format must become the sole supported topology registry format. All legacy format support, version negotiation, and backward-compatibility projection capabilities must be removed. The canonical in-memory model that downstream pipeline stages consume remains unchanged. The topology registry YAML file must live in config/ alongside other policy and configuration files, consistent with the project's established configuration layout.

## Scope
Must be removed

Legacy flat-format parsing capability
Format auto-detection and version negotiation logic
Backward-compatibility projection API (v0 compat view and its supporting types/errors)
Synthetic default env/cluster_id injection (exists only because the legacy format lacks cluster awareness)
Version-negotiation fields from the loader rules contract and its policy configuration
Input version tracking in loader metadata (single format, no ambiguity)
All test coverage for legacy loading, format equivalence, and compatibility projection
Must be added or moved

The topology registry YAML file must be placed in config/ consistent with other configuration files (policies, denylist, environment configs)
TOPOLOGY_REGISTRY_PATH default and Docker env references must point to the config/ location

## Must remain unchanged

Canonical in-memory model (streams, instances, topic index, ownership structures)
Registry resolver and all topology resolution behavior
Pipeline topology stage
Hot-path registry loading and reload-on-change behavior
All resolver and downstream pipeline tests