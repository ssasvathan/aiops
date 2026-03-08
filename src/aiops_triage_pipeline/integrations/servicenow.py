"""ServiceNow incident correlation adapter with tiered search and linkage upsert support."""

from __future__ import annotations

import hashlib
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Literal, Mapping
from uuid import uuid4

from pydantic import BaseModel, Field

from aiops_triage_pipeline.config.settings import IntegrationMode
from aiops_triage_pipeline.contracts.sn_linkage import ServiceNowLinkageContractV1
from aiops_triage_pipeline.denylist.enforcement import apply_denylist
from aiops_triage_pipeline.denylist.loader import DenylistV1
from aiops_triage_pipeline.logging.setup import get_logger

_CorrelationTier = Literal["tier1", "tier2", "tier3", "none"]
_UpsertOutcome = Literal["created", "updated", "skipped", "failed"]
_LinkageStatus = Literal["linked", "not-linked", "skipped", "failed"]
_LinkageState = Literal["PENDING", "SEARCHING", "FAILED_TEMP", "LINKED", "FAILED_FINAL"]


class ServiceNowCorrelationResult(BaseModel, frozen=True):
    """Structured result emitted by ServiceNow incident correlation."""

    matched: bool
    matched_tier: _CorrelationTier
    incident_sys_id: str | None = None
    reason: str
    reason_metadata: dict[str, Any] = Field(default_factory=dict)


class ServiceNowUpsertResult(BaseModel, frozen=True):
    """Structured result for a single ServiceNow upsert operation."""

    table: str
    external_id: str
    outcome: _UpsertOutcome
    reason: str
    request_id: str
    sys_id: str | None = None
    reason_metadata: dict[str, Any] = Field(default_factory=dict)


class ServiceNowLinkageWriteResult(BaseModel, frozen=True):
    """Structured linkage outcome for Problem/PIR orchestration."""

    linkage_status: _LinkageStatus
    linkage_reason: str
    request_id: str
    incident_sys_id: str | None = None
    problem_sys_id: str | None = None
    problem_external_id: str | None = None
    pir_task_sys_ids: tuple[str, ...] = ()
    pir_task_external_ids: tuple[str, ...] = ()
    linkage_state: _LinkageState | None = None
    retryable: bool | None = None
    next_attempt_at: datetime | None = None
    reason_metadata: dict[str, Any] = Field(default_factory=dict)


