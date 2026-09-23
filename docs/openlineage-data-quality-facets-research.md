# OpenLineage Data Quality Facets: What Signal Is Actually Available for Anomaly Detection

**Date:** 2026-09-07
**Question:** OpenLineage data quality facets — what signal is actually available for anomaly detection from batch and streaming jobs?

**Sourcing note.** Every claim below is cited to a primary source: the OpenLineage spec repo
(`github.com/OpenLineage/OpenLineage`, read from a shallow clone of `main` on 2026-09-07 —
`integration/dbt/pyproject.toml` reports `version = "1.54.0"`), the docs bundled in that repo under
`website/docs/`, the live `openlineage.io/docs` site, dbt's published JSON schemas at
`schemas.getdbt.com`, dbt's own docs at `docs.getdbt.com`, and first-party repos (Marquez,
elementary-data). Where something is an inference rather than a statement in a source, it is
labelled **(inference)**. Where a source could not be found, it says **not found** rather than
guessing. Non-primary sources are labelled inline.

Repo file paths below are relative to the OpenLineage repo root unless otherwise stated.

---

## 1. Which standard facets carry data-quality signal?

The full list of facet schemas lives in `spec/facets/*.json`. Five carry usable DQ / volume signal.

### 1.1 `dataQualityAssertions` — `spec/facets/DataQualityAssertionsDatasetFacet.json`

`$id: https://openlineage.io/spec/facets/1-1-0/DataQualityAssertionsDatasetFacet.json`.
It extends **`InputDatasetFacet`** (i.e. it belongs under `inputs[].inputFacets`, not `inputs[].facets`):

```json
"allOf": [
  { "$ref": "https://openlineage.io/spec/2-0-2/OpenLineage.json#/$defs/InputDatasetFacet" },
  { "type": "object",
    "required": ["assertions"],
    "properties": { "assertions": { "type": "array", "items": { "type": "object", ... } } } } ]
```

Per-assertion fields, verbatim from the schema (`required: ["assertion", "success"]`):

| Field | Type | Required | Schema description (quoted) |
|---|---|---|---|
| `assertion` | string | **yes** | "Classification of the test, e.g. 'not_null', 'unique', 'row_count', 'freshness', 'custom_sql'." |
| `success` | boolean | **yes** | "Whether the test found issues: 'true' (no issues found), 'false' (issues found). Independent of severity - a test can fail without blocking the pipeline when severity is 'warn'." |
| `column` | string | no | "Column that test refers to. It should match the name provided in SchemaDatasetFacet. If column field is empty, then test refers to whole dataset." |
| `severity` | string | no | "The configured severity level of the assertion. Common values are 'error' ... or 'warn' ..." |
| `name` | string | no | "Name identifying the test." |
| `description` | string | no | "Human-readable description of what the assertion checks." |
| `expected` | string | no | "The expected value or threshold for the assertion, **serialized as a string**." |
| `actual` | string | no | "The actual value observed during the assertion, **serialized as a string**." |
| `content` | string | no | "The assertion body, e.g. a SQL query or expression." |
| `contentType` | string | no | "The format of the content field ... Common values include 'sql', 'json', 'expression'." |
| `params` | object (`additionalProperties: true`) | no | "Arbitrary key-value pairs for assertion-specific inputs." |

**No units, no numeric types.** `expected`/`actual` are `"type": "string"` — a consumer must parse
them itself and has no declared unit or semantic. `expected`/`actual`/`severity`/`params` are new in
facet version `1-1-0`; older emitters produce only `assertion`/`success`/`column`
(cf. `website/static/spec/facets/1-0-0/DataQualityAssertionsDatasetFacet.json` … `1-0-2/`, which are
kept alongside `1-1-0/` in the repo).

### 1.2 `dataQualityMetrics` — two schemas, same body

There are **two** files with the same `$defs` body and the same output key `dataQualityMetrics`:

- `spec/facets/DataQualityMetricsInputDatasetFacet.json` — `$id .../1-0-3/...`, extends `InputDatasetFacet`.
- `spec/facets/DataQualityMetricsDatasetFacet.json` — `$id .../1-0-0/...`, extends `DatasetFacet`.

Both declare `"required": ["columnMetrics"]`:

```json
"required": ["columnMetrics"],
"properties": {
  "rowCount":    { "description": "The number of rows evaluated", "type": "integer" },
  "bytes":       { "description": "The size in bytes", "type": "integer" },
  "fileCount":   { "description": "The number of files evaluated", "type": "integer" },
  "lastUpdated": { "description": "The last time the dataset was changed",
                   "type": "string", "format": "date-time" },
  "columnMetrics": {
    "description": "The property key is the column name",
    "type": "object",
    "additionalProperties": {
      "type": "object",
      "properties": {
        "nullCount":     { "description": "The number of null values in this column for the rows evaluated", "type": "integer" },
        "distinctCount": { "description": "The number of distinct values in this column for the rows evaluated", "type": "integer" },
        "sum":           { "description": "The total sum of values in this column for the rows evaluated", "type": "number" },
        "count":         { "description": "The number of values in this column", "type": "number" },
        "min":           { "type": "number" },
        "max":           { "type": "number" },
        "quantiles":     { "description": "The property key is the quantile. Examples: 0.1 0.25 0.5 0.75 1",
                           "type": "object", "additionalProperties": { "type": "number" } }
      } } } }
```

Notes:
- **`columnMetrics` is the only required member.** `rowCount`, `bytes`, `fileCount`, `lastUpdated`
  are all optional. So a valid facet can be `{"columnMetrics": {}}` with no numbers at all.
- Per-column metrics are all optional, untyped as to unit. `min`/`max` have no description at all.
- `bytes` here vs `size` in `outputStatistics` — inconsistent naming across facets.
- `lastUpdated` is the only timestamp any DQ facet carries.

### 1.3 `columnMetrics`

**There is no standalone `columnMetrics` facet.** `columnMetrics` exists only as a *property* of the
two `dataQualityMetrics` schemas above. Confirmed by listing `spec/facets/` — no
`ColumnMetrics*.json` exists.

### 1.4 `outputStatistics` — `spec/facets/OutputStatisticsOutputDatasetFacet.json`

`$id .../1-0-2/...`, extends `OutputDatasetFacet` (lives under `outputs[].outputFacets`). **Nothing is
required** — there is no `required` key in the object at all:

```json
"properties": {
  "rowCount":  { "description": "The number of rows written to the dataset", "type": "integer" },
  "size":      { "description": "The size in bytes written to the dataset", "type": "integer" },
  "fileCount": { "description": "The number of files written to the dataset", "type": "integer" }
}
```

### 1.5 `inputStatistics` — `spec/facets/InputStatisticsInputDatasetFacet.json`

`$id .../1-0-0/...`, extends `InputDatasetFacet`, also with no required fields:
`rowCount` ("The number of rows read"), `size` ("The size in bytes read"), `fileCount`
("The number of files read"), all `"type": "integer"`.

### 1.6 `test` (TestRunFacet) — `spec/facets/TestRunFacet.json`

`$id .../1-0-1/...`, a **run** facet keyed `test`, "Results of test executions associated with this
run, capturing test outcomes and configured severities independently of dataset attribution."
`required: ["tests"]`; each `TestExecution` has `required: ["name", "status"]` and optional
`severity`, `type`, `description`, `expected` (string), `actual` (string), `content`, `contentType`,
`params`. It is the run-level mirror of `dataQualityAssertions`; `status` is
`'pass' | 'fail' | 'skip'` rather than a boolean, so **it can express "skipped"** where
`dataQualityAssertions.success` cannot (see §6).

### 1.7 Vendor facets with genuinely rich counters — `spec/registry/iceberg/`

