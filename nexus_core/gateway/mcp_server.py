"""SSE MCP-style gateway for the virtual assistant Paula."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field


@dataclass(frozen=True)
class PaulaAsset:
    name: str
    url: str
    media_type: str = "video/mp4"


class PaulaChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=32_000)


class VirtualAssistantPaula:
    """Provider-neutral Paula orchestration layer.

    Real LLM/STT/TTS providers can be injected later; the gateway only owns
    transport semantics and event ordering.
    """

    def __init__(
        self,
        *,
        assets: tuple[PaulaAsset, ...] | None = None,
    ) -> None:
        self.voice_model_loaded = False
        self.visual_assets_ready = False
        self.assets = assets or (
            PaulaAsset(
                name="idle",
                url=str(PurePosixPath("/assets/paula_idle.mp4")),
            ),
        )

    async def generate_response_stream(
        self,
        user_input: str,
        request: Request | None = None,
    ) -> AsyncIterator[dict[str, str]]:
        """Yield SSE events in a deterministic order and stop on disconnect."""
        yield {
            "event": "status",
            "data": json.dumps(
                {"status": "reasoning_started"},
                ensure_ascii=False,
            ),
        }

        if request is not None and await request.is_disconnected():
            return

        if self.assets:
            self.visual_assets_ready = True
            yield {
                "event": "asset_sync",
                "data": json.dumps(
                    {
                        "name": self.assets[0].name,
                        "url": self.assets[0].url,
                        "media_type": self.assets[0].media_type,
                    },
                    ensure_ascii=False,
                ),
            }

        yield {"event": "audio_stream_start", "data": "play"}

        # Transport-level reference implementation. A real LLM adapter can
        # replace this sequence without changing the SSE protocol.
        words = (
            "Oto nowe funkcje skonfigurowane w App Builderze."
            if user_input.strip()
            else "Podaj wiadomość."
        )
        for word in words.split():
            if request is not None and await request.is_disconnected():
                return
            yield {
                "event": "message",
                "data": json.dumps({"text": word}, ensure_ascii=False),
            }
            await asyncio.sleep(0)

        yield {
            "event": "action",
            "data": json.dumps(
                {"status": "tool_execution_ready"},
                ensure_ascii=False,
            ),
        }
        yield {"event": "done", "data": json.dumps({"status": "complete"})}


def create_app(paula: VirtualAssistantPaula | None = None) -> FastAPI:
    app = FastAPI(title="Nexus Core MCP Gateway — Paula SSE")
    assistant = paula or VirtualAssistantPaula()

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/api/v1/chat/paula")
    async def chat_with_paula(
        payload: PaulaChatRequest,
        request: Request,
    ) -> StreamingResponse:
        return StreamingResponse(
            assistant.generate_response_stream(payload.message, request),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    return app


app = create_app()
