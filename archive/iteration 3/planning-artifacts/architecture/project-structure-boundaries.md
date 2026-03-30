# Project Structure & Boundaries

## Complete Project Directory Structure

```text
aiops/
├── AGENTS.md
├── README.md
├── pyproject.toml
├── uv.lock
├── Dockerfile
├── docker-compose.yml
├── config/
│   ├── .env.dev
│   ├── .env.local
│   ├── .env.docker
│   ├── .env.uat.template
│   ├── .env.prod.template
│   ├── denylist.yaml
│   ├── topology-registry.yaml
│   ├── prometheus.yml
│   └── policies/
│       ├── rulebook-v1.yaml
│       ├── peak-policy-v1.yaml
│       ├── redis-ttl-policy-v1.yaml
│       ├── anomaly-detection-policy-v1.yaml
│       ├── outbox-policy-v1.yaml
│       ├── operational-alert-policy-v1.yaml
│       └── ...
├── src/aiops_triage_pipeline/
│   ├── __main__.py
│   ├── config/
│   │   └── settings.py
│   ├── pipeline/
│   │   ├── scheduler.py
│   │   ├── baseline_store.py
│   │   └── stages/
│   │       ├── evidence.py
│   │       ├── peak.py
│   │       ├── topology.py
│   │       ├── gating.py
│   │       ├── casefile.py
│   │       ├── outbox.py
│   │       ├── dispatch.py
│   │       └── linkage.py
│   ├── audit/
│   │   └── replay.py
│   ├── coordination/
│   ├── contracts/
│   ├── models/
│   ├── rule_engine/
│   ├── outbox/
│   ├── linkage/
│   ├── integrations/
│   ├── storage/
│   ├── registry/
│   └── health/
├── tests/
│   ├── unit/
│   │   ├── pipeline/
│   │   │   ├── test_scheduler.py
│   │   │   └── stages/test_gating.py
│   │   ├── audit/test_decision_reproducibility.py
│   │   ├── config/
│   │   ├── coordination/
│   │   └── ...
│   ├── integration/
│   │   ├── pipeline/
│   │   ├── coordination/
│   │   └── integrations/
│   └── atdd/
├── docs/
│   ├── architecture.md
│   ├── architecture-patterns.md
│   ├── project-structure.md
│   ├── development-guide.md
│   ├── developer-onboarding.md
│   ├── contracts.md
│   └── ...
├── scripts/
├── harness/
└── artifact/
    └── planning-artifacts/
```

## Architectural Boundaries

**API boundaries:**

- No new inbound/outbound API surfaces in this release.
- Existing event contracts remain fixed in `contracts/`.
- Rulebook policy remains externalized in `config/policies/rulebook-v1.yaml`.

**Component boundaries:**

- Scoring and gate-input enrichment remain inside `pipeline/stages/gating.py`.
- Orchestration flow remains in `pipeline/scheduler.py` and `__main__.py`.
- Deterministic gate evaluation remains split between `rule_engine/` (AG0-AG3) and stage-local AG4-AG6 handling in `gating.py`.

**Service boundaries:**

- Hot path: evidence -> peak -> topology -> gate input -> gate decision -> casefile -> dispatch.
- Cold path/diagnosis package remains isolated from scoring logic (D6).
- External integration adapters (`integrations/`) remain unchanged by scoring design.

**Data boundaries:**

- `GateInputContext` and `GateInputV1` structure remains unchanged.
- `ActionDecisionV1` structure remains unchanged.
- Scoring narrative metadata flows via `decision_basis` without contract-field expansion.

## Allowed Change Surface (Hard Boundary)

**Primary release files:**

- `src/aiops_triage_pipeline/pipeline/stages/gating.py`
- `src/aiops_triage_pipeline/pipeline/scheduler.py` (only if glue adjustments are needed)
- `src/aiops_triage_pipeline/config/settings.py`
- `config/.env.dev`
- `config/.env.uat.template`
- `config/.env.prod.template`
- `config/policies/rulebook-v1.yaml` (only threshold/reason alignment if required)

**Primary release tests:**

- `tests/unit/pipeline/stages/test_gating.py`
- `tests/unit/pipeline/test_scheduler.py`
- `tests/unit/audit/test_decision_reproducibility.py`
- `tests/unit/config/*` (for env/config assertions as needed)

**Documentation surface (broad refresh approved):**

- `docs/architecture.md`
- `docs/architecture-patterns.md`
- `docs/project-structure.md`
- `docs/runtime-modes.md`
- `docs/development-guide.md`
- `docs/developer-onboarding.md`
- `docs/contracts.md`
- `docs/data-models.md`
- `docs/component-inventory.md`
- `docs/project-overview.md`
- `docs/index.md`

