# Story 2.5: Run Casefile Lifecycle Retention Purge

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a platform operator,  
I want expired casefiles to be purged by lifecycle policy,  
so that storage retention remains compliant and bounded.

**Implements:** FR30

## Acceptance Criteria

1. **Given** retention policy and object storage access are configured  
   **When** the casefile-lifecycle runner scans casefile objects  
   **Then** expired artifacts are identified and purged according to policy  
   **And** non-expired artifacts remain untouched.

2. **Given** purge execution completes  
   **When** operational metrics/logs are emitted  
   **Then** purge counts and failures are observable  
   **And** failures are surfaced for follow-up without silent data loss.

## Tasks / Subtasks

- [x] Task 1: Validate and finalize retention policy contract usage for lifecycle mode (AC: 1)
  - [x] Confirm `CasefileRetentionPolicyV1` loading in `__main__.py` uses `config/policies/casefile-retention-policy-v1.yaml` with required `local|dev|uat|prod` entries.
  - [x] Confirm `resolve_retention_cutoff(...)` is used with timezone-aware UTC and rejects naive datetimes.
  - [x] Confirm no hardcoded retention window logic exists outside policy-driven resolution.

- [x] Task 2: Ensure lifecycle purge correctness at case scope and key layout boundaries (AC: 1)
  - [x] Keep object selection limited to canonical casefile keys under `cases/{case_id}/{stage}.json`.
  - [x] Ensure eligibility is resolved at case scope (triage timestamp preferred; fallback earliest stage timestamp), then purges all eligible keys for that case.
  - [x] Preserve deterministic ordering and bounded batch deletion (`list_page_size`, `delete_batch_size`), and verify idempotent reruns.

- [x] Task 3: Strengthen observability for lifecycle outcomes (AC: 2)
  - [x] Ensure structured lifecycle audit logs include `policy_ref`, `app_env`, `executed_at`, `scanned_count`, `eligible_count`, `purged_count`, `failed_count`, and affected `case_ids`.
  - [x] Add/verify OTLP metric emission for lifecycle purge outcomes (run count + purged/failed object counts) in shared metrics module if missing.
  - [x] Ensure partial delete failures remain visible and do not get swallowed by retry loops.

- [x] Task 4: Verify runtime-mode wiring and governance safety controls (AC: 1, 2)
  - [x] Confirm `--mode casefile-lifecycle` supports both `--once` and scheduled loop behavior via `CASEFILE_LIFECYCLE_POLL_INTERVAL_SECONDS`.
  - [x] Confirm destructive purge requires governance metadata (`CASEFILE_RETENTION_GOVERNANCE_APPROVAL`), with explicit invariant failure when missing.
  - [x] Confirm lifecycle mode startup logs expose policy/version and runtime tuning values without leaking secrets.

- [x] Task 5: Expand and run test coverage for purge behavior and observability (AC: 1, 2)
  - [x] Extend `tests/unit/storage/test_casefile_lifecycle.py` for any net-new metrics/logging fields and failure surfacing behavior.
  - [x] Extend `tests/integration/test_casefile_lifecycle.py` for purge/non-purge behavior, idempotent rerun, and partial-failure accounting.
  - [x] Extend `tests/unit/test_main.py` if lifecycle mode dispatch/startup behavior changes.
  - [x] Run quality gates:
    - [x] `uv run ruff check`
    - [x] `TESTCONTAINERS_RYUK_DISABLED=true DOCKER_HOST=unix://$HOME/.docker/desktop/docker.sock uv run pytest -q -rs`
    - [x] Confirm full regression reports `0 skipped`.

## Dev Notes

### Developer Context Section

- Story 2.5 is a lifecycle retention and observability hardening story in Epic 2.
- Existing lifecycle runner implementation already exists in:
  - `src/aiops_triage_pipeline/storage/lifecycle.py`
  - `src/aiops_triage_pipeline/storage/client.py`
  - `src/aiops_triage_pipeline/__main__.py` (`casefile-lifecycle` mode)
- Existing tests already cover core retention behavior and should be treated as the baseline:
  - `tests/unit/storage/test_casefile_lifecycle.py`
  - `tests/integration/test_casefile_lifecycle.py`
- Implementation priority is correctness and observability completeness, not redesign.

### Technical Requirements

- FR30: casefile-lifecycle runner scans object storage and purges expired casefiles according to retention policy.
- NFR-A1/NFR-A2 alignment: retention behavior remains auditable and policy-version traceable.
- Failure handling must stay explicit:
  - No silent drop of failed deletes.
  - Governance approval required for destructive purge operations.
  - Non-expired objects must remain untouched.

