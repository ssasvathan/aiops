"""Stage helpers for outbox READY-transition guardrails."""

from __future__ import annotations

from typing import Protocol

from aiops_triage_pipeline.contracts.case_header_event import CaseHeaderEventV1
from aiops_triage_pipeline.errors.exceptions import CriticalDependencyError
from aiops_triage_pipeline.logging.setup import get_logger
from aiops_triage_pipeline.outbox.publisher import (
    CaseHeaderPublisherProtocol,
    HeaderPublishEvidenceV1,
    publish_case_header_after_invariant_a,
)
from aiops_triage_pipeline.outbox.schema import OutboxReadyCasefileV1, OutboxRecordV1
from aiops_triage_pipeline.outbox.state_machine import create_ready_outbox_record
from aiops_triage_pipeline.storage.client import ObjectStoreClientProtocol


class OutboxRepositoryProtocol(Protocol):
    """Repository contract for persistent outbox transitions."""

    def insert_pending_object(
        self,
        *,
        confirmed_casefile: OutboxReadyCasefileV1,
    ) -> OutboxRecordV1: ...

    def transition_to_ready(
        self,
        *,
        case_id: str,
    ) -> OutboxRecordV1: ...

    def transition_to_sent(
        self,
        *,
        case_id: str,
    ) -> OutboxRecordV1: ...


def build_outbox_ready_record(
    *,
    confirmed_casefile: OutboxReadyCasefileV1,
    outbox_repository: OutboxRepositoryProtocol | None = None,
) -> OutboxRecordV1:
    """Build READY outbox record, optionally persisting PENDING_OBJECT->READY in Postgres."""
    if outbox_repository is None:
        return create_ready_outbox_record(confirmed_casefile=confirmed_casefile)

    logger = get_logger("pipeline.stages.outbox")
    try:
        outbox_repository.insert_pending_object(confirmed_casefile=confirmed_casefile)
        ready_record = outbox_repository.transition_to_ready(case_id=confirmed_casefile.case_id)
    except Exception as exc:
        if isinstance(exc, CriticalDependencyError):
            logger.critical(
                "outbox_persistence_halt_alert",
                event_type="DegradedModeEvent",
                case_id=confirmed_casefile.case_id,
                object_path=confirmed_casefile.object_path,
                affected_scope="postgres_outbox",
                reason=str(exc),
                capped_action_level="HALT",
                error_type=type(exc).__name__,
            )
            raise
        logger.error(
            "outbox_persistence_failed",
            event_type="outbox.persistence_failed",
            case_id=confirmed_casefile.case_id,
            reason=str(exc),
            error_type=type(exc).__name__,
        )
        raise

    logger.info(
        "outbox_ready_transition_confirmed",
        event_type="outbox.state_transition",
        case_id=ready_record.case_id,
        casefile_object_path=ready_record.casefile_object_path,
        status=ready_record.status,
        delivery_attempts=ready_record.delivery_attempts,
    )
    return ready_record


def build_outbox_ready_transition_payload(
    *,
    confirmed_casefile: OutboxReadyCasefileV1,
    outbox_repository: OutboxRepositoryProtocol | None = None,
) -> dict[str, str]:
    """Build minimal READY-transition payload from confirmed casefile metadata."""
    outbox_record = build_outbox_ready_record(
        confirmed_casefile=confirmed_casefile,
        outbox_repository=outbox_repository,
    )
    return {
        "status": outbox_record.status,
        "case_id": outbox_record.case_id,
        "casefile_object_path": outbox_record.casefile_object_path,
        "triage_hash": outbox_record.triage_hash,
    }


def publish_case_header_after_confirmed_casefile(
    *,
    confirmed_casefile: OutboxReadyCasefileV1,
    case_header_event: CaseHeaderEventV1,
    object_store_client: ObjectStoreClientProtocol,
    publisher: CaseHeaderPublisherProtocol,
    outbox_repository: OutboxRepositoryProtocol | None = None,
) -> HeaderPublishEvidenceV1:
    """Enforce Invariant A before publishing a case header from READY metadata."""
    logger = get_logger("pipeline.stages.outbox")
    outbox_record = build_outbox_ready_record(
        confirmed_casefile=confirmed_casefile,
        outbox_repository=outbox_repository,
    )
    publish_evidence = publish_case_header_after_invariant_a(
        outbox_record=outbox_record,
        case_header_event=case_header_event,
        object_store_client=object_store_client,
        publisher=publisher,
    )
    if outbox_repository is not None:
        try:
            sent_record = outbox_repository.transition_to_sent(case_id=outbox_record.case_id)
        except Exception as exc:
            if isinstance(exc, CriticalDependencyError):
                logger.critical(
                    "outbox_publish_state_persist_halt_alert",
                    event_type="DegradedModeEvent",
                    case_id=outbox_record.case_id,
                    object_path=outbox_record.casefile_object_path,
                    affected_scope="postgres_outbox",
                    reason=str(exc),
                    capped_action_level="HALT",
                    error_type=type(exc).__name__,
                )
                raise
            logger.error(
                "outbox_publish_state_persist_failed",
                event_type="outbox.publish_state_persist_failed",
                case_id=outbox_record.case_id,
                reason=str(exc),
                error_type=type(exc).__name__,
            )
            raise

        logger.info(
            "outbox_sent_transition_confirmed",
            event_type="outbox.state_transition",
            case_id=sent_record.case_id,
            casefile_object_path=sent_record.casefile_object_path,
            status=sent_record.status,
            delivery_attempts=sent_record.delivery_attempts,
        )
    return publish_evidence
