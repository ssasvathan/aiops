"""LLM diagnosis prompt builder — constructs structured prompt from triage context."""

from aiops_triage_pipeline.baseline.computation import time_to_bucket
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

CONFIDENCE CALIBRATION GUIDANCE:
- Use HIGH only when primary anomalous findings are strongly supported by PRESENT evidence.
- Use MEDIUM when evidence is mixed and at least one important signal is UNKNOWN/ABSENT/STALE.
- Use LOW when evidence is sparse, conflicting, or mostly unavailable.

FAULT-DOMAIN HINTS:
- CONSUMER_LAG often maps to CONSUMER_GROUP, DOWNSTREAM_DEPENDENCY, or BROKER_PRESSURE.
- VOLUME_DROP often maps to UPSTREAM_PRODUCER, ROUTING_MISCONFIGURATION, or SOURCE_OUTAGE.
- THROUGHPUT_CONSTRAINED_PROXY often maps to BROKER_CAPACITY, THROTTLING_POLICY, or NETWORK_PATH.
- BASELINE_DEVIATION often maps to UPSTREAM_PRODUCER, BROKER_PRESSURE, or SEASONAL_ANOMALY.

BASELINE DEVIATION DIAGNOSIS FRAMING:
When anomaly_family is BASELINE_DEVIATION, frame the verdict as a hypothesis.
Use language expressing uncertainty: "BASELINE_DEVIATION_CORRELATED_LIKELY",
"POSSIBLE_UPSTREAM_PRESSURE", or similar POSSIBLE/LIKELY/SUSPECTED prefix patterns.
The evidence_pack.facts must cite which deviation metrics and directions were observed.

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

_BASELINE_DEVIATION_FEW_SHOT = """
FEW-SHOT EXAMPLE (BASELINE_DEVIATION):
Input pattern:
  anomaly_family=BASELINE_DEVIATION
  topic_role=SHARED_TOPIC
  routing_key=OWN::Streaming::Metrics
  findings include BASELINE_DEV:consumer_lag.offset:HIGH and BASELINE_DEV:producer_rate:LOW
Expected output pattern (hypothesis framing required):
  verdict="BASELINE_DEVIATION_CORRELATED_LIKELY"
  fault_domain="UPSTREAM_PRODUCER"
  confidence="MEDIUM"
  evidence_pack.facts cites which BASELINE_DEVIATION metrics deviated HIGH or LOW
  gaps include any UNKNOWN evidence that limits confidence
"""

_CONSUMER_LAG_FEW_SHOT = """
FEW-SHOT EXAMPLE (deterministic, single canonical reference):
Input pattern:
  anomaly_family=CONSUMER_LAG
  topic_role=SHARED_TOPIC
  routing_key=OWN::Streaming::Payments
  findings include primary lag growth with PRESENT lag evidence and UNKNOWN throughput evidence
Expected output pattern:
  verdict="CONSUMER_LAG_LIKELY"
  fault_domain="CONSUMER_GROUP"
  confidence="MEDIUM"
  evidence_pack.matched_rules includes relevant finding_id values only
  gaps include UNKNOWN evidence that blocks HIGH confidence"""


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
    # Format findings with all explicit fields required by FR40.
    findings_lines = "\n".join(
        "  - "
        f"finding_id={f.finding_id}; "
        f"name={f.name}; "
        f"severity={f.severity}; "
        f"reason_codes={list(f.reason_codes)}; "
        f"evidence_required={list(f.evidence_required)}; "
        f"is_primary={f.is_primary}; "
        f"is_anomalous={f.is_anomalous}"
        for f in triage_excerpt.findings
    )

    # Build BASELINE_DEVIATION context block if applicable
    baseline_deviation_block = ""
    if triage_excerpt.anomaly_family == "BASELINE_DEVIATION":
        dow, hour = time_to_bucket(triage_excerpt.triage_timestamp)
        _dow_names = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
        dow_name = _dow_names[dow]
        deviating_metrics: list[str] = []
        for finding in triage_excerpt.findings:
            for rc in finding.reason_codes:
                if rc.startswith("BASELINE_DEV:"):
                    remainder = rc.removeprefix("BASELINE_DEV:")
                    parts = remainder.rsplit(":", 1)
                    if len(parts) != 2:  # noqa: PLR2004 — guard malformed reason_codes
                        continue  # skip unparseable entries; never crash the cold-path
                    metric_key, direction = parts
                    deviating_metrics.append(f"  - metric_key={metric_key}; direction={direction}")
        metrics_text = (
            "\n".join(deviating_metrics)
            if deviating_metrics
            else "  (no deviating metrics encoded in reason_codes)"
        )
        baseline_deviation_block = f"""

BASELINE DEVIATION CONTEXT:
  Seasonal time bucket: {dow_name} hour={hour} (dow={dow}, hour={hour})
  The following metrics deviated from their seasonal baseline:
{metrics_text}

  Hypothesis framing: Frame the verdict as a possible interpretation of the correlated deviations.
  Use LIKELY, POSSIBLE, or SUSPECTED prefixes — do NOT assert a definitive root cause."""

    if triage_excerpt.anomaly_family == "BASELINE_DEVIATION":
        few_shot_block = _BASELINE_DEVIATION_FEW_SHOT
    else:
        few_shot_block = _CONSUMER_LAG_FEW_SHOT

    case_context = f"""
CASE CONTEXT:
  case_id: {triage_excerpt.case_id}
  anomaly_family: {triage_excerpt.anomaly_family}
  topic: {triage_excerpt.topic}
  cluster_id: {triage_excerpt.cluster_id}
  stream_id: {triage_excerpt.stream_id}
  criticality_tier: {triage_excerpt.criticality_tier.value}
  topic_role: {triage_excerpt.topic_role}
  routing_key: {triage_excerpt.routing_key}
  sustained: {triage_excerpt.sustained}
  peak: {triage_excerpt.peak}
  env: {triage_excerpt.env.value}

EVIDENCE STATUS MAP (UNKNOWN = missing data — do NOT assume zero):
{evidence_lines if evidence_lines else "  (no evidence entries)"}

FINDINGS:
{findings_lines if findings_lines else "  (no findings)"}{baseline_deviation_block}

EVIDENCE SUMMARY:
{evidence_summary}
{few_shot_block}
""".strip()

    return f"{_SYSTEM_INSTRUCTION}\n\n{case_context}"
