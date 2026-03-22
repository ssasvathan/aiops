# Innovation & Novel Patterns

## Detected Innovation Areas

**1. Guardrails-as-frozen-contract decoupled from evolving diagnosis.**
Most AIOps platforms are either "all ML" or "all rules." This architecture explicitly separates deterministic safety gates (Rulebook AG0–AG6, frozen) from diagnosis intelligence (can evolve, can add ML) — with the structural guarantee that ML never overrides guardrails in PROD/TIER_0. The Rulebook is a safety engineering artifact, not a configuration option.

**2. LLM as bounded synthesis component, not action authority.**
The LLM synthesizes diagnosis hypotheses, ranks them, and explains evidence — but deterministic gates make the final action decision. LLM outputs must cite evidence IDs, propagate UNKNOWN explicitly, and never invent metric values. If LLM is unavailable, the pipeline degrades to deterministic findings with UNKNOWN semantics and safely-capped actions. This is a novel pattern: LLM-assisted observability with structural safety guarantees.

**3. Evidence truthfulness as an architectural invariant (UNKNOWN-not-zero).**
Missing Prometheus series → `EvidenceStatus=UNKNOWN`, propagated through every layer: evidence collection, peak detection, sustained computation, confidence scoring, gating. Most observability tools silently treat missing data as zero or drop it. Here, UNKNOWN is a first-class signal with explicit downstream consequences (confidence downgrade, action capping).

**4. Evidence-contract abstraction (contract-driven observability ingestion).**
`GateInput.v1` + `prometheus-metrics-contract-v1` + `peak-policy-v1` form a layered contract stack: canonical metric names → evidence primitives → gating envelope. New evidence sources (Phase 2 client telemetry, Phase 3 sink health) plug into the same abstraction. Evidence requirements are declared per Finding (`finding.evidence_required[]`), not in a central list — new anomaly families bring their own evidence contracts.

**5. Hot-path minimal contract + durability invariants as audit-first eventing.**
Kafka forwards only `CaseHeaderEvent.v1` + `TriageExcerpt.v1` — no object-store reads in the routing/paging path. CaseFile written to object storage before publish (Invariant A); outbox ensures publish-after-crash (Invariant B2). This is latency-safe (hot-path consumers never block on object-store reads) AND audit-safe (CaseFile always exists before any downstream action).

**6. Storm-control as safety engineering.**
Dedupe (AG5) + degraded-mode caps (Redis down → NOTIFY-only) prevent operational harm. `DegradedModeEvent` provides transparency. This treats alert storms as a safety hazard, not just a UX annoyance — the system structurally cannot generate paging storms even when its own infrastructure degrades.

**7. Replayability guarantee (reproducible decisions).**
CaseFiles record policy versions (rulebook_version, peak_policy_version, prometheus_metrics_contract_version, exposure_denylist_version, diagnosis_policy_version). Given the same evidence + same policy versions → same gating result. Auditors can replay any historical decision and verify it produces the same outcome. This is tamper-evident (write-once + SHA-256 hash) and version-stamped.

**8. Instance-scoped multi-cluster topology + backward-compatible migration.**
`streams[].instances[]` keyed by `(env, cluster_id)` with `topic_index` scoped per instance prevents cross-cluster collisions. Loader rules handle v0→v1 migration with deterministic canonicalization, compat views for legacy consumers, and fail-fast validation. This is correctness-by-construction for multi-cluster/DR environments.

**9. Hybrid topology governance hierarchy + coverage weighting (Phase 3).**
Three topology sources with explicit governance hierarchy: YAML governs (canonical stream grouping, exposure caps, ownership), Smartscape enriches (observed runtime dependencies, best-effort), platform edge facts supplement (producer→topic, consumer→topic edges emitted without app instrumentation). Observed topology never overrides governed topology. Coverage weighting makes gaps explicit rather than silent.

**10. Two-mode local dev with standardized integration modes.**
Mode A (docker-compose local infra) and Mode B (opt-in connection to dedicated remote environment) with `OFF | LOG | MOCK | LIVE` integration modes. Default is LOG (safe, visible). LIVE restricted to approved non-prod endpoints. Each environment (DEV, UAT, PROD) has dedicated infrastructure. Full pipeline testable locally with zero external calls.

**11. Postmortem enforcement + SN linkage + labeling loop as data flywheel.**
Selective postmortem enforcement (`PM_PEAK_SUSTAINED`) → SN Problem + PIR tasks (Phase 1B) → labeling loop (`owner_confirmed`, `resolution_category`, `false_positive`, `missing_evidence_reason`) → ML-readiness data quality gates → Phase 2 advisory ML. Each phase generates the data the next phase consumes. The labeling loop is not an afterthought — it's the structural enabler for advisory ML.

## Validation Approach

- **Invariant testing:** Invariant A (write-before-publish), Invariant B2 (publish-after-crash), UNKNOWN propagation, and exposure denylist enforcement are testable locally in Phase 0
- **Replayability verification:** Regression suite that replays historical evidence against specific policy versions and asserts identical gating outcomes
- **LLM degradation testing:** Pipeline must produce valid CaseFile + header/excerpt with LLM in stub/failure-injection mode (local/test only); actions must be safely gated
- **Storm-control simulation:** Inject Redis failures during active cases; verify NOTIFY-only behavior and `DegradedModeEvent` emission
- **Migration correctness:** Loader tests with v0 + v1 mixed registries; verify no cross-cluster collisions and compat views work

## Innovation Risk Mitigation

| Innovation Risk | Mitigation |
|---|---|
| LLM generates hallucinated evidence | Provenance requirement: must cite evidence IDs; schema validation rejects fabricated fields; UNKNOWN propagation enforced |
| LLM unavailability blocks pipeline | Non-blocking: deterministic fallback to NEEDS_MORE_EVIDENCE + gap; actions safely capped |
| LLM cost scales with case volume | Conditional invocation (PROD+TIER_0 or sustained only); bounded token input (excerpt, not raw logs) |
| Hybrid topology observed data overrides governance | Governance hierarchy: YAML > Smartscape > edge facts; observed never overrides governed |
| Labeling loop produces low-quality ML training data | Data quality gates: ≥ 70% label completion, consistency validation before ML consumption |
| Migration breaks legacy consumers | Compat views + deprecation plan (v0 supported Phase 1A, warnings Phase 1B/2, removed Phase 2+) |
