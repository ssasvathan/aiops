# Project Scoping & Phased Development

## MVP Strategy & Philosophy

**MVP Approach:** Problem-solving MVP — prove that deterministic, evidence-based triage with safety guardrails is operationally useful before adding intelligence layers. The MVP must demonstrate: "a real incident → correct evidence → correct routing → safe action → auditable record → LLM-enriched diagnosis" end-to-end.

**Why this order:** Phase 0 proves the signals are real (no simulated telemetry). Phase 1A proves the pipeline is operationally safe (guardrails, durability, degraded modes) with LLM-enriched diagnosis on the cold path. Phase 1B proves the system integrates into existing incident management. Only after this foundation exists does it make sense to add advisory ML (Phase 2) or broader topology coverage (Phase 3). Each phase generates the data and trust the next phase requires.

## MVP Feature Set — Phase 0 + Phase 1A + Phase 1B (Delivery Critical Path)

**Core User Journeys Supported:**
- Journey 1: Platform Ops — PAGE path (sustained lag, peak, TIER_0) ✓
- Journey 2: Service Owner — TICKET path (consumer lag, app-team routing, reroute/label) ✓
- Journey 3: Data Steward — NOTIFY path (volume drop, SOURCE_TOPIC) ✓
- Journey 4: Auditor — postmortem compliance review ✓
- Journey 5: Developer — local dev Mode A/B ✓
- Journey 6: SRE Manager — degraded mode + outbox health ✓
- Journey 7: Sink Health (Phase 3) — NOT in MVP; sink evidence is UNKNOWN

**Must-Have Capabilities (MVP cut-line):**

| Capability | Phase | Cut-line Rationale |
|---|---|---|
| Evidence Builder (3 signal patterns: lag, constrained proxy, volume drop) | 0 | Proves Prometheus truth; no simulated telemetry |
| Peak Profile (5-min buckets, sustained detection) | 0+1A | Required for `PM_PEAK_SUSTAINED` and AG4/AG6 |
| Topology Registry loader (v0+v1, instance-scoped) | 1A | Required for ownership routing and topic_role |
| CaseFile triage write-once + hash (Invariant A) | 1A | Non-negotiable durability invariant |
| Outbox (Invariant B2) + SLO + alerting | 1A | Non-negotiable publish-after-crash |
| Rulebook gating AG0–AG6 | 1A | Non-negotiable safety gates |
| ActionDecision.v1 | 1A | Required for action execution + audit |
| LLM Diagnosis (cold-path, non-blocking) | 1A | Mandatory for DiagnosisReport.v1; hot path does not wait; fallback: verdict=UNKNOWN, confidence=LOW, reason_codes=[LLM_TIMEOUT/UNAVAILABLE/ERROR] |
| Exposure denylist (versioned) | 1A | Non-negotiable for bank context |
| Dedupe + DegradedModeEvent | 1A | Storm control is safety-critical |
| Hot-path header/excerpt (no object-store reads) | 1A | Latency contract |
| SOFT postmortem (Slack/log) | 1A | `PM_PEAK_SUSTAINED` enforcement |
| SN linkage (tiered correlation, idempotent upsert) | 1B | HARD postmortem automation |
| Local-dev Mode A (docker-compose, zero external) | 0+1A | Developer independence |

**LLM Decision (locked):** LLM diagnosis is mandatory in Phase 1A. It is cold-path and non-blocking:
- Hot path (CaseFile triage write → outbox publish → Rulebook gating → action execution) must NOT wait on LLM.
- LLM consumes TriageExcerpt + structured evidence summary (exposure-capped). Must cite evidence refs/IDs. Missing evidence stays UNKNOWN.
- If LLM is unavailable/timeout/error: emit schema-valid DiagnosisReport with `verdict=UNKNOWN`, `confidence=LOW`, `reason_codes=[LLM_TIMEOUT | LLM_UNAVAILABLE | LLM_ERROR]`. Pipeline continues with deterministic findings + Rulebook gating.
- LLM never overrides Rulebook — it informs diagnosis narrative and hypothesis ranking only.
- CaseFile `diagnosis.json` is written when LLM completes; CaseFile `triage.json` is complete and actionable without it.

