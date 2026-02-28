---
stepsCompleted: ['step-01-detect-mode', 'step-02-load-context', 'step-03-risk-and-testability', 'step-04-coverage-plan', 'step-05-generate-output']
lastStep: 'step-05-generate-output'
lastSaved: '2026-02-28'
---

# Test Design Progress

## Step 1: Mode Detection

- **Mode**: System-Level
- **Reason**: PRD + Architecture + Epics all present; no sprint-status.yaml; solutioning phase
- **Prerequisites**: All satisfied (PRD with 68 FRs + 31 NFRs, Architecture document, Epics & Stories)
- **Outputs planned**:
  1. `test-design-architecture.md` (Architecture/Dev audience)
  2. `test-design-qa.md` (QA audience)
  3. `aiops-handoff.md` (BMAD integration)

## Step 2: Load Context

- **Stack**: Backend (Python 3.13, pytest 9.0.2, testcontainers 4.14.1)
- **Playwright**: Not applicable (no frontend)
- **Input Documents**:
  - PRD: 14 sharded files, 68 FRs + 31 NFRs
  - Architecture: architecture.md (event-driven pipeline, 12 frozen contracts)
  - Epics: epics.md (8 epics, 41 stories, 100% FR coverage)
  - UX: N/A (backend pipeline)
- **Knowledge Fragments Loaded**:
  - adr-quality-readiness-checklist.md (core)
  - test-levels-framework.md (core)
  - risk-governance.md (core)
  - test-quality.md (core)
- **Existing Test Coverage**: None (greenfield project)

## Step 3: Testability & Risk Assessment

### Testability Review

**Testability Concerns (6 actionable):**
- TC-1: LLM stub response fixtures needed (define diagnosis-stub-fixtures/)
- TC-2: Outbox crash-recovery injection mechanism unspecified
- TC-3: Time-dependent scheduler needs clock abstraction
- TC-4: Cross-stage hash chain corruption injection tests needed
- TC-5: Redis mid-cycle failure simulation via testcontainers pause/unpause
- TC-6: Prometheus total vs individual failure distinction in tests

**Assessment**: Controllability=STRONG, Observability=STRONG, Reliability=STRONG

**ASRs Identified**: 12 total (8 ACTIONABLE, 4 FYI)
- ASR-1: Invariant A (write-before-publish)
- ASR-2: Invariant B2 (publish-after-crash)
- ASR-3: UNKNOWN-not-zero propagation
- ASR-4: Hot path independent of LLM
- ASR-5: Deterministic Rulebook gating
- ASR-6: Exposure denylist at 4 boundaries
- ASR-7: 12 frozen contracts schema stability
- ASR-8: SHA-256 hash chain tamper evidence
- ASR-9: Environment action caps (FYI)
- ASR-10: 25-month retention (FYI)
- ASR-11: Meta-monitoring OTLP (FYI)
- ASR-12: Graceful shutdown (FYI)

### Risk Assessment

**High Risks (Score ≥ 6):**
- R-01: Invariant A under concurrency (P=2, I=3, Score=6) → Phase 0
- R-02: DEAD outbox accumulation (P=2, I=3, Score=6) → Phase 1A
- R-05: Redis failure storm potential (P=2, I=3, Score=6) → Phase 1A
- R-06: Prometheus total unavailability (P=2, I=3, Score=6) → Phase 0

**Medium Risks (Score 3-5):** R-03, R-04, R-07, R-08, R-09, R-10
**Low Risks (Score ≤ 2):** R-11, R-12

**Priority**: Phase 0 must prove R-01 + R-06; Phase 1A must prove R-02 + R-05

## Step 4: Coverage Plan & Execution Strategy

### Coverage Summary
- **76 test scenarios** (40 Unit + 36 Integration)
- P0: 28 scenarios (16 Unit + 12 Integration)
- P1: 33 scenarios (19 Unit + 14 Integration)
- P2: 11 scenarios, P3: 0

### Execution Tiers
- PR: Unit + fast integration (< 10 min)
- Nightly: Full suite including testcontainers (< 30 min)
- Weekly: Concurrency load + chaos tests (< 60 min)

### Resource Estimates
- Total: ~78–125 hours across all phases
- Phase 0: ~20–30 hours (invariants + degraded modes)
- Phase 1A: ~40–60 hours (remaining P0 + P1)
- Phase 1B: ~10–15 hours (SN-specific)

### Quality Gates
- P0 = 100% pass rate (PR blocking)
- P1 ≥ 95% (PR blocking)
- Code coverage ≥ 80% overall, ≥ 90% for contracts/gating/denylist
- All 4 high-risk mitigations tested before Phase 1A release

## Step 5: Generate Outputs & Validate

### Output Documents Generated
1. `artifact/test-artifacts/test-design-architecture.md` — Architecture/Dev audience
2. `artifact/test-artifacts/test-design-qa.md` — QA audience
3. `artifact/test-artifacts/test-design/aiops-handoff.md` — BMAD integration handoff

### Checklist Validation
- Architecture doc: PASS (actionable-first structure, no test code, cross-references QA doc)
- QA doc: PASS (pytest examples, interval estimates, P0/P1/P2 coverage plan)
- Handoff doc: PASS (artifact inventory, epic/story guidance, risk-to-story mapping)
- Cross-document consistency: PASS (same risk IDs, priorities, blockers)

### Completion Report
- **Mode**: System-Level
- **Output files**: 3 documents (architecture, QA, handoff)
- **Key risks**: 4 high-priority (R-01, R-02, R-05, R-06), all with mitigation plans
- **Gate thresholds**: P0=100%, P1>=95%, coverage>=80%
- **Open assumptions**: Crash injection mechanism (TC-2), clock abstraction (TC-3), LLM stub fixtures (TC-1) — all assigned to Pipeline Lead for Phase 0
