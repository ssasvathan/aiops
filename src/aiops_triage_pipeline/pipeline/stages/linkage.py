"""ServiceNow linkage orchestration and CaseFile linkage.json persistence."""

from __future__ import annotations

from typing import Any, Mapping

from pydantic import BaseModel

from aiops_triage_pipeline.integrations.servicenow import (
    ServiceNowClient,
    ServiceNowLinkageWriteResult,
)
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
    linkage_casefile: CaseFileLinkageV1
    linkage_object_path: str


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
) -> ServiceNowLinkagePersistResult:
    """Execute ServiceNow linkage and persist linkage.json as a write-once stage file."""
    linkage_result = servicenow_client.upsert_problem_and_pir_tasks(
        case_id=case_id,
        pd_incident_id=pd_incident_id,
        incident_sys_id=incident_sys_id,
        summary=summary,
        pir_task_types=pir_task_types,
        context=context,
    )

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
    return ServiceNowLinkagePersistResult(
        linkage_result=linkage_result,
        linkage_casefile=linkage_casefile,
        linkage_object_path=linkage_object_path,
    )
