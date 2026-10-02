from __future__ import annotations

from collections.abc import AsyncIterable
import asyncio
from contextlib import asynccontextmanager
import os

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.sse import EventSourceResponse, ServerSentEvent
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from odyn_ai.config import STTConfig, load_config
from odyn_ai.core.agents import AgentManager
from odyn_ai.core.builders import AppBuilder
from odyn_ai.core.engine import DualGGUFEngine
from odyn_ai.core.mcp_gateway import MCPAuth, MCPGateway
from odyn_ai.core.secret_manager import NativeSecretManager
from odyn_ai.core.document_generator import OdynDocumentBuilder
from odyn_ai.core.speech_to_text import SpeechToText, SpeechToTextError
from odyn_ai.core.execution import ExecutionEngine, ExecutionRequest
from odyn_ai.core.coding_agent import CodingAgent
from odyn_ai.core.github_integration import GitHubIntegration
from odyn_ai.core.orchestrator import AutonomousBuildOrchestrator
from odyn_ai.core.experience_memory import AgentExperienceMemory
from odyn_ai.core.evolution import build_production_swarm
from odyn_ai.core.rag_memory import RAGMemoryEngine
from odyn_ai.core.voice_commands import parse_voice_command
from nexus_core.reasoning import CognitiveEngine
from odyn_ai.api.document_api_models import DocumentExportRequest, ReportExportRequest, SpreadsheetExportRequest
from odyn_ai.api.mcp_api_models import MCPServerRequest, MCPToolRequest


config = load_config()
engine = DualGGUFEngine(config)
stt_config = STTConfig()
stt = SpeechToText(model_name=stt_config.model, device=stt_config.device, compute_type=stt_config.compute_type, max_audio_bytes=stt_config.max_audio_bytes, language=stt_config.language)
agents = AgentManager()
apps = AppBuilder()
documents = OdynDocumentBuilder(os.getenv("ODYN_EXPORT_DIR", "exports"))
mcp_allowed_hosts = {h.strip().lower() for h in os.getenv("ODYN_MCP_ALLOWED_HOSTS", "").split(",") if h.strip()}
mcp_policy = {}
for item in os.getenv("ODYN_MCP_TOOL_POLICY", "").split(","):
    if "=" in item:
        tool, rule = item.split("=", 1)
        mcp_policy[tool.strip()] = rule.strip()
mcp_secret_manager = None
try:
    mcp_secret_manager = NativeSecretManager()
except RuntimeError:
    mcp_secret_manager = None
mcp_gateway = MCPGateway(secret_manager=mcp_secret_manager, timeout=float(os.getenv("ODYN_MCP_TIMEOUT", "30")), allowed_hosts=mcp_allowed_hosts, tool_policy=mcp_policy, rate_limit=int(os.getenv("ODYN_MCP_RATE_LIMIT", "30")))
execution = ExecutionEngine()
coding_agent = CodingAgent(engine)
github = GitHubIntegration()
cognitive_engine = CognitiveEngine(
    evaluation_threshold=float(os.getenv("ODYN_COGNITIVE_EVAL_THRESHOLD", "0.80")),
    stress_threshold=float(os.getenv("ODYN_COGNITIVE_STRESS_THRESHOLD", "0.80")),
    max_reflections=int(os.getenv("ODYN_COGNITIVE_MAX_REFLECTIONS", "2")),
)

# Durable experience memory is always available. RAG is enabled only when
# an embedding GGUF is explicitly present/configured.
rag = None
rag_model = os.getenv("ODYN_RAG_EMBEDDING_MODEL", "")
if rag_model and os.path.isfile(rag_model):
    rag = RAGMemoryEngine(
        rag_model,
        data_path=os.getenv("ODYN_RAG_MEMORY_PATH", "odyn_rag_memory.json"),
    )
experience_memory = AgentExperienceMemory(rag=rag)

# Evolution swarm is enabled only when its external credentials are configured.
# The core ODYN pipeline remains usable without Hugging Face/GitLab credentials.
evolution_swarm = None
if all(os.getenv(name) for name in ("HF_TOKEN", "GL_TOKEN", "GL_PROJECT_ID")):
    try:
        evolution_swarm = build_production_swarm()
    except (RuntimeError, ValueError):
        evolution_swarm = None

orchestrator = AutonomousBuildOrchestrator(
    apps,
    execution,
    coding_agent,
    github,
    experience_memory,
    swarm=evolution_swarm,
    evolution_branch=os.getenv("ODYN_EVOLUTION_BRANCH", "odyn-evolution"),
)
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


class ExecutionRequestModel(BaseModel):
    action: str
    timeout: float = Field(default=300, gt=0, le=900)


class AgentEditRequest(BaseModel):
    instruction: str = Field(min_length=1, max_length=20000)


class GitHubCommitRequest(BaseModel):
    repository: str
    branch: str = "main"
    message: str = Field(min_length=1, max_length=200)
    create_branch: bool = False