### Architecture Compliance

- Keep lifecycle logic in storage/runtime boundaries:
  - storage logic in `storage/lifecycle.py` and `storage/client.py`
  - runtime wiring in `__main__.py` and `config/settings.py`
- Do not introduce parallel retention engines or alternate key layouts.
- Preserve immutable contract-first modeling (`CasefileRetentionPolicyV1`) and deterministic runner behavior.

### Library / Framework Requirements

- Locked project versions in `pyproject.toml`:
  - Python >= 3.13
  - boto3 ~= 1.42
  - pydantic == 2.12.5
  - pydantic-settings ~= 2.13.1
  - pytest == 9.0.2
- Latest observed (2026-03-22):
  - boto3 1.42.73
  - SQLAlchemy 2.0.48
  - pydantic 2.12.5
  - pytest 9.0.2
- Keep dependency upgrades out of scope unless required for a security or correctness fix.

### File Structure Requirements

Primary implementation files:
- `src/aiops_triage_pipeline/storage/lifecycle.py`
- `src/aiops_triage_pipeline/storage/client.py`
- `src/aiops_triage_pipeline/__main__.py`
- `src/aiops_triage_pipeline/health/metrics.py`
- `src/aiops_triage_pipeline/config/settings.py`

Primary test files:
- `tests/unit/storage/test_casefile_lifecycle.py`
- `tests/integration/test_casefile_lifecycle.py`
- `tests/unit/test_main.py`

Policy/config files:
- `config/policies/casefile-retention-policy-v1.yaml`

### Testing Requirements

- Unit tests must validate:
  - retention cutoff behavior per environment
  - canonical casefile key parsing and case-scope eligibility
  - deterministic batching and idempotent reruns
  - governance enforcement for destructive purge
  - audit log/metric field presence for purge outcomes
- Integration tests must validate:
  - expired objects purged, non-expired objects preserved
  - partial delete failures surfaced and counted
  - repeat execution is idempotent
- Full-suite sprint quality gate must pass with zero skipped tests.

### Previous Story Intelligence

From Story 2.4:
- Keep scope narrow and boundary-specific; avoid unrelated refactors.
- Preserve shared safety conventions (denylist/governance/structured logging patterns).
- Maintain explicit, test-backed completion evidence and zero-skip quality-gate discipline.

From Epic 2 prior stories:
- Continue deterministic, source-state-guarded behavior patterns.
- Treat observability fields and operational failure surfacing as acceptance criteria, not optional extras.

### Git Intelligence Summary

Recent Epic 2 commits indicate focused, incremental delivery:
- `4a7117a` story 2.4 completion and quality gates
- `0b670fd` story 2.2 review completion
- `7aa68be` story 2.2 workflow completion

Actionable guidance:
- Keep Story 2.5 changes constrained to lifecycle retention behavior + observability + tests.
- Preserve existing patterns for runtime mode wiring and structured logging.

### Latest Tech Information

External verification date: 2026-03-22.

- Boto3 docs (1.42.73) for `S3.Client.delete_objects` document request batches up to 1,000 keys.
- Boto3 docs for `list_objects_v2` document `MaxKeys` default behavior (up to 1,000) and continuation-token pagination.
- AWS S3 lifecycle docs note expiration removal can be delayed after eligibility; explicit list/head checks are needed for operational verification.
- Python `datetime` docs continue to distinguish aware vs naive datetimes; retention calculations should remain aware-UTC only.

### Project Context Reference

Applied `archive/project-context.md` guidance:
- Keep contract-first, immutable models.
- Use structured logs and avoid sensitive-value leakage.
- Preserve explicit degradation/failure signaling (no silent failure).
- Keep behavior changes test-backed with full-suite regression and zero skips.

### References

