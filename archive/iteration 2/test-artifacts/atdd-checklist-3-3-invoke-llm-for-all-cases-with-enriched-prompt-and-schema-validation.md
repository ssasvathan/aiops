---
stepsCompleted:
  - step-01-preflight-and-context
  - step-02-generation-mode
  - step-03-test-strategy
  - step-04-generate-tests
  - step-04c-aggregate
  - step-05-validate-and-complete
lastStep: step-05-validate-and-complete
lastSaved: '2026-03-22'
workflowType: testarch-atdd
inputDocuments:
  - artifact/implementation-artifacts/3-3-invoke-llm-for-all-cases-with-enriched-prompt-and-schema-validation.md
  - artifact/implementation-artifacts/sprint-status.yaml
  - src/aiops_triage_pipeline/__main__.py
  - src/aiops_triage_pipeline/diagnosis/graph.py
  - src/aiops_triage_pipeline/diagnosis/prompt.py
  - src/aiops_triage_pipeline/integrations/llm.py
  - src/aiops_triage_pipeline/contracts/diagnosis_report.py
  - tests/unit/test_main.py
  - tests/unit/diagnosis/test_graph.py
  - tests/unit/diagnosis/test_prompt.py
  - tests/unit/integrations/test_llm.py
  - tests/atdd/fixtures/story_3_3_test_data.py
  - tests/atdd/test_story_3_3_invoke_llm_for_all_cases_with_enriched_prompt_and_schema_validation_red_phase.py
  - _bmad/tea/config.yaml
  - _bmad/tea/testarch/tea-index.csv
  - _bmad/tea/testarch/knowledge/data-factories.md
  - _bmad/tea/testarch/knowledge/component-tdd.md
  - _bmad/tea/testarch/knowledge/test-quality.md
  - _bmad/tea/testarch/knowledge/test-healing-patterns.md
  - _bmad/tea/testarch/knowledge/test-levels-framework.md
  - _bmad/tea/testarch/knowledge/test-priorities-matrix.md
  - _bmad/tea/testarch/knowledge/ci-burn-in.md
  - _bmad/tea/testarch/knowledge/overview.md
  - _bmad/tea/testarch/knowledge/api-request.md
  - _bmad/tea/testarch/knowledge/auth-session.md
  - _bmad/tea/testarch/knowledge/recurse.md
  - _bmad/tea/testarch/knowledge/pactjs-utils-overview.md
  - _bmad/tea/testarch/knowledge/pactjs-utils-consumer-helpers.md
  - _bmad/tea/testarch/knowledge/pactjs-utils-provider-verifier.md
  - _bmad/tea/testarch/knowledge/pactjs-utils-request-filter.md
  - _bmad/tea/testarch/knowledge/pact-mcp.md
---

# ATDD Checklist - Epic 3, Story 3.3: Invoke LLM for All Cases with Enriched Prompt and Schema Validation

**Date:** 2026-03-22
**Author:** Sas
**Primary Test Level:** Backend acceptance/unit (pytest)
**TDD Phase:** RED

## Story Summary

Story 3.3 removes legacy cold-path invocation gating and requires diagnosis invocation for every
case while enriching the prompt payload for better diagnosis quality and schema-safe handling.

**As an** operations responder  
**I want** every case to receive enriched diagnostic analysis  
**So that** follow-up troubleshooting starts with structured hypotheses and next checks

## Acceptance Criteria

1. Given a cold-path case is ready for diagnosis, when prompt construction runs, then prompt
   content includes full finding fields, topology/routing context, domain hints, and few-shot
   guidance, and invocation is performed regardless of environment, tier, or sustained flag.
2. Given the LLM returns a response, when diagnosis parsing executes, then output is validated
   against `DiagnosisReportV1` and invalid schema responses are treated as invocation failure conditions.

## Stack Detection / Mode

- `detected_stack`: backend (Python service with pytest; no browser UI test framework)
- `tea_execution_mode`: auto -> sequential (single-agent backend adaptation)
- Generation mode: AI generation (no browser recording)

## Test Strategy

- P0 tests pin FR39 all-case invocation semantics by asserting no eligibility suppression for
  local/TIER_1/non-sustained inputs.
- P0 tests pin FR40 prompt enrichment requirements for full finding semantics and routing/topology
  fields.
- P1 tests pin FR40 prompt guidance requirements (confidence calibration, fault-domain hints,
  deterministic few-shot context).
- P1 test pins Story 3.3 wiring requirement: `_cold_path_process_event()` must invoke diagnosis after
  context retrieval and evidence summary generation.
- No browser E2E tests are generated for backend-only scope.

## Failing Tests Created (RED Phase)

### Backend Acceptance Tests (5)

**File:** `tests/atdd/test_story_3_3_invoke_llm_for_all_cases_with_enriched_prompt_and_schema_validation_red_phase.py`

- `test_p0_meets_invocation_criteria_allows_non_prod_tier1_unsustained_cases`
  - **Status:** RED
  - **Failure:** `meets_invocation_criteria(...)` still returns `False` for local/TIER_1/non-sustained.
