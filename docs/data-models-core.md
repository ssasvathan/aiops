# Data Models (core)

## Durable SQL Schemas

### outbox

Source: `src/aiops_triage_pipeline/outbox/schema.py`

- Primary key: `id`
- Natural unique key: `case_id`
- Core columns:
  - `case_id`, `casefile_object_path`, `triage_hash`
  - `status` in `PENDING_OBJECT | READY | SENT | RETRY | DEAD`
  - `created_at`, `updated_at`
  - `delivery_attempts`, `next_attempt_at`
  - `last_error_code`, `last_error_message`
- Indexing:
  - `(status, next_attempt_at)`
  - `(status, updated_at)`
  - `(status, created_at)`

### sn_linkage_retry

Source: `src/aiops_triage_pipeline/linkage/schema.py`

- Primary key: `case_id`
- Core columns:
  - `pd_incident_id`, `incident_sys_id`
  - `state` in `PENDING | SEARCHING | FAILED_TEMP | LINKED | FAILED_FINAL`
  - `attempt_count`, `retry_window_minutes`
  - `first_attempt_at`, `updated_at`, `deadline_at`, `next_attempt_at`
  - `request_id`, `last_error_code`, `last_error_message`
  - `last_retry_after_seconds`, `last_reason_metadata`
- Indexing:
  - `(state, next_attempt_at)`
  - `(state, updated_at)`

## Object Storage Data Model

Source: `src/aiops_triage_pipeline/storage/casefile_io.py`, `models/case_file.py`

- Path convention: `cases/<case_id>/<stage>.json`
- Stage payloads:
  - `triage` -> `CaseFileTriageV1`
  - `diagnosis` -> `CaseFileDiagnosisV1`
  - `linkage` -> `CaseFileLinkageV1`
  - `labels` -> `CaseFileLabelsV1`
- Integrity model:
  - Stage hashes are recomputed and validated before/after persistence
  - Write-once semantics enforced for stage objects

## Contract and Domain Model Families

### Policy / contract models (`contracts/`)

- Rulebook, peak policy, redis TTL policy, outbox policy, retention policy
- Prometheus metric contract and ServiceNow linkage contract
- Canonical event contracts: gate input, action decision, case header, triage excerpt, diagnosis report

### Runtime domain models (`models/`)

- Evidence and anomaly findings
- Peak classifications and sustained-window state
- Health status and degraded-mode events
- CaseFile downstream context and stage payload models

## Migration Strategy Signal

- No Alembic/Flyway migration folder detected.
- Schema lifecycle currently managed in-code via SQLAlchemy Core DDL helpers (`create_*_table`).
