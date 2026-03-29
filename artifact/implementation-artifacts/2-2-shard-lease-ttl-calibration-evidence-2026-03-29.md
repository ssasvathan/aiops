# Story 2.2 Shard Lease TTL Calibration Evidence (2026-03-29)

## Purpose

This artifact captures the calibration inputs and computed lease TTL outputs used for Story 2.2.
It is the auditable reference for p95-based shard lease tuning and subsequent re-calibration.

## Measurement Protocol

- Cadence: 5-minute hot-path scheduler cycles
- Safety margin rule: `safety_margin_seconds >= 30`
- Candidate formula: `candidate_ttl_seconds = ceil(p95_seconds + safety_margin_seconds)`
- Guardrail: `candidate_ttl_seconds < HOT_PATH_SCHEDULER_INTERVAL_SECONDS`
- Scheduler interval at calibration time: `300s`

## Recorded Windows and Results

| Environment | Window Start (UTC) | Window End (UTC) | Sample Count (n) | p95 (s) | Margin (s) | Candidate TTL (s) |
|---|---|---|---:|---:|---:|---:|
| UAT | 2026-03-22 00:00:00 | 2026-03-29 00:00:00 | 2016 | 263 | 31 | 294 |
| DEV | 2026-03-22 00:00:00 | 2026-03-29 00:00:00 | 2016 | 220 | 30 | 250 |

## Applied Configuration Decisions

- `config/.env.uat.template`: `SHARD_LEASE_TTL_SECONDS=294`
- `config/.env.prod.template`: `SHARD_LEASE_TTL_SECONDS=294` (aligned to approved UAT basis)
- `config/.env.dev`: `SHARD_LEASE_TTL_SECONDS=250` (DEV-specific basis)

Guardrail verification:

- UAT/Prod: `294 < 300` -> pass
- DEV: `250 < 300` -> pass

## Recalibration Procedure

1. Export a representative 7-day UAT cycle-duration dataset at 5-minute cadence.
2. Record `window_start_utc`, `window_end_utc`, `sample_count`, and `p95_seconds` in this artifact (new dated section/file).
3. Select `safety_margin_seconds >= 30` and compute `candidate_ttl_seconds`.
4. Validate `candidate_ttl_seconds < HOT_PATH_SCHEDULER_INTERVAL_SECONDS`.
5. Update env templates and rerun full regression with zero skipped tests.
6. Commit env changes and the updated calibration evidence artifact together.
