"""OTLP counters and histograms for baseline deviation detection telemetry (FR29, FR30)."""

from __future__ import annotations

from opentelemetry import metrics
from opentelemetry.context import Context
from opentelemetry.metrics import Counter, Histogram


class _NamedCounter:
    """Thin wrapper around OTel Counter that exposes the instrument name via `.name`."""

    def __init__(self, instrument: Counter, name: str) -> None:
        self._instrument = instrument
        self.name = name

    def add(
        self,
        amount: int | float,
        attributes: dict[str, str] | None = None,
        context: Context | None = None,
    ) -> None:
        self._instrument.add(amount, attributes=attributes, context=context)


class _NamedHistogram:
    """Thin wrapper around OTel Histogram that exposes the instrument name via `.name`."""

    def __init__(self, instrument: Histogram, name: str) -> None:
        self._instrument = instrument
        self.name = name

    def record(
        self,
        amount: int | float,
        attributes: dict[str, str] | None = None,
        context: Context | None = None,
    ) -> None:
        self._instrument.record(amount, attributes=attributes, context=context)


_meter = metrics.get_meter("aiops_triage_pipeline.baseline_deviation")

_DEVIATIONS_DETECTED_NAME = "aiops.baseline_deviation.deviations_detected"
_FINDINGS_EMITTED_NAME = "aiops.baseline_deviation.findings_emitted"
_SUPPRESSED_SINGLE_METRIC_NAME = "aiops.baseline_deviation.suppressed_single_metric"
_SUPPRESSED_DEDUP_NAME = "aiops.baseline_deviation.suppressed_dedup"
_STAGE_DURATION_SECONDS_NAME = "aiops.baseline_deviation.stage_duration_seconds"
_MAD_COMPUTATION_SECONDS_NAME = "aiops.baseline_deviation.mad_computation_seconds"

_deviations_detected = _NamedCounter(
    _meter.create_counter(
        name=_DEVIATIONS_DETECTED_NAME,
        description="Total metric deviations detected by baseline deviation stage",
        unit="1",
    ),
    _DEVIATIONS_DETECTED_NAME,
)
_findings_emitted = _NamedCounter(
    _meter.create_counter(
        name=_FINDINGS_EMITTED_NAME,
        description="Total correlated BASELINE_DEVIATION findings emitted",
        unit="1",
    ),
    _FINDINGS_EMITTED_NAME,
)
_suppressed_single_metric = _NamedCounter(
    _meter.create_counter(
        name=_SUPPRESSED_SINGLE_METRIC_NAME,
        description="Total findings suppressed due to single-metric threshold",
        unit="1",
    ),
    _SUPPRESSED_SINGLE_METRIC_NAME,
)
_suppressed_dedup = _NamedCounter(
    _meter.create_counter(
        name=_SUPPRESSED_DEDUP_NAME,
        description="Total findings suppressed due to hand-coded detector dedup",
        unit="1",
    ),
    _SUPPRESSED_DEDUP_NAME,
)
_stage_duration_seconds = _NamedHistogram(
    _meter.create_histogram(
        name=_STAGE_DURATION_SECONDS_NAME,
        description="Baseline deviation stage execution time per cycle",
        unit="s",
    ),
    _STAGE_DURATION_SECONDS_NAME,
)
_mad_computation_seconds = _NamedHistogram(
    _meter.create_histogram(
        name=_MAD_COMPUTATION_SECONDS_NAME,
        description="MAD computation time per scope per cycle",
        unit="s",
    ),
    _MAD_COMPUTATION_SECONDS_NAME,
)


def record_deviations_detected(count: int) -> None:
    """Increment deviations_detected counter by count (no-op if count <= 0)."""
    if count <= 0:
        return
    _deviations_detected.add(count)


def record_finding_emitted() -> None:
    """Increment findings_emitted counter by 1."""
    _findings_emitted.add(1)


def record_suppressed_single_metric() -> None:
    """Increment suppressed_single_metric counter by 1."""
    _suppressed_single_metric.add(1)


def record_suppressed_dedup() -> None:
    """Increment suppressed_dedup counter by 1."""
    _suppressed_dedup.add(1)


def record_stage_duration(seconds: float) -> None:
    """Record stage total execution duration in seconds."""
    _stage_duration_seconds.record(max(seconds, 0.0))


def record_mad_computation(seconds: float) -> None:
    """Record per-scope MAD computation duration in seconds."""
    _mad_computation_seconds.record(max(seconds, 0.0))
