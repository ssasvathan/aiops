# Open Items & Deferred Design Decisions

This section tracks unresolved design decisions and acknowledged deferrals. Items are separated into those requiring resolution before their target phase can ship and those explicitly deferred without blocking MVP.

## Open — Requires Resolution Before Target Phase

| ID | Item | Context | Target Phase |
|---|---|---|---|
| OI-1 | Edge Fact schema definition | Platform edge facts (producer→topic, consumer_group→topic, service→sink) are referenced throughout Phase 3 scope but no formal schema, ingestion contract, or provenance model exists. Required before hybrid topology enrichment can consume them. | Phase 3 |
| OI-2 | Sink-to-stream mapping policy | Sink identifiers must map to topology registry streams for Sink Health Evidence Track attribution. Mapping must remain exposure-safe (denylist applies to sink endpoints). No mapping policy or schema is defined. | Phase 3 |
| OI-3 | Dynatrace Smartscape integration contract | Phase 3 lists Smartscape as an inbound integration (OFF/MOCK/LIVE) but no API contract, query patterns, authentication model, or data-mapping specification exists. Required before hybrid topology can merge observed edges with governed YAML. | Phase 3 |
| OI-4 | Coverage weighting formula for hybrid topology | Phase 3 success metric requires "runtime enrichment covers >= 70% of expected edges." No formula defines how coverage weight is computed across YAML, Smartscape, and edge-fact sources. | Phase 3 |
| OI-5 | Exposure denylist initial seed content | The denylist is mandated as a versioned artifact (FR62, NFR-S5) enforced at every output boundary, but no initial denylist content (pattern list, field names, regex rules) is defined. Required before Phase 1A TriageExcerpt assembly. | Phase 1A |
| OI-6 | DiagnosisReport.v1 formal field schema | DiagnosisReport.v1 is referenced as "schema locked; content evolves" with fields (verdict, fault_domain, confidence, evidence_pack, next_checks, gaps), but no frozen YAML/JSON schema artifact exists comparable to GateInput.v1. Required for LLM output validation (FR40). | Phase 1A |
| OI-7 | CaseFile serialization schema | CaseFile stage files (triage, diagnosis, linkage, labels) are described semantically but no formal serialization schema (field names, types, nesting, SchemaEnvelope wrapping) is defined. See `docs/schema-evolution-strategy.md` for the envelope pattern and versioning strategy. | Phase 1A |
| OI-8 | Diagnosis policy freeze criteria | Diagnosis policy is explicitly "draft, not frozen" and can evolve independently of the Rulebook. No criteria exist for when or whether it should be frozen, nor how draft-to-production promotion is governed. | Phase 1A |
| OI-9 | Data classification taxonomy validation | CaseFile content is expected to fall within the bank's Internal/Operational tier, but formal validation against the bank's data classification taxonomy is deferred to deployment readiness review. Must be resolved before prod deployment. | Phase 1A (prod) |

## Deferred — Acknowledged, Not Blocking MVP

| ID | Item | Context | Target Phase |
|---|---|---|---|
| DF-1 | v0 registry deprecation timeline | v0 compat views supported in Phase 1A with deprecation warnings in Phase 1B/2 and removal Phase 2+. No concrete deprecation date or consumer-readiness gate defined. | Phase 2+ |
| DF-2 | LLM vendor selection & data handling contract | NFR-S8 requires bank-sanctioned LLM endpoints and a vendor contract prohibiting training on submitted data. Vendor identity, contract terms, and endpoint provisioning are unresolved. | Phase 1A (pre-prod) |
| DF-3 | Labeling workflow UX | CaseFile schema supports label fields from Phase 1A, but the operator capture workflow (UI/API/CLI) is explicitly deferred to Phase 2. | Phase 2 |
| DF-4 | Local-dev Mode B (dedicated remote env) | Mode B is opt-in. Mode A (docker-compose) is the MVP requirement. Mode B endpoint approval, credential provisioning, and guardrails against accidental prod calls are deferred. Each remote environment (DEV, UAT, PROD) has dedicated infrastructure. | Phase 1A+ |
| DF-5 | LLM cost model & invocation budget | LLM invocation is conditional with bounded token input (FR42), but no per-case token budget, monthly cost ceiling, or cost-tracking metric is defined. | Phase 1A (prod) |
| DF-6 | Multi-region / DR topology for AIOps pipeline | Instance-scoped topology supports multi-cluster for monitored streams, but DR posture for the pipeline's own components (Postgres, object storage, Redis) has no defined RTO/RPO targets. | Phase 1A (prod) |
| DF-7 | Outbox DEAD manual recovery procedure | DEAD=0 is a standing prod posture and any DEAD row is critical. Recovery requires human investigation (NFR-R4), but no runbook or replay tooling is specified. | Phase 1A (prod) |
| DF-8 | Advisory ML booster architecture | Phase 2 adds top-N hypothesis ranking from learned patterns. No ML model type, training pipeline, or serving architecture is defined. Blocked by label data quality gates. | Phase 2 |
| DF-9 | Runbook assistant content & linking strategy | Phase 2 includes a read-only runbook assistant providing "next best checks." No content authoring workflow or linking mechanism to CaseFile evidence is defined. | Phase 2 |
| DF-10 | Client/app-level telemetry metric contract | Phase 2 expands evidence sources to client/app signals. No metric names, collection methods, or prometheus-metrics-contract-v2 extension is defined. | Phase 2 |
| DF-11 | CaseFile purge automation implementation | Retention governance and auditable purge are required (FR21), but the lifecycle policy engine and purge audit log format are not specified. | Phase 1A (prod) |
| DF-12 | Sink health evidence source identification | Phase 3 defines six sink evidence primitives but does not identify which telemetry sources (exporters, agents) provide the raw signals. | Phase 3 |
