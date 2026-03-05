# Architecture Overview

## Purpose

`aiops-triage-pipeline` is an event-driven backend system that ingests infrastructure telemetry, classifies anomalies, enriches context, and drives deterministic triage/action preparation.

## Runtime Topology

Core local/runtime dependencies:

- Prometheus (telemetry source)
- Kafka + ZooKeeper (event transport)
- Postgres (durable outbox state)
- Redis (cache and dedupe)
- S3-compatible object storage (MinIO locally)

Application runtime modes:

- `hot-path`
- `cold-path`
- `outbox-publisher`

## Pipeline Shape

Hot path:

1. Evidence collection
2. Peak/sustained classification
3. Topology resolution and routing context
4. CaseFile triage assembly
5. Outbox staging
6. Gating input/action assembly
7. Dispatch integration handling

Parallel paths:

- Cold path: diagnosis enrichment and fallback behavior
- Outbox publisher: publishes from durable outbox state

## Package Boundaries

| Package | Responsibility |
|---|---|
| `pipeline/` | Scheduler and stage orchestration |
| `registry/` | Topology loader, resolver, ownership routing, legacy compat views |
| `contracts/` | Frozen v1 contracts and policy models |
| `outbox/` | Outbox schema/state machine/publisher |
| `diagnosis/` | Cold-path diagnosis orchestration and deterministic fallback |
| `storage/` | CaseFile I/O and serialization helpers |
| `cache/` | Evidence/peak/dedupe cache operations |
| `integrations/` | External adapter boundaries and mode control |
| `health/` | Component health tracking and telemetry exports |
| `denylist/` | Shared denylist load/enforcement |
| `logging/` | Structured logging setup |

## Design Invariants

- Deterministic behavior is preferred over implicit defaults in safety-critical paths.
- Topology lookups are in-memory and scope-aware.
- Outbox-mediated publishing is the durability path.
- Cross-boundary data shaping uses shared denylist enforcement.
- Contract models are frozen and validated at boundaries.

## Current Implementation Notes

- Epic 1 through Epic 3 scope is implemented and marked done in sprint tracking.
- Epic 4 is in progress; `pipeline/stages/casefile.py`, `storage/casefile_io.py`, and `models/case_file.py` are currently placeholders and expected to fill in as Epic 4 advances.
- `src/aiops_triage_pipeline/__main__.py` currently parses mode and prints startup mode; full wiring is incremental.

## Related Docs

- [Contracts](contracts.md)
- [Local Development](local-development.md)
- [Schema Evolution Strategy](schema-evolution-strategy.md)
