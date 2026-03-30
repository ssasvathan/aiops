---
project_name: 'aiOps'
user_name: 'Sas'
date: '2026-03-29T00:00:00-00:00'
sections_completed: ['technology_stack', 'language_rules', 'framework_rules', 'testing_rules', 'quality_rules', 'workflow_rules', 'anti_patterns']
status: 'complete'
rule_count: 72
optimized_for_llm: true
existing_patterns_found: 29
---

# Project Context for AI Agents

_This file contains critical rules and patterns that AI agents must follow when implementing code in this project. Focus on unobvious details that agents might otherwise miss._

---

## Technology Stack & Versions

- Python: >=3.13
- Package/build tooling: uv (uv_build>=0.9.21 backend)
- Core libs:
  - confluent-kafka==2.13.0
  - SQLAlchemy==2.0.47
  - psycopg[c]==3.3.3
  - pydantic==2.12.5
  - pydantic-settings~=2.13.1 (intentional compatible range)
  - redis==7.2.1
  - boto3~=1.42 (intentional compatible range)
  - httpx==0.28.1
  - opentelemetry-sdk==1.39.1
  - opentelemetry-exporter-otlp==1.39.1
  - langgraph==1.0.9
  - structlog==25.5.0
  - pyyaml~=6.0
- Dev/test:
  - pytest==9.0.2
  - pytest-asyncio==1.3.0
  - testcontainers==4.14.1
  - ruff~=0.15 (intentional compatible range)
  - prometheus-client~=0.24.0 (harness tests)
- Local infra image baselines (docker-compose):
  - Kafka/ZooKeeper: confluentinc/cp-kafka:7.5.0, cp-zookeeper:7.5.0
  - Postgres: 16
  - Redis: 7.2
  - MinIO: RELEASE.2025-01-20T14-49-07Z
  - Prometheus: v2.50.1

Implementation notes:
- `pyproject.toml` is the source of truth for app/runtime dependencies.
- `harness/requirements.txt` is harness-scoped and must not be treated as app dependency baseline.
- When changing pinned versions, rerun relevant unit + integration suites before merge.

## Critical Implementation Rules

### Language-Specific Rules

- Use Python 3.13 typing style consistently (`X | None`, built-in generics like `dict[str, Any]`).
- Keep contract/data models immutable by default (`BaseModel, frozen=True`) for policy and event contracts.
- Validate at boundaries:
  - Validate on model creation for in-memory objects.
  - Re-validate on deserialization from external I/O.
- Keep `config` package as a leaf:
  - `config/settings.py` must not import specific contract classes.
  - `load_policy_yaml(path, model_class)` stays generic; callers pass model classes.
- Enforce env-file resolution pattern:
  - `APP_ENV` is read before `Settings` class creation.
  - `.env.{APP_ENV}` is selected by settings config.
  - Direct environment variables override `.env` values.
- Preserve fail-fast validation for secure Kafka mode:
  - When `KAFKA_SECURITY_PROTOCOL=SASL_SSL`, require and validate existing paths for keytab and krb5 config.
- Use explicit exception taxonomy from `errors/exceptions.py`:
  - Critical invariants/dependencies raise halt-class exceptions.
  - Degradable dependencies raise degradable exceptions and continue with caps.
- Keep logging structured and contextual:
  - Use configured `structlog` pipeline.
  - Bind/clear `correlation_id` via provided logging helpers; do not hand-roll context propagation.
- Keep async safety assumptions explicit:
  - `HealthRegistry` concurrency uses `asyncio.Lock` (not threading locks).
  - Health metrics state (`_state_lock`) uses `threading.Lock` — OTLP callbacks are synchronous, not async.

### Framework-Specific Rules

- Pipeline architecture:
  - Keep hot path deterministic and non-blocking with respect to LLM work.
  - Cold path diagnosis is asynchronous/advisory; it must not override deterministic gating outcomes.
  - Stage order: `evidence → peak → topology → casefile → outbox → gating → dispatch`.

- Guardrail authority:
  - Rulebook-style deterministic gates (AG0–AG6) are authoritative for action decisions.
  - PAGE outside PROD+TIER_0 must remain structurally impossible.

