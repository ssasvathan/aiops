# Schema Evolution & Contract Versioning Strategy

> **Audience:** Engineers implementing schema changes, LLM agents assisting with upgrades, and auditors reviewing data compatibility.
>
> **Scope:** All versioned contracts, CaseFile storage, Kafka events, and policy artifacts in the AIOps triage pipeline.

## Core Concepts — Three Separate Versioning Axes

This system has three distinct versioning concepts that must never be conflated:

| Concept | What it tracks | Example | Changes when... |
|---|---|---|---|
| **Schema version** | The structure/shape of a data model | `GateInput v1` → `GateInput v2` | A field is added, removed, renamed, or changes type |
| **Enrichment stage** | Which pipeline component wrote a CaseFile artifact | `triage`, `diagnosis`, `linkage`, `labels` | Never — stages are fixed by pipeline architecture |
| **Policy version** | Which business rules were active at decision time | `rulebook_version: "1.3"` | Rules are updated (new gate thresholds, denylist entries, etc.) |

### Why this distinction matters

A CaseFile written 20 months ago might use:
- Schema version: `CaseFileTriage v1` (the data structure)
- Enrichment stage: `triage` (written by hot-path stage 4)
- Policy versions: `rulebook: 1.2, peak_policy: 1.0, denylist: 1.5` (the rules active at that time)

An auditor replaying this decision needs all three: the correct schema model to deserialize the data, the stage to understand what component produced it, and the policy versions to reproduce the gating decision.

---

## CaseFile Storage Model

### Directory structure per case

Each case gets a directory in object storage. Each enrichment stage writes a separate, immutable file:

```
cases/{case_id}/
    triage.json        ← Hot path (stage 4): evidence + gating inputs + action decision
    diagnosis.json     ← Cold path (stage 9): LLM DiagnosisReport
    linkage.json       ← Cold path (stage 11): SN correlation result (Phase 1B)
    labels.json        ← Human input (Phase 2+): operator annotations
```

### Rules

1. **Each file is written exactly once** by its owning pipeline component. No read-modify-write.
2. **Each file is independently immutable** after write. No overwrites, no in-place edits.
3. **Hash chain:** Each stage's file includes the SHA-256 hash of prior stage files it depends on (e.g., `diagnosis.json` includes the hash of `triage.json`).
4. **A "complete CaseFile"** is the logical aggregate of all files under `cases/{case_id}/`. Not every case will have all files (e.g., no `diagnosis.json` if LLM timed out, no `linkage.json` if action was not PAGE).
5. **The absence of a file is meaningful:** No `diagnosis.json` = LLM did not produce a result for this case. This is explicit and observable.
6. **Schema version is embedded** in every file via the envelope (see below).

### Why separate files per stage (not cumulative snapshots)

- **Write-once is naturally enforced:** Each component writes its own file. No component needs to read another component's file to append to it.
- **No data duplication:** Evidence isn't copied into `diagnosis.json`.
- **Clear provenance:** An auditor can immediately see which stages completed by listing the directory.
- **Failure is explicit:** Missing file = stage didn't complete. No ambiguity.
- **Simpler error handling:** If LLM fails, there's no partial v1.1 — there's simply no `diagnosis.json`.

---

## Schema Envelope Pattern

Every persisted artifact (CaseFile stage files, Kafka events) uses a standard envelope:

```python
from pydantic import BaseModel
from datetime import datetime

class SchemaEnvelope(BaseModel):
    """Standard wrapper for all versioned artifacts.

    The envelope enables version-aware deserialization:
    reading code inspects schema_name + schema_version to select
    the correct Pydantic model for the payload.
    """
    schema_name: str          # e.g., "CaseFileTriage", "GateInput", "TriageExcerpt"
    schema_version: str       # e.g., "v1", "v2" — incremented on breaking changes only
    created_at: datetime      # when this artifact was produced
    producer: str             # component that wrote this (e.g., "hot-path-stage-4", "llm-diagnosis")
    payload: dict             # the version-specific content, validated by the target model
```

### Deserialization with version routing

