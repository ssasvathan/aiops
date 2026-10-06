# AIOps Triage

Detects anomalies in operational and data-quality signal and turns them into triaged cases. This glossary fixes the vocabulary shared by the metric path (Kafka/Prometheus) and the data-quality path (dbt/Elementary/OpenLineage).

## Language

### Signal

**Series**:
A stream of timestamped numeric values sharing one stable identity; the thing a baseline is computed over.
_Avoid_: Metric (when the kind is not meant), time series (when it is irregular)

**Observation**:
One timestamped value in a series, stamped with the time it describes rather than the time it was processed.
_Avoid_: Sample, data point, reading

**Metric series**:
A series sampled on a fixed cadence from operational telemetry, identified by a metric key and a scope such as env, cluster and topic.
_Avoid_: DQ metric

**Series kind**:
A class of series sharing one set of detection properties — bucket width, expected cadence, minimum history and gating. The unit the detector is configured against, so that supporting a new class of signal is a registration rather than a change to the detector.
_Avoid_: Series type, signal type, metric type

**Deviation episode**:
One continuous stretch of a metric series being anomalous, carrying a first and last observation time; the unit a metric finding is raised on. Distinct from a single anomalous observation, of which an episode holds many.
_Avoid_: Deviation, breach, spike, firing

**DQ measurement series**:
A series of values measured on a dataset or column once per run (row count, null percentage, freshness lag), arriving irregularly but with an expected cadence.
_Avoid_: Check series, DQ metric, monitor series

**Measurement**:
One observation in a DQ measurement series.
_Avoid_: DQ metric, monitor result

**Check**:
A pass/fail assertion someone wrote against a dataset, such as a dbt test. Its result is carried as context on a case, not baselined.
_Avoid_: Test (outside dbt-specific discussion), assertion, rule

**Silence**:
An expected measurement that has not arrived within its series' expected cadence, meaning the job that would have produced it did not run. Distinct from a freshness anomaly, which is a measurement that did arrive and shows the data is old.
_Avoid_: Staleness, missing data, gap

### Case

**Verdict**:
A detector's judgement that a measurement is anomalous, made where the data lives and received by the pipeline rather than computed by it.
_Avoid_: Alert, test failure

**Finding**:
One anomaly the pipeline reports, on one series, with the evidence behind it.
_Avoid_: Incident, alert

**Correlation window**:
The span of time in which a metric deviation episode counts as a candidate cause of a measurement's anomaly: the measurement's own bucket interval, extended backwards by a lead-in margin. It filters candidates already linked by a source mapping; it never establishes the link itself.
_Avoid_: Lookback, time window, join window, co-occurrence window

**Lead-in margin**:
The single duration by which a correlation window extends before a measurement's bucket start, covering the gap between ingestion failing and the bucket it damaged beginning.
_Avoid_: Tolerance, grace period, slack, buffer

**Infrastructure scope**:
The identity of the thing that moves data, used as a case key: a Kafka scope (env, cluster and topic) for E2, a job scope for an IDP feed.
_Avoid_: Kafka scope (when the family is meant), source (which is where data enters, not what carries it)

**Case**:
The triaged unit a human acts on, keyed on an infrastructure scope, a root dataset, or an environment and cluster, gathering the findings of one incident with their blast radius.
_Avoid_: Ticket, alert

**Storm case**:
A case keyed on an environment and cluster, gathering the scope-keyed cases that fired together in one window. Its children attach to it rather than notifying separately, and it closes when they have.
_Avoid_: Incident, rollup, parent case

**Recurrence**:
A later verdict on a series whose case is already open; it is added to that case rather than raising a new one.
_Avoid_: Duplicate, re-fire

### Landscape

**E2**:
The Kafka ingestion platform. It writes topic data into its own repository, from which a dbt job copies it into bronze.

**IDP**:
The batch ingestion platform. It copies files from upstream sources and loads them directly into bronze.

**Zone**:
One stage of the medallion architecture that data passes through: bronze, silver, gold, then hosting. E2's own Snowflake schema sits outside the medallion and is not a zone.
_Avoid_: Layer, tier

**Bronze**:
The first medallion zone; raw data as delivered by E2 (via dbt) or IDP.
_Avoid_: Staging, raw zone

**Silver**, **Gold**:
The intermediate medallion zones that dbt builds from bronze.

**Hosting zone**:
The zone outside gold that consumers read from. Its contents are also delivered to other platforms (Databricks, the on-prem lakehouse).
_Avoid_: Serving layer, consumption zone

### Linking

**Source**:
Where data enters the warehouse: a Kafka topic (through E2) or an IDP feed.
_Avoid_: Upstream (when the ingestion entry point is meant)

**Landing table**:
The first table a source's data lands in: an E2 repository table for a Kafka topic, a bronze table for an IDP feed. The point where source identity and dataset identity meet.
_Avoid_: Raw table, sink table, staging table

**Load timestamp**:
The column recording when a row arrived in a table, stamped by whatever wrote it. Every monitored dataset buckets its measurements on this rather than on a business event time, so a short bucket means ingestion underdelivered rather than that fewer events occurred.
_Avoid_: Ingest timestamp, timestamp column, created_at, event time (which is the opposite)

**Consumer table**:
The table inside E2's own Snowflake schema that E2 exposes for reading, built from a landing table. The downstream half of E2's declared graph.
_Avoid_: Output table, serving table, gold table

**Source mapping**:
The link from a source to its landing table, the one hop dbt lineage does not cover.
_Avoid_: Topic mapping, lineage (for this hop)

**Root dataset**:
The most upstream *monitored* dataset in a case that is itself anomalous; a dataset-keyed case is keyed on it. Monitoring coverage therefore determines routing accuracy: a defect introduced in an unmonitored zone surfaces as a root further downstream than its true cause.
_Avoid_: Source dataset, origin table

**Transform-suspected case**:
A case whose root dataset has a monitored ancestor that is not anomalous, meaning the cause lies in an unmonitored zone between them. It is not routed to the root's owner.
_Avoid_: Unknown root, orphan case

**Blast radius**:
The datasets downstream of a root dataset along lineage, listed on its case as impact rather than raised as cases of their own.
_Avoid_: Affected tables, impact set

**Dataset owner**:
The team accountable for a dataset; a case whose root is a dataset goes to them, a case whose root is infrastructure goes to platform on-call.
_Avoid_: Data steward, producer
