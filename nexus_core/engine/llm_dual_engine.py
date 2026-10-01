from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

LlamaFactory = Callable[..., Any]

_DEFAULT_REJECTION_MARKERS = (
    "odrzucono",
    "błąd krytyczny",
    "critical error",
    "critical failure",
    "rejected",
)


@dataclass(frozen=True)
class DualModelConfig:
    """Runtime parameters for the independent Primary and Critic models."""

    primary_context: int = 8192
    critic_context: int = 2048
    n_gpu_layers_primary: int = -1
    n_gpu_layers_critic: int = -1
    n_threads_primary: int | None = None
    n_threads_critic: int | None = None
    primary_max_tokens: int = 1024
    critic_max_tokens: int = 256

    def __post_init__(self) -> None:
        if self.primary_context < 512:
            raise ValueError("primary_context must be at least 512")
        if self.critic_context < 512:
            raise ValueError("critic_context must be at least 512")
        if self.primary_max_tokens < 1:
            raise ValueError("primary_max_tokens must be positive")
        if self.critic_max_tokens < 1:
            raise ValueError("critic_max_tokens must be positive")


class DualModelEngine:
    """Independent GGUF Primary + Critic inference with non-blocking gating.

    llama-cpp-python is imported lazily so the rest of ODYN AI remains usable
    when the optional local-inference dependency is not installed.
    """

    def __init__(
        self,
        primary_path: str | Path,
        critic_path: str | Path,
        *,
        config: DualModelConfig | None = None,
        llama_factory: LlamaFactory | None = None,
        rejection_markers: tuple[str, ...] = _DEFAULT_REJECTION_MARKERS,
    ) -> None:
        self.primary_path = Path(primary_path)
        self.critic_path = Path(critic_path)
        self.config = config or DualModelConfig()
        self._llama_factory = llama_factory
        self._rejection_markers = tuple(marker.casefold() for marker in rejection_markers)

        self.primary: Any | None = None
        self.critic: Any | None = None
        self.last_evaluation = ""
        self.last_rejected = False
        self.last_gate_reason = "not_run"
        self._start_lock = asyncio.Lock()

    @staticmethod
    def _default_llama_factory() -> LlamaFactory:
        try:
            from llama_cpp import Llama
        except ImportError as exc:
            raise RuntimeError(
                "DualModelEngine wymaga opcjonalnej zależności 'llama-cpp-python'."
            ) from exc
        return Llama

    @property
    def llama_factory(self) -> LlamaFactory:
        return self._llama_factory or self._default_llama_factory()

    async def start(self) -> None:
        """Load both GGUF models without blocking or duplicating startup."""
        if self.primary is not None and self.critic is not None:
            return

        async with self._start_lock:
            if self.primary is not None and self.critic is not None:
                return
            loop = asyncio.get_running_loop()
            self.primary, self.critic = await asyncio.gather(
                loop.run_in_executor(None, self._load_primary),
                loop.run_in_executor(None, self._load_critic),
            )

    def _load_primary(self) -> Any:
        return self.llama_factory(
            model_path=str(self.primary_path),
            n_gpu_layers=self.config.n_gpu_layers_primary,
            n_ctx=self.config.primary_context,
            **self._thread_arg(self.config.n_threads_primary),
            verbose=False,
        )

    def _load_critic(self) -> Any:
        return self.llama_factory(
            model_path=str(self.critic_path),
            n_gpu_layers=self.config.n_gpu_layers_critic,
            n_ctx=self.config.critic_context,
            **self._thread_arg(self.config.n_threads_critic),
            verbose=False,
        )

    @staticmethod
    def _thread_arg(value: int | None) -> dict[str, int]:
        return {} if value is None else {"n_threads": value}

    @staticmethod
    def _extract_text(response: Any) -> str:
        try:
            return str(response["choices"][0]["text"])
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError("Nieprawidłowa odpowiedź z llama.cpp.") from exc

    def _primary_completion(
        self,
        prompt: str,
        *,
        max_tokens: int,
        temperature: float,
        top_p: float,
        top_k: int,
    ) -> str:
        if self.primary is None:
            raise RuntimeError("DualModelEngine nie został uruchomiony.")
        response = self.primary.create_completion(
            prompt,
            max_tokens=max_tokens,
            temperature=temperature,
            top_p=top_p,
            top_k=top_k,
        )
        return self._extract_text(response)

    def _critic_completion(
        self,
        prompt: str,
        *,
        max_tokens: int,
        temperature: float,
        top_p: float,
        top_k: int,
    ) -> str:
        if self.critic is None:
            raise RuntimeError("DualModelEngine nie został uruchomiony.")
        response = self.critic.create_completion(
            prompt,
            max_tokens=max_tokens,
            temperature=temperature,
            top_p=top_p,
            top_k=top_k,
        )
        return self._extract_text(response)

    def _is_rejected(self, evaluation: str) -> bool:
        normalized = evaluation.casefold()
        return any(marker in normalized for marker in self._rejection_markers)

    async def generate_primary(
        self,
        prompt: str,
        *,
        max_tokens: int | None = None,
        temperature: float = 0.65,
        top_p: float = 0.90,
        top_k: int = 40,
    ) -> str:
        if not prompt.strip():
            raise ValueError("prompt cannot be empty")
        await self.start()
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None,
            lambda: self._primary_completion(
                prompt,
                max_tokens=max_tokens or self.config.primary_max_tokens,
                temperature=temperature,
                top_p=top_p,
                top_k=top_k,
            ),
        )

    async def evaluate_critic(self, task: str, draft: str) -> str:
        if not task.strip() or not draft.strip():
            raise ValueError("task and draft cannot be empty")
        await self.start()
        prompt = (
            "SYSTEM: Jesteś krytykiem ODYN. Zwróć wyłącznie JSON z polami: "
            "decision, confidence, safety, logic, reason. decision musi być "
            "accept albo reject.\n\n"
            f"ZADANIE:\n{task}\n\nODPOWIEDŹ:\n{draft}"
        )
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None,
            lambda: self._critic_completion(
                prompt,
                max_tokens=self.config.critic_max_tokens,
                temperature=0.0,
                top_p=1.0,
                top_k=40,
            ),
        )

    async def correct_with_primary(
        self,
        task: str,
        draft: str,
        critic: Any,
        *,
        evidence: str = "",
    ) -> str:
        if not task.strip() or not draft.strip():
            raise ValueError("task and draft cannot be empty")
        await self.start()
        reason = getattr(critic, "reason", str(critic))
        prompt = (
            "SYSTEM: Popraw odpowiedź na podstawie krytyki. Zwróć tylko "
            "poprawioną odpowiedź. Nie opisuj procesu korekty.\n\n"
            f"ZADANIE:\n{task}\n\n"
            f"POPRZEDNIA ODPOWIEDŹ:\n{draft}\n\n"
            f"KRYTYKA:\n{reason}\n\n"
            f"DOWODY TEMPORALNE:\n{evidence or 'brak'}\n\n"
            "CORRECT"
        )
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None,
            lambda: self._primary_completion(
                prompt,
                max_tokens=self.config.primary_max_tokens,
                temperature=0.30,
                top_p=0.90,
                top_k=40,
            ),
        )

    async def generate_with_adversarial_gating(
        self,
        prompt: str,
        *,
        max_tokens: int | None = None,
        critic_max_tokens: int | None = None,
        temperature: float = 0.65,
        top_p: float = 0.90,
        top_k: int = 40,
    ) -> str:
        """Generate with Primary and validate the draft using the Critic model."""
        if not prompt.strip():
            raise ValueError("prompt cannot be empty")

        await self.start()
        loop = asyncio.get_running_loop()

        draft = await loop.run_in_executor(
            None,
            lambda: self._primary_completion(
                prompt,
                max_tokens=max_tokens or self.config.primary_max_tokens,
                temperature=temperature,
                top_p=top_p,
                top_k=top_k,
            ),
        )

        gate_prompt = (
            "SYSTEM: Oceń odpowiedź.\n"
            "Sprawdź bezpieczeństwo, błędy faktograficzne, błędy logiczne "
            "i zgodność z zadaniem. Jeśli występuje problem krytyczny, użyj "
            "jednoznacznie słowa ODRZUCONO lub BŁĄD KRYTYCZNY.\n\n"
            f"ZADANIE:\n{prompt}\n\n"
            f"ODPOWIEDŹ:\n{draft}\n"
        )
        evaluation = await loop.run_in_executor(
            None,
            lambda: self._critic_completion(
                gate_prompt,
                max_tokens=critic_max_tokens or self.config.critic_max_tokens,
                temperature=0.0,
                top_p=1.0,
                top_k=40,
            ),
        )

        self.last_evaluation = evaluation
        self.last_rejected = self._is_rejected(evaluation)
        self.last_gate_reason = "critic_rejected" if self.last_rejected else "accepted"

        if self.last_rejected:
            return (
                "Adversarial Gating Interwencja: "
                "Odpowiedź zatrzymana przez moduł ewaluacyjny."
            )

        return draft

    def status(self) -> dict[str, object]:
        return {
            "primary_model": self.primary_path.name,
            "critic_model": self.critic_path.name,
            "primary_loaded": self.primary is not None,
            "critic_loaded": self.critic is not None,
            "last_rejected": self.last_rejected,
            "last_gate_reason": self.last_gate_reason,
        }
