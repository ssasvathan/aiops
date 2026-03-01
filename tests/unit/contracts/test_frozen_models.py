"""Unit tests for all 5 frozen event contract models.

Tests cover:
- Immutability (frozen=True): mutation raises ValidationError
- Serialization round-trip: model_dump_json() -> model_validate_json()
- schema_version field equals "v1"
- Enum string serialization
- EvidenceStatus.UNKNOWN in evidence_status_map
- DiagnosisReportV1 fallback construction
"""

import json
from datetime import datetime

import pytest
from pydantic import ValidationError

from aiops_triage_pipeline.contracts import (
    Action,
    ActionDecisionV1,
    CaseHeaderEventV1,
    CriticalityTier,
    DiagnosisConfidence,
    DiagnosisReportV1,
    Environment,
    EvidencePack,
    EvidenceStatus,
    Finding,
    GateInputV1,
    TriageExcerptV1,
)

# ---------------------------------------------------------------------------
# Finding nested model
# ---------------------------------------------------------------------------


class TestFinding:
    def test_finding_is_frozen(self):
        finding = Finding(
            finding_id="f1",
            name="lag",
            is_anomalous=True,
            evidence_required=("lag_metric",),
        )
        with pytest.raises(ValidationError):
            finding.name = "mutated"  # type: ignore[misc]

    def test_finding_round_trip(self, sample_finding):
        json_str = sample_finding.model_dump_json()
        reconstructed = Finding.model_validate_json(json_str)
        assert sample_finding == reconstructed

    def test_finding_defaults(self):
        finding = Finding(
            finding_id="f2",
            name="volume-drop",
            is_anomalous=False,
            evidence_required=(),
        )
        assert finding.is_primary is None
        assert finding.severity is None
        assert finding.reason_codes == ()


# ---------------------------------------------------------------------------
# GateInputV1
# ---------------------------------------------------------------------------


class TestGateInputV1:
    def test_gate_input_is_frozen(self, sample_gate_input):
        with pytest.raises(ValidationError):
            sample_gate_input.env = Environment.PROD  # type: ignore[misc]

    def test_gate_input_round_trip(self, sample_gate_input):
        json_str = sample_gate_input.model_dump_json()
        reconstructed = GateInputV1.model_validate_json(json_str)
        assert sample_gate_input == reconstructed

    def test_gate_input_schema_version(self, sample_gate_input):
        assert sample_gate_input.schema_version == "v1"

    def test_gate_input_schema_version_in_json(self, sample_gate_input):
        data = json.loads(sample_gate_input.model_dump_json())
        assert data["schema_version"] == "v1"

    def test_gate_input_findings_is_tuple(self, sample_gate_input):
        assert isinstance(sample_gate_input.findings, tuple)

    def test_gate_input_optional_fields_default_none(self):
        gate_input = GateInputV1(
            env=Environment.DEV,
            cluster_id="c1",
            stream_id="s1",
            topic="t1",
            topic_role="SOURCE_TOPIC",
            anomaly_family="CONSUMER_LAG",
            criticality_tier=CriticalityTier.TIER_1,
            proposed_action=Action.NOTIFY,
            diagnosis_confidence=0.5,
            sustained=False,
            findings=(),
            evidence_status_map={},
            action_fingerprint="fp",
        )
        assert gate_input.consumer_group is None
        assert gate_input.partition_count_observed is None
        assert gate_input.peak is None
        assert gate_input.case_id is None
        assert gate_input.decision_basis is None

    def test_gate_input_evidence_status_unknown_preserved(self, sample_gate_input):
        assert sample_gate_input.evidence_status_map["throughput_metric"] == EvidenceStatus.UNKNOWN

    def test_gate_input_evidence_status_unknown_in_json(self, sample_gate_input):
        data = json.loads(sample_gate_input.model_dump_json())
        assert data["evidence_status_map"]["throughput_metric"] == "UNKNOWN"

    def test_gate_input_confidence_out_of_range_rejected(self):
        with pytest.raises(ValidationError):
            GateInputV1(
                env=Environment.LOCAL,
                cluster_id="c",
                stream_id="s",
                topic="t",
                topic_role="SOURCE_TOPIC",
                anomaly_family="CONSUMER_LAG",
                criticality_tier=CriticalityTier.TIER_0,
                proposed_action=Action.PAGE,
                diagnosis_confidence=1.5,  # out of range: must be 0.0–1.0
                sustained=True,
                findings=(),
                evidence_status_map={},
                action_fingerprint="fp",
            )

    def test_gate_input_invalid_topic_role_rejected(self):
        with pytest.raises(ValidationError):
            GateInputV1(
                env=Environment.LOCAL,
                cluster_id="c",
                stream_id="s",
                topic="t",
                topic_role="UNKNOWN_ROLE",  # not a valid Literal value
                anomaly_family="CONSUMER_LAG",
                criticality_tier=CriticalityTier.TIER_0,
                proposed_action=Action.PAGE,
                diagnosis_confidence=0.9,
                sustained=True,
                findings=(),
                evidence_status_map={},
                action_fingerprint="fp",
            )


