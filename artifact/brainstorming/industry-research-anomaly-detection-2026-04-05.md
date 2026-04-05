# Industry Research: Anomaly Detection Across Observability Signals

**Prepared for:** Brainstorming session on metric-agnostic anomaly detection
**Date:** 2026-04-05
**Scope:** Current (2024-2026) industry practices, vendor approaches, practitioner experiences

---

## 1. Industry Standard Approaches Across the Three Telemetry Signals

### The Core Finding: Different Signals Get Different Treatment

No leading platform uses a single uniform detection method across metrics, logs, and traces. Every major vendor uses **signal-specific detection strategies**, though they converge on a common pattern: **ultimately, everything becomes a numeric time series for statistical analysis**.

### Platform-by-Platform Breakdown

#### Datadog (Watchdog)

**Metrics:** Three anomaly detection algorithms, all statistical:
- **Basic**: Rolling quantile computation (no seasonality awareness, adapts quickly)
- **Agile**: Seasonal ARIMA variant (handles seasonality + adapts to level shifts)
- **Robust**: Seasonal-trend decomposition (stable predictions, resistant to lasting anomalies)
- Bounds parameter works like standard deviations (2-3 captures most normal points)

**Logs:** Log-based metrics (counts, distributions) are derived from log streams, then standard metric anomaly detection applies. Log pattern clustering groups similar messages into templates.

**Traces:** Watchdog monitors latency distributions and error rates derived from spans. Metric Correlations automatically surface related metric spikes across infrastructure.

**Cross-signal:** Watchdog Explains analyzes dimensional tags across all signal types to isolate root cause. Predictive correlations surface metric relationships even without explicit dependency mappings.

