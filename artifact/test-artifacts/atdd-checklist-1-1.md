---
stepsCompleted:
  - step-01-preflight-and-context
  - step-02-generation-mode
  - step-03-test-strategy
  - step-04-generate-tests
  - step-04c-aggregate
  - step-05-validate-and-complete
lastStep: step-05-validate-and-complete
lastSaved: '2026-04-11'
inputDocuments:
  - artifact/implementation-artifacts/1-1-grafana-prometheus-observability-infrastructure.md
  - _bmad/tea/config.yaml
  - config/prometheus.yml
  - docker-compose.yml
---

# ATDD Checklist: Story 1.1 — Grafana & Prometheus Observability Infrastructure

## TDD Red Phase: COMPLETE

All 33 tests generated. 32 FAIL (red phase — implementation not yet done). 1 PASSES (prometheus healthcheck already exists — contract documented).

- Integration Tests: 33 tests total
- Red Phase Failures: 32
- Pre-existing Contracts Verified: 1 (`test_p1_prometheus_has_healthcheck_defined`)

## Story Details

- **Story ID**: 1-1
- **Story Title**: Grafana & Prometheus Observability Infrastructure
- **Story Status**: ready-for-dev
- **Stack**: backend (Python/pytest)
- **Test File**: `tests/integration/test_infra_story_1_1_grafana_prometheus_red_phase.py`

## Test Strategy

All tests are **config-validation integration tests** — no live docker-compose stack is needed.
Tests validate static configuration correctness of YAML/JSON config files and docker-compose.yml.

Stack detection: `backend` (pyproject.toml present, no frontend indicators).
Generation mode: AI generation (no browser recording needed for backend).

## Acceptance Criteria Coverage

| AC | Priority | Test Class | Tests | Coverage |
|----|----------|-----------|-------|----------|
| AC1: Grafana service in docker-compose | P0/P1 | `TestAC1GrafanaServiceInDockerCompose` | 7 | image, env vars, volume mounts, grafana-data volume |
| AC2: Prometheus datasource provisioning | P0/P1 | `TestAC2PrometheusDatasourceProvisioning` | 6 | file exists, type, url, isDefault, access:proxy, timeInterval |
| AC3: Dashboard provisioning + JSON shells | P0/P1 | `TestAC3DashboardProvisioningAndJsonShells` | 10 | config exists, providers, allowUiUpdates, UID constants, panels=[], schemaVersion |
| AC4: Prometheus scrape job aiops-pipeline | P0 | `TestAC4PrometheusScrapeJob` | 4 | job exists, target app:8080, interval 15s, retention flag 15d |
| AC5: Healthcheck + startup readiness | P0/P1 | `TestAC5GrafanaHealthcheckAndDependency` | 6 | healthcheck, api/health endpoint, depends_on service_healthy, port 3000, prometheus healthcheck |

## Test Execution Results (Red Phase Verification)

```
33 tests collected
32 FAILED (red phase — implementation pending)
1 PASSED (prometheus healthcheck — pre-existing contract)
```

Run command: `uv run pytest tests/integration/test_infra_story_1_1_grafana_prometheus_red_phase.py -v`

## Red Phase Failure Summary

**AC1 failures (7 tests)**:
- `grafana` service not found in docker-compose.yml
- Image not pinned to `grafana/grafana-oss:12.4.2`
- `GF_AUTH_ANONYMOUS_ENABLED` env var not set
- `GF_AUTH_ANONYMOUS_ORG_ROLE` env var not set
- Volume mount `./grafana/provisioning:/etc/grafana/provisioning` missing
- Volume mount `./grafana/dashboards:/var/lib/grafana/dashboards` missing
- `grafana-data` volume not in top-level volumes

**AC2 failures (6 tests)**:
- `grafana/provisioning/datasources/prometheus.yaml` does not exist

**AC3 failures (8 tests)**:
- `grafana/provisioning/dashboards/dashboards.yaml` does not exist
- `grafana/dashboards/aiops-main.json` does not exist
- `grafana/dashboards/aiops-drilldown.json` does not exist

**AC4 failures (4 tests)**:
- `aiops-pipeline` scrape job not in `config/prometheus.yml`
- No `--storage.tsdb.retention.time=15d` flag in prometheus command in docker-compose.yml

**AC5 failures (4 tests)**:
- `grafana` service not defined (no healthcheck, depends_on, or port 3000)

**AC5 pass (1 test)**:
- `prometheus` already has healthcheck in docker-compose.yml ✓

## Critical Architecture Constraints (TDD Compliance Anchors)

These are embedded in test assertions as red-phase guards:

- Grafana image: MUST be `grafana/grafana-oss:12.4.2` (not `grafana/grafana:latest`)
- No `grafana.ini`: All config via `GF_` env vars only
- Dashboard UIDs are constants: `aiops-main` and `aiops-drilldown` (hardcoded — never auto-generated)
- Volume mounts: exact paths `./grafana/provisioning:/etc/grafana/provisioning` and `./grafana/dashboards:/var/lib/grafana/dashboards`
- Prometheus datasource URL: `http://prometheus:9090` (internal docker network)
- `access: proxy` in datasource (not `access: direct`)
- Retention: `--storage.tsdb.retention.time=15d` in Prometheus command (not config file)
- `timeInterval: 15s` in datasource jsonData (matches scrape_interval, NFR11)
- `allowUiUpdates: true` in dashboard provider (hybrid UI-first design workflow)
- `schemaVersion: 39` in both dashboard JSON shells

## Next Steps (TDD Green Phase)

After implementing Story 1.1:

1. Run tests: `uv run pytest tests/integration/test_infra_story_1_1_grafana_prometheus_red_phase.py -v`
2. Verify all 33 tests PASS (green phase)
3. If any tests fail:
   - Either fix implementation (feature bug)
   - Or update test if requirement clarified (document why in test)
4. Move story to `review` status in sprint-status.yaml

## Implementation Guidance

Files to CREATE:
- `grafana/provisioning/datasources/prometheus.yaml`
- `grafana/provisioning/dashboards/dashboards.yaml`
- `grafana/dashboards/aiops-main.json` (uid: aiops-main, schemaVersion: 39, panels: [])
- `grafana/dashboards/aiops-drilldown.json` (uid: aiops-drilldown, schemaVersion: 39, panels: [])

Files to MODIFY:
- `docker-compose.yml` — add grafana service block, update prometheus command, add grafana-data volume
- `config/prometheus.yml` — add aiops-pipeline scrape job

See `artifact/implementation-artifacts/1-1-grafana-prometheus-observability-infrastructure.md` dev notes for exact file content patterns.

## Knowledge Fragments Used

- `test-levels-framework.md` (integration test selection for backend config validation)
- `test-priorities-matrix.md` (P0/P1 risk assignment)
- `test-quality.md` (explicit assertions, deterministic tests)
- `data-factories.md` (no factories needed — config files are the test data)
- `test-healing-patterns.md` (actionable failure messages with "Story 1.1 RED phase:" prefix)
