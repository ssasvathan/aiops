# Epic 4 Acceptance Note — Multi-Replica Coordination and Throughput Safety

- Date: 2026-03-23
- Product Owner: Alice (Product Owner)
- Epic status at closure: done
- Stories delivered: 3/3

## 1) Epic Goal and Scope

Epic 4 delivered safe multi-replica (hot/hot) operation for the aiOps triage pipeline. Platform operators can now deploy two or more pods without duplicate interval execution, with scope shard assignment and automatic pod-failure recovery, all guarded by feature flags that allow activation in lower environments before production promotion. Fail-open semantics ensure Redis unavailability never halts the pipeline.

**FRs delivered:** FR44, FR45, FR46, FR47, FR48

**PRD CRs addressed:**

| CR | Signal | Status |
|---|---|---|
| CR-04: Sharded findings cache | Shard assignment produces even scope distribution; checkpoint replaces per-scope writes | ✅ Delivered in Story 4.2 |
| CR-05: Distributed hot/hot | Two pods run with zero duplicate pages/tickets; cycle lock acquired/yielded visible in OTLP metrics | ✅ Delivered in Stories 4.1 + 4.3 |

## 2) Story-Level Acceptance Verification

| Story | AC Status | Quality Evidence |
|---|---|---|
| 4.1: Add Distributed Cycle Lock with Fail-Open Behavior | ✅ All AC met | 74 unit + 2 integration tests targeted; full regression passing; zero skipped; ruff clean; code review fixes applied |
| 4.2: Coordinate Scope Shards and Recover from Pod Failure | ✅ All AC met | 1097 passed, 0 skipped; 7/7 ATDD green; two-pod contention + failed-holder recovery integration tests pass; code review fixes applied |
| 4.3: Roll Out Distributed Coordination Incrementally | ✅ All AC met | 1113 passed, 0 skipped; flag-combination unit tests (4 combinations); stateless rollout integration tests; operator docs; code review H1/H2/M1/M2/L1/L2 all fixed |

## 3) Rollout Acceptance Signals

What an operator must observe to confirm Epic 4 is behaving correctly when activating in a target environment:

**Cycle lock activation (`DISTRIBUTED_CYCLE_LOCK_ENABLED=true`):**
- [ ] OTLP counter `aiops_coordination_cycle_lock_acquired_total` increments on the pod that wins each interval
- [ ] OTLP counter `aiops_coordination_cycle_lock_yielded_total` increments on pods that yield each interval
- [ ] Under simulated Redis failure: `aiops_coordination_cycle_lock_fail_open_total` increments and cycle execution completes (no halt)
- [ ] No duplicate outbox rows or PagerDuty/Slack dispatches observed across pods for the same interval

**Shard coordination activation (`SHARD_REGISTRY_ENABLED=true`):**
- [ ] OTLP counter `aiops_coordination_shard_assignment_total` increments with shard labels
- [ ] Checkpoint writes per interval are batch-oriented (single Redis write per shard, not per scope)
- [ ] After simulating pod failure (kill pod holding shard lease), remaining pod resumes shard processing within one TTL expiry cycle without manual intervention
- [ ] OTLP counter `aiops_coordination_shard_lease_recovered_total` increments on recovery

## 4) Rollback Acceptance Signals

Feature flags default to `false`. Revert = set both flags back to `false` (or remove env var override):

- [ ] `DISTRIBUTED_CYCLE_LOCK_ENABLED=false` — verify no `aiops:lock:cycle` key is written to Redis after a full cycle execution
- [ ] `SHARD_REGISTRY_ENABLED=false` — verify no `aiops:shard:*` or `aiops:checkpoint:*` keys are written to Redis after a full cycle execution
- [ ] Full regression passes after flag revert: `uv run pytest -q -rs` → 1113 passed, 0 skipped
- [ ] No schema migrations, data migrations, or manual Redis cleanup required for rollback

## 5) Known Limitations and Deferred Items

| Item | Severity | Deferred to |
|---|---|---|
| Story-file in-file `status:` markers for 4.2 and 4.3 are `review` not `done` (sprint-status is authoritative and correct) | Low | Cleanup / Epic 5 story process improvement |
| Formal acceptance-note artifact was not produced at epic closure — this document retroactively closes that gap | Low | Resolved by this document |
| Acceptance-note template not previously defined as a reusable artifact | Low | Resolved — template created at `artifact/epic-acceptance-note-template.md` |

## 6) Product Owner Sign-Off

> Epic 4 delivered its stated goals. All three stories met their acceptance criteria. CR-04 and CR-05 from the PRD technical success checklist are satisfied. Distributed cycle lock and shard coordination are production-ready behind feature flags, with documented activation sequences in `docs/deployment-guide.md`. Rollback requires only flag reversion with no data migration. The epic is accepted.
>
> — Alice (Product Owner), 2026-03-23
