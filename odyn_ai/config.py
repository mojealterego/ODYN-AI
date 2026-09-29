from __future__ import annotations
import os
from pathlib import Path
from pydantic import BaseModel, Field, field_validator

BASE_DIR = Path(__file__).resolve().parent
MODELS_DIR = BASE_DIR / "models"
MAIN_MODEL_PATH = MODELS_DIR / os.getenv("ODYN_MAIN_MODEL", "model_glowny_normany.gguf")
DRAFT_MODEL_PATH = MODELS_DIR / os.getenv("ODYN_DRAFT_MODEL", "model_pomocniczy_maly.gguf")

class LLMConfig(BaseModel):
    n_ctx: int = Field(8192, ge=512, le=131072)
    n_threads: int = Field(max(1, (os.cpu_count() or 4) - 2), ge=1)
    n_gpu_layers_main: int = -1
    n_gpu_layers_draft: int = -1
    temperature: float = Field(.65, ge=0, le=2)
    top_p: float = Field(.9, gt=0, le=1)
    top_k: int = Field(40, ge=0)
    max_tokens: int = Field(2048, ge=1, le=32768)
    draft_tokens: int = Field(5, ge=1, le=32)
    backend: str = os.getenv("ODYN_BACKEND", "auto")
    llama_server_bin: str = os.getenv("ODYN_LLAMA_SERVER", "llama-server")
    server_host: str = os.getenv("ODYN_SERVER_HOST", "127.0.0.1")
    server_port: int = Field(int(os.getenv("ODYN_SERVER_PORT", "8091")), ge=1024, le=65535)
    server_start_timeout: float = Field(30, gt=0, le=300)

    @field_validator("backend")
    @classmethod
    def valid_backend(cls, value: str) -> str:
        value = value.strip().lower()
        if value not in {"auto", "server", "python"}:
            raise ValueError("backend must be auto, server or python")
        return value

SYSTEM_PROMPTS = {
    "default": "Jesteś ODYN AI. Odpowiadasz po polsku, precyzyjnie i rzeczowo. Nie zmyślasz faktów.",
    "coder": "Jesteś ODYN AI Koder. Projektujesz bezpieczne oprogramowanie produkcyjne. Odpowiadasz po polsku i stosujesz testy.",
    "researcher": "Jesteś ODYN AI Czarny Kruk. Analizujesz źródła internetowe, oddzielasz fakty od wniosków i odpowiadasz po polsku.",
}
def load_config() -> LLMConfig:
    return LLMConfig()
