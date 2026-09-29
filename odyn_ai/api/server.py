from __future__ import annotations

from collections.abc import AsyncIterable
from contextlib import asynccontextmanager
import os

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.sse import EventSourceResponse, ServerSentEvent
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from odyn_ai.config import load_config
from odyn_ai.core.agents import AgentManager
from odyn_ai.core.builders import AppBuilder
from odyn_ai.core.engine import DualGGUFEngine
from odyn_ai.core.document_generator import OdynDocumentBuilder
from odyn_ai.api.document_api_models import DocumentExportRequest, SpreadsheetExportRequest


config = load_config()
engine = DualGGUFEngine(config)
agents = AgentManager()
apps = AppBuilder()
documents = OdynDocumentBuilder(os.getenv("ODYN_EXPORT_DIR", "exports"))
UI_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "ui")


@asynccontextmanager
async def lifespan(_: FastAPI):
    await engine.start()
    yield
    await engine.close()


app = FastAPI(
    title="ODYN AI",
    version="0.1.0",
    description="Lokalna platforma agentów AI ODYN AI. Interfejs i komunikaty użytkownika są w języku polskim.",
    lifespan=lifespan,
)
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
    prompt: str = ""
    can_search: bool = False
    mode: str = "no_code"
    code: str = ""


class AppCreate(BaseModel):
    name: str
    description: str = ""
    agent_id: str = "odyn_glowny"
    language: str = "pl"
    platform: str = "web"
    mode: str = "no_code"


class WorkspaceWrite(BaseModel):
    path: str
    content: str


class FormCreate(BaseModel):
    name: str


class FormFieldCreate(BaseModel):
    field_type: str
    label: str
    required: bool = False
    validation: str = ""
    default: str = ""
    options: list[str] = []




@app.get("/")
async def index(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={"agents": agents.list_agents()},
    )


@app.get("/api/status", summary="Pobierz status silnika")
async def status():
    return {"product": "ODYN AI", "language": "pl", "engine": engine.status()}


@app.get("/api/agents", summary="Pobierz listę agentów")
async def list_agents():
    return {"agents": agents.list_agents()}


@app.post("/api/agents", summary="Utwórz agenta")
async def create_agent(payload: AgentCreate):
    try:
        if payload.mode == "code":
            return agents.create_code(payload.agent_id, payload.name, payload.code)
        if payload.mode != "no_code":
            raise ValueError("Tryb agenta musi być: no_code albo code.")
        return agents.create(payload.agent_id, payload.name, payload.prompt, payload.can_search)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@app.get("/api/apps", summary="Pobierz listę aplikacji")
async def list_apps():
    return {"apps": apps.list_apps()}


@app.post("/api/apps", summary="Utwórz aplikację")
async def create_app(payload: AppCreate):
    try:
        return apps.create(payload.name, payload.description, payload.agent_id, payload.language, payload.platform, payload.mode)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc



@app.post("/api/apps/{app_id}/forms", summary="Utwórz formularz No Code")
async def create_form(app_id: str, payload: FormCreate):
    try:
        return apps.create_form(app_id, payload.name)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@app.post("/api/forms/{form_id}/fields", summary="Dodaj pole formularza No Code")
async def add_form_field(form_id: str, payload: FormFieldCreate):
    try:
        return apps.add_form_field(form_id, payload.field_type, payload.label, required=payload.required, validation=payload.validation, default=payload.default, options=payload.options)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@app.get("/api/forms/{form_id}", summary="Pobierz formularz No Code")
async def get_form(form_id: str):
    try:
        return apps.get_form(form_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc


@app.get("/api/forms/{form_id}/preview", summary="Podgląd formularza No Code")
async def form_preview(form_id: str):
    try:
        return apps.form_preview(form_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc


@app.get("/api/apps/{app_id}/workspace", summary="Pobierz projekt IDE")
async def get_workspace(app_id: str):
    try:
        return apps.workspace(app_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc


@app.get("/api/apps/{app_id}/files", summary="Pobierz pliki projektu")
async def get_workspace_files(app_id: str):
    try:
        return apps.read_file(app_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc


@app.put("/api/apps/{app_id}/files", summary="Zapisz plik projektu")
async def write_workspace_file(app_id: str, payload: WorkspaceWrite):
    try:
        return apps.write_file(app_id, payload.path, payload.content)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@app.post("/chat/stream", response_class=EventSourceResponse, summary="Rozpocznij strumieniową rozmowę")
async def chat_stream(payload: ChatRequest) -> AsyncIterable[ServerSentEvent]:
    definition = agents.get(payload.agent_id)
    messages = [{"role": "system", "content": definition.prompt}]
    messages += [
        {"role": m.role, "content": m.content}
        for m in payload.history[-40:]
        if m.role in {"user", "assistant", "system"}
    ]
    messages.append({"role": "user", "content": payload.message})
    messages = await agents.preprocess(messages, payload.agent_id)

    async def stream() -> AsyncIterable[ServerSentEvent]:
        try:
            yield ServerSentEvent(comment="Strumień ODYN AI uruchomiony")
            async for token in engine.stream_chat(messages):
                yield ServerSentEvent(raw_data=token, event="token")
            yield ServerSentEvent(raw_data="[DONE]", event="done")
        except Exception as exc:
            yield ServerSentEvent(
                raw_data=f"[BŁĄD] {type(exc).__name__}: {exc}",
                event="error",
            )

    return stream()
