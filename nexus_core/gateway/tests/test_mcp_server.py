from __future__ import annotations

import json

import pytest
from httpx import ASGITransport, AsyncClient

from nexus_core.gateway.mcp_server import create_app


@pytest.mark.asyncio
async def test_paula_gateway_streams_ordered_sse_events() -> None:
    app = create_app()

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/api/v1/chat/paula",
            json={"message": "Zbuduj aplikację"},
        )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert "event: status" in response.text
    assert "event: asset_sync" in response.text
    assert "event: audio_stream_start" in response.text
    assert "event: message" in response.text
    assert "event: action" in response.text
    assert "event: done" in response.text
    assert response.text.index("event: status") < response.text.index("event: asset_sync")


@pytest.mark.asyncio
async def test_paula_gateway_rejects_empty_message() -> None:
    app = create_app()

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/api/v1/chat/paula",
            json={"message": ""},
        )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_paula_gateway_health() -> None:
    app = create_app()

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get("/health")

    assert response.json() == {"status": "ok"}
