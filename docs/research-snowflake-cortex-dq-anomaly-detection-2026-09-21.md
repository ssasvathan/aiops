# Research: Snowflake Cortex `ANOMALY_DETECTION` as a Detector for dbt/Elementary DQ Signal

> **Audience:** Architecture reviewers deciding where DQ anomaly verdicts get computed. Also
> engineers and LLM agents who would build whichever option wins.
>
> **Question:** Could `SNOWFLAKE.ML.ANOMALY_DETECTION` (the Snowflake ML Function once branded
> "Cortex ML-Based Functions") score the DQ series that Elementary writes into Snowflake? What
> would it add over Elementary's built-in z-score? And can its verdicts reach our Kafka-consuming
> triage pipeline, which runs outside Snowflake?
>
> **Scope:** Architecture proposal input only. No implementation, and no dollar estimates. Cost is
> given in units.
>
> **Date:** 2026-09-21. **Status:** Draft for review.

## Reading Rules

- Every non-obvious claim carries a source: a URL, or a file path in a pinned repo. Sources are
  **primary only**: docs.snowflake.com (fetched as the `.md` variants the site publishes), the
  Snowflake Service Consumption Table PDF, the `elementary-data/dbt-data-reliability` source, and
  docs.elementary-data.com.
- **[UNVERIFIED]** marks anything I could not confirm from a primary source.
- **(inference)** marks a conclusion I drew from sourced facts that no source states directly.
- This document builds on
  [`openlineage-data-quality-facets-research.md` §10.3](openlineage-data-quality-facets-research.md)
  and does not re-derive the Elementary schema. §10.3 was pinned at `c5912dfd` (0.25.1). I checked
  the facts it relies on against the new HEAD `9a7e2b55` (0.26.0), which is two commits later:
  the `data_monitoring_metrics` partition/cluster keys and the expanding-window
  `metrics_anomaly_score` view (`rows between unbounded preceding and current row`, 7-day filter)
  are unchanged.
- Snowflake paths below are relative to `https://docs.snowflake.com/en/`.

## Current-State Anchor (one paragraph)

Snowflake holds the business data that dbt builds and tests. DQ results and operational metrics
are not in Snowflake today. Metrics flow OTel Collector → Prometheus, and ClickHouse is available
as a platform. If we adopted Elementary, it would write `elementary_test_results`,
`data_monitoring_metrics` and the `metrics_anomaly_score` view into a Snowflake schema. So the DQ
series would already be sitting next to Cortex, with no extra data movement. The triage pipeline
lives outside Snowflake and consumes Kafka. The two real questions are therefore (a) is the
in-Snowflake detector any better than Elementary's, and (b) how does a verdict get out.

---

## 1. Input fit: can `ANOMALY_DETECTION` consume `data_monitoring_metrics`?

### 1.1 Required input shape

`CREATE SNOWFLAKE.ML.ANOMALY_DETECTION` syntax, verbatim
(`sql-reference/classes/anomaly-detection/commands/create-anomaly-detection`):

```sql
CREATE [ OR REPLACE ] SNOWFLAKE.ML.ANOMALY_DETECTION <model_name>(
  INPUT_DATA => <reference_to_training_data>,
  [ SERIES_COLNAME => '<series_column_name>', ]
  TIMESTAMP_COLNAME => '<timestamp_column_name>',
  TARGET_COLNAME => '<target_column_name>',
  LABEL_COLNAME => '<label_column_name>',
  [ CONFIG_OBJECT => <config_object> ]
)
[ [ WITH ] TAG ( <tag_name> = '<tag_value>' [ , <tag_name> = '<tag_value>' , ... ] ) ]
[ COMMENT = '<string_literal>' ]
```

| Argument | Requirement (source: same page) | Elementary column that maps to it |
|---|---|---|
| `INPUT_DATA` | Reference to a table, **view, or query** (`TABLE(...)`, `SYSTEM$REFERENCE`, `SYSTEM$QUERY_REFERENCE`) | A view over `data_monitoring_metrics` |
| `TIMESTAMP_COLNAME` | Column of type **TIMESTAMP_NTZ** | `bucket_end` (or `bucket_start`) |
| `TARGET_COLNAME` | **NUMERIC or FLOAT** | `metric_value` (`float`) |
| `LABEL_COLNAME` | Boolean "known anomaly" column, or `''` for unsupervised | None natively. Could come from triage feedback (inference) |
| `SERIES_COLNAME` | "should be a **VARIANT** because it can be any kind of value or a combination of values from more than one column in an array" | `[full_table_name, column_name, metric_name, dimension, dimension_value]` |

**Timestamp type.** Elementary declares `bucket_start`/`bucket_end` as `timestamp`
(`macros/edr/system/system_utils/empty_table.sql`, `default__empty_data_monitoring_metrics`). In
Snowflake, `TIMESTAMP` is an alias whose target is set by `TIMESTAMP_TYPE_MAPPING`, and that
parameter defaults to `TIMESTAMP_NTZ` (`sql-reference/parameters`, §TIMESTAMP_TYPE_MAPPING). So
the column fits as-is unless an account overrides the mapping. A `::TIMESTAMP_NTZ` cast in the
view removes the dependency (inference).

**Verdict:** the data does not fit *directly*. It fits through a thin view. Sketch (inference;
the column choices are ours):

```sql
CREATE VIEW dq_series_for_cortex AS
SELECT
  ARRAY_CONSTRUCT(full_table_name, column_name, metric_name,
                  dimension, dimension_value, metric_properties) AS series_key,  -- VARIANT
  bucket_end::TIMESTAMP_NTZ AS ts,
  metric_value AS y
FROM elementary.data_monitoring_metrics
QUALIFY ROW_NUMBER() OVER (PARTITION BY id ORDER BY updated_at DESC) = 1;  -- same dedupe Elementary applies
```

Two things in this view come from Elementary's own scoring code, not from Snowflake:

- The **dedupe on `id` / latest `updated_at`** mirrors `grouped_metrics_duplicates` in
  `macros/edr/data_monitoring/anomaly_detection/get_anomaly_scores_query.sql`.
  `data_monitoring_metrics` is append-only, and backfill re-emits recent buckets.
