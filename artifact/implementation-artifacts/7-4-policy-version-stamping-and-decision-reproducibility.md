# Story 7.4: Policy Version Stamping & Decision Reproducibility

Status: review

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As an auditor,
I want every CaseFile to record the exact policy versions used and historical gating decisions to be reproducible,
so that I can verify any past decision was correct given the evidence and policies active at that time (FR60, FR61).

## Acceptance Criteria

1. **Given** a CaseFile has been written with a gating decision
   **When** the CaseFile is inspected
   **Then** it records exact policy versions: `rulebook_version`, `peak_policy_version`, `prometheus_metrics_contract_version`, `exposure_denylist_version`, `diagnosis_policy_version` (FR60)

2. **And** given the same `gate_input` snapshot and the same rulebook version, re-evaluating the Rulebook through a dedicated `reproduce_gate_decision()` function produces an identical `ActionDecision.v1` (FR61)

3. **And** a regression test suite exercises decision reproducibility for representative cases covering: OBSERVE (no anomaly), NOTIFY (evidence-sufficient, confidence-low), env-capped action, evidence-insufficient gate (AG2 fail), sustained-threshold fail (AG4), and prod TIER_0 postmortem trigger (AG6)

4. **And** the audit flow is demonstrable via a `build_audit_trail()` function: retrieve CaseFile → extract evidence snapshot → extract gate rule IDs + reason codes → extract policy versions + SHA-256 hash (NFR-T6)

5. **And** `CaseFileTriageV1` provably contains all audit-required fields: all evidence rows used, `action_decision.gate_rule_ids`, `action_decision.gate_reason_codes`, all five `policy_versions` fields, and `triage_hash` as 64-char SHA-256

6. **And** unit tests verify: all policy version fields non-empty in assembled CaseFile, deterministic re-evaluation produces field-for-field identical `ActionDecisionV1` output, audit trail completeness for all required fields per NFR-T6

## Tasks / Subtasks

- [x] Task 1: Create `src/aiops_triage_pipeline/audit/` package with `replay.py` and `__init__.py` (AC: 2, 4)
  - [x] Add `src/aiops_triage_pipeline/audit/__init__.py` (empty or re-exporting public API)
  - [x] Add `src/aiops_triage_pipeline/audit/replay.py` with two public functions:
    - `reproduce_gate_decision(casefile: CaseFileTriageV1, rulebook: RulebookV1) -> ActionDecisionV1` — validates rulebook version matches `casefile.policy_versions.rulebook_version`, then calls `evaluate_rulebook_gates(gate_input=casefile.gate_input, rulebook=rulebook, dedupe_store=None)` for deterministic replay
    - `build_audit_trail(casefile: CaseFileTriageV1) -> dict[str, Any]` — returns a structured dict with all NFR-T6 required fields: `case_id`, `triage_timestamp`, `evidence_rows` (count + status_map), `gate_rule_ids`, `gate_reason_codes`, `final_action`, `policy_versions` (all 5 keys), `triage_hash`

- [x] Task 2: Add unit tests for `reproduce_gate_decision()` (AC: 2, 3, 6)
  - [x] Create `tests/unit/audit/__init__.py`
  - [x] Create `tests/unit/audit/test_decision_reproducibility.py` with parametrized regression suite:
    - OBSERVE path: low-confidence, no sustained, no anomaly findings
    - NOTIFY path: medium-confidence, evidence-present, env=dev (cap=NOTIFY)
    - Env-capped path: PAGE proposed but APP_ENV=dev caps to NOTIFY via AG1
    - AG2 fail path: evidence status UNKNOWN for required metric, gate caps action
    - AG4 fail path: confidence below floor — action downgraded
    - AG6 postmortem path: prod + TIER_0 + peak + sustained — `postmortem_required=True`
  - [x] Each test: build `GateInputV1` + call `evaluate_rulebook_gates(dedupe_store=None)` to get `expected`, assemble minimal `CaseFileTriageV1` with that `action_decision`, call `reproduce_gate_decision(casefile, rulebook)`, assert all fields equal
  - [x] Add test for version mismatch: `reproduce_gate_decision()` raises `ValueError` when rulebook version differs from `casefile.policy_versions.rulebook_version`

