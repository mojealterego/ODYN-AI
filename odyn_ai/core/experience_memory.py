from __future__ import annotations

import hashlib
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
                self.rag.add_memory(
                    text,
                    episode_id=episode.id,
                    metadata={
                        "agent_id": episode.agent_id,
                        "event_type": episode.event_type,
                        "valid_time_start": episode.valid_time_start.isoformat(),
                    },
                )
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

    def record_cognitive_plan(
        self,
        app_id: str,
        task: str,
        strategies: list[str],
        selected_strategy: str,
        *,
        cognitive_node_id: str | None = None,
        environmental_stress: float | None = None,
        context: dict[str, Any] | None = None,
    ) -> MemoryEpisode:
        return self.remember_and_index(
            "cognitive_plan",
            {
                "app_id": app_id,
                "task": task,
                "strategies": strategies,
                "selected_strategy": selected_strategy,
                "cognitive_node_id": cognitive_node_id,
                "environmental_stress": environmental_stress,
                "context": dict(context or {}),
            },
            text=(
                f"Plan kognitywny dla {app_id}: wybrano {selected_strategy}. "
                f"Alternatywy: {', '.join(strategies)}."
            ),
        )

    @staticmethod
    def infer_task_context(task: str, platform: str, files: dict[str, str] | None = None) -> dict[str, Any]:
        """Derive stable, non-sensitive features used to scope meta-learning."""
        text = task.lower()
        files = files or {}
        paths = " ".join(files).lower()
        if any(word in text for word in ("bug", "fix", "napraw", "error", "failure", "błąd")):
            task_type = "bugfix"
        elif any(word in text for word in ("refactor", "redesign", "architekt", "przebud")):
            task_type = "refactor"
        elif any(word in text for word in ("feature", "dodaj", "add", "implement", "wdroż")):
            task_type = "feature"
        else:
            task_type = "general"

        if platform == "android" or "build.gradle" in paths or "androidmanifest" in paths:
            architecture = "android"
        elif any(token in paths for token in ("react", "tsx", "vite", "next.config")):
            architecture = "react"
        elif "pyproject.toml" in paths or any(token in paths for token in (".py", "fastapi", "django")):
            architecture = "python"
        else:
            architecture = "unknown"

        return {
            "platform": platform,
            "task_type": task_type,
            "architecture": architecture,
        }

    def record_cognitive_strategy(
        self,
        app_id: str,
        strategy: str,
        *,
        selected: bool,
        cognitive_node_id: str | None = None,
    ) -> MemoryEpisode:
        return self.remember_and_index(
            "cognitive_strategy",
            {
                "app_id": app_id,
                "strategy": strategy,
                "selected": selected,
                "cognitive_node_id": cognitive_node_id,
            },
            text=f"Strategia kognitywna {app_id}: {strategy}; wybrana={selected}.",
        )

    def record_reflexion(
        self,
        app_id: str,
        stage: str,
        failure: str,
        *,
        failed_execution_id: int | None = None,
        cognitive_node_id: str | None = None,
    ) -> MemoryEpisode:
        episode = self.remember_and_index(
            "reflexion",
            {
                "app_id": app_id,
                "stage": stage,
                "failure": failure,
                "failed_execution_id": failed_execution_id,
                "cognitive_node_id": cognitive_node_id,
            },
            text=f"Refleksja po błędzie {stage} dla {app_id}: {failure}",
        )
        if failed_execution_id is not None:
            try:
                self.store.link(episode.id, failed_execution_id, "reflects_on")
            except Exception:
                pass
        return episode

    def record_decision(
        self,
        app_id: str,
        instruction: str,
        summary: str,
        changes: list[dict[str, str]],
        *,
        cognitive_strategy: str | None = None,
        cognitive_node_id: str | None = None,
    ) -> MemoryEpisode:
        return self.remember_and_index(
            "coding_decision",
            {
                "app_id": app_id,
                "instruction": instruction,
                "summary": summary,
                "changed_paths": [item["path"] for item in changes],
                "cognitive_strategy": cognitive_strategy,
                "cognitive_node_id": cognitive_node_id,
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
        *,
        decision_id: int | None = None,
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
                        "content_sha256": hashlib.sha256(
                            change["content"].encode("utf-8")
                        ).hexdigest(),
                    },
                    text=f"Zmiana kodu {app_id}: {change['path']}",
                )
            )
            if decision_id is not None:
                try:
                    self.store.link(records[-1].id, decision_id, "produced_by")
                except Exception:
                    pass
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

    def link(self, source_id: int, target_id: int, relation: str) -> None:
        """Create an explicit causal edge in the durable memory graph."""
        self.store.link(source_id, target_id, relation)

    def environmental_stress(self, *, window: int = 24) -> float:
        """Estimate current build stress from recent execution outcomes.

        The score is deterministic and bounded to [0, 1]. Recent failures,
        consecutive failures and correction pressure raise stress; successful
        executions lower it.
        """
        if window < 1:
            raise ValueError("window must be >= 1")
        events = [
            episode for episode in self.store.query(agent_id="odyn_orchestrator")
            if episode.event_type.endswith("_result")
            and episode.payload.get("stage") in {"test", "build"}
        ][-window:]
        if not events:
            return 0.0

        weighted_failures = 0.0
        weighted_successes = 0.0
        weight_total = 0.0
        consecutive_failures = 0
        correction_pressure = 0.0
        for index, episode in enumerate(reversed(events), start=1):
            weight = 1.0 / index
            weight_total += weight
            if episode.payload.get("ok", False):
                weighted_successes += weight
                if consecutive_failures == 0:
                    correction_pressure *= 0.5
            else:
                weighted_failures += weight
                consecutive_failures += 1
                correction_pressure += weight

        failure_rate = weighted_failures / weight_total
        success_rate = weighted_successes / weight_total
        consecutive_pressure = min(consecutive_failures / 3.0, 1.0)
        correction_rate = min(correction_pressure / weight_total, 1.0)

        stress = (
            0.10
            + 0.55 * failure_rate
            + 0.20 * consecutive_pressure
            + 0.15 * correction_rate
            - 0.15 * success_rate
        )
        return round(max(0.0, min(1.0, stress)), 4)

    @staticmethod
    def _context_similarity(left: dict[str, Any], right: dict[str, Any]) -> float:
        """Return deterministic weighted similarity in [0, 1]."""
        weights = {"task_type": 0.40, "platform": 0.30, "architecture": 0.30}
        related = {
            "platform": [{"web", "browser"}, {"android", "mobile"}, {"ios", "mobile"}],
            "architecture": [
                {"react", "vue", "frontend"},
                {"android", "compose"},
                {"python", "fastapi", "django"},
            ],
        }
        score = 0.0
        weight_total = 0.0
        for key, weight in weights.items():
            left_value = str(left.get(key, "")).strip().lower()
            right_value = str(right.get(key, "")).strip().lower()
            if not left_value or not right_value:
                continue
            weight_total += weight
            if left_value == right_value:
                score += weight
            elif any(
                left_value in family and right_value in family
                for family in related.get(key, [])
            ):
                score += weight * 0.75
        return round(score / weight_total, 4) if weight_total else 0.0

    @staticmethod
    def _task_window(
        events: list[MemoryEpisode],
        plan: MemoryEpisode,
    ) -> list[MemoryEpisode]:
        """Return only events belonging to the task that owns the plan."""
        task_starts = [
            event for event in events
            if event.event_type == "task_started"
            and event.transaction_time_start <= plan.transaction_time_start
        ]
        if not task_starts:
            return []
        task_start = task_starts[-1]
        next_task = next(
            (
                event for event in events
                if event.event_type == "task_started"
                and event.transaction_time_start > task_start.transaction_time_start
            ),
            None,
        )
        app_id = str(plan.payload.get("app_id", ""))
        return [
            event for event in events
            if event.transaction_time_start > plan.transaction_time_start
            and (next_task is None or event.transaction_time_start < next_task.transaction_time_start)
            and (not app_id or str(event.payload.get("app_id", "")) == app_id)
        ]

    def meta_learning_context(
        self,
        context: dict[str, Any],
        *,
        recent_limit: int = 64,
        min_similarity: float = 0.5,
    ) -> dict[str, Any]:
        """Estimate strategy outcomes using similarity-weighted contextual evidence."""
        if recent_limit < 1:
            raise ValueError("recent_limit must be >= 1")
        if not 0.0 <= min_similarity <= 1.0:
            raise ValueError("min_similarity must be between 0 and 1")

        wanted = {
            str(key): str(value).strip().lower()
            for key, value in context.items()
            if value is not None
        }
        events = self.store.query(agent_id="odyn_orchestrator")
        plans = [
            episode for episode in events
            if episode.event_type == "cognitive_plan"
            and episode.payload.get("selected_strategy")
        ][-recent_limit:]

        stats: dict[str, dict[str, float]] = {}
        evidence: list[dict[str, Any]] = []
        ignored_evidence = 0

        for plan in plans:
            source_context = {
                str(key): str(value).strip().lower()
                for key, value in plan.payload.get("context", {}).items()
                if value is not None
            }
            similarity = self._context_similarity(wanted, source_context)
            if similarity < min_similarity:
                ignored_evidence += 1
                continue

            strategy = str(plan.payload.get("selected_strategy", "")).strip()
            if not strategy:
                continue

            window = self._task_window(events, plan)
            if any(event.event_type == "successful_procedure" for event in window):
                outcome = "success"
            elif any(
                event.event_type.endswith("_result")
                and event.payload.get("ok") is False
                for event in window
            ):
                outcome = "failure"
            else:
                continue

            item = stats.setdefault(strategy, {"successes": 0.0, "failures": 0.0})
            item["successes" if outcome == "success" else "failures"] += similarity
            evidence.append({
                "strategy": strategy,
                "outcome": outcome,
                "similarity": similarity,
                "weight": similarity,
                "transaction_time": plan.transaction_time_start.isoformat(),
                "context": source_context,
            })

        evidence.sort(key=lambda item: item["transaction_time"])
        weighted_evidence = sum(item["weight"] for item in evidence)
        return {
            "context": wanted,
            "strategy_stats": stats,
            "evidence": evidence[-recent_limit:],
            "evidence_count": len(evidence),
            "weighted_evidence": round(weighted_evidence, 4),
            "ignored_evidence_count": ignored_evidence,
            "min_similarity": min_similarity,
        }

    def history_context(
        self,
        *,
        historical_transaction_at: datetime | None = None,
        valid_at: datetime | None = None,
        recent_limit: int = 8,
    ) -> dict[str, Any]:
        """Build a compact, structured context for history-aware reasoning."""
        if recent_limit < 1:
            raise ValueError("recent_limit must be >= 1")

        current = self.store.query(agent_id="odyn_orchestrator")
        historical_snapshot = None
        if historical_transaction_at is not None:
            snapshot = self.store.memory_snapshot(
                valid_at=valid_at or historical_transaction_at,
                transaction_at=historical_transaction_at,
            )
            historical_snapshot = {
                "valid_at": snapshot.valid_at.isoformat(),
                "transaction_at": snapshot.transaction_at.isoformat(),
                "episodic_count": len(snapshot.episodic),
                "procedural_count": len(snapshot.procedural),
                "edge_count": len(snapshot.edges),
                "procedures": [
                    {
                        "skill_name": skill.skill_name,
                        "code_reference": skill.code_reference,
                        "fitness_score": skill.fitness_score,
                    }
                    for skill in snapshot.procedural[-recent_limit:]
                ],
            }

        successes = [
            episode for episode in current
            if episode.event_type == "successful_procedure"
        ]
        failures = [
            episode for episode in current
            if episode.event_type.endswith("_result")
            and episode.payload.get("ok") is False
        ]
        corrections = [
            episode for episode in current
            if episode.event_type == "correction"
        ]

        strategy_stats: dict[str, dict[str, int]] = {}
        plans = [
            episode for episode in current
            if episode.event_type == "cognitive_plan"
            and episode.payload.get("selected_strategy")
        ]
        for index, plan in enumerate(plans):
            strategy = str(plan.payload["selected_strategy"])
            next_plan_time = plans[index + 1].transaction_time_start if index + 1 < len(plans) else None
            window = [
                episode for episode in current
                if episode.transaction_time_start > plan.transaction_time_start
                and (next_plan_time is None or episode.transaction_time_start < next_plan_time)
            ]
            stats = strategy_stats.setdefault(strategy, {"successes": 0, "failures": 0})
            if any(item.event_type == "successful_procedure" for item in window):
                stats["successes"] += 1
            elif any(item.event_type.endswith("_result") and item.payload.get("ok") is False for item in window):
                stats["failures"] += 1

        def compact(episodes: list[MemoryEpisode]) -> list[dict[str, Any]]:
            return [
                {
                    "id": episode.id,
                    "event_type": episode.event_type,
                    "payload": episode.payload,
                    "transaction_time": episode.transaction_time_start.isoformat(),
                }
                for episode in episodes[-recent_limit:]
            ]

        return {
            "current_memory": compact(current),
            "historical_snapshot": historical_snapshot,
            "successful_procedures": compact(successes),
            "failed_procedures": compact(failures),
            "corrections": compact(corrections),
            "strategy_stats": strategy_stats,
        }

    def snapshot(self) -> list[MemoryEpisode]:
        if self._last_task_id is None:
            return []
        return self.store.query(agent_id="odyn_orchestrator")

    @staticmethod
    def compact_result(result: Any) -> dict[str, Any]:
        if hasattr(result, "__dict__"):
            return json.loads(json.dumps(result.__dict__, default=str))
        return dict(result)