- Rule engine framework (AG0–AG3):
  - AG0–AG3 are evaluated in fixed order via `EARLY_GATE_ORDER`; do not reorder or skip entries.
  - All check types used in AG0–AG3 must be registered in `HANDLER_REGISTRY` at startup — validate with `validate_rulebook_handlers()` before first evaluation.
  - AG3 (source-topic-page-deny) is only applied when `should_apply_source_topic_page_deny()` predicate returns true; never force-evaluate AG3 unconditionally.
  - Rule engine produces an `EarlyGateEvaluation`; the full gating stage (`evaluate_rulebook_gates`) combines early gates with AG4–AG6.

- Environment cap framework:
  - Enforce max-action caps by `APP_ENV` (`local=OBSERVE`, `dev=NOTIFY`, `uat=TICKET`, `prod=PAGE`) through shared policy logic.
  - Do not implement per-component custom cap logic that diverges from central policy.

- Coordination framework:
  - Cycle lock uses Redis `SET NX EX` (`aiops:lock:cycle`); TTL expiry is the only release mechanism — no explicit unlock.
  - Redis lock acquisition failures must fail-open: always return `CycleLockStatus.fail_open` and proceed rather than blocking execution.
  - Shard assignment uses SHA-256 consistent hash (`scope_to_shard_id`) — never use PYTHONHASHSEED-dependent hashing.
  - Shard pod assignment sorts `active_pod_ids` lexicographically before mapping shards to pods.
  - Rollout flags gate coordination features (shard registry, cycle lock); check flags before activating coordination paths.

- Degraded-mode framework:
  - Degradable failures update `HealthRegistry` and continue with capped behavior.
  - Critical dependency/invariant failures halt processing (no silent fallback).

- Integration mode framework:
  - External integrations must implement `OFF | LOG | MOCK | LIVE` semantics consistently.
  - Default-safe operation remains LOG unless explicitly configured otherwise.

- LLM cold-path framework:
  - Cold-path LangGraph diagnosis runs asynchronously; results are advisory findings only.
  - Track inflight LLM invocations via `_llm_cold_path_inflight` UpDownCounter; decrement on completion/error/timeout.
  - Always implement a fallback path (`diagnosis/fallback.py`) for LLM failures — cold path must never block hot path.
  - LLM integration mode must default to `LOG`/`MOCK`; never `LIVE` without explicit config.

- Audit/replay framework:
  - Decision reproducibility (NFR-T6): `reproduce_gate_decision()` requires exact rulebook version match against `casefile.policy_versions.rulebook_version`.
  - Raise `ValueError` on rulebook version mismatch — do not attempt replay with mismatched versions.
  - Audit trail (`build_audit_trail()`) must be constructable from a stored `CaseFileTriageV1` alone.

- Denylist framework:
  - All outbound boundary shaping must use shared `apply_denylist(...)`.
  - No boundary-specific denylist reimplementations.

- Contract + serialization framework:
  - Frozen contract models are the source of truth for payload shape.
  - Serialize at I/O boundaries using canonical JSON paths; avoid ad-hoc serializers.

- Observability framework:
  - Use shared structured logging setup with correlation context.
  - Health/telemetry signals must flow through existing health/event primitives.
  - OTLP health status numeric mapping: `HEALTHY=0`, `DEGRADED=1`, `UNAVAILABLE=2`.
  - Use `create_up_down_counter` for gauges (health status, inflight counts), `create_counter` for totals, `create_histogram` for latency.

- Change validation rule:
  - Any change to these framework behaviors must include targeted unit/integration tests for the touched behaviors.

### Testing Rules

- Test framework + scope:
  - Use pytest with pytest-asyncio (`asyncio_mode=auto`).
  - Unit tests: `tests/unit/<domain>/` — mirror the source domain structure.
  - Integration tests: `tests/integration/` — require Docker-backed infra.
  - ATDD acceptance tests: `tests/atdd/` — system-level acceptance criteria.

- Sprint quality gate:
  - Full regression runs must complete with **0 skipped tests**.
  - Treat any skip as a failure; fix missing prerequisites instead of bypassing.
  - Preferred full regression command:
    `TESTCONTAINERS_RYUK_DISABLED=true DOCKER_HOST=unix://$HOME/.docker/desktop/docker.sock uv run pytest -q -rs`

