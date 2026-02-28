# ServiceNow Linkage Contract — v1 (Freeze Candidate)
**Date:** 2026-02-22  
**Scope:** Phase 1B (HARD postmortem automation): create/update **Problem + PIR tasks** linked to **PagerDuty-created ServiceNow Incident**.

---

## 1) Non-negotiables (locked posture)
- **PagerDuty creates ServiceNow Incidents.** AIOps **does not** create Incidents.
- AIOps may create/update:
  - **Problem** record
  - **PIR tasks** (or equivalent tasks/subtasks)
- Linkage must be **deterministic, auditable, and idempotent**.
- If linkage cannot be confirmed, AIOps must **fail safe** (no duplicate Problems, no task storms) and notify humans.

---

## 2) What “linkage” means
Given an AIOps case (CaseFile + ActionDecision), the system must reliably find the **ServiceNow Incident** that was created by PagerDuty for the same alert, then attach (or update) a **Problem** and **PIR tasks** to that Incident.

**Output fields (persisted in CaseFile and internal linkage store):**
- `sn_incident_number` (e.g., INC0012345)
- `sn_incident_sys_id`
- `sn_problem_number` (optional)
- `sn_problem_sys_id` (optional)
- `sn_linkage_status`: `PENDING | LINKED | FAILED_FINAL`
- `sn_linkage_reason_codes[]`

---

## 3) Correlation strategy (coverage-weighted, config-driven)
We lock the strategy to be **tiered** with explicit fallbacks.

### Tier 1 (preferred): Direct correlation field from PD→SN integration
**Assumption:** The PD→SN integration writes at least one stable PD identifier into the Incident.

**Required AIOps action for PAGE events:**
- Include `pd_incident_id` (or `pd_dedupe_key`) in the PagerDuty trigger payload as a stable identifier.

**ServiceNow search fields (config):**
- `search_fields = [ "u_pagerduty_incident_id", "correlation_id", "u_correlation_id" ]`  
(Actual field name(s) are org-specific; we keep this configurable.)

**Match rule:**
- Query Incident where any `search_field == pd_incident_id`.

### Tier 2: Keyword correlation in Incident text (if Tier 1 not available)
If integration does not populate a dedicated field, search in:
- `short_description`
- `description`
- `work_notes` (if indexed/allowed)

**Keywords (deterministic):**
- `aiops_case_id`
- `action_fingerprint`
- `stream_id`
- `env + cluster_id`
- primary `(topic, group)` identity

This only works if PD→SN templates include alert details; if not, Tier 2 will be weak.

### Tier 3: Time-window + routing + identity heuristic (last resort, lowest confidence)
Search incidents created within a bounded window:
- `created_on ∈ [case_time - 15m, case_time + 120m]`
- AND `assignment_group` or `caller` matches the expected platform intake group (config)
- AND at least 2 of 5 identity tokens appear in text fields

Tier 3 must set `sn_linkage_confidence = LOW` and requires a human escalation signal if used.

---

## 4) Eventual consistency & retry policy (locked)
**Problem:** PD→SN incident creation may be delayed and API indexing can lag.

**Retry policy:**
- Total retry window: **2 hours** from PAGE time
- Backoff: exponential with jitter, e.g. 1m, 2m, 5m, 10m, 20m, 30m (cap)
- If not found after 2 hours: `FAILED_FINAL` and send a Slack escalation (Phase 1A channel) containing:
  - `case_id`, `pd_incident_id`, search fields used, and last query summary
  - No sensitive sink identifiers

---

## 5) Idempotency rules (locked)
To prevent duplicates:
- **Problem external key:** `external_id = aiops_case_id` (preferred) or `action_fingerprint` (fallback).
- When creating/updating the Problem:
  - If a Problem exists with `external_id`, update it (do not create a new one).
- PIR tasks:
  - Created with stable `external_id = aiops_case_id + ":" + task_type`
  - Upsert behavior (create if missing, else update)

This guarantees that reruns and retries do not create duplicate Problems/tasks.

---

## 6) Minimal permissions (least privilege)
ServiceNow integration user must have:
- **READ** on `incident`
- **CREATE/UPDATE/READ** on `problem` and `task` types required for PIR workflow
- No broad admin roles

All API calls must be logged with:
- request id
- case id
- SN sys_ids touched
- outcome and latency

---

## 7) Data exposure controls (executive-safe posture)
- Slack notifications must not include:
  - sink endpoints
  - credentials
  - restricted internal hostnames
- CaseFile may store the SN sys_ids/numbers (not sensitive).

---

## 8) State machine (implementation-neutral contract)
Persist linkage attempts in a small durable table (or in CaseFile metadata + outbox):
- `PENDING` → `SEARCHING` → `LINKED`
- `SEARCHING` → `FAILED_TEMP` (transient errors) → `SEARCHING`
- `SEARCHING` → `FAILED_FINAL` (timeout or hard denial)

---

## 9) Definition of Done (Phase 1B)
A PAGE case in PROD + TIER_0 results in:
1) A ServiceNow Incident exists (created by PD)
2) AIOps links a Problem to that Incident
3) AIOps creates/upserts PIR tasks under the Problem (or equivalent)
4) The CaseFile is updated with `sn_*` linkage fields and provenance

