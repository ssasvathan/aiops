# API Contracts (core)

## Inbound API Surface

### 1) Health Endpoint

- Interface: raw asyncio TCP HTTP handler
- Code: `src/aiops_triage_pipeline/health/server.py`
- Effective route: `GET /health` (handler reads request headers and returns component map)
- Response: JSON object keyed by component name, values from `ComponentHealth.model_dump()`
- Typical fields per component: `status`, `reason`, `last_updated`

## Outbound API Surface

### 2) Prometheus Query API

- Code: `src/aiops_triage_pipeline/integrations/prometheus.py`
- Method: `GET`
- Endpoint pattern: `/api/v1/query?query=<metric>&time=<iso_timestamp>`
- Contract notes:
  - Expects `status=success`
  - Expects `data.resultType=vector`
  - Normalizes each sample as `{labels: dict[str,str], value: float}`

### 3) PagerDuty Events V2

- Code: `src/aiops_triage_pipeline/integrations/pagerduty.py`
- Method: `POST`
- Endpoint: `https://events.pagerduty.com/v2/enqueue`
- Request contract: `PageTriggerPayload`
  - `routing_key`, `dedup_key`, `event_action=trigger`, `payload`
- Dedup identity: `action_fingerprint` is used as `dedup_key`

### 4) Slack Incoming Webhook

- Code: `src/aiops_triage_pipeline/integrations/slack.py`
- Method: `POST`
- Endpoint: runtime-configured webhook URL
- Payload: text-based operational notifications for degraded mode, postmortem, and linkage escalation

### 5) ServiceNow Table API

- Code: `src/aiops_triage_pipeline/integrations/servicenow.py`
- Methods: `GET`, `POST`, `PATCH`
- Endpoint pattern: `<base_url>/api/now/table/{table}[/{record_sys_id}]`
- Contract behavior:
  - Tiered incident correlation (`tier1`, `tier2`, `tier3`)
  - Idempotent upsert for Problem/PIR records via deterministic external IDs
  - MI-1 guardrails prevent major-incident write scope

### 6) Kafka Event Publication Boundary

- Code: `src/aiops_triage_pipeline/integrations/kafka.py`
- Topics:
  - `aiops-case-header`
  - `aiops-triage-excerpt`
- Message contracts:
  - `CaseHeaderEventV1`
  - `TriageExcerptV1`

## API Contract Entities

- `CaseHeaderEventV1`, `TriageExcerptV1`, `ActionDecisionV1`, `GateInputV1`, `DiagnosisReportV1`
- Operational API policy contracts under `contracts/*` and `config/policies/*`

## Authentication / Authorization Notes

- No end-user auth boundary exposed in this backend (no user-facing REST auth routes).
- External API auth is integration-driven (e.g., ServiceNow bearer token, Slack webhook secret URL, PD routing key).
