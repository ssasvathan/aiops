# Project Structure & Boundaries

## Complete Project Directory Structure

Existing structure with revision-phase additions marked with `[NEW]`:

```
aiops/
├── pyproject.toml                          # Dependency source of truth
├── uv.lock
├── Dockerfile
├── docker-compose.yaml
├── config/
│   ├── .env.local
│   ├── .env.docker
│   ├── .env.dev
│   ├── .env.prod.template
│   ├── .env.uat.template
│   ├── denylist.yaml
│   ├── prometheus.yml
│   ├── topology-registry.yaml              # [NEW] relocated from _bmad/input/ (CR-11)
│   └── policies/
│       ├── anomaly-detection-policy-v1.yaml # [NEW] per-detector sensitivity (CR-03)
│       ├── casefile-retention-policy-v1.yaml
│       ├── local-dev-contract-v1.yaml
│       ├── operational-alert-policy-v1.yaml
│       ├── outbox-policy-v1.yaml
│       ├── peak-policy-v1.yaml
│       ├── prometheus-metrics-contract-v1.yaml
│       ├── redis-ttl-policy-v1.yaml
│       ├── rulebook-v1.yaml                # Modified: predicates become executable (CR-02)
│       ├── servicenow-linkage-contract-v1.yaml
│       └── topology-registry-loader-rules-v1.yaml  # Modified: version fields removed (CR-11)
├── src/aiops_triage_pipeline/
│   ├── __init__.py
│   ├── __main__.py                         # Composition root — all wiring (CR-05, CR-01)
│   ├── audit/
│   │   ├── __init__.py
│   │   └── replay.py
│   ├── cache/
│   │   ├── __init__.py
│   │   ├── client.py
│   │   ├── dedupe.py                       # Modified: atomic SET NX (CR-05)
│   │   ├── evidence_window.py              # Modified: bulk MGET (CR-10)
│   │   ├── findings_cache.py
│   │   ├── peak_cache.py
│   │   └── sustained_state.py              # [NEW] Redis-backed sustained window (CR-05)
│   ├── config/
│   │   ├── __init__.py
│   │   └── settings.py                     # Modified: new fields (CR-05, CR-03)
│   ├── contracts/
│   │   ├── __init__.py
│   │   ├── action_decision.py
│   │   ├── anomaly_detection_policy.py     # [NEW] per-detector sensitivity (CR-03)
│   │   ├── case_header_event.py
│   │   ├── casefile_retention_policy.py
│   │   ├── diagnosis_report.py
│   │   ├── enums.py
│   │   ├── gate_input.py
│   │   ├── local_dev.py
│   │   ├── operational_alert_policy.py
│   │   ├── outbox_policy.py
│   │   ├── peak_policy.py
│   │   ├── prometheus_metrics.py
│   │   ├── redis_ttl_policy.py
│   │   ├── rulebook.py                     # Modified: typed applies_when (CR-02)
│   │   ├── sn_linkage.py
│   │   ├── topology_registry.py            # Modified: v0 fields removed (CR-11)
│   │   └── triage_excerpt.py
│   ├── coordination/                       # [NEW] package (CR-05)
│   │   ├── __init__.py                     # Public API: CycleLock
│   │   ├── cycle_lock.py                   # SET NX EX protocol
│   │   └── protocol.py                     # CycleLock protocol
│   ├── denylist/
│   │   ├── __init__.py
│   │   ├── enforcement.py
│   │   └── loader.py
│   ├── diagnosis/
│   │   ├── __init__.py
│   │   ├── evidence_summary.py             # [NEW] deterministic builder (CR-06)
│   │   ├── fallback.py
│   │   ├── graph.py                        # Modified: remove criteria (CR-08)
│   │   └── prompt.py                       # Modified: enriched prompt (CR-09)
│   ├── errors/
│   │   ├── __init__.py
│   │   └── exceptions.py
│   ├── health/
│   │   ├── __init__.py
│   │   ├── alerts.py
│   │   ├── metrics.py                      # Modified: coordination counters (CR-05)
│   │   ├── otlp.py                         # Modified: pod identity (CR-05)
│   │   ├── registry.py
│   │   └── server.py
│   ├── integrations/
│   │   ├── __init__.py
│   │   ├── base.py
│   │   ├── kafka.py
│   │   ├── kafka_consumer.py               # [NEW] consumer adapter (CR-07)
│   │   ├── llm.py
│   │   ├── pagerduty.py
│   │   ├── prometheus.py
│   │   ├── servicenow.py
│   │   └── slack.py
│   ├── linkage/
│   │   ├── __init__.py
│   │   ├── repository.py
│   │   ├── schema.py
│   │   └── state_machine.py
│   ├── logging/
│   │   ├── __init__.py
│   │   └── setup.py                        # Modified: pod_name context (CR-05)
│   ├── models/
│   │   ├── __init__.py
│   │   ├── anomaly.py
│   │   ├── case_file.py
│   │   ├── events.py
│   │   ├── evidence.py
│   │   ├── health.py
│   │   └── peak.py
│   ├── outbox/
│   │   ├── __init__.py
│   │   ├── metrics.py
│   │   ├── publisher.py
│   │   ├── repository.py                   # Modified: SKIP LOCKED (CR-05)
│   │   ├── schema.py
│   │   ├── state_machine.py
│   │   └── worker.py
│   ├── pipeline/
│   │   ├── __init__.py
│   │   ├── baseline_collector.py           # [NEW] pluggable collector (CR-03)
│   │   ├── baseline_store.py              # [NEW] Redis baseline store (CR-03)
│   │   ├── scheduler.py                    # Modified: cycle lock, sustained wiring (CR-01, CR-05)
│   │   └── stages/
│   │       ├── __init__.py
│   │       ├── anomaly.py                  # Modified: per-scope thresholds (CR-03)
│   │       ├── casefile.py
│   │       ├── dispatch.py
│   │       ├── evidence.py
│   │       ├── gating.py                   # Modified: delegates to rule_engine (CR-02)
│   │       ├── linkage.py
│   │       ├── outbox.py
│   │       ├── peak.py                     # Modified: baseline + memory (CR-03, CR-10)
│   │       └── topology.py
│   ├── registry/
│   │   ├── __init__.py
│   │   ├── loader.py                       # Modified: v0 removal (CR-11)
│   │   └── resolver.py
│   ├── rule_engine/                        # [NEW] package (CR-02)
│   │   ├── __init__.py                     # Public API: evaluate_gates()
│   │   ├── engine.py                       # Sequential gate evaluation loop
│   │   ├── handlers.py                     # Handler registry + check-type handlers
│   │   ├── predicates.py                   # YAML predicate evaluator
│   │   ├── safety.py                       # Post-condition assertions
│   │   └── protocol.py                     # CheckHandler, CheckContext, CheckResult
│   └── storage/
│       ├── __init__.py
│       ├── casefile_io.py
│       ├── client.py
│       └── lifecycle.py
├── tests/
│   ├── conftest.py
│   ├── unit/
│   │   ├── conftest.py
│   │   ├── audit/
│   │   ├── cache/
│   │   │   ├── test_dedupe.py              # Modified: atomic dedupe tests (CR-05)
│   │   │   ├── test_evidence_window.py     # Modified: bulk load tests (CR-10)
│   │   │   ├── test_findings_cache.py
│   │   │   ├── test_peak_cache.py
│   │   │   └── test_sustained_state.py     # [NEW] (CR-05)
│   │   ├── config/
│   │   ├── contracts/
│   │   ├── coordination/                   # [NEW] (CR-05)
│   │   │   └── test_cycle_lock.py
│   │   ├── denylist/
│   │   ├── diagnosis/
│   │   │   ├── test_evidence_summary.py    # [NEW] (CR-06)
│   │   │   ├── test_fallback.py
│   │   │   ├── test_graph.py              # Modified: criteria removal (CR-08)
│   │   │   └── test_prompt.py             # Modified: enriched prompt (CR-09)
│   │   ├── health/
│   │   ├── integrations/
│   │   ├── models/
│   │   ├── outbox/
│   │   ├── pipeline/
│   │   │   ├── stages/
│   │   │   │   └── test_gating.py          # 36 functions must pass unmodified (CR-02)
│   │   │   └── test_scheduler.py
│   │   ├── registry/
│   │   │   ├── test_loader.py             # Modified: v0 tests removed (CR-11)
│   │   │   └── test_resolver.py
│   │   ├── rule_engine/                    # [NEW] (CR-02)
│   │   │   ├── test_engine.py
│   │   │   ├── test_handlers.py
│   │   │   ├── test_predicates.py
│   │   │   └── test_safety.py
│   │   └── storage/
│   └── integration/
│       ├── conftest.py                     # Modified: Redis + Kafka fixtures (CR-05, CR-07)
│       ├── coordination/                   # [NEW] (CR-05)
│       │   └── test_cycle_lock_contention.py  # Multi-process real Redis
│       ├── cold_path/                      # [NEW] (CR-07)
│       │   └── test_consumer_lifecycle.py  # Real Kafka consumer
│       └── ... (existing integration tests)
```