```python
from typing import TypeVar, Type

T = TypeVar("T", bound=BaseModel)

# Registry maps (schema_name, schema_version) → Pydantic model class
SCHEMA_REGISTRY: dict[tuple[str, str], Type[BaseModel]] = {
    ("CaseFileTriage", "v1"): CaseFileTriageV1,
    ("CaseFileTriage", "v2"): CaseFileTriageV2,  # added when v2 ships
    ("GateInput", "v1"): GateInputV1,
    ("DiagnosisReport", "v1"): DiagnosisReportV1,
    # ... all registered schema versions
}

def deserialize(envelope: SchemaEnvelope) -> BaseModel:
    """Deserialize any versioned artifact using its envelope metadata."""
    key = (envelope.schema_name, envelope.schema_version)
    model_class = SCHEMA_REGISTRY.get(key)
    if model_class is None:
        raise UnknownSchemaVersionError(
            f"No registered model for {envelope.schema_name} {envelope.schema_version}. "
            f"Known versions: {[k for k in SCHEMA_REGISTRY if k[0] == envelope.schema_name]}"
        )
    return model_class.model_validate(envelope.payload)
```

---

## Evolution Strategy by Contract Category

### Category 1: Kafka Event Schemas

**Contracts:** CaseHeaderEvent, TriageExcerpt, GateInput, ActionDecision, DiagnosisReport

**Compatibility window:** Short (Kafka topic retention — days/weeks). All consumers are internal to this pipeline.

**Default strategy: Additive-only (no version bump)**

Most real-world evolution is adding new optional fields:

```python
# Before
class GateInputV1(BaseModel):
    model_config = ConfigDict(frozen=True)
    env: str
    cluster_id: str
    # ... existing fields

# After — additive change, NO version bump needed
class GateInputV1(BaseModel):
    model_config = ConfigDict(frozen=True)
    env: str
    cluster_id: str
    # ... existing fields
    sink_health_status: str | None = None  # NEW — Phase 3, optional
```

Additive-only changes are backward AND forward compatible:
- Old consumers ignore unknown fields (`ConfigDict(extra='ignore')`)
- New consumers handle `None` for the new field when reading old messages

**Breaking change strategy: Dual-publish with migration window**

When additive-only is insufficient (field type change, field removal, semantic change):

1. Create `GateInputV2` model alongside `GateInputV1`
2. Producer publishes **both** v1 and v2 to the same Kafka topic (each wrapped in SchemaEnvelope)
3. Migrate consumers one by one to read v2
4. Once all consumers handle v2, stop publishing v1
5. After Kafka retention expires, v1 messages are gone — remove v1 reader code

**The dual-publish window is short** (bounded by Kafka retention + deployment cycle). This is manageable.

### Category 2: CaseFile Schemas (25-month retention)

**Contracts:** CaseFileTriage, CaseFileDiagnosis, CaseFileLinkage, CaseFileLabels

**Compatibility window:** 25 months (regulatory). This is the hard constraint.

**Strategy: Schema version registry with perpetual read support**

Write path always uses the **current** schema version. Read path supports **all** schema versions that have unexpired CaseFiles in storage.

```
Timeline example:
  Month 0:  Ship with CaseFileTriage v1
  Month 8:  Breaking change → ship CaseFileTriage v2 (write v2, read v1+v2)
  Month 15: Breaking change → ship CaseFileTriage v3 (write v3, read v1+v2+v3)
  Month 25: CaseFiles from Month 0 expire → v1 read support can be removed
  Month 33: CaseFiles from Month 8 expire → v2 read support can be removed
```

**Rules for CaseFile schema evolution:**

1. **CaseFile models are never deleted** from the codebase while unexpired CaseFiles using them exist in storage.
2. **Legacy models live in `src/{package}/schemas/legacy/`** — clearly separated from current models.
3. **The SCHEMA_REGISTRY always includes all versions** within the 25-month window.
4. **Every CaseFile stage file carries its schema version** in the SchemaEnvelope — this is how readers know which model to use.
5. **Additive-only changes are still preferred** — they don't require a version bump and avoid the multi-version read complexity entirely.

### Category 3: Policy Artifacts

**Contracts:** Rulebook, peak-policy, prometheus-metrics-contract, redis-ttl-policy, exposure denylist, diagnosis policy

**Strategy: Already solved by design**

Policy artifacts are versioned independently of their schema:
- `rulebook_version: "1.3"` means the rules changed, not the schema for expressing rules
- CaseFiles stamp which policy versions were active (`rulebook_version`, `peak_policy_version`, etc.)
- For decision replay, you load the exact policy version referenced in the CaseFile

Policy **schema** evolution (rare — the structure of how rules are expressed changes) follows the same additive-only / version-bump strategy as Kafka events. The compatibility window is short because the pipeline loads policies at startup from the current version.

### Category 4: Operational Contracts

**Contracts:** outbox-policy, local-dev-no-external-integrations, topology-registry-loader-rules, SN-linkage-contract

**Strategy: Direct update, no versioned coexistence**

These contracts define operational behavior, not persisted data. When they change, the new version takes effect immediately on deployment. There is no multi-version read problem because no historical data is stored in these schemas.