`spec/registry/iceberg/facets/IcebergScanReportInputDatasetFacet.json` (`icebergScanReport`) and
`IcebergCommitReportOutputDatasetFacet.json` (`icebergCommitReport`). The scan report carries
`snapshotId`, `schemaId`, `projectedFieldNames`, and a `scanMetrics` object of ~16 numeric counters
(`resultDataFiles`, `totalFileSizeInBytes`, `skippedDataFiles`, `totalPlanningDuration` "Duration of
the scan in MILLISECONDS", …). These are the only facets in the whole spec where units are stated.
Documented with example payloads in `website/docs/integrations/spark/dataset_metrics.md`.

---

## 2. Spec vs reality: what each integration actually populates

Method: shallow clone of `main`, then `grep -rl` for each facet name across `integration/`,
excluding generated client code, tests, and the website's archived spec copies.

### Summary table

| Facet | Spark | Flink | dbt (`openlineage-dbt`) | Great Expectations |
|---|---|---|---|---|
| `dataQualityAssertions` | **no producer** | **no producer** | **yes** (both processors) | uses its own `greatExpectations_assertions` |
| `dataQualityMetrics` (`columnMetrics`) | **no producer** | **no producer** | **no producer** | **yes** |
| `outputStatistics` | **yes** | **no producer** | **yes** (artifact processor; conditionally in structured-logs) | no |
| `inputStatistics` | **yes**, narrowly | **no producer** | no | no |
| `icebergScanReport` / `icebergCommitReport` | **yes** (Iceberg only) | no | no | no |
| `test` (TestRunFacet) | no | no | **yes**, singular tests only | no |

### 2.1 Flink emits *no* data-quality or statistics facets at all

```
$ grep -rn "dataQuality\|DataQuality\|outputStatistics\|OutputStatistics\|inputStatistics" \
    --include=*.java integration/flink
(no matches)
$ find integration/flink -name "*FacetBuilder*.java" -path "*/main/*"
(no matches)
```

There is no facet-builder mechanism in the Flink integration at all. What Flink *does* emit is:
`jobType` (`FlinkExecutionContext.FLINK_JOB_TYPE = "JOB"`, `integration = "FLINK"`),
`processing_engine`, an ownership job facet, a custom `flink_job` facet
(`integration/flink/shared/src/main/java/io/openlineage/flink/facets/FlinkJobDetailsFacet.java`,
just the Flink job id), `errorMessage` on failure, and a custom `checkpoints` run facet.

`checkpoints` is defined at
`integration/flink/shared/src/main/java/io/openlineage/flink/client/CheckpointFacet.java` and is a
**custom** facet (`extends OpenLineage.DefaultRunFacet`, so `_schemaURL` is BaseFacet's) with five
`int` fields: `completed`, `failed`, `in-progress`, `restored`, `total`. Those are *Flink checkpoint
counters*, not data counters — nothing about rows, bytes, or column values.

**Conclusion: for a Flink job you get zero data-quality signal from OpenLineage today.** The only
continuous series available is checkpoint success/failure counts.

### 2.2 Spark: `outputStatistics` yes, `inputStatistics` narrowly, DQ facets never

`integration/spark/shared/src/main/java/io/openlineage/spark/agent/facets/builder/OutputStatisticsOutputDatasetFacetBuilder.java`
is the producer. Conditions, from the code:

```java
public boolean isDefinedAt(Object x) {
  return (x instanceof SparkListenerJobEnd) || (x instanceof SparkListenerSQLExecutionEnd);
}
...
if (!context.getActiveJobId().isPresent()) { log.warn("No jobId found in context"); return; }
if (jobMetricsHolder.containsWriteMetrics(context.getActiveJobId().get())) {
  ... .rowCount(metrics.get(Metric.WRITE_RECORDS))
      .size(metrics.get(Metric.WRITE_BYTES))
      .fileCount(metrics.get(Metric.FILES_WRITTEN))
```

So it fires only on job/SQL-execution **end**, only when an active job id is resolvable, and only
when `containsWriteMetrics` is true — defined in
`integration/spark/shared/src/main/java/io/openlineage/spark/agent/JobMetricsHolder.java` as
`records + bytes > 0`. The numbers come from Spark `TaskMetrics` aggregated per stage
(`Metric` enum: `WRITE_BYTES, WRITE_RECORDS, FILES_WRITTEN, READ_BYTES, READ_RECORDS`).

**These are engine-side task metrics, not a query of the target table.** (inference) A write that
Spark performs via a pushed-down/native path with no Spark write task metrics will silently produce
no `outputStatistics` rather than `rowCount: 0`.

`inputStatistics` has three producers, each narrow:

1. `integration/spark/app/.../lifecycle/RddExecutionContext.java` — the RDD (non-SQL) path.
   `getInputStatisticsFacet()` requires `containsReadMetrics(activeJobId)` and fills `rowCount` from
   `Metric.READ_RECORDS` / `size` from `READ_BYTES`. Critically, it is attached only when there is
   exactly one input: `.map(d -> buildInputDataset(d, withInputStatistics && inputs.size() == 1))`.
2. `integration/spark/shared/.../lifecycle/plan/LogicalRelationDatasetBuilder.java` — fills only
   `size` (from `CatalogStatistics::sizeInBytes`, else `BaseRelation::sizeInBytes`) and `fileCount`
   (from `catalogTable.ignoredProperties().get("numFiles")`, or `relation.inputFiles().length`).
   **No `rowCount`**, and these are catalog/planner *estimates* of the whole table, not rows read.
3. `integration/spark/vendor/iceberg/.../IcebergInputStatisticsInputDatasetFacetBuilder.java` —
   sums `fileSizeInBytes` and `recordCount` over the Iceberg scan's data files. Guarded by
   `x.getClass().getCanonicalName().startsWith("org.apache.iceberg.spark")` and swallows reflection
   failures (`catch (NoSuchMethodException | InvocationTargetException | IllegalAccessException e)`).

The Spark docs state the limitation directly
(`website/docs/integrations/spark/dataset_metrics.md`): *"As a limitation to this, a row count for
input datasets is collected only for DataSourceV2 api datasets."*

The complete list of Spark facet builders under `*/main/*` contains **no** DQ builder:
`OutputStatisticsOutputDatasetFacetBuilder`, `IcebergInputStatisticsInputDatasetFacetBuilder`,
`IcebergScanReportInputDatasetFacetBuilder`, `IcebergCommitReportOutputDatasetFacetBuilder`,
`SparkPropertyFacetBuilder`, `DebugRunFacetBuilder`, `ErrorFacetBuilder`, `TagsJobFacetBuilder`, etc.
Occurrences of `dataQualityMetrics` in `integration/spark` are a Javadoc comment in
`OpenLineageRunEventBuilder.java:434` and test fixtures only.

### 2.3 Great Expectations is the only first-party producer of `dataQualityMetrics`

`integration/common/src/openlineage/common/provider/great_expectations/action.py`,
`parse_data_quality_facet()` builds `facet_data["columnMetrics"][result.column_id][result.facet_key]`
from GE expectation results and returns a `DataQualityMetricsInputDatasetFacet`. `results_facet()`
attaches it under **three** keys for compatibility:

```python
return {
    "dataQuality": data_quality_facet,
    "greatExpectations_assertions": assertions_facet,
    "dataQualityMetrics": data_quality_facet,
}
```

Note it returns `None` for the whole thing if *either* the metrics or the assertions parse comes back
empty (`if not data_quality_facet: return None` / `if not assertions_facet: return None`) — so a GE
suite with only column metrics and no parseable assertions emits nothing.

The GE assertions go into a **custom** `greatExpectations_assertions` facet, not the standard
`dataQualityAssertions`.

### 2.4 dbt — see §9.

---

## 3. Batch vs streaming shape: what is a "run", and when are events emitted?

### 3.1 The spec's own rule

`spec/OpenLineage.json`, `$defs/RunEvent.eventType`:

> "the current transition of the run state. It is required to issue 1 START event and 1 of
> [ COMPLETE, ABORT, FAIL ] event per run. Additional events with OTHER eventType can be added to the
> same run. For example to send additional metadata after the run is complete"

Enum: `START, RUNNING, COMPLETE, ABORT, FAIL, OTHER`. So a run is explicitly allowed to have many
`RUNNING` events between one START and one terminal event.

### 3.2 Flink: one run per job submission; RUNNING events driven by a *polling* thread

The emitter is `integration/flink/shared/src/main/java/io/openlineage/flink/tracker/OpenLineageContinousJobTracker.java`.
It is **not** a checkpoint listener. It spawns a thread that HTTP-GETs the Flink REST API:

```java
String url = String.format("%s/%s/checkpoints", this.jobsApiUrl, context.getJobId().getFlinkJobId());
...
Thread.sleep(trackingInterval.toMillis());
while (shouldContinue) {
  ... readValue(json, Checkpoints.class)
      .filter(newCheckpoints -> latestCheckpoints.isEmpty()
              || latestCheckpoints.get().getCounts().getTotal() != newCheckpoints.getCounts().getTotal())
      .ifPresentOrElse(this::emitNewCheckpointEvent, () -> log.info("no new checkpoint found"));
  Thread.sleep(trackingInterval.toMillis());
}
```

Interval default is 60 s: `FlinkOpenLineageConfig.java` — `private static final Integer
DEFAULT_TRACKING_INTERVAL = 60;`. Documented in `website/docs/integrations/flink/configuration.md`:

> `openlineage.trackingIntervalInSeconds` — "Defines polling interval for a tracking thread to
> refresh lineage metadata from jobs API and emit it in a form of `RUNNING` OpenLineage events." — 60 (default)
>
> `openlineage.flink.disableCheckpointTracking` — "Disables checkpoint polling against the Flink jobs
> API and prevents checkpoint-driven `RUNNING` events from being emitted…" — False (default)

So: a long-running Flink job **does** produce a series of events over time (roughly one per 60 s poll
in which the checkpoint total changed). The series is *observations of checkpoint counters*, nothing
about data.

**A run = one job submission**, identified by `olContext.getRunUuid()`, held for the life of the
execution context. Sequence: `START` on submit
(`FlinkExecutionContext.onJobSubmitted`), N × `RUNNING` from the tracker, then `COMPLETE`
(`onJobCompleted`) or `FAIL` (`onJobFailed`). A restarted/resubmitted job is a new run id (inference,
from `runUuid` being a field of the per-submission context).

**Flink 1.x vs 2.x differ in whether RUNNING events carry datasets at all:**

- Flink 1.x — `FlinkExecutionContext.onJobCheckpoint` calls `buildEventForEventType(EventType.RUNNING)`,
  which does `return commonEventBuilder().inputs(inputDatasets).outputs(outputDatasets)...`. Datasets
  **are** present (but with no statistics facets).
- Flink 2.x — `OpenLineageJobStatusChangedListener.onJobCheckpoint` calls `commonEventBuilder()`
  directly, which sets only `eventTime` and `job`. **No `inputs`/`outputs` on checkpoint RUNNING
  events.** Same in `OpenLineageDetachedJobStatusChangedListener.onJobCheckpoint`.

Detached mode caveat, `website/docs/integrations/flink/flink2.md`:
> "In the default flow, you're only seeing the `START` event and no `RUNNING`, `COMPLETE`, or `FAIL`
> events afterward, which is a strong signal that your job is being submitted remotely in detached mode."

and

> "Unlike the default flow, detached job tracking does not emit an immediate `RUNNING` event right
> after `START` to avoid race conditions."

**Bottom line for §3:** a long-running Flink job gives you a usable *time series*, but the only
varying payload is `checkpoints.{completed,failed,in-progress,restored,total}`. It is effectively
one event's worth of *data* information (whatever was in START) plus a liveness/checkpoint heartbeat.

### 3.3 Spark: RUNNING events exist but the statistics only land at the end

`integration/spark/app/src/main/java/io/openlineage/spark/agent/lifecycle/SparkSQLExecutionContext.java`
emits `RUNNING` for repeated job/SQL starts (`EventType eventType = emittedOnJobStart ? RUNNING : START;`)
and for `SparkListenerStageSubmitted` / `SparkListenerStageCompleted`. But
`OutputStatisticsOutputDatasetFacetBuilder.isDefinedAt` accepts only `SparkListenerJobEnd` and
`SparkListenerSQLExecutionEnd` — so the volume numbers arrive on the terminal event, not on RUNNING.
Note also `end(SparkListenerStageCompleted)` carries the comment
`// TODO: not invoked until https://github.com/OpenLineage/OpenLineage/issues/470 is completed`.

For Spark Structured Streaming: **not found** — there is no `website/docs/integrations/spark/spark_streaming`
page (404) and no dedicated streaming event-emission doc in `website/docs/integrations/spark/`. The
integration has micro-batch *stream strategies* for dataset naming
(`KafkaMicroBatchStreamStrategy`, `KinesisMicroBatchStreamStrategy`,
`MongoMicroBatchStreamStrategy` in `shared/src/main/java/io/openlineage/spark/agent/lifecycle/plan/`),
which is about identifying the source, not about counting rows per batch. (inference) Since each
micro-batch is a separate SQL execution, each would produce its own execution-scoped events, but I
could not find a primary source stating the run-id semantics, so treat that as unverified.

---

## 4. Identity and cardinality: what can a baseline be keyed on?

### 4.1 What the spec makes required

From `spec/OpenLineage.json`:

- `Job`: `required: ["namespace", "name"]` — name is "The unique name for that job within that
  namespace", example `"myjob.mytask"`.
- `Dataset`: `required: ["namespace", "name"]` — name is "The unique name for that dataset within
  that namespace", example `"instance.schema.table"`.
- `Run`: `required: ["runId"]`, `"format": "uuid"`, "The globally unique ID of the run associated
  with the job."
- `RunEvent`: `required: ["run", "job"]`. `inputs`/`outputs` are **optional**.

So the only cross-run-stable identifiers in the core model are **`job.namespace` + `job.name`** and
**`dataset.namespace` + `dataset.name`**. `runId` is a fresh UUID per run and is useless as a
baseline key — it is the *series index*, not the series identity.

Within a facet:
- `dataQualityAssertions[].column` — "It should match the name provided in SchemaDatasetFacet."
- `dataQualityAssertions[].name` / `.assertion` — the only per-check identifiers, both free-text
  strings with no uniqueness constraint. A dataset can carry two assertions with identical
  `assertion`+`column`+`name` and nothing in the schema forbids it.
- `dataQualityMetrics.columnMetrics` — keyed by column name ("The property key is the column name").

### 4.2 Practical key candidates, in decreasing stability

| Key | Stability | Evidence |
|---|---|---|
| `dataset.namespace` + `dataset.name` | best available; changes if the table is renamed or the namespace/URI convention changes | `spec/OpenLineage.json` `$defs/Dataset`; naming rules at https://openlineage.io/docs/spec/naming (`spec/Naming.md` is marked obsolete and redirects there) |
| `+ column name` | stable while the column exists | `columnMetrics` key / `assertions[].column` |
| `job.namespace` + `job.name` | producer-dependent — see below | `$defs/Job` |
| `assertions[].assertion` + `.column` (+ `.name`) | producer-dependent, free text | `spec/facets/DataQualityAssertionsDatasetFacet.json` |
| `run.runId` | **not stable** — new UUID per run | `$defs/Run` |

Producer-specific job-name instability worth knowing about:

- **dbt artifact processor** builds `job.name` from *physical* location:
  `self._format_dataset_name(output_node["database"], output_node["schema"],
  self.removeprefix(run["unique_id"], "model."))` plus a suffix (`""`, `".build.run"`, `".snapshot"`,
  `".test"`, `".build.test"`) — `integration/common/src/openlineage/common/provider/dbt/processor.py`.
  So **the same model gets a different job name under `dbt run` vs `dbt build`.**
- **dbt structured-logs processor** uses a *different* scheme entirely: `_get_job_name` returns
  `get_node_unique_id(event)` — i.e. `model.<project>.<name>`
  (`integration/common/src/openlineage/common/provider/dbt/structured_logs.py:872-876`).
  **Switching between the two dbt modes breaks job-name continuity.**
- **Flink 2.x** uses `context.getJobId().getJobNamespace()` / `.getJobName()`
  (`OpenLineageJobStatusChangedListener.commonEventBuilder`).

**Conclusion.** Key a baseline on `(dataset.namespace, dataset.name)` — plus `column` for
column-scoped signal, plus `assertion`+`column`+`name` for a per-check series. Do **not** key on
`job.name` unless you control the producer configuration, and never on `runId`.

---

## 5. Timestamps: can observations be placed on a timeline?

### 5.1 What is guaranteed

`spec/OpenLineage.json`, `$defs/BaseEvent`: `required: ["eventTime", "producer", "schemaURL"]`, where
`eventTime` is "the time the event occurred at", `"format": "date-time"`. **Every event carries a
timestamp.** That is the only mandatory time in the model.

Optional richer time: `spec/facets/NominalTimeRunFacet.json` (`$id .../1-0-1/`) with
`nominalStartTime` (required within the facet) — "An ISO-8601 timestamp representing the nominal
start time (included) of the run. AKA the schedule time" — and optional `nominalEndTime`. This is the
facet that distinguishes *logical/business time* from wall-clock, and it is the right thing to bucket
on for scheduled batch. It is emitted by schedulers (Airflow), not by Spark/Flink/dbt.

### 5.2 What the facets themselves carry

- `dataQualityAssertions`: **no timestamp field at all.** The observation's only time is the enclosing
  event's `eventTime`.
- `dataQualityMetrics`: optional `lastUpdated` ("The last time the dataset was changed",
  `format: date-time`) — this is dataset mtime, *not* the observation time.
- `outputStatistics` / `inputStatistics`: no timestamps.

### 5.3 Producer-specific gotcha: dbt test events are stamped at *emission* time

`integration/common/src/openlineage/common/provider/dbt/processor.py`, `parse_test()`:

```python
def parse_test(self, context: DbtRunContext, nodes: dict) -> DbtEvents:
    # The tests can have different timings, so just take current time
    started_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
    completed_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
```

Both START and COMPLETE for **every** dbt test event carry the same wall-clock instant — the moment
`dbt-ol` post-processed `run_results.json`, not when the test ran. By contrast `parse_execution()`
(models/snapshots/sources) does use real timings: `started_at, completed_at = self.get_timings(run["timing"])`,
sourced from run_results' `timing[].started_at`/`completed_at`.

**Consequence:** dbt *model* observations can be placed accurately on a timeline; dbt *test* (i.e.
`dataQualityAssertions`) observations are only accurate to the granularity of the whole dbt
invocation. For daily/hourly baselining that is fine; for intra-run ordering it is not.

For Flink checkpoint RUNNING events, `eventTime` is `ZonedDateTime.now()` at emission
(`OpenLineageJobStatusChangedListener.commonEventBuilder`), i.e. *poll* time, up to
`trackingIntervalInSeconds` after the checkpoint actually completed.

**Verdict:** yes, observations can be placed on a timeline reliably enough for day-over-day or
run-over-run baselining, using `eventTime` (and `nominalTime.nominalStartTime` where present). They
cannot be trusted at sub-minute resolution.

---

## 6. Nulls and gaps: "check did not run" vs "check ran, found zero"

### 6.1 `dataQualityAssertions` cannot express "did not run"

The schema's per-assertion `required` is `["assertion", "success"]` and `success` is a plain
`boolean`. There is **no** `skipped`/`null` state. The only way a skipped check is representable is
by *omitting the assertion entry entirely* — which is indistinguishable from "this dataset has no
such check configured".

The spec authors evidently recognised this: `spec/facets/TestRunFacet.json` uses a **string** status
instead —

> `"status"`: "Whether the test found issues: 'pass' (no issues found), 'fail' (issues found),
> **'skip' (not executed)**. Independent of severity…"

So if you need to distinguish did-not-run, you need `TestRunFacet` (a run facet), not
`dataQualityAssertions` (a dataset facet). The docs page
`website/docs/spec/facets/dataset-facets/data_quality_assertions.md` says explicitly:
"For run-level test reporting that is independent of any particular dataset, see the Test Run Facet."

### 6.2 Assertions do carry magnitude — but only since facet 1-1-0, and only as strings

`expected` and `actual` ("serialized as a string") were added in `1-1-0`. Field table in
`website/docs/spec/facets/dataset-facets/data_quality_assertions.md` and the worked example there:

```json
{ "assertion": "row_count", "name": "assert_order_row_count", "success": false,
  "severity": "warn", "description": "Expected at least 1000 rows",
  "expected": "1000", "actual": "999",
  "content": "SELECT COUNT(*) FROM orders", "contentType": "sql",
  "params": {"threshold": "0.01"} }
```

Two independent axes, per the docs' "`success` vs `severity`" section and the schema descriptions:
`success` = did the check find issues; `severity` = does that block the pipeline. A `severity: "warn"`
+ `success: false` assertion means issues were found but the run continued.

### 6.3 Statistics facets: absence vs zero

- `outputStatistics` and `inputStatistics` have **no required fields**, so an emitter can legally send
  `{}`. And Spark's builder only emits the facet at all when `records + bytes > 0`
  (`JobMetricsHolder.containsWriteMetrics`) — so **"wrote zero rows" and "we couldn't measure" both
  render as a missing facet.** That is the single biggest gap for volume anomaly detection: you cannot
  distinguish a genuine empty write from an instrumentation miss.
- dbt does the same: `if not row_count and not byte_count: return OutputDataset(...)` without
  `outputFacets`, and `rowCount=row_count if row_count > 0 else None`
  (`processor.py`, `node_to_output_dataset`). **A dbt model that wrote 0 rows emits no
  `outputStatistics`.**
- `dataQualityMetrics` requires `columnMetrics` but each per-column metric is optional, so
  `nullCount` absent ≠ `nullCount: 0`.

---

## 7. Custom facets: mechanism and tooling cost

### 7.1 The mechanism is deliberately trivial

`website/docs/spec/facets/custom-facets.md`:

> "as long as they follow the [BaseFacet](https://openlineage.io/spec/1-0-2/OpenLineage.json#/$defs/BaseFacet)
> to contain the two mandatory element `_producer` and `_schemaURL`, it will be accepted and stored as
> part of the OpenLineage event, and will be able to be retrieved when you query those events."
>
> "Custom facets are not part of the default facets. Therefore, it will be treated as a payload data
> as-is, but applications retrieving those, if they have the capability to understand its structure
> and use them, should be able to do so without any problems."

`spec/OpenLineage.json`, `$defs/BaseFacet`: `required: ["_producer", "_schemaURL"]`,
`additionalProperties: true`. `_producer` = "URI identifying the producer of this metadata";
`_schemaURL` = "The JSON Pointer URL to the corresponding version of the schema definition for this
facet". `RunFacet`/`JobFacet`/`DatasetFacet`/`InputDatasetFacet`/`OutputDatasetFacet` all just
`allOf` BaseFacet (Job/Dataset facets additionally get `_deleted: boolean`, "set to true to delete a
facet").

In Python you subclass `BaseFacet` and optionally override `_get_schema()`; if you don't, `_schemaURL`
defaults to BaseFacet's, which the docs call "legal". In Java the equivalent is extending
`OpenLineage.DefaultRunFacet` — exactly what the Flink integration does for `checkpoints`
(`integration/flink/shared/src/main/java/io/openlineage/flink/client/CheckpointFacet.java`).

**Naming conventions: the docs page explicitly does not give any** beyond the `my_facet` example.
The only convention with teeth is the registry proposal.

### 7.2 The facet registry (proposal 2161)

`proposals/2161/registry.md` defines the intended prefixing scheme:

> - Custom facet Prefix = `“${name}”`
> - Producer URI prefix = `“ol:${name}”`
> - Schema URI prefix: `“ol:${name}:${path}”` => `“${schema url prefix}/${path}”`

and requires: "Producers can create and evolve their custom facets without requiring approval from
the OpenLineage project." The registry is realised as `spec/registry/{Name}/registry.json` +
`spec/registry/{Name}/facets/*.json`, with `CODEOWNERS` delegation. As of this clone, only four
namespaces are registered: `core`, `gcp` (composer/dataproc/lineage), and `iceberg`
(`spec/registry/`). `spec/registry/core/registry.json` lists the 30 core facets as
`"ol:core:DataQualityAssertionsDatasetFacet.json"` etc. **Note `ol:core:` does not list
`DataQualityMetricsDatasetFacet.json`** — only the `Input` variant.

### 7.3 Cost in tooling compatibility — Marquez (the reference consumer)

*(Sourced from a shallow clone of `MarquezProject/marquez` @ `180f37b2`, main.)*

**Storage: lossless.** `api/src/main/resources/marquez/db/migration/V55.1__add_dataset_facets.sql`
creates `dataset_facets(created_at, dataset_uuid, dataset_version_uuid, run_uuid, lineage_event_time,
lineage_event_type, type, name, facet JSONB)`; `V55.2` and `V55.3` do the same for job and run facets.
`api/src/main/java/marquez/db/DatasetFacetsDao.java` `insertDatasetFacetsFor` iterates
`jsonNode.fieldNames()` and inserts one row per top-level facet name regardless of whether the name is
known. The models in `api/src/main/java/marquez/service/models/LineageEvent.java` use
`@JsonAnySetter`/`@JsonAnyGetter` into a `Map<String,Object> additional`; `InputDatasetFacets` and
`OutputDatasetFacets` have *only* the any-map. The full raw event is additionally retained in
`lineage_events(event_time, event JSONB, …)` (`V17.2__open_lineage.sql`). The only drops are run-facet
specific: `spark_unknown` is discarded and `spark.logicalPlan` deduped
(`api/src/main/java/marquez/db/RunFacetsDao.java`).

**Classification: known names get typed, unknown names become `UNKNOWN`.**
`DatasetFacetsDao.java` has `enum Type { DATASET, INPUT, OUTPUT, UNKNOWN }` and a name→type map:
`dataQualityMetrics, dataQualityAssertions → INPUT`; `outputStatistics → OUTPUT`; schema/documentation/
columnLineage/etc → `DATASET`; anything else → `UNKNOWN`.

**Read-side trap that matters for us:** dataset and dataset-version queries filter
`type ILIKE 'dataset' OR type ILIKE 'unknown' OR type ILIKE 'input'`
(`api/src/main/java/marquez/db/DatasetDao.java` L90, L132-134;
`api/src/main/java/marquez/db/DatasetVersionDao.java` L206, L274-275). So **`outputStatistics` is
excluded from the dataset REST responses**, while a *custom* facet — landing as `UNKNOWN` — passes
through. `DatasetVersionDao.findBy(UUID version)` (L167-195) has no type filter, so output facets do
appear on the single-version endpoint. That inconsistency is in the code as written.

**UI:** `dataQualityAssertions` is rendered specially — `web/src/helpers/nodes.ts` L109-133
(`datasetFacetsQualityAssertions()`, `datasetFacetsStatus()` deriving red/green from
`assertion.success`), consumed by `web/src/components/datasets/Assertions.tsx`,
`DatasetDetailPage.tsx`, `web/src/routes/datasets/Datasets.tsx` (HEALTHY/UNHEALTHY chip) and
`web/src/routes/table-level/TableLineageDatasetNode.tsx` (health dot on the graph).
**`dataQualityMetrics` and `outputStatistics` appear nowhere in `web/`** — they fall through to the
generic `<MqJsonView data={facets} />` raw dump (`web/src/components/datasets/DatasetInfo.tsx` L144-149).
A custom facet gets the same raw-JSON treatment.

**Query/trending: none.** The only facet-fetch endpoint is
`GET /api/v1/jobs/runs/{id}/facets?type=run|job` (`api/src/main/java/marquez/api/JobResource.java`
L277-300; `spec/openapi.yml` L481-497) — no time range, and `type=DATASET` is an explicit no-op with
the comment `// for future case if there's a need to add dataset facets to the endpoint`.
`GET .../datasets/{dataset}/versions` does `JSONB_AGG(facets ORDER BY lineage_event_time ASC)` but
offers only limit/offset. The only time-ranged endpoint is
`GET /api/v1/events/lineage?before&after` (`api/src/main/java/marquez/api/OpenLineageResource.java`
L128-136), which returns whole raw events. `api/src/main/java/marquez/db/StatsDao.java` aggregates
only `lineage_events.event_type` counts; a repo-wide grep for `rowCount`/`outputStatistics`/
`dataQualityMetrics` in `api/src/main/java/` hits **only** the two enum constants in
`DatasetFacetsDao.java`. Materialized views `V71__add_mat_views_lineage_metrics.sql` roll up event
counts by hour only. There is no index on `(name, lineage_event_time)`
(`V59.2__facet_tables_indexes.sql` indexes `dataset_uuid`, `dataset_version_uuid`, `run_uuid`).

**Net cost of emitting a custom DQ facet:** essentially zero for *storage* and *retrieval of the raw
blob*, and essentially total for *rendering and trending* — but note that Marquez gives you no
trending for the **standard** facets either. Emitting `dataQualityAssertions` is the one thing that
buys you Marquez UI treatment; everything numeric you will be querying Postgres or
`/api/v1/events/lineage` for yourself regardless.

---

## 8. Prior art: statistical/baseline anomaly detection on OpenLineage events

**Primary-source finding: not found.** I could not locate, in any first-party repo or doc, an
implementation that builds statistical baselines from OpenLineage event facets (as opposed to
consuming assertion pass/fail).

Concretely, what I checked and what I found:

- **Marquez** — no numeric aggregation of any facet value exists (evidence in §7.3:
  `StatsDao.java` counts event types only; grep for `rowCount`/`outputStatistics` in
  `api/src/main/java/` returns only enum constants). Marquez consumes `dataQualityAssertions` as
  a boolean health indicator only (`web/src/helpers/nodes.ts` `datasetFacetsStatus()`).
- **OpenLineage repo proposals** (`proposals/`) — a `grep -rli "anomaly"` across all proposals
  returns nothing about statistical baselining. `proposals/2161/registry.md` mentions "Data
  reliability, data quality" only as a *documentation category* to be written.
- **The OpenLineage DQ facets themselves** are shaped for point-in-time reporting: `expected`/`actual`
  are strings, and there is no facet anywhere in `spec/facets/` or `spec/registry/` carrying a
  baseline, threshold-from-history, z-score, or training window. The closest thing to a numeric time
  series in the spec is `outputStatistics.rowCount` + `eventTime`.

**Closest real prior art, and it deliberately does *not* use OpenLineage:** Elementary. Its
`metrics_anomaly_score` view
(`elementary-data/dbt-data-reliability`, `models/edr/data_monitoring/anomaly_detection/metrics_anomaly_score.sql`)
computes an expanding-window z-score directly over its own `data_monitoring_metrics` table:

```sql
case
    when {{ elementary.edr_normalize_stddev("training_stddev") }} is null then null
    when training_set_size = 1 then null  -- Single value case - no historical context
    when {{ elementary.edr_normalize_stddev("training_stddev") }} = 0 then 0  -- Stationary data
    else (metric_value - training_avg) / ({{ elementary.edr_normalize_stddev("training_stddev") }})
end as anomaly_score
```

**What it keys on:** the window partition is
`(metric_name, full_table_name, column_name, dimension, dimension_value)` — i.e. *dataset + column +
metric*, deliberately **not** job or run. That is a direct, independently-arrived-at confirmation of
the §4 conclusion. **Where it hits limits:** `full_table_name` changes on a rename, so metric history
does not survive model refactors; and the surrogate `id` includes `metric_properties`, so changing
e.g. `timestamp_column` or a `where_expression` starts a fresh series
(`macros/edr/data_monitoring/monitors_query/table_monitoring_query.sql`).

**Non-primary sources** (listed for completeness, not relied on): a DataHub marketing post
(datahub.com/blog/data-lineage-vs-data-observability) states that "smart anomaly detection ... isn't
part of the open source edition" of DataHub Cloud; datalakehousehub.com/blog/2026-05-openlineage-observability
argues OpenLineage should be the spine of data observability. Neither describes an implementation
against OpenLineage facets in enough detail to cite.

---

## 9. dbt

There are **two** processors, both Python. **There is no Rust `dbt-ol` in `integration/dbt`** —
`find integration/dbt -name "*.rs"` returns nothing; `integration/dbt/pyproject.toml` declares
`name = "openlineage-dbt"`, `version = "1.54.0"`, `[project.scripts] dbt-ol = "openlineage.dbt:main"`,
depending on `openlineage-integration-common` and `dbt-core>=1.0.0`. All the real logic is in
`integration/common/src/openlineage/common/provider/dbt/`.

| | Artifact processor (`processor.py` / `local.py`) | Structured-logs processor (`structured_logs.py`) |
|---|---|---|
| Entry | `dbt-ol run` (default), or `DbtLocalArtifactProcessor` called from Cosmos/Airflow | `dbt-ol run --consume-structured-logs` |
| Timing | post-hoc, after dbt exits | real-time, while dbt runs |
| Source | `manifest.json`, `run_results.json`, `catalog.json` | dbt's JSON log lines + `manifest.json` (+ `catalog.json` if present) |

`website/docs/integrations/dbt.md`:
> "**Artifact Processor (Post-Run)**: Extracts lineage after dbt finishes by parsing generated JSON
> artifacts (`manifest.json`, `run_results.json`, and optionally `catalog.json`)."
> …
> "**Events per Command**: The Artifact Processor emits a pair of events (**START** and **COMPLETE**
> or **FAIL**) for every executed dbt node (model, seed, snapshot, or test)."

### 9.1 Which facets, from which artifact

| Facet | Artifact processor | From | Structured logs |
|---|---|---|---|
| `dataQualityAssertions` | **yes** | `run_results.json` (`status`, `failures`) + `manifest.json` (`test_metadata`, `config.severity`, `parent_map`) | **yes**, from `NodeFinished` log events + manifest |
| `test` (TestRunFacet) | yes, **singular tests only** | same | yes |
| `outputStatistics` | **yes** | `catalog.json` `stats`, falling back to `run_results.json` `adapter_response` | only if `catalog.json` exists (no adapter_response path) |
| `dataQualityMetrics` / `columnMetrics` | **no** | — | **no** |
| `inputStatistics` | **no** | — | **no** |
| `schema` | yes | `catalog.json` `columns` | yes if catalog present |
| `columnLineage`, `sql`, `dbt_node`, `dbt_run`, `dbt_version`, `symlinks`, `documentation`, `dbt_model`, `dbt_exposures`, `tags`, `parent`, `externalQuery` | yes | manifest / run_results | mostly yes |

Note the docs' facet list in `website/docs/integrations/dbt.md` **omits both `outputStatistics` and
`dataQualityAssertions`**, even though the code emits them. The page itself carries a disclaimer:
"The authoritative source for supported facets and schemas is the source code."

### 9.2 dbt tests → `dataQualityAssertions`: magnitude IS carried

The mapping is `DbtArtifactProcessor.parse_assertions`,
`integration/common/src/openlineage/common/provider/dbt/processor.py` L628-679:

```python
for run in context.run_results["results"]:
    if not run["unique_id"].startswith("test."): continue
    test_node = nodes[run["unique_id"]]
    model_node = None
    for node in context.manifest["parent_map"][run["unique_id"]]:
        if any(node.startswith(prefix) for prefix in ["model.", "source.", "seed."]):
            model_node = node
    test_metadata = test_node.get("test_metadata")
    if test_metadata:
        name = test_metadata["name"];  node_columns = test_metadata
    else:                       # singular test — plain SQL file
        name = test_node["name"]; node_columns = test_node
    config = test_node.get("config", {})
    severity = config.get("severity")
    if severity: severity = severity.lower()

    failures = run.get("failures")
    actual   = str(failures) if failures is not None else None
    expected = expected_from_test_config(config, severity) if failures is not None else None

    assertions[model_node].append(
        data_quality_assertions_dataset.Assertion(
            assertion=name,
            name=test_node.get("name"),
            success=True if run["status"] == "pass" else False,
            column=get_from_nullable_chain(node_columns, ["kwargs", "column_name"])
                   or test_node.get("column_name"),
            severity=severity, actual=actual, expected=expected))
```

So **`actual` = the dbt `failures` count, stringified** — the failing-row magnitude *is* preserved
(as of the code in this clone; it is the `1-1-0` facet feature). `expected` comes from
`expected_from_test_config` (`processor.py` L94-106):

> "dbt's default is `"!= 0"` (any failing row trips the test) — semantically the expected count is 0.
> A non-default threshold like `"> 10"` is carried through so a consumer can distinguish 'expected
> zero failures, got N' from 'expected at most 10 failures, got N'."

```python
threshold_key = "warn_if" if (severity or "").lower() == "warn" else "error_if"
threshold = (config or {}).get(threshold_key)
if threshold is None or "".join(str(threshold).split()) == "!=0": return "0"
return str(threshold)
```

The structured-logs path is equivalent — `structured_logs.py` L544-548 and `_get_assertion` L620-651:

```python
# Structured-log NodeFinished events name the count `num_failures`
# (run_results.json calls the same value `failures`).
num_failures = (event["data"].get("run_result") or {}).get("num_failures")
...
actual = str(num_failures) if num_failures is not None else None
```

**Caveats:**
- `actual` is `None` whenever dbt's `failures` is `null` — which is what dbt writes for a test that
  errored rather than ran. So `actual: None` conflates "errored" with "adapter didn't report".
- `success = (status == "pass")`, so dbt statuses `warn`, `fail`, `error`, `skipped` all collapse to
  `success: false` in the assertion. The *aggregate per-model test event's* status is computed
  separately, treating warn as success: `"success" if all(a.success or (a.severity or "").lower() ==
  "warn" for a in node_assertions) else "error"` (`processor.py` L483-489).
- **Generic tests get a `dataQualityAssertions` facet; singular tests get a `TestRunFacet` instead.**
  `processor.py` L516-523: "Only singular tests get a per-test run event with TestRunFacet; generic
  tests are covered by the DataQualityAssertions dataset facet emitted in the loop above."
- The assertion facet is attached in **two** places for compatibility — as an `InputDataset`
  `inputFacets["dataQualityAssertions"]` *and* as a dataset `facets["dataQualityAssertions"]`, with
  the comment `# TODO: remove this next release` (`processor.py` L493-505).

### 9.3 Continuous signal for models: `outputStatistics` only, and it's fragile

`processor.py`, `node_to_output_dataset` L750-808. Precedence: **catalog first, adapter_response as
fallback**:

```python
if node.catalog_node:
    row_count = get_from_multiple_chains(node.catalog_node, [
        ["stats", "num_rows", "value"],    # bigquery
        ["stats", "row_count", "value"],   # snowflake
        ["stats", "rows", "value"],        # redshift
    ]) or 0
    byte_count = get_from_multiple_chains(node.catalog_node, [
        ["stats", "num_bytes", "value"],   # bigquery
        ["stats", "bytes", "value"],       # snowflake
    ]) or 0
    if self.adapter_type == Adapter.REDSHIFT:
        # size is the number of 1MB blocks
        blocks_count = get_from_multiple_chains(node.catalog_node, [["stats","size","value"]]) or 0
        byte_count = byte_count or blocks_count * (2**20)

if adapter_response:
    row_count  = row_count  or adapter_response.get("rows_affected", 0)
    byte_count = byte_count or adapter_response.get("bytes_processed", 0)

row_count = int(row_count); byte_count = int(byte_count)
if not row_count and not byte_count:
    return OutputDataset(name=name, namespace=namespace, facets=facets)
output_facets["outputStatistics"] = OutputStatisticsOutputDatasetFacet(
    rowCount=row_count if row_count > 0 else None,
    size=byte_count if byte_count > 0 else None)
```

Three things to internalise:

1. **`catalog.json` wins over `adapter_response`, and catalog.json is stale.** Per
   https://docs.getdbt.com/reference/artifacts/catalog-json, catalog is "Produced by: (Applies to dbt
   v2.0 and later) `--write-catalog` flag" and contains "information from your data warehouse about
   the tables and views" — i.e. a `dbt docs generate`/`--write-catalog` snapshot, not this run.
   So `rowCount` may be *the whole table at catalog-generation time*, whereas `rows_affected` is
   *rows this run wrote*. **These are semantically different quantities under the same facet field**,
   selected by whether `catalog.json` happens to be on disk. (inference — the code comments do not
   flag this, but the two sources are documented differently.)
2. **`rows_affected` is unreliable.** docs.getdbt.com/reference/artifacts/run-results-json:
   "`rows_affected`: Number of rows modified by the last statement executed (returns `-1` if count
   can't be determined or isn't applicable, like when creating a view)". The `> 0` guard prevents
   `-1` reaching the facet, but the result is a silent gap.
