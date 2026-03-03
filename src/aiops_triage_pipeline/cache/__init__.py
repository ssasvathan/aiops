"""Cache adapters for aiops-triage-pipeline."""

from aiops_triage_pipeline.cache.peak_cache import (
    PeakCacheClientProtocol,
    build_peak_cache_key,
    get_or_compute_peak_profile,
    get_peak_profile,
    peak_profile_ttl_seconds,
    set_peak_profile,
)

__all__ = [
    "PeakCacheClientProtocol",
    "build_peak_cache_key",
    "get_or_compute_peak_profile",
    "get_peak_profile",
    "peak_profile_ttl_seconds",
    "set_peak_profile",
]