# ---------------------------------------------------------------------------
# ActionDecisionV1
# ---------------------------------------------------------------------------


class TestActionDecisionV1:
    def test_action_decision_is_frozen(self, sample_action_decision):
        with pytest.raises(ValidationError):
            sample_action_decision.final_action = Action.OBSERVE  # type: ignore[misc]

    def test_action_decision_round_trip(self, sample_action_decision):
        json_str = sample_action_decision.model_dump_json()
        reconstructed = ActionDecisionV1.model_validate_json(json_str)
        assert sample_action_decision == reconstructed

    def test_action_decision_schema_version(self, sample_action_decision):
        assert sample_action_decision.schema_version == "v1"

    def test_action_decision_enum_serializes_as_string(self, sample_action_decision):
        json_str = sample_action_decision.model_dump_json()
        assert '"PAGE"' in json_str
        assert '"Action.PAGE"' not in json_str

    def test_action_decision_gate_rule_ids_tuple(self, sample_action_decision):
        assert isinstance(sample_action_decision.gate_rule_ids, tuple)

    def test_action_decision_postmortem_reason_codes_defaults_empty(self):
        decision = ActionDecisionV1(
            final_action=Action.OBSERVE,
            env_cap_applied=False,
            gate_rule_ids=(),
            gate_reason_codes=("PASS",),
            action_fingerprint="fp",
            postmortem_required=False,
        )
        assert decision.postmortem_reason_codes == ()
        assert decision.postmortem_mode is None


# ---------------------------------------------------------------------------
# CaseHeaderEventV1
# ---------------------------------------------------------------------------


class TestCaseHeaderEventV1:
    def test_case_header_event_is_frozen(self, sample_case_header_event):
        with pytest.raises(ValidationError):
            sample_case_header_event.case_id = "mutated"  # type: ignore[misc]

    def test_case_header_event_round_trip(self, sample_case_header_event):
        json_str = sample_case_header_event.model_dump_json()
        reconstructed = CaseHeaderEventV1.model_validate_json(json_str)
        assert sample_case_header_event == reconstructed

    def test_case_header_event_schema_version(self, sample_case_header_event):
        assert sample_case_header_event.schema_version == "v1"

    def test_case_header_event_evaluation_ts_utc_in_json(self, sample_case_header_event):
        json_str = sample_case_header_event.model_dump_json()
        # Pydantic v2 serializes datetime as ISO 8601 UTC string
        assert "2026-02-28" in json_str

    def test_case_header_event_enum_serializes_as_string(self, sample_case_header_event):
        json_str = sample_case_header_event.model_dump_json()
        assert '"PAGE"' in json_str
        assert '"prod"' in json_str  # Environment enum values are lowercase strings
        assert '"TIER_0"' in json_str

    def test_case_header_event_naive_datetime_rejected(self):
        with pytest.raises(ValidationError):
            CaseHeaderEventV1(
                case_id="c1",
                env=Environment.PROD,
                cluster_id="cl",
                stream_id="s",
                topic="t",
                anomaly_family="CONSUMER_LAG",
                criticality_tier=CriticalityTier.TIER_0,
                final_action=Action.PAGE,
                routing_key="team-a",
                evaluation_ts=datetime(2026, 2, 28, 12, 0, 0),  # naive — no tzinfo
            )