## Protected Zones (Do Not Modify Unless Explicitly Re-approved)

- `src/aiops_triage_pipeline/contracts/*` (frozen contract shapes)
- `src/aiops_triage_pipeline/diagnosis/*` (cold-path package)
- `src/aiops_triage_pipeline/integrations/*` (adapter behavior)
- `src/aiops_triage_pipeline/storage/*` and `outbox/*` state-machine semantics
- `src/aiops_triage_pipeline/linkage/*` retry transition semantics

## Requirements to Structure Mapping

**FR group: Confidence scoring (FR1-FR7)**

- Core implementation: `src/aiops_triage_pipeline/pipeline/stages/gating.py`
- Invocation/orchestration context: `src/aiops_triage_pipeline/pipeline/scheduler.py`
- Runtime flow wiring: `src/aiops_triage_pipeline/__main__.py`
- Unit coverage: `tests/unit/pipeline/stages/test_gating.py`

**FR group: AG4 gate evaluation (FR8-FR11)**

- Policy authority: `config/policies/rulebook-v1.yaml`
- Stage enforcement: `src/aiops_triage_pipeline/pipeline/stages/gating.py`
- Stage + scheduler tests: `tests/unit/pipeline/stages/test_gating.py`, `tests/unit/pipeline/test_scheduler.py`

**FR group: Peak history depth (FR12-FR14)**

- Env configuration: `config/.env.dev`, `config/.env.uat.template`, `config/.env.prod.template`
- Settings defaults/validation: `src/aiops_triage_pipeline/config/settings.py`
- Runtime consumption: `src/aiops_triage_pipeline/__main__.py`
- Config test surface: `tests/unit/config/*`

**FR group: Shard lease TTL (FR15-FR17)**

- Env configuration: `config/.env.*`
- Settings constraints: `src/aiops_triage_pipeline/config/settings.py`
- Runtime lease wiring: `src/aiops_triage_pipeline/__main__.py`
- Coordination primitive: `src/aiops_triage_pipeline/coordination/shard_registry.py`
- Test surface: `tests/unit/coordination/*` and integration coordination tests

**FR group: Audit & observability (FR18-FR20)**

- Decision construction path: `src/aiops_triage_pipeline/pipeline/stages/gating.py`
- Replay guarantee: `src/aiops_triage_pipeline/audit/replay.py`
- Replay tests: `tests/unit/audit/test_decision_reproducibility.py`
- Operational metrics/logging: `src/aiops_triage_pipeline/health/*`

## Integration Points

**Internal communication:**

- Stage outputs are typed models passed through scheduler/orchestrator boundaries.
- Gate-input enrichment consumes `evidence_output`, `peak_output`, and topology `context_by_scope`.
- Rulebook decision output feeds casefile assembly and downstream dispatch.

**External integrations (unchanged for this release):**

- Prometheus ingestion (evidence/peak inputs)
- Redis (sustained/peak cache, dedupe, coordination)
- PostgreSQL (outbox/linkage persistence)
- S3/MinIO (casefile persistence)
- Kafka publication
- PagerDuty/Slack/ServiceNow action adapters

**Data flow:**

1. Evidence stage builds anomaly findings and evidence status map.
2. Peak stage adds sustained/peak context and profiles.
3. Topology stage resolves routing/criticality context.
4. Gating stage derives confidence + candidate action and builds `GateInputV1`.
5. Rulebook applies AG0-AG6 to produce final `ActionDecisionV1`.
6. Casefile and dispatch stages persist artifacts and emit side effects.

## File Organization Patterns

**Configuration files:**

- Environment-specific runtime values in `config/.env.*`.
- Deterministic policy contracts in `config/policies/*.yaml`.
- Settings model remains single source of runtime validation.

**Source organization:**

- Domain logic by package (`pipeline`, `audit`, `coordination`, `rule_engine`, etc.).
- Stage logic remains in `pipeline/stages/` with no new package creation for this release.

**Test organization:**

- Tests mirror production module boundaries (unit/integration/audit folders).
- No release-specific catch-all test directory.

**Asset organization:**

- No new static asset domains; artifacts remain under `artifact/`.

## Development Workflow Integration

**Development server structure:**

- Runtime mode entrypoint remains `python -m aiops_triage_pipeline --mode ...`.
- No new runtime mode introduced for scoring.

**Build process structure:**

- Existing uv + Docker build structure remains unchanged.
- Lint/test gates remain unchanged, including full Docker-backed regression run with zero skips.

**Deployment structure:**

- Single image/multi-mode deployment model remains unchanged.
- Environment behavior continues to be controlled by `.env.*` + policy files.
