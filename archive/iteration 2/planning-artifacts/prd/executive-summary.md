# Executive Summary

aiOps is an event-driven AIOps triage platform that replaces static, context-blind infrastructure alerting with a deterministic, evidence-driven pipeline producing auditable operational decisions. The platform ingests Prometheus telemetry from Kafka infrastructure, detects anomalies through per-scope statistical baselines, resolves topology and blast radius, routes ownership, and dispatches actions through safety-gated deterministic evaluation — with every decision reproducible for 25 months.

The baseline implementation delivered all 8 epics: foundation, evidence collection, topology resolution, durable triage/outbox, deterministic gating (AG0-AG6), LLM diagnosis, governance/observability, and ServiceNow automation. This revision phase (11 changes, CR-01 through CR-11) activates built-but-unwired capabilities into operational readiness for deployment on a live OpenShift cluster with a mandatory hot/hot 2-pod minimum. The goal is not new features — it is transitioning from "built and tested" to "running on real data, proving itself."

The platform targets four specific failure modes in the current operational status quo: threshold rot (static thresholds never recalibrated as traffic scales), blast radius blindness (operators manually tracing topology before assessing severity), page storms (dozens of correlated alerts for a single root cause), and decision opacity (no audit trail explaining why an action was or wasn't taken).

Primary users are on-call engineers (receiving pre-triaged, deduplicated actions with ownership and blast radius pre-resolved), SRE/platform engineers (operating and tuning the platform through versioned YAML policies), and application team engineers (maintaining topology, denylist, and policy configurations across environments).

## What Makes This Special

Safety is structural, not configurable. PAGE is architecturally impossible outside PROD+TIER_0 — actions can only cap downward, never escalate. The LLM cold-path diagnosis enriches cases without risk: no import path, no shared state, no conditional wait on the hot path. This is a design invariant, not a deployment choice.

The telemetry-source-agnostic architecture means the gating engine evaluates `GateInputV1` without knowing whether the anomaly originated from Kafka lag, VM CPU, or database connection exhaustion. Phase 1 proves the architecture against Kafka + Prometheus; future phases extend evidence collectors without rewriting the triage pipeline.

Every decision is reproducible: hand an auditor the case ID and they can replay exact gate evaluations with the exact policy versions, evidence snapshot, and reason codes active at decision time. Write-once casefiles with SHA-256 hash chains, policy version stamping, and schema envelope versioning ensure 25-month audit integrity.

The revision phase activates the operational activation gap — wiring Redis caches so sustained detection actually works, making the YAML rulebook authoritative so operators can tune without code changes, enabling distributed multi-replica safety for K8s reality, and bringing the cold-path LLM from stub to live Kafka consumer producing real diagnosis reports.
