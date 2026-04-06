"""LLMClient — stub, failure-injection, and LIVE mode for cold-path LLM invocation.

LIVE mode uses LiteLLM to call the configured model (direct provider or gateway proxy)
and parses the response as a schema-validated DiagnosisReportV1 via model_validate().
"""

import json
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
    external network calls. LIVE mode uses LiteLLM to call the configured model
    (direct Anthropic/OpenAI or via LiteLLM gateway proxy) and parses the response
    as schema-validated DiagnosisReportV1. OFF mode raises ValueError.

    LiteLLM routing:
      - LLM_BASE_URL=None, LLM_API_KEY=sk-ant-...  → direct Anthropic API
      - LLM_BASE_URL=http://gateway, LLM_API_KEY=token → LiteLLM gateway (OpenAI-compatible)
    """

    def __init__(
        self,
        mode: IntegrationMode,
        failure_mode: LLMFailureMode = LLMFailureMode.NONE,
        base_url: str | None = None,
        api_key: str | None = None,
        model: str = "claude-sonnet-4-6",
    ) -> None:
        self._mode = mode
        self._failure_mode = failure_mode
        self._base_url = base_url
        self._api_key = api_key
        self._model = model
        self._logger = get_logger(__name__)

    async def invoke(
        self,
        case_id: str,
        triage_excerpt: TriageExcerptV1,
        evidence_summary: str,
        *,
        prompt: str | None = None,
    ) -> DiagnosisReportV1:
        """Invoke the LLM client.

        MOCK/LOG: returns deterministic stub report with no network I/O.
        LIVE: calls the configured model via LiteLLM and parses response as
              schema-validated DiagnosisReportV1.
        OFF: raises ValueError.

        Args:
            case_id: Case identifier for the report and structured log.
            triage_excerpt: Denylist-sanitized triage excerpt (cold-path LLM input).
            evidence_summary: Structured evidence summary string (cold-path LLM input).
            prompt: Structured prompt string built by diagnosis/graph.py (LIVE mode required).

        Returns:
            DiagnosisReportV1.

        Raises:
            ValueError: If mode is OFF, or LIVE mode without prompt provided.
        """
        if self._mode == IntegrationMode.OFF:
            raise ValueError("INTEGRATION_MODE_LLM=OFF is not a valid LLM operation mode")

        if self._mode == IntegrationMode.LIVE:
            if prompt is None:
                raise ValueError(
                    "LIVE mode requires prompt to be provided by the caller (diagnosis/graph.py)"
                )
            import litellm  # Lazy import — only needed in LIVE mode

            kwargs: dict = {
                "model": self._model,
                "messages": [{"role": "user", "content": prompt}],
            }
            if self._base_url:
                kwargs["base_url"] = self._base_url
            if self._api_key:
                kwargs["api_key"] = self._api_key

            response = await litellm.acompletion(**kwargs)
            content = response.choices[0].message.content
            # Strip markdown code fences (e.g. ```json ... ```) that some models
            # wrap around JSON output despite the prompt requesting raw JSON.
            stripped = content.strip()
            if stripped.startswith("```"):
                lines = stripped.splitlines()
                # Drop opening fence line (e.g. "```json" or "```")
                lines = lines[1:]
                # Drop closing fence line if present
                if lines and lines[-1].strip() == "```":
                    lines = lines[:-1]
                stripped = "\n".join(lines)
            response_data = json.loads(stripped)
            report = DiagnosisReportV1.model_validate({**response_data, "case_id": case_id})
            self._logger.info(
                "llm_invoke_live",
                mode=self._mode.value,
                case_id=case_id,
                model=self._model,
                verdict=report.verdict,
            )
            return report

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
