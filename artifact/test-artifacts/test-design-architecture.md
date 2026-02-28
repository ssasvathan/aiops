---
stepsCompleted: ['step-01-detect-mode', 'step-02-load-context', 'step-03-risk-and-testability', 'step-04-coverage-plan', 'step-05-generate-output']
lastStep: 'step-05-generate-output'
lastSaved: '2026-02-28'
workflowType: 'testarch-test-design'
inputDocuments:
  - artifact/planning-artifacts/prd/ (14 sharded files)
  - artifact/planning-artifacts/architecture.md
  - artifact/planning-artifacts/epics.md
---

# Test Design for Architecture: Event-Driven AIOps Triage Pipeline

**Purpose:** Architectural concerns, testability gaps, and NFR requirements for review by Architecture/Dev teams. Serves as a contract between QA and Engineering on what must be addressed before test development begins.

**Date:** 2026-02-28
**Author:** TEA Master Test Architect
**Status:** Architecture Review Pending
**Project:** aiOps
**PRD Reference:** artifact/planning-artifacts/prd/
**ADR Reference:** artifact/planning-artifacts/architecture.md

---

## Executive Summary

**Scope:** System-level test design for the Event-Driven AIOps Triage Pipeline — a 7-stage hot path (no LLM) + 5-stage cold path (async) with 12 frozen contracts, deterministic safety gating (AG0–AG6), and append-only CaseFile lifecycle.

**Architecture:**

- 15 architectural decisions across 5 categories (data, security, pipeline, serialization, infrastructure)
- asyncio.TaskGroup for concurrent case processing (100 cases/interval target)
- Durable outbox (Postgres) with Invariant A (write-before-publish) and B2 (publish-after-crash)
- Pydantic v2 frozen models as contract enforcement engine
- OpenTelemetry OTLP export for meta-monitoring

**Expected Scale:** 100 concurrent active cases per 5-minute evaluation interval across Business_Essential + Business_Critical Kafka clusters.

**Risk Summary:**

- **Total risks**: 12
- **High-priority (score >=6)**: 4 risks requiring immediate mitigation
- **Test effort**: ~76 test scenarios (~78–125 hours for 1 engineer)

---

## Quick Guide

### BLOCKERS - Team Must Decide

**Pre-Implementation Critical Path** — these MUST be completed before QA can write integration tests:

1. **TC-2: Crash Injection Mechanism** — Define the approach for simulating crashes between CaseFile write and outbox INSERT to test Invariant B2. Transaction abort? Process kill? SAVEPOINT rollback? (recommended owner: Pipeline Lead)
2. **TC-3: Clock Abstraction for Scheduler** — Provide injectable clock for the 5-minute wall-clock scheduler so tests can verify interval alignment and drift without waiting real time (recommended owner: Pipeline Lead)
3. **TC-1: LLM Stub Fixture Contract** — Define structured response fixtures for LLM stub mode covering valid, malformed, partial, and hallucinated-evidence responses (recommended owner: Pipeline Lead)

**What we need from team:** Complete these 3 items pre-implementation or integration test development is blocked.

---

### HIGH PRIORITY - Team Should Validate

1. **R-01: Invariant A Under Concurrency** — Verify that asyncio.TaskGroup per-case atomicity guarantees write-before-publish under 100 concurrent cases. QA will write load test; Architecture must confirm the concurrency model is sound. (Phase 0)
2. **R-06: Prometheus Total Unavailability Detection** — Validate that the TelemetryDegradedEvent pathway correctly distinguishes total Prometheus unavailability from individual missing series. QA will write both test paths; Architecture must confirm detection heuristic. (Phase 0)
3. **R-05: Redis Mid-Cycle Failure Handling** — Confirm AG5 degraded mode activates when Redis fails mid-evaluation (not just at startup). QA will use testcontainers pause/unpause; Architecture must confirm HealthRegistry update timing. (Phase 1A)

**What we need from team:** Review and approve the mitigation approaches.

---

### INFO ONLY - Solutions Provided

1. **Test strategy**: 40 Unit + 36 Integration tests (no E2E browser tests — backend pipeline)
2. **Tooling**: pytest 9.0.2, pytest-asyncio, testcontainers 4.14.1 (Postgres, Redis, Kafka, MinIO, OTLP Collector)
3. **Tiered execution**: PR (<10 min), Nightly (<30 min), Weekly (<60 min)
4. **Coverage**: 76 test scenarios prioritized P0–P2 with risk-based classification
5. **Quality gates**: P0=100%, P1>=95%, code coverage >=80% (>=90% for contracts/gating/denylist)

**What we need from team:** Review and acknowledge.

---

## Risk Assessment

**Total risks identified**: 12 (4 high-priority score >=6, 6 medium, 2 low)

### High-Priority Risks (Score >=6) — IMMEDIATE ATTENTION

