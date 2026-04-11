# Project Scope & Phased Development

## MVP Strategy

**Approach:** Problem-solving MVP — the minimum implementation that catches at least one "unknown unknown" anomaly that no existing detector would have caught, with enough context (correlated metrics + LLM hypothesis) to be actionable.

**Resource Requirements:** Single developer. All infrastructure dependencies (Redis, Prometheus, pipeline framework, cold-path consumer) already exist. The work is: one new pipeline stage, one finding model extension, one Redis keyspace, one backfill extension, and observability instrumentation.

## MVP Feature Set (Phase 1)

**Core User Journeys Supported:**
- Journey 1 (on-call receives correlated deviation notification with LLM hypothesis) — fully supported
- Journey 2 (noise suppression verification) — fully supported
- Journey 3 (zero-code new metric onboarding) — fully supported
- Journey 4 (operational monitoring) — partially supported (OTLP metrics yes, YAML tuning no)

**Must-Have Capabilities:**

| # | Capability | Justification |
|---|---|---|
| 1 | Seasonal baseline storage (168 time buckets in Redis) | Without seasonality, daily traffic patterns produce false anomalies twice daily |
| 2 | Cold-start backfill seeding | Without seed data, baselines are empty on first startup — no detection possible |
| 3 | MAD computation per scope/metric/bucket | Core statistical engine — the detection mechanism |
| 4 | Correlated deviation requirement (2+ metrics) | Without this, false positive rate is unacceptable — industry research validates this |
| 5 | Hand-coded detector dedup | Without this, users get duplicate findings for the same scope — noise and confusion |
| 6 | BASELINE_DEVIATION finding model | The pipeline contract that carries deviation data through topology/gating/dispatch |
| 7 | NOTIFY cap at source | Safety invariant — generic findings must never escalate to TICKET/PAGE |
| 8 | Incremental bucket updates per cycle | Baselines stay fresh without waiting for weekly recomputation |
| 9 | Weekly recomputation from Prometheus | Corrects baseline pollution from persistent anomalies |
| 10 | LLM diagnosis for baseline deviation cases | Stakeholder value — without hypothesis, raw statistical deviations are not actionable |
| 11 | OTLP observability instrumentation | Operators must be able to monitor the new stage's health and effectiveness |

**Explicitly NOT in MVP (could be manual initially):**
- Metric personality auto-classification — MAD works for all metric types in Phase 1; tune later with data
- YAML-configurable thresholds — constants in code; single-line change if urgent
- Cluster-level alert grouping — separate case files per scope; group manually if noisy
- Graduation pipeline — manual review of LLM hypotheses is sufficient initially

## Phase 2 (Growth) — Data-Driven Refinement

- Metric personality auto-classification (analyze 30-day history → select method per metric)
- YAML-configurable thresholds (extract constants to policy YAML when operators need it)
- Cluster-level alert grouping (consolidate multi-scope findings per cluster)
- Maintenance window context signals (suppress expected deviations during planned changes)

## Phase 3 (Expansion) — Multi-Signal Extension

- Trace baselines from Tempo (RED metrics per service)
- Log baselines from Loki (rate metrics per service)
- Cross-signal correlation (metrics + traces + logs for same topology scope)
- Graduation pipeline (recurring LLM hypotheses → candidate hand-coded rules)
- Per-signal topology mapping

## Risk Mitigation Strategy

**Technical Risks:**

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| MAD threshold too sensitive/conservative | Medium | Low | Constants are a single-line code change; tune based on first month of operational data |
| Redis memory pressure from 756K keys | Low | Medium | Estimated 75-150 MB; monitor with existing Redis health metrics; keys are small (list of ≤12 floats) |
| Cycle duration budget exceeded | Low | Medium | MAD computation is O(n) with n≤12; `mget` batches Redis reads; monitor via OTLP histogram |
| Cold-start backfill extends startup time | Medium | Low | Backfill already exists for peak history; seasonal bucketing is partitioning, not additional queries |
| Correlated deviation misses real single-metric anomalies | Medium | Low | Single-metric deviations are DEBUG-logged; can lower MIN_CORRELATED_DEVIATIONS to 1 if data shows missed anomalies |

**Operational Risks:**

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| False positive noise despite correlation gate | Low | High | MAD ±4.0 is conservative; NOTIFY cap limits blast radius; disable layer entirely if noisy (zero coupling to existing detectors) |
| Baseline pollution from persistent anomalies | Medium | Low | Weekly recomputation corrects drift; 12-week cap per bucket bounds pollution window |
| LLM hypothesis quality for unknown anomaly types | Medium | Medium | Hypothesis is advisory ("possible interpretation"); fallback diagnosis handles LLM failures; non-blocking |

**Resource Risks:**
- Single developer can deliver MVP — all infrastructure exists, no new external integrations
- If timeline is constrained, LLM diagnosis (item 10) could be deferred to a fast-follow — the detection layer works independently
- Fallback minimum: items 1-9 without LLM diagnosis still catch correlated deviations and route through the pipeline