- **`metric_properties` in the series key.** Elementary's window partition is
  `metric_name, full_table_name, column_name, dimension, dimension_value`, but its scoring query
  also filters `metric_properties = <this test's>` (same file). One table/column/metric can
  therefore carry several series that differ in `timestamp_column`, `where_expression` or
  `time_bucket`. Merging them would mix incompatible buckets (inference).

### 1.2 Regular intervals, gaps, duplicates

| Behaviour | What Snowflake documents | Source |
|---|---|---|
| Regular intervals required? | **No.** "Ideally … equally spaced intervals … However, model training can handle real-world data that has missing, duplicate, or misaligned time steps." | `user-guide/ml-functions/anomaly-detection` §Overview |
| Frequency | Inferred by heuristics that "on rare occasions, choose the wrong frequency". Can be pinned with `CONFIG_OBJECT => {'frequency': '1 day'}` (seconds … years, full unit names) | `user-guide/ml-functions/preprocessing`; `create-anomaly-detection` config table |
| Missing time steps | Filled: "Zero if the target value aggregation behavior is SUM", otherwise "Linear interpolation from nearby values". Missing *feature* values become NULL and are ignored | `preprocessing` §Filling in values for missing time steps |
| Multiple values per step | Aggregated by `aggregation_target` (default `MEAN`; also MEDIAN, MODE, MIN, MAX, SUM, FIRST, LAST). "Use the SUM method for count data" | `preprocessing`; `create-anomaly-detection` |
| Degradation | "a relatively small number of such adjustments does not noticeably affect the accuracy". There is no documented threshold at which it degrades or rejects | `preprocessing` |
| Hard rejection | A series with fewer than 2 unique timestamps errors: `"At least two unique timestamps are required."` (shown in `SHOW_TRAINING_LOGS` output) | `anomaly-detection` §Inspecting Training Logs |
| Granularity floor | Timestamps ≥ 1 second apart. Seasonal components ≥ 1 minute | `anomaly-detection` §Limitations |

**Implications for our data (inference):**

- Elementary's own buckets are regular per `metric_properties` (daily by default:
  `get_default_time_bucket()` → `{"period": "day", "count": 1}`,
  `macros/edr/tests/test_configuration/get_time_bucket.sql`). So `data_monitoring_metrics` series
  are well-behaved.
- `elementary_test_results.failures` / `failed_row_count` are **per test execution**, stamped at
  `detected_at`. That is irregular and follows the dbt schedule. To use them, pin `frequency` and
  set `aggregation_target: 'SUM'` (or `MAX`). Otherwise interpolation invents fractional failures
  on days with no run.
- Watch the **SUM + missing step = 0** rule. A day on which dbt did not run looks like "0
  failures", which is a clean day, not a gap. That hides outages. The dbt run-freshness signal
  must come from somewhere else.

### 1.3 Minimum history

| Rows per series | Behaviour | Source |
|---|---|---|
| < 2 | Training error | `anomaly-detection` §Single Time Series: "at least 2 data points to train a model" |
| 2–11 | **"Naive"** result: "all predicted values are equal to the last observed target value" | `anomaly-detection` §Limitations |
| ≥ 12 | Main GBM algorithm ("non-naive") | same |
| ≥ 60 | "non-linear results" | `anomaly-detection` §Single Time Series |
| Labelled mode | Counts only rows where the label is false | §Limitations |

Row count is in *time steps*, so the practical history follows from the bucket size (inference):

| Bucket | Non-naive (12 steps) | Non-linear (60 steps) | Weekly cycle visible (lag-7 needs several weeks) |
|---|---|---|---|
| Daily (Elementary default) | 12 days | **60 days** | "Season length … 7 for daily data" (§Limitations). Plan on ≥ 4–8 weeks (inference) |
| Hourly | 12 hours | 60 hours (2.5 days) | "24 for hourly data". Daily cycle within days, weekly cycle needs weeks (inference) |

Two cross-checks. Snowflake's own DMF anomaly detection, a different product on the same
platform, "requires at least two weeks of DMF data" for weekly seasonality and recommends 60
days (`user-guide/data-quality-anomaly` §About the training period). Evaluation is on by default
(`evaluate: TRUE`, `n_splits: 5`), and the forecasting guide notes that without enough data "no
evaluation metrics are available" (`user-guide/ml-functions/forecasting` line ~422). For short
series, set `{'evaluate': False}` (inference).

Elementary's daily default for comparison: `days_back: 14`, `min_training_set_size: 7`
(`macros/edr/system/system_utils/get_config_var.sql`). At HEAD `9a7e2b55`,
`min_training_set_size` is accepted by every anomaly test signature but is **not** written into
the `test_configuration` dict in `get_anomalies_test_configuration.sql`. The scoring query only
nulls out `training_set_size = 1`. It looks unenforced at this commit (inference from code
reading; worth confirming before relying on it).

### 1.4 Multi-series scale (10k+ keys)

