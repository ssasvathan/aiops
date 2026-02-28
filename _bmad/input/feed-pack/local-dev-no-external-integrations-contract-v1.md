# Local-Dev No-External-Integrations Contract — v1 (Freeze Candidate)
**Date:** 2026-02-22  
**Goal:** A developer can run the full AIOps pipeline locally **without any external org integrations** (Slack, ServiceNow, PagerDuty, Dynatrace, etc.).  
**Principle:** All integrations are **pluggable via config**; when not configured, the system must **degrade to local-safe behavior** (log sink, local mocks, or local infra).

---

## 1) Non-negotiable requirement
- Local build must run end-to-end with **zero external dependencies** beyond developer machine.
- External integrations must be optional and controlled by config.
- If an integration is disabled/unavailable, the system must:
  - continue core processing
  - record outcomes in CaseFile
  - emit human-visible output locally (logs)

---

## 2) Integration mode matrix (standardized)
Every outbound integration MUST support exactly one of these modes via config:

- `OFF`  → no outbound calls; emit **structured log events** only
- `LOG`  → explicit log-only sink (same as OFF but treated as intentional)
- `MOCK` → send to a **local mock endpoint** (developer-run)
- `LIVE` → send to real endpoint (nonprod/prod)

Recommended default for local: `LOG`.

---

## 3) Required local “infra” options (choose per dev)
Core dependencies for a realistic local run can be satisfied by:
- **Local containers (recommended)**: docker-compose with Kafka + Postgres + Redis + MinIO + Prometheus
- **In-memory substitutes (allowed for quick dev)**: only for non-durable components (e.g., Redis cache), never for CaseFile durability tests

**Hard rule:** CaseFile durability invariants must still be testable in local (object store before Kafka publish).
- Use **MinIO** as the local object store.
- Use **Postgres** locally for outbox to validate state machine behavior.

---

## 4) Concrete fallbacks by integration
### 4.1 Slack (Phase 1A “SOFT” postmortem enforcement)
- Local default: `mode=LOG`
- Behavior when LOG/OFF:
  - emit `NotificationEvent` to logs (JSON) with:
    - `case_id`, `final_action`, `routing_key`, `support_channel` (if known), `postmortem_required`, `reason_codes`
  - no external calls

### 4.2 ServiceNow (Phase 1B HARD automation)
- Local default: `mode=LOG`
- Behavior when LOG/OFF:
  - emit `SNLinkageAttemptEvent` to logs with:
    - `case_id`, `sn_linkage_status`, `reason_codes`, retry schedule decision
  - no Problems/tasks created

### 4.3 PagerDuty
- AIOps does not create Incidents (locked).  
- Local default: `mode=OFF`
- If any PD correlation IDs are needed for SN linkage testing, use `MOCK` mode with a local stub that returns deterministic IDs.

### 4.4 Dynatrace / Smartscape (Phase 3+)
- Local default: `mode=OFF`
- Provide `MOCK` mode later that reads a local “edge facts” file if needed.

### 4.5 Object Storage
- Local default: MinIO (LIVE to local endpoint)
- If MinIO not configured: fail-fast with clear message (because CaseFile durability is core)

### 4.6 Prometheus
Two local options:
- **LIVE (local Prometheus)** scraping exporters from local Kafka / lag exporter
- **MOCK (replay file provider)** for fast iteration (clearly flagged as mock; not used for MVP truth claims)

Local default recommendation: `LIVE` when running docker-compose; `MOCK` only for developer convenience.

---

## 5) Config contract (minimum)
A single config section per integration:
- `integrations.<name>.mode = LOG|MOCK|LIVE|OFF`
- `integrations.<name>.endpoint = ...` (only used in MOCK/LIVE)
- `integrations.<name>.credentials_ref = ...` (LIVE only; absent in local)

---

## 6) Definition of Done (local dev)
A developer can:
1) run harness traffic (Phase 0) or replay metrics
2) build evidence + peak + diagnosis + CaseFile
3) write CaseFile to local MinIO
4) publish header/excerpt to local Kafka (after outbox)
5) run action gating + dedupe
6) observe notifications/ticket intents via **logs** with structured events

No external calls should be required; any attempted calls must be blocked by config.