## Architectural Boundaries

**Package dependency rules:**

```
rule_engine/  →  contracts/ only (zero pipeline imports)
coordination/ →  contracts/, config/ only
cache/        →  contracts/, config/ only
diagnosis/    →  contracts/, denylist/ only
pipeline/     →  everything (orchestration layer)
__main__.py   →  everything (composition root)
```

**Runtime mode boundaries (no cross-mode imports):**

| Mode | Entry Point | Packages Used |
|---|---|---|
| hot-path | `__main__.py` → `scheduler.run()` | pipeline/, cache/, coordination/, rule_engine/, registry/, integrations/, health/, outbox/ |
| cold-path | `__main__.py` → `cold_path_consumer.run()` | integrations/kafka_consumer, diagnosis/, storage/, contracts/, denylist/, health/ |
| outbox-publisher | `__main__.py` → `outbox.worker.run()` | outbox/, integrations/kafka, health/ |
| casefile-lifecycle | `__main__.py` → `storage.lifecycle.run()` | storage/, health/ |

## CR-to-Structure Mapping

| CR | New Files | Modified Files |
|---|---|---|
| CR-01 (Wire Redis) | — | `__main__.py`, `scheduler.py` |
| CR-02 (DSL Rulebook) | `rule_engine/` (6 files), `tests/unit/rule_engine/` (4 files) | `contracts/rulebook.py`, `stages/gating.py`, `rulebook-v1.yaml` |
| CR-03 (Baselines) | `pipeline/baseline_collector.py`, `pipeline/baseline_store.py`, `contracts/anomaly_detection_policy.py`, `anomaly-detection-policy-v1.yaml` | `stages/anomaly.py`, `stages/peak.py`, `config/settings.py` |
| CR-04 (Shard checkpoint) | — | `cache/findings_cache.py` |
| CR-05 (Distributed) | `coordination/` (3 files), `cache/sustained_state.py`, integration tests | `cache/dedupe.py`, `outbox/repository.py`, `config/settings.py`, `health/metrics.py`, `health/otlp.py`, `logging/setup.py`, `.env.*` |
| CR-06 (Evidence summary) | `diagnosis/evidence_summary.py`, unit tests | — |
| CR-07 (Cold-path consumer) | `integrations/kafka_consumer.py`, integration tests | `__main__.py` |
| CR-08 (Remove criteria) | — | `diagnosis/graph.py`, `tests/unit/diagnosis/test_graph.py` |
| CR-09 (Prompt optimization) | — | `diagnosis/prompt.py`, `tests/unit/diagnosis/test_prompt.py` |
| CR-10 (Redis bulk + memory) | — | `cache/evidence_window.py`, `stages/peak.py` |
| CR-11 (Topology simplify) | `config/topology-registry.yaml` | `registry/loader.py`, `contracts/topology_registry.py`, `topology-registry-loader-rules-v1.yaml`, tests |

## Data Flow

```
Prometheus ──query──> [evidence stage] ──findings──> [anomaly stage]
                                                         │
Redis baselines <──read── [baseline_store] <──compute── [baseline_collector]
                                                         │
                            ┌────────────────────────────┘
                            ▼
                     [peak stage] ──sustained──> Redis sustained_state (CR-05)
                            │
                            ▼
                     [topology stage] ──config/topology-registry.yaml
                            │
                            ▼
                     [casefile stage] ──write-once──> S3
                            │
                            ▼
                     [outbox stage] ──insert──> Postgres outbox
                            │
                            ▼
                     [gating stage] ──evaluate──> rule_engine/ (CR-02)
                            │                         │
                            │                    Redis dedupe (AG5)
                            ▼
                     [dispatch stage] ──PagerDuty/Slack/ServiceNow
                            │
                     Outbox publisher ──publish──> Kafka
                            │
                     Cold-path consumer (CR-07) ──poll──> Kafka
                            │
                     evidence_summary (CR-06) + LLM ──write──> S3 diagnosis.json
```