**Explicitly NOT in MVP:**
- Client/app-level telemetry (Phase 2)
- Runbook assistant (Phase 2)
- Advisory ML boosters / top-N hypothesis ranking from learned patterns (Phase 2)
- Labeling feedback loop capture workflow (Phase 2 — CaseFile schema supports it, but operator workflow deferred)
- Sink Health Evidence Track (Phase 3)
- Hybrid topology / Smartscape / edge facts (Phase 3)
- Local-dev Mode B (opt-in connection to dedicated DEV environment — useful but not blocking)

## Phase Acceptance Criteria

Consolidated pass/fail checklists per phase. Each item is traceable to PRD sections (Success Criteria, Measurable Outcomes, Functional Requirements, NFRs, Domain-Specific Requirements) and/or external DoD documents. A phase is complete when all items pass.

### Phase 0 — Validation Harness

- [ ] Three real-signal patterns proven against real Prometheus metrics: consumer lag buildup, throughput-constrained proxy, volume drop (FR2, FR58)
- [ ] Missing Prometheus series maps to `EvidenceStatus=UNKNOWN` — never treated as zero — and UNKNOWN propagates through peak, sustained, and confidence computations (FR5; NFR-T2)
- [ ] Redis TTL behavior validated: evidence cache and dedupe keys honor environment-specific TTLs per redis-ttl-policy-v1 (FR7)
- [ ] Peak profile confidence validated: peak/near-peak classification computed per (env, cluster_id, topic) against historical baselines (FR3)
- [ ] Outbox state-machine transitions validated locally: PENDING_OBJECT → READY → SENT, plus RETRY and DEAD paths (FR23)
- [ ] Ownership mapping validated against topology registry: multi-level lookup returns correct owning team for test cases (FR13)
- [ ] `DegradedModeEvent` emitted when Redis is unavailable, containing affected scope, reason, capped action level, and estimated impact window (FR51; NFR-T4)
- [ ] `TelemetryDegradedEvent` emitted when Prometheus is totally unavailable; pipeline does NOT emit normal cases with all-UNKNOWN evidence; actions capped to OBSERVE/NOTIFY (FR67; NFR-R2)
- [ ] Harness stream naming is separate from prod naming — no collision with production stream identifiers
- [ ] Exposure safety violations = 0 across all harness outputs

### Phase 1A — MVP Triage Pipeline

- [ ] Full hot-path executes end-to-end: Evidence Builder → Peak Profile → Topology+Ownership → CaseFile triage write → Outbox publish → Rulebook gating (AG0–AG6) → Action Executor (FR17–FR35, FR66; NFR-T5)
- [ ] Invariant A holds: CaseFile `triage.json` written to object storage BEFORE Kafka header publish, verified by automated test (FR18; NFR-T2)
- [ ] Invariant B2 holds: Postgres durable outbox guarantees publish-after-crash, verified by crash-simulation test (FR22–FR23; NFR-T2)
- [ ] Hot-path contract enforced: Kafka forwards only CaseHeaderEvent.v1 + TriageExcerpt.v1 — no object-store reads in routing/paging path (FR24)
- [ ] Exposure denylist enforced on TriageExcerpt, Slack, and all notification outputs; zero violations (FR25, FR65; NFR-S5)
- [ ] Storm control operational: dedupe suppresses repeat PAGE/TICKET/NOTIFY within TTLs (120m/240m/60m); Redis unavailable → NOTIFY-only with `DegradedModeEvent` (FR33–FR34, FR51; NFR-T4)
- [ ] LLM diagnosis runs on cold path, non-blocking; hot path completes without LLM; LLM unavailability produces schema-valid DiagnosisReport fallback (FR36–FR41, FR66; NFR-T3)
- [ ] Outbox delivery SLO baselined: p95 ≤ 1 min, p99 ≤ 5 min; DEAD=0 prod posture validated (FR52–FR54; NFR-P1b)
- [ ] SOFT postmortem enforcement: `PM_PEAK_SUSTAINED` predicate triggers Slack/log notification (FR35, FR44)
- [ ] Local-dev Mode A runs full pipeline via docker-compose with zero external integration calls (FR55; NFR-T5)

