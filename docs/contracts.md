# Contracts

## Contract Strategy

This project uses typed, frozen v1 contracts as stable interfaces between stages and integration boundaries.

Contract modules live in:

- `src/aiops_triage_pipeline/contracts/`

## Event and Decision Contracts

| Contract | Module |
|---|---|
| `GateInputV1` | `contracts/gate_input.py` |
| `ActionDecisionV1` | `contracts/action_decision.py` |
| `CaseHeaderEventV1` | `contracts/case_header_event.py` |
| `TriageExcerptV1` | `contracts/triage_excerpt.py` |
| `DiagnosisReportV1` | `contracts/diagnosis_report.py` |

## Policy and Rule Contracts

| Contract | Module |
|---|---|
| `RulebookV1` | `contracts/rulebook.py` |
| `PeakPolicyV1` | `contracts/peak_policy.py` |
| `PrometheusMetricsContractV1` | `contracts/prometheus_metrics.py` |
| `RedisTtlPolicyV1` | `contracts/redis_ttl_policy.py` |
| `OutboxPolicyV1` | `contracts/outbox_policy.py` |
| `TopologyRegistryLoaderRulesV1` | `contracts/topology_registry.py` |
| `ServiceNowLinkageContractV1` | `contracts/sn_linkage.py` |
| `LocalDevContractV1` | `contracts/local_dev.py` |

## Shared Enum Surface

Common enumerations are defined in `contracts/enums.py` and reused across contracts and pipeline logic.

## Compatibility Guarantees

- Contract schema changes must be intentional and test-backed.
- Serialization compatibility must be validated in tests for changed contracts.
- Downstream consumers should rely on contract types rather than ad-hoc payload assumptions.

## Verification

Recommended checks when changing contracts:

```bash
uv run pytest -q tests/unit/contracts
uv run pytest -q
uv run ruff check
```

## Related Docs

- [Architecture](architecture.md)
- [Local Development](local-development.md)