class VoiceCommandRequest(BaseModel):
    text: str = Field(min_length=1, max_length=20000)
    app_id: str | None = None
    timeout: float = Field(default=300, gt=0, le=900)
    github_repository: str | None = None
    github_branch: str = "main"
    github_message: str = "feat(odyn): autonomous voice build"


class AutonomousBuildRequest(BaseModel):
    instruction: str = Field(min_length=1, max_length=20000)
    timeout: float = Field(default=300, gt=0, le=900)
    github_repository: str | None = None
    github_branch: str = "main"
    github_message: str = "feat(odyn): autonomous project update"


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



@app.get("/api/mcp/servers", summary="Pobierz zarejestrowane serwery MCP")
async def list_mcp_servers():
    return {"servers": mcp_gateway.list_servers()}


@app.post("/api/mcp/servers", summary="Zarejestruj serwer MCP")
async def register_mcp_server(payload: MCPServerRequest):
    try:
        return mcp_gateway.register_mcp_server(payload.name, payload.endpoint, auth=MCPAuth(kind=payload.auth_kind, secret_env=payload.secret_env, header=payload.auth_header, prefix=payload.auth_prefix, client_id_env=payload.client_id_env, client_secret_env=payload.client_secret_env, token_url=payload.token_url, scope=payload.scope, authorization_url=payload.authorization_url, redirect_uri=payload.redirect_uri, client_id=payload.client_id)).__dict__
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(403, str(exc)) from exc


@app.get("/api/mcp/servers/{server_name}/oauth/authorize", summary="Rozpocznij OAuth Authorization Code + PKCE")
async def start_mcp_oauth(server_name: str):
    try:
        request = mcp_gateway.create_oauth_authorization(server_name)
        return {"url": request.url, "state": request.state}
    except (ValueError, PermissionError) as exc:
        raise HTTPException(403, str(exc)) from exc


