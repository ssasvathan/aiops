# PeakPolicy v1 — 5-minute window semantics + Prometheus metric alignment
Date: 2026-02-22
Status: FROZEN (Phase 0 + Phase 1A)

## Purpose
Provide deterministic, auditable definitions for:
- peak window detection (for “near peak ingress” reasoning)
- sustained behavior (5 consecutive buckets)
- UNKNOWN handling (missing series is never treated as 0)

## Time semantics (locked)
- Bucket size: 5 minutes
- Sustained: 5 consecutive buckets (25 minutes)
- Buckets aligned to wall-clock 5-minute boundaries (00, 05, 10, ...)

## Canonical identities
- cluster_id := cluster_name (exact string)
- Topic evidence identity: (env, cluster_id, topic)
- Consumer lag identity: (env, cluster_id, group, topic)

## Canonical Prometheus metrics (v1)
Topic ingress / broker-topic metrics:
- messages-in rate: kafka_server_brokertopicmetrics_messagesinpersec
- bytes-in rate:    kafka_server_brokertopicmetrics_bytesinpersec
- bytes-out rate:   kafka_server_brokertopicmetrics_bytesoutpersec

Broker-topic request health:
- failed produce req/s: kafka_server_brokertopicmetrics_failedproducerequestspersec
- failed fetch req/s:   kafka_server_brokertopicmetrics_failedfetchrequestspersec
- total produce req/s:  kafka_server_brokertopicmetrics_totalproducerequestspersec
- total fetch req/s:    kafka_server_brokertopicmetrics_totalfetchrequestspersec

Consumer group telemetry:
- consumer lag:    kafka_consumergroup_group_lag
- consumer offset: kafka_consumergroup_group_offset

## Peak profile (baseline)
For each (env, cluster_id, topic), compute a baseline distribution on 5-minute buckets over history:
- p50, p90, p95 of messages-in rate (primary)
Optionally (same method):
- p95 of bytes-in rate (supports “large-message” volume shifts)

Minimum history to assert peak confidently:
- Preferred: >= 7 days of 5-minute buckets
- If less: set peak_confidence to LOW and allow downstream downgrade (do not “pretend” high confidence)

## Peak detection (per 5-minute bucket)
- peak=true  when current_messages_in_rate >= baseline_p95_messages_in_rate
- near_peak=true when current_messages_in_rate >= baseline_p90_messages_in_rate

## Sustained detection
- sustained=true when the condition holds for 5 consecutive buckets

## UNKNOWN handling (truthfulness rule)
If a required metric series for the identity is absent for the bucket (or cannot be evaluated):
- EvidenceStatus := UNKNOWN
- peak / near_peak / sustained MUST be treated as UNKNOWN (not false)
Downstream logic may downgrade confidence/action, but must not treat UNKNOWN as “OK”.

## Notes
- Exact label sets may differ by exporter; the Evidence Builder must aggregate to the canonical identities above.
- This policy freezes semantics and canonical metric names; if metric names differ in any environment, use a versioned alias map (see prometheus-metrics-contract-v1.yaml).
