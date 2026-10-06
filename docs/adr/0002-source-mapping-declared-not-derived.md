---
status: proposed
---

# Sources link to datasets through a source mapping, not time co-occurrence

Correlating a DQ anomaly with an infrastructure anomaly needs an entity link between a dataset (e.g. `E2.RAW.ORDERS`) and a source, and the two identities share nothing. Data enters on two paths. On the Kafka path, E2 writes a topic into its own repository. On the batch path, IDP loads files directly into bronze. No tool in our stack records the hop from a source to the table its data first lands in, and none is likely to: the OpenLineage research shows streaming ingestion emits almost no usable facets (ADR-0004). We declare that hop in a source mapping.

We originally intended to declare only that one hop and derive everything below it from dbt's `manifest.json`. Those manifests are not available to us, so the graph is declared end to end instead (ADR-0015). That does not change this decision — it widens it. The source mapping remains the link between source identity and dataset identity, and it is the edge on which a metric finding and a measurement finding become one case.

Cardinality is constrained where the mapping is declared: a topic may feed several landing tables, but a landing table fed by more than one source is rejected, because two sources make the root of a dataset-keyed case ambiguous and there is no evidence in the data to break the tie.

## Considered Options

- **Time co-occurrence only.** Rejected: every dataset would correlate with every lag spike in the same window, producing plausible-looking but false correlations.
- **Derive the hop from dbt lineage.** Not possible: dbt lineage begins at the first dbt-visible table, which is the landing table itself.
- **OpenLineage-derived lineage for both paths.** The intended long-term state, once E2 emits lineage with `kafka://` inputs. Not available today.

## Consequences

The two paths sit differently with respect to ownership. E2 is ours, so the topic → landing table hop is ours to declare, to keep correct as topics are added, and eventually to emit natively. Whether IDP emits OpenLineage is a fact about IDP's configuration, and IDP's owner decides whether to turn it on; the declared fallback covers IDP until they do.
