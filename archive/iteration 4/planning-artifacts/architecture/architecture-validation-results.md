# Architecture Validation Results

## Coherence Validation

**Decision Compatibility:** PASS
- All 6 decisions (D1-D6) are mutually compatible with no contradictions
- D1 (flat keys) ↔ D3 (client class): client encapsulates key formatting internally
- D2 (single stage function) ↔ D6 (exact scope dedup): dedup is an internal predicate within the stage
- D4 (async recompute with bulk write) ↔ D1 (flat keys): bulk write via pipelined SET is natural for flat keys
- D5 (extend backfill) ↔ D3 (client.seed_from_history): backfill feeds data to client method

**Pattern Consistency:** PASS
- All 7 patterns (P1-P7) align with architectural decisions
- P2 constants module feeds into D2 stage function and D3 client methods
- P3 time_to_bucket is the single source of truth used by D2, D4, and D5
- P4 model shape supports D6 dedup (scope tuple matching) and existing contract passthrough
- P6/P7 naming conventions follow existing project patterns

**Structure Alignment:** PASS
- New `baseline/` package cleanly separates domain from pipeline orchestration
- Stage file in `pipeline/stages/` follows existing stage module conventions
- Test structure mirrors source structure per project-context.md rules
- All boundaries (data access, computation, stage, contract) are respected by file layout

## Requirements Coverage Validation

**Functional Requirements Coverage: 32/32**

| FR | Description | Architectural Support |
|---|---|---|
| FR1 | Store baselines in 168 time buckets | D1 key schema, D3 SeasonalBaselineClient |
| FR2 | Seed from 30-day Prometheus history | D5 backfill extension |
| FR3 | Update current bucket per cycle | D3 client.update_bucket() |
| FR4 | Weekly recompute from Prometheus | D4 background async with bulk write |
| FR5 | Cap at 12 weeks per bucket | P2 MAX_BUCKET_VALUES constant |
| FR6 | Skip if < minimum samples | P2 MIN_BUCKET_SAMPLES, baseline/computation.py |
| FR7 | MAD computation per scope/metric/bucket | baseline/computation.py |
| FR8 | Classify deviation by threshold | P2 MAD_THRESHOLD |
| FR9 | Deviation direction (HIGH/LOW) | P4 BaselineDeviationContext.deviation_direction |
| FR10 | Record magnitude, baseline, current value | P4 BaselineDeviationContext fields |
| FR11 | Collect deviations per scope | baseline_deviation.py stage logic |
| FR12 | Emit only when >= correlated threshold | P2 MIN_CORRELATED_DEVIATIONS |
| FR13 | Suppress single-metric at DEBUG | P6 baseline_deviation_suppressed_single_metric |
| FR14 | Dedup with hand-coded detectors | D6 exact scope tuple match |
| FR15 | Include correlated deviations list | P4 finding structure (tuple of findings with context) |
| FR16 | BASELINE_DEVIATION family, LOW, is_primary=False | P4 model, stage emission logic |
| FR17 | proposed_action=NOTIFY at source | Stage sets NOTIFY unconditionally |
| FR18 | Topology passthrough | Existing topology stage — no modifications |
| FR19 | Gating passthrough (AG0-AG6) | Existing gate framework — no modifications |
| FR20 | Casefile passthrough | Existing casefile stage — no modifications |
| FR21 | Dispatch NOTIFY via Slack | Existing dispatch stage — no modifications |
| FR22 | Discover metrics from contract YAML | Existing PrometheusMetricsContractV1, D3 client |
| FR23 | Backfill new metrics on startup | D5 backfill extension |
| FR24 | Baseline across all discovered scopes | Evidence stage scope discovery, D3 client |
| FR25 | Cold-path processes BASELINE_DEVIATION | Existing cold-path consumer — no new files |
| FR26 | LLM prompt includes deviation context | P4 BaselineDeviationContext in TriageExcerptV1 |
| FR27 | Hypothesis-framed LLM output | Existing diagnosis prompt framework |
| FR28 | Fallback diagnosis on LLM failure | Existing fallback path — no modifications |
| FR29 | OTLP counters | P7 aiops.baseline_deviation.* counters |
| FR30 | OTLP histograms | P7 aiops.baseline_deviation.* histograms |
| FR31 | Structured log events | P6 baseline_deviation_* event names |
| FR32 | HealthRegistry integration | Existing health framework |

**Non-Functional Requirements Coverage: 17/17**