3. **Zero rows ⇒ no facet.** `if not row_count and not byte_count: return` without `outputFacets`.

**No column-level statistics of any kind.** `columnMetrics`, `nullCount`, `distinctCount`,
quantiles — nothing. `catalog.json`'s `columns` are used only for the `schema` facet
(`extract_catalog_fields`). Per schemas.getdbt.com/dbt/catalog/v1.json a `CatalogTable` has
`metadata`/`columns`/`stats`, and `StatsItem` is `{id, label, value (bool|string|number|null),
include, description}` — untyped, warehouse-dependent, which is why dbt-ol has to probe three
different key paths per adapter.

Structured-logs mode calls the same `node_to_output_dataset` via `_get_model_node`, which does attach
`catalog_node = get_from_nullable_chain(self.catalog, ["nodes", node_id])`
(`structured_logs.py` L1001-1014) — but never passes `adapter_response`. **So in structured-logs mode
you get `outputStatistics` only if a `catalog.json` exists, and never from `rows_affected`.**

### 9.4 Identity across runs

- **Test identity in the facet** is `assertion` (= `test_metadata["name"]`, e.g. `not_null`,
  `unique`, `accepted_values`, or the custom generic test's name), `name` (= `test_node["name"]`, the
  dbt-generated node name, e.g. `not_null_orders_order_id`), and `column`
  (`test_metadata.kwargs.column_name`). The dbt `unique_id` is **not** in the assertion — it appears
  only in the `dbt_node` *job* facet (`DbtNodeJobFacet(... unique_id=...)`).
