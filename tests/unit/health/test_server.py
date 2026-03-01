"""Unit tests for the /health asyncio HTTP server (AC3)."""

import asyncio
import json

import pytest

from aiops_triage_pipeline.health.registry import HealthRegistry
from aiops_triage_pipeline.health.server import start_health_server
from aiops_triage_pipeline.models.health import HealthStatus


async def _http_get(host: str, port: int) -> tuple[bytes, bytes]:
    """Send a minimal HTTP GET and return (raw_headers_bytes, body_bytes)."""
    reader, writer = await asyncio.open_connection(host, port)
    try:
        writer.write(b"GET /health HTTP/1.1\r\nHost: localhost\r\n\r\n")
        await writer.drain()

        raw_headers = b""
        while True:
            line = await reader.readline()
            if line in (b"\r\n", b""):
                break
            raw_headers += line

        body = b""
        while True:
            chunk = await reader.read(4096)
            if not chunk:
                break
            body += chunk
    finally:
        writer.close()
        await writer.wait_closed()

    return raw_headers, body


@pytest.fixture
def patched_registry(monkeypatch):
    """Fresh HealthRegistry injected into the server module for test isolation."""
    fresh = HealthRegistry()
    monkeypatch.setattr(
        "aiops_triage_pipeline.health.server.get_health_registry",
        lambda: fresh,
    )
    return fresh


async def test_server_returns_200_ok(patched_registry):
    """Server responds with HTTP 200 OK."""
    server = await start_health_server(host="127.0.0.1", port=0)
    port = server.sockets[0].getsockname()[1]
    async with server:
        raw_headers, _ = await _http_get("127.0.0.1", port)
    assert b"200 OK" in raw_headers


async def test_server_returns_json_content_type(patched_registry):
    """Server includes Content-Type: application/json header."""
    server = await start_health_server(host="127.0.0.1", port=0)
    port = server.sockets[0].getsockname()[1]
    async with server:
        raw_headers, _ = await _http_get("127.0.0.1", port)
    assert b"application/json" in raw_headers


async def test_server_body_reflects_registry_state(patched_registry):
    """JSON body matches current HealthRegistry component statuses."""
    await patched_registry.update("redis", HealthStatus.DEGRADED, reason="timeout")
    await patched_registry.update("prometheus", HealthStatus.HEALTHY)

    server = await start_health_server(host="127.0.0.1", port=0)
    port = server.sockets[0].getsockname()[1]
    async with server:
        _, body = await _http_get("127.0.0.1", port)

    data = json.loads(body)
    assert data["redis"]["status"] == "DEGRADED"
    assert data["redis"]["reason"] == "timeout"
    assert data["prometheus"]["status"] == "HEALTHY"


async def test_server_empty_registry_returns_empty_object(patched_registry):
    """Server returns {} when no components have been registered."""
    server = await start_health_server(host="127.0.0.1", port=0)
    port = server.sockets[0].getsockname()[1]
    async with server:
        _, body = await _http_get("127.0.0.1", port)
    assert json.loads(body) == {}


async def test_server_survives_abrupt_client_disconnect(patched_registry):
    """Server continues serving after a client disconnects without sending a request.

    Exercises the try/finally resource-cleanup path in _handle_health_request.
    """
    server = await start_health_server(host="127.0.0.1", port=0)
    port = server.sockets[0].getsockname()[1]
    async with server:
        # Connect and immediately close — no HTTP headers sent
        reader, writer = await asyncio.open_connection("127.0.0.1", port)
        writer.close()
        await writer.wait_closed()
        await asyncio.sleep(0.05)  # Let the handler reach its finally block

        # Server must still be alive and serve a valid response
        _, body = await _http_get("127.0.0.1", port)
        assert json.loads(body) == {}
