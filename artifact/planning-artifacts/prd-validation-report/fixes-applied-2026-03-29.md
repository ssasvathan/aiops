# Fixes Applied — 2026-03-29

All validation findings addressed. The following changes were made to `artifact/planning-artifacts/prd.md`:

## FR Fixes

| FR | Change |
|---|---|
| FR5 | Replaced "weak coverage → OBSERVE" with specific condition: "insufficient evidence coverage that cannot produce `diagnosis_confidence >= 0.6` without tier amplifiers → OBSERVE" |
| FR16 | Quantified "safety margin" → "minimum safety margin of 30 seconds above measured p95 (e.g., UAT-measured p95 of 47s → TTL of 90s or greater)" |
| FR17 | Restated as system capability: "The system can suppress duplicate scope processing effects through the checkpoint deduplication mechanism…" |

## NFR Fixes

| NFR | Change |
|---|---|
| NFR-P1 | Replaced "no measurable latency" + implementation rationale → "< 1ms p99 latency per scoring invocation" |
| NFR-P3 | Replaced "expected and bounded by configured depth" → testable: "must not cause heap exhaustion or OOM errors under normal operating scope load" |
| NFR-S2 | Replaced policy statement → testable assertion: "must contain no secrets, credentials, or sensitive data — safe to store in version-controlled env-files" |
| NFR-A2 | Replaced "genuinely weak evidence coverage" → testable: "at least one record must carry a non-`LOW_CONFIDENCE` reason code in UAT audit records" |
| NFR-A3 | Replaced "meaningful variance" → measurable: "standard deviation < 0.05 in `diagnosis_confidence` across first 100 scored events indicates regression" |

## Structural Fix

- **Project Scoping & Phased Development**: Removed duplicated "MVP Feature Set (This Release)" and "Post-MVP Features" subsections (both repeated content already present in **Product Scope**). Section now contains only MVP Strategy & Philosophy and Risk Mitigation Strategy, eliminating ambiguity about which section is authoritative for epic/story generation.

## Frontmatter Fix

- Added `date: '2026-03-28'` to PRD frontmatter (was only present in document body)

**Post-fix assessment:** All validation findings resolved. PRD is ready for downstream artifact generation.