- **Stability:** all three are derived from the model name + column name + test args. Renaming the
  model or the column changes `name` (and `column`); changing test args can change it too. dbt also
  hashes long generated names. **So test identity is stable across ordinary reruns and unstable
  across model/column refactors.** (inference from how dbt constructs test node names, corroborated
  by Elementary hitting the same problem — see §8.)
- **Job name differs per mode and per command**, see §4.2. Under `dbt build` a model's job name gets
  `.build.run` and its test aggregate gets `.build.test`; under `dbt run`/`dbt test` they get `""`
  and `".test"`.
- **`run.runId` is a fresh `generate_new_uuid()` per node per invocation**
  (`processor.py`: `run_id = str(generate_new_uuid())` in both `parse_execution` and `parse_test`).
- The one genuinely stable per-invocation handle is `DbtRunRunFacet.invocation_id`
  (`integration/common/src/openlineage/common/provider/dbt/facets.py`), alongside `project_name`,
  `profile_name`, `full_refresh`. Use it to group all nodes of one dbt run.

### 9.5 Post-hoc vs mid-run

Both exist. `integration/dbt/src/openlineage/dbt/__init__.py` `main()` branches on
`--consume-structured-logs` → `DbtStructuredLogsProcessor`, else `DbtLocalArtifactProcessor`.
`website/docs/integrations/dbt.md` on the structured-logs mode:

> "OpenLineage events are emitted **in real-time** while the dbt run is actively executing."

and its nested run hierarchy: `Orchestrator Parent Run → dbt Command Run → Node Run → Query Run`.
It also documents the trade-off:
> "**Artifact Processor**: `run_results.json` only retains the last adapter response / query ID for a
> node, dropping earlier queries. **Structured Log Processor**: Captures every individual SQL query
> event emitted by dbt as it executes."

with the caveat: "**Sequential Log Attribution Assumption**: The Structured Log Processor attributes
SQL queries to nodes under the assumption that query log events arrive **sequentially**."

**Net:** structured-logs mode buys real-time + full query capture + a proper parent/child run tree,
but costs you the `adapter_response` row-count path and uses a different `job.name` scheme.

---

## 10. Alternatives to dbt-ol: what preserves magnitude?

dbt-ol does **not** throw away test magnitude (§9.2) — that's the corrected picture as of
`openlineage-dbt` 1.54.0. What it *does* lose is (a) numeric typing (`actual`/`expected` are strings),
(b) column-level distributions entirely, and (c) row counts when the value is 0 or unavailable.

| Source | Test failure magnitude | Model row count | Model bytes | Column-level stats | Historical baseline |
|---|---|---|---|---|---|
| `dataQualityAssertions` via dbt-ol | `actual` (string) + `expected` (string) | — | — | none | none |
| `outputStatistics` via dbt-ol | — | `rowCount`, absent if 0/unknown | `size` | none | none |
| **raw `run_results.json`** | `failures` (`integer\|null`, **required**) | `adapter_response.rows_affected` | `adapter_response.bytes_processed` | none | none |
| **`catalog.json`** | — | `stats.num_rows`/`row_count`/`rows` `.value` | `stats.num_bytes`/`bytes` | column names + types only | none |
| **Elementary** | `failed_row_count` + `failures` (both `bigint`) | `row_count` metric | — | ~20 column metrics | **yes** — expanding-window avg/stddev/z-score |