| Risk ID | Category | Description | P | I | Score | Mitigation | Owner | Timeline |
|---|---|---|---|---|---|---|---|---|
| **R-01** | **TECH** | Invariant A violation under 100 concurrent CaseFile writes — race on object storage + outbox | 2 | 3 | **6** | Per-case atomicity in asyncio.TaskGroup; integration test with concurrent cases | Pipeline Lead | Phase 0 |
| **R-02** | **OPS** | DEAD outbox accumulation in prod — Kafka unavailability pushes rows to DEAD, requiring manual investigation | 2 | 3 | **6** | Exponential backoff; DEAD alerting (NFR-R4); recovery runbook; test RETRY->DEAD path | Ops Lead | Phase 1A |
| **R-05** | **PERF** | Redis mid-cycle failure causes paging storm — dedupe keys lost, all cases processed as new | 2 | 3 | **6** | AG5 NOTIFY-only cap; DegradedModeEvent; testcontainers pause/unpause simulation | Pipeline Lead | Phase 1A |
| **R-06** | **DATA** | Prometheus total unavailability emitting all-UNKNOWN cases — fails to distinguish from individual missing series | 2 | 3 | **6** | TelemetryDegradedEvent; cap to OBSERVE/NOTIFY; dedicated test paths for total vs partial | Pipeline Lead | Phase 0 |

### Medium-Priority Risks (Score 3–5)

| Risk ID | Category | Description | P | I | Score | Mitigation | Owner |
|---|---|---|---|---|---|---|---|
| R-03 | TECH | LLM hallucination bypassing schema validation | 2 | 2 | 4 | Schema validation + provenance check + AG4 confidence threshold | Pipeline Lead |
| R-04 | SEC | Exposure denylist bypass at one of 4 boundaries | 1 | 3 | 3 | Single shared function + integration test per boundary + PR review | Security Lead |
| R-07 | OPS | Topology registry stale data causing wrong-team routing | 2 | 2 | 4 | Registry reload <=5s + OTLP metric + labeling feedback (Phase 2) | Platform Lead |
| R-08 | DATA | CaseFile hash chain broken by storage corruption | 1 | 3 | 3 | SHA-256 verification on read-back + infrastructure replication | Storage Lead |
| R-09 | PERF | Scheduler drift exceeding 30s tolerance under load | 2 | 2 | 4 | Wall-clock alignment + drift metric + WARN log + clock injection | Pipeline Lead |
| R-10 | OPS | ServiceNow linkage 2-hour retry exhaustion | 2 | 2 | 4 | FAILED_FINAL escalation via Slack + queue depth monitoring | SN Lead |

### Low-Priority Risks (Score 1–2)

| Risk ID | Category | Description | P | I | Score | Action |
|---|---|---|---|---|---|---|
| R-11 | TECH | Testcontainers flakiness in CI | 2 | 1 | 2 | Session-scoped containers + health checks |
| R-12 | SEC | Bank credential rotation during active pipeline | 1 | 2 | 2 | Startup keytab validation + graceful shutdown |

---

## Testability Concerns and Architectural Gaps

### ACTIONABLE CONCERNS — Architecture Team Must Address

#### Blockers to Fast Feedback

| Concern | Impact | What Architecture Must Provide | Owner | Timeline |
|---|---|---|---|---|
| **TC-2: No crash injection mechanism** | Cannot test Invariant B2 (publish-after-crash) | Define crash simulation approach (SAVEPOINT rollback, session kill, or transaction abort pattern) | Pipeline Lead | Phase 0 |
| **TC-3: No clock abstraction** | Cannot test scheduler drift/alignment without 5-min waits | Inject clock dependency into scheduler for deterministic time control | Pipeline Lead | Phase 0 |
| **TC-1: No LLM stub fixture contract** | Cannot test LLM malformed/partial output handling paths | Define `diagnosis-stub-fixtures/` with representative response payloads | Pipeline Lead | Phase 0 |

#### Architectural Improvements Needed

1. **TC-5: Redis mid-cycle failure injection**
   - **Current problem**: Architecture describes Redis degraded mode but not how to simulate mid-evaluation failure
   - **Required change**: HealthRegistry must detect Redis loss within the same evaluation cycle (not just at cycle start)
   - **Impact if not fixed**: AG5 degraded mode tests are unreliable
   - **Owner**: Pipeline Lead
   - **Timeline**: Phase 1A

2. **TC-6: Prometheus failure mode distinction**
   - **Current problem**: Two failure modes (individual missing series vs total unavailability) have different behaviors
   - **Required change**: Evidence Builder must have explicit detection logic for total Prometheus unavailability with documented heuristic
   - **Impact if not fixed**: TelemetryDegradedEvent may not fire or may fire incorrectly
   - **Owner**: Pipeline Lead
   - **Timeline**: Phase 0

---

### Testability Assessment Summary

#### What Works Well

