"""Deterministic fallback report builder for cold-path LLM failure scenarios."""

from aiops_triage_pipeline.contracts.diagnosis_report import DiagnosisReportV1, EvidencePack
from aiops_triage_pipeline.contracts.enums import DiagnosisConfidence


def build_fallback_report(
    reason_codes: tuple[str, ...],
    case_id: str | None = None,
) -> DiagnosisReportV1:
    """Build a deterministic fallback DiagnosisReportV1 for LLM failure scenarios.

    Used by LLMClient in MOCK mode and all failure-injection scenarios.
    triage_hash is intentionally None — hash chain populated in Story 6.3.
    """
    return DiagnosisReportV1(
        case_id=case_id,
        verdict="UNKNOWN",
        fault_domain=None,
        confidence=DiagnosisConfidence.LOW,
        evidence_pack=EvidencePack(facts=(), missing_evidence=(), matched_rules=()),
        next_checks=(),
        gaps=(),
        reason_codes=reason_codes,
        triage_hash=None,
    )
