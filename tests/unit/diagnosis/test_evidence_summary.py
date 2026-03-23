"""Unit tests for diagnosis/evidence_summary.py — TDD RED PHASE.

These tests will FAIL until the production module
``src/aiops_triage_pipeline/diagnosis/evidence_summary.py`` is implemented
(Story 3.2, AC2).

Test IDs follow: 3.2-UNIT-{seq} (continuation from test_context_retrieval.py)
"""

from __future__ import annotations

from datetime import UTC, datetime

from aiops_triage_pipeline.contracts.enums import (
    CriticalityTier,
    Environment,
    EvidenceStatus,
)
from aiops_triage_pipeline.contracts.gate_input import Finding
from aiops_triage_pipeline.contracts.triage_excerpt import TriageExcerptV1

# ---------------------------------------------------------------------------
# RED PHASE — module does not exist yet; collected tests will fail with ImportError
# ---------------------------------------------------------------------------
_IMPORT_ERROR: ImportError | None = None
try:
    from aiops_triage_pipeline.diagnosis.evidence_summary import build_evidence_summary
except ImportError as _err:
    _IMPORT_ERROR = _err
    _IMPORT_ERROR_MSG = str(_err)

    def build_evidence_summary(triage_excerpt):  # type: ignore[misc]  # noqa: F811
        raise ImportError(
            "aiops_triage_pipeline.diagnosis.evidence_summary not implemented yet "
            f"(Story 3.2 RED phase): {_IMPORT_ERROR_MSG}"
        )

# ---------------------------------------------------------------------------
# Test data helpers
# ---------------------------------------------------------------------------

_TRIAGE_TIMESTAMP = datetime(2026, 3, 22, 18, 0, 0, tzinfo=UTC)


def _make_finding(
    finding_id: str = "f-lag-001",
    name: str = "CONSUMER_LAG_SUSTAINED",
    severity: str = "HIGH",
    is_anomalous: bool = True,
    is_primary: bool = True,
    evidence_required: tuple[str, ...] = ("consumer_lag_max",),
    reason_codes: tuple[str, ...] = ("lag_exceeds_threshold", "sustained_condition"),
) -> Finding:
    return Finding(
        finding_id=finding_id,
        name=name,
        is_anomalous=is_anomalous,
        evidence_required=evidence_required,
        is_primary=is_primary,
        severity=severity,
        reason_codes=reason_codes,
    )


def _make_full_excerpt(
    evidence_status_map: dict[str, EvidenceStatus] | None = None,
    findings: tuple[Finding, ...] | None = None,
    sustained: bool = True,
    peak: bool | None = True,
) -> TriageExcerptV1:
    """Build a TriageExcerptV1 with all four EvidenceStatus variants."""
    if evidence_status_map is None:
        evidence_status_map = {
            "consumer_lag_max": EvidenceStatus.PRESENT,
            "consumer_lag_avg": EvidenceStatus.UNKNOWN,
            "topic_offset_delta": EvidenceStatus.ABSENT,
            "producer_rate": EvidenceStatus.STALE,
        }
    if findings is None:
        findings = (_make_finding(),)
    return TriageExcerptV1(
        case_id="case-prod-cluster-a-payments-lag-001",
        env=Environment.PROD,
        cluster_id="cluster-a",
        stream_id="stream-payments",
        topic="payments.events",
        anomaly_family="CONSUMER_LAG",
        topic_role="SOURCE_TOPIC",
        criticality_tier=CriticalityTier.TIER_0,
        routing_key="OWN::Streaming::Payments",
        sustained=sustained,
        peak=peak,
        evidence_status_map=evidence_status_map,
        findings=findings,
        triage_timestamp=_TRIAGE_TIMESTAMP,
    )


# ---------------------------------------------------------------------------
# 3.2-UNIT-101: Return type and basic structure
# ---------------------------------------------------------------------------