- One model object holds many series via `SERIES_COLNAME` ("each store's sales can be checked
  separately by a single model based on the store identifier", `anomaly-detection` §Overview).
  **Series are modelled independently inside one object.** Each has its own feature importance
  (`EXPLAIN_FEATURE_IMPORTANCE` returns rank per `SERIES`) and its own training log.
- **No documented maximum series count per model.** [UNVERIFIED] The largest data point Snowflake
  publishes is **1,000 series × 100,000 rows**: Standard XL 840 s, Snowpark-optimized XL 831 s,
  evaluation off (`anomaly-detection` §Training on Multi-Series Data table). "multi-series data
  trains considerably faster on larger warehouse sizes."
- For "> 100 million rows" across multiple series, the forecasting guide says "Consider batching
  training by series into multiple jobs" (`forecasting` §Warehouse selection).
- Our shape is the opposite of Snowflake's benchmark: **many series, few rows**. 10k series × 60–400
  daily rows is 0.6–4 M rows, well under the 5 M standard-warehouse ceiling. But there is no
  published timing for 10k short series, so training wall-time at that scale is [UNVERIFIED].
  Sharding by `metric_name` or by schema into a handful of models is the prudent design, and it
  also bounds the blast radius of `ON_ERROR` (inference).
- Use `ON_ERROR: 'SKIP'`. Without it, one bad series (e.g. < 2 timestamps) aborts training for all
  10k. With it, failures are listed per series by `<model>!SHOW_TRAINING_LOGS()`
  (`create-anomaly-detection` config `on_error`;
  `sql-reference/classes/anomaly-detection/methods/show_training_logs`).
- Inference throughput: "approximately 1 second to process 100 rows in the input dataset,
  regardless of warehouse size" (`anomaly-detection` §Detecting Anomalies). Scoring one new
  bucket for 10k series is therefore roughly 100 s per detection call (inference, linear
  extrapolation).

---

## 2. Cortex vs Elementary z-score: what the model adds

### 2.1 What Cortex models

From `anomaly-detection` §About the Algorithm and §Limitations:

| Capability | Cortex `ANOMALY_DETECTION` |
|---|---|
| Model | Gradient boosting machine. "Like an ARIMA model, it uses a differencing transformation to model data with a non-stationary trend and uses auto-regressive lags" |
| Trend | Yes: differencing plus "rolling averages of historical target data to help predict trends" |
| Seasonality | **Automatic** "cyclic calendar variables (such as day of week and week of year)". Lag season length tied to frequency (24 hourly, 7 daily). **Not configurable**: "does not provide parameters to override trend, seasonality, or seasonal amplitudes; these are inferred from the data" |
| Exogenous features | Yes: numeric or categorical, may be NULL, high cardinality OK (no one-hot). **They must be supplied at detection time for the timestamps being scored.** Training and detection column sets must match or it errors |
| Prediction interval | Yes. `prediction_interval` (default 0.99) at detection time. Docs suggest "very close to 1.0; 0.9999 or even closer" |
| Supervised / labelled | Yes: optional Boolean `LABEL_COLNAME` marks known anomalies in training "to avoid overfitting to known anomalies" |
| Output bounds clamp | `lower_bound` / `upper_bound` in training config: "the model will not predict values below [above] this threshold" (`create-anomaly-detection`) |
| Explanation | Global per-series feature importance only (§4.3) |
| Strictly out-of-sample | "timestamps in the test data must all be greater than timestamps in the training data"; "cannot detect anomalies in the training data" |
| Algorithm versioning | Snowflake may refine the algorithm. Existing models keep their version and you cannot revert (§About the Algorithm). A 2024-06-15 update asked users to retrain models built 2024-05-27..06-15 because of degraded performance (`release-notes/2024/other/2024-06-15-anomaly-detection`) |

### 2.2 What Elementary does, like for like

All from `macros/edr/data_monitoring/anomaly_detection/get_anomaly_scores_query.sql` and
`macros/edr/tests/test_utils/get_anomaly_query.sql` @ `9a7e2b55`:

- **Score:** `(metric_value - training_avg) / training_stddev`. Bounds:
  `training_avg ± anomaly_sensitivity * training_stddev` (`get_limit_metric_values`). Default
  `anomaly_sensitivity: 3`. Elementary's docs call the method "standard score … Z-score"
  (docs.elementary-data.com/data-tests/data-anomaly-detection).
- **Training window:** expanding, `rows between unbounded preceding and current row`, bounded by
  `days_back` (default 14). **The current point is in its own training set** unless
  `exclude_detection_period_from_training` is on. The in-code comment says so: "values in the
  detection period are included in the training calculation, which can lead to false negatives"
  (docs.elementary-data.com/data-tests/anomaly-detection-configuration/training-period).
- **Seasonality:** `seasonality: day_of_week | hour_of_day | hour_of_week`
  (`macros/edr/tests/test_configuration/get_seasonality.sql`). It adds `bucket_seasonality` to
  the window `PARTITION BY`. So Mondays are compared only with Mondays: separate
  mean/stddev buckets, not a fitted seasonal component. `day_of_week` requires a 1-day bucket,
  and `hour_of_*` requires a 1-hour bucket (compiler errors otherwise). With `day_of_week` or
  `hour_of_week`, `days_back` is multiplied by 7 (`get_days_back.sql`). Default: none
  (docs.elementary-data.com/data-tests/anomaly-detection-configuration/seasonality).
- **Direction and guards:** `anomaly_direction` (`both|spike|drop`; freshness metrics are
  spike-only). `ignore_small_changes` (spike/drop % thresholds). `fail_on_zero`. `min_value`.
  `anomaly_exclude_metrics` (a SQL predicate to drop points from training). `detection_delay`.
- **Constant series:** `training_stddev = 0` → `anomaly_score = 0` ("Stationary data case"), and
  `training_set_size = 1` → NULL.
- **Trend, exogenous features, labels, calibrated intervals:** none. The "interval" is
  ±k·σ with no distributional calibration (inference from the formula).

### 2.3 Net difference

| Dimension | Elementary z-score | Cortex `ANOMALY_DETECTION` |
|---|---|---|
| Seasonality | Manual, one of three bucket partitions. Divides the training set by 7 or 24 | Automatic calendar features + AR lags. Can't be forced on or off |
| Trend | None. A growing table drifts toward the upper bound and gets flagged | Differencing + rolling means |
| Level shift after a legit change | Expanding window slowly absorbs it. `anomaly_exclude_metrics` can drop points | Absorbed at next retrain. `LABEL_COLNAME` can mark it. No doc on shift handling [UNVERIFIED] |
| Exogenous context | No | Yes (e.g. "is_holiday", "upstream_backfill"), if also known at scoring time |
| Supervised feedback | No | Yes: boolean labels (a natural sink for triage "false positive" verdicts, inference) |
| Out-of-sample discipline | No: current point is in training by default | Yes, enforced |
| Sensitivity knob | `anomaly_sensitivity` (σ multiples) | `prediction_interval` (probability) |
| Where it runs | Inside `dbt test` (the anomaly test *is* the detector) | Separately: a scheduled/triggered task or alert |
| Explainability | Transparent formula: avg, stddev, bounds per point | Opaque GBM: forecast, bounds, percentile, and a z-like `DISTANCE` |

---

## 3. Model lifecycle

| Aspect | Documented behaviour | Source |
|---|---|---|
| Creation | Explicit DDL `CREATE [OR REPLACE] SNOWFLAKE.ML.ANOMALY_DETECTION`. Training happens at create time. Result is a **schema-level object** | `anomaly-detection` §Overview, §Training |
| Privilege | `CREATE SNOWFLAKE.ML.ANOMALY_DETECTION ON SCHEMA` | `anomaly-detection` §Granting Privileges |
| Data access | Runs "using limited privileges". Tables/views must be passed as references carrying caller privileges | §Training, Using… |
| Per-series vs shared | One object, many independently modelled series (`SERIES_COLNAME`). One model per series is equally possible (inference) | §Overview; `explain_feature_importance` returns per-`SERIES` rows |
| Update | **Immutable.** "You cannot update existing models with new data; you must train an entirely new model. Models do not support versioning." | §Limitations |
| Retraining | **Manual only**: no auto-retrain. Snowflake's pattern is a task running `CREATE OR REPLACE …` on a schedule (example uses `SCHEDULE = '60 MINUTE'`). Recommended cadence "once a day, once a week, or once a month" | §Recurring Training with a Snowflake Task; §Limitations |
| Retrain side effect | Recreating a standalone task cancels its next run (task DDL). Model `CREATE OR REPLACE` swaps the whole object: all series retrain together (inference) | `sql-reference/sql/create-task` usage notes |
| Cold start: new series | Not documented. A series absent from training has no per-series model. Likely an error at detection that `ON_ERROR: 'SKIP'` drops ("Series that failed are absent from the output") [UNVERIFIED for the unseen-series case] | `detect_anomalies` config `on_error` |
| Cold start: short series | 2–11 rows → naive last-value forecast. ≥ 12 → GBM | §Limitations |
| Clone / share / replicate | Cannot clone, share across roles/accounts, or replicate. Skipped when a schema/DB is cloned | §Limitations; `create-anomaly-detection` usage notes |
| Metadata | `SHOW SNOWFLAKE.ML.ANOMALY_DETECTION`: `created_on, name, database_name, schema_name, current_version, comment, owner` | `…/commands/show-anomaly-detection` |
| What's persisted / cost of holding | Storage of internal objects, visible in `ACCOUNT_USAGE.TABLES` and `ACCOUNT_USAGE.STAGES` with null db/schema and populated `instance_id`. "fully managed by the model instance, and you cannot access or delete them separately" | `guides-overview-ml-functions` §Cost Considerations |
| Session requirement | `AUTOCOMMIT` must be enabled | `guides-overview-ml-functions` §Limitations |

**Lifecycle implication (inference).** Scores must be strictly out-of-sample, and Elementary
re-emits the last `backfill_days` (default 2) of buckets on every run. So a restated bucket that
was already in the training set can't be re-scored until the next retrain has moved past it. The
clean pattern: retrain nightly on data up to a cutoff T, and score only buckets with `ts > T`.
Elementary instead re-scores its detection window on every `dbt test`.

---

## 4. Output

### 4.1 `DETECT_ANOMALIES` columns (verbatim from `…/methods/detect_anomalies` §Returns)

| Column | Type | Description |
|---|---|---|
| `SERIES` | VARIANT | Series value (NULL if model was trained with single time series). Present in all results since the 2024-05-10 BCR (`release-notes/bcr-bundles/un-bundled/bcr-cortex-forecast-anomaly-detection-series-column`) |
| `TS` | TIMESTAMP_NTZ | The timestamps of the data |
| `Y` | FLOAT | The values for the time series |
| `FORECAST` | FLOAT | The predicted value at the timestamp |
| `LOWER_BOUND` | FLOAT | Lower bound of the prediction interval. Lower values are flagged |
| `UPPER_BOUND` | FLOAT | Upper bound of the prediction interval. Higher values are flagged |
| `IS_ANOMALY` | BOOLEAN | True if the value is an anomaly |
| `PERCENTILE` | FLOAT | Percentile of observed Y given the interval. Anomalous if outside `((1 - alpha) / 2, 1 - (1 - alpha) / 2)` |
| `DISTANCE` | FLOAT | "The multiple of the standard deviation from the FORECAST column (z-score)" |

Syntax (verbatim):

```sql
<model_name>!DETECT_ANOMALIES(
  INPUT_DATA => <reference_to_data_to_analyze>,
  TIMESTAMP_COLNAME => '<timestamp_column_name>',
  TARGET_COLNAME => '<target_column_name>',
  [ CONFIG_OBJECT => <configuration_object>, ]
  [ SERIES_COLNAME => '<series_column_name>' ]
)
```

Results can be persisted with `CREATE TABLE … AS SELECT * FROM TABLE(model!DETECT_ANOMALIES(...))`
(`anomaly-detection` §Using…). That table is what any egress path would read.

### 4.2 Tunables at detection time

- `prediction_interval` (FLOAT, default 0.99) and `on_error` (`'abort'|'skip'`). Nothing else.
- **Doc inconsistency to be aware of:** the reference table describes `prediction_interval` as
  "the percentage of the observations that should be marked as anomalies" and calls a *higher*
  value "less strict … fewer observations marked". The user guide says "0.99 … means that roughly
  1% of the data is marked". Both agree that **higher = fewer anomalies**; the "percentage marked"
  wording is wrong (inference).
- Training-time tunables (`create-anomaly-detection`): `frequency`, `aggregation_target`,
  `aggregation_numeric`, `aggregation_categorical`, `lower_bound`, `upper_bound`, `evaluate`,
  `evaluation_config` (`n_splits` 5, `max_train_size`, `test_size`, `gap`,
  `prediction_interval` 0.95), `on_error`.

### 4.3 Explanation

- **There is no per-point "why".** `<model>!EXPLAIN_FEATURE_IMPORTANCE()` returns
  `SERIES, RANK, FEATURE_NAME, IMPORTANCE_SCORE, FEATURE_TYPE` (`user_provided` |
  `derived_from_timestamp` | `derived_from_endogenous`) per series for the **model**, not per
  anomaly. It counts how often trees split on each feature. Scores are normalised to sum to 1,
  and "should be considered estimates". "For extremely simple series (for example, when the target
  column has a constant value), all feature importance scores may be zero"
  (`…/methods/explain_feature_importance`; `anomaly-detection` §Understanding Feature Importance).
