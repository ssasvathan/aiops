# Critical Folders Summary

| Folder | Purpose | Criticality |
|---|---|---|
| `src/aiops_triage_pipeline/pipeline/stages` | Implements deterministic triage pipeline stages and gating logic | High |
| `src/aiops_triage_pipeline/outbox` | Durable publish sequencing and retry/dead-state handling | High |
| `src/aiops_triage_pipeline/linkage` | ServiceNow linkage retry durability and transition guards | High |
| `src/aiops_triage_pipeline/storage` | Casefile persistence, write-once integrity, lifecycle operations | High |
| `src/aiops_triage_pipeline/contracts` | Frozen interfaces for events and runtime policies | High |
| `src/aiops_triage_pipeline/models` | Canonical domain payloads exchanged across stages | High |
| `src/aiops_triage_pipeline/integrations` | External boundary for Prometheus/Kafka/Slack/PD/SN | High |
| `src/aiops_triage_pipeline/config` | Runtime settings validation and environment binding | Medium |
| `config/policies` | Declarative policy controls for gate, retry, retention, alerts | High |
| `tests/unit` and `tests/integration` | Behavioral regression and system integration safety net | High |

## Critical Folder Count

- folder_count: 10
