---
status: proposed
---

# A case is keyed on an infrastructure scope, a root dataset, or a storm, merged through the source mapping

A DQ anomaly on a dataset must be able to form a case whether or not anything infrastructural fired, and a case must be able to span both signal kinds when they describe one event. Case identity therefore has three shapes: an **infrastructure scope**, a **root dataset**, and — above both — a **storm** keyed on an environment and cluster, for the case where many scopes fire at once (ADR-0014). When a scope and a dataset both fire and the source mapping links them, they merge into one case.

An infrastructure scope is itself a family, matching the two source shapes ADR-0002 names: a Kafka scope (`env`, `cluster_id`, `topic`) for the E2 path, and a job scope for an IDP feed. v1 implements the Kafka shape only (ADR-0011), but the key is defined as the family so that adding the batch path later is a new shape rather than a second kind of case. The system is greenfield, so all of this is contract design rather than migration.

Because data flows downstream, one upstream problem shows up as an anomaly in every monitored dataset below it. A dataset-keyed case is therefore keyed on the **root dataset**: the most upstream *monitored* dataset anomalous in the same window, over the declared graph (ADR-0015). Anomalies on datasets downstream of it attach to that case as blast radius rather than opening cases of their own. The root also decides where a case is eventually routed — an infrastructure root to platform on-call, a dataset root to the dataset owner — though during the proving run every case routes to the triage team regardless (ADR-0012).

Monitoring coverage is therefore a determinant of routing accuracy, and the glossary says so. A defect introduced in an unmonitored part of the graph surfaces as a root further downstream than its true cause. Where a case's root has a monitored ancestor that is *not* anomalous, the case is marked **transform-suspected** and is not attributed to the root's owner; the share of such cases is a proving-run measure (ADR-0016), because it is the evidence for how much lineage coverage v2 needs.

## Considered Options

- **DQ anomalies only attach to existing Kafka cases.** Rejected: a DQ failure with no accompanying infrastructure anomaly would go unreported, and those are the failures least likely to be caught any other way.
- **A separate DQ case type linked to the Kafka case.** Rejected: one incident would become two cases, the opposite of the correlation goal.
- **One case per anomalous dataset.** Rejected: a single bad load would raise a case for every dataset below it.
- **Merge downstream anomalies by time window alone.** Rejected for the same reason as ADR-0002: unrelated datasets anomalous in the same window would merge.

## Consequences

The rule this states is narrower than the rule it implies. "Most upstream anomalous dataset" is the restricted version of *most upstream anomalous node*, in a graph whose nodes are sources and datasets. Signal from above the source — a service's CPU or memory, where one E2 application serves many topics — extends that graph by a level and would let several scope-keyed cases collapse into one service-rooted case, replacing the count threshold that defines a storm today. That is deferred with the rest of v2, but the keying decided here is the reason it can be an extension rather than a redesign.
