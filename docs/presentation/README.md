# Presentation: DQ anomaly detection

A walkthrough page for reviewing `docs/proposal-dq-anomaly-detection-2026-09-22.md`
with a distinguished engineer. Open `index.html` in a browser; no build step.

## What this is built for

Decided by interview on 2026-09-23. These constraints explain every choice below,
so re-read them before changing the page.

- **Audience: one DE.** Not a room. Driven on a shared screen as a conversation,
  which is why this is a scrolling walkthrough and not a slide deck.
- **Cold.** He will not have read the proposal. The page does the heavy lifting.
- **~30 minutes**, with Q&A eating into it.
- **The ask is direction only.** Not ratification of the evidence bar. The
  committed thresholds are *shown as already made*, so he can say "that one's
  wrong" in sixty seconds without being asked to sign the set.
- **What he knows:** E2 by name (not in detail — the presenter manages that
  conversation separately, so the page never explains E2), and the baseline
  detector only vaguely.
- **What he doesn't know:** Elementary. It gets a full section; nothing else new does.

## Shape

Ten main sections, then a flat appendix of jump targets.

1. The ask · 2. The problem · 3. The correlation problem · 4. What one case looks
like · 5. Elementary · 6. The proving run · 7. The seam · 8. The three hard things
· 9. C now, A as the target · 10. How we would know it worked

**Section 4 is not in the proposal.** It walks scenario 1 concretely. A cold
reader needs to see the destination before the mechanism.

**Section 7 is deliberately one claim, not an argument.** ADR-0001 is load-bearing
for the direction being approved, so it cannot be absent — but a DE with a vague
picture of the detector will not productively review the reframing in five
minutes, and trying would cost section 10. The argument lives in appendix B.

## Appendix policy

Appendix sections exist for questions that are *known* to be coming, plus an index
of all 16 ADRs. ADR content is never inlined — the markdown is the source of truth
and a second copy would rot.

The medallion diagram is in appendix A, not inline, and section 1 points at it
explicitly. He will ask where this goes; answering on demand is stronger than
pre-empting, and it protects the v1 scope.

## Maintenance

The mermaid diagrams are copied verbatim from the proposal's fenced blocks. When
an ADR changes, update the proposal first, then re-copy. Everything else is prose
derived from the proposal — if the two disagree, the proposal wins.

`CONTEXT.md` is a domain glossary and deliberately holds none of this.
