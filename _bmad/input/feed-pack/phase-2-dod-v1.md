# Phase 2 — Definition of Done (DoD) — v1 (Freeze Candidate)
**Date:** 2026-02-22  
**Theme:** Better evidence + better triage quality (human-led).  
**Non-negotiables:** Prometheus truth, deterministic guardrails (Rulebook), auditable CaseFile.

---

## Purpose (why Phase 2 exists)
Phase 2 reduces *UNKNOWN* and improves triage accuracy by expanding evidence coverage and adding assistive intelligence **without** removing human ownership.

---

## In-scope deliverables (capabilities)
1) **Expanded evidence sources (beyond broker-only)**
   - Client/app-level telemetry signals where available (e.g., consumer processing, errors, saturation).
   - Standardize evidence into the same primitives model (EvidenceStatus + provenance + confidence).

2) **Runbook assistant (read-only)**
   - For each case, provide “next best checks” with links to evidence and rationale.
   - Output is advisory only; **Rulebook still gates actions**.

3) **Diagnosis quality boosters (optional, advisory)**
   - Seasonality-aware scoring, clustering similar cases, confidence adjustment suggestions.
   - Must surface as “recommendations,” not decisions.

4) **Operational feedback loop**
   - Minimal labeling capture: `resolution_category`, `owner_confirmed`, `false_positive`, `missing_evidence_reason`.
   - Used to drive Phase 2/3 backlog and future ML readiness.

---

## Explicit non-goals (Phase 2 is NOT)
- Not full autonomous remediation in PROD/TIER_0.
- Not replacing deterministic guardrails with ML.
- Not requiring all application teams to instrument before value is delivered.

---

## Success metrics (measured in PROD + nonprod)
- **UNKNOWN reduction:** for top 3 anomaly families, UNKNOWN evidence rate reduced by **≥ 50%** vs Phase 1 baseline.
- **Routing accuracy:** misroute rate **< 5%** (measured via owner-confirmed labels or manual sampling).
- **Triage usefulness:** ≥ **80%** of sampled cases are rated “useful” by responders (simple scale or reaction tag).
- **Noise control:** no increase in paging storms; dedupe effectiveness maintained (repeat PAGE for same fingerprint within TTL remains near-zero).
- **Outbox reliability:** outbox SLOs and DEAD=0 posture maintained under new evidence load.

---

## Acceptance criteria (Definition of Done)
1) **Evidence model compatibility preserved**
   - All new signals map into Evidence primitives with explicit `provenance`, `confidence`, and `UNKNOWN` handling.
2) **Guardrails remain authoritative**
   - Rulebook outputs (gate ids + reasons) remain present and deterministically explain any capping decision.
3) **CaseFile remains system-of-record**
   - New evidence sources referenced/embedded in CaseFile without breaking exposure caps.
4) **Local-dev independence**
   - Phase 2 features run locally with integrations in `LOG/OFF` modes; no external Slack/SN required.
5) **Labeling loop works**
   - At minimum, the system can capture/attach labels to CaseFile for a subset of cases (even if via a simple operator workflow).

---

## Exit criteria (when Phase 2 is “done enough”)
- Metrics above are met for at least **4 consecutive weeks**.
- Stable operational playbook exists for new evidence sources (what to trust, what can be UNKNOWN).
- Clear backlog for Phase 3 (topology gaps, sink evidence) is evidence-driven (from labels + UNKNOWN reasons).

