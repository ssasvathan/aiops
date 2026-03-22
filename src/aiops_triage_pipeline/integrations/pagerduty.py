"""PagerDuty Events V2 integration for PAGE action dispatch."""

import json
import time
import urllib.request
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel

from aiops_triage_pipeline.denylist.enforcement import apply_denylist
from aiops_triage_pipeline.denylist.loader import DenylistV1
from aiops_triage_pipeline.logging.setup import get_logger

_PD_EVENTS_V2_URL = "https://events.pagerduty.com/v2/enqueue"


class PagerDutyIntegrationMode(str, Enum):
    """PagerDuty notification mode (mirrors SlackIntegrationMode pattern).

    OFF  — Silently drop all trigger requests; no log, no HTTP.
    LOG  — Log the trigger payload only; no HTTP call.
    MOCK — Log the trigger payload and increment mock_send_count; no HTTP call.
    LIVE — Log the trigger payload and POST to PD Events V2 API.
    """

    OFF = "OFF"
    LOG = "LOG"
    MOCK = "MOCK"
    LIVE = "LIVE"


class PageTriggerPayload(BaseModel, frozen=True):
    """PD Events V2 trigger payload (canonical shape per API spec)."""

    routing_key: str
    dedup_key: str
    event_action: Literal["trigger"] = "trigger"
    payload: dict[str, Any]


class PagerDutyClient:
    """PagerDuty Events V2 client for PAGE action dispatch.

    All non-OFF modes emit a structured log entry first.
    HTTP calls only occur in LIVE mode.

    Args:
        mode:           Integration mode controlling trigger behavior.
        pd_routing_key: PD Events V2 service integration key (used as routing_key
                        in the API request). Required for LIVE mode; optional
                        otherwise.
    """

    def __init__(
        self,
        mode: PagerDutyIntegrationMode = PagerDutyIntegrationMode.OFF,
        pd_routing_key: str | None = None,
    ) -> None:
        self._mode = mode
        self._pd_routing_key = pd_routing_key
        self._mock_send_count: int = 0

    @property
    def mode(self) -> PagerDutyIntegrationMode:
        return self._mode

    @property
    def mock_send_count(self) -> int:
        """Number of triggers dispatched in MOCK mode (simulating successful sends)."""
        return self._mock_send_count

    def send_page_trigger(
        self,
        *,
        case_id: str,
        action_fingerprint: str,
        routing_key: str,
        summary: str,
        denylist: DenylistV1 | None = None,
    ) -> None:
        """Send a PAGE trigger to PagerDuty according to the configured integration mode.

        In OFF mode, the trigger is silently dropped — no log, no HTTP.
        In LOG and MOCK modes, a structured log entry is emitted; no HTTP call is made.
        In LIVE mode, a structured log entry is emitted and HTTP delivery is attempted.

        The ``dedup_key`` is always set to ``action_fingerprint``, which is the stable
        case identity token. PagerDuty uses this to correlate/deduplicate incidents
        (stable pd_incident_id per FR43).

        Args:
            case_id:           Case identifier for audit traceability (NFR-S6).
            action_fingerprint: Stable fingerprint → used as PD dedup_key.
            routing_key:       Topology routing key (goes into custom_details, NOT
                               the PD service key).
            summary:           Human-readable description of the incident.
        """
        if self._mode == PagerDutyIntegrationMode.OFF:
            return

        logger = get_logger("integrations.pagerduty")
        sanitized = apply_denylist(
            {
                "case_id": case_id,
                "action_fingerprint": action_fingerprint,
                "topology_routing_key": routing_key,
                "summary": summary,
            },
            denylist,
        ) if denylist is not None else {
            "case_id": case_id,
            "action_fingerprint": action_fingerprint,
            "topology_routing_key": routing_key,
            "summary": summary,
        }
        sanitized_case_id = str(sanitized.get("case_id", "[redacted]"))
        sanitized_action_fingerprint = str(sanitized.get("action_fingerprint", "[redacted]"))
        sanitized_topology_routing_key = str(
            sanitized.get("topology_routing_key", "[redacted]")
        )
        sanitized_summary = str(sanitized.get("summary", "[redacted]"))
        logger.info(
            "pd_page_trigger_dispatch",
            event_type="integrations.pagerduty.trigger",
            case_id=sanitized_case_id,
            action_fingerprint=sanitized_action_fingerprint,
            topology_routing_key=sanitized_topology_routing_key,
            mode=self._mode.value,
            summary=sanitized_summary,
        )

        if self._mode == PagerDutyIntegrationMode.LOG:
            return

        if self._mode == PagerDutyIntegrationMode.MOCK:
            self._mock_send_count += 1
            return

        # LIVE mode — attempt PD Events V2 delivery
        self._send_live(
            case_id=sanitized_case_id,
            action_fingerprint=action_fingerprint,
            sanitized_action_fingerprint=sanitized_action_fingerprint,
            routing_key=sanitized_topology_routing_key,
            summary=sanitized_summary,
            logger=logger,
        )

    def _send_live(
        self,
        *,
        case_id: str,
        action_fingerprint: str,
        sanitized_action_fingerprint: str,
        routing_key: str,
        summary: str,
        logger: object,
    ) -> None:
        """POST trigger to PD Events V2. Catches and logs all HTTP errors (non-critical)."""
        _log = logger  # type: ignore[assignment]

        if not self._pd_routing_key:
            _log.warning(
                "pd_page_trigger_no_routing_key",
                event_type="integrations.pagerduty.no_routing_key",
                case_id=case_id,
                action_fingerprint=action_fingerprint,
                mode=self._mode.value,
            )
            return

        trigger = PageTriggerPayload(
            routing_key=self._pd_routing_key,
            dedup_key=action_fingerprint,
            payload={
                "summary": summary,
                "severity": "critical",
                "source": "aiops-triage-pipeline",
                "custom_details": {
                    "case_id": case_id,
                    "topology_routing_key": routing_key,
                    "action_fingerprint": sanitized_action_fingerprint,
                },
            },
        )

        req = urllib.request.Request(
            _PD_EVENTS_V2_URL,
            data=json.dumps(trigger.model_dump()).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        start = time.monotonic()
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                end = time.monotonic()
                latency_ms = round((end - start) * 1000, 2)
                raw = resp.read()
                pd_response: dict[str, Any] = json.loads(raw) if raw else {}
                pd_incident_id = pd_response.get("dedup_key", action_fingerprint)
                _log.info(
                    "pd_page_trigger_sent",
                    event_type="integrations.pagerduty.trigger_sent",
                    case_id=case_id,
                    action_fingerprint=sanitized_action_fingerprint,
                    action="trigger",
                    mode=self._mode.value,
                    pd_incident_id=pd_incident_id,
                    latency_ms=latency_ms,
                    outcome="success",
                )
        except Exception as exc:
            end = time.monotonic()
            latency_ms = round((end - start) * 1000, 2)
            _log.warning(
                "pd_page_trigger_send_failed",
                event_type="integrations.pagerduty.send_error",
                case_id=case_id,
                action_fingerprint=sanitized_action_fingerprint,
                action="trigger",
                mode=self._mode.value,
                latency_ms=latency_ms,
                error_type=type(exc).__name__,
                outcome="error",
            )
