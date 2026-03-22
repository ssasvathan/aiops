# Story 1.3: Policy & Operational Contract Models

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a platform developer,
I want the 8 frozen policy and operational contracts defined as immutable Pydantic models,
so that policy versioning, TTL configuration, and operational rules are enforced consistently across the pipeline.

> **Source note:** The epics.md user story says "7 contracts" but the Acceptance Criteria lists 8 distinct YAML contracts. This story implements all 8 as specified in the AC.

## Acceptance Criteria

1. **Given** the `contracts/` package exists with event contracts from Story 1.2, **When** the 8 policy contracts are implemented as Pydantic `frozen=True` models, **Then** the following contract modules exist in `src/aiops_triage_pipeline/contracts/`:
   - `RulebookV1` in `rulebook.py`
   - `PeakPolicyV1` in `peak_policy.py`
   - `PrometheusMetricsContractV1` in `prometheus_metrics.py`
   - `RedisTtlPolicyV1` in `redis_ttl_policy.py`
   - `OutboxPolicyV1` in `outbox_policy.py`
   - `ServiceNowLinkageContractV1` in `sn_linkage.py`
   - `LocalDevContractV1` in `local_dev.py`
   - `TopologyRegistryLoaderRulesV1` in `topology_registry.py`

2. **And** attempting to mutate any field on any frozen policy model raises a `pydantic.ValidationError`

3. **And** `model_dump_json()` produces valid JSON and `model_validate_json()` round-trips successfully (reconstructs an identical model) for each of the 8 contracts

4. **And** each contract includes a `schema_version` field (type `Literal["v1"]` with default `"v1"`)

5. **And** the 5 existing stub YAML files in `config/policies/` are updated with real field values matching the model structure, and 3 new stub YAML files are created for the missing contracts:
   - `config/policies/servicenow-linkage-contract-v1.yaml` (new)
   - `config/policies/local-dev-contract-v1.yaml` (new)
   - `config/policies/topology-registry-loader-rules-v1.yaml` (new)

6. **And** `uv run ruff check` passes with zero errors on all implemented contract files

7. **And** unit tests in `tests/unit/contracts/test_policy_models.py` verify immutability, serialization round-trip, and schema validation for all 8 policy contracts

## Tasks / Subtasks

