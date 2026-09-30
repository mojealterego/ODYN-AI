from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from odyn_ai.core.coding_agent import CodingAgent
from odyn_ai.core.execution import ExecutionEngine, ExecutionRequest
from odyn_ai.core.github_integration import GitHubIntegration
from nexus_core.reasoning.cognitive_engine import CognitiveEngine
from odyn_ai.core.experience_memory import AgentExperienceMemory


@dataclass
class PipelineResult:
    app_id: str
    ok: bool
    changes: list[dict[str, str]]
    test: dict[str, Any]
    build: dict[str, Any] | None
    github: dict[str, Any] | None
    stage: str
    diagnostics: list[str]
    memory_events: list[int] = field(default_factory=list)
    cognitive_graph: dict[str, Any] = field(default_factory=dict)


class AutonomousBuildOrchestrator:
    """ODYN edit -> test -> correction -> build -> verify -> GitHub pipeline."""

    def __init__(
        self,
        apps,
        engine,
        coding_agent: CodingAgent,
        github: GitHubIntegration,
        memory: AgentExperienceMemory | None = None,
        *,
        max_corrections: int = 1,
        cognitive_engine: CognitiveEngine | None = None,
    ) -> None:
        self.apps = apps
        self.execution = engine
        self.coding_agent = coding_agent
        self.github = github
        self.memory = memory
        self.max_corrections = max(0, max_corrections)
        self.cognitive = cognitive_engine or CognitiveEngine()

    def _remember(self, method: str, *args, **kwargs) -> None:
        if not self.memory:
            return
        try:
            getattr(self.memory, method)(*args, **kwargs)
        except Exception:
            # Persistence/RAG is advisory. It must never break a build.
            return

    def _remember_episode(self, method: str, *args, **kwargs) -> int | None:
        if not self.memory:
            return None
        try:
            episode = getattr(self.memory, method)(*args, **kwargs)
            return getattr(episode, "id", None)
        except Exception:
            return None

    def _link_memory(self, source_id: int | None, target_id: int | None, relation: str) -> None:
        if not self.memory or source_id is None or target_id is None:
            return
        try:
            self.memory.link(source_id, target_id, relation)
        except Exception:
            return

    def _remember_change_episodes(
        self,
        app_id: str,
        changes: list[dict[str, str]],
        *,
        decision_id: int | None = None,
    ) -> list[int]:
        if not self.memory:
            return []
        try:
            episodes = self.memory.record_changes(
                app_id, changes, decision_id=decision_id
            )
        except TypeError:
            try:
                episodes = self.memory.record_changes(app_id, changes)
            except Exception:
                return []
        except Exception:
            return []
        return [episode.id for episode in episodes if getattr(episode, "id", None) is not None]

    def _cognitive_strategy_scores(
        self, instruction: str, files: dict[str, str], memory_context: str
    ) -> dict[str, float]:
        text = f"{instruction} {memory_context}".lower()
        scores = {"minimal_patch": 0.75, "test_first": 0.85, "architecture": 0.55}
        if any(word in text for word in ("refactor", "architecture", "architekt", "redesign")):
            scores["architecture"] += 0.35
        if any(word in text for word in ("failure", "fail", "błąd", "error", "napraw", "korekta")):
            scores["test_first"] += 0.10
        if len(files) >= 10:
            scores["test_first"] += 0.05
            scores["architecture"] += 0.05
        if any(word in text for word in ("simple", "prosty", "small", "mała")):
            scores["minimal_patch"] += 0.10
        return scores

    def _cognitive_snapshot(self, selected_strategy: str) -> dict[str, Any]:
        snapshot = self.cognitive.snapshot()
        snapshot["selected_strategy"] = selected_strategy
        return snapshot
    async def _apply(
        self,
        platform: str,
        instruction: str,
        files: dict[str, str],
        *,
        memory_context: str = "",
    ) -> dict[str, Any]:
        if memory_context:
            try:
                return await self.coding_agent.apply(
                    platform, instruction, files, memory_context=memory_context
                )
            except TypeError:
                # Compatibility with third-party/test CodingAgent implementations.
                pass
        return await self.coding_agent.apply(platform, instruction, files)

    def _persist_changes(
        self,
        app_id: str,
        previous: dict[str, str],
        edited: dict[str, Any],
    ) -> list[dict[str, str]]:
        changes = [
            change for change in edited.get("changes", [])
            if previous.get(change["path"]) != change["content"]
        ]
        for path, content in edited["files"].items():
            if previous.get(path) != content:
                self.apps.write_file(app_id, path, content)
        return changes

    async def _correct(
        self,
        app_id: str,
        platform: str,
        files: dict[str, str],
        stage: str,
        result: dict[str, Any],
        *,
        failed_execution_id: int | None = None,
    ) -> tuple[dict[str, str], list[dict[str, str]], bool]:
        diagnostics = list(result.get("diagnostics", []))
        failure = (
            f"KOREKTA AUTONOMICZNA. Etap: {stage}. "
            f"Napraw błąd na podstawie diagnostyki, zachowując istniejącą funkcjonalność. "
            f"Diagnostyka: {' | '.join(diagnostics)}. "
            f"STDERR: {result.get('stderr', '')[-6000:]}"
        )
        context = self.memory.recall(failure, top_k=4) if self.memory else ""
        edited = await self._apply(platform, failure, files, memory_context=context)
        changes = self._persist_changes(app_id, files, edited)
        if not changes:
            return files, [], False

        correction_id = self._remember_episode(
            "record_correction",
            app_id,
            stage,
            diagnostics,
            changes,
            failed_execution_id=failed_execution_id,
        )
        decision_id = self._remember_episode(
            "record_decision",
            app_id,
            failure,
            edited.get("summary", ""),
            changes,
        )
        self._link_memory(decision_id, correction_id, "corrects")
        change_ids = self._remember_change_episodes(
            app_id, changes, decision_id=decision_id
        )
        for change_id in change_ids:
            self._link_memory(change_id, failed_execution_id, "changed_before")
        return dict(edited["files"]), changes, True

    async def _execute_stage(
        self,
        app_id: str,
        platform: str,
        files: dict[str, str],
        stage: str,
        timeout: float,
        *,
        allow_correction: bool,
        cognitive_task: str | None = None,
        cognitive_parent_id: str | None = None,
    ):
        result = await self.execution.execute(
            ExecutionRequest(platform, stage, files, timeout)
        )
        result_dict = asdict(result)
        failed_execution_id = self._remember_episode(
            "record_execution", app_id, stage, result_dict
        )

        if result.ok or not allow_correction:
            return files, [], result, failed_execution_id

        failure_text = (
            f"{stage} failed for {app_id}: "
            f"{' | '.join(result_dict.get('diagnostics', []))} "
            f"{result_dict.get('stderr', '')[-2000:]}"
        )
        failure_node = self.cognitive.add_thought(
            "failure",
            failure_text,
            parent_id=cognitive_parent_id,
            metadata={"stage": stage},
        )
        reflexion_node = self.cognitive.record_reflexion(
            cognitive_task or stage,
            failure_text,
            parent_id=failure_node,
        )
        self._remember_episode(
            "record_reflexion",
            app_id,
            stage,
            failure_text,
            failed_execution_id=failed_execution_id,
            cognitive_node_id=reflexion_node,
        )

        files, changes, corrected = await self._correct(
            app_id,
            platform,
            files,
            stage,
            result_dict,
            failed_execution_id=failed_execution_id,
        )
        if not corrected:
            return files, [], result, failed_execution_id

        self.cognitive.add_thought(
            "correction",
            f"{stage}: corrected {', '.join(item['path'] for item in changes)}",
            parent_id=reflexion_node,
            metadata={"changed_paths": [item["path"] for item in changes]},
        )

        retry = await self.execution.execute(
            ExecutionRequest(platform, stage, files, timeout)
        )
        retry_execution_id = self._remember_episode(
            "record_execution", app_id, f"{stage}_retry", asdict(retry)
        )
        return files, changes, retry, retry_execution_id

    async def run(
        self,
        app_id: str,
        instruction: str,
        timeout: float = 300,
        github_repository: str | None = None,
        github_branch: str = "main",
        github_message: str = "feat(odyn): autonomous project update",
    ) -> PipelineResult:
        project = self.apps.workspace(app_id)
        platform = project["platform"]
        files = dict(project["files"])
        memory_events: list[int] = []
        changes: list[dict[str, str]] = []
        task_id: int | None = None

        if self.memory:
            try:
                task_id = self.memory.start_task(app_id, instruction, platform).id
                memory_events.append(task_id)
            except Exception:
                pass

        context = self.memory.recall(instruction, top_k=4) if self.memory else ""
        task_node_id = self.cognitive.add_thought("task", instruction)
        strategy_scores = self._cognitive_strategy_scores(instruction, files, context)
        strategies = ["minimal_patch", "test_first", "architecture"]
        plan = self.cognitive.plan_build(
            instruction,
            strategies,
            lambda _node, action: strategy_scores[action],
            parent_id=task_node_id,
        )
        selected_strategy = plan["selected_strategy"]

        plan_memory_id = self._remember_episode(
            "record_cognitive_plan",
            app_id,
            instruction,
            strategies,
            selected_strategy,
            cognitive_node_id=plan["root_id"],
        )
        if plan_memory_id is not None:
            memory_events.append(plan_memory_id)
        for strategy, node_id in zip(strategies, plan["branch_ids"]):
            strategy_memory_id = self._remember_episode(
                "record_cognitive_strategy",
                app_id,
                strategy,
                selected=strategy == selected_strategy,
                cognitive_node_id=node_id,
            )
            if strategy_memory_id is not None:
                memory_events.append(strategy_memory_id)

        selected_instruction = (
            f"[ODYN COGNITIVE STRATEGY: {selected_strategy}] "
            f"Apply the selected build strategy deliberately. "
            f"Original task: {instruction}"
        )
        edited = await self._apply(
            platform, selected_instruction, files, memory_context=context
        )
        initial_changes = self._persist_changes(app_id, files, edited)
        files = dict(edited["files"])
        changes.extend(initial_changes)

        decision_node_id = self.cognitive.add_thought(
            "coding_decision",
            edited.get("summary", ""),
            parent_id=plan["selected_id"],
            metadata={"strategy": selected_strategy},
        )
        decision_id = self._remember_episode(
            "record_decision",
            app_id,
            selected_instruction,
            edited.get("summary", ""),
            initial_changes,
            cognitive_strategy=selected_strategy,
            cognitive_node_id=decision_node_id,
        )
        if decision_id is not None:
            memory_events.append(decision_id)
        initial_change_ids = self._remember_change_episodes(
            app_id, initial_changes, decision_id=decision_id
        )
        memory_events.extend(initial_change_ids)
        self._link_memory(task_id, decision_id, "decided_by")

        files, test_changes, test, test_memory_id = await self._execute_stage(
            app_id, platform, files, "test", timeout,
            allow_correction=self.max_corrections > 0,
            cognitive_task=instruction,
            cognitive_parent_id=decision_node_id,
        )
        changes.extend(test_changes)
        if test_memory_id is not None:
            memory_events.append(test_memory_id)

        if not test.ok:
            return PipelineResult(
                app_id, False, changes, asdict(test), None, None,
                "test",
                test.diagnostics + ["Build został zatrzymany, ponieważ testy nie przeszły."],
                memory_events,
            )

        files, build_changes, build, build_memory_id = await self._execute_stage(
            app_id, platform, files, "build", timeout,
            allow_correction=self.max_corrections > 0,
            cognitive_task=instruction,
            cognitive_parent_id=decision_node_id,
        )
        changes.extend(build_changes)
        if build_memory_id is not None:
            memory_events.append(build_memory_id)

        if not build.ok:
            return PipelineResult(
                app_id, False, changes, asdict(test), asdict(build), None,
                "build",
                build.diagnostics + ["Weryfikacja artefaktu nie powiodła się."],
                memory_events,
            )

        self._remember(
            "record_success",
            app_id,
            platform,
            "verified",
            build.artifact,
            source_execution_id=build_memory_id,
        )

        github_result = None
        if github_repository:
            github_result = asdict(await self.github.commit_files(
                github_repository, files, github_message, github_branch, False
            ))

        return PipelineResult(
            app_id, True, changes, asdict(test), asdict(build),
            github_result, "verified",
            ["Testy PASS", "Build PASS", "Artefakt zweryfikowany."],
            memory_events,
        )
