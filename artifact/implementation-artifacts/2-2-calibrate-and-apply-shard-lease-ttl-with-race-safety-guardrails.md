# Story 2.2: Calibrate and Apply Shard Lease TTL with Race-Safety Guardrails

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a Platform Operations Engineer,
I want shard lease TTL calibrated from observed UAT cycle timing,
so that overlapping shard processing risk is controlled during operations.

## Acceptance Criteria

1. Given UAT cycle durations are observed and p95 is measured, when `SHARD_LEASE_TTL_SECONDS` is set, then configured TTL exceeds measured p95 by at least 30 seconds and the calibration basis is documented for operational review.

2. Given transient residual race windows can still occur during calibration, when duplicate processing attempts are encountered, then checkpoint deduplication suppresses duplicate downstream processing effects and overlap effects do not propagate to external action systems.

## Tasks / Subtasks

- [ ] Add Docker pre-check as first step (carry-over process rule from Epic 1 retro) (AC: all)
  - [ ] Run `bash scripts/docker-precheck.sh` before any testcontainers-backed test run.

- [ ] Capture UAT cycle-duration baseline and compute p95 for calibration (AC: 1)
  - [ ] Collect hot-path cycle duration evidence from UAT logs/metrics over representative windows.
  - [ ] Compute p95 cycle duration and record the exact sample window and methodology in docs.
  - [ ] Derive `candidate_ttl_seconds = ceil(p95_seconds + safety_margin_seconds)` with `safety_margin_seconds >= 30`.

- [ ] Configure explicit `SHARD_LEASE_TTL_SECONDS` values per environment (AC: 1)
  - [ ] Add `SHARD_LEASE_TTL_SECONDS=<value>` to `config/.env.dev` (operationally documented non-secret value).
  - [ ] Add `SHARD_LEASE_TTL_SECONDS=<value>` to `config/.env.uat.template` based on UAT p95 + margin.
  - [ ] Add `SHARD_LEASE_TTL_SECONDS=<value>` to `config/.env.prod.template` aligned to approved UAT calibration basis.
  - [ ] Add inline comment near each value documenting calibration formula and date.
  - [ ] Ensure chosen values satisfy architecture guardrail: `0 < SHARD_LEASE_TTL_SECONDS < HOT_PATH_SCHEDULER_INTERVAL_SECONDS`.

- [ ] Enforce startup validation guardrails in settings (AC: 1)
  - [ ] Preserve existing positivity validation (`SHARD_LEASE_TTL_SECONDS must be > 0`).
  - [ ] Add/extend validation so named envs (`dev`, `uat`, `prod`) reject implicit fallback/default TTL when env-specific TTL is required.
  - [ ] Add/extend validation that rejects lease TTL greater than or equal to scheduler interval, with clear operator-facing error text.

- [ ] Preserve and validate race-safety behavior via checkpoint + dedupe pathways (AC: 2)
  - [ ] Confirm shard lease contention behavior remains `acquired|yielded|fail_open` with Redis `SET NX EX` semantics.
  - [ ] Confirm holder-failure recovery after TTL expiry remains deterministic and requires no manual unlock.
  - [ ] Verify duplicate downstream effects are suppressed by existing checkpoint/dedupe mechanisms under residual overlap conditions.

- [ ] Update documentation for operations and rollout clarity (AC: 1, 2)
  - [ ] Update `docs/runtime-modes.md` with calibrated TTL procedure and environment examples.
  - [ ] Update `docs/deployment-guide.md` to align defaults/examples with current code and calibration policy.
  - [ ] Add/refresh runbook notes showing where p95 evidence is gathered and how operators re-calibrate.

- [ ] Add/adjust targeted tests (AC: all)
  - [ ] `tests/unit/config/test_settings.py`: validation coverage for invalid/missing/unbounded TTL in named envs.
  - [ ] `tests/unit/pipeline/test_scheduler.py`: verify lease TTL wiring from `Settings` into shard coordinator calls.
  - [ ] `tests/integration/coordination/test_shard_lease_contention.py`: verify contention winner/yield and recovery timing behavior.
  - [ ] Add/extend tests that verify residual overlap cannot propagate duplicate external effects.

- [ ] Execute quality gate with zero skipped tests (AC: all)
  - [ ] Run targeted suites for updated modules.
  - [ ] Run full regression: `TESTCONTAINERS_RYUK_DISABLED=true DOCKER_HOST=unix://$HOME/.docker/desktop/docker.sock uv run pytest -q -rs`.
  - [ ] Confirm `0 skipped` before marking story done.

## Dev Notes

### Story Context and Constraints