- `<model>!SHOW_EVALUATION_METRICS()` returns cross-validated `MAE, MAPE, MDA, MSE, SMAPE,
  COVERAGE_INTERVAL, WINKLER_ALPHA` per series. It can also be computed on new out-of-sample data
  (`…/methods/show_evaluation_metrics`). This is a per-series model-quality signal we could use to
  suppress verdicts from badly fitting series (inference).
- For a triage casefile, the per-point evidence available is `Y, FORECAST, LOWER/UPPER_BOUND,
  PERCENTILE, DISTANCE`. That is richer than Elementary's `training_avg / stddev / min/max`
  because it is seasonality- and trend-aware. But it is not explainable in the same arithmetic way
  (inference).

---

## 5. Latency and freshness

`ANOMALY_DETECTION` is **batch only**. Scoring is a SQL call over a table/view/query reference.
There is no streaming or per-row trigger inside the function (`detect_anomalies`). Latency is set
by what invokes it.

| Invoker | Granularity | Source |
|---|---|---|
| Scheduled task | `SCHEDULE = '<num> { HOURS \| MINUTES \| SECONDS }'` or CRON. Docs show `'10 SECONDS'` and `'30 SECONDS'` examples. Exact min/max of `<num>` not stated on the pages read [UNVERIFIED]. One instance at a time: an overrunning run skips the next slot | `user-guide/tasks-intro` §Run a task on a fixed schedule; `sql-reference/sql/create-task` |
| **Triggered task** (`WHEN SYSTEM$STREAM_HAS_DATA('<stream>')`) | Runs when a stream on the table/view has data. **Default at most every 30 s**. `USER_TASK_MINIMUM_TRIGGER_INTERVAL_IN_SECONDS` min **10**, max 604800. Health check every 12 h. Serverless form requires `TARGET_COMPLETION_INTERVAL` (10 s – 24 h) | `user-guide/tasks-triggered`; `create-task` |
| Alert on a schedule | `SCHEDULE = '<num> MINUTE'` (whole minutes, **1 minute minimum** in practice; max `11520` = 8 days) or CRON. "only guarantee that conditions are not evaluated *before* their set interval" | `sql-reference/sql/create-alert` §SCHEDULE |
| Alert on new data | Runs when new rows land in one table/view with change tracking. **The condition may not call stored procedures, use CTEs, DML or joins.** So it can't call `DETECT_ANOMALIES` itself; it can only watch a results table | `user-guide/alerts` §Alerts on new data |