---

## Safe Migration Procedures

### Procedure A: Additive-only field addition (no version bump)

**Use when:** Adding a new optional field to any contract.

**Steps:**

1. **Add the field** to the Pydantic model with a default value:
   ```python
   new_field: str | None = None  # or appropriate default
   ```
2. **Update producing code** to populate the new field where applicable.
3. **Update consuming code** to handle the new field (with graceful handling of `None` for messages/files that predate the change).
4. **Deploy.** Order doesn't matter — consumers tolerate the field being absent (default value), and the new field is ignored by old consumers (`extra='ignore'`).
5. **No schema version bump.** No registry update. No dual-publish window.

**Verification:**
- [ ] New field has a default value (backward compatible)
- [ ] Consumer code handles `None` / default value for the new field
- [ ] Existing tests still pass without modification
- [ ] New tests cover the new field when present and when absent

### Procedure B: Breaking schema change on a Kafka event

**Use when:** Changing a field type, removing a field, or changing field semantics on CaseHeaderEvent, TriageExcerpt, GateInput, ActionDecision, or DiagnosisReport.

**Steps:**

1. **Create the new model version:**
   ```
   src/{package}/schemas/gate_input_v2.py
   ```
   Keep the v1 model in place.

2. **Register both versions** in SCHEMA_REGISTRY:
   ```python
   ("GateInput", "v1"): GateInputV1,
   ("GateInput", "v2"): GateInputV2,
   ```

3. **Update the producer** to publish both v1 and v2 wrapped in SchemaEnvelope:
   ```python
   # Publish v2 (primary)
   publish(SchemaEnvelope(schema_name="GateInput", schema_version="v2", payload=v2_data))
   # Publish v1 (compatibility — remove after migration)
   publish(SchemaEnvelope(schema_name="GateInput", schema_version="v1", payload=v1_compat_data))
   ```

4. **Migrate consumers** one at a time to prefer v2:
   - Consumer reads the envelope, routes to v2 handler if available, falls back to v1
   - Test each consumer independently

5. **Remove v1 publishing** after all consumers handle v2 and Kafka retention has expired for v1-only messages.

6. **Remove v1 model** after the Kafka retention window has passed (no v1-only messages remain).

**Verification:**
- [ ] Both v1 and v2 models exist and are registered
- [ ] Producer publishes both versions during migration window
- [ ] Each consumer handles both v1 and v2
- [ ] Integration test verifies v1 → v2 consumer migration
- [ ] After migration: only v2 published, v1 reader code retained until retention expires

### Procedure C: Breaking schema change on a CaseFile stage

**Use when:** Changing a field type, removing a field, or changing field semantics on CaseFileTriage, CaseFileDiagnosis, CaseFileLinkage, or CaseFileLabels.

**This is the most sensitive migration. Extra caution required.**

**Steps:**

1. **Create the new model version:**
   ```
   src/{package}/schemas/casefile_triage_v2.py
   ```
   **Do NOT modify or delete the v1 model.**

2. **Move v1 to legacy** (optional, for clarity):
   ```
   src/{package}/schemas/legacy/casefile_triage_v1.py
   ```
   Ensure the import path is updated in SCHEMA_REGISTRY.

3. **Register both versions** in SCHEMA_REGISTRY.

4. **Update the write path** to use v2 only:
   ```python
   # From this point forward, all new CaseFiles use v2
   envelope = SchemaEnvelope(
       schema_name="CaseFileTriage",
       schema_version="v2",
       ...
   )
   ```

5. **Update all read paths** to handle both v1 and v2:
   - The `deserialize()` function uses the envelope's `schema_version` to route
   - Audit/replay tools must handle both versions
   - Cold-path stages that read triage files must handle both

6. **Calculate the v1 retirement date:**
   ```
   v1_retirement_date = v2_deployment_date + 25 months (CaseFile retention)
   ```
   Add a code comment and a tracking item:
   ```python
   # LEGACY: CaseFileTriageV1 — can be removed after {v1_retirement_date}
   # when all v1 CaseFiles have expired per 25-month retention policy.
   ```

7. **After v1_retirement_date:** Verify no v1 CaseFiles remain in storage, then remove v1 model and registry entry.

**Verification:**
- [ ] v1 model is preserved (in legacy/ if moved) and registered
- [ ] v2 model is registered and used by write path
- [ ] All read paths handle both v1 and v2 via envelope routing
- [ ] Audit replay tool tested with both v1 and v2 CaseFiles
- [ ] Hash chain verification works across both versions
- [ ] Retirement date documented in code and tracked
- [ ] Integration test: write v2, read v2, read old v1 (from fixture) — all succeed