- Frozen Pydantic models provide deterministic input construction for all pipeline stages
- Integration adapter base class with OFF/LOG/MOCK/LIVE modes enables built-in mock capability
- HealthRegistry can be set to DEGRADED/UNAVAILABLE per component for controlled fault injection
- Versioned YAML policies can be loaded from test fixtures for deterministic gating
- structlog JSON with correlation_id enables log-based assertions
- OpenTelemetry OTLP + testcontainers Collector stub validates metric emission
- Deterministic Rulebook (same GateInput + policies = same ActionDecision) supports decision replay

#### Accepted Trade-offs

- **No property-based testing initially** — UNKNOWN propagation tested with representative cases, not exhaustive; acceptable for Phase 0/1A
- **Session-scoped testcontainers** — Tests share container instances within a session; per-test isolation via data cleanup, not per-test containers

---

## Risk Mitigation Plans (High-Priority Risks >=6)

### R-01: Invariant A Under Concurrency (Score: 6)

**Mitigation Strategy:**

1. asyncio.TaskGroup processes each case as an independent async task with per-case object storage write + outbox insert
2. Object storage write must return success before outbox INSERT executes (sequential within each case)
3. Integration test spawns 100 concurrent cases, verifies every CaseFile exists before its corresponding Kafka header

**Owner:** Pipeline Lead
**Timeline:** Phase 0
**Status:** Planned
**Verification:** `test_pipeline_e2e.py` with 100 concurrent cases passes; no header without prior CaseFile

### R-02: DEAD Outbox Accumulation (Score: 6)

**Mitigation Strategy:**

1. Exponential backoff with configurable max retries (per outbox-policy-v1)
2. DEAD>0 alert fires immediately in prod (NFR-R4)
3. Recovery runbook documents manual replay/resolution procedure
4. Test RETRY->DEAD transition with Kafka deliberately unavailable

**Owner:** Ops Lead
**Timeline:** Phase 1A
**Status:** Planned
**Verification:** `test_outbox_publish.py` demonstrates RETRY->DEAD path; alert rule validated

### R-05: Redis Failure Storm (Score: 6)

**Mitigation Strategy:**

1. AG5 degraded mode caps all actions to NOTIFY-only when Redis unavailable
2. DegradedModeEvent emitted on Redis status transition
3. Testcontainers pause Redis mid-evaluation to simulate realistic failure
4. Verify no PAGE actions dispatched during Redis unavailability

**Owner:** Pipeline Lead
**Timeline:** Phase 1A
**Status:** Planned
**Verification:** `test_degraded_modes.py` pauses Redis mid-cycle; asserts NOTIFY-only + DegradedModeEvent

### R-06: Prometheus Total Unavailability (Score: 6)

**Mitigation Strategy:**

1. Evidence Builder detects total Prometheus unavailability (distinct from individual missing series)
2. TelemetryDegradedEvent emitted; actions capped to OBSERVE/NOTIFY
3. No all-UNKNOWN cases emitted (pipeline skips case creation when Prometheus is completely down)
4. Separate test paths: individual missing series (UNKNOWN propagation) vs total failure (TelemetryDegradedEvent)

**Owner:** Pipeline Lead
**Timeline:** Phase 0
**Status:** Planned
**Verification:** Two integration tests: `test_individual_missing_series` and `test_total_prometheus_unavailability`

---

## Assumptions and Dependencies

### Assumptions

1. asyncio.TaskGroup provides sufficient per-case isolation for Invariant A under 100 concurrent cases
2. Testcontainers pause/unpause API reliably simulates mid-cycle infrastructure failures
3. LLM stub mode produces deterministic output that exercises all schema validation paths
4. Banking regulatory examination will accept SHA-256 hash chain as tamper evidence

### Dependencies

1. **Testcontainers Docker support** — CI environment must support Docker-in-Docker or equivalent. Required by Phase 0.
2. **OTLP Collector container image** — Available in testcontainers registry. Required by Phase 1A.
3. **MinIO container image** — Available in testcontainers registry. Required by Phase 0.

### Risks to Plan

- **Risk**: Testcontainers adds CI flakiness (container startup failures)
  - **Impact**: Integration tests become unreliable, blocking PRs
  - **Contingency**: Session-scoped containers + health check waits; separate unit and integration test commands

---

**End of Architecture Document**

**Next Steps for Architecture Team:**

1. Review Quick Guide (BLOCKERS/HIGH PRIORITY/INFO ONLY) and assign owners
2. Resolve 3 pre-implementation blockers (TC-1, TC-2, TC-3) before Phase 0
3. Validate assumptions about concurrency model and failure detection heuristics
4. Provide feedback on testability gaps

**Next Steps for QA Team:**

1. Wait for pre-implementation blockers to be resolved
2. Refer to companion QA doc (test-design-qa.md) for test scenarios and execution strategy
3. Begin test infrastructure setup (conftest.py, testcontainers fixtures, test data factories)