**Realistic end-to-end chain (inference, from the numbers above):**

```
dbt test → Elementary on-run-end INSERT into data_monitoring_metrics
  → stream on data_monitoring_metrics
  → triggered task (≤30 s default, ≥10 s tuned) runs DETECT_ANOMALIES on buckets with ts > last_train_cutoff
       (~1 s / 100 rows scored + warehouse resume; user-managed warehouses bill ≥60 s per resume)
  → INSERT into dq_anomaly_results
  → same task (or alert-on-new-data) emits the verdict (§6)
```

That gives **tens of seconds to low minutes** after the Elementary insert commits, dominated by the
trigger interval and warehouse resume. That is not much worse than Elementary's in-run verdict.
Note, though, that Elementary's verdict is available *inside the dbt run*, before on-run-end
completes, while Cortex's arrives *after* it. Retraining is a separate, slower (nightly) task. A
`CREATE OR REPLACE` retrain of a large multi-series model takes minutes (§1.4 table) and must not
overlap scoring (inference).

---

## 6. Egress: getting a verdict out of Snowflake

### 6.1 Mechanisms, what they can reach, and whether they can carry a structured event

| Mechanism | Direction / targets | Payload | Constraints | Source |
|---|---|---|---|---|
| `SYSTEM$SEND_SNOWFLAKE_NOTIFICATION` + **queue** notification integration | Outbound to **Amazon SNS**, **Google Pub/Sub**, **Azure Event Grid** | `application/json` via `SNOWFLAKE.NOTIFICATION.APPLICATION_JSON(...)`. Returns "Enqueued notifications" (async) | **Same cloud platform as the account**: SNS only from AWS-hosted accounts, Pub/Sub only from GCP, Event Grid only from Azure. Government regions can't send to commercial regions | `user-guide/notifications/snowflake-notifications`; `user-guide/notifications/queue-notifications`; `sql-reference/sql/create-notification-integration-queue-outbound-{aws,gcp,azure}` |
| Webhook notification integration | Outbound HTTPS, **allowlisted hosts only**: `hooks.slack.com/services/…`, MS Teams Logic Apps / Power Platform workflow URLs, `events.pagerduty.com/v2/enqueue`, `api-private.atlassian.com/automation/webhooks/jira/…`, `<instance>.service-now.com/…` | Templated body (`WEBHOOK_BODY_TEMPLATE`), custom headers, secret | **Cannot target an arbitrary URL** (so not our ingest endpoint or a Kafka REST proxy). Not in PRC | `sql-reference/sql/create-notification-integration-webhooks` §WEBHOOK_URL |
| Email notification integration | Email to verified addresses | text/html | Human channel only. Content may be retained up to 30 days (AWS SES) | `snowflake-notifications` |
| **Python/Java/Scala UDF or procedure + External Access Integration** | Any host allowed by an `EGRESS` `HOST_PORT` network rule. **Any port** ("valid port range is 1-65535 … To allow access to all ports, define the port as 0"). Default 443 | Whatever the handler sends | Only Java/Python/Scala handlers. Private connectivity (PrivateLink/PSC) needs **Business Critical**. Trial accounts disabled by default. Billed as warehouse time + data transfer (`TRANSFER_TYPE = EXTERNAL_ACCESS`) | `developer-guide/external-network-access/external-network-access-overview`; `…-limitations`; `sql-reference/sql/create-network-rule`; `…/external-network-access-billing` |
| External functions | Scalar remote call via a proxy (Amazon API Gateway, Azure API Management) → remote service | Row batches as JSON | Must behave like a function (one row out per row in). Separate data-transfer billing | `sql-reference/external-functions-introduction` |
| Snowflake Connector for Kafka | **Ingest only**: "The current version of the Kafka connector is limited to loading data into Snowflake" | — | No Snowflake → Kafka direction | `user-guide/kafka-connector-overview` |

