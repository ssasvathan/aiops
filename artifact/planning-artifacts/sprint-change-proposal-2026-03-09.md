# Sprint Change Proposal — Hot-Path Verification Gap
**Date:** 2026-03-09
**Status:** Approved — Ready for Implementation
**Scope Classification:** Minor
**Proposed by:** Correct Course Workflow (BMAD)

---

## Section 1: Issue Summary

### Problem Statement

The hot-path pipeline has been receiving a series of isolated fixes (4 commits in a short window: `fix(hot-path) ×3`, `fix(logging) ×1`) without a reliable way to confirm each fix worked end-to-end. This made every iteration feel unstable — not because the code was fundamentally broken, but because there was no verification protocol to prove it was working.

### Discovery Context

Identified during sprint execution when `docker compose up` repeatedly produced uncertain outcomes. Live evidence captured during this workflow confirmed:

- The application **is currently functioning correctly** — 3 complete hot-path scheduler cycles with zero errors, drift=0 on steady-state cycles
- Two required settings (`PROMETHEUS_URL`, `HOT_PATH_SCHEDULER_INTERVAL_SECONDS`) were added to `config/.env.docker` but never committed, meaning the working state is **not reproducible** from the repository
- A `WARNING` fires every cycle for `env=harness` not found in the Redis TTL policy — noisy and misleading
- The harness produces Prometheus metrics with `env=harness` but no topology entry exists for that env, so the evidence pipeline can never produce a casefile from harness signals — end-to-end detection is structurally blocked

### Root Cause

**Story 1.8** (Local Development Environment) has an explicit acceptance criterion that was never delivered:

> *"a smoke test script validates that all services are healthy and reachable"*

Without this script, every developer must manually interpret logs to determine whether the system is healthy — leading to the trial-and-error fix pattern observed.

---

## Section 2: Impact Analysis

### Epic Impact

| Epic | Impact |
|---|---|
| **Epic 1: Project Foundation & Developer Experience** | Two stories with unmet ACs: Story 1.8 (smoke test missing) and Story 1.9 (harness env not wired into detection chain) |
| Epic 2–8 | Not directly blocked, but carry hidden verification risk until Epic 1 closure |

### Story Impact

| Story | Status | Required Change |
|---|---|---|
| **Story 1.8** — Local Dev Environment | AC incomplete | Add smoke test script; confirm all AC points met |
| **Story 1.9** — Harness Traffic Generation | AC incomplete | Wire `env=harness` into TTL policy and topology registry so signals can reach the gate stage |
| **Story 1.10** *(new, optional)* | Not yet created | End-to-end casefile production verification: harness triggers anomaly → pipeline produces casefile → confirmed in MinIO + Postgres |

### Artifact Conflicts

| Artifact | Conflict | Required Change |
|---|---|---|
| `config/.env.docker` | Uncommitted required settings — not reproducible from repo | Commit `PROMETHEUS_URL` and `HOT_PATH_SCHEDULER_INTERVAL_SECONDS` additions |
| `config/policies/redis-ttl-policy-v1.yaml` | `env=harness` missing — WARNING fires every cycle | Add `harness` env block mirroring `local` TTL values |
| Smoke test script *(missing)* | Story 1.8 AC unmet | Create `scripts/smoke-test.sh` or equivalent |
| `_bmad/input/feed-pack/topology-registry.yaml` | No `env=harness` stream entry | Add harness-scoped topology entry or explicitly document that harness signals are out-of-band |
| `artifact/planning-artifacts/epics.md` | Stories 1.8 and 1.9 shown as complete | Update status to reflect AC completion work required |

### Technical Impact

- No code changes required to `__main__.py` or any pipeline stage
- JSON log output is **expected and correct** (NFR-O3 compliant structlog pipeline) — not a bug
- `HOT_PATH_SCHEDULER_INTERVAL_SECONDS=30` is appropriate for local docker iteration (default 300s is too slow for development feedback loops)

---

## Section 3: Recommended Approach

**Selected: Direct Adjustment (Option 1)**

Modify and complete existing Story 1.8 and 1.9 acceptance criteria within the current Epic 1 structure. No rollback, no MVP reduction, no new epics required.

**Rationale:**
- The application is working — the problem is absence of a verification layer, not broken logic
- All changes are additive and low-risk; no working behavior is altered
- Once a smoke test exists, every future fix can be verified in under 2 minutes
- Team momentum is fully preserved

**Effort:** Low
**Risk:** Low
**Timeline impact:** Minimal — 1–2 targeted stories, no downstream epic disruption

---

## Section 4: Detailed Change Proposals

### Change 1 — Commit Config Drift in `.env.docker`

**Story:** 1.8
**Artifact:** `config/.env.docker`

