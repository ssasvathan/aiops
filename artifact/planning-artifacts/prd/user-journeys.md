# User Journeys

## Journey 1: Kafka Platform Ops Engineer — Sustained Lag During Peak (PAGE Path)

**Persona:** Priya, Kafka Platform Ops on-call engineer. 3 AM, phone buzzes.

**Opening Scene:** Priya's pager fires. The page summary shows: `CaseHeaderEvent.v1` — sustained consumer lag on `e2-p-sourcestream` (KAFKA_SOURCE_STREAM role), Business_Essential cluster, TIER_0, peak window active. The TriageExcerpt (executive-safe, no sensitive endpoints) gives her: stream_id, anomaly family, confidence score, sustained=true, matched gates (AG1 passed, AG4 passed), final action=PAGE, `PM_PEAK_SUSTAINED` postmortem required.

**Rising Action:** Priya opens the full CaseFile from object storage. She sees: Evidence Builder findings with specific Prometheus metric values (messages-in rate vs p95 baseline), peak profile confirmation, topology context (stream → instances → topic_index → downstream components AT_RISK), ownership routing chain (how it reached her team), and all gate reason codes. She doesn't need to manually correlate Prometheus dashboards — the CaseFile has the evidence window, the baseline comparison, and the sustained-interval history. Time-to-first-action is minutes, not the usual 20+ minutes of manual Prometheus spelunking.

**Climax:** Priya identifies the issue as a downstream processing bottleneck causing backpressure on the shared source-stream. Sink visibility is UNKNOWN in Phase 1A — she cannot yet attribute to a specific downstream component (e.g., NiFi, HDFS landing) without Phase 3 Sink Health Evidence. She escalates using the blast_radius (downstream components marked AT_RISK) and topology_exposure from the CaseFile. The postmortem obligation (`PM_PEAK_SUSTAINED`) is tracked — Phase 1A logs the obligation to Slack; Phase 1B will auto-create a Problem + PIR tasks in ServiceNow linked to the PD-created Incident.

**Resolution:** Incident resolved. The CaseFile is the permanent record. Auditors can trace: evidence → diagnosis → gate decisions → action → postmortem obligation. No ambiguity about why she was paged or what the system decided.

**Capabilities revealed:** CaseFile assembly, peak profile, ownership routing, Rulebook gating (AG1/AG4), exposure-safe excerpt, `PM_PEAK_SUSTAINED` postmortem tracking, object-storage durability.

---

## Journey 2: Service Owner / Application Team On-call — Consumer Lag Routed to App Team

**Persona:** Marcus, payments application team on-call. His team owns consumer groups reading from `payment-p-events`.

**Opening Scene:** Marcus receives a TICKET (not a PAGE — his consumer group is TIER_1, capped by AG1). The TriageExcerpt tells him: sustained consumer lag on his consumer group against `payment-p-events` (SOURCE_TOPIC role), Business_Critical cluster. Anomaly family: CONSUMER_LAG. The excerpt includes the routing chain showing why it reached his team (consumer_group_owner match in topology registry).

**Rising Action:** Marcus opens the CaseFile. He sees: lag metric values over the 5-minute sustained window, the specific consumer group identity `(env, cluster_id, group, topic)`, peak context (not peak — so `PM_PEAK_SUSTAINED` did NOT fire), and the topology view showing his app's position in the pipeline. The findings declare their evidence requirements (`finding.evidence_required[]`), and AG2 confirms evidence is sufficient — any missing series remains UNKNOWN and is reflected in confidence (never treated as zero, never assumed PRESENT). He also sees: topic_role=SOURCE_TOPIC, so AG3 would have denied PAGE even if tier allowed it — the system prevented a 3 AM page for a source-topic anomaly.

**Climax:** Marcus identifies his consumer is falling behind due to a recent deployment that increased per-record processing time. The CaseFile's evidence pack and topology context gave him the starting point without manually correlating Prometheus dashboards across clusters.

**Resolution:** Marcus rolls back the deployment. The dedupe window (TICKET: 240 minutes) prevents a storm of duplicate tickets while he works. The CaseFile is retained for his team's postmortem review.

**Alternative path — misroute:** Marcus reviews the CaseFile and determines the lag is not caused by his application — it's a platform-side issue. He labels the case: `owner_confirmed: false`, `resolution_category: misrouted`, and reroutes to the platform ops team. This feeds the routing accuracy metric (target: ≥ 95% correct-team routing) and the labeling loop. Over time, misroute patterns drive topology registry corrections.

