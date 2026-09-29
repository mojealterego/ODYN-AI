from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any

from nexus_core.memory import BitemporalMemoryNode, MemoryEpisode

from odyn_ai.core.rag_memory import RAGMemoryEngine


class AgentExperienceMemory:
    """Adapter joining durable bitemporal memory with semantic RAG recall."""

    def __init__(
        self,
        store: BitemporalMemoryNode | None = None,
        rag: RAGMemoryEngine | None = None,
    ) -> None:
        self.store = store or BitemporalMemoryNode(
            os.getenv("ODYN_MEMORY_DB", "nexus_bitemporal.db")
        )
        self.rag = rag
        self._last_task_id: int | None = None

    def remember(
        self,
        event_type: str,
        payload: dict[str, Any],
        *,
        valid_start: datetime | None = None,
        agent_id: str = "odyn_orchestrator",
    ) -> MemoryEpisode:
        return self.store.record_episode(
            agent_id,
            event_type,
            payload,
            valid_start or datetime.now(timezone.utc),
        )

    def recall(self, query: str, top_k: int = 4) -> str:
        if not self.rag:
            return ""
        try:
            return self.rag.retrieve_relevant(query, top_k=top_k)
        except Exception:
            # Memory must never make the build pipeline unavailable.
            return ""

    def remember_and_index(
        self,
        event_type: str,
        payload: dict[str, Any],
        *,
        text: str | None = None,
        agent_id: str = "odyn_orchestrator",
    ) -> MemoryEpisode:
        episode = self.remember(event_type, payload, agent_id=agent_id)
        if self.rag and text:
            try:
                self.rag.add_memory(text)
            except Exception:
                pass
        return episode

    def start_task(self, app_id: str, instruction: str, platform: str) -> MemoryEpisode:
        episode = self.remember_and_index(
            "task_started",
            {"app_id": app_id, "instruction": instruction, "platform": platform},
            text=f"Zadanie ODYN: {instruction}. Platforma: {platform}.",
        )
        self._last_task_id = episode.id
        return episode

    def record_decision(
        self,
        app_id: str,
        instruction: str,
        summary: str,
        changes: list[dict[str, str]],
    ) -> MemoryEpisode:
        return self.remember_and_index(
            "coding_decision",
            {
                "app_id": app_id,
                "instruction": instruction,
                "summary": summary,
                "changed_paths": [item["path"] for item in changes],
            },
            text=(
                f"Decyzja Coding Agent dla {app_id}: {summary}. "
                f"Zmiany: {', '.join(item['path'] for item in changes)}."
            ),
        )

    def record_changes(
        self,
        app_id: str,
        changes: list[dict[str, str]],
    ) -> list[MemoryEpisode]:
        records = []
        for change in changes:
            records.append(
                self.remember_and_index(
                    "code_change",
                    {
                        "app_id": app_id,
                        "path": change["path"],
                        "content_size": len(change["content"].encode("utf-8")),
                    },
                    text=f"Zmiana kodu {app_id}: {change['path']}",
                )
            )
        return records

    def record_execution(
        self,
        app_id: str,
        stage: str,
        result: dict[str, Any],
    ) -> MemoryEpisode:
        payload = {
            "app_id": app_id,
            "stage": stage,
            "ok": result.get("ok", False),
            "exit_code": result.get("exit_code"),
            "artifact": result.get("artifact"),
            "duration_ms": result.get("duration_ms", 0),
            "diagnostics": result.get("diagnostics", []),
            "stdout": result.get("stdout", "")[-4000:],
            "stderr": result.get("stderr", "")[-4000:],
        }
        text = (
            f"Wynik {stage} dla {app_id}: "
            f"{'PASS' if payload['ok'] else 'FAIL'}. "
            f"Diagnostyka: {' | '.join(payload['diagnostics'])}"
        )
        return self.remember_and_index(f"{stage}_result", payload, text=text)

    def record_correction(
        self,
        app_id: str,
        stage: str,
        diagnostics: list[str],
        changes: list[dict[str, str]],
        *,
        failed_execution_id: int | None = None,
    ) -> MemoryEpisode:
        episode = self.remember_and_index(
            "correction",
            {
                "app_id": app_id,
                "failed_stage": stage,
                "diagnostics": diagnostics,
                "changed_paths": [item["path"] for item in changes],
                "failed_execution_id": failed_execution_id,
            },
            text=(
                f"Korekta po błędzie {stage} dla {app_id}. "
                f"Problem: {' | '.join(diagnostics)}. "
                f"Poprawione pliki: {', '.join(item['path'] for item in changes)}."
            ),
        )
        if failed_execution_id is not None:
            try:
                self.store.link(episode.id, failed_execution_id, "corrects")
            except Exception:
                pass
        return episode

    def record_success(
        self,
        app_id: str,
        platform: str,
        stage: str,
        artifact: str | None,
        *,
        source_execution_id: int | None = None,
    ) -> MemoryEpisode:
        skill_name = f"{platform}.{stage}.verified"
        episode = self.remember_and_index(
            "successful_procedure",
            {
                "app_id": app_id,
                "platform": platform,
                "stage": stage,
                "artifact": artifact,
                "procedure": "edit → test → build → verify",
                "source_execution_id": source_execution_id,
            },
            text=(
                f"Skuteczna procedura ODYN: {platform}, {stage}. "
                f"Projekt {app_id} przeszedł weryfikację."
            ),
        )
        if source_execution_id is not None:
            try:
                self.store.link(episode.id, source_execution_id, "verified_by")
            except Exception:
                pass
        try:
            self.store.upsert_procedural_skill(
                skill_name,
                "odyn_ai.core.orchestrator.AutonomousBuildOrchestrator",
                1.0,
            )
        except Exception:
            pass
        return episode

    def snapshot(self) -> list[MemoryEpisode]:
        if self._last_task_id is None:
            return []
        return self.store.query(agent_id="odyn_orchestrator")

    @staticmethod
    def compact_result(result: Any) -> dict[str, Any]:
        if hasattr(result, "__dict__"):
            return json.loads(json.dumps(result.__dict__, default=str))
        return dict(result)
