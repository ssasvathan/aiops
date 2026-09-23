# Research: Medallion Path Facts — Elementary on Sources, OpenLineage on the Batch Path, Airflow OTel Metrics

> **Audience:** Architecture reviewers of the DQ anomaly proposal. Also engineers and LLM agents
> who will wire detection onto the bronze → silver → gold → hosting path.
>
> **Question:** Data reaches the Snowflake bronze zone two ways: Kafka streaming, and batch Spark
> jobs (orchestrated by Airflow) that copy source files into bronze. dbt then builds bronze →
> silver → gold → hosting. Five things need checking. (1) Can Elementary's anomaly tests run on dbt
> `sources`? (2) Where does Elementary write, and how? (3) How does it pick buckets and windows?
> (4) What lineage and row counts does OpenLineage give us on the batch path? (5) What
> operational metrics does Airflow emit natively over OpenTelemetry?
>
> **Scope:** Architecture proposal input only. No implementation.
>
> **Date:** 2026-09-22. **Status:** Draft for review.

## Reading Rules

- Every non-obvious claim carries a source: a URL, or a file path in a pinned repo (see
  [Sources read](#sources-read)). Sources are **primary only**:
  `elementary-data/dbt-data-reliability`, docs.elementary-data.com (read from the
  `elementary-data/elementary` repo's `docs/` tree, which is what the site renders),
  `OpenLineage/OpenLineage`, airflow.apache.org docs, the `apache/airflow` source, and
  `snowflakedb/spark-snowflake` (read only to check one Spark-metrics question).
- **[UNVERIFIED]** marks anything I could not confirm from a primary source.
- **(inference)** marks a conclusion I drew from sourced facts that no source states directly.
- Short path prefixes:
  - `EDR/` = `https://github.com/elementary-data/dbt-data-reliability/blob/9a7e2b55/`
  - `EDOCS/` = `https://docs.elementary-data.com/` (source: `elementary-data/elementary@e34d8539:docs/`)
  - `OL/` = `https://github.com/OpenLineage/OpenLineage/blob/d204b0e1/`
  - `AF-OL/` = `https://airflow.apache.org/docs/apache-airflow-providers-openlineage/stable/` (page version 2.20.1)
  - `AF/` = `https://airflow.apache.org/docs/apache-airflow/stable/` (page version 3.3.2)

---

## 1. Elementary anomaly tests on dbt `sources`

### 1.1 Yes, sources are supported

- The official "add tests" page has a `Sources` tab. It puts `volume`/`freshness`/`dimension`/
  `all_columns`/`column` anomaly tests directly on a source table
  (`EDOCS/data-tests/add-elementary-tests`, `docs/data-tests/add-elementary-tests.mdx:176-215`):

  ```yaml
  sources:
    - name: "my_non_dbt_data"
      database: "raw_events"
      schema: "product"
      tables:
        - name: "raw_product_login_events"
          ## sources don't have config, so elementary config is placed under 'meta'
          meta:
            elementary:
              timestamp_column: "loaded_at"
          tests:
            - elementary.freshness_anomalies
            - elementary.dimension_anomalies:
                dimensions:
                  - event_type
            - elementary.all_columns_anomalies:
                column_anomalies:
                  - null_count
                  - missing_count
                  - zero_count
            - elementary.schema_changes_from_baseline
          columns:
            - name: user_id
              data_type: text
              tests:
                - elementary.column_anomalies
  ```

- **Config goes in `meta.elementary`, not `config.elementary`**, for sources. The
  `timestamp_column` page gives a separate `source` example using `meta: elementary:
  timestamp_column: loaded_at` (`EDOCS/data-tests/anomaly-detection-configuration/timestamp-column`).
  You can also pass any parameter inline as a test argument, the same way as on models.
- Mechanically, the test macro resolves its target relation from the test node's single
  `depends_on` node. It also has a regex fallback that matches `source('<src>', '<table>')` when a
  `where` wraps the model (`EDR/macros/edr/tests/test_utils/get_model_relation_for_test.sql:5-41`).
  Ephemeral models are rejected. Sources are not
  (`EDR/macros/edr/tests/test_table_anomalies.sql:42-50`).

### 1.2 Exact test names (package 0.26.0)

Defined as `{% test <name>(...) %}` in `EDR/macros/edr/tests/`. Invoke them as
`elementary.<name>`:

| Test | File | Mandatory param |
|---|---|---|
| `volume_anomalies` | `test_volume_anomalies.sql:1` | none ("highly recommended" `timestamp_column`, `EDOCS/data-tests/anomaly-detection-tests/volume-anomalies`) |
| `freshness_anomalies` | `test_freshness_anomalies.sql:1` | **`timestamp_column`** (`mandatory_params=["timestamp_column"]`, line 80) |
| `event_freshness_anomalies` | `test_event_freshness_anomalies.sql:1` | **`event_timestamp_column`**, which must be a timestamp type. Compile error otherwise (lines 127-147). `update_timestamp_column` is optional |
| `column_anomalies` | `test_column_anomalies.sql` | none |
| `all_columns_anomalies` | `test_all_columns_anomalies.sql` | none |
| `dimension_anomalies` | `test_dimension_anomalies.sql` | `dimensions` |
| `table_anomalies` (the generic one the three table tests wrap) | `test_table_anomalies.sql:1` | `table_anomalies` list |

The same directory also has `schema_changes`, `schema_changes_from_baseline`, `volume_threshold`,
`metric_stability`, `data_freshness_sla`, `execution_sla`, `collect_metrics` and others. These
are not anomaly-scored in the z-score sense.

### 1.3 Limitations that matter on bronze sources

| Limitation | Source |
|---|---|
| `freshness_anomalies` cannot run without a `timestamp_column`. `event_freshness_anomalies` cannot run without `event_timestamp_column` | §1.2 |
| `seasonality` needs a `timestamp_column`. Otherwise it is a compile error: "Test with seasonality must have a timestamp_column" | `EDR/macros/edr/tests/test_configuration/get_seasonality.sql:16-19` |
| `training_period`, `detection_period` and `time_bucket` only apply to tests **with** a `timestamp_column` | `EDOCS/…/training-period`, `…/detection-period`, `…/time-bucket` ("Relevant tests: Anomaly detection tests with `timestamp_column`") |
| **Sources are treated like incremental models.** The full training window is computed on the first run (and on full refresh). Later runs only recompute the `detection_period` buckets, and overwrite them to catch backfills | `EDOCS/…/training-period` "How it works"; code: `EDR/macros/edr/data_monitoring/data_monitors_configuration/get_buckets_configuration.sql:139-143` ("We assume we should also cosider sources as incremental", `is_incremental_model(..., source_included=true)`); `EDR/macros/utils/graph/is_incremental_model.sql:1-6` |
| **No `timestamp_column` → a whole-table scan on every run.** The query is `select * from <table> [where …]`, one metric value per run, `bucket_start = null`, `bucket_end = run_started_at` | `EDR/macros/edr/data_monitoring/monitors_query/table_monitoring_query.sql` `get_no_timestamp_table_query` (~lines 84-123), `get_no_timestamp_volume_query` |
| With a `timestamp_column`, the monitored table is filtered to the bucket range (`time_filtered_monitored_table`). Whether Snowflake prunes micro-partitions for that filter depends on how the bronze table is clustered relative to the column | code: same file; pruning: **(inference)**, not stated by Elementary |
| Only one relation per test. Views and tables are supported. Ephemeral is not | `test_table_anomalies.sql:42-50` |

On the whole-table scan: for a pure `row_count` this is `count(*)`. Snowflake *may* answer that
from metadata. **[UNVERIFIED]** I did not check Snowflake docs for that in this pass.
`column_anomalies`/`all_columns_anomalies` without a timestamp do scan the columns.

---

## 2. Elementary's own schema, bootstrap, and result tables

- **Schema name.** The install guide tells you to add `models: elementary: +schema: "elementary"`
  to `dbt_project.yml`. It then says: "Depending on your project custom schema macro, the schema
  will be named `elementary` or `<target_schema>_elementary`"
  (`EDOCS/quickstart` via `docs/_snippets/quickstart-package-install.mdx`). So `_elementary` is
  **not** a hard-coded suffix. It is dbt's default `generate_schema_name` concatenation
  (`<target.schema>_<custom>`) applied to the `+schema` you set. A custom
  `generate_schema_name` macro changes it.
- **Bootstrap.** The same guide gives `dbt deps` then `dbt run --select elementary`. The guide
  says this "will mostly create empty tables, that will be updated with artifacts, metrics and
  test results in your future dbt executions" (same snippet). The package ships models under
  `EDR/models/edr/`, including `run_results/elementary_test_results.sql`,
  `data_monitoring/data_monitoring/data_monitoring_metrics.sql`,
  `data_monitoring/anomaly_detection/metrics_anomaly_score.sql`, and `dbt_artifacts/dbt_sources.sql`.
  It also warns that some models must be incremental, so global materialization overrides must
  not touch the `elementary` package.
- **Temp test tables.** Per-test metric and anomaly-score tables go in
  `<elementary_schema><tests_schema_name>`. `tests_schema_name` defaults to `""`, i.e. the
  same schema (`EDR/macros/edr/system/system_utils/get_config_var.sql:118`). A legacy `__tests`
  suffix is still honoured if that schema already exists
  (`EDR/macros/edr/tests/test_utils/get_elementary_tests_schema.sql:2-12`).
- **on-run-end writes `elementary_test_results`.** The package's `dbt_project.yml` registers
  `on-run-end: "{{ elementary.on_run_end() }}"` (`EDR/dbt_project.yml`). The flow:
  - `on_run_end()` calls `handle_tests_results()` when `is_test_command()` is true and
    `disable_tests_results` is not set (`EDR/macros/edr/system/hooks/on_run_end.sql:16-20`).
  - That macro inserts the cached test results into `elementary_test_results`. It also inserts
    the per-test metrics into `data_monitoring_metrics`, and column snapshots into
    `schema_columns_snapshot` (`EDR/macros/edr/tests/on_run_end/handle_tests_results.sql:30-57`).
  - The same hook also uploads dbt artifacts, run results, source-freshness results (on
    `dbt source freshness`) and invocations (`on_run_end.sql:8-30`).
  - (inference) The results only land if the hook runs. A `dbt test`/`dbt build` that is killed
    before on-run-end leaves no rows.

---

## 3. Buckets, windows, seasonality, and the no-timestamp case

| Knob | Shape | Default | Source |
|---|---|---|---|
| `time_bucket` | `{period: hour\|day\|week\|month, count: int>0}` | `{period: day, count: 1}` | `EDR/…/test_configuration/get_time_bucket.sql:1-7,80-82`; `EDOCS/…/time-bucket` |
| `training_period` | `{period: day\|week\|month, count}` | 14 days (`days_back: 14`) | `EDOCS/…/training-period`; `get_config_var.sql:115`; converted to days in `get_period_vars.sql:29-51` |
| `detection_period` | `{period: day\|week\|month, count}` | 2 days (`backfill_days: 2`) | `EDOCS/…/detection-period`; `get_config_var.sql:117`; `get_period_vars.sql:1-27` |
| `detection_delay` | `{period: hour\|day\|week, count>=0}` | 0 hours | `get_detection_delay.sql:1-11` |
| `seasonality` | `day_of_week` \| `hour_of_day` \| `hour_of_week` | none | `get_seasonality.sql:21-35`; `EDOCS/…/seasonality` |
| `anomaly_sensitivity` | z-score threshold | 3 | `get_config_var.sql:116`; `EDOCS/data-tests/data-anomaly-detection` ("Z-score") |
| `min_training_set_size` | int | 7 | `get_config_var.sql:144` |
| `anomaly_direction` | both/spike/drop | `both` | `get_config_var.sql:146` |

Rules the code enforces:

- `day_of_week` requires `time_bucket` = exactly `{day, 1}`. `hour_of_day` and `hour_of_week`
  require exactly `{hour, 1}`. Anything else is a compile error (`get_seasonality.sql:36-56`).
- With `day_of_week` or `hour_of_week`, `days_back` is multiplied by 7. So the default 14-day
  training period becomes 98 days of history (`get_days_back.sql:5-7`; the docs say the same in
  `EDOCS/…/seasonality` "How it works").
- The windows are stretched to whole buckets. Weekly buckets start on the warehouse's configured
  week start (`EDOCS/…/time-bucket`, `EDOCS/…/training-period` "Changes from default").
- Both `training_period` and `detection_period` are given as periods but converted to **whole
  days**, rounded up (`get_period_vars.sql:65-97`).
- `detection_period`: only buckets inside it can be flagged. On incremental models and sources it
  is also the recompute window (`EDOCS/…/detection-period`).

**No timestamp column** (`EDOCS/…/timestamp-column`, and the code in §1.3):

- "each time the test runs it calculates the metric for all of the data in the table, and checks
  for anomalies between the metric from previous runs … it will take the test `training_period`
  days to start working, as it needs the time to collect the necessary metrics."
- There are no time buckets: one point per test run, stamped `run_started_at`. Cadence equals
  your `dbt test` cadence. `time_bucket`, `seasonality`, `training_period` and
  `detection_period` do not apply.
- `volume_anomalies` measures **total table size**, not rows-arrived-per-period. That is
  `get_no_timestamp_volume_query` → `row_count()` over the whole table. On an append-only bronze
  table this is a monotonically rising series. (inference) A z-score on a rising total is a weak
  detector of "today's load was short".
- `freshness_anomalies` is unavailable. `event_freshness_anomalies` without
  `update_timestamp_column` falls back to "now minus max(event timestamp)" per run
  (`table_monitoring_query.sql`, `get_no_timestamp_event_freshness_query`; mapping at
  `get_metric_query`).

---

## 4. OpenLineage on the batch path

### 4(a) Airflow OpenLineage provider (v2.20.1)

**Every task emits events, but only "supported" ones carry datasets**
(`AF-OL/supported_classes.html`, "What does 'supported operator' mean?"):

> "All Airflow operators will automatically emit OpenLineage events … regardless of whether they
> appear on the 'supported' list. Every OpenLineage event will contain basic information such as:
> Task and DAG run metadata (execution time, state …), Job relationship …, Error message …"
> "'Supported' operators provide additional metadata … Input and output datasets …
> An unsupported operator will still appear in the lineage graph, but without these details."

**Spark jobs submitted from Airflow.** The provider does **not** extract Spark datasets itself.
The Spark integration (the `OpenLineageSparkListener` inside the Spark app) must be installed and
enabled separately (`AF-OL/spark.html`, "OpenLineage Spark Integration"):

> "For Spark applications to send lineage (regardless if triggered from Airflow or not), you need
> to have the Spark OpenLineage integration enabled and configured in your Spark application."

What the provider *does* do is **inject** parent-job and (HTTP-only) transport config into the
Spark conf. That links the Spark run to the Airflow task via `ParentRunFacet` (same page):

- **Operators with automatic injection:** `SparkSubmitOperator`, `EmrAddStepsOperator`,
  `EmrContainerOperator`, `EmrServerlessStartJobOperator`, `GlueJobOperator`, `LivyOperator`,
  `DatabricksRunNowOperator`, `DatabricksSubmitRunOperator`, `DataprocCreateBatchOperator`,
  `DataprocInstantiateInlineWorkflowTemplateOperator`, `DataprocSubmitJobOperator`.
- **Config:** `[openlineage] spark_inject_parent_job_info = true`
  (env `AIRFLOW__OPENLINEAGE__SPARK_INJECT_PARENT_JOB_INFO`). The provider then injects
  `spark.openlineage.parentJobNamespace|parentJobName|parentRunId` and
  `rootParentJobNamespace|rootParentJobName|rootParentRunId`. The root properties need Spark
  integration ≥ 1.31.0. Per-operator opt-out is `openlineage_inject_parent_job_info=False`.
  Manually set `spark.openlineage.parent*` values are never overwritten.
- **Transport injection:** a separate option on the same page. "Currently, only HTTP transport is
  supported for automatic transport injection."
- **Caveats:** for `EmrAddStepsOperator`, transport injection is not supported. For
  `GlueJobOperator`, props go via `--conf` in `script_args`, and "the Glue job itself must still
  have the Spark OpenLineage integration … enabled".

**Plain file-copy operators.** The supported list includes, among others:
- `S3CopyObjectOperator`, `S3CopyPrefixOperator`, `S3CreateObjectOperator`,
  `S3FileTransformOperator`
- `GCSToGCSOperator`, `LocalFilesystemToGCSOperator`, `S3ToGCSOperator`, `GCSToS3Operator`,
  `SFTPToGCSOperator`, `GCSToSFTPOperator`, `SFTPOperator`
- `CopyFromExternalStageToSnowflakeOperator`

Hook-level lineage also covers arbitrary Python tasks that call supported hook methods, e.g.
`S3Hook.copy_object()/load_file()/download_file()` and `GCSHook.copy()/upload()/download()`
(`AF-OL/supported_classes.html`, "Hook Level Lineage" and the per-provider lists). These give
**dataset identity only** (inputs/outputs). Row counts are a separate question. For
`CopyFromExternalStageToSnowflakeOperator`, `get_openlineage_facets_on_complete` builds plain
input file datasets and one output table dataset, with no statistics facet
(`https://github.com/apache/airflow/blob/main/providers/snowflake/src/airflow/providers/snowflake/transfers/copy_into_snowflake.py`
lines 255-324). Whether other file operators attach output statistics: **[UNVERIFIED]**. I did
not read each operator's source.

### 4(b) Spark integration: `outputStatistics` (rowCount, size, fileCount)

**How it is produced.** `OutputStatisticsOutputDatasetFacetBuilder` fires on
`SparkListenerJobEnd` / `SparkListenerSQLExecutionEnd`. It emits `outputStatistics` **only if**
`JobMetricsHolder` holds write metrics for the active job
(`OL/integration/spark/shared/src/main/java/io/openlineage/spark/agent/facets/builder/OutputStatisticsOutputDatasetFacetBuilder.java:35-70`).
Those metrics are summed from Spark **task** `outputMetrics().recordsWritten()/bytesWritten()`.
`fileCount` is approximated as 1 per task with `bytesWritten > 0`. If all read/write metrics
are 0, the map is empty and no facet is emitted
(`OL/integration/spark/shared/src/main/java/io/openlineage/spark/agent/JobMetricsHolder.java:184-217,262-290`).
The spec fields are `rowCount`, `size` and `fileCount`
(`OL/website/docs/spec/facets/dataset-facets/output-dataset-facets/output_statistics.md`).

**Conditions, in short:**
1. The Spark OpenLineage listener is enabled in the job (§4a).
2. The write goes through a Spark path that populates task `outputMetrics`.
3. Spark 3.x or later. A test notes "Spark rowCount metrics currently only working in Spark 3.x"
   (`OL/integration/spark/app/src/test/java/io/openlineage/spark/agent/lifecycle/SparkReadWriteIntegTest.java:187`).

**Files.** Yes. The integration test writes JSON files with `df.write().json(...)` and asserts
`outputStatistics.rowCount == 4` on the COMPLETE event (`SparkReadWriteIntegTest.java:344-374`).
JDBC writes are also asserted (`rowCount == 2`, lines 134-192). The docs list the facets as
collected by the Spark integration, with the caveat that *input* row counts only work for
DataSourceV2 (`OL/website/docs/integrations/spark/dataset_metrics.md`).

**Snowflake via the Spark-Snowflake connector.**
- *Dataset identity:* yes. The vendor module
  `OL/integration/spark/vendor/snowflake/.../SnowflakeSaveIntoDataSourceCommandDatasetBuilder.java:36-58`
  turns a `SaveIntoDataSourceCommand` against `net.snowflake.spark.snowflake.DefaultSource` into
  an output dataset from `sfurl`/`sfdatabase`/`sfschema`/`dbtable` (or `query`), with schema.
- *Row count:* **probably not.** (inference, **[UNVERIFIED]** empirically) The connector uploads
  partitions to a stage using its own cloud-storage client inside `mapPartitionsWithIndex`, then
  COPYs into the table
  (`https://github.com/snowflakedb/spark-snowflake/blob/ac1a75a1/src/main/scala/net/snowflake/spark/snowflake/io/CloudStorageOperations.scala:859-861`).
  A grep of `src/main` finds no reference to `outputMetrics`, `recordsWritten` or
  `bytesWritten`. So Spark task output metrics would stay 0, and by the gating above no
  `outputStatistics` facet would be emitted.
- No OpenLineage test asserts `outputStatistics` for Snowflake writes: the only Snowflake tests
  are `SnowflakeRelationVisitorTest` and `ColumnLevelLineageSnowflakeTest`. The integrations
  matrix (`OL/website/docs/integrations/about.md:34`) does not list Snowflake as a Spark
  datasource.
- (inference) To get a trustworthy loaded-row count for bronze, take it from Snowflake itself,
  e.g. COPY/load history or Elementary `volume_anomalies` on the bronze source with
  `timestamp_column: <load ts>`. Do not take it from the Spark event.

---

## 5. Airflow native OpenTelemetry metrics

- **Yes, native.** `[metrics] otel_on` ("Enables sending Airflow metrics to an OpenTelemetry
  Collector") was added in **2.6.0**, default `False`
  (`https://github.com/apache/airflow/blob/main/airflow-core/src/airflow/config_templates/config.yml:1334-1341`).
  Traces are separate (`[traces] otel_on`, added 2.10.0, same file ~line 1460). You need
  `pip install 'apache-airflow[otel]'` and a Collector (`AF/administration-and-deployment/logging-monitoring/metrics.html`,
  "Setup - OpenTelemetry").
- **Config keys (3.3.2 docs):** `otel_on`, `otel_prefix` (default `airflow`), `otel_service`,
  `otel_ssl_active`. Deprecated since **3.2.0** in favour of standard `OTEL_*` env vars:
  `otel_host`, `otel_port`, `otel_interval_milliseconds`, `otel_debugging_on` (config.yml
  lines 1342-1395; metrics page Note). The deprecation reason says to configure exporters
  "exclusively using the standard OpenTelemetry environment variables such as
  `OTEL_EXPORTER_OTLP_ENDPOINT`, `OTEL_EXPORTER_OTLP_PROTOCOL`, `OTEL_SERVICE_NAME`".
- **Tags become native attributes** under OTel (`otel_on` "sends tags as native attributes").
  Set `service.instance.id` via `OTEL_RESOURCE_ATTRIBUTES` per process, or HA schedulers'
  series collide (metrics page, "Identifying components and their instances").
- **Histograms:** timers go out as OTel **exponential histograms**. The page says to use
  opentelemetry-collector-contrib **≥ 0.115.0** and Prometheus native histograms
  (`--enable-feature=native-histograms` for 2.40-3.8, `scrape_native_histograms: true` for
  3.8+). Otherwise "data points may be dropped or rendered incorrectly" (metrics page,
  "Histogram Metrics and Backend Requirements"). This repo pins
  `otel/opentelemetry-collector-contrib:0.96.0` (`docker-compose.yml:164`) and
  `prom/prometheus:v2.50.1`.

**Task-level metrics** (metrics page, "Metric Descriptions"; name = new tagged name, legacy
dotted name in brackets):

| Concern | Metric | Kind | Tags |
|---|---|---|---|
| Task started | `ti.start` [`ti.start.{dag_id}.{task_id}`] | counter | dag_id, task_id |
| Task finished, by state | `ti.finish` [`ti.finish.{dag_id}.{task_id}.{state}`] | counter | dag_id, task_id, state |
| Success / failure | `ti_successes`, `ti_failures` | counter | dag_id, task_id |
| Per-operator outcome | `operator_successes`, `operator_failures` [`…_{operator_name}`] | counter | operator |
| Heartbeat-less kill | `task_instances_without_heartbeats_killed` | counter | dag_id, task_id |
| Killed externally | `scheduler.tasks.killed_externally` | counter | dag_id, task_id |
| Current state gauges | `ti.scheduled`, `ti.queued`, `ti.running`, `ti.deferred` [`….{queue}.{dag_id}.{task_id}`] | gauge | queue, dag_id, task_id |
| Run duration | `task.duration` [`dag.{dag_id}.{task_id}.duration`] | timer (ms) | dag_id, task_id |
| Wait before run | `task.scheduled_duration`, `task.queued_duration` | timer (ms) | dag_id, task_id |
| DAG run outcome/time | `dagrun.duration.success`, `dagrun.duration.failed`, `dagrun.schedule_delay`, `dagrun.first_task_scheduling_delay` | timer | dag_id |
| Retry on resumable ops | `resumable_job.reconnect_attempt`, `resumable_job.reconnect_success`, `resumable_job.terminal_resubmit` | counter | operator |

**Retries:** there is **no** dedicated generic `ti_retries` counter in the metric list.
(inference) Retries show up as `ti.finish` with `state=up_for_retry`. The docs only say `ti.finish`
is tagged by state; they do not enumerate the state values, so the exact label value is
**[UNVERIFIED]**. The `resumable_job.*` counters only cover `ResumableJobMixin` operators.

---

## Implications for the DQ anomaly proposal

1. **Elementary can own bronze detection, but only where bronze has a load timestamp.** Put
   `volume_anomalies` and `freshness_anomalies` on the bronze `sources` with
   `meta.elementary.timestamp_column: <ingest/load ts>`. Both Kafka-landed and Spark-landed
   tables need such a column. Without one, volume becomes "total rows per `dbt test` run" (a
   rising series and a full-table query), freshness is impossible, and seasonality is
   impossible. **Requirement to state in the proposal:** every bronze table gets a
   loader-stamped timestamp column.
2. **Sources get incremental metric collection for free.** After the first run, only the
   `detection_period` (default 2 days) is recomputed. That keeps bronze scans bounded, provided
   the tables are clustered or pruned on that timestamp (inference).
3. **Seasonality forces bucket choice.** Hourly Kafka lanes → `time_bucket {hour,1}` +
   `hour_of_week`. Daily Spark batches → `{day,1}` + `day_of_week`. Both multiply the history
   window ×7 (98 days by default), so cold-start needs backfilled data or a shorter
   `training_period`.
4. **Results land where the proposal expects.** They go in `elementary_test_results` /
   `data_monitoring_metrics`, in the `<target_schema>_elementary` schema (with dbt's default
   schema macro). They are written by the on-run-end hook of `dbt test`/`dbt build`, so
   detection latency equals dbt test cadence.
5. **OpenLineage gives batch-path *topology*, not a reliable bronze row count.** Airflow emits an
   event per task regardless. `SparkSubmitOperator`/Databricks/Dataproc/EMR only get
   Airflow↔Spark linkage if the Spark listener is installed and `spark_inject_parent_job_info`
   is on. Spark → files yields `outputStatistics.rowCount`. Spark → Snowflake via the connector
   very likely does not. File-copy operators give dataset identity only. **Do not design the
   "rows landed in bronze" signal on OpenLineage `outputStatistics`.** Use Elementary volume on
   the bronze source, which is warehouse truth. OpenLineage is the join key: it tells you which
   Airflow task/DAG run fed the bronze table that went anomalous.
6. **Airflow operational health is available natively over OTLP.** The metrics are
   `ti.finish{state}`, `ti_failures`, `task.duration` and the `dagrun.*` timers. They can feed
   the existing OTel Collector → Prometheus path. But the repo's pinned collector (0.96.0) is
   below the documented 0.115.0 minimum for Airflow's exponential-histogram timers, and
   Prometheus 2.50.1 needs the native-histograms flag. Plan a collector and Prometheus bump
   before relying on `task.duration`.

---

## Sources read

| Source | Version / date |
|---|---|
| `elementary-data/dbt-data-reliability` @ `9a7e2b55` (package 0.26.0): `dbt_project.yml`; `macros/edr/tests/test_{volume,freshness,event_freshness,table,column,all_columns}_anomalies.sql`; `test_configuration/get_{time_bucket,seasonality,period_vars,days_back,detection_delay}.sql`; `test_utils/get_model_relation_for_test.sql`, `get_elementary_tests_schema.sql`; `data_monitoring/monitors_query/table_monitoring_query.sql`; `data_monitors_configuration/get_buckets_configuration.sql`; `utils/graph/is_incremental_model.sql`; `system/system_utils/get_config_var.sql`; `system/hooks/on_run_end.sql`; `tests/on_run_end/handle_tests_results.sql`; `models/edr/**` listing | cloned 2026-09-22 |
| `elementary-data/elementary` @ `e34d8539` `docs/`: `data-tests/add-elementary-tests.mdx`, `data-tests/anomaly-detection-tests/*.mdx`, `anomaly-detection-configuration/{timestamp-column,training-period,detection-period,time-bucket,seasonality}.mdx`, `data-tests/data-anomaly-detection.mdx`, `_snippets/quickstart-package-install.mdx` (= docs.elementary-data.com) | cloned 2026-09-22 |
| `OpenLineage/OpenLineage` @ `d204b0e1` (Spark `1.54.0-SNAPSHOT`): `OutputStatisticsOutputDatasetFacetBuilder.java`, `JobMetricsHolder.java`, `vendor/snowflake/**`, `SparkReadWriteIntegTest.java`; `website/docs/integrations/spark/dataset_metrics.md`, `website/docs/integrations/about.md`, `website/docs/spec/facets/dataset-facets/output-dataset-facets/output_statistics.md` | cloned 2026-09-22 |
| `snowflakedb/spark-snowflake` @ `ac1a75a1`: `io/CloudStorageOperations.scala`; grep of `src/main` for output metrics | cloned 2026-09-22 |
| `AF-OL/supported_classes.html`, `AF-OL/spark.html` | provider 2.20.1, fetched 2026-09-22 |
| `apache/airflow@main` `providers/snowflake/.../transfers/copy_into_snowflake.py` | fetched 2026-09-22 |
| `AF/administration-and-deployment/logging-monitoring/metrics.html` | Airflow 3.3.2, fetched 2026-09-22 |
| `apache/airflow@main` `airflow-core/src/airflow/config_templates/config.yml` | fetched 2026-09-22 |
| PyPI JSON: `apache-airflow` 3.3.2, `apache-airflow-providers-openlineage` 2.20.1, `elementary-data` 0.26.0 | fetched 2026-09-22 |
| This repo: `docker-compose.yml:164` (collector pin) | working tree 2026-09-22 |