### Phase 1B — ServiceNow Integration

- [ ] Tiered SN Incident correlation functional: Tier 1 (PD field) → Tier 2 (keyword) → Tier 3 (time-window + routing heuristic) (FR46)
- [ ] Idempotent Problem + PIR task upsert via `external_id` keying — no duplicates on retry (FR47)
- [ ] 2-hour retry window with exponential backoff + jitter; FAILED_FINAL → Slack escalation (exposure-safe) (FR48)
- [ ] SN linkage state machine persisted: PENDING → SEARCHING → LINKED or SEARCHING → FAILED_TEMP → SEARCHING or SEARCHING → FAILED_FINAL (FR49)
- [ ] Tier 1 vs Tier 2/3 fallback rates tracked as Prometheus metrics (FR50)
- [ ] SN linkage rate: ≥ 90% of PAGE cases LINKED within 2-hour retry window
- [ ] Least-privilege SN integration user enforced: READ on incident, CRUD on problem/task only (NFR-S6)
- [ ] MI-1 posture holds: system does NOT create Major Incident objects — verified by automated test (FR67)
- [ ] Outbox SLO and DEAD=0 posture maintained under SN linkage load
- [ ] Exposure denylist enforced on SN Problem/PIR descriptions and FAILED_FINAL Slack escalation; zero violations (NFR-S5)

### Phase 2 — Better Evidence + Triage Quality

> Full DoD: `phase-2-dod-v1.md`. Key PRD exit criteria below.

- [ ] Expanded evidence sources mapped to Evidence primitives with explicit provenance, confidence, and UNKNOWN handling
- [ ] UNKNOWN evidence rate reduced ≥ 50% vs Phase 1 baseline for top 3 anomaly families, measured 4 consecutive weeks
- [ ] Routing accuracy: misroute rate < 5%; correct-team routing ≥ 95% for top critical streams, measured via owner-confirmed labels
- [ ] Triage usefulness rating ≥ 80% "useful" from sampled responder feedback, sustained 4 consecutive weeks
- [ ] Labeling loop operational: label completion ≥ 70% for eligible cases; consistency checks pass before ML consumption (FR63–FR64)
- [ ] Rulebook guardrails remain authoritative: ML/advisory boosters never directly trigger actions in PROD/TIER_0
- [ ] Outbox SLO and DEAD=0 posture maintained under expanded evidence load
- [ ] Phase 2 features run locally with integrations in LOG/OFF modes
- [ ] Phase 3 backlog is evidence-driven from labels + UNKNOWN reasons

### Phase 3 — Hybrid Topology + Sink Health

> Full DoD: `phase-3-dod-v1.md`. Key PRD exit criteria below.

- [ ] Hybrid topology operational: YAML (governed) + Smartscape (observed) + edge facts, instance-scoped by (env, cluster_id)
- [ ] YAML governance never overridden by observed topology
- [ ] Sink Health Evidence Track operational with 6 standardized primitives (SINK_CONNECTIVITY, SINK_ERROR_RATE, SINK_LATENCY, SINK_BACKLOG, SINK_THROTTLE, SINK_AUTH_FAILURE)
- [ ] Topology edge coverage ≥ 70% for top N critical streams, measured 8 consecutive weeks
- [ ] Sink evidence AVAILABLE rate ≥ 60% for streams with defined sinks
- [ ] "Wrong layer" misdiagnosis reduced ≥ 30% vs Phase 1 baseline, measured via labels
- [ ] Diagnosis attribution distinguishes Kafka symptoms vs downstream sink symptoms with evidence references
- [ ] Exposure safety: zero incidents of sensitive sink identifiers in outputs
- [ ] Phase 3 components default to OFF/LOG locally; mock inputs supported via local files
- [ ] All success metrics sustained 8 consecutive weeks; runbooks exist for hybrid topology signal interpretation

