"""LLMClient — stub, failure-injection, and LIVE mode for cold-path LLM invocation.

LIVE mode response parsing is minimal — Story 6.3 replaces with structured prompt
and schema-validated output.
"""

from enum import Enum

from aiops_triage_pipeline.config.settings import IntegrationMode
from aiops_triage_pipeline.contracts.diagnosis_report import DiagnosisReportV1, EvidencePack
from aiops_triage_pipeline.contracts.enums import DiagnosisConfidence
from aiops_triage_pipeline.contracts.triage_excerpt import TriageExcerptV1
from aiops_triage_pipeline.logging.setup import get_logger


class LLMFailureMode(str, Enum):
    NONE = "NONE"
    TIMEOUT = "TIMEOUT"
    UNAVAILABLE = "UNAVAILABLE"
    MALFORMED = "MALFORMED"
    ERROR = "ERROR"


_FAILURE_REASON_CODES: dict[LLMFailureMode, str] = {
    LLMFailureMode.NONE: "LLM_STUB",
    LLMFailureMode.TIMEOUT: "LLM_TIMEOUT",
    LLMFailureMode.UNAVAILABLE: "LLM_UNAVAILABLE",
    LLMFailureMode.MALFORMED: "LLM_SCHEMA_INVALID",
    LLMFailureMode.ERROR: "LLM_ERROR",
}


class LLMClient:
    """LLM client with stub, failure-injection, and LIVE mode support.

    In MOCK or LOG mode, returns a deterministic fallback DiagnosisReportV1 with no
    external network calls. LIVE mode makes an HTTP POST to LLM_BASE_URL/diagnose
    and returns a stub DiagnosisReportV1 — Story 6.3 replaces with structured prompt
    and schema-validated output. OFF mode raises ValueError.
    """

    def __init__(
        self,
        mode: IntegrationMode,
        failure_mode: LLMFailureMode = LLMFailureMode.NONE,
        base_url: str | None = None,
        api_key: str | None = None,
    ) -> None:
        self._mode = mode
        self._failure_mode = failure_mode
        self._base_url = base_url
        self._api_key = api_key
        self._logger = get_logger(__name__)

    async def invoke(
        self,
        case_id: str,
        triage_excerpt: TriageExcerptV1,
        evidence_summary: str,
    ) -> DiagnosisReportV1:
        """Invoke the LLM client.

        MOCK/LOG: returns deterministic stub report with no network I/O.
        LIVE: makes HTTP POST to LLM_BASE_URL/diagnose and returns a stub
              DiagnosisReportV1 — Story 6.3 replaces with structured output parsing.
        OFF: raises ValueError.

        Args:
            case_id: Case identifier for the report and structured log.
            triage_excerpt: Denylist-sanitized triage excerpt (cold-path LLM input).
            evidence_summary: Structured evidence summary string (cold-path LLM input).

        Returns:
            DiagnosisReportV1.

        Raises:
            ValueError: If mode is OFF, or LIVE mode without LLM_BASE_URL configured.
        """
        if self._mode == IntegrationMode.OFF:
            raise ValueError("INTEGRATION_MODE_LLM=OFF is not a valid LLM operation mode")

        if self._mode == IntegrationMode.LIVE:
            if not self._base_url:
                raise ValueError(
                    "INTEGRATION_MODE_LLM=LIVE requires LLM_BASE_URL to be configured"
                )
            import httpx  # Lazy import — only needed in LIVE mode

            body = {
                "case_id": case_id,
                "evidence_summary": evidence_summary,
                # triage_excerpt fields are denylist-sanitized by diagnosis/graph.py before invoke()
            }
            async with httpx.AsyncClient(timeout=60.0) as client:
                headers = {"Content-Type": "application/json"}
                if self._api_key:
                    headers["Authorization"] = f"Bearer {self._api_key}"
                response = await client.post(
                    f"{self._base_url}/diagnose",
                    json=body,
                    headers=headers,
                )
                response.raise_for_status()
            # Story 6.3 replaces this stub with structured response parsing
            self._logger.info(
                "llm_invoke_live_stub",
                mode=self._mode.value,
                case_id=case_id,
                status_code=response.status_code,
            )
            return DiagnosisReportV1(
                case_id=case_id,
                verdict="UNKNOWN",
                fault_domain=None,
                confidence=DiagnosisConfidence.LOW,
                evidence_pack=EvidencePack(facts=(), missing_evidence=(), matched_rules=()),
                next_checks=(),
                gaps=(),
                reason_codes=("LLM_LIVE_STUB",),
                triage_hash=None,
            )

        # MOCK and LOG: return deterministic stub/fallback report — no network I/O
        reason_code = _FAILURE_REASON_CODES[self._failure_mode]
        report = DiagnosisReportV1(
            case_id=case_id,
            verdict="UNKNOWN",
            fault_domain=None,
            confidence=DiagnosisConfidence.LOW,
            evidence_pack=EvidencePack(facts=(), missing_evidence=(), matched_rules=()),
            next_checks=(),
            gaps=(),
            reason_codes=(reason_code,),
            triage_hash=None,
        )
        self._logger.info(
            "llm_invoke_stub",
            mode=self._mode.value,
            failure_mode=self._failure_mode.value,
            case_id=case_id,
            reason_codes=report.reason_codes,
        )
        return report