- [x] Task 3: Add unit tests for `build_audit_trail()` and audit trail completeness (AC: 4, 5, 6)
  - [x] In `tests/unit/audit/test_decision_reproducibility.py` (or a separate `test_audit_trail.py`):
    - Assert `build_audit_trail()` returns all required keys: `case_id`, `triage_timestamp`, `evidence_rows`, `gate_rule_ids`, `gate_reason_codes`, `final_action`, `policy_versions`, `triage_hash`
    - Assert `policy_versions` sub-dict contains all 5 non-empty strings
    - Assert `triage_hash` matches `re.fullmatch(r"[0-9a-f]{64}", hash)` (64-char SHA-256)
    - Assert `gate_rule_ids` is a tuple/list containing all of AG0–AG6
    - Assert `gate_reason_codes` is present (may be empty tuple for clean paths)

- [x] Task 4: Extend `tests/unit/pipeline/stages/test_casefile.py` with explicit FR60/NFR-T6 assertions (AC: 1, 5, 6)
  - [x] Add test `test_policy_versions_all_fields_populated`: assemble a full casefile and assert each of the 5 `policy_versions` fields is non-empty string
  - [x] Add test `test_casefile_audit_trail_fields_complete`: assert `gate_input` is present, `action_decision.gate_rule_ids` is non-empty tuple, `action_decision.gate_reason_codes` is tuple, `evidence_snapshot.rows` is present, `triage_hash` is 64-char hex

- [x] Task 5: Run quality gates with zero-skip posture (AC: 1–6)
  - [x] `uv run ruff check`
  - [x] `uv run pytest -q -m "not integration"`
  - [x] `TESTCONTAINERS_RYUK_DISABLED=true DOCKER_HOST=unix://$HOME/.docker/desktop/docker.sock uv run pytest -q -rs`
  - [x] Verify full run reports `0 skipped`

## Dev Notes

### Developer Context Section

- Story key: `7-4-policy-version-stamping-and-decision-reproducibility`
- Story ID: `7.4`
- Epic context: Epic 7 governance, audit, and operational observability. Story 7.4 closes the audit loop by formalizing the reproducibility layer over the existing deterministic gating and CaseFile infrastructure built in Epics 4 and 5.
- Dependency context:
  - The `CaseFilePolicyVersions` model and `assemble_casefile_triage_stage()` already stamp all 5 policy versions correctly — this is **not** what needs implementing. The implementation gap is the **replay and audit trail layer** on top of what exists.
  - `evaluate_rulebook_gates()` in `pipeline/stages/gating.py` is already deterministic. Story 7.4 formalizes this property via a dedicated `reproduce_gate_decision()` function and regression test suite.
  - The existing integration test `test_action_decision_determinism` in `tests/integration/test_pipeline_e2e.py` validates two independent live runs agree, but does NOT test CaseFile-based replay from stored artifacts.

Implementation intent:
- Create a thin `audit/` package whose sole purpose is to expose the reproducibility and audit-trail functions. Do **not** duplicate gating logic — call `evaluate_rulebook_gates()` directly.
- The regression test suite should be pure unit tests (no containers, no Redis) using `dedupe_store=None` so AG5 does not introduce non-deterministic state.

### Technical Requirements

