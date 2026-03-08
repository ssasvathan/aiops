"""LLM diagnosis prompt builder — constructs structured prompt from triage context."""

from aiops_triage_pipeline.contracts.triage_excerpt import TriageExcerptV1

_SYSTEM_INSTRUCTION = """
You are a production incident diagnosis assistant for a Kafka-based AIOps platform.

Analyze the provided triage excerpt and evidence summary and produce a diagnosis report.

OUTPUT REQUIREMENTS:
- Respond ONLY with valid JSON matching the DiagnosisReportV1 schema (defined below)
- Do NOT include any text outside the JSON object
- Do NOT fabricate metric values, counts, or findings not present in the evidence pack
- If evidence is UNKNOWN or missing, propagate UNKNOWN — never assume presence or default to zero

EVIDENCE CITATION RULES:
- Cite only evidence IDs and keys explicitly provided in the evidence_status_map
- Reference specific findings by their finding_id from the findings list
- The evidence_pack.facts field must cite observable evidence (PRESENT status only)
- The evidence_pack.missing_evidence field must list any evidence with UNKNOWN/ABSENT/STALE status
- The evidence_pack.matched_rules field cites Rulebook finding IDs

DIAGNOSISREPORTV1 JSON SCHEMA:
{
  "schema_version": "v1",
  "case_id": "<string or null>",
  "verdict": "<non-empty string>",
  "fault_domain": "<string or null>",
  "confidence": "LOW" | "MEDIUM" | "HIGH",
  "evidence_pack": {
    "facts": ["<cited evidence fact>", ...],
    "missing_evidence": ["<UNKNOWN/ABSENT evidence ID>", ...],
    "matched_rules": ["<finding_id>", ...]
  },
  "next_checks": ["<recommended check>", ...],
  "gaps": ["<evidence gap>", ...],
  "reason_codes": [],
  "triage_hash": null
}
""".strip()


def build_llm_prompt(triage_excerpt: TriageExcerptV1, evidence_summary: str) -> str:
    """Build a structured LLM diagnosis prompt from triage context and evidence.

    Returns a single string containing system instructions and case context.
    The caller (diagnosis/graph.py) passes this as the 'prompt' field to LLMClient.invoke().
    Input is already denylist-sanitized by run_cold_path_diagnosis() before this is called.
    """
    # Format evidence_status_map for readability
    evidence_lines = "\n".join(
        f"  {key}: {status.value}" for key, status in triage_excerpt.evidence_status_map.items()
    )
    # Format findings
    findings_lines = "\n".join(
        f"  [{f.finding_id}] {f.name} (anomalous={f.is_anomalous})"
        for f in triage_excerpt.findings
    )

    case_context = f"""
CASE CONTEXT:
  case_id: {triage_excerpt.case_id}
  anomaly_family: {triage_excerpt.anomaly_family}
  topic: {triage_excerpt.topic}
  cluster_id: {triage_excerpt.cluster_id}
  stream_id: {triage_excerpt.stream_id}
  criticality_tier: {triage_excerpt.criticality_tier.value}
  sustained: {triage_excerpt.sustained}
  peak: {triage_excerpt.peak}
  env: {triage_excerpt.env.value}

EVIDENCE STATUS MAP (UNKNOWN = missing data — do NOT assume zero):
{evidence_lines if evidence_lines else "  (no evidence entries)"}

FINDINGS:
{findings_lines if findings_lines else "  (no findings)"}

EVIDENCE SUMMARY:
{evidence_summary}
""".strip()

    return f"{_SYSTEM_INSTRUCTION}\n\n{case_context}"
