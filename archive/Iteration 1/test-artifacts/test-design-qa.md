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

# Test Design for QA: Event-Driven AIOps Triage Pipeline

**Purpose:** Test execution recipe for QA team. Defines what to test, how to test it, and what QA needs from other teams.

**Date:** 2026-02-28
**Author:** TEA Master Test Architect
**Status:** Draft
**Project:** aiOps

**Related:** See Architecture doc (test-design-architecture.md) for testability concerns and architectural blockers.

---

## Executive Summary

**Scope:** System-level test coverage for the aiOps triage pipeline — 7-stage hot path, 5-stage cold path, 12 frozen contracts, deterministic safety gating (AG0–AG6), and append-only CaseFile lifecycle.

**Risk Summary:**

- Total Risks: 12 (4 high-priority score >=6, 6 medium, 2 low)
- Critical Categories: TECH (concurrency, LLM), DATA (Prometheus, hash chain), PERF (Redis storm), OPS (outbox DEAD)

**Coverage Summary:**

- P0 tests: ~28 (invariants, contracts, gating, degraded modes)
- P1 tests: ~33 (pipeline stages, integrations, operability)
- P2 tests: ~11 (governance, logging, edge cases)
- P3 tests: 0
- **Total**: ~76 tests (~78–125 hours with 1 engineer)

---

## Not in Scope

| Item | Reasoning | Mitigation |
|---|---|---|
| **Infrastructure-level encryption (TLS, SSE)** | NFR-S1/S2 are infrastructure concerns, not application-level | Validated by platform team during deployment readiness |
| **CaseFile retention lifecycle (25-month purge)** | Infrastructure-level object storage lifecycle policy | Audit policy configuration; not application-testable |
| **CI/CD pipeline definitions** | Deferred per architecture decision 5C | Codebase structured CI-ready; bank Git Actions integration handled separately |
| **Phase 2+ ML advisory features** | Out of scope for Phase 0/1A/1B | Tested when Phase 2 implementation begins |
| **Phase 3 Dynatrace hybrid topology** | Out of scope for current phases | Tested when Phase 3 implementation begins |
| **Cross-border data handling** | Not applicable — operational telemetry only, no PII | Evaluated during multi-region deployment if needed |

---

## Dependencies & Test Blockers

### Backend/Architecture Dependencies (Pre-Implementation)

**Source:** See Architecture doc "Quick Guide" for detailed mitigation plans.

1. **TC-2: Crash Injection Mechanism** — Pipeline Lead — Phase 0
   - QA needs a defined approach to simulate crashes between CaseFile write and outbox INSERT
   - Blocks Invariant B2 integration test (TS-020)

2. **TC-3: Clock Abstraction** — Pipeline Lead — Phase 0
   - QA needs injectable clock for scheduler tests
   - Blocks scheduler drift/alignment tests

3. **TC-1: LLM Stub Fixtures** — Pipeline Lead — Phase 0
   - QA needs structured response payloads (valid, malformed, partial, hallucinated)
   - Blocks LLM degradation test scenarios (TS-037, TS-038)

### QA Infrastructure Setup (Pre-Implementation)

1. **Testcontainers Session Fixtures** — QA
   - Session-scoped `conftest.py` for Postgres, Redis, Kafka, MinIO, OTLP Collector
   - Health check waits before test execution

2. **Test Data Factories** — QA
   - Pydantic model factories for GateInputV1, ActionDecisionV1, EvidenceSnapshot
   - Policy fixture loading from versioned YAML test data

3. **Test Environments** — QA
   - Local: `docker-compose up` + `APP_ENV=local`
   - CI: Testcontainers (no docker-compose dependency)

**Example fixture pattern (pytest):**