1. **`reproduce_gate_decision()` contract:**
   - Signature: `reproduce_gate_decision(casefile: CaseFileTriageV1, rulebook: RulebookV1) -> ActionDecisionV1`
   - Must validate: `str(rulebook.version) == casefile.policy_versions.rulebook_version` — raise `ValueError` with descriptive message if mismatch
   - Must call: `evaluate_rulebook_gates(gate_input=casefile.gate_input, rulebook=rulebook, dedupe_store=None)`
   - Must NOT pass a `dedupe_store` — deterministic replay excludes storm-dedup transient state (AG5 dedupe depends on Redis TTL windows that cannot be recreated from a stored CaseFile)
   - Returns: `ActionDecisionV1` — caller compares against `casefile.action_decision`

2. **`build_audit_trail()` contract:**
   - Signature: `build_audit_trail(casefile: CaseFileTriageV1) -> dict[str, Any]`
   - Returns a plain dict (not a Pydantic model) — callers can serialize to JSON for operator review
   - Required keys and sources:
     - `case_id` ← `casefile.case_id`
     - `triage_timestamp` ← `casefile.triage_timestamp.isoformat()`
     - `evidence_rows` ← `[{"metric_key": r.metric_key, "value": r.value, "scope": list(r.scope)} for r in casefile.evidence_snapshot.rows]`
     - `evidence_status_map` ← `dict(casefile.evidence_snapshot.evidence_status_map)` (string keys, EvidenceStatus enum values serialized as strings)
     - `gate_rule_ids` ← `list(casefile.action_decision.gate_rule_ids)`
     - `gate_reason_codes` ← `list(casefile.action_decision.gate_reason_codes)`
     - `final_action` ← `casefile.action_decision.final_action.value`
     - `policy_versions` ← `casefile.policy_versions.model_dump()`
     - `triage_hash` ← `casefile.triage_hash`

3. **`diagnosis_policy_version` — what it is:**
   - The `diagnosis_policy_version` field is a string passed at startup by `__main__.py` — typically the LangGraph version (e.g., `"langgraph-1.0.9"`) or a diagnosis prompt template version. In tests, use `"v1"` as the canonical stub value.
   - Story 7.4 does NOT need to change how this version is sourced — the assembly already works correctly.

4. **AG5 and reproducibility semantics:**
   - Calling `reproduce_gate_decision()` with `dedupe_store=None` means AG5 will always PASS (no storm dedup). If the original decision was OBSERVE due to AG5 dedup, the replayed decision may differ at AG5. This is expected behavior — the audit function's purpose is to verify evidence-based determinism, not storm-dedup state reconstruction.
   - Tests should use scenarios where AG5 would not fire (unique fingerprints, dedupe_store=None) to test the pure policy-evidence reproducibility path.

5. **Policy version assertion in `reproduce_gate_decision()`:**
   - `RulebookV1.version` is an `int` — cast to `str` for comparison: `str(rulebook.version)`
   - The stored `casefile.policy_versions.rulebook_version` is already a string (e.g., `"1"`)

### Architecture Compliance

- Keep the `audit/` package as a leaf: it may import from `contracts/`, `models/`, and `pipeline/stages/gating.py` — but nothing in `pipeline/`, `health/`, `outbox/`, or `integrations/` should import from `audit/`
- Do NOT introduce FastAPI, HTTP endpoints, or CLI commands for this story — the audit functions are Python callables only
- Preserve existing `evaluate_rulebook_gates()` signature — do not modify it for this story
- Do not add new fields to `CaseFileTriageV1` or `CaseFilePolicyVersions` — all required fields already exist
- Do not modify `assemble_casefile_triage_stage()` — it already stamps all versions correctly
- Maintain frozen model discipline: `CaseFileTriageV1` and all contract models are `frozen=True`

### Library / Framework Requirements

Pinned versions to keep (no new dependencies needed):
- `pydantic==2.12.5` — use `model_dump()` for `CaseFilePolicyVersions` serialization in `build_audit_trail()`
- No new libraries required — `audit/replay.py` only imports from existing project modules

