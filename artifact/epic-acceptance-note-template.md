# Epic {{epic_number}} Acceptance Note — {{epic_title}}

- Date: {{date}}
- Product Owner: {{product_owner}}
- Epic status at closure: done
- Stories delivered: {{n}}/{{n}}

## 1) Epic Goal and Scope

{{one-paragraph summary of what the epic set out to achieve and for whom}}

**FRs delivered:** {{FR list}}
**PRD CRs addressed:** {{CR list with short signal description}}

## 2) Story-Level Acceptance Verification

| Story | AC Status | Quality Evidence |
|---|---|---|
| {{story_id}}: {{story_title}} | ✅ All AC met | {{test count}}, 0 skipped, ruff clean |

## 3) Rollout Acceptance Signals

What an operator must observe to confirm the epic is behaving correctly in a target environment:

- [ ] {{observable signal 1 — e.g., specific metric emitted, log message, health endpoint}}
- [ ] {{observable signal 2}}
- [ ] {{observable signal 3}}

## 4) Rollback Acceptance Signals

What reverting this epic's changes looks like and how to verify the revert is clean:

- [ ] {{flag / config change to revert}}
- [ ] {{verification step — e.g., no coordination keys written to Redis after a full cycle}}
- [ ] {{regression check}}

## 5) Known Limitations and Deferred Items

| Item | Severity | Deferred to |
|---|---|---|
| {{description}} | Low/Medium/High | Epic {{n}} / Backlog |

_None_ if there are no known limitations.

## 6) Product Owner Sign-Off

> {{acceptance statement — e.g., "Epic N delivered its stated goals. Acceptance criteria were met for all stories. Rollout is safe to proceed with the activation sequence documented in deployment-guide.md."}}
>
> — {{product_owner}}, {{date}}
