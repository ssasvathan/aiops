"""ServiceNow linkage orchestration and CaseFile linkage.json persistence."""

from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import Any, Mapping, Protocol

from pydantic import BaseModel

from aiops_triage_pipeline.denylist.loader import DenylistV1
from aiops_triage_pipeline.integrations.servicenow import (
    ServiceNowClient,
    ServiceNowLinkageWriteResult,
)
from aiops_triage_pipeline.integrations.slack import SlackClient
from aiops_triage_pipeline.linkage.schema import LinkageRetryRecordV1
from aiops_triage_pipeline.linkage.state_machine import (
    is_retry_due,
    mark_linkage_failure,
    mark_linkage_searching,
    mark_linkage_success,
)
from aiops_triage_pipeline.logging.setup import get_logger
from aiops_triage_pipeline.models.case_file import (
    LINKAGE_HASH_PLACEHOLDER,
    CaseFileLinkageV1,
)
from aiops_triage_pipeline.pipeline.stages.casefile import persist_casefile_linkage_stage
from aiops_triage_pipeline.storage.casefile_io import compute_casefile_linkage_hash
from aiops_triage_pipeline.storage.client import ObjectStoreClientProtocol


class ServiceNowLinkagePersistResult(BaseModel, frozen=True):
    """ServiceNow linkage outcome plus persisted linkage stage metadata."""

    linkage_result: ServiceNowLinkageWriteResult
    linkage_retry_state: LinkageRetryRecordV1 | None = None
    linkage_casefile: CaseFileLinkageV1 | None = None
    linkage_object_path: str | None = None


class LinkageRetryRepositoryProtocol(Protocol):
    """Repository contract required by linkage retry orchestration."""

    def get_or_create_pending(
        self,
        *,
        case_id: str,
        pd_incident_id: str,
        incident_sys_id: str | None,
        retry_window_minutes: int,
        now: datetime | None = None,
    ) -> LinkageRetryRecordV1: ...

    def persist_transition(
        self,
        *,
        case_id: str,
        next_record: LinkageRetryRecordV1,
        expected_source_statuses: set[str],
    ) -> LinkageRetryRecordV1: ...