**Capabilities revealed:** Consumer-group ownership routing, TIER_1 action capping (AG1), SOURCE_TOPIC PAGE denial (AG3), evidence sufficiency with UNKNOWN-aware confidence (AG2), dedupe storm control (AG5), instance-scoped topology lookup, reroute/labeling feedback for routing accuracy.

---

## Journey 3: Data Steward — Volume Drop on Source Topic

**Persona:** Anika, payments data steward. Responsible for data quality from the Payments source system.

**Opening Scene:** Anika receives a NOTIFY (not TICKET — confidence is moderate, sustained but below threshold for higher urgency per AG4). The notification tells her: volume drop detected on `payment-p-events` (SOURCE_TOPIC), Business_Essential cluster. The TriageExcerpt is clean — no sink endpoints, no internal hostnames, just the anomaly summary and her team's routing key.

**Rising Action:** Anika checks the CaseFile. She sees the messages-in rate has dropped significantly against the p90 baseline, the source_system is identified as "Payments," and the blast radius is LOCAL_SOURCE_INGESTION (not shared pipeline). She doesn't need to understand the shared pipeline topology — the CaseFile scopes the issue to her domain. The gap list notes no client-level telemetry available yet (Phase 2 will add this).

**Climax:** Anika contacts the upstream Payments application team. The volume drop correlates with a scheduled maintenance window they forgot to communicate. She confirms it's expected.

**Resolution:** The case resolves as a false positive from the steward's perspective. In Phase 2, Anika's feedback (label: `false_positive`, `missing_evidence_reason: scheduled_maintenance_not_communicated`) feeds the labeling loop, improving future diagnosis quality.

**Capabilities revealed:** Data steward routing (topic_owner match), SOURCE_TOPIC scoping, blast radius classification, exposure-safe notifications, gap reporting, Phase 2 labeling feedback.

---

## Journey 4: Incident Manager / Auditor — Postmortem Compliance Review

**Persona:** David, incident management lead. Quarterly audit of postmortem compliance.

**Opening Scene:** David queries CaseFiles from object storage for the past quarter. He filters for cases where `PM_PEAK_SUSTAINED` fired (AG6: peak && sustained && TIER_0 in PROD). He needs to verify: did every obligated case get a postmortem?

**Rising Action:** For each flagged case, David traces the decision chain: Evidence Builder findings → peak profile confirmation → Rulebook gate outputs (AG6 `on_pass: set_postmortem_required: true`, reason code `PM_PEAK_SUSTAINED`) → action decision → postmortem enforcement record. In Phase 1A, he checks Slack logs for SOFT enforcement notifications. In Phase 1B, he checks ServiceNow for linked Problem + PIR tasks.

**Climax:** David finds one case where SN linkage was `FAILED_FINAL` (2-hour retry window exhausted). The CaseFile records the `sn_linkage_status`, `sn_linkage_reason_codes`, and the Slack escalation that was sent. He can see exactly what happened: Tier 1 correlation failed (PD field not populated), Tier 2 keyword search found no match, Tier 3 heuristic timed out. The system failed safe — no duplicate Problems were created, and humans were notified.

**Resolution:** David flags the linkage gap for process improvement (PD→SN integration needs the correlation field populated). The audit trail is complete — every decision is deterministic and traceable. He confirms: the system never created a Major Incident object (MI-1 posture held).

**Capabilities revealed:** CaseFile as audit record, `PM_PEAK_SUSTAINED` traceability, SN linkage state machine (PENDING → SEARCHING → FAILED_FINAL), idempotency guarantees, MI-1 posture, 25-month retention.

---

## Journey 5: AIOps Platform Developer — Local Development & Diagnosis Evolution

**Persona:** Chen, platform engineer building the AIOps system.

**Opening Scene:** Chen is developing a new diagnosis rule for a throughput-constrained proxy pattern. He needs to run the full pipeline locally without any external integrations.

**Rising Action (Mode A — Local Containers):** Chen runs `docker-compose up` — Kafka, Postgres, Redis, MinIO, Prometheus all start locally. All integrations default to `LOG` mode. He configures the harness to generate traffic patterns that produce the constrained-proxy signal (lag + near-peak ingress + not a volume drop). Harness stream naming is separate from prod naming. He watches: Evidence Builder collects from local Prometheus → peak profile computes against local baseline → CaseFile writes to MinIO → outbox transitions through PENDING_OBJECT → READY → SENT → Kafka header published to local broker. Slack/SN actions appear as structured `NotificationEvent` JSON in logs. He validates the full invariant chain locally.