- Scope is FR15, FR16, FR17 (Epic 2 Story 2.2): per-environment lease TTL configuration, UAT p95-based calibration, residual-race suppression.
- This is a brownfield surgical change. Do not introduce new packages, architectural layers, or contract changes.
- Keep Redis shard-lease behavior on `SET NX EX` with TTL-expiry ownership transfer. No explicit unlock path is allowed.
- Keep checkpoint/dedupe behavior as the residual safety net; do not redesign this mechanism in this story.
- Values are operational (non-secret) and must be safe for version-controlled env files.
- Full regression quality gate must run with zero skipped tests.

### Current Code Reality (Build on Existing)

- `Settings` currently defines `SHARD_LEASE_TTL_SECONDS: int = 270` and validates only `> 0`.
- Scheduler wiring already passes `settings.SHARD_LEASE_TTL_SECONDS` into `shard_coordinator.acquire_lease(...)`.
- Shard coordination already uses Redis `SET NX EX` lease semantics and fails open on Redis errors.
- Env files currently define `STAGE2_PEAK_HISTORY_MAX_DEPTH` explicitly, but do not yet define `SHARD_LEASE_TTL_SECONDS`.
- Docs currently have drift: `runtime-modes.md` documents TTL default 270 while `deployment-guide.md` documents 360.

### Technical Requirements

- FR15: `SHARD_LEASE_TTL_SECONDS` must be operator-configurable in `.env.dev`, `.env.uat.template`, `.env.prod.template`.
- FR16: For UAT/Prod, choose TTL from UAT p95 measurement with at least +30s margin.
- Hard guardrail from architecture: lease TTL must remain below scheduler interval for clean per-cycle re-acquisition.
- If measured `p95 + 30s` violates interval constraint, do not silently clamp; surface explicit validation/documented decision.
- Record calibration evidence (timestamped measurement window, p95 result, selected margin, final TTL) in docs.

### Architecture Compliance

- Allowed change surface:
  - `config/.env.dev`
  - `config/.env.uat.template`
  - `config/.env.prod.template`
  - `src/aiops_triage_pipeline/config/settings.py`
  - `src/aiops_triage_pipeline/__main__.py` (only if wiring or safety checks require tiny glue updates)
  - `src/aiops_triage_pipeline/coordination/shard_registry.py` (only if strictly required by acceptance criteria)
  - `tests/unit/config/test_settings.py`
  - `tests/unit/pipeline/test_scheduler.py`
  - `tests/integration/coordination/test_shard_lease_contention.py`
  - docs updates in `docs/`

- Protected zones (do not modify unless re-approved):
  - `src/aiops_triage_pipeline/contracts/*`
  - `src/aiops_triage_pipeline/integrations/*`
  - `src/aiops_triage_pipeline/storage/*`
  - `src/aiops_triage_pipeline/outbox/*`
  - `src/aiops_triage_pipeline/linkage/*`

- No new inbound/outbound API surfaces. No schema migrations.

### Library / Framework Requirements

Latest checks executed on 2026-03-29 from official PyPI package indexes:

- `pydantic-settings`: latest `2.13.1` (project already aligned)
- `pydantic`: latest `2.12.5` (project already aligned)
- `pytest`: latest `9.0.2` (project already aligned)
- `testcontainers`: latest `4.14.2` (project pinned to `4.14.1`; no upgrade required for this story)
- `redis` (client library): latest `7.4.0` (project pinned to `7.2.1`; no upgrade required for this story)

Story guidance:
- Do not bundle dependency upgrades into Story 2.2.
- Keep implementation focused on config calibration, validation guardrails, and verification.

### File Structure Requirements

Primary implementation surface:

- `config/.env.dev`
- `config/.env.uat.template`
- `config/.env.prod.template`
- `src/aiops_triage_pipeline/config/settings.py`

Primary verification surface:

- `tests/unit/config/test_settings.py`
- `tests/unit/pipeline/test_scheduler.py`
- `tests/integration/coordination/test_shard_lease_contention.py`
- Related coordination/degraded-mode integration tests if touched by changes

Documentation surface:

- `docs/runtime-modes.md`
- `docs/deployment-guide.md`
- Optional supporting docs with calibration runbook details

### Testing Requirements

- Add/extend unit tests to verify:
  - named-env TTL validation rejects missing/implicit default where policy requires explicit env TTL;
  - `SHARD_LEASE_TTL_SECONDS` remains strictly positive;
  - lease TTL < scheduler interval guardrail.

- Add/extend scheduler tests to verify:
  - `lease_ttl_seconds` passed to shard coordinator equals active settings value;
  - shard flag and lock flag behavior remain independent.

- Run and maintain integration coverage for:
  - lease contention (single winner + one yielded holder);
  - post-expiry recovery by another pod;
  - fail-open behavior under Redis errors;
  - residual overlap protection via existing checkpoint/dedupe controls.

- Required commands:

