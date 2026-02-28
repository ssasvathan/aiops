# Redis TTL Policy v1 — Evidence Cache + Action Dedupe
Date: 2026-02-22
Status: FROZEN (Phase 0 + Phase 1A)

## Purpose
Define bounded Redis retention for:
- evidence windows / per-interval findings (cache-only)
- peak profiles (cache-only; recomputable)
- action dedupe keys (storm control)

Redis is NOT system-of-record. CaseFile in object storage is authoritative.

## A) Evidence cache TTL (per-interval + window aggregates + per-interval findings)
- local/dev: 2 hours
- nonprod:   24 hours
- prod:      72 hours

## B) Peak profiles TTL (cache-only; recomputable)
- local/dev: 1 day
- nonprod:   7 days
- prod:      14 days

## C) Action dedupe TTL (storm control; keyed by action_fingerprint)
(applies in all envs; PAGE cannot occur outside PROD+TIER_0 due to rulebook caps)
- PAGE:   120 minutes
- TICKET: 240 minutes
- NOTIFY: 60 minutes
- OBSERVE: 0 (do not store)

## D) Degraded-mode behavior
If Redis is unavailable or error rate exceeds threshold:
- deny PAGE/TICKET
- allow NOTIFY only
