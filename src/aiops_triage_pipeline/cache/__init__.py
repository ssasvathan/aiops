"""Cache adapters for aiops-triage-pipeline."""

from aiops_triage_pipeline.cache.evidence_window import (
    EvidenceWindowCacheClientProtocol,
    build_legacy_sustained_window_cache_key,
    build_sustained_window_cache_key,
    evidence_window_ttl_seconds,
    get_sustained_window_state,
    load_sustained_window_states,
    persist_sustained_window_states,
    set_sustained_window_state,
)
from aiops_triage_pipeline.cache.findings_cache import (
    FindingsCacheClientProtocol,
    build_interval_findings_cache_key,
    build_legacy_interval_findings_cache_key,
    get_interval_findings,
    get_or_compute_interval_findings,
    interval_findings_ttl_seconds,
    set_interval_findings,
)
from aiops_triage_pipeline.cache.peak_cache import (
    PeakCacheClientProtocol,
    build_peak_cache_key,
    get_or_compute_peak_profile,
    get_peak_profile,
    peak_profile_ttl_seconds,
    set_peak_profile,
)

__all__ = [
    "EvidenceWindowCacheClientProtocol",
    "FindingsCacheClientProtocol",
    "PeakCacheClientProtocol",
    "build_sustained_window_cache_key",
    "build_legacy_sustained_window_cache_key",
    "build_interval_findings_cache_key",
    "build_legacy_interval_findings_cache_key",
    "build_peak_cache_key",
    "evidence_window_ttl_seconds",
    "interval_findings_ttl_seconds",
    "get_sustained_window_state",
    "load_sustained_window_states",
    "persist_sustained_window_states",
    "get_interval_findings",
    "get_or_compute_interval_findings",
    "get_or_compute_peak_profile",
    "get_peak_profile",
    "peak_profile_ttl_seconds",
    "set_sustained_window_state",
    "set_interval_findings",
    "set_peak_profile",
]