class ServiceNowClient:
    """ServiceNow incident correlation adapter plus idempotent Problem/PIR upsert paths."""

    def __init__(
        self,
        mode: IntegrationMode = IntegrationMode.OFF,
        *,
        base_url: str | None = None,
        auth_token: str | None = None,
        linkage_contract: ServiceNowLinkageContractV1 | None = None,
        mock_match_tier: _CorrelationTier = "none",
        denylist: DenylistV1 | None = None,
    ) -> None:
        self._mode = mode
        self._base_url = base_url.rstrip("/") if base_url else None
        self._auth_token = auth_token
        self._contract = linkage_contract or ServiceNowLinkageContractV1()
        self._mock_match_tier = mock_match_tier
        self._denylist = denylist or DenylistV1(
            denylist_version="unset",
            denied_field_names=(),
        )
        self._logger = get_logger("integrations.servicenow")
        self._mock_upsert_sys_ids: dict[tuple[str, str], str] = {}

    @property
    def linkage_contract(self) -> ServiceNowLinkageContractV1:
        """Return the active ServiceNow linkage contract."""
        return self._contract

    def correlate_incident(
        self,
        *,
        case_id: str,
        pd_incident_id: str,
        routing_key: str,
        keywords: tuple[str, ...] = (),
        case_timestamp: datetime | None = None,
    ) -> ServiceNowCorrelationResult:
        """Correlate a PD incident to a ServiceNow incident via Tier 1 -> Tier 2 -> Tier 3."""
        request_id = uuid4().hex
        effective_timestamp = case_timestamp or datetime.now(timezone.utc)
        missing_fields = self._missing_required_values(
            case_id=case_id,
            pd_incident_id=pd_incident_id,
            routing_key=routing_key,
        )
        if missing_fields:
            return ServiceNowCorrelationResult(
                matched=False,
                matched_tier="none",
                reason="invalid_input",
                reason_metadata={
                    "request_id": request_id,
                    "missing_fields": missing_fields,
                },
            )
        tier_order = self._contract.correlation_strategy

        if self._mode == IntegrationMode.OFF:
            return ServiceNowCorrelationResult(
                matched=False,
                matched_tier="none",
                reason="mode_off",
                reason_metadata={"request_id": request_id},
            )

        if self._mode == IntegrationMode.LOG:
            for tier in tier_order:
                self._log_tier_attempt(
                    request_id=request_id,
                    case_id=case_id,
                    tier=tier,
                    outcome="planned",
                    latency_ms=0.0,
                )
            return ServiceNowCorrelationResult(
                matched=False,
                matched_tier="none",
                reason="mode_log_noop",
                reason_metadata={"request_id": request_id},
            )

        if self._mode == IntegrationMode.MOCK:
            return self._correlate_mock(request_id=request_id, case_id=case_id)

        return self._correlate_live(
            request_id=request_id,
            case_id=case_id,
            pd_incident_id=pd_incident_id,
            routing_key=routing_key,
            keywords=keywords,
            case_timestamp=effective_timestamp,
        )

    def build_problem_external_id(self, *, case_id: str, pd_incident_id: str) -> str:
        """Build deterministic external_id key for Problem upsert."""
        return self._build_external_id(
            kind="problem",
            case_id=case_id,
            pd_incident_id=pd_incident_id,
        )

    def build_pir_task_external_id(
        self,
        *,
        case_id: str,
        pd_incident_id: str,
        task_type: str,
    ) -> str:
        """Build deterministic external_id key for PIR task upsert."""
        return self._build_external_id(
            kind="pir-task",
            case_id=case_id,
            pd_incident_id=pd_incident_id,
            task_type=task_type,
        )

    def upsert_problem(
        self,
        *,
        case_id: str,
        pd_incident_id: str,
        incident_sys_id: str,
        summary: str,
        context: Mapping[str, Any] | None = None,
        request_id: str | None = None,
    ) -> ServiceNowUpsertResult:
        """Idempotently upsert a ServiceNow Problem record keyed by deterministic external_id."""
        resolved_request_id = request_id or uuid4().hex
        missing = self._missing_required_values(
            case_id=case_id,
            pd_incident_id=pd_incident_id,
            routing_key=incident_sys_id,
        )
        if missing:
            return ServiceNowUpsertResult(
                table=self._contract.problem_table,
                external_id="",
                outcome="failed",
                reason="invalid_input",
                request_id=resolved_request_id,
                reason_metadata={"missing_fields": missing},
            )

        external_id = self.build_problem_external_id(
            case_id=case_id,
            pd_incident_id=pd_incident_id,
        )
        payload = self._build_problem_payload(
            external_id=external_id,
            case_id=case_id,
            pd_incident_id=pd_incident_id,
            incident_sys_id=incident_sys_id,
            summary=summary,
            context=context,
        )
        return self._upsert_record(
            request_id=resolved_request_id,
            case_id=case_id,
            action="problem_upsert",
            table=self._contract.problem_table,
            external_id=external_id,
            payload=payload,
        )

    def upsert_pir_task(
        self,
        *,
        case_id: str,
        pd_incident_id: str,
        problem_sys_id: str,
        task_type: str,
        summary: str,
        context: Mapping[str, Any] | None = None,
        request_id: str | None = None,
    ) -> ServiceNowUpsertResult:
        """Idempotently upsert a ServiceNow PIR task record keyed by deterministic external_id."""
        resolved_request_id = request_id or uuid4().hex
        if not problem_sys_id.strip():
            return ServiceNowUpsertResult(
                table=self._contract.pir_task_table,
                external_id="",
                outcome="failed",
                reason="invalid_input",
                request_id=resolved_request_id,
                reason_metadata={"missing_fields": ("problem_sys_id",)},
            )
        missing = self._missing_required_values(
            case_id=case_id,
            pd_incident_id=pd_incident_id,
            routing_key=task_type,
        )
        if missing:
            return ServiceNowUpsertResult(
                table=self._contract.pir_task_table,
                external_id="",
                outcome="failed",
                reason="invalid_input",
                request_id=resolved_request_id,
                reason_metadata={"missing_fields": missing},
            )

        external_id = self.build_pir_task_external_id(
            case_id=case_id,
            pd_incident_id=pd_incident_id,
            task_type=task_type,
        )
        payload = self._build_pir_task_payload(
            external_id=external_id,
            case_id=case_id,
            pd_incident_id=pd_incident_id,
            problem_sys_id=problem_sys_id,
            task_type=task_type,
            summary=summary,
            context=context,
        )
        return self._upsert_record(
            request_id=resolved_request_id,
            case_id=case_id,
            action="pir_task_upsert",
            table=self._contract.pir_task_table,
            external_id=external_id,
            payload=payload,
        )

    def upsert_problem_and_pir_tasks(
        self,
        *,
        case_id: str,
        pd_incident_id: str,
        incident_sys_id: str | None,
        summary: str,
        pir_task_types: tuple[str, ...] = ("pir",),
        context: Mapping[str, Any] | None = None,
    ) -> ServiceNowLinkageWriteResult:
        """Cold-path linkage orchestration with structured outcomes and no raised errors."""
        request_id = uuid4().hex
        if incident_sys_id is None or not incident_sys_id.strip():
            return ServiceNowLinkageWriteResult(
                linkage_status="not-linked",
                linkage_reason="missing_incident_sys_id",
                request_id=request_id,
                incident_sys_id=incident_sys_id,
            )

        task_types = self._dedupe_preserve_order(pir_task_types)
        if not task_types:
            return ServiceNowLinkageWriteResult(
                linkage_status="failed",
                linkage_reason="invalid_input",
                request_id=request_id,
                incident_sys_id=incident_sys_id,
                reason_metadata={"missing_fields": ("pir_task_types",)},
            )
        try:
            problem = self.upsert_problem(
                case_id=case_id,
                pd_incident_id=pd_incident_id,
                incident_sys_id=incident_sys_id,
                summary=summary,
                context=context,
                request_id=request_id,
            )
            if problem.outcome == "failed":
                problem_metadata = {"problem_reason": problem.reason, **problem.reason_metadata}
                return ServiceNowLinkageWriteResult(
                    linkage_status="failed",
                    linkage_reason="upsert_error",
                    request_id=request_id,
                    incident_sys_id=incident_sys_id,
                    problem_external_id=problem.external_id,
                    reason_metadata=problem_metadata,
                )
            if problem.outcome == "skipped":
                return ServiceNowLinkageWriteResult(
                    linkage_status="skipped",
                    linkage_reason=problem.reason,
                    request_id=request_id,
                    incident_sys_id=incident_sys_id,
                    problem_external_id=problem.external_id,
                )
            if problem.sys_id is None:
                return ServiceNowLinkageWriteResult(
                    linkage_status="failed",
                    linkage_reason="upsert_error",
                    request_id=request_id,
                    incident_sys_id=incident_sys_id,
                    problem_external_id=problem.external_id,
                    reason_metadata={"problem_reason": "missing_problem_sys_id"},
                )

            pir_task_sys_ids: list[str] = []
            pir_task_external_ids: list[str] = []
            for task_type in task_types:
                upsert = self.upsert_pir_task(
                    case_id=case_id,
                    pd_incident_id=pd_incident_id,
                    problem_sys_id=problem.sys_id,
                    task_type=task_type,
                    summary=summary,
                    context=context,
                    request_id=request_id,
                )
                pir_task_external_ids.append(upsert.external_id)
                if upsert.outcome == "failed":
                    pir_metadata = {"pir_task_reason": upsert.reason, **upsert.reason_metadata}
                    return ServiceNowLinkageWriteResult(
                        linkage_status="failed",
                        linkage_reason="upsert_error",
                        request_id=request_id,
                        incident_sys_id=incident_sys_id,
                        problem_sys_id=problem.sys_id,
                        problem_external_id=problem.external_id,
                        pir_task_sys_ids=tuple(pir_task_sys_ids),
                        pir_task_external_ids=tuple(pir_task_external_ids),
                        reason_metadata=pir_metadata,
                    )
                if upsert.outcome == "skipped":
                    return ServiceNowLinkageWriteResult(
                        linkage_status="skipped",
                        linkage_reason=upsert.reason,
                        request_id=request_id,
                        incident_sys_id=incident_sys_id,
                        problem_sys_id=problem.sys_id,
                        problem_external_id=problem.external_id,
                        pir_task_external_ids=tuple(pir_task_external_ids),
                    )
                if upsert.sys_id is not None:
                    pir_task_sys_ids.append(upsert.sys_id)

            return ServiceNowLinkageWriteResult(
                linkage_status="linked",
                linkage_reason="linked",
                request_id=request_id,
                incident_sys_id=incident_sys_id,
                problem_sys_id=problem.sys_id,
                problem_external_id=problem.external_id,
                pir_task_sys_ids=tuple(pir_task_sys_ids),
                pir_task_external_ids=tuple(pir_task_external_ids),
            )
        except Exception as exc:  # noqa: BLE001 - orchestration must never break hot-path completion
            return ServiceNowLinkageWriteResult(
                linkage_status="failed",
                linkage_reason="upsert_error",
                request_id=request_id,
                incident_sys_id=incident_sys_id,
                reason_metadata=self._build_error_metadata(str(exc)),
            )

    def _correlate_mock(
        self,
        *,
        request_id: str,
        case_id: str,
    ) -> ServiceNowCorrelationResult:
        for tier in self._contract.correlation_strategy:
            if tier == self._mock_match_tier:
                self._log_tier_attempt(
                    request_id=request_id,
                    case_id=case_id,
                    tier=tier,
                    outcome="mock_match",
                    latency_ms=0.0,
                )
                return ServiceNowCorrelationResult(
                    matched=True,
                    matched_tier=tier,
                    incident_sys_id=f"mock-{tier}-sys-id",
                    reason="mock_match",
                    reason_metadata={"request_id": request_id},
                )
            self._log_tier_attempt(
                request_id=request_id,
                case_id=case_id,
                tier=tier,
                outcome="not_found",
                latency_ms=0.0,
            )

        return ServiceNowCorrelationResult(
            matched=False,
            matched_tier="none",
            reason="not_found",
            reason_metadata={"request_id": request_id},
        )

    def _correlate_live(
        self,
        *,
        request_id: str,
        case_id: str,
        pd_incident_id: str,
        routing_key: str,
        keywords: tuple[str, ...],
        case_timestamp: datetime,
    ) -> ServiceNowCorrelationResult:
        if not self._base_url:
            return ServiceNowCorrelationResult(
                matched=False,
                matched_tier="none",
                reason="missing_base_url",
                reason_metadata={"request_id": request_id},
            )

        query_by_tier_map = {
            "tier1": self._build_tier1_query(pd_incident_id),
            "tier2": self._build_tier2_query(pd_incident_id, case_id, routing_key, keywords),
            "tier3": self._build_tier3_query(routing_key, case_timestamp),
        }
        query_by_tier = (
            (tier, query_by_tier_map[tier]) for tier in self._contract.correlation_strategy
        )
        errors: list[str] = []

        for tier, query in query_by_tier:
            incidents, outcome, latency_ms, error = self._query_incidents(query=query)
            self._log_tier_attempt(
                request_id=request_id,
                case_id=case_id,
                tier=tier,
                outcome=outcome,
                latency_ms=latency_ms,
                error=error,
            )
            if incidents:
                incident = self._rank_incidents(incidents)[0]
                return ServiceNowCorrelationResult(
                    matched=True,
                    matched_tier=tier,
                    incident_sys_id=self._coerce_to_string(incident.get("sys_id")),
                    reason="match_found",
                    reason_metadata={
                        "request_id": request_id,
                        "incident_number": self._coerce_to_string(incident.get("number")),
                    },
                )
            if error:
                errors.append(error)

        return ServiceNowCorrelationResult(
            matched=False,
            matched_tier="none",
            reason="not_found" if not errors else "search_error",
            reason_metadata={"request_id": request_id, "errors": tuple(errors)},
        )

    def _build_tier1_query(self, pd_incident_id: str) -> str:
        escaped_pd_incident_id = self._escape_query_value(pd_incident_id)
        return "^NQ".join(
            f"{field}={escaped_pd_incident_id}" for field in self._contract.tier1_correlation_fields
        )

    def _build_tier2_query(
        self,
        pd_incident_id: str,
        case_id: str,
        routing_key: str,
        keywords: tuple[str, ...],
    ) -> str:
        search_tokens = self._dedupe_preserve_order(
            (pd_incident_id, case_id, routing_key, *keywords)
        )
        text_fields = list(self._contract.tier2_text_fields)
        if self._contract.tier2_include_work_notes and "work_notes" not in text_fields:
            text_fields.append("work_notes")

        clauses: list[str] = []
        for token in search_tokens:
            escaped_token = self._escape_query_value(token)
            for field in text_fields:
                clauses.append(f"{field}LIKE{escaped_token}")
        return "^NQ".join(clauses)

    def _build_tier3_query(self, routing_key: str, case_timestamp: datetime) -> str:
        effective_case_timestamp = case_timestamp.astimezone(timezone.utc)
        window = timedelta(minutes=self._contract.tier3_window_minutes)
        window_start = (effective_case_timestamp - window).strftime("%Y-%m-%d %H:%M:%S")
        window_end = effective_case_timestamp.strftime("%Y-%m-%d %H:%M:%S")
        escaped_routing_key = self._escape_query_value(routing_key)

        routing_clauses = [
            f"sys_created_on>={window_start}^sys_created_on<={window_end}^short_descriptionLIKE{escaped_routing_key}",
            f"sys_created_on>={window_start}^sys_created_on<={window_end}^descriptionLIKE{escaped_routing_key}",
        ]

        if self._contract.tier2_include_work_notes:
            routing_clauses.append(
                f"sys_created_on>={window_start}^sys_created_on<={window_end}^work_notesLIKE{escaped_routing_key}"
            )

        if self._contract.tier3_assignment_groups:
            for assignment_group in self._contract.tier3_assignment_groups:
                escaped_group = self._escape_query_value(assignment_group)
                routing_clauses.append(
                    f"sys_created_on>={window_start}^sys_created_on<={window_end}^assignment_group={escaped_group}^short_descriptionLIKE{escaped_routing_key}"
                )

        return "^NQ".join(routing_clauses)

    def _query_incidents(
        self,
        *,
        query: str,
    ) -> tuple[list[dict[str, Any]], str, float, str | None]:
        if not self._base_url:
            return [], "error", 0.0, "missing_base_url"

        params = {
            "sysparm_query": query,
            "sysparm_limit": str(self._contract.max_results_per_tier),
            "sysparm_fields": self._build_sysparm_fields(),
        }
        records, latency_ms, error = self._request_records(
            method="GET",
            table=self._contract.incident_table,
            params=params,
        )
        if error:
            return [], "error", latency_ms, error
        return records, "success" if records else "not_found", latency_ms, None

    def _upsert_record(
        self,
        *,
        request_id: str,
        case_id: str,
        action: str,
        table: str,
        external_id: str,
        payload: dict[str, Any],
    ) -> ServiceNowUpsertResult:
        self._assert_write_scope(table=table)

        if self._mode == IntegrationMode.OFF:
            self._log_write_attempt(
                request_id=request_id,
                case_id=case_id,
                action=action,
                outcome="mode_off",
                latency_ms=0.0,
                sys_ids_touched=(),
            )
            return ServiceNowUpsertResult(
                table=table,
                external_id=external_id,
                outcome="skipped",
                reason="mode_off",
                request_id=request_id,
            )

        if self._mode == IntegrationMode.LOG:
            self._log_write_attempt(
                request_id=request_id,
                case_id=case_id,
                action=action,
                outcome="mode_log_noop",
                latency_ms=0.0,
                sys_ids_touched=(),
            )
            return ServiceNowUpsertResult(
                table=table,
                external_id=external_id,
                outcome="skipped",
                reason="mode_log_noop",
                request_id=request_id,
            )

        if self._mode == IntegrationMode.MOCK:
            key = (table, external_id)
            existing = self._mock_upsert_sys_ids.get(key)
            if existing is None:
                generated = hashlib.sha256("|".join(key).encode("utf-8")).hexdigest()[:12]
                existing = f"mock-{generated}"
                self._mock_upsert_sys_ids[key] = existing
                outcome = "created"
            else:
                outcome = "updated"
            self._log_write_attempt(
                request_id=request_id,
                case_id=case_id,
                action=action,
                outcome=outcome,
                latency_ms=0.0,
                sys_ids_touched=(existing,),
            )
            return ServiceNowUpsertResult(
                table=table,
                external_id=external_id,
                outcome=outcome,
                reason="mock_upsert",
                request_id=request_id,
                sys_id=existing,
            )

        if not self._base_url:
            return ServiceNowUpsertResult(
                table=table,
                external_id=external_id,
                outcome="failed",
                reason="missing_base_url",
                request_id=request_id,
            )

        lookup_params = {
            "sysparm_query": (
                f"{self._contract.external_id_field}={self._escape_query_value(external_id)}"
            ),
            "sysparm_limit": str(self._contract.max_upsert_lookup_results),
            "sysparm_fields": f"sys_id,{self._contract.external_id_field}",
        }
        records, lookup_latency_ms, lookup_error = self._request_records(
            method="GET",
            table=table,
            params=lookup_params,
        )
        if lookup_error:
            self._log_write_attempt(
                request_id=request_id,
                case_id=case_id,
                action=action,
                outcome="lookup_error",
                latency_ms=lookup_latency_ms,
                sys_ids_touched=(),
                error=lookup_error,
            )
            return ServiceNowUpsertResult(
                table=table,
                external_id=external_id,
                outcome="failed",
                reason="lookup_error",
                request_id=request_id,
                reason_metadata=self._build_error_metadata(lookup_error),
            )

        try:
            existing_sys_id = self._extract_existing_sys_id(records)
        except ValueError as exc:
            self._log_write_attempt(
                request_id=request_id,
                case_id=case_id,
                action=action,
                outcome="lookup_error",
                latency_ms=lookup_latency_ms,
                sys_ids_touched=(),
                error=str(exc),
            )
            return ServiceNowUpsertResult(
                table=table,
                external_id=external_id,
                outcome="failed",
                reason="lookup_error",
                request_id=request_id,
                reason_metadata=self._build_error_metadata(str(exc)),
            )

        if existing_sys_id is None:
            write_result, write_latency_ms, write_error = self._request_record_mutation(
                method="POST",
                table=table,
                payload=payload,
            )
            total_latency_ms = round(lookup_latency_ms + write_latency_ms, 2)
            if write_error:
                self._log_write_attempt(
                    request_id=request_id,
                    case_id=case_id,
                    action=action,
                    outcome="create_error",
                    latency_ms=total_latency_ms,
                    sys_ids_touched=(),
                    error=write_error,
                )
                return ServiceNowUpsertResult(
                    table=table,
                    external_id=external_id,
                    outcome="failed",
                    reason="create_error",
                    request_id=request_id,
                    reason_metadata=self._build_error_metadata(write_error),
                )
            created_sys_id = self._extract_sys_id_from_result(write_result)
            if created_sys_id is None:
                self._log_write_attempt(
                    request_id=request_id,
                    case_id=case_id,
                    action=action,
                    outcome="create_error",
                    latency_ms=total_latency_ms,
                    sys_ids_touched=(),
                    error="missing_sys_id",
                )
                return ServiceNowUpsertResult(
                    table=table,
                    external_id=external_id,
                    outcome="failed",
                    reason="create_error",
                    request_id=request_id,
                    reason_metadata=self._build_error_metadata("missing_sys_id"),
                )

            self._log_write_attempt(
                request_id=request_id,
                case_id=case_id,
                action=action,
                outcome="created",
                latency_ms=total_latency_ms,
                sys_ids_touched=(created_sys_id,),
            )
            return ServiceNowUpsertResult(
                table=table,
                external_id=external_id,
                outcome="created",
                reason="created",
                request_id=request_id,
                sys_id=created_sys_id,
            )

        write_result, write_latency_ms, write_error = self._request_record_mutation(
            method="PATCH",
            table=table,
            payload=payload,
            record_sys_id=existing_sys_id,
        )
        total_latency_ms = round(lookup_latency_ms + write_latency_ms, 2)
        if write_error:
            self._log_write_attempt(
                request_id=request_id,
                case_id=case_id,
                action=action,
                outcome="update_error",
                latency_ms=total_latency_ms,
                sys_ids_touched=(existing_sys_id,),
                error=write_error,
            )
            return ServiceNowUpsertResult(
                table=table,
                external_id=external_id,
                outcome="failed",
                reason="update_error",
                request_id=request_id,
                reason_metadata=self._build_error_metadata(write_error),
            )

        resolved_sys_id = self._extract_sys_id_from_result(write_result) or existing_sys_id
        self._log_write_attempt(
            request_id=request_id,
            case_id=case_id,
            action=action,
            outcome="updated",
            latency_ms=total_latency_ms,
            sys_ids_touched=(resolved_sys_id,),
        )
        return ServiceNowUpsertResult(
            table=table,
            external_id=external_id,
            outcome="updated",
            reason="updated",
            request_id=request_id,
            sys_id=resolved_sys_id,
        )

    def _request_records(
        self,
        *,
        method: Literal["GET"],
        table: str,
        params: Mapping[str, str],
    ) -> tuple[list[dict[str, Any]], float, str | None]:
        request = urllib.request.Request(
            self._build_table_url(table=table, params=params),
            headers=self._build_headers(),
            method=method,
        )
        start = time.monotonic()
        try:
            with urllib.request.urlopen(
                request,
                timeout=self._contract.live_timeout_seconds,
            ) as response:
                raw = response.read()
            payload = json.loads(raw) if raw else {}
            result = payload.get("result", [])
            if isinstance(result, dict):
                result = [result]
            if not isinstance(result, list):
                raise ValueError("ServiceNow response 'result' must be a list or object")
            records = [entry for entry in result if isinstance(entry, dict)]
            latency_ms = round((time.monotonic() - start) * 1000, 2)
            return records, latency_ms, None
        except urllib.error.HTTPError as exc:
            latency_ms = round((time.monotonic() - start) * 1000, 2)
            return [], latency_ms, self._format_http_error(exc)
        except Exception as exc:  # noqa: BLE001 - surfaced as structured outcomes
            latency_ms = round((time.monotonic() - start) * 1000, 2)
            return [], latency_ms, str(exc)

    def _request_record_mutation(
        self,
        *,
        method: Literal["POST", "PATCH"],
        table: str,
        payload: Mapping[str, Any],
        record_sys_id: str | None = None,
    ) -> tuple[dict[str, Any], float, str | None]:
        body = json.dumps(payload, sort_keys=True).encode("utf-8")
        headers = self._build_headers()
        headers["Content-Type"] = "application/json"
        request = urllib.request.Request(
            self._build_table_url(table=table, record_sys_id=record_sys_id),
            headers=headers,
            method=method,
            data=body,
        )
        start = time.monotonic()
        try:
            with urllib.request.urlopen(
                request,
                timeout=self._contract.live_timeout_seconds,
            ) as response:
                raw = response.read()
            parsed = json.loads(raw) if raw else {}
            result = parsed.get("result", {})
            if isinstance(result, list):
                result = result[0] if result else {}
            if not isinstance(result, dict):
                result = {}
            latency_ms = round((time.monotonic() - start) * 1000, 2)
            return result, latency_ms, None
        except urllib.error.HTTPError as exc:
            latency_ms = round((time.monotonic() - start) * 1000, 2)
            return {}, latency_ms, self._format_http_error(exc)
        except Exception as exc:  # noqa: BLE001 - surfaced as structured outcomes
            latency_ms = round((time.monotonic() - start) * 1000, 2)
            return {}, latency_ms, str(exc)

    def _build_problem_payload(
        self,
        *,
        external_id: str,
        case_id: str,
        pd_incident_id: str,
        incident_sys_id: str,
        summary: str,
        context: Mapping[str, Any] | None,
    ) -> dict[str, Any]:
        payload = {
            self._contract.external_id_field: external_id,
            "short_description": summary.strip() or f"AIOps case {case_id}",
            "description": self._build_description(
                case_id=case_id,
                pd_incident_id=pd_incident_id,
                incident_sys_id=incident_sys_id,
                context=context,
            ),
        }
        return self._sanitize_payload_for_write(
            table=self._contract.problem_table,
            payload=payload,
            required_fields=(self._contract.external_id_field,),
        )

    def _build_pir_task_payload(
        self,
        *,
        external_id: str,
        case_id: str,
        pd_incident_id: str,
        problem_sys_id: str,
        task_type: str,
        summary: str,
        context: Mapping[str, Any] | None,
    ) -> dict[str, Any]:
        payload = {
            self._contract.external_id_field: external_id,
            "problem": problem_sys_id,
            "short_description": f"{task_type}: {summary.strip()}",
            "description": self._build_description(
                case_id=case_id,
                pd_incident_id=pd_incident_id,
                problem_sys_id=problem_sys_id,
                context={"task_type": task_type, **(dict(context or {}))},
            ),
        }
        return self._sanitize_payload_for_write(
            table=self._contract.pir_task_table,
            payload=payload,
            required_fields=(self._contract.external_id_field, "problem"),
        )

    def _sanitize_payload_for_write(
        self,
        *,
        table: str,
        payload: dict[str, Any],
        required_fields: tuple[str, ...],
    ) -> dict[str, Any]:
        sanitized = apply_denylist(dict(payload), self._denylist)
        for field_name in required_fields:
            if field_name in payload:
                sanitized[field_name] = payload[field_name]
        if "short_description" not in sanitized:
            sanitized["short_description"] = "AIOps linkage update"
        if "description" not in sanitized:
            sanitized["description"] = json.dumps({"source": "aiops"}, sort_keys=True)
        self._assert_write_scope(table=table)
        self._assert_mi_guardrails(table=table, payload=sanitized)
        return sanitized

    def _build_description(
        self,
        *,
        case_id: str,
        pd_incident_id: str,
        incident_sys_id: str | None = None,
        problem_sys_id: str | None = None,
        context: Mapping[str, Any] | None,
    ) -> str:
        description_payload = {
            "case_id": case_id,
            "pd_incident_id": pd_incident_id,
            "context": dict(context or {}),
        }
        if incident_sys_id is not None and incident_sys_id.strip():
            description_payload["incident_sys_id"] = incident_sys_id
        if problem_sys_id is not None and problem_sys_id.strip():
            description_payload["problem_sys_id"] = problem_sys_id
        sanitized_description = apply_denylist(description_payload, self._denylist)
        return json.dumps(sanitized_description, sort_keys=True)

    def _assert_write_scope(self, *, table: str) -> None:
        allowed = {self._contract.problem_table, self._contract.pir_task_table}
        if table not in allowed:
            raise ValueError("write scope violation: only Problem/PIR task tables are allowed")
        if table == self._contract.incident_table:
            raise ValueError("write scope violation: incident table is read-only")

    def _assert_mi_guardrails(self, *, table: str, payload: Mapping[str, Any]) -> None:
        if self._contract.mi_creation_allowed:
            return
        if "major_incident" in table.lower():
            raise ValueError("MI-1 posture violation: major incident table writes are disallowed")
        lowered_payload = json.dumps(payload, sort_keys=True).lower()
        if "major incident" in lowered_payload or "major_incident" in lowered_payload:
            raise ValueError("MI-1 posture violation: major incident fields are disallowed")

    def _build_external_id(
        self,
        *,
        kind: str,
        case_id: str,
        pd_incident_id: str,
        task_type: str | None = None,
    ) -> str:
        normalized_case_id = case_id.strip()
        normalized_pd_incident_id = pd_incident_id.strip()
        normalized_task_type = task_type.strip() if task_type else None
        base_parts = [normalized_case_id, normalized_pd_incident_id]
        if normalized_task_type:
            base_parts.append(normalized_task_type)
        digest = hashlib.sha256("|".join(base_parts).encode("utf-8")).hexdigest()[:12]
        if normalized_task_type:
            return (
                f"aiops:{kind}:{normalized_case_id}:{normalized_pd_incident_id}:"
                f"{digest}:{normalized_task_type}"
            )
        return f"aiops:{kind}:{normalized_case_id}:{normalized_pd_incident_id}:{digest}"

    def _extract_existing_sys_id(self, records: list[dict[str, Any]]) -> str | None:
        if not records:
            return None
        distinct_sys_ids = sorted(
            {
                sys_id
                for sys_id in (
                    self._coerce_to_string(record.get("sys_id")) for record in records
                )
                if sys_id
            }
        )
        if not distinct_sys_ids:
            return None
        if len(distinct_sys_ids) > 1:
            raise ValueError(
                "multiple existing records found for external_id: "
                + ",".join(distinct_sys_ids)
            )
        return distinct_sys_ids[0]

    @staticmethod
    def _extract_sys_id_from_result(result: Mapping[str, Any]) -> str | None:
        return ServiceNowClient._coerce_to_string(result.get("sys_id"))

    def _build_table_url(
        self,
        *,
        table: str,
        params: Mapping[str, str] | None = None,
        record_sys_id: str | None = None,
    ) -> str:
        if not self._base_url:
            raise ValueError("ServiceNow base_url is required for LIVE mode")
        encoded_table = urllib.parse.quote(table, safe="")
        url = f"{self._base_url}/api/now/table/{encoded_table}"
        if record_sys_id:
            url = f"{url}/{urllib.parse.quote(record_sys_id, safe='')}"
        if params:
            url = f"{url}?{urllib.parse.urlencode(dict(params))}"
        return url

    def _build_headers(self) -> dict[str, str]:
        headers = {"Accept": "application/json"}
        if self._auth_token:
            headers["Authorization"] = f"Bearer {self._auth_token}"
        return headers

    def _log_tier_attempt(
        self,
        *,
        request_id: str,
        case_id: str,
        tier: str,
        outcome: str,
        latency_ms: float,
        error: str | None = None,
    ) -> None:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "request_id": request_id,
            "case_id": case_id,
            "action": "incident_search",
            "outcome": outcome,
            "latency_ms": latency_ms,
            "tier": tier,
            "mode": self._mode.value,
        }
        if error:
            payload["error"] = error
        self._logger.info("sn_correlation_tier_attempt", **payload)

    def _log_write_attempt(
        self,
        *,
        request_id: str,
        case_id: str,
        action: str,
        outcome: str,
        latency_ms: float,
        sys_ids_touched: tuple[str, ...],
        error: str | None = None,
    ) -> None:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "request_id": request_id,
            "case_id": case_id,
            "action": action,
            "outcome": outcome,
            "latency_ms": latency_ms,
            "sys_ids_touched": sys_ids_touched,
            "mode": self._mode.value,
        }
        if error:
            payload["error"] = error
        self._logger.info("sn_write_attempt", **payload)

    @staticmethod
    def _format_http_error(exc: urllib.error.HTTPError) -> str:
        parts = [f"http_status={exc.code}"]
        retry_after = ServiceNowClient._parse_retry_after_header(
            exc.headers.get("Retry-After") if exc.headers else None
        )
        if retry_after is not None:
            parts.append(f"retry_after_seconds={retry_after}")
        if exc.reason:
            parts.append(f"reason={exc.reason}")
        return ";".join(parts)

    @classmethod
    def _build_error_metadata(cls, error: str | None) -> dict[str, Any]:
        if not error:
            return {}
        metadata: dict[str, Any] = {"error": error}
        error_code = cls._extract_error_code(error)
        if error_code is not None:
            metadata["error_code"] = error_code
        retry_after = cls._extract_retry_after_seconds(error)
        if retry_after is not None:
            metadata["retry_after_seconds"] = retry_after
        return metadata

    @staticmethod
    def _extract_error_code(error: str) -> str | None:
        normalized = error.lower()
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
            for marker in ("connection refused", "connection reset", "connection aborted")
        ):
            return "connection_error"
        return None

    @staticmethod
    def _extract_retry_after_seconds(error: str) -> int | None:
        marker = "retry_after_seconds="
        if marker not in error:
            return None
        try:
            value = error.split(marker, 1)[1].split(";", 1)[0].strip()
            parsed = int(value)
            return parsed if parsed > 0 else None
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _parse_retry_after_header(value: str | None) -> int | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            return None
        if normalized.isdigit():
            parsed = int(normalized)
            return parsed if parsed > 0 else None
        try:
            parsed_dt = parsedate_to_datetime(normalized)
        except (TypeError, ValueError):
            return None
        if parsed_dt.tzinfo is None:
            parsed_dt = parsed_dt.replace(tzinfo=timezone.utc)
        delta_seconds = int((parsed_dt - datetime.now(timezone.utc)).total_seconds())
        return max(delta_seconds, 1)

    @staticmethod
    def _escape_query_value(value: str) -> str:
        return value.replace("^", "")

    @staticmethod
    def _dedupe_preserve_order(items: tuple[str, ...]) -> tuple[str, ...]:
        deduped: list[str] = []
        seen: set[str] = set()
        for item in items:
            if not item or item in seen:
                continue
            seen.add(item)
            deduped.append(item)
        return tuple(deduped)

    @staticmethod
    def _coerce_to_string(value: object) -> str | None:
        if value is None:
            return None
        return str(value)

    @staticmethod
    def _missing_required_values(
        *,
        case_id: str,
        pd_incident_id: str,
        routing_key: str,
    ) -> tuple[str, ...]:
        missing: list[str] = []
        if not case_id.strip():
            missing.append("case_id")
        if not pd_incident_id.strip():
            missing.append("pd_incident_id")
        if not routing_key.strip():
            missing.append("routing_key")
        return tuple(missing)

    def _build_sysparm_fields(self) -> str:
        fields = [
            "sys_id",
            "number",
            "short_description",
            "description",
            "sys_created_on",
        ]
        if self._contract.tier2_include_work_notes:
            fields.append("work_notes")
        return ",".join(fields)

    @classmethod
    def _rank_incidents(cls, incidents: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return sorted(
            incidents,
            key=lambda incident: (
                cls._parse_created_on(cls._coerce_to_string(incident.get("sys_created_on"))),
                cls._coerce_to_string(incident.get("sys_id")) or "",
            ),
            reverse=True,
        )

    @staticmethod
    def _parse_created_on(value: str | None) -> datetime:
        if not value:
            return datetime.min.replace(tzinfo=timezone.utc)
        normalized = value.replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(normalized)
            if parsed.tzinfo is None:
                return parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc)
        except ValueError:
            pass
        try:
            return datetime.strptime(value, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
        except ValueError:
            return datetime.min.replace(tzinfo=timezone.utc)
