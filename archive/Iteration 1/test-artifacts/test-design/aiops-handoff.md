---
title: 'TEA Test Design -> BMAD Handoff Document'
version: '1.0'
workflowType: 'testarch-test-design-handoff'
inputDocuments:
  - artifact/test-artifacts/test-design-architecture.md
  - artifact/test-artifacts/test-design-qa.md
sourceWorkflow: 'testarch-test-design'
generatedBy: 'TEA Master Test Architect'
generatedAt: '2026-02-28'
projectName: 'aiOps'
---

# TEA -> BMAD Integration Handoff

## Purpose

This document bridges TEA's test design outputs with BMAD's epic/story decomposition workflow (`create-epics-and-stories`). It provides structured integration guidance so that quality requirements, risk assessments, and test strategies flow into implementation planning.

## TEA Artifacts Inventory

| Artifact | Path | BMAD Integration Point |
|---|---|---|
| Test Design (Architecture) | `artifact/test-artifacts/test-design-architecture.md` | Epic quality requirements, risk mitigation assignments |
| Test Design (QA) | `artifact/test-artifacts/test-design-qa.md` | Story acceptance criteria, test scenario references |
| Risk Assessment | (embedded in both test design docs) | Epic risk classification, story priority |
| Coverage Strategy | (embedded in QA doc) | Story test requirements, P0/P1 scenarios |
| This Handoff | `artifact/test-artifacts/test-design/aiops-handoff.md` | BMAD workflow integration bridge |

## Epic-Level Integration Guidance

### Risk References

The following P0/P1 risks should appear as epic-level quality gates:

**Epic 1 (Project Foundation):**
- No high risks directly. Foundation enables all other epics.
- Quality gate: All 12 frozen contracts pass round-trip tests (P0-023, P0-024)

**Epic 2 (Evidence Collection):**
- **R-06** (Score 6): Prometheus total unavailability — TelemetryDegradedEvent pathway must be proven
- Quality gate: UNKNOWN-not-zero propagation tests pass (P0-002, P0-003, P0-004)

**Epic 3 (Topology Resolution):**
- **R-07** (Score 4): Stale topology data — registry reload test
- Quality gate: Topology resolver unit tests pass (P0-005)

**Epic 4 (Durable Triage):**
- **R-01** (Score 6): Invariant A under concurrency — CaseFile before Kafka header
- **R-02** (Score 6): DEAD outbox accumulation — RETRY->DEAD path
- Quality gate: Invariant A (P0-008, P0-009) + Invariant B2 (P0-011) tests pass

**Epic 5 (Safety Gating):**
- **R-05** (Score 6): Redis failure storm — AG5 NOTIFY-only cap
- Quality gate: All AG0–AG6 tests pass (P0-013–P0-019); degraded mode test (P0-028)

**Epic 6 (LLM Diagnosis):**
- **R-03** (Score 4): LLM hallucination — schema validation + provenance
- Quality gate: LLM timeout fallback (P0-021); hot path independent of LLM (P0-022)

**Epic 7 (Governance & Observability):**
- **R-04** (Score 3): Denylist bypass — 4-boundary enforcement
- Quality gate: Denylist negative tests at all boundaries (P0-025, P0-026, P0-027)

**Epic 8 (ServiceNow Automation, Phase 1B):**
- **R-10** (Score 4): SN retry exhaustion — FAILED_FINAL escalation
- Quality gate: SN tiered correlation + idempotent upsert tests pass

### Quality Gates

| Epic | Quality Gate | Minimum Test Coverage |
|---|---|---|
| Epic 1 | All 12 contracts frozen + round-trip | P0-023, P0-024 |
| Epic 2 | UNKNOWN propagation + TelemetryDegradedEvent | P0-002, P0-003, P0-004 |
| Epic 3 | Topology resolver correct | P0-005 |
| Epic 4 | Invariant A + B2 proven | P0-008, P0-009, P0-011, P0-012 |
| Epic 5 | All AG0–AG6 pass + degraded mode | P0-013–P0-019, P0-028 |
| Epic 6 | LLM fallback + hot path independence | P0-021, P0-022 |
| Epic 7 | Denylist at 4 boundaries | P0-025, P0-026, P0-027 |
| Epic 8 | SN correlation + upsert | P1-019, P1-020, P1-021 |

## Story-Level Integration Guidance