def execute_servicenow_linkage_and_persist(
    *,
    case_id: str,
    pd_incident_id: str,
    incident_sys_id: str | None,
    summary: str,
    triage_hash: str,
    object_store_client: ObjectStoreClientProtocol,
    servicenow_client: ServiceNowClient,
    diagnosis_hash: str | None = None,
    pir_task_types: tuple[str, ...] = ("pir",),
    context: Mapping[str, Any] | None = None,
    linkage_retry_repository: LinkageRetryRepositoryProtocol | None = None,
    slack_client: SlackClient | None = None,
    denylist: DenylistV1 | None = None,
    now: datetime | None = None,
) -> ServiceNowLinkagePersistResult:
    """Execute ServiceNow linkage with retry-state orchestration and terminal persistence."""
    if linkage_retry_repository is None:
        # Backward-compatible one-shot execution path.
        linkage_result = servicenow_client.upsert_problem_and_pir_tasks(
            case_id=case_id,
            pd_incident_id=pd_incident_id,
            incident_sys_id=incident_sys_id,
            summary=summary,
            pir_task_types=pir_task_types,
            context=context,
        )
        terminal_state = (
            "LINKED"
            if linkage_result.linkage_status in {"linked", "skipped"}
            else "FAILED_FINAL"
        )
        resolved_result = linkage_result.model_copy(
            update={
                "linkage_state": terminal_state,
                "retryable": False,
                "next_attempt_at": None,
            }
        )
        linkage_casefile, linkage_object_path = _persist_terminal_linkage_stage(
            case_id=case_id,
            incident_sys_id=incident_sys_id,
            triage_hash=triage_hash,
            diagnosis_hash=diagnosis_hash,
            object_store_client=object_store_client,
            linkage_result=resolved_result,
            linkage_retry_state=None,
        )
        return ServiceNowLinkagePersistResult(
            linkage_result=resolved_result,
            linkage_retry_state=None,
            linkage_casefile=linkage_casefile,
            linkage_object_path=linkage_object_path,
        )

    retry_state = linkage_retry_repository.get_or_create_pending(
        case_id=case_id,
        pd_incident_id=pd_incident_id,
        incident_sys_id=incident_sys_id,
        retry_window_minutes=servicenow_client.linkage_contract.retry_window_minutes,
        now=now,
    )

    if retry_state.state == "LINKED":
        return ServiceNowLinkagePersistResult(
            linkage_result=ServiceNowLinkageWriteResult(
                linkage_status="linked",
                linkage_reason="already_linked",
                request_id=retry_state.request_id or "unknown",
                incident_sys_id=retry_state.incident_sys_id,
                linkage_state="LINKED",
                retryable=False,
            ),
            linkage_retry_state=retry_state,
        )
    if retry_state.state == "FAILED_FINAL":
        return ServiceNowLinkagePersistResult(
            linkage_result=ServiceNowLinkageWriteResult(
                linkage_status="failed",
                linkage_reason="failed_final_terminal",
                request_id=retry_state.request_id or "unknown",
                incident_sys_id=retry_state.incident_sys_id,
                linkage_state="FAILED_FINAL",
                retryable=False,
                reason_metadata=retry_state.last_reason_metadata,
            ),
            linkage_retry_state=retry_state,
        )
    if retry_state.state == "FAILED_TEMP" and not is_retry_due(record=retry_state, now=now):
        return ServiceNowLinkagePersistResult(
            linkage_result=ServiceNowLinkageWriteResult(
                linkage_status="failed",
                linkage_reason="retry_scheduled",
                request_id=retry_state.request_id or "retry-scheduled",
                incident_sys_id=retry_state.incident_sys_id,
                linkage_state="FAILED_TEMP",
                retryable=True,
                next_attempt_at=retry_state.next_attempt_at,
                reason_metadata=retry_state.last_reason_metadata,
            ),
            linkage_retry_state=retry_state,
        )

    source_state = retry_state.state
    searching_state = mark_linkage_searching(record=retry_state, now=now)
    retry_state = linkage_retry_repository.persist_transition(
        case_id=case_id,
        next_record=searching_state,
        expected_source_statuses={source_state},
    )

    start = time.monotonic()
    linkage_result = servicenow_client.upsert_problem_and_pir_tasks(
        case_id=case_id,
        pd_incident_id=pd_incident_id,
        incident_sys_id=incident_sys_id,
        summary=summary,
        pir_task_types=pir_task_types,
        context=context,
    )
    latency_ms = round((time.monotonic() - start) * 1000, 2)

    if linkage_result.linkage_status in {"linked", "skipped"}:
        linked_state = mark_linkage_success(
            record=retry_state,
            request_id=linkage_result.request_id,
            incident_sys_id=linkage_result.incident_sys_id or incident_sys_id,
            now=now,
        )
        retry_state = linkage_retry_repository.persist_transition(
            case_id=case_id,
            next_record=linked_state,
            expected_source_statuses={"SEARCHING"},
        )
        resolved_result = linkage_result.model_copy(
            update={
                "linkage_state": "LINKED",
                "retryable": False,
                "next_attempt_at": None,
            }
        )
        linkage_casefile, linkage_object_path = _persist_terminal_linkage_stage(
            case_id=case_id,
            incident_sys_id=incident_sys_id,
            triage_hash=triage_hash,
            diagnosis_hash=diagnosis_hash,
            object_store_client=object_store_client,
            linkage_result=resolved_result,
            linkage_retry_state=retry_state,
        )
        return ServiceNowLinkagePersistResult(
            linkage_result=resolved_result,
            linkage_retry_state=retry_state,
            linkage_casefile=linkage_casefile,
            linkage_object_path=linkage_object_path,
        )

    transient, error_code, retry_after_seconds, error_message, reason_metadata = (
        _classify_failure_from_linkage_result(
            linkage_result=linkage_result,
            transient_error_classifications=(
                servicenow_client.linkage_contract.transient_error_classifications
            ),
        )
    )
    failure_state = mark_linkage_failure(
        record=retry_state,
        transient=transient,
        error_code=error_code,
        error_message=error_message,
        request_id=linkage_result.request_id,
        retry_base_seconds=servicenow_client.linkage_contract.retry_base_seconds,
        retry_max_seconds=servicenow_client.linkage_contract.retry_max_seconds,
        retry_jitter_ratio=servicenow_client.linkage_contract.retry_jitter_ratio,
        retry_after_seconds=retry_after_seconds,
        reason_metadata=reason_metadata,
        now=now,
    )
    retry_state = linkage_retry_repository.persist_transition(
        case_id=case_id,
        next_record=failure_state,
        expected_source_statuses={"SEARCHING"},
    )

    if retry_state.state == "FAILED_TEMP":
        resolved_result = linkage_result.model_copy(
            update={
                "linkage_state": "FAILED_TEMP",
                "retryable": True,
                "next_attempt_at": retry_state.next_attempt_at,
                "reason_metadata": retry_state.last_reason_metadata,
            }
        )
        return ServiceNowLinkagePersistResult(
            linkage_result=resolved_result,
            linkage_retry_state=retry_state,
        )

    resolved_result = linkage_result.model_copy(
        update={
            "linkage_state": "FAILED_FINAL",
            "retryable": False,
            "next_attempt_at": None,
            "reason_metadata": retry_state.last_reason_metadata,
        }
    )
    if linkage_result.linkage_status == "failed":
        _emit_failed_final_escalation(
            case_id=case_id,
            pd_incident_id=pd_incident_id,
            retry_state=retry_state,
            latency_ms=latency_ms,
            slack_client=slack_client,
            denylist=denylist,
        )
    linkage_casefile, linkage_object_path = _persist_terminal_linkage_stage(
        case_id=case_id,
        incident_sys_id=incident_sys_id,
        triage_hash=triage_hash,
        diagnosis_hash=diagnosis_hash,
        object_store_client=object_store_client,
        linkage_result=resolved_result,
        linkage_retry_state=retry_state,
    )
    return ServiceNowLinkagePersistResult(
        linkage_result=resolved_result,
        linkage_retry_state=retry_state,
        linkage_casefile=linkage_casefile,
        linkage_object_path=linkage_object_path,
    )