### 10.1 Raw `run_results.json` — the cheapest upgrade in *fidelity*, none in *scope*

From schemas.getdbt.com/dbt/run-results/v6.json, `RunResultOutput` has
`"required": ["status", "timing", "thread_id", "execution_time", "adapter_response", "message",
"failures", "unique_id", "compiled", "compiled_code", "relation_name"]` (`batch_results` optional,
`"default": null`). Types: `failures` is `integer | null`; `adapter_response` is an untyped `object`;
`status` is the union `"success" | "error" | "skipped" | "partial success" | "no-op" | "pass" |
"fail" | "warn" | "runtime error"`; `execution_time` is `number`.

Per docs.getdbt.com/reference/artifacts/run-results-json: `timing` "breaks down execution time into
steps (often `compile` + `execute`)" each with `name`/`started_at`/`completed_at`;
`execution_time` is "Total time spent executing the node (in seconds)"; `adapter_response` is a
"Dictionary of metadata returned from the database, which varies by adapter" including `code`,
`rows_affected` (`-1` when undeterminable), `bytes_processed`.

**What raw run_results gives you over dbt-ol:** `failures` as a real integer (not a string), the
full 9-value `status` enum (so you can separate `skipped` / `error` / `warn` / `fail`),
`execution_time` as a duration series, and the untruncated `adapter_response`. **What it does not
give you:** anything column-level, anything about rows that *passed*, and any history — it is one
file per invocation and you must persist it yourself.

