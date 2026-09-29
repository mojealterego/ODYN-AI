from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from odyn_ai.core.coding_agent import CodingAgent
from odyn_ai.core.execution import ExecutionEngine, ExecutionRequest
from odyn_ai.core.github_integration import GitHubIntegration
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
    ) -> None:
        self.apps = apps
        self.execution = engine
        self.coding_agent = coding_agent
        self.github = github
        self.memory = memory
        self.max_corrections = max(0, max_corrections)

    def _remember(self, method: str, *args, **kwargs) -> None:
        if not self.memory:
            return
        try:
            getattr(self.memory, method)(*args, **kwargs)
        except Exception:
            # Persistence/RAG is advisory. It must never break a build.
            return

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

        self._remember(
            "record_correction",
            app_id,
            stage,
            diagnostics,
            changes,
        )
        self._remember(
            "record_decision",
            app_id,
            failure,
            edited.get("summary", ""),
            changes,
        )
        self._remember("record_changes", app_id, changes)
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
    ):
        result = await self.execution.execute(
            ExecutionRequest(platform, stage, files, timeout)
        )
        result_dict = asdict(result)
        self._remember("record_execution", app_id, stage, result_dict)

        if result.ok or not allow_correction:
            return files, [], result

        files, changes, corrected = await self._correct(
            app_id, platform, files, stage, result_dict
        )
        if not corrected:
            return files, [], result

        retry = await self.execution.execute(
            ExecutionRequest(platform, stage, files, timeout)
        )
        self._remember("record_execution", app_id, f"{stage}_retry", asdict(retry))
        return files, changes, retry

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

        if self.memory:
            try:
                task = self.memory.start_task(app_id, instruction, platform)
                memory_events.append(task.id)
            except Exception:
                pass

        context = self.memory.recall(instruction, top_k=4) if self.memory else ""
        edited = await self._apply(platform, instruction, files, memory_context=context)
        initial_changes = self._persist_changes(app_id, files, edited)
        files = dict(edited["files"])
        changes.extend(initial_changes)

        if self.memory:
            try:
                memory_events.append(
                    self.memory.record_decision(
                        app_id, instruction, edited.get("summary", ""), initial_changes
                    ).id
                )
                memory_events.extend(
                    item.id for item in self.memory.record_changes(app_id, initial_changes)
                )
            except Exception:
                pass

        files, test_changes, test = await self._execute_stage(
            app_id, platform, files, "test", timeout,
            allow_correction=self.max_corrections > 0,
        )
        changes.extend(test_changes)

        if not test.ok:
            return PipelineResult(
                app_id, False, changes, asdict(test), None, None,
                "test",
                test.diagnostics + ["Build został zatrzymany, ponieważ testy nie przeszły."],
                memory_events,
            )

        files, build_changes, build = await self._execute_stage(
            app_id, platform, files, "build", timeout,
            allow_correction=self.max_corrections > 0,
        )
        changes.extend(build_changes)

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
