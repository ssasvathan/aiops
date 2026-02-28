# Outbox Policy v1 — Postgres Durable Outbox (CaseHeader publish)
Date: 2026-02-22
Status: FROZEN (Phase 1A)

## Invariants (locked)
- Invariant A: write CaseFile to object storage BEFORE publishing Kafka header
- Invariant B2: Postgres Durable Outbox ensures publish after crash
- Object existence check before publish

## State machine (v1)
PENDING_OBJECT → READY → SENT
Additional: RETRY, DEAD

## Retention (default)
SENT:
- prod:      14 days
- nonprod:    7 days
- local/dev:  2 days

DEAD:
- prod:      90 days
- nonprod:   30 days
- local/dev:  7 days

PENDING_OBJECT / READY / RETRY:
- retain until resolved; operated via age/backlog alerts

## Delivery SLO (prod)
Measured as: CaseFile write success → Kafka header publish success
- p95 ≤ 1 minute
- p99 ≤ 5 minutes
- critical breach: p99 > 10 minutes

## Alert triggers (starting thresholds)
PENDING_OBJECT oldest age:
- >5 min warn
- >15 min critical

READY oldest age:
- >2 min warn
- >10 min critical

READY count:
- >100 warn
- >1000 critical (tune later)

RETRY oldest age:
- >30 min critical

DEAD count:
- prod: >0 critical
- nonprod: >5 warn, >20 critical
