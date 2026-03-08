"""Integration test bootstrap for Docker/Testcontainers defaults."""

from __future__ import annotations

import os
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

import redis as redis_lib

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
