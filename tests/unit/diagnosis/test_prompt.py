"""Unit tests for diagnosis/prompt.py — build_llm_prompt() function."""

from __future__ import annotations

from datetime import datetime, timezone

from aiops_triage_pipeline.contracts.enums import CriticalityTier, Environment, EvidenceStatus
from aiops_triage_pipeline.contracts.gate_input import Finding
from aiops_triage_pipeline.contracts.triage_excerpt import TriageExcerptV1
from aiops_triage_pipeline.diagnosis.prompt import build_llm_prompt

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_excerpt(case_id: str = "case-prompt-001") -> TriageExcerptV1:
    """TriageExcerptV1 with PROD/TIER_0/sustained=True and populated evidence_status_map."""
    return TriageExcerptV1(
        case_id=case_id,
        env=Environment.PROD,
        cluster_id="cluster-a",
        stream_id="stream-x",
        topic="payments.events",
        anomaly_family="CONSUMER_LAG",
        topic_role="SOURCE_TOPIC",
        criticality_tier=CriticalityTier.TIER_0,
        routing_key="OWN::Streaming::Payments",
        sustained=True,
        evidence_status_map={
            "consumer_lag": EvidenceStatus.UNKNOWN,
            "throughput": EvidenceStatus.PRESENT,
        },
        findings=(
            Finding(
                finding_id="F1",
                name="lag_buildup",
                is_anomalous=True,
                evidence_required=("consumer_lag",),
            ),
        ),
        triage_timestamp=datetime(2026, 3, 7, 12, 0, 0, tzinfo=timezone.utc),
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_build_llm_prompt_returns_non_empty_string() -> None:
    """build_llm_prompt returns a non-empty string."""
    result = build_llm_prompt(_make_excerpt(), "Evidence summary here.")
    assert isinstance(result, str)
    assert len(result) > 0


def test_build_llm_prompt_contains_anomaly_family() -> None:
    """Prompt contains the anomaly_family from the triage excerpt."""
    excerpt = _make_excerpt()
    result = build_llm_prompt(excerpt, "some summary")
    assert excerpt.anomaly_family in result


def test_build_llm_prompt_contains_evidence_summary() -> None:
    """Prompt contains the evidence_summary string."""
    summary = "Consumer lag elevated: 45000 messages behind."
    result = build_llm_prompt(_make_excerpt(), summary)
    assert summary in result


def test_build_llm_prompt_instructs_json_output() -> None:
    """Prompt contains 'JSON' (case-insensitive) to instruct structured output."""
    result = build_llm_prompt(_make_excerpt(), "summary")
    assert "json" in result.lower()


def test_build_llm_prompt_instructs_unknown_propagation() -> None:
    """Prompt explicitly instructs the LLM to propagate UNKNOWN — not fabricate."""
    result = build_llm_prompt(_make_excerpt(), "summary")
    assert "propagate UNKNOWN" in result


def test_build_llm_prompt_instructs_evidence_citation() -> None:
    """Prompt instructs the LLM to cite evidence IDs from the evidence_status_map."""
    result = build_llm_prompt(_make_excerpt(), "summary")
    assert "EVIDENCE CITATION RULES" in result


def test_build_llm_prompt_contains_evidence_status_map() -> None:
    """Prompt renders evidence_status_map entries (at least one key visible)."""
    excerpt = _make_excerpt()
    result = build_llm_prompt(excerpt, "summary")
    # At least one key from evidence_status_map must appear in the prompt
    assert any(key in result for key in excerpt.evidence_status_map)


def test_build_llm_prompt_contains_finding_id() -> None:
    """Prompt renders findings with their finding_id so the LLM can reference them."""
    excerpt = _make_excerpt()
    result = build_llm_prompt(excerpt, "summary")
    # finding_id "F1" from the helper's Finding must appear in the prompt
    assert excerpt.findings[0].finding_id in result


def test_build_llm_prompt_contains_full_finding_fields() -> None:
    """Prompt includes all explicit finding fields required by Story 3.3 FR40."""
    result = build_llm_prompt(_make_excerpt(), "summary")
    assert "finding_id=" in result
    assert "name=" in result
    assert "severity=" in result
    assert "reason_codes=" in result
    assert "evidence_required=" in result
    assert "is_primary=" in result
    assert "is_anomalous=" in result


def test_build_llm_prompt_contains_routing_context_and_guidance_blocks() -> None:
    """Prompt includes routing/topology context plus confidence + few-shot guidance."""
    result = build_llm_prompt(_make_excerpt(), "summary")
    lower_result = result.lower()
    assert "topic_role" in result
    assert "routing_key" in result
    assert "fault-domain hints" in lower_result
    assert "confidence calibration guidance" in lower_result
    assert "few-shot example" in lower_result
