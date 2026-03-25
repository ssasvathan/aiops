---
project_name: 'aiOps'
user_name: 'Sas'
date: '2026-03-02T18:13:10-05:00'
sections_completed: ['technology_stack', 'language_rules', 'framework_rules', 'testing_rules', 'quality_rules', 'workflow_rules', 'anti_patterns']
status: 'complete'
rule_count: 50
optimized_for_llm: true
existing_patterns_found: 18
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

### Framework-Specific Rules

- Pipeline architecture:
  - Keep hot path deterministic and non-blocking with respect to LLM work.
  - Cold path diagnosis is asynchronous/advisory; it must not override deterministic gating outcomes.
- Guardrail authority:
  - Rulebook-style deterministic gates are authoritative for action decisions.
  - PAGE outside PROD+TIER_0 must remain structurally impossible.
- Environment cap framework:
  - Enforce max-action caps by `APP_ENV` (`local=OBSERVE`, `dev=NOTIFY`, `uat=TICKET`, `prod=PAGE`) through shared policy logic.
  - Do not implement per-component custom cap logic that diverges from central policy.
- Degraded-mode framework:
  - Degradable failures update `HealthRegistry` and continue with capped behavior.
  - Critical dependency/invariant failures halt processing (no silent fallback).
- Integration mode framework:
  - External integrations must implement `OFF | LOG | MOCK | LIVE` semantics consistently.
  - Default-safe operation remains LOG unless explicitly configured otherwise.
- Denylist framework:
  - All outbound boundary shaping must use shared `apply_denylist(...)`.
  - No boundary-specific denylist reimplementations.
- Contract + serialization framework:
  - Frozen contract models are the source of truth for payload shape.
  - Serialize at I/O boundaries using canonical JSON paths; avoid ad-hoc serializers.
- Observability framework:
  - Use shared structured logging setup with correlation context.
  - Health/telemetry signals should flow through existing health/event primitives.
- Change validation rule:
  - Any change to these framework behaviors must include targeted unit/integration tests for the touched behaviors.

### Testing Rules

- Test framework + scope:
  - Use pytest with pytest-asyncio (`asyncio_mode=auto`).
  - Keep unit tests under `tests/unit/` and integration tests under `tests/integration/`.
- Async test patterns:
  - Use `async def` tests for async components and avoid sync wrappers for async logic.
  - For concurrency-sensitive behavior (e.g., health registry), include explicit concurrent update scenarios.
- Contract validation tests:
  - For frozen contract models, include immutability tests (mutation should fail).
  - Test both happy-path and schema-mismatch/failure-path validations.
- Config/settings tests:
  - Verify env-default behavior, env overrides, and fail-fast startup validation paths.
  - Clear singleton caches (`get_settings.cache_clear()`) when test isolation requires it.
- Logging/observability tests:
  - Validate structured log field expectations and secret masking behavior.
  - Verify correlation context propagation and cleanup behavior.
- Denylist tests:
  - Validate shared enforcement behavior (name- and pattern-based filtering, case-insensitive name handling).
  - Keep denylist behavior tests focused on canonical `apply_denylist(...)`.
- Integration boundary tests:
  - When changing integration/dependency behavior, run or add integration tests that exercise real infra boundaries.
- Test discipline:
  - New behavior changes should include or update targeted tests in the relevant test package.
  - Avoid placeholder-only coverage for production logic.
  - Enforce no-skip regressions: full pytest quality-gate runs must end with zero skipped tests; missing environment prerequisites must be fixed, not skipped.

### Code Quality & Style Rules

- Enforce Ruff baseline from `pyproject.toml`:
  - line length 100
  - target version py313
  - lint selection `E,F,I,N,W`
  - keep `N818` ignored (intentional architecture decision)
- Naming and layout conventions:
  - Use snake_case modules/functions/variables.
  - Keep domain packages separated by responsibility (`contracts/`, `pipeline/`, `integrations/`, `health/`, etc.).
  - Keep tests mirrored by domain under `tests/unit/<domain>/`.
- Schema-first model style:
  - Prefer explicit typed fields and constrained literals/enums for contract shapes.
  - Keep contract/policy models immutable (`frozen=True`) unless mutability is explicitly required.
  - Encode structural invariants with validators (for example required gate IDs), not prose-only comments.
- Commenting/documentation:
  - Use short, purpose-driven docstrings/comments for non-obvious logic.
  - Document architectural invariants and "must not" behavior where violated assumptions are costly.
- Logging style:
  - Use structured event names and key-value fields (not free-form log text blobs).
  - Never log secrets; preserve masking patterns for credentials/URLs.
  - Keep field naming consistent with observability schema (`severity`, `timestamp`, `component`, `correlation_id`).
- Config/code boundary:
  - Keep policy loading generic and avoid coupling config module to specific contract classes.
- Test assertion style:
  - Prefer assertions on structured fields (parsed JSON/model fields) over brittle raw-string comparisons.
- Consistency over novelty:
  - Reuse existing helper functions/utilities for cross-cutting behavior (denylist, logging, health) rather than introducing parallel patterns.

### Development Workflow Rules

- Source-of-truth workflow artifacts:
  - Treat architecture/PRD/epics artifacts in `artifact/planning-artifacts/` as normative implementation guidance.
  - Do not introduce behavior that conflicts with defined invariants (durability guarantees, environment action caps, hot/cold path separation) without updating governing artifacts.
- Dependency change workflow:
  - Update versions via `pyproject.toml` + lockfile flow, not ad-hoc local-only installs.
  - Reconcile dependency changes with impacted tests before merge.
- Configuration workflow:
  - Preserve `APP_ENV`-driven env file selection and env-var override precedence.
  - Keep environment defaults safe and prevent secret leakage in committed config/log output.
- Integration safety workflow:
  - Default to non-destructive integration modes (`LOG`/`MOCK`) unless requirements explicitly call for `LIVE`.
  - Avoid accidental outbound effects during local/dev execution.
- Change locality + traceability:
  - When modifying behavior, update nearest tests and relevant docs/contracts in the same change set.
  - Keep PRs scoped and requirement-traceable.
- Quality gate workflow:
  - Run lint/tests relevant to changed areas before completion.
  - For cross-cutting/integration-impacting changes, include integration coverage checks.
- High-risk review workflow:
  - Changes touching contracts, gating logic, denylist enforcement, action caps, or degraded-mode behavior require explicit regression verification.

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
  - Changes in caps/gating/contracts/denylist/degraded-mode areas require targeted regression tests.

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

Last Updated: 2026-03-02T18:13:10-05:00
