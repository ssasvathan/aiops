"""LLMClient — stub and failure-injection mode for cold-path LLM invocation (Story 6.1).

LIVE mode is not implemented until Story 6.2.
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
    """LLM client with stub and failure-injection support.

    In MOCK or LOG mode, returns a deterministic fallback DiagnosisReportV1 with no
    external network calls. LIVE mode raises NotImplementedError until Story 6.2.
    OFF mode raises ValueError — it is not a valid LLM operation mode.
    """

    def __init__(
        self,
        mode: IntegrationMode,
        failure_mode: LLMFailureMode = LLMFailureMode.NONE,
    ) -> None:
        self._mode = mode
        self._failure_mode = failure_mode
        self._logger = get_logger(__name__)

    async def invoke(
        self,
        case_id: str,
        triage_excerpt: TriageExcerptV1,
        evidence_summary: str,
    ) -> DiagnosisReportV1:
        """Invoke the LLM client (stub in MOCK/LOG mode; not implemented in LIVE mode).

        Args:
            case_id: Case identifier for the fallback report and structured log.
            triage_excerpt: Structured triage excerpt (cold-path LLM input).
            evidence_summary: Free-text evidence summary (cold-path LLM input).

        Returns:
            DiagnosisReportV1 with deterministic fallback fields in MOCK/LOG mode.

        Raises:
            ValueError: If mode is OFF.
            NotImplementedError: If mode is LIVE (implemented in Story 6.2).
        """
        if self._mode == IntegrationMode.OFF:
            raise ValueError("INTEGRATION_MODE_LLM=OFF is not a valid LLM operation mode")
        if self._mode == IntegrationMode.LIVE:
            raise NotImplementedError("LLM LIVE mode not implemented until Story 6.2")

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
