# Story 1.2: Event Contract Models

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a platform developer,
I want the 5 frozen event contracts defined as immutable Pydantic models,
so that every pipeline stage shares a single source of truth for event data structures and schema validation is enforced at creation and deserialization boundaries.

## Acceptance Criteria

1. **Given** the `contracts/` package exists, **When** the 5 event contracts are implemented as Pydantic `frozen=True` models, **Then** the following event contracts exist in `src/aiops_triage_pipeline/contracts/`:
   - `GateInputV1` in `gate_input.py`
   - `ActionDecisionV1` in `action_decision.py`
   - `CaseHeaderEventV1` in `case_header_event.py`
   - `TriageExcerptV1` in `triage_excerpt.py`
   - `DiagnosisReportV1` in `diagnosis_report.py`

2. **And** attempting to mutate any field on any of the 5 frozen models raises a `pydantic.ValidationError`

3. **And** `model_dump_json()` produces valid JSON and `model_validate_json()` round-trips successfully (reconstructs an identical model) for each of the 5 contracts

4. **And** each contract includes a `schema_version` field set to `"v1"` as a `Literal["v1"]` type

5. **And** shared enum types (`Environment`, `CriticalityTier`, `Action`, `EvidenceStatus`, `DiagnosisConfidence`) are defined in `contracts/enums.py` and use the `str, Enum` mixin for automatic string serialization to JSON

6. **And** `uv run ruff check` passes with zero errors on the implemented contracts

7. **And** unit tests in `tests/unit/contracts/test_frozen_models.py` verify immutability, serialization round-trip, and schema validation for all 5 event contracts

## Tasks / Subtasks

