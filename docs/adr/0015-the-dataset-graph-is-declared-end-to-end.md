---
status: proposed
---

# The dataset graph is declared end to end, because dbt manifests are not available to us

ADR-0002 keeps one declared hop (source → landing table) and derives everything below it from dbt's `manifest.json`. That premise does not hold: the manifests for the dbt projects that build the medallion zones are not available to us, and the platform is multitenanted and self-serve, so there is no single manifest spanning bronze to hosting even in principle. Root dataset, blast radius and the "a monitored ancestor was clean" test all read that graph, so without it they have no implementation.

We therefore declare the graph end to end. For the E2 path this is cheap and honest, because the whole graph is ours and it is three nodes: Kafka topic → landing table → consumer table, the first edge being the source mapping and the second the copy E2 performs inside its own Snowflake schema. Root and blast radius are computed over that declared graph. Deriving the graph from dbt lineage moves from a v1 mechanism to a v2 capability, conditional on manifest access, and joins the requests of other platforms with the declared graph as its fallback.

## Considered Options

- **Derive lineage from `manifest.json`.** The intended design, and unavailable. Kept as the v2 target, since a declared graph does not scale past paths we own.
- **Infer lineage from Snowflake `ACCESS_HISTORY` or query logs.** Not pursued for v1: it needs account-level privileges we are less likely to get than the manifests themselves, and it infers edges probabilistically where the declared graph states them.
- **Drop root and blast radius until lineage exists.** Rejected: on the E2 path the graph is small and ours, and the concepts need exercising on a real graph before they are extended to a large one.

## Consequences

- The declared graph is maintained by hand. At three nodes per topic on a path we own, that is sustainable; across the medallion it would not be, which is precisely why manifest access is a v2 prerequisite rather than a nice-to-have.
- Cardinality is constrained at declaration: a topic may feed several landing tables, but a landing table fed by more than one source is rejected, because it makes the root ambiguous.
- Transform-suspected cases (a root whose monitored ancestor is clean) are rare on a three-node graph and common on the medallion. Measuring their share during the proving run is what tells us how much lineage coverage v2 actually needs.
