# Comprehensive Analysis (core)

## Scan Level Execution

- Requested scan level: exhaustive
- Batches completed (subfolder strategy):
  - `src/aiops_triage_pipeline` -> 91 files, 16923 lines
  - `tests/unit` -> 79 files, 20074 lines
  - `tests/integration` -> 9 files, 2589 lines
  - `harness` -> 10 files, 294 lines
  - `config` -> 17 files, 820 lines
  - `scripts` -> 1 file, 79 lines

## Configuration Management

- Environment files: `config/.env.local`, `.env.dev`, `.env.docker`, `.env.uat.template`, `.env.prod.template`
- Policy contracts: `config/policies/*.yaml` (rulebook, TTL, outbox, retention, alerting, ServiceNow linkage, topology)
- Runtime settings validator: `src/aiops_triage_pipeline/config/settings.py`

## Authentication / Security Patterns

- Integration-mode safety controls (`OFF|LOG|MOCK|LIVE`) for PagerDuty, Slack, ServiceNow, LLM
- Secret-bearing fields are masked in startup config logs
- Kerberos guardrails for Kafka SASL_SSL mode
- Denylist sanitization before external notifications and ServiceNow payload writes

## Entry Points and Bootstrap

- Primary app entrypoint: `src/aiops_triage_pipeline/__main__.py`
- Supported modes: `hot-path`, `cold-path`, `outbox-publisher`, `casefile-lifecycle`
- Health endpoint bootstrap: `src/aiops_triage_pipeline/health/server.py`
- Supporting harness entrypoint: `harness/main.py`

## Shared Code and Utilities

- No dedicated `shared/` or `common/` directory pattern; shared functionality is package-oriented:
  - `contracts/`, `models/`, `logging/`, `errors/`, `config/`, `health/`

## Async / Event-Driven Architecture

- Async scheduling and stage execution in `pipeline/scheduler.py`
- Async Prometheus collection with threaded blocking-call isolation
- Background outbox publisher worker loop
- Durable retry orchestration for ServiceNow linkage

## CI/CD and Operations

- Local operational baseline: Dockerfile + `docker-compose.yml`
- Infrastructure services in compose: Kafka/ZooKeeper, Postgres, Redis, MinIO, Prometheus, harness, app
- No `.github/workflows/*` pipeline files currently present

## Localization

- No first-class i18n/l10n directory (`i18n/`, `locales/`, `translations/`) detected

## Integration Summary

- External systems: Prometheus, Kafka, PagerDuty, Slack, ServiceNow, S3-compatible object storage
- Reliability boundaries:
  - Outbox durable state machine
  - Linkage retry state table
  - Write-once CaseFile stage persistence