- [x] Task 1: Implement `RulebookV1` (AC: #1, #2, #3, #4)
  - [x] Create `src/aiops_triage_pipeline/contracts/rulebook.py`
  - [x] Define nested models: `RulebookDefaults`, `RulebookCaps`, `GateEffect`, `GateEffects`, `GateCheck`, `GateSpec`
  - [x] Define `RulebookV1(BaseModel, frozen=True)` with all required fields (see Dev Notes)
  - [x] Set `schema_version: Literal["v1"] = "v1"`
  - [x] Update `config/policies/rulebook-v1.yaml` with valid field values matching the model

- [x] Task 2: Implement `PeakPolicyV1` (AC: #1, #2, #3, #4)
  - [x] Create `src/aiops_triage_pipeline/contracts/peak_policy.py`
  - [x] Define nested models: `PeakThresholdPolicy`
  - [x] Define `PeakPolicyV1(BaseModel, frozen=True)` with all required fields (see Dev Notes)
  - [x] Update `config/policies/peak-policy-v1.yaml` with valid field values

- [x] Task 3: Implement `PrometheusMetricsContractV1` (AC: #1, #2, #3, #4)
  - [x] Create `src/aiops_triage_pipeline/contracts/prometheus_metrics.py`
  - [x] Define nested models: `MetricIdentityConfig`, `MetricDefinition`, `TruthfulnessConfig`
  - [x] Define `PrometheusMetricsContractV1(BaseModel, frozen=True)` (see Dev Notes for full field spec from authoritative YAML)
  - [x] Update `config/policies/prometheus-metrics-contract-v1.yaml` with full field values (copy from `_bmad/input/feed-pack/prometheus-metrics-contract-v1.yaml`)

- [x] Task 4: Implement `RedisTtlPolicyV1` (AC: #1, #2, #3, #4)
  - [x] Create `src/aiops_triage_pipeline/contracts/redis_ttl_policy.py`
  - [x] Define nested model: `RedisTtlsByEnv`
  - [x] Define `RedisTtlPolicyV1(BaseModel, frozen=True)` with `ttls_by_env: dict[str, RedisTtlsByEnv]`
  - [x] Update `config/policies/redis-ttl-policy-v1.yaml` with values for local/dev/uat/prod envs

- [x] Task 5: Implement `OutboxPolicyV1` (AC: #1, #2, #3, #4)
  - [x] Create `src/aiops_triage_pipeline/contracts/outbox_policy.py`
  - [x] Define nested model: `OutboxRetentionPolicy`
  - [x] Define `OutboxPolicyV1(BaseModel, frozen=True)` with `retention_by_env: dict[str, OutboxRetentionPolicy]`
  - [x] Update `config/policies/outbox-policy-v1.yaml` with retention values per FR26 (SENT 14d prod, DEAD 90d prod)

- [x] Task 6: Implement `ServiceNowLinkageContractV1` (AC: #1, #2, #3, #4)
  - [x] Create `src/aiops_triage_pipeline/contracts/sn_linkage.py`
  - [x] Define `ServiceNowLinkageContractV1(BaseModel, frozen=True)` (Phase 1B contract; minimal for Phase 1A, see Dev Notes)
  - [x] Create `config/policies/servicenow-linkage-contract-v1.yaml` with stub values

- [x] Task 7: Implement `LocalDevContractV1` (AC: #1, #2, #3, #4)
  - [x] Create `src/aiops_triage_pipeline/contracts/local_dev.py`
  - [x] Define nested model: `LocalDevIntegrationModes`
  - [x] Define `LocalDevContractV1(BaseModel, frozen=True)` (see Dev Notes)
  - [x] Create `config/policies/local-dev-contract-v1.yaml` with integration mode defaults

- [x] Task 8: Implement `TopologyRegistryLoaderRulesV1` (AC: #1, #2, #3, #4)
  - [x] Create `src/aiops_triage_pipeline/contracts/topology_registry.py`
  - [x] Define `TopologyRegistryLoaderRulesV1(BaseModel, frozen=True)` (see Dev Notes)
  - [x] Create `config/policies/topology-registry-loader-rules-v1.yaml` with loader rules

- [x] Task 9: Update `contracts/__init__.py` exports (AC: #1)
  - [x] ADD policy contract exports to the existing Story 1.2 event contract exports (ADDITIVE — do not remove Story 1.2 exports)
  - [x] Add to `__all__`: `RulebookV1`, `PeakPolicyV1`, `PrometheusMetricsContractV1`, `RedisTtlPolicyV1`, `OutboxPolicyV1`, `ServiceNowLinkageContractV1`, `LocalDevContractV1`, `TopologyRegistryLoaderRulesV1`
  - [x] Add to `__all__`: nested models needed by consuming code: `RulebookDefaults`, `RulebookCaps`, `GateSpec`, `GateEffect`, `PeakThresholdPolicy`, `RedisTtlsByEnv`, `OutboxRetentionPolicy`

- [x] Task 10: Create unit tests (AC: #7)
  - [x] Create `tests/unit/contracts/test_policy_models.py`
  - [x] For each of the 8 contracts: test immutability (mutation raises `ValidationError`)
  - [x] For each of the 8 contracts: test `model_dump_json()` → `model_validate_json()` round-trip
  - [x] For each of the 8 contracts: test `schema_version` field equals `"v1"`
  - [x] Test `RulebookV1` construction from dict (simulating YAML-loaded dict)
  - [x] Test `RulebookV1.caps.paging_denied_topic_roles` is accessible and correct type
  - [x] Test `PrometheusMetricsContractV1.metrics` keys are accessible
  - [x] Test `RedisTtlPolicyV1.ttls_by_env["prod"].dedupe_seconds` is correct
  - [x] Test `OutboxPolicyV1.retention_by_env["prod"].sent_retention_days == 14`
  - [x] Place reusable fixtures in `tests/unit/contracts/conftest.py` (not in the test file itself)

- [x] Task 11: Verify quality gates (AC: #6)
  - [x] Run `uv run ruff check src/aiops_triage_pipeline/contracts/` — zero errors
  - [x] Run `uv run pytest tests/unit/contracts/test_policy_models.py` — all tests pass

## Dev Notes

### PREREQUISITE: Story 1.2 MUST be complete first

Story 1.3 builds on the following outputs of Story 1.2:
- `contracts/` package has all 5 event contracts (`GateInputV1`, `ActionDecisionV1`, `CaseHeaderEventV1`, `TriageExcerptV1`, `DiagnosisReportV1`) + enums implemented
- `contracts/__init__.py` exports all event contracts and shared enums
- Python 3.13 + `uv` environment is working and `pydantic==2.12.5` is installed

**DO NOT implement Story 1.3 unless Story 1.2 is done and `uv run pytest tests/unit/contracts/` passes.**

### Pydantic v2 Frozen Model Pattern (SAME AS STORY 1.2)

```python
from pydantic import BaseModel
from typing import Literal

class ExamplePolicyV1(BaseModel, frozen=True):
    schema_version: Literal["v1"] = "v1"
    some_field: str
    optional_field: str | None = None
```

**Same critical patterns as Story 1.2 apply:**
- `frozen=True` on class (not `model_config`)
- `Literal["v1"] = "v1"` for schema_version
- `str | None` for optional strings (not `Optional[str]`)
- `tuple[T, ...]` for immutable sequences (not `list[T]`)
- Datetime: `datetime` with UTC-aware where needed

### Import Boundary Rules (CRITICAL — same as Story 1.2)

`contracts/` is a **LEAF package**:
- ✅ `from pydantic import BaseModel, ConfigDict`
- ✅ `from typing import Literal`
- ✅ `from datetime import datetime`
- ✅ stdlib only
- ❌ **NO** `from aiops_triage_pipeline.*` imports of any kind
- ❌ **NO** imports from `config/`, `models/`, `errors/`, `pipeline/`, etc.

**This is strictly enforced in code review.**

### `contracts/__init__.py` — ADDITIVE UPDATE

After Story 1.2, `contracts/__init__.py` already exports the event contracts. Story 1.3 ADDS to it — it does NOT replace it. The final file should export BOTH event contracts (from 1.2) AND policy contracts (from 1.3).

```python
"""Frozen contract models for aiops-triage-pipeline."""

# ── Event Contracts (Story 1.2) ─────────────────────────────────────────────
from aiops_triage_pipeline.contracts.enums import (
    Action, CriticalityTier, DiagnosisConfidence, Environment, EvidenceStatus,
)
from aiops_triage_pipeline.contracts.action_decision import ActionDecisionV1
from aiops_triage_pipeline.contracts.case_header_event import CaseHeaderEventV1
from aiops_triage_pipeline.contracts.diagnosis_report import DiagnosisReportV1, EvidencePack
from aiops_triage_pipeline.contracts.gate_input import Finding, GateInputV1
from aiops_triage_pipeline.contracts.triage_excerpt import TriageExcerptV1

# ── Policy Contracts (Story 1.3) ─────────────────────────────────────────────
from aiops_triage_pipeline.contracts.rulebook import (
    GateEffect, GateSpec, RulebookCaps, RulebookDefaults, RulebookV1,
)
from aiops_triage_pipeline.contracts.peak_policy import PeakPolicyV1, PeakThresholdPolicy
from aiops_triage_pipeline.contracts.prometheus_metrics import PrometheusMetricsContractV1
from aiops_triage_pipeline.contracts.redis_ttl_policy import RedisTtlPolicyV1, RedisTtlsByEnv
from aiops_triage_pipeline.contracts.outbox_policy import OutboxPolicyV1, OutboxRetentionPolicy
from aiops_triage_pipeline.contracts.sn_linkage import ServiceNowLinkageContractV1
from aiops_triage_pipeline.contracts.local_dev import LocalDevContractV1, LocalDevIntegrationModes
from aiops_triage_pipeline.contracts.topology_registry import TopologyRegistryLoaderRulesV1

__all__ = [
    # Enums
    "Action", "CriticalityTier", "DiagnosisConfidence", "Environment", "EvidenceStatus",
    # Event contracts (Story 1.2)
    "ActionDecisionV1", "CaseHeaderEventV1", "DiagnosisReportV1", "EvidencePack",
    "Finding", "GateInputV1", "TriageExcerptV1",
    # Policy contracts (Story 1.3)
    "GateEffect", "GateSpec", "RulebookCaps", "RulebookDefaults", "RulebookV1",
    "PeakPolicyV1", "PeakThresholdPolicy",
    "PrometheusMetricsContractV1",
    "RedisTtlPolicyV1", "RedisTtlsByEnv",
    "OutboxPolicyV1", "OutboxRetentionPolicy",
    "ServiceNowLinkageContractV1",
    "LocalDevContractV1", "LocalDevIntegrationModes",
    "TopologyRegistryLoaderRulesV1",
]
```

### Contract 1: RulebookV1 (`contracts/rulebook.py`)

**Source authority:** `_bmad/input/feed-pack/rulebook-v1.yaml` — read this file for the canonical gate definitions.

**Purpose:** Deterministic safety guardrails for AG0–AG6 gate evaluation (Stage 6). Loaded at startup via `model_validate(yaml_dict)`. Provides env caps, tier caps, and gate evaluation specs.

**Key consumers:** `pipeline/stages/gating.py` (Story 5.1), `pipeline/stages/dispatch.py` (Story 5.7)

**Policy version stamp field:** `rulebook_version = rulebook.rulebook_id` — written into `triage.json` CaseFiles (FR60).

**GateCheck uses `extra="allow"` — gate checks have type-specific fields that vary:**
```python
from pydantic import BaseModel, ConfigDict
from typing import Literal

class RulebookDefaults(BaseModel, frozen=True):
    missing_series_policy: str       # "UNKNOWN_NOT_ZERO"
    required_evidence_policy: str    # "PRESENT_ONLY"
    missing_confidence_policy: str   # "DOWNGRADE"
    missing_sustained_policy: str    # "DOWNGRADE"

class RulebookCaps(BaseModel, frozen=True):
    max_action_by_env: dict[str, str]           # {"local": "OBSERVE", "dev": "OBSERVE", ...}
    max_action_by_tier_in_prod: dict[str, str]  # {"TIER_0": "PAGE", "TIER_1": "TICKET", ...}
    paging_denied_topic_roles: tuple[str, ...]  # ("SOURCE_TOPIC",)

class GateEffect(BaseModel, frozen=True):
    cap_action_to: str | None = None
    set_reason_codes: tuple[str, ...] = ()
    set_reason_text: tuple[str, ...] = ()
    confidence_floor: float | None = None
    force_postmortem_mode: str | None = None
    set_postmortem_required: bool | None = None
    set_postmortem_reason_codes: tuple[str, ...] = ()

class GateEffects(BaseModel, frozen=True):
    on_fail: GateEffect | None = None
    on_cap_applied: GateEffect | None = None
    on_duplicate: GateEffect | None = None
    on_store_error: GateEffect | None = None
    on_pass: GateEffect | None = None

class GateCheck(BaseModel):
    # extra="allow" because type-specific fields vary by gate type
    model_config = ConfigDict(frozen=True, extra="allow")
    check_id: str
    type: str

class GateSpec(BaseModel):
    # extra="allow" to handle polymorphic applies_when (str or dict)
    model_config = ConfigDict(frozen=True, extra="allow")
    id: str
    name: str
    intent: str
    effect: GateEffects
    checks: tuple[GateCheck, ...] = ()

class RulebookV1(BaseModel, frozen=True):
    schema_version: Literal["v1"] = "v1"
    rulebook_id: str                    # "rulebook.v1" — used as policy version stamp
    version: int                        # 1
    evaluation_interval_minutes: int    # 5
    sustained_intervals_required: int   # 5
    defaults: RulebookDefaults
    caps: RulebookCaps
    gates: tuple[GateSpec, ...]
```

**Updated `config/policies/rulebook-v1.yaml`:** Copy the full structure from `_bmad/input/feed-pack/rulebook-v1.yaml` but ensure the root-level `schema_version: "v1"` field is present. The feed-pack file uses `version: 1` (int) — the model maps this to `version: int`, while `schema_version: Literal["v1"]` is added by the model default.

**YAML loading pattern** (for reference — actual loading happens in Story 1.4's `config/settings.py`):
```python
import yaml
from pathlib import Path
rulebook_dict = yaml.safe_load(Path("config/policies/rulebook-v1.yaml").read_text())
rulebook = RulebookV1.model_validate(rulebook_dict)
```

### Contract 2: PeakPolicyV1 (`contracts/peak_policy.py`)

**Purpose:** System-wide defaults for peak/near-peak classification against historical baselines. Used by `pipeline/stages/peak.py` (Story 2.3). Per-stream peak window policy overrides live in the topology registry.

**Key consumers:** `pipeline/stages/peak.py` (Story 2.3), `cache/peak_cache.py` (Story 2.6)

**Policy version stamp field:** `peak_policy_version = peak_policy.schema_version`

```python
from pydantic import BaseModel
from typing import Literal

class PeakThresholdPolicy(BaseModel, frozen=True):
    peak_percentile: int = 90      # p90 for peak classification
    near_peak_percentile: int = 95  # p95 for near-peak classification
    bucket_minutes: int = 15        # Time bucket for aggregation
    min_baseline_windows: int = 4   # Min windows to compute reliable baseline

class PeakPolicyV1(BaseModel, frozen=True):
    schema_version: Literal["v1"] = "v1"
    metric: str                    # Canonical metric name for peak detection
    timezone: str                  # "America/Toronto"
    recompute_frequency: str       # "weekly"
    defaults: PeakThresholdPolicy
```

**Updated `config/policies/peak-policy-v1.yaml`:**
```yaml
schema_version: "v1"
metric: "kafka_server_brokertopicmetrics_messagesinpersec"
timezone: "America/Toronto"
recompute_frequency: "weekly"
defaults:
  peak_percentile: 90
  near_peak_percentile: 95
  bucket_minutes: 15
  min_baseline_windows: 4
```

### Contract 3: PrometheusMetricsContractV1 (`contracts/prometheus_metrics.py`)

**Source authority:** `_bmad/input/feed-pack/prometheus-metrics-contract-v1.yaml` — read this file, it's fully specified. **Copy it verbatim** to `config/policies/prometheus-metrics-contract-v1.yaml`.

**Purpose:** Canonical metric names, identity labels, and alias resolution for Prometheus queries. Used by `integrations/prometheus.py` (Story 2.1) to normalize metric names.

**Key consumers:** `pipeline/stages/evidence.py` (Story 2.1), `integrations/prometheus.py`

**Policy version stamp field:** `prometheus_metrics_contract_version = contract.version` (e.g., `"v1"`)

**CRITICAL:** `metrics` is a `dict[str, MetricDefinition]` where keys are logical names (e.g., `"consumer_group_lag"`) and values are `MetricDefinition` models. The pipeline uses the canonical name for Prometheus queries and checks aliases for typo-tolerance.

```python
from pydantic import BaseModel
from typing import Literal

class MetricIdentityConfig(BaseModel, frozen=True):
    cluster_id_rule: str                        # "cluster_id := cluster_name (exact string; no transforms)"
    topic_identity_labels: tuple[str, ...]      # ("env", "cluster_name", "topic")
    lag_identity_labels: tuple[str, ...]        # ("env", "cluster_name", "group", "topic")
    ignore_labels_for_identity: tuple[str, ...] # ("instance", "job", "nodes_group", ...)

class MetricDefinition(BaseModel, frozen=True):
    canonical: str              # Exact Prometheus metric name to query
    role: str                   # Human description of what the metric measures
    aliases: tuple[str, ...] = ()  # Tolerated typo variants — check these if canonical not found

class TruthfulnessConfig(BaseModel, frozen=True):
    missing_series: dict[str, str]  # {"rule": "Missing series must map to EvidenceStatus=UNKNOWN..."}
    partition: dict[str, str]       # {"rule": "partition is aggregation-only; never identity."}

class PrometheusMetricsContractV1(BaseModel, frozen=True):
    schema_version: Literal["v1"] = "v1"
    version: str                               # "v1" from YAML (redundant with schema_version but present)
    date: str                                  # "2026-02-22"
    status: str                                # "FROZEN"
    identity: MetricIdentityConfig
    metrics: dict[str, MetricDefinition]       # logical_name → MetricDefinition
    truthfulness: TruthfulnessConfig
    notes: tuple[str, ...] = ()
```

**Note on `version` field:** The YAML has `version: v1` (string). The model has both `schema_version: Literal["v1"]` (standard) AND `version: str` to capture the YAML's `version` field. Both will be `"v1"`.

### Contract 4: RedisTtlPolicyV1 (`contracts/redis_ttl_policy.py`)

**Purpose:** Environment-specific TTLs for Redis caching of evidence windows, peak profiles, and action deduplication. Used by `cache/` module (Stories 2.6, 5.5).

**FR7 requirement:** "cache evidence windows, peak profiles, and per-interval findings in Redis with environment-specific TTLs per redis-ttl-policy-v1"

**Key consumers:** `cache/evidence_window.py` (Story 2.6), `cache/peak_cache.py` (Story 2.6), `cache/dedupe.py` (Story 5.5)

```python
from pydantic import BaseModel
from typing import Literal

class RedisTtlsByEnv(BaseModel, frozen=True):
    evidence_window_seconds: int    # TTL for evidence window snapshots
    peak_profile_seconds: int       # TTL for peak baseline profiles
    dedupe_seconds: int             # TTL for action deduplication fingerprints

class RedisTtlPolicyV1(BaseModel, frozen=True):
    schema_version: Literal["v1"] = "v1"
    ttls_by_env: dict[str, RedisTtlsByEnv]  # keys: "local", "dev", "uat", "prod"
```

**Updated `config/policies/redis-ttl-policy-v1.yaml`:**
```yaml
schema_version: "v1"
ttls_by_env:
  local:
    evidence_window_seconds: 600      # 10 min — fast iteration
    peak_profile_seconds: 3600        # 1 hour
    dedupe_seconds: 300               # 5 min
  dev:
    evidence_window_seconds: 900      # 15 min
    peak_profile_seconds: 7200        # 2 hours
    dedupe_seconds: 600               # 10 min
  uat:
    evidence_window_seconds: 1800     # 30 min
    peak_profile_seconds: 14400       # 4 hours
    dedupe_seconds: 900               # 15 min
  prod:
    evidence_window_seconds: 3600     # 1 hour
    peak_profile_seconds: 86400       # 24 hours
    dedupe_seconds: 1800              # 30 min
```

### Contract 5: OutboxPolicyV1 (`contracts/outbox_policy.py`)

**Purpose:** Retention policy for outbox records by state and environment. Enforced by `outbox/publisher.py` (Story 4.7).

**FR26 requirement:** "SENT (14d prod), DEAD (90d prod), PENDING/READY/RETRY until resolved"

**Key consumers:** `outbox/state_machine.py` (Story 4.4), `outbox/publisher.py` (Story 4.7)

```python
from pydantic import BaseModel
from typing import Literal

class OutboxRetentionPolicy(BaseModel, frozen=True):
    sent_retention_days: int        # Retain SENT records for N days (audit window)
    dead_retention_days: int        # Retain DEAD records for N days (forensics)
    max_retry_attempts: int = 3     # Max RETRY attempts before → DEAD

class OutboxPolicyV1(BaseModel, frozen=True):
    schema_version: Literal["v1"] = "v1"
    retention_by_env: dict[str, OutboxRetentionPolicy]  # keys: "local", "dev", "uat", "prod"
```

**Updated `config/policies/outbox-policy-v1.yaml`:**
```yaml
schema_version: "v1"
retention_by_env:
  local:
    sent_retention_days: 1
    dead_retention_days: 7
    max_retry_attempts: 3
  dev:
    sent_retention_days: 3
    dead_retention_days: 14
    max_retry_attempts: 3
  uat:
    sent_retention_days: 7
    dead_retention_days: 30
    max_retry_attempts: 5
  prod:
    sent_retention_days: 14     # FR26: SENT 14d prod
    dead_retention_days: 90     # FR26: DEAD 90d prod
    max_retry_attempts: 5
```

### Contract 6: ServiceNowLinkageContractV1 (`contracts/sn_linkage.py`)

**Purpose:** Phase 1B contract for ServiceNow tiered incident correlation. **Minimal for Phase 1A** — the model is defined now but the implementation of SN linkage is Story 8.1. This contract is loaded at startup to configure the SN integration adapter.

**Key consumers:** `integrations/servicenow.py` (Story 8.x — Phase 1B)

**Phase 1A behavior:** `enabled: false` — SN integration runs in LOG mode regardless of other settings.

```python
from pydantic import BaseModel
from typing import Literal

class ServiceNowLinkageContractV1(BaseModel, frozen=True):
    schema_version: Literal["v1"] = "v1"
    enabled: bool = False                            # Phase 1A: always False
    max_correlation_window_days: int = 7            # Search window for SN incident correlation
    correlation_strategy: tuple[str, ...] = ()      # Tiered search strategy names (Phase 1B)
    mi_creation_allowed: bool = False               # FR67b: MI creation NEVER allowed by automation
```

**New `config/policies/servicenow-linkage-contract-v1.yaml`:**
```yaml
schema_version: "v1"
enabled: false
max_correlation_window_days: 7
correlation_strategy: []
mi_creation_allowed: false    # FR67b: MI-1 posture — never allow automated MI creation
```

### Contract 7: LocalDevContractV1 (`contracts/local_dev.py`)

**Purpose:** Specifies integration modes for local development environment. Consumed at startup by `config/settings.py` (Story 1.4) to configure integration adapters with OFF/LOG/MOCK/LIVE modes.

**Key consumers:** `config/settings.py` (Story 1.4), `integrations/base.py` (all integration adapters)

**Integration modes:** `OFF` (no calls), `LOG` (log would-call), `MOCK` (synthetic response), `LIVE` (real external call)

```python
from pydantic import BaseModel
from typing import Literal

class LocalDevIntegrationModes(BaseModel, frozen=True):
    prometheus: str = "MOCK"      # MOCK — use harness data, not real Prometheus
    kafka_consumer: str = "MOCK"  # MOCK — harness sends synthetic events
    kafka_producer: str = "MOCK"  # MOCK — capture Kafka publishes without real broker
    pagerduty: str = "LOG"        # LOG — never page in local dev
    slack: str = "LOG"            # LOG — never send Slack messages
    servicenow: str = "OFF"       # OFF — no SN calls in local dev
    llm: str = "MOCK"             # MOCK — use stub LLM responses (deterministic fallback)
    redis: str = "LIVE"           # LIVE — use docker-compose Redis
    postgres: str = "LIVE"        # LIVE — use docker-compose Postgres

class LocalDevContractV1(BaseModel, frozen=True):
    schema_version: Literal["v1"] = "v1"
    use_testcontainers: bool = False  # False — local dev uses docker-compose, not testcontainers
    integration_modes: LocalDevIntegrationModes
```

**New `config/policies/local-dev-contract-v1.yaml`:**
```yaml
schema_version: "v1"
use_testcontainers: false
integration_modes:
  prometheus: "MOCK"
  kafka_consumer: "MOCK"
  kafka_producer: "MOCK"
  pagerduty: "LOG"
  slack: "LOG"
  servicenow: "OFF"
  llm: "MOCK"
  redis: "LIVE"
  postgres: "LIVE"
```

### Contract 8: TopologyRegistryLoaderRulesV1 (`contracts/topology_registry.py`)

**Purpose:** Rules governing how the topology registry loader reads and validates the `_bmad/input/feed-pack/topology-registry*.yaml` files. Used by `registry/loader.py` (Story 3.1).

**Source data formats:** Two YAML formats exist in the feed-pack:
- v1: `topology-registry.yaml` — simple stream/topic index format
- v2: `topology-registry.instances-v2.ownership-v1.clusters.yaml` — instances-based with routing

**Key consumers:** `registry/loader.py` (Story 3.1), `registry/resolver.py` (Story 3.2)

```python
from pydantic import BaseModel
from typing import Literal

class TopologyRegistryLoaderRulesV1(BaseModel, frozen=True):
    schema_version: Literal["v1"] = "v1"
    supported_registry_versions: tuple[int, ...] = (1, 2)  # v1 and v2 formats
    prefer_v2_format: bool = True           # Use v2 if available, fall back to v1
    routing_key_required: bool = True       # All topics must have a routing_key resolved
    fail_on_unknown_topic_role: bool = False  # Unknown roles degrade gracefully (no hard fail)
    unknown_routing_key_fallback: str = "OWN::Streaming::KafkaPlatform::Ops"  # Last-resort fallback
    cluster_id_transform: str = "NONE"      # "cluster_id := cluster_name (exact string; no transforms)"
```

**New `config/policies/topology-registry-loader-rules-v1.yaml`:**
```yaml
schema_version: "v1"
supported_registry_versions: [1, 2]
prefer_v2_format: true
routing_key_required: true
fail_on_unknown_topic_role: false
unknown_routing_key_fallback: "OWN::Streaming::KafkaPlatform::Ops"
cluster_id_transform: "NONE"
```

### Unit Test Requirements (`tests/unit/contracts/test_policy_models.py`)

**Test file structure:** Mirror the Story 1.2 `test_frozen_models.py` style.

```python
import pytest
from pydantic import ValidationError
from aiops_triage_pipeline.contracts import (
    RulebookV1, RulebookDefaults, RulebookCaps, GateSpec, GateEffect,
    PeakPolicyV1, PeakThresholdPolicy,
    PrometheusMetricsContractV1,
    RedisTtlPolicyV1, RedisTtlsByEnv,
    OutboxPolicyV1, OutboxRetentionPolicy,
    ServiceNowLinkageContractV1,
    LocalDevContractV1, LocalDevIntegrationModes,
    TopologyRegistryLoaderRulesV1,
)

# ── Immutability tests (one per contract) ────────────────────────────────────

def test_rulebook_is_frozen(minimal_rulebook: RulebookV1) -> None:
    with pytest.raises(ValidationError):
        minimal_rulebook.version = 2  # type: ignore[misc]

def test_peak_policy_is_frozen(minimal_peak_policy: PeakPolicyV1) -> None:
    with pytest.raises(ValidationError):
        minimal_peak_policy.timezone = "UTC"  # type: ignore[misc]

# ... (repeat pattern for all 8 contracts)

# ── Round-trip tests ─────────────────────────────────────────────────────────

def test_rulebook_round_trip(minimal_rulebook: RulebookV1) -> None:
    json_str = minimal_rulebook.model_dump_json()
    reconstructed = RulebookV1.model_validate_json(json_str)
    assert minimal_rulebook == reconstructed

# ... (repeat for all 8 contracts)

# ── Schema version tests ─────────────────────────────────────────────────────

def test_all_policy_contracts_have_schema_version_v1(
    minimal_rulebook: RulebookV1,
    minimal_peak_policy: PeakPolicyV1,
    # ... inject all 8 contracts via conftest fixtures
) -> None:
    contracts = [minimal_rulebook, minimal_peak_policy, ...]
    for contract in contracts:
        assert contract.schema_version == "v1"

# ── Semantic field tests ─────────────────────────────────────────────────────

def test_rulebook_caps_paging_denied_roles(minimal_rulebook: RulebookV1) -> None:
    assert "SOURCE_TOPIC" in minimal_rulebook.caps.paging_denied_topic_roles

def test_redis_ttl_prod_dedupe_accessible(minimal_redis_ttl: RedisTtlPolicyV1) -> None:
    assert minimal_redis_ttl.ttls_by_env["prod"].dedupe_seconds > 0

def test_outbox_prod_retention(minimal_outbox_policy: OutboxPolicyV1) -> None:
    assert minimal_outbox_policy.retention_by_env["prod"].sent_retention_days == 14
    assert minimal_outbox_policy.retention_by_env["prod"].dead_retention_days == 90

def test_sn_mi_creation_not_allowed(minimal_sn_linkage: ServiceNowLinkageContractV1) -> None:
    # FR67b: MI-1 posture — automated MI creation must never be allowed
    assert minimal_sn_linkage.mi_creation_allowed is False

def test_rulebook_model_validate_from_dict() -> None:
    # Simulate what happens when loading from YAML: model_validate(yaml_dict)
    data = {
        "rulebook_id": "rulebook.v1",
        "version": 1,
        "evaluation_interval_minutes": 5,
        "sustained_intervals_required": 5,
        "defaults": {
            "missing_series_policy": "UNKNOWN_NOT_ZERO",
            "required_evidence_policy": "PRESENT_ONLY",
            "missing_confidence_policy": "DOWNGRADE",
            "missing_sustained_policy": "DOWNGRADE",
        },
        "caps": {
            "max_action_by_env": {"local": "OBSERVE", "dev": "OBSERVE", "prod": "PAGE"},
            "max_action_by_tier_in_prod": {"TIER_0": "PAGE", "TIER_1": "TICKET"},
            "paging_denied_topic_roles": ["SOURCE_TOPIC"],
        },
        "gates": [],
    }
    rulebook = RulebookV1.model_validate(data)
    assert rulebook.rulebook_id == "rulebook.v1"
    assert rulebook.evaluation_interval_minutes == 5
```

**Fixtures in `tests/unit/contracts/conftest.py`** (NOT in the test file):
```python
import pytest
from aiops_triage_pipeline.contracts import (
    RulebookV1, RulebookDefaults, RulebookCaps, GateEffects,
    PeakPolicyV1, PeakThresholdPolicy,
    PrometheusMetricsContractV1,
    RedisTtlPolicyV1, RedisTtlsByEnv,
    OutboxPolicyV1, OutboxRetentionPolicy,
    ServiceNowLinkageContractV1,
    LocalDevContractV1, LocalDevIntegrationModes,
    TopologyRegistryLoaderRulesV1,
)

@pytest.fixture
def minimal_rulebook() -> RulebookV1:
    return RulebookV1(
        rulebook_id="rulebook.v1",
        version=1,
        evaluation_interval_minutes=5,
        sustained_intervals_required=5,
        defaults=RulebookDefaults(
            missing_series_policy="UNKNOWN_NOT_ZERO",
            required_evidence_policy="PRESENT_ONLY",
            missing_confidence_policy="DOWNGRADE",
            missing_sustained_policy="DOWNGRADE",
        ),
        caps=RulebookCaps(
            max_action_by_env={"local": "OBSERVE", "dev": "OBSERVE", "prod": "PAGE"},
            max_action_by_tier_in_prod={"TIER_0": "PAGE", "TIER_1": "TICKET", "TIER_2": "NOTIFY"},
            paging_denied_topic_roles=("SOURCE_TOPIC",),
        ),
        gates=(),
    )

@pytest.fixture
def minimal_redis_ttl() -> RedisTtlPolicyV1:
    return RedisTtlPolicyV1(
        ttls_by_env={
            "prod": RedisTtlsByEnv(
                evidence_window_seconds=3600,
                peak_profile_seconds=86400,
                dedupe_seconds=1800,
            ),
        }
    )

@pytest.fixture
def minimal_outbox_policy() -> OutboxPolicyV1:
    return OutboxPolicyV1(
        retention_by_env={
            "prod": OutboxRetentionPolicy(sent_retention_days=14, dead_retention_days=90),
        }
    )

# ... add fixtures for the remaining contracts
```

### Project Structure Notes

**Files to create in Story 1.3:**
```
src/aiops_triage_pipeline/contracts/
├── rulebook.py               # RulebookV1 (+ nested: RulebookDefaults, RulebookCaps, GateSpec, GateCheck, GateEffect, GateEffects)
├── peak_policy.py            # PeakPolicyV1 (+ PeakThresholdPolicy)
├── prometheus_metrics.py     # PrometheusMetricsContractV1 (+ MetricIdentityConfig, MetricDefinition, TruthfulnessConfig)
├── redis_ttl_policy.py       # RedisTtlPolicyV1 (+ RedisTtlsByEnv)
├── outbox_policy.py          # OutboxPolicyV1 (+ OutboxRetentionPolicy)
├── sn_linkage.py             # ServiceNowLinkageContractV1
├── local_dev.py              # LocalDevContractV1 (+ LocalDevIntegrationModes)
└── topology_registry.py      # TopologyRegistryLoaderRulesV1

config/policies/
├── rulebook-v1.yaml          # UPDATE: replace stub with real values (copy from feed-pack)
├── peak-policy-v1.yaml       # UPDATE: replace stub with values from Dev Notes
├── prometheus-metrics-contract-v1.yaml  # UPDATE: copy from _bmad/input/feed-pack/
├── redis-ttl-policy-v1.yaml  # UPDATE: replace stub with TTL values from Dev Notes
├── outbox-policy-v1.yaml     # UPDATE: replace stub with retention values from Dev Notes
├── servicenow-linkage-contract-v1.yaml  # CREATE: stub values from Dev Notes
├── local-dev-contract-v1.yaml           # CREATE: integration modes from Dev Notes
└── topology-registry-loader-rules-v1.yaml  # CREATE: loader rules from Dev Notes

tests/unit/contracts/
├── conftest.py               # ADD: policy contract fixtures (story 1.2 may have created this already)
└── test_policy_models.py     # CREATE: 8 contract tests
```

**Alignment with architecture:** All 8 contract files match the `contracts/` directory structure from `artifact/planning-artifacts/architecture.md#Complete Project Directory Structure`. No regressions on Story 1.2 event contract files.

**Story 1.2's `contracts/__init__.py`:** This story EXTENDS it, not replaces it. Read the file first, then add the policy contract imports below the existing event contract imports.

**`tests/unit/contracts/conftest.py`:** Story 1.2 may have created this file with event contract fixtures. Story 1.3 ADDS policy contract fixtures — do not remove existing fixtures.

### Ruff Compliance Notes

Same rules as Story 1.2 apply:
- Python 3.13 native generics: `dict[str, str]`, `tuple[str, ...]` — no `from typing import Dict, Tuple`
- `str | None` not `Optional[str]`
- Line length 100 chars max
- All imports used (no unused imports)
- `from __future__ import annotations` NOT needed

**Special note for `GateCheck` and `GateSpec`:** These use `model_config = ConfigDict(frozen=True, extra="allow")`. Import `ConfigDict` from pydantic:
```python
from pydantic import BaseModel, ConfigDict
```
Make sure `ConfigDict` is not imported but unused elsewhere.

### What Is NOT In Scope for Story 1.3

- **YAML loading at startup** (Story 1.4): `config/settings.py` will load policy YAMLs using `pydantic-settings` or `yaml.safe_load()`. Story 1.3 only defines the models; it does NOT wire up YAML loading.
- **`pyyaml` dependency** (Story 1.4): If YAML loading requires pyyaml, it will be added to `pyproject.toml` in Story 1.4.
- **Gate evaluation logic** (Story 5.1): `pipeline/stages/gating.py` implements AG0–AG6. The `RulebookV1` model here just represents the data structure, not the evaluation logic.
- **Redis TTL enforcement** (Story 2.6): `cache/` modules will consume `RedisTtlPolicyV1`. Not this story.
- **Topology registry loading** (Story 3.1): `registry/loader.py` loads the actual topology YAML files using `TopologyRegistryLoaderRulesV1`. Not this story.
- **SN integration** (Stories 8.x): `ServiceNowLinkageContractV1` is a stub model; integration is Phase 1B.
- **Exposure denylist contract** (Story 1.5): `DenylistV1` is a separate contract in `denylist/loader.py`.
- **`models/` package content**: `EvidenceSnapshot`, `CaseFile`, etc. are NOT contracts — not touched here.

### Previous Story Intelligence (from Story 1.2)

Story 1.2 (Event Contract Models) established these patterns — follow them exactly:
- `frozen=True` on class declaration (not `model_config`)
- `tuple[T, ...]` for immutable sequences (not `list[T]`)
- Enum fields use `str, Enum` mixin (serializes to string values)
- `Optional[T]` → `T | None` for optional fields
- DO NOT use `model_config = {"exclude_none": True}` — null fields appear in JSON
- Test pattern: `model_dump_json()` → `model_validate_json()` → `assert original == reconstructed`
- DO NOT define fixtures inside test files — all fixtures go in `conftest.py`
- `uv run ruff check` must pass BEFORE submitting for review

**New pattern for Story 1.3 (not in Story 1.2):**
- `model_config = ConfigDict(frozen=True, extra="allow")` for polymorphic models (GateCheck, GateSpec)
- `model_validate(dict)` used to load from YAML dictionaries (not just JSON strings)

### Git Context

Recent commits: "Test cases are done", "PRA/Architecture/Epic is completed"

Untracked files include `src/` and `tests/` — all source files from Story 1.1 are untracked (new project). The `contracts/__init__.py` is currently an empty stub (1 line). Story 1.2 will populate it with event contracts before Story 1.3 runs.

### References

- Rulebook v1 authoritative field spec: [Source: `_bmad/input/feed-pack/rulebook-v1.yaml`]
- Prometheus metrics contract field spec: [Source: `_bmad/input/feed-pack/prometheus-metrics-contract-v1.yaml`]
- FR7 (Redis TTL requirement): [Source: `artifact/planning-artifacts/epics.md#FR7`]
- FR26 (Outbox retention requirement): [Source: `artifact/planning-artifacts/epics.md#FR26`]
- FR60 (Policy version stamps in CaseFiles): [Source: `artifact/planning-artifacts/epics.md#FR60`]
- FR67b (MI-1 posture — no automated MI creation): [Source: `artifact/planning-artifacts/epics.md#FR67b`]
- Architecture Decision 2B (Denylist as frozen Pydantic model): [Source: `artifact/planning-artifacts/architecture.md#Category 2`]
- Architecture Decision 3B (Validate at creation via frozen=True): [Source: `artifact/planning-artifacts/architecture.md#Category 3`]
- Import boundary rules: [Source: `artifact/planning-artifacts/architecture.md#Architectural Boundaries`]
- Complete project directory structure: [Source: `artifact/planning-artifacts/architecture.md#Complete Project Directory Structure`]
- Naming conventions: [Source: `artifact/planning-artifacts/architecture.md#Naming Conventions`]
- pydantic-settings version: ~2.13.1 [Source: `pyproject.toml`]
- Pydantic version: 2.12.5 [Source: `pyproject.toml`]
- Tech stack table: [Source: `artifact/planning-artifacts/architecture.md#Technology Stack`]

## Dev Agent Record

### Agent Model Used

claude-opus-4-6

### Debug Log References

### Completion Notes List

- Implemented all 8 frozen Pydantic policy contract models (`frozen=True`) with `schema_version: Literal["v1"] = "v1"` on each.
- `GateCheck` and `GateSpec` use `model_config = ConfigDict(frozen=True, extra="allow")` to handle polymorphic gate type-specific fields from the rulebook YAML.
- Updated 5 existing stub YAML files with real values and created 3 new YAML files for contracts not previously stubbed.
- `prometheus-metrics-contract-v1.yaml` copied verbatim from `_bmad/input/feed-pack/prometheus-metrics-contract-v1.yaml` with `schema_version: "v1"` added.
- `rulebook-v1.yaml` copied from feed-pack with full AG0–AG6 gate definitions and `schema_version: "v1"` added.
- `contracts/__init__.py` updated additively — all Story 1.2 event contract exports preserved; 15 new policy contract names added to `__all__`.
- `tests/unit/contracts/conftest.py` updated additively — all Story 1.2 fixtures preserved; 8 new policy contract fixtures added.
- 24 new unit tests in `test_policy_models.py`: immutability (8), round-trip (8), schema_version (1), semantic field checks (6), YAML-dict loading (1).
- All 72 tests pass (48 Story 1.2 + 24 Story 1.3). Zero ruff errors.
- **Code review fixes (2026-03-01):** 5 MEDIUM issues resolved:
  - `LocalDevIntegrationModes` fields typed as `Literal["OFF","LOG","MOCK","LIVE"]` via `_IntegrationMode` alias — invalid mode strings now fail at validation time.
  - `RedisTtlPolicyV1` and `OutboxPolicyV1` gained `@model_validator(mode="after")` enforcing all 4 required environment keys (`local`, `dev`, `uat`, `prod`).
  - `prometheus-metrics-contract-v1.yaml`: removed copy-paste alias that was identical to canonical for `failed_fetch_requests_per_sec`.
  - `conftest.py` fixtures `minimal_redis_ttl` and `minimal_outbox_policy` updated to include all 4 required environments.
  - 2 new tests added for `GateSpec.applies_when` extra-field round-trip (dict and string forms).
- All 74 tests pass (48 Story 1.2 + 26 Story 1.3). Zero ruff errors.

### File List

**New files created:**
- `src/aiops_triage_pipeline/contracts/rulebook.py`
- `src/aiops_triage_pipeline/contracts/peak_policy.py`
- `src/aiops_triage_pipeline/contracts/prometheus_metrics.py`
- `src/aiops_triage_pipeline/contracts/redis_ttl_policy.py`
- `src/aiops_triage_pipeline/contracts/outbox_policy.py`
- `src/aiops_triage_pipeline/contracts/sn_linkage.py`
- `src/aiops_triage_pipeline/contracts/local_dev.py`
- `src/aiops_triage_pipeline/contracts/topology_registry.py`
- `config/policies/servicenow-linkage-contract-v1.yaml`
- `config/policies/local-dev-contract-v1.yaml`
- `config/policies/topology-registry-loader-rules-v1.yaml`
- `tests/unit/contracts/test_policy_models.py`

**Modified files:**
- `src/aiops_triage_pipeline/contracts/__init__.py`
- `config/policies/rulebook-v1.yaml`
- `config/policies/peak-policy-v1.yaml`
- `config/policies/prometheus-metrics-contract-v1.yaml`
- `config/policies/redis-ttl-policy-v1.yaml`
- `config/policies/outbox-policy-v1.yaml`
- `tests/unit/contracts/conftest.py`
- `artifact/implementation-artifacts/1-3-policy-and-operational-contract-models.md`
- `artifact/implementation-artifacts/sprint-status.yaml`

## Change Log

- 2026-02-28: Implemented Story 1.3 — 8 frozen Pydantic policy contract models, 8 YAML policy files (5 updated, 3 created), additive __init__.py exports, and 24 unit tests. All AC satisfied. (claude-sonnet-4-6)
- 2026-03-01: Code review — fixed 5 MEDIUM issues: `LocalDevIntegrationModes` mode validation, required-env validators on `RedisTtlPolicyV1`/`OutboxPolicyV1`, prometheus YAML alias bug, 2 new `GateSpec.applies_when` round-trip tests. 74/74 tests pass. (claude-sonnet-4-6)
- 2026-03-01: Low-issue fixes — `__init__.py` import section reorganization, `conftest.py` imports from public API, `PeakPolicyV1` timezone IANA validator + `Literal` recompute_frequency, `RulebookV1` gates required-ID validator (AG0–AG6), fixture/test updates. 74/74 tests pass. (claude-sonnet-4-6)