### Procedure D: Policy version update (non-schema change)

**Use when:** Updating Rulebook rules, peak thresholds, denylist entries, or other policy content without changing the policy schema structure.

**Steps:**

1. **Increment the policy version** (e.g., `rulebook: "1.3"` → `"1.4"`).
2. **Update the policy artifact** (YAML/JSON file).
3. **Deploy.** Pipeline loads the new policy version at startup.
4. **All new CaseFiles** will stamp the new policy version in their metadata.
5. **No code changes needed** unless the policy schema itself changed (which would be Procedure B or C).

**For decision replay of old CaseFiles:**
- The replay tool reads the `rulebook_version` stamp from the CaseFile
- It loads the referenced policy version from the policy artifact archive
- It re-evaluates the Rulebook with the original evidence + original policy → must produce identical ActionDecision

**This requires:** A policy artifact archive that retains old policy versions for the CaseFile retention window (25 months).

---

## Code Organization

```
src/{package}/
    schemas/
        __init__.py              # Re-exports current versions
        envelope.py              # SchemaEnvelope model + deserialize()
        registry.py              # SCHEMA_REGISTRY mapping

        # Current versions (what the write path uses)
        casefile_triage.py       # CaseFileTriageV1 (or V2 when shipped)
        casefile_diagnosis.py    # CaseFileDiagnosisV1
        casefile_linkage.py      # CaseFileLinkageV1
        casefile_labels.py       # CaseFileLabelsV1
        gate_input.py            # GateInputV1
        action_decision.py       # ActionDecisionV1
        case_header_event.py     # CaseHeaderEventV1
        triage_excerpt.py        # TriageExcerptV1
        diagnosis_report.py      # DiagnosisReportV1

        # Legacy versions (read-only, kept for deserialization)
        legacy/
            __init__.py
            # Models moved here when superseded by a new version
            # Each file has a comment: "Can be removed after {date}"
```

### Naming conventions

- Model classes: `{SchemaName}V{N}` (e.g., `GateInputV1`, `CaseFileTriageV2`)
- Schema name in envelope: PascalCase without version (e.g., `"GateInput"`, `"CaseFileTriage"`)
- Schema version in envelope: `"v1"`, `"v2"` (lowercase v, integer)
- Files: snake_case matching the schema (e.g., `gate_input.py`, `casefile_triage.py`)
- Legacy files: same naming, under `legacy/` directory

---

## Decision Log

| Decision | Choice | Rationale |
|---|---|---|
| CaseFile enrichment naming | Named stage files (triage/diagnosis/linkage/labels) | Avoids confusion with schema versions; clear provenance per stage |
| Schema versioning mechanism | Envelope pattern with version registry | Enables multi-version reads for 25-month CaseFile retention |
| Default evolution strategy | Additive-only (new optional fields, no version bump) | Covers majority of real-world changes without complexity |
| Breaking change strategy (Kafka) | Dual-publish with short migration window | Kafka retention is short; consumers are all internal |
| Breaking change strategy (CaseFile) | Schema registry with perpetual read support for 25 months | Regulatory requirement; old CaseFiles must remain readable |
| Legacy model retention | Keep in `schemas/legacy/` until retention expiry | Explicit retirement dates; never silently removed |
| Policy evolution | Version stamping in CaseFiles + policy archive | Already designed into the system; policies change independently of schemas |

---

## Quick Reference for Future Changes

**"I need to add a new field to GateInput"**
→ Follow Procedure A (additive-only). Add as `Optional[T] = None`. No version bump.

**"I need to change the type of a field in TriageExcerpt"**
→ Follow Procedure B (breaking Kafka change). Create v2, dual-publish, migrate consumers.

**"I need to restructure CaseFileTriage"**
→ Follow Procedure C (breaking CaseFile change). Create v2, keep v1 for 25 months, update all readers.

**"I need to add a new Rulebook gate (AG7)"**
→ Follow Procedure D (policy update). Increment rulebook version, update policy artifact. No schema change unless AG7 requires new GateInput fields (then also Procedure A).

**"I need to add a new CaseFile enrichment stage"**
→ Create a new Pydantic model (e.g., `CaseFileNewStageV1`), register in SCHEMA_REGISTRY, write to a new file under `cases/{case_id}/new_stage.json`. No existing models change.

**"How do I know which legacy models can be removed?"**
→ Check the retirement date comment in each legacy model file. Verify no unexpired CaseFiles using that version exist in object storage. Remove the model and its registry entry.