def _persist_terminal_linkage_stage(
    *,
    case_id: str,
    incident_sys_id: str | None,
    triage_hash: str,
    diagnosis_hash: str | None,
    object_store_client: ObjectStoreClientProtocol,
    linkage_result: ServiceNowLinkageWriteResult,
    linkage_retry_state: LinkageRetryRecordV1 | None,
) -> tuple[CaseFileLinkageV1, str]:
    linkage_placeholder = CaseFileLinkageV1(
        case_id=case_id,
        linkage_status=linkage_result.linkage_status,
        linkage_reason=linkage_result.linkage_reason,
        incident_sys_id=linkage_result.incident_sys_id or incident_sys_id,
        problem_sys_id=linkage_result.problem_sys_id,
        problem_external_id=linkage_result.problem_external_id,
        pir_task_sys_ids=linkage_result.pir_task_sys_ids,
        pir_task_external_ids=linkage_result.pir_task_external_ids,
        triage_hash=triage_hash,
        diagnosis_hash=diagnosis_hash,
        linkage_hash=LINKAGE_HASH_PLACEHOLDER,
    )
    linkage_casefile = linkage_placeholder.model_copy(
        update={"linkage_hash": compute_casefile_linkage_hash(linkage_placeholder)}
    )
    linkage_object_path = persist_casefile_linkage_stage(
        casefile=linkage_casefile,
        object_store_client=object_store_client,
    )
    return linkage_casefile, linkage_object_path


