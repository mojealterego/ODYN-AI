from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
import json
import shutil
import subprocess
from typing import Any

import httpx

from odyn_ai.config import DRAFT_MODEL_PATH, MAIN_MODEL_PATH, LLMConfig


class DualGGUFEngine:
    """Warstwa inferencji. Dwa modele GGUF korzystają z llama-server."""

    def __init__(self, config: LLMConfig) -> None:
        self.config = config
        self._process: subprocess.Popen[str] | None = None
        self._python_llm: Any | None = None
        self.backend = self._choose_backend()

    def _choose_backend(self) -> str:
        models = MAIN_MODEL_PATH.is_file() and DRAFT_MODEL_PATH.is_file()
        server = shutil.which(self.config.llama_server_bin) is not None

        if self.config.backend == "server":
            if not models:
                raise FileNotFoundError("Brak obu wymaganych modeli GGUF.")
            if not server:
                raise FileNotFoundError(f"Nie znaleziono programu llama-server: {self.config.llama_server_bin}")
            return "server"

        if self.config.backend == "auto" and models and server:
            return "server"

        return "python"

    @property
    def true_dual_gguf(self) -> bool:
        return self.backend == "server"

    async def start(self) -> None:
        if self.backend == "server":
            await self._start_server()
        else:
            await asyncio.to_thread(self._load_python)

    async def _start_server(self) -> None:
        command = [
            self.config.llama_server_bin,
            "-m",
            str(MAIN_MODEL_PATH),
            "--model-draft",
            str(DRAFT_MODEL_PATH),
            "--spec-type",
            "draft-simple",
            "--spec-draft-n-max",
            str(self.config.draft_tokens),
            "-c",
            str(self.config.n_ctx),
            "-ngl",
            str(self.config.n_gpu_layers_main),
            "-ngld",
            str(self.config.n_gpu_layers_draft),
            "--host",
            self.config.server_host,
            "--port",
            str(self.config.server_port),
            "--jinja",
            "--alias",
            "odyn-main",
        ]
        self._process = subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
        )
        deadline = asyncio.get_running_loop().time() + self.config.server_start_timeout

        async with httpx.AsyncClient(timeout=2) as client:
            while asyncio.get_running_loop().time() < deadline:
                if self._process.poll() is not None:
                    raise RuntimeError("llama-server zakończył pracę podczas uruchamiania.")
                try:
                    if (
                        await client.get(
                            f"http://{self.config.server_host}:{self.config.server_port}/health"
                        )
                    ).is_success:
                        return
                except httpx.HTTPError:
                    pass
                await asyncio.sleep(.25)

        raise TimeoutError("llama-server nie osiągnął gotowości w wyznaczonym czasie.")

    def _load_python(self) -> None:
        if self._python_llm is not None:
            return
        if not MAIN_MODEL_PATH.is_file():
            raise FileNotFoundError(f"Brak głównego modelu GGUF: {MAIN_MODEL_PATH}")

        from llama_cpp import Llama
        from llama_cpp.llama_speculative import LlamaPromptLookupDecoding

        self._python_llm = Llama(
            model_path=str(MAIN_MODEL_PATH),
            n_ctx=self.config.n_ctx,
            n_threads=self.config.n_threads,
            n_gpu_layers=self.config.n_gpu_layers_main,
            draft_model=LlamaPromptLookupDecoding(num_pred_tokens=self.config.draft_tokens),
            verbose=False,
        )

    @staticmethod
    def _validate_inference_params(
        inference_params: dict[str, float] | None,
    ) -> dict[str, float]:
        params = {
            "temperature": float(inference_params["temperature"])
            if inference_params and "temperature" in inference_params
            else None,
            "top_p": float(inference_params["top_p"])
            if inference_params and "top_p" in inference_params
            else None,
        }
        if params["temperature"] is not None and not 0 <= params["temperature"] <= 2:
            raise ValueError("temperature must be between 0 and 2")
        if params["top_p"] is not None and not 0 < params["top_p"] <= 1:
            raise ValueError("top_p must be between 0 and 1")
        return {key: value for key, value in params.items() if value is not None}

    def effective_inference_params(
        self, inference_params: dict[str, float] | None = None
    ) -> dict[str, float]:
        overrides = self._validate_inference_params(inference_params)
        return {
            "temperature": overrides.get("temperature", self.config.temperature),
            "top_p": overrides.get("top_p", self.config.top_p),
        }
    async def stream_chat(
        self,
        messages: list[dict[str, str]],
        *,
        inference_params: dict[str, float] | None = None,
    ) -> AsyncIterator[str]:
        params = self.effective_inference_params(inference_params)
        if self.backend == "server":
            async for token in self._stream_server(messages, params):
                yield token
            return

        if self._python_llm is None:
            await asyncio.to_thread(self._load_python)

        queue: asyncio.Queue[str | BaseException | None] = asyncio.Queue()
        loop = asyncio.get_running_loop()

        def produce() -> None:
            try:
                stream = self._python_llm.create_chat_completion(
                    messages=messages,
                    temperature=params["temperature"],
                    top_p=params["top_p"],
                    top_k=self.config.top_k,
                    max_tokens=self.config.max_tokens,
                    stream=True,
                )
                for chunk in stream:
                    content = chunk.get("choices", [{}])[0].get("delta", {}).get("content")
                    if content:
                        loop.call_soon_threadsafe(queue.put_nowait, content)
            except BaseException as exc:
                loop.call_soon_threadsafe(queue.put_nowait, exc)
            finally:
                loop.call_soon_threadsafe(queue.put_nowait, None)

        asyncio.create_task(asyncio.to_thread(produce))

        while True:
            item = await queue.get()
            if item is None:
                break
            if isinstance(item, BaseException):
                raise RuntimeError(str(item)) from item
            yield item

    async def _stream_server(
        self, messages: list[dict[str, str]], params: dict[str, float]
    ) -> AsyncIterator[str]:
        url = f"http://{self.config.server_host}:{self.config.server_port}/v1/chat/completions"
        payload = {
            "model": "odyn-main",
            "messages": messages,
            "temperature": params["temperature"],
            "top_p": params["top_p"],
            "max_tokens": self.config.max_tokens,
            "stream": True,
        }

        async with httpx.AsyncClient(timeout=None) as client:
            async with client.stream("POST", url, json=payload) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        return
                    try:
                        obj = json.loads(data)
                    except ValueError:
                        continue
                    content = obj.get("choices", [{}])[0].get("delta", {}).get("content")
                    if content:
                        yield content

    async def close(self) -> None:
        if self._process is not None:
            self._process.terminate()
            try:
                await asyncio.to_thread(self._process.wait, 5)
            except subprocess.TimeoutExpired:
                self._process.kill()
            self._process = None

        self._python_llm = None

    def status(self) -> dict[str, object]:
        return {
            "backend": self.backend,
            "true_dual_gguf": self.true_dual_gguf,
            "main_model": MAIN_MODEL_PATH.name,
            "main_model_present": MAIN_MODEL_PATH.is_file(),
            "draft_model": DRAFT_MODEL_PATH.name,
            "draft_model_present": DRAFT_MODEL_PATH.is_file(),
            "llama_server": shutil.which(self.config.llama_server_bin),
        }