class TestBuildEvidenceSummaryReturnType:
    """AC2: build_evidence_summary must return a non-empty string."""

    def test_returns_string(self) -> None:
        """3.2-UNIT-101: build_evidence_summary returns a str."""
        excerpt = _make_full_excerpt()

        result = build_evidence_summary(excerpt)

        assert isinstance(result, str)

    def test_returns_non_empty_string(self) -> None:
        """3.2-UNIT-102: Output is not empty."""
        excerpt = _make_full_excerpt()

        result = build_evidence_summary(excerpt)

        assert len(result) > 0


# ---------------------------------------------------------------------------
# 3.2-UNIT-103: Byte-stability (determinism)
# ---------------------------------------------------------------------------


class TestBuildEvidenceSummaryByteStability:
    """AC2: Identical inputs must produce byte-identical outputs across calls."""

    def test_same_input_produces_identical_output_across_two_calls(self) -> None:
        """3.2-UNIT-103: Two calls with identical excerpt produce identical strings."""
        excerpt = _make_full_excerpt()

        result_a = build_evidence_summary(excerpt)
        result_b = build_evidence_summary(excerpt)

        assert result_a == result_b

    def test_different_dict_insertion_order_produces_identical_output(self) -> None:
        """3.2-UNIT-104: Dict insertion order must NOT affect output (keys sorted)."""
        # Two excerpts with same data but different dict key insertion orders
        excerpt_order_a = _make_full_excerpt(
            evidence_status_map={
                "consumer_lag_max": EvidenceStatus.PRESENT,
                "consumer_lag_avg": EvidenceStatus.UNKNOWN,
                "topic_offset_delta": EvidenceStatus.ABSENT,
                "producer_rate": EvidenceStatus.STALE,
            }
        )
        excerpt_order_b = _make_full_excerpt(
            evidence_status_map={
                "producer_rate": EvidenceStatus.STALE,
                "topic_offset_delta": EvidenceStatus.ABSENT,
                "consumer_lag_avg": EvidenceStatus.UNKNOWN,
                "consumer_lag_max": EvidenceStatus.PRESENT,
            }
        )

        result_a = build_evidence_summary(excerpt_order_a)
        result_b = build_evidence_summary(excerpt_order_b)

        assert result_a == result_b

    def test_findings_order_does_not_affect_output(self) -> None:
        """3.2-UNIT-105: Findings are sorted by finding_id before rendering."""
        finding_x = _make_finding(finding_id="f-zzz", name="FINDING_ZZZ")
        finding_a = _make_finding(finding_id="f-aaa", name="FINDING_AAA")

        excerpt_order_1 = _make_full_excerpt(findings=(finding_x, finding_a))
        excerpt_order_2 = _make_full_excerpt(findings=(finding_a, finding_x))

        result_1 = build_evidence_summary(excerpt_order_1)
        result_2 = build_evidence_summary(excerpt_order_2)

        assert result_1 == result_2

    def test_no_timestamp_in_output(self) -> None:
        """3.2-UNIT-106: Output must contain no timestamps (non-determinism source)."""
        excerpt = _make_full_excerpt()

        result = build_evidence_summary(excerpt)

        # No ISO datetime patterns like 2026-03-22
        assert "2026" not in result, (
            "Output must not contain timestamps (breaks byte-stability guarantee)"
        )

    def test_no_random_elements_in_output(self) -> None:
        """3.2-UNIT-107: Repeated calls must produce identical output (no random elements)."""
        excerpt = _make_full_excerpt()
        results = [build_evidence_summary(excerpt) for _ in range(5)]

        assert len(set(results)) == 1, (
            "All 5 calls must produce the same output (no randomness)"
        )


# ---------------------------------------------------------------------------
# 3.2-UNIT-108: Section presence — fixed section order
# ---------------------------------------------------------------------------


