# Research: Elementary Operations Facts — PII, Warehouse Cost, Repeat Firing, External Reads

> **Audience:** Design reviewers of the proposal to use Elementary as the in-Snowflake data-quality
> detector, with our external triage pipeline consuming verdicts by polling Elementary's result
> tables.
>
> **Question:** Five operational facts the design review needs. (1) Does Elementary store failing
> row samples or raw column values, and can that be switched off? (2) What do the anomaly tests
> actually cost per dbt invocation, and which knobs reduce it? (3) If an anomaly persists, does
> Elementary re-fire every run, and is there suppression a table-reader can rely on? (4) What
> privileges does an external poller need, and is there a safe append-only watermark column?
> (5) What is in a verdict row, column by column?
>
> **Scope:** Architecture proposal input only. No implementation.
>
> **Date:** 2026-09-22. **Status:** Draft for review.

## Reading Rules

- Every non-obvious claim carries a source: a URL, or a file path in a pinned repo (see
  [Sources read](#sources-read)). Sources are **primary only**:
  `elementary-data/dbt-data-reliability` (the dbt package),
  `elementary-data/elementary` (the `edr` CLI, and the `docs/` tree that renders as
  docs.elementary-data.com), `dbt-labs/dbt-snowflake` (read only to resolve one timestamp
  question), and docs.snowflake.com.
- **[UNVERIFIED]** marks anything I could not confirm from a primary source.
- **(inference)** marks a conclusion I drew from sourced facts that no source states directly.
- Short path prefixes:
  - `EDR/` = `https://github.com/elementary-data/dbt-data-reliability/blob/9a7e2b55/`
    (v0.26.0, commit `9a7e2b559693e662c30672b2d449b4025c254cd9`, 2026-09-08)
  - `CLI/` = `https://github.com/elementary-data/elementary/blob/e34d8539/`
    (commit `e34d8539b9c7f350c2de9ee954794d40b9260d93`, 2026-09-10)
  - `EDOCS/` = `https://docs.elementary-data.com/` (source: `elementary-data/elementary@e34d8539:docs/`)
  - `SF/` = `https://docs.snowflake.com/en/`

---

## 0. Executive summary for the review

| # | Question | Short answer |
|---|---|---|
| 1 | Failed-row samples / PII | **Yes, by default.** Up to 5 raw failing rows per dbt test go to `test_result_rows.result_rows` as JSON. Globally killable with one var: `test_sample_row_count: 0`. Anomaly tests store **only aggregates**, no raw rows — but `source_value`/`other` can carry one raw value (a freshness timestamp, or a `dimension_value`). |
| 2 | Warehouse cost | The expensive knob is `timestamp_column`. Without it, **every monitor full-scans the table every run**. With it, scans are windowed. Incremental bucket reuse only kicks in for **incremental models and sources** — a `table`-materialised model recomputes the whole `days_back` window (default 14 days) every run. `all_columns_anomalies` issues **one query per column**. |
| 3 | Repeat firing | **Yes, it re-fires every run** while the anomalous bucket is inside the `backfill_days` window (default 2 days). Suppression is an **`edr` CLI feature only**, not visible to a table reader (see §3). |
| 4 | External reads | `USAGE` on database + schema, `SELECT` on the tables. `created_at` is the insert-time watermark; tables are **append-only on Snowflake** (no update/delete/purge). Two caveats: `created_at` is **session-timezone, not UTC**, and `id` can repeat. |
| 5 | Verdict row | `elementary_test_results` has 28 columns; `data_monitoring_metrics` has 15. The rich anomaly payload (score, bounds, training stats) lives in the **`result_rows` JSON**, not in flat columns. |

---

## 1. Failed row samples and raw column values

### 1.1 Two different storage paths, and they behave differently

Elementary writes test outcomes through two distinct code paths, and only one of them touches
raw data:

| Path | Applies to | Raw rows stored? |
|---|---|---|
| `handle_dbt_test` | **Ordinary dbt tests** (`not_null`, `unique`, `accepted_values`, `dbt_expectations.*`, your own singular tests) and Elementary's non-anomaly tests | **Yes** — up to `test_sample_row_count` whole rows |
| `store_anomaly_test_results` | **Anomaly tests** (`volume_anomalies`, `freshness_anomalies`, `table_anomalies`, `column_anomalies`, `all_columns_anomalies`, `dimension_anomalies`) | **No raw rows** — only aggregate metric rows |

The split is made in the test materialization, which short-circuits for Elementary's own
anomaly/schema tests before the sampling code is ever reached
(`EDR/macros/edr/materializations/test/test.sql:30-39`):

```jinja
{% if test_namespace == "elementary" %}
    {% set elementary_test_type = elementary.get_elementary_test_type(...) %}
    {% if elementary_test_type and elementary_test_type != "with_context" %}
        {# Anomaly detection and schema change tests handle their own result row collection #}
        {% do return(materialization_macro()) %}
    {% endif %}
{% endif %}
```

### 1.2 Ordinary dbt tests: 5 raw rows per failing test, by default

`handle_dbt_test` reads a sample limit and then **re-runs the test's own compiled SQL** with a
`LIMIT` on it (`EDR/macros/edr/materializations/test/test.sql:69-70, 212-235`):

```jinja
{% set sample_limit = elementary.get_config_var("test_sample_row_count") %}
...
    with test_results as (
      {{ sql }}
    )
    select * from test_results {% if sample_limit is not none %} limit {{ sample_limit }} {% endif %}
```

Because a dbt generic test's compiled SQL is `select * from <model> where <failing condition>`,
**whatever columns the test selects is exactly what gets stored** — the package says so in a
comment (`EDR/macros/edr/tests/test_utils/get_context_select_clause.sql:5-6`):

> "(see `query_test_result_rows`), so whatever a test selects is exactly what ..."

The default is **5 rows** (`EDR/macros/edr/system/system_utils/get_config_var.sql:128`):

```jinja
"test_sample_row_count": 5,
```

Note also the cost side-effect: sampling is a **second execution of the test query** against the
monitored table, on every failing test. It is skipped when the test passes
(`ignore_passed_tests=true`, `EDR/macros/edr/materializations/test/test.sql:107-109, 225-228`)
and skipped entirely without a query when `sample_limit == 0`
(`EDR/.../test.sql:213-215`: *"performance: no need to run a sql query that we know returns an empty list"*).

### 1.3 Where the sample lands

By default, samples go to their **own table**, `test_result_rows`, not into
`elementary_test_results` (`EDR/macros/edr/system/system_utils/get_config_var.sql:147`):

```jinja
"store_result_rows_in_own_table": true,
```

`test_result_rows` has six columns (`EDR/models/edr/run_results/test_result_rows.sql:16-25`):

| Column | Type | Meaning |
|---|---|---|
| `elementary_test_results_id` | long_string | FK to `elementary_test_results.id` |
| `result_row` | long_string | **the raw failing row, serialised** |
| `detected_at` | timestamp | |
| `created_at` | timestamp | insert time |
| `row_index` | int | |
| `test_type` | string | |

If `store_result_rows_in_own_table` is set to `false`, the sample is instead rendered into the
`result_rows` column of `elementary_test_results`, subject to a size cap
(`EDR/macros/edr/tests/on_run_end/handle_tests_results.sql:9-22, 146-152, 313-316`; the cap is
`long_string_size`, default 65535 — `get_config_var.sql:140`).

**Both tables live in the same Elementary schema**, so a reader granted `SELECT` on the schema to
poll verdicts would also be able to read the samples unless samples are disabled or grants are
made table-by-table. (inference — see §4.1.)

### 1.4 Turning samples off — four mechanisms, one global

The precedence order is documented in a comment block
(`EDR/macros/edr/materializations/test/test.sql:84-95`) and implemented at lines 96-105:

```jinja
{% if disable_test_samples %} {% set sample_limit = 0 %}
{% elif elementary.should_show_sample_rows(flattened_test) %}
{# Tag explicitly opts in — keep sample_limit as-is #}
{% elif elementary.get_config_var("enable_samples_on_show_sample_rows_tags") %}
    {# Feature is on but no show_sample_rows tag found — hide by default #}
    {% set sample_limit = 0 %}
{% elif elementary.is_pii_table(flattened_test) %} {% set sample_limit = 0 %}
{% elif elementary.is_pii_test(flattened_test) %} {% set sample_limit = 0 %}
{% elif elementary.should_disable_sampling_for_pii(flattened_test) %}
    {% set sample_limit = 0 %}
{% endif %}
```

| Mechanism | Where set | Default | Effect |
|---|---|---|---|
| `test_sample_row_count: 0` | `vars:` in `dbt_project.yml` (global), or per-test `meta` | `5` | **Global kill switch.** `sample_limit == 0` returns `[]` without running any query. |
| `meta: {disable_test_samples: true}` | per test | unset | Per-test kill switch; highest precedence. |
| `disable_samples_on_pii_tags: true` + `pii_tags: ["pii"]` | `vars:` | `false` / `["pii"]` | Opt-**out**: any model, test, or column tagged `pii` gets no sample. Column-level tagging redacts just those columns from the sample (`get_columns_to_exclude_from_sampling`, `EDR/.../test.sql:297-306`). |
| `enable_samples_on_show_sample_rows_tags: true` + `show_sample_rows_tags` | `vars:` | `false` / `["show_sample_rows"]` | Opt-**in**: samples hidden by default, shown only on tagged objects. PII tags still win (`EDR/macros/edr/system/system_utils/should_show_sample_rows.sql:8-10`). |

> **Recommendation for our design (inference):** for a fail-closed posture, set
> `enable_samples_on_show_sample_rows_tags: true` (deny-by-default) rather than relying on
> `disable_samples_on_pii_tags` (allow-by-default, depends on every column being correctly
> tagged). `test_sample_row_count: 0` is simpler still if we never want samples.

### 1.5 Anomaly tests store aggregates, not raw rows — with two exceptions

`store_anomaly_test_results` sets `result_rows` to the **anomaly score rows**, not source data
(`EDR/macros/edr/data_monitoring/anomaly_detection/store_anomaly_test_results.sql:142`):

```jinja
"result_rows": filtered_anomaly_scores_rows,
```

Those rows are the output of `get_anomaly_scores_query`, whose columns are
(`EDR/macros/edr/tests/test_utils/get_anomaly_query.sql:102-127`): `id`, `metric_id`,
`test_execution_id`, `test_unique_id`, `detected_at`, `full_table_name`, `column_name`,
`metric_name`, `anomaly_score`, `anomaly_score_threshold`, `anomalous_value`, `bucket_start`,
`bucket_end`, `bucket_seasonality`, `metric_value`, `min_metric_value`, `max_metric_value`,
`training_avg`, `training_stddev`, `training_set_size`, `training_start`, `training_end`,
`dimension`, `dimension_value`, `anomaly_description`. All aggregates.

The metrics themselves are aggregates by construction — the monitor catalogue is a fixed list
(`EDR/macros/edr/data_monitoring/monitors/monitors.sql:1-31`): table-level `row_count`,
`freshness`; column-level `null_count`, `null_percent`, `not_null_percent`, `min_length`,
`max_length`, `average_length`, `missing_count`, `missing_percent`, `not_missing_percent`,
`min`, `max`, `zero_count`, `zero_percent`, `not_zero_percent`, `average`,
`standard_deviation`, `variance`, `sum`, `count_true`, `count_false`.

**Two places where a raw value does leak through:**

1. **`source_value` / `anomalous_value` / `other`.** For the freshness monitor, `source_value` is
   the raw max timestamp cast to string
   (`EDR/macros/edr/data_monitoring/monitors_query/table_monitoring_query.sql:420`):
   ```jinja
   {{ elementary.edr_cast_as_string("update_timestamp") }} as source_value,
   ```
   It is surfaced as `anomalous_value` in the score query
   (`EDR/.../get_anomaly_scores_query.sql:271`) and written to the `other` column of
   `elementary_test_results` (`EDR/.../store_anomaly_test_results.sql:130-132`). For the
   table/column monitors `source_value` is explicitly `NULL`
   (`table_monitoring_query.sql:109, 348`; `column_monitoring_query.sql:297`). A freshness
   timestamp is low-sensitivity. (inference)
2. **`dimension_value`.** `dimension_anomalies` groups by a user-chosen column and stores the
   **actual distinct values of that column** as `dimension_value` in
   `data_monitoring_metrics`, and repeats them verbatim in the human-readable description
   (`EDR/macros/edr/alerts/anomaly_detection_description.sql`, `dimension_metric_description`;
   `EDR/.../store_anomaly_test_results.sql:96-110`). **Do not put `dimension_anomalies` on a
   high-cardinality or sensitive column** — that is the one anomaly test that writes column
   contents into the Elementary tables. (inference)

### 1.6 Two further sensitivity items reviewers usually miss

- **`elementary_test_results.test_results_query` stores compiled SQL.** For ordinary dbt tests it
  is `elementary.get_compiled_code(flattened_test)`
  (`EDR/macros/edr/materializations/test/test.sql:172`). That can embed literal values from test
  config (e.g. an `accepted_values` list). Capped at `query_max_size` (default 1,000,000 chars,
  `get_config_var.sql:141`); `collect_model_sql` (default `true`, line 139) governs model SQL
  upload to the artifact tables.
- **`data_monitoring_metrics.metric_properties` stores `where_expression` verbatim** — the JSON
  blob is `{timestamp_column, where_expression, time_bucket, freshness_column,
  event_timestamp_column, dimensions}` (`EDR/macros/edr/metadata_collection/get_metric_properties.sql:28-35`),
  serialised into the column at `table_monitoring_query.sql:107`. Business logic, not data. (inference)

There is **no `store_failures` or `fail_calc` handling in the Elementary package** — those are
dbt-core test configs that write `dbt_test__audit` tables owned by dbt, entirely separate from
Elementary's tables. Elementary's nearest analogue is `calculate_failed_count` (default `true`,
`get_config_var.sql:149`), which only populates the integer `failed_row_count` column, no rows.

---

## 2. Warehouse cost profile

### 2.1 The single most important knob: `timestamp_column`

Every table monitor branches on it (`EDR/macros/edr/data_monitoring/monitors_query/table_monitoring_query.sql:56-76`):

```jinja
{%- if timestamp_column %}
    {{ elementary.get_timestamp_table_query(...) }}
{% else %}
    {{ elementary.get_no_timestamp_table_query(...) }}
{% endif %}
```

**Without `timestamp_column`** (`get_no_timestamp_table_query`, lines 78-113): the query is
`select * from <model>` with no time predicate at all, producing a **single** metric row whose
`bucket_start` is `NULL` and whose `bucket_end` is the run timestamp. So:

- the monitored table is **scanned in full on every dbt invocation**;
- there is **no bucket history to reuse** — each run contributes exactly one point;
- the "training set" is one point per run, so detection quality depends on run cadence, not on data time.

**With `timestamp_column`** (`get_timestamp_table_query`, lines 138-250): the scan is bounded by
a predicate pushed down to the source table:

```jinja
where
    {{ timestamp_col_expr }}
    >= {{ elementary.edr_timeadd("day", -7, elementary.edr_cast_as_timestamp(min_bucket_start)) }}
```

(the extra 7 days is deliberate — the freshness metric diffs consecutive buckets, so the first
diff would otherwise be null; see the comment at lines 165-170). A second CTE then narrows to
`>= min_bucket_start`.

> **Design consequence:** on Snowflake, a `timestamp_column` that is also the table's clustering
> key turns these into partition-pruned scans. Without one, budget for a full table scan per
> monitor per run. (inference)

### 2.2 Incremental bucket reuse: only for incremental models and sources

`get_metric_buckets_min_and_max` picks between two strategies
(`EDR/macros/edr/data_monitoring/data_monitors_configuration/get_buckets_configuration.sql:151-165`):

```jinja
{# We assume we should also cosider sources as incremental #}
{% if force_metrics_backfill or not (
    elementary.is_incremental_model(
        elementary.get_model_graph_node(model_relation), source_included=true,
    ) or unit_test
) %}
    {%- set buckets = ... run_query(regular_bucket_times_query) ... %}
{%- else %}
    {%- set buckets = ... run_query(incremental_bucket_times_query) ... %}
{% endif %}
```

| Strategy | Chosen when | Window computed each run |
|---|---|---|
| `regular_bucket_times_query` (lines 92-107) | model is **not** incremental and **not** a source, **or** `force_metrics_backfill: true` | `min_bucket_start = detection_end - days_back` — i.e. **the whole `days_back` window (default 14 days) is recomputed every run** |
| `incremental_bucket_times_query` (lines 109-149) | model is incremental, or is a dbt **source** | `min(missing buckets, detection_end - backfill_days)` — only buckets **absent from `data_monitoring_metrics`**, plus a `backfill_days` (default 2) re-do window |

The incremental path is the caching mechanism: it left-joins the candidate bucket grid against
buckets already present in `data_monitoring_metrics` for that exact
`(full_table_name, metric_properties, metric_name, column_name)` and keeps only the misses
(lines 117-142). Note the join key includes `metric_properties` as a JSON equality —
**changing `timestamp_column`, `where_expression`, `time_bucket` or `dimensions` invalidates the
whole history for that test** and forces a full `days_back` recompute. (inference)

> **This is the counterintuitive one for the review.** Putting `volume_anomalies` on a
> `table`-materialised gold model does **not** get incremental bucket reuse: it re-aggregates 14
> days of data on every single `dbt test`. Only incremental models and `sources:` get the cheap
> path. `days_back` is therefore the lever that matters most for those models.

### 2.3 Cost by test type

| Test | Queries issued per invocation | Notes |
|---|---|---|
| `volume_anomalies` | 1 bucket-window query + 1 metrics query + 1 anomaly-score query | Delegates to `table_anomalies` with `table_anomalies=["row_count"]` (`EDR/macros/edr/tests/test_volume_anomalies.sql:22-24`). Cheapest — a grouped `count(*)`. |
| `freshness_anomalies` / `table_anomalies` | same shape | `table` monitors are limited to `["row_count", "freshness", "event_freshness"]` (`EDR/macros/edr/data_monitoring/data_monitors_configuration/get_table_monitors.sql:24-26`). |
| `column_anomalies` | one metrics query **per listed column** | Scoped by the explicit `column_anomalies:` list. |
| `all_columns_anomalies` | **one bucket query + one metrics query per column in the table** | See below. |
| `dimension_anomalies` | 1, but the group-by cardinality drives row volume into `data_monitoring_metrics` | Also the only test that stores raw column values (§1.5). |

`all_columns_anomalies` loops over every column returned by `adapter.get_columns_in_relation` and
issues a separate `insert ... select` per column
(`EDR/macros/edr/tests/test_all_columns_anomalies.sql:113-165`):

```jinja
{%- for column_obj_and_monitors in column_objs_and_monitors %}
    ...
    {% if test_configuration.timestamp_column %}
        {%- set min_bucket_start, max_bucket_end = elementary.get_metric_buckets_min_and_max(...) %}
    {%- endif %}
    ...
    {%- do elementary.run_query(
        elementary.insert_as_select(temp_table_relation, column_monitoring_query)
    ) -%}
{%- endfor %}
```

So a 120-column table means ~240 round-trips (a bucket query and a metrics query per column),
each scanning the detection window of the table. **`all_columns_anomalies` on a wide fact table
is the dominant cost risk in this design.** (inference)

Scoping knobs for it, parsed at `EDR/macros/edr/tests/test_all_columns_anomalies.sql:200-217`:

- `column_anomalies:` — restrict which **monitors** run (e.g. just `null_percent`);
- `exclude_prefix:` — skip columns by prefix;
- `exclude_regexp:` — skip columns by regex (case-insensitive).

Default monitors per column type are narrower than the available set
(`EDR/macros/edr/data_monitoring/monitors/monitors.sql:33-57`) — e.g. numeric columns default to
7 monitors (`min`, `max`, `zero_count`, `zero_percent`, `average`, `standard_deviation`,
`variance`), all computed in one grouped pass per column.

### 2.4 The full knob list

From `EDR/macros/edr/system/system_utils/get_config_var.sql:108-170` (global `vars:`; most are
also settable per test, or per model via `meta.elementary`, through
`elementary.get_test_argument`):

| Var | Default | Cost effect |
|---|---|---|
| `days_back` | `14` | Training window. For non-incremental models this is **the scan width every run**. Multiplied by 7 when `seasonality` is set (`EDR/macros/edr/tests/test_configuration/get_days_back.sql:5-7`). |
| `backfill_days` | `2` | Re-computed recent window on the incremental path; also the firing window (§3.1). |
| `anomaly_sensitivity` | `3` | Z-score threshold. No cost effect. |
| `min_training_set_size` | `7` | No cost effect. |
| `force_metrics_backfill` | `false` | **Forces the expensive full-`days_back` path for every model.** Leave off. |
| `time_bucket` | `{period: day, count: 1}` (`EDR/macros/edr/tests/test_configuration/get_time_bucket.sql:1-6`) | Hourly buckets multiply row volume in `data_monitoring_metrics` ~24x. Allowed periods: `hour`, `day`, `week`, `month`. |
| `where_expression` | none | Pushed into the monitored-table CTE (`table_monitoring_query.sql:86-88`, `column_monitoring_query.sql:38-44`) — genuinely reduces scanned rows. |
| `detection_delay` | none | Shifts `detection_end` back, so late-arriving data isn't mis-scored (`get_buckets_configuration.sql:1-8`). |
| `detection_period` / `training_period` | none | Ergonomic aliases converted to `backfill_days` / `days_back` (`EDR/macros/edr/tests/test_configuration/get_period_vars.sql`). |
| `test_sample_row_count` | `5` | Each failing test re-runs its own query once more (§1.2). |
| `dbt_artifacts_chunk_size` | `5000` | Insert batching for the on-run-end writes. |
| `query_max_size` | `1000000` | Truncation cap on stored SQL. |
| `cache_artifacts` | `true` | Artifact upload path, not monitors. |

I found **no documented benchmark or cost figure** in either repo — no "monitoring a 1TB table
costs X" statement exists. The cost characterisation above is read from the generated SQL.
**[UNVERIFIED]** as a published claim.

### 2.5 Where the metrics land, and how they're stored on Snowflake

`data_monitoring_metrics` is configured with `partition_by(column="bucket_end")` and
`cluster_by(["full_table_name", "metric_name"])`
(`EDR/models/edr/data_monitoring/data_monitoring/data_monitoring_metrics.sql:14-19`) — but both
dispatch to no-ops outside BigQuery:

- `EDR/macros/utils/cross_db_utils/partition_by.sql:23`: `{% macro default__get_partition_by(column) %} {% do return(none) %} {% endmacro %}`
- `EDR/macros/utils/cross_db_utils/cluster_by.sql:12`: `{% macro default__get_cluster_by(columns) %} {% do return(none) %} {% endmacro %}`

**So on Snowflake the Elementary result tables are unclustered heap tables.** If we poll them
frequently, we may want to add our own clustering key or a stream. (inference)

---

## 3. Repeat firing when an anomaly persists

### 3.1 Yes — the test re-fires every run, but only for a bounded window

Two facts combine here.

**Fact A: a failing test result is written on every invocation.** `elementary_test_results` is an
append-only incremental model (`EDR/models/edr/run_results/elementary_test_results.sql:4-13`), and
`handle_tests_results` inserts a fresh row per test per invocation on the `on-run-end` hook
(`EDR/macros/edr/tests/on_run_end/handle_tests_results.sql:44-56`). Nothing reads back the
previous run's verdict. So **N consecutive runs with the same anomaly produce N `fail` rows**.

**Fact B: an anomalous bucket stops counting as a failure once it ages past `backfill_days`.**
The `is_anomalous` flag is not just a threshold test — it is ANDed with a recency window
(`EDR/macros/edr/tests/test_utils/get_anomaly_query.sql:132-137`):

```jinja
{{ elementary.edr_condition_as_boolean(
    '(' ~ elementary.anomaly_score_condition(test_configuration) ~ ') and bucket_end > '
    ~ elementary.edr_timeadd('day', backfill_period, 'max_bucket_end')
  ) }} as is_anomalous
```

and the test's failure count is the number of `is_anomalous` rows
(`EDR/macros/edr/data_monitoring/anomaly_detection/store_anomaly_test_results.sql:78-87`).

So the practical repeat-firing profile for a **daily** `time_bucket` with default
`backfill_days: 2`:

| Run | Behaviour |
|---|---|
| Run that first sees the bad bucket | `status = fail`, `failures >= 1` |
| Every run for the next ~2 days | `status = fail` again, same bucket, new row, new `id` |
| After the bucket falls outside the `backfill_days` window | `status = pass` again, even though the metric row and its bad `anomaly_score` stay in `data_monitoring_metrics` forever |

(inference) **Our triage pipeline must de-duplicate.** A persistent anomaly on a table tested
every hour will produce ~48 identical `fail` rows before it silently self-heals to `pass`. The
natural dedup key, borrowed from Elementary's own grouping (see §3.3), is
`(test_unique_id, column_name, test_sub_type)` — plus, for anomaly tests, `bucket_end` if we want
one finding per bad bucket rather than one per incident.

Note also the `pass`/`fail` normalisation quirk: for `test_type = 'anomaly_detection'`, a dbt
`fail` is rewritten to `pass` when `failures == 0`, because one dbt test emits many result rows
(`EDR/macros/edr/tests/on_run_end/handle_tests_results.sql:62-75`). So **trust `failures`, not
only `status`.**

### 3.2 Suppression is an `edr` CLI feature, invisible to a table reader

There **is** deduplication/suppression, but it lives entirely in the `edr monitor` alerting path,
not in the dbt package that writes the result tables.

- **Config key:** `alert_suppression_interval`, in **hours**
  (`CLI/elementary/monitor/fetchers/alerts/schema/alert_data.py:22`).
- **Where set:** per-test/per-model `meta.alert_suppression_interval` or
  `meta.alerts_config.alert_suppression_interval`
  (`CLI/elementary/monitor/fetchers/alerts/schema/alert_data.py:54-56`), or globally via the CLI
  flag `--suppression-interval` (int, **default `0` = no suppression**,
  `CLI/elementary/monitor/cli.py:253-258`). Meta wins over CLI unless
  `--override-dbt-project-config` is passed
  (`CLI/.../alert_data.py:122-130`). It is **not** a `config.yml` key.
- **Algorithm** (Python, not SQL — `CLI/elementary/monitor/data_monitoring/alerts/data_monitoring_alerts.py:199-225`):

  ```python
  is_alert_in_suppression = (
      (current_time_utc - convert_time_to_timezone(last_sent_time)).total_seconds() / 3600
      <= suppression_interval
      if last_sent_time else False
  )
  ```

  i.e. **`now() − max(sent_at) for this `alert_class_id` ≤ interval_hours`**. `last_sent_time`
  comes from a SQL macro over `alerts_v2`
  (`CLI/elementary/monitor/dbt_project/macros/alerts/fetchers/get_alerts.sql:33-65`):
  `select alert_class_id, max(sent_at) as last_sent_at from alerts_v2 where status = 'sent' group by alert_class_id`.
- A second, independent dedup also applies: `_get_latest_alerts` keeps only the alert with the
  max `detected_at` per `alert_class_id` within the current batch
  (`CLI/.../data_monitoring_alerts.py:227-249`).

### 3.3 Where suppression state lives — and why it matters for us

State is **in the warehouse**, in a table called `alerts_v2`, created by the `edr` CLI's own
bundled dbt project (`CLI/elementary/monitor/dbt_project/models/alerts/alerts_v2.sql`,
incremental, `unique_key='alert_id'`). Columns
(`CLI/elementary/monitor/dbt_project/macros/alerts/population/utils/empty_alert_tables.sql:52-63`):

`alert_id`, `alert_class_id`, `type` (`test` | `model` | `source_freshness`), `detected_at`,
`created_at`, `updated_at`, `status`, `data` (JSON blob), `sent_at`.

`status` is the successor to the old `suppression_status` and takes values
`pending` / `sent` / `skipped` (`AlertStatus` enum,
`CLI/elementary/monitor/fetchers/alerts/schema/pending_alerts.py:30-33`). `suppression_status`
itself survives only on the **deprecated** v1 `alerts` / `alerts_models` /
`alerts_source_freshness` tables, read for backward-compat migration only.

`alert_class_id` — Elementary's own notion of "same issue" — is
(`CLI/elementary/monitor/dbt_project/macros/alerts/population/test_alerts.sql:131`):

```sql
coalesce(test_unique_id,'None') || '.' || coalesce(column_name,'None') || '.' || coalesce(sub_type,'None')
```

For models and source freshness it is simply `unique_id`.

> **Three consequences for our design:**
>
> 1. **None of this is available if we only poll `elementary_test_results` / `data_monitoring_metrics`.**
>    Suppression is computed by `edr monitor` and recorded in `alerts_v2`; the result tables carry
>    no suppression column and no "already reported" marker. If we don't run `edr monitor`,
>    `alerts_v2` never exists. **We must implement our own dedup.** (inference)
> 2. **If we do run `edr monitor`, `alerts_v2` is NOT append-only.** `edr` issues in-place
>    `UPDATE`s: `update alerts_v2 set status='sent', sent_at=..., updated_at=... where alert_id in (...) and status='pending'`
>    (`CLI/elementary/monitor/dbt_project/macros/alerts/manage/update_sent_alerts.sql:14-22`; the
>    `skipped` twin is `update_skipped_alerts.sql:14-18`). A watermark poller over `alerts_v2`
>    would miss those transitions; only a watermark over `updated_at` would catch them.
> 3. **`edr monitor` needs write privileges** on the Elementary schema (it materialises
>    `alerts_v2` and other `elementary_cli` models there, then `UPDATE`s them). `edr report` /
>    `edr send-report` only run dbt *operations* and are read-only against the warehouse.
>
> An alternative design worth considering: let `edr monitor` populate `alerts_v2` and have our
> triage pipeline consume **`alerts_v2` on `updated_at`** rather than `elementary_test_results`,
> to inherit Elementary's suppression and grouping for free — at the cost of a non-append-only
> source and a dependency on the CLI. (inference)

---

## 4. Reading the tables from outside

### 4.1 Privileges

Elementary's docs do not publish literal Snowflake GRANT SQL. For Snowflake they point at a macro
instead (`EDOCS/cloud/integrations/dwh/snowflake`, source
`CLI/docs/_snippets/cloud/integrations/create-user-operation.mdx`):

> "On your dbt project, run: `dbt run-operation create_elementary_user` ... This command will
> generate a query to create a user with the necessary permissions."

They do, however, state the *shape* of the read-only grant clearly
(`EDOCS/cloud/general/security-and-privacy`, source
`CLI/docs/cloud/general/security-and-privacy.mdx`):

> "we instruct our customers to create a dedicated role for Elementary with `read only` access
> only to the Elementary schema in your data warehouse. As long as you follow the onboarding
> process instructions, it will be impossible for Elementary Cloud to read data from your
> warehouse that does not reside in the Elementary schema."

and the Databricks equivalent is spelled out literally as a schema-level grant
(`EDOCS/cloud/integrations/dwh/databricks`): `GRANT SELECT ON SCHEMA <elementary_schema> TO ...`.

Translating to Snowflake using the official privilege reference
(`SF/user-guide/security-access-control-privileges`):

| Object | Privilege | Snowflake's definition |
|---|---|---|
| Database | `USAGE` | "Enables using a database, including returning the database details in the SHOW DATABASES command output." |
| Schema | `USAGE` | "Enables using a schema, including returning the schema details in the SHOW SCHEMAS command output." |
| Table / view | `SELECT` | "Enables executing a SELECT statement on a table/view." |

Snowflake also notes: *"The role must have the USAGE privilege on the schema as well as the
required privilege or privileges on the object."*

So the minimal poller grant is (inference, assembled from the above):

```sql
GRANT USAGE ON DATABASE <db> TO ROLE <poller>;
GRANT USAGE ON SCHEMA <db>.<elementary_schema> TO ROLE <poller>;
GRANT SELECT ON TABLE <db>.<elementary_schema>.elementary_test_results TO ROLE <poller>;
GRANT SELECT ON TABLE <db>.<elementary_schema>.data_monitoring_metrics TO ROLE <poller>;
-- deliberately NOT granted: test_result_rows (see §1)
```

**Grant table-by-table, not `ON ALL TABLES IN SCHEMA`** — the failing-row samples in
`test_result_rows` live in the same schema (§1.3), and a schema-wide grant hands them to the
poller. (inference)

The Elementary schema is conventionally a dedicated one, set via dbt custom schema
(`EDOCS/oss/general/faq`, source `CLI/docs/_snippets/faq/question-schema-no-accordion.mdx`):
`models: elementary: +schema: elementary`, producing a `<target>_elementary` suffix. Resolution
in code reads the schema off the first model node in the `elementary` package
(`EDR/macros/utils/graph/get_package_database_and_schema.sql:9-21`). Note that a *second*
schema may exist for transient test tables — `<elementary_schema><tests_schema_name>`, with a
legacy `__tests` suffix (`EDR/macros/edr/tests/test_utils/get_elementary_tests_schema.sql:1-21`).

For completeness, the writer side needs much more
(`EDOCS/oss/general/faq`, source `CLI/docs/_snippets/faq/question-profile-permissions.mdx`):

> "The provided credentials need to have permission to: Read - Information schema and the tables
> configured for monitoring. Write - To the database configured in `elementary` profile,
> including creating new schemas."

### 4.2 The watermark column: `created_at`

Both tables declare their intended watermark in model `meta`:

- `elementary_test_results` (`EDR/models/edr/run_results/elementary_test_results.sql:6-10`):
  `{"dedup_by_column": "id", "timestamp_column": "created_at", "prev_timestamp_column": "detected_at"}`
- `data_monitoring_metrics` (`EDR/models/edr/data_monitoring/data_monitoring/data_monitoring_metrics.sql:9-13`):
  `{"dedup_by_column": "id", "timestamp_column": "created_at", "prev_timestamp_column": "updated_at"}`

`created_at` is assigned **by the warehouse at INSERT time**, not carried from the client:

- For `elementary_test_results` / `test_result_rows`, `insert_rows` substitutes
  `elementary.edr_current_timestamp()` into the `created_at` position of every row
  (`EDR/macros/utils/table_operations/insert_rows.sql:133, 210-212, 238-239`).
- For `data_monitoring_metrics`, the INSERT is explicit
  (`EDR/macros/edr/tests/on_run_end/handle_tests_results.sql:208-212`):
  `{{ elementary.edr_current_timestamp() }} as created_at`.

`created_at` is therefore **monotonically non-decreasing in insert order within a warehouse**, and
is the correct watermark. (inference)

### 4.3 Three watermark caveats

**(a) `created_at` is in the Snowflake *session* timezone; sibling columns are UTC.**
`edr_current_timestamp()` dispatches to dbt's `current_timestamp_backcompat`
(`EDR/macros/utils/cross_db_utils/current_timestamp.sql:5-15`), which on Snowflake is
(`dbt-labs/dbt-snowflake`, `dbt/include/snowflake/macros/utils/timestamps.sql`):

```jinja
{% macro snowflake__current_timestamp_backcompat() %}
  current_timestamp::{{ type_timestamp() }}
{% endmacro %}
```

— i.e. a naive `TIMESTAMP_NTZ` in the session's `TIMEZONE`. By contrast:

| Column | Source | Zone |
|---|---|---|
| `created_at` | `edr_current_timestamp()` → `current_timestamp::timestamp` | **session TZ**, naive |
| `data_monitoring_metrics.updated_at` | `edr_current_timestamp_in_utc()` (`table_monitoring_query.sql:38`) | **UTC**, naive |
| `elementary_test_results.detected_at` | Python `datetime.utcnow()` at test time (`EDR/macros/edr/system/system_utils/times.sql:9-15`, via `flatten_test`'s `generated_at`) | **UTC** (client clock) |

> **Action for the design:** pin the Elementary role's session `TIMEZONE` to `UTC`, or watermark
> using the same session TZ the writer used. Mixing `created_at` with UTC-based columns in a
> single comparison will silently skip or replay rows. (inference)

**(b) `id` is not unique, and there is no sequence column.** Both models carry
`meta.dedup_by_column: "id"` precisely because duplicates are expected; dedup happens at *read*
time, via a row_number window in `dump_table`
(`EDR/macros/commands/dump_table.sql:44-48, 77-89`), not at write time. On Snowflake the
incremental strategy is plain `append`
(`EDR/macros/utils/cross_db_utils/incremental_strategy.sql:51-53`:
`{% macro default__get_append_only_incremental_strategy() %} {% do return("append") %} {% endmacro %}`).
There is **no auto-increment or sequence column** on either table. A poller must watermark on
`created_at` and de-duplicate on `id` itself. (inference)

For `elementary_test_results`, `id` = `test_execution_id` =
`invocation_id ~ "." ~ test_unique_id` (`EDR/macros/utils/graph/get_node_execution_id.sql:1-4`) —
so re-running the same invocation is the duplicate scenario. For anomaly tests, `id` is instead
the surrogate key of `(metric_id, test_execution_id)`
(`EDR/.../get_anomaly_scores_query.sql:262-265`), so it also changes per invocation.

**(c) Are rows ever updated or deleted after insert? On Snowflake: no.**

- Both models use the `append` incremental strategy with **no `unique_key`** — insert-only.
- **No retention/purge/TTL exists.** Grepping both repos for `delete from`, `purge`, `retention`
  turns up nothing that touches these two tables. `days_back` bounds how far back queries *read*,
  never what is deleted.
- `clean_elementary_temp_tables` (default `true`,
  `EDR/macros/edr/system/system_utils/get_config_var.sql:151`) **drops transient staging tables
  only** — those matching `test%__tmp_%`
  (`EDR/macros/edr/tests/test_utils/clean_elementary_test_tables.sql:1-60`), called last in
  `on_run_end` (`EDR/macros/edr/system/hooks/on_run_end.sql:38-40`). It never touches the result
  tables.
- The destructive table-op macros that do exist (`replace_table_data`, `remove_rows`,
  `delete_duplicate_rows` under `EDR/macros/utils/table_operations/` and
  `EDR/macros/commands/`) are called **only** from
  `EDR/macros/edr/dbt_artifacts/upload_artifacts_to_table.sql:79,87`, i.e. against the
  current-state **artifact** tables (`dbt_models`, `dbt_tests`, `dbt_sources`, ...), not the
  history tables. `delete_duplicate_rows` is additionally Postgres-only — the `default__`
  implementation raises a compiler error (`EDR/macros/commands/delete_duplicate_rows.sql:38-40`).
- `dbt run --full-refresh` is defended against: both models set
  `full_refresh=elementary.get_config_var("elementary_full_refresh")`, default `false`
  (`get_config_var.sql:137`), so a project-wide full refresh will *not* wipe result history
  unless that var is flipped.

> **Conclusion: `elementary_test_results` and `data_monitoring_metrics` are safe append-only
> sources for a `created_at` watermark, subject to the timezone and duplicate-`id` caveats.**
> `alerts_v2` is **not** (§3.3).

One residual risk: the tables are `on_schema_change="append_new_columns"`, so an Elementary
upgrade can add columns mid-flight. A poller should `SELECT` an explicit column list, not `*`.
(inference)

---

## 5. What a verdict row actually contains

### 5.1 `elementary_test_results` — 28 columns

Defined in `EDR/macros/edr/system/system_utils/empty_table.sql:1-35`. Column-by-column semantics
are **not documented on the docs site** — `EDOCS/dbt/package-models` gives only a one-paragraph
description per table — so the "meaning" column below is read from the code that populates it
(chiefly `EDR/macros/edr/materializations/test/test.sql:129-193`,
`EDR/macros/edr/tests/on_run_end/handle_tests_results.sql:104-160`, and
`EDR/macros/edr/data_monitoring/anomaly_detection/store_anomaly_test_results.sql:124-146`).

| Column | Type | Meaning | Anomaly-test value |
|---|---|---|---|
| `id` | long_string | Row identity; **not unique** | surrogate key of `(metric_id, test_execution_id)` |
| `data_issue_id` | string | | `metric_id` — **the FK into `data_monitoring_metrics.id`** |
| `test_execution_id` | long_string | `invocation_id.test_unique_id` | same |
| `test_unique_id` | long_string | dbt test node id | same |
| `model_unique_id` | long_string | **dataset identity** — the dbt node under test | same |
| `invocation_id` | string | **link back to the dbt invocation** (set on-run-end, `handle_tests_results.sql:118`) | same |
| `detected_at` | timestamp | Python `utcnow()` at test execution (UTC) | same |
| `created_at` | timestamp | warehouse insert time (**session TZ**) — the watermark | same |
| `database_name` | string | dataset identity | same |
| `schema_name` | string | dataset identity | same |
| `table_name` | string | dataset identity | same |
| `column_name` | string | **column identity** (null for table-level) | the monitored column |
| `test_type` | string | | literally `"anomaly_detection"` |
| `test_sub_type` | string | | **`metric_name`** — e.g. `row_count`, `freshness`, `null_percent` |
| `test_results_description` | long_string | human-readable verdict | generated sentence, e.g. *"The last row_count value is 812.0. The average for this metric is 10432.117."* (`EDR/macros/edr/alerts/anomaly_detection_description.sql`) |
| `owners` | string | model owners from meta | same |
| `tags` | string | model tags + test tags, concatenated | same |
| `test_results_query` | long_string | SQL to reproduce the failure (see §1.6) | a `select * from (...) where anomaly_score is not null and ...` filter |
| `other` | string | | **`anomalous_value`** = `source_value` (freshness: the raw last-update timestamp) |
| `test_name` | long_string | | e.g. `volume_anomalies` |
| `test_params` | long_string | JSON of the test args **merged with the resolved anomaly config** | includes `timestamp_column`, `where_expression`, `time_bucket`, `days_back`, `backfill_days`, `anomaly_sensitivity`, `anomaly_direction`, `seasonality`, `detection_delay`, `dimensions`, ... (`EDR/macros/edr/tests/test_configuration/get_anomalies_test_configuration.sql:128-148`) |
| `severity` | string | dbt severity (`error`/`warn`) | same |
| `status` | string | `pass` / `fail` / `warn` / `error` / `skipped`; **rewritten to `pass` when `failures==0` for anomaly tests** (§3.1) | same |
| `failures` | bigint | **count of `is_anomalous` rows** for anomaly tests | ditto |
| `test_short_name` | string | | |
| `test_alias` | string | | |
| `result_rows` | long_string | JSON sample — **empty by default**, since `store_result_rows_in_own_table: true` routes dbt-test samples to `test_result_rows`. For **anomaly tests this is where the rich payload lives** (§5.3). | the anomaly score rows |
| `failed_row_count` | bigint | populated when `calculate_failed_count: true` | |

### 5.2 `data_monitoring_metrics` — 15 columns

Defined in `EDR/macros/edr/system/system_utils/empty_table.sql:74-95`.

| Column | Type | Carries |
|---|---|---|
| `id` | string | surrogate key of `(full_table_name, column_name, metric_name, metric_type, [dimension, dimension_value,] bucket_end, metric_properties)` (`table_monitoring_query.sql:23-34`, `column_monitoring_query.sql:308-320`). **This is `elementary_test_results.data_issue_id`.** |
| `full_table_name` | string | **dataset identity** (`db.schema.table`) |
| `column_name` | string | **column identity**; NULL for table-level metrics |
| `metric_name` | string | e.g. `row_count`, `freshness`, `null_percent` |
| `metric_type` | string | e.g. `row_count`; equals `metric_name` for column monitors |
| `metric_value` | float | **the metric value** |
| `source_value` | string | raw value behind the metric — freshness timestamp, else NULL (§1.5) |
| `bucket_start` | timestamp | **bucket interval start**; NULL when no `timestamp_column` |
| `bucket_end` | timestamp | **bucket interval end**; = run time when no `timestamp_column` |
| `bucket_duration_hours` | int | bucket width in hours |
| `updated_at` | timestamp | metric computation time, **UTC** |
| `dimension` | string | the `dimensions` list joined by `"; "` |
| `dimension_value` | string | **the actual column values** (§1.5) |
| `metric_properties` | string | JSON: `timestamp_column`, `where_expression`, `time_bucket`, `freshness_column`, `event_timestamp_column`, `dimensions`. **Part of the identity** — changing any of these forks the history. |
| `created_at` | timestamp | insert time, session TZ — the watermark |

### 5.3 Where the score and the bounds actually live

**Neither table has a flat `anomaly_score`, `min_metric_value` or `max_metric_value` column.**
Those are computed in the anomaly-score query and stored, as JSON, in
`elementary_test_results.result_rows`
(`EDR/.../store_anomaly_test_results.sql:142`). Each JSON element has
(`EDR/macros/edr/tests/test_utils/get_anomaly_query.sql:102-127`):

| Field | What it is |
|---|---|
| `metric_id` | FK to `data_monitoring_metrics.id` |
| `metric_value` | the observed value |
| `anomaly_score` | **z-score**: `(metric_value − training_avg) / stddev` — `NULL` when `training_set_size = 1`, `0` when stddev is 0 (`EDR/.../get_anomaly_scores_query.sql:253-258`) |
| `anomaly_score_threshold` | `anomaly_sensitivity` (default 3) |
| `min_metric_value` / `max_metric_value` | **the expected range**: `training_avg ∓ sensitivity × stddev`, optionally widened by `ignore_small_changes` percent thresholds (`EDR/.../get_anomaly_scores_query.sql:309-336`) |
| `training_avg`, `training_stddev`, `training_set_size`, `training_start`, `training_end` | the baseline |
| `bucket_start`, `bucket_end`, `bucket_seasonality` | **bucket interval** |
| `full_table_name`, `column_name`, `metric_name`, `dimension`, `dimension_value` | **dataset + column identity** |
| `anomalous_value` | `source_value` |
| `anomaly_description` | the human sentence |
| `is_anomalous` | boolean; the threshold **and** the `backfill_days` recency window (§3.1) |

There are also three **views** over the metrics that recompute scores without a test running
(`EDOCS/dbt/package-models`, source `CLI/docs/dbt/package-models.mdx`):
`metrics_anomaly_score` — *"a view on `data_monitoring_metrics` that runs the same query the
anomaly detection tests run to calculate anomaly scores"*
(`EDR/models/edr/data_monitoring/anomaly_detection/metrics_anomaly_score.sql`, which exposes
`anomaly_score`, `training_avg`, `training_stddev`, `training_set_size`, `is_anomaly` as flat
columns over a 7-day tail); `anomaly_threshold_sensitivity`; and `monitors_runs`.

> **Recommended finding shape (inference).** Poll `elementary_test_results` on
> `created_at > watermark AND failures > 0`, then:
> - **finding key** = `(model_unique_id, test_unique_id, column_name, test_sub_type)` — this is
>   exactly Elementary's own `alert_class_id` (§3.3), so our dedup matches theirs;
> - **occurrence key** = add `bucket_end` (parsed from `result_rows`) for one finding per bad bucket;
> - **dataset** = `database_name.schema_name.table_name` + `model_unique_id`;
> - **metric / observed / expected** = `test_sub_type`, and `metric_value` / `min_metric_value` /
>   `max_metric_value` / `anomaly_score` parsed out of the `result_rows` JSON;
> - **provenance** = `invocation_id`, `test_execution_id`, `detected_at`;
> - **drill-down** = `data_issue_id` → `data_monitoring_metrics.id` for the full bucket history;
> - **do not ingest** `result_rows` for non-anomaly tests, and do not grant `test_result_rows`.
>
> The `result_rows` JSON parse is the awkward part: it is a `long_string`, not a Snowflake
> `VARIANT`, so we need `PARSE_JSON` on read. **[UNVERIFIED]** — I did not confirm the exact
> serialisation format of the JSON array against a live warehouse.

---

## 6. Open questions and gaps

| # | Gap | Status |
|---|---|---|
| 1 | Exact on-disk serialisation of `result_rows` / `test_result_rows.result_row` (JSON array of objects? escaped string?) | **[UNVERIFIED]** — needs a live run to confirm before we write a parser |
| 2 | Published cost benchmarks for monitors on large tables | **Do not exist.** Neither repo contains any figure; §2 is derived from the generated SQL |
| 3 | `days_back`, `backfill_days`, `force_metrics_backfill` on the docs site | **Undocumented** — they survive only in old release notes (`EDOCS/oss/release-notes/releases/0.8.0`, `0.7.10`). The current documented surface is `training_period` / `detection_period`, which convert to them (`EDR/macros/edr/tests/test_configuration/get_period_vars.sql`). Treat the code as the contract |
| 4 | The five PII vars (`disable_test_samples`, `disable_samples_on_pii_tags`, `pii_tags`, `enable_samples_on_show_sample_rows_tags`, `show_sample_rows_tags`) | **Real in code, absent from the docs site.** Only `test_sample_row_count` and the CLI's `--disable-samples` flag are documented. Undocumented vars can change without a deprecation notice — pin the package version |
| 5 | Sample table name | Docs are **internally inconsistent**: `test_result_rows` in `EDOCS/oss/general/faq`, `test_results_samples` in `EDOCS/cloud/general/security-and-privacy`. The code says `test_result_rows` (`EDR/models/edr/run_results/test_result_rows.sql`) |
| 6 | `elementary.table_anomalies` | **Real test in code** (`EDR/macros/edr/tests/test_table_anomalies.sql`) but **absent from the docs site**, where it appears only as a free-text tag in two tutorials. `volume_anomalies` is its documented one-metric wrapper |
| 7 | Column-level schema reference for the result tables | **None exists in the docs.** §5 above is read from the package source and is, as far as I can tell, the only complete list |
| 8 | Whether Snowflake's `create_elementary_user` macro grants more than we want | Not checked — the macro is referenced by docs but I did not locate and read it |

---

## 7. Sources read

**Primary repos (pinned):**

- `elementary-data/dbt-data-reliability` @ `9a7e2b559693e662c30672b2d449b4025c254cd9` (v0.26.0, 2026-09-08)
  - `dbt_project.yml`
  - `models/edr/run_results/elementary_test_results.sql`, `test_result_rows.sql`
  - `models/edr/data_monitoring/data_monitoring/data_monitoring_metrics.sql`
  - `models/edr/data_monitoring/anomaly_detection/metrics_anomaly_score.sql`
  - `macros/edr/system/system_utils/empty_table.sql`, `get_config_var.sql`, `times.sql`,
    `get_run_started_at.sql`, `should_show_sample_rows.sql`, `is_pii_table.sql`,
    `get_pii_columns_from_parent_model.sql`, `clean_elementary_temp_tables.sql`
  - `macros/edr/materializations/test/test.sql`
  - `macros/edr/tests/on_run_end/handle_tests_results.sql`
  - `macros/edr/tests/test_all_columns_anomalies.sql`, `test_volume_anomalies.sql`, `test_table_anomalies.sql`
  - `macros/edr/tests/test_utils/get_anomaly_query.sql`, `get_elementary_tests_schema.sql`, `get_context_select_clause.sql`
  - `macros/edr/tests/test_configuration/get_anomalies_test_configuration.sql`, `get_time_bucket.sql`, `get_days_back.sql`, `get_period_vars.sql`
  - `macros/edr/data_monitoring/anomaly_detection/get_anomaly_scores_query.sql`, `store_anomaly_test_results.sql`
  - `macros/edr/data_monitoring/data_monitors_configuration/get_buckets_configuration.sql`, `get_table_monitors.sql`, `get_column_monitors.sql`
  - `macros/edr/data_monitoring/monitors_query/table_monitoring_query.sql`, `column_monitoring_query.sql`, `get_start_bucket_in_data.sql`
  - `macros/edr/data_monitoring/monitors/monitors.sql`
  - `macros/edr/alerts/anomaly_detection_description.sql`
  - `macros/edr/metadata_collection/get_metric_properties.sql`
  - `macros/utils/cross_db_utils/incremental_strategy.sql`, `current_timestamp.sql`, `partition_by.sql`, `cluster_by.sql`, `table_type.sql`
  - `macros/utils/table_operations/insert_rows.sql`, `replace_table_data.sql`, `remove_rows.sql`
  - `macros/utils/graph/get_node_execution_id.sql`, `get_package_database_and_schema.sql`
  - `macros/commands/dump_table.sql`, `delete_duplicate_rows.sql`
- `elementary-data/elementary` @ `e34d8539b9c7f350c2de9ee954794d40b9260d93` (2026-09-10)
  - `elementary/monitor/cli.py`
  - `elementary/monitor/data_monitoring/alerts/data_monitoring_alerts.py`
  - `elementary/monitor/fetchers/alerts/schema/alert_data.py`, `pending_alerts.py`
  - `elementary/monitor/fetchers/alerts/alerts.py`
  - `elementary/monitor/alerts/grouping_type.py`
  - `elementary/config/config.py`
  - `elementary/monitor/dbt_project/models/alerts/alerts_v2.sql`
  - `elementary/monitor/dbt_project/macros/alerts/population/utils/empty_alert_tables.sql`, `test_alerts.sql`, `model_alerts.sql`, `source_freshness_alerts.sql`
  - `elementary/monitor/dbt_project/macros/alerts/fetchers/get_alerts.sql`
  - `elementary/monitor/dbt_project/macros/alerts/manage/update_sent_alerts.sql`, `update_skipped_alerts.sql`
  - `elementary/monitor/data_monitoring/alerts/integrations/slack/slack.py`
- `dbt-labs/dbt-snowflake` — `dbt/include/snowflake/macros/utils/timestamps.sql` (read only to resolve the `created_at` timezone question)

**Docs (docs.elementary-data.com, rendered from `elementary-data/elementary@e34d8539:docs/`):**

- `data-tests/anomaly-detection-configuration/timestamp-column`, `where-expression`,
  `detection-period`, `training-period`, `time-bucket`, `detection-delay`,
  `exclude_prefix`, `exclude_regexp`, `column-anomalies`, `anomaly-exclude-metrics`
- `data-tests/anomaly-detection-tests/volume-anomalies`, `freshness-anomalies`,
  `event-freshness-anomalies`, `column-anomalies`, `all-columns-anomalies`, `dimension-anomalies`
- `data-tests/introduction`, `key-features`, `best-practices/detection-and-coverage`
- `dbt/package-models`, `dbt/dbt-artifacts`
- `cloud/general/security-and-privacy`, `cloud/integrations/dwh/snowflake`,
  `cloud/integrations/dwh/databricks`, `cloud/guides/troubleshoot`
- `oss/general/faq`, `oss/cli-commands`, `oss/release-notes/releases/0.8.0`, `0.7.10`

**Snowflake:**

- `https://docs.snowflake.com/en/user-guide/security-access-control-privileges`
