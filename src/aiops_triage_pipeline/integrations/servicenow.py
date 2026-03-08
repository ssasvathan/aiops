"""ServiceNow incident correlation adapter with tiered search strategy."""

from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field

from aiops_triage_pipeline.config.settings import IntegrationMode
from aiops_triage_pipeline.contracts.sn_linkage import ServiceNowLinkageContractV1
from aiops_triage_pipeline.logging.setup import get_logger

_CorrelationTier = Literal["tier1", "tier2", "tier3", "none"]


class ServiceNowCorrelationResult(BaseModel, frozen=True):
    """Structured result emitted by ServiceNow incident correlation."""

    matched: bool
    matched_tier: _CorrelationTier
    incident_sys_id: str | None = None
    reason: str
    reason_metadata: dict[str, Any] = Field(default_factory=dict)


class ServiceNowClient:
    """ServiceNow incident correlation adapter (read-only for Story 8.1)."""

    def __init__(
        self,
        mode: IntegrationMode = IntegrationMode.OFF,
        *,
        base_url: str | None = None,
        auth_token: str | None = None,
        linkage_contract: ServiceNowLinkageContractV1 | None = None,
        mock_match_tier: _CorrelationTier = "none",
    ) -> None:
        self._mode = mode
        self._base_url = base_url.rstrip("/") if base_url else None
        self._auth_token = auth_token
        self._contract = linkage_contract or ServiceNowLinkageContractV1()
        self._mock_match_tier = mock_match_tier
        self._logger = get_logger("integrations.servicenow")

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

        params = urllib.parse.urlencode(
            {
                "sysparm_query": query,
                "sysparm_limit": str(self._contract.max_results_per_tier),
                "sysparm_fields": self._build_sysparm_fields(),
            }
        )
        url = (
            f"{self._base_url}/api/now/table/{self._contract.incident_table}"
            f"?{params}"
        )
        headers = {"Accept": "application/json"}
        if self._auth_token:
            headers["Authorization"] = f"Bearer {self._auth_token}"
        request = urllib.request.Request(url, headers=headers, method="GET")

        start = time.monotonic()
        try:
            with urllib.request.urlopen(
                request, timeout=self._contract.live_timeout_seconds
            ) as response:
                raw = response.read()
            payload = json.loads(raw) if raw else {}
            records = payload.get("result", [])
            if not isinstance(records, list):
                raise ValueError("ServiceNow response 'result' must be a list")
            latency_ms = round((time.monotonic() - start) * 1000, 2)
            return records, "success" if records else "not_found", latency_ms, None
        except Exception as exc:  # noqa: BLE001 - errors are surfaced as structured outcomes
            latency_ms = round((time.monotonic() - start) * 1000, 2)
            return [], "error", latency_ms, str(exc)

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
