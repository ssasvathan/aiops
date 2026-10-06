# Research: dbt Selector Semantics over Sources, Elementary's `on-run-end` under Partial Selection, and `detection_delay` at Bucket Boundaries

> **Audience:** Architecture reviewers of the DQ anomaly proposal, specifically the Gate 1 checks
> ADR-0018 defers. Also whoever builds the series-kind registry and the tier schedules.
>
> **Question:** ADR-0018 plans one dbt project with one scheduled invocation per cadence tier,
> selected by generated tag (`dbt test --select tag:hourly`, `tag:daily`), with Elementary anomaly
> monitors attached to dbt `sources` in Snowflake. It names two unverified facts and one failure
> mode to rule out. Three things need checking. (1) Does `--select tag:X` actually reach tests
> attached to *sources*, and how does tag inheritance and indirect selection affect that?
> (2) Does Elementary's `on-run-end` hook persist correctly when only a subset of tests was
> selected, and what happens when a tier's tag matches nothing? (3) At a bucket boundary, is
> `detection_delay` bounded on `bucket_start` or `bucket_end`, and what does that cost in latency?
>
> **Scope:** Architecture proposal input only. No implementation. Nothing in this repo was changed.
>
> **Date:** 2026-10-02. **Status:** Draft for review.

## Reading Rules