- Async test patterns:
  - Use `async def` tests for async components; avoid sync wrappers for async logic.
  - For concurrency-sensitive behavior (e.g., health registry, cycle lock), include explicit concurrent scenarios.

- Contract validation tests:
  - For frozen contract models, include immutability tests (mutation must raise).
  - Test both happy-path and schema-mismatch/failure-path validations.

- Coordination tests:
  - Cycle lock tests must cover: acquired, skipped (already held), and fail-open (Redis error) outcomes.
  - Shard assignment tests must verify determinism across identical inputs (hash stability).
  - Rollout flag tests must verify flag-gated paths activate/deactivate correctly.

- Rule engine tests:
  - Cover startup validation: missing gates and unregistered check types must raise `RuleEngineStartupError`.
  - Cover AG3 predicate gating: test cases where AG3 should and should not apply.
  - Cover `assert_page_is_limited_to_prod_tier0` safety invariant.

- Audit/replay tests:
  - Decision reproducibility tests (`tests/unit/audit/test_decision_reproducibility.py`) must verify version mismatch raises `ValueError`.
  - Must verify that replay of stored casefile produces identical `ActionDecisionV1`.

- Config/settings tests:
  - Verify env-default behavior, env overrides, and fail-fast startup validation paths.
  - Clear singleton caches (`get_settings.cache_clear()`) when test isolation requires it.

- Logging/observability tests:
  - Validate structured log field expectations and secret masking behavior.
  - Verify correlation context propagation and cleanup behavior.

- Denylist tests:
  - Keep denylist behavior tests focused on canonical `apply_denylist(...)`.
  - Validate name- and pattern-based filtering, case-insensitive name handling.

- Test discipline:
  - New behavior changes must include or update targeted tests in the relevant test package.
  - Avoid placeholder-only coverage for production logic.
  - Integration boundary changes must run or add integration tests that exercise real infra.

### Code Quality & Style Rules

- Enforce Ruff baseline from `pyproject.toml`:
  - line length 100
  - target version py313
  - lint selection `E,F,I,N,W`
  - keep `N818` ignored (intentional: exception names omit "Error" suffix by architecture decision)

- Naming and layout conventions:
  - Use snake_case for modules, functions, and variables.
  - Keep domain packages separated by responsibility:
    `contracts/`, `models/`, `pipeline/`, `coordination/`, `rule_engine/`, `diagnosis/`,
    `cache/`, `integrations/`, `health/`, `outbox/`, `linkage/`, `storage/`, `audit/`,
    `registry/`, `denylist/`, `errors/`, `logging/`, `config/`.
  - Keep tests mirrored by domain under `tests/unit/<domain>/`.

- Schema-first model style:
  - Prefer explicit typed fields and constrained literals/enums for contract shapes.
  - Keep contract/policy models immutable (`frozen=True`) unless mutability is explicitly required.
  - Encode structural invariants with validators (e.g., required gate IDs), not prose-only comments.

- Commenting/documentation:
  - Use short, purpose-driven docstrings/comments for non-obvious logic.
  - Document architectural invariants and "must not" behavior where violated assumptions are costly.

- Logging style:
  - Use structured event names and key-value fields (not free-form log text blobs).
  - Never log secrets; preserve masking patterns for credentials/URLs.
  - Keep field naming consistent with observability schema (`severity`, `timestamp`, `component`, `correlation_id`).

- Config/code boundary:
  - Keep policy loading generic; avoid coupling config module to specific contract classes.

- Test assertion style:
  - Prefer assertions on structured fields (parsed model fields) over brittle raw-string comparisons.

- Consistency over novelty:
  - Reuse existing helper functions/utilities for cross-cutting behavior (denylist, logging, health, coordination)
    rather than introducing parallel patterns.

### Development Workflow Rules

- Source-of-truth workflow artifacts:
  - Treat architecture/PRD/epics artifacts in `docs/` as normative implementation guidance.
  - Do not introduce behavior that conflicts with defined invariants (durability guarantees, environment
    action caps, hot/cold path separation) without updating governing artifacts.

