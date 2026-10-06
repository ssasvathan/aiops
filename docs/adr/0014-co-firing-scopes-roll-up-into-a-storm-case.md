---
status: proposed
---

# Scopes that fire together in one cluster roll up into a single storm case

A cluster-wide E2 incident makes every topic's metric series anomalous and every landing table short at once. Under ADR-0003 alone that produces one case per scope, each merging its own dataset anomalies: hundreds of cases describing one event, arriving together, which is indistinguishable from an outage of the triage system itself. We therefore add one level above the scope key. When more than **five** scopes in the same environment and cluster fire within one correlation window, they roll up into a **storm case** keyed on `(env, cluster_id)`, and the scope-keyed cases attach as its children.

Children attach and do not notify independently; the storm case routes to platform on-call; it closes when its children have. The key is environment and cluster rather than environment alone: an incident spanning clusters is rare enough to be worth seeing as two cases.

## Considered Options

- **No rollup; rate-limit notifications instead.** Rejected: rate limiting hides cases rather than relating them, and the responder still cannot see that one event caused all of them.
- **Roll up on environment alone.** Rejected: it merges genuinely independent cluster incidents and produces a case whose root is unactionable.
- **Infer the storm from a shared upstream cause.** The better answer, and it needs signal above the source — service CPU and memory, where one E2 application serves many topics — which ADR-0003's consequences already defer to v2. The count threshold is the version available without that signal.

## Consequences

- Five is a starting number from the same family as the lead-in margin: its value comes from the proving run, not from the design.
- A storm case is the third case key, alongside infrastructure scope and root dataset, and `CONTEXT.md` records it as such.
- The storm scenario is one of the six injected failures the proving run must demonstrate (ADR-0016).
