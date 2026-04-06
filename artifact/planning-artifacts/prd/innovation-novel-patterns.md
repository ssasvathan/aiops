# Innovation & Novel Patterns

## Detected Innovation Areas

**1. Two-Layer Detection Architecture**
The coexistence of hand-coded causal detectors (known failure modes) with a generic statistical safety net (unknown unknowns) in a single pipeline — with deterministic dedup ensuring they don't collide — mirrors the Datadog Watchdog + Monitors pattern but is novel in the self-hosted LGTM ecosystem. No open-source tool provides this for Grafana/Prometheus stacks. The OSS LGTM stack has a documented gap in cross-signal correlation and topology-aware detection; this addresses part of that gap.

**2. Correlated Deviation as Noise Gate**
Requiring 2+ metrics to deviate in the same cycle for the same scope before emitting a finding is an unconventional approach to false positive management. Standard anomaly detection systems detect per-metric and filter post-hoc. This system uses correlation as a structural admission gate — single-metric anomalies never enter the pipeline. This dramatically reduces noise at the source rather than downstream.

**3. Graduation Pipeline (Growth Feature)**
The concept that recurring LLM hypotheses (3+ identical) surface as candidate hand-coded detector rules means the system bootstraps its own domain-specific detection capability. The generic layer discovers patterns; the LLM interprets them; human review promotes them to first-class detectors. This is a closed-loop learning system built from deterministic components.

## Market Context & Competitive Landscape

- Grafana's OSS `promql-anomaly-detection` framework provides per-metric baselining via recording rules but has no correlation, no topology enrichment, and no LLM diagnosis
- Vendor platforms (Datadog Watchdog, Dynatrace Davis) provide correlation and topology but are closed-source, cloud-only, and expensive
- No self-hosted solution combines statistical baseline + correlation gate + topology enrichment + LLM diagnosis in a single pipeline with deterministic gating and audit trails

## Validation Approach

- **Correlated deviation effectiveness:** Compare false positive rate of correlated-only findings vs. hypothetical all-single-metric findings using first 3 months of operational data
- **Two-layer coverage:** Track cases where baseline deviation caught an anomaly that no hand-coded detector would have fired on — the "unknown unknown" detection rate
- **Graduation viability (Growth):** Track LLM hypothesis recurrence and evaluate whether surfaced candidates represent genuine detector-worthy patterns

Innovation risk is low — all individual components use proven techniques (MAD, time bucketing, Redis, existing pipeline stages). The innovation is in the combination, not the components. The baseline layer is independently disableable with zero coupling to existing detectors. See Risk Mitigation Strategy under Project Scope for detailed risk tables.