```python
import pytest
from aiops_triage_pipeline.contracts.gate_input import GateInputV1

@pytest.fixture
def gate_input_factory():
    """Factory for creating GateInputV1 test instances."""
    def _create(**overrides):
        defaults = {
            "case_id": "test-case-001",
            "env": "prod",
            "cluster_id": "cluster-01",
            "topic": "payments.events",
            "criticality_tier": "TIER_0",
            "evidence_status_map": {"lag": "PRESENT", "throughput": "PRESENT"},
            "sustained": True,
            "confidence": 0.85,
            # ... other required fields
        }
        defaults.update(overrides)
        return GateInputV1(**defaults)
    return _create
```

---

## Risk Assessment

**Note:** Full risk details in Architecture doc. This section summarizes risks relevant to QA test planning.

### High-Priority Risks (Score >=6)

| Risk ID | Category | Description | Score | QA Test Coverage |
|---|---|---|---|---|
| **R-01** | TECH | Invariant A under 100 concurrent cases | **6** | TS-015 + TS-016: concurrent CaseFile writes verified before Kafka headers |
| **R-02** | OPS | DEAD outbox accumulation in prod | **6** | TS-019 + TS-020: RETRY->DEAD transition + crash recovery |
| **R-05** | PERF | Redis mid-cycle failure storm | **6** | TS-054 + TS-055: pause Redis during evaluation, assert NOTIFY-only |
| **R-06** | DATA | Prometheus total unavailability | **6** | TS-004: TelemetryDegradedEvent + no all-UNKNOWN cases |

### Medium/Low-Priority Risks

| Risk ID | Category | Description | Score | QA Test Coverage |
|---|---|---|---|---|
| R-03 | TECH | LLM hallucination | 4 | TS-038: malformed LLM output -> schema rejection -> fallback |
| R-04 | SEC | Denylist bypass at boundary | 3 | TS-049–053: negative tests at all 4 boundaries |
| R-07 | OPS | Stale topology registry | 4 | TS-011: registry reload on change |
| R-08 | DATA | Hash chain corruption | 3 | TS-070–071: hash verification + corruption detection |
| R-09 | PERF | Scheduler drift | 4 | Clock injection test (blocked on TC-3) |
| R-10 | OPS | SN retry exhaustion | 4 | TS-045: 2-hour window + FAILED_FINAL escalation |
| R-11 | TECH | Testcontainers flakiness | 2 | Session-scoped containers + health checks |
| R-12 | SEC | Credential rotation | 2 | TS-075: keytab path validation |

---

## Entry Criteria

- [ ] All requirements and assumptions agreed upon by QA, Dev, PM
- [ ] Pre-implementation blockers resolved (TC-1, TC-2, TC-3 from Architecture doc)
- [ ] Testcontainers session fixtures ready (Postgres, Redis, Kafka, MinIO, OTLP Collector)
- [ ] Test data factories ready (Pydantic model factories, policy fixtures)
- [ ] Docker available in CI environment
- [ ] Feature deployed to local/test environment

## Exit Criteria

- [ ] All P0 tests passing (28 scenarios)
- [ ] All P1 tests passing or failures triaged and accepted (33 scenarios)
- [ ] No open high-priority / high-severity bugs
- [ ] Test coverage >=80% overall, >=90% for contracts/gating/denylist
- [ ] All 4 high-risk mitigations have passing integration tests
- [ ] Invariant A and B2 tests pass in every PR

---

## Test Coverage Plan

**IMPORTANT:** P0/P1/P2 = **priority and risk level** (what to focus on if time-constrained), NOT execution timing. See "Execution Strategy" for when tests run.

### P0 (Critical)

**Criteria:** Blocks core functionality + High risk (>=6) + No workaround

