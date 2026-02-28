# Domain-Specific Requirements

## Compliance & Regulatory

- **Audit trail completeness:** Every action decision must be deterministically traceable from evidence → diagnosis → Rulebook gate outputs → final action. CaseFile is the system-of-record (25-month prod retention). This satisfies internal audit and regulatory examination requirements for operational systems in a bank.
- **No automated Major Incident creation (MI-1):** The system does not create MI objects — this is a human decision boundary. AIOps supports postmortem automation (Problem + PIR tasks) but does not escalate into the bank's MI process autonomously.
- **Postmortem selectivity:** Postmortem obligations are predicate-driven (`PM_PEAK_SUSTAINED` via AG6), not blanket. This prevents audit noise from non-critical cases while ensuring every high-impact case is tracked.
- **Data retention:** CaseFile retention (25 months prod) aligns with banking regulatory examination windows. Outbox SENT/DEAD retention policies are defined per environment.
- **Cross-border data handling:** Not applicable for current scope. This platform processes operational telemetry (Kafka metrics, infrastructure health signals) from the bank's internal Kafka infrastructure. CaseFiles contain no customer PII, no transaction data, and no cross-border personal data — all data subjects are internal systems, not natural persons. If the deployment topology spans geographic regions (e.g., multi-region DR), data residency requirements for CaseFile storage should be evaluated during deployment planning as an infrastructure concern.

## Evidence Integrity & Immutability

- **Write-once / append-only CaseFiles:** CaseFile objects in storage must be write-once or append-only with versioning. Once evidence and decisions are recorded, they cannot be silently mutated. Any amendments (e.g., postmortem annotations, SN linkage updates) must be appended as new versions, preserving the original decision record.
- **Hash / checksum for audit integrity:** Each CaseFile version must include a content hash (e.g., SHA-256) recorded at write time. Auditors must be able to verify that the CaseFile retrieved matches the hash recorded at decision time — tamper-evidence for regulatory examination.
- **Policy version stamping:** Every CaseFile must record the exact versions of policies used to make its decisions: `rulebook_version`, `peak_policy_version`, `prometheus_metrics_contract_version`, `exposure_denylist_version`, `diagnosis_policy_version` (if applicable). This ensures reproducibility: given the same evidence + the same policy versions, the same gating decision must result.

## Data Minimization & Privacy

- **No PII/secrets in CaseFiles:** CaseFiles must not contain personally identifiable information, credentials, API keys, or secrets. Evidence fields must be limited to operational telemetry identifiers (cluster_id, topic, group, stream_id, metric values) — not user data payloads.
- **Sensitive field redaction:** Any field that could transitively reference sensitive data (e.g., sink endpoints with embedded credentials, Ranger group names that reveal org structure) must be redacted or excluded from CaseFile content. The exposure denylist applies to CaseFile content, not just excerpts.
- **Store only necessary evidence:** CaseFiles store evidence summaries (metric values, findings, status maps), not raw telemetry dumps. The principle is: enough to reproduce the decision, not enough to reconstruct the data pipeline's content.
- **Purge/retention governance:** Retention periods (25 months prod CaseFile, 14 days SENT outbox, 90 days DEAD outbox) must be enforced by automated lifecycle policies. Purge operations must be auditable (logged with timestamp, scope, policy reference). No manual ad-hoc deletion without governance approval.
- **Data classification alignment:** CaseFile content, TriageExcerpt, and all pipeline outputs contain operational telemetry identifiers (no PII, no secrets) and are expected to fall within the bank's Internal/Operational classification tier. The exposure denylist and data minimization controls must be validated against the bank's formal data classification taxonomy during deployment readiness review — the bank's Information Security team owns the taxonomy.

## Policy Governance & Change Management

