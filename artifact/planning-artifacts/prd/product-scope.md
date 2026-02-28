# Product Scope

## MVP — Phase 0 + Phase 1A + Phase 1B (Delivery Critical Path)

**Phase 0 (Local Harness — NOT MVP):**
- Prove lag buildup, throughput-constrained proxy, and volume drop patterns using real Prometheus metrics
- Validate Redis TTL behavior (evidence cache + dedupe) and peak profile confidence
- Validate outbox state-machine transitions (PENDING_OBJECT → READY → SENT + RETRY/DEAD)
- Validate ownership mapping against topology registry
- Validate `DegradedModeEvent` emission when Redis is unavailable
- Validate `TelemetryDegradedEvent` emission when Prometheus is unavailable (no all-UNKNOWN cases emitted; actions capped)
- Harness stream naming separate from prod naming

**Phase 1A (MVP Triage Pipeline):**
- Evidence Builder → Peak Profile → Topology+Ownership Enrichment → CaseFile (object storage) → Outbox → Kafka header/excerpt → Rulebook gating (AG0–AG6) → Action Executor (env caps + dedupe) → SOFT postmortem enforcement (Slack/log)
- All frozen contracts implemented: Rulebook, GateInput, Redis TTL, Outbox, Peak, Prometheus metrics, Registry loader, local-dev
- Clusters: Business_Essential, Business_Critical (prod)
- Exposure denylist enforced on TriageExcerpt + Slack
- Storm control: dedupe across PAGE/TICKET/NOTIFY with explicit `DegradedModeEvent` on Redis failure

**Phase 1B (SN Postmortem Automation):**
- Link to PD-created Incident via tiered correlation (Tier 1: PD field → Tier 2: keyword → Tier 3: heuristic)
- Idempotent Problem + PIR task upsert (external_id keyed)
- 2-hour retry window with exponential backoff + jitter
- FAILED_FINAL → Slack escalation (exposure-safe)
- Least-privilege SN integration user (read incident, CRUD problem/task)
- Track Tier 1 vs Tier 2/3 fallback rates from day one

## Growth Features — Phase 2 (Better Evidence + Better Triage Quality)

- Expanded evidence sources (client/app-level telemetry) mapped to Evidence primitives with provenance/confidence/UNKNOWN
- Runbook assistant (read-only, advisory — Rulebook still gates)
- Advisory ML boosters: top-N hypothesis ranking, confidence adjustment from learned patterns — ML never directly triggers actions in PROD/TIER_0
- Labeling feedback loop: `resolution_category`, `owner_confirmed`, `false_positive`, `missing_evidence_reason`
- ML-readiness data-quality gates: label completion rate ≥ 70% for eligible cases; validation/consistency checks for key labels (`owner_confirmed`, `resolution_category`) must pass before ML models consume them
- Success: UNKNOWN reduction ≥ 50%, misroute rate < 5%, triage usefulness ≥ 80% — measured 4 consecutive weeks

## Vision — Phase 3 (Hybrid Topology + Sink Health)

- Coverage-weighted hybrid topology: YAML (governed logical truth) + Smartscape (best-effort observed) + platform edge facts (emit without app instrumentation)
- Sink Health Evidence Track: `SINK_CONNECTIVITY`, `SINK_ERROR_RATE`, `SINK_LATENCY`, `SINK_BACKLOG`, `SINK_THROTTLE`, `SINK_AUTH_FAILURE`
- Improved diagnosis attribution: "Kafka symptoms vs downstream sink symptoms" with evidence references and uncertainty
- Instance-scoped enriched topology views keyed by `(env, cluster_id)`
- YAML governance never overridden by observed topology
- Success: edge coverage ≥ 70%, "wrong layer" misdiagnosis reduced ≥ 30%, sink evidence AVAILABLE ≥ 60%, exposure violations = 0 — measured 8 consecutive weeks
