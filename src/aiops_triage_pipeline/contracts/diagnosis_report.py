"""DiagnosisReportV1 — output of cold-path LLM diagnosis; also produced by deterministic fallback.

Valid reason_codes: LLM_UNAVAILABLE, LLM_TIMEOUT, LLM_ERROR, LLM_STUB, LLM_SCHEMA_INVALID
"""

from typing import Annotated, Literal

from pydantic import BaseModel, Field

from aiops_triage_pipeline.contracts.enums import DiagnosisConfidence


class EvidencePack(BaseModel, frozen=True):
    facts: tuple[str, ...]  # Evidence facts cited by LLM
    missing_evidence: tuple[str, ...]  # Evidence IDs/primitives missing (UNKNOWN propagation)
    matched_rules: tuple[str, ...]  # Rulebook/policy rules matched


class DiagnosisReportV1(BaseModel, frozen=True):
    schema_version: Literal["v1"] = "v1"
    case_id: str | None = None  # None in fallback scenarios
    verdict: Annotated[str, Field(min_length=1)]  # LLM verdict (or "UNKNOWN" for fallback)
    fault_domain: str | None = None  # Identified fault domain; None when UNKNOWN
    confidence: DiagnosisConfidence  # LOW/MEDIUM/HIGH
    evidence_pack: EvidencePack  # Facts, missing evidence, matched rules
    next_checks: tuple[str, ...] = ()  # Recommended follow-up checks
    gaps: tuple[str, ...] = ()  # Evidence gaps identified
    reason_codes: tuple[str, ...] = ()  # LLM_UNAVAILABLE / LLM_TIMEOUT / LLM_ERROR / LLM_STUB
    triage_hash: str | None = None  # SHA-256 of triage.json for audit hash chain