- **Controlled policy changes:** Rulebook, exposure denylist, postmortem predicates (`PM_PEAK_SUSTAINED`), and Prometheus metrics contract must follow controlled change management: versioned artifacts, approval gates, and audit trail of who changed what and when.
- **Policy versioning:** All policy artifacts must carry explicit version identifiers (e.g., `rulebook.v1`, `gateinput.v1`). Version bumps require review. CaseFiles record which policy versions were active at decision time (see Evidence Integrity above).
- **Diagnosis policy separation:** Diagnosis policy (currently draft, not frozen) can evolve independently of Rulebook guardrails. This is by design — but changes must still be versioned and traceable. The Rulebook remains authoritative regardless of diagnosis policy changes.
- **Denylist governance:** The exposure denylist (controlling what appears in TriageExcerpt/Slack/SN outputs) must be a versioned, reviewable artifact — not hardcoded logic. Changes to the denylist are security-sensitive and require explicit approval.

## LLM Role & Boundaries

- **Bounded role:** The LLM is a "diagnosis synthesis + hypothesis ranking + explanation" component. It produces structured DiagnosisReport output (verdict, fault domain, confidence, evidence pack, next checks). It is NOT the action authority — deterministic Rulebook gates (AG0–AG6) are final.
- **Provenance-aware outputs:** LLM outputs must cite evidence IDs/references from the structured evidence pack. LLM must explicitly propagate UNKNOWN when evidence is missing — never invent metric values, never fabricate findings, never assert PRESENT when the evidence_status_map says UNKNOWN/ABSENT/STALE.
- **Exposure-capped inputs:** LLM primarily consumes the executive-safe TriageExcerpt + structured evidence summaries (GateInput-shaped). Sensitive sink identifiers/endpoints remain excluded from LLM context. CaseFile richer detail is available for evidence references but the exposure denylist still applies to any LLM-generated narrative that surfaces in outputs.
- **Non-blocking degradation:** If LLM is unavailable or times out, the pipeline must still produce a valid CaseFile + header/excerpt using deterministic findings and UNKNOWN semantics. DiagnosisReport falls back to `verdict: NEEDS_MORE_EVIDENCE` with a gap recorded. Actions remain safely gated — typically capped to OBSERVE/NOTIFY by AG4 (low confidence) when LLM is absent.
- **Cost controls:** LLM invocation is conditional — triggered only when case meets criteria (e.g., PROD+TIER_0, or sustained anomaly, or confidence above threshold). Token usage is bounded: input is excerpt + structured evidence summary, not full raw Prometheus series or log dumps. Phase 2 advisory ML (top-N hypothesis ranking) is similarly bounded.
- **Schema safety:** LLM output must be validated against DiagnosisReport schema. Invalid/unparseable LLM output → deterministic fallback (NEEDS_MORE_EVIDENCE + gap), never a crash or silent malformation. The system is resilient to bad model outputs.

## Technical Constraints

- **Exposure controls (executive-safe posture):** All outputs visible to humans outside the platform team (TriageExcerpt, Slack notifications, SN Problem descriptions) must enforce the versioned denylist: no sensitive sink endpoints/identifiers, no credentials, no restricted internal hostnames, no Ranger access group names. CaseFile stores richer detail but is access-controlled.
- **Least-privilege integrations:** SN integration user has READ on incident, CRUD on problem/task — no broad admin roles. All API calls logged with request_id, case_id, sys_ids touched, outcome, latency.
- **No accidental prod calls:** Local-dev LIVE mode is restricted to approved non-prod endpoints. Config must prevent accidental connection to production integrations. Default integration mode is LOG (safe, visible).
- **Deterministic safety gates:** Rulebook guardrails (AG0–AG6) are deterministic policy, not probabilistic. ML (Phase 2+) is advisory only and never directly triggers actions in PROD/TIER_0. This is a regulatory posture: automated decisions that can page humans at 3 AM must be explainable and auditable.

## Integration Requirements

