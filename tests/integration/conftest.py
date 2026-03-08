"""Integration test bootstrap for Docker/Testcontainers defaults."""

from __future__ import annotations

import os
import time
from http.client import RemoteDisconnected
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

import pytest
import redis as redis_lib
from testcontainers.core.container import DockerContainer

_DOCKER_DESKTOP_SOCKET = Path.home() / ".docker" / "desktop" / "docker.sock"
_DOCKER_ENGINE_SOCKET = Path("/var/run/docker.sock")


def _configure_testcontainers_environment() -> None:
    if os.environ.get("DOCKER_HOST"):
        return

    if _DOCKER_ENGINE_SOCKET.exists():
        os.environ["DOCKER_HOST"] = f"unix://{_DOCKER_ENGINE_SOCKET}"
        return

    if _DOCKER_DESKTOP_SOCKET.exists():
        os.environ["DOCKER_HOST"] = f"unix://{_DOCKER_DESKTOP_SOCKET}"
        os.environ.setdefault("TESTCONTAINERS_RYUK_DISABLED", "true")


_configure_testcontainers_environment()


def _is_environment_prereq_error(exc: Exception) -> bool:
    """Return True when the exception indicates a missing Docker/DB prerequisite."""
    text = f"{type(exc).__name__}: {exc}"
    return any(
        marker in text
        for marker in (
            "no pq wrapper available",
            "libpq library not found",
            "Error while fetching server API version",
            "DockerException",
            "Cannot connect to Docker daemon",
        )
    )


def _wait_for_minio(endpoint_url: str, timeout_seconds: float = 30.0) -> None:
    """Poll MinIO health endpoint until it responds 200 or timeout expires."""
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        try:
            with urlopen(f"{endpoint_url}/minio/health/live", timeout=1.0) as response:  # noqa: S310
                if response.status == 200:
                    return
        except (URLError, TimeoutError, ConnectionError):
            time.sleep(0.25)
    raise TimeoutError(f"Timed out waiting for MinIO health endpoint at {endpoint_url}")


def _wait_for_redis(host: str, port: int, timeout_seconds: float = 30.0) -> None:
    """Poll Redis until ping succeeds or timeout expires."""
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        try:
            redis_client = redis_lib.Redis(
                host=host,
                port=port,
                decode_responses=True,
                socket_connect_timeout=1.0,
            )
            if redis_client.ping():
                return
        except (redis_lib.exceptions.RedisError, OSError):
            time.sleep(0.25)
    raise TimeoutError(f"Timed out waiting for Redis at {host}:{port}")


def _wait_for_http_endpoint(url: str, timeout_seconds: float = 30.0) -> None:
    """Poll an HTTP endpoint until it responds 200."""
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        try:
            with urlopen(url, timeout=1.0) as response:  # noqa: S310
                if response.status == 200:
                    return
        except (URLError, TimeoutError, ConnectionError, RemoteDisconnected, OSError):
            time.sleep(0.25)
    raise TimeoutError(f"Timed out waiting for HTTP endpoint at {url}")


@pytest.fixture(scope="session")
def otlp_collector_container():
    """Session-scoped OTLP Collector with Prometheus exporter for integration assertions."""
    with (
        DockerContainer("otel/opentelemetry-collector-contrib:0.106.1")
        .with_exposed_ports(4318, 8888) as container
    ):
        host = container.get_container_host_ip()
        otlp_port = int(container.get_exposed_port(4318))
        metrics_url = f"http://{host}:{int(container.get_exposed_port(8888))}/metrics"
        _wait_for_http_endpoint(metrics_url)
        yield {
            "otlp_endpoint": f"http://{host}:{otlp_port}/v1/metrics",
            "metrics_url": metrics_url,
            "collector": container,
        }
