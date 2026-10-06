---
status: proposed
---

# Cases route to the triage team until the false-positive bar is met, not to dataset owners

ADR-0007 proposes monitors applied by convention rather than opt-in, and ADR-0003 routes a dataset-rooted case to the dataset owner. Composed without care, those two decisions page a team that wrote no monitors, asked for nothing, and has no reason yet to trust a statistical detector whose false-positive rate we cannot state. That is how a detector gets muted, and a muted detector is worse than none because it is believed to be working. We therefore separate detection coverage from routing: during the proving run and until the false-positive bar is met, every case routes to the triage team, who disposition it and hand off by hand. Routing to dataset owners is a later step, gated on evidence rather than on the pipeline being finished.

The bar is a sustained rate of no more than one **wrong** case per dataset per week, measured at Gate 2 (ADR-0016). "Wrong" is one of three dispositions a human records on every case: **actionable** (a real problem someone had to fix), **benign-real** (the measurement was genuinely anomalous and no action was needed, such as a legitimate business spike) and **wrong** (the measurement was not anomalous). The bar applies to *wrong* alone. A high benign-real rate is a different defect with a different remedy — more context and better severity, not lower sensitivity — and collapsing the two into a single pass/fail disposition would push us to detune a detector that is working.

Merged cases have one owner and one lifecycle. The root decides the owner (ADR-0003); closure is governed by the series recovering (ADR-0009), never by an owner's opinion that their half looks fine.

## Considered Options

- **Route to dataset owners from day one.** Rejected: it spends the owners' goodwill at exactly the moment we have the least evidence, and first impressions of an alerting system are difficult to revise.
- **Route nothing anywhere and read a dashboard.** Rejected: nobody dispositions a dashboard, and disposition counts are the evidence the whole proving run exists to produce.
- **Two-way disposition (true/false positive).** Rejected: it hides the benign-real class, which is the one most likely to be large early and the one least improved by changing thresholds.

## Consequences

- Disposition is recurring human cost: one named person, one pass a day, for the duration. It is scope, not overhead, and it is the instrument that produces the go/no-go evidence.
- It needs somewhere to record the verdict. The smallest thing that works is a disposition field on the case written by a one-command CLI, with counts surfaced on the existing dashboard. Not a UI, not a workflow tool, not an incident-system integration: those are earned later.
- Owner routing becomes a discrete later decision with a named trigger, which is also the moment dataset owners need to be told the system exists.
