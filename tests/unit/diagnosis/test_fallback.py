"""Unit tests for diagnosis/fallback.py — build_fallback_report()."""

import pytest
from pydantic import ValidationError

from aiops_triage_pipeline.contracts.diagnosis_report import DiagnosisReportV1, EvidencePack
from aiops_triage_pipeline.contracts.enums import DiagnosisConfidence
from aiops_triage_pipeline.diagnosis.fallback import build_fallback_report


def test_build_fallback_report_stub_defaults() -> None:
    """build_fallback_report with LLM_STUB returns correct schema with case_id=None."""
    report = build_fallback_report(("LLM_STUB",))

    assert isinstance(report, DiagnosisReportV1)
    assert report.schema_version == "v1"
    assert report.verdict == "UNKNOWN"
    assert report.confidence == DiagnosisConfidence.LOW
    assert report.reason_codes == ("LLM_STUB",)
    assert report.case_id is None
    assert report.fault_domain is None
    assert report.triage_hash is None


def test_build_fallback_report_case_id_propagated() -> None:
    """build_fallback_report sets case_id when provided."""
    report = build_fallback_report(("LLM_TIMEOUT",), case_id="case-123")

    assert report.case_id == "case-123"
    assert report.reason_codes == ("LLM_TIMEOUT",)
    assert report.verdict == "UNKNOWN"
    assert report.confidence == DiagnosisConfidence.LOW


def test_build_fallback_report_unavailable() -> None:
    """build_fallback_report with LLM_UNAVAILABLE returns correct fields."""
    report = build_fallback_report(("LLM_UNAVAILABLE",))

    assert report.reason_codes == ("LLM_UNAVAILABLE",)
    assert report.verdict == "UNKNOWN"
    assert report.confidence == DiagnosisConfidence.LOW
    assert report.case_id is None


def test_build_fallback_report_schema_invalid() -> None:
    """build_fallback_report with LLM_SCHEMA_INVALID returns correct fields."""
    report = build_fallback_report(("LLM_SCHEMA_INVALID",))

    assert report.reason_codes == ("LLM_SCHEMA_INVALID",)
    assert report.verdict == "UNKNOWN"
    assert report.confidence == DiagnosisConfidence.LOW


def test_build_fallback_report_error() -> None:
    """build_fallback_report with LLM_ERROR returns correct fields."""
    report = build_fallback_report(("LLM_ERROR",))

    assert report.reason_codes == ("LLM_ERROR",)
    assert report.verdict == "UNKNOWN"
    assert report.confidence == DiagnosisConfidence.LOW


def test_build_fallback_report_frozen_mutation_raises() -> None:
    """DiagnosisReportV1 is frozen — mutation must raise ValidationError or TypeError."""
    report = build_fallback_report(("LLM_STUB",))

    with pytest.raises((ValidationError, TypeError)):
        report.verdict = "CHANGED"  # type: ignore[misc]


def test_build_fallback_report_evidence_pack_empty() -> None:
    """build_fallback_report returns EvidencePack with all empty tuples."""
    report = build_fallback_report(("LLM_STUB",))

    assert isinstance(report.evidence_pack, EvidencePack)
    assert report.evidence_pack.facts == ()
    assert report.evidence_pack.missing_evidence == ()
    assert report.evidence_pack.matched_rules == ()


# ---------------------------------------------------------------------------
# BASELINE_DEVIATION — AC 4 verification tests
# ---------------------------------------------------------------------------


def test_build_fallback_report_baseline_deviation_timeout() -> None:
    """BASELINE_DEVIATION case with LLM_TIMEOUT returns UNKNOWN/LOW with triage_hash=None."""
    report = build_fallback_report(("LLM_TIMEOUT",), case_id="bd-case-001")

    assert isinstance(report, DiagnosisReportV1)
    assert report.verdict == "UNKNOWN"
    assert report.confidence == DiagnosisConfidence.LOW
    assert report.reason_codes == ("LLM_TIMEOUT",)
    assert report.case_id == "bd-case-001"
    assert report.triage_hash is None
    assert report.fault_domain is None
    # Round-trip schema validity
    DiagnosisReportV1.model_validate(report.model_dump(mode="json"))


def test_build_fallback_report_baseline_deviation_unavailable() -> None:
    """BASELINE_DEVIATION case with LLM_UNAVAILABLE returns correct schema (no case_id)."""
    report = build_fallback_report(("LLM_UNAVAILABLE",))

    assert isinstance(report, DiagnosisReportV1)
    assert report.verdict == "UNKNOWN"
    assert report.confidence == DiagnosisConfidence.LOW
    assert report.reason_codes == ("LLM_UNAVAILABLE",)
    assert report.case_id is None
    assert report.triage_hash is None
    assert report.fault_domain is None
    # Round-trip schema validity
    DiagnosisReportV1.model_validate(report.model_dump(mode="json"))


def test_build_fallback_report_baseline_deviation_error() -> None:
    """BASELINE_DEVIATION case with LLM_ERROR returns correct schema."""
    report = build_fallback_report(("LLM_ERROR",))

    assert isinstance(report, DiagnosisReportV1)
    assert report.verdict == "UNKNOWN"
    assert report.confidence == DiagnosisConfidence.LOW
    assert report.reason_codes == ("LLM_ERROR",)
    assert report.case_id is None
    assert report.triage_hash is None
    assert report.fault_domain is None
    # Round-trip schema validity
    DiagnosisReportV1.model_validate(report.model_dump(mode="json"))