- **Prometheus:** Sole source of truth for telemetry. Label normalization (`cluster_id := cluster_name` exact string). Canonical metric names locked in prometheus-metrics-contract-v1. Missing series → UNKNOWN.
- **Object storage:** CaseFile system-of-record. Write-once/append-only with hash verification. Invariant A (write before publish) is non-negotiable. MinIO locally, production object store in higher environments.
- **Postgres:** Durable outbox (Invariant B2). State machine: PENDING_OBJECT → READY → SENT (+ RETRY, DEAD). SLO and alert thresholds defined in outbox-policy-v1.
- **Redis:** Cache-only (evidence windows, peak profiles, dedupe keys). NOT system-of-record. Degraded mode must be safe (NOTIFY-only). TTLs defined per environment in redis-ttl-policy-v1.
- **Kafka:** Hot-path transport for `CaseHeaderEvent.v1` + `TriageExcerpt.v1`. No object-store reads in hot path. Consumers route/page based on header/excerpt only.
- **PagerDuty:** External — creates SN Incidents. AIOps sends PAGE triggers with stable `pd_incident_id` for correlation. AIOps does NOT create Incidents.
- **ServiceNow (Phase 1B):** Tiered correlation to find PD-created Incident → idempotent Problem + PIR task upsert. 2-hour retry window. FAILED_FINAL escalation via Slack.
- **Slack:** Notification sink for SOFT postmortem enforcement (Phase 1A), degraded-mode events, and SN linkage escalations. Exposure denylist enforced. Falls back to structured log events when not configured.

## Risk Mitigations

| Risk | Mitigation | Contract Reference |
|---|---|---|
| Paging storm during infrastructure degradation | Redis down → NOTIFY-only (AG5); `DegradedModeEvent` emitted | rulebook-v1.yaml, redis-ttl-policy-v1.md |
| Wrong-team routing causing alert fatigue | Multi-level ownership lookup (group → topic → stream → platform default); reroute/labeling feedback loop | topology-registry-loader-rules-v1.md |
| Sensitive data leaking in notifications | Versioned exposure denylist enforced on TriageExcerpt + Slack; CaseFile access-controlled | BMAD-READY-INPUT §4.5 |
| CaseFile loss before publish | Invariant A (write to object storage before Kafka publish); outbox ensures publish-after-crash | outbox-policy-v1.md |
| CaseFile tampering post-decision | Write-once/append-only with SHA-256 hash; policy version stamping | (new requirement) |
| PII/secrets in operational artifacts | Data minimization policy; sensitive field redaction; exposure denylist on CaseFile content | (new requirement) |
| Uncontrolled policy drift | Versioned policy artifacts; approval gates; CaseFile records active policy versions | (new requirement) |
| Duplicate SN Problems/tasks on retry | Idempotent upsert via external_id keying | servicenow-linkage-contract-v1.md |
| Accidental prod integration calls from local dev | LIVE mode requires explicit endpoint+cred config; restricted to approved non-prod endpoints | local-dev-no-external-integrations-contract-v1.md |
| ML overriding safety gates | ML is advisory only (Phase 2+); Rulebook guardrails remain authoritative; ML never triggers actions in PROD/TIER_0 | rulebook-v1.yaml, phase-2-dod-v1.md |
| Missing telemetry treated as "OK" | Individual missing series → `EvidenceStatus=UNKNOWN` (never zero); total Prometheus unavailability → `TelemetryDegradedEvent` + cap to OBSERVE/NOTIFY (no all-UNKNOWN cases) | prometheus-metrics-contract-v1.yaml, peak-policy-v1.md |
| LLM hallucinates evidence or metric values | Provenance requirement: must cite evidence IDs; schema validation rejects fabricated fields; UNKNOWN propagation enforced | (new requirement) |
| LLM unavailability blocks triage pipeline | Non-blocking: deterministic fallback to NEEDS_MORE_EVIDENCE + gap; actions safely capped to OBSERVE/NOTIFY | (new requirement) |
| LLM cost scales with case volume | Conditional invocation (PROD+TIER_0 or sustained only); bounded token input (excerpt, not raw logs) | (new requirement) |
| LLM consumes sensitive data | Exposure-capped inputs: LLM receives TriageExcerpt + structured evidence, not raw CaseFile with sink details | (new requirement) |