# ---------------------------------------------------------------------------
# TriageExcerptV1
# ---------------------------------------------------------------------------


class TestTriageExcerptV1:
    def test_triage_excerpt_is_frozen(self, sample_triage_excerpt):
        with pytest.raises(ValidationError):
            sample_triage_excerpt.case_id = "mutated"  # type: ignore[misc]

    def test_triage_excerpt_round_trip(self, sample_triage_excerpt):
        json_str = sample_triage_excerpt.model_dump_json()
        reconstructed = TriageExcerptV1.model_validate_json(json_str)
        assert sample_triage_excerpt == reconstructed

    def test_triage_excerpt_schema_version(self, sample_triage_excerpt):
        assert sample_triage_excerpt.schema_version == "v1"

    def test_triage_excerpt_findings_is_tuple(self, sample_triage_excerpt):
        assert isinstance(sample_triage_excerpt.findings, tuple)

    def test_triage_excerpt_evidence_unknown_preserved(self, sample_triage_excerpt):
        status = sample_triage_excerpt.evidence_status_map["throughput_metric"]
        assert status == EvidenceStatus.UNKNOWN

    def test_triage_excerpt_evidence_unknown_serializes_as_string(self, sample_triage_excerpt):
        data = json.loads(sample_triage_excerpt.model_dump_json())
        assert data["evidence_status_map"]["throughput_metric"] == "UNKNOWN"

    def test_triage_excerpt_peak_defaults_none(self):
        from datetime import timezone

        excerpt = TriageExcerptV1(
            case_id="c1",
            env=Environment.DEV,
            cluster_id="cl1",
            stream_id="s1",
            topic="t1",
            anomaly_family="CONSUMER_LAG",
            topic_role="SOURCE_TOPIC",
            criticality_tier=CriticalityTier.TIER_2,
            routing_key="team-a",
            sustained=False,
            evidence_status_map={},
            findings=(),
            triage_timestamp=datetime(2026, 2, 28, tzinfo=timezone.utc),
        )
        assert excerpt.peak is None

    def test_triage_excerpt_naive_datetime_rejected(self):
        with pytest.raises(ValidationError):
            TriageExcerptV1(
                case_id="c1",
                env=Environment.DEV,
                cluster_id="cl",
                stream_id="s",
                topic="t",
                anomaly_family="CONSUMER_LAG",
                topic_role="SOURCE_TOPIC",
                criticality_tier=CriticalityTier.TIER_2,
                routing_key="team-a",
                sustained=False,
                evidence_status_map={},
                findings=(),
                triage_timestamp=datetime(2026, 2, 28),  # naive — no tzinfo
            )


# ---------------------------------------------------------------------------
# DiagnosisReportV1
# ---------------------------------------------------------------------------


