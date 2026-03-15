# Design Spec: Developer Onboarding Guide
**Date:** 2026-03-15
**Output file:** `docs/developer-onboarding.md`

---

## Overview

A single Markdown document that onboards new developers to the AIOps Triage Pipeline codebase. The target reader has just cloned the repo and needs to build an accurate mental model of the system before contributing code. The document uses the "Mental Model First" approach: establish concepts and vocabulary before showing code, then progressively add depth.

**Audience:** Developers who will contribute to the codebase.
**Format:** Single Markdown file with embedded Mermaid diagrams and code snippets. File pointers throughout.
**Scope:** Architecture, pipeline stages, runtime modes, data contracts, configuration, and code navigation.
**Non-goals:** Does not replace existing reference docs (contracts.md, runtime-modes.md, etc.) — it links to them.

---

## Section 1 — What Problem Does This Solve?

**Content:** 2–3 paragraphs, no code.

Explains:
- The pain: infrastructure generates continuous telemetry; triaging anomalies manually at scale is slow, inconsistent, and error-prone.
- What the system does: ingests Prometheus metrics, classifies anomaly patterns, assembles a durable case artifact, gates through a deterministic rulebook, and dispatches actions (PagerDuty, Slack, or structured log fallback).
- What it produces: a `CaseFile` (immutable S3 artifact), Kafka events (`CaseHeaderEventV1`, `TriageExcerptV1`), and an `ActionDecisionV1`.

Establishes vocabulary used throughout: *anomaly → triage → case → gate → action*.

---

## Section 2 — How the System Thinks

**Content:** 4 mental models, each 2–3 sentences + one visual aid. No code snippets yet.

### Mental Model 1: The Pipeline Is Sequential and Deterministic
Every anomaly passes through the same numbered stages in order. No stage can skip a previous one or override its output. Given the same inputs and policy versions, the system always produces the same outputs — making decisions auditable and replayable.

### Mental Model 2: Contracts Are Frozen
All data flowing between stages are immutable Pydantic v2 models (`frozen=True`). A stage receives a contract, reads it, and produces a new one — it never mutates what it received. This makes each stage independently testable and prevents subtle bugs from shared mutable state.

### Mental Model 3: Safety Modes Prevent Accidents
Every external call (PagerDuty, Slack, Kafka, ServiceNow, LLM) has an explicit safety mode: `OFF | LOG | MOCK | LIVE`. In `OFF`, the integration is disabled. In `LOG`, it logs the payload but makes no call. In `MOCK`, it returns a canned response. Only `LIVE` makes the real call. Local development defaults to `OFF` or `LOG`.

### Mental Model 4: Write-Once Persistence
CaseFiles are immutable artifacts written to object storage. Each enrichment stage writes exactly one file (`triage.json`, `diagnosis.json`, `linkage.json`). A missing file means that stage did not complete — never that it failed silently. This makes the system's state always observable.

**Diagram:** Mermaid flowchart showing the high-level concept:
```
Prometheus → [Pipeline Stages] → S3 CaseFile
                                → Outbox (Postgres) → Kafka Events
                                → Action Dispatch (PD / Slack)
```

---

## Section 3 — The Pipeline Journey

**Content:** Full Mermaid stage-flow diagram, then a per-stage walkthrough.

### Mermaid Diagram
Full stage flow (Stages 1–9) with hot path vs cold path clearly labelled. Shows the async fork after Stage 7 for the cold path. Shows the Outbox as a separate publication channel.

### Per-Stage Walkthrough
For each hot-path stage: one-sentence description, key entry function with file pointer, and the real function signature from the codebase as a code snippet. Stage numbering and naming follows `docs/runtime-modes.md` and the actual file layout — do not invent stage numbers for gating sub-steps.

Stages covered in order (matching `runtime-modes.md` per-cycle flow):
1. **Evidence** — Prometheus samples are collected separately, then `collect_evidence_stage_output()` processes them into findings. Note: this function is synchronous, not async; Prometheus collection happens upstream in `run_evidence_stage_cycle()` in `scheduler.py`.
2. **Peak** — `collect_peak_stage_output()` in `pipeline/stages/peak.py`
3. **Topology** — `collect_topology_stage_output()` in `pipeline/stages/topology.py`
4. **Gate Inputs** — `collect_gate_inputs_by_scope()` in `pipeline/stages/gating.py`
5. **Gate Decisions** — `evaluate_rulebook_gate_inputs_by_scope()` in `pipeline/stages/gating.py`
6. **CaseFile Assembly + Outbox** — `assemble_casefile_triage_stage()` and `persist_casefile_and_prepare_outbox_ready()` in `pipeline/stages/casefile.py`; also includes the outbox row insert via `pipeline/stages/outbox.py` — this is the key step that decouples hot-path from Kafka
7. **Dispatch** — `dispatch_action()` in `pipeline/stages/dispatch.py`