| Test ID | Requirement | Test Level | Risk Link | Notes |
|---|---|---|---|---|
| **P0-001** | Evidence Builder produces EvidenceSnapshot (FR1–FR3) | Unit | ASR-3 | |
| **P0-002** | Missing series -> UNKNOWN (never zero) (FR4) | Unit | ASR-3, R-06 | |
| **P0-003** | UNKNOWN propagates through peak -> sustained -> gating (FR4) | Unit | ASR-3 | |
| **P0-004** | Total Prometheus unavailability -> TelemetryDegradedEvent (FR67a) | Integration | R-06 | Testcontainers |
| **P0-005** | Topology resolver: anomaly key -> stream_id + ownership (FR9–12) | Unit | | |
| **P0-006** | CaseFile triage.json assembly (FR17–18) | Unit | | |
| **P0-007** | SHA-256 hash computation on CaseFile write (FR19) | Unit | ASR-8 | |
| **P0-008** | Invariant A: CaseFile exists before Kafka header (FR22) | Integration | R-01 | Testcontainers |
| **P0-009** | Invariant A under 100 concurrent cases (NFR-P6) | Integration | R-01 | Weekly tier |
| **P0-010** | Outbox state machine transitions (FR23–24) | Unit | | |
| **P0-011** | Invariant B2: publish-after-crash (FR25) | Integration | R-02 | Blocked on TC-2 |
| **P0-012** | Outbox delivers CaseHeaderEvent + TriageExcerpt to Kafka (FR22, 26) | Integration | | Testcontainers |
| **P0-013** | Rulebook AG0: schema validation (FR27) | Unit | ASR-5 | |
| **P0-014** | Rulebook AG1: environment/tier cap (FR28) | Unit | ASR-5, ASR-9 | |
| **P0-015** | Rulebook AG2: evidence sufficiency (FR29) | Unit | ASR-5 | |
| **P0-016** | Rulebook AG4: sustained/confidence threshold (FR31) | Unit | ASR-5 | |
| **P0-017** | Rulebook AG5: dedupe/degraded mode (FR32) | Unit | ASR-5, R-05 | |
| **P0-018** | Rulebook sequential evaluation AG0->AG6 (FR34) | Unit | ASR-5 | |
| **P0-019** | Decision replay: same inputs -> same output (NFR-T1) | Unit | ASR-5 | |
| **P0-020** | Full hot-path E2E (NFR-T5) | Integration | ASR-4 | Testcontainers |
| **P0-021** | LLM timeout -> deterministic fallback (FR38) | Unit | ASR-4 | |
| **P0-022** | Hot path unaffected by LLM unavailability (FR41) | Integration | ASR-4 | |
| **P0-023** | 12 frozen contracts: frozen=True, round-trip (all contracts) | Unit | ASR-7 | |
| **P0-024** | Contract schema regression (all contracts) | Unit | ASR-7 | |
| **P0-025** | Denylist on TriageExcerpt (NFR-S5) | Unit | ASR-6 | |
| **P0-026** | Denylist on Slack (NFR-S5) | Unit | ASR-6 | |
| **P0-027** | Denylist negative: denied fields absent (all 4 boundaries) | Integration | R-04, ASR-6 | |
| **P0-028** | Redis unavailable -> NOTIFY-only + DegradedModeEvent (NFR-R1) | Integration | R-05 | Testcontainers |

**Total P0:** ~28 tests

---

### P1 (High)

**Criteria:** Important features + Medium risk + Common workflows