**Rising Action (Mode B — Dedicated DEV):** Later, Chen needs to test against realistic data volumes. He configures integration endpoints to point at the dedicated DEV environment's Kafka and Prometheus. LIVE mode is explicitly enabled with approved DEV endpoints — the config prevents accidental prod calls. He runs the same pipeline against real DEV telemetry.

**Climax:** Chen's new diagnosis rule correctly identifies the constrained-proxy pattern. He validates the rule produces the expected GateInput fields, passes AG0 (schema valid), and AG2 (evidence requirements declared in `finding.evidence_required[]` are all PRESENT). The rule is ready for review.

**Resolution:** Chen submits the diagnosis policy change. The frozen contracts (Rulebook, GateInput, Peak, Prometheus metrics) didn't need to change — diagnosis evolved independently. Local-dev independence means no shared environment was blocked during development.

**Capabilities revealed:** Mode A/B local dev, LOG-mode integration fallbacks, harness traffic generation, diagnosis policy evolution independent of frozen contracts, outbox state-machine validation, MinIO as local object store.

---

## Journey 6: Ops Lead / SRE Manager — System Health & Degraded Mode

**Persona:** Fatima, SRE manager overseeing the AIOps platform in production.

**Opening Scene:** Fatima's monitoring dashboard shows a Redis connectivity issue in the prod cluster. She needs to understand the impact on AIOps behavior.

**Rising Action:** The AIOps system detects Redis unavailability and immediately emits a `DegradedModeEvent` to logs and Slack (her platform ops channel). The event contains: affected scope (evidence cache + dedupe store), reason (Redis connection timeout), capped action level (NOTIFY-only — PAGE and TICKET denied per AG5 `DEGRADE_AND_ALLOW_NOTIFY`), and estimated impact window. Cases continue to process — evidence is still collected from Prometheus, CaseFiles still written to object storage, outbox still publishes — but no pages or tickets fire. Responders see the `DegradedModeEvent` and understand why.

**Climax:** Fatima also monitors the outbox dashboard. She checks: DEAD count = 0 (holding), READY oldest age < 2 min (healthy), PENDING_OBJECT backlog normal. The outbox is unaffected by the Redis issue (Postgres is fine). She confirms the system is degrading safely — no paging storms, no silent failures.

**Resolution:** Redis recovers. Dedupe state is rebuilt (cache-only, recomputable). Fatima reviews the degraded-mode window: no false pages were sent, NOTIFY-only behavior held throughout. She logs the incident duration for capacity planning.

**Sub-scenario — Prometheus Unavailability:**

**Opening Scene:** A week later, Fatima sees a different degradation: Prometheus scrape failures across the prod cluster. The AIOps system detects total Prometheus unavailability (not individual missing series — those map to per-metric `EvidenceStatus=UNKNOWN` as normal) and emits a `TelemetryDegradedEvent` to logs and Slack. The event contains: affected scope (all evidence collection), reason (Prometheus connection timeout), and recovery status.

**Rising Action:** Unlike the Redis scenario, this affects evidence collection at the source. The pipeline does NOT emit normal cases with all-UNKNOWN evidence — it recognizes that total source unavailability is different from individual metric gaps. Actions are capped to OBSERVE/NOTIFY. No pages, no tickets. The outbox continues operating (Postgres is fine), but no new CaseFiles are produced because there is no evidence to collect.

**Climax:** Fatima confirms on the meta-monitoring dashboard: Prometheus connectivity shows scrape failure, `TelemetryDegradedEvent` is active, no new cases are being generated. She verifies the system is NOT generating noise — no all-UNKNOWN cases flooding the pipeline.

**Resolution:** Prometheus recovers. `TelemetryDegradedEvent` clears. Normal evaluation resumes on the next 5-minute interval. No backfill of missed intervals — the system acknowledges the gap rather than fabricating evidence. Fatima logs the outage window.

**Capabilities revealed:** `DegradedModeEvent` transparency, Redis degraded-mode behavior (AG5), `TelemetryDegradedEvent` transparency, Prometheus degraded-mode behavior (no all-UNKNOWN cases, action capping to OBSERVE/NOTIFY), outbox health monitoring (SLO, DEAD=0, age thresholds), safe degradation without paging storms, no-backfill recovery.

---

## Journey 7: Kafka Platform Ops — Sink Unreachable (Phase 3)

**Persona:** Priya again, on-call. This time the system has Phase 3 capabilities.

**Opening Scene:** Priya receives a TICKET. The TriageExcerpt shows: consumer lag sustained on the shared source-stream, but the CaseFile now includes Sink Health Evidence — a new evidence track unavailable in Phase 1A.