### P0/P1 Test Scenarios -> Story Acceptance Criteria

The following test scenarios MUST be reflected in story acceptance criteria:

| Test ID | Scenario | Recommended Story | Acceptance Criteria Addition |
|---|---|---|---|
| P0-002 | Missing series -> UNKNOWN | Story 2.1 (Evidence Collection) | "Given a missing Prometheus series, When evidence is built, Then EvidenceStatus=UNKNOWN (never zero)" |
| P0-008 | Invariant A | Story 4.1 (CaseFile Write) | "Given a CaseFile write, When triage is complete, Then CaseFile exists in object storage BEFORE Kafka header" |
| P0-011 | Invariant B2 | Story 4.3 (Outbox Durability) | "Given a crash between CaseFile write and Kafka publish, When the system recovers, Then the outbox publishes the message" |
| P0-018 | Rulebook sequential | Story 5.1 (Rulebook Engine) | "Given a GateInput, When gates are evaluated, Then AG0-AG6 execute sequentially and halt on first failure" |
| P0-019 | Decision replay | Story 5.2 (Decision Audit) | "Given a historical CaseFile with policy versions, When the same GateInput is re-evaluated with those versions, Then the same ActionDecision results" |
| P0-028 | Redis degraded | Story 5.5 (Degraded Mode) | "Given Redis unavailable, When an action decision is made, Then actions are capped to NOTIFY-only and DegradedModeEvent is emitted" |
| P0-027 | Denylist boundaries | Story 7.1 (Exposure Controls) | "Given a denied field in input data, When output is assembled at any of the 4 boundaries, Then the denied field is absent" |

### Data-TestId Requirements

Not applicable — backend pipeline with no UI. Test identification uses pytest markers and test function naming conventions per architecture patterns.

## Risk-to-Story Mapping

| Risk ID | Category | P x I | Recommended Story/Epic | Test Level |
|---|---|---|---|---|
| R-01 | TECH | 6 | Epic 4 / Story 4.1, 4.2 | Integration |
| R-02 | OPS | 6 | Epic 4 / Story 4.3 | Integration |
| R-03 | TECH | 4 | Epic 6 / Story 6.2 | Unit |
| R-04 | SEC | 3 | Epic 7 / Story 7.1 | Integration |
| R-05 | PERF | 6 | Epic 5 / Story 5.5, 5.6 | Integration |
| R-06 | DATA | 6 | Epic 2 / Story 2.1, 2.4 | Integration |
| R-07 | OPS | 4 | Epic 3 / Story 3.2 | Integration |
| R-08 | DATA | 3 | Epic 4 / Story 4.1 | Integration |
| R-09 | PERF | 4 | Epic 2 / Story 2.2 (scheduler) | Unit |
| R-10 | OPS | 4 | Epic 8 / Story 8.2 | Unit |
| R-11 | TECH | 2 | Epic 1 / Story 1.5 (test infra) | Integration |
| R-12 | SEC | 2 | Epic 1 / Story 1.3 (config) | Unit |

## Recommended BMAD -> TEA Workflow Sequence

1. **TEA Test Design** (`TD`) -> produces this handoff document (COMPLETE)
2. **BMAD Sprint Planning** -> consumes this handoff, schedules epics with quality gates
3. **BMAD Create/Update Stories** -> embeds P0 test scenarios as acceptance criteria
4. **TEA ATDD** (`AT`) -> generates acceptance tests per story (during implementation)
5. **BMAD Implementation** -> developers implement with test-first guidance
6. **TEA Automate** (`TA`) -> generates full test suite
7. **TEA Trace** (`TR`) -> validates coverage completeness

## Phase Transition Quality Gates

| From Phase | To Phase | Gate Criteria |
|---|---|---|
| Test Design | Sprint Planning | All P0 risks have mitigation strategy (COMPLETE) |
| Sprint Planning | Implementation (Phase 0) | Stories have acceptance criteria from test design |
| Phase 0 | Phase 1A | Invariant A + B2 proven; UNKNOWN propagation tested; TelemetryDegradedEvent validated |
| Phase 1A | Phase 1B | All P0 tests pass; P1 >=95%; all 4 high-risk mitigations have passing tests |
| Phase 1B | Phase 2 | SN integration tests pass; full hot+cold path E2E verified |
| Any Phase | Release | Trace matrix shows >=80% coverage of P0/P1 requirements |