| Test ID | Requirement | Test Level | Risk Link | Notes |
|---|---|---|---|---|
| **P1-001** | Peak profile classification (FR5–6) | Unit | | |
| **P1-002** | Sustained detection: 5 consecutive buckets (FR7) | Unit | | |
| **P1-003** | Peak cache hit/miss from Redis (FR8) | Unit | | |
| **P1-004** | Multi-level ownership resolution (FR13–14) | Unit | | |
| **P1-005** | Topology registry v0/v1 canonicalization (FR15) | Unit | | |
| **P1-006** | CaseFile write-once enforcement (FR20) | Integration | ASR-8 | |
| **P1-007** | Outbox RETRY with exponential backoff (FR24) | Unit | | |
| **P1-008** | Outbox RETRY -> DEAD after max retries (FR24) | Unit | R-02 | |
| **P1-009** | Rulebook AG3: SOURCE_TOPIC denial (FR30) | Unit | | |
| **P1-010** | Rulebook AG6: postmortem predicate (FR33) | Unit | | |
| **P1-011** | Action dispatch: PAGE to PagerDuty (FR43–44) | Integration | | MOCK mode |
| **P1-012** | Action dispatch: NOTIFY to Slack (FR45) | Integration | | MOCK mode |
| **P1-013** | Structured log fallback when Slack unavailable (FR45) | Unit | | |
| **P1-014** | Dedupe via Redis: fingerprint suppressed within TTL (FR35) | Unit | | |
| **P1-015** | LLM diagnosis produces valid DiagnosisReport.v1 (FR36–37) | Unit | | |
| **P1-016** | LLM malformed output -> rejection -> fallback (FR39) | Unit | R-03 | |
| **P1-017** | LLM stub mode produces deterministic output (NFR-T3) | Unit | | |
| **P1-018** | diagnosis.json with triage.json hash reference (FR40) | Integration | ASR-8 | |
| **P1-019** | SN tiered correlation (FR46–47) | Integration | | Phase 1B |
| **P1-020** | SN idempotent Problem + PIR upsert (FR48) | Unit | | Phase 1B |
| **P1-021** | SN 2-hour retry + FAILED_FINAL escalation (FR49) | Unit | R-10 | Phase 1B |
| **P1-022** | Denylist on SN Problem/PIR (NFR-S5) | Unit | ASR-6 | Phase 1B |
| **P1-023** | Denylist on LLM narrative (NFR-S5) | Unit | ASR-6 | |
| **P1-024** | Redis mid-cycle failure (pause/unpause) (NFR-T4) | Integration | R-05 | Weekly tier |
| **P1-025** | Redis recovery -> dedupe rebuilt (NFR-R3) | Integration | | |
| **P1-026** | Object storage unavailable -> pipeline halts (NFR-R2) | Integration | | |
| **P1-027** | Postgres unavailable -> pipeline halts (NFR-R2) | Integration | | |
| **P1-028** | Kafka unavailable -> outbox READY accumulates (NFR-R2) | Integration | | |
| **P1-029** | HealthRegistry per-component status (FR51–52) | Unit | | |
| **P1-030** | DegradedModeEvent structure (FR53) | Unit | | |
| **P1-031** | TelemetryDegradedEvent structure (FR67a) | Unit | | |
| **P1-032** | OTLP metrics exported (NFR-O1) | Integration | ASR-11 | |
| **P1-033** | OTLP Collector receives correct metrics (NFR-O1) | Integration | | |
| **P1-034** | Policy version stamps in CaseFile (FR60–62) | Unit | ASR-5 | |
| **P1-035** | Audit trail: CaseFile -> evidence -> gating -> action (NFR-T6) | Integration | | |
| **P1-036** | Hash chain: triage -> diagnosis -> linkage (ASR-8) | Integration | | |
| **P1-037** | Hash chain negative: corrupted hash detected (ASR-8) | Integration | R-08 | |
| **P1-038** | APP_ENV loads correct .env file (FR55) | Unit | | |
| **P1-039** | Integration mode switching OFF/LOG/MOCK/LIVE (FR56–57) | Unit | | |
| **P1-040** | Environment action caps (FR58) | Unit | ASR-9 | |
| **P1-041** | LIVE mode restricted in local env (FR59) | Unit | | |

**Total P1:** ~41 tests

---

### P2 (Medium)

**Criteria:** Secondary features + Low risk + Edge cases