### 10.2 `catalog.json` — table stats, but stale and untyped

`--write-catalog` / `dbt docs generate` only. `StatsItem.value` is `boolean|string|number|null`, and
which stats exist "differs by database and relation type". Adequate for a slow-moving table-size
trend; not a per-run measurement.

### 10.3 Elementary — the only option that ships a real baseline

*(Primary sources: `elementary-data/dbt-data-reliability` @ `c5912dfd`, package version 0.25.1;
`elementary-data/elementary` @ `1a1081f5`. Note the dbt package models live in
`dbt-data-reliability`, not in `elementary`.)*

**`elementary_test_results`** — `models/edr/run_results/elementary_test_results.sql`, incremental,
indexed on `id` and `(test_unique_id, detected_at)`. Column list is defined in
`macros/edr/system/system_utils/empty_table.sql` (`empty_elementary_test_results`):
`id, data_issue_id, test_execution_id, test_unique_id, model_unique_id, invocation_id, detected_at,
created_at, database_name, schema_name, table_name, column_name, test_type, test_sub_type,
test_results_description, owners, tags, test_results_query, other, test_name, test_params, severity,
status, failures (bigint), test_short_name, test_alias, result_rows, failed_row_count (bigint)`.

So Elementary keeps **`failures` AND `failed_row_count` as `bigint`**, plus `result_rows` (the actual
offending rows) and `test_results_query` (the SQL to reproduce). Stamped in
`macros/edr/tests/on_run_end/handle_tests_results.sql`:

