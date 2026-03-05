"""Integration test bootstrap for Docker/Testcontainers defaults."""

from __future__ import annotations

import os
from pathlib import Path

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