def _classify_failure_from_linkage_result(
    *,
    linkage_result: ServiceNowLinkageWriteResult,
    transient_error_classifications: tuple[str, ...],
) -> tuple[bool, str, int | None, str, dict[str, Any]]:
    metadata = dict(linkage_result.reason_metadata)
    error_message = str(metadata.get("error") or linkage_result.linkage_reason)
    error_code = _as_non_empty_string(metadata.get("error_code")) or _infer_error_code(
        error_message
    )
    if error_code is None:
        error_code = linkage_result.linkage_reason
    retry_after_seconds = _as_positive_int(metadata.get("retry_after_seconds"))
    if retry_after_seconds is None:
        retry_after_seconds = _infer_retry_after_seconds(error_message)
    transient = error_code in set(transient_error_classifications)
    metadata["error_code"] = error_code
    if retry_after_seconds is not None:
        metadata["retry_after_seconds"] = retry_after_seconds
    return transient, error_code, retry_after_seconds, error_message, metadata


def _infer_error_code(error_message: str) -> str | None:
    normalized = error_message.lower()
    if "http_status=429" in normalized or "http error 429" in normalized:
        return "http_429"
    if any(
        marker in normalized
        for marker in (
            "http_status=500",
            "http_status=502",
            "http_status=503",
            "http_status=504",
            "http error 500",
            "http error 502",
            "http error 503",
            "http error 504",
        )
    ):
        return "http_5xx"
    if "timed out" in normalized or "timeout" in normalized:
        return "timeout"
    if any(
        marker in normalized
        for marker in (
            "connection refused",
            "connection reset",
            "connection aborted",
            "temporarily unavailable",
        )
    ):
        return "connection_error"
    return None


def _infer_retry_after_seconds(error_message: str) -> int | None:
    marker = "retry_after_seconds="
    if marker not in error_message:
        return None
    try:
        value = error_message.split(marker, 1)[1].split(";", 1)[0].strip()
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _emit_failed_final_escalation(
    *,
    case_id: str,
    pd_incident_id: str,
    retry_state: LinkageRetryRecordV1,
    latency_ms: float,
    slack_client: SlackClient | None,
    denylist: DenylistV1 | None,
) -> None:
    logger = get_logger("pipeline.stages.linkage")
    request_id = retry_state.request_id or "unknown"
    timestamp = datetime.now(tz=UTC).isoformat()
    reason_code = retry_state.last_error_code or "FAILED_FINAL"
    logger.warning(
        "sn_linkage_failed_final_escalation_fallback",
        timestamp=timestamp,
        request_id=request_id,
        case_id=case_id,
        action="sn_linkage_failed_final_escalation",
        outcome="FAILED_FINAL",
        latency_ms=latency_ms,
        pd_incident_id=pd_incident_id,
        incident_sys_id=retry_state.incident_sys_id,
        reason_code=reason_code,
        attempt_count=retry_state.attempt_count,
        retry_window_minutes=retry_state.retry_window_minutes,
    )
    if slack_client is None:
        return
    effective_denylist = denylist or DenylistV1(
        denylist_version="unset",
        denied_field_names=(),
        denied_value_patterns=(),
    )
    slack_client.send_linkage_failed_final_escalation(
        case_id=case_id,
        request_id=request_id,
        pd_incident_id=pd_incident_id,
        incident_sys_id=retry_state.incident_sys_id,
        reason_code=reason_code,
        error_message=retry_state.last_error_message,
        attempt_count=retry_state.attempt_count,
        retry_window_minutes=retry_state.retry_window_minutes,
        latency_ms=latency_ms,
        denylist=effective_denylist,
    )


def _as_non_empty_string(value: object) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _as_positive_int(value: object) -> int | None:
    if value is None:
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None
