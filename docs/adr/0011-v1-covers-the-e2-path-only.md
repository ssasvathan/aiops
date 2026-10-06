---
status: proposed
---

# v1 is a proving run on the E2 path, from topic to consumer table, inside E2's own Snowflake space

E2 does not sit in the medallion architecture. It owns a repository outside the datahub, and its Snowflake space holds the tables its data lands in and the tables it exposes for reading. v1 runs entirely there: a Kafka topic, the **landing table** it is written to, and the **consumer table** built from it — three nodes, all ours, mimicking inside E2's space the downstream movement the medallion performs at larger scale. We own the topics, the tables, their load timestamps, and the Kafka metric series on the other side of the correlation, so the whole loop can be proved without waiting on any other team.

**Neither hop is a daily batch.** The topic streams into the landing table continuously, and a separate job copies the landing table into the consumer table every 15 minutes. The path therefore carries two cadences rather than one, and neither is the once-a-day shape the first draft assumed: the load cadence is no longer the dominant term in detection latency, and bucket width rather than load cadence sets the smallest shortfall we can see (ADR-0008).

Monitors run from our own minimal dbt project, which declares those tables as **sources** and builds no models. Sources are also the materialisation Elementary's bucket reuse actually supports, so this is not only the cheapest path politically but the cheapest one to run. It needs a Snowflake role and a warehouse, not the platform team's agreement (ADR-0007).

Because no downstream consumer reads the consumer table, this is a **proving run**, not a pilot, and it is judged accordingly (ADR-0016): it can prove mechanism, cost, correlation and false-positive behaviour, and it explicitly cannot prove that incidents were caught before a consumer reported them. Saying so is the difference between evidence and assertion.

The medallion path and the IDP batch path are both v2. Every ingredient IDP needs — job metrics, OpenLineage emission, load timestamps on bronze — is a request to its owners, and the medallion additionally needs dbt manifests we do not have (ADR-0015). None of it is needed to show the idea works.

## Considered Options

- **A proving run spanning the medallion zones.** Rejected: it needs manifest access for lineage and monitors inside tenants we do not own, making first delivery depend on two other teams' yes.
- **A proving run spanning both ingestion paths.** Rejected for v1: the weakest part of the batch story, correlating a DQ anomaly with Airflow and Spark job signal, is also the slowest to arrange.
- **Wait for a path with real consumers.** Rejected: it trades months of delay for one metric, when the three measures that actually decide the design are all available here.

## Consequences

- The demonstrable correlation story is consumer lag or throughput trouble on a topic, and a volume or null-rate anomaly on the landing table it feeds, in one case.
- The declared graph is three nodes, so root and blast radius are exercised but not stressed. The medallion is where they are stressed, and where manifest access becomes a prerequisite rather than a nice-to-have.
- The requests of other platforms move from prerequisites to v2 preparation, which is a better position to ask from: the ask arrives with a working system behind it.
