"""Deterministic evidence summary builder for cold-path diagnosis input.

Implements FR38 and D9: pure function TriageExcerptV1 → str.
Guarantees byte-identical output for identical inputs by:
- Sorting all collections before rendering (evidence_status_map keys, findings, reason_codes)
- Using fixed section order
- Emitting no timestamps, no random UUIDs
- Explicitly labeling all four EvidenceStatus values (PRESENT, UNKNOWN, ABSENT, STALE)

D9 specification: "Pure function: TriageExcerptV1 → str. Deterministic ordering
(sorted keys, fixed section order). No timestamps in output. Conditionally includes
sections based on evidence status."
"""

from __future__ import annotations

from aiops_triage_pipeline.contracts.enums import EvidenceStatus
from aiops_triage_pipeline.contracts.gate_input import Finding
from aiops_triage_pipeline.contracts.triage_excerpt import TriageExcerptV1


def build_evidence_summary(triage_excerpt: TriageExcerptV1) -> str:
    """Build a deterministic, byte-stable evidence summary string from a TriageExcerptV1.

    Output sections (fixed order):
      1. Case Context
      2. Evidence Status (PRESENT / UNKNOWN / ABSENT / STALE)
      3. Anomaly Findings (all Finding fields, sorted by finding_id)
      4. Temporal Context (sustained flag, peak flag)

    The function is pure: no I/O, no side effects, no timestamps, no randomness.
    Identical inputs always produce byte-identical outputs.

    Args:
        triage_excerpt: The triage excerpt to summarize.

    Returns:
        Deterministic text representation of the evidence summary.
    """
    lines: list[str] = []

    # -----------------------------------------------------------------------
    # Section 1: Case Context
    # -----------------------------------------------------------------------
    lines.append("== Case Context ==")
    lines.append(f"Case ID: {triage_excerpt.case_id}")
    lines.append(f"Environment: {triage_excerpt.env.value}")
    lines.append(f"Cluster: {triage_excerpt.cluster_id}")
    lines.append(f"Stream: {triage_excerpt.stream_id}")
    lines.append(f"Topic: {triage_excerpt.topic}")
    lines.append(f"Anomaly Family: {triage_excerpt.anomaly_family}")
    lines.append(f"Topic Role: {triage_excerpt.topic_role}")
    lines.append(f"Criticality Tier: {triage_excerpt.criticality_tier.value}")
    lines.append(f"Routing Key: {triage_excerpt.routing_key}")
    lines.append("")

    # -----------------------------------------------------------------------
    # Section 2: Evidence Status
    # Sort keys for determinism regardless of dict insertion order.
    # -----------------------------------------------------------------------
    lines.append("== Evidence Status ==")

    sorted_evidence_items = sorted(triage_excerpt.evidence_status_map.items())

    # Group by status — use EvidenceStatus enum order for section ordering
    present_keys = [k for k, v in sorted_evidence_items if v == EvidenceStatus.PRESENT]
    unknown_keys = [k for k, v in sorted_evidence_items if v == EvidenceStatus.UNKNOWN]
    absent_keys = [k for k, v in sorted_evidence_items if v == EvidenceStatus.ABSENT]
    stale_keys = [k for k, v in sorted_evidence_items if v == EvidenceStatus.STALE]

    lines.append("PRESENT:")
    if present_keys:
        for key in present_keys:
            lines.append(f"  - {key}: PRESENT")
    else:
        lines.append("  (none)")

    lines.append("UNKNOWN (missing or unavailable metric):")
    if unknown_keys:
        for key in unknown_keys:
            lines.append(f"  - {key}: UNKNOWN — missing or unavailable metric")
    else:
        lines.append("  (none)")

    lines.append("ABSENT:")
    if absent_keys:
        for key in absent_keys:
            lines.append(f"  - {key}: ABSENT")
    else:
        lines.append("  (none)")

    lines.append("STALE:")
    if stale_keys:
        for key in stale_keys:
            lines.append(f"  - {key}: STALE")
    else:
        lines.append("  (none)")

    lines.append("")

    # -----------------------------------------------------------------------
    # Section 3: Anomaly Findings
    # Sort findings by finding_id for determinism.
    # -----------------------------------------------------------------------
    lines.append("== Anomaly Findings ==")

    sorted_findings: list[Finding] = sorted(
        triage_excerpt.findings, key=lambda f: f.finding_id
    )

    if sorted_findings:
        for finding in sorted_findings:
            lines.append(f"Finding ID: {finding.finding_id}")
            lines.append(f"  Name: {finding.name}")
            severity_str = finding.severity if finding.severity is not None else "N/A"
            lines.append(f"  Severity: {severity_str}")
            lines.append(f"  Is Anomalous: {finding.is_anomalous}")
            is_primary_str = str(finding.is_primary) if finding.is_primary is not None else "N/A"
            lines.append(f"  Is Primary: {is_primary_str}")
            # Sort evidence_required for determinism
            sorted_evidence_required = sorted(finding.evidence_required)
            lines.append(f"  Evidence Required: {', '.join(sorted_evidence_required)}")
            # Sort reason_codes for determinism
            sorted_reason_codes = sorted(finding.reason_codes)
            if sorted_reason_codes:
                lines.append(f"  Reason Codes: {', '.join(sorted_reason_codes)}")
            else:
                lines.append("  Reason Codes: (none)")
    else:
        lines.append("  (no findings)")

    lines.append("")

    # -----------------------------------------------------------------------
    # Section 4: Temporal Context
    # -----------------------------------------------------------------------
    lines.append("== Temporal Context ==")
    lines.append(f"Sustained: {triage_excerpt.sustained}")
    peak_str = str(triage_excerpt.peak) if triage_excerpt.peak is not None else "N/A"
    lines.append(f"Peak: {peak_str}")
    lines.append("")

    return "\n".join(lines)
