---
stepsCompleted:
  - step-01-preflight-and-context
  - step-02-generation-mode
  - step-03-test-strategy
  - step-04-generate-tests
  - step-04c-aggregate
  - step-05-validate-and-complete
lastStep: step-05-validate-and-complete
lastSaved: '2026-04-05'
inputDocuments:
  - artifact/implementation-artifacts/2-2-baseline-deviation-finding-model.md
  - _bmad/tea/config.yaml
  - src/aiops_triage_pipeline/baseline/models.py
  - src/aiops_triage_pipeline/models/anomaly.py
  - tests/unit/baseline/test_computation.py
  - tests/unit/baseline/test_client.py
  - tests/unit/pipeline/stages/test_anomaly.py
  - pyproject.toml
  - _bmad/tea/testarch/knowledge/test-quality.md
  - _bmad/tea/testarch/knowledge/data-factories.md
---

# ATDD Checklist: Story 2.2 — BASELINE_DEVIATION Finding Model

## TDD Red Phase (Current State)

**Status: RED — Tests FAIL (feature not implemented yet)**

- Unit Tests: 21 tests collected (all fail at import — `ImportError: cannot import name 'BaselineDeviationContext'`)
- E2E Tests: N/A — backend stack, no UI
- 0 tests skipped

## Stack Detection

- `detected_stack` = `backend` (Python, `pyproject.toml`, pydantic v2)
- Test framework: `pytest 9.0.2`, `pytest-asyncio 1.3.0`, `asyncio_mode=auto`
- No browser testing needed

## Generation Mode

- AI generation (backend stack; no browser recording)

## Test Strategy

| Test | Level | Priority | AC |
|------|-------|----------|----|
| `test_baseline_deviation_context_fields` | Unit | P0 | AC1 |
| `test_baseline_deviation_context_low_direction` | Unit | P0 | AC1 |
| `test_baseline_deviation_context_is_frozen` | Unit | P0 | AC1 |
| `test_baseline_deviation_context_frozen_blocks_direction_mutation` | Unit | P1 | AC1 |
| `test_baseline_deviation_context_serialization_round_trip` | Unit | P0 | AC1 |
| `test_baseline_deviation_context_invalid_direction` | Unit | P0 | AC1 |
| `test_baseline_deviation_context_invalid_direction_empty_string` | Unit | P1 | AC1 |
| `test_baseline_deviation_context_time_bucket_is_tuple` | Unit | P0 | AC1 |
| `test_baseline_deviation_stage_output_fields` | Unit | P0 | AC2 |
| `test_baseline_deviation_stage_output_empty_findings` | Unit | P0 | AC2 |
| `test_baseline_deviation_stage_output_is_frozen` | Unit | P0 | AC2 |
| `test_baseline_deviation_stage_output_serialization_round_trip` | Unit | P0 | AC2 |
| `test_anomaly_finding_baseline_deviation_family_accepted` | Unit | P0 | AC3 |
| `test_anomaly_finding_baseline_deviation_family_invalid_raises` | Unit | P1 | AC3 |
| `test_anomaly_finding_with_baseline_context` | Unit | P0 | AC3, AC4 |
| `test_anomaly_finding_baseline_context_provides_full_replay_context` | Unit | P1 | AC4 |
| `test_anomaly_finding_baseline_context_defaults_none` | Unit | P0 | AC5 |
| `test_anomaly_finding_existing_families_unchanged` | Unit | P0 | AC5 |
| `test_anomaly_finding_explicit_none_baseline_context` | Unit | P1 | AC5 |

**Total tests: 19**

## Acceptance Criteria Coverage

| AC | Covered | Tests |
|----|---------|-------|
| AC1: BaselineDeviationContext frozen Pydantic model | ✅ | 8 tests |
| AC2: BaselineDeviationStageOutput frozen Pydantic model | ✅ | 4 tests |
| AC3: AnomalyFinding with BASELINE_DEVIATION family | ✅ | 4 tests |
| AC4: Full replay context fields (NFR-A2) | ✅ | 2 tests |
| AC5: Backward compatibility (existing families) | ✅ | 3 tests |
| AC6: Covered by AC1+AC2+AC3+AC4+AC5 above | ✅ | all above |
| AC7: Documentation updates | N/A | (not a code test) |

## TDD Red Phase Failure Confirmation

```
ERROR collecting tests/unit/baseline/test_models.py
ImportError: cannot import name 'BaselineDeviationContext'
  from 'aiops_triage_pipeline.baseline.models'
  (/home/sas/workspace/aiops/src/aiops_triage_pipeline/baseline/models.py)
```

**This is INTENTIONAL — correct TDD red phase.**

The failure proves:
1. `baseline/models.py` is still a placeholder stub — needs Task 1 implementation
2. `models/anomaly.py` needs Task 2 extension (BASELINE_DEVIATION Literal + baseline_context field)
3. Tests assert EXPECTED behavior that will pass once implementation is complete

## Generated Files

- `tests/unit/baseline/test_models.py` — 19 unit tests (NEW FILE — TDD RED PHASE)
- `artifact/test-artifacts/atdd-checklist-2-2-baseline-deviation-finding-model.md` — this file

## Quality Checklist

- [x] No `@pytest.mark.xfail` or `@pytest.mark.skip` (project rule: 0-skipped-tests)
- [x] All imports at module level (retro L4, ruff I001)
- [x] `ruff check` passes cleanly (E, F, I, N, W)
- [x] Tests use `pytest.raises(Exception)` for frozen immutability (ValidationError in Pydantic v2)
- [x] Tests use `pytest.raises(ValidationError)` for Literal validation errors
- [x] Field type assertions use `isinstance()` (retro L2)
- [x] Tests assert EXPECTED behavior — not placeholders
- [x] Each test has a clear docstring with priority tag and AC reference
- [x] No test file modifications to existing tests

## Next Steps (TDD Green Phase)

After Story 2.2 implementation (Tasks 1–2):

1. Implement `BaselineDeviationContext` and `BaselineDeviationStageOutput` in `src/aiops_triage_pipeline/baseline/models.py`
2. Extend `AnomalyFinding` in `src/aiops_triage_pipeline/models/anomaly.py` (additive-only)
3. Run `uv run pytest tests/unit/baseline/test_models.py -v` → verify all 19 tests PASS
4. Run `uv run pytest tests/unit/ -q` → confirm 0 regressions
5. Proceed with Task 3.6 (ruff check on test file — already clean)

## Implementation Notes for Story 2.2 Dev Agent

- `baseline/models.py` needs: `BaselineDeviationContext(BaseModel, frozen=True)` and `BaselineDeviationStageOutput(BaseModel, frozen=True)` — see Dev Notes canonical implementations
- `models/anomaly.py` needs: `from __future__ import annotations`, TYPE_CHECKING guard for `BaselineDeviationContext`, `"BASELINE_DEVIATION"` added to `AnomalyFamily` Literal, `baseline_context: "BaselineDeviationContext | None" = None` field
- Circular import is resolved via TYPE_CHECKING guard (see Dev Notes critical section)