- Every non-obvious claim carries a source: a URL, a file path in a pinned repo (see
  [Sources read](#sources-read)), or a named experiment in
  [Appendix A](#appendix-a-the-throwaway-harness). Sources are **primary only**: the
  `dbt-labs/dbt-core` source at pinned tags, `dbt-labs/dbt` `main` (the Rust v2 rewrite),
  docs.getdbt.com, the `elementary-data/dbt-data-reliability` source at its release tag, and the
  `elementary-data/elementary` `docs/` tree (which is what docs.elementary-data.com renders).
  No blog posts, no Medium, no secondary summaries.
- **[UNVERIFIED]** marks anything I could not confirm from a primary source.
- **(inference)** marks a conclusion I drew from sourced facts that no source states directly.
- **(experiment)** marks a claim established by running the code, not by reading it. Every
  experiment is reproducible from [Appendix A](#appendix-a-the-throwaway-harness).
- Short path prefixes:
  - `DBT/` = `https://github.com/dbt-labs/dbt-core/blob/v1.11.9/`
    (commit `c8cafcd97850d5cf8e159ac16b0f05cf342affaa`)
  - `DBT1125/` = `https://github.com/dbt-labs/dbt-core/blob/v1.12.5/`
    (commit `7f78d7b6aa3a88e5efa6dd92753e4983d92aeba4`) — read only to confirm the v1.11.9
    findings still hold at the newest v1 release
  - `DBT2/` = `https://github.com/dbt-labs/dbt/blob/612ff165/` (dbt v2, the Rust rewrite,
    `main` @ `612ff1656f3bee2b3253d3ce47b7756e6009d6f3`, 2026-10-02)
  - `DBTDOCS/` = `https://docs.getdbt.com/` — **the version selector on these pages now defaults
    to "dbt v2"**, with v1 / 1.12 / 1.11 also offered. Pages fetched 2026-10-02, "last updated
    Sep 10, 2026". So the prose I quote describes v2 unless stated otherwise; the code I quote
    describes v1.
  - `EDR/` = `https://github.com/elementary-data/dbt-data-reliability/blob/9a7e2b55/`
    (**package 0.26.0**, tag `0.26.0` = commit `9a7e2b559693e662c30672b2d449b4025c254cd9`)
  - `EDOCS/` = `https://docs.elementary-data.com/` (source:
    `elementary-data/elementary@e34d8539:docs/`)

### Nothing is installed in this repo

Checked before reading anything:

- `uv pip list | grep -i -E 'dbt|elementary'` → **empty**.
- No `dbt_project.yml`, no `packages.yml`, no `package-lock.yml` anywhere in the working tree.
- No `~/.dbt` directory. No `dbt` on `PATH`. `import dbt` fails.

So **this repo has no dbt install, no dbt project and no Elementary install today**, and nothing
below describes an installed version. Everything is pinned to a specific released version or
commit, named above, so that the proposal's claims stay checkable against whatever eventually
gets installed. To settle the questions that could not be settled by reading, I built a
**throwaway harness outside the repo** (in `/tmp`, nothing committed): dbt-core 1.11.9 +
dbt-postgres 1.11.0 + dbt-duckdb 1.11.0, with the Elementary package 0.26.0 installed from dbt
Hub. See [Appendix A](#appendix-a-the-throwaway-harness).

Version notes that matter for pinning:

- The newest published dbt-core v1 is **1.12.5** (dbt's own `--version` self-check said so). I
  ran the harness on **1.11.9**, because `dbt-postgres`/`dbt-duckdb` had no 1.12-series release
  to pair with it. I therefore diffed every file I rely on between `v1.11.9` and `v1.12.5`:
  the source tag-inheritance block is byte-identical (`DBT1125/core/dbt/parser/sources.py:264-272`
  vs `DBT/core/dbt/parser/sources.py:263-272`) and the empty-selection short circuit is
  structurally identical (`DBT1125/core/dbt/task/runnable.py:766-775`). Both findings hold at
  1.12.5.
- `dbt-labs/dbt-core`'s `main` branch **no longer contains the Python v1 implementation**. Its
  README says: "dbt v1 development has moved to the `1.latest` branch. The `main` branch now
  contains all the Apache 2.0 source code of dbt v2.0 — a ground-up rewrite of dbt in Rust"
  (`DBT2/README.md`). Elementary 0.26.0 declares
  `require-dbt-version: [">=1.0.0", "<3.0.0"]` (`EDR/dbt_project.yml:4`), so it nominally permits
  v2. **Everything in Q1 and Q2 below was verified against the Python v1 engine only.** See
  [§4](#4-the-dbt-v2-caveat).

---

## 0. Executive summary for the review

| # | Question | Short answer | Status |
|---|---|---|---|
| 1 | Does `dbt test --select tag:hourly` reach tests on *sources*? | **Yes — and twice over**, if and only if the tag is written as a top-level `tags:` key. Source and source-table `tags:` are **inherited by the attached tests**, so the tests are selected *directly*, and the source node also pulls them in *indirectly*. `dbt test` restricts to test resource types by itself; no `resource_type:test` or `test_type:` needed. But a tag written as `config: tags:` on a source table tags the **source node only, not its tests** — and that variant collapses to zero selected tests under `--indirect-selection empty`. | **verified** |
| 2 | Does Elementary's `on-run-end` persist correctly under a partial selection? | **Yes for a non-empty selection** — the macro iterates the `results` context variable, which dbt scopes to the selected nodes, and the metrics insert reads a per-run temp-table cache, not the graph. **No for an empty selection**: when zero nodes are selected, dbt short-circuits *before* `before_run`/`after_run`, so `on-run-start` and `on-run-end` **never fire**, nothing is written — not even a `dbt_invocations` row — and **the process exits 0**. That is exactly ADR-0018's silent-stop failure mode, and it is real. | **verified** |
| 3 | Is the `detection_delay` bound on `bucket_start` or `bucket_end`? | **`bucket_end <= detection_end`**, in three places. Consequence: `detection_delay` set to one bucket width costs **a full extra bucket of latency**, deterministically — the most recent closed bucket is always excluded. `detection_delay` *is* documented, and it does shift the `backfill_days` window (both ends move), contradicting a line in Elementary's own docs. | **verified** |

Three things the reviewer should take away:

1. **ADR-0018's named failure mode is real and dbt will not tell you.** A tier whose tag matches
   nothing prints two warnings and exits 0. The fix is one flag, below.
2. **The tag generator's YAML shape is load-bearing.** `tags:` and `config: tags:` are not
   interchangeable on sources. ADR-0018 does not say which one the registry emits.
3. **ADR-0013's latency budget is only valid at `detection_delay: 0`.** Adding a one-hour delay
   to absorb scheduling jitter turns "within 75 minutes" into "within 135 minutes".

---

## 1. Q1 — dbt selector semantics over sources

> **Verdict:** `dbt test --select tag:hourly` does select tests attached to source tables, with
> no extra selection method needed, provided the tag is a top-level `tags:` key on the source or
> source table — because those tags are *copied onto the test nodes at parse time*. A tag written
> as `config: tags:` works too, but only by indirect selection, and so breaks under
> `--indirect-selection empty`.

### 1.1 `dbt test` already restricts to tests. Nothing else is needed.

`TestTask` does not use the plain `NodeSelector`. It builds a `ResourceTypeSelector` whose
`resource_types` are `TEST_NODE_TYPES` (`DBT/core/dbt/task/test.py:410-427`):

```python
    @property
    def resource_types(self) -> List[NodeType]:
        resource_types: Collection[NodeType] = resource_types_from_args(
            self.args, set(TEST_NODE_TYPES), set(TEST_NODE_TYPES)
        )
        # filter out any non-test node types
        resource_types = [rt for rt in resource_types if rt in TEST_NODE_TYPES]
        return list(resource_types)
```

`TEST_NODE_TYPES = [NodeType.Test, NodeType.Unit]` (`DBT/core/dbt/node_types.py:30-33`).
`ResourceTypeSelector.node_is_match` returns `node.resource_type in self.resource_types`
(`DBT/core/dbt/graph/selector.py`, last 20 lines), and `NodeSelector.filter_selection` applies
`_is_match` to everything selected. So **the source node itself is selected and then filtered
back out**, and only its tests survive.

**`--select tag:X` on its own is therefore sufficient for `dbt test`.** Adding
`resource_type:test` or `test_type:generic` is redundant, not required. The `source:` method is
also not required; it is an *alternative* way in, documented for exactly this purpose
(`DBTDOCS/reference/node-selection/test-selection-examples`):

> "The same principle can be extended to tests defined on other resource types. In these cases,
> we will execute all tests defined on certain sources via the `source:` selection method"
> — with `dbt test --select "source:*"`, `source:jaffle_shop`, `source:jaffle_shop.customers`.

The `source:` method's own value grammar is `${source_name}`,
`${source_name}.${table_name}`, or `${package}.${source}.${table}`; anything with more than three
dot-separated parts is a runtime error (`DBT/core/dbt/graph/selector_methods.py:312-339`).
Note that the methods reference page describes `source:` purely in terms of *models*
("used to select models that select from a specified source… Use in conjunction with the `+`
operator", `DBTDOCS/reference/node-selection/methods`), which is why the test-selection page is
the one to cite for our use.

### 1.2 Tag inheritance source → table → test is real, and it only flows downward

Two different code paths compute tags, and they disagree about `config.tags`:

| Path | What it tags | Reads | Citation |
|---|---|---|---|
| `calculate_tags_from_raw_target` | the **source node** | `source.tags` + `source.config.tags` + `table.tags` + `table.config.tags` | `DBT/core/dbt/parser/sources.py:477-490` |
| `_parse_generic_test` | the **test nodes attached to a source** | `source.tags` + `table.tags` (+ column `tags` and column `config.tags`) | `DBT/core/dbt/parser/sources.py:263-272` |

The test path, quoted in full, is the load-bearing one:

```python
        tags_sources = [target.source.tags, target.table.tags]
        if column is not None:
            tags_sources.append(column.tags)
            if column_config_tags := column.config.get("tags", []):
                if isinstance(column_config_tags, list):
                    tags_sources.append(column_config_tags)
                elif isinstance(column_config_tags, str):
                    tags_sources.append([column_config_tags])
        tags = list(itertools.chain.from_iterable(tags_sources))
```

Three things follow directly from that list:

1. **`tags:` on a source, and `tags:` on a source table, are both inherited by every test under
   that table** — including table-level tests, not just column tests. Inheritance is one-way
   (source → table → test); a tag on a test never propagates up.
2. **`config: tags:` at the source or source-table level is *not* in the list.** It tags the
   source node, never the test node. (Column-level `config.tags` *is* in the list. The asymmetry
   is in the code at both 1.11.9 and 1.12.5; whether it is intentional is **[UNVERIFIED]** — I
   found no dbt docs page or changelog entry addressing it.)
3. **Models behave the opposite way.** For models, the test's inherited tags are the *column*
   tags only (`DBT/core/dbt/parser/schema_generic_tests.py:380-396`, `tags=column_tags`); a
   model-level `tags:`/`config.tags` is not copied onto its tests. So the convenient
   source-level inheritance we are relying on is a source-specific behaviour, and it is **not
   documented**: the methods page says nothing about tag inheritance from sources or source
   tables to their tests (`DBTDOCS/reference/node-selection/methods`, checked explicitly).

dbt-core's own functional suite relies on the inheritance, which is the strongest confirmation
short of running it. `DBT/tests/functional/sources/fixtures.py:94-137` defines a source with
`tags: [my_test_source_tag]` and a table with `tags: [my_test_source_table_tag]`, and
`DBT/tests/functional/sources/test_simple_source.py:89-110` asserts:

```python
        results = self.run_dbt_with_vars(
            project, ["test", "--models", "tag:my_test_source_table_tag+"]
        )
        assert len(results) == 6

        results = self.run_dbt_with_vars(project, ["test", "--models", "tag:my_test_source_tag+"])
        # test_table + other_test_table
        assert len(results) == 8
```

### 1.3 Indirect selection: it matters, but only for the `config.tags` spelling

Indirect selection expands a selection to adjacent tests. The four modes and the fact that
`eager` is the default are both in the code
(`DBT/core/dbt/graph/selector.py`, `expand_selection`, and
`DBT/core/dbt/cli/params.py:317-323`, `default="eager"`) and in the docs
(`DBTDOCS/reference/node-selection/test-selection-examples`: "You can use the following modes
(with `eager` as the default)"; empty mode "runs no tests and restricts the build to the selected
node… It doesn't execute any tests, whether they are directly attached to the selected node or
not").

The crucial structural fact is that **a test on a single source has exactly one parent**. So
`set(node.depends_on_nodes) <= set(selected)` is satisfied the moment the source is selected, and
`cautious` behaves like `eager` for it. `buildable` additionally unions `self.manifest.sources`
into the "present" set outright (`DBT/core/dbt/graph/selector.py`, `expand_selection`:
`selected_and_parents = selected.union(self.graph.select_parents(selected)).union(self.manifest.sources)`).
Only `empty` drops them.

(experiment) Measured on the harness with `dbt ls --resource-type test --select tag:X
--indirect-selection <mode>`, over a project with four source tables tagged four different ways:

| Tag written as | Test node's own tags | eager | cautious | buildable | empty |
|---|---|---|---|---|---|
| `tags:` on the source (top level) | `['hourly']` | 2 tests | 2 | 2 | **2** |
| `tags:` on the source table | `['daily']` | 1 test | 1 | 1 | **1** |
| `config: tags:` on the source table | `[]` | 1 test | 1 | 1 | **0 — "No nodes selected!"** |
| `config: tags:` on a *model* | `[]` | 1 test | 1 | 1 | **0 — "No nodes selected!"** |

The manifest confirms the mechanism directly (experiment, `target/manifest.json`): the source node
`source.tiertest.src_untagged.tbl_c` carries `['cfgdaily']` while its test
`source_not_null_src_untagged_tbl_c_id` carries `[]`.

So: with the top-level `tags:` spelling, the tier selection is robust across **all four** indirect
modes, because the tests carry the tag themselves and are selected directly. With the
`config: tags:` spelling, the tier depends on indirect expansion, and an operator (or a future dbt
default change, or a CI wrapper) setting `--indirect-selection empty` silently empties the tier.

**Status:** verified.

### What this means for the proposal

- `dbt test --select tag:hourly` is a valid tier mechanism over sources. No `source:` selector,
  no `resource_type:test`, no `test_type:` needed. ADR-0018's premise holds.
- **The registry's generated YAML must emit `tags:` at the source or source-table level, not
  `config: tags:`.** This is not a style preference; it is the difference between a tier that is
  selected directly and a tier that depends on indirect expansion. The modern dbt idiom is
  drifting toward `config:` blocks for everything (note that Elementary's own config for sources
  goes under `meta:`, `EDOCS/data-tests/add-elementary-tests`), so a generator author would
  plausibly pick the wrong one. Write it down in the registry's generator contract and assert it.
- Because inheritance flows source → table → test, the registry can tag at whichever level maps
  to the series kind: a whole source for a uniform-cadence landing zone, a single table where a
  kind differs. One generated tag per cadence tier, applied at the level the kind is declared at,
  is enough.
- The inheritance behaviour we depend on is **undocumented** and source-specific (models do the
  opposite). Treat it as a pinned-version behaviour: the Gate 1 check should include a parse-time
  assertion, not just a manual read. See [§5](#5-what-to-assert-instead-of-trusting-this-document).

---

## 2. Q2 — Elementary's `on-run-end` under a partial selection

> **Verdict:** Under a non-empty partial selection Elementary persists exactly the selected tier's
> results and nothing else — it iterates `results`, which dbt scopes to the selection, and the
> metrics insert reads a per-run temp-table cache rather than the graph. Under an **empty**
> selection the hook never runs at all, nothing is written, and dbt exits 0.

### 2.1 The hook chain, and what it reads

Elementary registers `on-run-end` in its own `dbt_project.yml` (`EDR/dbt_project.yml:24`).
`on_run_end()` gates on three things and then calls `handle_tests_results()`
(`EDR/macros/edr/system/hooks/on_run_end.sql:2,4,16-19`):

```jinja
{% macro on_run_end() %}
    {% if not elementary.is_elementary_enabled() %} {% do return("") %} {% endif %}
    {%- if execute and not elementary.is_docs_command() %}
        ...
        {% if elementary.is_test_command() and not elementary.get_config_var(
            "disable_tests_results"
        ) %}
            {% do elementary.handle_tests_results() %}
        {% endif %}
```

`is_test_command()` is `flags.WHICH in ["test", "build", "retry"]`
(`EDR/macros/utils/command_type_utils.sql:1-3`), so `dbt test --select tag:hourly` qualifies.

**Where the rows come from — the crux.** `handle_tests_results()` builds the
`elementary_test_results` payload via `get_result_enriched_elementary_test_results`, whose loop is
`{% for result in results %}` (`EDR/macros/edr/tests/on_run_end/handle_tests_results.sql:86`),
filtered to `{% if node.resource_type == "test" %}`. It does **not** iterate `graph.nodes`. And the
`data_monitoring_metrics` insert does not touch the graph either: it reads
`elementary.get_cache("tables").get("metrics").get("relations")`
(`handle_tests_results.sql:24-32`), i.e. the per-test temp relations created by the tests that
*actually ran in this invocation*, and unions them (`insert_data_monitoring_metrics`, same file,
from line 163).

So the dangerous shape the proposal feared — a hook that iterates the whole graph and therefore
writes rows for unselected tests, or drops rows for selected ones — is **not** how Elementary 0.26.0
works for either result table.

`results` is scoped to the selection by dbt, not by Elementary. `after_run` constructs the hook
context from the run's own results list (`DBT/core/dbt/task/run.py`, `after_run`):

```python
        extras = {
            "schemas": list({s for _, s in database_schema_set}),
            "results": [
                r for r in results if r.thread_id != "main" or r.status == RunStatus.Error
            ],  # exclude that didn't fail to preserve backwards compatibility
            "database_schemas": list(database_schema_set),
        }
```

(experiment) Confirmed with a bare `on-run-end` hook of
`{{ log('results len=' ~ (results | length), info=True) }}` over a project with two source tables,
one tagged `hourly` and one `daily`, each carrying one `elementary.volume_anomalies` test:

- `dbt test --select tag:hourly` → `MYHOOK results len=1`
- `dbt test --select tag:daily` → `MYHOOK results len=1`

(experiment) And the persistence is correct end to end. After `dbt test --select tag:hourly` only:

```
ELEMENTARY_TEST_RESULTS:
  ('test.tiertest.elementary_source_volume_anomalies_raw_base_.2d87b7a5cc', 'base', 'row_count', 'pass', 2026-10-02 20:25:00)
DATA_MONITORING_METRICS:
  ('DEV.MAIN.BASE', 'row_count', 356 rows, 2026-09-18 00:00 → 2026-10-02 20:00)
```

One row for the selected tier's test, zero for the unselected tier's. After then running
`--select tag:daily`, both tiers' rows are present, with distinct `detected_at`. No cross-writing
in either direction.

Worth knowing: the **dbt-artifact** uploads in the same hook (`upload_dbt_artifacts`,
`on_run_end.sql:11`) *are* whole-graph by design. (experiment) `elementary.dbt_tests` after a
`tag:hourly`-only run contains **both** tests, with their inherited tags visible:

```
test...volume_anomalies_raw_base_    ["elementary-tests", "hourly"]
test...volume_anomalies_raw2_base_   ["daily", "elementary-tests"]
```

That is a useful side effect: `dbt_tests.tags` is a warehouse-side record of which tier each test
*is assigned to*, independent of which tier last ran. See [§5](#5-what-to-assert-instead-of-trusting-this-document).

### 2.2 Zero selected nodes: the hook does not fire, nothing is written, exit code 0

`GraphRunnableTask.run()` short-circuits before the hook-bearing code path
(`DBT/core/dbt/task/runnable.py:603-626`):

```python
            if len(self._flattened_nodes) == 0:
                warn_or_error(NothingToDo())
                result = self.get_result(
                    results=[],
                    generated_at=datetime.now(timezone.utc).replace(tzinfo=None),
                    elapsed_time=0.0,
                )
            else:
                selected_uids = frozenset(n.unique_id for n in self._flattened_nodes)
                result = self.execute_with_hooks(selected_uids)
```

`execute_with_hooks` is the *only* caller of `before_run` and `after_run`
(`DBT/core/dbt/task/runnable.py:544-600`), and `after_run` is the only caller of
`safe_run_hooks(adapter, RunHookType.End, extras)`. So on an empty selection:
**`on-run-start` and `on-run-end` are both skipped entirely.**

`NothingToDo` is a `WarnLevel` event whose message is "Nothing to do. Try checking your model
configs and model specification args" (`DBT/core/dbt/events/types.py:1936-1941`). An unmatched
criterion additionally fires `NoNodesForSelectionCriteria`, also `WarnLevel`: "The selection
criterion '{spec_raw}' does not match any enabled nodes"
(`DBT/core/dbt/events/types.py:1510-1515`). And with `results=[]`,
`interpret_results` computes `num_total == 0` and returns `True` — **success**
(`DBT/core/dbt/task/runnable.py:655-672`).

(experiment) Exactly as read:

```
$ dbt test --select tag:weekly
  The selection criterion 'tag:weekly' does not match any enabled nodes
  Nothing to do. Try checking your model configs and model specification args
$ echo $?
0
```

No `MYHOOK` line. No Elementary rows. **And no `elementary.dbt_invocations` row either** — after
four successful invocations plus this one, `dbt_invocations` still held four rows, the four
being `run --select elementary`, `run --select base`, `test --select tag:hourly`,
`test --select tag:daily`. The invocation table records the selection criteria in a `selected`
column, which would be the obvious place to audit tier coverage from — but the row for the
silently-stopped tier is never written, because writing it is itself part of `on-run-end`. **The
silent stop is silent in Elementary's tables too.**

### 2.3 The subtler empty case, and why one warning is not enough

A tier can select zero *tests* while still matching the criterion. (experiment) With a tag written
as `config: tags:` on a source table and `--indirect-selection empty`:

```
$ dbt test --select tag:cfgtier --indirect-selection empty
  Nothing to do. Try checking your model configs and model specification args
$ echo $?
0
```

`NoNodesForSelectionCriteria` **did not fire** — the criterion did match a node, the source. Only
`NothingToDo` fired. So a mitigation that escalates only `NoNodesForSelectionCriteria` would miss
this case. Both must be escalated.

### 2.4 The mitigation, verified

Both events are `warn_or_error` events, so `--warn-error-options` escalates them
(`DBT/core/dbt/cli/params.py:820-827`; env var `DBT_WARN_ERROR_OPTIONS`).

(experiment) Each row below is a real exit code from the harness:

| Command | Exit |
|---|---|
| `dbt test --select tag:weekly` | **0** |
| `dbt test --select tag:weekly --warn-error-options '{"error": ["NoNodesForSelectionCriteria"]}'` | **2** ("Compilation Error: The selection criterion 'tag:weekly' does not match any enabled nodes") |
| `dbt test --select tag:weekly --warn-error-options '{"error": ["NothingToDo"]}'` | **2** ("Compilation Error: Nothing to do…") |
| `dbt test --select tag:cfgtier --indirect-selection empty` | **0** |
| `dbt test --select tag:cfgtier --indirect-selection empty --warn-error-options '{"error": ["NothingToDo","NoNodesForSelectionCriteria"]}'` | **2** |
| `dbt test --select tag:weekly --warn-error` | **2** (escalates everything, including unrelated deprecations) |

### 2.5 Other conditions under which the hook does not write

| Condition | Effect | Source |
|---|---|---|
| `vars: disable_tests_results: true` | `handle_tests_results()` skipped; artifacts and run-results uploads still happen | `on_run_end.sql:16-19`; `EDR/macros/edr/system/system_utils/get_config_var.sql:126` |
| `vars: edr_cli_run: true` | the **entire** hook returns early | `on_run_end.sql:6`; `get_config_var.sql:134` |
| `dbt docs generate` / `serve` | whole hook skipped | `on_run_end.sql:4` |
| `elementary_enabled` | **No such flag exists.** `is_elementary_enabled()` only checks that the package's database/schema resolves to something non-null — it is a misconfiguration guard, not a user toggle | `EDR/macros/edr/system/system_utils/is_elementary_enabled.sql` |
| Also available: `disable_dbt_artifacts_autoupload`, `disable_run_results`, `disable_dbt_invocation_autoupload`, `disable_freshness_results` | each suppresses its own upload only | `on_run_end.sql:10-30`; `get_config_var.sql:124-134` |
| `--store-failures` off | **No effect on the hook.** Elementary's own storage path is independent of dbt's `store_failures`; anomaly tests go through `store_anomaly_test_results` and store aggregates only | `handle_tests_results.sql` throughout; prior note `research-elementary-operations-2026-09-22.md` §1.1 |
| `--empty` | **Not a `dbt test` flag.** `--empty/--no-empty` exists as a param (`DBT/core/dbt/cli/params.py:213-218`) but is not attached to the `test` command, so the question does not arise. **[UNVERIFIED]** for `dbt build --empty`, which I did not test | `DBT/core/dbt/cli/params.py:213-218` |
| Run killed before `on-run-end` | no rows; the insert is a single post-run operation | (inference), consistent with prior note §2 |

**Status:** verified. (The sub-claim about `dbt build --empty` is the one gap, and it is not on the
proposal's path.)

### What this means for the proposal

- **ADR-0018's "a tier that silently stops being tested is the failure mode to rule out" is not
  hypothetical. It is dbt's default behaviour, and it is worse than feared** — not merely "tests
  selected out but reported as success", but *no hook, no rows, no invocation record, exit 0*. The
  tier simply ceases to exist and every observable surface says fine.
- **Every scheduled tier invocation must carry
  `--warn-error-options '{"error": ["NothingToDo", "NoNodesForSelectionCriteria"]}'`** (or the env
  var equivalent, so it cannot be forgotten per-command). Both names, for the reason in §2.3.
  This turns the silent stop into a non-zero exit the orchestrator can alert on. It is the
  cheapest control in the whole design and it belongs in ADR-0018's consequences, not in a runbook.
- The good news is that the hard part works: Elementary's partial-selection persistence is
  correct, so **the "one dbt project, one schedule per tier" shape in ADR-0018 is sound** and the
  single-egress-path assumption ADR-0013 rests on is not threatened by tiering. ADR-0018's
  rejection of a project-per-tier stands on the grounds it gave.
- Do **not** plan to audit tier coverage from `elementary.dbt_invocations`, which is the obvious
  candidate: the row is written by the same hook that does not run. Audit from `dbt_tests.tags`
  (whole-graph, uploaded on every successful invocation) joined against
  `elementary_test_results`/`data_monitoring_metrics` freshness. See [§5](#5-what-to-assert-instead-of-trusting-this-document).

---

## 3. Q3 — `detection_delay` at bucket boundaries

> **Verdict:** The bound is **`bucket_end <= detection_end`**, in the metric-collection bucket
> grid, in the anomaly-scoring bucket grid, and in the per-adapter grid generator. A
> `detection_delay` of one bucket width therefore costs **a full extra bucket of latency**, every
> time, because the most recent closed bucket always has `bucket_end > detection_end`.

### 3.1 `detection_end` is a wall-clock instant, not a bucket boundary

```jinja
{% macro get_detection_end(detection_delay) %}
    {% if not detection_delay %}
        {% do return(elementary.get_run_started_at().replace(microsecond=0)) %}
    {% endif %}
    {%- set kwargs = {detection_delay.period + "s": detection_delay.count} %}
    {%- set detection_end = elementary.get_run_started_at().replace(
        microsecond=0
    ) - modules.datetime.timedelta(**kwargs) %}
    {% do return(detection_end) %}
{% endmacro %}
```

`EDR/macros/edr/data_monitoring/data_monitors_configuration/get_buckets_configuration.sql:1-11`.
Note there is **no bucket truncation** — `detection_end` is `run_started_at` minus the delay, an
arbitrary instant.

### 3.2 The bucket grid is filtered on `bucket_end`, three times over

**Metric collection, incremental path** (which is the one sources take — Elementary treats sources
as incremental: "We assume we should also cosider sources as incremental",
`get_buckets_configuration.sql:139-143`, calling `is_incremental_model(..., source_included=true)`):

```sql
        with all_buckets as (
            select edr_bucket_start as bucket_start, edr_bucket_end as bucket_end
            from ({{ elementary.complete_buckets_cte(metric_properties, trunc_min_bucket_start_expr, detection_end_expr) }}) results
            where edr_bucket_start >= {{ trunc_min_bucket_start_expr }}
            and edr_bucket_end <= {{ detection_end_expr }}
        ),
        buckets_with_existing_metrics as (
            select distinct bucket_start, bucket_end
            from {{ data_monitoring_metrics_relation }}
            where bucket_start >= {{ trunc_min_bucket_start_expr }}
            and bucket_end <= {{ detection_end_expr }}
```

`get_buckets_configuration.sql:99-109`. The upper bound on the candidate grid is
`edr_bucket_end <= detection_end`; the lower bound is on `bucket_start`.

**Anomaly scoring** repeats the identical pair
(`EDR/macros/edr/data_monitoring/anomaly_detection/get_anomaly_scores_query.sql:104-108`):

```sql
                select edr_bucket_start, edr_bucket_end
                from ({{ elementary.complete_buckets_cte(metric_properties, min_bucket_start_expr,
                                                         detection_end_expr) }}) results
                where edr_bucket_start >= {{ min_bucket_start_expr }}
                  and edr_bucket_end <= {{ detection_end_expr }}
```

**The grid generator itself** applies the same bound a third time, inside every adapter
implementation. Snowflake's (`EDR/macros/edr/system/system_utils/buckets_cte.sql:95-114`):

```sql
        with timestamps as (
          select {{ min_bucket_start_expr }} as edr_bucket_start
          union all
          select {{ bucket_end_expr }} as next_bucket
          from timestamps
          where next_bucket < {{ max_bucket_end_expr }}
        )
        select
          edr_bucket_start,
          {{ bucket_end_expr }} as edr_bucket_end
        from timestamps
        where {{ bucket_end_expr }} <= {{ max_bucket_end_expr }}
```

Every other adapter in that file — postgres, redshift, bigquery, databricks/spark, duckdb, athena,
trino, clickhouse, fabric, vertica, sqlserver, dremio — ends with the same
`where <bucket_end expr> <= max_bucket_end_expr`. **The bound is on `bucket_end` and it is
adapter-independent.** (The non-incremental path reaches the same place differently, by computing
`max_bucket_end = days_back_start + floor(datediff / count) * count` whole buckets,
`get_buckets_configuration.sql:84-95`.)

### 3.3 The latency consequence, derived and then measured

Let bucket width be `W`, and let `B` be the end of the most recent *closed* bucket at the moment
the test runs. By definition `run_started_at ∈ [B, B + W)`.

- With `detection_delay: 0` → `detection_end = run_started_at >= B`, so `B <= detection_end` and
  **the most recent closed bucket is included**. Latency to detection is the scheduling gap only.
- With `detection_delay` = `W` → `detection_end = run_started_at - W ∈ [B - W, B)`, so
  `detection_end < B` **always**, and the most recent closed bucket is **always excluded**. The
  previous bucket, ending `B - W <= detection_end`, is the newest one scored.

So the answer to the question as posed: **a full extra bucket of latency, deterministically.** (If
the bound had been on `bucket_start`, a one-bucket delay would have cost nothing, since
`B - W <= detection_end` holds; it is the `bucket_end` spelling that costs the bucket.) A delay
*shorter* than `run_started_at - B` costs nothing; anything longer costs the bucket. At
`detection_delay == W` the cost is unconditional.

(experiment) Measured. Two identical source tables, both `time_bucket {hour, 1}`, both
`timestamp_column: loaded_at`, differing only in `detection_delay`; one `dbt test` invocation at
**20:26:54 UTC**:

| Source table | `detection_delay` | rows in `data_monitoring_metrics` | `max(bucket_end)` |
|---|---|---|---|
| `DEV.MAIN.BASE` | *(none)* | 356 | **2026-10-02 20:00** |
| `DEV.MAIN.BASE_B` | `{period: hour, count: 1}` | 355 | **2026-10-02 19:00** |

The 19:00–20:00 bucket — closed 27 minutes before the run — is present without the delay and
absent with it. One bucket, one row, exactly as derived.

### 3.4 Is it documented? And does it interact with `backfill_days`?

**Documented: yes**, with its own page, `EDOCS/data-tests/anomaly-detection-configuration/detection-delay`
(source `docs/data-tests/anomaly-detection-configuration/detection-delay.mdx`):

> "The duration for retracting the detection period. That's useful in cases which the latest data
> should be excluded from the test. For example, this can happen because of scheduling issues- if
> the test is running before the table is populated for some reason. The detection delay is the
> period of time to ignore, after the detection period."
> "_Default: 0_ … _Relevant tests: Anomaly detection tests with `timestamp_column`_"

Two defects in that page, both confirmed against code:

1. **The documented period list is wrong.** The page says "supported periods: hour, day, week,
   month". The code's allow-list is `["hour", "day", "week"]`
   (`EDR/macros/edr/tests/test_configuration/get_detection_delay.sql:9-11`), and
   `validate_detection_delay` raises a compiler error for anything outside it (same file,
   lines 66-72). `detection_delay: {period: month, count: 1}` is a documented value that fails to
   compile. (`time_bucket` *does* accept `month` on Snowflake — `default__supported_periods()`
   returns `["hour", "day", "week", "month"]`,
   `EDR/macros/edr/tests/test_configuration/get_time_bucket.sql:80-82` — so the two lists differ,
   which is probably where the doc error came from.)
2. **"It does not affect the other duration parameters, like `detection_period` or
   `training_period`"** is true of their *lengths* and misleading about their *positions*. Both
   window starts are computed *from* `detection_end`:
   - `get_backfill_bucket_start(detection_end, backfill_days)` =
     `(detection_end - timedelta(backfill_days)).strftime("%Y-%m-%d 00:00:00")`
     (`get_buckets_configuration.sql:27-33`)
   - `get_trunc_min_bucket_start_expr(detection_end, metric_properties, days_back)` truncates
     `detection_end - days_back` to midnight and then `date_trunc`s to the bucket period
     (`get_buckets_configuration.sql:13-25`)

   So `detection_delay` slides the **whole** detection and training window backwards by the delay.
   Both ends move; neither length changes. That is the honest statement.

Two further interaction facts worth recording, since the proposal uses hourly buckets:
`backfill_days` is a **whole-day** count and the backfill start is truncated to **midnight**
(`get_backfill_bucket_start`, above). So at the default `backfill_days: 2`, an hourly-bucketed
series recomputes on the order of 48–72 hourly buckets on every invocation regardless of
`detection_delay` — which is precisely the "recompute two daily buckets twenty-four times a day
for no new information" cost argument ADR-0018 makes for tiering, in its hourly form.

**Status:** verified.

### What this means for the proposal

- **`detection_delay` is not a free jitter absorber.** It is tempting for exactly the problem its
  docs describe — "the test is running before the table is populated" — which is a real risk on an
  hourly tier where the test schedule and the load schedule are independent. But at one bucket
  width it costs a whole bucket of detection latency, unconditionally.
- **This collides with ADR-0013's stated latency budget.** ADR-0013 says, of the E2
  hourly-bucketed path:

  > "on E2's hourly-bucketed series tested hourly, a shortfall becomes a case **within 75 minutes
  > of the end of the hour it occurred in**, the spread depending on where the bucket boundary
  > falls relative to the test schedule — the bucket must close, the next `dbt test` must run, and
  > the poll must come round."

  That chain is correct **only at `detection_delay: 0`**, which ADR-0013 never states as a
  precondition. Add `detection_delay: {period: hour, count: 1}` and the chain gains a fourth link
  — the bucket must close, *then a further hour must elapse*, then the test must run, then the
  poll must come round — making it **within 135 minutes**. ADR-0013 should either state
  `detection_delay: 0` as a precondition of the 75-minute figure, or quote the 135-minute figure.
  This is not a contradiction of ADR-0013 as written; it is an unstated precondition that the
  obvious operational fix would violate.
- The right place to absorb load jitter is therefore the **test schedule offset**, not
  `detection_delay`: run the hourly tier at e.g. `:20` rather than `:00`, which costs 20 minutes
  instead of 60 and keeps the most recent closed bucket in scope. `detection_delay` is for the
  case where data arrives *more than* a bucket late, and should be a declared property of a series
  kind in the registry (ADR-0018) with its latency cost written next to it, not a tuning knob
  someone reaches for during an incident.
- The registry should reject `detection_delay: {period: month, ...}` at generation time, since the
  docs advertise it and the code rejects it (§3.4).

---

## 4. The dbt v2 caveat

Q1 and Q2 are verified against the **Python v1 engine**. dbt v2 (the Rust rewrite) is now what
`dbt-labs/dbt`'s `main` branch contains, and the docs pages I read default to it. The pieces I
could confirm about v2 in a short pass:

- It has an equivalent warn-level code: `ErrorCode::NoNodesSelected = 1601`
  (`DBT2/crates/dbt-error/src/codes.rs:248`), emitting "The selection criterion '{}' does not match
  any enabled nodes" (`DBT2/crates/dbt-main/src/compilation.rs:1720-1727`,
  `DBT2/crates/dbt-main/src/dbt_lib.rs:1389`), and it participates in `warn_error_options`
  (`DBT2/crates/dbt-common/src/warn_error_options/legacy.rs:27`).
- It knows about Elementary's hook specifically — its adapter test fixtures reference
  `operation.elementary.elementary-on_run_end-0`
  (`DBT2/crates/dbt-adapter/src/time_machine/validation.rs:1254`), so Elementary-on-v2 is at least
  on dbt Labs' radar.
- It has `indirect_selection` handling in `DBT2/crates/dbt-parser/src/resolve/resolve_selectors.rs`.

What I did **not** establish for v2, and what therefore stays **[UNVERIFIED]**: whether source
`tags:` are still inherited by source tests; whether `on-run-end` fires when zero nodes are
selected; whether a `NothingToDo` equivalent exists at all (I found no such string in the Rust
crates).

**Recommendation:** pin the tier runner to **dbt-core v1 (Python)**, record the pin in the
registry's generator contract, and re-run the [§5](#5-what-to-assert-instead-of-trusting-this-document)
assertions as part of any v2 migration. Elementary's `require-dbt-version` of `<3.0.0` will not
stop you from installing v2 and silently inheriting different selector semantics.

---

## 5. What to assert instead of trusting this document

Everything above is pinned to versions that are not installed here. Three cheap, automatable
checks turn these findings into guarantees that survive an upgrade. All three run from
`manifest.json` or a single warehouse query; none needs a live anomaly.

1. **Parse-time tag coverage (catches the `config: tags:` trap and a mis-generated registry).**
   `dbt parse`, then over `target/manifest.json`: for every node with
   `resource_type == "test"` whose `depends_on.nodes` contains a `source.*` id, assert its `tags`
   contain **exactly one** of the declared cadence tiers. A test with zero tiers is an orphan
   nobody schedules; a test with two is a drift ADR-0018 already warns about ("a series bucketed
   daily and tested hourly is a drift that no tool would report"). This is the assertion that
   makes ADR-0018's "the tags are generated from this registry rather than maintained beside it"
   enforceable rather than aspirational.
2. **Non-empty tier at invocation time.** Every scheduled tier command carries
   `--warn-error-options '{"error": ["NothingToDo", "NoNodesForSelectionCriteria"]}'`. Verified in
   §2.4. Set it as `DBT_WARN_ERROR_OPTIONS` in the tier's environment so a hand-run command cannot
   omit it.
3. **Warehouse-side tier liveness, from `dbt_tests` not `dbt_invocations`.** Join
   `elementary.dbt_tests` (whole-graph, has the tier in `tags`) to the newest `detected_at` in
   `elementary_test_results` per `test_unique_id`, and alert when a test's staleness exceeds a
   small multiple of its tier's cadence. This is the only one of the three that catches a tier
   that stopped running because its *scheduler* stopped, rather than because its selection
   emptied — and it reuses the read pattern and the grants ADR-0013 and ADR-0010 already
   establish. Do not build it on `dbt_invocations.selected`: §2.2 shows that row is absent in
   exactly the case you are trying to detect.

### Experiments that would settle the remaining gaps

Each needs only a minimal dbt project; none needs Snowflake.

- **Does the v2 engine inherit source tags and fire `on-run-end` on an empty selection?** Install
  the v2 binary, reuse the [Appendix A](#appendix-a-the-throwaway-harness) project verbatim, and
  run the same six commands. Look at: the test nodes' `tags` in the manifest, whether the
  `on-run-end` log line appears, and `echo $?`.
- **`dbt build --empty` interaction with the hook.** Add a model, run
  `dbt build --empty --select tag:hourly`, and check whether `elementary_test_results` gains rows
  and whether `data_monitoring_metrics` gains rows with plausible values. The concern is metrics
  computed against an empty relation being persisted as real history.
- **Is the `config: tags:` / `tags:` asymmetry for sources intentional?** Search dbt-core's issue
  tracker and the `1.latest` branch changelog for the `tags_sources` list. Settles whether
  recommendation §1 is a durable contract or a bug that may be "fixed" in either direction.

---

## Appendix A — the throwaway harness

Built outside the repo, at `/tmp/dqres`. Nothing was installed into
`/home/sas/workspace/aiops` and no file in it was modified other than this one.

```
python 3.11 venv
dbt-core      1.11.9      (newest published v1 is 1.12.5; see Reading Rules)
dbt-postgres  1.11.0      (used for `dbt ls` selection tests only — never connects)
dbt-duckdb    1.11.0      (used for the execution tests; no server needed)
elementary    0.26.0      (from dbt Hub; `dbt deps` reported 0.26.0 as the newest
                           version compatible with the installed dbt-core)
```

The installed package's macros were diffed against the `0.26.0` tag **and** against repo HEAD
(`91ffeabb`, 2026-10-01). All six files this note quotes —`on_run_end.sql`,
`handle_tests_results.sql`, `get_buckets_configuration.sql`, `get_anomaly_scores_query.sql`,
`buckets_cte.sql`, `get_detection_delay.sql` — are **byte-identical across installed 0.26.0, tag
`9a7e2b55`, and HEAD `91ffeabb`**. So the `EDR/` citations describe both the released package and
current `main`.

Project shapes used:

- **Selection project** (postgres profile, never connected; `dbt parse` + `dbt ls` only): four
  source tables tagged four ways — source-level `tags:`, table-level `tags:`, table-level
  `config: tags:`, and a model-level `config: tags:` control — each with a `not_null` test on a
  column. Produced the §1.2 manifest facts and the §1.3 matrix.
- **Execution project** (duckdb): one `table`-materialised model of 499 rows spaced one hour
  apart, exposed as two dbt sources (`raw`/`raw2`) with `tags: [hourly]` and `tags: [daily]`,
  `meta.elementary.timestamp_column: loaded_at`, `time_bucket` of `{hour,1}` and `{day,1}`, each
  carrying `elementary.volume_anomalies`; plus a bare
  `on-run-end: "{{ log('MYHOOK results len=' ~ (results | length), info=True) }}"`. Bootstrapped
  with `dbt deps`, `dbt run --select elementary` (33 models), `dbt run`. Produced §2.1, §2.2, §2.3
  and §2.4.
- **Delay project** (duckdb, fresh database): two identical 499-row tables, two sources, both
  `{hour,1}` buckets, one with `detection_delay: {period: hour, count: 1}` and one without, tested
  in a single invocation. Produced §3.3.

**Caveat on the experiments.** They ran on **duckdb, not Snowflake**. The findings they support
are adapter-independent by construction: Q1 and Q2 are dbt-core selection, hook-dispatch and
exit-code behaviour, which runs before any adapter SQL; Q3's bound is in the Jinja predicate and
is repeated verbatim in every one of the twelve adapter implementations of
`complete_buckets_cte`, Snowflake's included (§3.2). A Snowflake re-run would nevertheless be
cheap insurance at Gate 1, and would also settle whether session timezone (ADR-0013's known trap)
perturbs `get_run_started_at()` relative to bucket boundaries — a question this pass did not ask.

---

## Sources read

| Source | Version / commit | Read for |
|---|---|---|
| `dbt-labs/dbt-core` @ `v1.11.9` (`c8cafcd9`): `core/dbt/graph/selector.py`, `selector_methods.py`; `core/dbt/task/test.py`, `task/run.py`, `task/runnable.py`; `core/dbt/parser/sources.py`, `parser/schema_generic_tests.py`, `parser/generic_test_builders.py`; `core/dbt/node_types.py`, `events/types.py`, `cli/params.py`; `tests/functional/sources/{fixtures.py,test_simple_source.py}` | cloned 2026-10-02 | Q1 selector + parser semantics; Q2 hook dispatch and empty-selection short circuit |
| `dbt-labs/dbt-core` @ `v1.12.5` (`7f78d7b6`): same files, diffed against `v1.11.9` | cloned 2026-10-02 | confirming the two load-bearing findings survive to the newest v1 |
| `dbt-labs/dbt` @ `612ff165` (`main` = dbt v2, Rust): `README.md`, `Cargo.toml`, `crates/dbt-error/src/codes.rs`, `crates/dbt-main/src/{compilation.rs,dbt_lib.rs}`, `crates/dbt-common/src/warn_error_options/legacy.rs`, `crates/dbt-adapter/src/time_machine/validation.rs` | cloned 2026-10-02 | §4, the v2 caveat |
| `DBTDOCS/reference/node-selection/methods`; `DBTDOCS/reference/node-selection/test-selection-examples` | version selector defaults to **dbt v2**; v1 / 1.12 / 1.11 also offered; "last updated Sep 10, 2026"; fetched 2026-10-02 | indirect-selection modes and defaults; `source:` and `test_type:` for `dbt test`; confirmed **silence** on source→test tag inheritance |
| `elementary-data/dbt-data-reliability` @ tag `0.26.0` = `9a7e2b55` (HEAD `91ffeabb` 2026-10-01 also checked; the quoted files are identical): `dbt_project.yml`; `macros/edr/system/hooks/on_run_end.sql`; `macros/utils/command_type_utils.sql`; `macros/edr/system/system_utils/{is_elementary_enabled.sql,get_config_var.sql,buckets_cte.sql}`; `macros/edr/tests/on_run_end/handle_tests_results.sql`; `macros/edr/data_monitoring/data_monitors_configuration/get_buckets_configuration.sql`; `macros/edr/data_monitoring/anomaly_detection/get_anomaly_scores_query.sql`; `macros/edr/tests/test_configuration/{get_detection_delay.sql,get_time_bucket.sql}` | cloned 2026-10-02 | Q2 hook internals; Q3 predicates |
| `elementary-data/elementary` @ `e34d8539` `docs/`: `data-tests/anomaly-detection-configuration/{detection-delay,detection-period}.mdx` | cloned 2026-10-02 (same commit as the 2026-09-22 notes) | Q3 documentation status and the two doc defects |
| The throwaway harness | dbt-core 1.11.9, dbt-postgres 1.11.0, dbt-duckdb 1.11.0, elementary 0.26.0 | all `(experiment)` claims; see [Appendix A](#appendix-a-the-throwaway-harness) |
| This repo | working tree 2026-10-02 | confirming **no** dbt/Elementary install, no dbt project, no `~/.dbt` |
| Prior notes in this repo: `docs/research-elementary-operations-2026-09-22.md`, `docs/research-medallion-path-facts-2026-09-22.md` | working tree | structure, citation style, and the already-established facts this note builds on (sources-as-incremental, `meta.elementary` config, bucket/window knobs) |