| Test ID | Requirement | Test Level | Risk Link | Notes |
|---|---|---|---|---|
| **P2-001** | Registry reload on data change (FR16) | Integration | R-07 | |
| **P2-002** | LLM provenance check: evidence IDs exist (FR42) | Unit | | |
| **P2-003** | SN linkage.json fields (FR50) | Unit | | Phase 1B |
| **P2-004** | Structured logging: JSON, correlation_id (NFR-O3) | Unit | | |
| **P2-005** | Active config logged at startup (NFR-O4) | Unit | | |
| **P2-006** | Graceful shutdown (NFR-O6) | Integration | ASR-12 | |
| **P2-007** | Kerberos keytab path validation (NFR-S4) | Unit | | |

**Total P2:** ~7 tests

---

## Execution Strategy

**Philosophy:** Run everything in PRs if under 15 minutes. Defer only expensive/long-running tests.

### Every PR: pytest Unit + Fast Integration (~10 min)

**All functional tests:**

- All Unit tests (pytest -m "not integration")
- Fast integration tests (pytest -m "integration and not slow")
- Ruff lint (uv run ruff check) + format check (uv run ruff format --check)
- Total: ~60+ tests from P0, P1, P2

**Why run in PRs:** Fast feedback, testcontainers start once per session

### Nightly: Full Integration Suite (~30 min)

**All integration tests including testcontainers:**

- Full pytest run (all markers)
- Total: ~76 tests including all testcontainer-dependent tests

**Why defer to nightly:** Full testcontainers startup + multi-container coordination

### Weekly: Load + Chaos Tests (~60 min)

**Concurrency and failure simulation:**

- 100 concurrent cases (TS-016 / P0-009)
- Redis mid-cycle pause/unpause (TS-055 / P1-024)
- Extended degraded mode scenarios

**Why defer to weekly:** Resource-intensive, long-running, infrequent validation sufficient

---

## QA Effort Estimate

| Priority | Count | Effort Range | Notes |
|---|---|---|---|
| P0 | ~28 | ~30–45 hours | Invariants, contracts, gating — complex setup |
| P1 | ~41 | ~30–50 hours | Pipeline stages, integrations, operability |
| P2 | ~7 | ~5–10 hours | Edge cases, logging, governance |
| Infra | — | ~15–25 hours | Testcontainers setup, fixtures, conftest |
| **Total** | **~76** | **~80–130 hours** | **1 engineer, spread across phases** |

**Assumptions:**

- Includes test design, implementation, debugging, CI integration
- Excludes ongoing maintenance (~10% effort)
- Assumes test infrastructure (factories, fixtures) ready
- Phase 0: ~20–30 hours (invariants + degraded modes)
- Phase 1A: ~40–60 hours (remaining P0 + P1)
- Phase 1B: ~10–15 hours (SN-specific tests)

---

## Implementation Planning Handoff

| Work Item | Owner | Target Milestone | Dependencies/Notes |
|---|---|---|---|
| Testcontainers session fixtures (conftest.py) | Dev/QA | Phase 0 | Docker-in-Docker in CI |
| Pydantic model test factories | Dev/QA | Phase 0 | Frozen contract models must exist |
| Policy fixture YAML test data | Dev/QA | Phase 0 | Policy schemas must be defined |
| LLM stub fixture payloads | Pipeline Lead | Phase 0 | Blocked on TC-1 |
| Crash injection pattern for Invariant B2 | Pipeline Lead | Phase 0 | Blocked on TC-2 |
| Clock abstraction for scheduler | Pipeline Lead | Phase 0 | Blocked on TC-3 |
| OTLP Collector testcontainer config | Dev/QA | Phase 1A | Debug/file exporter for assertions |

---

## Tooling & Access

| Tool or Service | Purpose | Access Required | Status |
|---|---|---|---|
| Docker | Testcontainers runtime | Docker daemon in CI | Pending CI setup |
| MinIO container | Object storage tests | Public image | Ready |
| Postgres container | Outbox tests | Public image | Ready |
| Redis container | Cache/dedupe tests | Public image | Ready |
| Kafka + ZooKeeper containers | Event transport tests | Public images | Ready |
| OTLP Collector container | Meta-monitoring tests | Public image | Ready |

