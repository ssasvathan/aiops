# Source Tree Analysis

```text
aiops/
├── src/aiops_triage_pipeline/                  # Core backend package
│   ├── __main__.py                             # Runtime entrypoint (--mode hot/cold/outbox/lifecycle)
│   ├── pipeline/
│   │   ├── scheduler.py                        # Stage orchestration and degraded-mode handling
│   │   └── stages/                             # Evidence/peak/topology/casefile/outbox/gating/dispatch modules
│   ├── contracts/                              # Frozen v1 policy and event contracts
│   ├── models/                                 # Domain and stage payload models
│   ├── integrations/                           # Prometheus/Kafka/Slack/PagerDuty/ServiceNow adapters
│   ├── outbox/                                 # Durable outbox schemas, state machine, repository, worker
│   ├── linkage/                                # ServiceNow linkage retry schema/state/repository
│   ├── storage/                                # S3/MinIO client and write-once casefile IO
│   ├── registry/                               # Topology registry loading and ownership resolution
│   ├── health/                                 # Health registry, /health server, OTLP + alert evaluators
│   ├── cache/                                  # Redis-backed dedupe/findings/peak/evidence cache helpers
│   ├── diagnosis/                              # Cold-path diagnosis graph and LLM fallback
│   ├── denylist/                               # Sensitive-field suppression enforcement
│   ├── logging/                                # Structlog configuration
│   └── errors/                                 # Domain-specific exceptions and invariants
├── config/
│   ├── .env.*                                  # Local/dev/docker/uat/prod environment profiles
│   ├── denylist.yaml                           # Data exposure denylist rules
│   ├── policies/*.yaml                         # Rulebook, outbox, retention, alerting, topology contracts
│   └── prometheus.yml                          # Local Prometheus scrape config
├── tests/
│   ├── unit/                                   # Contract, stage, storage, integration, health unit coverage
│   └── integration/                            # Docker-backed integration and e2e coverage
├── harness/                                    # Synthetic telemetry source and behavior patterns
├── docker-compose.yml                          # Local dependent service topology
├── Dockerfile                                  # Multi-stage runtime image build
└── scripts/smoke-test.sh                       # End-to-end local stack health check
```

## Entry Points

- CLI runtime: `src/aiops_triage_pipeline/__main__.py`
- Health listener bootstrap: `src/aiops_triage_pipeline/health/server.py`
- Harness service: `harness/main.py`

## Key File Locations

- Contracts: `src/aiops_triage_pipeline/contracts/*`
- Durable outbox schema: `src/aiops_triage_pipeline/outbox/schema.py`
- Linkage retry schema: `src/aiops_triage_pipeline/linkage/schema.py`
- Runtime settings: `src/aiops_triage_pipeline/config/settings.py`
- Stage orchestration: `src/aiops_triage_pipeline/pipeline/scheduler.py`

## Integration Paths

- Pipeline stages call integration adapters under `integrations/`.
- Outbox worker emits Kafka contracts after durable state transitions.
- ServiceNow linkage persists retry state and escalates failed-final cases.
