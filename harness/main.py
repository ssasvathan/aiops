"""Harness entry point: start Prometheus HTTP server and run pattern loop."""
import os
import threading
import time

from patterns import consumer_lag, normal, throughput_proxy, volume_drop
from prometheus_client import start_http_server

PATTERN = os.environ.get("HARNESS_PATTERN", "all")
CYCLE_SECONDS = int(os.environ.get("HARNESS_CYCLE_SECONDS", "60"))
INTENSITY = float(os.environ.get("HARNESS_INTENSITY", "0.5"))

_ALL_PATTERNS = [throughput_proxy, consumer_lag, volume_drop, normal]
_PATTERN_MAP = {
    "consumer_lag": [consumer_lag],
    "throughput_constrained": [throughput_proxy],
    "volume_drop": [volume_drop],
    "normal": [normal],
    "all": _ALL_PATTERNS,
}


def _run_loop() -> None:
    sequence = _PATTERN_MAP.get(PATTERN, _ALL_PATTERNS)
    while True:
        for mod in sequence:
            try:
                mod.run(duration=CYCLE_SECONDS, intensity=INTENSITY)
            except Exception as exc:
                print(f"[harness] Pattern {mod.__name__} raised: {exc}", flush=True)


if __name__ == "__main__":
    if PATTERN not in _PATTERN_MAP:
        print(
            f"[harness] WARNING: Unknown HARNESS_PATTERN={PATTERN!r}. "
            f"Valid values: {sorted(_PATTERN_MAP)}. Falling back to 'all'.",
            flush=True,
        )
    if not 0.0 <= INTENSITY <= 1.0:
        print(
            f"[harness] WARNING: HARNESS_INTENSITY={INTENSITY} is outside [0.0, 1.0]. "
            "Metric values may be nonsensical.",
            flush=True,
        )
    if CYCLE_SECONDS <= 0:
        print(
            f"[harness] WARNING: HARNESS_CYCLE_SECONDS={CYCLE_SECONDS} must be > 0. "
            "Defaulting to 60.",
            flush=True,
        )
        CYCLE_SECONDS = 60
    start_http_server(8000)
    print(
        f"Harness metrics server listening on :8000 | "
        f"pattern={PATTERN} cycle={CYCLE_SECONDS}s intensity={INTENSITY}"
    )
    t = threading.Thread(target=_run_loop, daemon=True)
    t.start()
    while True:
        time.sleep(1)