```bash
uv run pytest -q tests/unit/config/test_settings.py tests/unit/pipeline/test_scheduler.py
```

```bash
uv run pytest -q tests/integration/coordination/test_shard_lease_contention.py
```

```bash
TESTCONTAINERS_RYUK_DISABLED=true DOCKER_HOST=unix://$HOME/.docker/desktop/docker.sock uv run pytest -q -rs
```

Acceptance gate: full regression must finish with `0 skipped`.

### Previous Story Intelligence (Story 2.1)

- Carry forward Docker pre-check before integration/full-suite runs (`bash scripts/docker-precheck.sh`).
- Maintain small change surface and avoid touching scoring/audit/contracts for this story.
- Keep `Settings` validation style consistent with existing `@model_validator` patterns.
- Preserve `get_settings.cache_clear()` discipline in settings tests where singleton caching affects isolation.
- Keep docs and code defaults aligned (avoid drift in operational docs).
- Continue strict zero-skip full regression gate.

### Git Intelligence Summary

Recent commit sequence indicates:

- Epic 1 retrospective completed and sprint advanced to Epic 2.
- Story 2.1 implemented as configuration + validation + docs + tests with minimal surface.
- Pattern to follow for Story 2.2: focused config/settings/docs/tests changes; avoid architecture drift.

Relevant recent commits:
- `560efb9` `fix(config): resolve story 2.1 review findings`
- `0eb4a08` `feat(config): implement story 2.1 env-specific peak depth`
- `27cc38c` `retro(epic-1): complete Epic 1 retrospective and advance to Epic 2`

### Latest Tech Information (Step 4 Research)

Date checked: 2026-03-29.

- Official package-index checks confirm project-critical toolchain remains current for this scope.
- No breaking upgrade is required to implement Story 2.2.
- Implement with existing stack versions and avoid dependency churn in this story.

### Project Context Reference

Critical rules from `artifact/project-context.md` applied:

- `APP_ENV` controls env-file selection via `.env.{APP_ENV}` with direct env-var override precedence.
- Keep `config` package as a leaf; avoid introducing contract-model imports in `settings.py`.
- Shard coordination remains fail-open on Redis coordination failures.
- Preserve deterministic hash-based shard mapping and TTL-expiry lease recovery behavior.
- Treat test skips as failures; full regression must complete with zero skips.

### References

- `artifact/planning-artifacts/epics.md` (Epic 2 / Story 2.2 acceptance criteria)
- `artifact/planning-artifacts/prd.md` (FR15-FR17, calibration and race-safety expectations)
- `artifact/planning-artifacts/architecture/core-architectural-decisions.md` (TTL policy guardrails)
- `artifact/planning-artifacts/architecture/project-structure-boundaries.md` (change surface + protected zones)
- `artifact/planning-artifacts/architecture/project-context-analysis.md` (constraints + coordinated release posture)
- `artifact/planning-artifacts/architecture/implementation-patterns-consistency-rules.md`
- `artifact/project-context.md`
- `artifact/implementation-artifacts/2-1-configure-environment-specific-peak-history-depth-and-loading.md`
- `artifact/implementation-artifacts/epic-1-retro-2026-03-29.md`
- `src/aiops_triage_pipeline/config/settings.py`
- `src/aiops_triage_pipeline/coordination/shard_registry.py`
- `src/aiops_triage_pipeline/__main__.py`
- `tests/unit/config/test_settings.py`
- `tests/unit/pipeline/test_scheduler.py`
- `tests/integration/coordination/test_shard_lease_contention.py`
- `docs/runtime-modes.md`
- `docs/deployment-guide.md`

## Story Completion Status

- Story analysis type: exhaustive artifact-based context build
- Previous-story intelligence: applied
- Git-intelligence dependency: completed
- Web research dependency: completed
- Completion note: Ultimate context engine analysis completed - comprehensive developer guide created

## Dev Agent Record

### Agent Model Used

gpt-5 (Codex)

### Debug Log References

- Loaded and analyzed sprint status, epics, PRD, architecture, project-context, previous story, and retrospective artifacts.
- Used parallel sub-analysis for PRD and architecture extraction focused on Story 2.2.
- Confirmed current code baseline for shard lease settings/wiring/tests.
- Verified latest package versions from official package indexes for story guardrails.

### Completion Notes List

- Story created for next backlog item: `2-2-calibrate-and-apply-shard-lease-ttl-with-race-safety-guardrails`.
- Story is prepared as `ready-for-dev` with implementation guardrails and test expectations.
- Sprint status was updated from `backlog` to `ready-for-dev` for this story key.

### File List

- artifact/implementation-artifacts/2-2-calibrate-and-apply-shard-lease-ttl-with-race-safety-guardrails.md
- artifact/implementation-artifacts/sprint-status.yaml