Implementation guidance:
- Import `evaluate_rulebook_gates` from `aiops_triage_pipeline.pipeline.stages.gating`
- Import `CaseFileTriageV1`, `CaseFilePolicyVersions` from `aiops_triage_pipeline.models.case_file`
- Import `RulebookV1` from `aiops_triage_pipeline.contracts.rulebook`
- Import `ActionDecisionV1` from `aiops_triage_pipeline.contracts.action_decision`

### File Structure Requirements

New files to create:
- `src/aiops_triage_pipeline/audit/__init__.py`
- `src/aiops_triage_pipeline/audit/replay.py`
- `tests/unit/audit/__init__.py`
- `tests/unit/audit/test_decision_reproducibility.py`

Existing files to touch (extend tests only):
- `tests/unit/pipeline/stages/test_casefile.py` — add 2 tests for FR60/NFR-T6 completeness assertions

Files to NOT touch:
- `src/aiops_triage_pipeline/models/case_file.py` — already correct
- `src/aiops_triage_pipeline/pipeline/stages/casefile.py` — already correct
- `src/aiops_triage_pipeline/pipeline/stages/gating.py` — call it, don't change it
- `src/aiops_triage_pipeline/contracts/*.py` — all frozen, do not modify

### Testing Requirements

Minimum coverage for the reproducibility regression suite (all pure unit tests, no containers):

| Test case | Scenario | Expected `final_action` | AG5 notes |
|-----------|----------|------------------------|-----------|
| OBSERVE baseline | Low confidence, no anomaly findings, `evidence_status_map` all PRESENT | OBSERVE | dedupe_store=None |
| NOTIFY-capped (dev) | PAGE proposed, env=dev → AG1 caps to NOTIFY | NOTIFY | dedupe_store=None |
| Evidence insufficient (AG2) | Required metric UNKNOWN, AG2 caps action | NOTIFY or lower | dedupe_store=None |
| Sustained fail (AG4) | `sustained=False`, confidence below floor | cap applied | dedupe_store=None |
| AG6 postmortem | env=prod, TIER_0, peak=True, sustained=True | PAGE + postmortem_required | dedupe_store=None |
| Version mismatch | Rulebook version differs from casefile stamp | ValueError raised | n/a |

Invariants each test must assert after calling `reproduce_gate_decision()`:
- `replayed.final_action == stored.final_action` (when dedupe_store=None and original also used None)
- `replayed.gate_rule_ids == stored.gate_rule_ids`
- `replayed.env_cap_applied == stored.env_cap_applied`
- `replayed.postmortem_required == stored.postmortem_required`

For `build_audit_trail()`:
- All required keys present in returned dict
- `policy_versions` dict contains exactly 5 non-empty string values
- `triage_hash` matches `^[0-9a-f]{64}$`
- `gate_rule_ids` contains all 7 gate IDs (AG0–AG6) for happy-path cases

Regression and integration expectations:
- All existing tests in `test_casefile.py`, `test_gating.py`, and `test_pipeline_e2e.py` must pass without modification
- No new integration tests required for this story (the integration layer is already covered by e2e tests including `test_action_decision_determinism`)
- Full regression must remain zero-skip

Required quality gate commands:
- `uv run ruff check`
- `uv run pytest -q -m "not integration"`
- `TESTCONTAINERS_RYUK_DISABLED=true DOCKER_HOST=unix://$HOME/.docker/desktop/docker.sock uv run pytest -q -rs`

### Previous Story Intelligence

From Story 7.3 (`7-3-alerting-rules-and-component-health-thresholds.md`):
- No direct dependency. Story 7.3 added alert evaluation logic that is orthogonal to this story's audit/reproducibility layer.
- Quality gate posture established: zero-skip, no ruff violations. Maintain.

From Stories 4.1–4.3 (CaseFile assembly, write-once, append-only stages):
- `CaseFileTriageV1` with `policy_versions`, `gate_input`, `action_decision`, `triage_hash` is fully implemented and tested
- `assemble_casefile_triage_stage()` in `pipeline/stages/casefile.py:58` stamps all 5 policy versions — do not re-implement
- `compute_casefile_triage_hash()` produces the 64-char SHA-256 — do not re-implement