| NFR | Description | Architectural Support |
|---|---|---|
| NFR-P1 | 40s stage budget | D2 single stage function, measurable via P7 stage_duration_seconds |
| NFR-P2 | 50ms Redis batch reads | D1 mget batching by scope |
| NFR-P3 | 1ms MAD computation | Pure function in baseline/computation.py |
| NFR-P4 | 10-min backfill | D5 extends existing backfill |
| NFR-P5 | 10-min recompute | D4 background async, non-blocking |
| NFR-P6 | 5ms incremental update | D3 client.update_bucket() single SET |
| NFR-S1 | 200MB Redis at 3x | D1 flat keys, estimated 75-150MB at 1x |
| NFR-S2 | Linear scaling with scopes | D2 per-scope processing loop |
| NFR-S3 | Zero-code new metrics | FR22-24 contract-driven discovery |
| NFR-S4 | mget at 3x scale | D1 batching, constrained by NFR-P2 |
| NFR-R1 | Per-scope error isolation | Stage try/catch per scope, continues on error |
| NFR-R2 | Fail-open on Redis unavailable | D3 client fail-open, P6 redis_unavailable event |
| NFR-R3 | MIN_BUCKET_SAMPLES guard | P2 constant, computation.py check |
| NFR-R4 | Atomic recompute | D4 in-memory build + bulk write |
| NFR-R5 | Independently disableable | BASELINE_DEVIATION_ENABLED setting (Gap 1 resolved) |
| NFR-A1 | Hash-chain integrity | Existing casefile framework — no modifications |
| NFR-A2 | Full context for replay | P4 BaselineDeviationContext captures all fields |
| NFR-A3 | Suppression traceability | P6 structured log events with scope/metric/reason |
| NFR-A4 | Reproducible gate decisions | Existing reproduce_gate_decision() — no modifications |

## Implementation Readiness Validation

**Decision Completeness:** PASS
- 6 decisions documented with rationale, affected components, and trade-off analysis
- All decisions include concrete interface patterns (function signatures, class interfaces, key formats)
- Implementation sequence and cross-component dependencies mapped

**Structure Completeness:** PASS
- All new files and directories specified with purpose annotations
- FR-to-file mapping provides explicit traceability for implementers
- 4 architectural boundaries defined (data access, computation, stage, contract)

**Pattern Completeness:** PASS
- 7 conflict points identified and resolved with code examples and anti-patterns
- Enforcement rules provide clear checklist for AI agent compliance
- Patterns reference existing project-context.md rules for everything not baseline-specific

## Gap Analysis & Resolutions

**Gap 1 (Resolved): NFR-R5 — Disable Mechanism**

Added `BASELINE_DEVIATION_ENABLED` setting:
- Default: `true`
- Follows existing pattern: `DISTRIBUTED_CYCLE_LOCK_ENABLED`, `SHARD_REGISTRY_ENABLED`
- Rollback: set `BASELINE_DEVIATION_ENABLED=false` for immediate, zero-risk disable
- Setting added to `config/settings.py`, documented in env file templates

The flag must gate three execution points in `scheduler.py`:
1. **Stage execution:** skip `run_baseline_deviation_stage_cycle()` in the per-cycle loop
2. **Backfill seeding:** skip `SeasonalBaselineClient.seed_from_history()` during startup — do not waste 10 minutes seeding baselines if the feature is disabled
3. **Weekly recompute timer:** do not spawn background recomputation coroutine

**Gap 2 (Resolved): Shard Coordination Interaction**

When shard coordination is enabled (Story 4.2), the baseline deviation stage receives only the shard-filtered scope set from the scheduler — consistent with how evidence and peak stages receive filtered scopes. No architectural change needed; the scheduler's existing scope filtering applies before the stage is called. The baseline deviation stage is shard-unaware by design — it processes whatever scopes it receives.

**Gap 3 (Resolved): Cold-Path Evidence Summary Modification**

`build_evidence_summary()` in the cold-path currently formats findings for CONSUMER_LAG, VOLUME_DROP, and THROUGHPUT_CONSTRAINED_PROXY. It must be extended to format BASELINE_DEVIATION findings including BaselineDeviationContext fields (deviation direction, magnitude, baseline vs. current values, correlated metrics). This is a code modification to an existing function, not a new file. Test coverage: `tests/unit/diagnosis/test_evidence_summary.py` needs new test cases for baseline deviation context formatting.

**Gap 4 (Resolved): Full-Cycle Dedup Integration Test**

Add a scheduler-level integration test that exercises the full stage sequence (evidence → peak → baseline_deviation → topology) with overlapping scopes — where a hand-coded detector fires on the same scope as a baseline deviation. Validates that only the hand-coded finding survives (D6 dedup). This is the highest-risk interaction point and must be tested beyond unit-level mocks. Location: `tests/integration/test_baseline_deviation.py`

