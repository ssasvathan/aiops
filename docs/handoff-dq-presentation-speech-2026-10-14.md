# Handoff: prepare the spoken delivery for the DQ anomaly detection walkthrough

**Date:** 2026-10-14
**Repo:** `/home/sas/workspace/aiops`
**Branch:** `docs/dq-anomaly-proposal` (main branch is `main`)
**Next session's focus:** preparing the presentation *speech* — what the presenter actually says while driving the page. The artifact itself is essentially done; the spoken layer does not exist yet.

## What this work is

A proposal to add data-quality anomaly detection as a second signal kind on an existing
anomaly-detection substrate. The deliverable is a buy-in architecture document plus a
walkthrough page for a review with one distinguished engineer. Nothing is in production;
nothing is being built yet. The ask in the review is **direction only**.

Read these, in this order, before doing anything:

1. `docs/presentation/README.md` — the constraints the page was designed against (audience, duration, what the DE does and does not know). These constraints govern the speech too.
2. `docs/presentation/index.html` — the page itself. Open in a browser, no build step. This is what will be on the shared screen.
3. `docs/proposal-dq-anomaly-detection-2026-09-22.md` — source of truth. If the page and the proposal disagree, the proposal wins.
4. `docs/adr/` — nineteen ADRs, `0001`–`0019`. The page indexes them in appendix J and never inlines their content.

Supporting research, referenced rather than summarised here:
`docs/research-dbt-elementary-selection-2026-10-02.md` (answers the three Gate 1 checks ADR-0018 defers),
`docs/research-snowflake-cortex-dq-anomaly-detection-2026-09-21.md`,
`docs/research-elementary-operations-2026-09-22.md`,
`docs/research-medallion-path-facts-2026-09-22.md`,
`docs/research-manual-openlineage-emission-2026-09-22.md`,
`docs/research-clickhouse-metrics-and-openlineage-storage-2026-09-07.md`,
`docs/openlineage-data-quality-facets-research.md`.

## Current state of the page

Eight main sections, then a flat appendix of ten jump targets (A–J). Section order and the
kicker line above each heading:

| # | Kicker | Heading |
|---|---|---|
| s1 | Where we are | What exists, and what it cannot see |
| s2 | The destination | What one case looks like |
| s3 | The one structural change | Data quality becomes a second signal kind on the substrate we already have |
| s4 | Where the difficulty is | The hard parts |
| s5 | The candidates | Options for data-quality detection |
| s6 | The occupant | What fills the slot in v1 |
| s7 | v1 | A proving run on a path we own end to end |
| s8 | Where we are going | Where this goes |

Appendix: A What we do not know yet · B The seam in full (ADR-0001) · C What it costs ·
D C vs A in full · E What the pipeline may read · F Who gets paged · G Not OpenLineage,
not Cortex · H Verdict egress · I Requests of other platforms · J The nineteen ADRs.

### Uncommitted change on disk

`docs/presentation/index.html` is modified (48 insertions, 48 deletions) and not committed. Two things:

- "What we do not know yet" moved out of the main flow into appendix A, and "Where this goes" was promoted from appendix A into section 8. The main flow now ends on the destination rather than on open questions.
- Em dashes inside the mermaid subgraph labels and the following paragraph were replaced with commas, per the documentation style rule in `AGENTS.md`.

Decide with the user whether to commit this before or after the speech work.

### `README.md` is stale

It still describes the earlier ten-section shape (with "The ask", "The problem", "The
correlation problem", "Elementary" as separate numbered sections) and says sixteen ADRs
where there are now nineteen. The *constraints* and *appendix policy* parts of that README
are still accurate and still binding; the "Shape" section is not. Worth fixing, but do not
let it displace the speech work unless the user asks.

## What the next session needs to produce

No speaker notes, script, or timing plan exists anywhere in the repo. That is the gap.
Likely shape of the deliverable, to confirm with the user:

- An opening that establishes the ask (direction, not ratification) in under a minute, given a cold audience who has not read the proposal.
- Per-section spoken beats, with the explicit decision of what is said aloud versus left on the screen to be read. The page was written to do the heavy lifting, so reading it out loud is the failure mode.
- A timing budget. The review is ~30 minutes with Q&A eating into it, so the main flow has to land in meaningfully less than that.
- A navigation plan: which appendices to jump to on which question. Section 3 is deliberately one claim rather than an argument, and the argument lives in appendix B; the speech has to handle that handoff if the DE pushes.
- Anticipated-question drill, especially: whether Elementary's z-score is good enough, running cost, monitoring coverage, where the lead-in margin sits, and the organisational ask of the dbt platform team. All five are named in appendix A.

## Constraints to carry over

- **Tone and prose:** `AGENTS.md` has a documentation style guide. It governs anything written into the repo. Plain complete sentences, no em dashes, no announcing that something matters, no quotable one-liners, no habitual grouping in threes. Spoken delivery notes should follow the same spirit.
- The committed evidence thresholds are shown as already decided, so the DE can reject one quickly without being asked to endorse the set. Do not reopen them in the speech.
- The page never explains E2. The presenter handles that conversation separately.
- Elementary is the one genuinely new thing to the audience and gets a full section. Nothing else new does.
- Keep the speech material out of `docs/presentation/index.html` if it would show on the shared screen. Ask the user where they want it (a separate markdown file next to the page is the obvious choice, or hidden speaker notes in the page).

## Suggested skills

Call the Skill tool for these:

- **`bmad-cis-agent-storyteller`** — narrative framing for the spoken arc, if the user wants the speech structured deliberately rather than section by section. (Triggered by asking for Sophia / the Master Storyteller.)
- **`bmad-cis-agent-presentation-master`** — presentation and visual-storytelling expertise, for decisions about what the screen does while the presenter talks. (Triggered by asking for Caravaggio / the Presentation Expert.)
- **`grill-me`** or **`grilling`** — to rehearse the Q&A. This is the highest-value one here: the review's whole purpose is a distinguished engineer stress-testing the direction, so being grilled on the proposal before the real thing is direct practice.
- **`writing-beats`** — if the speech is drafted as written prose, for assembling it into beats that ground each term before leaning on it. Relevant because the audience is cold.
- **`bmad-editorial-review-prose`** — a copy-edit pass on any prose committed to the repo, against the `AGENTS.md` style rules.

## Housekeeping

- This repo has a test suite, but nothing in this work touches code. If a full run is ever needed, `AGENTS.md` has the Docker-enabled command and a zero-skips quality gate.
- Commit attribution lines for this project are supplied by the session environment; follow whatever the next session's instructions specify.