**A native Kafka producer is available inside Snowflake Python.** The Snowflake Anaconda channel
publishes `python-confluent-kafka` **2.2.0** (py38–py311) and `aiokafka` **0.14.0** (py311–py314)
for linux-64 (`https://repo.anaconda.com/pkgs/snowflake/linux-64/repodata.json`, read
2026-09-21). With an External Access Integration opening the broker `host:port`, a Python stored
procedure could produce to Kafka directly. I did not check whether librdkafka's TCP/SASL/TLS
traffic works end to end through the egress proxy. That is [UNVERIFIED]; spike it before relying
on it.

### 6.2 Which paths can deliver a *structured anomaly event* to a Kafka consumer?

- **Yes, directly:** Python procedure + EAI → Kafka brokers (confluent-kafka), or → an HTTPS Kafka
  REST proxy / our own ingest endpoint.
- **Yes, via one cloud hop:** queue notification (JSON) → SNS / Pub/Sub / Event Grid → a bridge
  into Kafka (e.g. a Kafka Connect source for SQS or Pub/Sub, or a small forwarder). The bridge is
  outside Snowflake's docs, and its specifics are [UNVERIFIED] here.
- **Yes, pull-based:** our side polls `dq_anomaly_results` (Snowflake connector / JDBC / SQL API)
  and produces to Kafka. Snowflake does nothing beyond writing the table (inference).
- **Via a proxy:** external function → API Gateway/APIM → function → Kafka. Awkward, since the
  scalar-function contract fights a fire-and-forget event (inference).
- **No:** webhooks (host allowlist), email, the Kafka connector (sink only).

---

## 7. Cost model (units, not estimates)

| Component | Unit | Source |
|---|---|---|
| `ANOMALY_DETECTION` training + `DETECT_ANOMALIES` | **Virtual-warehouse credits** for the warehouse that runs the statement. There is no ML-Functions line item: the Service Consumption Table (effective 2026-09-16) lists none in Table 5 (Serverless) or the AI tables (inference by absence). Docs: "you incur storage and compute costs" | `guides-overview-ml-functions` §Cost Considerations; Consumption Table |
| Standard warehouse | XS 1, S 2, M 4, L 8, XL 16, 2XL 32 … credits/hour. Per-second after a **60-second minimum** per start/resume | Consumption Table, Table 1(a) and preamble |
| Gen 2 warehouse | AWS/GCP XS 1.35 … ; Azure XS 1.25 … credits/hour | Table 1(b) |
| Snowpark-optimized warehouse | `MEMORY_1X` XS 1.00 … ; `MEMORY_16X` from M 6.00 … credits/hour | Table 1(c) |
| Warehouse choice | Single series: bigger warehouse does not speed training. Multi-series: bigger is faster. > 5 M rows in the largest series → Snowpark-optimized | `anomaly-detection` §Selecting a Virtual Warehouse |
| Model storage | Storage for model-internal tables/stages (`instance_id` in `ACCOUNT_USAGE.TABLES/STAGES`) | `guides-overview-ml-functions` |
| Serverless tasks | Compute-Hours × multiplier **0.9**, Cloud Services × **1**. "Serverless Tasks Flex" **0.5** / 1. One Compute-Hour = XS-equivalent for 1 h, per-second | Consumption Table, Table 5 + Serverless Features preamble |
| Serverless alerts | **0.9** / 1 | Table 5 |
| User-managed task / alert | Warehouse credits, 60 s minimum per resume ("even a simple action that sends an email notification incurs at least one minute of warehouse cost") | `user-guide/tasks-intro` §Task costs; `user-guide/alerts` §serverless |
| Triggered tasks | "don't use compute resources until the event is triggered". Skipped checks cost nothing | `user-guide/tasks-triggered` |
| Cloud Services | 4.4 credits/hour. Free up to 10% of daily warehouse credits. Serverless-feature CS usage doesn't count toward the adjustment | Consumption Table preamble |
| External network access | Warehouse time + data transfer (`EXTERNAL_ACCESS`) + third-party charges | `…/external-network-access-billing` |
| (Adjacent) Snowflake DMF Data Quality Monitoring | 2 / 1 multiplier. `ROW_COUNT` DMF 0.9 | Table 5 + footnote 13 |

Whether ML Function calls can run on **serverless** task compute rather than a named warehouse
is not documented [UNVERIFIED]. Every Snowflake example specifies `WAREHOUSE =`.

---

## 8. Documented limitations and failure modes

