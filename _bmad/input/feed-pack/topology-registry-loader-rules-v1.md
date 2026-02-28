# Topology Registry Schema Evolution & Loader Rules — v1 (Freeze Candidate)
**Date:** 2026-02-22  
**Purpose:** Lock backward-compat behavior while migrating from legacy `streams[]` to `streams[].instances[]` without breaking Phase 1A.

---

## 1) Goal (what we are locking)
We are locking **loader behavior**, not every registry field.

**Target:** one canonical in-memory model:
- `streams[]` (logical pipelines grouped by `stream_id`)
- `streams[].instances[]` (runtime scope keyed by `(env, cluster_id)`)

This preserves the locked semantic:  
`stream_id` = logical end-to-end pipeline grouping key; `env/cluster_id` are **instance-scoped**.

---

## 2) Supported input shapes
### 2.1 Legacy shape (v0)
A legacy stream entry may contain topics/ACL/sinks at stream scope and may implicitly assume one environment/cluster.

### 2.2 Instances shape (v1)
A stream entry explicitly declares:
- `instances[]` where each instance has:
  - `env`
  - `cluster_id` (must equal Prometheus `cluster_name` string)
  - `topic_index` scoped within this `(env, cluster_id)`

---

## 3) Loader contract (hard rules)
### 3.1 Version detection
Loader MUST accept both formats:
- If `streams[].instances[]` exists → treat as v1.
- Else → treat as v0 legacy.

Loader should also accept an optional top-level `schema_version` (recommended):
- `schema_version: 0` or `schema_version: 1`
If absent, infer from presence of `instances[]`.

### 3.2 Canonicalization
Loader output MUST always be canonical v1 in-memory:
- Every `stream` becomes a `stream` with `instances[]`.
- Legacy `stream` without `instances[]` becomes **one instance**.

### 3.3 Legacy → v1 mapping rule
If a legacy stream does not declare `env/cluster_id`, loader applies:
- `env := default_env` (from loader config, per deployment)
- `cluster_id := default_cluster_id` (from loader config, per deployment)
- Create `instances[0]` with those values.

**Important:** we do **not** guess cluster_id. It is injected by config, or the registry must be upgraded.

### 3.4 Backward compatibility for consumers
Any internal consumer that still expects legacy fields must consume via a **compat view**:
- `stream.compat.default_instance := instances[0]`
- If multiple instances exist, compat view uses:
  - a) explicit `compat_default_instance_key` if provided, else
  - b) deterministic ordering (env, cluster_id lexicographic) **only for compat**, never for routing.

Do NOT merge instances back into a single view unless explicitly requested (merging causes topic collisions).

---

## 4) Topic index scoping rules (collision prevention)
### 4.1 Scope
`topic_index` MUST be scoped by `(env, cluster_id)`:
- Same topic name may exist in multiple clusters; that is allowed.
- Within a single instance, topic names must be unique per role (or unique overall, depending on your model).

### 4.2 Uniqueness validation
Loader validation MUST fail fast if within a single instance:
- Duplicate `topic_index` keys collide (same topic+role identity)
- Duplicate consumer-group ownership keys collide (same `(env, cluster_id, group)` owner maps to multiple routing keys)

---

## 5) Ownership routing integration (v1)
Ownership lookup priority is locked:
1) consumer group owner `(env, cluster_id, group)`
2) topic owner `(env, cluster_id, topic)`
3) stream default owner `(stream_id, env, cluster_id)`
4) platform default

Loader MUST validate that all referenced `routing_key` values exist in `routing_directory`.

---

## 6) Validation rules (minimum)
Loader must validate:
- `cluster_id` strings are non-empty and treated as opaque IDs (no normalization)
- `env` in allowed enum (local/dev/nonprod/prod) as per deployment policy
- `stream_id` unique across registry
- `instances[]` keys unique by `(env, cluster_id)` per stream
- `topic_index` keys unique within instance scope

---

## 7) Deprecation plan
- **Phase 1A:** Loader supports v0 + v1. New changes must be made in v1 format.
- **Phase 1B/2:** Emit warnings if v0 streams detected.
- **Phase 2+:** Remove v0 support once all registries migrated and consumers use canonical model.

---

## 8) What this prevents (explicitly)
- Cross-cluster topic collisions in `topic_index`
- Silent misrouting due to guessed cluster IDs
- Breaking consumers during migration
- “Merge everything” anti-pattern that destroys instance semantics