**Gap 5 (Resolved): anomaly_family Literal Shared Type**

The `anomaly_family` Literal type may be defined inline in multiple contracts (AnomalyFinding, GateInputV1, CaseHeaderEventV1, TriageExcerptV1). Adding BASELINE_DEVIATION requires updating ALL locations where this Literal is defined. The architecture prescribes: if a shared type alias exists in `contracts/enums.py`, update it once. If the Literal is duplicated across contracts, consolidate it into a shared type first, then add BASELINE_DEVIATION. This prevents agents from updating one contract but missing others.

**Critical Gaps:** None
**Important Gaps:** 0 remaining (5 found, 5 resolved)

## Architecture Completeness Checklist

**Requirements Analysis**
- [x] Project context thoroughly analyzed (32 FRs, 17 NFRs, 72 project rules)
- [x] Scale and complexity assessed (Medium-High, 756K Redis keys, 5-min cycle)
- [x] Technical constraints identified (stage ordering, hot-path determinism, frozen contracts)
- [x] Cross-cutting concerns mapped (observability, reliability, auditability, testability, dedup, extensibility)

**Architectural Decisions**
- [x] 6 critical decisions documented with rationale and trade-off analysis
- [x] Technology stack confirmed (no new additions required)
- [x] Integration patterns defined (4 input sources, scheduler orchestration, existing downstream passthrough)
- [x] Performance considerations addressed (stage budget, Redis batching, async recompute)

**Implementation Patterns**
- [x] 7 conflict points identified and resolved with code examples
- [x] Naming conventions established (log events, OTLP instruments, constants)
- [x] Model patterns specified (BaselineDeviationContext, BaselineDeviationStageOutput)
- [x] Enforcement rules documented (5 mandatory rules for AI agents)

**Project Structure**
- [x] Complete directory structure defined (5 new files, 2 modified files)
- [x] Component boundaries established (data access, computation, stage, contract)
- [x] Integration points mapped (stage-to-stage, scheduler orchestration, external)
- [x] FR-to-file mapping complete (all 7 categories mapped to specific files)

## Architecture Readiness Assessment

**Overall Status:** READY FOR IMPLEMENTATION

**Confidence Level:** High — all requirements traced, all gaps resolved, brownfield integration points are well-understood from existing documentation

**Key Strengths:**
- Complete FR and NFR traceability (49/49 requirements mapped to architectural components)
- Brownfield-aware design that extends existing patterns rather than introducing new ones
- Pure function stage design enables deterministic unit testing without infrastructure
- Conservative-by-default posture structurally enforced (NOTIFY cap, correlation gate, dedup)
- Independent disableability via feature flag provides zero-risk rollback

**Areas for Future Enhancement (Post-MVP):**
- Metric personality auto-classification (Phase 2) may require computation.py refactoring to support multiple statistical methods
- YAML-configurable thresholds (Phase 2) will move constants from code to policy YAML
- Multi-signal extension (Phase 3) will require SeasonalBaselineClient to handle non-Kafka scope shapes

## Implementation Handoff

**AI Agent Guidelines:**
- Follow all 6 architectural decisions (D1-D6) exactly as documented
- Apply all 7 implementation patterns (P1-P7) consistently
- Respect project structure boundaries — baseline domain logic in `baseline/`, stage function in `pipeline/stages/`
- Import constants from `baseline/constants.py` — never hardcode
- Use `time_to_bucket()` for all bucket derivations — never derive inline
- Follow existing project-context.md rules for all patterns not specified in this document
- Include documentation updates per the Documentation Impact table in each implementation story

**Scheduler Story Sequencing Note:**
All `scheduler.py` modifications (stage integration, backfill extension, recompute timer, `BASELINE_DEVIATION_ENABLED` checks) should be implemented in a single story to avoid merge conflicts from multiple stories touching the same file.

**Implementation Sequence:**
1. `baseline/constants.py` + `baseline/models.py` — foundation models and constants
2. `baseline/computation.py` — MAD computation and time_to_bucket pure functions
3. `baseline/client.py` — SeasonalBaselineClient with Redis I/O
4. `models/anomaly_finding.py` + shared `anomaly_family` Literal — additive contract extension
5. `pipeline/stages/baseline_deviation.py` — stage function with dedup and correlation
6. `pipeline/scheduler.py` — stage integration, backfill extension, recompute timer, feature flag checks (single story)
7. `build_evidence_summary()` modification — cold-path BASELINE_DEVIATION context formatting
8. Observability instrumentation and tests throughout