**Note for document writer:** All stage entry functions shown (e.g. `collect_gate_inputs_by_scope()`, `evaluate_rulebook_gate_inputs_by_scope()`) are the domain-layer functions in `pipeline/stages/`. The scheduler (`pipeline/scheduler.py`) wraps these in `run_*_stage_cycle()` helpers. Show the domain-layer signatures in the per-stage walkthrough — these are what contributors read and modify. Do not show the scheduler wrappers in the per-stage section.

**Outbox insertion:** In the hot-path, the outbox row is inserted by calling `outbox_repository.insert_pending_object()` directly in `_hot_path_scheduler_loop()` — not via `pipeline/stages/outbox.py`. The `pipeline/stages/outbox.py` module serves the **outbox-publisher** worker path. The per-stage walkthrough for Stage 6 should point to `outbox/repository.py:insert_pending_object()` for the insertion step, and clarify that `pipeline/stages/outbox.py` is used by the separate outbox-publisher process.

Example format for each stage entry in the document:
```
**Stage 1 — Evidence**
Processes collected Prometheus samples into per-scope anomaly findings.
← src/aiops_triage_pipeline/pipeline/stages/evidence.py
```
```python
def collect_evidence_stage_output(
    samples_by_metric: Mapping[str, list[Mapping[str, Any]]],
    *,
    findings_cache_client: FindingsCacheClientProtocol | None = None,
    redis_ttl_policy: RedisTtlPolicyV1 | None = None,
    evaluation_time: datetime | None = None,
    telemetry_degraded_active: bool = False,
    telemetry_degraded_events: Sequence[TelemetryDegradedEvent] = (),
    max_safe_action: Action | None = None,
) -> EvidenceStageOutput:
```
All snippets must use the real signatures from the codebase — no simplified or fabricated examples.

### Gate Engine Subsection
A table of AG0–AG6 with each gate's responsibility. A short code note showing the short-circuit pattern (a gate returning `BLOCK` causes all subsequent gates to be skipped).

### Cold Path Note
Stages 8 (LLM Diagnosis) and 9 (ServiceNow Linkage) run asynchronously after hot-path dispatch. The `--mode cold-path` dispatch in `__main__.py` is currently a bootstrap stub (logs a warning and exits). However, the underlying domain logic is substantially implemented and testable independently:
- `diagnosis/` — LangGraph graph, prompt builder, fallback path, `diagnosis.json` write-once persistence
- `linkage/` — ServiceNow retry state machine, repository, schema (`linkage/repository.py`, `linkage/state_machine.py`, `pipeline/stages/linkage.py`)

New contributors should not assume these directories are empty placeholders — they contain real logic awaiting orchestration wiring.

---

## Section 4 — Runtime Modes

**Content:** Mermaid dependency diagram, then per-mode walkthrough.

### Mermaid Diagram
Four process boxes with their infrastructure dependencies (arrows to Redis, Postgres, S3, Kafka, Prometheus). Makes the separation of concerns immediately visible.

### Per-Mode Walkthrough
For each of the 4 modes:
- **Purpose:** one sentence
- **Run command:** with `APP_ENV=local` prefix
- **`--once` flag:** supported or not, and when to use it during development
- **When you'd use this:** practical dev context

Modes covered:
1. `hot-path` — **Fully wired**: loads all policies, initialises all runtime clients (Prometheus, Redis, S3, Postgres, PagerDuty, Slack, Topology), then runs `asyncio.run(_hot_path_scheduler_loop(...))` — the complete triage loop. This is the primary mode developers run locally to exercise the full pipeline.
2. `cold-path` — **Bootstrap stub in `__main__.py`**: the entrypoint logs a warning and exits. The domain modules (`diagnosis/`, `linkage/`) are implemented but not yet orchestrated through this mode.
3. `outbox-publisher` — polls Postgres outbox, publishes to Kafka (continuous or `--once`)
4. `casefile-lifecycle` — purges expired CaseFiles from S3 (hourly or `--once`)

### Dependency Matrix Table
Reproduced from existing docs: which mode needs Redis / Postgres / Kafka / S3 / Prometheus.

---

## Section 5 — Data Contracts

**Content:** Concept explanation, key contracts with snippets, enums reference.

### Contracts vs Models
Short explanation: *contracts* are stable frozen interfaces shared across subsystem boundaries (serialized, versioned, never mutated); *models* are internal domain types used within a stage. A contributor changes a model freely; changing a contract requires explicit versioning and test coverage.

### Key Contracts
For each of the four most commonly encountered contracts, show the frozen pattern and key fields. Use full paths in the format `← src/aiops_triage_pipeline/contracts/<file>.py`:

1. **`GateInputV1`** (`← src/aiops_triage_pipeline/contracts/gate_input.py`) — assembles all evidence for a scope into the rulebook input
2. **`ActionDecisionV1`** (`← src/aiops_triage_pipeline/contracts/action_decision.py`) — the rulebook's output; what action to take and why
3. **`CaseHeaderEventV1`** (`← src/aiops_triage_pipeline/contracts/case_header_event.py`) — published to Kafka, identifies the case
4. **`TriageExcerptV1`** (`← src/aiops_triage_pipeline/contracts/triage_excerpt.py`) — published to Kafka, carries the triage summary