class TestBuildEvidenceSummarySections:
    """AC2: Output must contain all required sections in fixed order."""

    def test_case_context_section_present(self) -> None:
        """3.2-UNIT-108: Output contains a 'Case Context' section."""
        excerpt = _make_full_excerpt()

        result = build_evidence_summary(excerpt)

        assert "Case Context" in result

    def test_evidence_status_section_present(self) -> None:
        """3.2-UNIT-109: Output contains an 'Evidence Status' section."""
        excerpt = _make_full_excerpt()

        result = build_evidence_summary(excerpt)

        assert "Evidence Status" in result

    def test_anomaly_findings_section_present(self) -> None:
        """3.2-UNIT-110: Output contains an 'Anomaly Findings' section."""
        excerpt = _make_full_excerpt()

        result = build_evidence_summary(excerpt)

        assert "Anomaly Findings" in result

    def test_temporal_context_section_present(self) -> None:
        """3.2-UNIT-111: Output contains a 'Temporal Context' section."""
        excerpt = _make_full_excerpt()

        result = build_evidence_summary(excerpt)

        assert "Temporal Context" in result

    def test_case_context_appears_before_evidence_status(self) -> None:
        """3.2-UNIT-112: 'Case Context' section appears before 'Evidence Status'."""
        excerpt = _make_full_excerpt()

        result = build_evidence_summary(excerpt)

        case_context_pos = result.index("Case Context")
        evidence_status_pos = result.index("Evidence Status")
        assert case_context_pos < evidence_status_pos

    def test_evidence_status_appears_before_anomaly_findings(self) -> None:
        """3.2-UNIT-113: 'Evidence Status' section appears before 'Anomaly Findings'."""
        excerpt = _make_full_excerpt()

        result = build_evidence_summary(excerpt)

        evidence_status_pos = result.index("Evidence Status")
        anomaly_findings_pos = result.index("Anomaly Findings")
        assert evidence_status_pos < anomaly_findings_pos

    def test_anomaly_findings_appears_before_temporal_context(self) -> None:
        """3.2-UNIT-114: 'Anomaly Findings' section appears before 'Temporal Context'."""
        excerpt = _make_full_excerpt()

        result = build_evidence_summary(excerpt)

        anomaly_findings_pos = result.index("Anomaly Findings")
        temporal_context_pos = result.index("Temporal Context")
        assert anomaly_findings_pos < temporal_context_pos


# ---------------------------------------------------------------------------
# 3.2-UNIT-115: All four EvidenceStatus values in correct labeled sections
# ---------------------------------------------------------------------------


class TestBuildEvidenceSummaryStatusSections:
    """AC2: All four EvidenceStatus values appear in explicitly labeled subsections."""

    def test_present_status_appears_in_present_section(self) -> None:
        """3.2-UNIT-115: PRESENT evidence keys appear in a PRESENT-labeled section."""
        excerpt = _make_full_excerpt(
            evidence_status_map={"consumer_lag_max": EvidenceStatus.PRESENT}
        )

        result = build_evidence_summary(excerpt)

        assert "PRESENT" in result
        assert "consumer_lag_max" in result

    def test_unknown_status_appears_in_unknown_section(self) -> None:
        """3.2-UNIT-116: UNKNOWN evidence keys appear in an UNKNOWN-labeled section.

        UNKNOWN means 'missing or unavailable metric' — must never be collapsed.
        """
        excerpt = _make_full_excerpt(
            evidence_status_map={"consumer_lag_avg": EvidenceStatus.UNKNOWN}
        )

        result = build_evidence_summary(excerpt)

        assert "UNKNOWN" in result
        assert "consumer_lag_avg" in result

    def test_absent_status_appears_in_absent_section(self) -> None:
        """3.2-UNIT-117: ABSENT evidence keys appear in an ABSENT-labeled section."""
        excerpt = _make_full_excerpt(
            evidence_status_map={"topic_offset_delta": EvidenceStatus.ABSENT}
        )

        result = build_evidence_summary(excerpt)

        assert "ABSENT" in result
        assert "topic_offset_delta" in result

    def test_stale_status_appears_in_stale_section(self) -> None:
        """3.2-UNIT-118: STALE evidence keys appear in a STALE-labeled section."""
        excerpt = _make_full_excerpt(
            evidence_status_map={"producer_rate": EvidenceStatus.STALE}
        )

        result = build_evidence_summary(excerpt)

        assert "STALE" in result
        assert "producer_rate" in result

    def test_all_four_statuses_in_output_with_all_present(self) -> None:
        """3.2-UNIT-119: All four status labels appear when all four variants are present."""
        excerpt = _make_full_excerpt(
            evidence_status_map={
                "consumer_lag_max": EvidenceStatus.PRESENT,
                "consumer_lag_avg": EvidenceStatus.UNKNOWN,
                "topic_offset_delta": EvidenceStatus.ABSENT,
                "producer_rate": EvidenceStatus.STALE,
            }
        )

        result = build_evidence_summary(excerpt)

        assert "PRESENT" in result
        assert "UNKNOWN" in result
        assert "ABSENT" in result
        assert "STALE" in result

    def test_unknown_section_explicitly_describes_missing_unavailable(self) -> None:
        """3.2-UNIT-120: UNKNOWN section explicitly states 'missing or unavailable'."""
        excerpt = _make_full_excerpt(
            evidence_status_map={
                "consumer_lag_avg": EvidenceStatus.UNKNOWN,
            }
        )

        result = build_evidence_summary(excerpt)

        # D9 requirement: UNKNOWN means "missing or unavailable metric" — must be explicit
        result_lower = result.lower()
        assert "unknown" in result_lower
        assert ("missing" in result_lower or "unavailable" in result_lower), (
            "UNKNOWN section must explicitly describe 'missing' or 'unavailable' metric"
        )


