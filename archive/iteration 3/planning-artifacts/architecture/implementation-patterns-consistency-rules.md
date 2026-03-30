# Implementation Patterns & Consistency Rules

## Pattern Categories Defined

**Critical conflict points identified:**

- Scoring helper/function naming and constant naming drift across contributors.
- Inconsistent scoring metadata shape in `decision_basis`.
- Divergent test placement and boundary-condition coverage.
- Non-deterministic fallback behavior/logging under scoring failures.

## Naming Patterns

**Code naming standards:**

- Use `snake_case` for functions, variables, and metadata keys.
- Use `UPPER_SNAKE_CASE` for constants and reason codes.
- Use deterministic private helper naming with `_score_` and `_derive_` prefixes.
- Use test naming format `test_<behavior>_<expected_outcome>`.

**Scoring-specific naming rules:**

- All scoring constants must use `SCORE_V1_` prefix.
- AG4 reason codes remain unchanged (`LOW_CONFIDENCE`, `NOT_SUSTAINED`).
- Additional scoring taxonomy appears in metadata/log fields, not contract enum changes.

## Structure Patterns

**Module organization rules:**

- Keep scoring logic in `pipeline/stages/gating.py` only.
- Keep scoring helpers private to the module.
- Do not create `scoring.py`, `gating_scoring.py`, or shared utility packages for this release.
- Keep scoring integration adjacent to `collect_gate_inputs_by_scope` flow.

**Test organization rules:**

- Stage-level scoring/gate behavior: `tests/unit/pipeline/stages/test_gating.py`
- Scheduler-level behavior: `tests/unit/pipeline/test_scheduler.py`
- Replay compatibility: `tests/unit/audit/test_decision_reproducibility.py`

## Format Patterns

**Scoring metadata format (`decision_basis`):**

- Use a flat key structure with stable `snake_case` keys.
- Keys are fixed whitelist (no ad hoc additions by individual contributors).
- Serialize keys in deterministic order when assembling payloads for hashing/replay stability.

**Recommended fixed key set:**

- `score_version`
- `base_score`
- `sustained_boost`
- `peak_boost`
- `final_score`
- `score_reason_code`
- `fallback_applied`

## Communication Patterns

**Log/event naming standards:**

- Scoring log event types must use `gating.scoring.*` prefix.
- Use deterministic reason-code semantics in logs to support audit analysis.
- Avoid introducing new outward-facing contract fields for scoring narrative data.

**State propagation pattern:**

- Scoring computes candidate `proposed_action` + `diagnosis_confidence`.
- AG0-AG6 and environment caps remain the only final action authorities.
- Downstream components consume gate outputs exactly as currently designed.

## Process Patterns

**Error handling pattern (mandatory):**

- Any scoring exception must fall back to:
  - `diagnosis_confidence = 0.0`
  - `proposed_action = OBSERVE`
  - `fallback_applied = true` metadata marker
- Emit warning-level scoring fallback log with deterministic event naming.

**Boundary-validation pattern (mandatory):**

- Explicitly test both thresholds:
  - `0.60` (AG4 floor pass boundary)
  - `0.85` (PAGE-candidate derivation boundary)

## Enforcement Guidelines

**All AI agents MUST:**

- Follow naming/structure conventions exactly (`SCORE_V1_`, `_score_`, `_derive_`, snake_case).
- Keep scoring logic module-local and deterministic.
- Preserve fallback safety behavior and deterministic metadata/logging.

**Pattern enforcement method:**

- Code review checklist includes naming-prefix verification and module-local placement verification.
- Unit tests must include boundary and fallback assertions before merge.
- Any pattern deviation must be documented in architecture artifact change notes before approval.

## Pattern Examples

**Good examples:**

- `SCORE_V1_BASE_PRESENT_WEIGHT = ...`
- `_score_evidence_base(...)`
- `_derive_proposed_action_from_score(...)`
- `decision_basis["fallback_applied"] = True`
- `event_type="gating.scoring.fallback_applied"`

**Anti-patterns:**

- `MAGIC_SCORE = 0.73` (unnamed constant)
- `def scoreConfidence(...)` (camelCase function name)
- creating `pipeline/stages/scoring.py` for this release
- nested/variable metadata shapes per contributor
- swallowing scoring exceptions without fallback marker/log
