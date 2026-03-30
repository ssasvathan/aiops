# Measurability Validation

## Functional Requirements

**Total FRs Analyzed:** 20

**Format Violations:** 1
- FR17 (line ~396): "The checkpoint mechanism continues to function as the downstream deduplication safety net..." — does not follow `[Actor] can [capability]` pattern; this is a preservation/continuity constraint rather than a new capability statement.

**Subjective / Vague Quantifiers Found:** 2
- FR5 (line ~375): "weak coverage → OBSERVE" — "weak coverage" not quantified; a specific threshold (e.g., `coverage ratio < 0.3`) would be more precise.
- FR16 (line ~394): "with a safety margin" — margin not quantified in the FR text (though UAT measurement is described in Success Criteria, the FR itself is underspecified).

**Implementation Leakage:** 1
- FR6 (line ~376): References `collect_gate_inputs_by_scope` (specific method name). Brownfield context makes this borderline acceptable as a named integration point, but it is technically an implementation detail. Domain contract names (`GateInputContext`, `ActionDecisionV1`, config keys) throughout FRs are considered acceptable for this brownfield context.

**FR Violations Total:** 4

---

## Non-Functional Requirements

**Total NFRs Analyzed:** 16 (NFR-P1–P3, NFR-S1–S2, NFR-R1–R3, NFR-A1–A4, NFR-T1–T3, PG1–PG3)

**Missing / Vague Metrics:** 4
- NFR-P1 (line ~408): "adds no measurable latency" — no specific threshold stated (e.g., `< 1ms`). Also embeds implementation rationale ("pure arithmetic over...") which belongs in architecture docs, not the NFR statement itself.
- NFR-P3 (line ~410): "bounded by the configured depth per scope" — no specific memory limit stated; reads as an explanatory note rather than a testable NFR.
- NFR-A2 (line ~425): "genuinely weak evidence coverage" — "genuinely weak" is subjective. A coverage ratio threshold (e.g., `< 0.3`) would make this testable.
- NFR-A3 (line ~426): "meaningful variance" — no distribution width or statistical measure specified. A minimum standard deviation or range requirement would be testable.

**Policy Statements (Not Measurable):** 1
- NFR-S2 (line ~415): "standard env-file commit practices apply" — policy reference, not a testable requirement. Either remove or convert to a binary testable assertion.

**NFR Violations Total:** 5

---

## Overall Assessment

**Total Requirements:** 36 (20 FRs + 16 NFRs)
**Total Violations:** 9 (4 FR + 5 NFR)

**Severity:** Warning (5–10 violations)

**Recommendation:** PRD would benefit from targeted refinements. The violations are minor and do not affect core traceability or functionality. Priority fixes:
1. Quantify "weak coverage" threshold in FR5 and "safety margin" in FR16.
2. Replace NFR-P1 vagueness with a specific latency bound (e.g., `< 1ms p99`).
3. Add measurable thresholds to NFR-A2 and NFR-A3.
4. Convert NFR-S2 to a binary testable assertion or remove it.
5. Restate FR17 as a capability ("The system can maintain checkpoint deduplication...") or move to Domain Requirements as an invariant.