All contract file pointers throughout Section 5 must use the full `src/aiops_triage_pipeline/` prefix for consistency with the rest of the document.

Each snippet shows the `class ... (BaseModel, frozen=True)` pattern and 3–5 representative fields.

### Shared Enums
Short table of all enums from `src/aiops_triage_pipeline/contracts/enums.py` with their values:
- `Environment` — LOCAL, HARNESS, DEV, UAT, PROD
- `Action` — OBSERVE, NOTIFY, TICKET, PAGE
- `CriticalityTier` — TIER_0, TIER_1, TIER_2, UNKNOWN
- `EvidenceStatus` — PRESENT, UNKNOWN, ABSENT, STALE
- `DiagnosisConfidence` — LOW, MEDIUM, HIGH

These appear in nearly every contract and model — knowing them prevents confusion when reading the cold-path domain code (`DiagnosisReportV1`) as well as hot-path contracts.

### Pointer
Ends with a link to `docs/schema-evolution-strategy.md` for the procedure when a contract must change.

---

## Section 6 — Configuration

**Content:** Three layers of configuration, integration modes pattern, env caps table.

### Layer 1: Settings (`config/settings.py`)
How settings are loaded (`pydantic-settings`, `APP_ENV`, env files). Key variable groups shown as a compact table:
- Infrastructure (Kafka, Postgres, Redis, S3)
- Integration modes (`INTEGRATION_MODE_PD`, `INTEGRATION_MODE_SLACK`, etc.)
- Scheduler intervals
- OTLP observability

### Layer 2: Policy YAMLs (`config/policies/`)
Loaded once at startup, drive all pipeline behavior. Table of policy files → contract → what it controls. Key insight: changing pipeline behavior means editing a YAML, not application code.

### Layer 3: Integration Modes
The `OFF/LOG/MOCK/LIVE` pattern shown with a short code snippet from the dispatch stage illustrating how the mode is checked before making a real call. Explains why this matters for local development.

### Environment Action Caps
Table: `local/harness → OBSERVE`, `dev → NOTIFY`, `uat → TICKET`, `prod → PAGE`. Short explanation of AG1 gate enforcing this cap.

---

## Section 7 — Code Navigation

**Content:** Annotated directory tree, "where do I look when..." table, local dev checklist.

### Annotated Directory Tree
Trimmed to the directories a contributor touches most. Each directory gets a one-line annotation. Focuses on `src/aiops_triage_pipeline/` but also includes `harness/`, `tests/`, `config/`.

### "Where Do I Look When...?" Table
~10 common tasks mapped to specific files:

| I want to... | Look here |
|---|---|
| Change how anomalies are classified | `pipeline/stages/peak.py` + `config/policies/peak-policy-v1.yaml` |
| Add or modify a rulebook gate | `pipeline/stages/gating.py` + `contracts/rulebook.py` |
| Change what gets published to Kafka | `contracts/case_header_event.py` or `contracts/triage_excerpt.py` |
| Add a new Prometheus metric to ingest | `config/policies/prometheus-metrics-contract-v1.yaml` |
| Change casefile retention behavior | `storage/lifecycle.py` + `config/policies/casefile-retention-policy-v1.yaml` |
| Add a new integration | `integrations/` + mode in `config/settings.py` |
| Understand a CaseFile written to S3 | `models/case_file.py` |
| Trace a past triage decision | `audit/replay.py` |
| Add a new topology scope | `registry/loader.py`; the registry itself is an external file — its path is set via the `TOPOLOGY_REGISTRY_PATH` env var, not committed under `config/policies/` |
| Understand health/degraded posture | `health/registry.py` + `health/alerts.py` |

### Local Dev Checklist
A short numbered list:
1. `uv sync --dev`
2. `docker compose up -d --build`
3. `bash scripts/smoke-test.sh`
4. Pick a mode and run it

Links to `docs/local-development.md` for full troubleshooting.

---

## Diagrams Summary

| Section | Diagram Type | Content |
|---------|-------------|---------|
| Section 2 | Mermaid flowchart | High-level concept: sources → pipeline → outputs |
| Section 3 | Mermaid flowchart | Full 9-stage pipeline, hot vs cold path |
| Section 4 | Mermaid graph | 4 runtime modes with infrastructure dependencies |

---

## Formatting Conventions

- Each section begins with a 1–2 sentence orientation: *"This section covers X. After reading it you'll understand Y."*
- Code snippets are kept short (≤15 lines) — enough to show the pattern, not the full implementation
- Every code snippet is followed by a file pointer in the format: `← src/aiops_triage_pipeline/path/to/file.py`
- Cross-references to existing docs (`docs/contracts.md`, `docs/schema-evolution-strategy.md`, etc.) appear at the end of relevant sections, not inline
- No section is longer than it needs to be; depth scales with complexity of the concept

---

## Success Criteria

A new developer who reads this document should be able to:
1. Describe what the system does and what it produces
2. Follow the flow of a single anomaly through all pipeline stages
3. Know which mode to run for their current task
4. Find the file to edit for any of the common tasks in the navigation table
5. Make a safe local change (edit a policy or stage) and run the test suite