## Phase Dependencies

```
Phase 0 ──→ Phase 1A ──→ Phase 1B ──→ Phase 2 ──→ Phase 3
  │              │             │            │            │
  │              │             │            │            └─ Hybrid topology + sink health
  │              │             │            └─ Advisory ML + labeling + expanded evidence
  │              │             └─ SN linkage (requires Phase 1A PAGE working)
  │              └─ MVP pipeline + LLM diagnosis (requires Phase 0 signal validation)
  └─ Local harness (proves signals are real)
```

**Cross-phase data dependencies:**
- Phase 1A → Phase 1B: PAGE cases + pd_incident_id needed for SN linkage
- Phase 1A/1B → Phase 2: CaseFiles + DiagnosisReports + postmortem records needed for labeling loop
- Phase 2 labeling → Phase 2 ML: Label completion ≥ 70% + consistency validation needed before ML consumption
- Phase 2 evidence expansion → Phase 3: UNKNOWN reduction informs where topology/sink gaps matter most

## Risk Mitigation Strategy

**Technical Risks:**

| Risk | Severity | Mitigation | Cut-line Impact |
|---|---|---|---|
| Prometheus metric availability/quality in prod | High | Phase 0 validates real signals; canonical metric contract locks names/aliases | Blocks Phase 1A if signals don't exist |
| Outbox complexity (state machine + alerting) | Medium | Phase 0 validates locally; outbox-policy-v1 locks SLO/thresholds | Must be solid for Phase 1A — no shortcuts |
| Registry migration (v0→v1 legacy consumers) | Medium | Loader rules locked; compat views + deprecation plan | Phase 1A supports both; remove v0 in Phase 2+ |
| LLM integration (mandatory cold-path) | Medium | Non-blocking; fallback emits DiagnosisReport with verdict=UNKNOWN, confidence=LOW, reason_codes=[LLM_TIMEOUT/UNAVAILABLE/ERROR]; hot path unaffected; LLM stub/failure-injection mode for local/test | Cannot cut — but cannot block hot path either |
| Redis failure during active incidents | Medium | AG5 degraded mode + DegradedModeEvent; validated in Phase 0 | Safety-critical — must work from Phase 1A |

**Operational Risks:**

| Risk | Severity | Mitigation |
|---|---|---|
| PD→SN integration doesn't populate correlation field | High | Tiered correlation fallback (Tier 2/3); track fallback rates; escalate to integration team |
| Responders don't trust AIOps routing | Medium | Reroute/labeling loop; routing accuracy metric; Phase 2 improvements driven by feedback |
| Outbox DEAD accumulation | High | DEAD=0 prod posture; >0 = critical alert; 90-day retention for forensics |
| Policy drift without governance | Medium | Versioned artifacts; approval gates; CaseFile stamps policy versions |

**Resource Risks:**
- **Minimum viable team:** 1-2 engineers can deliver Phase 0 + Phase 1A given frozen contracts (most design decisions are made). Phase 1B SN integration may require SN admin access coordination.
- **If resources constrained:** Phase 0 + Phase 1A (including cold-path LLM) is the minimum. SN linkage (Phase 1B) and labeling (Phase 2) can be deferred without breaking core safety guarantees. LLM cannot be cut but its fallback mode means it doesn't block delivery.
- **If timeline constrained:** Phase 0 can be compressed if Prometheus signals are already known to exist in the target environment. Phase 1B can follow Phase 1A with a gap if SN access is not yet available.