---

## Interworking & Regression

| Service/Component | Impact | Regression Scope | Validation Steps |
|---|---|---|---|
| **Prometheus** | Telemetry source — Evidence Builder depends on query results | Evidence collection tests (TS-001–004) | Verify EvidenceSnapshot matches expected structure from PromQL results |
| **Kafka** | Event transport — outbox publisher writes headers/excerpts | Outbox publish tests (TS-021) | Verify message schema and content on Kafka topic |
| **Object Storage (MinIO/S3)** | CaseFile SoR — all stages write here | CaseFile write tests (TS-012–016) | Verify write-once, hash chain, stage file structure |
| **Postgres** | Outbox durability — state machine persistence | Outbox state machine tests (TS-017–020) | Verify state transitions under normal and crash scenarios |
| **Redis** | Cache + dedupe — degradable dependency | Degraded mode tests (TS-054–056) | Verify NOTIFY-only cap and DegradedModeEvent under Redis failure |
| **PagerDuty** | PAGE action sink | Dispatch tests (TS-031) in MOCK mode | Verify trigger payload structure |
| **Slack** | NOTIFY action sink | Dispatch tests (TS-032) in MOCK mode | Verify notification payload with denylist applied |

**Regression test strategy:**

- All unit tests must pass before any PR merge
- All integration tests must pass nightly
- Contract regression tests (TS-047–048) catch unintended schema changes across all 12 frozen contracts
- Cross-component tests (full E2E hot path TS-035) validate end-to-end data flow

---

## Appendix A: Code Examples & Tagging

**pytest markers for selective execution:**

```python
import pytest

# P0 critical test — invariant verification
@pytest.mark.integration
class TestInvariantA:
    async def test_casefile_exists_before_kafka_header(self, minio_client, kafka_consumer):
        """Invariant A: CaseFile must exist in object storage before header on Kafka."""
        # ... trigger pipeline for test case ...

        # Consume Kafka header
        header = kafka_consumer.poll(timeout=10.0)
        assert header is not None

        # Verify CaseFile exists
        case_id = header.value()["case_id"]
        obj = minio_client.get_object("cases", f"{case_id}/triage.json")
        assert obj is not None

# P0 unit test — contract validation
class TestFrozenContracts:
    def test_gate_input_v1_is_frozen(self):
        """All frozen contracts must reject mutation."""
        gate_input = GateInputV1(case_id="test", env="prod", ...)
        with pytest.raises(ValidationError):
            gate_input.case_id = "modified"

    def test_gate_input_v1_round_trip(self):
        """Serialize -> deserialize produces identical model."""
        original = GateInputV1(case_id="test", env="prod", ...)
        json_bytes = original.model_dump_json()
        restored = GateInputV1.model_validate_json(json_bytes)
        assert original == restored
```

**Run specific markers:**

```bash
# Run only unit tests (fast, no containers)
uv run pytest -m "not integration"

# Run only integration tests
uv run pytest -m integration

# Run only slow/weekly tests
uv run pytest -m slow

# Run all tests
uv run pytest

# Lint + format check
uv run ruff check && uv run ruff format --check
```

---

## Appendix B: Knowledge Base References

- **Risk Governance**: `risk-governance.md` — Risk scoring methodology (P x I, 1-9 scale)
- **Test Levels Framework**: `test-levels-framework.md` — Unit/Integration/E2E selection guide
- **Test Quality**: `test-quality.md` — Definition of Done (deterministic, <300 lines, <1.5 min, self-cleaning)
- **ADR Quality Readiness Checklist**: `adr-quality-readiness-checklist.md` — 8-category, 29-criteria testability framework

---

**Generated by:** TEA Master Test Architect
**Workflow:** `_bmad/tea/testarch/test-design`
**Version:** 5.0 (Step-File Architecture)