```
OLD: (missing)

NEW (already present, needs committing):
# Prometheus — use container service name for container-to-container networking
PROMETHEUS_URL=http://prometheus:9090

# Hot-path scheduler — short interval for local docker iteration (default 300s is too slow)
HOT_PATH_SCHEDULER_INTERVAL_SECONDS=30
```

**Rationale:** These settings are required for the app to start. Without committing them, any developer cloning the repo will hit a startup failure with no clear error — exactly the pattern that triggered the isolated fix loop.

---

### Change 2 — Add `harness` env to Redis TTL Policy

**Story:** 1.9
**Artifact:** `config/policies/redis-ttl-policy-v1.yaml`

```
OLD:
ttls_by_env:
  local:
    evidence_window_seconds: 600
    ...
  dev: ...
  uat: ...
  prod: ...

NEW: (add after local block)
  harness:
    evidence_window_seconds: 600      # match local — fast iteration
    peak_profile_seconds: 3600
    dedupe_seconds: 300
    dedupe_ttl_by_action:
      page_seconds: 7200
      ticket_seconds: 14400
      notify_seconds: 3600
```

**Rationale:** Eliminates the `evidence_window_ttl_env_not_found` WARNING that fires every cycle. Harness signals use `env=harness`; this entry ensures TTL lookup succeeds without fallback.

---

### Change 3 — Create Docker Smoke Test Script

**Story:** 1.8
**Artifact:** `scripts/smoke-test.sh` *(new file)*

**Proposed behaviour:**
1. Wait for all services to report healthy (`docker compose ps` health status)
2. Verify app container is running (not exited)
3. Tail app logs for N seconds and assert:
   - At least one `hot_path_cycle_completed` event with no `hot_path_startup_failed` or `hot_path_bootstrap_failed`
   - Zero `CRITICAL` or `ERROR` severity lines
   - JSON log lines are valid JSON (parseable)
4. Exit 0 on pass, non-zero with specific failure message on fail

**Rationale:** Directly satisfies Story 1.8 AC. Gives every developer a single command to confirm the happy path.

---

### Change 4 — Add Harness Topology Entry

**Story:** 1.9
**Artifact:** `_bmad/input/feed-pack/topology-registry.yaml` *(also `config/` equivalent if needed)*

**Proposed change:** Add a harness-scoped stream entry with `env=harness` so that evidence pipeline signals from the harness can traverse topology → gate → casefile stages. This enables end-to-end casefile production in local docker — the missing final proof that the detection chain works.

**Rationale:** Without this, `produced_cases=0` forever in local docker, making it impossible to verify the full pipeline. This is explicitly required by Story 1.9 AC: *"it produces real Prometheus metrics... detectable by the evidence pipeline."*

---

### Change 5 — Story 1.10: End-to-End Happy Path Verification *(optional)*

**Story:** New — Story 1.10
**Type:** New story

**Proposed AC:**
- Given the local docker-compose stack is running with harness active
- When the smoke test completes and the pipeline has run ≥2 cycles
- Then at least one casefile is written to MinIO (`aiops-cases` bucket)
- And at least one outbox record exists in Postgres (`outbox` table) with status `PENDING_OBJECT` or later
- And the `produced_cases` log field shows a value > 0 in at least one cycle
- And a verification script confirms this automatically

**Rationale:** Closes the loop on "the pipeline works end-to-end" — not just "the app starts." This is the definitive proof that harness → evidence → gate → casefile → dispatch works as a chain.

---

## Section 5: Implementation Handoff

### Scope Classification: **Minor**

All changes are within Epic 1 story completion. Direct implementation by the development team. No PO/SM backlog reorganisation required beyond acknowledging Stories 1.8 and 1.9 as open.

### Handoff Recipients

| Role | Responsibility |
|---|---|
| **Dev Team** | Implement all 4 changes above; optionally create Story 1.10 |
| **Product Owner (Sas)** | Approve this proposal; confirm Story 1.10 is in or out of current sprint |

### Recommended Delivery Order

```
1. Commit .env.docker drift              → 5 min, immediate reproducibility
2. Add harness env to TTL policy         → 5 min, eliminates cycle WARNING
3. Write smoke test script               → ~2h, closes Story 1.8 AC
4. Add harness topology entry            → ~1h, closes Story 1.9 AC gap
5. Story 1.10 (optional)                 → ~3h, end-to-end casefile proof
```

### Success Criteria

- `docker compose up && scripts/smoke-test.sh` exits 0 from a clean clone
- Zero `WARNING` or `ERROR` lines in steady-state app logs
- At least one `produced_cases > 0` cycle confirmed in local docker (with Story 1.10 / Change 4)
- No fix is needed that cannot be verified by the smoke test within 2 minutes of applying it

---

*Generated by: Correct Course Workflow (BMAD BMM)*
*Workflow executed: 2026-03-09*
