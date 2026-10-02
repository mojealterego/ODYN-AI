from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any

from odyn_ai.core.engine import DualGGUFEngine


@dataclass(frozen=True)
class FileChange:
    path: str
    content: str


class CodingAgent:
    """LLM-guided project editor with a strict machine-readable patch contract."""

    MAX_FILES = 20
    MAX_FILE_SIZE = 1_000_000

    def __init__(self, engine: DualGGUFEngine) -> None:
        self.engine = engine

    @staticmethod
    def _system(platform: str) -> str:
        return (
            "Jesteś ODYN Coding Agent. Edytujesz WYŁĄCZNIE przekazane pliki projektu. "
            "Zwracasz wyłącznie poprawny JSON bez markdown. Schemat: "
            '{"summary":"...","changes":[{"path":"relative/path","content":"pełna nowa treść"}]}. '
            "Nie wykonujesz poleceń, nie tworzysz sekretów, nie używasz ścieżek absolutnych ani .. . "
            "Jeżeli zmiana nie jest potrzebna, zwróć changes=[] . "
            f"Platforma projektu: {platform}."
        )

    async def propose(
        self,
        platform: str,
        instruction: str,
        files: dict[str, str],
        *,
        memory_context: str = "",
        inference_params: dict[str, float] | None = None,
    ) -> dict[str, Any]:
        if not instruction.strip():
            raise ValueError("Instrukcja zmiany jest wymagana.")

        compact = {k: v[: self.MAX_FILE_SIZE] for k, v in files.items()}
        context = memory_context.strip()
        prompt = (
            "INSTRUKCJA UŻYTKOWNIKA:\n"
            + instruction.strip()
            + (
                "\n\nDOŚWIADCZENIE Z PAMIĘCI ODYN:\n"
                + context
                if context
                else ""
            )
            + "\n\nPLIKI PROJEKTU:\n"
            + json.dumps(compact, ensure_ascii=False)
        )
        messages = [
            {"role": "system", "content": self._system(platform)},
            {"role": "user", "content": prompt},
        ]
        text = ""
        try:
            stream = self.engine.stream_chat(
                messages, inference_params=inference_params
            )
            async for token in stream:
                text += token
                if len(text) > 25_000_000:
                    raise ValueError("Odpowiedź Coding Agent jest zbyt duża.")
        except TypeError:
            async for token in self.engine.stream_chat(messages):
                text += token

        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError("Coding Agent nie zwrócił poprawnego JSON.") from exc

        changes = data.get("changes")
        if not isinstance(changes, list) or len(changes) > self.MAX_FILES:
            raise ValueError("Nieprawidłowa lista zmian Coding Agent.")

        normalized: list[dict[str, str]] = []
        for item in changes:
            if (
                not isinstance(item, dict)
                or not isinstance(item.get("path"), str)
                or not isinstance(item.get("content"), str)
            ):
                raise ValueError("Każda zmiana musi zawierać path i content.")
            path = PurePosixPath(item["path"])
            if path.is_absolute() or ".." in path.parts or item["path"].startswith("~"):
                raise ValueError(f"Niebezpieczna ścieżka zmiany: {item['path']}")
            if len(item["content"].encode("utf-8")) > self.MAX_FILE_SIZE:
                raise ValueError(f"Plik jest zbyt duży: {item['path']}")
            normalized.append({"path": str(path), "content": item["content"]})

        return {"summary": str(data.get("summary", "")), "changes": normalized}

    async def apply(
        self,
        platform: str,
        instruction: str,
        files: dict[str, str],
        *,
        memory_context: str = "",
        inference_params: dict[str, float] | None = None,
    ) -> dict[str, Any]:
        proposal = await self.propose(
            platform,
            instruction,
            files,
            memory_context=memory_context,
            inference_params=inference_params,
        )
        updated = dict(files)
        for change in proposal["changes"]:
            updated[change["path"]] = change["content"]
        return {**proposal, "files": updated}
