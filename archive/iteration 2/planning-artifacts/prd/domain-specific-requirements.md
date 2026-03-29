# Domain-Specific Requirements

The following requirements reflect AIOps domain constraints that shape the system's architecture independently of any specific CR — they are standing invariants that every revision change must preserve.

## Audit & Decision Reproducibility

- 25-month casefile retention with write-once semantics and SHA-256 hash chains ensuring tamper-evident artifact integrity
- Policy version stamping in every casefile — any historical decision can be replayed with the exact rulebook, peak policy, denylist, and anomaly detection policy versions active at decision time
- Schema envelope versioning with perpetual read support across the retention window — old casefiles remain deserializable as schema versions evolve
- Structured logs with correlation IDs (case_id) enabling field-level querying of the full decision trail in Elastic (LASS)

## Operational Safety Invariants

- PAGE is structurally impossible outside PROD+TIER_0 — enforced by environment caps and post-condition safety assertions independent of YAML correctness
- Actions only cap downward, never escalate — monotonic reduction is a design invariant, not a configuration choice
- Environment-based action caps: local=OBSERVE, dev=NOTIFY, uat=TICKET, prod=PAGE
- Hot/cold path separation — the LLM advisory path has no import path, no shared state, and no conditional wait on the deterministic hot path

## Degraded Mode Handling

- UNKNOWN evidence is never collapsed to PRESENT or zero — missing-evidence semantics propagate end-to-end through gate evaluation
- Degradable dependency failures update HealthRegistry and continue with capped behavior
- Critical dependency/invariant failures halt processing with loud failure (no silent fallback)
- Redis unavailability: cycle lock fails open (preserves availability, worst case equals single-instance behavior), sustained state falls back to None (conservative — no false sustained=true)

## Integration Safety

- All external integrations (PagerDuty, Slack, ServiceNow, LLM) implement OFF|LOG|MOCK|LIVE semantics
- Default-safe operation: LOG unless explicitly configured otherwise — prevents unintended outbound effects in local/dev
- Prod enforcement rejects MOCK/OFF for critical integrations
- Shared denylist enforcement (`apply_denylist()`) at all outbound boundaries — no boundary-specific reimplementations
- ServiceNow MI-1 guardrails prevent major-incident write scope

## Multi-Replica Coordination Safety

- Zero duplicate dispatches across pods via distributed cycle lock (one pod executes per interval, losers yield)
- Consistent sustained-window state across replicas via externalized Redis storage
- Atomic AG5 deduplication replacing two-step is_duplicate()+remember() with single SET NX EX
- Outbox row locking preventing concurrent publishers from selecting the same batch
- Pod identity in OTLP resource attributes and structlog context for per-instance observability
- Feature-flagged rollout (DISTRIBUTED_CYCLE_LOCK_ENABLED, default false) for incremental activation

## Data Integrity

- Write-once casefile stages — each stage file written exactly once by its owning pipeline component, no read-modify-write, no overwrites
- Durable outbox state machine with source-state-guarded SQL transitions (PENDING_OBJECT > READY > SENT/RETRY/DEAD)
- Hash chain verification — each casefile stage includes SHA-256 hash of prior stage files it depends on
- Outbox DEAD=0 standing posture with monitoring and alerting
- S3 put_if_absent enforces idempotent casefile persistence across replicas
