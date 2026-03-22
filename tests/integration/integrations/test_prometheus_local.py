import errno
import math
import os
import socket
import time
from datetime import UTC, datetime
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

import pytest
from testcontainers.core.container import DockerContainer

from aiops_triage_pipeline.integrations.prometheus import (
    PrometheusHTTPClient,
    build_metric_queries,
)

_FALLBACK_PROMETHEUS_IMAGE = os.getenv("AIOPS_PROMETHEUS_TEST_IMAGE", "prom/prometheus:v2.50.1")
_CONNECTIVITY_ERRNOS = {
    errno.ECONNREFUSED,
    errno.ENETUNREACH,
    errno.EHOSTUNREACH,
    errno.ETIMEDOUT,
}


def _wait_for_prometheus(base_url: str, timeout_seconds: float = 30.0) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        try:
            with urlopen(f"{base_url}/-/healthy", timeout=1.0) as response:  # noqa: S310
                if response.status == 200:
                    return
        except (URLError, TimeoutError, ConnectionError, OSError):
            time.sleep(0.25)
    raise TimeoutError(f"Timed out waiting for Prometheus at {base_url}")


def _is_prometheus_connectivity_failure(exc: BaseException) -> bool:
    if isinstance(exc, HTTPError):
        return False
    if isinstance(exc, (TimeoutError, ConnectionError, socket.timeout)):
        return True
    if isinstance(exc, URLError):
        reason = exc.reason
        if isinstance(reason, str):
            lowered = reason.lower()
            return "connection refused" in lowered or "timed out" in lowered
        if isinstance(reason, (TimeoutError, ConnectionError, socket.timeout)):
            return True
        if isinstance(reason, OSError):
            return reason.errno in _CONNECTIVITY_ERRNOS
        return False
    if isinstance(exc, OSError):
        return exc.errno in _CONNECTIVITY_ERRNOS
    return False


def _assert_sample_shape(samples: list[dict[str, object]]) -> None:
    for sample in samples:
        assert set(sample.keys()) == {"labels", "value"}
        labels = sample["labels"]
        value = sample["value"]
        assert isinstance(labels, dict)
        assert all(isinstance(k, str) and isinstance(v, str) for k, v in labels.items())
        assert isinstance(value, float)
        assert math.isfinite(value)


def _wait_for_non_empty_series(
    client: PrometheusHTTPClient,
    *,
    metric_name: str,
    timeout_seconds: float = 30.0,
) -> list[dict[str, object]]:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        samples = client.query_instant(metric_name, at_time=datetime.now(tz=UTC))
        if samples:
            return samples
        time.sleep(0.5)
    raise AssertionError(
        f"Expected non-empty '{metric_name}' series within {timeout_seconds:.0f}s "
        "to validate Prometheus query-path behavior."
    )


@pytest.mark.integration
def test_local_prometheus_query_path_smoke() -> None:
    queries = build_metric_queries()
    metric = queries["topic_messages_in_per_sec"].metric_name
    evaluation_time = datetime.now(tz=UTC)

    try:
        client = PrometheusHTTPClient(base_url="http://localhost:9090")
        samples = client.query_instant(
            metric,
            at_time=evaluation_time,
        )
    except (URLError, TimeoutError, ConnectionError) as exc:
        if not _is_prometheus_connectivity_failure(exc):
            raise
        try:
            with DockerContainer(_FALLBACK_PROMETHEUS_IMAGE).with_exposed_ports(9090) as container:
                host = container.get_container_host_ip()
                port = int(container.get_exposed_port(9090))
                fallback_base_url = f"http://{host}:{port}"
                _wait_for_prometheus(fallback_base_url)
                client = PrometheusHTTPClient(base_url=fallback_base_url)
                samples = client.query_instant(
                    metric,
                    at_time=evaluation_time,
                )
                if not samples:
                    self_series = _wait_for_non_empty_series(client, metric_name="up")
                    _assert_sample_shape(self_series)
        except Exception as fallback_exc:  # pragma: no cover - defensive path for CI diagnostics
            pytest.fail(
                "Fallback Prometheus container startup failed. Pre-pull "
                f"'{_FALLBACK_PROMETHEUS_IMAGE}' (or set AIOPS_PROMETHEUS_TEST_IMAGE "
                f"to a locally available mirror). Underlying error: {fallback_exc!r}"
            )

    assert isinstance(samples, list)
    _assert_sample_shape(samples)
