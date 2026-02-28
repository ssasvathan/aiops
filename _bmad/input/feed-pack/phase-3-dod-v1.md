# Phase 3 — Definition of Done (DoD) — v1 (Freeze Candidate)
**Date:** 2026-02-22  
**Theme:** End-to-end coverage: runtime topology + sink health evidence.  
**Non-negotiables:** YAML remains governed logical truth; observed topology is best-effort; exposure caps preserved.

---

## Purpose (why Phase 3 exists)
Phase 3 reduces “wrong layer / wrong owner” triage by combining:
- **Governed logical topology** (registry/YAML)
- **Observed runtime topology** (Dynatrace Smartscape + platform edge facts)
- **Sink health evidence** (so cases can attribute failures beyond Kafka)

---

## In-scope deliverables (capabilities)
1) **Coverage-weighted Hybrid Topology (operational)**
   - YAML: canonical `stream_id` grouping + ACL/sink metadata + exposure caps.
   - Dynatrace Smartscape: observed service dependency graph (best-effort).
   - Platform instrumentation: emits “edge facts” (producer→topic, consumer_group→topic, service→sink) even if apps don’t instrument.
   - Topology enrichment produces an **instance-scoped** view keyed by `(env, cluster_id)`.

2) **Sink Health Evidence Track (standardized primitives)**
   - Evidence primitives supported (at minimum):  
     `SINK_CONNECTIVITY`, `SINK_ERROR_RATE`, `SINK_LATENCY`, `SINK_BACKLOG`, `SINK_THROTTLE`, `SINK_AUTH_FAILURE`
   - Cases can represent sink evidence as `AVAILABLE/UNKNOWN` with provenance/confidence.
   - Slack/excerpts remain executive-safe: no sensitive sink endpoints/identifiers.

3) **Improved diagnosis attribution**
   - The system can present: “Kafka symptoms vs downstream sink symptoms” with clear evidence references and uncertainty.
   - Ownership routing improves using runtime edges when registry coverage is partial (but never overrides governance caps).

---

## Explicit non-goals (Phase 3 is NOT)
- Not replacing registry/YAML with Dynatrace.
- Not requiring full distributed tracing coverage or universal instrumentation.
- Not enabling automatic remediation across sinks in PROD/TIER_0 by default.

---

## Success metrics
- **Topology coverage:** for top N critical streams, runtime enrichment covers **≥ 70%** of expected edges (as measured by edge-fact presence or Smartscape visibility).
- **Attribution improvement:** “wrong layer” misdiagnosis reduced by **≥ 30%** vs Phase 1 baseline (measured via labels).
- **Sink visibility:** for streams with defined sinks, sink evidence is `AVAILABLE` (not UNKNOWN) for **≥ 60%** of relevant cases (initial target).
- **Exposure safety:** zero incidents of sensitive sink identifiers in Slack/excerpts (sampling + automated checks).

---

## Acceptance criteria (Definition of Done)
1) **Hybrid topology output is instance-scoped**
   - All enriched topology views are keyed by `(env, cluster_id)` and map anomalies → `stream_id` + instance topology.
2) **Governance remains authoritative**
   - YAML stream grouping and exposure caps are never overridden by observed topology.
3) **Sink evidence integrates cleanly**
   - Sink evidence is represented as Evidence primitives with provenance/confidence and supports UNKNOWN.
4) **Operational viability**
   - Responders can use the enriched view to answer: “is this Kafka, consumer app, or sink?” with evidence.
5) **Local-dev independence**
   - Phase 3 components default to `OFF/LOG` locally; mock inputs (edge facts / sink signals) allowed via local files.

---

## Exit criteria (when Phase 3 is “done enough”)
- Meets success metrics for at least **8 consecutive weeks** (higher bar due to scope).
- Runbooks exist for the hybrid topology signals (what coverage means, how to interpret gaps).
- The system produces evidence-driven recommendations for next enhancements (e.g., where to instrument next) without breaking Phase 1 guardrails.