```jinja
{% do elementary_test_results_row.update({
        "status": status, "failures": failures,
        "invocation_id": invocation_id,
        "failed_row_count": elementary_test_failed_row_count }) %}
```

**`data_monitoring_metrics`** — `models/edr/data_monitoring/data_monitoring/data_monitoring_metrics.sql`,
incremental append-only, `partition_by=bucket_end`, `cluster_by=["full_table_name","metric_name"]`.
Columns (`default__empty_data_monitoring_metrics`): `id, full_table_name, column_name, metric_name,
metric_type, metric_value (float), source_value, bucket_start, bucket_end, bucket_duration_hours,
updated_at, dimension, dimension_value, metric_properties` (+ `created_at`). **This is a genuine
time-bucketed numeric time series** — exactly the thing OpenLineage has no facet for.

**`metrics_anomaly_score`** — a *view* over the above
(`models/edr/data_monitoring/anomaly_detection/metrics_anomaly_score.sql`) exposing
`anomaly_score, latest_metric_value, bucket_start, bucket_end, training_avg, training_stddev,
training_start, training_end, training_set_size, is_anomaly`, with expanding-window training stats
(`rows between unbounded preceding and current row`) and a 7-day output filter. The anomaly *test*
path additionally computes `min_metric_value`/`max_metric_value` bounds
(`macros/edr/data_monitoring/anomaly_detection/get_anomaly_scores_query.sql`,
`get_limit_metric_values`: `(±1) * anomaly_sensitivity * normalized_stddev + training_avg`).

**Monitors available** — `macros/edr/data_monitoring/monitors/monitors.sql`, `get_available_monitors()`:

```jinja
{ "table": ["row_count", "freshness"],
  "column_any_type": ["null_count", "null_percent", "not_null_percent"],
  "column_string": ["min_length","max_length","average_length","missing_count","missing_percent","not_missing_percent"],
  "column_numeric": ["min","max","zero_count","zero_percent","not_zero_percent","average","standard_deviation","variance","sum"],
  "column_boolean": ["count_true","count_false"] }
```

`get_default_monitors()` in the same file drops `not_null_percent`, `not_missing_percent`,
`not_zero_percent`, `sum`. Schema changes are **not** continuous — they snapshot into
`schema_columns_snapshot` and emit discrete test rows.

**Identity in Elementary** (directly relevant to §4): metric-series partition key is
`(metric_name, full_table_name, column_name, dimension, dimension_value)`; the row `id` is
`generate_surrogate_key(["full_table_name","column_name","metric_name","metric_type","bucket_end","metric_properties"])`
(`macros/edr/data_monitoring/monitors_query/table_monitoring_query.sql`). Test rows are keyed by
`test_unique_id` (the dbt node unique_id) across runs, with per-execution `id =
"{invocation_id}.{unique_id}"` (`macros/utils/graph/get_node_execution_id.sql`). `elementary_unique_id`
is **not a stored column** — it is a CLI-side expression
`test_unique_id + '.' + column_name + '.' + test_sub_type`
(`elementary-data/elementary`, `elementary/monitor/dbt_project/macros/get_test_results.sql:244`),
introduced because *"Due to inconsistency test sub type and column name in some of elementary's tests
we need to calculate different elementary unique id"*.

---

## What this means for baseline anomaly detection

### Can be keyed and trended

1. **`(dataset.namespace, dataset.name)` + `eventTime`** is the only universally-available series key.
   Independently confirmed as the right choice by Elementary, which partitions on
   `full_table_name, column_name, metric_name, dimension, dimension_value` and deliberately ignores
   job and run.
2. **Volume from `outputStatistics.rowCount` / `.size` / `.fileCount`** — real from Spark
   (`SparkListenerJobEnd`/`SQLExecutionEnd`, `WRITE_RECORDS`/`WRITE_BYTES` task metrics) and from dbt
   (catalog stats, else `adapter_response.rows_affected`). This is the single best continuous signal
   OpenLineage actually delivers today.
3. **Per-check pass/fail *and magnitude* from `dataQualityAssertions`**, keyed on
   `(dataset, assertion, column, name)`, with `actual`/`expected` parsed from string to number.
   dbt-ol populates all of these.
4. **Iceberg tables get far more**: `icebergScanReport.scanMetrics.*` and
   `icebergCommitReport.commitMetrics.*` (`addedRecords`, `totalRecords`, `addedFilesSizeInBytes`,
   `totalFilesSizeInBytes`, `totalDuration`, …) — ~30 typed counters per event, the richest numeric
   payload in the whole ecosystem.
5. **Run duration** — derivable from START/COMPLETE `eventTime` pairs on the same `runId`.
6. **Flink liveness** — `checkpoints.{failed,total}` deltas at ~60 s resolution.

### Cannot be keyed or trended

1. **Column-level distributions.** `dataQualityMetrics.columnMetrics` (nullCount, distinctCount,
   min/max/sum, quantiles) is spec'd but has **exactly one first-party producer: Great Expectations**.
   Not Spark, not Flink, not dbt. If we want column drift, we generate it ourselves.
2. **Anything from Flink.** Zero DQ facets, zero statistics facets, no facet-builder framework.
   Flink 2.x checkpoint RUNNING events don't even carry `inputs`/`outputs`. A long-running Flink job
   is, for DQ purposes, one event plus a heartbeat.
3. **Zero-valued volume.** "Wrote 0 rows" and "couldn't measure" are both a missing `outputStatistics`
   in Spark (`records + bytes > 0` guard) and in dbt (`if not row_count and not byte_count: return`).
   **Any volume baseline will systematically miss the empty-write failure mode** unless we emit our
   own facet that distinguishes them.
4. **"Check did not run."** `dataQualityAssertions.success` is a bare boolean with no skip state; a
   skipped check is simply an absent array entry, indistinguishable from an unconfigured one. Use
   `TestRunFacet.status` (`pass`/`fail`/**`skip`**) if this matters.
5. **Stable identity across refactors.** Dataset names track physical location; dbt test names track
   model+column+args; dbt job names change between `run` and `build` and between the two dbt-ol modes.
   Any rename resets the baseline. Elementary has the same defect, so it is a property of the domain,
   not of OpenLineage.
6. **Sub-minute timing.** dbt test events are stamped with `datetime.now()` at post-processing time,
   not test execution time; Flink checkpoint events are stamped at poll time.
7. **Trending from the reference consumer.** Marquez stores everything losslessly but has no
   name-scoped time-ranged facet API, no supporting index, and no numeric aggregation anywhere.
   Trending means querying `dataset_facets` in Postgres directly, or paging
   `/api/v1/events/lineage?before=&after=` and extracting client-side. Also:
   **`outputStatistics` is type-classified `OUTPUT` and filtered out of Marquez's dataset REST
   responses** — it is reachable via the raw events endpoint and the single dataset-version endpoint
   only.

### The pragmatic shape

Emit a **custom dataset facet** (BaseFacet + `_producer` + `_schemaURL`, registered under our own
`spec/registry/{name}` prefix per `proposals/2161/registry.md`) carrying explicitly-typed numeric
observations with an explicit "measured / not measured / measured-zero" tri-state — i.e. exactly the
distinction the standard facets cannot make. Cost in Marquez: it lands as `UNKNOWN` type, which
means it *survives* the dataset-facet type filter that `outputStatistics` does not, and renders as
raw JSON — the same treatment `dataQualityMetrics` and `outputStatistics` already get. Keep emitting
standard `dataQualityAssertions` alongside it, because that is the one facet Marquez's UI renders
natively.