From Story 5.1–5.9 (Rulebook gate engine):
- `evaluate_rulebook_gates()` in `pipeline/stages/gating.py:71` is the authoritative deterministic evaluator
- `dedupe_store: GateDedupeStoreProtocol | None = None` — passing `None` skips AG5 dedup, producing deterministic replay
- `_EvaluationState` internal, all gate logic is pure function over `gate_input` and `rulebook`

### Git Intelligence Summary

Recent relevant commits:
- `8f7886a` (`fix(story-7.3): resolve code review findings and sync status`) — final Epic 7 operational layer; Story 7.4 begins the audit/governance layer
- `463da94` (`feat(story-7.3): implement operational alert policy and runtime rule evaluation`) — confirms alert infra complete, no conflicts with audit module
- `50614ad` (`chore: mark epic 6 done in sprint status`) — LLM/diagnosis layer complete, `diagnosis_policy_version` stamping confirmed working

Actionable guidance:
- The `audit/` package is entirely new — no existing code conflicts
- Keep `audit/replay.py` minimal (two functions, ~50 lines total)
- The regression test suite is the substantive deliverable — invest in comprehensive parametrized cases

### Latest Tech Information

Research timestamp: 2026-03-08.

- Pydantic 2.12.5: `model_dump()` on frozen models returns a plain dict; use `mode="json"` only if you need enum values as strings (required for `evidence_status_map` values in `build_audit_trail()`)
- `str(rulebook.version)` is safe — `RulebookV1.version` is typed as `int` per `contracts/rulebook.py`; the stored `CaseFilePolicyVersions.rulebook_version` is always a string
- No dependency changes needed — all required types are already imported in existing modules

### Project Context Reference

Applied rules from `artifact/project-context.md`:
- Deterministic guardrails remain authoritative: `reproduce_gate_decision()` must not alter stored decisions, only replay them
- Contract-first: do not add fields to frozen models without a contract revision
- Change locality + traceability: add `audit/` package + tests in same changeset; do not touch unrelated modules
- Never skip regression in quality gates: zero-skip discipline maintained
- Structured logging: if adding any logging in `replay.py`, use `get_logger()` from `aiops_triage_pipeline.logging.setup`

### Project Structure Notes

- New `audit/` package sits at `src/aiops_triage_pipeline/audit/` — consistent with existing domain packages (`health/`, `denylist/`, `diagnosis/`)
- Import boundary: `audit/` may import from `contracts/`, `models/`, `pipeline/stages/gating.py` only
- Test location: `tests/unit/audit/` — mirrors source tree per project convention
- No `conftest.py` needed in `tests/unit/audit/` — use direct fixture construction in each test

### References

- [Source: `artifact/planning-artifacts/epics.md` — Story 7.4 acceptance criteria (FR60, FR61, NFR-T6)]
- [Source: `src/aiops_triage_pipeline/models/case_file.py` — `CaseFilePolicyVersions`, `CaseFileTriageV1`]
- [Source: `src/aiops_triage_pipeline/pipeline/stages/casefile.py:58` — `assemble_casefile_triage_stage()` policy version stamping]
- [Source: `src/aiops_triage_pipeline/pipeline/stages/gating.py:71` — `evaluate_rulebook_gates()` deterministic evaluator]
- [Source: `src/aiops_triage_pipeline/contracts/rulebook.py` — `RulebookV1.version` (int), gate IDs AG0–AG6]
- [Source: `src/aiops_triage_pipeline/contracts/action_decision.py` — `ActionDecisionV1` fields]
- [Source: `src/aiops_triage_pipeline/contracts/gate_input.py` — `GateInputV1` fields]
- [Source: `tests/integration/test_pipeline_e2e.py:704` — `test_action_decision_determinism` (existing integration baseline)]
- [Source: `tests/integration/test_pipeline_e2e.py:680` — policy version assertions in e2e test]
- [Source: `tests/unit/pipeline/stages/test_casefile.py` — existing casefile assembly tests]
- [Source: `artifact/project-context.md` — implementation guardrails and testing discipline]

