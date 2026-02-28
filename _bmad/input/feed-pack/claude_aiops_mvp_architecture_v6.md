# Claude MD — Agentic AIOps MVP for Kafka (Context + Diagnosis) — Canonical Scope & Architecture (v5)

<role>
You are an expert AI engineer and systems architect. Your job is to implement or evolve this AIOps MVP **without reinventing** existing components, keeping the design production-oriented while being explicit about what is simulated vs real.
</role>

<purpose>
This document is the **canonical scope + architecture + rules** for the laptop MVP. It consolidates the original Context-Agent MVP and the later Diagnosis + interval-based signal model into a single coherent design, suitable for ongoing evolution.
</purpose>

---

## 1) System Context

<context>
We operate a shared Kafka ingestion pipeline. For a given domain (e.g., Payments), ingestion and downstream propagation looks like:

source topic (per source system) → shared source-stream topic → shared standardizer/raw topics → NiFi flow → EDL landing (HDFS path) → Hive external view → Ranger/AD groups

The MVP simulates telemetry and signal generation, but preserves the same conceptual pipeline and ownership boundaries.
</context>

---

## 2) MVP Scope Boundaries

<in_scope>
- One Python **uv** project implementing a single **LangGraph** graph representing the AIOps chain.
- Simulated telemetry → normalized metrics → interval/topic-grouped signal findings.
- Optional ML evidence enrichment within **signal_report_gen** (classical ML; may be stubbed/simulated in MVP) to support correlation, signature grouping, and ranked hypotheses for diagnosis.
- A Context Agent that produces a validated **ContextEnvelope v1** (enrichment + features).
- A Diagnosis Agent that produces a validated **DiagnosisReport v1** (decision + next checks).
- Registry-as-code topology/ownership metadata (YAML).
- Diagnosis policy bundle (YAML) interpreted by the LLM (rule IDs for traceability).
- CLI demo runner for deterministic scenarios.
- Tests and linting gates that pass without API keys (no-LLM mode).
</in_scope>

<out_of_scope>
- Real integrations (Kafka, Prometheus, Dynatrace, NiFi APIs, Ranger APIs, paging/ticketing tools).
- Full ML Ops (training pipelines, model registry, drift monitoring) beyond simple offline/stubbed models.
- Auto-remediation / Action Agent execution.
- UI dashboards and multi-tenant RBAC.
- Persistent incident similarity search (stubs/refs only).
</out_of_scope>

---

## 3) Target Architecture

### 3.1 LangGraph nodes (MVP)
<graph>
The graph is a linear pipeline with explicit data contracts between nodes:

1) simulate_telemetry (simulated)
2) normalize_metrics (simulated)
3) pattern_agent (simulated seasonality / peak profile)
4) feature_store (simulated baselines/history)
5) detect (simulated anomaly detection; retains anomaly_signal for compatibility)
6) signal_report_gen (interval-based + grouped-by-topic report; optionally adds ML evidence enrichment)
7) context_agent (LLM-assisted enrichment under strict invariants)
8) diagnosis_agent (LLM-first decision using policy bundle)
9) emit_case_file (assemble final JSON)
</graph>

### 3.2 State model
<state>
GraphState carries:
- code-owned identifiers (correlation_id)
- anomaly_signal summary (legacy compatibility)
- signal_window (rolling last N intervals; N ≤ 5 for MVP)
- signals_by_topic (last-interval map topic → topic finding)
- ml_evidence (optional evidence bundle from signal_report_gen; non-authoritative inputs to Context + Diagnosis)
- context_envelope (ContextEnvelope v1)
- diagnosis_report (DiagnosisReport v1)
- gaps (structured gap list for missing/invalid inputs)
</state>

---

## 4) Core Data Contracts and Invariants

### 4.1 Canonical metrics vocabulary
<metrics>
Define a canonical set of metric names (e.g., MetricName enum). All telemetry normalization, findings, baselines, and policy references MUST use this canonical vocabulary. If aliases exist, they must be mapped to canonical values in one place only.
</metrics>

### 4.2 Signal evaluation semantics
<signal_semantics>
- evaluation_interval_minutes = 5
- sustained_intervals_required = 5
- sustained is computed using the **tail consecutive anomalous interval count** (ending at the latest interval) for the same (topic, anomaly_type).
- signal_window is the rolling window used for both context and diagnosis input shaping (default last 5 intervals).
</signal_semantics>