- `test_p0_spawn_task_invokes_for_non_prod_non_tier0_and_non_sustained_case`
  - **Status:** RED
  - **Failure:** `spawn_cold_path_diagnosis_task(...)` returns `None` for non-prod/TIER_1/non-sustained.
- `test_p0_prompt_contains_full_finding_fields_and_routing_context`
  - **Status:** RED
  - **Failure:** prompt omits required enriched fields (e.g., `severity`, `reason_codes`, `topic_role`, `routing_key`).
- `test_p1_prompt_contains_confidence_guidance_and_few_shot_example_block`
  - **Status:** RED
  - **Failure:** prompt lacks explicit confidence calibration + few-shot guidance content.
- `test_p1_process_event_invokes_diagnosis_path_for_every_case`
  - **Status:** RED
  - **Failure:** `_cold_path_process_event(...)` still ends at Story 3.2 stub log and does not call diagnosis path.

## Fixtures Created

- `tests/atdd/fixtures/story_3_3_test_data.py`
  - `build_case_header_event(...)`
  - `build_triage_excerpt(...)`

## Mock Requirements

- `_cold_path_process_event(...)` dependency calls are monkeypatched to isolate wiring expectations.
- No external LLM network calls are used in this RED-phase suite.
- No browser automation sessions were opened (backend-only story).

## Implementation Checklist

### Test: `test_p0_meets_invocation_criteria_allows_non_prod_tier1_unsustained_cases`

- [ ] Remove env/tier/sustained gating from invocation criteria.
- [ ] Ensure FR39 all-case invocation semantics are enforced for cold-path diagnosis.

### Test: `test_p0_spawn_task_invokes_for_non_prod_non_tier0_and_non_sustained_case`

- [ ] Update launcher behavior so diagnosis task is created for all cases.
- [ ] Remove or bypass old eligibility short-circuit in spawn path.

### Test: `test_p0_prompt_contains_full_finding_fields_and_routing_context`

- [ ] Enrich `build_llm_prompt(...)` with full finding fields:
      `finding_id`, `name`, `severity`, `reason_codes`, `evidence_required`, `is_primary`, `is_anomalous`.
- [ ] Include explicit `topic_role` and `routing_key` prompt content.

### Test: `test_p1_prompt_contains_confidence_guidance_and_few_shot_example_block`

- [ ] Add confidence calibration guidance to system instructions.
- [ ] Add deterministic fault-domain guidance examples.
- [ ] Add deterministic few-shot block for output consistency.

### Test: `test_p1_process_event_invokes_diagnosis_path_for_every_case`

- [ ] Replace Story 3.2 stub boundary in `_cold_path_process_event(...)` with diagnosis invocation.
- [ ] Pass required composition-root dependencies (LLM client, denylist, health registry,
      timeout, alert evaluator, object store and triage hash context).
- [ ] Preserve fail-open consumer behavior: per-message failure logs warning and continues.

## Running Tests

```bash
uv run pytest -q tests/atdd/test_story_3_3_invoke_llm_for_all_cases_with_enriched_prompt_and_schema_validation_red_phase.py
```

## Test Execution Evidence

**Command:** `uv run pytest -q tests/atdd/test_story_3_3_invoke_llm_for_all_cases_with_enriched_prompt_and_schema_validation_red_phase.py`

**Result:**

```text
FFFFF
5 failed in 0.69s
```

**Failure indicators:**

- Invocation criteria still filters non-prod/TIER_1/non-sustained cases.
- Spawn launcher still suppresses diagnosis task for non-prod/TIER_1/non-sustained cases.
- Prompt missing full finding/routing enrichment fields.
- Prompt missing explicit confidence calibration and few-shot guidance text.
- Processor boundary still does not invoke diagnosis path.

## Generated Artifacts

- `artifact/test-artifacts/tea-atdd-api-tests-2026-03-23T02-33-48Z.json`
- `artifact/test-artifacts/tea-atdd-e2e-tests-2026-03-23T02-33-48Z.json`
- `artifact/test-artifacts/tea-atdd-summary-2026-03-23T02-33-48Z.json`
- `artifact/test-artifacts/atdd-checklist-3-3-invoke-llm-for-all-cases-with-enriched-prompt-and-schema-validation.md`

## Validation Notes

- Prerequisites satisfied: Story ACs are explicit and testable; backend pytest framework is present.
- Core + backend + API-only Playwright Utils + Pact.js/Pact-MCP knowledge fragments were loaded.
- Temp ATDD artifacts were stored under `artifact/test-artifacts/`.
- No browser CLI/MCP sessions were used; no cleanup required.

## Completion Summary

ATDD RED phase is complete for Story 3.3 with 5 deterministic failing backend acceptance tests
covering all-case invocation semantics, prompt enrichment requirements, and cold-path wiring to
invoke diagnosis.

Sprint status updated: `3-3-invoke-llm-for-all-cases-with-enriched-prompt-and-schema-validation: in-progress`
