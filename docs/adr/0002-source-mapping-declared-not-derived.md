---
status: proposed
---

# Sources link to datasets through a source mapping, not time co-occurrence

Correlating a DQ anomaly with an infrastructure anomaly needs an entity link between a dataset (e.g. `ANALYTICS.PUBLIC.ORDERS`) and a source, and the two identities share nothing. Data enters on two paths. On the Kafka path, E2 writes a topic into its own repository and a dbt job copies it into bronze. On the batch path, IDP loads files directly into bronze. dbt's `manifest.json` covers every hop from the first dbt-visible table onward, including E2 repository → bronze. What no tool in our stack records is the hop before that: source → landing table. We keep that one hop in a source mapping and derive everything downstream from dbt lineage. For Kafka topics the mapping is declared by hand, because the OpenLineage research shows streaming ingestion emits almost no usable facets. For IDP feeds it is taken from OpenLineage where IDP's jobs emit it, and declared otherwise.

## Considered Options

- **Time co-occurrence only.** Rejected: every dataset would correlate with every lag spike in the same window, producing plausible-looking but false correlations.
- **Declared for both paths.** Viable, but it throws away lineage IDP may already be able to emit, and a hand-kept list drifts as feeds are added.
- **OpenLineage-derived lineage for both paths.** The intended long-term state, once E2 emits lineage with `kafka://` inputs. Not available today.

## Consequences

The two paths sit differently with respect to ownership. E2 is ours, so the topic → E2 repository hop is ours to declare, to keep correct as topics are added, and eventually to emit natively. Whether IDP emits OpenLineage is a fact about IDP's configuration, and IDP's owner decides whether to turn it on; the declared fallback covers IDP until they do.