### 4.2.1 ML evidence enrichment (optional; classical ML)
<ml_evidence>
`signal_report_gen` may attach an optional **ml_evidence** bundle to reduce alert noise and improve triage quality when multi-signal telemetry is available (metrics + logs + traces) and components are topologically connected.

Scope of **ml_evidence** (evidence only; never a final decision):
- Incident correlation: cluster related symptoms into incident candidates (with confidence).
- Log signature grouping: reduce raw log noise into stable signatures/features usable for correlation.
- Topology-aware RCA ranking: produce ranked candidate fault components/domains constrained by registry topology.
- Recommendation ranking + auto-resolve safety scoring: rank suggested next steps and provide a safety score (no execution in MVP).

Invariants:
- **ml_evidence is advisory** and must not override signal semantics, registry mappings, or policy bundle rules.
- Absence of ml_evidence must be handled (deterministic baseline report remains valid).
- Include minimal provenance when present (e.g., model/version identifier and training window), so downstream reports remain audit-friendly.
</ml_evidence>


### 4.3 ContextEnvelope v1 (enrichment contract)
<context_envelope_contract>
ContextEnvelope is a validated JSON object with at least:
- contract_version = "context_envelope.v1"
- correlation_id (code-owned; must not be modified by LLM)
- event: the observed anomaly signal (topic, env, detected_at, anomaly_type, metric_name/value, direction, topic_role, consumer_group if relevant)
- identifiers: environment, stream_id, source_system (role-dependent), plus optional dataset/pipeline/namespace identifiers
- blast_radius (scope + impacted sources)
- business_context (peak_context, criticality tier, topic role, stream id)
- topology_exposure (downstream components marked AT_RISK with exposure_type)
- ownership (platform_team, steward_team when applicable)
- historical_context.notes: list of strings
- change_context.notes: list of strings
- severity_inputs (features + recommendation band; NOT a final severity)
- gaps[] (structured, role-aware)
</context_envelope_contract>

<context_agent_rules>
Context Agent responsibilities:
- Enrich the signal with topology, ownership, blast radius, and peak context.
- Provide “severity inputs” (features + recommendation band) but **not** the final incident decision.
- Never decide fault domain, suppression, or urgency.

LLM usage rules:
- LLM may generate narrative notes and add supporting reasons, but **must not** change invariants (correlation_id, topic_role/stream_id derived from registry, etc.).
- Output must be schema-safe: the system must never crash due to malformed LLM output.
- If LLM output is invalid, return a deterministic valid ContextEnvelope and record a gap.
</context_agent_rules>

### 4.4 DiagnosisReport v1 (decision contract)
<diagnosis_report_contract>
DiagnosisReport is a validated JSON object with at least:
- contract_version = "diagnosis_report.v1"
- correlation_id (must match GraphState correlation_id)
- observed_signal (topic, anomaly_type, env, detected_at, sustained, confidence, metric findings)
- decision:
  - verdict: LIKELY_REAL | LIKELY_FALSE_POSITIVE | NEEDS_MORE_EVIDENCE
  - fault_domain: UPSTREAM_PRODUCER | PLATFORM_PIPELINE | DOWNSTREAM_CONSUMER | KAFKA_INFRA | UNKNOWN | MULTI_DOMAIN
  - owner_to_notify: platform_team / steward_team / other (string)
  - urgency: PAGE | TICKET | NOTIFY | OBSERVE | SUPPRESS
  - confidence: 0..1
- evidence_pack:
  - facts[] (short bullets grounded in signal+context)
  - missing_evidence[] (what would increase certainty)
  - matched_rules[] (rule_id + rule_name)
- next_checks[] (checklist; no remediation)
- gaps[] (diagnosis-scoped gaps, e.g., invalid LLM output)
</diagnosis_report_contract>

<diagnosis_agent_rules>
Diagnosis Agent responsibilities:
- Decide false alert vs real incident, classify likely fault domain, pick urgency, recommend next checks.
- Be **LLM-first** for decisions in normal mode; deterministic code may only build inputs, enforce invariants, validate schema, and provide no-LLM test stubs.
- Traceability is mandatory: include matched rule IDs from the policy bundle.
- If LLM output is invalid/unparseable, return a valid DiagnosisReport with verdict NEEDS_MORE_EVIDENCE and record a gap (no “hidden” deterministic policy engine in the LLM path).
</diagnosis_agent_rules>

---

## 5) Registry-as-Code and Policy Bundles