| Failure mode | What Snowflake says | Consequence for DQ series (inference unless quoted) |
|---|---|---|
| Short history | < 12 rows → naive last-value forecast. < 60 → linear only. < 2 → error | New tables/columns get naive verdicts for 12 buckets. With daily buckets, ~2 months to full fidelity |
| Anomalies in training data | "cannot detect anomalies in the training data … Ensure that the training data covers a typical period free of actual outliers, or label known outliers" | Past incidents inflate intervals unless labelled. We need a label source |
| Level shifts / regime change | Not addressed. Only guidance: retrain regularly "to help the model keep up with changing trends" | [UNVERIFIED] behaviour. A legit step change keeps firing until the next retrain includes it, then becomes normal |
| Low-variance / constant series | Only statement: feature importances "may be zero" for constant targets. No documented interval behaviour for constant series [UNVERIFIED] | Elementary is explicit (`stddev = 0 → score 0`, never anomalous). Cortex behaviour on the first deviation after a constant run must be tested |
| Zero-heavy counts (`failures = 0`) | No specific guidance. Tools: `aggregation_target: 'SUM'` for counts, `lower_bound: 0` to stop negative forecasts | A GBM on mostly-zero series yields near-zero intervals. Plausibly every non-zero is flagged, which may be exactly right for "failures", but that is a threshold rule, not ML [UNVERIFIED] |
| Missing steps | Interpolated, or zero-filled under SUM | "No run" can masquerade as "clean" |
| Wrong frequency inference | "on rare occasions, choose the wrong frequency" | Always pin `frequency` |
| One bad series aborts all | Default `on_error: 'ABORT'` | Use `SKIP` + `SHOW_TRAINING_LOGS` |
| No tuning of algorithm | "You cannot choose or adjust the anomaly detection algorithm" | No per-metric custom seasonality like Elementary's `hour_of_week` |
| Algorithm drift across releases | New models get new versions. Old models keep theirs. No rollback. 2024-06 regression incident | Pin by recording `current_version` from `SHOW` |
| Object portability | No clone, share, or replication (skipped on clone) | DR/failover accounts must retrain |
| Region / edition | `ANOMALY_DETECTION` GA since release 7.44 (Dec 14–15, 2023) (`release-notes/2023/7_44`). The preprocessing page says "This feature is not available in the People's Republic of China". **No edition requirement found** on the ML Function pages. Contrast: DMF anomaly detection needs **Enterprise** (`user-guide/data-quality-anomaly`). Webhook integrations not in PRC. Queue integrations tied to the account's cloud | Check account cloud before picking the queue egress path |

---

## (a) Comparison: Cortex `ANOMALY_DETECTION` vs Elementary z-score

| Dimension | Elementary z-score (`dbt-data-reliability` 0.26.0) | Cortex `SNOWFLAKE.ML.ANOMALY_DETECTION` |
|---|---|---|
| **Input fit** | Native: reads its own `data_monitoring_metrics` | Needs a view: VARIANT series key, TIMESTAMP_NTZ, FLOAT target. Irregular `test_results` counts need pinned `frequency` + `SUM` aggregation |
| **Min history** | Default `days_back` 14. `min_training_set_size` 7 exists but appears unenforced at HEAD (inference) | 12 steps non-naive, 60 non-linear. Weekly seasonality realistically ≥ several weeks of daily buckets |
| **Seasonality** | Manual: `day_of_week` / `hour_of_day` / `hour_of_week` partitions | Automatic calendar + lag features. Not overridable |
| **Trend** | None | Yes |
| **Exogenous / labels** | No / No | Yes / Yes |
| **Lifecycle** | Stateless SQL recomputed per `dbt test`. No model object | Explicit immutable model object. Retrain = `CREATE OR REPLACE` via task. No auto-retrain. No clone/replication |
| **Cold start** | Score NULL until 2 points. Then z-score on tiny samples | Naive until 12 rows. Unseen series undocumented |
| **Output** | `anomaly_score, training_avg, training_stddev, min/max_metric_value, is_anomalous`, written to `elementary_test_results` | `SERIES, TS, Y, FORECAST, LOWER_BOUND, UPPER_BOUND, IS_ANOMALY, PERCENTILE, DISTANCE` |
| **Sensitivity** | `anomaly_sensitivity` (σ), direction, % guards, `fail_on_zero` | `prediction_interval` only (+ training `lower/upper_bound`) |
| **Explanation** | Arithmetic, fully transparent | Per-series feature importance + CV metrics. No per-point attribution |
| **Latency** | In-run: verdict exists when `dbt test` finishes | Post-run: stream → triggered task (≥10 s, default 30 s) + warehouse resume. Tens of seconds to minutes |
| **Egress** | Rows in Snowflake tables (+ Elementary CLI/Cloud alerting, out of scope) | Same tables. Plus native queue notifications (SNS/PubSub/EventGrid), EAI Python procs. No arbitrary webhooks |
| **Cost** | Warehouse credits of the dbt test run | Warehouse credits for training (dominant) + scoring (~1 s/100 rows) + serverless task/alert at 0.9× Compute-Hours + model storage |

## (b) Fits Elementary DQ series: **conditionally**

It fits, if **all** of these hold:

1. **A view reshapes `data_monitoring_metrics`.** The series key is a VARIANT array that includes
   `metric_properties`. Rows are deduped on `id` by latest `updated_at`. Timestamps are cast to
   TIMESTAMP_NTZ (§1.1).
2. **`frequency` is pinned per model.** Mixed bucket sizes live in separate models (§1.2).
3. **Enough history exists.** At least 12 buckets for any verdict and ~60 for full fidelity:
   about 2 months at Elementary's daily default. Series below that are routed to Elementary's
   z-score or suppressed (§1.3).
4. **Training runs as a scheduled `CREATE OR REPLACE` task with a cutoff,** and scoring only
   touches `ts > cutoff`. This means accepting that Elementary's backfill restatements are not
   re-scored until the next retrain (§3).
5. **Scale is sharded.** Models are split so that no single `CREATE OR REPLACE` retrains all 10k+
   series. `ON_ERROR: 'SKIP'` is set and `SHOW_TRAINING_LOGS` is monitored. The per-model series
   ceiling is unpublished (§1.4).
6. **Zero-heavy count series (`failures`, `failed_row_count`) are handled deliberately.** Either
   keep them on a rule (failures > 0 is already a verdict; dbt raises it) or model them with
   `aggregation_target: 'SUM'` + `lower_bound: 0`, and validate empirically first. Constant-series
   behaviour is undocumented (§8).
7. **A label source exists** for known incidents (triage outcomes → `LABEL_COLNAME`). Otherwise
   past incidents widen intervals (§8).

It does **not** fit for the checks Elementary evaluates as discrete events (schema changes via
`schema_columns_snapshot`, pass/fail dbt tests). Those are not time series.

Where Cortex clearly beats Elementary: trending tables (row counts that grow), multi-period
seasonality without hand configuration, and series where known context (holidays, planned
backfills) can be supplied as exogenous columns at scoring time.

## (c) Verdict egress to our triage pipeline: viable paths, least build first