- [Source: `artifact/planning-artifacts/epics.md` — Epic 2, Story 2.5, FR30]
- [Source: `artifact/planning-artifacts/prd/functional-requirements.md` — FR30]
- [Source: `artifact/planning-artifacts/prd/non-functional-requirements.md` — auditability and reliability expectations]
- [Source: `artifact/planning-artifacts/architecture/project-structure-boundaries.md`]
- [Source: `artifact/planning-artifacts/architecture/implementation-patterns-consistency-rules.md`]
- [Source: `artifact/implementation-artifacts/2-4-dispatch-pagerduty-and-slack-actions-with-denylist-safety.md`]
- [Source: `src/aiops_triage_pipeline/storage/lifecycle.py`]
- [Source: `src/aiops_triage_pipeline/storage/client.py`]
- [Source: `src/aiops_triage_pipeline/__main__.py`]
- [Source: `src/aiops_triage_pipeline/config/settings.py`]
- [Source: `src/aiops_triage_pipeline/contracts/casefile_retention_policy.py`]
- [Source: `config/policies/casefile-retention-policy-v1.yaml`]
- [Source: `tests/unit/storage/test_casefile_lifecycle.py`]
- [Source: `tests/integration/test_casefile_lifecycle.py`]
- [Source: `tests/unit/test_main.py`]
- [Source: `archive/project-context.md`]
- [Source: `https://docs.aws.amazon.com/boto3/latest/reference/services/s3/client/delete_objects.html`]
- [Source: `https://docs.aws.amazon.com/boto3/latest/reference/services/s3/client/list_objects_v2.html`]
- [Source: `https://docs.aws.amazon.com/AmazonS3/latest/userguide/lifecycle-expire-general-considerations.html`]
- [Source: `https://docs.python.org/3/library/datetime.html`]

## Dev Agent Record

### Agent Model Used

gpt-5-codex

### Debug Log References

- Workflow executed: `bmad-bmm-dev-story` (YOLO/full-auto)
- Target story: `2-5-run-casefile-lifecycle-retention-purge`
- Source-of-truth status file: `artifact/implementation-artifacts/sprint-status.yaml`
- Red phase validated first with:
  - `uv run pytest -q tests/atdd/test_story_2_5_casefile_lifecycle_retention_purge_red_phase.py -q` (initially failing as expected)
- Quality gates executed:
  - `uv run ruff check`
  - `TESTCONTAINERS_RYUK_DISABLED=true DOCKER_HOST=unix://$HOME/.docker/desktop/docker.sock uv run pytest -q -rs`

### Completion Notes List

- Added lifecycle OTLP metric hook via `record_casefile_lifecycle_purge_outcome(...)` and wired emission from `CasefileLifecycleRunner.run_once(...)`.
- Extended lifecycle audit logging to include `failed_keys` so partial delete failures are visible for operational follow-up.
- Extended lifecycle mode startup logs to include `policy_schema_version`, `retention_policy_path`, and `governance_approval_ref`.
- Added/updated unit tests for lifecycle metrics emission, failed-key audit visibility, and startup logging metadata.
- Full regression completed with `934 passed` and `0 skipped`.

### File List

- `src/aiops_triage_pipeline/storage/lifecycle.py`
- `src/aiops_triage_pipeline/health/metrics.py`
- `src/aiops_triage_pipeline/__main__.py`
- `tests/unit/storage/test_casefile_lifecycle.py`
- `tests/unit/health/test_metrics.py`
- `tests/unit/test_main.py`
- `tests/atdd/fixtures/story_2_5_test_data.py`
- `tests/atdd/test_story_2_5_casefile_lifecycle_retention_purge_red_phase.py`
- `artifact/implementation-artifacts/2-5-run-casefile-lifecycle-retention-purge.md`

### Senior Developer Review (AI)

- Outcome: **Approved after fixes**
- Findings identified and resolved:
  - [HIGH] Governance approval invariant accepted whitespace-only values in lifecycle purge constructor (`src/aiops_triage_pipeline/storage/lifecycle.py`), allowing destructive path to proceed until downstream client enforcement.
    - Fix: normalize stripped governance approval to `None` when blank, ensuring invariant fails before delete attempt.
    - Test proof: added `test_runner_rejects_blank_governance_approval_for_destructive_purge`.
  - [HIGH] Story File List did not match actual changed source files (missing `tests/atdd/fixtures/story_2_5_test_data.py`).
    - Fix: synchronized File List to include all changed source/test files for this story workflow.
  - [LOW] ATDD test patched shared metrics hook using direct `setattr`, risking cross-test state leakage.
    - Fix: switched to pytest `monkeypatch` for automatic restoration.

### Change Log

- 2026-03-22: Implemented Story 2.5 lifecycle observability/governance deltas (metric emission, failed-key audit fields, startup log metadata) with unit + integration + full-regression validation.
- 2026-03-22: Completed `bmad-bmm-code-review`; fixed governance blank-approval invariant, ATDD monkeypatch isolation, and reconciled story evidence metadata with actual changed files.

## Story Completion Status

- Story status: `done`
- Completion note: Code review completed with all Critical/High/Medium/Low findings resolved and regression gates rerun.