## Dev Agent Record

### Agent Model Used

claude-sonnet-4-6

### Debug Log References

- Sprint status discovery selected first backlog story `7-4-policy-version-stamping-and-decision-reproducibility`
- Core context analyzed from:
  - `artifact/planning-artifacts/epics.md` — Epic 7, Story 7.4 complete acceptance criteria
  - `artifact/planning-artifacts/architecture.md` — architectural boundaries and patterns
  - `artifact/project-context.md` — implementation guardrails
  - `artifact/implementation-artifacts/7-3-alerting-rules-and-component-health-thresholds.md` — previous story intelligence
- Source code analyzed:
  - `src/aiops_triage_pipeline/models/case_file.py` — `CaseFilePolicyVersions` (all 5 fields confirmed)
  - `src/aiops_triage_pipeline/pipeline/stages/casefile.py` — `assemble_casefile_triage_stage()` confirmed stamps all versions
  - `src/aiops_triage_pipeline/pipeline/stages/gating.py` — `evaluate_rulebook_gates()` confirmed deterministic
  - `tests/integration/test_pipeline_e2e.py` — existing determinism and policy version presence tests
  - `tests/unit/pipeline/stages/test_casefile.py` — existing unit tests to extend
- Key insight: all model and assembly infrastructure is complete; Story 7.4's implementation gap is the `audit/replay.py` module and the reproducibility regression test suite

### Completion Notes List

- Created `src/aiops_triage_pipeline/audit/__init__.py` exporting `reproduce_gate_decision` and `build_audit_trail`.
- Created `src/aiops_triage_pipeline/audit/replay.py` (~70 lines): thin leaf package calling `evaluate_rulebook_gates(dedupe_store=None)` for deterministic replay and extracting NFR-T6 audit trail fields.
- Created `tests/unit/audit/__init__.py` (empty).
- Created `tests/unit/audit/test_decision_reproducibility.py` with 15 tests: 6 reproduce_gate_decision regression scenarios (OBSERVE, NOTIFY-capped dev, AG2 fail, AG4 fail, AG6 postmortem, version mismatch) + 9 build_audit_trail completeness assertions.
- Extended `tests/unit/pipeline/stages/test_casefile.py` with 2 new FR60/NFR-T6 tests.
- Quality gates: ruff clean, 710 unit tests pass (0 skipped), 729 full regression tests pass (0 skipped).
- Key design decision: test rulebook uses AG5 with no `on_store_error` effect so `dedupe_store=None` is a no-op for non-OBSERVE actions, enabling PAGE to survive to AG6 in postmortem test.

### File List

- `src/aiops_triage_pipeline/audit/__init__.py` (new)
- `src/aiops_triage_pipeline/audit/replay.py` (new)
- `tests/unit/audit/__init__.py` (new)
- `tests/unit/audit/test_decision_reproducibility.py` (new)
- `tests/unit/pipeline/stages/test_casefile.py` (modified — 2 tests added)
- `artifact/implementation-artifacts/sprint-status.yaml` (modified — status in-progress)
- `artifact/implementation-artifacts/7-4-policy-version-stamping-and-decision-reproducibility.md` (modified — tasks checked, status updated)

## Change Log

- 2026-03-08: Created Story 7.4 implementation-ready context file with audit/replay module design, reproducibility test matrix, architecture compliance, and developer guardrails.
- 2026-03-08: Implemented Story 7.4 — created `audit/` package with `reproduce_gate_decision()` and `build_audit_trail()`, 6-scenario reproducibility regression suite, 9 audit trail completeness tests, 2 FR60/NFR-T6 casefile assertions. Full regression 729/729 pass, 0 skipped.
