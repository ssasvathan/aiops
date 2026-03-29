# Product Scope

## MVP — Revision Phase (All-or-Nothing)

Operational activation — all 11 revision changes land as a single all-or-nothing delivery for the dev OpenShift deployment. This is not a feature-prioritization MVP; it is a complete activation package where each CR addresses a specific gap between the delivered baseline and operational readiness. Partial delivery leaves the system unable to prove itself under real conditions.

**Resource Requirements:** Single developer (Sas) with AI-assisted implementation. The existing 8-epic baseline provides complete test coverage and architectural scaffolding — the revision phase is controlled deltas against a stable, tested codebase.

| # | Change | Category |
|---|---|---|
| CR-01 | Wire Redis cache layer (sustained state + peak profiles + batch ops) | Activation |
| CR-02 | DSL-driven rulebook gate engine (YAML-authoritative evaluation) | Refactor |
| CR-03 | Unified per-scope metric baselines (replace hardcoded thresholds) | New capability |
| CR-04 | Sharded findings cache for hot/hot K8s deployment | New capability |
| CR-05 | Distributed hot/hot Phase 1 — multi-replica safety | New capability |
| CR-06 | Evidence summary builder for LLM consumption | Activation |
| CR-07 | Cold-path Kafka consumer pod (implement runtime mode) | Activation |
| CR-08 | Remove cold-path invocation criteria (unconditional LLM diagnosis) | Simplification |
| CR-09 | Optimize cold-path LLM prompt for higher quality output | Enhancement |
| CR-10 | Redis bulk load & peak stage memory efficiency | Performance |
| CR-11 | Topology registry simplify to single format | Simplification |

**Operational setup (separate from code changes):** Dynatrace dashboard, Kibana/Elastic saved searches, OpenShift deployment manifests, OTLP exporter configuration, Elastic JSON field parsing verification, Postgres outbox DDL script for database provisioning.

**Core User Journeys Supported:**
- Responder success path (requires CR-01, CR-02, CR-03, CR-05, CR-06, CR-07, CR-08, CR-09)
- Responder degraded telemetry path (requires CR-01, CR-03)
- Operator deployment and tuning path (requires CR-02, CR-05, CR-11)
- Maintainer configuration path (requires CR-11)
- Recipients improved alerting (requires all hot-path CRs)

All CRs are must-have. No CR can be deferred without breaking the operational activation goal.

## Implementation Ordering (Dependency-Driven)

| Phase | CRs | Rationale |
|---|---|---|
| Foundation | CR-01 (Wire Redis), CR-11 (Topology simplify) | CR-01 unblocks CR-03, CR-04, CR-05, CR-10; CR-11 is independent cleanup |
| Core pipeline | CR-02 (DSL rulebook), CR-03 (Unified baselines) | CR-02 is independent refactor; CR-03 depends on CR-01 |
| Multi-replica | CR-04 (Sharded cache), CR-05 (Distributed hot/hot), CR-10 (Redis bulk + memory) | All depend on CR-01; CR-05 is highest-risk new capability |
| Cold path | CR-06 (Evidence summary), CR-07 (Cold-path consumer), CR-08 (Remove criteria), CR-09 (Prompt optimization) | Sequential chain: CR-06 > CR-07 > CR-08/CR-09 |

## Documentation Updates (Per CR)

Each CR must update affected documentation in `docs/` and `README.md` as part of the same change set. Documentation drift from prior phases is not acceptable for a system targeting operational deployment.

All documentation must reference only project-native concepts (CRs, contracts, pipeline stages, runtime modes, policy files). References to BMAD artifacts, story identifiers, epic numbers, or workflow-specific methodology terminology must never appear in `docs/` or `README.md` — these become irrelevant over the project's operational lifetime and create confusion for future maintainers.

| CR | Documentation Updates Required |
|---|---|
| CR-01 | `runtime-modes.md` (dependency matrix), `local-development.md` (runtime mode status) |
| CR-02 | `architecture-patterns.md` (gate evaluation pattern) |
| CR-03 | `runtime-modes.md` (baseline computation mechanism), policy file references in relevant docs |
| CR-05 | `architecture.md` (multi-replica deployment), `deployment-guide.md` (coordination config), `runtime-modes.md` (Redis dependency for coordination), `README.md` (architecture principles, runtime modes table) |
| CR-07 | `runtime-modes.md` (cold-path fully wired), `local-development.md` (runtime mode status table), `README.md` (runtime modes table — no longer "Bootstrap only") |
| CR-11 | `component-inventory.md` (single format), `project-structure.md` (remove v0/v1 reference), `README.md` (project structure tree) |

## Risk Mitigation Strategy

**Technical Risks:**

| Risk | Severity | Mitigation |
|---|---|---|
| CR-02 (DSL rulebook) — AG1 multi-step cap logic extraction | High | Dedicated handler with explicit multi-outcome return; 7 existing AG1 parametrized test cases as regression net |
| CR-05 (Distributed hot/hot) — new coordination layer | High | Feature flag (default false) for incremental rollout; deploy at 1 replica first, verify, then scale |
| CR-03 (Unified baselines) — broadest code surface change | Medium | New anomaly detection policy with cold-start fallbacks preserving current behavior when baselines unavailable |
| CR-02 safety invariant shift — structural to behavioral | Medium | Post-condition safety assertions catch violations regardless of YAML content; 36 existing test functions (60+ cases) as regression safety net |
| CR-07 (Cold-path consumer) — first Kafka consumer in the system | Low | Existing diagnosis chain is fully built and tested; consumer is thin orchestration layer |

**Resource Risks:**

Single-developer project. Mitigation: AI-assisted implementation, existing comprehensive test suite, and all-or-nothing scope prevents partial delivery ambiguity. If timeline pressure emerges, the implementation ordering allows early CRs (CR-01, CR-11, CR-02) to land and stabilize before higher-risk CRs.

## Growth Features (Post-MVP — UAT/Prod Promotion)

- Stable dev operation with documented triage quality evidence justifying UAT deployment
- Environment promotion through dev > UAT > prod with increasing action cap ceilings
- Hard postmortem enforcement lifecycle (mandatory creation, quality gates, follow-through tracking)
- CI/CD pipeline definitions

## Vision (Future)

- Multi-infrastructure telemetry expansion — VMs, OpenShift, databases, applications via additional evidence collectors producing the same Finding and GateInput contracts
- Application telemetry instrumentation — instrumenting existing applications with metrics, structured logging, and distributed tracing
- ML-enhanced root cause analysis — agent-to-agent invocation with enterprise RCA agent
- Scope-based partitioning / consistent hashing for horizontal throughput scaling
- Cross-pod HealthRegistry synchronization
- KPI dashboards for senior management
