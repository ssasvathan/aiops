# Success Criteria

## User Success

**Kafka Platform Ops (primary responders):**
- Cases arrive with correct owning team pre-routed — responder does not manually triage ownership
- CaseFile provides enough context to START investigation and measurably reduces Prometheus re-queries and time-to-first-action
- False-positive PAGE rate is measurably low — responders trust that a page means "real, sustained, high-confidence, PROD TIER_0"
- Responders can trace any action decision back to specific gate IDs + reason codes (AG0–AG6) without reading code
- When degraded mode engages (Redis unavailable), responders receive an explicit `DegradedModeEvent` in logs/Slack explaining why PAGE/TICKET is capped — no silent behavioral changes

**Data Stewards (secondary):**
- Notified only for anomalies in their stewardship domain (SOURCE_TOPIC routing) — not paged for platform issues
- CaseFile references relevant topology (stream, topic role, source system) without requiring steward to know pipeline internals

**Incident Responders / Auditors:**
- Any case can be reproduced from object storage (CaseFile is system-of-record, 25-month prod retention)
- Postmortem obligations are traceable: `PM_PEAK_SUSTAINED` predicate (AG6) fires selectively, not blanket
- No sensitive sink endpoints/credentials appear in TriageExcerpt or Slack outputs (exposure denylist enforced)

## Business Success

- **Incident response quality:** Correct-team routing rate ≥ 95% for top critical streams (measured via owner-confirmed labels or manual sampling in Phase 2+)
- **Noise reduction:** No paging storms — repeat PAGE for same fingerprint within dedupe TTL is near-zero; repeat TICKET/NOTIFY within respective dedupe TTLs also near-zero; degraded Redis → NOTIFY-only with explicit `DegradedModeEvent` (no silent caps)
- **Audit readiness:** Every action decision is deterministically explainable via Rulebook gate IDs + reason codes; CaseFile provenance chain is complete
- **MI-1 posture:** System does NOT create Major Incident objects — this is a human decision boundary
- **Outbox reliability (prod):** DEAD=0 as standing posture; any DEAD row is critical alert
- **SN linkage (Phase 1B):** ≥ 90% of PAGE cases LINKED to PD-created SN Incident within 2-hour retry window; Tier 1 vs Tier 2/3 correlation fallback rates tracked — Tier 2/3 usage should trend down over time as PD→SN integration matures

## Technical Success

**Invariants (must hold at all times):**
- Invariant A: CaseFile written to object storage BEFORE Kafka header publish
- Invariant B2: Postgres durable outbox guarantees publish-after-crash
- Hot-path contract: Kafka forwards only `CaseHeaderEvent.v1` + `TriageExcerpt.v1` — no object-store reads in routing/paging path
- Missing Prometheus series → `EvidenceStatus=UNKNOWN` (never treated as zero)
- PAGE structurally impossible outside PROD+TIER_0 (AG1 env+tier caps)
- Exposure denylist enforced on all excerpt/notification outputs

**Outbox SLO (prod):**
- p95 CaseFile-write → Kafka-publish ≤ 1 minute
- p99 ≤ 5 minutes
- Critical breach: p99 > 10 minutes
- Alert thresholds: PENDING_OBJECT >5m warn / >15m crit; READY >2m warn / >10m crit; RETRY >30m crit; DEAD >0 crit (prod)

**Storm control + degraded-mode transparency:**
- Dedupe suppresses repeat PAGE/TICKET/NOTIFY within respective TTLs (PAGE 120m, TICKET 240m, NOTIFY 60m) — near-zero repeats
- Redis unavailable → deny PAGE/TICKET, allow NOTIFY only (AG5 `DEGRADE_AND_ALLOW_NOTIFY`)
- Degraded-mode engagement MUST emit explicit `DegradedModeEvent` to logs and Slack (if configured) with: affected scope, reason, capped action level, and estimated impact window

**Local-dev independence (dual-mode):**
- **Mode A (default): Local containers.** docker-compose with Kafka + Postgres + Redis + MinIO + Prometheus. No external integration calls. Full pipeline runs end-to-end locally.
- **Mode B (opt-in): Dedicated remote environment.** When endpoints and credentials are explicitly configured, integrations may connect to a dedicated remote environment's infrastructure (e.g., DEV). LIVE mode is allowed only when explicitly configured and restricted to approved non-prod endpoints — no accidental prod calls.
- All integrations support `OFF | LOG | MOCK | LIVE` modes. Default is `LOG` (safe, visible). LIVE requires explicit endpoint+credential configuration.
- CaseFile durability invariants testable in both modes (MinIO locally or real object store in dedicated environments).

## Measurable Outcomes

| Metric | Phase 0 | Phase 1A | Phase 1B | Phase 2 | Phase 3 |
|--------|---------|----------|----------|---------|---------|
| Real-signal patterns proven | 3 (lag, constrained proxy, volume drop) | — | — | — | — |
| Outbox DEAD=0 (prod) | local validated | maintained | maintained | maintained | maintained |
| Outbox SLO p95 ≤ 1 min | local validated | measured | measured | measured | measured |
| Correct-team routing | local validated | baseline established | baseline | ≥ 95% | improved |
| SN linkage rate (PAGE cases) | — | — | ≥ 90% within 2h | maintained | maintained |
| SN Tier 2/3 fallback rate | — | — | baseline tracked | trending down | trending down |
| Dedupe effectiveness (repeat PAGE/TICKET/NOTIFY) | — | near-zero | near-zero | near-zero | near-zero |
| DegradedModeEvent emitted on Redis failure | — | validated | validated | validated | validated |
| TelemetryDegradedEvent emitted on Prometheus failure | local validated | validated | validated | validated | validated |
| UNKNOWN evidence rate (top 3 families) | — | baseline | — | ≥ 50% reduction | further reduction |
| Triage usefulness rating | — | — | — | ≥ 80% "useful" | maintained |
| Label completion rate (eligible cases) | — | — | — | ≥ 70% | maintained |
| Label consistency (owner_confirmed, resolution_category) | — | — | — | validation passing | maintained |
| Topology edge coverage (top N streams) | — | — | — | — | ≥ 70% |
| Sink evidence AVAILABLE rate | — | — | — | — | ≥ 60% |
| Exposure safety violations | 0 | 0 | 0 | 0 | 0 |