@app.post("/api/mcp/servers/{server_name}/oauth/callback", summary="Zakończ OAuth Authorization Code + PKCE")
async def complete_mcp_oauth(server_name: str, code: str, state: str):
    try:
        token = await mcp_gateway.complete_oauth_authorization(server_name, code, state)
        return {"token_type": token.token_type, "expires_in": token.expires_in, "scope": token.scope}
    except (ValueError, PermissionError) as exc:
        raise HTTPException(403, str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(502, str(exc)) from exc


@app.delete("/api/mcp/servers/{server_name}", summary="Wyrejestruj serwer MCP")
async def unregister_mcp_server(server_name: str):
    if not mcp_gateway.unregister_mcp_server(server_name):
        raise HTTPException(404, "Serwer MCP nie jest zarejestrowany.")
    return {"removed": True, "name": server_name}


@app.post("/api/mcp/servers/{server_name}/initialize", summary="Zainicjalizuj serwer MCP")
async def initialize_mcp_server(server_name: str):
    try:
        return await mcp_gateway.initialize(server_name)
    except (ValueError, RuntimeError, TimeoutError) as exc:
        raise HTTPException(502, str(exc)) from exc


@app.get("/api/mcp/servers/{server_name}/tools", summary="Odkryj narzędzia serwera MCP")
async def list_mcp_tools(server_name: str):
    try:
        return {"tools": await mcp_gateway.discover_tools(server_name)}
    except (ValueError, RuntimeError, TimeoutError) as exc:
        raise HTTPException(502, str(exc)) from exc


@app.post("/api/mcp/tools/execute", summary="Wywołaj narzędzie MCP")
async def execute_mcp_tool(payload: MCPToolRequest):
    try:
        return await mcp_gateway.execute_tool(payload.server_name, payload.tool_name, payload.payload)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(403, str(exc)) from exc
    except (RuntimeError, TimeoutError) as exc:
        raise HTTPException(502, str(exc)) from exc


@app.post("/api/stt/transcribe", summary="Transkrybuj nagranie głosowe lokalnym Whisperem")
async def transcribe_audio(file: UploadFile = File(...)):
    content_type = (file.content_type or "").split(";", 1)[0].strip().lower()
    if content_type not in {"audio/webm", "audio/ogg", "audio/wav", "audio/x-wav", "audio/mpeg", "audio/mp4", "audio/x-m4a"}:
        raise HTTPException(415, "Nieobsługiwany format audio.")
    audio = await file.read(stt_config.max_audio_bytes + 1)
    if len(audio) > stt_config.max_audio_bytes:
        raise HTTPException(413, f"Plik audio przekracza limit {stt_config.max_audio_bytes // (1024 * 1024)} MB.")
    try:
        text = await asyncio.to_thread(stt.transcribe_bytes, audio, content_type)
        return {"text": text, "language": stt_config.language, "model": stt_config.model, "backend": "local-whisper"}
    except SpeechToTextError as exc:
        raise HTTPException(422, str(exc)) from exc


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


@app.post("/api/apps/{app_id}/agent/edit", summary="Agent automatycznie edytuje projekt")
async def agent_edit_project(app_id: str, payload: AgentEditRequest):
    try:
        project = apps.workspace(app_id)
        result = await coding_agent.apply(project["platform"], payload.instruction, project["files"])
        for path, content in result["files"].items():
            if project["files"].get(path) != content:
                apps.write_file(app_id, path, content)
        return {"app_id": app_id, "summary": result["summary"], "changes": result["changes"], "files": sorted(result["files"]), "persisted": True}
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(502, f"Coding Agent nie wykonał zmiany: {exc}") from exc


@app.post("/api/apps/{app_id}/execute", summary="Uruchom Test/Build/Run projektu")
async def execute_project(app_id: str, payload: ExecutionRequestModel):
    try:
        project = apps.workspace(app_id)
        if payload.action not in {"run", "build", "test"}:
            raise ValueError("Akcja musi być: run, build albo test.")
        result = await execution.execute(ExecutionRequest(project["platform"], payload.action, project["files"], payload.timeout))
        return result.__dict__
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@app.post("/api/apps/{app_id}/autonomous-build", summary="Autonomicznie edytuj, testuj, buduj i weryfikuj projekt")
async def autonomous_build(app_id: str, payload: AutonomousBuildRequest):
    try:
        result = await orchestrator.run(app_id, payload.instruction, payload.timeout, payload.github_repository, payload.github_branch, payload.github_message)
        return result.__dict__
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(403, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(502, f"Pipeline ODYN: {exc}") from exc



@app.get("/api/reasoning/snapshot", summary="Pobierz aktualny graf myśli ODYN")
async def reasoning_snapshot():
    return cognitive_engine.snapshot()


@app.post("/api/reasoning/modulation", summary="Oblicz parametry inferencji dla poziomu stresu zadania")
async def reasoning_modulation(stress: float):
    try:
        return cognitive_engine.cognitive_modulation(stress)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc

@app.post("/api/voice/command", summary="Wykonaj głosową komendę budowy aplikacji")
async def voice_command(payload: VoiceCommandRequest):
    command = parse_voice_command(payload.text)
    if command is None:
        return {
            "executed": False,
            "action": "chat",
            "message": "To nie jest jawna komenda budowy aplikacji.",
        }

    app_id = payload.app_id
    created = None
    try:
        if app_id:
            project = apps.workspace(app_id)
            platform = project["platform"]
        else:
            created = apps.create(
                command.name,
                command.instruction,
                "odyn_glowny",
                "pl",
                command.platform,
                "code",
            )
            app_id = str(created["app_id"])
            platform = command.platform

        result = await orchestrator.run(
            app_id,
            command.instruction,
            payload.timeout,
            payload.github_repository,
            payload.github_branch,
            payload.github_message,
        )
        return {
            "executed": True,
            "action": command.action,
            "app_id": app_id,
            "created": created is not None,
            "name": command.name,
            "platform": platform,
            "result": result.__dict__,
        }
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(403, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(502, f"Głosowy pipeline ODYN: {exc}") from exc


@app.post("/api/apps/{app_id}/github/commit", summary="Wyślij projekt do GitHub")
async def commit_project_to_github(app_id: str, payload: GitHubCommitRequest):
    try:
        project = apps.workspace(app_id)
        result = await github.commit_files(payload.repository, project["files"], payload.message, payload.branch, payload.create_branch)
        return result.__dict__
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(403, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(502, f"GitHub API: {exc}") from exc


def _document_response(path: str, media_type: str) -> FileResponse:
    return FileResponse(path, media_type=media_type, filename=os.path.basename(path))


@app.post("/api/documents/pdf", summary="Eksportuj dokument PDF")
async def export_pdf(payload: DocumentExportRequest):
    path = documents.generate_pdf(payload.title, payload.content, payload.filename)
    return _document_response(path, "application/pdf")


@app.post("/api/documents/docx", summary="Eksportuj dokument DOCX")
async def export_docx(payload: DocumentExportRequest):
    path = documents.generate_docx(payload.title, payload.content, payload.filename)
    return _document_response(
        path,
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )


@app.post("/api/documents/xlsx", summary="Eksportuj arkusz XLSX")
async def export_xlsx(payload: SpreadsheetExportRequest):
    path = documents.generate_xlsx(
        payload.data,
        payload.filename,
        sheet_name=payload.sheet_name,
        header=payload.header,
    )
    return _document_response(
        path,
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@app.post("/api/reports/export", summary="Eksportuj raport ODYN do wybranego formatu")
async def export_report(payload: ReportExportRequest):
    path = documents.generate_report(
        payload.format,
        payload.title,
        payload.content,
        payload.filename,
        data=payload.data,
        sheet_name=payload.sheet_name,
        header=payload.header,
    )
    media_types = {
        "pdf": "application/pdf",
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    }
    return _document_response(path, media_types[payload.format])


@app.post("/api/agents/{agent_id}/reports/export", summary="Eksportuj raport wygenerowany przez agenta")
async def export_agent_report(agent_id: str, payload: ReportExportRequest):
    try:
        agents.get(agent_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
    return await export_report(payload)


@app.post("/chat/stream", response_class=EventSourceResponse, response_model=None, summary="Rozpocznij strumieniową rozmowę")
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
