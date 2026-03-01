"""Lightweight /health HTTP endpoint — asyncio raw TCP, no external HTTP framework."""

import asyncio
import json

from aiops_triage_pipeline.health.registry import get_health_registry


async def _handle_health_request(
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
) -> None:
    """Handle a single HTTP GET /health request."""
    try:
        # Read and discard HTTP request headers (we don't inspect method or path)
        while True:
            line = await reader.readline()
            if line in (b"\r\n", b"\n", b""):
                break

        registry = get_health_registry()
        statuses = {
            name: health.model_dump(mode="json")
            for name, health in registry.get_all().items()
        }
        body = json.dumps(statuses, default=str).encode("utf-8")

        response = (
            b"HTTP/1.1 200 OK\r\n"
            b"Content-Type: application/json\r\n"
            b"Content-Length: " + str(len(body)).encode() + b"\r\n"
            b"Connection: close\r\n"
            b"\r\n"
            + body
        )
        writer.write(response)
        await writer.drain()
    finally:
        writer.close()
        await writer.wait_closed()


async def start_health_server(host: str = "127.0.0.1", port: int = 8080) -> asyncio.Server:
    """Start the asyncio-based /health HTTP endpoint server.

    Args:
        host: Bind address (default 127.0.0.1 — loopback only; pass "0.0.0.0" for all interfaces)
        port: Port to listen on (default 8080)

    Returns:
        asyncio.Server instance — caller is responsible for closing on shutdown.

    Usage:
        server = await start_health_server(port=8080)
        async with server:
            await server.serve_forever()
    """
    return await asyncio.start_server(_handle_health_request, host, port)
