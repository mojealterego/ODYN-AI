from __future__ import annotations
from collections.abc import AsyncIterable
from contextlib import asynccontextmanager
import os
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.sse import EventSourceResponse, ServerSentEvent
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field
from odyn_ai.config import load_config
from odyn_ai.core.agents import AgentManager
from odyn_ai.core.builders import AppBuilder
from odyn_ai.core.engine import DualGGUFEngine

config = load_config()
engine = DualGGUFEngine(config)
agents = AgentManager()
apps = AppBuilder()
UI_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "ui")

@asynccontextmanager
async def lifespan(_: FastAPI):
    await engine.start()
    yield
    await engine.close()

app = FastAPI(title="ODYN AI", version="0.1.0", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=UI_DIR), name="static")
templates = Jinja2Templates(directory=UI_DIR)

class ChatMessage(BaseModel):
    role: str
    content: str

class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=20000)
    agent_id: str = "odyn_glowny"
    history: list[ChatMessage] = Field(default_factory=list)

class AgentCreate(BaseModel):
    agent_id: str
    name: str
    prompt: str
    can_search: bool = False

class AppCreate(BaseModel):
    name: str
    description: str = ""
    agent_id: str = "odyn_glowny"
    language: str = "pl"

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(request=request, name="index.html", context={"agents": agents.list_agents()})

@app.get("/api/status")
async def status():
    return {"product": "ODYN AI", "language": "pl", "engine": engine.status()}

@app.get("/api/agents")
async def list_agents():
    return {"agents": agents.list_agents()}

@app.post("/api/agents")
async def create_agent(payload: AgentCreate):
    try: return agents.create(payload.agent_id, payload.name, payload.prompt, payload.can_search)
    except ValueError as exc: raise HTTPException(422, str(exc)) from exc

@app.get("/api/apps")
async def list_apps():
    return {"apps": apps.list_apps()}

@app.post("/api/apps")
async def create_app(payload: AppCreate):
    return apps.create(payload.name, payload.description, payload.agent_id, payload.language)

@app.post("/chat/stream", response_class=EventSourceResponse)
async def chat_stream(payload: ChatRequest) -> AsyncIterable[ServerSentEvent]:
    definition = agents.get(payload.agent_id)
    messages = [{"role": "system", "content": definition.prompt}]
    messages += [{"role": m.role, "content": m.content} for m in payload.history[-40:] if m.role in {"user","assistant","system"}]
    messages.append({"role": "user", "content": payload.message})
    messages = await agents.preprocess(messages, payload.agent_id)
    async def stream() -> AsyncIterable[ServerSentEvent]:
        try:
            yield ServerSentEvent(comment="ODYN AI stream started")
            async for token in engine.stream_chat(messages):
                yield ServerSentEvent(raw_data=token, event="token")
            yield ServerSentEvent(raw_data="[DONE]", event="done")
        except Exception as exc:
            yield ServerSentEvent(raw_data=f"[ERROR] {type(exc).__name__}: {exc}", event="error")
    return stream()
