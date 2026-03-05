"""Stage helpers for outbox READY-transition guardrails."""

from __future__ import annotations

from aiops_triage_pipeline.outbox.schema import OutboxReadyCasefileV1


def build_outbox_ready_transition_payload(
    *,
    confirmed_casefile: OutboxReadyCasefileV1,
) -> dict[str, str]:
    """Build minimal READY-transition payload from confirmed casefile metadata."""
    return {
        "status": "READY",
        "case_id": confirmed_casefile.case_id,
        "casefile_object_path": confirmed_casefile.object_path,
        "triage_hash": confirmed_casefile.triage_hash,
    }
