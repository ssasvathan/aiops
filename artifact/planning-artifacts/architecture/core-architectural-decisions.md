# Core Architectural Decisions

## Decision Priority Analysis

**Critical Decisions (Block Implementation):**

| ID | Decision | Final Choice | Rationale |
|---|---|---|---|
| D-R1 | Scoring function interface and placement | Pure, module-local function in `pipeline/stages/gating.py` | Smallest change surface, strongest D6 hot/cold isolation, easiest deterministic testing |
| D-R2 | Tier weights and calibration strategy | v1 deterministic weighted formula (base + sustained amplifier + peak amplifier), with UAT calibration | Enables predictable behavior now and tunable policy constants later |
| D-R3 | Reason code taxonomy | Keep AG4 fail codes (`LOW_CONFIDENCE`, `NOT_SUSTAINED`) unchanged; add richer scoring taxonomy in scoring metadata/logs | Preserves compatibility while improving observability |
| D-R4 | `proposed_action` derivation | Score-band mapping: `<0.6=OBSERVE`, `0.6-<0.85=TICKET`, `>=0.85=PAGE` candidate | Creates clear candidate-action intent while preserving downstream caps |
| D-R5 | Configuration values | `STAGE2_PEAK_HISTORY_MAX_DEPTH`: dev=2016, uat=4320, prod=8640; `SHARD_LEASE_TTL_SECONDS`: initial 90, then UAT p95 + safety margin (>=30s) | Restores baseline quality and lease safety with explicit operational calibration path |
| D-R6 | Backward compatibility | No contract/schema migration; replay supports both pre-score and post-score records | Lowest-risk path in frozen-contract architecture and pre-live state |

**Important Decisions (Shape Architecture):**

- None beyond the six release-critical decisions listed above.

**Deferred Decisions (Post-MVP):**

- Numeric micro-calibration of v1 scoring constants based on first UAT confidence distribution telemetry.
- Automated per-environment TTL derivation from observed cycle latency telemetry.

## Data Architecture

- No contract or schema changes.
- `GateInputContext` and `GateInputV1` fields (`proposed_action`, `diagnosis_confidence`) remain structurally unchanged.
- Backward compatibility is ensured through deterministic replay behavior and explicit regression coverage.

## Authentication & Security

- No new auth paths, credentials, or external trust boundaries are introduced.
- Scoring function remains pure hot-path computation with no external I/O.
- Configuration values introduced/updated (`STAGE2_PEAK_HISTORY_MAX_DEPTH`, `SHARD_LEASE_TTL_SECONDS`) contain no secrets and are safe for version-controlled env files.

## API & Communication Patterns

- No inbound/outbound interface additions or shape changes.
- AG4 policy remains authoritative with existing threshold semantics (`diagnosis_confidence >= 0.6`) and reason codes.
- Scoring metadata is carried through internal decision basis/logging without changing frozen contract fields.

## Frontend Architecture

- Not applicable for this backend-only release.

## Infrastructure & Deployment

- Environment-specific peak-depth values are mandatory in env files to eliminate fallback to legacy depth 12.
- Lease TTL policy is `TTL = p95_cycle_duration + safety_margin`, with safety margin >=30s and TTL constrained below scheduler interval.
- Initial coordinated release value is 90 seconds pending measured UAT baseline confirmation for uat/prod tuning.

## Decision Impact Analysis

**Implementation Sequence:**

1. Update environment configuration values (`STAGE2_PEAK_HISTORY_MAX_DEPTH`, initial `SHARD_LEASE_TTL_SECONDS`).
2. Implement module-local scoring function in `pipeline/stages/gating.py` with named constants (no magic numbers).
3. Derive score and candidate `proposed_action` prior to `GateInputV1` assembly.
4. Preserve AG0-AG6 gate evaluation flow and cap-downward behavior.
5. Add/adjust deterministic tests (AG4 boundaries, all-UNKNOWN floor, high-confidence sustained+peak path, replay compatibility).
6. Execute UAT calibration and finalize TTL/weight tuning values if required.

**Cross-Component Dependencies:**

- Peak-depth configuration quality directly affects tier-3 peak amplifier behavior.
- Scoring outputs feed AG4 gating decisions; AG1/AG3/AG4/environment caps remain final action authorities.
- Replay determinism relies on unchanged contract shapes and deterministic scoring logic.
