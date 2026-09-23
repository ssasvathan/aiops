---
status: proposed
---

# A case is keyed on either an infrastructure scope or a root dataset, merged through the source mapping

Case identity is Kafka-shaped today: `derive_case_id` builds `case-{env}-{cluster_id}-{topic}-{fingerprint}` (`pipeline/stages/casefile.py`), and the gate input requires `cluster_id` and `topic`. A DQ anomaly on a dataset with no Kafka topic behind it (e.g. an IDP-loaded table) cannot form a case at all. We extend case identity to two shapes: an infrastructure scope or a dataset. When both fire and the source mapping links them, they merge into one case.

An infrastructure scope is itself a family, matching the two source shapes ADR-0002 already names: a Kafka scope (`env`, `cluster_id`, `topic`) for the E2 path, and a job scope for an IDP feed. v1 implements the Kafka shape only (ADR-0011), but the key is defined as the family so that adding the batch path later is a new shape rather than a second kind of case. The system is greenfield, so this is a contract design choice rather than a migration, but it is the largest single contract change in the proposal.

Because data flows bronze → silver → gold → hosting, one upstream problem shows up as an anomaly in every monitored zone below it. A dataset-keyed case is therefore keyed on the root dataset, the most upstream dataset anomalous in the same window. Anomalies on datasets downstream of it along dbt lineage attach to that case as blast radius rather than opening cases of their own. The root also decides where the case goes: an infrastructure root goes to platform on-call, a dataset root to the dataset owner.

## Considered Options

- **DQ anomalies only attach to existing Kafka cases.** Rejected: a DQ failure with no accompanying infrastructure anomaly would go unreported, and those are the failures least likely to be caught any other way.
- **A separate DQ case type linked to the Kafka case.** Rejected: one incident would become two cases, the opposite of the correlation goal.
- **One case per anomalous dataset.** Rejected: a single bad bronze load would raise a case for every zone and every model below it.
- **Merge downstream anomalies by time window alone.** Rejected for the same reason as ADR-0002: unrelated datasets anomalous in the same window would merge.

## Consequences

The rule this states is narrower than the rule it implies. "Most upstream anomalous dataset" is the two-level version of *most upstream anomalous node*, where the graph is dbt lineage below the landing table and the source mapping above it. Signal from above the source — a service's CPU or memory, where one E2 application serves many topics — would extend that graph by a level and let several scope-keyed cases collapse into one service-rooted case. That is deferred with the rest of v2, but the keying decided here is the reason it can be an extension rather than a redesign.
