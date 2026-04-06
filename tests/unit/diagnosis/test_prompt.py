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


# ---------------------------------------------------------------------------
# BASELINE_DEVIATION helpers
# ---------------------------------------------------------------------------


def _make_baseline_deviation_excerpt(case_id: str = "case-bd-001") -> TriageExcerptV1:
    """TriageExcerptV1 with anomaly_family=BASELINE_DEVIATION and reason_codes encoding deviations.

    Findings use gate_input.Finding (not AnomalyFinding) as per TriageExcerptV1.findings contract.
    Deviation details are encoded in reason_codes: 'BASELINE_DEV:{metric_key}:{direction}'.
    """
    return TriageExcerptV1(
        case_id=case_id,
        env=Environment.PROD,
        cluster_id="cluster-b",
        stream_id="stream-bd",
        topic="metrics.baseline",
        anomaly_family="BASELINE_DEVIATION",
        topic_role="SHARED_TOPIC",
        criticality_tier=CriticalityTier.TIER_1,
        routing_key="OWN::Streaming::Metrics",
        sustained=True,
        evidence_status_map={
            "baseline_history": EvidenceStatus.PRESENT,
            "current_window": EvidenceStatus.PRESENT,
        },
        findings=(
            Finding(
                finding_id="BD-001",
                name="baseline_deviation_correlated",
                is_anomalous=True,
                severity="LOW",
                is_primary=False,
                evidence_required=("baseline_history", "current_window"),
                reason_codes=(
                    "BASELINE_DEV:consumer_lag.offset:HIGH",
                    "BASELINE_DEV:producer_rate:LOW",
                ),
            ),
        ),
        triage_timestamp=datetime(2026, 4, 5, 8, 0, 0, tzinfo=timezone.utc),
    )


# ---------------------------------------------------------------------------
# BASELINE_DEVIATION tests (AC5 — Story 3.1)
# ---------------------------------------------------------------------------


def test_build_llm_prompt_baseline_deviation_includes_deviation_context() -> None:
    """Prompt built from a BASELINE_DEVIATION excerpt includes metric names and directions.

    AC5: test_build_llm_prompt_baseline_deviation_includes_deviation_context — verifies
    that the prompt contains deviating metric names extracted from reason_codes, and
    includes the seasonal time bucket (dow, hour) context per AC2/FR26.
    Expects a 'BASELINE DEVIATION CONTEXT' section with 'consumer_lag.offset' and 'producer_rate'.
    """
    excerpt = _make_baseline_deviation_excerpt()
    result = build_llm_prompt(excerpt, "Baseline deviation evidence summary.")
    assert "BASELINE DEVIATION CONTEXT" in result
    assert "consumer_lag.offset" in result
    assert "producer_rate" in result
    assert "HIGH" in result
    assert "LOW" in result
    # AC2/FR26: time bucket (dow, hour) as human-readable seasonal context
    # triage_timestamp=2026-04-05 08:00 UTC → Sunday (dow=6), hour=8
    assert "dow=" in result
    assert "hour=" in result


def test_build_llm_prompt_baseline_deviation_hypothesis_framing() -> None:
    """Prompt instructs the LLM to frame output as a hypothesis ('possible interpretation').

    AC5: test_build_llm_prompt_baseline_deviation_hypothesis_framing — verifies that the
    BASELINE_DEVIATION prompt contains hypothesis framing language such as
    'possible interpretation', 'LIKELY', or 'HYPOTHESIS'.
    """
    excerpt = _make_baseline_deviation_excerpt()
    result = build_llm_prompt(excerpt, "summary")
    lower_result = result.lower()
    assert any(
        phrase in lower_result
        for phrase in ("possible interpretation", "likely", "hypothesis", "suspected")
    ), (
        "Prompt must contain hypothesis framing language "
        "('possible interpretation', 'LIKELY', 'HYPOTHESIS', or 'SUSPECTED')"
    )


def test_build_llm_prompt_baseline_deviation_topology_context() -> None:
    """Prompt for BASELINE_DEVIATION includes topic_role and routing_key.

    AC5: test_build_llm_prompt_baseline_deviation_topology_context — verifies topology
    context renders correctly for BASELINE_DEVIATION cases (topic_role and routing_key).
    """
    excerpt = _make_baseline_deviation_excerpt()
    result = build_llm_prompt(excerpt, "summary")
    assert "topic_role" in result
    assert excerpt.topic_role in result
    assert "routing_key" in result
    assert excerpt.routing_key in result


def test_build_llm_prompt_baseline_deviation_few_shot_example() -> None:
    """Prompt for BASELINE_DEVIATION includes a BASELINE_DEVIATION-specific few-shot example.

    AC5: test_build_llm_prompt_baseline_deviation_few_shot_example — verifies that a
    BASELINE_DEVIATION example appears in the prompt (alongside or replacing the
    CONSUMER_LAG example).
    """
    excerpt = _make_baseline_deviation_excerpt()
    result = build_llm_prompt(excerpt, "summary")
    assert "BASELINE_DEVIATION" in result
    # The few-shot example must mention BASELINE_DEVIATION in an example context
    assert result.count("BASELINE_DEVIATION") >= 2, (
        "Prompt must contain BASELINE_DEVIATION at least twice: once in case context "
        "and once in a few-shot example"
    )