<registry_rules>
Registry YAML encodes:
- stream definitions (env, stream_id, owners, criticality tier)
- topic index (topic → role, stream_id, source_system where applicable)
- downstream components for exposure (standardizer topic, NiFi flow id, HDFS sink paths, Hive views, Ranger groups)
- peak window policy metadata; peak window evaluation uses the pattern agent output (simulated in MVP)
</registry_rules>

<policy_rules>
Diagnosis policy YAML is a human-readable rule bundle:
- version, evaluation_interval_minutes, sustained_intervals
- fault domain definitions
- rules[] with:
  - id, name, applies_to
  - evidence.required/supports/contradicts (text for LLM interpretation)
  - decision defaults (verdict, fault_domain, urgency)

Policy is not executed as code in MVP; it is interpreted by the LLM against the structured inputs.
</policy_rules>

---

## 6) Domain Rules (Non-negotiable)

<domain_rules>
Blast radius:
- anomaly on SOURCE_TOPIC ⇒ LOCAL_SOURCE_INGESTION
- anomaly on shared KAFKA_SOURCE_STREAM ⇒ SHARED_KAFKA_INGESTION

Exposure semantics:
- Downstream components are marked AT_RISK, not “failed”.
- exposure_type distinguishes:
  - DOWNSTREAM_DATA_FRESHNESS_RISK (default for upstream lag/volume anomalies)
  - DIRECT_COMPONENT_RISK (reserved for future direct evidence)
  - VISIBILITY_ONLY (optional)

Canonical landing identifier:
- HDFS path is canonical for sinks/datasets in MVP.

Peak window evaluation:
- detected_at is an instant; convert into the configured timezone (e.g., America/Toronto) before evaluating day-of-week/hour windows.

Gap policy is role-aware:
- For SOURCE_TOPIC, source_system is required; missing → gap
- For shared roles (KAFKA_SOURCE_STREAM, STANDARDIZER_SHARED, AUDIT_RAW_SHARED), source_system is not applicable; no gap
</domain_rules>

---

## 7) Runtime Modes and Configuration

<runtime_modes>
- Default mode: LLM enabled (Context + Diagnosis call Claude via LangChain/Anthropic).
- No-LLM mode: enabled via CLI flag `--no-llm` or env var `AIOPS_LLM_DISABLED=1`.
  - Must produce deterministic, schema-valid ContextEnvelope and DiagnosisReport (using stubs where needed).
  - Must not require API keys and must be used by tests.
</runtime_modes>

<llm_config>
- Model selection is controlled by env var `AIOPS_LLM_MODEL`.
- Default should be a stable model alias suitable for dev; production can pin a dated snapshot outside this MVP.
</llm_config>

---

## 8) CLI and Demo Expectations

<demo>
`run_demo.py` runs deterministic scenarios and prints a Case File JSON:
- correlation_id
- signal_agent_report (interval/topic grouped)
- context_envelope
- diagnosis_report

Scenarios must demonstrate:
- at least one PAGE decision (high confidence, sustained, shared stream, peak)
- at least one lower urgency (NOTIFY/TICKET)
- at least one false positive / SUPPRESS (not sustained and/or low confidence)
</demo>

---

## 9) Quality Gates (Must Pass)

<quality_gates>
The repo is considered healthy only if these pass:
- uv sync
- uv run python -m compileall .
- uv run pytest -q
- uv run ruff check .

Tests must be deterministic and must not require API keys.
</quality_gates>

---

## 10) Claude Authoring Rules (for future changes)

<prompting_rules>
When using this MD to ask Claude for changes:
- Keep prompts structured with clear sections and consistent tags (XML tags are recommended for separating context/instructions/contracts/examples).
- Provide explicit output formats and schemas for any structured JSON.
- Prefer “tell what to do” instructions, and match prompt formatting to desired output formatting.
- For JSON, prefer schema-constrained output patterns to prevent invalid structures; ensure the runtime is resilient to invalid model outputs.
</prompting_rules>

---

## 11) Future Extensions (Non-blocking)
<future>
- Replace simulated telemetry and baselines with real platform signal agent outputs.
- Replace stubbed/simulated ML evidence with trained classical models (and governance controls) when incident outcome data is available.
- Add an Action Agent (remediation execution) as a separate scope with strict safety rails.
- Add incident similarity search and persistent case storage.
- Add UI and multi-tenant governance when productized.
</future>
