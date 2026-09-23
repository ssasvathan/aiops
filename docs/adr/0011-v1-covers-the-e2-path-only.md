---
status: proposed
---

# v1 covers the E2 path only, from topic to hosting

v1 monitors datasets fed by E2, the Kafka ingestion platform we own, and follows them from the E2 repository through bronze to the hosting zone. We own the topics, the repository tables and their load timestamps, and the Kafka metric series on the other side of the correlation, so the whole loop can be proved without waiting on another team. The IDP batch path is deliberately left for v2: every ingredient it needs (job metrics, OpenLineage, load timestamps) is a request to IDP's owners, and none of them is needed to show the idea works.

This trades breadth for speed. The reviewer will reasonably ask why the pilot skips half the ingestion landscape, and the answer is that the design already covers it: the source mapping (ADR-0002) is path-agnostic, case identity is keyed on datasets rather than Kafka scopes (ADR-0003), and the IDP requests are written up with their fallbacks. What v1 does not do is prove the batch half in practice.

## Considered Options

- **A pilot spanning both ingestion paths.** Rejected for v1: it makes first delivery depend on another team's yes, and the weakest part of the batch story (correlating a DQ anomaly with Airflow/Spark job signal) is also the slowest to arrange.
- **Everything the platform default touches.** Rejected: the cold start means roughly two weeks before anything is useful and fourteen before seasonal comparison works, so a wide launch spends warehouse credit on datasets before there is any evidence the verdicts are worth acting on.

## Consequences

- The v1 correlation story is the one we can demonstrate end to end: consumer lag or throughput trouble on a topic, and a volume or null-rate anomaly on the bronze table it lands in, in one case.
- Monitors still have to be declared in dbt projects owned by data owners, so ADR-0007's platform default remains the one live cross-team ask in v1, with "monitor bronze sources and hosting ourselves" as its fallback.
- The IDP requests move from prerequisites to v2 preparation, which is a better position to ask from: the ask arrives with a working system behind it.