| Rank | Path | What we'd build | Structured event? | Gating conditions |
|---|---|---|---|---|
| 1 | **Python stored procedure + External Access Integration → Kafka** (confluent-kafka 2.2.0 from Snowflake's Anaconda channel), called at the end of the scoring task | Network rule (`HOST_PORT`, broker ports), secret, EAI, one ~50-line proc | Yes: we control the schema (e.g. reuse the casefile event contract) | Brokers must be reachable from Snowflake egress. Private path needs Business Critical. librdkafka-through-EAI is [UNVERIFIED]. Spike first. Fallback: same proc → HTTPS REST proxy / our ingest API |
| 2 | **Pull: our side polls `dq_anomaly_results`** (high-water mark on `TS`/insert time) and produces to Kafka | One small poller service (or a JDBC source connector) with a Snowflake service user | Yes | No Snowflake-side egress config at all. Adds poll latency and holds a warehouse or SQL API connection |
| 3 | **Queue notification** (`SYSTEM$SEND_SNOWFLAKE_NOTIFICATION` + `APPLICATION_JSON`) → SNS / Pub/Sub / Event Grid → bridge to Kafka | Notification integration + cloud IAM + a bridge (Kafka Connect source or forwarder) | Yes (JSON) | Queue must be on the **same cloud** as the Snowflake account. Bridge is an extra moving part outside Snowflake |
| 4 | External function → API Gateway / APIM → function → Kafka | API integration, gateway, function, Kafka client | Yes, but forced into a scalar-function contract | Most infrastructure. No advantage over rank 1 |
| — | Webhook integration | — | — | **Not viable**: URL allowlist (Slack/Teams/PagerDuty/Jira/ServiceNow only) |
| — | Snowflake Kafka connector | — | — | **Not viable**: ingest only |
| — | Email | — | — | Human channel only |

Framing note (inference): all four viable paths publish rows that are already in a Snowflake
table. The same paths would carry **Elementary's** verdicts (`elementary_test_results` rows where
`test_type = 'anomaly_detection'`). So egress does not favour Cortex over Elementary. The detector
choice and the egress choice can be made independently.

## (d) Sources read

| Source | Version / date |
|---|---|
| `user-guide/ml-functions/anomaly-detection` (.md) | fetched 2026-09-21 |
| `sql-reference/classes/anomaly_detection` | fetched 2026-09-21 |
| `sql-reference/classes/anomaly-detection/commands/create-anomaly-detection` | fetched 2026-09-21 |
| `sql-reference/classes/anomaly-detection/commands/show-anomaly-detection` | fetched 2026-09-21 |
| `sql-reference/classes/anomaly-detection/methods/detect_anomalies` | fetched 2026-09-21 |
| `…/methods/explain_feature_importance`, `…/show_evaluation_metrics`, `…/show_training_logs` | fetched 2026-09-21 |
| `user-guide/ml-functions/preprocessing` | fetched 2026-09-21 |
| `user-guide/ml-functions/forecasting` | fetched 2026-09-21 |
| `guides-overview-ml-functions` (cost, limitations) | fetched 2026-09-21 |
| `release-notes/2023/7_44` (GA), `release-notes/2024/other/2024-06-15-anomaly-detection`, `release-notes/bcr-bundles/un-bundled/bcr-cortex-forecast-anomaly-detection-series-column` | as published |
| `user-guide/data-quality-anomaly` (DMF anomaly detection, for contrast) | fetched 2026-09-21 |
| `user-guide/tasks-intro`, `user-guide/tasks-triggered`, `sql-reference/sql/create-task` | fetched 2026-09-21 |
| `user-guide/alerts`, `sql-reference/sql/create-alert` | fetched 2026-09-21 |
| `user-guide/notifications/about-notifications`, `…/queue-notifications`, `…/snowflake-notifications`, `…/webhook-notifications` | fetched 2026-09-21 |
| `sql-reference/sql/create-notification-integration` + `-webhooks`, `-queue-outbound-aws/-gcp/-azure` | fetched 2026-09-21 |
| `sql-reference/stored-procedures/system_send_snowflake_notification` | fetched 2026-09-21 |
| `developer-guide/external-network-access/external-network-access-overview`, `…-limitations`, `…-billing`, `…/creating-using-external-network-access`; `sql-reference/sql/create-network-rule` | fetched 2026-09-21 |
| `sql-reference/external-functions-introduction` | fetched 2026-09-21 |
| `user-guide/kafka-connector-overview` | fetched 2026-09-21 |
| `user-guide/cost-understanding-compute`, `user-guide/cost-understanding-data-transfer` | fetched 2026-09-21 |
| `sql-reference/parameters` (§TIMESTAMP_TYPE_MAPPING), `sql-reference/data-types-datetime` | fetched 2026-09-21 |
| Snowflake Service Consumption Table (`snowflake.com/legal-files/CreditConsumptionTable.pdf`) | **Effective September 16, 2026** |
| Snowflake Anaconda channel `repo.anaconda.com/pkgs/snowflake/linux-64/repodata.json` | read 2026-09-21: `python-confluent-kafka` 2.2.0, `aiokafka` 0.14.0 |
| `elementary-data/dbt-data-reliability` @ `9a7e2b55` (release 0.26.0, 2026-09-08): `get_anomaly_scores_query.sql`, `get_anomaly_query.sql`, `get_seasonality.sql`, `get_days_back.sql`, `get_time_bucket.sql`, `get_detection_delay.sql`, `get_anomalies_test_configuration.sql`, `get_config_var.sql`, `empty_table.sql`, `column_numeric_monitors.sql`, `metrics_anomaly_score.sql`, `data_monitoring_metrics.sql` | cloned 2026-09-21. Delta from §10.3's `c5912dfd`: 2 commits (`a1079994` adds a `metric_stability` test; `9a7e2b55` release) |
| docs.elementary-data.com: `data-tests/data-anomaly-detection`, `…/anomaly-detection-configuration/seasonality`, `…/training-period`, `…/anomaly-sensitivity` | fetched 2026-09-21 |
| `docs/openlineage-data-quality-facets-research.md` §10.3 (this repo) | Elementary facts reused, not re-derived |