- Dependency change workflow:
  - Update versions via `pyproject.toml` + lockfile (`uv.lock`) flow, not ad-hoc local-only installs.
  - Reconcile dependency changes with impacted tests before merge.
  - `harness/requirements.txt` is harness-scoped only; never treat it as the app dependency baseline.

- Configuration workflow:
  - Preserve `APP_ENV`-driven env file selection and env-var override precedence.
  - Keep environment defaults safe and prevent secret leakage in committed config/log output.
  - `config/denylist.yaml` is governed by CODEOWNERS review — treat as high-sensitivity.

- Integration safety workflow:
  - Default to non-destructive integration modes (`LOG`/`MOCK`) unless requirements explicitly call for `LIVE`.
  - Avoid accidental outbound effects during local/dev execution.

- Validation before PR:
  - `uv run pytest -q tests/unit`
  - `uv run pytest -q tests/integration -m integration`
  - Full regression: `TESTCONTAINERS_RYUK_DISABLED=true DOCKER_HOST=unix://$HOME/.docker/desktop/docker.sock uv run pytest -q -rs`
  - `uv run ruff check`

- Change locality + traceability:
  - When modifying behavior, update nearest tests and relevant docs/contracts in the same change set.
  - Keep PRs scoped and requirement-traceable.

- High-risk review workflow:
  - Changes touching contracts, gating logic, denylist enforcement, action caps, coordination primitives,
    audit/replay paths, or degraded-mode behavior require explicit regression verification.

### Critical Don't-Miss Rules

- Never bypass deterministic guardrails:
  - Do not allow diagnosis/ML/LLM paths to override gate-based decisions.
  - PAGE must remain structurally impossible outside PROD+TIER_0.

- Never bypass durability controls:
  - Preserve write-before-publish and crash-safe publish behavior.
  - Do not add publish paths that skip outbox/durability handling.

- Never collapse UNKNOWN into PRESENT/zero:
  - Preserve missing-evidence UNKNOWN semantics end-to-end.
  - Do not apply implicit defaults that inflate confidence/actions.

- Never fork cross-cutting enforcement:
  - Use shared `apply_denylist(...)` at all output boundaries.
  - Use shared logging/correlation and health-registry primitives.
  - Do not introduce parallel policy/cap evaluators.

- Never weaken integration safety posture:
  - Keep non-destructive defaults (`LOG`) unless requirements explicitly demand otherwise.
  - Prevent unintended LIVE calls in local/dev execution paths.

- Never leak sensitive data:
  - Do not log secrets or raw credentials.
  - Preserve masking/redaction behavior for URLs and secrets.

- Never fail silently on critical-path faults:
  - Degradable failures must emit health/degraded signals and capped behavior.
  - Invariant/critical dependency failures must fail loudly and stop unsafe progression.

- Never drift from contract-first implementation:
  - Keep payload/event/policy shapes aligned with frozen contract models.
  - Do not add ad-hoc fields outside validated schema paths.

- Never ship risky changes unverified:
  - Changes in caps/gating/contracts/denylist/degraded-mode/coordination/audit areas require targeted regression tests.

- Never use Redis unlock for cycle lock:
  - `aiops:lock:cycle` uses TTL expiry only — adding explicit DEL/unlock breaks the distributed ownership model.

- Never use PYTHONHASHSEED-dependent hashing for shard assignment:
  - Always use SHA-256 (`hashlib.sha256`) for `scope_to_shard_id` — Python's built-in `hash()` is process-local.

- Never replay audit decisions with a mismatched rulebook version:
  - `reproduce_gate_decision()` raises `ValueError` on version mismatch — do not suppress or catch and continue.

- Never let the LLM cold path block or override:
  - Cold-path timeout or failure must fall back gracefully; the hot-path deterministic result is always authoritative.

---

## Usage Guidelines

**For AI Agents:**

- Read this file before implementing any code.
- Follow all rules exactly as documented.
- When in doubt, prefer the more restrictive option.
- Update this file when new patterns emerge.

**For Humans:**

- Keep this file lean and focused on agent needs.
- Update when technology stack changes.
- Review quarterly for outdated rules.
- Remove rules that become obvious over time.

Last Updated: 2026-03-29T00:00:00-00:00
