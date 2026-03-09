# Architecture Patterns

## Part: core

- project_type_id: backend
- primary_pattern: Service/API-centric event-driven pipeline
- secondary_patterns:
  - Stage-based processing pipeline (`evidence -> peak -> topology -> casefile -> outbox -> gating -> dispatch`)
  - Contract-first modeling (Pydantic frozen schemas for events, policy, and domain payloads)
  - Durable outbox pattern for reliable Kafka publication
  - Retry-state orchestration for ServiceNow linkage durability
  - Adapter-based integration boundaries (Kafka, Prometheus, Slack, PagerDuty, ServiceNow)

## Pattern Rationale

- `src/aiops_triage_pipeline/pipeline/stages/*` implements deterministic stage modules with explicit IO models.
- `src/aiops_triage_pipeline/outbox/*` separates state transitions, persistence, and publisher loop concerns.
- `src/aiops_triage_pipeline/linkage/*` uses durable SQL retry state with source-state guarded transitions.
- `src/aiops_triage_pipeline/contracts/*` and `models/*` enforce immutable event/data contracts.
- `src/aiops_triage_pipeline/integrations/*` isolates external side effects behind mode-aware adapters (`OFF|LOG|MOCK|LIVE`).

## Architectural Style Assignment

- Assigned style: **Layered backend with event-pipeline core and durable side-effect boundaries**.
- Why: orchestration and business logic are centralized in pipeline stages, while persistence/integration effects are isolated through repositories and adapters.
