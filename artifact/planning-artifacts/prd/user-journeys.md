# User Journeys

## Journey 1: On-Call Engineer — "The Responder" (Success Path)

**Opening Scene:** It's 2 AM. Priya is the on-call engineer for platform services this week. Her phone buzzes — a single PagerDuty page. Not the usual cascade of 15 raw AlertManager notifications she's learned to dread during cluster-wide issues. One page, one case ID, one clear summary: sustained consumer lag anomaly on `orders-processing` consumer group in the `prod-east` cluster, TIER_0 source topic `order-events`, blast radius classification HIGH with 12 downstream consumers at risk.

**Rising Action:** Priya opens the case artifact linked in the page. The evidence snapshot shows exactly what the pipeline observed: lag building over the sustained window, per-scope baseline deviation, peak classification OFF_PEAK (so this isn't normal peak-hour behavior). The gate evaluation trail shows AG0 validated the input, AG1 confirmed PROD environment permits PAGE, AG2 confirmed required evidence is PRESENT, AG3 verified source topic classification, AG4 confirmed sustained=true above confidence threshold, AG5 passed deduplication (first occurrence of this fingerprint), AG6 flagged for postmortem candidacy. She sees *why* this is a PAGE and not a TICKET — it's PROD, TIER_0, sustained, with full evidence.

**Climax:** Within 90 seconds of the page, Priya knows the affected consumer group, the source topic, the owning team (already resolved by multi-level ownership routing), the blast radius (12 downstream consumers), and the severity rationale. She doesn't need to open Grafana, trace the topology manually, or check a spreadsheet for the escalation contact. She starts remediation.

**Resolution:** The cold-path LLM diagnosis arrives 45 seconds later — a structured report hypothesizing consumer-group-level lag due to partition rebalance, citing the specific evidence pack, suggesting next checks (consumer group describe, partition assignment history). Priya confirms the hypothesis, restarts the stuck consumer, and references the case ID in the incident channel. The case becomes the single source of truth for the post-incident review.

## Journey 2: On-Call Engineer — "The Responder" (Edge Case — Degraded Telemetry)

**Opening Scene:** Marcus receives a Slack notification (not a page) for a consumer lag anomaly on a TIER_1 topic in the UAT environment. The notification includes the case ID and a note: evidence status for two metrics is UNKNOWN due to Prometheus query timeout during this cycle.

**Rising Action:** Marcus opens the case artifact. The gate evaluation shows AG1 capped the action to TICKET (UAT environment cap), but the evidence summary explicitly marks two metrics as UNKNOWN with the reason "Prometheus query timeout." The gate trail shows AG2 evaluated evidence sufficiency with UNKNOWN propagation — the system didn't assume the missing evidence was fine, it propagated uncertainty through the decision.

**Climax:** Marcus sees the system made a conservative decision — TICKET instead of escalating on incomplete evidence. The UNKNOWN metrics are clearly flagged, not silently defaulted to zero or present. He decides to investigate the Prometheus timeout separately but trusts that the triage decision was sound given the available evidence.

**Resolution:** The next cycle's evidence collection succeeds. If the anomaly persists with full evidence, the system will produce a new case with complete data. Marcus doesn't need to second-guess whether the first case missed something — the evidence gaps are explicit and auditable.

## Journey 3: SRE / Platform Engineer — "The Operator"

**Opening Scene:** Jordan owns the aiOps platform deployment. The revision phase just landed all 11 CRs. Jordan deploys to the dev OpenShift cluster with hot/hot 2-pod minimum and the distributed cycle lock feature flag enabled.

**Rising Action:** Jordan monitors the system through OTLP metrics in Dynatrace: pipeline cycle completion rate, outbox delivery latency, coordination lock stats (acquired/yielded/failed per pod), Redis sustained-state hit/miss rates. The structured logs in Kibana show per-cycle evidence collection, gate evaluations, and action dispatches — all tagged with pod identity and correlation IDs.

**Climax:** After a week of stable operation, Jordan notices the action distribution skews heavily toward OBSERVE (expected in dev, where the environment cap is NOTIFY). Jordan adjusts the anomaly detection sensitivity in `anomaly-detection-policy-v1.yaml`, deploys to dev, and reviews casefile artifacts to confirm the threshold change produces the expected shift in finding detection rates. The casefiles stamp the new policy version — Jordan can compare gate decisions before and after the policy change.

**Resolution:** Jordan documents the tuning results, confirms pipeline health metrics are within targets (cycle completion 100%, outbox delivery p95 < 1 min, zero DEAD rows, zero duplicate dispatches), and begins preparing the case for UAT promotion with confidence that the policy behavior is predictable and verifiable.

## Journey 4: Application Team Engineer — "The Maintainer"

**Opening Scene:** Alex's team owns a set of Kafka consumer groups that process payment events. They need to update the topology registry to reflect a new consumer group they've added, and adjust the denylist to exclude a noisy internal metrics topic from notifications.

**Rising Action:** Alex edits the topology registry YAML in `config/` — adding the new consumer group under the correct stream with ownership routing pointing to their team's PagerDuty service and Slack channel. Alex also adds the noisy topic to `config/denylist.yaml`. Both changes are committed and deployed to dev.

**Climax:** The hot-path reloads the topology registry on the next cycle (reload-on-change behavior). Alex watches the structured logs to confirm the new consumer group appears in topology resolution. When a test anomaly fires on the new consumer group, the casefile correctly shows the ownership routed to Alex's team and the denylist-excluded topic is absent from the triage excerpt.

**Resolution:** Alex promotes the configuration changes through UAT to prod, confident the changes behave as expected because the same pipeline logic evaluated them in dev with real execution. The policy version stamp in each casefile traces exactly which topology and denylist versions were active at decision time.

## Journey 5: Kafka Consumer/Producer Stakeholders — "The Recipients"

**Opening Scene:** The payments team runs six consumer groups across three clusters. They don't know aiOps exists. They know their pager goes off when something breaks.

**Rising Action:** Instead of receiving 40 raw AlertManager notifications during a cluster-wide broker issue (one per consumer group per metric threshold), they receive a single PAGE for the highest-severity affected consumer group with ownership pre-resolved to their on-call rotation. The page includes a case ID with blast radius context showing which of their other consumer groups are also affected.

**Resolution:** From the payments team's perspective, alerting just got dramatically better. Fewer alerts, better context, correct routing. They don't need to know about gate evaluations, casefiles, or policy versions. aiOps is invisible infrastructure that makes their operational life less painful.

## Journey Requirements Summary

| Journey | Key Capabilities Revealed |
|---|---|
| Responder — Success Path | Pre-triaged pages with ownership/blast radius, case artifact with evidence + gate trail, cold-path LLM diagnosis, postmortem candidacy detection |
| Responder — Degraded Telemetry | UNKNOWN evidence propagation, conservative decision under uncertainty, explicit evidence gap reporting, multi-cycle recovery |
| Operator | OTLP metrics visibility, YAML policy tuning, casefile-based verification, coordination metrics, environment promotion workflow |
| Maintainer | Topology registry editing + reload, denylist management, configuration testing in lower environments, policy version traceability |
| Recipients | Deduplicated actions, ownership pre-routing, blast radius context, invisible infrastructure improvement |