# ---------------------------------------------------------------------------
# 3.2-UNIT-121: Findings section contains all Finding fields
# ---------------------------------------------------------------------------


class TestBuildEvidenceSummaryFindingsSection:
    """AC2: All Finding fields must appear in the anomaly findings section."""

    def test_finding_id_appears_in_output(self) -> None:
        """3.2-UNIT-121: finding_id is rendered in findings section."""
        finding = _make_finding(finding_id="f-unique-id-xyz")
        excerpt = _make_full_excerpt(findings=(finding,))

        result = build_evidence_summary(excerpt)

        assert "f-unique-id-xyz" in result

    def test_finding_name_appears_in_output(self) -> None:
        """3.2-UNIT-122: Finding name is rendered in findings section."""
        finding = _make_finding(name="MY_UNIQUE_FINDING_NAME")
        excerpt = _make_full_excerpt(findings=(finding,))

        result = build_evidence_summary(excerpt)

        assert "MY_UNIQUE_FINDING_NAME" in result

    def test_finding_severity_appears_in_output(self) -> None:
        """3.2-UNIT-123: Finding severity is rendered in findings section."""
        finding = _make_finding(severity="CRITICAL")
        excerpt = _make_full_excerpt(findings=(finding,))

        result = build_evidence_summary(excerpt)

        assert "CRITICAL" in result

    def test_finding_is_anomalous_appears_in_output(self) -> None:
        """3.2-UNIT-124: Finding is_anomalous flag is rendered in findings section."""
        finding = _make_finding(is_anomalous=True)
        excerpt = _make_full_excerpt(findings=(finding,))

        result = build_evidence_summary(excerpt)

        # Some representation of anomalous state must appear
        result_lower = result.lower()
        assert "anomalous" in result_lower or "is_anomalous" in result_lower

    def test_finding_is_primary_appears_in_output(self) -> None:
        """3.2-UNIT-125: Finding is_primary flag is rendered in findings section."""
        finding = _make_finding(is_primary=True)
        excerpt = _make_full_excerpt(findings=(finding,))

        result = build_evidence_summary(excerpt)

        result_lower = result.lower()
        assert "primary" in result_lower or "is_primary" in result_lower

    def test_finding_evidence_required_appears_in_output(self) -> None:
        """3.2-UNIT-126: Finding evidence_required keys appear in findings section."""
        finding = _make_finding(evidence_required=("unique_evidence_key_abc",))
        excerpt = _make_full_excerpt(findings=(finding,))

        result = build_evidence_summary(excerpt)

        assert "unique_evidence_key_abc" in result

    def test_finding_reason_codes_appear_in_output(self) -> None:
        """3.2-UNIT-127: Finding reason_codes appear in findings section."""
        finding = _make_finding(reason_codes=("unique_reason_code_xyz",))
        excerpt = _make_full_excerpt(findings=(finding,))

        result = build_evidence_summary(excerpt)

        assert "unique_reason_code_xyz" in result

    def test_multiple_findings_all_rendered(self) -> None:
        """3.2-UNIT-128: Multiple findings are all rendered in output."""
        finding_a = _make_finding(finding_id="f-aaa", name="FINDING_A")
        finding_b = _make_finding(finding_id="f-bbb", name="FINDING_B")
        excerpt = _make_full_excerpt(findings=(finding_a, finding_b))

        result = build_evidence_summary(excerpt)

        assert "FINDING_A" in result
        assert "FINDING_B" in result


