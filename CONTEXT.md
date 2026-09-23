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

**Infrastructure scope**:
The identity of the thing that moves data, used as a case key: a Kafka scope (env, cluster and topic) for E2, a job scope for an IDP feed.
_Avoid_: Kafka scope (when the family is meant), source (which is where data enters, not what carries it)

**Case**:
The triaged unit a human acts on, keyed on an infrastructure scope or a root dataset, gathering the findings of one incident with their blast radius.
_Avoid_: Ticket, alert

**Recurrence**:
A later verdict on a series whose case is already open; it is added to that case rather than raising a new one.
_Avoid_: Duplicate, re-fire

### Landscape

**E2**:
The Kafka ingestion platform. It writes topic data into its own repository, from which a dbt job copies it into bronze.

**IDP**:
The batch ingestion platform. It copies files from upstream sources and loads them directly into bronze.

**Zone**:
One stage of the medallion architecture that data passes through: bronze, silver, gold, then hosting.
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

**Source mapping**:
The link from a source to its landing table, the one hop dbt lineage does not cover.
_Avoid_: Topic mapping, lineage (for this hop)

**Root dataset**:
The most upstream dataset in a case that is itself anomalous; a dataset-keyed case is keyed on it.
_Avoid_: Source dataset, origin table

**Blast radius**:
The datasets downstream of a root dataset along lineage, listed on its case as impact rather than raised as cases of their own.
_Avoid_: Affected tables, impact set

**Dataset owner**:
The team accountable for a dataset; a case whose root is a dataset goes to them, a case whose root is infrastructure goes to platform on-call.
_Avoid_: Data steward, producer