- [x] Task 1: Create shared enum types (AC: #5)
  - [x] Create `src/aiops_triage_pipeline/contracts/enums.py`
  - [x] Implement `Environment(str, Enum)`: LOCAL, DEV, UAT, PROD
  - [x] Implement `CriticalityTier(str, Enum)`: TIER_0, TIER_1, TIER_2, UNKNOWN
  - [x] Implement `Action(str, Enum)`: OBSERVE, NOTIFY, TICKET, PAGE
  - [x] Implement `EvidenceStatus(str, Enum)`: PRESENT, UNKNOWN, ABSENT, STALE
  - [x] Implement `DiagnosisConfidence(str, Enum)`: LOW, MEDIUM, HIGH

- [x] Task 2: Implement `GateInputV1` (AC: #1, #2, #3, #4)
  - [x] Create `src/aiops_triage_pipeline/contracts/gate_input.py`
  - [x] Define `Finding` nested frozen model (see Dev Notes for full field spec)
  - [x] Define `GateInputV1(BaseModel, frozen=True)` with all required and optional fields (see Dev Notes)
  - [x] Set `schema_version: Literal["v1"] = "v1"`
  - [x] Verify field types match the authoritative contract YAML (`_bmad/input/feed-pack/gateinput-v1.contract.yaml`)

- [x] Task 3: Implement `ActionDecisionV1` (AC: #1, #2, #3, #4)
  - [x] Create `src/aiops_triage_pipeline/contracts/action_decision.py`
  - [x] Define `ActionDecisionV1(BaseModel, frozen=True)` with all fields (see Dev Notes)
  - [x] Set `schema_version: Literal["v1"] = "v1"`

- [x] Task 4: Implement `CaseHeaderEventV1` (AC: #1, #2, #3, #4)
  - [x] Create `src/aiops_triage_pipeline/contracts/case_header_event.py`
  - [x] Define `CaseHeaderEventV1(BaseModel, frozen=True)` (Kafka publish contract - small payload, header only)
  - [x] Set `schema_version: Literal["v1"] = "v1"`
  - [x] Use `datetime` with UTC-aware ISO 8601 for `evaluation_ts`

- [x] Task 5: Implement `TriageExcerptV1` (AC: #1, #2, #3, #4)
  - [x] Create `src/aiops_triage_pipeline/contracts/triage_excerpt.py`
  - [x] Define `TriageExcerptV1(BaseModel, frozen=True)` (Kafka publish contract + cold path input)
  - [x] Set `schema_version: Literal["v1"] = "v1"`
  - [x] Include `evidence_status_map: dict[str, EvidenceStatus]` — UNKNOWN-not-zero is critical
  - [x] Include `findings: tuple[Finding, ...]` (frozen tuple, not list, for immutability)

- [x] Task 6: Implement `DiagnosisReportV1` (AC: #1, #2, #3, #4)
  - [x] Create `src/aiops_triage_pipeline/contracts/diagnosis_report.py`
  - [x] Define `EvidencePack` nested frozen model with `facts`, `missing_evidence`, `matched_rules` fields
  - [x] Define `DiagnosisReportV1(BaseModel, frozen=True)` with all fields (see Dev Notes)
  - [x] Set `schema_version: Literal["v1"] = "v1"`
  - [x] Fallback contract: verdict=UNKNOWN, confidence=LOW, reason_codes for LLM_UNAVAILABLE/LLM_TIMEOUT/LLM_ERROR/LLM_STUB scenarios must be expressible

- [x] Task 7: Update `contracts/__init__.py` exports (AC: #1)
  - [x] Replace stub content with explicit `__all__` exports for all 5 contracts + enums
  - [x] Export: `GateInputV1`, `ActionDecisionV1`, `CaseHeaderEventV1`, `TriageExcerptV1`, `DiagnosisReportV1`
  - [x] Export: `Finding`, `EvidencePack`, `Environment`, `CriticalityTier`, `Action`, `EvidenceStatus`, `DiagnosisConfidence`

- [x] Task 8: Create unit tests (AC: #7)
  - [x] Create `tests/unit/contracts/` directory with `__init__.py` if not already present
  - [x] Create `tests/unit/contracts/test_frozen_models.py`
  - [x] For each of the 5 contracts: test immutability (mutation raises `ValidationError`)
  - [x] For each of the 5 contracts: test `model_dump_json()` → `model_validate_json()` round-trip
  - [x] For each of the 5 contracts: test `schema_version` field equals `"v1"`
  - [x] Test enum string serialization: assert `Action.PAGE` serializes to `"PAGE"` in JSON
  - [x] Test `EvidenceStatus.UNKNOWN` in `evidence_status_map` serializes correctly
  - [x] Test `DiagnosisReportV1` fallback construction (verdict=UNKNOWN, confidence=LOW)

- [x] Task 9: Verify quality gates (AC: #6)
  - [x] Run `uv run ruff check src/aiops_triage_pipeline/contracts/` — must pass with zero errors
  - [x] Run `uv run pytest tests/unit/contracts/` — all tests must pass

## Dev Notes

### PREREQUISITE: Story 1.1 must be complete first

Story 1.2 depends on the following outputs of Story 1.1:
- `src/aiops_triage_pipeline/contracts/` package exists with stub `__init__.py`
- `pyproject.toml` contains `pydantic==2.12.5`
- `uv.lock` is present and `pydantic` is resolved
- Python `3.13` environment via `uv` is working

**DO NOT implement Story 1.2 unless Story 1.1 is done and `uv run ruff check` passes.**

### Pydantic v2 Frozen Model Pattern (MUST FOLLOW)

**Architecture Decision 3B:** Validate at creation via `frozen=True`. Re-validate on deserialization from external sources. No redundant mid-pipeline validation.

```python
from pydantic import BaseModel
from typing import Literal

class ExampleContractV1(BaseModel, frozen=True):
    schema_version: Literal["v1"] = "v1"
    some_field: str
    # Optional fields: use Optional[T] = None — NEVER exclude from serialization
    optional_field: str | None = None
```

**Critical patterns:**
- `frozen=True` is set on the model class itself (Pydantic v2 syntax), NOT via `model_config`
- `Literal["v1"] = "v1"` ensures schema_version is always exactly `"v1"` — validated on deserialization
- Enum fields use the `str, Enum` mixin (string values serialize directly without `.value`)
- `Optional[T] = None` for optional fields — **never use `model_config = {"exclude_none": True}`** — null fields must appear in JSON
- For collection fields in a frozen model, use `tuple[T, ...]` instead of `list[T]` (lists are mutable; tuples are hashable and immutable)
- Datetime fields: use `datetime` from stdlib; Pydantic v2 handles ISO 8601 UTC serialization automatically. Always use UTC-aware datetimes.

**Serialization test pattern:**
```python
contract = SomeContractV1(field="value")
json_str = contract.model_dump_json()
reconstructed = SomeContractV1.model_validate_json(json_str)
assert contract == reconstructed
```

### Shared Enum Definitions (`contracts/enums.py`)

All enums use `str, Enum` for automatic JSON serialization as string values:

```python
from enum import Enum

class Environment(str, Enum):
    LOCAL = "local"
    DEV = "dev"
    UAT = "uat"
    PROD = "prod"

class CriticalityTier(str, Enum):
    TIER_0 = "TIER_0"
    TIER_1 = "TIER_1"
    TIER_2 = "TIER_2"
    UNKNOWN = "UNKNOWN"

class Action(str, Enum):
    OBSERVE = "OBSERVE"
    NOTIFY = "NOTIFY"
    TICKET = "TICKET"
    PAGE = "PAGE"

class EvidenceStatus(str, Enum):
    PRESENT = "PRESENT"
    UNKNOWN = "UNKNOWN"  # Missing Prometheus series — NEVER treat as zero
    ABSENT = "ABSENT"
    STALE = "STALE"

class DiagnosisConfidence(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
```

**Environment notes:** The authoritative list is local/dev/uat/prod (not "stage" — `stage` appears in the contract YAML comment but the architecture uses `uat`).

### Contract 1: GateInputV1 (`contracts/gate_input.py`)

**Source authority:** `_bmad/input/feed-pack/gateinput-v1.contract.yaml`

**Purpose:** Deterministic input to Rulebook AG0–AG6 evaluation (Stage 6).

**Usage:** Assembled from evidence + topology + case context. Passed in-memory from Stage 5→6. Never serialized between pipeline stages (Architecture Decision 3A). Written as part of CaseFile `triage.json` (FR17).

```python
class Finding(BaseModel, frozen=True):
    finding_id: str
    name: str
    is_anomalous: bool
    evidence_required: tuple[str, ...]  # Evidence primitives required; drives AG2
    is_primary: bool | None = None      # If True, AG2 uses this finding's requirements preferentially
    severity: str | None = None
    reason_codes: tuple[str, ...] = ()

class GateInputV1(BaseModel, frozen=True):
    schema_version: Literal["v1"] = "v1"
    # Identity
    env: Environment
    cluster_id: str                     # cluster_id := cluster_name (exact string)
    stream_id: str                      # Logical end-to-end pipeline grouping key
    topic: str                          # Topic that triggered the anomaly key
    topic_role: str                     # SOURCE_TOPIC / SHARED_TOPIC / SINK_TOPIC
    anomaly_family: str                 # CONSUMER_LAG / VOLUME_DROP / THROUGHPUT_CONSTRAINED_PROXY
    criticality_tier: CriticalityTier
    # Diagnosis inputs
    proposed_action: Action             # Diagnosis result before gates apply
    diagnosis_confidence: float         # 0.0–1.0; deterministic scalar from diagnosis stage
    sustained: bool                     # True if anomaly sustained for sustained_intervals_required windows
    findings: tuple[Finding, ...]       # Justify diagnosis; declare evidence requirements
    evidence_status_map: dict[str, EvidenceStatus]  # Evidence primitive -> PRESENT/UNKNOWN/ABSENT/STALE
    action_fingerprint: str             # Identity fingerprint (excludes timestamps/metric values)
    # Optional
    consumer_group: str | None = None   # Required for lag-based anomalies; omit otherwise
    partition_count_observed: int | None = None  # For confidence downgrade on partition coverage change
    peak: bool | None = None            # If computed; used for postmortem selector (AG6)
    case_id: str | None = None          # Stable case identifier (for audit)
    decision_basis: dict | None = None  # Optional deterministic linkage
```

**action_fingerprint construction rule:** Include `env/cluster_id/stream_id/topic_role/(topic|group)/anomaly_family/tier`. EXCLUDE timestamps and metric values.

### Contract 2: ActionDecisionV1 (`contracts/action_decision.py`)

**Purpose:** Output of Rulebook gate evaluation (AG0–AG6). Input to Stage 7 (Dispatch). Written to CaseFile `triage.json`.

**Usage authority:** Story 5.1 AC: "ActionDecision.v1 containing: final_action, env_cap_applied, gate_rule_ids, gate_reason_codes, action_fingerprint, postmortem_required, postmortem_mode, postmortem_reason_codes"

```python
class ActionDecisionV1(BaseModel, frozen=True):
    schema_version: Literal["v1"] = "v1"
    final_action: Action                    # Final gated action (monotonically reduced from proposed)
    env_cap_applied: bool                   # True if environment cap reduced the action
    gate_rule_ids: tuple[str, ...]          # IDs of rules that evaluated (for audit)
    gate_reason_codes: tuple[str, ...]      # Reason codes from gate evaluation
    action_fingerprint: str                 # Same fingerprint as GateInputV1 (for dedupe)
    postmortem_required: bool               # True if PM_PEAK_SUSTAINED predicate fired (AG6)
    postmortem_mode: str | None = None      # "SOFT" for Phase 1A when postmortem_required=True
    postmortem_reason_codes: tuple[str, ...] = ()  # Reason codes for postmortem trigger
```

**Gate monotonicity invariant:** `final_action` can only be equal to or lower than `proposed_action` in `GateInputV1`. Gates can reduce but never escalate.

### Contract 3: CaseHeaderEventV1 (`contracts/case_header_event.py`)

**Purpose:** Kafka Kafka event published via durable outbox (FR22). Hot-path consumers use this for routing/paging decisions WITHOUT needing to read object storage (FR24).

**Kafka topic:** `aiops-case-header`

**Constraint:** Payload must be small — header only. No raw telemetry. No evidence details (those are in TriageExcerpt).

```python
from datetime import datetime

class CaseHeaderEventV1(BaseModel, frozen=True):
    schema_version: Literal["v1"] = "v1"
    case_id: str                            # Stable case identifier
    env: Environment
    cluster_id: str
    stream_id: str
    topic: str
    anomaly_family: str                     # CONSUMER_LAG / VOLUME_DROP / THROUGHPUT_CONSTRAINED_PROXY
    criticality_tier: CriticalityTier
    final_action: Action                    # Gated action decision
    routing_key: str                        # Team routing key from topology registry
    evaluation_ts: datetime                 # UTC-aware timestamp of the evaluation cycle
```

**Serialization note:** `datetime` serializes to ISO 8601 UTC string via Pydantic v2 default. Consumers can parse back with `model_validate_json()`.

### Contract 4: TriageExcerptV1 (`contracts/triage_excerpt.py`)

**Purpose:** Kafka event published alongside `CaseHeaderEventV1` via durable outbox (FR22). Also used as input to cold-path LLM diagnosis (FR36). Subject to exposure denylist enforcement before publish (FR25).

**Kafka topic:** `aiops-triage-excerpt`

**CRITICAL:** Exposure denylist (`apply_denylist()` from Story 1.5) MUST be applied to this contract before Kafka serialization. The contract itself is immutable — denylist application creates a new cleaned dict for serialization, not a mutated model.

```python
from datetime import datetime

class TriageExcerptV1(BaseModel, frozen=True):
    schema_version: Literal["v1"] = "v1"
    case_id: str
    env: Environment
    cluster_id: str
    stream_id: str
    topic: str
    anomaly_family: str
    topic_role: str                                     # SOURCE_TOPIC / SHARED_TOPIC / SINK_TOPIC
    criticality_tier: CriticalityTier
    routing_key: str                                    # Team routing key
    sustained: bool
    peak: bool | None = None                            # None if peak computation unavailable
    evidence_status_map: dict[str, EvidenceStatus]      # UNKNOWN propagation is critical
    findings: tuple[Finding, ...]                       # Structured findings (from gate_input)
    triage_timestamp: datetime                          # UTC-aware triage assembly time
```

**UNKNOWN propagation reminder:** `evidence_status_map` entries with `EvidenceStatus.UNKNOWN` mean the Prometheus series was MISSING — NOT that the metric value was zero. This distinction is critical for cold-path diagnosis correctness.

### Contract 5: DiagnosisReportV1 (`contracts/diagnosis_report.py`)

**Purpose:** Output of cold-path LLM diagnosis (FR37). Written to `cases/{case_id}/diagnosis.json`. Also produced by deterministic fallback when LLM is unavailable/errors (FR39).

**Usage:** Produced by `diagnosis/graph.py` (LLM path) and `diagnosis/fallback.py` (deterministic fallback). Validated by `model_validate()` to ensure LLM output is schema-valid (FR40).

```python
class EvidencePack(BaseModel, frozen=True):
    facts: tuple[str, ...]              # Evidence facts cited by LLM
    missing_evidence: tuple[str, ...]   # Evidence IDs/primitives missing (UNKNOWN propagation)
    matched_rules: tuple[str, ...]      # Rulebook/policy rules matched

class DiagnosisReportV1(BaseModel, frozen=True):
    schema_version: Literal["v1"] = "v1"
    case_id: str | None = None                          # None in fallback scenarios
    verdict: str                                        # LLM verdict (or "UNKNOWN" for fallback)
    fault_domain: str | None = None                     # Identified fault domain; None when UNKNOWN
    confidence: DiagnosisConfidence                     # LOW/MEDIUM/HIGH
    evidence_pack: EvidencePack                         # Facts, missing evidence, matched rules
    next_checks: tuple[str, ...] = ()                   # Recommended follow-up checks
    gaps: tuple[str, ...] = ()                          # Evidence gaps identified
    reason_codes: tuple[str, ...] = ()                  # LLM_UNAVAILABLE / LLM_TIMEOUT / LLM_ERROR / LLM_STUB
    triage_hash: str | None = None                      # SHA-256 of triage.json (hash chain, Story 6.2)
```

**Deterministic fallback construction:**
```python
# LLM unavailable
fallback = DiagnosisReportV1(
    verdict="UNKNOWN",
    confidence=DiagnosisConfidence.LOW,
    evidence_pack=EvidencePack(facts=(), missing_evidence=(), matched_rules=()),
    reason_codes=("LLM_UNAVAILABLE",),
)
```
Valid `reason_codes` values: `LLM_UNAVAILABLE`, `LLM_TIMEOUT`, `LLM_ERROR`, `LLM_STUB`, `LLM_SCHEMA_INVALID`

### `contracts/__init__.py` Exports

Replace the Story 1.1 stub with explicit exports:

```python
"""Frozen contract models for aiops-triage-pipeline."""

from aiops_triage_pipeline.contracts.enums import (
    Action,
    CriticalityTier,
    DiagnosisConfidence,
    Environment,
    EvidenceStatus,
)
from aiops_triage_pipeline.contracts.action_decision import ActionDecisionV1
from aiops_triage_pipeline.contracts.case_header_event import CaseHeaderEventV1
from aiops_triage_pipeline.contracts.diagnosis_report import DiagnosisReportV1, EvidencePack
from aiops_triage_pipeline.contracts.gate_input import Finding, GateInputV1
from aiops_triage_pipeline.contracts.triage_excerpt import TriageExcerptV1

__all__ = [
    "Action",
    "ActionDecisionV1",
    "CaseHeaderEventV1",
    "CriticalityTier",
    "DiagnosisConfidence",
    "DiagnosisReportV1",
    "Environment",
    "EvidencePack",
    "EvidenceStatus",
    "Finding",
    "GateInputV1",
    "TriageExcerptV1",
]
```

### Unit Test Requirements (`tests/unit/contracts/test_frozen_models.py`)

```python
import pytest
from pydantic import ValidationError
from aiops_triage_pipeline.contracts import (
    GateInputV1, ActionDecisionV1, CaseHeaderEventV1,
    TriageExcerptV1, DiagnosisReportV1,
    Action, Environment, CriticalityTier, EvidenceStatus,
    DiagnosisConfidence, Finding, EvidencePack,
)

# Immutability test pattern for each contract:
def test_gate_input_is_frozen():
    gate_input = GateInputV1(
        env=Environment.LOCAL,
        cluster_id="cluster-1",
        stream_id="stream-1",
        topic="topic-1",
        topic_role="SOURCE_TOPIC",
        anomaly_family="CONSUMER_LAG",
        criticality_tier=CriticalityTier.TIER_0,
        proposed_action=Action.PAGE,
        diagnosis_confidence=0.85,
        sustained=True,
        findings=(Finding(finding_id="f1", name="lag", is_anomalous=True, evidence_required=("lag_metric",)),),
        evidence_status_map={"lag_metric": EvidenceStatus.PRESENT},
        action_fingerprint="env/cluster-1/stream-1/SOURCE_TOPIC/topic-1/CONSUMER_LAG/TIER_0",
    )
    with pytest.raises(ValidationError):
        gate_input.env = Environment.PROD  # type: ignore[misc]

# Round-trip test pattern for each contract:
def test_gate_input_round_trip():
    gate_input = GateInputV1(...)
    json_str = gate_input.model_dump_json()
    reconstructed = GateInputV1.model_validate_json(json_str)
    assert gate_input == reconstructed

# Schema version test:
def test_gate_input_schema_version():
    gate_input = GateInputV1(...)
    assert gate_input.schema_version == "v1"

# Enum string serialization:
def test_enum_serializes_as_string():
    decision = ActionDecisionV1(
        final_action=Action.PAGE, env_cap_applied=False,
        gate_rule_ids=("AG0",), gate_reason_codes=("PASS",),
        action_fingerprint="fp", postmortem_required=False,
    )
    json_str = decision.model_dump_json()
    assert '"PAGE"' in json_str  # Not '"Action.PAGE"'

# DiagnosisReport fallback:
def test_diagnosis_report_fallback_is_valid():
    fallback = DiagnosisReportV1(
        verdict="UNKNOWN",
        confidence=DiagnosisConfidence.LOW,
        evidence_pack=EvidencePack(facts=(), missing_evidence=(), matched_rules=()),
        reason_codes=("LLM_UNAVAILABLE",),
    )
    assert fallback.verdict == "UNKNOWN"
    json_str = fallback.model_dump_json()
    reconstructed = DiagnosisReportV1.model_validate_json(json_str)
    assert fallback == reconstructed
```

**DO NOT define fixtures inside the test file** — place any reusable fixtures in `tests/unit/contracts/conftest.py`.

### Ruff Compliance Notes

The following must hold for zero ruff errors:
- All imports are used (no unused imports)
- `from __future__ import annotations` is NOT needed in Python 3.13 (PEP 563 is not the default)
- `tuple[str, ...]` and `dict[str, EvidenceStatus]` are valid Python 3.13 native generics — no `from typing import Tuple, Dict`
- `str | None` is valid Python 3.10+ syntax — use this instead of `Optional[str]`
- Line length limit is 100 chars (from Story 1.1 pyproject.toml `[tool.ruff]`)
- Constants and modules must be in correct case per ruff N rules

### Import Boundary Rules (CRITICAL)

`contracts/` is a **LEAF package** — it **imports from nothing in this project**.

| ✅ Allowed | ❌ Forbidden |
|---|---|
| `from enum import Enum` | `from aiops_triage_pipeline.models import ...` |
| `from pydantic import BaseModel` | `from aiops_triage_pipeline.config import ...` |
| `from typing import Literal` | `from aiops_triage_pipeline.errors import ...` |
| `from datetime import datetime` | Any other `aiops_triage_pipeline.*` import |
| Imports from stdlib | |

**This will be enforced in code review for all future stories.**

### Naming Conventions (Applied to This Story)

| Artifact | Convention | Examples |
|---|---|---|
| Contract class names | `PascalCase` + `V1` suffix | `GateInputV1`, `CaseHeaderEventV1` |
| Nested model class names | `PascalCase` | `Finding`, `EvidencePack` |
| Module filenames | `snake_case` | `gate_input.py`, `action_decision.py` |
| Enum class names | `PascalCase` | `Action`, `CriticalityTier` |
| Enum member names | `UPPER_SNAKE_CASE` | `TIER_0`, `CONSUMER_LAG` |
| JSON field names | `snake_case` (Pydantic default) | `schema_version`, `case_id`, `evidence_status_map` |

### What Is NOT In Scope for Story 1.2

- **Policy contracts** (Story 1.3): `RulebookV1`, `PeakPolicyV1`, `RedisTtlPolicyV1`, `OutboxPolicyV1`, `PrometheusMetricsContractV1`, `ServiceNowLinkageContractV1`, `LocalDevContractV1`, `TopologyRegistryLoaderRulesV1`
- **Contract loading from YAML** (Stories 1.3, 1.4): Policy contracts are loaded from YAML files via `pydantic-settings` — not applicable here
- **`models/` package content** (Story 1.1 stubs, subsequent stories): `EvidenceSnapshot`, `CaseFile`, `PeakResult`, etc. are NOT contracts — they are internal mutable models
- **Exposure denylist enforcement** (Story 1.5): `apply_denylist()` is not implemented here
- **SHA-256 hashing** (Story 4.2): `triage_hash` field in `DiagnosisReportV1` will be `None` until Story 6.2
- **Testcontainers**: No Docker required for this story — pure unit tests only

### Project Structure Notes

- **Alignment:** `contracts/` package files established here are the canonical leaf package per Architecture Decision 5A and the import rules table.
- **No detected conflicts:** Story 1.1 creates stub `contracts/__init__.py`; this story replaces that stub with the full implementation. No regression risk.
- **Stub files remain untouched:** `models/`, `pipeline/`, `diagnosis/`, etc. stubs from Story 1.1 are NOT modified — those belong to later stories.
- **Test directory:** `tests/unit/contracts/` may need to be created if Story 1.1 only created `tests/unit/` with subdirectories for other packages. Create `__init__.py` in `tests/unit/contracts/` as needed.

### References

- GateInput.v1 field spec: [Source: `_bmad/input/feed-pack/gateinput-v1.contract.yaml`]
- ActionDecision.v1 fields: [Source: `artifact/planning-artifacts/epics.md#Story 5.1`]
- CaseHeaderEvent + TriageExcerpt usage: [Source: `artifact/planning-artifacts/epics.md#FR22, FR24, Story 4.5`]
- DiagnosisReport fields: [Source: `artifact/planning-artifacts/epics.md#FR37, Story 6.2, Story 6.3`]
- Frozen contract enforcement (Decision 3B): [Source: `artifact/planning-artifacts/architecture.md#Pipeline Communication & Serialization`]
- In-memory passing (Decision 3A): [Source: `artifact/planning-artifacts/architecture.md#Pipeline Communication & Serialization`]
- Kafka serialization (Decision 3C): [Source: `artifact/planning-artifacts/architecture.md#Pipeline Communication & Serialization`]
- Import boundary rules: [Source: `artifact/planning-artifacts/architecture.md#Architectural Boundaries`]
- Naming conventions: [Source: `artifact/planning-artifacts/architecture.md#Naming Conventions`]
- Directory structure: [Source: `artifact/planning-artifacts/architecture.md#Complete Project Directory Structure`]
- UNKNOWN-not-zero evidence semantics: [Source: `_bmad/input/feed-pack/gateinput-v1.contract.yaml#evidence_status_semantics`]
- Enum serialization + null handling: [Source: `artifact/planning-artifacts/architecture.md#Format Patterns`]

## Dev Agent Record

### Agent Model Used

claude-sonnet-4-6

### Debug Log References

- Ruff E501 violations fixed: shortened inline comments in `gate_input.py` (moved to preceding comment line) and split `diagnosis_report.py` docstring to multi-line format
- Test fix: `Environment.PROD` serializes to `"prod"` (lowercase) per enum definition — test corrected from `'"PROD"'` to `'"prod"'`
- Test fix: `test_triage_excerpt_peak_defaults_none` referenced undefined `sample_triage_excerpt` fixture — converted to standalone test with inline datetime

### Completion Notes List

- Implemented all 5 frozen event contract models using Pydantic v2 `frozen=True` pattern
- Created `contracts/enums.py` with 5 shared enums using `str, Enum` mixin for automatic JSON string serialization
- `GateInputV1` and `TriageExcerptV1` share `Finding` nested model (imported from `gate_input.py`)
- `DiagnosisReportV1` includes `EvidencePack` nested model for structured evidence citation
- All contracts verified: immutable, JSON round-trip, `schema_version="v1"`, enum string serialization
- 43 unit tests in `tests/unit/contracts/test_frozen_models.py` + fixtures in `conftest.py`
- `uv run ruff check src/aiops_triage_pipeline/contracts/` → 0 errors
- `uv run pytest tests/unit/contracts/` → 43/43 passed
- `uv run pytest tests/unit/` → 44/44 passed (0 regressions)
- Import boundary rule upheld: `contracts/` imports only stdlib (`enum`, `datetime`, `typing`) and `pydantic`

### File List

- `src/aiops_triage_pipeline/contracts/__init__.py` (modified — replaced stub with full exports)
- `src/aiops_triage_pipeline/contracts/enums.py` (new)
- `src/aiops_triage_pipeline/contracts/gate_input.py` (modified — added AwareDatetime, Field constraints, Literal types, typed dict)
- `src/aiops_triage_pipeline/contracts/action_decision.py` (new)
- `src/aiops_triage_pipeline/contracts/case_header_event.py` (modified — AwareDatetime, Literal anomaly_family)
- `src/aiops_triage_pipeline/contracts/triage_excerpt.py` (modified — AwareDatetime, Literal topic_role/anomaly_family)
- `src/aiops_triage_pipeline/contracts/diagnosis_report.py` (modified — verdict min_length=1 constraint)
- `tests/unit/contracts/conftest.py` (new)
- `tests/unit/contracts/test_frozen_models.py` (modified — ruff fixes, added 6 validation tests)

## Change Log

- 2026-02-28: Implemented Story 1.2 — created 5 frozen event contract models, shared enums, nested models (Finding, EvidencePack), updated contracts/__init__.py exports, created 43 unit tests. All ACs satisfied.
- 2026-02-28: Code review fixes (AI) — enforced UTC-aware datetimes via `AwareDatetime` on `evaluation_ts`/`triage_timestamp`; constrained `diagnosis_confidence` to `0.0–1.0` via `Field(ge, le)`; enforced `verdict` non-empty via `Field(min_length=1)`; constrained `topic_role` and `anomaly_family` to `Literal` types across all contracts; typed `decision_basis` as `dict[str, Any]`; fixed 3 ruff violations in test file; added 6 validation tests. 49/49 tests pass, ruff clean.