# ---------------------------------------------------------------------------
# 3.2-UNIT-129: Temporal context section
# ---------------------------------------------------------------------------


class TestBuildEvidenceSummaryTemporalContext:
    """AC2: Temporal context section reflects sustained and peak flags."""

    def test_sustained_true_appears_in_temporal_context(self) -> None:
        """3.2-UNIT-129: sustained=True is reflected in temporal context section."""
        excerpt = _make_full_excerpt(sustained=True)

        result = build_evidence_summary(excerpt)

        result_lower = result.lower()
        assert "sustained" in result_lower

    def test_sustained_false_appears_in_temporal_context(self) -> None:
        """3.2-UNIT-130: sustained=False is also rendered (not omitted)."""
        excerpt = _make_full_excerpt(sustained=False)

        result = build_evidence_summary(excerpt)

        result_lower = result.lower()
        assert "sustained" in result_lower

    def test_peak_true_appears_in_temporal_context(self) -> None:
        """3.2-UNIT-131: peak=True is reflected in temporal context section."""
        excerpt = _make_full_excerpt(peak=True)

        result = build_evidence_summary(excerpt)

        result_lower = result.lower()
        assert "peak" in result_lower

    def test_peak_none_does_not_crash(self) -> None:
        """3.2-UNIT-132: peak=None is handled gracefully (no exception)."""
        excerpt = _make_full_excerpt(peak=None)

        # Must not raise
        result = build_evidence_summary(excerpt)
        assert isinstance(result, str)


# ---------------------------------------------------------------------------
# 3.2-UNIT-133: Case context section contains identity fields
# ---------------------------------------------------------------------------


class TestBuildEvidenceSummaryCaseContext:
    """AC2: Case context section includes key identity fields."""

    def test_case_id_in_case_context_section(self) -> None:
        """3.2-UNIT-133: case_id appears in the case context section."""
        excerpt = _make_full_excerpt()

        result = build_evidence_summary(excerpt)

        assert "case-prod-cluster-a-payments-lag-001" in result

    def test_env_in_case_context_section(self) -> None:
        """3.2-UNIT-134: env (e.g. 'prod') appears in the case context section."""
        excerpt = _make_full_excerpt()

        result = build_evidence_summary(excerpt)

        assert "prod" in result.lower()

    def test_topic_in_case_context_section(self) -> None:
        """3.2-UNIT-135: topic appears in the case context section."""
        excerpt = _make_full_excerpt()

        result = build_evidence_summary(excerpt)

        assert "payments.events" in result

    def test_anomaly_family_in_case_context_section(self) -> None:
        """3.2-UNIT-136: anomaly_family appears in the case context section."""
        excerpt = _make_full_excerpt()

        result = build_evidence_summary(excerpt)

        assert "CONSUMER_LAG" in result

    def test_criticality_tier_in_case_context_section(self) -> None:
        """3.2-UNIT-137: criticality_tier appears in the case context section."""
        excerpt = _make_full_excerpt()

        result = build_evidence_summary(excerpt)

        assert "TIER_0" in result