Sources:
- [Introducing Anomaly Detection in Datadog](https://www.datadoghq.com/blog/introducing-anomaly-detection-datadog/)
- [Anomaly Monitor Documentation](https://docs.datadoghq.com/monitors/types/anomaly/)
- [AI-Powered Metrics Monitoring](https://www.datadoghq.com/blog/ai-powered-metrics-monitoring/)
- [Watchdog Documentation](https://docs.datadoghq.com/watchdog/)

#### Dynatrace (Davis AI)

**Fundamentally different approach: Causal AI + Topology.**

**Metrics:** Auto-adaptive baselining that adapts to changing metric behavior over time. Topology-aware -- analyzes thousands of topologically related metrics per component simultaneously. Uses the Smartscape real-time dependency graph as context.

**Logs:** Correlates logs with traces using shared context. Log analysis feeds into the broader causal model rather than standalone detection.

**Traces:** Deep integration with the Smartscape topology model. Trace anomalies are analyzed in the context of service dependencies and infrastructure relationships.

**Root Cause:** Deterministic fault-tree analysis (same methodology as NASA/FAA). This is causation, not correlation. The Grail data lakehouse + Smartscape dependency graph enables Davis to establish baselines with topology and dependency context.

**Key differentiator:** Davis does not just detect anomalies -- it identifies root cause by following dependency chains through the topology graph. The "Problem Graph" maps anomalies to impacted entities and dependency chains.

Sources:
- [Davis AI Documentation](https://docs.dynatrace.com/docs/discover-dynatrace/platform/davis-ai)
- [How Davis Works](https://dynatrace.awsworkshop.io/50_operate/20_how_davis_works.html)
- [Smartscape Documentation](https://docs.dynatrace.com/docs/analyze-explore-automate/smartscape)
- [Dynatrace Root Cause Analysis](https://docs.dynatrace.com/docs/platform/davis-ai/root-cause-analysis)

#### New Relic (Applied Intelligence)

**Metrics:** Dynamic baselines that "adjust to accommodate the expected fluidity and volatility of your business." A single alert config can apply to up to 5,000 related time series per service/entity. ML-based anomaly detection now extends beyond APM to nearly any entity type.

**Logs:** Pattern analysis and anomaly detection integrated with Applied Intelligence correlation.

**Traces:** Distributed tracing anomaly detection identifies unusual patterns in trace data.

**Cross-signal:** Issue Maps visualize upstream and downstream entities affected by incidents, highlighting infrastructure context (hosts, owners, regions). Applied Intelligence correlates related incidents into unified issues enriched with context, automatically surfacing probable root causes.

Sources:
- [Next Gen AIOps](https://newrelic.com/blog/how-to-relic/next-gen-ai-ops)
- [Applied Intelligence](https://newrelic.com/platform/applied-intelligence)
- [Distributed Tracing Anomaly Detection](https://newrelic.com/blog/apm/distributed-tracing-anomaly-detection)

#### Elastic

**Metrics:** Unsupervised ML using Bayesian distribution modeling + time series decomposition + clustering + correlation analysis. Models compute probability distributions per time bucket, continuously updating. Anomaly scores range 0-100, aggregated to reduce noise and normalized to rank significance.

**Logs:** Two distinct approaches:
1. **Log rate anomaly detection**: Detects when log entry rates fall outside expected bounds (metric-derived)
2. **Log categorization**: ML automatically categorizes log messages by pattern, then detects anomalous categories or volumes

**Traces:** Integrates with APM for span-level anomaly detection.

**Key detail:** Elastic ML jobs analyze 4 weeks of historical data by default and run indefinitely. Log anomaly results retained 120 days.

Sources:
- [Elastic Anomaly Detection Algorithms](https://www.elastic.co/docs/explore-analyze/machine-learning/anomaly-detection/ml-ad-algorithms)
- [Detect Metric Anomalies](https://www.elastic.co/docs/solutions/observability/infra-and-hosts/detect-metric-anomalies)
- [Inspect Log Anomalies](https://www.elastic.co/docs/solutions/observability/logs/inspect-log-anomalies)
- [Elastic AIOps](https://www.elastic.co/observability/aiops)

#### Splunk (ITSI)

**Metrics/KPIs:** Adaptive thresholding (replaced older anomaly detection as of ITSI 4.20). Supports multiple statistical methods: standard deviation, range, percentage, or quantile. Computes thresholds adaptively without distribution assumptions. Thresholds are robust to outliers.

**Two detection algorithms:**
1. **Trending**: Monitors sliding window on single time series, compares current patterns to historical
2. **Entity Cohesion**: Monitors all time series within a group, scores departures from collective behavior

**Logs:** Pattern clustering and categorization. Splunk's log pattern analysis groups repetitive messages.

Sources:
- [Splunk ITSI Adaptive Thresholding](https://help.splunk.com/en/splunk-it-service-intelligence/splunk-it-service-intelligence/visualize-and-assess-service-health/4.21/advanced-thresholding/migrate-anomaly-detection-to-adaptive-thresholding-in-itsi)
- [ML-Powered Adaptive Thresholding](https://www.splunk.com/en_us/blog/it/ml-powered-assistance-for-adaptive-thresholding-in-itsi.html)
- [Understanding Anomaly Detection in ITSI](https://lantern.splunk.com/Observability_Use_Cases/Monitor_Business/Understanding_anomaly_detection_in_ITSI)

### Summary: Common Statistical Methods Across Platforms

| Method | Used By | Signal Type | Notes |
|--------|---------|-------------|-------|
| Seasonal decomposition (STL/SARIMA) | Datadog (Robust/Agile) | Metrics | Handles daily/weekly patterns |
| Rolling quantiles | Datadog (Basic), Splunk | Metrics | Fast adaptation, no seasonality |
| Bayesian distribution modeling | Elastic | Metrics | Probability-based scoring |
| Mean + standard deviation | Grafana (Adaptive), most platforms | Metrics | Universal baseline approach |
| Median + MAD | Grafana (Robust) | Metrics | Outlier-resistant alternative |
| Auto-adaptive baselining | Dynatrace | Metrics | Topology-aware, adapts over time |
| Dynamic baselines | New Relic | Metrics | Scales to thousands of series |
| Adaptive thresholding | Splunk ITSI | KPIs | Distribution-free, robust |
| Log rate monitoring | Elastic, Datadog | Logs | Derives count metric from logs |
| Log pattern clustering | All platforms | Logs | Groups similar messages |
| Latency/error rate baselines | All platforms | Traces | Derives metrics from spans |

---

## 2. "Derive a Metric, Then Baseline the Metric" -- Is This the Standard Pattern?

### Yes, This Is the Dominant Pattern

**The overwhelming industry consensus is: convert everything to a numeric time series, then apply statistical detection.** This is true across all three signals.

#### How Each Signal Gets Converted

**Logs to Metrics:**
- **Log rate**: Count of log entries per time window (most common)
- **Log-derived KPIs**: Extract numeric values from structured fields (e.g., response times from access logs)
- **Pattern frequency**: Count occurrences of each log template/pattern over time
- **Error rates**: Ratio of error-level logs to total logs

Tools that explicitly support log-to-metric conversion: Datadog (Logs to Metrics), Splunk (Log Metricization), Fluent Bit (log_to_metrics filter), Vector (log_to_metric transform), OpenTelemetry Collector (connectors), OpenSearch (Data Prepper).

IBM Research published "Decoding Logs for Automatic Metric Identification" (CLOUD 2024), describing LogMId -- a method to automatically extract critical IT metrics from logs.

**Traces to Metrics:**
- **Latency percentiles**: p50, p95, p99 per service/endpoint
- **Error rates**: Percentage of failed spans per service
- **Throughput**: Requests per second per service
- **Span duration distributions**: Statistical summaries of span durations

Every observability platform extracts these RED metrics (Rate, Errors, Duration) from traces before applying anomaly detection.

Sources:
- [Datadog Logs to Metrics](https://docs.datadoghq.com/logs/log_configuration/logs_to_metrics/)
- [Splunk Log Metricization](https://docs.splunk.com/Observability/logs/metricization.html)
- [Vector log_to_metric Transform](https://vector.dev/docs/reference/configuration/transforms/log_to_metric/)
- [IBM LogMId Research](https://research.ibm.com/publications/decoding-logs-for-automatic-metric-identification)
- [Fluent Bit log_to_metrics](https://docs.fluentbit.io/manual/data-pipeline/filters/log_to_metrics)

#### But There Are Complementary Non-Metric Approaches

While "derive a metric" dominates, some techniques work on the raw signal:

**For Logs:**
- **Log template/pattern mining**: Algorithms like Drain extract templates, then detect new/unseen patterns (not just frequency changes). Drain groups logs by length and token prefix into a parse tree.
- **Semantic vector analysis**: NLP/embedding-based approaches encode log messages as vectors, detect semantic anomalies. This is gaining ground with LLMs.
- **Sequential analysis**: Detect anomalous sequences of log events (e.g., event A always follows B, but suddenly doesn't).

**For Traces:**
- **Structural/graph analysis**: Recent research (TraceGra, GTrace, ServiceAnomaly) represents traces as DAGs and uses graph neural networks to detect structural anomalies -- when the call graph itself changes shape, not just when latency changes.
- **Group-wise detection**: GTrace categorizes traces by shared sub-structure, detecting when a trace's structure deviates from its group.
- **Combined trace-log analysis**: DeepTraLog combines trace structure with log content for multi-modal detection.

**Important nuance:** These non-metric approaches are primarily research-stage or used by the most sophisticated platforms (Dynatrace). For pragmatic, production-ready systems, the "derive a metric, baseline the metric" pattern remains the standard.

Sources:
- [TraceGra: Graph Deep Learning for Traces](https://www.sciencedirect.com/science/article/abs/pii/S0140366423001135)
- [GTrace: Group-wise Trace Anomaly Detection (ESEC/FSE 2023)](https://dl.acm.org/doi/10.1145/3611643.3613861)
- [DeepTraLog: Trace-Log Combined Detection](https://cspengxin.github.io/publications/icse22-DeepTraLog.pdf)
- [AIOps Log Anomaly Detection: Systematic Review](https://www.sciencedirect.com/science/article/pii/S2667305325001346)

---

## 3. State of the Art for Simple, Pragmatic Anomaly Detection

### The "Good Enough" Tier

Based on practitioner experience from Booking.com, Tinybird, Grafana Labs, and the broader SRE community, here are the proven simple approaches ranked by pragmatism:

#### Tier 1: Start Here (Simplest, Most Proven)

**1. Z-Score with Sliding Window**
- Formula: `z = (x - mean) / stddev` over a recent window (e.g., 30 minutes)
- Threshold: +/- 2 to 3 standard deviations
- Pros: Dead simple, well-understood, fast to compute
- Cons: Sensitive to outliers in the window, assumes roughly normal distribution
- Used by: Grafana adaptive strategy (with smoothing), most custom implementations

**2. Percentile/Quantile Bands**
- Compare current value against historical percentiles (e.g., 5th and 95th)
- Booking.com found this "worked surprisingly well" with 4-5 weeks of same-day/time history
- Pros: No distribution assumptions, intuitive, handles skewed data
- Cons: Needs more historical data, slower to adapt
- Used by: Datadog (Basic algorithm), Splunk ITSI

**3. Moving Average + Standard Deviation Bands**
- Compute rolling mean and stddev, flag values outside N stddev
- Essentially z-score but explicitly framed as bands
- Used by: Grafana promql-anomaly-detection framework (adaptive strategy)

#### Tier 2: Worth the Complexity (Better, Still Simple)

**4. Median + MAD (Median Absolute Deviation)**
- Formula: `modified_z = 0.6745 * (x - median) / MAD`
- MAD = median of absolute deviations from the median
- Pros: Robust to outliers (the median is not pulled by extremes), works with non-normal data
- Cons: Less sensitive to subtle shifts, can miss gradual degradation
- Used by: Grafana promql-anomaly-detection framework (robust strategy)
- **Recommended when data is spiky or has fat tails**

**5. Seasonal Decomposition (Simple)**
- Compare current value to same hour/day-of-week from previous weeks
- Booking.com uses 4-5 weeks of same-weekday data as baseline
- Pros: Handles daily/weekly patterns naturally
- Cons: Needs weeks of history, cold-start problem
- Used by: Datadog (Agile/Robust), most enterprise platforms

**6. IQR (Interquartile Range)**
- Anomaly if value < Q1 - 1.5*IQR or > Q3 + 1.5*IQR
- Pros: Distribution-free, classic, robust
- Cons: Static (needs windowing for time series)

#### Tier 3: Slightly More Complex (Only If Needed)

**7. Holt-Winters Exponential Smoothing**
- Triple exponential smoothing with level, trend, and seasonal components
- Mentioned in Kafka monitoring context for lag and consumption rates
- Pros: Handles trend + seasonality, well-studied
- Cons: More parameters to tune, more complex than z-score

**8. Isolation Forest**
- Tree-based: anomalies are isolated quickly because they're different from the bulk
- Pros: Works in high dimensions, no distribution assumptions, low computational complexity
- Cons: Batch-oriented (not great for streaming), harder to explain

### The Critical Insight from Practitioners

**"Detecting the anomaly itself is actually not that difficult. The hard part is understanding what it means."** -- Booking.com Engineering

Booking.com, after extensive production experience, recommends:
1. **Decompose metrics into sub-dimensions** (region, device type, etc.) for diagnosis
2. **Express anomalies in business terms** ("lost N orders") not statistical values
3. **Build simulation interfaces** to test parameters before deployment
4. **Handle known events** (holidays, campaigns) with correction factors
5. **Filter past anomalies** from baseline computation to prevent distortion

Sources:
- [Simple Statistics for Anomaly Detection (Tinybird)](https://www.tinybird.co/blog/anomaly-detection)
- [Anomaly Detection Using Statistical Analysis (Booking.com)](https://medium.com/booking-com-development/anomaly-detection-in-time-series-using-statistical-analysis-cc587b21d008)
- [Effective Anomaly Detection Using Basic Statistics (RisingWave)](https://risingwave.com/blog/effective-anomaly-detection-in-time-series-using-basic-statistics/)
- [Moving Z-Score vs Moving IQR](https://medium.com/@kis.andras.nandor/detecting-time-series-anomalies-moving-z-score-vs-moving-iqr-70754d853105)
- [MAD vs Z-Score for Outlier Detection](https://hausetutorials.netlify.app/posts/2019-10-07-outlier-detection-with-median-absolute-deviation/)
- [Grafana promql-anomaly-detection](https://github.com/grafana/promql-anomaly-detection)

---

## 4. LGTM Stack Specifically

### Built-In Anomaly Detection Capabilities

#### Grafana Cloud (Commercial)

**Grafana Machine Learning (ML App):**
- Metric forecasting: Learns historical patterns, predicts future values, creates dynamic upper/lower bounds
- Captures daily and weekly seasonality automatically
- Adaptive alerting: Alert when metric goes out of predicted bounds instead of tuning static thresholds
- Automatic baseline: Shows anomaly band with lower/upper thresholds based on historic standard deviation

**Adaptive Traces (for Tempo data):**
- Enabled by default -- zero configuration
- Learns "normal" patterns (e.g., typical latency for specific database queries)
- Monitors incoming traces for significant deviations from baseline
- When anomaly detected, temporarily increases sampling of relevant traces and surfaces them
- Based on the Asserts.ai acquisition technology

**Adaptive Telemetry Suite:**
- Analyzes how telemetry is used, recommends optimizations
- Classifies and prioritizes telemetry data
- Helps reduce noise by ensuring only valuable data is stored and surfaced

#### Grafana OSS / Self-Hosted (promql-anomaly-detection Framework)

**This is the most relevant for self-hosted LGTM stacks.** It is an open-source framework requiring only Prometheus/Mimir -- no external ML systems.

**Architecture:**
1. **Recording rules** generate anomaly bands (upper/lower bounds) for each time series
2. **Alerting rules** fire when time series persistently cross the bands

**Two strategies:**
- **Adaptive (default):** Mean + standard deviation with 26h smoothing and high-pass filter. Best for detecting short-term changes while minimizing false positives on recurring events. Assumes roughly normal data.
- **Robust:** Median + MAD (median absolute deviation). Better for spiky or non-normally distributed metrics. Better for longer-term change detection.

**Three band types:**
- Short-term bands: Expand based on variability within ~24-26h
- Long-term bands: Incorporate seasonality for daily/weekly patterns
- Margin bands: Minimum band width when variability is too low

**Configuration labels:**
- `anomaly_name`: Unique metric identifier
- `anomaly_strategy`: Algorithm selection (adaptive/robust)
- `anomaly_type`: Metric-specific thresholds (requests, latency, errors, resource)

**Key advantage:** Works with any Prometheus-compatible system. No external dependencies. Pure PromQL.

#### Cross-Signal Anomaly Detection in LGTM

**There is no built-in cross-signal correlation in the OSS LGTM stack.** This is a gap.

- Grafana provides visualization of all signals on the same dashboard
- Exemplars link metrics to traces
- Loki labels can be correlated with Tempo trace IDs
- But automated "anomaly in metric X correlates with log pattern Y and trace latency Z" does not exist natively
- Grafana Cloud's commercial ML features partially address this
- For self-hosted, this is a build-it-yourself concern

Sources:
- [Grafana promql-anomaly-detection GitHub](https://github.com/grafana/promql-anomaly-detection)
- [Grafana ML Forecasting Documentation](https://grafana.com/docs/grafana-cloud/machine-learning/dynamic-alerting/forecasting/)
- [Investigate Anomalies (Adaptive Traces)](https://grafana.com/docs/grafana-cloud/adaptive-telemetry/adaptive-traces/manage-recommendations/investigate-anomalies/)
- [Application Observability Automatic Baseline](https://grafana.com/docs/grafana-cloud/monitor-applications/application-observability/manual/automatic-baseline/)
- [Anomaly Detection for Grafana: A Primer (Eyer)](https://www.eyer.ai/blog/anomaly-detection-for-grafana-a-primer/)
- [How to Implement Anomaly Detection in Grafana](https://oneuptime.com/blog/post/2026-01-27-anomaly-detection-grafana/view)

---

## 5. Topology Enrichment of Anomalies

### How Leading Platforms Connect Anomalies to Topology

#### Dynatrace: The Gold Standard

**Smartscape** is a real-time, continuously-updated dependency graph that:
- Auto-discovers all components (processes, hosts, services, applications)
- Maps dependencies automatically across hybrid/multicloud
- Serves as the "single source of truth" for topology

**Davis AI + Smartscape integration:**
- Anomaly detection is topology-aware from the start (not post-hoc enrichment)
- When anomaly detected, Davis follows dependency chains through Smartscape
- The "Problem Graph" shows root cause + blast radius on the topology
- Fault-tree analysis walks vertical (host->process->service->app) and horizontal (service-to-service) topology

**Key insight:** In Dynatrace, **topology is used at detection time, not just enrichment time.** Davis analyzes thousands of topologically-related metrics per component simultaneously. This means an anomaly in service A is immediately contextualized against the health of its dependencies.

#### New Relic: Issue Maps

- Issue Maps visualize upstream/downstream entities affected by incidents
- Display infrastructure context: hosts, owners, regions, environments
- Interactive: clicking entities shows details, hovering shows dependencies
- Applied Intelligence correlates related incidents into unified issues
- Enriches with datastore analysis, error analysis, stack traces, external service calls

#### Datadog: Correlation-Based

- Metric Correlations surface related metric anomalies across infrastructure
- Watchdog Explains analyzes dimensional tags to isolate root cause
- Predictive correlations identify relationships without explicit dependency maps
- Less topology-centric than Dynatrace; more statistical correlation

#### ServiceNow: CMDB-Driven

- Maps alerts to business services, teams, and ownership using CMDB
- Events are enriched with topology, service, owner, and priority context
- Root cause agents model dependencies as directed graphs
- Follows: gather alerts -> enrich -> find related symptoms -> suggest root cause -> execute remediation

### Detection Time vs. Enrichment Time

| Platform | When Topology Is Used | Approach |
|----------|----------------------|----------|
| Dynatrace | **Detection time** | Topology-aware baselining and analysis |
| New Relic | Enrichment + visualization | Issue Maps assembled after detection |
| Datadog | Enrichment time | Correlations computed post-detection |
| ServiceNow | Enrichment time | CMDB mapping applied to raw alerts |
| Grafana (OSS) | Neither (manual) | No built-in topology-aware detection |

### Data Models Used

**Dynatrace Smartscape:** Real-time entity graph with typed relationships. Layers: datacenter/cloud -> hosts -> processes -> services -> applications. Automatically maintained via OneAgent discovery.

**ServiceNow CMDB:** Configuration Items (CIs) with relationship records. Traditional CMDB model enriched with auto-discovery.

**OpenTelemetry Resource Model:** Resource attributes on every telemetry signal. `service.name` (required), plus optional: `service.namespace`, `service.version`, `host.name`, `k8s.pod.name`, `cloud.region`, etc. Traces inherently carry dependency information through span parent-child relationships. The OTel Collector's `resourcedetection` processor can auto-enrich with infrastructure metadata.

**Knowledge Graphs (Research):** Recent research proposes dynamic knowledge graphs for context-aware anomaly detection in microservices, capturing evolving system state beyond static topology.

Sources:
- [Dynatrace Smartscape](https://www.dynatrace.com/platform/application-topology-discovery/smartscape/)
- [Dynatrace Root Cause Analysis Concepts](https://docs.dynatrace.com/docs/dynatrace-intelligence/root-cause-analysis/concepts)
- [New Relic Next Gen AIOps](https://newrelic.com/blog/how-to-relic/next-gen-ai-ops)
- [ServiceNow Observability Bridge](https://thrupthitech.blogspot.com/2025/08/how-servicenow-supercharges.html)
- [OpenTelemetry Resource Semantic Conventions](https://opentelemetry.io/docs/specs/semconv/resource/)
- [Context-Aware Anomaly Detection Using Dynamic Knowledge Graphs](https://www.researchgate.net/publication/399712228_Towards_Context-Aware_Anomaly_Detection_for_AIOps_in_Microservices_Using_Dynamic_Knowledge_Graphs)
- [Selector AI: CMDB and AIOps](https://www.selector.ai/blog/modern-network-observability-device-discovery-cmdb-and-aiops/)

---

## 6. Critical Anti-Patterns and Lessons Learned

### The Sobering Reality of Anomaly Detection

**The most important finding from this research:**

> "Anomaly detection in software is, and always will be, an unsolved problem." -- John Allspaw, former CTO of Etsy

A comprehensive analysis by Quesma found that despite major vendors launching anomaly detection features between 2013-2016:
- By 2021, only **12% of SREs used it regularly**
- Only **7.5% found it valuable**
- **40% never used it at all**

The Lacework cautionary tale: Polygraph technology promised rule-free cloud activity analysis, raised $1.9B, reached $8.3B valuation, then failed to work reliably -- fire-sold for $200-230M.

### Anti-Pattern 1: "Detect All Anomalies, Then Filter"

**Problem:** Real production systems generate enormous numbers of benign anomalies. Algorithms detect them easily, but most are unimportant, leading to a flood of false positives.

**Evidence:** PagerDuty's 2025 report: average on-call engineer receives ~50 alerts/week, but only 2-5% require human intervention. Catchpoint 2024: 70% of SRE teams report alert fatigue as top-three concern. Google Cloud: 53% of alerts are false positives.

**Instead:** Start with a small number of well-understood, high-signal metrics. Expand gradually.

### Anti-Pattern 2: "One Algorithm Fits All Metric Types"

**Problem:** Different metrics have fundamentally different characteristics:
- Counters (monotonically increasing) vs. gauges (fluctuating values)
- Bounded metrics (CPU 0-100%) vs. unbounded (request latency)
- Seasonal metrics (traffic) vs. non-seasonal (error rates during incidents)
- High-cardinality (per-endpoint) vs. low-cardinality (cluster-wide)

**Evidence:** Splunk ITSI moved from a single anomaly detection engine to offering multiple methods (standard deviation, range, percentage, quantile) because no single approach worked universally. Academic benchmarks show contradictory algorithm rankings -- LSTM-AD ranks highly in one survey, mid-tier in another, while simpler k-means outperforms it.

**Instead:** Classify metrics by type and apply appropriate methods. Grafana's `anomaly_type` label (requests, latency, errors, resource) is a good model.

### Anti-Pattern 3: "Sophisticated ML from Day One"

**Problem:** Complex ML models are harder to debug, explain, and trust. When an alert fires at 2 AM, operators need to understand why.

**Evidence:** The biggest winners -- Datadog, Wiz -- were initially light on AI. The Quesma analysis found that narrowly-scoped ML features that succeeded were so basic they stopped being marketed as "AI": log pattern grouping, automated threshold setting, predictive resource exhaustion. Academic research confirms "very simple baselines can not only match, but even outperform complex deep learning solutions."

**Instead:** Start with z-score/MAD/percentile bands. Add complexity only when you can demonstrate the simple approach fails on specific, identified cases.

### Anti-Pattern 4: "Ignoring the Cold-Start Problem"

**Problem:** Statistical baselines need history. New services, new metrics, and new deployments have no baseline.

**Evidence:** Booking.com found they needed 4-5 weeks of same-weekday data for reliable percentile-based detection. Elastic ML jobs default to 4 weeks of historical analysis.

**Instead:** Have an explicit cold-start strategy: use static thresholds or peer-group comparison until sufficient history exists. Grafana's margin bands (minimum band width) address this partially.

### Anti-Pattern 5: "Treating Anomaly Detection as a Pure Signal Processing Problem"

**Problem:** Whether something is anomalous depends on context, not just the data. A deployment causes metric changes that are expected. A Black Friday traffic spike is normal.

**Evidence:** The 2025 paper "Open Challenges in Time Series Anomaly Detection: An Industry Perspective" (arXiv:2502.05392) argues that "whether an event constitutes an anomaly depends on context, not intrinsic data properties." They found human domain knowledge essential and that purely signal-based anomaly determination may be fundamentally insufficient.

**Instead:** Build in context signals: deployment markers, known events, maintenance windows. Support human feedback loops.

### Anti-Pattern 6: "Batch-Evaluated Algorithms in Streaming Contexts"

**Problem:** Most academic benchmarks use batch evaluation (fit on complete data). Production systems operate in streaming mode (only prior data available).

**Evidence:** The arXiv industry perspective paper found that current benchmarks "provide little guidance for practitioners" because they evaluate fundamentally different scenarios than production use. Fixed threshold selection especially requires full data + ground truth -- impossible in streaming.

**Instead:** Ensure your detection approach works online/streaming. Z-score with sliding window, rolling percentiles, and exponential smoothing all work natively in streaming.

### What Practitioners Actually Recommend

1. **RED metrics first**: Rate, Errors, Duration. These consistently outperform ML-based approaches for service health.
2. **P99 latency**: 99th percentile monitoring is the single most effective trace-derived metric.
3. **Start with static thresholds**: Graduate to dynamic baselines only for metrics that clearly need them.
4. **Invest in context, not algorithms**: Topology, deployment events, ownership -- these matter more than detection sophistication.
5. **Decompose before detecting**: Break aggregate metrics into dimensions (service, region, endpoint) before applying anomaly detection.
6. **Make alerts actionable**: Anomaly detection is only valuable if it triggers a clear investigation path.

Sources:
- [Lessons from Pre-LLM AI in Observability (Quesma)](https://quesma.com/blog/aiops-observability/)
- [Open Challenges in Time Series Anomaly Detection: Industry Perspective](https://arxiv.org/html/2502.05392v1)
- [Alert Fatigue and AI (OneUptime)](https://oneuptime.com/blog/post/2026-03-05-alert-fatigue-ai-on-call/view)
- [ML Anomaly Detection in Observability (FusionReactor)](https://fusion-reactor.com/blog/machine-learning-anomaly-detection-transforming-modern-observability-2024-guide/)
- [AI Anomaly Detection Deep Dive (Edge Delta)](https://edgedelta.com/company/blog/ai-anomaly-detection)

---

## 7. Synthesis: Implications for Metric-Agnostic Design

### What the Industry Evidence Tells Us

1. **"Derive a metric, baseline the metric" IS the right foundational pattern.** Every major platform does this. Non-metric detection methods exist but are research-stage or very specialized.

2. **Metric-agnostic does not mean algorithm-agnostic.** Different metric types need different treatment. The minimum viable classification: counter vs. gauge, seasonal vs. non-seasonal, bounded vs. unbounded.

3. **Z-score / MAD with sliding window is the proven "good enough" starting point.** Grafana's open-source framework validates this with two strategies: adaptive (mean/stddev) and robust (median/MAD).

4. **Topology enrichment is critical but can be decoupled from detection.** Most platforms (except Dynatrace) do detection first, enrichment second. This is architecturally simpler and pragmatically sufficient.

5. **The real battle is false positive management, not detection sensitivity.** Every practitioner source emphasizes this. Start conservative, expand scope gradually.

6. **Seasonality handling is the first meaningful upgrade from basic z-score.** When simple z-score fails, it is almost always because of daily/weekly patterns. Same-weekday comparison (Booking.com pattern) is the simplest fix.

7. **The OSS LGTM stack has real gaps in cross-signal correlation and topology-aware detection.** This is an area where a custom AIOps platform can add significant value.

### For the Kafka Telemetry Use Case Specifically

Kafka metrics (messages/sec, consumer lag, throughput) map well to this pattern:
- **Messages/sec**: Gauge, often seasonal (business hours), baseline with z-score + weekday comparison
- **Consumer lag**: Gauge, typically non-seasonal but spiky, MAD may be more appropriate
- **Throughput (bytes/sec)**: Gauge, often correlated with messages/sec, seasonal
- **Under-replicated partitions**: Counter/gauge, typically near-zero, static threshold may be better than statistical baseline
- **ISR shrink rate**: Event-like, static threshold or rate-of-change detection

The "derive a metric, baseline the metric" approach directly applies. The key design decision is whether to classify metrics and apply different strategies (Grafana model) or use a single robust method (MAD) for everything.