**Rising Action:** Priya opens the CaseFile. Unlike Phase 1A where downstream attribution was UNKNOWN, she now sees sink evidence primitives: `SINK_CONNECTIVITY: ABSENT` for the HDFS landing path, `SINK_ERROR_RATE: PRESENT (elevated)`, `SINK_LATENCY: PRESENT (normal)`. The coverage-weighted hybrid topology view (YAML governance + Smartscape observed + platform edge facts) shows the full path from Kafka consumer through NiFi to HDFS sink — with the edge fact confirming the consumer-to-sink relationship even though the application team hasn't instrumented.

**Climax:** The CaseFile's diagnosis attribution now distinguishes: "Kafka symptoms are secondary (lag is a consequence); primary evidence points to sink unreachability." The system presents this as "Kafka OK, downstream sink unreachable" with evidence references and explicit uncertainty markers. Priya routes directly to the storage/infrastructure team — no wasted triage cycle on the Kafka layer. The TriageExcerpt remains exposure-safe: it references the sink evidence status (`SINK_CONNECTIVITY: ABSENT`) but does NOT include the actual HDFS path, endpoint, or Ranger access groups.

**Resolution:** Storage team confirms HDFS maintenance caused the sink outage. The CaseFile records the full evidence chain including sink primitives with provenance and confidence. The "wrong layer" misdiagnosis that would have occurred in Phase 1A is avoided.

**Note:** In Phase 1A, this same scenario would show `SINK_CONNECTIVITY: UNKNOWN`, `SINK_ERROR_RATE: UNKNOWN` — the system would not misattribute, but would surface the UNKNOWN status and route based on Kafka-layer evidence only.

**Capabilities revealed:** Sink Health Evidence Track (`SINK_CONNECTIVITY`, `SINK_ERROR_RATE`), coverage-weighted hybrid topology (YAML + Smartscape + edge facts), improved diagnosis attribution ("Kafka vs sink"), exposure-safe sink evidence in excerpts, Phase 3 edge-fact coverage without app instrumentation.

---

## System Actor: PagerDuty (External)

**Scope:** PagerDuty creates ServiceNow Incidents externally. AIOps sends PAGE trigger payloads to PD containing `pd_incident_id` (or `pd_dedupe_key`) as a stable identifier for downstream SN correlation. AIOps does NOT create Incidents. PD→SN integration is an external dependency; AIOps relies on it populating a correlation field for Tier 1 linkage.

## System Actor: ServiceNow (Phase 1B)

**Scope:** AIOps interacts with SN via least-privilege integration user (read incident, CRUD problem/task). Interactions:
- **Search:** Find PD-created Incident using tiered correlation (Tier 1: PD field → Tier 2: keyword in description/work_notes → Tier 3: time-window + routing heuristic)
- **Create/Update:** Idempotent Problem upsert (`external_id = aiops_case_id`), PIR task upsert (`external_id = aiops_case_id:task_type`)
- **Retry:** Exponential backoff with jitter over 2-hour window (1m, 2m, 5m, 10m, 20m, 30m cap)
- **Fail-safe:** `FAILED_FINAL` after 2 hours → Slack escalation (exposure-safe: case_id + pd_incident_id + search fields used, no sensitive identifiers)
- **Linkage state:** Persisted as `PENDING → SEARCHING → LINKED` or `SEARCHING → FAILED_TEMP → SEARCHING` or `SEARCHING → FAILED_FINAL`
- **All API calls logged** with request_id, case_id, SN sys_ids touched, outcome, latency

## Journey Requirements Summary

| Capability Area | Journeys |
|---|---|
| Evidence Builder + Peak Profile | 1, 2, 3, 5 |
| Ownership routing (multi-level) | 1, 2, 3 |
| Rulebook gating (AG0–AG6) | 1, 2, 3, 4, 6 |
| CaseFile durability + audit trail | 1, 2, 3, 4, 5 |
| Exposure denylist (excerpt/Slack) | 1, 2, 3, 4, 7 |
| Hot-path minimal contract | 1, 2 |
| `PM_PEAK_SUSTAINED` postmortem | 1, 4 |
| Storm control (dedupe) | 2, 6 |
| Degraded-mode transparency (`DegradedModeEvent`, `TelemetryDegradedEvent`) | 6 |
| Outbox SLO + health monitoring | 5, 6 |
| SN linkage (Phase 1B) | 1, 4, SN actor |
| Local-dev Mode A/B | 5 |
| Labeling + reroute feedback loop | 2, 3 |
| Instance-scoped topology | 1, 2, 3, 5 |
| Sink Health Evidence Track (Phase 3) | 7 |
| Hybrid topology (Phase 3) | 7 |