class TestDiagnosisReportV1:
    def test_diagnosis_report_is_frozen(self, sample_diagnosis_report):
        with pytest.raises(ValidationError):
            sample_diagnosis_report.verdict = "mutated"  # type: ignore[misc]

    def test_diagnosis_report_round_trip(self, sample_diagnosis_report):
        json_str = sample_diagnosis_report.model_dump_json()
        reconstructed = DiagnosisReportV1.model_validate_json(json_str)
        assert sample_diagnosis_report == reconstructed

    def test_diagnosis_report_schema_version(self, sample_diagnosis_report):
        assert sample_diagnosis_report.schema_version == "v1"

    def test_diagnosis_report_fallback_is_valid(self):
        fallback = DiagnosisReportV1(
            verdict="UNKNOWN",
            confidence=DiagnosisConfidence.LOW,
            evidence_pack=EvidencePack(facts=(), missing_evidence=(), matched_rules=()),
            reason_codes=("LLM_UNAVAILABLE",),
        )
        assert fallback.verdict == "UNKNOWN"
        assert fallback.confidence == DiagnosisConfidence.LOW
        assert fallback.case_id is None
        assert fallback.fault_domain is None
        assert "LLM_UNAVAILABLE" in fallback.reason_codes

    def test_diagnosis_report_fallback_round_trip(self):
        fallback = DiagnosisReportV1(
            verdict="UNKNOWN",
            confidence=DiagnosisConfidence.LOW,
            evidence_pack=EvidencePack(facts=(), missing_evidence=(), matched_rules=()),
            reason_codes=("LLM_UNAVAILABLE",),
        )
        json_str = fallback.model_dump_json()
        reconstructed = DiagnosisReportV1.model_validate_json(json_str)
        assert fallback == reconstructed

    def test_diagnosis_report_all_fallback_reason_codes(self):
        valid_codes = (
            "LLM_UNAVAILABLE", "LLM_TIMEOUT", "LLM_ERROR", "LLM_STUB", "LLM_SCHEMA_INVALID"
        )
        for code in valid_codes:
            fallback = DiagnosisReportV1(
                verdict="UNKNOWN",
                confidence=DiagnosisConfidence.LOW,
                evidence_pack=EvidencePack(facts=(), missing_evidence=(), matched_rules=()),
                reason_codes=(code,),
            )
            assert code in fallback.reason_codes

    def test_diagnosis_report_empty_verdict_rejected(self):
        with pytest.raises(ValidationError):
            DiagnosisReportV1(
                verdict="",  # empty string — must be rejected
                confidence=DiagnosisConfidence.LOW,
                evidence_pack=EvidencePack(facts=(), missing_evidence=(), matched_rules=()),
            )

    def test_evidence_pack_is_frozen(self, sample_evidence_pack):
        with pytest.raises(ValidationError):
            sample_evidence_pack.facts = ("mutated",)  # type: ignore[misc]

    def test_evidence_pack_round_trip(self, sample_evidence_pack):
        json_str = sample_evidence_pack.model_dump_json()
        reconstructed = EvidencePack.model_validate_json(json_str)
        assert sample_evidence_pack == reconstructed

    def test_diagnosis_report_defaults(self):
        report = DiagnosisReportV1(
            verdict="UNKNOWN",
            confidence=DiagnosisConfidence.LOW,
            evidence_pack=EvidencePack(facts=(), missing_evidence=(), matched_rules=()),
        )
        assert report.next_checks == ()
        assert report.gaps == ()
        assert report.reason_codes == ()
        assert report.triage_hash is None


# ---------------------------------------------------------------------------
# Enum string serialization (cross-contract)
# ---------------------------------------------------------------------------


class TestEnumSerialization:
    def test_action_page_serializes_as_string(self, sample_action_decision):
        json_str = sample_action_decision.model_dump_json()
        assert '"PAGE"' in json_str

    def test_environment_prod_serializes_as_lowercase_string(self, sample_case_header_event):
        json_str = sample_case_header_event.model_dump_json()
        assert '"prod"' in json_str  # Environment.PROD = "prod" (lowercase value)

    def test_criticality_tier_serializes_as_string(self, sample_case_header_event):
        json_str = sample_case_header_event.model_dump_json()
        assert '"TIER_0"' in json_str

    def test_evidence_status_unknown_serializes_as_string(self, sample_gate_input):
        json_str = sample_gate_input.model_dump_json()
        assert '"UNKNOWN"' in json_str

    def test_diagnosis_confidence_serializes_as_string(self, sample_diagnosis_report):
        json_str = sample_diagnosis_report.model_dump_json()
        assert '"HIGH"' in json_str
